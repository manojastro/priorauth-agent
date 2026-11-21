import re

import pytest

from src.policies.loader import PLAN_TYPES, load_policies, parse_policy, policy_for_service

POLICIES = load_policies()
CPT_LIKE = re.compile(r"\b\d{5}\b")  # 5-digit codes; we must not embed CPT


def test_eight_policies():
    assert len(POLICIES) == 8


@pytest.mark.parametrize("pid", sorted(POLICIES))
def test_policy_structure(pid):
    p = POLICIES[pid]
    assert p.version
    assert set(p.pa_required) == set(PLAN_TYPES)
    assert p.services and all(s.code.startswith("SVC-") for s in p.services)
    assert len(p.criteria) >= 3
    prefix = p.criteria[0].id.split("-")[0]
    # Numbered criteria, exclusions, red flags, required documents all present.
    for sec in ("2", "3", "4", "5", "6"):
        assert f"{prefix}-{sec}" in p.sections, f"{pid} missing section {prefix}-{sec}"
    for c in p.criteria:
        assert re.fullmatch(rf"{prefix}-2\.\d+", c.id)
        assert c.text and c.window_days > 0
        assert "note" in {x.kind for x in p.criteria}


@pytest.mark.parametrize("pid", sorted(POLICIES))
def test_criterion_params_complete(pid):
    for c in POLICIES[pid].criteria:
        if c.kind == "condition":
            assert c.codes and c.non_qualifying_codes
        elif c.kind == "procedure_duration":
            assert c.code and c.min_days
        elif c.kind == "procedure_count":
            assert c.code and c.min_count
        elif c.kind == "medication_trial":
            assert c.rxnorm and c.min_days
        elif c.kind == "observation_threshold":
            assert c.code and c.op and c.value is not None and c.value_type
        elif c.kind == "observation_result":
            assert c.met_value and c.not_met_value


def test_no_cpt_like_codes_in_policy_text():
    for p in POLICIES.values():
        for s in p.sections.values():
            assert not CPT_LIKE.search(s.text), f"{p.policy_id} {s.id} has a 5-digit code"


def test_some_service_needs_no_pa_on_some_plan():
    assert any(not all(p.pa_required.values()) for p in POLICIES.values())


def test_policy_for_service():
    assert policy_for_service("SVC-MRI-LSPINE").policy_id == "ACME-POL-LSMRI"
    assert policy_for_service("SVC-NOPE") is None


def test_missing_heading_is_rejected():
    raw = (
        "---\npolicy_id: X\nversion: '1'\ntitle: t\nservices: [{code: SVC-X, display: x}]\n"
        "pa_required: {HMO: true, PPO: true, EPO: true}\n"
        "criteria: [{id: X-2.1, kind: note, window_days: 10}]\n---\n## X-1 Scope\ntext\n"
    )
    with pytest.raises(ValueError, match="no section heading"):
        parse_policy(raw)


def test_section_ids_are_stable_snapshot():
    """Citations point at these ids; changing them is a breaking change."""
    got = {pid: [c.id for c in p.criteria] for pid, p in POLICIES.items()}
    assert got["ACME-POL-LSMRI"] == ["LSMRI-2.1", "LSMRI-2.2", "LSMRI-2.3", "LSMRI-2.4"]
    assert got["ACME-POL-TKA"] == ["TKA-2.1", "TKA-2.2", "TKA-2.3", "TKA-2.4", "TKA-2.5"]
    assert got["ACME-POL-RABIO"] == ["RABIO-2.1", "RABIO-2.2", "RABIO-2.3", "RABIO-2.4"]
