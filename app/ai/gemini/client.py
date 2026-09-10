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
