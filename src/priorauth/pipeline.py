"""Phase 2 steps up to assessment: load_context -> retrieve_policy -> extract_evidence ->
verify_citations -> assess_criteria. Plain functions; M4 wraps them as LangGraph nodes.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from src.common.fhir_source import FhirSource
from src.common.llm import LLM
from src.intake.service import IntakeResult
from src.policies.loader import Criterion, Policy, load_policies
from src.policies.retriever import InMemoryHybridRetriever, chunk_policy, rrf
from src.priorauth import notes as note_ext
from src.priorauth import structured
from src.priorauth.models import CaseAssessment, CriterionAssessment, EvidenceItem, Label
from src.priorauth.verify import verify_citations

EVIDENCE_TYPES = ("Condition", "Procedure", "MedicationRequest", "Observation", "DocumentReference")
_CRITERION_ID = r"-2\.\d+$"


def readiness(eligible: bool, pa_required: bool | None, labels: list[Label]):
    if not eligible or not pa_required:
        return None
    if "not_met" in labels:
        return "likely_not_meeting_criteria"
    if "missing" in labels:
        return "needs_more_info"
    return "ready_to_submit"


def load_context(src: FhirSource, patient_id: str, policy: Policy, sd: date) -> list[dict]:
    """Patient resources of relevant types, not after the service date, not older than the
    longest policy window."""
    ref = f"Patient/{patient_id}"
    oldest = sd - timedelta(days=max(c.window_days for c in policy.criteria) * 3)
    out = []
    for rt in EVIDENCE_TYPES:
        for r in src.search(rt, {"patient": ref}):
            d = _res_date(r)
            if d is None or oldest <= d <= sd:
                out.append(r)
    return out


def _res_date(r: dict) -> date | None:
    for v in (
        r.get("recordedDate"),
        r.get("effectiveDateTime"),
        r.get("performedDateTime"),
        (r.get("performedPeriod") or {}).get("end"),
        ((r.get("dispenseRequest") or {}).get("validityPeriod") or {}).get("end"),
        r.get("date"),
    ):
        if v:
            return date.fromisoformat(v[:10])
    return None


_RETRIEVERS: dict[str, InMemoryHybridRetriever] = {}


def default_retriever(llm: LLM) -> InMemoryHybridRetriever:
    key = llm.name
    if key not in _RETRIEVERS:
        chunks = [c for p in load_policies().values() for c in chunk_policy(p)]
        _RETRIEVERS[key] = InMemoryHybridRetriever(chunks, llm.embed)
    return _RETRIEVERS[key]


def retrieve_policy(
    retriever, policy: Policy, service_display: str, documents: list[str] | None = None, k: int = 8
):
    """One query for the service's coverage criteria, plus one per document the payer asked
    for (from CRD). Rankings fused with RRF. Returns (criteria, section ids seen, not retrieved)."""
    queries = [f"{service_display} coverage criteria requirements"]
    queries += [f"{service_display} {d}" for d in dict.fromkeys(documents or [])]
    rankings = [
        [h.chunk.section_id for h in retriever.search(q, policy.policy_id, k)] for q in queries
    ]
    fused = rrf(rankings)
    sections = sorted(fused, key=lambda sid: (-fused[sid], sid))
    # Parent expansion: a retrieved "X-2 Coverage criteria" heading brings in all its children.
    expanded = list(sections)
    for sid in sections:
        if re.fullmatch(r"[A-Z]+-2", sid):
            expanded += [c.id for c in policy.criteria if c.id.startswith(f"{sid}.")]
    ids = list(dict.fromkeys(sid for sid in expanded if re.search(_CRITERION_ID, sid)))
    by_id = {c.id: c for c in policy.criteria}
    got = [by_id[i] for i in ids if i in by_id]
    missing = [c.id for c in policy.criteria if c.id not in ids]
    # Keep policy order so the checklist reads naturally.
    return sorted(got, key=lambda c: list(by_id).index(c.id)), sections, missing


def extract_evidence(
    llm: LLM, criteria: list[Criterion], resources: list[dict], sd: date
) -> list[EvidenceItem]:
    """Structured resources first (deterministic), then free-text notes (LLM)."""
    items: list[EvidenceItem] = []
    for c in criteria:
        if c.kind != "note":
            items += structured.find(c, resources, sd)
    notes = [r for r in resources if r["resourceType"] == "DocumentReference"]
    note_criteria = [c for c in criteria if c.kind == "note"]
    items += note_ext.extract_from_notes(llm, note_criteria, notes)
    for it in items:
        if it.source == "note" and it.evidence_date:
            crit = next(c for c in criteria if c.id == it.criterion_id)
            it.in_window = sd - timedelta(days=crit.window_days) <= it.evidence_date <= sd
    return items


def assess_note_criterion(c: Criterion, items: list[EvidenceItem]) -> tuple[Label, str]:
    win = [e for e in items if e.in_window]
    sup = [e for e in win if e.stance == "supports"]
    con = [e for e in win if e.stance == "contradicts"]

    def cite(e: EvidenceItem) -> str:
        where = f"chars {e.span[0]}-{e.span[1]}" if e.span else "no verified span"
        return f"DocumentReference/{e.resource_id} {where}"

    if sup and con:
        return "missing", f"notes conflict ({cite(sup[0])} vs {cite(con[0])}); needs clarification"
    if sup:
        return "met", f"documented in {cite(sup[0])}"
    if con:
        return "not_met", f"note documents the opposite: {cite(con[0])}"
    if items:
        return "missing", f"only notes older than {c.window_days} days: {cite(items[0])}"
    return "missing", "no verified note evidence found"


def assess_criteria(
    criteria: list[Criterion], all_criteria: list[Criterion], verified: list[EvidenceItem],
    dropped: list[EvidenceItem],
) -> list[CriterionAssessment]:  # fmt: skip
    out = []
    assessed = {c.id for c in criteria}
    for c in all_criteria:
        mine = [e for e in verified if e.criterion_id == c.id]
        bad = [e for e in dropped if e.criterion_id == c.id]
        if c.id not in assessed:
            label, reason = "missing", "criterion not returned by policy retrieval; not assessed"
        elif c.kind == "note":
            label, reason = assess_note_criterion(c, mine)
        else:
            label, reason = structured.assess(c, mine)
        out.append(CriterionAssessment(criterion_id=c.id, section_id=c.id, label=label,
                                       reason=reason, evidence=mine, dropped=bad))  # fmt: skip
    return out


def run_assessment(
    src: FhirSource, llm: LLM, intake: IntakeResult, retriever=None, verify: bool = True
) -> CaseAssessment:
    ledger_start = len(llm.ledger.calls)
    policy = load_policies()[intake.policy_id]
    sd = intake.service_date
    resources = load_context(src, intake.patient_id, policy, sd)
    service = policy.services[0].display
    docs = [d.document for d in intake.documents_required]
    criteria, sections, not_retrieved = retrieve_policy(
        retriever or default_retriever(llm), policy, service, docs
    )
    candidates = extract_evidence(llm, criteria, resources, sd)
    patient_ref = f"Patient/{intake.patient_id}"
    if verify:
        verified, dropped = verify_citations(src, candidates, patient_ref)
    else:  # baseline: accept every candidate as-is
        verified, dropped = candidates, []
    assessed = assess_criteria(criteria, policy.criteria, verified, dropped)
    notes = [r for r in resources if r["resourceType"] == "DocumentReference"]
    return CaseAssessment(
        service_request_id=intake.service_request_id,
        policy_id=policy.policy_id,
        retrieved_sections=sections,
        missing_from_retrieval=not_retrieved,
        criteria=assessed,
        readiness=readiness(intake.eligible, intake.pa_required, [a.label for a in assessed]),
        injection_flags=note_ext.injection_flags(notes),
        citations_total=len(candidates),
        citations_verified=len(verified),
        llm_usage=llm.ledger.totals(since=ledger_start),
    )
