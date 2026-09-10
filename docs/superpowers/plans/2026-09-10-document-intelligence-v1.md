# Document Intelligence v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v1 FastAPI service that accepts a lab-report file, runs it through an AI provider (Gemini) to extract minimal structured data, validates/maps that into a FHIR `Observation`, validates it against a custom FHIR profile via the HL7 validator, and serves the result through an async job API.

**Architecture:** `POST /extractions` enqueues a `BackgroundTasks` job; a worker pipeline calls an injected, self-retrying `AIClient` (Gemini for v1) to get minimal JSON, maps it to a FHIR `Observation`, validates that resource against a SUSHI-compiled profile via a sidecar HL7 validator service, and stores the outcome in an in-memory job store that `GET /extractions/{job_id}` reads.

**Tech Stack:** Python 3.12, FastAPI, `jsonschema`, `google-genai` SDK, `httpx`, `pytest` + `pytest-asyncio`, FHIR Shorthand (FSH) + SUSHI (Node.js, build-time only), HL7 `validator_cli.jar` (Java, runs as a sidecar), Docker + docker-compose, plain `pip`/`requirements.txt`.

**Spec:** `docs/superpowers/specs/2026-09-10-document-intelligence-design.md`

## Global Constraints

- Accepted input files: PDF, JPEG, PNG only (spec: Purpose).
- `X-Viome-User-Id` header is required on `POST /extractions`; missing/empty → `400` (spec: API).
- `X-AI-Model` header is optional, defaults to the configured default provider (`gemini` for v1); unknown value → `400` (spec: API).
- No persistence beyond the life of a job — in-memory only, no DB/object storage (spec: Non-goals).
- No auth (spec: Non-goals).
- `AIClient` is callable (`__call__`), constructed with a `RetryPolicy` injected at construction time; retry logic never lives in the worker (spec: AI provider abstraction, RetryPolicy).
- FHIR validation failures are terminal — never retried through the AI provider (spec: Error handling).
- Dependency management is plain `pip` + `requirements.txt`; `pyproject.toml` holds metadata/tool config only (spec: Project structure).

---

## File Structure

