from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from backend.core.config import Settings
from backend.main import create_app
from backend.services.mannmitra_service import TurnResult
from rag_engine import RAGContext
from risk_analysis import EmotionResult, RiskAssessment


class StubMannMitraService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict], list[float]]] = []
        self.voice_calls: list[tuple[bytes, str]] = []

    def process_turn(
        self,
        text: str,
        chat_history: list[dict],
        history_scores: list[float],
        voice_diagnostics: dict | None = None,
    ) -> TurnResult:
        self.calls.append((text, chat_history, history_scores))
        return TurnResult(
            assistant_response="- Stubbed supportive reply",
            emotion=EmotionResult(label="neutral", score=1.0, all_emotions={"neutral": 1.0}),
            assessment=RiskAssessment(tier="GREEN", score=0.1),
            rag_context=RAGContext(is_used=False),
            voice_diagnostics=voice_diagnostics,
        )

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
