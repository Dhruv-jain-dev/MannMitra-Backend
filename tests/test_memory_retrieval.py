from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from backend.core.database import Database
from backend.models import Conversation, Message, User
from backend.repositories.conversations import ConversationRepository
from backend.services.mannmitra_service import MannMitraService


class _SemanticMemory:
    @staticmethod
    def semantic_similarities(query: str, passages: list[str]) -> list[float]:
        return [0.78, 0.05][: len(passages)]


class _UnavailableSemanticMemory:
    @staticmethod
    def semantic_similarities(query: str, passages: list[str]) -> list[float]:
        raise RuntimeError("embedding service unavailable")


class MemoryRetrievalTests(unittest.TestCase):
    def service(self, semantic_engine=None) -> MannMitraService:
        service = object.__new__(MannMitraService)
        service.rag_engine = semantic_engine or _SemanticMemory()
        return service

    def test_explicit_recall_phrasings_are_detected(self) -> None:
        prompts = (
            "What did you tell me previously?",
            "Can you remind me what we discussed?",
            "What did I say in our previous chat?",
        )
        self.assertTrue(all(MannMitraService.is_explicit_memory_request(prompt) for prompt in prompts))

    def test_topical_recall_prefers_relevant_message_over_newer_unrelated_message(self) -> None:
        candidates = [
            {"content": "I am worried about my maths exam next week.", "created_at": 1},
            {"content": "I enjoyed cooking dinner with my roommate.", "created_at": 3},
        ]
        selected = self.service().select_previous_memory(
            "What did you tell me previously about the upcoming test?", candidates
        )
        self.assertEqual(selected, [candidates[0]])

    def test_semantic_recall_handles_different_wording(self) -> None:
        candidates = [
            {"content": "My maths exam is next Monday and I am worried.", "created_at": 2},
            {"content": "I enjoy cooking dinner on weekends.", "created_at": 1},
        ]
        selected = self.service().select_previous_memory(
            "I want to talk to my teacher about that assessment.", candidates
        )
        self.assertEqual(selected, [candidates[0]])

    def test_empty_or_unavailable_memory_returns_empty(self) -> None:
        self.assertEqual(self.service().select_previous_memory("What did you tell me previously?", []), [])
        candidates = [{"content": "An old message", "created_at": 1}]
        self.assertEqual(
            self.service(_UnavailableSemanticMemory()).select_previous_memory(
                "What did you tell me previously about exams?", candidates
            ),
            [],
        )

    def test_repository_memory_candidates_are_user_scoped(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            database = Database(f"sqlite:///{(Path(temp_dir.name) / 'memory.db').as_posix()}")
            database.create_all()
            now = datetime.now(timezone.utc)
            with database.session_factory() as session:
                user_a = User(id="user-a")
                user_b = User(id="user-b")
                current = Conversation(id="current", user=user_a)
                prior_a = Conversation(id="prior-a", user=user_a)
                prior_b = Conversation(id="prior-b", user=user_b)
                session.add_all([
                    user_a,
                    user_b,
                    current,
                    prior_a,
                    prior_b,
                    Message(conversation=prior_a, position=1, role="user", content="User A exam concern", created_at=now),
                    Message(conversation=prior_b, position=1, role="user", content="User B private concern", created_at=now + timedelta(seconds=1)),
                ])
                session.commit()
            repository = ConversationRepository(database.session_factory)
            candidates = repository.previous_memory_candidates("user-a", "current")
            self.assertEqual([item["content"] for item in candidates], ["User A exam concern"])
            database.dispose()
        finally:
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
