"""The ONLY code path that sends a prior-auth request or appeal to the payer.

Approval gate (tested invariant): a submission needs an audit-store approval event that
- exists and has action "approve" (or "approve_appeal" for appeals),
- was recorded by a user with role pa_reviewer,
- belongs to this thread, and
- was given for exactly this payload (sha256 matches).
Graph state alone is never trusted for this.
"""

from __future__ import annotations

import httpx

from src.common.audit import AuditStore
from src.common.roles import PA_REVIEWER
from src.priorauth.packet import packet_hash


class ApprovalGateError(PermissionError):
    pass


def check_approval(
    audit: AuditStore, thread_id: str, payload: dict, approval_id: str | None, action: str
) -> None:
    if not approval_id:
        raise ApprovalGateError("no approval recorded")
    ev = audit.get(approval_id)
    if ev is None:
        raise ApprovalGateError("approval event not found in audit store")
    if ev.action != action:
        raise ApprovalGateError(f"audit event is {ev.action!r}, not {action!r}")
    if ev.role != PA_REVIEWER:
        raise ApprovalGateError(f"approval by role {ev.role!r}; only {PA_REVIEWER} may approve")
    if ev.thread_id != thread_id:
        raise ApprovalGateError("approval belongs to a different case")
    if ev.details.get("payload_hash") != packet_hash(payload):
        raise ApprovalGateError("payload changed after approval")


def submit_packet(
    payer: httpx.Client, audit: AuditStore, thread_id: str, packet: dict, approval_id: str | None
) -> dict:
    check_approval(audit, thread_id, packet, approval_id, "approve")
    r = payer.post("/pas/submit", json=packet, headers={"X-Reviewer-Approval": approval_id})
    r.raise_for_status()
    return r.json()


def submit_appeal(
    payer: httpx.Client, audit: AuditStore, thread_id: str, appeal: dict, approval_id: str | None
) -> dict:
    check_approval(audit, thread_id, appeal, approval_id, "approve_appeal")
    r = payer.post("/pas/appeal", json=appeal, headers={"X-Reviewer-Approval": approval_id})
    r.raise_for_status()
    return r.json()


def get_status(payer: httpx.Client, submission_id: str) -> dict:
    r = payer.get(f"/pas/status/{submission_id}")
    r.raise_for_status()
    return r.json()
