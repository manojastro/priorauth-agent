"""Thin service over the compiled graph: start a case, read its state, record a decision.

Checkpointer: SQLite file under data/runtime/ by default (local, survives restarts);
CHECKPOINTER=postgres uses langgraph-checkpoint-postgres with the app database.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from langgraph.types import Command

from src.common.config import get_settings
from src.priorauth.graph import AGENT, Deps, build_graph

RUNTIME = Path(__file__).resolve().parents[2] / "data" / "runtime"


@contextmanager
def open_checkpointer(kind: str | None = None, path: Path | None = None):
    kind = kind or os.getenv("CHECKPOINTER", "sqlite")
    if kind == "postgres":
        from langgraph.checkpoint.postgres import PostgresSaver

        with PostgresSaver.from_conn_string(get_settings().postgres_dsn) as saver:
            saver.setup()
            yield saver
        return
    from langgraph.checkpoint.sqlite import SqliteSaver

    path = path or RUNTIME / "checkpoints.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    try:
        yield SqliteSaver(conn)
    finally:
        conn.close()


class PAService:
    def __init__(self, deps: Deps, checkpointer):
        self.deps = deps
        self.graph = build_graph(deps, checkpointer)

    @staticmethod
    def _cfg(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def start(self, service_request_id: str, user: str, role: str, case_id: str = "") -> str:
        thread_id = f"{service_request_id}-{uuid.uuid4().hex[:6]}"
        self.deps.audit.append(
            thread_id,
            user,
            role,
            "run_started",
            {"service_request_id": service_request_id, "case_id": case_id},
        )
        self.graph.invoke({"service_request_id": service_request_id}, self._cfg(thread_id))
        return thread_id

    def state(self, thread_id: str) -> dict:
        snap = self.graph.get_state(self._cfg(thread_id))
        pending = [i.value for t in snap.tasks for i in t.interrupts]
        return {"values": snap.values, "next": list(snap.next), "pending_review": pending}

    def decide(self, thread_id: str, decision: dict) -> dict:
        self.graph.invoke(Command(resume=decision), self._cfg(thread_id))
        return self.state(thread_id)

    def threads(self) -> list[dict]:
        out = []
        for ev in self.deps.audit.all():
            if ev.action == "run_started":
                out.append(
                    {
                        "thread_id": ev.thread_id,
                        "started_by": ev.actor,
                        "at": ev.at_utc,
                        **ev.details,
                    }
                )
        return out


__all__ = ["AGENT", "PAService", "open_checkpointer"]
