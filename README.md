# priorauth-agent

> **Synthetic data. Not for clinical use.**

Staff-facing agent that prepares prior-authorization packets with cited evidence from a FHIR R4
record and synthetic payer policies. **A human `pa_reviewer` approves every submission.**
The agent never makes clinical decisions. The mock payer is Da Vinci-*inspired* (CRD/PAS ideas)
and is **not** a certified or conformant implementation. No HIPAA compliance is claimed.

Status: M0 skeleton (see `PROGRESS.md`). No eval numbers yet.

## Quickstart (local)
```bash
cp .env.example .env
docker compose up -d
uv run python -m scripts.check_services --wait 180
uv run pytest
```
