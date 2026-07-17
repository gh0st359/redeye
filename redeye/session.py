"""Session persistence: JSONL transcripts so investigations can be resumed."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _session_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


@dataclass
class Session:
    session_id: str
    path: Path
    meta: dict[str, Any] = field(default_factory=dict)
    messages: list[dict] = field(default_factory=list)

    @classmethod
    def create(cls, sessions_dir: Path, *, goal: str, model: str, mode: str) -> "Session":
        sid = _session_id()
        # avoid collisions within the same second
        n, base = 0, sid
        while (sessions_dir / f"{sid}.jsonl").exists():
            n += 1
            sid = f"{base}-{n}"
        s = cls(session_id=sid, path=sessions_dir / f"{sid}.jsonl")
        s.meta = {
            "type": "meta",
            "session_id": sid,
            "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "goal": goal,
            "model": model,
            "permission_mode": mode,
        }
        s._append(s.meta)
        return s

    @classmethod
    def resume(cls, path: Path) -> "Session":
        meta: dict[str, Any] = {}
        messages: list[dict] = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("type") == "meta":
                    meta = rec
                elif rec.get("type") == "message":
                    messages.append(rec["message"])
        return cls(session_id=meta.get("session_id", path.stem), path=path, meta=meta, messages=messages)

    def _append(self, rec: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def append_message(self, message: dict) -> None:
        self.messages.append(message)
        self._append({"type": "message", "message": message})

    def log_event(self, kind: str, payload: dict) -> None:
        self._append({"type": "event", "kind": kind, "payload": payload,
                      "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")})


def list_sessions(sessions_dir: Path) -> list[dict[str, Any]]:
    out = []
    for p in sorted(sessions_dir.glob("*.jsonl"), reverse=True):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                first = json.loads(fh.readline())
            if first.get("type") == "meta":
                first["path"] = str(p)
                out.append(first)
        except Exception:
            continue
    return out
