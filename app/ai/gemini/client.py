from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from google import genai
from google.genai import types

from app.ai.gemini.prompts import build_extraction_prompt
from app.jobs.retry_policy import RetryPolicy, TransportError

DEFAULT_MODEL_NAME = "gemini-3.6-flash"
# The installed google-genai SDK version (0.3.0) has no built-in request
# timeout, and its calls are synchronous/blocking. Without a bound, a stalled
# Gemini response hangs this call forever - and since this runs inside the
# async worker, that freezes the whole event loop, not just this one job.
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0


class GeminiClient:
    def __init__(
        self,
        retry_policy: RetryPolicy,
        api_key: str,
        model_name: str = DEFAULT_MODEL_NAME,
        sdk_client: Any | None = None,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._retry_policy = retry_policy
        self._model_name = model_name
        self._sdk_client = sdk_client or genai.Client(api_key=api_key)
        self._request_timeout_seconds = request_timeout_seconds

    def __call__(
        self, file_bytes: bytes, mime_type: str, schema: dict, prompt_context: str
    ) -> dict:
        def do_request(feedback: str | None) -> dict:
            prompt = build_extraction_prompt(prompt_context, schema, feedback)

            def call_sdk() -> str:
                response = self._sdk_client.models.generate_content(
                    model=self._model_name,
                    contents=[
                        types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                        prompt,
                    ],
                    config={"response_mime_type": "application/json"},
                )
                return response.text

            executor = ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(call_sdk)
                try:
                    response_text = future.result(timeout=self._request_timeout_seconds)
                except FutureTimeoutError as exc:
                    raise TransportError(
                        f"Gemini request timed out after {self._request_timeout_seconds}s"
                    ) from exc
                return json.loads(response_text)
            except TransportError:
                raise
            except Exception as exc:  # SDK-level transport errors, or malformed JSON
                raise TransportError(str(exc)) from exc
            finally:
                # Don't block on the stuck thread finishing - a timed-out SDK
                # call can't be killed, but we can stop waiting on it here.
                executor.shutdown(wait=False, cancel_futures=True)

        return self._retry_policy.run(do_request, schema)
