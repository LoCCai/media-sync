"""Alembic environment bundled with the media-sync package."""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import Connection, Engine

from media_sync.config import Settings
from media_sync.infrastructure.db import Base, create_database_engine
from media_sync.infrastructure.db.database import (
    SQLITE_BUSY_TIMEOUT_MS,
    SQLITE_SECURE_DELETE_PRAGMA,
)

config = context.config
if config.config_file_name is not None and config.cmd_opts is not None:
    # Only the standalone Alembic CLI owns process logging. Embedded callers
    # must retain their root handlers, levels, and application audit loggers.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    command_line_url = context.get_x_argument(as_dictionary=True).get("database_url")
    configured_url = config.get_main_option("sqlalchemy.url").strip()
    return command_line_url or configured_url or Settings().resolved_database_url


def _apply_sqlite_pragmas(connection: Connection) -> None:
    """Install the pragmas on a caller-supplied SQLite connection.

    The pragmas (secure_delete, foreign_keys, busy_timeout, WAL) are normally
    installed by ``create_database_engine``'s connect listener. A caller that
    hands us a raw ``Connection`` built from a plain ``create_engine()`` would
    otherwise run 0003's table rebuild and scrubbing ``UPDATE`` with
    ``secure_delete=OFF``, which is exactly the residue 0082 set out to remove.

    The statements go through the raw DBAPI cursor rather than
    ``Connection.exec_driver_sql``: the latter would autobegin a SQLAlchemy
    transaction, and Alembic then refuses its own ``begin_transaction()``.
    """

    if connection.dialect.name != "sqlite":
        return
    dbapi_connection = connection.connection.dbapi_connection
    if dbapi_connection is None:  # pragma: no cover - a live Connection always has one
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(SQLITE_SECURE_DELETE_PRAGMA)
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def _configure(connection: Connection) -> None:
    _apply_sqlite_pragmas(connection)
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
