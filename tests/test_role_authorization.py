from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app
from backend.models import User


class RoleAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_url = f"sqlite:///{(Path(self.temp_dir.name) / 'roles.db').as_posix()}"
        self.app = create_app(
            Settings(
                app_name="Role Test",
                environment="test",
                database_url=database_url,
                auth_jwt_secret="role-test-secret",
            ),
            service_factory=lambda: object(),
        )
        self.client = TestClient(self.app)
        self.client.__enter__()
        with self.app.state.database.session_factory() as session:
            session.add_all([
                User(id="counselor-1", role="counselor"),
                User(id="admin-1", role="admin"),
            ])
            session.commit()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def headers_for(self, subject: str, expires_in_seconds: int = 3600) -> dict[str, str]:
        token = self.app.state.auth_service.create_access_token(subject, expires_in_seconds)
        return {"Authorization": f"Bearer {token}"}

    def test_new_demo_identity_is_server_provisioned_as_student(self) -> None:
        response = self.client.post("/api/conversations", json={}, headers=self.headers_for("new-student"))
        self.assertEqual(response.status_code, 201)
        with self.app.state.database.session_factory() as session:
            self.assertEqual(session.get(User, "new-student").role, "student")

    def test_valid_roles_are_loaded_from_database(self) -> None:
        self.assertEqual(
            self.client.post("/api/conversations", json={}, headers=self.headers_for("student-1")).status_code,
            201,
        )
        self.assertEqual(
            self.client.get("/api/conversations", headers=self.headers_for("counselor-1")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/conversations", headers=self.headers_for("admin-1")).status_code,
            403,
        )

    def test_invalid_persisted_role_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            User(id="invalid-1", role="superuser")

    def test_expired_and_invalid_tokens_are_unauthorized(self) -> None:
        self.assertEqual(
            self.client.get("/api/conversations", headers=self.headers_for("student-1", -1)).status_code,
            401,
        )
        self.assertEqual(
            self.client.get("/api/conversations", headers={"Authorization": "Bearer invalid.token.value"}).status_code,
            401,
        )

if __name__ == "__main__":
    unittest.main()
