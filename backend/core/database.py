"""SQLAlchemy database setup for Supabase PostgreSQL persistence."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def normalize_database_url(database_url: str) -> str:
    """Use the psycopg driver for PostgreSQL URLs."""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


class Database:
    """Owns one engine and creates short-lived request sessions."""

    def __init__(self, database_url: str) -> None:
        database_url = normalize_database_url(database_url)
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def create_all(self) -> None:
        """Create missing tables for isolated local/test databases.

        Production and shared databases must use ``migrate``/Alembic so
        existing MannMitra data is preserved across schema changes.
        """
        # Import models before metadata creation so every table is registered.
        from backend import models  # noqa: F401

        Base.metadata.create_all(self.engine)

    def migrate(self, revision: str = "head") -> None:
        """Apply versioned Alembic migrations to this database."""
        try:
            from alembic import command
            from alembic.config import Config
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Alembic is required to run database migrations; install the project migration dependencies."
            ) from exc

        is_postgresql = self.engine.url.get_backend_name() == "postgresql"
        config_name = "alembic-pg.ini" if is_postgresql else "alembic.ini"
        config = Config(str(Path(__file__).resolve().parents[2] / config_name))
        migration_url = self.engine.url.render_as_string(hide_password=False).replace("%", "%%")
        config.set_main_option("sqlalchemy.url", migration_url)
        target_revision = revision if is_postgresql or revision != "head" else "20261110_05"
        command.upgrade(config, target_revision)

    def session(self) -> Session:
        return self.session_factory()

    def dispose(self) -> None:
        """Release pooled database connections during application shutdown."""
        self.engine.dispose()
