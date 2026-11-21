import pytest
from fastapi.testclient import TestClient

from src.common.config import SYNTHETIC_BANNER
from src.payer_mock.app import app
from src.payer_mock.crd import CrdRequest, check, rule_table
from src.policies.loader import PLAN_TYPES, load_policies

client = TestClient(app)


def test_rule_table_covers_every_service_and_plan():
    table = rule_table()
    for p in load_policies().values():
        for s in p.services:
            for plan in PLAN_TYPES:
                row = table[(s.code, plan)]
                assert row.pa_required == p.pa_required[plan]
                assert row.policy_id == p.policy_id


def test_pa_required_lists_documents_per_criterion():
    r = check(CrdRequest(service_code="SVC-MRI-LSPINE", plan_type="HMO"))
    assert r.pa_required is True and r.policy_id == "ACME-POL-LSMRI"
    assert [d.criterion_id for d in r.documents_required] == [
        "LSMRI-2.1",
        "LSMRI-2.2",
        "LSMRI-2.3",
        "LSMRI-2.4",
    ]
    assert r.documentation_section == "LSMRI-5"


def test_no_pa_needed_has_no_documents():
    r = check(CrdRequest(service_code="SVC-MRI-KNEE", plan_type="PPO"))
    assert r.pa_required is False and r.documents_required == []
    assert r.policy_id == "ACME-POL-KMRI"


@pytest.mark.parametrize(
    ("code", "plan", "known"),
    [("SVC-NOPE", "HMO", False), ("SVC-MRI-KNEE", "PLATINUM", True)],
)
def test_unknown_service_or_plan(code, plan, known):
    r = check(CrdRequest(service_code=code, plan_type=plan))
    assert r.pa_required is None and r.known_service is known


def test_http_endpoint():
    r = client.post("/crd/check", json={"service_code": "SVC-CPAP", "plan_type": "EPO"})
    assert r.status_code == 200
    body = r.json()
    assert body["pa_required"] is True and body["policy_id"] == "ACME-POL-CPAP"


def test_http_rejects_bad_body():
    assert client.post("/crd/check", json={"service_code": "SVC-CPAP"}).status_code == 422


def test_health_shows_banner():
    assert client.get("/health").json()["banner"] == SYNTHETIC_BANNER
