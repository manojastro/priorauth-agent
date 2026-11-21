---
policy_id: ACME-POL-TKA
version: "2026.1"
title: Total knee arthroplasty
services:
  - code: SVC-TKA
    display: Total knee arthroplasty
pa_required: {HMO: true, PPO: true, EPO: true}
criteria:
  - id: TKA-2.1
    kind: condition
    codes: [M17.0, M17.11, M17.12]
    non_qualifying_codes: [M25.561]
    window_days: 730
  - id: TKA-2.2
    kind: observation_threshold
    code: KL-GRADE
    display: Kellgren-Lawrence radiographic grade
    value_type: integer
    op: ">="
    value: 3
    window_days: 365
  - id: TKA-2.3
    kind: procedure_duration
    code: PT-COURSE
    display: Physical therapy course
    min_days: 84
    window_days: 365
  - id: TKA-2.4
    kind: observation_threshold
    code: "39156-5"
    system: http://loinc.org
    display: Body mass index
    value_type: quantity
    unit: kg/m2
    op: "<"
    value: 40
    window_days: 90
  - id: TKA-2.5
    kind: note
    window_days: 90
---
# Acme Health Plan medical policy: Total knee arthroplasty

> Synthetic policy written for a demo. Not a real payer policy. Not for clinical use.

## TKA-1 Scope
This policy covers elective total knee arthroplasty (internal service code SVC-TKA).

## TKA-2 Coverage criteria
All of the criteria below must be documented.

### TKA-2.1 Qualifying diagnosis
A documented diagnosis of primary osteoarthritis of the knee (ICD-10-CM M17.0, M17.11 or M17.12) within the last 24 months. Knee pain without an osteoarthritis diagnosis (M25.561) does not qualify.

### TKA-2.2 Radiographic severity
A recorded Kellgren-Lawrence grade of 3 or higher within the last 12 months.

### TKA-2.3 Conservative therapy
At least 12 weeks (84 days) of documented conservative therapy within the last 12 months.

### TKA-2.4 Body mass index
A body mass index below 40 kg/m2 recorded within the 90 days before the request.

### TKA-2.5 Functional limitation
A clinical note from the last 90 days documents a functional limitation that affects activities of daily living.

## TKA-3 Exclusions
### TKA-3.1 Active infection
Active joint infection is an exclusion.

## TKA-4 Red-flag exceptions
### TKA-4.1 None
There are no red-flag exceptions for this elective procedure.

## TKA-5 Required documentation
### TKA-5.1 Documents to submit
Diagnosis, radiographic grade, therapy records, recent BMI and the most recent clinical note.

## TKA-6 Prior authorization by plan type
### TKA-6.1 Plan rules
Prior authorization is required for HMO, PPO and EPO plans.
