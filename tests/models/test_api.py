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
