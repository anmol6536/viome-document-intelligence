import pytest

from app.fhir.validator import FhirValidationError, ValidatorUnavailableError
from app.jobs.retry_policy import ExtractionValidationError, ProviderUnavailableError
from app.jobs.store import JobStore
from app.jobs.worker import run_extraction_job
from app.models.api import JobStatus

SCHEMA = {"type": "object", "required": ["value"], "properties": {"value": {"type": "number"}}}


class _FakeValidator:
    def __init__(self, raise_error: Exception | None = None):
        self._raise_error = raise_error
        self.calls = []

    def validate(self, resource):
        self.calls.append(resource)
        if self._raise_error:
            raise self._raise_error


@pytest.mark.asyncio
async def test_successful_job_ends_succeeded_with_mapped_resource():
    store = JobStore()
    record = await store.create(user_id="user-1", schema_id="lab_observation", model_id="gemini")

    def client(file_bytes, mime_type, schema, prompt_context):
        return {"code": "2093-3", "display": "Cholesterol", "value": 180, "unit": "mg/dL", "effective_date": "2026-01-15"}

    validator = _FakeValidator()

    await run_extraction_job(
        job_id=record.job_id,
        file_bytes=b"pdf-bytes",
        mime_type="application/pdf",
        client=client,
        schema=SCHEMA,
        prompt_context="lab observation",
        schema_id="lab_observation",
        user_id="user-1",
        store=store,
        fhir_validator=validator,
    )

    final = await store.get(record.job_id)
    assert final.status == JobStatus.SUCCEEDED
    assert final.result["resourceType"] == "Observation"
    assert validator.calls == [final.result]


@pytest.mark.asyncio
async def test_provider_unavailable_fails_job_with_reason():
    store = JobStore()
    record = await store.create(user_id="user-1", schema_id="lab_observation", model_id="gemini")

    def client(file_bytes, mime_type, schema, prompt_context):
        raise ProviderUnavailableError("gemini down")

    await run_extraction_job(
        job_id=record.job_id,
        file_bytes=b"pdf-bytes",
        mime_type="application/pdf",
        client=client,
        schema=SCHEMA,
        prompt_context="lab observation",
        schema_id="lab_observation",
        user_id="user-1",
        store=store,
        fhir_validator=_FakeValidator(),
    )

    final = await store.get(record.job_id)
    assert final.status == JobStatus.FAILED
    assert final.error.reason == "gemini_unavailable"


@pytest.mark.asyncio
async def test_extraction_validation_failure_fails_job_with_detail():
    store = JobStore()
    record = await store.create(user_id="user-1", schema_id="lab_observation", model_id="gemini")

    def client(file_bytes, mime_type, schema, prompt_context):
        raise ExtractionValidationError(["value: not a number"])

    await run_extraction_job(
        job_id=record.job_id,
        file_bytes=b"pdf-bytes",
        mime_type="application/pdf",
        client=client,
        schema=SCHEMA,
        prompt_context="lab observation",
        schema_id="lab_observation",
        user_id="user-1",
        store=store,
        fhir_validator=_FakeValidator(),
    )

    final = await store.get(record.job_id)
    assert final.status == JobStatus.FAILED
    assert final.error.reason == "extraction_validation_failed"
    assert final.error.detail == ["value: not a number"]


@pytest.mark.asyncio
async def test_fhir_validation_failure_is_terminal_not_retried():
    store = JobStore()
    record = await store.create(user_id="user-1", schema_id="lab_observation", model_id="gemini")
    call_count = {"n": 0}

    def client(file_bytes, mime_type, schema, prompt_context):
        call_count["n"] += 1
        return {"code": "2093-3", "display": "Cholesterol", "value": 180, "unit": "mg/dL", "effective_date": "2026-01-15"}

    validator = _FakeValidator(raise_error=FhirValidationError(["Observation.status: required"]))

    await run_extraction_job(
        job_id=record.job_id,
        file_bytes=b"pdf-bytes",
        mime_type="application/pdf",
        client=client,
        schema=SCHEMA,
        prompt_context="lab observation",
        schema_id="lab_observation",
        user_id="user-1",
        store=store,
        fhir_validator=validator,
    )

    final = await store.get(record.job_id)
    assert final.status == JobStatus.FAILED
    assert final.error.reason == "fhir_validation_failed"
    assert call_count["n"] == 1  # never re-invoked the AI client


@pytest.mark.asyncio
async def test_validator_unavailable_fails_job():
    store = JobStore()
    record = await store.create(user_id="user-1", schema_id="lab_observation", model_id="gemini")

    def client(file_bytes, mime_type, schema, prompt_context):
        return {"code": "2093-3", "display": "Cholesterol", "value": 180, "unit": "mg/dL", "effective_date": "2026-01-15"}

    validator = _FakeValidator(raise_error=ValidatorUnavailableError("unreachable"))

    await run_extraction_job(
        job_id=record.job_id,
        file_bytes=b"pdf-bytes",
        mime_type="application/pdf",
        client=client,
        schema=SCHEMA,
        prompt_context="lab observation",
        schema_id="lab_observation",
        user_id="user-1",
        store=store,
        fhir_validator=validator,
    )

    final = await store.get(record.job_id)
    assert final.status == JobStatus.FAILED
    assert final.error.reason == "validator_unavailable"
