from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_SCHEMA_SUFFIX = ".extract.schema.json"


class SchemaRegistry:
    def __init__(self, schemas: dict[str, dict]) -> None:
        self._schemas = schemas

    @classmethod
    def load(cls, directory: Path | None = None) -> "SchemaRegistry":
        directory = directory or Path(__file__).parent
        schemas: dict[str, dict] = {}
        for path in sorted(directory.glob(f"*{_SCHEMA_SUFFIX}")):
            schema_id = path.name[: -len(_SCHEMA_SUFFIX)]
            with path.open() as f:
                schemas[schema_id] = json.load(f)
        return cls(schemas)

    def get(self, schema_id: str) -> dict | None:
        return self._schemas.get(schema_id)

    def __contains__(self, schema_id: str) -> bool:
        return schema_id in self._schemas


@lru_cache
def get_schema_registry() -> SchemaRegistry:
    return SchemaRegistry.load()
