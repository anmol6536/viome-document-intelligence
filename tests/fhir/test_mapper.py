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


def test_maps_multi_observation_to_bundle_of_observations():
    minimal = [
        {
            "code": "2093-3",
            "display": "Total Cholesterol",
            "value": 180,
            "unit": "mg/dL",
            "effective_date": "2026-08-04",
        },
        {
            "code": "2085-9",
            "display": "HDL Cholesterol",
            "value": 55,
            "unit": "mg/dL",
            "effective_date": "2026-08-04",
        },
    ]

    bundle = map_to_observation("multi_observation", minimal, user_id="user-123")

    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert len(bundle["entry"]) == 2
    first = bundle["entry"][0]["resource"]
    assert first["resourceType"] == "Observation"
    assert first["subject"] == {"reference": "Patient/user-123"}
    assert first["code"]["coding"][0]["code"] == "2093-3"
    second = bundle["entry"][1]["resource"]
    assert second["code"]["coding"][0]["code"] == "2085-9"
