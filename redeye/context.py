"""Context-window management.

Models choke quietly when you stuff 200 tool results into context. RedEye
estimates tokens (chars/4, a robust approximation) and, past the configured
budget, compresses *older tool outputs* — which are almost always the bloat —
while preserving the system prompt, the goal, and the most recent turns
verbatim. Compressed content keeps head and tail with a marker, so the model
retains conclusions and can re-fetch if it truly needs the middle.
"""
from __future__ import annotations

from typing import Any

KEEP_RECENT_MESSAGES = 8      # never touch the last N messages
TOOL_HEAD = 900               # chars kept from the start of an old tool result
TOOL_TAIL = 300


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            total += sum(len(str(part)) for part in content)
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            total += len(fn.get("name", "")) + len(fn.get("arguments", ""))
    return total // 4 + 100


def _compress_tool_message(msg: dict, aggressive: bool) -> dict:
    content = msg.get("content", "")
    if not isinstance(content, str) or len(content) <= TOOL_HEAD + TOOL_TAIL + 200:
        return msg
    if aggressive:
        compressed = f"[earlier tool output omitted to save context — {len(content)} chars; re-run the tool if needed]"
    else:
        compressed = (
            content[:TOOL_HEAD]
            + f"\n[...{len(content) - TOOL_HEAD - TOOL_TAIL} chars compressed...]\n"
            + content[-TOOL_TAIL:]
        )
    new = dict(msg)
    new["content"] = compressed
    return new


def fit(messages: list[dict[str, Any]], budget_tokens: int) -> list[dict[str, Any]]:
    if estimate_tokens(messages) <= budget_tokens:
        return messages

    boundary = max(1, len(messages) - KEEP_RECENT_MESSAGES)
    # Pass 1: soft compression of old tool messages
    pass1 = [
        _compress_tool_message(m, aggressive=False) if (i < boundary and m.get("role") == "tool") else m
        for i, m in enumerate(messages)
    ]
    if estimate_tokens(pass1) <= budget_tokens:
        return pass1
    # Pass 2: aggressive omission of old tool messages
    pass2 = [
        _compress_tool_message(m, aggressive=True) if (i < boundary and m.get("role") == "tool") else m
        for i, m in enumerate(messages)
    ]
    return pass2
