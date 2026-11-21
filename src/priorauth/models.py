"""Data models for evidence, assessments and the LLM's structured note output."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

Label = Literal["met", "not_met", "missing"]
Stance = Literal["supports", "contradicts"]
Readiness = Literal["ready_to_submit", "needs_more_info", "likely_not_meeting_criteria"]


class EvidenceItem(BaseModel):
    criterion_id: str
    source: Literal["structured", "note"]
    resource_type: str
    resource_id: str
    stance: Stance
    # Field checks the verifier re-reads from the server: {"code.coding[0].code": "M54.50"}.
    checks: dict[str, str] = {}
    # Notes only: exact quote and its character span in the decoded note text.
    quote: str | None = None
    span: tuple[int, int] | None = None
    evidence_date: date | None = None
    in_window: bool = True
    facts: dict = {}
    verified: bool = False
    verify_note: str = ""


class CriterionAssessment(BaseModel):
    criterion_id: str
    section_id: str
    label: Label
    reason: str
    evidence: list[EvidenceItem]  # verified only
    dropped: list[EvidenceItem] = []  # failed verification


class CaseAssessment(BaseModel):
    service_request_id: str
    policy_id: str
    retrieved_sections: list[str]
    missing_from_retrieval: list[str]
    criteria: list[CriterionAssessment]
    readiness: Readiness | None
    injection_flags: list[dict]
    citations_total: int
    citations_verified: int
    llm_usage: dict


# ----- LLM structured output (strict JSON schema: every field required, no extras) -----


class NoteFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_id: str
    note_id: str
    stance: Stance
    quote: str


class NoteFindings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[NoteFinding]
