"""Packaged nullable tombstone migration and safe downgrade audit."""

from __future__ import annotations

from importlib.resources import as_file, files
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from media_sync.infrastructure.db import Database, upgrade_database
from media_sync.infrastructure.db.migration import MIGRATIONS_PACKAGE

HEAD = "0009_subscription_removal"
PARENT = "0008_playback_evidence"


def _config(database_url: str, output: StringIO | None = None) -> Config:
    configuration = Config(output_buffer=output)
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return configuration


def _downgrade(database_url: str, *, offline: bool = False) -> None:
    with as_file(files(MIGRATIONS_PACKAGE)) as migration_path:
        configuration = _config(database_url, StringIO())
        configuration.set_main_option("script_location", str(migration_path))
        command.downgrade(configuration, f"{HEAD}:{PARENT}" if offline else PARENT, sql=offline)


def test_populated_upgrade_preserves_unique_key_cursor_history_and_nullable_default(tmp_path: Path) -> None:
    url = f"sqlite+pysqlite:///{(tmp_path / 'migration.sqlite3').as_posix()}"
    upgrade_database(url, PARENT)
    database = Database(url)
    account_id, author_id, subscription_id = (str(uuid4()) for _ in range(3))
    try:
        with database.engine.begin() as connection:
            connection.execute(
                text("INSERT INTO accounts (id, platform, display_name) VALUES (:id, 'bili', 'Retained')"),
                {"id": account_id},
            )
            connection.execute(
                text(
                    "INSERT INTO authors (id, platform, remote_id, display_name, first_seen_at, last_seen_at) "
                    "VALUES (:id, 'bili', '123', 'Retained', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": author_id},
            )
            connection.execute(
                text(
                    "INSERT INTO subscriptions (id, account_id, author_id, cursor, checkpoint_revision) "
                    "VALUES (:id, :account, :author, :cursor, 7)"
                ),
                {"id": subscription_id, "account": account_id, "author": author_id, "cursor": '{"head":"retained"}'},
            )
        upgrade_database(url, HEAD)
        inspector = inspect(database.engine)
        deleted = next(column for column in inspector.get_columns("subscriptions") if column["name"] == "deleted_at")
        assert deleted["nullable"]
        assert any(
            set(key["column_names"]) == {"account_id", "author_id"}
            for key in inspector.get_unique_constraints("subscriptions")
        )
        with database.engine.connect() as connection:
            row = connection.execute(
                text("SELECT enabled,checkpoint_revision,cursor,deleted_at FROM subscriptions")
            ).one()
            assert tuple(row) == (1, 7, '{"head":"retained"}', None)
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
            assert connection.scalar(text("SELECT COUNT(*) FROM accounts")) == 1
            assert connection.scalar(text("SELECT COUNT(*) FROM authors")) == 1
        # This is an exact historical schema test: current ORM/service models
        # may contain columns introduced after 0009.
        with database.engine.begin() as connection:
            connection.execute(text("UPDATE subscriptions SET deleted_at=CURRENT_TIMESTAMP, enabled=0"))
        with pytest.raises(RuntimeError, match="removed_subscriptions_prevent_downgrade"):
            _downgrade(url)
        with database.engine.begin() as connection:
            assert connection.scalar(text("SELECT deleted_at FROM subscriptions")) is not None
            connection.execute(text("UPDATE subscriptions SET deleted_at=NULL"))
        _downgrade(url)
        assert "deleted_at" not in {column["name"] for column in inspect(database.engine).get_columns("subscriptions")}
        upgrade_database(url, HEAD)
        with database.engine.connect() as connection:
            row = connection.execute(
                text("SELECT enabled,checkpoint_revision,cursor,deleted_at FROM subscriptions")
            ).one()
            assert tuple(row) == (0, 7, '{"head":"retained"}', None)
    finally:
        database.dispose()


@pytest.mark.parametrize("url", ["sqlite+pysqlite:///offline.sqlite3", "postgresql+psycopg://offline/unused"])
def test_tombstone_offline_upgrade_and_refusal_to_downgrade_without_audit(url: str) -> None:
    output = StringIO()
    with as_file(files(MIGRATIONS_PACKAGE)) as migration_path:
        configuration = _config(url, output)
        configuration.set_main_option("script_location", str(migration_path))
        command.upgrade(configuration, f"{PARENT}:{HEAD}", sql=True)
    assert "ALTER TABLE subscriptions ADD COLUMN deleted_at" in output.getvalue()
    with pytest.raises(RuntimeError, match="subscription_removal_downgrade_requires_online_audit"):
        _downgrade(url, offline=True)


def test_fresh_packaged_head_and_metadata_agree_on_nullable_tombstone(tmp_path: Path) -> None:
    migrated = Database(f"sqlite+pysqlite:///{(tmp_path / 'fresh.sqlite3').as_posix()}")
    metadata = Database("sqlite+pysqlite:///:memory:")
    try:
        upgrade_database(migrated.url)
        metadata.create_schema()
        for database in (migrated, metadata):
            columns = inspect(database.engine).get_columns("subscriptions")
            column = next(column for column in columns if column["name"] == "deleted_at")
            assert column["nullable"] and column["default"] is None
    finally:
        migrated.dispose()
        metadata.dispose()
