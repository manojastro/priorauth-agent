"""Phase 2 LangGraph agent.

intake -> load_context -> retrieve_policy -> extract_evidence -> verify_citations ->
assess_criteria -> build_packet -> human_review (interrupt) -> submit -> track_status

human_review: approve -> submit; edit (criterion overrides, audited) -> build_packet -> review
again; reject -> END (needs more info). Ineligible or no-PA cases stop after intake.
State is plain JSON so any checkpointer (SQLite locally, Postgres) can persist it; review can
resume after a restart.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from src.common.audit import AuditStore
from src.common.fhir_source import FhirSource
from src.common.llm import LLM
from src.common.roles import PA_REVIEWER
from src.intake.service import run_intake
from src.policies.loader import load_policies
from src.priorauth import pipeline as pl
from src.priorauth.models import EvidenceItem
from src.priorauth.packet import build_packet, packet_hash, validate_packet_offline
from src.priorauth.payer_client import get_status, submit_packet
from src.priorauth.verify import verify_citations

AGENT = "agent"


@dataclass
class Deps:
    src: FhirSource
    llm: LLM
    payer: httpx.Client
    audit: AuditStore
    retriever: Any = None
    today: Callable[[], date] = date.today
    max_polls: int = 5
    poll_interval_s: float = 0.0
    extra: dict = field(default_factory=dict)


class PAState(TypedDict, total=False):
    service_request_id: str
    stage: str
    intake: dict
    resources: list[dict]
    criteria_ids: list[str]
    sections: list[str]
    not_retrieved: list[str]
    candidates: list[dict]
    verified: list[dict]
    dropped: list[dict]
    assessment: dict
    packet: dict
    packet_hash: str
    packet_errors: list[str]
    last_decision: dict
    approval_id: str | None
    submission: dict
    status_history: list[dict]


def _tid(config) -> str:
    return config["configurable"]["thread_id"]


def build_graph(deps: Deps, checkpointer=None):
    policies = load_policies()

    def policy_of(state):
        return policies[state["intake"]["policy_id"]]

    def n_intake(state: PAState, config) -> dict:
        r = run_intake(deps.src, deps.payer, state["service_request_id"])
        stage = "intake_done"
        if not r.eligible:
            stage = "not_eligible"
        elif r.pa_required is False:
            stage = "no_pa_required"
        elif r.pa_required is None:
            stage = "pa_requirement_unknown"
        deps.audit.append(
            _tid(config),
            AGENT,
            "system",
            "intake",
            {"stage": stage, "reasons": r.eligibility_reasons, "pa_required": r.pa_required},
        )
        return {"intake": r.model_dump(mode="json"), "stage": stage}

    def n_load_context(state: PAState) -> dict:
        i = state["intake"]
        sd = date.fromisoformat(i["service_date"])
        return {"resources": pl.load_context(deps.src, i["patient_id"], policy_of(state), sd)}

    def n_retrieve(state: PAState) -> dict:
        p = policy_of(state)
        docs = [d["document"] for d in state["intake"]["documents_required"]]
        crit, sections, missing = pl.retrieve_policy(
            deps.retriever or pl.default_retriever(deps.llm), p, p.services[0].display, docs
        )
        return {
            "criteria_ids": [c.id for c in crit],
            "sections": sections,
            "not_retrieved": missing,
        }

    def n_extract(state: PAState) -> dict:
        p = policy_of(state)
        crit = [c for c in p.criteria if c.id in state["criteria_ids"]]
        sd = date.fromisoformat(state["intake"]["service_date"])
        items = pl.extract_evidence(deps.llm, crit, state["resources"], sd)
        return {"candidates": [i.model_dump(mode="json") for i in items]}

    def n_verify(state: PAState) -> dict:
        items = [EvidenceItem.model_validate(i) for i in state["candidates"]]
        ok, bad = verify_citations(deps.src, items, f"Patient/{state['intake']['patient_id']}")
        return {
            "verified": [i.model_dump(mode="json") for i in ok],
            "dropped": [i.model_dump(mode="json") for i in bad],
        }

    def n_assess(state: PAState) -> dict:
        p = policy_of(state)
        crit = [c for c in p.criteria if c.id in state["criteria_ids"]]
        ok = [EvidenceItem.model_validate(i) for i in state["verified"]]
        bad = [EvidenceItem.model_validate(i) for i in state["dropped"]]
        assessed = pl.assess_criteria(crit, p.criteria, ok, bad)
        i = state["intake"]
        notes = [r for r in state["resources"] if r["resourceType"] == "DocumentReference"]
        return {
            "assessment": {
                "policy_id": p.policy_id,
                "policy_version": p.version,
                "criteria": [a.model_dump(mode="json") for a in assessed],
                "readiness": pl.readiness(
                    i["eligible"], i["pa_required"], [a.label for a in assessed]
                ),
                "injection_flags": pl.note_ext.injection_flags(notes),
                "citations_total": len(state["candidates"]),
                "citations_verified": len(ok),
            },
            "stage": "assessed",
        }

    def n_build_packet(state: PAState) -> dict:
        packet = build_packet(deps.src, state["intake"], state["assessment"], deps.today())
        return {
            "packet": packet,
            "packet_hash": packet_hash(packet),
            "packet_errors": validate_packet_offline(packet),
            "approval_id": None,  # any earlier approval is void for a rebuilt packet
            "stage": "awaiting_review",
        }

    def n_review(state: PAState, config) -> dict:
        tid = _tid(config)
        decision = interrupt(
            {
                "type": "review_request",
                "packet_hash": state["packet_hash"],
                "readiness": state["assessment"]["readiness"],
                "criteria": [
                    {"id": c["criterion_id"], "label": c["label"]}
                    for c in state["assessment"]["criteria"]
                ],
                "packet_errors": state["packet_errors"],
            }
        )
        user, role = decision.get("user", "?"), decision.get("role", "?")
        action = decision.get("action")
        if role != PA_REVIEWER or action not in ("approve", "edit", "reject"):
            deps.audit.append(
                tid,
                user,
                role,
                "decision_refused",
                {"action": action, "why": "only pa_reviewer may decide"},
            )
            return {"last_decision": {**decision, "refused": True}, "stage": "awaiting_review"}
        if action == "approve":
            if state["packet_errors"]:
                deps.audit.append(
                    tid,
                    user,
                    role,
                    "decision_refused",
                    {"action": action, "why": "packet failed validation"},
                )
                return {"last_decision": {**decision, "refused": True}, "stage": "awaiting_review"}
            ev = deps.audit.append(
                tid,
                user,
                role,
                "approve",
                {"payload_hash": state["packet_hash"], "comment": decision.get("comment", "")},
            )
            return {"last_decision": decision, "approval_id": ev.event_id, "stage": "approved"}
        if action == "reject":
            deps.audit.append(tid, user, role, "reject", {"comment": decision.get("comment", "")})
            return {"last_decision": decision, "stage": "needs_more_info"}
        # edit: criterion overrides, each audited with before/after
        overrides = decision.get("overrides") or {}
        a = {**state["assessment"], "criteria": [dict(c) for c in state["assessment"]["criteria"]]}
        for c in a["criteria"]:
            ov = overrides.get(c["criterion_id"])
            if not ov:
                continue
            reason = (ov.get("reason") or "").strip()
            if ov.get("label") not in ("met", "not_met", "missing") or not reason:
                deps.audit.append(
                    tid,
                    user,
                    role,
                    "override_refused",
                    {
                        "criterion_id": c["criterion_id"],
                        "why": "label must be met/not_met/missing and reason given",
                    },
                )
                continue
            before = {"label": c["label"], "reason": c["reason"]}
            c["label"] = ov["label"]
            c["reason"] = f"Reviewer override by {user}: {reason}"
            c["overridden_by"] = user
            deps.audit.append(
                tid,
                user,
                role,
                "override",
                {"criterion_id": c["criterion_id"]},
                before=before,
                after={"label": c["label"], "reason": c["reason"]},
            )
        i = state["intake"]
        a["readiness"] = pl.readiness(
            i["eligible"], i["pa_required"], [c["label"] for c in a["criteria"]]
        )
        return {"assessment": a, "last_decision": decision, "stage": "edited"}

    def n_submit(state: PAState, config) -> dict:
        tid = _tid(config)
        resp = submit_packet(deps.payer, deps.audit, tid, state["packet"], state.get("approval_id"))
        deps.audit.append(
            tid,
            AGENT,
            "system",
            "submitted",
            {
                "submission_id": resp["submission_id"],
                "status": resp["status"],
                "approval_id": state["approval_id"],
            },
        )
        return {"submission": resp, "status_history": [resp], "stage": f"payer_{resp['status']}"}

    def n_track(state: PAState, config) -> dict:
        sub = state["submission"]
        history = list(state.get("status_history", []))
        polls = 0
        while not sub["final"] and polls < deps.max_polls:
            if deps.poll_interval_s:
                time.sleep(deps.poll_interval_s)
            sub = get_status(deps.payer, sub["submission_id"])
            history.append(sub)
            polls += 1
        if (
            sub["status"] != state["submission"]["status"]
            or sub["final"] != state["submission"]["final"]
        ):
            deps.audit.append(
                _tid(config),
                AGENT,
                "system",
                "status_update",
                {
                    "submission_id": sub["submission_id"],
                    "status": sub["status"],
                    "final": sub["final"],
                },
            )
        stage = f"payer_{sub['status']}" + ("" if sub["final"] else "_waiting")
        return {"submission": sub, "status_history": history, "stage": stage}

    def after_intake(state: PAState) -> str:
        return "load_context" if state["stage"] == "intake_done" else END

    def after_review(state: PAState) -> str:
        if state["stage"] == "approved":
            return "submit"
        if state["stage"] == "edited":
            return "build_packet"
        if state["stage"] == "awaiting_review":
            return "human_review"
        return END

    g = StateGraph(PAState)
    g.add_node("intake", n_intake)
    g.add_node("load_context", n_load_context)
    g.add_node("retrieve_policy", n_retrieve)
    g.add_node("extract_evidence", n_extract)
    g.add_node("verify_citations", n_verify)
    g.add_node("assess_criteria", n_assess)
    g.add_node("build_packet", n_build_packet)
    g.add_node("human_review", n_review)
    g.add_node("submit", n_submit)
    g.add_node("track_status", n_track)
    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", after_intake, ["load_context", END])
    g.add_edge("load_context", "retrieve_policy")
    g.add_edge("retrieve_policy", "extract_evidence")
    g.add_edge("extract_evidence", "verify_citations")
    g.add_edge("verify_citations", "assess_criteria")
    g.add_edge("assess_criteria", "build_packet")
    g.add_edge("build_packet", "human_review")
    g.add_conditional_edges(
        "human_review", after_review, ["submit", "build_packet", "human_review", END]
    )
    g.add_edge("submit", "track_status")
    g.add_edge("track_status", END)
    return g.compile(checkpointer=checkpointer)
