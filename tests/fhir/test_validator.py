import httpx
import pytest

from app.fhir.validator import FhirValidationError, FhirValidator, ValidatorUnavailableError

RESOURCE = {"resourceType": "Observation"}


def test_validate_passes_silently_when_valid():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"valid": True, "issues": []})

    transport = httpx.MockTransport(handler)
    validator = FhirValidator(
        base_url="http://validator.local",
        http_client=httpx.Client(transport=transport),
    )
    validator.validate(RESOURCE)  # should not raise


def test_validate_raises_fhir_validation_error_with_issues():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"valid": False, "issues": ["Observation.status: required"]}
        )

    transport = httpx.MockTransport(handler)
    validator = FhirValidator(
        base_url="http://validator.local",
        http_client=httpx.Client(transport=transport),
    )
    with pytest.raises(FhirValidationError) as exc_info:
        validator.validate(RESOURCE)
    assert exc_info.value.issues == ["Observation.status: required"]


def test_validate_raises_validator_unavailable_on_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(handler)
    validator = FhirValidator(
        base_url="http://validator.local",
        http_client=httpx.Client(transport=transport),
    )
    with pytest.raises(ValidatorUnavailableError):
        validator.validate(RESOURCE)
