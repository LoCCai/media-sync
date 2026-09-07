"""Bili delivery baseline migration is exact, empty-by-default and loss-aware."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from importlib import import_module
from importlib.resources import as_file, files
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    Database,
    SubscriptionRepository,
    SyncRunRepository,
    upgrade_database,
)
from media_sync.infrastructure.db.migration import MIGRATIONS_PACKAGE
from media_sync.infrastructure.db.models import BiliSubscriptionProgress, SyncRunContent

PARENT = "0013_exact_subscription_delivery"
HEAD = "0014_bili_delivery_baseline"
NOW = datetime(2026, 9, 7, tzinfo=UTC)


def _downgrade(database: Database, *, exclusive_maintenance: bool = False) -> None:
    with as_file(files(MIGRATIONS_PACKAGE)) as path:
        config = Config()
        config.set_main_option("script_location", str(path))
        config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
        if exclusive_maintenance:
            config.cmd_opts = SimpleNamespace(x=["exclusive-maintenance=true"])
        command.downgrade(config, PARENT)


def _seed_scope(database: Database) -> tuple[str, str, str, str, str]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter="mediacrawler",
            display_name="Migration account",
        )
        author, contents = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(platform="bili", remote_id="252671524", display_name="Migration author"),
            (ContentUpsert(remote_id="BV1migration", remote_type="video", kind="video"),),
            seen_at=NOW,
        )
        subscription = SubscriptionRepository(session).create(account_id=account.id, author_id=author.id)
        run = SyncRunRepository(session).create(subscription_id=subscription.id, attempt=1)
        return account.id, author.id, subscription.id, run.id, contents[0].id


def _snapshot(database: Database, tables: list[str]) -> dict[str, list[tuple[object, ...]]]:
    with database.engine.connect() as connection:
        return {
            table: sorted((tuple(row) for row in connection.execute(text(f"SELECT * FROM {table}"))), key=repr)
            for table in tables
        }


def _shape(database: Database, table: str) -> tuple[object, ...]:
    inspector = inspect(database.engine)
    return (
        inspector.get_pk_constraint(table),
        sorted(inspector.get_unique_constraints(table), key=lambda item: str(item["name"])),
        sorted(inspector.get_check_constraints(table), key=lambda item: str(item["name"])),
        sorted(inspector.get_foreign_keys(table), key=lambda item: str(item["name"])),
        sorted(inspector.get_indexes(table), key=lambda item: str(item["name"])),
        [(item["name"], str(item["type"]), item["nullable"], item["default"]) for item in inspector.get_columns(table)],
    )


def _assert_foreign_keys(database: Database) -> None:
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_upgrade_starts_unproven_and_empty_roundtrip_preserves_parent_data(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'bili%baseline.sqlite3').as_posix()}")
    try:
        upgrade_database(database.url, PARENT)
        _seed_scope(database)
        parent_tables = sorted(set(inspect(database.engine).get_table_names()) - {"alembic_version"})
        before = _snapshot(database, parent_tables)

        upgrade_database(database.url, HEAD)

        assert set(inspect(database.engine).get_table_names()) == {
            *parent_tables,
            "alembic_version",
            "sync_run_contents",
            "bili_subscription_progress",
        }
        assert len(parent_tables) + 2 == 24
        assert _snapshot(database, parent_tables) == before
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
            assert connection.scalar(text("SELECT COUNT(*) FROM sync_run_contents")) == 0
            assert connection.scalar(text("SELECT COUNT(*) FROM bili_subscription_progress")) == 0
        _assert_foreign_keys(database)

        _downgrade(database, exclusive_maintenance=True)
        assert _snapshot(database, parent_tables) == before
        assert "sync_run_contents" not in inspect(database.engine).get_table_names()
        assert "bili_subscription_progress" not in inspect(database.engine).get_table_names()
        upgrade_database(database.url, HEAD)
        assert _snapshot(database, parent_tables) == before
        _assert_foreign_keys(database)
    finally:
        database.dispose()


def test_migrated_tables_match_current_metadata(tmp_path: Path) -> None:
    migrated = Database(f"sqlite+pysqlite:///{(tmp_path / 'migrated.sqlite3').as_posix()}")
    metadata = Database("sqlite+pysqlite:///:memory:")
    try:
        upgrade_database(migrated.url, HEAD)
        metadata.create_schema()
        for table in ("sync_run_contents", "bili_subscription_progress"):
            assert _shape(migrated, table) == _shape(metadata, table)
    finally:
        migrated.dispose()
        metadata.dispose()


@pytest.mark.parametrize("blocker", ["run_content", "delivery_progress"])
def test_downgrade_refuses_any_delivery_history_without_deleting_it(tmp_path: Path, blocker: str) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / f'{blocker}.sqlite3').as_posix()}")
    try:
        upgrade_database(database.url, HEAD)
        account_id, author_id, subscription_id, run_id, content_id = _seed_scope(database)
        with database.session() as session:
            if blocker == "run_content":
                session.add(
                    SyncRunContent(
                        run_id=run_id,
                        content_id=content_id,
                        subscription_id=subscription_id,
                        position=0,
                        asset_count=0,
                        observed_at=NOW,
                    )
                )
            else:
                session.add(
                    BiliSubscriptionProgress(
                        subscription_id=subscription_id,
                        phase="backfill",
                        generation_id=str(uuid4()),
                        account_id=account_id,
                        auth_revision=0,
                        author_id=author_id,
                        author_fingerprint_sha256=hashlib.sha256(b"252671524").hexdigest(),
                        scope="uploads",
                        policy_fingerprint_sha256="a" * 64,
                        upstream_sha="b" * 40,
                        checkpoint_revision=0,
                        schedule_revision=0,
                        created_at=NOW,
                        updated_at=NOW,
                    )
                )
        tables = inspect(database.engine).get_table_names()
        before = _snapshot(database, tables)
        with pytest.raises(RuntimeError, match="bili_delivery_history_prevents_downgrade"):
            _downgrade(database, exclusive_maintenance=True)
        assert _snapshot(database, tables) == before
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        _assert_foreign_keys(database)
    finally:
        database.dispose()


def test_sqlite_downgrade_requires_explicit_exclusive_maintenance(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'maintenance.sqlite3').as_posix()}")
    try:
        upgrade_database(database.url, HEAD)
        tables = inspect(database.engine).get_table_names()
        before = _snapshot(database, tables)
        with pytest.raises(
            RuntimeError,
            match="bili_delivery_sqlite_downgrade_requires_exclusive_maintenance",
        ):
            _downgrade(database)
        assert _snapshot(database, tables) == before
        _assert_foreign_keys(database)
    finally:
        database.dispose()


def test_offline_downgrade_requires_online_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = import_module(f"media_sync.infrastructure.db.migrations.versions.{HEAD}")
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_context=lambda: SimpleNamespace(as_sql=True)))
    with pytest.raises(RuntimeError, match="bili_delivery_downgrade_requires_online_audit"):
        migration.downgrade()


def test_postgresql_downgrade_locks_both_history_tables_before_auditing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module(f"media_sync.infrastructure.db.migrations.versions.{HEAD}")
    statements: list[str] = []

    class Connection:
        dialect = SimpleNamespace(name="postgresql")

        def execute(self, statement: object) -> SimpleNamespace:
            statements.append(" ".join(str(statement).split()))
            return SimpleNamespace(first=lambda: None)

    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            get_context=lambda: SimpleNamespace(as_sql=False),
            get_bind=lambda: Connection(),
            drop_table=lambda _table: None,
            drop_index=lambda _index, table_name: None,
        ),
    )
    migration.downgrade()
    assert statements == [
        "LOCK TABLE bili_subscription_progress, sync_run_contents IN ACCESS EXCLUSIVE MODE",
        "SELECT 1 FROM bili_subscription_progress LIMIT 1",
        "SELECT 1 FROM sync_run_contents LIMIT 1",
    ]


def test_postgresql_offline_upgrade_creates_only_new_delivery_tables() -> None:
    output = StringIO()
    with as_file(files(MIGRATIONS_PACKAGE)) as path:
        config = Config(output_buffer=output)
        config.set_main_option("script_location", str(path))
        config.set_main_option("sqlalchemy.url", "postgresql://example.invalid/media_sync")
        command.upgrade(config, f"{PARENT}:{HEAD}", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE sync_run_contents" in sql
    assert "CREATE TABLE bili_subscription_progress" in sql
    assert "source_end_observed_at TIMESTAMP WITH TIME ZONE" in sql
    assert "ON DELETE RESTRICT" in sql and "ON DELETE CASCADE" in sql
    assert "INSERT INTO sync_run_contents" not in sql
    assert "INSERT INTO bili_subscription_progress" not in sql
