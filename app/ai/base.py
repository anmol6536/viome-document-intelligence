from __future__ import annotations

from typing import Protocol


class AIClient(Protocol):
    def __call__(
        self, file_bytes: bytes, mime_type: str, schema: dict, prompt_context: str
    ) -> dict: ...
