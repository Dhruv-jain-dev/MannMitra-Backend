from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend import models  # noqa: F401
from backend.core.config import get_database_url
from backend.core.database import Base, normalize_database_url


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    return normalize_database_url(get_database_url())


def _configure(connection=None) -> None:
    options = {
        "target_metadata": target_metadata,
        "compare_type": True,
        "transactional_ddl": True,
    }
    if connection is None:
        options.update(
            url=database_url(),
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
    else:
        options["connection"] = connection
    context.configure(**options)


def run_migrations_offline() -> None:
    _configure()
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    injected_connection = config.attributes.get("connection")
    if injected_connection is not None:
        _configure(injected_connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
