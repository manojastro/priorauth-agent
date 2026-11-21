from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from evals.common import load_ground_truth
from src.common import fhir_codes as fc
from src.common.config import SYNTHETIC_BANNER
from src.common.fhir_client import FhirClient
from src.common.fhir_source import BundleSource, HapiSource, NotFound
from src.intake import eligibility as el
from src.intake.service import run_intake
from src.payer_mock.app import app

SD = date(2026, 10, 15)
GTS = load_ground_truth()
SRC = BundleSource()
PAYER = TestClient(app)


def cov(**over):
    c = {
        "resourceType": "Coverage",
        "id": "c1",
        "status": "active",
        "subscriberId": "ACM12345678",
        "beneficiary": {"reference": "Patient/p1"},
        "payor": [{"reference": f"Organization/{fc.PAYER_ORG_ID}"}],
        "class": [
            {"type": {"coding": [{"system": fc.COVERAGE_CLASS, "code": "plan"}]}, "value": "HMO"}
        ],
        "period": {"start": "2025-01-01"},
    }
    c.update(over)
    return c


def test_eligible_happy_path():
    r = el.check_eligibility([cov()], SD)
    assert r.eligible and r.reasons == [] and r.coverage.plan_type == "HMO"


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"period": {"start": "2025-01-01", "end": "2026-09-30"}}, el.NOT_ACTIVE_ON_DATE),
        ({"period": {"start": "2026-11-01"}}, el.NOT_ACTIVE_ON_DATE),
        ({"status": "cancelled"}, el.STATUS_NOT_ACTIVE),
        ({"class": []}, el.PLAN_TYPE_MISSING),
        ({"subscriberId": None}, el.MEMBER_ID_MISSING),
        ({"payor": [{"reference": "Organization/other"}]}, el.WRONG_PAYER),
    ],
)
def test_ineligible_reasons(over, reason):
    r = el.check_eligibility([cov(**over)], SD)
    assert not r.eligible and reason in r.reasons


def test_no_coverage():
    r = el.check_eligibility([], SD)
    assert not r.eligible and r.reasons == [el.NO_COVERAGE]


def test_coverage_end_date_is_inclusive():
    assert el.check_eligibility(
        [cov(period={"start": "2025-01-01", "end": "2026-10-15"})], SD
    ).eligible


def test_member_id_from_identifier():
    c = cov(subscriberId=None, identifier=[{"system": fc.MEMBER_ID, "value": "ACM1"}])
    assert el.check_eligibility([c], SD).coverage.member_id == "ACM1"


def test_prefers_coverage_active_on_date():
    old = cov(id="a-old", period={"start": "2020-01-01", "end": "2021-01-01"})
    new = cov(id="b-new")
    r = el.check_eligibility([old, new], SD)
    assert r.eligible and r.coverage.coverage_id == "b-new"


@pytest.mark.parametrize("g", GTS, ids=lambda g: g["case_id"])
def test_intake_matches_ground_truth(g):
    r = run_intake(SRC, PAYER, g["service_request_id"])
    assert r.eligible == g["expected"]["eligible"]
    assert sorted(r.eligibility_reasons) == sorted(g["expected"]["eligibility_reasons"])
    assert r.pa_required == g["expected"]["pa_required"]
    assert r.policy_id == g["policy_id"]
    assert r.summary.startswith(SYNTHETIC_BANNER)
    if r.pa_required:
        assert r.documents_required


def test_intake_falls_back_to_coverage_search():
    g = GTS[0]

    class NoInsuranceOnSR(BundleSource):
        def read(self, rt, rid):
            r = super().read(rt, rid)
            return {k: v for k, v in r.items() if k != "insurance"} if rt == "ServiceRequest" else r

    r = run_intake(NoInsuranceOnSR(), PAYER, g["service_request_id"])
    assert r.coverage.coverage_id == g["coverage_id"]


def test_unknown_service_request():
    with pytest.raises(NotFound):
        run_intake(SRC, PAYER, "does-not-exist")


def test_hapi_source_maps_404_to_not_found():
    def handler(req):
        return httpx.Response(404, json={"resourceType": "OperationOutcome"})

    src = HapiSource(FhirClient("http://fhir.test/fhir", transport=httpx.MockTransport(handler)))
    with pytest.raises(NotFound):
        src.read("Patient", "x")


def test_hapi_source_search_follows_next_links():
    pages = {
        "/fhir/Coverage": {
            "entry": [{"resource": {"id": "1"}}],
            "link": [{"relation": "next", "url": "http://fhir.test/fhir/Coverage?page=2"}],
        },
        "/fhir/Coverage?page=2": {"entry": [{"resource": {"id": "2"}}], "link": []},
    }

    def handler(req):
        key = req.url.path + (f"?{req.url.query.decode()}" if b"page" in req.url.query else "")
        return httpx.Response(200, json=pages[key])

    src = HapiSource(FhirClient("http://fhir.test/fhir", transport=httpx.MockTransport(handler)))
    assert [r["id"] for r in src.search("Coverage", {})] == ["1", "2"]
