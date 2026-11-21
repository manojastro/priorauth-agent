"""Where FHIR resources come from: the live HAPI server, or local case bundles (offline).

Both implement the same small read/search interface, so intake and evals run the same code
with or without the docker stack.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from src.common.fhir_client import FhirClient, FhirError

CASES_DIR = Path(__file__).resolve().parents[2] / "data" / "cases" / "bundles"


class NotFound(LookupError):
    pass


class FhirSource(Protocol):
    def read(self, resource_type: str, resource_id: str) -> dict: ...

    def search(self, resource_type: str, params: dict) -> list[dict]: ...


class HapiSource:
    """Live HAPI FHIR server."""

    def __init__(self, client: FhirClient | None = None):
        self.client = client or FhirClient()

    def read(self, resource_type: str, resource_id: str) -> dict:
        try:
            return self.client.read(resource_type, resource_id)
        except FhirError as e:
            if e.status in (404, 410):
                raise NotFound(f"{resource_type}/{resource_id}") from e
            raise

    def search(self, resource_type: str, params: dict) -> list[dict]:
        return self.client.search(resource_type, params)


class BundleSource:
    """Offline source over transaction bundles on disk. Supports the searches we use:
    `patient` / `subject` / `beneficiary` = "Patient/<id>"."""

    REF_PARAMS = {"patient": ("subject", "beneficiary", "patient"), "subject": ("subject",)}

    def __init__(self, bundle_dir: Path = CASES_DIR):
        self._by_key: dict[tuple[str, str], dict] = {}
        for f in sorted(bundle_dir.glob("*.json")):
            for e in json.loads(f.read_text(encoding="utf-8")).get("entry", []):
                r = e["resource"]
                self._by_key[(r["resourceType"], r["id"])] = r

    def read(self, resource_type: str, resource_id: str) -> dict:
        try:
            return self._by_key[(resource_type, resource_id)]
        except KeyError:
            raise NotFound(f"{resource_type}/{resource_id}") from None

    def search(self, resource_type: str, params: dict) -> list[dict]:
        out = []
        for (rt, _), r in self._by_key.items():
            if rt != resource_type:
                continue
            if all(self._match(r, k, v) for k, v in params.items()):
                out.append(r)
        return out

    def _match(self, r: dict, key: str, value: str) -> bool:
        if key == "beneficiary":
            fields = ("beneficiary",)
        elif key in self.REF_PARAMS:
            fields = self.REF_PARAMS[key]
        else:
            raise NotImplementedError(f"BundleSource does not support search param {key!r}")
        return any((r.get(f) or {}).get("reference") == value for f in fields)
