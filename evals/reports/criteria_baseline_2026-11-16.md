# Criteria eval — baseline

> **Synthetic data. Not for clinical use.**

- Run at (UTC): 2026-11-16T03:39:48+00:00
- Commit: `ff89033aa2f14ec77b406bca8a2c149ed71b19f3` (dirty worktree: True)
- Data source: offline: data/cases bundles + in-process mock payer

- Extractor: FakeLLM keyword heuristic (offline stand-in, NOT a language model)


| Metric | dev | holdout | all |
|---|---|---|---|
| Criterion accuracy | 1.0 | 1.0 | 1.0 |
| Criterion macro-F1 | 1.0 | 1.0 | 1.0 |
| Missing-info recall | 1.0 | 1.0 | 1.0 |
| Citation faithfulness | 1.0 | 1.0 | 1.0 |
| Readiness accuracy | 1.0 | 1.0 | 1.0 |
| Injection: criteria flipped to met | 0 | 0 | 0 |
| Retrieval recall (criteria) | 1.0 | 1.0 | 1.0 |
| Wall time per case p50 (s) | 0.0064 | 0.0079 | 0.0067 |
| Wall time per case p95 (s) | 0.009 | 0.0087 | 0.0089 |
| LLM calls | 40 | 10 | 50 |
| Prompt tokens | 0 | 0 | 0 |
| Estimated cost (USD) | 0.0 | 0.0 | 0.0 |

## Criterion errors, dev set only (0)

