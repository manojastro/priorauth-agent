"""Create synthetic Acme Health Plan Coverage for Synthea patients that lack one.

Usage: uv run python -m scripts.seed_coverage [--in data/synthea/fhir] [--seed N]

Reads Synthea patient bundles, writes data/synthea/coverage_bundle.json (a transaction bundle).
Coverage.beneficiary uses a conditional reference on the Synthea patient identifier, so it
resolves to whatever id HAPI assigned. About 15% of coverages are terminated on purpose.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

from src.common import fhir_codes as fc
from src.policies.loader import PLAN_TYPES

SYNTHEA_ID_SYSTEM = "https://github.com/synthetichealth/synthea"
DEFAULT_IN = Path("data/synthea/fhir")
DEFAULT_OUT = Path("data/synthea/coverage_bundle.json")
REFERENCE_DATE = date(2026, 10, 1)
TERMINATED_RATE = 0.15


def patients_without_coverage(bundle: dict) -> list[str]:
    """Return Synthea identifiers of patients in a bundle that has no Coverage resource."""
    res = [e["resource"] for e in bundle.get("entry", [])]
    if any(r["resourceType"] == "Coverage" for r in res):
        return []
    out = []
    for r in res:
        if r["resourceType"] != "Patient":
            continue
        ident = next(
            (i["value"] for i in r.get("identifier", []) if i.get("system") == SYNTHEA_ID_SYSTEM),
            None,
        )
        if ident:
            out.append(ident)
    return out


def make_coverage(rng: random.Random, synthea_id: str, n: int) -> dict:
    plan = rng.choice(PLAN_TYPES)
    member_id = f"ACM{rng.randint(10_000_000, 99_999_999)}"
    start = REFERENCE_DATE - timedelta(days=rng.randint(200, 2000))
    period = {"start": start.isoformat()}
    if rng.random() < TERMINATED_RATE:
        period["end"] = (REFERENCE_DATE - timedelta(days=rng.randint(10, 180))).isoformat()
    return {
        "resourceType": "Coverage",
        "id": f"synthea-cov-{n:04d}",
        "status": "active",
        "subscriberId": member_id,
        "identifier": [{"system": fc.MEMBER_ID, "value": member_id}],
        "beneficiary": {"reference": f"Patient?identifier={SYNTHEA_ID_SYSTEM}|{synthea_id}"},
        "payor": [{"reference": f"Organization/{fc.PAYER_ORG_ID}"}],
        "class": [
            {
                "type": {"coding": [{"system": fc.COVERAGE_CLASS, "code": "plan"}]},
                "value": plan,
                "name": f"Acme Health Plan {plan}",
            }
        ],
        "period": period,
    }


def build(in_dir: Path, seed: int) -> dict:
    rng = random.Random(seed)
    ids: list[str] = []
    for f in sorted(in_dir.glob("*.json")):
        if f.name.startswith(("hospitalInformation", "practitionerInformation")):
            continue
        ids += patients_without_coverage(json.loads(f.read_text(encoding="utf-8")))
    entries = []
    for n, sid in enumerate(sorted(ids), start=1):
        cov = make_coverage(rng, sid, n)
        entries.append(
            {"resource": cov, "request": {"method": "PUT", "url": f"Coverage/{cov['id']}"}}
        )
    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_dir", type=Path, default=DEFAULT_IN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=20261114)
    args = ap.parse_args()
    bundle = build(args.in_dir, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(bundle['entry'])} coverages to {args.out}")


if __name__ == "__main__":
    main()
