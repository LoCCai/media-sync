"""Programmatic access to the package-owned Alembic migration history."""

from __future__ import annotations

from importlib.resources import as_file, files

from alembic import command
from alembic.config import Config

MIGRATIONS_PACKAGE = "media_sync.infrastructure.db.migrations"


def _config_value(value: str) -> str:
    """Escape ConfigParser interpolation without changing the URL Alembic reads."""

    return value.replace("%", "%%")


def upgrade_database(database_url: str, revision: str = "head") -> None:
    """Upgrade ``database_url`` using migrations shipped inside the package.

    The function deliberately creates its Alembic configuration in memory, so
    an installed wheel never depends on a repository-level ``alembic.ini``.
    ``database_url`` is not logged or returned.
    """

    if not database_url.strip():
        raise ValueError("database_url must not be empty")
    if not revision.strip():
        raise ValueError("revision must not be empty")

    migration_resources = files(MIGRATIONS_PACKAGE)
    with as_file(migration_resources) as migration_path:
        configuration = Config()
        configuration.set_main_option("script_location", str(migration_path))
        configuration.set_main_option("sqlalchemy.url", _config_value(database_url))
        command.upgrade(configuration, revision)


__all__ = ["MIGRATIONS_PACKAGE", "upgrade_database"]
