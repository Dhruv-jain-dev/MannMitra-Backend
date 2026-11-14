from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.core.database import Base
from backend.main import _aggregate_checkins, _department_aggregates, create_app
from backend.models import CheckIn, User


class AdminAggregationTests(unittest.TestCase):
    def test_aggregates_are_real_and_small_departments_are_suppressed(self) -> None:
        engine = create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all([User(id=f"s{i}", role="student", department="Engineering") for i in range(5)])
            session.add(User(id="small", role="student", department="Small department")); session.flush()
            session.add_all([CheckIn(user_id=f"s{i}", mood="okay", stress_level=i + 1) for i in range(5)])
            session.commit()
            self.assertEqual(_aggregate_checkins(session)["check_in_count"], 5)
            groups = _department_aggregates(session, None, None)
            self.assertFalse(next(group for group in groups if group["department"] == "Engineering")["suppressed"])
            self.assertTrue(next(group for group in groups if group["department"] == "Small department")["suppressed"])


class AdminAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(Settings(app_name="Admin tests", environment="test", database_url=f"sqlite:///{(Path(self.temp_dir.name) / 'admin.db').as_posix()}", auth_jwt_secret="admin-secret"), service_factory=lambda: object())
        self.client = TestClient(self.app); self.client.__enter__()
        with self.app.state.database.session_factory() as session:
            session.add_all([User(id="admin", role="admin"), User(id="student", role="student")]); session.commit()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None); self.temp_dir.cleanup()

    def test_admin_endpoints_reject_non_admin_and_accept_date_filters(self) -> None:
        student_token = self.app.state.auth_service.create_access_token("student")
        admin_token = self.app.state.auth_service.create_access_token("admin")
        student_headers = {"Authorization": f"Bearer {student_token}"}; admin_headers = {"Authorization": f"Bearer {admin_token}"}
        self.assertEqual(self.client.get("/api/admin/dashboard", headers=student_headers).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/dashboard", headers=admin_headers).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/analytics?start_date=2030-01-01&end_date=2029-01-01", headers=admin_headers).status_code, 422)


if __name__ == "__main__":
    unittest.main()
