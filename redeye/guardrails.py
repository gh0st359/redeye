"""Anti-loop guardrails for the agent harness.

Agents fail in boring ways: calling the same tool with the same arguments
forever, hammering an endpoint that keeps erroring, or wandering past any
reasonable step budget. LoopGuard watches the tool-call stream and either
injects steering feedback (soft intervention) or forces the run to end
(hard stop) before the model burns the budget.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GuardConfig:
    max_steps: int = 40                 # one "step" = one LLM turn
    max_wall_seconds: int = 900
    repeat_soft_threshold: int = 2      # identical call seen N times -> steer
    repeat_hard_threshold: int = 4      # identical call seen N times -> hard stop
    error_soft_threshold: int = 3       # consecutive errors -> steer
    error_hard_threshold: int = 6       # consecutive errors -> hard stop
    per_tool_soft_cap: int = 12         # total calls of one tool -> steer
    per_tool_hard_cap: int = 20         # total calls of one tool -> hard stop


@dataclass
class GuardVerdict:
    stop: bool = False
    reason: Optional[str] = None        # human-facing reason when stopping
    steering: Optional[str] = None      # message injected into the tool result


class LoopGuard:
    def __init__(self, cfg: GuardConfig):
        self.cfg = cfg
        self.steps = 0
        self.started = time.monotonic()
        self._call_counts: dict[str, int] = {}
        self._tool_counts: dict[str, int] = {}
        self._consecutive_errors = 0
        self._steered: set[str] = set()  # keys we've already nudged about

    # ------------------------------------------------------------------ #
    @staticmethod
    def _fingerprint(tool: str, args: dict) -> str:
        blob = tool + "::" + json.dumps(args, sort_keys=True, default=str)
        return hashlib.sha1(blob.encode()).hexdigest()

    def record_step(self) -> None:
        self.steps += 1

    def record_call(self, tool: str, args: dict) -> GuardVerdict:
        fp = self._fingerprint(tool, args)
        self._call_counts[fp] = self._call_counts.get(fp, 0) + 1
        self._tool_counts[tool] = self._tool_counts.get(tool, 0) + 1
        n_identical = self._call_counts[fp]
        n_tool = self._tool_counts[tool]

        if n_identical >= self.cfg.repeat_hard_threshold:
            return GuardVerdict(
                stop=True,
                reason=f"called `{tool}` with identical arguments {n_identical} times — looping",
            )
        if n_tool >= self.cfg.per_tool_hard_cap:
            return GuardVerdict(
                stop=True,
                reason=f"used `{tool}` {n_tool} times in one run — no progress",
            )
        steering = None
        if n_identical >= self.cfg.repeat_soft_threshold and fp not in self._steered:
            self._steered.add(fp)
            steering = (
                f"SYSTEM NOTE: you have already called {tool} with these exact arguments "
                f"{n_identical} times. Repeating it will not produce new information. "
                "Change the query, pivot to a different source, or move on."
            )
        elif n_tool >= self.cfg.per_tool_soft_cap and f"t:{tool}" not in self._steered:
            self._steered.add(f"t:{tool}")
            steering = (
                f"SYSTEM NOTE: {tool} has been used {n_tool} times this run. "
                "If it is not yielding new leads, switch to a different tool or start "
                "synthesizing what you already have."
            )
        return GuardVerdict(steering=steering)

    def record_result(self, ok: bool) -> GuardVerdict:
        self._consecutive_errors = 0 if ok else self._consecutive_errors + 1
        if self._consecutive_errors >= self.cfg.error_hard_threshold:
            return GuardVerdict(
                stop=True,
                reason=f"{self._consecutive_errors} consecutive tool errors — environment is unhealthy",
            )
        if self._consecutive_errors >= self.cfg.error_soft_threshold:
            return GuardVerdict(
                steering=(
                    f"SYSTEM NOTE: the last {self._consecutive_errors} tool calls failed. "
                    "Stop retrying the same failing approach. Check parameters, try a different "
                    "source, or proceed with the data you already have and note the gap."
                )
            )
        return GuardVerdict()

    def budget_check(self) -> GuardVerdict:
        if self.steps >= self.cfg.max_steps:
            return GuardVerdict(
                stop=True, reason=f"step budget exhausted ({self.cfg.max_steps} steps)"
            )
        elapsed = time.monotonic() - self.started
        if elapsed >= self.cfg.max_wall_seconds:
            return GuardVerdict(
                stop=True, reason=f"wall-clock budget exhausted ({int(elapsed)}s)"
            )
        return GuardVerdict()

    def stats(self) -> dict:
        return {
            "steps": self.steps,
            "elapsed_s": round(time.monotonic() - self.started, 1),
            "unique_calls": len(self._call_counts),
            "tools_used": dict(self._tool_counts),
        }
