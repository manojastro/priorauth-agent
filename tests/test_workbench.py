"""Workbench: login stub, server-side role enforcement, banner, evidence viewer."""

import re
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from evals.common import load_ground_truth
from src.common.audit import AuditStore
from src.common.config import SYNTHETIC_BANNER
from src.common.fhir_source import BundleSource
from src.common.llm import get_llm
from src.payer_mock import pas
from src.payer_mock.app import app as payer_app
from src.priorauth.graph import Deps
from src.priorauth.service import PAService, open_checkpointer
from src.workbench.app import create_app

GTS = load_ground_truth()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PAYER_RANDOM_PEND_RATE", "0")
    pas.STORE.reset()

    @contextmanager
    def factory():
        audit = AuditStore(tmp_path / "audit.sqlite")
        with open_checkpointer("sqlite", tmp_path / "cp.sqlite") as cp:
            deps = Deps(src=BundleSource(), llm=get_llm(), payer=TestClient(payer_app), audit=audit)
            yield PAService(deps, cp)
        audit.close()

    with TestClient(create_app(factory)) as c:
        yield c


def login(c, name):
    assert c.post("/login", data={"username": name}, follow_redirects=False).status_code == 303


def start(c, g):
    r = c.post(
        "/cases/start",
        data={"service_request_id": g["service_request_id"], "case_id": g["case_id"]},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return r.headers["location"]


def test_requires_login(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"
    r = client.post("/cases/start", data={"service_request_id": "x"})
    assert r.status_code == 401


def test_banner_on_every_page(client):
    assert SYNTHETIC_BANNER in client.get("/login").text
    login(client, "coord.demo")
    assert SYNTHETIC_BANNER in client.get("/").text
    loc = start(client, GTS[0])
    assert SYNTHETIC_BANNER in client.get(loc).text


def test_unknown_user_rejected(client):
    assert client.post("/login", data={"username": "admin"}).status_code == 400


def test_coordinator_sees_disabled_buttons_and_cannot_submit(client):
    login(client, "coord.demo")
    g = next(g for g in GTS if g["category"] == "met")
    loc = start(client, g)
    page = client.get(loc).text
    assert re.search(r'value="approve"\s+disabled', page)
    # Even a hand-crafted POST is refused server-side (role comes from the session).
    client.post(f"{loc}/decision", data={"action": "approve", "role": "pa_reviewer"})
    assert pas.STORE.submissions == {}
    assert "decision_refused" in client.get(loc).text


def test_reviewer_approves_and_sees_payer_response(client):
    login(client, "reviewer.demo")
    g = next(g for g in GTS if g["category"] == "met")
    loc = start(client, g)
    r = client.post(f"{loc}/decision", data={"action": "approve", "comment": "ok"})
    assert r.status_code == 200
    page = client.get(loc).text
    assert "payer_approved" in page and "pre-auth ref" in page
    assert len(pas.STORE.submissions) == 1


def test_evidence_viewer_highlights_note_span(client):
    login(client, "reviewer.demo")
    g = next(g for g in GTS if g["category"] == "met")
    lab = next(
        lab
        for lab in g["expected"]["criteria"].values()
        if lab["supporting"] and "span" in lab["supporting"][0]
    )
    s = lab["supporting"][0]
    r = client.get(
        f"/evidence/DocumentReference/{s['resource_id']}",
        params={"start": s["span"][0], "end": s["span"][1]},
    )
    assert r.status_code == 200 and "<mark>" in r.text


def test_queue_never_shows_ground_truth(client):
    login(client, "coord.demo")
    page = client.get("/").text
    for word in ("ready_to_submit", "likely_not_meeting_criteria", "holdout", "prompt_injection"):
        assert word not in page
