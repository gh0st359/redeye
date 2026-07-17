"""Skills: reusable tradecraft playbooks injected into the agent on demand.

A skill is a Markdown file with a small front-matter block:

    ---
    name: domain-recon
    description: Map a domain's infrastructure, subdomains, mail providers...
    ---

    # Body with methodology, pivots, query templates...

Built-in skills ship inside the package; user skills live in ~/.redeye/skills/
and override built-ins with the same name. The agent sees the catalog (name +
description) in its system prompt and loads bodies progressively via the
`skill_load` tool — keeping context lean.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass
class Skill:
    name: str
    description: str
    body: str
    origin: str  # "builtin" | "user"


def _parse(text: str, origin: str) -> Skill | None:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        return None
    meta, body = m.group(1), m.group(2)
    fields: dict[str, str] = {}
    for line in meta.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    if not fields.get("name"):
        return None
    return Skill(
        name=fields["name"],
        description=fields.get("description", ""),
        body=body.strip(),
        origin=origin,
    )


def load_skills(user_dir: Path | None = None) -> dict[str, Skill]:
    skills: dict[str, Skill] = {}

    builtin_dir = resources.files("redeye") / "builtin_skills"
    for entry in builtin_dir.iterdir():
        if entry.name.endswith(".md"):
            skill = _parse(entry.read_text(encoding="utf-8"), "builtin")
            if skill:
                skills[skill.name] = skill

    if user_dir and user_dir.exists():
        for p in sorted(user_dir.glob("*.md")):
            try:
                skill = _parse(p.read_text(encoding="utf-8"), "user")
                if skill:
                    skills[skill.name] = skill  # user overrides builtin
            except Exception:
                continue
    return skills


def catalog_lines(skills: dict[str, Skill]) -> str:
    if not skills:
        return "(no skills installed)"
    return "\n".join(
        f"- {s.name} [{s.origin}]: {s.description}" for s in sorted(skills.values(), key=lambda x: x.name)
    )
