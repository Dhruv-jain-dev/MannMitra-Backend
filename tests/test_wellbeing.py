from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app
from backend.models import User


class WellbeingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_url = f"sqlite:///{(Path(self.temp_dir.name) / 'wellbeing.db').as_posix()}"
        self.app = create_app(
            Settings(
                app_name="Wellbeing Test",
                environment="test",
                database_url=database_url,
                auth_jwt_secret="wellbeing-test-secret",
            ),
            service_factory=lambda: object(),
        )
        self.client = TestClient(self.app)
        self.client.__enter__()
        with self.app.state.database.session_factory() as session:
            session.add(User(id="counselor-1", role="counselor"))
            session.commit()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def headers_for(self, subject: str) -> dict[str, str]:
        token = self.app.state.auth_service.create_access_token(subject)
        return {"Authorization": f"Bearer {token}"}

    def test_check_ins_and_insights_are_student_scoped(self) -> None:
        student_headers = self.headers_for("student-1")
        other_headers = self.headers_for("student-2")

        first = self.client.post(
            "/api/wellbeing/check-in",
            json={"mood": "stressed", "stress_level": 8, "notes": "Exam week"},
            headers=student_headers,
        )
        second = self.client.post(
            "/api/wellbeing/check-in",
            json={"mood": "okay", "stress_level": 4},
            headers=student_headers,
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["mood"], "stressed")

        history = self.client.get("/api/wellbeing/check-ins?page=1&page_size=1", headers=student_headers)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["total"], 2)
        self.assertEqual(len(history.json()["items"]), 1)

        insights = self.client.get("/api/wellbeing/insights", headers=student_headers)
        self.assertEqual(insights.status_code, 200)
        self.assertEqual(insights.json()["check_in_count"], 2)
        self.assertEqual(insights.json()["average_stress"], 6.0)
        self.assertEqual(insights.json()["mood_distribution"], {"okay": 1, "stressed": 1})
        self.assertEqual(len(insights.json()["recent_trends"]), 2)

        other_insights = self.client.get("/api/wellbeing/insights", headers=other_headers)
        self.assertEqual(other_insights.status_code, 200)
        self.assertEqual(other_insights.json()["check_in_count"], 0)

    def test_validation_and_role_authorization(self) -> None:
        invalid = self.client.post(
            "/api/wellbeing/check-in",
            json={"mood": "unknown", "stress_level": 11},
            headers=self.headers_for("student-1"),
        )
        self.assertEqual(invalid.status_code, 422)

        counselor = self.client.get("/api/wellbeing/insights", headers=self.headers_for("counselor-1"))
        self.assertEqual(counselor.status_code, 403)

        unauthenticated = self.client.get("/api/wellbeing/insights")
        self.assertEqual(unauthenticated.status_code, 401)


if __name__ == "__main__":
    unittest.main()
