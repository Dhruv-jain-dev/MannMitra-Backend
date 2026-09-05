from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from backend.core.config import Settings
from backend.main import create_app
from backend.services.mannmitra_service import MannMitraService, TurnResult
from rag_engine import RAGContext
from risk_analysis import EmotionResult, RiskAssessment


class StubMannMitraService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict], list[float]]] = []
        self.previous_memories: list[list[dict]] = []
        self.memory_lookups: list[bool] = []
        self.voice_calls: list[tuple[bytes, str]] = []

    def process_turn(
        self,
        text: str,
        chat_history: list[dict],
        history_scores: list[float],
        voice_diagnostics: dict | None = None,
        previous_memory: list[dict] | None = None,
        memory_lookup_attempted: bool = False,
    ) -> TurnResult:
        self.calls.append((text, chat_history, history_scores))
        self.previous_memories.append(previous_memory or [])
        self.memory_lookups.append(memory_lookup_attempted)
        return TurnResult(
            assistant_response="- Stubbed supportive reply",
            emotion=EmotionResult(label="neutral", score=1.0, all_emotions={"neutral": 1.0}),
            assessment=RiskAssessment(tier="GREEN", score=0.1),
            rag_context=RAGContext(is_used=False),
            voice_diagnostics=voice_diagnostics,
        )

    @staticmethod
    def is_explicit_memory_request(text: str) -> bool:
        return "earlier" in text.casefold() or "previous" in text.casefold() or "yesterday" in text.casefold()

    @staticmethod
    def select_previous_memory(query: str, candidates: list[dict]) -> list[dict]:
        query_terms = set(query.casefold().replace("?", "").split())
        relevant = [item for item in candidates if query_terms & set(item["content"].casefold().replace(".", "").split())]
        return relevant[:1] or (candidates[:1] if StubMannMitraService.is_explicit_memory_request(query) else [])

    def process_voice_input(self, audio_bytes: bytes, suffix: str) -> dict:
        self.voice_calls.append((audio_bytes, suffix))
        return {
            "transcript": "Voice transcript",
            "transcript_warning": None,
            "duration": 1.2,
            "acoustic_stress": 42.0,
            "vocal_tone": "calm",
            "acoustic_available": False,
            "fusion_source": "transcript-only (no fine-tuned acoustic weights found)",
        }


