---
policy_id: ACME-POL-BARI
version: "2026.1"
title: Bariatric surgery
services:
  - code: SVC-BARIATRIC
    display: Bariatric surgery
pa_required: {HMO: true, PPO: true, EPO: true}
criteria:
  - id: BARI-2.1
    kind: observation_threshold
    code: "39156-5"
    system: http://loinc.org
    display: Body mass index
    value_type: quantity
    unit: kg/m2
    op: ">="
    value: 40
    window_days: 365
  - id: BARI-2.2
    kind: procedure_duration
    code: WT-PROGRAM
    display: Supervised weight management program
    min_days: 180
    window_days: 730
  - id: BARI-2.3
    kind: procedure_done
    code: PSYCH-EVAL
    display: Pre-surgical psychological evaluation
    window_days: 365
  - id: BARI-2.4
    kind: note
    window_days: 180
---
# Acme Health Plan medical policy: Bariatric surgery

> Synthetic policy written for a demo. Not a real payer policy. Not for clinical use.

## BARI-1 Scope
This policy covers bariatric surgery for adult members (internal service code SVC-BARIATRIC).

## BARI-2 Coverage criteria
All of the criteria below must be documented.

### BARI-2.1 Body mass index
A body mass index of 40 kg/m2 or higher recorded within the last 12 months.

### BARI-2.2 Supervised weight program
Participation in a supervised weight management program for at least 6 months (180 days) within the last 24 months.

### BARI-2.3 Psychological evaluation
A pre-surgical psychological evaluation completed within the last 12 months.

### BARI-2.4 Nutrition counseling
A clinical note from the last 180 days documents completed nutrition counseling.

## BARI-3 Exclusions
### BARI-3.1 Age
Members under 18 are reviewed under a separate policy.

## BARI-4 Red-flag exceptions
### BARI-4.1 None
There are no red-flag exceptions.

## BARI-5 Required documentation
### BARI-5.1 Documents to submit
BMI record, program records, psychological evaluation record and the counseling note.

## BARI-6 Prior authorization by plan type
### BARI-6.1 Plan rules
Prior authorization is required for HMO, PPO and EPO plans.
