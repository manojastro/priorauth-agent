"""Thin FHIR R4 REST client over httpx. JSON dicts in and out; R4B models for offline checks."""

from __future__ import annotations

from typing import Any

import httpx

from src.common.config import get_settings

FHIR_JSON = "application/fhir+json"


class FhirError(RuntimeError):
    def __init__(self, status: int, body: Any):
        super().__init__(f"FHIR HTTP {status}: {str(body)[:500]}")
        self.status = status
        self.body = body


class FhirClient:
    def __init__(self, base_url: str | None = None, timeout: float = 60.0, **kwargs):
        self.base_url = (base_url or get_settings().fhir_base_url).rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Accept": FHIR_JSON, "Content-Type": FHIR_JSON},
            **kwargs,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> FhirClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _check(self, r: httpx.Response) -> dict:
        body = r.json() if r.content else {}
        if r.status_code >= 400:
            raise FhirError(r.status_code, body)
        return body

    def read(self, resource_type: str, resource_id: str) -> dict:
        return self._check(self._http.get(f"/{resource_type}/{resource_id}"))

    def search(self, resource_type: str, params: dict | None = None) -> list[dict]:
        """Search and follow `next` links. Returns resources (not entries)."""
        out: list[dict] = []
        bundle = self._check(self._http.get(f"/{resource_type}", params=params or {}))
        while True:
            out += [e["resource"] for e in bundle.get("entry", []) if "resource" in e]
            nxt = next(
                (lk["url"] for lk in bundle.get("link", []) if lk["relation"] == "next"), None
            )
            if not nxt:
                return out
            bundle = self._check(self._http.get(nxt))

    def transaction(self, bundle: dict) -> dict:
        return self._check(self._http.post("", json=bundle))

    def validate(self, resource: dict) -> dict:
        """POST {type}/$validate. Returns the OperationOutcome (HTTP 4xx also returns one)."""
        r = self._http.post(f"/{resource['resourceType']}/$validate", json=resource)
        return r.json()


def outcome_errors(outcome: dict) -> list[str]:
    return [
        i.get("diagnostics", "")
        for i in outcome.get("issue", [])
        if i.get("severity") in ("error", "fatal")
    ]
