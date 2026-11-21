"""build_packet: FHIR R4 collection Bundle with a Claim (use = preauthorization), the supporting
resources it references, and a human-readable cover summary (Claim.text narrative).

Each verified evidence item becomes a Claim.supportingInfo entry whose category code is the policy
criterion id, so the payer can map evidence to criteria. Note evidence carries its quote and span
in an extension.
"""

from __future__ import annotations

import hashlib
import html
import json
from datetime import date

from src.common import fhir_codes as fc
from src.common.config import SYNTHETIC_BANNER
from src.common.fhir_source import FhirSource

SUPPORTING_CATEGORY = "http://acme-health.example/fhir/CodeSystem/pa-criterion"
EXT_QUOTE = "http://acme-health.example/fhir/StructureDefinition/evidence-quote"
EXT_SPAN = "http://acme-health.example/fhir/StructureDefinition/evidence-span"
EXT_LABEL = "http://acme-health.example/fhir/StructureDefinition/criterion-assessment"
EXT_STANCE = "http://acme-health.example/fhir/StructureDefinition/evidence-stance"
CLAIM_TYPE = "http://terminology.hl7.org/CodeSystem/claim-type"
PRIORITY = "http://terminology.hl7.org/CodeSystem/processpriority"


def packet_hash(packet: dict) -> str:
    return hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()


def _narrative(intake: dict, assessment: dict) -> dict:
    rows = "".join(
        f"<tr><td>{html.escape(c['criterion_id'])}</td><td>{html.escape(c['label'])}</td>"
        f"<td>{html.escape(c['reason'])}</td></tr>"
        for c in assessment["criteria"]
    )
    div = (
        '<div xmlns="http://www.w3.org/1999/xhtml">'
        f"<p><b>{html.escape(SYNTHETIC_BANNER)}</b></p>"
        f"<p>Prior authorization request for {html.escape(str(intake['service_code']))} "
        f"on {html.escape(str(intake['service_date']))} under policy "
        f"{html.escape(str(assessment['policy_id']))}.</p>"
        f"<p>Readiness (agent recommendation, reviewer decides): "
        f"{html.escape(str(assessment['readiness']))}</p>"
        f"<table><tr><th>Criterion</th><th>Assessment</th><th>Reason</th></tr>{rows}</table>"
        "</div>"
    )
    return {"status": "generated", "div": div}


def build_packet(src: FhirSource, intake: dict, assessment: dict, created: date) -> dict:
    sr = src.read("ServiceRequest", intake["service_request_id"])
    patient_ref = f"Patient/{intake['patient_id']}"
    cov_id = intake["coverage"]["coverage_id"]
    supporting: list[dict] = []
    include: dict[tuple[str, str], dict] = {}
    for key in (("Patient", intake["patient_id"]), ("Coverage", cov_id),
                ("ServiceRequest", intake["service_request_id"])):  # fmt: skip
        include[key] = src.read(*key)
    for c in assessment["criteria"]:
        for e in c["evidence"]:
            info = {
                "sequence": len(supporting) + 1,
                "category": {
                    "coding": [{"system": SUPPORTING_CATEGORY, "code": c["criterion_id"]}]
                },
                "valueReference": {"reference": f"{e['resource_type']}/{e['resource_id']}"},
                "extension": [
                    {"url": EXT_LABEL, "valueString": c["label"]},
                    {"url": EXT_STANCE, "valueString": e["stance"]},
                ],
            }
            if e["source"] == "note":
                info["extension"] += [
                    {"url": EXT_QUOTE, "valueString": e["quote"]},
                    {"url": EXT_SPAN, "valueString": f"{e['span'][0]}-{e['span'][1]}"},
                ]
            supporting.append(info)
            key = (e["resource_type"], e["resource_id"])
            include.setdefault(key, src.read(*key))
    diagnoses = [
        {"sequence": i + 1, "diagnosisReference": {"reference": ref}}
        for i, ref in enumerate(
            dict.fromkeys(
                f"Condition/{e['resource_id']}"
                for c in assessment["criteria"]
                for e in c["evidence"]
                if e["resource_type"] == "Condition" and e["stance"] == "supports"
            )
        )
    ]
    claim = {
        "resourceType": "Claim",
        "id": f"pa-{intake['service_request_id']}",
        "text": _narrative(intake, assessment),
        "status": "active",
        "type": {"coding": [{"system": CLAIM_TYPE, "code": "professional"}]},
        "use": "preauthorization",
        "patient": {"reference": patient_ref},
        "created": created.isoformat(),
        "insurer": {"reference": f"Organization/{fc.PAYER_ORG_ID}"},
        "provider": {"reference": f"Organization/{fc.CLINIC_ORG_ID}"},
        "priority": {"coding": [{"system": PRIORITY, "code": "normal"}]},
        "referral": {"reference": f"ServiceRequest/{intake['service_request_id']}"},
        "insurance": [
            {"sequence": 1, "focal": True, "coverage": {"reference": f"Coverage/{cov_id}"}}
        ],
        "item": [
            {
                "sequence": 1,
                "productOrService": sr["code"],
                "servicedDate": str(intake["service_date"]),
            }
        ],
    }
    if supporting:
        claim["supportingInfo"] = supporting
    if diagnoses:
        claim["diagnosis"] = diagnoses
    entries = [{"fullUrl": f"urn:pa:Claim/{claim['id']}", "resource": claim}]
    for (rt, rid), res in include.items():
        entries.append({"fullUrl": f"urn:pa:{rt}/{rid}", "resource": res})
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": f"{created.isoformat()}T00:00:00Z",
        "entry": entries,
    }


def validate_packet_offline(packet: dict) -> list[str]:
    """Parse every resource with fhir.resources R4B models. HAPI $validate is used when live."""
    from fhir.resources.R4B import get_fhir_model_class

    errs = []
    for e in packet["entry"]:
        r = e["resource"]
        try:
            get_fhir_model_class(r["resourceType"]).model_validate(r)
        except Exception as ex:  # noqa: BLE001
            errs.append(f"{r['resourceType']}/{r.get('id')}: {str(ex)[:300]}")
    try:
        get_fhir_model_class("Bundle").model_validate(packet)
    except Exception as ex:  # noqa: BLE001
        errs.append(f"Bundle: {str(ex)[:300]}")
    return errs
