from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app
from backend.models import CheckIn, User


class CounselorCaseApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(
            Settings(
                app_name="Counselor Case Test",
                environment="test",
                database_url=f"sqlite:///{(Path(self.temp_dir.name) / 'cases.db').as_posix()}",
                auth_jwt_secret="counselor-case-secret",
            ),
            service_factory=lambda: object(),
        )
        self.client = TestClient(self.app)
        self.client.__enter__()
        with self.app.state.database.session_factory() as session:
            session.add_all([
                User(id="counselor-1", role="counselor"),
                User(id="counselor-2", role="counselor"),
                User(id="student-1", role="student"),
            ])
            session.add(CheckIn(user_id="student-1", mood="stressed", stress_level=8, notes="Exam week"))
            session.commit()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def headers_for(self, subject: str) -> dict[str, str]:
        token = self.app.state.auth_service.create_access_token(subject)
        return {"Authorization": f"Bearer {token}"}

    def test_counselor_case_lifecycle_and_assigned_checkins(self) -> None:
        counselor = self.headers_for("counselor-1")
        created = self.client.post(
            "/api/counselor/cases",
            json={
                "student_id": "student-1",
                "summary": "Exam stress follow-up",
                "priority": "priority",
                "next_follow_up": "2030-01-01T10:00:00Z",
            },
            headers=counselor,
        )
        self.assertEqual(created.status_code, 201)
        case_id = created.json()["id"]

        dashboard = self.client.get("/api/counselor/dashboard", headers=counselor)
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json()["open_case_count"], 1)
        self.assertEqual(len(dashboard.json()["upcoming_followups"]), 1)

        detail = self.client.get(f"/api/counselor/cases/{case_id}", headers=counselor)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["check_ins"][0]["stress_level"], 8)

        updated = self.client.patch(
            f"/api/counselor/cases/{case_id}",
            json={"status": "closed", "details": "Reviewed with student."},
            headers=counselor,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "closed")

    def test_cases_are_counselor_scoped_and_students_are_forbidden(self) -> None:
        created = self.client.post(
            "/api/counselor/cases",
            json={"student_id": "student-1", "summary": "Private case"},
            headers=self.headers_for("counselor-1"),
        )
        case_id = created.json()["id"]
        self.assertEqual(self.client.get("/api/counselor/cases", headers=self.headers_for("counselor-2")).json(), [])
        self.assertEqual(
            self.client.get(f"/api/counselor/cases/{case_id}", headers=self.headers_for("counselor-2")).status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/counselor/dashboard", headers=self.headers_for("student-1")).status_code,
            403,
        )

    def test_case_input_is_validated(self) -> None:
        response = self.client.post(
            "/api/counselor/cases",
            json={"student_id": "student-1", "summary": "", "priority": "urgent"},
            headers=self.headers_for("counselor-1"),
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
