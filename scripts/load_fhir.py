"""Load bundles into HAPI in dependency order.

Usage: uv run python -m scripts.load_fhir [--synthea] [--cases] [--validate]

Order: shared case orgs -> Synthea hospital + practitioner bundles -> Synthea patient bundles
-> seeded coverage -> case bundles. With --validate, every case resource is first checked with
HAPI's $validate; any error stops the load (we fix the generator, never loosen validation).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.common.fhir_client import FhirClient, outcome_errors

SYNTHEA_DIR = Path("data/synthea/fhir")
COVERAGE_BUNDLE = Path("data/synthea/coverage_bundle.json")
CASES_DIR = Path("data/cases/bundles")


def synthea_files() -> list[Path]:
    files = sorted(SYNTHEA_DIR.glob("*.json"))
    first = [f for f in files if f.name.startswith("hospitalInformation")]
    second = [f for f in files if f.name.startswith("practitionerInformation")]
    rest = [f for f in files if f not in first and f not in second]
    out = first + second + rest
    if COVERAGE_BUNDLE.exists():
        out.append(COVERAGE_BUNDLE)
    return out


def case_files() -> list[Path]:
    files = sorted(CASES_DIR.glob("*.json"))
    return [f for f in files if f.name == "_shared.json"] + [
        f for f in files if f.name != "_shared.json"
    ]


def validate_bundle(client: FhirClient, bundle: dict, name: str) -> list[str]:
    errs = []
    for e in bundle["entry"]:
        r = e["resource"]
        for msg in outcome_errors(client.validate(r)):
            errs.append(f"{name} {r['resourceType']}/{r['id']}: {msg}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthea", action="store_true")
    ap.add_argument("--cases", action="store_true")
    ap.add_argument("--validate", action="store_true", help="$validate case resources first")
    args = ap.parse_args()
    if not (args.synthea or args.cases):
        args.synthea = args.cases = True

    with FhirClient() as client:
        # Shared orgs first: Synthea coverage references the payer org.
        files = case_files()[:1] if args.synthea else []
        if args.synthea:
            files += synthea_files()
        if args.cases:
            files += [f for f in case_files() if f not in files]
        for f in files:
            bundle = json.loads(f.read_text(encoding="utf-8"))
            if args.validate and f.parent == CASES_DIR:
                errs = validate_bundle(client, bundle, f.name)
                if errs:
                    print("\n".join(errs))
                    return 1
            client.transaction(bundle)
            print(f"loaded {f} ({len(bundle.get('entry', []))} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
