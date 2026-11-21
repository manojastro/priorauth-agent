---
policy_id: ACME-POL-RABIO
version: "2026.1"
title: Biologic therapy for rheumatoid arthritis (step therapy)
services:
  - code: SVC-RA-BIO
    display: Biologic DMARD for rheumatoid arthritis
pa_required: {HMO: true, PPO: true, EPO: true}
criteria:
  - id: RABIO-2.1
    kind: condition
    codes: [M06.9, M05.79]
    non_qualifying_codes: [M19.90]
    window_days: 365
  - id: RABIO-2.2
    kind: medication_trial
    rxnorm:
      - {code: "6851", display: methotrexate}
    min_days: 84
    window_days: 365
  - id: RABIO-2.3
    kind: observation_result
    code: TB-SCREEN
    display: Tuberculosis screening result
    met_value: negative
    not_met_value: positive
    window_days: 365
  - id: RABIO-2.4
    kind: note
    window_days: 90
---
# Acme Health Plan medical policy: Biologic for rheumatoid arthritis

> Synthetic policy written for a demo. Not a real payer policy. Not for clinical use.

## RABIO-1 Scope
This policy covers biologic disease-modifying therapy for rheumatoid arthritis (internal service code SVC-RA-BIO). It is a step-therapy policy.

## RABIO-2 Coverage criteria
All of the criteria below must be documented.

### RABIO-2.1 Qualifying diagnosis
A documented diagnosis of rheumatoid arthritis (ICD-10-CM M06.9 or M05.79) within the last 12 months. Osteoarthritis (M19.90) does not qualify.

### RABIO-2.2 Conventional therapy first (step therapy)
A documented trial of methotrexate for at least 12 weeks (84 days) within the last 12 months.

### RABIO-2.3 Tuberculosis screening
A negative tuberculosis screening result within the last 12 months.

### RABIO-2.4 Disease activity
A clinical note from the last 90 days documents moderate or high disease activity despite conventional therapy.

## RABIO-3 Exclusions
### RABIO-3.1 Combination biologics
Use of two biologic agents at the same time is not covered.

## RABIO-4 Red-flag exceptions
### RABIO-4.1 Methotrexate contraindication
A documented contraindication to methotrexate waives RABIO-2.2.

## RABIO-5 Required documentation
### RABIO-5.1 Documents to submit
Diagnosis, medication history with dates, TB screening result and the most recent clinical note.

## RABIO-6 Prior authorization by plan type
### RABIO-6.1 Plan rules
Prior authorization is required for HMO, PPO and EPO plans.
