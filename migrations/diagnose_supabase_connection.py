"""Guarded, read-only Supabase target diagnostic.

This script never edits environment files and refuses to connect until the
operator supplies the exact host and username copied from the dashboard.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from backend.core.database import normalize_database_url


CONFIRMATION = "CONFIRM-SUPABASE-DASHBOARD-VALUES"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Exact Session Pooler hostname from Supabase")
    parser.add_argument("--username", required=True, help="Exact Session Pooler username from Supabase")
    parser.add_argument("--confirm", required=True, help="Must equal the documented confirmation token")
    args = parser.parse_args()

    if args.confirm != CONFIRMATION:
        print("REFUSED=confirmation token mismatch")
        return 2

    env_path = Path(__file__).resolve().parents[1] / ".env"
    values = dotenv_values(env_path)
    file_url = values.get("DATABASE_URL")
    process_url = os.environ.get("DATABASE_URL")
    if not file_url:
        print("REFUSED=root .env has no DATABASE_URL")
        return 2
    if process_url and process_url != file_url:
        print("REFUSED=process DATABASE_URL overrides root .env")
        return 2

    parsed = urlsplit(file_url)
    configured_host = parsed.hostname or ""
    configured_username = parsed.username or ""
    project_ref = (
        configured_username.split(".", 1)[1]
        if configured_username.startswith("postgres.") and "." in configured_username
        else ""
    )

    print("ROOT_ENV_SOURCE=YES")
    print("HOST_MATCH=" + str(configured_host == args.host).upper())
    print("USERNAME_MATCH=" + str(configured_username == args.username).upper())
    print("PROJECT_REFERENCE_PRESENT=" + str(bool(project_ref)).upper())
    print("SESSION_POOLER_HOST=" + str(configured_host.endswith(".pooler.supabase.com")).upper())
    print("PORT_5432=" + str(parsed.port == 5432).upper())
    print("DATABASE_POSTGRES=" + str(parsed.path.lstrip("/") == "postgres").upper())

    if configured_host != args.host or configured_username != args.username:
        print("REFUSED=dashboard target does not match root .env")
        return 3

    try:
        engine = create_engine(
            normalize_database_url(file_url),
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10},
        )
        with engine.connect() as connection:
            print("SELECT_1=" + str(connection.execute(text("SELECT 1")).scalar_one()))
            identity = connection.execute(
                text("SELECT current_database(), current_schema()")
            ).one()
            print("DATABASE=" + str(identity[0]))
            print("SCHEMA=" + str(identity[1]))
        engine.dispose()
        return 0
    except OperationalError as exc:
        message = str(exc).lower()
        if "password authentication failed" in message:
            print("CONNECTION=FAIL_AUTHENTICATION")
        elif "ssl" in message:
            print("CONNECTION=FAIL_SSL")
        elif "timeout" in message:
            print("CONNECTION=FAIL_TIMEOUT")
        else:
            print("CONNECTION=FAIL_POSTGRESQL_OPERATIONAL")
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
