from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app
from backend.models import SupportCase, User


class CounselorWorkflowApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(Settings(app_name="Workflow tests", environment="test", database_url=f"sqlite:///{(Path(self.temp_dir.name) / 'workflow.db').as_posix()}", auth_jwt_secret="workflow-secret"), service_factory=lambda: object())
        self.client = TestClient(self.app); self.client.__enter__()
        with self.app.state.database.session_factory() as session:
            session.add_all([User(id="c1", role="counselor"), User(id="c2", role="counselor"), User(id="s1", role="student")])
            session.add(SupportCase(id="case-1", counselor_id="c1", student_id="s1", summary="Exam support")); session.commit()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None); self.temp_dir.cleanup()

    def headers(self, subject: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.app.state.auth_service.create_access_token(subject)}"}

    def test_owned_intervention_and_followup_persist_and_update(self) -> None:
        headers = self.headers("c1")
        intervention = self.client.post("/api/counselor/interventions", json={"case_id": "case-1", "title": "Study planning"}, headers=headers)
        self.assertEqual(intervention.status_code, 201)
        intervention_id = intervention.json()["id"]
        self.assertEqual(self.client.patch(f"/api/counselor/interventions/{intervention_id}", json={"status": "completed"}, headers=headers).status_code, 200)
        followup = self.client.post("/api/counselor/followups", json={"case_id": "case-1", "title": "Review", "due_at": "2030-01-01T10:00:00Z"}, headers=headers)
        self.assertEqual(followup.status_code, 201)
        self.assertEqual(self.client.patch(f"/api/counselor/followups/{followup.json()['id']}", json={"status": "cancelled"}, headers=headers).status_code, 200)

    def test_other_counselor_and_student_cannot_access_case_workflows(self) -> None:
        payload = {"case_id": "case-1", "title": "Not assigned"}
        self.assertEqual(self.client.post("/api/counselor/interventions", json=payload, headers=self.headers("c2")).status_code, 404)
        self.assertEqual(self.client.post("/api/counselor/followups", json={**payload, "due_at": "2030-01-01T10:00:00Z"}, headers=self.headers("s1")).status_code, 403)


if __name__ == "__main__":
    unittest.main()
