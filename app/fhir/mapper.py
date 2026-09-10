from __future__ import annotations

IG_CANONICAL = "http://viome.com/fhir/document-intelligence"
VIOME_LAB_OBSERVATION_PROFILE = f"{IG_CANONICAL}/StructureDefinition/viome-lab-observation"


class MappingError(Exception):
    """Raised when minimal extracted data cannot be mapped to a FHIR resource."""


def _map_lab_observation(minimal_data: dict, user_id: str) -> dict:
    return {
        "resourceType": "Observation",
        "meta": {"profile": [VIOME_LAB_OBSERVATION_PROFILE]},
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": minimal_data["code"],
                    "display": minimal_data["display"],
                }
            ]
        },
        "subject": {"reference": f"Patient/{user_id}"},
        "effectiveDateTime": minimal_data["effective_date"],
        "valueQuantity": {
            "value": minimal_data["value"],
            "unit": minimal_data["unit"],
            "system": "http://unitsofmeasure.org",
            "code": minimal_data["unit"],
        },
    }


def _map_multi_observation(minimal_data: list, user_id: str) -> dict:
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"resource": _map_lab_observation(item, user_id)} for item in minimal_data
        ],
    }


_MAPPERS = {
    "lab_observation": _map_lab_observation,
    "multi_observation": _map_multi_observation,
}


def map_to_observation(schema_id: str, minimal_data: dict, user_id: str) -> dict:
    mapper = _MAPPERS.get(schema_id)
    if mapper is None:
        raise MappingError(f"no FHIR mapper registered for schema_id={schema_id!r}")
    try:
        return mapper(minimal_data, user_id)
    except KeyError as exc:
        raise MappingError(f"minimal data missing required field: {exc}") from exc
