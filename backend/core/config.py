"""Safe, non-secret configuration for the Phase 1 backend."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    database_url: str
    auth_jwt_secret: str | None = None
    auth_jwt_issuer: str = "mannmitra-api"
    max_audio_upload_bytes: int = 10 * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load environment-backed settings without exposing secret values."""
    load_dotenv(override=False)
    default_database = Path(__file__).resolve().parents[2] / "mannmitra_dev.db"
    environment = os.environ.get("MANNMITRA_ENV", "development")
    configured_secret = os.environ.get("MANNMITRA_AUTH_JWT_SECRET") or None
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("MANNMITRA_DATABASE_URL")
    # A per-process key keeps local development usable without introducing a
    # shared fallback credential. Production must always configure its own key.
    auth_secret = configured_secret or (secrets.token_urlsafe(32) if environment.lower() in {"development", "dev", "test"} else None)
    return Settings(
        app_name=os.environ.get("MANNMITRA_APP_NAME", "MannMitra API"),
        environment=environment,
        database_url=database_url or f"sqlite:///{default_database.as_posix()}",
        auth_jwt_secret=auth_secret,
        auth_jwt_issuer=os.environ.get("MANNMITRA_AUTH_JWT_ISSUER", "mannmitra-api"),
        max_audio_upload_bytes=int(os.environ.get("MANNMITRA_MAX_AUDIO_UPLOAD_BYTES", 10 * 1024 * 1024)),
    )
