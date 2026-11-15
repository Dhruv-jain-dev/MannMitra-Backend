"""Isolated HTTP-test app; never used by production startup.

The launcher requires CAMPUSPULSE_TEST_DATABASE_URL and
CAMPUSPULSE_TEST_JWT_SECRET so an integration run cannot accidentally use the
developer or shared production database configuration.
"""

import os

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from backend.core.config import Settings
from backend.models import User
from backend.main import create_app
from backend.services.mannmitra_service import MannMitraService


class LocalTestLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


LOCAL_TEST_ACCOUNTS = {
    "student.test@mannmitra.local": ("local-student-00000000-0000-4000-8000-000000000001", "student", "StudentTest!2026"),
    "counselor.test@mannmitra.local": ("local-counselor-0000-4000-8000-000000000002", "counselor", "CounselorTest!2026"),
    "admin.test@mannmitra.local": ("local-admin-00000000-0000-4000-8000-000000000003", "admin", "AdminTest!2026"),
}


def configure_local_auth(app):
    """Add the fixed-account login surface to an isolated test app only."""
    # The shared app exposes a development-token route for unit tests. Remove
    # it from this browser-facing harness so local login cannot mint arbitrary
    # users.
    app.router.routes = [route for route in app.router.routes if getattr(route, "path", None) != "/api/auth/dev-token"]
    app.state.local_test_identity_registry = {
        subject: {"email": email}
        for email, (subject, _role, _password) in LOCAL_TEST_ACCOUNTS.items()
    }

    @app.post("/api/test-auth/sign-in")
    def local_test_sign_in(payload: LocalTestLoginRequest):
        account = LOCAL_TEST_ACCOUNTS.get(payload.email.strip().casefold())
        if account is None or payload.password != account[2]:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid local test credentials")
        subject, role, _ = account
        with app.state.database.session_factory() as session:
            profile = session.get(User, subject)
            if profile is not None and profile.role != role:
                raise HTTPException(status_code=403, detail="Local test profile has an incompatible role")
            if profile is None:
                session.add(User(id=subject, role=role))
                session.commit()
        token = app.state.auth_service.create_access_token(subject)
        return {"access_token": token, "token_type": "bearer", "user": {"id": subject, "role": role}}

    return app


def build_local_app(database_url: str, secret: str):
    return configure_local_auth(create_app(
        Settings(
            app_name="CampusPulse HTTP Tests",
            environment="test",
            database_url=database_url,
            auth_jwt_secret=secret,
        ),
        service_factory=MannMitraService,
    ))


if os.environ.get("CAMPUSPULSE_TEST_DATABASE_URL") and os.environ.get("CAMPUSPULSE_TEST_JWT_SECRET"):
    app = build_local_app(os.environ["CAMPUSPULSE_TEST_DATABASE_URL"], os.environ["CAMPUSPULSE_TEST_JWT_SECRET"])
else:
    app = None
