"""Alembic environment bundled with the media-sync package."""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import Connection, Engine

from media_sync.config import Settings
from media_sync.infrastructure.db import Base, create_database_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    command_line_url = context.get_x_argument(as_dictionary=True).get("database_url")
    configured_url = config.get_main_option("sqlalchemy.url").strip()
    return command_line_url or configured_url or Settings().resolved_database_url


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Render SQL without opening a database connection."""

    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_as_batch=url.startswith("sqlite"),
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations through an injected connection or managed engine."""

    supplied: Any = config.attributes.get("connection")
    if supplied is not None:
        if isinstance(supplied, Engine):
            with supplied.connect() as connection:
                _configure(connection)
            return
        _configure(supplied)
        return

    engine = create_database_engine(_database_url())
    try:
        with engine.connect() as connection:
            _configure(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
