"""Runtime assembly: wires config, LLM, tools, MCP, skills, case and session."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .agent import Agent, EventFn, ApprovalFn
from .case import CaseStore
from .config import Config
from .llm import BaseLLM, build_llm
from .mcp_client import McpManager
from .permissions import PermissionPolicy
from .prompts import build_system_prompt, summarize_tools
from .session import Session
from .skills import Skill, load_skills
from .tools import build_registry


@dataclass
class Runtime:
    cfg: Config
    llm: BaseLLM
    registry: object
    policy: PermissionPolicy
    skills: dict[str, Skill]
    mcp: Optional[McpManager]
    case: CaseStore
    session: Session

    def make_agent(self, emit: EventFn, approval_fn: Optional[ApprovalFn] = None,
                   fresh_guard: bool = True) -> Agent:
        mcp_summary = ""
        if self.mcp and (self.mcp.connected or self.mcp.errors):
            parts = [f"MCP servers connected: {', '.join(self.mcp.connected) or 'none'}"]
            for name, err in self.mcp.errors.items():
                parts.append(f"MCP server {name} failed: {err}")
            mcp_summary = "\n## MCP\n\n" + "\n".join(parts)
        system_prompt = build_system_prompt(
            skills_catalog=_catalog(self.skills),
            permission_mode=self.policy.mode,
            tools_summary=summarize_tools(self.registry.tiers()),
            mcp_summary=mcp_summary,
        )
        return Agent(
            cfg=self.cfg,
            llm=self.llm,
            registry=self.registry,
            policy=self.policy,
            case=self.case,
            session=self.session,
            skills=self.skills,
            system_prompt=system_prompt,
            emit=emit,
            approval_fn=approval_fn,
        )

    def shutdown(self) -> None:
        if self.mcp:
            self.mcp.shutdown()


def _catalog(skills: dict[str, Skill]) -> str:
    from .skills import catalog_lines

    return catalog_lines(skills)


def build_runtime(
    cfg: Config,
    *,
    goal: str,
    session: Optional[Session] = None,
    case: Optional[CaseStore] = None,
    connect_mcp: bool = True,
) -> Runtime:
    llm = build_llm(cfg)
    skills = load_skills(cfg.skills_dir)
    policy = PermissionPolicy(mode=cfg.permission_mode)

    if session is None:
        session = Session.create(cfg.sessions_dir, goal=goal, model=cfg.model, mode=policy.mode)
    if case is None:
        case_path = cfg.sessions_dir / f"{session.session_id}.case.json"
        case = CaseStore(goal=goal, path=case_path)
        case.save()

    registry = build_registry(cfg, case=case, skills=skills)

    mcp: Optional[McpManager] = None
    if connect_mcp and cfg.mcp_servers:
        mcp = McpManager(cfg.mcp_servers)
        mcp.start()
        mcp.bridge_tools(registry)

    return Runtime(
        cfg=cfg, llm=llm, registry=registry, policy=policy,
        skills=skills, mcp=mcp, case=case, session=session,
    )
