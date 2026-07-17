"""Tool registry assembly: built-in OSINT tools + case tools + skill loader."""
from __future__ import annotations

from typing import Optional

from ..case import CaseStore
from ..config import Config
from ..skills import Skill
from .base import ToolRegistry
from . import crypto, meta, network, people, web


def build_registry(
    cfg: Config,
    *,
    case: Optional[CaseStore] = None,
    skills: Optional[dict[str, Skill]] = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    web.register(registry, cfg)
    network.register(registry, cfg)
    people.register(registry, cfg)
    crypto.register(registry, cfg)
    meta.register(registry, cfg)

    if case is not None:
        _register_case_tools(registry, case)
    if skills is not None:
        _register_skill_tool(registry, skills)
    return registry


def _register_case_tools(registry: ToolRegistry, case: CaseStore) -> None:

    @registry.tool(
        name="case_add_finding",
        description=(
            "Record a structured finding to the case file. Call this the moment you "
            "establish a fact worth keeping — with its source URL/record and your "
            "confidence (high = 2+ independent sources, medium = one credible source, "
            "low = inference/lead)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "One-line statement of the fact"},
                "detail": {"type": "string", "description": "Supporting evidence and context"},
                "source": {"type": "string", "description": "URL, record, or API the fact came from"},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["title", "detail"],
        },
    )
    def case_add_finding(title: str, detail: str, source: str = "", confidence: str = "medium"):
        from .base import ToolResult

        f = case.add_finding(title, detail, source, confidence)
        return ToolResult(ok=True, content=f"Finding #{len(case.findings)} recorded: {f.title}")

    @registry.tool(
        name="case_list_findings",
        description="List everything recorded in the case file so far this investigation.",
        parameters={"type": "object", "properties": {}},
    )
    def case_list_findings():
        from .base import ToolResult

        return ToolResult(ok=True, content=case.summary())

    @registry.tool(
        name="case_add_note",
        description=(
            "Add an analyst note to the case — hypotheses, gaps, things to verify, "
            "observations that are not yet findings."
        ),
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Note text"}},
            "required": ["text"],
        },
    )
    def case_add_note(text: str):
        from .base import ToolResult

        case.add_note(text)
        return ToolResult(ok=True, content="Note added to case file.")


def _register_skill_tool(registry: ToolRegistry, skills: dict[str, Skill]) -> None:

    @registry.tool(
        name="skill_load",
        description=(
            "Load a tradecraft skill's full playbook into context. Call this BEFORE "
            "collecting, for every skill relevant to the objective."
        ),
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Skill name from the catalog"}},
            "required": ["name"],
        },
    )
    def skill_load(name: str):
        from .base import ToolResult

        skill = skills.get(name.strip())
        if not skill:
            return ToolResult.error(
                f"unknown skill {name!r}. Available: {', '.join(sorted(skills))}"
            )
        return ToolResult(
            ok=True,
            content=f"# Skill: {skill.name}\n\n{skill.body}\n\n— Follow this methodology. "
            "Record findings as you go.",
        )
