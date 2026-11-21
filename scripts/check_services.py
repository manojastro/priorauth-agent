"""Check that the local docker compose stack is up and ready.

Usage: uv run python -m scripts.check_services [--wait SECONDS]
"""

import argparse
import sys
import time

import httpx
import psycopg

from src.common.config import get_settings


def check_hapi(base_url: str) -> tuple[bool, str]:
    try:
        headers = {"Accept": "application/fhir+json"}
        r = httpx.get(f"{base_url}/metadata", timeout=10, headers=headers)
        if r.status_code == 200 and r.json().get("fhirVersion", "").startswith("4.0"):
            return True, f"fhirVersion={r.json()['fhirVersion']}"
        return False, f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


def check_postgres(dsn: str) -> tuple[bool, str]:
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            row = conn.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()
            if row:
                return True, f"pgvector={row[0]}"
            return False, "pgvector extension missing"
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


def check_jaeger(url: str = "http://localhost:16686") -> tuple[bool, str]:
    try:
        r = httpx.get(url, timeout=5)
        return r.status_code == 200, f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


def run_checks() -> dict[str, tuple[bool, str]]:
    s = get_settings()
    return {
        "hapi": check_hapi(s.fhir_base_url),
        "postgres": check_postgres(s.postgres_dsn),
        "jaeger": check_jaeger(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", type=int, default=0, help="seconds to keep retrying")
    args = ap.parse_args()
    deadline = time.monotonic() + args.wait
    while True:
        results = run_checks()
        if all(ok for ok, _ in results.values()) or time.monotonic() >= deadline:
            break
        time.sleep(5)
    for name, (ok, detail) in results.items():
        print(f"{'OK  ' if ok else 'FAIL'} {name}: {detail}")
    return 0 if all(ok for ok, _ in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
