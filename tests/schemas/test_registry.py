import pytest

from app.schemas.registry import SchemaRegistry


def test_load_registers_schema_by_id():
    registry = SchemaRegistry.load()
    assert "lab_observation" in registry
    schema = registry.get("lab_observation")
    assert schema["title"] == "LabObservationExtraction"
    assert "code" in schema["required"]


def test_get_unknown_schema_returns_none():
    registry = SchemaRegistry.load()
    assert registry.get("does_not_exist") is None
