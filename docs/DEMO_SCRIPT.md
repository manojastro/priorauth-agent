# Demo script (3 minutes)

> **Synthetic data. Not for clinical use.**

Offline, no Docker needed:
```bash
uv run uvicorn src.workbench.app:app --port 8000
```
1. Open http://localhost:8000, log in as `coord.demo` (pa_coordinator). Click **Run agent** on a
   case. The agent runs intake → retrieval → evidence → verification → assessment → packet and
   stops at human review. Buttons are disabled: coordinators cannot approve.
2. Log out, log in as `reviewer.demo`. Open the run. Show the checklist: each criterion has a
   label, a reason and evidence links. Click a note link: the cited sentence is highlighted.
3. Approve → the packet goes to the mock payer → payer response with pre-auth ref.
4. Run a case with missing documentation → **Reject (request more info)**. No submission.
5. Run a case that does not meet criteria → approve → payer **denied** (ACME-D01).
6. Show the audit trail: run start, intake, refused coordinator decision, overrides with
   before/after, approval, submission, status.
7. Run the prompt-injection case: the injected line is flagged and ignored; no criterion flips.
