"""End-to-end harness tests with a scripted LLM — no network, no API key."""
from __future__ import annotations

from pathlib import Path

import pytest

from redeye.agent import Agent
from redeye.case import CaseStore
from redeye.config import Config
from redeye.llm import LLMResponse, ToolCall
from redeye.permissions import PermissionPolicy
from redeye.session import Session
from redeye.skills import load_skills
from redeye.tools import build_registry
from redeye.tools.base import ToolResult


class ScriptedLLM:
    """Plays back a fixed script of responses keyed by turn number.

    `final` is returned for tool-less calls — i.e. the harness's forced
    final synthesis after a hard stop (complete(..., tools=None)).
    """

    def __init__(self, script, final=None):
        self.script = script
        self.final = final
        self.turns = 0
        self.model = "scripted"

    def complete(self, messages, tools=None, on_token=None):
        if tools is None and self.final is not None:
            resp = self.final
        else:
            idx = min(self.turns, len(self.script) - 1)
            self.turns += 1
            resp = self.script[idx]
        if on_token and resp.content:
            on_token(resp.content)
        return resp


@pytest.fixture()
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("REDEYE_HOME", str(tmp_path / "home"))
    cfg = Config.load(config_path=str(tmp_path / "nope.toml"), provider="echo", mode="fullauto")
    cfg.max_steps = 10
    cfg.sessions_dir.mkdir(parents=True, exist_ok=True)
    session = Session.create(cfg.sessions_dir, goal="test goal", model="scripted", mode="fullauto")
    case = CaseStore(goal="test goal", path=cfg.sessions_dir / "t.case.json")
    skills = load_skills(None)
    registry = build_registry(cfg, case=case, skills=skills)

    @registry.tool(name="fake_lookup", description="test tool",
                   parameters={"type": "object",
                               "properties": {"q": {"type": "string"}},
                               "required": ["q"]})
    def fake_lookup(q: str):
        return ToolResult(ok=True, content=f"result for {q}")

    events = []

    def emit(kind, data):
        events.append((kind, data))

    def make_agent(llm):
        return Agent(
            cfg=cfg, llm=llm, registry=registry, policy=PermissionPolicy(mode="fullauto"),
            case=case, session=session, skills=skills, system_prompt="sys",
            emit=emit, approval_fn=lambda n, t, a: (True, False),
        )

    return make_agent, case, session, events


def test_tool_then_final(harness):
    make_agent, case, session, events = harness
    llm = ScriptedLLM([
        LLMResponse(content="looking…", tool_calls=[ToolCall(id="1", name="fake_lookup", arguments={"q": "acme"})]),
        LLMResponse(content="looking…", tool_calls=[ToolCall(id="2", name="case_add_finding", arguments={
            "title": "Acme exists", "detail": "confirmed via fake_lookup", "source": "fake_lookup", "confidence": "high"})]),
        LLMResponse(content="Final assessment: acme confirmed."),
    ])
    result = make_agent(llm).run("investigate acme")
    assert "Final assessment" in result.final_text
    assert result.stopped_reason is None
    assert len(case.findings) == 1
    assert case.findings[0].title == "Acme exists"
    assert result.report_path and Path(result.report_path).exists()
    kinds = [k for k, _ in events]
    assert "tool_call" in kinds and "tool_result" in kinds and "report" in kinds
    # transcript persisted
    assert session.path.exists()
    text = session.path.read_text()
    assert "fake_lookup" in text and "test goal" in text


def test_loop_guard_stops_repeat_and_synthesizes(harness):
    make_agent, case, session, events = harness
    # a model stuck in a loop: same call forever
    looping = [LLMResponse(tool_calls=[ToolCall(id=str(i), name="fake_lookup", arguments={"q": "same"})])
               for i in range(12)]
    llm = ScriptedLLM(looping, final=LLMResponse(content="Summary from what I had."))
    result = make_agent(llm).run("loop test")
    assert result.stopped_reason and "identical" in result.stopped_reason
    assert "Summary" in result.final_text
    assert any(k == "steering" for k, _ in events)  # harness nudged before stopping


def test_denied_tool_tells_model(harness):
    make_agent, case, session, events = harness
    llm = ScriptedLLM([
        LLMResponse(tool_calls=[ToolCall(id="1", name="fake_lookup", arguments={"q": "x"})]),
        LLMResponse(content="understood, moving on without it."),
    ])
    agent = make_agent(llm)
    agent.approval_fn = lambda n, t, a: (False, False)
    agent.policy = PermissionPolicy(mode="balanced")  # forces ASK for active+
    # fake_lookup is passive → allowed; make it sensitive via registry edit
    agent.registry.get("fake_lookup").tier = "sensitive"
    result = agent.run("denial test")
    assert "understood" in result.final_text
    tool_msgs = [m for m in session.messages if m.get("role") == "tool"]
    assert "DENIED" in tool_msgs[-1]["content"]


def test_step_budget_interrupts(harness):
    make_agent, case, session, events = harness
    calls = [LLMResponse(tool_calls=[ToolCall(id=str(i), name="fake_lookup", arguments={"q": f"v{i}"})])
             for i in range(30)]
    llm = ScriptedLLM(calls, final=LLMResponse(content="budget summary"))
    result = make_agent(llm).run("budget test")
    assert result.stopped_reason and "step budget" in result.stopped_reason
    assert "budget summary" in result.final_text
