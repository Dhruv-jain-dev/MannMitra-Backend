from __future__ import annotations

import unittest
from unittest.mock import patch

import backend.services.mannmitra_service as service_module
from backend.services.mannmitra_service import MannMitraService
from rag_engine import RAGContext


class _FakeResponse:
    text = "A grounded supportive reply."


class _FakeModels:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate_content(self, *, model: str, contents: str, config=None):
        self.prompts.append(contents)
        return _FakeResponse()


class _FakeClient:
    def __init__(self) -> None:
        self.models = _FakeModels()


class RagGroundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = object.__new__(MannMitraService)
        self.service.gemini_available = True
        self.service.gemini_model = "test-model"
        self.client = _FakeClient()

    def generate(self, rag_context: RAGContext) -> str:
        with patch.object(service_module, "_genai_client", self.client), patch.object(
            service_module, "_genai_types", None
        ):
            return self.service.generate_reply(
                "How can I manage my exam stress?",
                [{"role": "user", "content": "I have a lot to do."}],
                rag_context,
                previous_memory=[{"content": "I mentioned a maths exam earlier."}],
            )

    def test_relevant_chunks_are_included_as_separate_grounding_context(self) -> None:
        self.generate(
            RAGContext(
                is_used=True,
                retrieved_documents=["Break the task into one small first step."],
                sources=["academic_paralysis.txt"],
            )
        )
        prompt = self.client.models.prompts[0]
        self.assertIn("Conversation history", prompt)
        self.assertIn("Relevant previous-chat memory", prompt)
        self.assertIn("Retrieved support context (not conversation history)", prompt)
        self.assertIn("Break the task into one small first step.", prompt)
        self.assertIn("Use retrieved support context only when it helps", prompt)
        self.assertIn("never invent medical or psychological claims", prompt)

    def test_empty_retrieval_does_not_add_empty_grounding_section(self) -> None:
        self.generate(RAGContext(is_used=True, retrieved_documents=["", "  "], sources=[]))
        prompt = self.client.models.prompts[0]
        self.assertNotIn("Retrieved support context", prompt)
        self.assertIn("Current student's message", prompt)

    def test_unused_retrieval_preserves_generation_and_fallback_shape(self) -> None:
        reply = self.generate(RAGContext(is_used=False))
        prompt = self.client.models.prompts[0]
        self.assertEqual(reply, "A grounded supportive reply.")
        self.assertNotIn("Retrieved support context", prompt)


if __name__ == "__main__":
    unittest.main()
