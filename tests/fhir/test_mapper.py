import pytest

from app.fhir.mapper import DOCUMENT_CHECKSUM_SYSTEM, MappingError, map_to_observation

CHECKSUM = "a" * 64  # stand-in sha256 hex digest


def test_maps_lab_observation_to_fhir_observation():
    minimal = {
        "code": "2093-3",
        "display": "Cholesterol",
        "value": 180,
        "unit": "mg/dL",
        "effective_date": "2026-01-15",
    }

    observation = map_to_observation(
        "lab_observation", minimal, user_id="user-123", document_checksum=CHECKSUM
    )

    assert observation["resourceType"] == "Observation"
    assert observation["meta"]["profile"] == [
        "http://viome.com/fhir/document-intelligence/StructureDefinition/viome-lab-observation"
    ]
    assert observation["meta"]["tag"] == [{"system": DOCUMENT_CHECKSUM_SYSTEM, "code": CHECKSUM}]
    assert observation["identifier"] == [{"system": DOCUMENT_CHECKSUM_SYSTEM, "value": CHECKSUM}]
    assert observation["status"] == "final"
    assert observation["category"][0]["coding"][0]["code"] == "laboratory"
    assert observation["subject"] == {"reference": "Patient/user-123"}
    assert observation["effectiveDateTime"] == "2026-01-15"
    assert observation["code"]["text"] == "Cholesterol"
    coding = observation["code"]["coding"][0]
    assert coding == {"system": "http://loinc.org", "code": "2093-3", "display": "Cholesterol"}
    assert observation["valueQuantity"] == {
        "value": 180,
        "unit": "mg/dL",
        "system": "http://unitsofmeasure.org",
        "code": "mg/dL",
    }
    assert observation["text"]["status"] == "generated"
    assert "Cholesterol" in observation["text"]["div"]
    # id is a real UUID string
    import uuid

    uuid.UUID(observation["id"])


def test_same_checksum_and_code_yields_same_observation_id():
    minimal = {
        "code": "2093-3",
        "display": "Cholesterol",
        "value": 180,
        "unit": "mg/dL",
        "effective_date": "2026-01-15",
    }

    first = map_to_observation(
        "lab_observation", minimal, user_id="user-123", document_checksum=CHECKSUM
    )
    second = map_to_observation(
        "lab_observation", minimal, user_id="user-123", document_checksum=CHECKSUM
    )

    assert first["id"] == second["id"]


def test_different_checksum_yields_different_observation_id():
    minimal = {
        "code": "2093-3",
        "display": "Cholesterol",
        "value": 180,
        "unit": "mg/dL",
        "effective_date": "2026-01-15",
    }

    first = map_to_observation(
        "lab_observation", minimal, user_id="user-123", document_checksum=CHECKSUM
    )
    second = map_to_observation(
        "lab_observation", minimal, user_id="user-123", document_checksum="b" * 64
    )

    assert first["id"] != second["id"]


def test_unknown_schema_id_raises_mapping_error():
    with pytest.raises(MappingError):
        map_to_observation("unknown_schema", {}, user_id="user-123", document_checksum=CHECKSUM)


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

    bundle = map_to_observation(
        "multi_observation", minimal, user_id="user-123", document_checksum=CHECKSUM
    )

    assert bundle["resourceType"] == "Bundle"
    assert bundle["identifier"] == {"system": DOCUMENT_CHECKSUM_SYSTEM, "value": CHECKSUM}
    assert bundle["type"] == "collection"
    assert len(bundle["entry"]) == 2
    first = bundle["entry"][0]["resource"]
    assert first["resourceType"] == "Observation"
    assert first["subject"] == {"reference": "Patient/user-123"}
    assert first["code"]["coding"][0]["code"] == "2093-3"
    second = bundle["entry"][1]["resource"]
    assert second["code"]["coding"][0]["code"] == "2085-9"
    # two entries with different codes in the same document get different ids
    assert first["id"] != second["id"]


def test_multi_observation_entries_get_stable_ids_across_repeated_mapping():
    minimal = [
        {
            "code": "2093-3",
            "display": "Total Cholesterol",
            "value": 180,
            "unit": "mg/dL",
            "effective_date": "2026-08-04",
        },
    ]

    first_bundle = map_to_observation(
        "multi_observation", minimal, user_id="user-123", document_checksum=CHECKSUM
    )
    second_bundle = map_to_observation(
        "multi_observation", minimal, user_id="user-123", document_checksum=CHECKSUM
    )

    assert first_bundle["id"] == second_bundle["id"]
    assert (
        first_bundle["entry"][0]["resource"]["id"]
        == second_bundle["entry"][0]["resource"]["id"]
    )