```
.
├── app/
│   ├── main.py
│   ├── api/
│   │   └── extractions.py
│   ├── ai/
│   │   ├── base.py
│   │   ├── registry.py
│   │   └── gemini/
│   │       ├── client.py
│   │       └── prompts.py
│   ├── schemas/
│   │   ├── registry.py
│   │   └── lab_observation.extract.schema.json
│   ├── fhir/
│   │   ├── mapper.py
│   │   └── validator.py
│   ├── jobs/
│   │   ├── store.py
│   │   ├── retry_policy.py
│   │   └── worker.py
│   ├── models/
│   │   └── api.py
│   └── core/
│       └── config.py
├── fhir-ig/
│   ├── sushi-config.yaml
│   └── input/fsh/observation.fsh
├── tests/
│   ├── conftest.py
│   ├── schemas/test_registry.py
│   ├── jobs/test_store.py
│   ├── jobs/test_retry_policy.py
│   ├── ai/test_gemini_client.py
│   ├── fhir/test_mapper.py
│   ├── fhir/test_validator.py
│   ├── jobs/test_worker.py
│   └── api/test_extractions.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `app/__init__.py`, `app/core/__init__.py`, `app/core/config.py`
- Create: `app/main.py`
- Test: `tests/conftest.py`, `tests/api/test_health.py`

**Interfaces:**
- Produces: `app.core.config.Settings` (Pydantic `BaseSettings`) with fields `gemini_api_key: str`, `default_ai_model: str = "gemini"`, `max_transport_retries: int = 2`, `max_validation_retries: int = 3`, `retry_backoff_seconds: float = 1.0`, `fhir_validator_url: str = "http://localhost:8090"`, `max_upload_bytes: int = 20 * 1024 * 1024`, `allowed_content_types: set[str] = {"application/pdf", "image/jpeg", "image/png"}`. Loaded via `get_settings()` (cached with `functools.lru_cache`).
- Produces: `app.main.app` (the `FastAPI` instance), with `GET /health` returning `{"status": "ok"}`.

- [ ] **Step 1: Write `requirements.txt`**

```
fastapi==0.115.6
uvicorn[standard]==0.32.1
pydantic==2.10.3
pydantic-settings==2.7.0
jsonschema==4.23.0
google-genai==0.3.0
httpx==0.28.1
python-multipart==0.0.20
pytest==8.3.4
pytest-asyncio==0.25.0
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "viome-document-intelligence"
version = "0.1.0"
description = "AI-assisted extraction of lab report data into FHIR resources"
requires-python = ">=3.12"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 3: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
.env
.pytest_cache/
*.egg-info/
fhir-ig/output/
fhir-ig/fsh-generated/
.DS_Store
```

- [ ] **Step 4: Write `.env.example`**

```
GEMINI_API_KEY=changeme
DEFAULT_AI_MODEL=gemini
MAX_TRANSPORT_RETRIES=2
MAX_VALIDATION_RETRIES=3
RETRY_BACKOFF_SECONDS=1.0
FHIR_VALIDATOR_URL=http://localhost:8090
MAX_UPLOAD_BYTES=20971520
```

- [ ] **Step 5: Write `app/core/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    default_ai_model: str = "gemini"

    max_transport_retries: int = 2
    max_validation_retries: int = 3
    retry_backoff_seconds: float = 1.0

    fhir_validator_url: str = "http://localhost:8090"

    max_upload_bytes: int = 20 * 1024 * 1024
    allowed_content_types: set[str] = {"application/pdf", "image/jpeg", "image/png"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: Write `app/main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title="Viome Document Intelligence")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 7: Write `tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
```

- [ ] **Step 8: Write the failing/passing health test**

```python
# tests/api/test_health.py
def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 9: Install deps and run the test**

Run: `pip install -r requirements.txt && pytest tests/api/test_health.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add requirements.txt pyproject.toml .gitignore .env.example app/main.py app/core tests/conftest.py tests/api/test_health.py app/__init__.py
git commit -m "chore: project scaffolding with FastAPI health endpoint"
```

---

### Task 2: Extraction schema registry

**Files:**
- Create: `app/schemas/__init__.py`
- Create: `app/schemas/lab_observation.extract.schema.json`
- Create: `app/schemas/registry.py`
- Test: `tests/schemas/test_registry.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `app.schemas.registry.SchemaRegistry` with `load(directory: pathlib.Path | None = None) -> SchemaRegistry` classmethod, `get(schema_id: str) -> dict | None`, `__contains__(schema_id: str) -> bool`. `app.schemas.registry.get_schema_registry() -> SchemaRegistry` (module-level singleton, lazily built from the package directory).

- [ ] **Step 1: Write the extraction schema fixture**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "LabObservationExtraction",
  "type": "object",
  "required": ["code", "display", "value", "unit", "effective_date"],
  "properties": {
    "code": {"type": "string", "description": "LOINC code for the lab test"},
    "display": {"type": "string", "description": "Human-readable test name"},
    "value": {"type": "number", "description": "Numeric result value"},
    "unit": {"type": "string", "description": "UCUM unit for the value"},
    "effective_date": {"type": "string", "format": "date", "description": "YYYY-MM-DD date the sample was taken/reported"}
  },
  "additionalProperties": false
}
```

Save as `app/schemas/lab_observation.extract.schema.json`.

- [ ] **Step 2: Write the failing test**

```python
# tests/schemas/test_registry.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/schemas/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError` for `app.schemas.registry`

- [ ] **Step 4: Write `app/schemas/registry.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/schemas/test_registry.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/schemas tests/schemas
git commit -m "feat: extraction schema registry"
```

---

### Task 3: API request/response models

**Files:**
- Create: `app/models/__init__.py`
- Create: `app/models/api.py`
- Test: `tests/models/test_api.py`

**Interfaces:**
- Produces: `app.models.api.JobStatus` (str `Enum`: `PENDING`, `PROCESSING`, `SUCCEEDED`, `FAILED`), `app.models.api.JobError` (Pydantic model: `reason: str`, `detail: dict | list | str | None = None`), `app.models.api.JobCreatedResponse` (`job_id: str`), `app.models.api.JobStatusResponse` (`job_id: str`, `status: JobStatus`, `result: dict | None = None`, `error: JobError | None = None`).

- [ ] **Step 1: Write the failing test**

```python
# tests/models/test_api.py
from app.models.api import JobCreatedResponse, JobError, JobStatus, JobStatusResponse


def test_job_status_response_serializes_pending_with_no_result():
    response = JobStatusResponse(job_id="abc", status=JobStatus.PENDING)
    payload = response.model_dump()
    assert payload["status"] == "pending"
    assert payload["result"] is None
    assert payload["error"] is None


def test_job_status_response_serializes_failure():
    response = JobStatusResponse(
        job_id="abc",
        status=JobStatus.FAILED,
        error=JobError(reason="extraction_validation_failed", detail=["value is required"]),
    )
    assert response.model_dump()["error"]["reason"] == "extraction_validation_failed"


def test_job_created_response():
    assert JobCreatedResponse(job_id="abc").model_dump() == {"job_id": "abc"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/models/test_api.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `app/models/api.py`**

```python
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobError(BaseModel):
    reason: str
    detail: dict | list | str | None = None


class JobCreatedResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    result: dict | None = None
    error: JobError | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/models/test_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/models tests/models
git commit -m "feat: API request/response models"
```

---

### Task 4: In-memory job store

**Files:**
- Create: `app/jobs/__init__.py`
- Create: `app/jobs/store.py`
- Test: `tests/jobs/test_store.py`

**Interfaces:**
- Consumes: `app.models.api.JobStatus`, `JobError` (Task 3).
- Produces: `app.jobs.store.JobRecord` (dataclass: `job_id: str`, `status: JobStatus`, `user_id: str`, `schema_id: str`, `model_id: str`, `result: dict | None = None`, `error: JobError | None = None`, `created_at: datetime`, `updated_at: datetime`). `app.jobs.store.JobStore` with async methods `create(user_id: str, schema_id: str, model_id: str) -> JobRecord`, `update(job_id: str, **fields) -> JobRecord`, `get(job_id: str) -> JobRecord | None`. `app.jobs.store.get_job_store() -> JobStore` (process-wide singleton).

- [ ] **Step 1: Write the failing test**

```python
# tests/jobs/test_store.py
import pytest

from app.jobs.store import JobStore
from app.models.api import JobStatus


@pytest.mark.asyncio
async def test_create_then_get_returns_pending_job():
    store = JobStore()
    record = await store.create(user_id="u1", schema_id="lab_observation", model_id="gemini")
    fetched = await store.get(record.job_id)
    assert fetched.status == JobStatus.PENDING
    assert fetched.user_id == "u1"


@pytest.mark.asyncio
async def test_update_changes_status_and_result():
    store = JobStore()
    record = await store.create(user_id="u1", schema_id="lab_observation", model_id="gemini")
    updated = await store.update(record.job_id, status=JobStatus.SUCCEEDED, result={"resourceType": "Observation"})
    assert updated.status == JobStatus.SUCCEEDED
    assert updated.result == {"resourceType": "Observation"}


@pytest.mark.asyncio
async def test_get_unknown_job_returns_none():
    store = JobStore()
    assert await store.get("does-not-exist") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_store.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `app/jobs/store.py`**

```python
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from functools import lru_cache

from app.models.api import JobError, JobStatus


@dataclass
class JobRecord:
    job_id: str
    status: JobStatus
    user_id: str
    schema_id: str
    model_id: str
    result: dict | None = None
    error: JobError | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, user_id: str, schema_id: str, model_id: str) -> JobRecord:
        record = JobRecord(
            job_id=str(uuid.uuid4()),
            status=JobStatus.PENDING,
            user_id=user_id,
            schema_id=schema_id,
            model_id=model_id,
        )
        async with self._lock:
            self._jobs[record.job_id] = record
        return record

    async def update(self, job_id: str, **fields) -> JobRecord:
        async with self._lock:
            current = self._jobs[job_id]
            updated = replace(current, updated_at=datetime.now(UTC), **fields)
            self._jobs[job_id] = updated
            return updated

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            return self._jobs.get(job_id)


@lru_cache
def get_job_store() -> JobStore:
    return JobStore()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/jobs/test_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/jobs/__init__.py app/jobs/store.py tests/jobs/test_store.py
git commit -m "feat: in-memory job store"
```

---

### Task 5: RetryPolicy

**Files:**
- Create: `app/jobs/retry_policy.py`
- Test: `tests/jobs/test_retry_policy.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure component; takes `jsonschema`).
- Produces: `app.jobs.retry_policy.TransportError(Exception)`, `app.jobs.retry_policy.ProviderUnavailableError(Exception)`, `app.jobs.retry_policy.ExtractionValidationError(Exception)` (has `.errors: list[str]` attribute). `app.jobs.retry_policy.RetryPolicy(max_transport_retries: int = 2, max_validation_retries: int = 3, backoff_seconds: float = 1.0, sleep_fn: Callable[[float], None] = time.sleep)` with `run(self, do_request: Callable[[str | None], dict], schema: dict) -> dict`. `do_request` takes `feedback: str | None` (validation-error feedback to include in the next prompt, `None` on the first attempt) and returns parsed JSON, raising `TransportError` on transport failure. `run` raises `ProviderUnavailableError` or `ExtractionValidationError` when retries are exhausted.

- [ ] **Step 1: Write the failing test**

```python
# tests/jobs/test_retry_policy.py
import pytest

from app.jobs.retry_policy import (
    ExtractionValidationError,
    ProviderUnavailableError,
    RetryPolicy,
    TransportError,
)

SCHEMA = {
    "type": "object",
    "required": ["value"],
    "properties": {"value": {"type": "number"}},
}


def test_returns_result_on_first_success():
    policy = RetryPolicy(sleep_fn=lambda _: None)
    calls = []

    def do_request(feedback):
        calls.append(feedback)
        return {"value": 1}

    result = policy.run(do_request, SCHEMA)
    assert result == {"value": 1}
    assert calls == [None]


def test_retries_transport_errors_then_succeeds():
    policy = RetryPolicy(max_transport_retries=2, sleep_fn=lambda _: None)
    attempts = {"count": 0}

    def do_request(feedback):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise TransportError("boom")
        return {"value": 1}

    result = policy.run(do_request, SCHEMA)
    assert result == {"value": 1}
    assert attempts["count"] == 3


def test_exhausted_transport_retries_raises_provider_unavailable():
    policy = RetryPolicy(max_transport_retries=1, sleep_fn=lambda _: None)

    def do_request(feedback):
        raise TransportError("boom")

    with pytest.raises(ProviderUnavailableError):
        policy.run(do_request, SCHEMA)


def test_validation_retry_passes_feedback_and_eventually_succeeds():
    policy = RetryPolicy(max_validation_retries=2, sleep_fn=lambda _: None)
    feedbacks = []

    def do_request(feedback):
        feedbacks.append(feedback)
        if len(feedbacks) < 2:
            return {"value": "not-a-number"}
        return {"value": 1}

    result = policy.run(do_request, SCHEMA)
    assert result == {"value": 1}
    assert feedbacks[0] is None
    assert feedbacks[1] is not None and "value" in feedbacks[1]


def test_exhausted_validation_retries_raises_with_last_errors():
    policy = RetryPolicy(max_validation_retries=1, sleep_fn=lambda _: None)

    def do_request(feedback):
        return {"value": "not-a-number"}

    with pytest.raises(ExtractionValidationError) as exc_info:
        policy.run(do_request, SCHEMA)
    assert exc_info.value.errors
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_retry_policy.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `app/jobs/retry_policy.py`**

```python
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
            feedback = "Fix these validation errors: " + "; ".join(last_errors)

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/jobs/test_retry_policy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/jobs/retry_policy.py tests/jobs/test_retry_policy.py
git commit -m "feat: RetryPolicy with transport and validation-with-feedback retries"
```

---

### Task 6: AIClient protocol + Gemini client

**Files:**
- Create: `app/ai/__init__.py`, `app/ai/base.py`
- Create: `app/ai/gemini/__init__.py`, `app/ai/gemini/prompts.py`, `app/ai/gemini/client.py`
- Test: `tests/ai/test_gemini_client.py`

**Interfaces:**
- Consumes: `app.jobs.retry_policy.RetryPolicy`, `TransportError` (Task 5).
- Produces: `app.ai.base.AIClient` (`typing.Protocol` with `__call__(self, file_bytes: bytes, mime_type: str, schema: dict, prompt_context: str) -> dict`). `app.ai.gemini.prompts.build_extraction_prompt(prompt_context: str, schema: dict, feedback: str | None) -> str`. `app.ai.gemini.client.GeminiClient(retry_policy: RetryPolicy, api_key: str, model_name: str = "gemini-2.5-flash", sdk_client: Any | None = None)`, implementing `AIClient`. `sdk_client`, when provided, must expose `.models.generate_content(model, contents, config) -> object with a .text: str attribute` (this is the shape tests inject as a fake; production code without `sdk_client` builds a real `google.genai.Client`).

- [ ] **Step 1: Write `app/ai/base.py`**

```python
from __future__ import annotations

from typing import Protocol


class AIClient(Protocol):
    def __call__(
        self, file_bytes: bytes, mime_type: str, schema: dict, prompt_context: str
    ) -> dict: ...
```

- [ ] **Step 2: Write `app/ai/gemini/prompts.py`**

```python
from __future__ import annotations

import json


def build_extraction_prompt(prompt_context: str, schema: dict, feedback: str | None) -> str:
    base = (
        "You are extracting structured lab-result data from the attached document.\n"
        f"{prompt_context}\n"
        "Return ONLY a single JSON object matching this JSON Schema, with no extra "
        "commentary and no markdown fences:\n"
        f"{json.dumps(schema)}"
    )
    if feedback:
        base += f"\n\nYour previous response was invalid. {feedback}"
    return base
```

- [ ] **Step 3: Write the failing test**

```python
# tests/ai/test_gemini_client.py
import json

import pytest

from app.ai.gemini.client import GeminiClient
from app.jobs.retry_policy import RetryPolicy, TransportError

SCHEMA = {
    "type": "object",
    "required": ["value"],
    "properties": {"value": {"type": "number"}},
}


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return _FakeResponse(json.dumps(response))


class _FakeSdkClient:
    def __init__(self, responses):
        self.models = _FakeModels(responses)


def test_call_returns_parsed_json_on_success():
    sdk_client = _FakeSdkClient([{"value": 1}])
    client = GeminiClient(
        retry_policy=RetryPolicy(sleep_fn=lambda _: None),
        api_key="unused",
        sdk_client=sdk_client,
    )

    result = client(b"filebytes", "application/pdf", SCHEMA, "context")

    assert result == {"value": 1}
    assert sdk_client.models.calls[0]["model"] == "gemini-2.5-flash"


def test_call_retries_with_feedback_on_invalid_json_shape():
    sdk_client = _FakeSdkClient([{"value": "not-a-number"}, {"value": 1}])
    client = GeminiClient(
        retry_policy=RetryPolicy(max_validation_retries=1, sleep_fn=lambda _: None),
        api_key="unused",
        sdk_client=sdk_client,
    )

    result = client(b"filebytes", "application/pdf", SCHEMA, "context")

    assert result == {"value": 1}
    assert len(sdk_client.models.calls) == 2
    second_prompt = sdk_client.models.calls[1]["contents"][-1]
    assert "invalid" in second_prompt.lower()


def test_transport_error_from_sdk_is_wrapped_and_retried(monkeypatch):
    class _RaisingModels(_FakeModels):
        def generate_content(self, model, contents, config):
            self.calls.append({"model": model})
            raise RuntimeError("connection reset")

    sdk_client = _FakeSdkClient([])
    sdk_client.models = _RaisingModels([])

    client = GeminiClient(
        retry_policy=RetryPolicy(max_transport_retries=1, sleep_fn=lambda _: None),
        api_key="unused",
        sdk_client=sdk_client,
    )

    with pytest.raises(Exception):
        client(b"filebytes", "application/pdf", SCHEMA, "context")
    assert len(sdk_client.models.calls) == 2
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/ai/test_gemini_client.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 5: Write `app/ai/gemini/client.py`**

```python
from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types

from app.ai.gemini.prompts import build_extraction_prompt
from app.jobs.retry_policy import RetryPolicy, TransportError

DEFAULT_MODEL_NAME = "gemini-2.5-flash"


class GeminiClient:
    def __init__(
        self,
        retry_policy: RetryPolicy,
        api_key: str,
        model_name: str = DEFAULT_MODEL_NAME,
        sdk_client: Any | None = None,
    ) -> None:
        self._retry_policy = retry_policy
        self._model_name = model_name
        self._sdk_client = sdk_client or genai.Client(api_key=api_key)

    def __call__(
        self, file_bytes: bytes, mime_type: str, schema: dict, prompt_context: str
    ) -> dict:
        def do_request(feedback: str | None) -> dict:
            prompt = build_extraction_prompt(prompt_context, schema, feedback)
            try:
                response = self._sdk_client.models.generate_content(
                    model=self._model_name,
                    contents=[
                        types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                        prompt,
                    ],
                    config={"response_mime_type": "application/json"},
                )
            except Exception as exc:  # SDK-level transport/timeout errors
                raise TransportError(str(exc)) from exc
            return json.loads(response.text)

        return self._retry_policy.run(do_request, schema)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/ai/test_gemini_client.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/ai tests/ai
git commit -m "feat: AIClient protocol and self-retrying Gemini client"
```

---

### Task 7: AI client registry

**Files:**
- Create: `app/ai/registry.py`
- Test: `tests/ai/test_registry.py`

**Interfaces:**
- Consumes: `app.ai.base.AIClient`, `app.ai.gemini.client.GeminiClient` (Task 6), `app.jobs.retry_policy.RetryPolicy` (Task 5), `app.core.config.Settings`, `get_settings` (Task 1).
- Produces: `app.ai.registry.build_ai_client_registry(settings: Settings) -> dict[str, AIClient]`, `app.ai.registry.get_ai_client_registry() -> dict[str, AIClient]` (singleton built from `get_settings()`).

- [ ] **Step 1: Write the failing test**

```python
# tests/ai/test_registry.py
from app.ai.registry import build_ai_client_registry
from app.core.config import Settings


def test_registry_has_gemini_client():
    settings = Settings(gemini_api_key="unused-test-key")
    registry = build_ai_client_registry(settings)
    assert "gemini" in registry
    assert callable(registry["gemini"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ai/test_registry.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `app/ai/registry.py`**

```python
from __future__ import annotations

from functools import lru_cache

from app.ai.base import AIClient
from app.ai.gemini.client import GeminiClient
from app.core.config import Settings, get_settings
from app.jobs.retry_policy import RetryPolicy


def build_ai_client_registry(settings: Settings) -> dict[str, AIClient]:
    retry_policy = RetryPolicy(
        max_transport_retries=settings.max_transport_retries,
        max_validation_retries=settings.max_validation_retries,
        backoff_seconds=settings.retry_backoff_seconds,
    )
    return {
        "gemini": GeminiClient(retry_policy=retry_policy, api_key=settings.gemini_api_key),
    }


@lru_cache
def get_ai_client_registry() -> dict[str, AIClient]:
    return build_ai_client_registry(get_settings())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ai/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ai/registry.py tests/ai/test_registry.py
git commit -m "feat: AI client registry mapping model id to AIClient"
```

---

### Task 8: FHIR mapper

**Files:**
- Create: `app/fhir/__init__.py`
- Create: `app/fhir/mapper.py`
- Test: `tests/fhir/test_mapper.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure function operating on plain dicts).
- Produces: `app.fhir.mapper.MappingError(Exception)`. `app.fhir.mapper.map_to_observation(schema_id: str, minimal_data: dict, user_id: str) -> dict`. For `schema_id == "lab_observation"`, maps `{code, display, value, unit, effective_date}` to a FHIR `Observation` dict with `subject.reference = f"Patient/{user_id}"`. Raises `MappingError` for an unknown `schema_id`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fhir/test_mapper.py
import pytest

from app.fhir.mapper import MappingError, map_to_observation


def test_maps_lab_observation_to_fhir_observation():
    minimal = {
        "code": "2093-3",
        "display": "Cholesterol",
        "value": 180,
        "unit": "mg/dL",
        "effective_date": "2026-01-15",
    }

    observation = map_to_observation("lab_observation", minimal, user_id="user-123")

    assert observation["resourceType"] == "Observation"
    assert observation["status"] == "final"
    assert observation["subject"] == {"reference": "Patient/user-123"}
    assert observation["effectiveDateTime"] == "2026-01-15"
    coding = observation["code"]["coding"][0]
    assert coding == {"system": "http://loinc.org", "code": "2093-3", "display": "Cholesterol"}
    assert observation["valueQuantity"] == {
        "value": 180,
        "unit": "mg/dL",
        "system": "http://unitsofmeasure.org",
        "code": "mg/dL",
    }


def test_unknown_schema_id_raises_mapping_error():
    with pytest.raises(MappingError):
        map_to_observation("unknown_schema", {}, user_id="user-123")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/fhir/test_mapper.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `app/fhir/mapper.py`**

```python
from __future__ import annotations


class MappingError(Exception):
    """Raised when minimal extracted data cannot be mapped to a FHIR resource."""


def _map_lab_observation(minimal_data: dict, user_id: str) -> dict:
    return {
        "resourceType": "Observation",
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": minimal_data["code"],
                    "display": minimal_data["display"],
                }
            ]
        },
        "subject": {"reference": f"Patient/{user_id}"},
        "effectiveDateTime": minimal_data["effective_date"],
        "valueQuantity": {
            "value": minimal_data["value"],
            "unit": minimal_data["unit"],
            "system": "http://unitsofmeasure.org",
            "code": minimal_data["unit"],
        },
    }


