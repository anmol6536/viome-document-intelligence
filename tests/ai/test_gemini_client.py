import json
import time

import pytest

from app.ai.gemini.client import GeminiClient
from app.jobs.retry_policy import ProviderUnavailableError, RetryPolicy, TransportError

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
    assert sdk_client.models.calls[0]["model"] == "gemini-3.1-flash-lite"


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


def test_call_raises_provider_unavailable_when_sdk_call_hangs_past_timeout():
    class _SlowModels(_FakeModels):
        def generate_content(self, model, contents, config):
            time.sleep(0.2)  # longer than the client's request_timeout_seconds below
            return _FakeResponse(json.dumps({"value": 1}))

    sdk_client = _FakeSdkClient([])
    sdk_client.models = _SlowModels([])

    client = GeminiClient(
        retry_policy=RetryPolicy(max_transport_retries=0, sleep_fn=lambda _: None),
        api_key="unused",
        sdk_client=sdk_client,
        request_timeout_seconds=0.01,
    )

    with pytest.raises(ProviderUnavailableError):
        client(b"filebytes", "application/pdf", SCHEMA, "context")
