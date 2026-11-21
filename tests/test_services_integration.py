"""Integration checks against the running docker compose stack.

Run with: uv run pytest -m integration
Skipped automatically when the stack is not reachable.
"""

import pytest

from scripts.check_services import run_checks

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def results():
    r = run_checks()
    if not any(ok for ok, _ in r.values()):
        pytest.skip("docker compose stack not running")
    return r


@pytest.mark.parametrize("service", ["hapi", "postgres", "jaeger"])
def test_service_ready(results, service):
    ok, detail = results[service]
    assert ok, f"{service}: {detail}"
