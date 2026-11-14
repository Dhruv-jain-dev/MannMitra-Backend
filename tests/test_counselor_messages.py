from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app
from backend.models import Conversation, SupportCase, User


class CounselorMessagingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(
            Settings(
                app_name="Counselor Messaging Test",
                environment="test",
                database_url=f"sqlite:///{(Path(self.temp_dir.name) / 'messages.db').as_posix()}",
                auth_jwt_secret="counselor-messages-secret",
            ),
            service_factory=lambda: object(),
        )
        self.client = TestClient(self.app)
        self.client.__enter__()
        with self.app.state.database.session_factory() as session:
            session.add_all([
                User(id="student-1", role="student"),
                User(id="student-2", role="student"),
                User(id="counselor-1", role="counselor"),
                User(id="counselor-2", role="counselor"),
            ])
            session.add(SupportCase(counselor_id="counselor-1", student_id="student-1", summary="Support"))
            session.add(Conversation(user_id="student-1", kind="mannmitra", title="Private MannMitra"))
            session.commit()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def headers_for(self, subject: str) -> dict[str, str]:
        token = self.app.state.auth_service.create_access_token(subject)
        return {"Authorization": f"Bearer {token}"}

    def test_assigned_student_and_counselor_can_exchange_and_mark_read(self) -> None:
        student = self.headers_for("student-1")
        counselor = self.headers_for("counselor-1")
        sent = self.client.post(
            "/api/counselor/messages",
            json={"counselor_id": "counselor-1", "content": "I would like to talk."},
            headers=student,
        )
        self.assertEqual(sent.status_code, 201)
        conversation_id = sent.json()["conversation_id"]

        threads = self.client.get("/api/counselor/messages", headers=counselor)
        self.assertEqual(threads.status_code, 200)
        self.assertEqual(threads.json()["items"][0]["unread_count"], 1)
        self.assertEqual(
            self.client.post(f"/api/counselor/messages/{conversation_id}/read", headers=counselor).json()["marked_read"], 1
        )
        reply = self.client.post(
            "/api/counselor/messages",
            json={"conversation_id": conversation_id, "content": "I am here to help."},
            headers=counselor,
        )
        self.assertEqual(reply.status_code, 201)
        history = self.client.get("/api/counselor/messages", headers=student).json()["items"][0]
        self.assertEqual(len(history["messages"]), 2)
        self.assertIsNotNone(history["messages"][0]["read_at"])

    def test_unassigned_users_and_other_roles_are_rejected(self) -> None:
        self.assertEqual(
            self.client.post(
                "/api/counselor/messages",
                json={"counselor_id": "counselor-1", "content": "No assignment."},
                headers=self.headers_for("student-2"),
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/counselor/messages", headers=self.headers_for("student-2")).json(), {"items": []})
        self.assertEqual(self.client.get("/api/counselor/messages", headers=self.headers_for("counselor-2")).json(), {"items": []})
        self.assertEqual(
            self.client.post(
                "/api/counselor/messages",
                json={"counselor_id": "counselor-1", "content": ""},
                headers=self.headers_for("student-1"),
            ).status_code,
            422,
        )

    def test_mannmitra_threads_are_not_exposed(self) -> None:
        self.assertEqual(self.client.get("/api/counselor/messages", headers=self.headers_for("student-1")).json(), {"items": []})


if __name__ == "__main__":
    unittest.main()
