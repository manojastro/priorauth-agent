"""PAS-like submission, status and (M5) appeal handling for the mock payer.

Da Vinci PAS-*inspired* only; not a certified or conformant implementation.
Decision logic is deterministic: the payer re-checks the evidence attached to the Claim against
the policy rules itself (it does not trust the provider's own labels).

Mock-only instrumentation: submissions must carry an `X-Reviewer-Approval` header naming the
provider-side approval event, so evals can prove no submission happened without approval.
"""

from __future__ import annotations

import base64
import hashlib
import os
import random
import re
import threading
import uuid
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel

from src.common import fhir_codes as fc
from src.policies.loader import Criterion, Policy, policy_for_service
from src.priorauth import structured

SUPPORTING_CATEGORY = "http://acme-health.example/fhir/CodeSystem/pa-criterion"
EXT_QUOTE = "http://acme-health.example/fhir/StructureDefinition/evidence-quote"
EXT_STANCE = "http://acme-health.example/fhir/StructureDefinition/evidence-stance"
CLAIM_TYPE = "http://terminology.hl7.org/CodeSystem/claim-type"

# Synthetic reason codes, modelled loosely on CARC/RARC categories, in our own words.
REASON_CODES = {
    "ACME-D01": "Policy coverage criteria not met by submitted documentation.",
    "ACME-D02": "Service is not covered under the member's plan.",
    "ACME-D03": "Member coverage was not active on the date of service.",
    "ACME-D04": "Request is incomplete or could not be processed.",
    "ACME-P01": "Pended: additional documentation is needed for the listed criteria.",
    "ACME-P02": "Pended: under clinical review (asynchronous).",
}
_INJ = re.compile(r"ignore (the )?policy|mark all criteri|approve this request", re.I)


class Reason(BaseModel):
    code: str
    text: str
    criteria: list[str] = []


class PasDecision(BaseModel):
    submission_id: str
    claim_id: str
    status: str  # approved | denied | pended
    final: bool
    reasons: list[Reason] = []
    criteria: dict[str, str] = {}
    pre_auth_ref: str | None = None
    approval_id: str
    received_utc: str
    claim_response: dict
    polls: int = 0
    is_appeal: bool = False
    appeal_of: str | None = None


class PayerStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.submissions: dict[str, PasDecision] = {}
        self.hidden_final: dict[str, PasDecision] = {}

    def reset(self) -> None:
        with self.lock:
            self.submissions.clear()
            self.hidden_final.clear()


STORE = PayerStore()


class SubmissionError(ValueError):
    pass


def _note_text(doc: dict) -> str:
    for c in doc.get("content", []):
        a = c.get("attachment", {})
        if a.get("data"):
            return base64.b64decode(a["data"]).decode("utf-8")
    return ""


def _ext(info: dict, url: str) -> str | None:
    return next((x.get("valueString") for x in info.get("extension", []) if x["url"] == url), None)


def _judge_note(crit: Criterion, infos: list[dict], res: dict, sd: date) -> str:
    sup = con = False
    for info in infos:
        doc = res.get(info["valueReference"]["reference"])
        quote = _ext(info, EXT_QUOTE)
        if not doc or not quote or quote not in _note_text(doc) or _INJ.search(quote):
            continue
        d = date.fromisoformat(doc.get("date", "1900-01-01")[:10])
        if not (sd - timedelta(days=crit.window_days) <= d <= sd):
            continue
        if _ext(info, EXT_STANCE) == "contradicts":
            con = True
        else:
            sup = True
    if sup and not con:
        return "met"
    if con and not sup:
        return "not_met"
    return "missing"


def evaluate_claim(bundle: dict) -> tuple[Policy, dict[str, str], dict]:
    entries = [e["resource"] for e in bundle.get("entry", [])]
    res = {f"{r['resourceType']}/{r['id']}": r for r in entries}
    claims = [r for r in entries if r["resourceType"] == "Claim"]
    if len(claims) != 1 or claims[0].get("use") != "preauthorization":
        raise SubmissionError("bundle must contain exactly one Claim with use=preauthorization")
    claim = claims[0]
    codes = [
        c.get("code")
        for c in claim["item"][0]["productOrService"].get("coding", [])
        if c.get("system") == fc.ACME_SERVICE
    ]
    policy = policy_for_service(codes[0]) if codes else None
    if policy is None:
        raise SubmissionError("unknown service code")
    sd = date.fromisoformat(claim["item"][0]["servicedDate"][:10])
    by_crit: dict[str, list[dict]] = {}
    for info in claim.get("supportingInfo", []):
        cid = info["category"]["coding"][0]["code"]
        by_crit.setdefault(cid, []).append(info)
    labels = {}
    for crit in policy.criteria:
        infos = by_crit.get(crit.id, [])
        if crit.kind == "note":
            labels[crit.id] = _judge_note(crit, infos, res, sd)
            continue
        attached = [
            res[i["valueReference"]["reference"]]
            for i in infos
            if i["valueReference"]["reference"] in res
        ]
        labels[crit.id] = structured.assess(crit, structured.find(crit, attached, sd))[0]
    return policy, labels, claim


