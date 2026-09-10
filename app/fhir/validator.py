from __future__ import annotations

import httpx


class ValidatorUnavailableError(Exception):
    """Raised when the HL7 validator sidecar cannot be reached."""


class FhirValidationError(Exception):
    """Raised when the HL7 validator rejects a resource."""

    def __init__(self, issues: list[str]) -> None:
        super().__init__(f"FHIR validation failed: {issues}")
        self.issues = issues


class FhirValidator:
    def __init__(self, base_url: str, http_client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._http_client = http_client or httpx.Client(timeout=30.0)

    def validate(self, resource: dict) -> None:
        try:
            response = self._http_client.post(f"{self._base_url}/validate", json=resource)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ValidatorUnavailableError(str(exc)) from exc
        except ValueError as exc:  # non-JSON response body
            raise ValidatorUnavailableError(str(exc)) from exc

        if not payload.get("valid", False):
            raise FhirValidationError(payload.get("issues", []))
