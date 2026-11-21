"""M3 eval: criterion accuracy + macro-F1, missing-info recall, citation faithfulness,
readiness accuracy, injection resistance, retrieval recall, latency. Dev and holdout separately.

Usage: uv run python -m evals.runners.criteria_eval [--live] [--baseline]
Default: offline case bundles + LLM_PROVIDER from .env (default "fake" = keyword heuristic,
NOT a language model; the report says which). --baseline turns off retrieval and verification.
"""

from __future__ import annotations

import argparse
import statistics
import time

import httpx
from fastapi.testclient import TestClient

from evals.common import SPLITS, load_ground_truth, meta_block, run_metadata, write_report
from src.common.config import get_settings
from src.common.fhir_source import BundleSource, FhirSource, HapiSource
from src.common.llm import LLM, get_llm
from src.intake.service import run_intake
from src.payer_mock.app import app as payer_app
from src.policies.loader import load_policies
from src.priorauth.pipeline import run_assessment

LABELS = ("met", "not_met", "missing")


class AllCriteriaRetriever:
    """Baseline: no retrieval, every policy section returned."""

    def search(self, query, policy_id=None, k=10):
        from src.policies.retriever import Hit, chunk_policy

        p = load_policies()[policy_id]
        return [Hit(chunk=c, score=0, vector_rank=None, lexical_rank=None) for c in chunk_policy(p)]


def macro_f1(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    f1s = []
    for lab in LABELS:
        tp = sum(1 for g, w in pairs if g == lab and w == lab)
        fp = sum(1 for g, w in pairs if g == lab and w != lab)
        fn = sum(1 for g, w in pairs if g != lab and w == lab)
        if tp + fp + fn == 0:
            continue
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * p * r / (p + r) if p + r else 0.0)
    return round(sum(f1s) / len(f1s), 4)


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 4)
    return round(statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1], 4)


def evaluate(src: FhirSource, payer, llm: LLM, gts: list[dict], baseline: bool) -> dict:
    rows = []
    for g in gts:
        t0 = time.perf_counter()
        intake = run_intake(src, payer, g["service_request_id"])
        a = run_assessment(
            src, llm, intake,
            retriever=AllCriteriaRetriever() if baseline else None,
            verify=not baseline,
        )  # fmt: skip
        wall = time.perf_counter() - t0
        exp = g["expected"]["criteria"]
        got = {c.criterion_id: c for c in a.criteria}
        rows.append(
            {
                "case_id": g["case_id"],
                "split": g["split"],
                "category": g["category"],
                "tricky_kind": g["tricky_kind"],
                "has_injection": g["has_injection"],
                "criteria": [
                    {
                        "id": cid,
                        "got": got[cid].label,
                        "want": e["label"],
                        "reason": got[cid].reason,
                    }
                    for cid, e in exp.items()
                ],
                "readiness": [a.readiness, g["expected"]["readiness"]],
                "citations_total": a.citations_total,
                "citations_verified": a.citations_verified,
                "retrieval_missing": a.missing_from_retrieval,
                "n_criteria": len(exp),
                "injection_flags": a.injection_flags,
                "wall_s": round(wall, 4),
                "llm": a.llm_usage,
            }
        )
    return {"metrics": {s: metrics(rows, s) for s in (*SPLITS, "all")}, "rows": rows}


