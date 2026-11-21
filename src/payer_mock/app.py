"""Mock payer service (Acme Health Plan). Synthetic data. Not for clinical use.

Da Vinci CRD/PAS-*inspired* only; not a certified or conformant implementation.
Run: uv run uvicorn src.payer_mock.app:app --port 8090
"""

from fastapi import FastAPI, Header, HTTPException

from src.common.config import SYNTHETIC_BANNER
from src.payer_mock import pas
from src.payer_mock.crd import CrdRequest, CrdResponse, check

app = FastAPI(
    title="Acme Health Plan mock payer",
    description=f"{SYNTHETIC_BANNER} Da Vinci-inspired mock; not a certified implementation.",
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "banner": SYNTHETIC_BANNER}


@app.post("/crd/check", response_model=CrdResponse)
def crd_check(req: CrdRequest) -> CrdResponse:
    return check(req)


@app.post("/pas/submit", response_model=pas.PasDecision)
def pas_submit(bundle: dict, x_reviewer_approval: str = Header(default="")) -> pas.PasDecision:
    try:
        return pas.decide(bundle, x_reviewer_approval)
    except pas.SubmissionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/pas/status/{submission_id}", response_model=pas.PasDecision)
def pas_status(submission_id: str) -> pas.PasDecision:
    d = pas.status(submission_id)
    if d is None:
        raise HTTPException(status_code=404, detail="unknown submission")
    return d


@app.get("/pas/submissions", response_model=list[pas.PasDecision])
def pas_submissions() -> list[pas.PasDecision]:
    """Mock-only audit view used by evals (approval-gate invariant)."""
    return list(pas.STORE.submissions.values())
