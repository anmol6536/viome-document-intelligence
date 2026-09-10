import pytest

from app.fhir.mapper import MappingError, map_to_observation


def test_maps_lab_observation_to_fhir_observation():
    minimal = {
        "code": "2093-3",
        "display": "Cholesterol",
        "value": 180,
        "unit": "mg/dL",
        "effective_date": "2026-01-15",
    }

    observation = map_to_observation("lab_observation", minimal, user_id="user-123")

    assert observation["resourceType"] == "Observation"
    assert observation["meta"]["profile"] == [
        "http://viome.com/fhir/document-intelligence/StructureDefinition/viome-lab-observation"
    ]
    assert observation["status"] == "final"
    assert observation["subject"] == {"reference": "Patient/user-123"}
    assert observation["effectiveDateTime"] == "2026-01-15"
    coding = observation["code"]["coding"][0]
    assert coding == {"system": "http://loinc.org", "code": "2093-3", "display": "Cholesterol"}
    assert observation["valueQuantity"] == {
        "value": 180,
        "unit": "mg/dL",
        "system": "http://unitsofmeasure.org",
        "code": "mg/dL",
    }


def test_unknown_schema_id_raises_mapping_error():
    with pytest.raises(MappingError):
        map_to_observation("unknown_schema", {}, user_id="user-123")