def metrics(rows: list[dict], split: str) -> dict:
    sel = [r for r in rows if split == "all" or r["split"] == split]
    pairs = [(c["got"], c["want"]) for r in sel for c in r["criteria"]]
    missing = [p for p in pairs if p[1] == "missing"]
    ready = [tuple(r["readiness"]) for r in sel if r["readiness"][1] is not None]
    inj = [c for r in sel if r["has_injection"] for c in r["criteria"]]
    walls = [r["wall_s"] for r in sel]
    return {
        "n_cases": len(sel),
        "n_criteria": len(pairs),
        "criterion_accuracy": _ratio(sum(g == w for g, w in pairs), len(pairs)),
        "criterion_macro_f1": macro_f1(pairs),
        "missing_recall": _ratio(sum(g == "missing" for g, _ in missing), len(missing)),
        "citation_faithfulness": _ratio(
            sum(r["citations_verified"] for r in sel), sum(r["citations_total"] for r in sel)
        ),
        "readiness_accuracy": _ratio(sum(g == w for g, w in ready), len(ready)),
        "injection_cases": sum(1 for r in sel if r["has_injection"]),
        "injection_false_met": sum(1 for c in inj if c["got"] == "met" and c["want"] != "met"),
        "retrieval_recall": _ratio(
            sum(r["n_criteria"] - len(r["retrieval_missing"]) for r in sel),
            sum(r["n_criteria"] for r in sel),
        ),
        "wall_s_p50": _pct(walls, 50),
        "wall_s_p95": _pct(walls, 95),
        "llm_calls": sum(r["llm"]["calls"] for r in sel),
        "prompt_tokens": sum(r["llm"]["prompt_tokens"] for r in sel),
        "completion_tokens": sum(r["llm"]["completion_tokens"] for r in sel),
        "cost_usd": None
        if any(r["llm"]["cost_usd"] is None for r in sel)
        else round(sum(r["llm"]["cost_usd"] for r in sel), 6),
    }


NAMES = {
    "criterion_accuracy": "Criterion accuracy",
    "criterion_macro_f1": "Criterion macro-F1",
    "missing_recall": "Missing-info recall",
    "citation_faithfulness": "Citation faithfulness",
    "readiness_accuracy": "Readiness accuracy",
    "injection_false_met": "Injection: criteria flipped to met",
    "retrieval_recall": "Retrieval recall (criteria)",
    "wall_s_p50": "Wall time per case p50 (s)",
    "wall_s_p95": "Wall time per case p95 (s)",
    "llm_calls": "LLM calls",
    "prompt_tokens": "Prompt tokens",
    "cost_usd": "Estimated cost (USD)",
}


def to_markdown(meta: dict, res: dict, title: str) -> str:
    out = [f"# {title}\n", meta_block(meta), f"- Extractor: {meta['extractor']}\n", ""]
    out += ["| Metric | dev | holdout | all |", "|---|---|---|---|"]
    for k, label in NAMES.items():
        cells = [res["metrics"][s][k] for s in (*SPLITS, "all")]
        out.append(
            f"| {label} | " + " | ".join("n/a" if c is None else str(c) for c in cells) + " |"
        )
    out.append("")
    wrong = [
        (r["case_id"], r["category"], r["tricky_kind"], c)
        for r in res["rows"]
        if r["split"] == "dev"  # never list holdout failures: we must not tune on them
        for c in r["criteria"]
        if c["got"] != c["want"]
    ]
    out.append(f"## Criterion errors, dev set only ({len(wrong)})\n")
    for cid, cat, tk, c in wrong:
        out.append(
            f"- `{cid}` {cat}/{tk} {c['id']}: got **{c['got']}**, "
            f"want **{c['want']}** — {c['reason']}"
        )
    return "\n".join(out) + "\n"


def run(live: bool = False, baseline: bool = False) -> dict:
    gts = load_ground_truth()
    settings = get_settings()
    llm = get_llm(settings)
    if live:
        src: FhirSource = HapiSource()
        payer = httpx.Client(base_url=settings.payer_mock_url, timeout=30)
        source = "live HAPI + mock payer service"
    else:
        src, payer = BundleSource(), TestClient(payer_app)
        source = "offline: data/cases bundles + in-process mock payer"
    with payer:
        res = evaluate(src, payer, llm, gts, baseline)
    meta = run_metadata(source)
    meta["extractor"] = (
        "FakeLLM keyword heuristic (offline stand-in, NOT a language model)"
        if llm.name == "fake"
        else f"{llm.name} model {getattr(llm, 'chat_model', '?')}"
    )
    meta["mode"] = "baseline (no retrieval, no verification)" if baseline else "full pipeline"
    payload = {"meta": meta, **res}
    name = "criteria_baseline" if baseline else "criteria"
    title = "Criteria eval — baseline" if baseline else "Criteria eval (M3)"
    j, m = write_report(name, payload, to_markdown(meta, res, title))
    print(f"wrote {j} and {m}")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    a = ap.parse_args()
    run(a.live, a.baseline)


if __name__ == "__main__":
    main()
