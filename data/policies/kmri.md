---
policy_id: ACME-POL-KMRI
version: "2026.1"
title: Magnetic resonance imaging of the knee
services:
  - code: SVC-MRI-KNEE
    display: MRI knee without contrast
pa_required: {HMO: true, PPO: false, EPO: true}
criteria:
  - id: KMRI-2.1
    kind: condition
    codes: [M25.561, M25.562, S83.511A]
    non_qualifying_codes: [M25.511]
    window_days: 365
  - id: KMRI-2.2
    kind: procedure_duration
    code: PT-COURSE
    display: Physical therapy course
    min_days: 28
    window_days: 180
  - id: KMRI-2.3
    kind: procedure_done
    code: XR-KNEE
    display: Plain radiograph of the knee
    window_days: 60
  - id: KMRI-2.4
    kind: note
    window_days: 60
---
# Acme Health Plan medical policy: Knee MRI

> Synthetic policy written for a demo. Not a real payer policy. Not for clinical use.

## KMRI-1 Scope
This policy covers outpatient MRI of the knee (internal service code SVC-MRI-KNEE).

## KMRI-2 Coverage criteria
All of the criteria below must be documented.

### KMRI-2.1 Qualifying diagnosis
A documented diagnosis of knee pain or a knee ligament sprain (ICD-10-CM M25.561, M25.562 or S83.511A) within the last 12 months. Shoulder pain (M25.511) does not qualify.

### KMRI-2.2 Conservative therapy
At least 4 weeks (28 days) of documented conservative therapy, such as physical therapy, within the 6 months before the request.

### KMRI-2.3 Plain radiograph
A plain radiograph of the affected knee performed within the 60 days before the request.

### KMRI-2.4 Examination findings
A clinical note from the last 60 days documents mechanical symptoms (locking, catching) or instability on examination.

## KMRI-3 Exclusions
### KMRI-3.1 Screening use
MRI used for screening without symptoms is not covered.

## KMRI-4 Red-flag exceptions
### KMRI-4.1 Acute trauma
Acute trauma with suspected complete ligament rupture waives KMRI-2.2.

## KMRI-5 Required documentation
### KMRI-5.1 Documents to submit
Diagnosis, therapy records, radiograph record and the most recent clinical note.

## KMRI-6 Prior authorization by plan type
### KMRI-6.1 Plan rules
Prior authorization is required for HMO and EPO plans. It is not required for PPO plans.
