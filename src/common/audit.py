"""Append-only audit trail. SQLite locally/tests; Postgres when AUDIT_BACKEND=postgres.

Every reviewer decision, criterion override (with before/after), submission and status change
is written here. The submit gate reads approvals back from this store, not from graph state.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "runtime" / "audit.sqlite"


class AuditEvent(BaseModel):
    event_id: str
    at_utc: str
    thread_id: str
    actor: str
    role: str
    action: str
    details: dict = {}
    before: dict | None = None
    after: dict | None = None


class AuditStore:
    """SQLite-backed. Thread-safe for the workbench's simple use."""

    def __init__(self, path: Path | str = DEFAULT_DB):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS audit (
                 event_id TEXT PRIMARY KEY, at_utc TEXT NOT NULL, thread_id TEXT NOT NULL,
                 actor TEXT NOT NULL, role TEXT NOT NULL, action TEXT NOT NULL,
                 details TEXT NOT NULL, before TEXT, after TEXT)"""
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS audit_thread ON audit (thread_id)")
        self._conn.commit()

    def append(
        self,
        thread_id: str,
        actor: str,
        role: str,
        action: str,
        details: dict | None = None,
        before: dict | None = None,
        after: dict | None = None,
    ) -> AuditEvent:
        ev = AuditEvent(
            event_id=uuid.uuid4().hex,
            at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
            thread_id=thread_id,
            actor=actor,
            role=role,
            action=action,
            details=details or {},
            before=before,
            after=after,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ev.event_id,
                    ev.at_utc,
                    ev.thread_id,
                    ev.actor,
                    ev.role,
                    ev.action,
                    json.dumps(ev.details, sort_keys=True),
                    None if before is None else json.dumps(before, sort_keys=True),
                    None if after is None else json.dumps(after, sort_keys=True),
                ),
            )
            self._conn.commit()
        return ev

    def _rows(self, sql: str, args: tuple) -> list[AuditEvent]:
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [
            AuditEvent(
                event_id=r[0],
                at_utc=r[1],
                thread_id=r[2],
                actor=r[3],
                role=r[4],
                action=r[5],
                details=json.loads(r[6]),
                before=json.loads(r[7]) if r[7] else None,
                after=json.loads(r[8]) if r[8] else None,
            )
            for r in rows
        ]

    def for_thread(self, thread_id: str) -> list[AuditEvent]:
        return self._rows(
            "SELECT * FROM audit WHERE thread_id = ? ORDER BY at_utc, rowid", (thread_id,)
        )

    def get(self, event_id: str) -> AuditEvent | None:
        rows = self._rows("SELECT * FROM audit WHERE event_id = ?", (event_id,))
        return rows[0] if rows else None

    def all(self) -> list[AuditEvent]:
        return self._rows("SELECT * FROM audit ORDER BY at_utc, rowid", ())

    def close(self) -> None:
        self._conn.close()
