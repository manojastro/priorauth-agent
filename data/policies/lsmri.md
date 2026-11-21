---
policy_id: ACME-POL-LSMRI
version: "2026.1"
title: Magnetic resonance imaging of the lumbar spine
services:
  - code: SVC-MRI-LSPINE
    display: MRI lumbar spine without contrast
pa_required: {HMO: true, PPO: true, EPO: true}
criteria:
  - id: LSMRI-2.1
    kind: condition
    codes: [M54.50, M54.16, M51.16]
    non_qualifying_codes: [M54.2]
    window_days: 365
  - id: LSMRI-2.2
    kind: procedure_duration
    code: PT-COURSE
    display: Physical therapy course
    min_days: 42
    window_days: 180
  - id: LSMRI-2.3
    kind: medication_trial
    rxnorm:
      - {code: "5640", display: ibuprofen}
      - {code: "7258", display: naproxen}
      - {code: "41493", display: meloxicam}
    min_days: 28
    window_days: 180
  - id: LSMRI-2.4
    kind: note
    window_days: 60
---
# Acme Health Plan medical policy: Lumbar spine MRI

> Synthetic policy written for a demo. Not a real payer policy. Not for clinical use.

## LSMRI-1 Scope
This policy covers outpatient MRI of the lumbar spine (internal service code SVC-MRI-LSPINE) for adult members with low back symptoms.

## LSMRI-2 Coverage criteria
All of the criteria below must be documented in the medical record.

### LSMRI-2.1 Qualifying diagnosis
A documented diagnosis of low back pain, lumbar radiculopathy, or lumbar disc disorder with radiculopathy (ICD-10-CM M54.50, M54.16 or M51.16), recorded within the last 12 months. Neck pain alone (M54.2) does not qualify.

### LSMRI-2.2 Conservative therapy
At least 6 weeks (42 days) of documented conservative therapy, such as a supervised physical therapy course, completed within the 6 months before the request.

### LSMRI-2.3 Anti-inflammatory medication trial
A documented trial of a non-steroidal anti-inflammatory drug (for example ibuprofen, naproxen or meloxicam) lasting at least 4 weeks (28 days), within the 6 months before the request.

### LSMRI-2.4 Neurological examination
A clinical note from the last 60 days documents a neurological examination of the lower extremities.

## LSMRI-3 Exclusions
### LSMRI-3.1 Repeat imaging
Repeat lumbar MRI within 12 months without a documented change in symptoms is not covered.

## LSMRI-4 Red-flag exceptions
### LSMRI-4.1 Red flags waive conservative therapy
When the record documents a red flag (suspected cauda equina syndrome, progressive motor deficit, suspected malignancy or infection), criteria LSMRI-2.2 and LSMRI-2.3 do not apply.

## LSMRI-5 Required documentation
### LSMRI-5.1 Documents to submit
Diagnosis, therapy records with dates, medication history with dates, and the most recent clinical note.

## LSMRI-6 Prior authorization by plan type
### LSMRI-6.1 Plan rules
Prior authorization is required for HMO, PPO and EPO plans.
