"""Safe, non-secret configuration for the Phase 1 backend."""

from __future__ import annotations

import os
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
    return Settings(
        app_name=os.environ.get("MANNMITRA_APP_NAME", "MannMitra API"),
        environment=os.environ.get("MANNMITRA_ENV", "development"),
        database_url=os.environ.get("MANNMITRA_DATABASE_URL", f"sqlite:///{default_database.as_posix()}"),
        auth_jwt_secret=os.environ.get("MANNMITRA_AUTH_JWT_SECRET") or None,
        auth_jwt_issuer=os.environ.get("MANNMITRA_AUTH_JWT_ISSUER", "mannmitra-api"),
        max_audio_upload_bytes=int(os.environ.get("MANNMITRA_MAX_AUDIO_UPLOAD_BYTES", 10 * 1024 * 1024)),
    )
