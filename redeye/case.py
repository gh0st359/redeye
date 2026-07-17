"""Case file: structured findings the agent records during a run."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Finding:
    title: str
    detail: str
    source: str = ""
    confidence: str = "medium"  # low | medium | high
    timestamp: str = field(default_factory=_now)


@dataclass
class CaseStore:
    goal: str = ""
    findings: list[Finding] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)
    case_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    created: str = field(default_factory=_now)
    path: Optional[Path] = None

    def add_finding(self, title: str, detail: str, source: str = "", confidence: str = "medium") -> Finding:
        if confidence not in ("low", "medium", "high"):
            confidence = "medium"
        f = Finding(title=title.strip(), detail=detail.strip(), source=source.strip(), confidence=confidence)
        self.findings.append(f)
        self.save()
        return f

    def add_note(self, text: str) -> None:
        self.notes.append({"timestamp": _now(), "text": text})
        self.save()

    def summary(self) -> str:
        if not self.findings:
            return "No findings recorded yet."
        lines = [f"Case {self.case_id} — {len(self.findings)} finding(s):"]
        for i, f in enumerate(self.findings, 1):
            src = f" [source: {f.source}]" if f.source else ""
            lines.append(f"{i}. ({f.confidence}) {f.title}{src}\n   {f.detail}")
        return "\n".join(lines)

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "case_id": self.case_id,
            "created": self.created,
            "goal": self.goal,
            "findings": [asdict(f) for f in self.findings],
            "notes": self.notes,
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> "CaseStore":
        data = json.loads(path.read_text())
        store = cls(
            goal=data.get("goal", ""),
            case_id=data.get("case_id", uuid.uuid4().hex[:8]),
            created=data.get("created", _now()),
            path=path,
        )
        store.findings = [Finding(**f) for f in data.get("findings", [])]
        store.notes = list(data.get("notes", []))
        return store
