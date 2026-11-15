"""Deterministic contract tests for the isolated local browser test app.

These tests avoid Starlette TestClient and application lifespan startup because
the installed Windows Starlette/HTTPX combination can hang while opening its
AnyIO portal. Live startup is verified separately against port 8001.
"""

import unittest
import time
from types import SimpleNamespace

from fastapi import HTTPException
import jwt

from backend.core.config import Settings
from backend.core.auth import AuthService, AuthenticatedUser, require_admin
from backend.main import ProvisionUserRequest, create_app
from tests.http_test_app import LOCAL_TEST_ACCOUNTS, LocalTestLoginRequest, configure_local_auth


class _FakeSession:
    def __init__(self):
        self.added = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def get(self, model, subject):
        return None

    def add(self, profile):
        return None

    def commit(self):
        return None

    def begin(self):
        return self

    def flush(self):
        return None


class _FakeDatabase:
    def session_factory(self):
        return _FakeSession()


class LocalLoginContractTests(unittest.TestCase):
    def setUp(self):
        self.app = configure_local_auth(
            create_app(
                Settings(
                    app_name="Local Login Contract",
                    environment="test",
                    database_url="sqlite:///local-login-contract.db",
                    auth_jwt_secret="local-login-contract-secret",
                ),
                service_factory=lambda: object(),
            )
        )
        self.app.state.database = _FakeDatabase()
        self.app.state.auth_service = SimpleNamespace(create_access_token=lambda subject: f"token-for-{subject}")
        self.login_endpoint = next(
            route.endpoint for route in self.app.routes if getattr(route, "path", None) == "/api/test-auth/sign-in"
        )
        self.provision_endpoint = next(
            route for route in self.app.routes if getattr(route, "path", None) == "/api/admin/users/provision"
        )

    def test_health_and_local_login_routes_are_registered(self):
        paths = {getattr(route, "path", None) for route in self.app.routes}
        self.assertIn("/health", paths)
        self.assertIn("/api/test-auth/sign-in", paths)

    def test_cors_allows_frontend_port_5319(self):
        cors = next(middleware for middleware in self.app.user_middleware if middleware.cls.__name__ == "CORSMiddleware")
        origins = set(cors.kwargs["allow_origins"])
        self.assertIn("http://127.0.0.1:5319", origins)
        self.assertIn("http://localhost:5319", origins)

    def test_student_counselor_and_admin_login_response_contract(self):
        for email, (subject, role, password) in LOCAL_TEST_ACCOUNTS.items():
            response = self.login_endpoint(LocalTestLoginRequest(email=email, password=password))
            self.assertEqual(response["access_token"], f"token-for-{subject}")
            self.assertEqual(response["token_type"], "bearer")
            self.assertEqual(response["user"], {"id": subject, "role": role})

    def test_invalid_credentials_are_rejected(self):
        with self.assertRaises(HTTPException) as context:
            self.login_endpoint(
                LocalTestLoginRequest(
                    email="student.test@mannmitra.local",
                    password="wrong-password",
                )
            )
        self.assertEqual(context.exception.status_code, 401)

    def test_local_admin_can_provision_without_a_supabase_uuid(self):
        response = self.provision_endpoint.endpoint(
            ProvisionUserRequest(email="new.local@mannmitra.local", role="counselor"),
            SimpleNamespace(app=self.app),
            AuthenticatedUser(id=LOCAL_TEST_ACCOUNTS["admin.test@mannmitra.local"][0], role="admin"),
        )
        self.assertEqual(response["role"], "counselor")
        self.assertIn(response["id"], self.app.state.local_test_identity_registry)

    def test_provision_route_remains_admin_only(self):
        self.assertIn(require_admin, [dependency.call for dependency in self.provision_endpoint.dependant.dependencies])
        with self.assertRaises(HTTPException):
            require_admin(AuthenticatedUser(id="local-student", role="student"))
        with self.assertRaises(HTTPException):
            require_admin(AuthenticatedUser(id="local-counselor", role="counselor"))

    def test_synthetic_local_token_is_rejected_by_production_verifier(self):
        local_token = self.app.state.auth_service.create_access_token(
            LOCAL_TEST_ACCOUNTS["admin.test@mannmitra.local"][0]
        )
        production_verifier = AuthService(
            "production-only-secret",
            "https://project.supabase.co/auth/v1",
            supabase_jwt_secret="supabase-jwt-secret",
            allow_legacy_tokens=True,
        )
        with self.assertRaises(HTTPException):
            production_verifier.verify_access_token(local_token)

    def test_real_supabase_jwt_verification_path_is_unchanged(self):
        token = jwt.encode(
            {
                "sub": "7d033690-5f1e-4b59-b638-332561a6825f",
                "iss": "https://project.supabase.co/auth/v1",
                "aud": "authenticated",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3_600,
            },
            "supabase-jwt-secret-32-bytes-long-key",
            algorithm="HS256",
        )
        production_verifier = AuthService(
            "production-only-secret",
            "https://project.supabase.co/auth/v1",
            supabase_jwt_secret="supabase-jwt-secret-32-bytes-long-key",
            allow_legacy_tokens=True,
        )
        self.assertEqual(
            production_verifier.verify_access_token(token).id,
            "7d033690-5f1e-4b59-b638-332561a6825f",
        )


if __name__ == "__main__":
    unittest.main()
