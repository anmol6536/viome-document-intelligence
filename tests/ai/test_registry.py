from app.ai.registry import build_ai_client_registry
from app.core.config import Settings


def test_registry_has_gemini_client():
    settings = Settings(gemini_api_key="unused-test-key")
    registry = build_ai_client_registry(settings)
    assert "gemini" in registry
    assert callable(registry["gemini"])