class Phase2PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_url = f"sqlite:///{(Path(self.temp_dir.name) / 'test.db').as_posix()}"
        self.service = StubMannMitraService()
        self.app = create_app(
            Settings(
                app_name="MannMitra Test",
                environment="test",
                database_url=database_url,
                auth_jwt_secret="test-auth-secret",
            ),
            service_factory=lambda: self.service,
        )
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def create_conversation(self) -> str:
        response = self.client.post("/api/conversations", json={"title": "Test"}, headers=self.headers_for("student-1"))
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def headers_for(self, user_id: str) -> dict[str, str]:
        token = self.app.state.auth_service.create_access_token(user_id)
        return {"Authorization": f"Bearer {token}"}

    def test_conversation_creation_and_listing(self) -> None:
        table_names = set(inspect(self.app.state.database.engine).get_table_names())
        self.assertTrue({"users", "conversations", "messages", "message_analyses"}.issubset(table_names))
        conversation_id = self.create_conversation()
        response = self.client.get("/api/conversations", headers=self.headers_for("student-1"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [conversation_id])

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "mannmitra-backend"})

    def test_text_persistence_and_idempotency(self) -> None:
        conversation_id = self.create_conversation()
        payload = {
            "conversation_id": conversation_id,
            "request_id": "request-1",
            "text": "I feel tired today",
        }
        first = self.client.post("/api/mannmitra/text", json=payload, headers=self.headers_for("student-1"))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["risk"]["tier"], "GREEN")
        duplicate = self.client.post("/api/mannmitra/text", json=payload, headers=self.headers_for("student-1"))
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.json(), first.json())
        self.assertEqual(len(self.service.calls), 1)

        messages = self.client.get(
            f"/api/conversations/{conversation_id}/messages", headers=self.headers_for("student-1")
        )
        self.assertEqual(messages.status_code, 200)
        self.assertEqual([message["role"] for message in messages.json()], ["user", "assistant"])
        self.assertIsNotNone(messages.json()[0]["analysis"])

    def test_voice_persistence_analytics_and_idempotency(self) -> None:
        conversation_id = self.create_conversation()
        data = {"conversation_id": conversation_id, "request_id": "voice-request-1"}
        files = {"audio": ("recording.wav", BytesIO(b"fake-wav"), "audio/wav")}
        first = self.client.post("/api/mannmitra/voice", data=data, files=files, headers=self.headers_for("student-1"))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["voice"]["transcript"], "Voice transcript")
        duplicate = self.client.post(
            "/api/mannmitra/voice",
            data=data,
            files={"audio": ("recording.wav", BytesIO(b"fake-wav"), "audio/wav")},
            headers=self.headers_for("student-1"),
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(len(self.service.voice_calls), 1)
        self.assertEqual(len(self.service.calls), 1)

        analytics = self.client.get(
            f"/api/conversations/{conversation_id}/analytics", headers=self.headers_for("student-1")
        )
        self.assertEqual(analytics.status_code, 200)
        self.assertEqual(analytics.json()["latest"]["risk"]["tier"], "GREEN")
        self.assertEqual(analytics.json()["latest_voice"]["vocal_tone"], "calm")
        self.assertEqual(analytics.json()["risk_history"], [0.1])

    def test_voice_upload_validation_and_malformed_text(self) -> None:
        conversation_id = self.create_conversation()
        malformed_text = self.client.post(
            "/api/mannmitra/text",
            json={"conversation_id": conversation_id, "request_id": "bad-text", "text": ""},
            headers=self.headers_for("student-1"),
        )
        self.assertEqual(malformed_text.status_code, 422)
        unsupported = self.client.post(
            "/api/mannmitra/voice",
            data={"conversation_id": conversation_id, "request_id": "bad-audio"},
            files={"audio": ("recording.txt", BytesIO(b"not audio"), "text/plain")},
            headers=self.headers_for("student-1"),
        )
        self.assertEqual(unsupported.status_code, 415)

    def test_voice_upload_size_limit(self) -> None:
        database_url = f"sqlite:///{(Path(self.temp_dir.name) / 'small-limit.db').as_posix()}"
        limited_app = create_app(
            Settings(
                app_name="MannMitra Test",
                environment="test",
                database_url=database_url,
                auth_jwt_secret="test-auth-secret",
                max_audio_upload_bytes=3,
            ),
            service_factory=StubMannMitraService,
        )
        with TestClient(limited_app) as client:
            token = limited_app.state.auth_service.create_access_token("student-1")
            headers = {"Authorization": f"Bearer {token}"}
            conversation = client.post("/api/conversations", json={"title": "Small"}, headers=headers).json()
            response = client.post(
                "/api/mannmitra/voice",
                data={"conversation_id": conversation["id"], "request_id": "too-large"},
                files={"audio": ("recording.wav", BytesIO(b"four"), "audio/wav")},
                headers=headers,
            )
            self.assertEqual(response.status_code, 413)

    def test_persisted_context_and_risk_history_are_reused(self) -> None:
        conversation_id = self.create_conversation()
        for request_id, text in (("request-1", "First turn"), ("request-2", "Second turn")):
            response = self.client.post(
                "/api/mannmitra/text",
                json={
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                    "text": text,
                },
                headers=self.headers_for("student-1"),
            )
            self.assertEqual(response.status_code, 200)
        _, second_history, second_scores = self.service.calls[1]
        self.assertEqual([turn["role"] for turn in second_history], ["user", "assistant", "user"])
        self.assertEqual(second_scores, [0.1])

    def test_conversations_receive_distinct_dynamic_titles(self) -> None:
        conversations = [self.client.post("/api/conversations", json={}, headers=self.headers_for("student-1")).json() for _ in range(4)]
        for conversation_id, request_id, text in (
            (conversations[0]["id"], "title-1", "I'm really stressed about my maths exam next week."),
            (conversations[1]["id"], "title-2", "I had an argument with my roommate."),
            (conversations[2]["id"], "title-3", "How can I improve my sleep schedule?"),
            (conversations[3]["id"], "title-4", "I don't know how to talk to my professor."),
        ):
            response = self.client.post(
                "/api/mannmitra/text",
                json={"conversation_id": conversation_id, "request_id": request_id, "text": text},
                headers=self.headers_for("student-1"),
            )
            self.assertEqual(response.status_code, 200)
        titles = {item["id"]: item["title"] for item in self.client.get("/api/conversations", headers=self.headers_for("student-1")).json()}
        self.assertEqual(titles[conversations[0]["id"]], "Maths Exam Stress")
        self.assertEqual(titles[conversations[1]["id"]], "Roommate Conflict")
        self.assertEqual(titles[conversations[2]["id"]], "Improving Sleep Schedule")
        self.assertEqual(titles[conversations[3]["id"]], "Talking to Professor")
        self.assertEqual(len(set(titles.values())), 4)

    def test_legacy_fixed_title_is_backfilled_from_first_message(self) -> None:
        conversation = self.client.post(
            "/api/conversations", json={"title": "Exam Stress & Planning"}, headers=self.headers_for("student-1")
        ).json()
        self.client.post(
            "/api/mannmitra/text",
            json={"conversation_id": conversation["id"], "request_id": "legacy-title", "text": "I had an argument with my roommate."},
            headers=self.headers_for("student-1"),
        )
        listed = self.client.get("/api/conversations", headers=self.headers_for("student-1")).json()
        title = next(item["title"] for item in listed if item["id"] == conversation["id"])
        self.assertEqual(title, "Roommate Conflict")

    def test_short_greeting_waits_for_a_meaningful_title_message(self) -> None:
        conversation = self.client.post("/api/conversations", json={}, headers=self.headers_for("student-1")).json()
        for request_id, text in (("greeting", "Hi"), ("meaningful", "I need help with my project deadline.")):
            self.client.post(
                "/api/mannmitra/text",
                json={"conversation_id": conversation["id"], "request_id": request_id, "text": text},
                headers=self.headers_for("student-1"),
            )
        listed = self.client.get("/api/conversations", headers=self.headers_for("student-1")).json()
        title = next(item["title"] for item in listed if item["id"] == conversation["id"])
        self.assertEqual(title, "Need Help Project Deadline")

    def test_relevant_previous_chat_memory_is_user_scoped(self) -> None:
        earlier = self.create_conversation()
        initial = "My mathematics exam starts on September 15 and I am really worried about it."
        self.client.post(
            "/api/mannmitra/text",
            json={"conversation_id": earlier, "request_id": "earlier-exam", "text": initial},
            headers=self.headers_for("student-1"),
        )
        other_conversation = self.client.post("/api/conversations", json={}, headers=self.headers_for("student-2")).json()["id"]
        other_text = "My exams are on a completely different date."
        self.client.post(
            "/api/mannmitra/text",
            json={"conversation_id": other_conversation, "request_id": "other-exam", "text": other_text},
            headers=self.headers_for("student-2"),
        )
        current = self.create_conversation()
        response = self.client.post(
            "/api/mannmitra/text",
            json={"conversation_id": current, "request_id": "recall-exam", "text": "I told you earlier about my exams. What did I say?"},
            headers=self.headers_for("student-1"),
        )
        self.assertEqual(response.status_code, 200)
        memory = self.service.previous_memories[-1]
        self.assertIn(initial, [item["content"] for item in memory])
        self.assertNotIn(other_text, [item["content"] for item in memory])
        self.assertTrue(self.service.memory_lookups[-1])

    def test_explicit_recall_without_prior_data_is_marked_for_safe_no_memory_response(self) -> None:
        current = self.create_conversation()
        response = self.client.post(
            "/api/mannmitra/text",
            json={"conversation_id": current, "request_id": "no-memory", "text": "What did we discuss yesterday?"},
            headers=self.headers_for("student-1"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.service.previous_memories[-1], [])
        self.assertTrue(self.service.memory_lookups[-1])

    def test_no_memory_reply_says_the_prior_information_was_not_found(self) -> None:
        service = object.__new__(MannMitraService)
        service.gemini_available = False
        reply = service.generate_reply(
            "What did we discuss yesterday?",
            [],
            RAGContext(is_used=False),
            previous_memory=[],
            memory_lookup_attempted=True,
        )
        self.assertIn("couldn't find matching information in your previous conversations", reply)

    def test_representative_explicit_recall_phrasings_are_detected(self) -> None:
        prompts = (
            "What did I tell you earlier about my exams?",
            "What did I say in our previous chat?",
            "Do you remember what I told you about my maths exam?",
            "What did we discuss about my exams?",
            "Did I tell you anything earlier about my maths exam?",
            "What did I say in our previous chat about exams?",
            "What did we discuss yesterday?",
        )
        self.assertTrue(all(MannMitraService.is_explicit_memory_request(prompt) for prompt in prompts))

    def test_semantic_memory_selection_can_continue_a_related_topic(self) -> None:
        class SemanticRag:
            @staticmethod
            def semantic_similarities(query: str, passages: list[str]) -> list[float]:
                return [0.72, 0.11]

        service = object.__new__(MannMitraService)
        service.rag_engine = SemanticRag()
        candidates = [
            {"content": "My maths exam is next Monday and I am worried.", "created_at": 2},
            {"content": "I enjoy cooking dinner on weekends.", "created_at": 1},
        ]
        selected = service.select_previous_memory("I want to talk to my teacher. How should I?", candidates)
        self.assertEqual(selected, [candidates[0]])

    def test_authentication_and_conversation_ownership(self) -> None:
        conversation_id = self.create_conversation()
        self.assertEqual(self.client.get("/api/conversations").status_code, 401)
        self.assertEqual(
            self.client.get("/api/conversations", headers={"Authorization": "Bearer invalid.token.value"}).status_code,
            401,
        )
        self.assertEqual(
            self.client.get(
                f"/api/conversations/{conversation_id}/messages", headers=self.headers_for("student-2")
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/conversations/{conversation_id}/analytics", headers=self.headers_for("student-2")
            ).status_code,
            404,
        )
        response = self.client.post(
            "/api/mannmitra/text",
            json={"conversation_id": conversation_id, "request_id": "other-user-request", "text": "Not mine"},
            headers=self.headers_for("student-2"),
        )
        self.assertEqual(response.status_code, 404)
        listed = self.client.get("/api/conversations", headers=self.headers_for("student-2"))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json(), [])


if __name__ == "__main__":
    unittest.main()
