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
