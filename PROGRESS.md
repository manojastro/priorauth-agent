# PROGRESS

> **Synthetic data. Not for clinical use.**

Status labels: `planned` · `built` · `tested` · `evaluated` · `deployed`

## M0 — Skeleton (2026-11-14)

| Item | Status | Notes |
|---|---|---|
| Repo layout (§4), uv project, Python 3.12 | built | `git init` local only, nothing committed or pushed |
| ruff + pytest tooling | tested | `ruff check` clean; `pytest`: 16 passed, 3 skipped (integration) |
| `src/common/config.py` (pydantic-settings, SecretStr) | tested | secrets hidden from repr (test) |
| `src/common/telemetry.py` | planned | stub; exporter wiring in M3 |
| `docker-compose.yml` (HAPI, Postgres+pgvector, Jaeger) | built | **not yet run: Docker not installed on this machine** |
| `scripts/check_services.py` + integration tests | built | skip when stack is down; unverified against a live stack |
| `.env.example`, `.gitignore`, `CLAUDE.md`, docs stubs, README banner | built | |

**M0 acceptance**
- pytest passes: ✅ (16 passed, 3 integration skipped)
- `docker compose up` healthy: ❌ not verified — Docker Desktop is not installed.

## Environment
- Java: Temurin 21.0.13 LTS installed via winget 2026-11-14 (for Synthea in M1). Verified with `java -version`; new terminals pick up PATH.
- Docker Desktop (WSL2): **missing**. Required for M0 acceptance and all of M1's HAPI steps.

## M1 — Synthetic data (2026-11-14, code-only by request; services/deploy later)

| Item | Status | Notes |
|---|---|---|
| 8 policies `data/policies/*.md` + loader `src/policies/loader.py` | tested | stable section IDs, snapshot test; no CPT text |
| `scripts/build_cases.py` (50 cases + ground truth, 10 held-out) | tested | mix 20/15/10/5; byte-identical across runs; all resources parse as FHIR R4B |
| `src/common/fhir_client.py` (read/search/transaction/$validate) | built | not run against HAPI |
| `scripts/generate_patients.py` (Synthea v3.3.0, seed 20261114) | built | jar not downloaded; not run |
| `scripts/seed_coverage.py` | tested | on fake Synthea bundles only |
| `scripts/load_fhir.py` (ordered load, optional `$validate`) | built | not run; needs HAPI |

Tests: `pytest` 254 passed, 3 skipped (integration). `ruff check` clean.

**M1 acceptance**
- `build_cases.py` reproducible from seed: ✅ (test compares bytes of two runs)
- HAPI returns patients, coverages, case resources: ❌ not verified (no Docker)
- Cases validated against HAPI `$validate`: ❌ not verified; offline R4B validation passes

## M2 — Phase 1 intake + mock payer CRD (2026-11-16, code-only)

| Item | Status | Notes |
|---|---|---|
| Mock payer `POST /crd/check` (`src/payer_mock/`) | tested | rule table built from policy files; run: `uv run uvicorn src.payer_mock.app:app --port 8090` |
| Eligibility check (`src/intake/eligibility.py`) | tested | deterministic; reasons: status, date window, plan type, member id, payer |
| Intake service (`src/intake/service.py`) | tested | SR → coverage → eligibility → CRD → summary with banner |
| FHIR sources (`src/common/fhir_source.py`) | tested | `HapiSource` (live, tested with mock transport only) and `BundleSource` (offline) |
| Intake eval + `evals.run_all` | evaluated | report: `evals/reports/intake_2026-11-16.md` |

Tests: `pytest` 327 passed, 3 skipped (integration). `ruff check` clean.

**M2 acceptance** — eligibility and PA-required accuracy reported on all 50 cases: ✅
(from `evals/reports/intake_2026-11-16.json`, commit `uncommitted`, offline data source).
Eligibility 50/50, PA-required 50/50 (dev 40/40, holdout 10/10).
Caveat: this is deterministic code scored against labels from the same synthetic generator,
and the set has only 1 terminated-coverage and 1 no-PA case, so 100% is expected and says little.
Not yet run against live HAPI (`--live`).

