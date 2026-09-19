"""Append-only audit log (JSONL).

Every consequential step — query received, plan, evidence gathered, response,
access denials, and approval decisions — is written as one validated
:class:`AuditEvent` per line, so a reviewer can reconstruct exactly what the
agent did, with what data, for whom.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from ..config import settings as default_settings
from ..contracts.models import AuditEvent


class AuditLogger:
    def __init__(self, path: Optional[Path] = None, echo: bool = False):
        self.path = Path(path) if path else (default_settings.audit_dir / "audit.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.echo = echo
        self.events: list[AuditEvent] = []
        self._lock = threading.Lock()

    def log(self, event: str, query_id: Optional[str] = None, user_id: Optional[str] = None,
            role: Optional[str] = None, **detail) -> AuditEvent:
        ev = AuditEvent(event=event, query_id=query_id, user_id=user_id, role=role, detail=detail)
        line = ev.model_dump_json()
        with self._lock:
            self.events.append(ev)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        if self.echo:
            print(f"[audit] {ev.event} q={query_id} {detail}")
        return ev
