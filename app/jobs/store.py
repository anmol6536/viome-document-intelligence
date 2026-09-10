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
            if job_id not in self._jobs:
                raise KeyError(f"no job found with id={job_id!r}")
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
