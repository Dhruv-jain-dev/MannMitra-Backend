"""Owner-controlled one-time first-admin bootstrap CLI.

This module is intentionally not imported by the FastAPI application.
"""

from __future__ import annotations

import argparse
import logging

from backend.core.config import get_settings
from backend.core.database import Database
from backend.services.admin_bootstrap import BootstrapError, bootstrap_first_admin
from backend.services.supabase_auth_admin import SupabaseAuthAdmin

CONFIRMATION = "BOOTSTRAP-FIRST-ADMIN-20261115"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the first MannMitra administrator")
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    if args.confirm != CONFIRMATION:
        parser.error("incorrect bootstrap confirmation token")

    settings = get_settings()
    if not settings.admin_bootstrap_enabled:
        print("Bootstrap is disabled")
        return 1
    if not settings.admin_bootstrap_target_id:
        print("ADMIN_BOOTSTRAP_TARGET_ID is not configured")
        return 1
    if not settings.supabase_url or not settings.supabase_service_role_key:
        print("Supabase Auth admin configuration is incomplete")
        return 1

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    database = Database(settings.database_url)
    try:
        result = bootstrap_first_admin(
            target_id=settings.admin_bootstrap_target_id,
            auth_admin=SupabaseAuthAdmin(settings.supabase_url, settings.supabase_service_role_key),
            session_factory=database.session_factory,
        )
        print(f"Bootstrap succeeded for the configured identity; role={result['role']}")
        print("Set ADMIN_BOOTSTRAP_ENABLED=false and remove ADMIN_BOOTSTRAP_TARGET_ID immediately.")
        return 0
    except BootstrapError as exc:
        print(f"Bootstrap refused: {exc}")
        return 1
    finally:
        database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
