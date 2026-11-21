"""Code systems and identifiers used across the project (synthetic, demo only)."""

ICD10CM = "http://hl7.org/fhir/sid/icd-10-cm"
LOINC = "http://loinc.org"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
UCUM = "http://unitsofmeasure.org"
COVERAGE_CLASS = "http://terminology.hl7.org/CodeSystem/coverage-class"
CONDITION_CLINICAL = "http://terminology.hl7.org/CodeSystem/condition-clinical"

# Internal (made-up) code systems. Used instead of CPT, and instead of guessing SNOMED/LOINC codes.
ACME_SERVICE = "http://acme-health.example/fhir/CodeSystem/service"
ACME_CLINICAL = "http://acme-health.example/fhir/CodeSystem/clinical"
CASE_TAG = "http://acme-health.example/fhir/CodeSystem/case-id"
MEMBER_ID = "http://acme-health.example/fhir/sid/member-id"
CLINIC_MRN = "http://demo-clinic.example/fhir/sid/mrn"

PAYER_ORG_ID = "acme-health-plan"
CLINIC_ORG_ID = "demo-clinic"
PRACTITIONER_ID = "demo-practitioner"
