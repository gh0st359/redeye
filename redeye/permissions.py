"""Permission modes and per-tool risk policy.

Every tool in RedEye carries a risk tier:

  passive   — queries a third-party public data source (search engines, DNS,
              certificate transparency, archives, public APIs). Never touches
              the subject's own infrastructure.
  active    — sends a request to infrastructure associated with the subject
              (e.g. fetching the subject's own website headers). Still a plain
              HTTP GET, but it is visible to the subject.
  sensitive — anything with side effects: writing local files outside the case
              store, or MCP tools that do not declare themselves read-only.

Modes:
  readonly  — passive: allow.   active: ask.     sensitive: deny.
  balanced  — passive: allow.   active: ask once (then remembered).  sensitive: ask.
  fullauto  — allow everything, no prompts. For sandboxed/headless use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Decision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


MODE_DESCRIPTIONS = {
    "readonly": "passive sources only; anything that touches the subject requires approval",
    "balanced": "passive sources run freely; active/sensitive tools ask once",
    "fullauto": "no prompts — everything runs (use in sandboxes only)",
}


@dataclass
class PermissionPolicy:
    mode: str = "balanced"
    _always_allow: set[str] = field(default_factory=set)
    _always_deny: set[str] = field(default_factory=set)

    def decide(self, tool_name: str, tier: str) -> Decision:
        if tool_name in self._always_deny:
            return Decision.DENY
        if tool_name in self._always_allow:
            return Decision.ALLOW

        if self.mode == "fullauto":
            return Decision.ALLOW
        if self.mode == "readonly":
            if tier == "passive":
                return Decision.ALLOW
            if tier == "active":
                return Decision.ASK
            return Decision.DENY
        # balanced
        if tier == "passive":
            return Decision.ALLOW
        return Decision.ASK

    def remember(self, tool_name: str, allow: bool) -> None:
        (self._always_allow if allow else self._always_deny).add(tool_name)

    def set_mode(self, mode: str) -> None:
        if mode not in MODE_DESCRIPTIONS:
            raise ValueError(f"mode must be one of {list(MODE_DESCRIPTIONS)}")
        self.mode = mode
        self._always_allow.clear()
        self._always_deny.clear()
