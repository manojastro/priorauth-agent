---
policy_id: ACME-POL-PTX
version: "2026.1"
title: Outpatient physical therapy beyond 12 visits
services:
  - code: SVC-PT-EXT
    display: Additional outpatient physical therapy visits (beyond 12)
pa_required: {HMO: true, PPO: false, EPO: true}
criteria:
  - id: PTX-2.1
    kind: condition
    codes: [M54.50, M17.11, M25.561]
    non_qualifying_codes: [R53.83]
    window_days: 365
  - id: PTX-2.2
    kind: procedure_count
    code: PT-VISIT
    display: Physical therapy visit
    min_count: 12
    window_days: 120
  - id: PTX-2.3
    kind: note
    window_days: 30
---
# Acme Health Plan medical policy: Physical therapy beyond 12 visits

> Synthetic policy written for a demo. Not a real payer policy. Not for clinical use.

## PTX-1 Scope
This policy covers outpatient physical therapy visits after the first 12 visits in a plan year (internal service code SVC-PT-EXT).

## PTX-2 Coverage criteria
All of the criteria below must be documented.

### PTX-2.1 Qualifying diagnosis
A documented musculoskeletal diagnosis (ICD-10-CM M54.50, M17.11 or M25.561) within the last 12 months. General fatigue (R53.83) does not qualify.

### PTX-2.2 Initial visits completed
At least 12 physical therapy visits completed within the last 120 days.

### PTX-2.3 Measurable improvement
A therapy or clinical note from the last 30 days documents measurable functional improvement and a reason to continue.

## PTX-3 Exclusions
### PTX-3.1 Maintenance therapy
Maintenance therapy with no expected further improvement is not covered.

## PTX-4 Red-flag exceptions
### PTX-4.1 Post-surgical
Therapy within 90 days after joint replacement is reviewed under the surgical policy.

## PTX-5 Required documentation
### PTX-5.1 Documents to submit
Diagnosis, visit log and the most recent progress note.

## PTX-6 Prior authorization by plan type
### PTX-6.1 Plan rules
Prior authorization is required for HMO and EPO plans. It is not required for PPO plans.
