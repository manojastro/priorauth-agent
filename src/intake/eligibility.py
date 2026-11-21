"""Deterministic eligibility check. Plain code, no LLM."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from src.common import fhir_codes as fc

# Reason codes (stable; evals compare against them).
NO_COVERAGE = "no_coverage_found"
NOT_ACTIVE_ON_DATE = "coverage_not_active_on_service_date"
STATUS_NOT_ACTIVE = "coverage_status_not_active"
PLAN_TYPE_MISSING = "plan_type_missing"
MEMBER_ID_MISSING = "member_id_missing"
WRONG_PAYER = "payer_not_acme"


class CoverageFacts(BaseModel):
    coverage_id: str | None = None
    status: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    plan_type: str | None = None
    member_id: str | None = None
    payer_ref: str | None = None


class EligibilityResult(BaseModel):
    eligible: bool
    reasons: list[str]
    coverage: CoverageFacts


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


def coverage_facts(cov: dict) -> CoverageFacts:
    plan = next(
        (
            c.get("value")
            for c in cov.get("class", [])
            if any(
                cd.get("system") == fc.COVERAGE_CLASS and cd.get("code") == "plan"
                for cd in c.get("type", {}).get("coding", [])
            )
        ),
        None,
    )
    member = cov.get("subscriberId") or next(
        (i.get("value") for i in cov.get("identifier", []) if i.get("system") == fc.MEMBER_ID),
        None,
    )
    period = cov.get("period", {})
    return CoverageFacts(
        coverage_id=cov.get("id"),
        status=cov.get("status"),
        period_start=_date(period.get("start")),
        period_end=_date(period.get("end")),
        plan_type=plan,
        member_id=member,
        payer_ref=(cov.get("payor") or [{}])[0].get("reference"),
    )


def active_on(f: CoverageFacts, d: date) -> bool:
    if f.period_start and d < f.period_start:
        return False
    if f.period_end and d > f.period_end:
        return False
    return True


def check_eligibility(coverages: list[dict], service_date: date) -> EligibilityResult:
    """Pick the best coverage for the service date and check it.

    Preference: active status and period covering the date; else the first coverage found
    (so the reasons explain what is wrong with it).
    """
    if not coverages:
        return EligibilityResult(eligible=False, reasons=[NO_COVERAGE], coverage=CoverageFacts())
    facts = [coverage_facts(c) for c in coverages]
    facts.sort(
        key=lambda f: (
            not (f.status == "active" and active_on(f, service_date)),
            f.coverage_id or "",
        )
    )
    f = facts[0]
    reasons = []
    if f.status != "active":
        reasons.append(STATUS_NOT_ACTIVE)
    if not active_on(f, service_date):
        reasons.append(NOT_ACTIVE_ON_DATE)
    if not f.plan_type:
        reasons.append(PLAN_TYPE_MISSING)
    if not f.member_id:
        reasons.append(MEMBER_ID_MISSING)
    if f.payer_ref != f"Organization/{fc.PAYER_ORG_ID}":
        reasons.append(WRONG_PAYER)
    return EligibilityResult(eligible=not reasons, reasons=reasons, coverage=f)
