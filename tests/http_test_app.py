"""Isolated HTTP-test app; never used by production startup.

The launcher requires CAMPUSPULSE_TEST_DATABASE_URL and
CAMPUSPULSE_TEST_JWT_SECRET so an integration run cannot accidentally use the
developer or shared production database configuration.
"""

import os
from pathlib import Path

from backend.core.config import Settings
from backend.main import create_app


database_url = os.environ["CAMPUSPULSE_TEST_DATABASE_URL"]
secret = os.environ["CAMPUSPULSE_TEST_JWT_SECRET"]

app = create_app(
    Settings(
        app_name="CampusPulse HTTP Tests",
        environment="test",
        database_url=database_url,
        auth_jwt_secret=secret,
    ),
    service_factory=lambda: object(),
)
