"""LLM provider layer.

RedEye talks to any OpenAI-compatible chat-completions endpoint with function
calling: OpenRouter, Ollama (/v1), LM Studio, vLLM, llama.cpp server, etc.
A deterministic "echo" provider is included so the harness can be exercised
with no network and no API key.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .config import Config


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"


class BaseLLM:
    def complete(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> LLMResponse:
        raise NotImplementedError


class OpenAICompatLLM(BaseLLM):
    def __init__(self, cfg: Config):
        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": cfg.api_key or "redeye-local", "timeout": 180.0}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        if cfg.default_headers:
            kwargs["default_headers"] = cfg.default_headers
        self.client = OpenAI(**kwargs)
        self.model = cfg.model

    def complete(self, messages, tools=None, on_token=None) -> LLMResponse:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        content_parts: list[str] = []
        tool_acc: dict[int, dict[str, Any]] = {}
        usage: dict[str, int] = {}
        finish = "stop"

        stream = self.client.chat.completions.create(**kwargs)
        for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens or 0,
                    "completion_tokens": chunk.usage.completion_tokens or 0,
                }
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish = choice.finish_reason
            delta = choice.delta
            if delta and delta.content:
                content_parts.append(delta.content)
                if on_token:
                    on_token(delta.content)
            for tc in (delta.tool_calls if delta else None) or []:
                slot = tool_acc.setdefault(tc.index, {"id": None, "name": "", "args": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    slot["args"] += tc.function.arguments

        tool_calls: list[ToolCall] = []
        for idx in sorted(tool_acc):
            slot = tool_acc[idx]
            raw = slot["args"] or "{}"
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                # Some local models emit trailing garbage; try to salvage the first object.
                try:
                    args = json.loads(raw[: raw.rindex("}") + 1])
                except Exception:
                    args = {"_raw": raw}
            tool_calls.append(
                ToolCall(id=slot["id"] or f"call_{idx}", name=slot["name"], arguments=args)
            )

        return LLMResponse(
            content="".join(content_parts), tool_calls=tool_calls, usage=usage, finish_reason=finish
        )


class EchoLLM(BaseLLM):
    """Deterministic offline provider.

    Exercises the full agent harness — tool dispatch, guardrails, case store,
    reporting — without any network or API key. Useful for tests and for
    trying RedEye before you plug in a model.
    """

    def __init__(self, cfg: Config):
        self.model = "echo"
        self._turns = 0

    def complete(self, messages, tools=None, on_token=None) -> LLMResponse:
        self._turns += 1
        tool_names = {t["function"]["name"] for t in (tools or [])}
        if self._turns == 1 and "case_add_finding" in tool_names:
            goal = messages[-1]["content"][:200] if messages else "unknown goal"
            return LLMResponse(
                content="[echo] Planning: record the objective, then synthesize.\n",
                tool_calls=[
                    ToolCall(
                        id="echo_call_1",
                        name="case_add_finding",
                        arguments={
                            "title": "Investigation objective",
                            "detail": f"Operator goal: {goal}",
                            "source": "redeye echo provider",
                            "confidence": "high",
                        },
                    )
                ],
            )
        text = (
            "[echo] Run complete. The echo provider is a deterministic stand-in: it recorded "
            "your objective to the case file and produced this summary so you can verify the "
            "harness end-to-end (tool dispatch, permissions, guardrails, session, report). "
            "Point RedEye at OpenRouter or Ollama for real intelligence work."
        )
        if on_token:
            for chunk in text.split(" "):
                on_token(chunk + " ")
        return LLMResponse(content=text)


def build_llm(cfg: Config) -> BaseLLM:
    if cfg.provider == "echo":
        return EchoLLM(cfg)
    return OpenAICompatLLM(cfg)
