"""Reviewer workbench (FastAPI + Jinja2 + HTMX). Synthetic data. Not for clinical use.

Run (offline, no docker needed): uv run uvicorn src.workbench.app:app --port 8000
Login is a stub (pick a demo user); production would use the organisation's SSO.
Roles are enforced server-side: only pa_reviewer can approve, edit or reject.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from src.common.audit import AuditStore
from src.common.config import SYNTHETIC_BANNER
from src.common.fhir_source import BundleSource, NotFound
from src.common.llm import get_llm
from src.common.roles import DEMO_USERS, PA_REVIEWER
from src.payer_mock.app import app as payer_app
from src.priorauth.graph import Deps
from src.priorauth.payer_client import get_status
from src.priorauth.service import RUNTIME, PAService, open_checkpointer

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.globals["BANNER"] = SYNTHETIC_BANNER
CASES = Path(__file__).resolve().parents[2] / "data" / "cases" / "bundles"


@contextmanager
def default_service():
    """Offline wiring: case bundles from disk, mock payer in-process, SQLite state."""
    from fastapi.testclient import TestClient

    audit = AuditStore(RUNTIME / "audit.sqlite")
    with TestClient(payer_app) as payer, open_checkpointer() as cp:
        deps = Deps(src=BundleSource(), llm=get_llm(), payer=payer, audit=audit)
        yield PAService(deps, cp)
    audit.close()


def queue_rows() -> list[dict]:
    """Case list from the ServiceRequests on disk. Ground-truth labels are never shown."""
    rows = []
    for f in sorted(CASES.glob("pa-case-*.json")):
        b = json.loads(f.read_text(encoding="utf-8"))
        sr = next(
            e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "ServiceRequest"
        )
        rows.append(
            {
                "case_id": f.stem,
                "service_request_id": sr["id"],
                "service": sr["code"]["text"],
                "date": sr.get("occurrenceDateTime", ""),
            }
        )
    return rows


def create_app(service_factory=default_service) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with service_factory() as svc:
            app.state.svc = svc
            yield

    app = FastAPI(title="Prior-auth reviewer workbench", lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.getenv("WORKBENCH_SESSION_SECRET") or secrets.token_hex(32),
        same_site="lax",
    )

    def user(request: Request) -> dict | None:
        u = request.session.get("user")
        return {"name": u, "role": DEMO_USERS[u]} if u in DEMO_USERS else None

    def need_user(request: Request) -> dict:
        u = user(request)
        if not u:
            raise HTTPException(status_code=401, detail="login required")
        return u

    def render(request: Request, name: str, **ctx):
        return TEMPLATES.TemplateResponse(request, name, {"user": user(request), **ctx})

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return render(request, "login.html", users=DEMO_USERS)

    @app.post("/login")
    def login(request: Request, username: str = Form(...)):
        if username not in DEMO_USERS:
            raise HTTPException(status_code=400, detail="unknown demo user")
        request.session["user"] = username
        return RedirectResponse("/", status_code=303)

    @app.get("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    def queue(request: Request):
        if not user(request):
            return RedirectResponse("/login", status_code=303)
        svc: PAService = request.app.state.svc
        threads = []
        for t in reversed(svc.threads()):
            st = svc.state(t["thread_id"])["values"]
            threads.append({**t, "stage": st.get("stage", "?")})
        return render(request, "queue.html", cases=queue_rows(), threads=threads)

    @app.post("/cases/start")
    def start(request: Request, service_request_id: str = Form(...), case_id: str = Form("")):
        u = need_user(request)
        tid = request.app.state.svc.start(service_request_id, u["name"], u["role"], case_id)
        return RedirectResponse(f"/threads/{tid}", status_code=303)

    @app.get("/threads/{tid}", response_class=HTMLResponse)
    def case_page(request: Request, tid: str):
        if not user(request):
            return RedirectResponse("/login", status_code=303)
        svc: PAService = request.app.state.svc
        st = svc.state(tid)
        v = st["values"]
        if not v:
            raise HTTPException(status_code=404, detail="unknown case")
        patient = None
        if v.get("intake", {}).get("patient_id"):
            try:
                patient = svc.deps.src.read("Patient", v["intake"]["patient_id"])
            except NotFound:
                patient = None
        return render(
            request,
            "case.html",
            tid=tid,
            v=v,
            pending=st["pending_review"],
            patient=patient,
            audit=svc.deps.audit.for_thread(tid),
            is_reviewer=user(request)["role"] == PA_REVIEWER,
            packet_json=json.dumps(v.get("packet"), indent=2) if v.get("packet") else "",
        )

    @app.post("/threads/{tid}/decision")
    async def decision(request: Request, tid: str):
        u = need_user(request)
        form = await request.form()
        overrides = {}
        for k, val in form.items():
            if k.startswith("override_label_") and val:
                cid = k.removeprefix("override_label_")
                overrides[cid] = {"label": val, "reason": form.get(f"override_reason_{cid}", "")}
        d = {
            "action": form.get("action"),
            "user": u["name"],
            "role": u["role"],  # from the session, never from the form
            "comment": form.get("comment", ""),
            "overrides": overrides,
        }
        request.app.state.svc.decide(tid, d)
        return RedirectResponse(f"/threads/{tid}", status_code=303)

    @app.post("/threads/{tid}/poll", response_class=HTMLResponse)
    def poll(request: Request, tid: str):
        u = need_user(request)
        svc: PAService = request.app.state.svc
        sub = svc.state(tid)["values"].get("submission")
        if not sub:
            raise HTTPException(status_code=404, detail="no submission")
        cur = get_status(svc.deps.payer, sub["submission_id"])
        svc.deps.audit.append(
            tid,
            u["name"],
            u["role"],
            "status_polled",
            {"status": cur["status"], "final": cur["final"]},
        )
        return render(request, "_status.html", sub=cur, tid=tid)

    @app.get("/evidence/{rtype}/{rid}", response_class=HTMLResponse)
    def evidence(request: Request, rtype: str, rid: str, start: int = -1, end: int = -1):
        need_user(request)
        try:
            res = request.app.state.svc.deps.src.read(rtype, rid)
        except NotFound as e:
            raise HTTPException(status_code=404, detail="not found") from e
        ctx = {"rtype": rtype, "rid": rid, "json": json.dumps(res, indent=2)}
        if rtype == "DocumentReference":
            data = res["content"][0]["attachment"].get("data", "")
            text = base64.b64decode(data).decode("utf-8") if data else ""
            ok = 0 <= start < end <= len(text)
            ctx |= {
                "before": text[:start] if ok else text,
                "hit": text[start:end] if ok else "",
                "after": text[end:] if ok else "",
            }
        return render(request, "_evidence.html", **ctx)

    return app


app = create_app()
