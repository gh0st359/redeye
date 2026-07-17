"""Tool primitives and the central registry.

A Tool is a pure function with a JSON-schema signature, a risk tier used by
the permission policy, and a timeout. Handlers return ToolResult; the registry
turns exceptions into structured error results so a flaky source never crashes
a run.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

RiskTier = str  # "passive" | "active" | "sensitive"

MAX_RESULT_CHARS = 12_000  # keep individual tool outputs digestible for the model


@dataclass
class ToolResult:
    ok: bool
    content: str
    data: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False

    @classmethod
    def error(cls, message: str) -> "ToolResult":
        return cls(ok=False, content=f"ERROR: {message}")


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema (object)
    handler: Callable[..., ToolResult]
    tier: RiskTier = "passive"
    timeout: float = 30.0
    origin: str = "builtin"  # "builtin" | "mcp:<server>"

    def openai_schema(self) -> dict:
        params = dict(self.parameters)
        params.setdefault("type", "object")
        params.setdefault("properties", {})
        params.pop("$schema", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def tool(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        tier: RiskTier = "passive",
        timeout: float = 30.0,
    ) -> Callable:
        """Decorator form of register()."""

        def wrap(fn: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
            self.register(
                Tool(
                    name=name,
                    description=description,
                    parameters=parameters,
                    handler=fn,
                    tier=tier,
                    timeout=timeout,
                )
            )
            return fn

        return wrap

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def tiers(self) -> dict[str, RiskTier]:
        return {n: t.tier for n, t in self._tools.items()}

    def openai_tools(self) -> list[dict]:
        return [t.openai_schema() for t in self._tools.values()]

    def execute(self, name: str, args: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult.error(f"unknown tool {name!r}. Available: {', '.join(self.names())}")
        started = time.monotonic()
        try:
            result = tool.handler(**(args or {}))
        except TypeError as exc:
            return ToolResult.error(f"bad arguments for {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 — a source must never kill a run
            return ToolResult.error(f"{name} failed: {type(exc).__name__}: {exc}")
        finally:
            _ = started  # timing handled by caller via events
        if len(result.content) > MAX_RESULT_CHARS:
            head = result.content[: MAX_RESULT_CHARS - 400]
            tail = result.content[-300:]
            result.content = head + f"\n\n[...truncated {len(result.content) - len(head) - 300} chars...]\n\n" + tail
            result.truncated = True
        return result
