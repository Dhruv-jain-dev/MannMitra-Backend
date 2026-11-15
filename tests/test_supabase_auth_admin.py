from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from fastapi import HTTPException

from backend.core.config import Settings
from backend.core.database import Database
from backend.main import ProvisionUserRequest, create_app
from backend.services.supabase_auth_admin import SupabaseAdminError, SupabaseAuthAdmin
from backend.core.auth import AuthenticatedUser, require_admin
from backend.models import User


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self): return json.dumps(self.payload).encode("utf-8")


class SupabaseAuthAdminTests(unittest.TestCase):
    def test_invite_uses_auth_invite_route_and_safe_response(self) -> None:
        with patch("backend.services.supabase_auth_admin.urlopen", return_value=FakeResponse({"id": "auth-1"})) as open_url:
            result = SupabaseAuthAdmin("https://project.supabase.co", "secret-not-printed").invite_user("new@example.com")
        self.assertEqual(result["id"], "auth-1")
        self.assertEqual(open_url.call_args.args[0].full_url, "https://project.supabase.co/auth/v1/invite")

    def test_auth_failure_preserves_status_without_response_body(self) -> None:
        error = HTTPError("https://project.supabase.co/auth/v1/invite", 429, "rate", {}, None)
        error.read = lambda: b'{"msg":"private detail","code":"over_request_rate_limit"}'
        with patch("backend.services.supabase_auth_admin.urlopen", side_effect=error):
            with self.assertRaises(SupabaseAdminError) as raised:
                SupabaseAuthAdmin("https://project.supabase.co", "secret-not-printed").invite_user("new@example.com")
        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn("rate limit", str(raised.exception))
        self.assertNotIn("private detail", str(raised.exception))

    def test_duplicate_auth_email_is_rejected_before_invite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db = Database(f"sqlite:///{(Path(directory) / 'admin.db').as_posix()}")
            db.create_all()
            app = create_app(Settings(app_name="provision test", environment="test", database_url=f"sqlite:///{(Path(directory) / 'admin.db').as_posix()}", supabase_url="https://project.supabase.co", supabase_service_role_key="test-key"), service_factory=lambda: object())
            app.state.database = db
            with db.session_factory() as session:
                session.add(User(id="admin-1", role="admin")); session.commit()
            endpoint = next(route.endpoint for route in app.routes if route.path == "/api/admin/users/provision")
            fake = SimpleNamespace(find_user_by_email=lambda _: {"id": "existing-auth"}, invite_user=lambda _: (_ for _ in ()).throw(AssertionError("invite must not run")))
            with patch("backend.main.SupabaseAuthAdmin", return_value=fake):
                with self.assertRaises(HTTPException) as raised:
                    endpoint(ProvisionUserRequest(email="existing@example.com", role="counselor"), SimpleNamespace(app=app), AuthenticatedUser(id="admin-1", role="admin"))
            self.assertEqual(raised.exception.status_code, 409)
            db.dispose()

    def test_new_identity_creates_only_the_requested_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_url = f"sqlite:///{(Path(directory) / 'admin.db').as_posix()}"
            db = Database(db_url); db.create_all()
            app = create_app(Settings(app_name="provision success test", environment="test", database_url=db_url, supabase_url="https://project.supabase.co", supabase_service_role_key="test-key"), service_factory=lambda: object())
            app.state.database = db
            with db.session_factory() as session:
                session.add(User(id="admin-1", role="admin")); session.commit()
            endpoint = next(route.endpoint for route in app.routes if route.path == "/api/admin/users/provision")
            fake = SimpleNamespace(find_user_by_email=lambda _: None, invite_user=lambda _: {"id": "auth-counselor-1"})
            with patch("backend.main.SupabaseAuthAdmin", return_value=fake):
                result = endpoint(ProvisionUserRequest(email="new@example.com", role="counselor", department=" Student Support "), SimpleNamespace(app=app), AuthenticatedUser(id="admin-1", role="admin"))
            self.assertEqual(result["id"], "auth-counselor-1")
            self.assertEqual(result["department"], "Student Support")
            with db.session_factory() as session:
                self.assertEqual(session.get(User, "auth-counselor-1").role, "counselor")
            db.dispose()

    def test_blank_department_is_rejected_before_auth_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_url = f"sqlite:///{(Path(directory) / 'admin.db').as_posix()}"
            db = Database(db_url); db.create_all()
            app = create_app(Settings(app_name="provision validation test", environment="test", database_url=db_url, supabase_url="https://project.supabase.co", supabase_service_role_key="test-key"), service_factory=lambda: object())
            app.state.database = db
            endpoint = next(route.endpoint for route in app.routes if route.path == "/api/admin/users/provision")
            with patch("backend.main.SupabaseAuthAdmin") as auth_client:
                with self.assertRaises(HTTPException) as raised:
                    endpoint(ProvisionUserRequest(email="new@example.com", role="counselor", department="   "), SimpleNamespace(app=app), AuthenticatedUser(id="admin-1", role="admin"))
            self.assertEqual(raised.exception.status_code, 422)
            auth_client.assert_not_called()
            db.dispose()

    def test_temporary_password_sets_server_side_change_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_url = f"sqlite:///{(Path(directory) / 'admin.db').as_posix()}"
            db = Database(db_url); db.create_all()
            app = create_app(Settings(app_name="temporary password test", environment="test", database_url=db_url, supabase_url="https://project.supabase.co", supabase_service_role_key="test-key"), service_factory=lambda: object())
            app.state.database = db
            with db.session_factory() as session:
                session.add(User(id="admin-1", role="admin")); session.commit()
            endpoint = next(route.endpoint for route in app.routes if route.path == "/api/admin/users/provision")
            fake = SimpleNamespace(find_user_by_email=lambda _: None, create_user=lambda email, password: {"id": "auth-temp-1"})
            payload = ProvisionUserRequest(email="temp@example.com", role="counselor", method="temporary_password", password="StrongTemporary!9", password_confirmation="StrongTemporary!9")
            with patch("backend.main.SupabaseAuthAdmin", return_value=fake):
                result = endpoint(payload, SimpleNamespace(app=app), AuthenticatedUser(id="admin-1", role="admin"))
            self.assertTrue(result["must_change_password"])
            with db.session_factory() as session:
                profile = session.get(User, "auth-temp-1")
                self.assertTrue(profile.must_change_password)
                self.assertIsNotNone(profile.password_change_requested_at)
            with self.assertRaises(HTTPException):
                require_admin(AuthenticatedUser(id="auth-temp-1", role="counselor", must_change_password=True))
            db.dispose()

    def test_password_changed_clears_requirement_only_after_auth_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_url = f"sqlite:///{(Path(directory) / 'admin.db').as_posix()}"
            db = Database(db_url); db.create_all()
            app = create_app(Settings(app_name="password verification test", environment="test", database_url=db_url, supabase_url="https://project.supabase.co", supabase_service_role_key="test-key"), service_factory=lambda: object())
            app.state.database = db
            requested = datetime.now(timezone.utc) - timedelta(minutes=5)
            with db.session_factory() as session:
                session.add(User(id="auth-temp-1", role="counselor", must_change_password=True, password_change_requested_at=requested)); session.commit()
            endpoint = next(route.endpoint for route in app.routes if route.path == "/api/auth/password-changed")
            fake = SimpleNamespace(get_user=lambda _: {"id": "auth-temp-1", "updated_at": datetime.now(timezone.utc).isoformat()})
            with patch("backend.main.SupabaseAuthAdmin", return_value=fake):
                result = endpoint(SimpleNamespace(app=app), AuthenticatedUser(id="auth-temp-1", role="counselor", must_change_password=True))
            self.assertFalse(result["must_change_password"])
            with db.session_factory() as session:
                self.assertFalse(session.get(User, "auth-temp-1").must_change_password)
            db.dispose()


if __name__ == "__main__":
    unittest.main()
