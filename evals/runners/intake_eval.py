"""M2 eval: eligibility accuracy and PA-required accuracy on all 50 cases (dev + holdout).

Usage: uv run python -m evals.runners.intake_eval [--live]
Default runs offline: case bundles from disk + the mock payer app in-process (TestClient).
--live uses HAPI and the mock payer at PAYER_MOCK_URL.
"""

from __future__ import annotations

import argparse

import httpx
from fastapi.testclient import TestClient

from evals.common import (
    SPLITS,
    accuracy,
    load_ground_truth,
    meta_block,
    run_metadata,
    write_report,
)
from src.common.config import get_settings
from src.common.fhir_source import BundleSource, FhirSource, HapiSource
from src.intake.service import run_intake
from src.payer_mock.app import app as payer_app


def evaluate(src: FhirSource, payer: httpx.Client, gts: list[dict]) -> dict:
    rows = []
    for g in gts:
        r = run_intake(src, payer, g["service_request_id"])
        e = g["expected"]
        rows.append(
            {
                "case_id": g["case_id"],
                "split": g["split"],
                "category": g["category"],
                "tricky_kind": g["tricky_kind"],
                "eligible": [r.eligible, e["eligible"]],
                "eligibility_reasons": [
                    sorted(r.eligibility_reasons),
                    sorted(e["eligibility_reasons"]),
                ],
                "pa_required": [r.pa_required, e["pa_required"]],
                "policy_id": [r.policy_id, g["policy_id"]],
            }
        )
    metrics = {}
    for split in (*SPLITS, "all"):
        sel = [x for x in rows if split == "all" or x["split"] == split]
        metrics[split] = {
            k: accuracy([tuple(x[k]) for x in sel])
            for k in ("eligible", "eligibility_reasons", "pa_required", "policy_id")
        }
    failures = [
        x
        for x in rows
        if any(
            x[k][0] != x[k][1]
            for k in ("eligible", "eligibility_reasons", "pa_required", "policy_id")
        )
    ]
    return {"metrics": metrics, "failures": failures, "rows": rows}


def to_markdown(meta: dict, res: dict) -> str:
    names = {
        "eligible": "Eligibility accuracy",
        "eligibility_reasons": "Eligibility reasons exact match",
        "pa_required": "PA-required accuracy",
        "policy_id": "Policy selection accuracy",
    }
    out = ["# Intake eval (M2)\n", meta_block(meta), ""]
    out.append("| Metric | dev | holdout | all |")
    out.append("|---|---|---|---|")
    for k, label in names.items():
        cells = []
        for split in (*SPLITS, "all"):
            m = res["metrics"][split][k]
            cells.append(f"{m['accuracy']:.2%} ({m['correct']}/{m['n']})")
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    out.append("")
    if res["failures"]:
        out.append("## Failures\n")
        for f in res["failures"]:
            out.append(f"- `{f['case_id']}` ({f['category']}/{f['tricky_kind']}): {f}")
    else:
        out.append("No failures.")
    return "\n".join(out) + "\n"


def run(live: bool = False) -> dict:
    gts = load_ground_truth()
    if live:
        src: FhirSource = HapiSource()
        payer: httpx.Client = httpx.Client(base_url=get_settings().payer_mock_url, timeout=30)
        source = "live HAPI + mock payer service"
    else:
        src = BundleSource()
        payer = TestClient(payer_app)
        source = "offline: data/cases bundles + in-process mock payer"
    with payer:
        res = evaluate(src, payer, gts)
    meta = run_metadata(source)
    payload = {"meta": meta, **res}
    j, m = write_report("intake", payload, to_markdown(meta, res))
    print(f"wrote {j} and {m}")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    run(ap.parse_args().live)


if __name__ == "__main__":
    main()
