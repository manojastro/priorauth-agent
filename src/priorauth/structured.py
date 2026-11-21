"""Deterministic evidence finding and assessment for structured FHIR resources.

No LLM here: codes, dates, durations, counts and thresholds are plain code.
"""

from __future__ import annotations

from datetime import date, timedelta

from src.common import fhir_codes as fc
from src.policies.loader import Criterion
from src.priorauth.models import EvidenceItem, Label

TYPE_FOR_KIND = {
    "condition": "Condition",
    "procedure_duration": "Procedure",
    "procedure_count": "Procedure",
    "procedure_done": "Procedure",
    "medication_trial": "MedicationRequest",
    "observation_threshold": "Observation",
    "observation_result": "Observation",
}


def _d(v: str | None) -> date | None:
    return date.fromisoformat(v[:10]) if v else None


def _code_index(cc: dict, system: str) -> tuple[int, str] | None:
    for i, c in enumerate(cc.get("coding", [])):
        if c.get("system") == system:
            return i, c.get("code")
    return None


def _item(crit, res, stance, checks, when, sd, **facts) -> EvidenceItem:
    in_window = when is not None and sd - timedelta(days=crit.window_days) <= when <= sd
    return EvidenceItem(
        criterion_id=crit.id,
        source="structured",
        resource_type=res["resourceType"],
        resource_id=res["id"],
        stance=stance,
        checks=checks,
        evidence_date=when,
        in_window=in_window,
        facts=facts,
    )


def find(crit: Criterion, resources: list[dict], sd: date) -> list[EvidenceItem]:
    rtype = TYPE_FOR_KIND[crit.kind]
    out: list[EvidenceItem] = []
    for r in (x for x in resources if x["resourceType"] == rtype):
        if crit.kind == "condition":
            hit = _code_index(r.get("code", {}), fc.ICD10CM)
            if not hit or hit[1] not in crit.codes + crit.non_qualifying_codes:
                continue
            i, code = hit
            stance = "supports" if code in crit.codes else "contradicts"
            when = _d(r.get("recordedDate") or r.get("onsetDateTime"))
            if when is None:
                continue
            path = "recordedDate" if r.get("recordedDate") else "onsetDateTime"
            out.append(
                _item(crit, r, stance, {f"code.coding[{i}].code": code, path: when.isoformat()},
                      when, sd, code=code)
            )  # fmt: skip
        elif crit.kind.startswith("procedure"):
            hit = _code_index(r.get("code", {}), crit.system or fc.ACME_CLINICAL)
            if not hit or hit[1] != crit.code or r.get("status") != "completed":
                continue
            i, _ = hit
            checks = {f"code.coding[{i}].code": crit.code, "status": "completed"}
            if "performedPeriod" in r:
                start = _d(r["performedPeriod"].get("start"))
                end = _d(r["performedPeriod"].get("end"))
                if start is None or end is None:
                    continue
                checks |= {"performedPeriod.start": start.isoformat(),
                           "performedPeriod.end": end.isoformat()}  # fmt: skip
                days = (end - start).days
            else:
                end = _d(r.get("performedDateTime"))
                if end is None:
                    continue
                checks["performedDateTime"] = end.isoformat()
                days = 0
            stance = "supports"
            if crit.kind == "procedure_duration" and days < crit.min_days:
                stance = "contradicts"
            out.append(_item(crit, r, stance, checks, end, sd, days=days))
        elif crit.kind == "medication_trial":
            hit = _code_index(r.get("medicationCodeableConcept", {}), fc.RXNORM)
            codes = {m.code for m in crit.rxnorm}
            if not hit or hit[1] not in codes:
                continue
            i, code = hit
            vp = (r.get("dispenseRequest") or {}).get("validityPeriod") or {}
            start, end = _d(vp.get("start") or r.get("authoredOn")), _d(vp.get("end"))
            if start is None or end is None:
                continue
            days = (end - start).days
            checks = {
                f"medicationCodeableConcept.coding[{i}].code": code,
                "dispenseRequest.validityPeriod.start": start.isoformat(),
                "dispenseRequest.validityPeriod.end": end.isoformat(),
            }
            stance = "supports" if days >= crit.min_days else "contradicts"
            out.append(_item(crit, r, stance, checks, end, sd, code=code, days=days))
        else:  # observations
            hit = _code_index(r.get("code", {}), crit.system or fc.ACME_CLINICAL)
            if not hit or hit[1] != crit.code:
                continue
            i, _ = hit
            when = _d(r.get("effectiveDateTime"))
            if when is None:
                continue
            checks = {f"code.coding[{i}].code": crit.code, "effectiveDateTime": when.isoformat()}
            if crit.kind == "observation_threshold":
                if "valueInteger" in r:
                    v, checks["valueInteger"] = float(r["valueInteger"]), str(r["valueInteger"])
                elif "valueQuantity" in r:
                    v = float(r["valueQuantity"]["value"])
                    checks["valueQuantity.value"] = str(r["valueQuantity"]["value"])
                else:
                    continue
                ok = v >= crit.value if crit.op == ">=" else v < crit.value
                stance = "supports" if ok else "contradicts"
                out.append(_item(crit, r, stance, checks, when, sd, value=v))
            else:
                v = r.get("valueString")
                if v not in (crit.met_value, crit.not_met_value):
                    continue
                checks["valueString"] = v
                stance = "supports" if v == crit.met_value else "contradicts"
                out.append(_item(crit, r, stance, checks, when, sd, value=v))
    return sorted(out, key=lambda e: (e.evidence_date or date.min, e.resource_id), reverse=True)


def assess(crit: Criterion, items: list[EvidenceItem]) -> tuple[Label, str]:
    """Label from VERIFIED structured items only."""
    win = [e for e in items if e.in_window]
    ids = lambda xs: ", ".join(f"{e.resource_type}/{e.resource_id}" for e in xs)  # noqa: E731
    if crit.kind == "procedure_count":
        n = len(win)
        if n >= crit.min_count:
            return "met", f"{n} completed visits in window (need {crit.min_count}): {ids(win)}"
        if n:
            return "not_met", f"only {n} visits in window (need {crit.min_count}): {ids(win)}"
    else:
        sup = [e for e in win if e.stance == "supports"]
        con = [e for e in win if e.stance == "contradicts"]
        if sup:
            return "met", f"verified evidence in window: {ids(sup[:1])}"
        if con:
            return "not_met", f"documented but does not satisfy criterion: {ids(con[:1])}"
    if items:
        return (
            "missing",
            f"evidence only outside the {crit.window_days}-day window: {ids(items[:1])}",
        )
    return "missing", "no verified evidence found"
