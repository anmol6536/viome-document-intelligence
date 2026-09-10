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
        "gemini": GeminiClient(
            retry_policy=retry_policy,
            api_key=settings.gemini_api_key,
            request_timeout_seconds=settings.gemini_request_timeout_seconds,
        ),
    }


@lru_cache
def get_ai_client_registry() -> dict[str, AIClient]:
    return build_ai_client_registry(get_settings())
