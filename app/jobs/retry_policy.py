from __future__ import annotations

import time
from collections.abc import Callable

import jsonschema


class TransportError(Exception):
    """Raised by a request callable on a transport-level failure (timeout, 5xx, ...)."""


class ProviderUnavailableError(Exception):
    """Raised when transport retries are exhausted."""


class ExtractionValidationError(Exception):
    """Raised when the extraction schema still fails validation after all retries."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__(f"extraction validation failed: {errors}")
        self.errors = errors


class RetryPolicy:
    def __init__(
        self,
        max_transport_retries: int = 2,
        max_validation_retries: int = 3,
        backoff_seconds: float = 1.0,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._max_transport_retries = max_transport_retries
        self._max_validation_retries = max_validation_retries
        self._backoff_seconds = backoff_seconds
        self._sleep_fn = sleep_fn

    def run(self, do_request: Callable[[str | None], dict], schema: dict) -> dict:
        feedback: str | None = None
        last_errors: list[str] = []
        validator = jsonschema.Draft7Validator(schema)

        for _ in range(self._max_validation_retries + 1):
            result = self._call_with_transport_retry(do_request, feedback)
            errors = sorted(validator.iter_errors(result), key=lambda e: e.path)
            if not errors:
                return result
            last_errors = [e.message for e in errors]
            error_parts = []
            for e in errors:
                path_str = ".".join(str(p) for p in e.path) if e.path else "root"
                error_parts.append(f"field '{path_str}': {e.message}")
            feedback = "Fix these validation errors: " + "; ".join(error_parts)

        raise ExtractionValidationError(last_errors)

    def _call_with_transport_retry(
        self, do_request: Callable[[str | None], dict], feedback: str | None
    ) -> dict:
        last_exc: Exception | None = None
        for attempt in range(self._max_transport_retries + 1):
            try:
                return do_request(feedback)
            except TransportError as exc:
                last_exc = exc
                if attempt < self._max_transport_retries:
                    self._sleep_fn(self._backoff_seconds * (attempt + 1))
        raise ProviderUnavailableError(str(last_exc)) from last_exc
