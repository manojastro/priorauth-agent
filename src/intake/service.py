"""Phase 1 intake: ServiceRequest -> eligibility + PA requirement discovery -> summary.

Usage (live stack): uv run python -m src.intake.service <ServiceRequest id>
Synthetic data. Not for clinical use.
"""

from __future__ import annotations

import argparse
import json
from datetime import date

import httpx
from pydantic import BaseModel

from src.common import fhir_codes as fc
from src.common.config import SYNTHETIC_BANNER, get_settings
from src.common.fhir_source import FhirSource, HapiSource, NotFound
from src.intake.eligibility import CoverageFacts, check_eligibility
from src.payer_mock.crd import CrdResponse, RequiredDocument


class IntakeResult(BaseModel):
    banner: str = SYNTHETIC_BANNER
    service_request_id: str
    patient_id: str | None
    service_code: str | None
    service_date: date | None
    eligible: bool
    eligibility_reasons: list[str]
    coverage: CoverageFacts
    pa_required: bool | None
    policy_id: str | None
    policy_version: str | None
    documents_required: list[RequiredDocument]
    crd_message: str
    summary: str


def _service_code(sr: dict) -> str | None:
    for c in sr.get("code", {}).get("coding", []):
        if c.get("system") == fc.ACME_SERVICE:
            return c.get("code")
    return None


def _service_date(sr: dict) -> date | None:
    v = sr.get("occurrenceDateTime") or (sr.get("occurrencePeriod") or {}).get("start")
    v = v or sr.get("authoredOn")
    return date.fromisoformat(v[:10]) if v else None


def load_coverages(src: FhirSource, sr: dict, patient_ref: str) -> list[dict]:
    """Coverages named on the ServiceRequest first; else search by beneficiary."""
    out = []
    for ins in sr.get("insurance", []):
        ref = ins.get("reference", "")
        if ref.startswith("Coverage/"):
            try:
                out.append(src.read("Coverage", ref.split("/", 1)[1]))
            except NotFound:
                pass
    return out or src.search("Coverage", {"beneficiary": patient_ref})


def crd_check(http: httpx.Client, service_code: str, plan_type: str) -> CrdResponse:
    r = http.post("/crd/check", json={"service_code": service_code, "plan_type": plan_type})
    r.raise_for_status()
    return CrdResponse.model_validate(r.json())


def summarize(res: dict) -> str:
    lines = [SYNTHETIC_BANNER]
    if res["eligible"]:
        lines.append(f"Eligible: yes (plan {res['coverage'].plan_type}).")
    else:
        lines.append(f"Eligible: no ({', '.join(res['eligibility_reasons'])}).")
    if res["pa_required"] is None:
        lines.append(f"PA required: unknown ({res['crd_message']}).")
    elif res["pa_required"]:
        lines.append(f"PA required: yes. Policy {res['policy_id']} v{res['policy_version']}.")
        docs = "; ".join(f"{d.criterion_id}: {d.document}" for d in res["documents_required"])
        lines.append(f"Documents to gather: {docs}.")
    else:
        lines.append("PA required: no.")
    return "\n".join(lines)


def run_intake(src: FhirSource, payer: httpx.Client, service_request_id: str) -> IntakeResult:
    sr = src.read("ServiceRequest", service_request_id)
    patient_ref = (sr.get("subject") or {}).get("reference", "")
    service_code = _service_code(sr)
    service_date = _service_date(sr)

    elig = check_eligibility(load_coverages(src, sr, patient_ref), service_date or date.today())
    if service_date is None:
        elig.reasons.append("service_date_missing")
        elig.eligible = False

    crd = None
    if service_code and elig.coverage.plan_type:
        crd = crd_check(payer, service_code, elig.coverage.plan_type)
    res = {
        "service_request_id": service_request_id,
        "patient_id": patient_ref.split("/", 1)[1] if "/" in patient_ref else None,
        "service_code": service_code,
        "service_date": service_date,
        "eligible": elig.eligible,
        "eligibility_reasons": elig.reasons,
        "coverage": elig.coverage,
        "pa_required": crd.pa_required if crd else None,
        "policy_id": crd.policy_id if crd else None,
        "policy_version": crd.policy_version if crd else None,
        "documents_required": crd.documents_required if crd else [],
        "crd_message": crd.message if crd else "no plan type or service code; CRD not called",
    }
    return IntakeResult(**res, summary=summarize(res))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("service_request_id")
    args = ap.parse_args()
    with httpx.Client(base_url=get_settings().payer_mock_url, timeout=30) as payer:
        out = run_intake(HapiSource(), payer, args.service_request_id)
    print(json.dumps(out.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
