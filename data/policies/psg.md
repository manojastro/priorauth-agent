---
policy_id: ACME-POL-PSG
version: "2026.1"
title: Attended polysomnography (sleep study)
services:
  - code: SVC-PSG
    display: Attended in-lab polysomnography
pa_required: {HMO: true, PPO: true, EPO: false}
criteria:
  - id: PSG-2.1
    kind: condition
    codes: [R06.83, G47.10, G47.30]
    non_qualifying_codes: [G47.00]
    window_days: 365
  - id: PSG-2.2
    kind: observation_threshold
    code: ESS-TOTAL
    display: Epworth Sleepiness Scale total score
    value_type: integer
    op: ">="
    value: 10
    window_days: 180
  - id: PSG-2.3
    kind: note
    window_days: 90
---
# Acme Health Plan medical policy: Polysomnography

> Synthetic policy written for a demo. Not a real payer policy. Not for clinical use.

## PSG-1 Scope
This policy covers attended in-lab polysomnography (internal service code SVC-PSG).

## PSG-2 Coverage criteria
All of the criteria below must be documented.

### PSG-2.1 Qualifying diagnosis
A documented diagnosis of snoring, hypersomnia or suspected sleep apnea (ICD-10-CM R06.83, G47.10 or G47.30) within the last 12 months. Insomnia alone (G47.00) does not qualify.

### PSG-2.2 Daytime sleepiness score
An Epworth Sleepiness Scale total score of 10 or higher recorded within the last 6 months.

### PSG-2.3 Observed symptoms
A clinical note from the last 90 days documents witnessed apneas, or choking or gasping during sleep.

## PSG-3 Exclusions
### PSG-3.1 Home study preferred
Members who meet the plan's home sleep test rules should use a home test first; this is reviewed case by case.

## PSG-4 Red-flag exceptions
### PSG-4.1 Occupational safety
Drowsy-driving events documented in the record waive PSG-2.2.

## PSG-5 Required documentation
### PSG-5.1 Documents to submit
Diagnosis, sleepiness score and the most recent clinical note.

## PSG-6 Prior authorization by plan type
### PSG-6.1 Plan rules
Prior authorization is required for HMO and PPO plans. It is not required for EPO plans.
