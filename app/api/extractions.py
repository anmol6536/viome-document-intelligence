from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Header, UploadFile

from app.ai.base import AIClient
from app.ai.registry import get_ai_client_registry
from app.core.config import Settings, get_settings
from app.fhir.validator import FhirValidator
from app.jobs.store import JobStore, get_job_store
from app.jobs.worker import run_extraction_job
from app.models.api import JobCreatedResponse, JobStatusResponse
from app.schemas.registry import SchemaRegistry, get_schema_registry

router = APIRouter()


def _build_fhir_validator() -> FhirValidator:
    return FhirValidator(base_url=get_settings().fhir_validator_url)


@router.post("/extractions", response_model=JobCreatedResponse, status_code=202)
async def create_extraction(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    schema_id: str = Form(...),
    x_viome_user_id: str = Header(default=""),
    x_ai_model: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    schema_registry: SchemaRegistry = Depends(get_schema_registry),
    ai_clients: dict[str, AIClient] = Depends(get_ai_client_registry),
    store: JobStore = Depends(get_job_store),
) -> JobCreatedResponse:
    if not x_viome_user_id.strip():
        raise HTTPException(status_code=400, detail="X-Viome-User-Id header is required")

    schema = schema_registry.get(schema_id)
    if schema is None:
        raise HTTPException(status_code=400, detail=f"unknown schema_id: {schema_id!r}")

    if file.content_type not in settings.allowed_content_types:
        raise HTTPException(
            status_code=400, detail=f"unsupported file type: {file.content_type!r}"
        )

    model_id = x_ai_model or settings.default_ai_model
    client = ai_clients.get(model_id)
    if client is None:
        raise HTTPException(status_code=400, detail=f"unknown X-AI-Model: {model_id!r}")

    file_bytes = await file.read()
    if len(file_bytes) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="file exceeds maximum upload size")

    record = await store.create(user_id=x_viome_user_id, schema_id=schema_id, model_id=model_id)

    background_tasks.add_task(
        run_extraction_job,
        job_id=record.job_id,
        file_bytes=file_bytes,
        mime_type=file.content_type,
        client=client,
        schema=schema,
        prompt_context=f"Report type: {schema_id}",
        schema_id=schema_id,
        user_id=x_viome_user_id,
        store=store,
        fhir_validator=_build_fhir_validator(),
    )

    return JobCreatedResponse(job_id=record.job_id)


@router.get("/extractions/{job_id}", response_model=JobStatusResponse)
async def get_extraction(
    job_id: str, store: JobStore = Depends(get_job_store)
) -> JobStatusResponse:
    record = await store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="job not found")

    return JobStatusResponse(
        job_id=record.job_id,
        status=record.status,
        result=record.result,
        error=record.error,
    )
