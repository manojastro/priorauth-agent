# Limitations

> **Synthetic data. Not for clinical use.**

- All eval numbers so far use an offline keyword heuristic, not an LLM, on templated notes.
- Notes are only searched for note-type criteria; evidence for structured criteria written only
  in free text (e.g. "completed 8 weeks of PT" with no Procedure resource) is not used.
- Single-policy, single-service cases; no red-flag exception handling yet (LSMRI-4.1 etc.).
- HAPI, Postgres retrieval and the live payer service have not been run (no Docker yet).
- FHIR offline validation uses R4B models; HAPI R4 `$validate` not yet run.
- Mock payer is Da Vinci-inspired, not CRD/PAS conformant.
