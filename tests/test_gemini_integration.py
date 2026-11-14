from __future__ import annotations

import unittest
from unittest.mock import patch

import backend.services.mannmitra_service as service_module
from backend.services.mannmitra_service import GeminiGenerationError, MannMitraService
from rag_engine import RAGContext


class _FailingModels:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def generate_content(self, **_kwargs):
        raise self.error


class _FailingClient:
    def __init__(self, error: Exception) -> None:
        self.models = _FailingModels(error)


class _ProviderAuthError(RuntimeError):
    status_code = 401


class GeminiIntegrationTests(unittest.TestCase):
    def service(self) -> MannMitraService:
        service = object.__new__(MannMitraService)
        service.gemini_available = True
        service.gemini_model = "test-model"
        return service

    def test_authentication_failure_is_categorized_without_fallback(self) -> None:
        error = _ProviderAuthError("provider rejected authentication")
        with patch.object(service_module, "_genai_client", _FailingClient(error)), patch.object(service_module, "_genai_types", None):
            with self.assertRaises(GeminiGenerationError) as raised:
                self.service().generate_reply("hello", [], RAGContext(is_used=False))
        self.assertEqual(raised.exception.category, "authentication")
        self.assertNotIn("API key", raised.exception.public_detail)

    def test_timeout_is_categorized_without_prompt_logging(self) -> None:
        error = TimeoutError("request timed out")
        with patch.object(service_module, "_genai_client", _FailingClient(error)), patch.object(service_module, "_genai_types", None):
            with self.assertRaises(GeminiGenerationError) as raised:
                self.service().generate_reply("private message", [], RAGContext(is_used=False))
        self.assertEqual(raised.exception.category, "timeout")
        self.assertNotIn("private message", raised.exception.public_detail)


if __name__ == "__main__":
    unittest.main()
