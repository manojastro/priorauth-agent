---
policy_id: ACME-POL-CPAP
version: "2026.1"
title: Continuous positive airway pressure device
services:
  - code: SVC-CPAP
    display: CPAP device
    hcpcs: E0601
pa_required: {HMO: true, PPO: true, EPO: true}
criteria:
  - id: CPAP-2.1
    kind: condition
    codes: [G47.33]
    non_qualifying_codes: [G47.31]
    window_days: 365
  - id: CPAP-2.2
    kind: observation_threshold
    code: AHI
    display: Apnea-hypopnea index
    value_type: quantity
    unit: /h
    op: ">="
    value: 5
    window_days: 365
  - id: CPAP-2.3
    kind: procedure_done
    code: PSG-STUDY
    display: Attended polysomnography
    window_days: 365
  - id: CPAP-2.4
    kind: note
    window_days: 90
---
# Acme Health Plan medical policy: CPAP device

> Synthetic policy written for a demo. Not a real payer policy. Not for clinical use.

## CPAP-1 Scope
This policy covers a CPAP device (internal service code SVC-CPAP; public HCPCS Level II code E0601).

## CPAP-2 Coverage criteria
All of the criteria below must be documented.

### CPAP-2.1 Qualifying diagnosis
A documented diagnosis of obstructive sleep apnea (ICD-10-CM G47.33) within the last 12 months. Central sleep apnea (G47.31) is not covered under this policy.

### CPAP-2.2 Apnea-hypopnea index
An apnea-hypopnea index of 5 events per hour or higher recorded within the last 12 months.

### CPAP-2.3 Qualifying sleep study
A sleep study performed within the last 12 months.

### CPAP-2.4 Face-to-face evaluation
A clinical note from the last 90 days documents a face-to-face evaluation of sleep symptoms.

## CPAP-3 Exclusions
### CPAP-3.1 Replacement
Device replacement within 5 years is reviewed under a separate policy.

## CPAP-4 Red-flag exceptions
### CPAP-4.1 None
There are no red-flag exceptions.

## CPAP-5 Required documentation
### CPAP-5.1 Documents to submit
Diagnosis, sleep study record with AHI and the evaluation note.

## CPAP-6 Prior authorization by plan type
### CPAP-6.1 Plan rules
Prior authorization is required for HMO, PPO and EPO plans.
