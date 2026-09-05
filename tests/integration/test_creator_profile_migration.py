"""Packaged creator-profile upgrade retains old aliases and Operation history."""

from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from media_sync.infrastructure.db import Database, OperationRepository, upgrade_database
from media_sync.infrastructure.db.migration import MIGRATIONS_PACKAGE

HEAD = "0010_creator_profiles"
PARENT = "0009_subscription_removal"


def _downgrade(database: Database) -> None:
    with as_file(files(MIGRATIONS_PACKAGE)) as path:
        configuration = Config()
        configuration.set_main_option("script_location", str(path))
        configuration.set_main_option("sqlalchemy.url", database.url)
        command.downgrade(configuration, PARENT)


def test_populated_upgrade_preserves_author_paths_alias_checkpoint_tombstone_and_operation_children(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'migration.sqlite3').as_posix()}")
    account, author, subscription = (str(uuid4()) for _ in range(3))
    try:
        upgrade_database(database.url, PARENT)
        with database.engine.begin() as connection:
            connection.execute(
                text("INSERT INTO accounts (id, platform, display_name) VALUES (:id,'bili','Old account')"),
                {"id": account},
            )
            connection.execute(
                text(
                    "INSERT INTO authors (id,platform,remote_id,display_name,profile_url,avatar_url,"
                    "first_seen_at,last_seen_at) "
                    "VALUES (:id,'bili','123','Original export path','https://space.bilibili.com/123','old-avatar',"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ),
                {"id": author},
            )
            connection.execute(
                text(
                    "INSERT INTO subscriptions (id,account_id,author_id,enabled,deleted_at,checkpoint_revision,cursor) "
                    "VALUES (:id,:account,:author,0,CURRENT_TIMESTAMP,7,:cursor)"
                ),
                {"id": subscription, "account": account, "author": author, "cursor": '{"head":"kept"}'},
            )
        with database.session() as session:
            existing = OperationRepository(session).create_or_replay(
                kind="scheduler-run", request_fingerprint="a" * 64, target_type="account", target_id=account
            )
            operation_id = existing.operation_id
        with database.engine.connect() as connection:
            events = connection.scalar(text("SELECT COUNT(*) FROM operation_events"))
            subjects = connection.scalar(text("SELECT COUNT(*) FROM operation_subjects"))
        upgrade_database(database.url)
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
            assert connection.scalar(text("SELECT auth_revision FROM accounts")) == 0
            row = connection.execute(
                text("SELECT local_alias,checkpoint_revision,cursor,enabled,deleted_at FROM subscriptions")
            ).one()
            assert tuple(row[:4]) == ("Original export path", 7, '{"head":"kept"}', 0) and row[4] is not None
            assert connection.execute(text("SELECT display_name,profile_url,avatar_url FROM authors")).one() == (
                "Original export path",
                "https://space.bilibili.com/123",
                "old-avatar",
            )
            assert connection.scalar(text("SELECT COUNT(*) FROM operation_events")) == events
            assert connection.scalar(text("SELECT COUNT(*) FROM operation_subjects")) == subjects
            assert connection.scalar(text("SELECT id FROM operations")) == operation_id
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        with database.engine.begin() as connection, pytest.raises(IntegrityError):
            connection.execute(text("UPDATE accounts SET auth_revision=-1"))
        with database.engine.begin() as connection:
            connection.execute(text("UPDATE subscriptions SET local_alias='Personal note'"))
        with pytest.raises(RuntimeError, match="alias_prevents_downgrade"):
            _downgrade(database)
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT local_alias FROM subscriptions")) == "Personal note"
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
    finally:
        database.dispose()


def test_fresh_schema_metadata_nullable_binary_and_auth_default_match(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'fresh.sqlite3').as_posix()}")
    metadata = Database("sqlite+pysqlite:///:memory:")
    try:
        upgrade_database(database.url)
        metadata.create_schema()
        for table in ("accounts", "subscriptions", "creator_profiles", "creator_profile_lookups"):
            migration_columns = {item["name"]: item for item in inspect(database.engine).get_columns(table)}
            metadata_columns = {item["name"]: item for item in inspect(metadata.engine).get_columns(table)}
            assert migration_columns.keys() == metadata_columns.keys()
            assert {key: value["nullable"] for key, value in migration_columns.items()} == {
                key: value["nullable"] for key, value in metadata_columns.items()
            }
            assert {item["name"] for item in inspect(database.engine).get_check_constraints(table)} == {
                item["name"] for item in inspect(metadata.engine).get_check_constraints(table)
            }
        _downgrade(database)
        assert "creator_profiles" not in inspect(database.engine).get_table_names()
        upgrade_database(database.url)
        assert "creator_profiles" in inspect(database.engine).get_table_names()
    finally:
        database.dispose()
        metadata.dispose()


def test_creator_operation_history_prevents_destructive_downgrade(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'history.sqlite3').as_posix()}")
    try:
        upgrade_database(database.url)
        with database.session() as session:
            operation = OperationRepository(session).create_or_replay(
                kind="creator-profile", request_fingerprint="a" * 64, target_type="account", target_id=str(uuid4())
            )
        with pytest.raises(RuntimeError, match="history_prevents_downgrade"):
            _downgrade(database)
        with database.session() as session:
            assert OperationRepository(session).require(operation.operation_id).kind == "creator-profile"
    finally:
        database.dispose()
