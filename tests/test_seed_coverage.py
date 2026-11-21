import json

from fhir.resources.R4B import get_fhir_model_class

from scripts import seed_coverage as sc


def _synthea_bundle(uuid, with_cov=False):
    entries = [
        {
            "resource": {
                "resourceType": "Patient",
                "id": uuid,
                "identifier": [{"system": sc.SYNTHEA_ID_SYSTEM, "value": uuid}],
            }
        }
    ]
    if with_cov:
        entries.append({"resource": {"resourceType": "Coverage", "id": "c"}})
    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}


def test_builds_coverage_for_patients_without_one(tmp_path):
    for i in range(40):
        (tmp_path / f"p{i:02d}.json").write_text(json.dumps(_synthea_bundle(f"uuid-{i:02d}")))
    (tmp_path / "hascov.json").write_text(json.dumps(_synthea_bundle("uuid-x", with_cov=True)))
    (tmp_path / "hospitalInformation1.json").write_text(json.dumps(_synthea_bundle("h")))

    b = sc.build(tmp_path, seed=7)
    covs = [e["resource"] for e in b["entry"]]
    assert len(covs) == 40
    for c in covs:
        get_fhir_model_class("Coverage").model_validate(c)
        assert c["beneficiary"]["reference"].startswith("Patient?identifier=")
    assert any("end" in c["period"] for c in covs), "expect some terminated coverage"
    assert {c["class"][0]["value"] for c in covs} <= {"HMO", "PPO", "EPO"}
    assert sc.build(tmp_path, seed=7) == b
