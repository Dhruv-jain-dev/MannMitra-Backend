"""Atomically adopt the existing Supabase schema into Alembic tracking.

This module is intentionally guarded and is not invoked by application startup.
It stamps the verified legacy baseline and runs only the adoption revision on
one caller-owned PostgreSQL transaction.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from backend.core.config import get_database_url
from backend.core.database import normalize_database_url
from migrations.adoption_validation import capture_schema, validate_baseline_snapshot


BASELINE_REVISION = "20261110_05"
ADOPTION_REVISION = "20261112_06"
CONFIRMATION = "ADOPT-SUPABASE-20261112"


def adopt(confirmation: str) -> None:
    if confirmation != CONFIRMATION:
        raise ValueError("Refusing adoption: exact confirmation token is required")

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    engine = create_engine(
        normalize_database_url(get_database_url()),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    try:
        with engine.begin() as connection:
            version_table_exists = connection.execute(
                text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
            ).scalar_one()
            if version_table_exists:
                raise RuntimeError("Refusing adoption: public.alembic_version already exists")

            validate_baseline_snapshot(capture_schema(connection), allow_adoption_gaps=True)
            config.attributes["connection"] = connection
            command.stamp(config, BASELINE_REVISION)
            stamped_revision = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar_one()
            if stamped_revision != BASELINE_REVISION:
                raise RuntimeError(f"Baseline stamp did not reach {BASELINE_REVISION}")
            command.upgrade(config, ADOPTION_REVISION)
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if revision != ADOPTION_REVISION:
                raise RuntimeError(f"Adoption did not reach {ADOPTION_REVISION}")
            validate_baseline_snapshot(capture_schema(connection), allow_adoption_gaps=False)
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Atomically adopt the existing Supabase schema into Alembic")
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit("Refusing adoption: explicit confirmation token is required")
    adopt(args.confirm)


if __name__ == "__main__":
    main()