## M3 — Retrieval + evidence extraction + citation verification (2026-11-16, code-only)

| Item | Status | Notes |
|---|---|---|
| LLM interface `src/common/llm.py` (Azure, OpenAI-compatible, FakeLLM, usage ledger) | tested | real providers built but **not called** (no keys); cost = unknown unless prices set in `.env` |
| Chunker + `InMemoryHybridRetriever` (BM25 + cosine, RRF) | evaluated | breadcrumbs + one query per CRD document + parent expansion |
| `PgHybridRetriever` (pgvector + FTS, RRF in SQL) | built | not run; needs Postgres |
| Structured evidence finder + assessment (`src/priorauth/structured.py`) | evaluated | deterministic |
| Note extraction (`src/priorauth/notes.py`), injection flags | evaluated | offline with keyword heuristic only |
| `verify_citations` (`src/priorauth/verify.py`) | tested | value/span re-check, patient match, rejects instruction-like quotes |
| Pipeline `src/priorauth/pipeline.py` | evaluated | plain functions; LangGraph wrapping in M4 |
| `evals.runners.criteria_eval` + baseline, `evals.run_all` | evaluated | reports `evals/reports/criteria_2026-11-16.*`, `criteria_baseline_2026-11-16.*`, `summary_2026-11-16.*` |

Tests: `pytest` 366 passed, 3 skipped (integration). `ruff check` clean.

**M3 acceptance** — first eval report with criterion accuracy and citation faithfulness: ✅;
injection cases handled: ✅ (0 criteria flipped to met; adversarial unit tests with a
"compromised" and a "lying" fake model pass).
Numbers (report `criteria_2026-11-16.json`, base commit ff89033, dirty worktree, offline):
criterion accuracy 1.0 dev / 1.0 holdout, citation faithfulness 1.0 / 1.0.
**These numbers are not meaningful about an LLM.** The extractor was the offline keyword
heuristic (no model), tuned on dev errors against templated synthetic notes. Baseline equals
full pipeline offline because the heuristic never fabricates quotes. A real-model run
(`LLM_PROVIDER=azure|openai`) is needed before any claim. Before tuning, the first run scored
criterion accuracy 0.48 (retrieval recall 0.38); fixes were made from dev-set errors only.

## M4 — Packet, human review, submission, status (2026-11-16, code-only)

| Item | Status | Notes |
|---|---|---|
| LangGraph graph (`src/priorauth/graph.py`), 10 nodes, `interrupt()` review | tested | LangGraph 1.2.22 |
| Checkpointing (`src/priorauth/service.py`) | tested | SQLite file locally; Postgres saver wired, **not run** |
| Packet builder: Bundle + Claim(use=preauthorization) + cover narrative | tested | offline R4B validation; HAPI `$validate` not run |
| Approval gate (`src/priorauth/payer_client.py`) | tested | approval read from audit store; role, thread and payload hash must match |
| Audit store (`src/common/audit.py`) with override before/after | tested | SQLite; Postgres backend not built yet |
| Mock payer `POST /pas/submit`, `GET /pas/status/{id}` | tested | deterministic re-check of attached evidence; optional random pend |
| Workbench (`src/workbench/`) Jinja2 + HTMX, login stub | tested | also checked by hand in a browser: login, run, evidence highlight, approve → payer approved |

Tests: `pytest` 389 passed, 3 skipped (integration). `ruff check` clean.

**M4 acceptance**
- End-to-end demo for 3 cases (approved / needs more info / denied): ✅ `test_demo_three_outcomes`
- Approval-gate invariant tests: ✅ coordinator refused, forged/foreign/stale approvals rejected,
  payer refuses missing approval header, static check that only `payer_client` posts to PAS,
  every payer submission maps to a pa_reviewer approval event.
- Restart mid-review still works: ✅ `test_restart_mid_review_resumes_from_checkpoint`
  (SQLite checkpointer; Postgres checkpointer not exercised without Docker).
