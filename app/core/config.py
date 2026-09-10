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
