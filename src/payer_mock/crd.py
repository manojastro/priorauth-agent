"""CRD-like coverage requirement lookup. Deterministic rule table built from the policy files.

Da Vinci CRD-*inspired* only. Not a certified or conformant implementation.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel

from src.policies.loader import PLAN_TYPES, load_policies

# What evidence type each criterion kind needs; used to list documents to gather.
DOCUMENT_FOR_KIND = {
    "condition": "Diagnosis (Condition)",
    "procedure_duration": "Therapy or program record with dates (Procedure)",
    "procedure_count": "Visit log (Procedure)",
    "procedure_done": "Procedure record (Procedure)",
    "medication_trial": "Medication history with dates (MedicationRequest)",
    "observation_threshold": "Measured result (Observation)",
    "observation_result": "Test result (Observation)",
    "note": "Recent clinical note (DocumentReference)",
}


class CrdRequest(BaseModel):
    service_code: str
    plan_type: str


class RequiredDocument(BaseModel):
    criterion_id: str
    document: str


class CrdResponse(BaseModel):
    service_code: str
    plan_type: str
    known_service: bool
    pa_required: bool | None
    policy_id: str | None = None
    policy_version: str | None = None
    documentation_section: str | None = None
    documents_required: list[RequiredDocument] = []
    message: str = ""


class RuleRow(BaseModel):
    service_code: str
    plan_type: str
    pa_required: bool
    policy_id: str
    policy_version: str


@lru_cache
def rule_table() -> dict[tuple[str, str], RuleRow]:
    table: dict[tuple[str, str], RuleRow] = {}
    for p in load_policies().values():
        for s in p.services:
            for plan in PLAN_TYPES:
                table[(s.code, plan)] = RuleRow(
                    service_code=s.code,
                    plan_type=plan,
                    pa_required=p.pa_required[plan],
                    policy_id=p.policy_id,
                    policy_version=p.version,
                )
    return table


def check(req: CrdRequest) -> CrdResponse:
    row = rule_table().get((req.service_code, req.plan_type))
    if row is None:
        known = any(code == req.service_code for code, _ in rule_table())
        return CrdResponse(
            service_code=req.service_code,
            plan_type=req.plan_type,
            known_service=known,
            pa_required=None,
            message="unknown plan type" if known else "service not in rule table",
        )
    policy = load_policies()[row.policy_id]
    docs = []
    if row.pa_required:
        docs = [
            RequiredDocument(criterion_id=c.id, document=DOCUMENT_FOR_KIND[c.kind])
            for c in policy.criteria
        ]
    prefix = policy.criteria[0].id.split("-")[0]
    return CrdResponse(
        service_code=req.service_code,
        plan_type=req.plan_type,
        known_service=True,
        pa_required=row.pa_required,
        policy_id=row.policy_id,
        policy_version=row.policy_version,
        documentation_section=f"{prefix}-5",
        documents_required=docs,
        message="prior authorization required" if row.pa_required else "no prior auth needed",
    )
