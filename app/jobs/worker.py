from __future__ import annotations

from app.ai.base import AIClient
from app.fhir.mapper import MappingError, map_to_observation
from app.fhir.validator import FhirValidationError, FhirValidator, ValidatorUnavailableError
from app.jobs.retry_policy import ExtractionValidationError, ProviderUnavailableError
from app.jobs.store import JobStore
from app.models.api import JobError, JobStatus


async def run_extraction_job(
    job_id: str,
    file_bytes: bytes,
    mime_type: str,
    client: AIClient,
    schema: dict,
    prompt_context: str,
    schema_id: str,
    user_id: str,
    store: JobStore,
    fhir_validator: FhirValidator,
) -> None:
    await store.update(job_id, status=JobStatus.PROCESSING)

    try:
        minimal_data = client(file_bytes, mime_type, schema, prompt_context)
    except ProviderUnavailableError as exc:
        await store.update(
            job_id,
            status=JobStatus.FAILED,
            error=JobError(reason="gemini_unavailable", detail=str(exc)),
        )
        return
    except ExtractionValidationError as exc:
        await store.update(
            job_id,
            status=JobStatus.FAILED,
            error=JobError(reason="extraction_validation_failed", detail=exc.errors),
        )
        return

    try:
        resource = map_to_observation(schema_id, minimal_data, user_id)
    except MappingError as exc:
        await store.update(
            job_id,
            status=JobStatus.FAILED,
            error=JobError(reason="mapping_failed", detail=str(exc)),
        )
        return

    try:
        fhir_validator.validate(resource)
    except FhirValidationError as exc:
        await store.update(
            job_id,
            status=JobStatus.FAILED,
            error=JobError(reason="fhir_validation_failed", detail=exc.issues),
        )
        return
    except ValidatorUnavailableError as exc:
        await store.update(
            job_id,
            status=JobStatus.FAILED,
            error=JobError(reason="validator_unavailable", detail=str(exc)),
        )
        return

    await store.update(job_id, status=JobStatus.SUCCEEDED, result=resource)
