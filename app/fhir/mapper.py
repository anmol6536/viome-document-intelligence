from __future__ import annotations


class MappingError(Exception):
    """Raised when minimal extracted data cannot be mapped to a FHIR resource."""


def _map_lab_observation(minimal_data: dict, user_id: str) -> dict:
    return {
        "resourceType": "Observation",
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


_MAPPERS = {
    "lab_observation": _map_lab_observation,
}


def map_to_observation(schema_id: str, minimal_data: dict, user_id: str) -> dict:
    mapper = _MAPPERS.get(schema_id)
    if mapper is None:
        raise MappingError(f"no FHIR mapper registered for schema_id={schema_id!r}")
    try:
        return mapper(minimal_data, user_id)
    except KeyError as exc:
        raise MappingError(f"minimal data missing required field: {exc}") from exc
