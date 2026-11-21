# Evals

> **Synthetic data. Not for clinical use.**

Run: `uv run python -m evals.run_all` (add `--live` for HAPI + payer service). Reports land in
`evals/reports/` with date, commit and dirty-worktree flag. Dev (40) and held-out (10) cases are
reported separately; only dev-set errors are listed, and only dev errors were used for fixes.

## Current state (2026-11-16)
- Intake (M2): eligibility and PA-required 50/50. Deterministic code vs generator labels.
- Criteria (M3): offline keyword heuristic, no LLM. First run 0.48 criterion accuracy; after
  retrieval fixes (breadcrumbs, per-document queries, parent expansion) and stemming, 1.0.
  This shows the plumbing works on templated synthetic notes; it says nothing about an LLM.
- Baseline (no retrieval, no verification) equals full pipeline offline: the heuristic never
  fabricates. Value of verification is shown by adversarial unit tests
  (`tests/test_evidence.py`): a compromised model obeying the injection, and a model that
  invents quotes, are both neutralised by `verify_citations`; with verification off, the
  invented quotes flip `missing` criteria to `met`.

## Failure examples seen during development (dev set)
- Generic single query missed criterion sections (no "criteria" words in them) → recall 0.38.
- "improved" vs "improvement" token mismatch hid PT progress notes → fixed with prefix stems.
- Baseline crashed on a note citation with no span → fixed; covered by a test.

## Not yet measured
Real-LLM extraction, unsupported-claim rate, 10-case manual spot check, live HAPI runs.
