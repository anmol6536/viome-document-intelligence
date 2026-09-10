from __future__ import annotations

import uuid

IG_CANONICAL = "http://viome.com/fhir/document-intelligence"
VIOME_LAB_OBSERVATION_PROFILE = f"{IG_CANONICAL}/StructureDefinition/viome-lab-observation"
DOCUMENT_CHECKSUM_SYSTEM = f"{IG_CANONICAL}/identifier/document-checksum"
LABORATORY_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/observation-category"

# Fixed namespace used to derive resource ids deterministically from a source
# document's checksum (uuid5), so re-uploading the same document/image always
# produces the same Bundle/Observation ids instead of new ones every time.
DOCUMENT_ID_NAMESPACE = uuid.UUID("15b45329-7604-4ce5-a197-65cc0cd25369")


class MappingError(Exception):
    """Raised when minimal extracted data cannot be mapped to a FHIR resource."""


def _deterministic_id(*parts: str) -> str:
    return str(uuid.uuid5(DOCUMENT_ID_NAMESPACE, ":".join(parts)))


def _narrative_text(display: str, value: float, unit: str, effective_date: str) -> dict:
    return {
        "status": "generated",
        "div": (
            '<div xmlns="http://www.w3.org/1999/xhtml">'
            f"{display}: {value} {unit} ({effective_date})"
            "</div>"
        ),
    }


def _map_lab_observation(
    minimal_data: dict, user_id: str, document_checksum: str, index: int = 0
) -> dict:
    code = minimal_data["code"]
    display = minimal_data["display"]
    value = minimal_data["value"]
    unit = minimal_data["unit"]
    effective_date = minimal_data["effective_date"]

    return {
        "resourceType": "Observation",
        "id": _deterministic_id(document_checksum, str(index), code),
        "meta": {
            "profile": [VIOME_LAB_OBSERVATION_PROFILE],
            "tag": [{"system": DOCUMENT_CHECKSUM_SYSTEM, "code": document_checksum}],
        },
        "identifier": [{"system": DOCUMENT_CHECKSUM_SYSTEM, "value": document_checksum}],
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": LABORATORY_CATEGORY_SYSTEM,
                        "code": "laboratory",
                        "display": "Laboratory",
                    }
                ],
                "text": "Laboratory",
            }
        ],
        "code": {
            "coding": [{"system": "http://loinc.org", "code": code, "display": display}],
            "text": display,
        },
        "subject": {"reference": f"Patient/{user_id}"},
        "effectiveDateTime": effective_date,
        "valueQuantity": {
            "value": value,
            "unit": unit,
            "system": "http://unitsofmeasure.org",
            "code": unit,
        },
        "text": _narrative_text(display, value, unit, effective_date),
    }


def _map_multi_observation(minimal_data: list, user_id: str, document_checksum: str) -> dict:
    return {
        "resourceType": "Bundle",
        "id": _deterministic_id(document_checksum),
        "identifier": {"system": DOCUMENT_CHECKSUM_SYSTEM, "value": document_checksum},
        "type": "collection",
        "entry": [
            {"resource": _map_lab_observation(item, user_id, document_checksum, index=i)}
            for i, item in enumerate(minimal_data)
        ],
    }


_MAPPERS = {
    "lab_observation": _map_lab_observation,
    "multi_observation": _map_multi_observation,
}


def map_to_observation(
    schema_id: str, minimal_data: dict | list, user_id: str, document_checksum: str
) -> dict:
    mapper = _MAPPERS.get(schema_id)
    if mapper is None:
        raise MappingError(f"no FHIR mapper registered for schema_id={schema_id!r}")
    try:
        return mapper(minimal_data, user_id, document_checksum)
    except KeyError as exc:
        raise MappingError(f"minimal data missing required field: {exc}") from exc
