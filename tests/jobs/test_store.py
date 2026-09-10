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


@pytest.mark.asyncio
async def test_update_unknown_job_raises_key_error():
    store = JobStore()
    with pytest.raises(KeyError, match="no job found with id"):
        await store.update("does-not-exist", status=JobStatus.SUCCEEDED)
