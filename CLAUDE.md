# CLAUDE.md — Prior-Authorization Agent (synthetic data only)

Source of truth for scope: `BUILD_SPEC.md`. If anything is unclear or conflicts with current library/standard behaviour, ask Manoj. Do not guess.

## Working rules

1. **Plan first.** Start in plan mode. Propose the plan for the current milestone only, then wait for "go". Re-plan at the start of every milestone.
2. **Milestone by milestone.** At the end of each milestone, run lint, unit tests and that milestone's acceptance checks. Update `PROGRESS.md`, then stop and show results.
3. **Status honesty.** Label every feature `planned`, `built`, `tested`, `evaluated` or `deployed`. Never write a metric you did not measure. Eval numbers come only from eval runner output files, with date and commit.
4. **Never without an explicit "yes" in chat:**
   - create or change cloud resources (including Azure Health Data Services, which is **paid**), or run any deployment
   - `git push`, or open a remote PR
   - spend money
5. **Synthetic data only.** No real patient data. No MIMIC or other credentialed datasets. Every UI page and report shows the banner: "Synthetic data. Not for clinical use."
6. **No clinical advice.** The agent only compares documented evidence against written policy criteria and reports met / not met / missing, with citations. No diagnosis or treatment suggestions.
7. **Secrets.** Keep in `.env` (gitignored); commit `.env.example`. Never print or commit secrets.
8. **Verify, don't guess.** Check installed library versions and docs before use. FHIR resource fields must match FHIR R4. Validate generated resources against the HAPI server; don't invent fields.
9. **Local-first and cheap.** Everything runs with `docker compose up` on Windows 11 (Docker Desktop + WSL2) and Ubuntu. Locally use the free HAPI FHIR server, not paid Azure FHIR.
10. **Tests.** Use pytest. Never weaken or delete tests to make them pass.
11. **Licensing care.** Use ICD-10-CM codes (public). Do **not** embed CPT descriptor text (AMA copyright). Use internal service codes such as `SVC-MRI-LSPINE`, optionally mapped to public HCPCS Level II codes.
12. **Deterministic where it matters.** Coverage lookups, mock payer decision logic, schema validation and the "no submit without approval" gate are plain code. The LLM extracts evidence from free-text notes, maps evidence to criteria, and drafts text.
13. **If stuck after 2 attempts**, stop and explain.

Also (from user's global config): no human-less submission, ever; a human `pa_reviewer` approves every submission.

## Tech stack (pin latest stable versions; record in `docs/DECISIONS.md`)

| Area | Choice |
|---|---|
| Language / tooling | Python 3.12, `uv`, `ruff`, `pytest` |
| API / UI | FastAPI, Pydantic v2, Jinja2 + HTMX reviewer workbench (no React) |
| FHIR server (local) | HAPI FHIR JPA server in Docker (`hapiproject/hapi`), FHIR R4 |
| FHIR client | `httpx` + `fhir.resources` (or `fhirclient`); pick one, record the choice |
| Synthetic patients | Synthea (Java 17+ or per its README), ~100 patients, fixed seed, FHIR R4 bundles |
| Agent | LangGraph + `langgraph-checkpoint-postgres`, `interrupt()` for reviewer approval |
| Database | PostgreSQL 16 + pgvector (Docker): agent state, cases, audit, policy chunks + embeddings |
| Retrieval | Hybrid: pgvector cosine + Postgres FTS, merged by reciprocal rank fusion; chunk policies by criterion, keep section IDs |
| LLM | Provider interface `src/common/llm.py`. Azure OpenAI primary (`AZURE_OPENAI_*`, incl. embeddings deployment); OpenAI-compatible secondary (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODEL`, `EMBED_MODEL`); `FakeLLM` for offline tests. Log tokens and cost per call. Structured outputs (JSON schema) for every extraction step |
| Mock payer | Separate FastAPI service, Da Vinci-inspired (CRD/PAS ideas). **Not** a certified implementation; README says so |
| MCP (optional) | FHIR read tools as an MCP server |
| Observability | OpenTelemetry → Jaeger locally; `azure-monitor-opentelemetry` behind a flag |
| OCR (optional, M8) | Azure AI Document Intelligence `prebuilt-healthInsuranceCard.us`; check free tier and ask first |
| Azure IaC (written, not deployed) | Bicep: Container Apps, PostgreSQL Flexible Server (pgvector), Key Vault, Log Analytics + App Insights, optional paid Azure Health Data Services FHIR |

## Do-not-build

No patient-facing chat, diagnosis/treatment suggestions or symptom checker. No claims of HIPAA compliance or Da Vinci conformance. No auto-submission. No real payer integrations.
