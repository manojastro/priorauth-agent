"""M4: LangGraph flow, approval-gate invariant, audit, restart mid-review, 3-case demo."""

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evals.common import load_ground_truth
from src.common.audit import AuditStore
from src.common.fhir_source import BundleSource
from src.common.llm import get_llm
from src.common.roles import PA_COORDINATOR, PA_REVIEWER
from src.payer_mock import pas
from src.payer_mock.app import app as payer_app
from src.priorauth.graph import Deps
from src.priorauth.packet import packet_hash
from src.priorauth.payer_client import ApprovalGateError, check_approval, submit_packet
from src.priorauth.service import PAService, open_checkpointer

ROOT = Path(__file__).resolve().parents[1]
GTS = load_ground_truth()
REV = {"user": "reviewer.demo", "role": PA_REVIEWER}
COORD = {"user": "coord.demo", "role": PA_COORDINATOR}


def first(pred):
    return next(g for g in GTS if pred(g))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAYER_RANDOM_PEND_RATE", "0")
    pas.STORE.reset()
    audit = AuditStore(tmp_path / "audit.sqlite")
    payer = TestClient(payer_app)
    deps = Deps(src=BundleSource(), llm=get_llm(), payer=payer, audit=audit)
    with open_checkpointer("sqlite", tmp_path / "cp.sqlite") as cp:
        yield PAService(deps, cp), deps, tmp_path
    audit.close()


def submissions():
    return list(pas.STORE.submissions.values())


# ---------------- approval-gate invariant ----------------


def test_run_pauses_for_review_and_nothing_is_submitted(env):
    svc, _, _ = env
    g = first(lambda g: g["category"] == "met")
    tid = svc.start(g["service_request_id"], **COORD)
    st = svc.state(tid)
    assert st["next"] == ["human_review"] and st["pending_review"]
    assert submissions() == []


@pytest.mark.parametrize("action", ["approve", "edit", "reject"])
def test_coordinator_cannot_decide(env, action):
    svc, deps, _ = env
    g = first(lambda g: g["category"] == "met")
    tid = svc.start(g["service_request_id"], **COORD)
    st = svc.decide(tid, {"action": action, **COORD})
    assert st["next"] == ["human_review"] and submissions() == []
    assert deps.audit.for_thread(tid)[-1].action == "decision_refused"


def test_forged_role_in_state_cannot_bypass_gate(env):
    svc, deps, _ = env
    g = first(lambda g: g["category"] == "met")
    tid = svc.start(g["service_request_id"], **COORD)
    packet = svc.state(tid)["values"]["packet"]
    # An approval written by a coordinator, or for another thread, or for another payload:
    bad_role = deps.audit.append(
        tid, "x", PA_COORDINATOR, "approve", {"payload_hash": packet_hash(packet)}
    )
    other = deps.audit.append(
        "other-thread", "r", PA_REVIEWER, "approve", {"payload_hash": packet_hash(packet)}
    )
    stale = deps.audit.append(tid, "r", PA_REVIEWER, "approve", {"payload_hash": "deadbeef"})
    for ev_id in (None, "no-such-event", bad_role.event_id, other.event_id, stale.event_id):
        with pytest.raises(ApprovalGateError):
            submit_packet(deps.payer, deps.audit, tid, packet, ev_id)
    assert submissions() == []


def test_valid_approval_check_passes(env):
    svc, deps, _ = env
    g = first(lambda g: g["category"] == "met")
    tid = svc.start(g["service_request_id"], **COORD)
    packet = svc.state(tid)["values"]["packet"]
    ev = deps.audit.append(tid, "r", PA_REVIEWER, "approve", {"payload_hash": packet_hash(packet)})
    check_approval(deps.audit, tid, packet, ev.event_id, "approve")


def test_payer_rejects_submission_without_approval_header():
    pas.STORE.reset()
    r = TestClient(payer_app).post("/pas/submit", json={"resourceType": "Bundle", "entry": []})
    assert r.status_code == 400 and submissions() == []


def test_only_payer_client_posts_to_pas():
    """Static check: no other module in src/ sends to /pas/submit or /pas/appeal."""
    hits = []
    for f in (ROOT / "src").rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in ("/pas/submit", "/pas/appeal"):
                    hits.append(f.relative_to(ROOT).as_posix())
    assert set(hits) <= {"src/priorauth/payer_client.py", "src/payer_mock/app.py"}


def test_every_submission_has_reviewer_approval(env):
    svc, deps, _ = env
    for g in [first(lambda g: g["category"] == "met"), first(lambda g: g["category"] == "not_met")]:
        tid = svc.start(g["service_request_id"], **COORD)
        svc.decide(tid, {"action": "approve", **COORD})  # refused
        svc.decide(tid, {"action": "approve", **REV})
    subs = submissions()
    assert len(subs) == 2
    for s in subs:
        ev = deps.audit.get(s.approval_id)
        assert ev and ev.action == "approve" and ev.role == PA_REVIEWER


# ---------------- review actions ----------------


def test_edit_overrides_are_audited_and_rebuild_packet(env):
    svc, deps, _ = env
    g = first(lambda g: g["category"] == "missing")
    tid = svc.start(g["service_request_id"], **REV)
    before = svc.state(tid)["values"]
    cid = next(
        c["criterion_id"] for c in before["assessment"]["criteria"] if c["label"] == "missing"
    )
    st = svc.decide(
        tid,
        {
            "action": "edit",
            **REV,
            "overrides": {cid: {"label": "met", "reason": "faxed record reviewed"}},
        },
    )
    v = st["values"]
    assert st["next"] == ["human_review"]
    c = next(c for c in v["assessment"]["criteria"] if c["criterion_id"] == cid)
    assert c["label"] == "met" and "faxed record reviewed" in c["reason"]
    assert v["packet_hash"] != before["packet_hash"]
    ov = [e for e in deps.audit.for_thread(tid) if e.action == "override"]
    assert len(ov) == 1 and ov[0].before["label"] == "missing" and ov[0].after["label"] == "met"


