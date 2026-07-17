"""Markdown intelligence report generation."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .case import CaseStore


def generate_report(
    case: CaseStore,
    *,
    final_summary: str,
    model: str,
    guard_stats: dict,
    session_id: str,
    reports_dir: Path,
) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []
    lines.append(f"# RedEye Intelligence Report — Case {case.case_id}")
    lines.append("")
    lines.append(f"- **Generated:** {now}")
    lines.append(f"- **Session:** {session_id}")
    lines.append(f"- **Model:** {model}")
    lines.append(f"- **Run stats:** {guard_stats.get('steps', '?')} steps, "
                 f"{guard_stats.get('elapsed_s', '?')}s, "
                 f"{guard_stats.get('unique_calls', '?')} tool calls")
    lines.append("")
    lines.append("## Objective")
    lines.append("")
    lines.append(case.goal or "_(not recorded)_")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(final_summary.strip() or "_(no final summary produced)_")
    lines.append("")
    lines.append(f"## Findings ({len(case.findings)})")
    lines.append("")
    if not case.findings:
        lines.append("_No structured findings were recorded during this run._")
    for i, f in enumerate(case.findings, 1):
        badge = {"high": "🟢 HIGH", "medium": "🟡 MEDIUM", "low": "🔴 LOW"}.get(f.confidence, f.confidence)
        lines.append(f"### {i}. {f.title}")
        lines.append("")
        lines.append(f"- **Confidence:** {badge}")
        if f.source:
            lines.append(f"- **Source:** {f.source}")
        lines.append(f"- **Recorded:** {f.timestamp}")
        lines.append("")
        lines.append(f.detail)
        lines.append("")
    if case.notes:
        lines.append("## Analyst Notes")
        lines.append("")
        for n in case.notes:
            lines.append(f"- _{n['timestamp']}_ — {n['text']}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "Produced by RedEye from **open sources only**. Assess reliability and "
        "corroborate independently before acting on any finding. Confidence labels "
        "reflect source quality and corroboration, not certainty."
    )

    fname = f"redeye-{case.case_id}-{session_id}.md"
    path = reports_dir / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
