import base64
import collections
from datetime import date, timedelta

import pytest
from fhir.resources.R4B import get_fhir_model_class

from scripts import build_cases as bc
from src.common import fhir_codes as fc
from src.policies.loader import load_policies

BUNDLES, GTS = bc.build_all()
GT = {g["case_id"]: g for g in GTS}
POLICIES = load_policies()


def resources(case_id):
    return {
        (e["resource"]["resourceType"], e["resource"]["id"]): e["resource"]
        for e in BUNDLES[case_id]["entry"]
    }


def note_text(res):
    return base64.b64decode(res["content"][0]["attachment"]["data"]).decode("utf-8")


def test_fifty_cases_and_mix():
    assert len(GTS) == 50
    cats = collections.Counter(g["category"] for g in GTS)
    assert cats == {"met": 20, "missing": 15, "not_met": 10, "tricky": 5}
    assert sorted(g["tricky_kind"] for g in GTS if g["tricky_kind"]) == sorted(bc.TRICKY_KINDS)


def test_holdout_is_ten_and_stratified():
    held = [g for g in GTS if g["split"] == "holdout"]
    assert len(held) == 10
    assert collections.Counter(g["category"] for g in held) == bc.HOLDOUT_COUNTS


def test_all_eight_services_used():
    assert {g["policy_id"] for g in GTS} == set(POLICIES)


def test_deterministic_bytes(tmp_path):
    m1 = bc.write_all(tmp_path / "a")
    m2 = bc.write_all(tmp_path / "b")
    assert m1 == m2
    for rel in m1["files"]:
        assert (tmp_path / "a" / rel).read_bytes() == (tmp_path / "b" / rel).read_bytes()


def test_different_seed_differs():
    _, other = bc.build_all(seed=1)
    assert [g["plan_type"] for g in other] != [g["plan_type"] for g in GTS]


@pytest.mark.parametrize("name", sorted(BUNDLES))
def test_every_resource_validates_as_fhir(name):
    for e in BUNDLES[name]["entry"]:
        r = e["resource"]
        get_fhir_model_class(r["resourceType"]).model_validate(r)
        assert e["request"] == {"method": "PUT", "url": f"{r['resourceType']}/{r['id']}"}


@pytest.mark.parametrize("case_id", sorted(GT))
def test_case_resources_tagged_and_referenced(case_id):
    res = resources(case_id)
    for r in res.values():
        assert r["meta"]["tag"] == [{"system": fc.CASE_TAG, "code": case_id}]
        assert len(r["id"]) <= 64
    g = GT[case_id]
    assert ("ServiceRequest", g["service_request_id"]) in res
    assert ("Coverage", g["coverage_id"]) in res
    assert ("Patient", g["patient_id"]) in res


@pytest.mark.parametrize("case_id", sorted(GT))
def test_ground_truth_supporting_ids_exist_and_spans_match(case_id):
    res = resources(case_id)
    g = GT[case_id]
    policy = POLICIES[g["policy_id"]]
    assert list(g["expected"]["criteria"]) == [c.id for c in policy.criteria]
    for cid, lab in g["expected"]["criteria"].items():
        assert lab["label"] in ("met", "not_met", "missing")
        if lab["label"] == "met":
            assert lab["supporting"], f"{cid} met without evidence"
        for s in lab["supporting"]:
            r = res[(s["resource_type"], s["resource_id"])]
            if "span" in s:
                a, b = s["span"]
                assert 0 <= a < b <= len(note_text(r))


@pytest.mark.parametrize("case_id", sorted(GT))
def test_readiness_matches_labels(case_id):
    e = GT[case_id]["expected"]
    labels = [lab["label"] for lab in e["criteria"].values()]
    assert e["readiness"] == bc.readiness(e["eligible"], e["pa_required"], labels)


def test_category_semantics():
    for g in GTS:
        labels = [lab["label"] for lab in g["expected"]["criteria"].values()]
        if g["category"] == "met":
            assert set(labels) == {"met"} and g["expected"]["readiness"] == "ready_to_submit"
        if g["category"] == "missing":
            assert "missing" in labels and "not_met" not in labels
        if g["category"] == "not_met":
            assert "not_met" in labels


def _tricky(kind):
    return next(g for g in GTS if g["tricky_kind"] == kind)


def test_terminated_coverage_case():
    g = _tricky("terminated_coverage")
    cov = resources(g["case_id"])[("Coverage", g["coverage_id"])]
    assert date.fromisoformat(cov["period"]["end"]) < date.fromisoformat(g["service_date"])
    assert g["expected"]["eligible"] is False and g["expected"]["readiness"] is None


def test_no_pa_case():
    g = _tricky("no_pa_required")
    assert g["expected"]["pa_required"] is False
    assert POLICIES[g["policy_id"]].pa_required[g["plan_type"]] is False


def test_other_cases_require_pa():
    for g in GTS:
        if g["tricky_kind"] != "no_pa_required":
            assert g["expected"]["pa_required"] is True


def test_injection_case_has_line_and_is_not_all_met():
    g = _tricky("prompt_injection")
    notes = [r for (t, _), r in resources(g["case_id"]).items() if t == "DocumentReference"]
    assert any(bc.INJECTION_LINE in note_text(n) for n in notes)
    assert g["has_injection"]
    assert any(lab["label"] != "met" for lab in g["expected"]["criteria"].values())


def test_injection_line_only_in_injection_case():
    for g in GTS:
        if g["has_injection"]:
            continue
        for (t, _), r in resources(g["case_id"]).items():
            if t == "DocumentReference":
                assert bc.INJECTION_LINE not in note_text(r)


def test_contradictory_case_has_two_conflicting_notes():
    g = _tricky("contradictory_notes")
    lab = next(lab for lab in g["expected"]["criteria"].values() if "note" in lab)
    assert lab["label"] == "missing" and len(lab["supporting"]) == 2


def test_stale_case_evidence_outside_window():
    g = _tricky("stale_evidence")
    cid, lab = next((k, v) for k, v in g["expected"]["criteria"].items() if "note" in v)
    assert lab["label"] == "missing"
    crit = next(c for c in POLICIES[g["policy_id"]].criteria if c.id == cid)
    sd = date.fromisoformat(g["service_date"])
    r = resources(g["case_id"])[
        (lab["supporting"][0]["resource_type"], lab["supporting"][0]["resource_id"])
    ]
    d = (
        r.get("recordedDate")
        or r.get("effectiveDateTime")
        or r.get("performedDateTime")
        or (r.get("performedPeriod") or {}).get("end")
        or r["dispenseRequest"]["validityPeriod"]["end"]
    )
    assert date.fromisoformat(d) < sd - timedelta(days=crit.window_days)


def test_met_note_spans_quote_the_met_sentence():
    for g in GTS:
        res = resources(g["case_id"])
        for cid, lab in g["expected"]["criteria"].items():
            if lab["label"] == "met" and cid in bc.NOTE_TEXT:
                s = lab["supporting"][0]
                a, b = s["span"]
                txt = note_text(res[(s["resource_type"], s["resource_id"])])
                assert txt[a:b] == bc.NOTE_TEXT[cid][0]
