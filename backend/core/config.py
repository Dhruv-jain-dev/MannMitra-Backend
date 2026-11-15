"""Safe, non-secret configuration for the Phase 1 backend."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    database_url: str
    auth_jwt_secret: str | None = None
    auth_jwt_issuer: str = "mannmitra-api"
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_jwks_url: str | None = None
    supabase_jwt_issuer: str | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_secret: str | None = None
    admin_bootstrap_enabled: bool = False
    admin_bootstrap_target_id: str | None = None
    max_audio_upload_bytes: int = 10 * 1024 * 1024


def get_database_url() -> str:
    """Resolve the required server-side Supabase PostgreSQL URL."""
    load_dotenv(override=False)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be configured for Supabase PostgreSQL")
    if not database_url.lower().startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("DATABASE_URL must use a PostgreSQL URL; SQLite is not supported")
    return database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load environment-backed settings without exposing secret values."""
    load_dotenv(override=False)
    environment = os.environ.get("MANNMITRA_ENV", "development")
    configured_secret = os.environ.get("MANNMITRA_AUTH_JWT_SECRET") or None
    database_url = get_database_url()
    # A per-process key keeps local development usable without introducing a
    # shared fallback credential. Production must always configure its own key.
    auth_secret = configured_secret or (secrets.token_urlsafe(32) if environment.lower() in {"development", "dev", "test"} else None)
    return Settings(
        app_name=os.environ.get("MANNMITRA_APP_NAME", "MannMitra API"),
        environment=environment,
        database_url=database_url,
        auth_jwt_secret=auth_secret,
        auth_jwt_issuer=os.environ.get("MANNMITRA_AUTH_JWT_ISSUER", "mannmitra-api"),
        supabase_url=os.environ.get("SUPABASE_URL") or None,
        supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY") or None,
        supabase_service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or None,
        supabase_jwks_url=os.environ.get("SUPABASE_JWKS_URL") or None,
        supabase_jwt_issuer=os.environ.get("SUPABASE_JWT_ISSUER") or None,
        supabase_jwt_audience=os.environ.get("SUPABASE_JWT_AUDIENCE", "authenticated"),
        supabase_jwt_secret=os.environ.get("SUPABASE_JWT_SECRET") or None,
        admin_bootstrap_enabled=os.environ.get("ADMIN_BOOTSTRAP_ENABLED", "false").strip().lower() == "true",
        admin_bootstrap_target_id=os.environ.get("ADMIN_BOOTSTRAP_TARGET_ID") or None,
        max_audio_upload_bytes=int(os.environ.get("MANNMITRA_MAX_AUDIO_UPLOAD_BYTES", 10 * 1024 * 1024)),
    )