def _coverage_ok(bundle: dict, claim: dict, sd: date) -> tuple[bool, str | None]:
    ref = claim["insurance"][0]["coverage"]["reference"]
    cov = next(
        (
            e["resource"]
            for e in bundle["entry"]
            if f"{e['resource']['resourceType']}/{e['resource']['id']}" == ref
        ),
        None,
    )
    if cov is None:
        return False, None
    p = cov.get("period", {})
    start = date.fromisoformat(p["start"][:10]) if p.get("start") else date.min
    end = date.fromisoformat(p["end"][:10]) if p.get("end") else date.max
    plan = next((c.get("value") for c in cov.get("class", [])), None)
    return (cov.get("status") == "active" and start <= sd <= end), plan


def _claim_response(claim: dict, sub_id: str, status: str, final: bool, reasons, pre_auth):
    cr = {
        "resourceType": "ClaimResponse",
        "id": sub_id,
        "status": "active",
        "type": {"coding": [{"system": CLAIM_TYPE, "code": "professional"}]},
        "use": "preauthorization",
        "patient": claim["patient"],
        "created": datetime.now(UTC).date().isoformat(),
        "insurer": {"reference": f"Organization/{fc.PAYER_ORG_ID}"},
        "request": {"reference": f"Claim/{claim['id']}"},
        "outcome": "complete" if final else "queued",
        "disposition": f"{status}: " + "; ".join(r.text for r in reasons) if reasons else status,
    }
    if pre_auth:
        cr["preAuthRef"] = pre_auth
    return cr


def decide(bundle: dict, approval_id: str, appeal_of: str | None = None) -> PasDecision:
    if not approval_id:
        raise SubmissionError("missing X-Reviewer-Approval")
    policy, labels, claim = evaluate_claim(bundle)
    sd = date.fromisoformat(claim["item"][0]["servicedDate"][:10])
    active, plan = _coverage_ok(bundle, claim, sd)
    reasons: list[Reason] = []
    if not active:
        status = "denied"
        reasons.append(Reason(code="ACME-D03", text=REASON_CODES["ACME-D03"]))
    elif plan and not policy.pa_required.get(plan, True):
        status = "approved"  # no PA needed; accept as informational
    elif failing := [c for c, v in labels.items() if v == "not_met"]:
        status = "denied"
        reasons.append(Reason(code="ACME-D01", text=REASON_CODES["ACME-D01"], criteria=failing))
    elif missing := [c for c, v in labels.items() if v == "missing"]:
        status = "pended"
        reasons.append(Reason(code="ACME-P01", text=REASON_CODES["ACME-P01"], criteria=missing))
    else:
        status = "approved"
    sub_id = f"pas-{uuid.uuid4().hex[:12]}"
    pre_auth = (
        f"ACME-PA-{hashlib.sha1(sub_id.encode()).hexdigest()[:10].upper()}"
        if status == "approved"
        else None
    )
    now = datetime.now(UTC).isoformat(timespec="seconds")
    final = PasDecision(
        submission_id=sub_id,
        claim_id=claim["id"],
        status=status,
        final=True,
        reasons=reasons,
        criteria=labels,
        pre_auth_ref=pre_auth,
        approval_id=approval_id,
        received_utc=now,
        claim_response=_claim_response(claim, sub_id, status, True, reasons, pre_auth),
        is_appeal=appeal_of is not None,
        appeal_of=appeal_of,
    )
    rate = float(os.getenv("PAYER_RANDOM_PEND_RATE", "0"))
    rng = random.Random(int(hashlib.sha1(claim["id"].encode()).hexdigest(), 16))
    with STORE.lock:
        if status != "pended" and rng.random() < rate:
            r = [Reason(code="ACME-P02", text=REASON_CODES["ACME-P02"])]
            shown = final.model_copy(
                update={
                    "status": "pended",
                    "final": False,
                    "reasons": r,
                    "pre_auth_ref": None,
                    "claim_response": _claim_response(claim, sub_id, "pended", False, r, None),
                }
            )
            STORE.hidden_final[sub_id] = final
            STORE.submissions[sub_id] = shown
            return shown
        STORE.submissions[sub_id] = final
    return final


def status(sub_id: str) -> PasDecision | None:
    polls_needed = int(os.getenv("PAYER_POLLS_UNTIL_FINAL", "2"))
    with STORE.lock:
        cur = STORE.submissions.get(sub_id)
        if cur is None:
            return None
        cur = cur.model_copy(update={"polls": cur.polls + 1})
        if not cur.final and sub_id in STORE.hidden_final and cur.polls >= polls_needed:
            cur = STORE.hidden_final.pop(sub_id).model_copy(update={"polls": cur.polls})
        STORE.submissions[sub_id] = cur
        return cur