_MAPPERS = {
    "lab_observation": _map_lab_observation,
}


def map_to_observation(schema_id: str, minimal_data: dict, user_id: str) -> dict:
    mapper = _MAPPERS.get(schema_id)
    if mapper is None:
        raise MappingError(f"no FHIR mapper registered for schema_id={schema_id!r}")
    try:
        return mapper(minimal_data, user_id)
    except KeyError as exc:
        raise MappingError(f"minimal data missing required field: {exc}") from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/fhir/test_mapper.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/fhir/__init__.py app/fhir/mapper.py tests/fhir/test_mapper.py
git commit -m "feat: map minimal extraction JSON to FHIR Observation"
```

---

### Task 9: HL7 validator client

**Files:**
- Create: `app/fhir/validator.py`
- Test: `tests/fhir/test_validator.py`

**Interfaces:**
- Consumes: `app.core.config.Settings` (Task 1).
- Produces: `app.fhir.validator.ValidatorUnavailableError(Exception)`, `app.fhir.validator.FhirValidationError(Exception)` (`.issues: list[str]`). `app.fhir.validator.FhirValidator(base_url: str, http_client: httpx.Client | None = None)` with `validate(self, resource: dict) -> None` — raises `FhirValidationError` if the sidecar reports issues, `ValidatorUnavailableError` on a connection/timeout failure, returns `None` on success. Expects the sidecar's `POST {base_url}/validate` to return JSON `{"valid": bool, "issues": list[str]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fhir/test_validator.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/fhir/test_validator.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `app/fhir/validator.py`**

```python
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
        except httpx.HTTPError as exc:
            raise ValidatorUnavailableError(str(exc)) from exc

        payload = response.json()
        if not payload.get("valid", False):
            raise FhirValidationError(payload.get("issues", []))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/fhir/test_validator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/fhir/validator.py tests/fhir/test_validator.py
git commit -m "feat: HL7 FHIR validator sidecar client"
```

---

### Task 10: Worker pipeline

**Files:**
- Create: `app/jobs/worker.py`
- Test: `tests/jobs/test_worker.py`

**Interfaces:**
- Consumes: `app.jobs.store.JobStore`, `JobRecord` (Task 4); `app.jobs.retry_policy.ProviderUnavailableError`, `ExtractionValidationError` (Task 5); `app.ai.base.AIClient` (Task 6); `app.fhir.mapper.map_to_observation`, `MappingError` (Task 8); `app.fhir.validator.FhirValidator`, `FhirValidationError`, `ValidatorUnavailableError` (Task 9); `app.schemas.registry.SchemaRegistry` (Task 2); `app.models.api.JobStatus`, `JobError` (Task 3).
- Produces: `app.jobs.worker.run_extraction_job(job_id: str, file_bytes: bytes, mime_type: str, client: AIClient, schema: dict, prompt_context: str, schema_id: str, user_id: str, store: JobStore, fhir_validator: FhirValidator) -> None` — an async function driving one job from `PENDING`/`PROCESSING` to a final `SUCCEEDED`/`FAILED` state in `store`.

- [ ] **Step 1: Write the failing test**

```python
# tests/jobs/test_worker.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_worker.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `app/jobs/worker.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/jobs/test_worker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/jobs/worker.py tests/jobs/test_worker.py
git commit -m "feat: worker pipeline orchestrating extraction -> mapping -> FHIR validation"
```

---

### Task 11: API endpoints

**Files:**
- Create: `app/api/__init__.py`, `app/api/extractions.py`
- Modify: `app/main.py`
- Test: `tests/api/test_extractions.py`

**Interfaces:**
- Consumes: `app.jobs.store.get_job_store` (Task 4); `app.schemas.registry.get_schema_registry` (Task 2); `app.ai.registry.get_ai_client_registry` (Task 7); `app.fhir.validator.FhirValidator` (Task 9); `app.jobs.worker.run_extraction_job` (Task 10); `app.models.api.*` (Task 3); `app.core.config.get_settings` (Task 1).
- Produces: `app.api.extractions.router` (`APIRouter`), mounted in `app.main.app` at prefix `""`. Endpoints: `POST /extractions` → `202` `JobCreatedResponse`; `GET /extractions/{job_id}` → `200` `JobStatusResponse`.
- Note: `schema_id` MUST be declared as `Form(...)`, not a bare `str`, because FastAPI treats non-file params as query params (not form fields) once any `UploadFile` param is present — a bare `str` would 422 against the multipart test requests below.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_extractions.py
import io

from app.ai.registry import get_ai_client_registry
from app.fhir.validator import FhirValidator
from app.main import app
from app.schemas.registry import get_schema_registry


def _install_fake_ai_client(monkeypatch, response):
    def fake_client(file_bytes, mime_type, schema, prompt_context):
        return response

    app.dependency_overrides[get_ai_client_registry] = lambda: {"gemini": fake_client}


def _install_fake_validator(monkeypatch):
    class _FakeValidator:
        def validate(self, resource):
            return None

    app.dependency_overrides.setdefault  # no-op to keep monkeypatch import used
    import app.api.extractions as extractions_module

    monkeypatch.setattr(extractions_module, "_build_fhir_validator", lambda: _FakeValidator())


def test_missing_user_id_header_returns_400(client):
    files = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
    response = client.post("/extractions", files=files, data={"schema_id": "lab_observation"})
    assert response.status_code == 400


def test_unknown_schema_id_returns_400(client):
    files = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
    response = client.post(
        "/extractions",
        files=files,
        data={"schema_id": "nope"},
        headers={"X-Viome-User-Id": "user-1"},
    )
    assert response.status_code == 400


def test_unsupported_file_type_returns_400(client):
    files = {"file": ("report.txt", io.BytesIO(b"hello"), "text/plain")}
    response = client.post(
        "/extractions",
        files=files,
        data={"schema_id": "lab_observation"},
        headers={"X-Viome-User-Id": "user-1"},
    )
    assert response.status_code == 400


def test_unknown_ai_model_header_returns_400(client):
    files = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
    response = client.post(
        "/extractions",
        files=files,
        data={"schema_id": "lab_observation"},
        headers={"X-Viome-User-Id": "user-1", "X-AI-Model": "not-a-model"},
    )
    assert response.status_code == 400


def test_get_unknown_job_returns_404(client):
    response = client.get("/extractions/does-not-exist")
    assert response.status_code == 404


def test_full_flow_returns_succeeded_job(client, monkeypatch):
    _install_fake_ai_client(
        monkeypatch,
        {
            "code": "2093-3",
            "display": "Cholesterol",
            "value": 180,
            "unit": "mg/dL",
            "effective_date": "2026-01-15",
        },
    )
    _install_fake_validator(monkeypatch)

    files = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
    create_response = client.post(
        "/extractions",
        files=files,
        data={"schema_id": "lab_observation"},
        headers={"X-Viome-User-Id": "user-1"},
    )
    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    status_response = client.get(f"/extractions/{job_id}")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["status"] == "succeeded"
    assert body["result"]["resourceType"] == "Observation"
    assert body["result"]["subject"] == {"reference": "Patient/user-1"}

    app.dependency_overrides.clear()
```

Note: `TestClient` runs `BackgroundTasks` synchronously before returning the response, so the job is already finished by the time `GET` is called.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_extractions.py -v`
Expected: FAIL with `ImportError` / 404s on `/extractions`

- [ ] **Step 3: Write `app/api/extractions.py`**

```python
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
```

- [ ] **Step 4: Modify `app/main.py` to mount the router**

```python
from fastapi import FastAPI

from app.api.extractions import router as extractions_router

app = FastAPI(title="Viome Document Intelligence")
app.include_router(extractions_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/api/test_extractions.py -v`
Expected: PASS

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tasks so far)

- [ ] **Step 7: Commit**

```bash
git add app/api app/main.py tests/api/test_extractions.py
git commit -m "feat: POST/GET /extractions API endpoints"
```

---

### Task 12: FHIR Implementation Guide (FSH profile)

**Files:**
- Create: `fhir-ig/sushi-config.yaml`
- Create: `fhir-ig/input/fsh/observation.fsh`

**Interfaces:**
- Consumes: nothing (build-time artifact consumed by the validator sidecar in Task 13).
- Produces: on `sushi build .` inside `fhir-ig/`, a `fhir-ig/output/` directory containing `StructureDefinition-viome-lab-observation.json` (the compiled profile) plus the base IG resources.

- [ ] **Step 1: Write `fhir-ig/sushi-config.yaml`**

```yaml
canonical: http://viome.com/fhir/document-intelligence
name: ViomeDocumentIntelligenceIG
id: viome.fhir.document-intelligence
status: draft
version: 0.1.0
fhirVersion: 4.0.1
copyrightYear: 2026+
releaseLabel: ci-build
publisher:
  name: Viome
parameters:
  show-inherited-invariants: false
```

- [ ] **Step 2: Write `fhir-ig/input/fsh/observation.fsh`**

```fsh
Profile: ViomeLabObservation
Parent: Observation
Id: viome-lab-observation
Title: "Viome Lab Observation"
Description: "A single lab result extracted from an uploaded report, scoped to Viome's document intelligence pipeline."

* status = #final (exactly)
* code 1..1 MS
* code.coding 1..* MS
* code.coding.system 1..1 MS
* code.coding.code 1..1 MS
* subject 1..1 MS
* subject.reference 1..1
* subject.reference obeys viome-subject-is-patient-reference
* effectiveDateTime 1..1 MS
* value[x] 1..1 MS
* valueQuantity only Quantity
* valueQuantity.value 1..1
* valueQuantity.unit 1..1
* valueQuantity.system 1..1
* valueQuantity.code 1..1

Invariant: viome-subject-is-patient-reference
Description: "Observation.subject.reference must point at a Patient resource."
Expression: "startsWith('Patient/')"
Severity: #error
```

- [ ] **Step 3: Compile the IG with SUSHI (verifies the FSH is valid)**

Run (requires Node.js; installs SUSHI globally if not present):
```bash
npm install -g fsh-sushi
cd fhir-ig && sushi build .
```
Expected: `SUSHI STATUS: SUCCESS` and `fhir-ig/output/StructureDefinition-viome-lab-observation.json` exists.

- [ ] **Step 4: Commit**

```bash
git add fhir-ig/sushi-config.yaml fhir-ig/input
git commit -m "feat: FSH profile for the Viome lab Observation resource"
```

---

### Task 13: Dockerization (app + HL7 validator sidecar)

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `docker/validator/Dockerfile`
- Create: `docker/validator/server.py`

**Interfaces:**
- Consumes: `fhir-ig/output/` (Task 12, produced during the validator image build), `app/` (this task's `Dockerfile`).
- Produces: two Docker images (`app`, `validator`) wired together by `docker-compose.yml`; the validator image exposes `POST /validate` on port `8090` matching `app.fhir.validator.FhirValidator`'s expected contract (`{"valid": bool, "issues": list[str]}`), backed internally by shelling out to `validator_cli.jar` against the compiled IG.

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write `docker/validator/server.py`**

A small FastAPI shim that shells out to `validator_cli.jar` per request against the compiled IG package and normalizes its output into `{"valid": bool, "issues": list[str]}`.

```python
import json
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, Request

app = FastAPI(title="HL7 FHIR Validator Sidecar")

IG_PATH = Path("/ig/output")
VALIDATOR_JAR = Path("/opt/validator_cli.jar")


@app.post("/validate")
async def validate(request: Request) -> dict:
    resource = await request.json()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json.dump(resource, tmp)
        tmp_path = tmp.name

    result = subprocess.run(
        [
            "java",
            "-jar",
            str(VALIDATOR_JAR),
            tmp_path,
            "-ig",
            str(IG_PATH),
            "-output",
            f"{tmp_path}.out.json",
            "-output-style",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    issues: list[str] = []
    output_path = Path(f"{tmp_path}.out.json")
    if output_path.exists():
        outcome = json.loads(output_path.read_text())
        for issue in outcome.get("issues", []):
            if issue.get("severity") in ("error", "fatal"):
                issues.append(issue.get("message", "unknown validation error"))
    elif result.returncode != 0:
        issues.append(result.stderr.strip() or "validator_cli failed with no output")

    return {"valid": not issues, "issues": issues}
```

- [ ] **Step 3: Write `docker/validator/Dockerfile`**

```dockerfile
FROM eclipse-temurin:21-jre AS validator-jar
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN curl -L -o /opt/validator_cli.jar \
    https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/download/validator_cli.jar

FROM node:20-slim AS ig-build
WORKDIR /ig
RUN npm install -g fsh-sushi
COPY fhir-ig/ .
RUN sushi build .

FROM eclipse-temurin:21-jre
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*
COPY --from=validator-jar /opt/validator_cli.jar /opt/validator_cli.jar
COPY --from=ig-build /ig/output /ig/output
WORKDIR /srv
COPY docker/validator/server.py .
RUN pip3 install --no-cache-dir --break-system-packages fastapi uvicorn
EXPOSE 8090
CMD ["python3", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8090"]
```

- [ ] **Step 4: Write `docker-compose.yml`**

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      GEMINI_API_KEY: ${GEMINI_API_KEY:-changeme}
      FHIR_VALIDATOR_URL: http://validator:8090
    depends_on:
      - validator

  validator:
    build:
      context: .
      dockerfile: docker/validator/Dockerfile
    ports:
      - "8090:8090"
```

- [ ] **Step 5: Build and smoke-test both containers**

Run: `docker compose build && docker compose up -d`
Then: `curl -s http://localhost:8000/health` → expect `{"status":"ok"}`
Then: `curl -s -X POST http://localhost:8090/validate -H 'Content-Type: application/json' -d '{"resourceType":"Observation","status":"final","code":{"coding":[{"system":"http://loinc.org","code":"2093-3"}]},"subject":{"reference":"Patient/user-1"},"effectiveDateTime":"2026-01-15","valueQuantity":{"value":180,"unit":"mg/dL","system":"http://unitsofmeasure.org","code":"mg/dL"}}'` → expect `{"valid":true,"issues":[]}`
Then: `docker compose down`

- [ ] **Step 6: Commit**

```bash
git add Dockerfile docker-compose.yml docker/validator
git commit -m "chore: dockerize app and HL7 FHIR validator sidecar"
```

---

### Task 14: README

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: developer-facing documentation only.

- [ ] **Step 1: Write `README.md`**

```markdown
# Viome Document Intelligence

FastAPI service that extracts structured lab-result data from uploaded
reports (PDF/JPEG/PNG) via Gemini, maps it into a FHIR `Observation`, and
validates it against a custom FHIR profile.

## Local development

    pip install -r requirements.txt
    cp .env.example .env  # fill in GEMINI_API_KEY
    uvicorn app.main:app --reload

## Running with Docker (app + FHIR validator sidecar)

    docker compose up --build

## Tests

    pytest -v

## API

- `POST /extractions` — multipart `file` + `schema_id` fields, headers
  `X-Viome-User-Id` (required) and `X-AI-Model` (optional, defaults to
  `gemini`). Returns `202 {"job_id": "..."}`.
- `GET /extractions/{job_id}` — returns job status and, once `succeeded`,
  the FHIR `Observation` result.

See `docs/superpowers/specs/2026-09-10-document-intelligence-design.md`
for the full design.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```
