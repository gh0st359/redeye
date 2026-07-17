"""The RedEye agent loop.

One run = one investigation. The loop alternates model turns and tool calls,
with four pieces of machinery wrapped around it:

  * permissions   — every call is checked against the mode policy
  * guardrails    — LoopGuard watches for repetition, error spirals, budgets
  * context       — old tool output is compressed as the window fills
  * case + session — findings and the full transcript are persisted live

The loop is event-driven: callers (TUI, one-shot runner, tests) subscribe via
`emit` and decide how to render. Approval requests flow through `approval_fn`
so headless runs can auto-decide.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from . import context as ctx_mgr
from .case import CaseStore
from .config import Config
from .guardrails import GuardConfig, LoopGuard
from .llm import BaseLLM
from .permissions import Decision, PermissionPolicy
from .reporting import generate_report
from .session import Session
from .skills import Skill

EventFn = Callable[[str, dict], None]
ApprovalFn = Callable[[str, str, dict], tuple[bool, bool]]  # (approved, remember)


@dataclass
class RunResult:
    final_text: str
    report_path: Optional[Path]
    stopped_reason: Optional[str]
    stats: dict


class Agent:
    def __init__(
        self,
        *,
        cfg: Config,
        llm: BaseLLM,
        registry,
        policy: PermissionPolicy,
        case: CaseStore,
        session: Session,
        skills: dict[str, Skill],
        system_prompt: str,
        emit: EventFn,
        approval_fn: Optional[ApprovalFn] = None,
    ):
        self.cfg = cfg
        self.llm = llm
        self.registry = registry
        self.policy = policy
        self.case = case
        self.session = session
        self.skills = skills
        self.system_prompt = system_prompt
        self.emit = emit
        self.approval_fn = approval_fn or (lambda name, tier, args: (True, False))
        self.guard = LoopGuard(
            GuardConfig(
                max_steps=cfg.max_steps,
                max_wall_seconds=cfg.max_wall_seconds,
            )
        )

    # ------------------------------------------------------------------ #
    def run(self, goal: str, prior_messages: Optional[list[dict]] = None) -> RunResult:
        messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        if prior_messages:
            messages += [m for m in prior_messages if m.get("role") != "system"]
        messages.append({"role": "user", "content": goal})
        for m in messages:
            if m not in self.session.messages:
                self.session.append_message(m)

        final_text = ""
        stopped_reason: Optional[str] = None
        tools_schema = self.registry.openai_tools()

        while True:
            budget = self.guard.budget_check()
            if budget.stop:
                stopped_reason = budget.reason
                self.emit("warning", {"message": f"Run halted: {budget.reason}"})
                final_text = self._final_synthesis(messages)
                break

            self.guard.record_step()
            self.emit("step", {"n": self.guard.steps})
            fitted = ctx_mgr.fit(messages, self.cfg.context_token_budget)

            try:
                response = self.llm.complete(
                    fitted, tools=tools_schema, on_token=lambda t: self.emit("token", {"text": t})
                )
            except Exception as exc:  # noqa: BLE001
                stopped_reason = f"LLM error: {type(exc).__name__}: {exc}"
                self.emit("warning", {"message": stopped_reason})
                break

            self.emit("assistant_turn_end", {"content": response.content})

            if not response.tool_calls:
                final_text = response.content
                messages.append({"role": "assistant", "content": response.content})
                self.session.append_message(messages[-1])
                break

            assistant_msg = {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ],
            }
            messages.append(assistant_msg)
            self.session.append_message(assistant_msg)

            hard_stop: Optional[str] = None
            for tc in response.tool_calls:
                tool_msg, verdict = self._execute_tool(tc)
                messages.append(tool_msg)
                self.session.append_message(tool_msg)
                if verdict and verdict.stop:
                    hard_stop = verdict.reason
                    break

            if hard_stop:
                stopped_reason = hard_stop
                self.emit("warning", {"message": f"Run halted: {hard_stop}"})
                final_text = self._final_synthesis(messages)
                break

        # ---------------- wrap up: report ---------------- #
        report_path: Optional[Path] = None
        try:
            report_path = generate_report(
                self.case,
                final_summary=final_text,
                model=self.cfg.model,
                guard_stats=self.guard.stats(),
                session_id=self.session.session_id,
                reports_dir=self.cfg.reports_dir,
            )
            self.emit("report", {"path": str(report_path)})
        except Exception as exc:  # noqa: BLE001
            self.emit("warning", {"message": f"report generation failed: {exc}"})

        return RunResult(
            final_text=final_text,
            report_path=report_path,
            stopped_reason=stopped_reason,
            stats=self.guard.stats(),
        )

    # ------------------------------------------------------------------ #
    def _execute_tool(self, tc) -> tuple[dict, Any]:
        tool = self.registry.get(tc.name)
        tier = tool.tier if tool else "passive"

        verdict = self.guard.record_call(tc.name, tc.arguments)
        if verdict.stop:
            msg = {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": f"BLOCKED BY HARNESS: {verdict.reason}",
            }
            self.emit("tool_result", {
                "name": tc.name, "ok": False, "preview": verdict.reason, "elapsed": 0.0,
            })
            return msg, verdict

        # permission gate
        decision = self.policy.decide(tc.name, tier)
        approved = decision != Decision.DENY
        if decision == Decision.ASK:
            self.emit("tool_call", {"name": tc.name, "args": tc.arguments, "tier": tier, "needs_approval": True})
            ok, remember = self.approval_fn(tc.name, tier, tc.arguments)
            approved = ok
            if remember:
                self.policy.remember(tc.name, ok)
        else:
            self.emit("tool_call", {"name": tc.name, "args": tc.arguments, "tier": tier, "needs_approval": False})

        if not approved:
            content = (
                f"DENIED: the operator declined `{tc.name}` (tier={tier}, mode={self.policy.mode}). "
                "Do not retry this tool; continue with permitted sources."
            )
            self.emit("tool_result", {"name": tc.name, "ok": False, "preview": "denied by operator", "elapsed": 0.0})
            self.guard.record_result(ok=True)  # a denial is not an environment failure
            return {"role": "tool", "tool_call_id": tc.id, "content": content}, None

        started = time.monotonic()
        result = self.registry.execute(tc.name, tc.arguments)
        elapsed = time.monotonic() - started

        err_verdict = self.guard.record_result(ok=result.ok)
        content = result.content
        notes = [n for n in (verdict.steering, err_verdict.steering) if n]
        if notes:
            content += "\n\n" + "\n".join(notes)
            for n in notes:
                self.emit("steering", {"message": n})

        preview = result.content.replace("\n", " ")[:220]
        self.emit("tool_result", {
            "name": tc.name, "ok": result.ok, "preview": preview,
            "elapsed": round(elapsed, 2), "truncated": result.truncated,
        })
        self.session.log_event("tool", {
            "name": tc.name, "args": tc.arguments, "ok": result.ok, "elapsed": round(elapsed, 2),
        })
        msg = {"role": "tool", "tool_call_id": tc.id, "content": content}
        if err_verdict.stop:
            return msg, err_verdict
        return msg, None

    # ------------------------------------------------------------------ #
    def _final_synthesis(self, messages: list[dict]) -> str:
        """Force a closing summary when the loop was interrupted."""
        prompt = (
            "The run was stopped by the harness. Using ONLY what you have already collected, "
            "deliver the executive summary now: key findings with confidence, gaps, next steps. "
            "Do not call any tools."
        )
        synth = messages + [{"role": "user", "content": prompt}]
        try:
            resp = self.llm.complete(
                ctx_mgr.fit(synth, self.cfg.context_token_budget), tools=None,
                on_token=lambda t: self.emit("token", {"text": t}),
            )
            return resp.content or "(no summary produced)"
        except Exception as exc:  # noqa: BLE001
            self.emit("warning", {"message": f"final synthesis failed: {exc}"})
            return "(run interrupted before a summary could be generated)"