def test_override_without_reason_is_refused(env):
    svc, deps, _ = env
    g = first(lambda g: g["category"] == "missing")
    tid = svc.start(g["service_request_id"], **REV)
    cid = svc.state(tid)["values"]["assessment"]["criteria"][0]["criterion_id"]
    svc.decide(tid, {"action": "edit", **REV, "overrides": {cid: {"label": "met", "reason": " "}}})
    assert any(e.action == "override_refused" for e in deps.audit.for_thread(tid))
    assert not any(e.action == "override" for e in deps.audit.for_thread(tid))


def test_approval_before_edit_is_void(env):
    """An approval binds to one packet hash; a rebuilt packet needs a new approval."""
    svc, deps, _ = env
    g = first(lambda g: g["category"] == "missing")
    tid = svc.start(g["service_request_id"], **REV)
    old_packet = svc.state(tid)["values"]["packet"]
    early = deps.audit.append(
        tid, "r", PA_REVIEWER, "approve", {"payload_hash": packet_hash(old_packet)}
    )
    cid = svc.state(tid)["values"]["assessment"]["criteria"][0]["criterion_id"]
    svc.decide(tid, {"action": "edit", **REV, "overrides": {cid: {"label": "met", "reason": "ok"}}})
    new_packet = svc.state(tid)["values"]["packet"]
    with pytest.raises(ApprovalGateError):
        submit_packet(deps.payer, deps.audit, tid, new_packet, early.event_id)


# ---------------- restart mid-review ----------------


def test_restart_mid_review_resumes_from_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("PAYER_RANDOM_PEND_RATE", "0")
    pas.STORE.reset()
    g = first(lambda g: g["category"] == "met")
    cp_file, audit_file = tmp_path / "cp.sqlite", tmp_path / "audit.sqlite"

    audit = AuditStore(audit_file)
    with open_checkpointer("sqlite", cp_file) as cp:
        deps = Deps(src=BundleSource(), llm=get_llm(), payer=TestClient(payer_app), audit=audit)
        tid = PAService(deps, cp).start(g["service_request_id"], **COORD)
    audit.close()  # "process exits"

    audit2 = AuditStore(audit_file)
    with open_checkpointer("sqlite", cp_file) as cp2:
        deps2 = Deps(src=BundleSource(), llm=get_llm(), payer=TestClient(payer_app), audit=audit2)
        svc2 = PAService(deps2, cp2)
        assert svc2.state(tid)["next"] == ["human_review"]
        st = svc2.decide(tid, {"action": "approve", **REV})
    assert st["values"]["stage"] == "payer_approved"
    assert [e.action for e in audit2.for_thread(tid)][:2] == ["run_started", "intake"]
    audit2.close()


# ---------------- 3-case end-to-end demo ----------------


def test_demo_three_outcomes(env):
    svc, deps, _ = env
    approved = first(lambda g: g["category"] == "met" and g["split"] == "dev")
    more_info = first(lambda g: g["category"] == "missing" and g["split"] == "dev")
    denied = first(
        lambda g: (
            g["category"] == "not_met"
            and g["split"] == "dev"
            and g["expected"]["readiness"] == "likely_not_meeting_criteria"
        )
    )

    t1 = svc.start(approved["service_request_id"], **COORD)
    s1 = svc.decide(t1, {"action": "approve", **REV})["values"]
    assert s1["stage"] == "payer_approved" and s1["submission"]["pre_auth_ref"]

    t2 = svc.start(more_info["service_request_id"], **COORD)
    s2 = svc.decide(t2, {"action": "reject", **REV, "comment": "request PT records"})["values"]
    assert s2["stage"] == "needs_more_info" and "submission" not in s2

    t3 = svc.start(denied["service_request_id"], **COORD)
    s3 = svc.decide(t3, {"action": "approve", **REV, "comment": "submit as documented"})["values"]
    assert s3["stage"] == "payer_denied"
    assert s3["submission"]["reasons"][0]["code"] == "ACME-D01"
    assert len(submissions()) == 2


def test_ineligible_and_no_pa_cases_stop_after_intake(env):
    svc, _, _ = env
    for kind, stage in (
        ("terminated_coverage", "not_eligible"),
        ("no_pa_required", "no_pa_required"),
    ):
        g = first(lambda g, k=kind: g["tricky_kind"] == k)
        tid = svc.start(g["service_request_id"], **COORD)
        st = svc.state(tid)
        assert st["values"]["stage"] == stage and st["next"] == []
    assert submissions() == []


def test_async_pending_resolves_via_status_polls(env, monkeypatch):
    svc, deps, _ = env
    monkeypatch.setenv("PAYER_RANDOM_PEND_RATE", "1.0")
    monkeypatch.setenv("PAYER_POLLS_UNTIL_FINAL", "2")
    g = first(lambda g: g["category"] == "met")
    tid = svc.start(g["service_request_id"], **COORD)
    v = svc.decide(tid, {"action": "approve", **REV})["values"]
    assert v["status_history"][0]["status"] == "pended"
    assert v["stage"] == "payer_approved" and v["submission"]["final"]
    assert any(e.action == "status_update" for e in deps.audit.for_thread(tid))
