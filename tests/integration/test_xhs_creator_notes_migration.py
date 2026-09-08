"""XHS creator-note progress migration is empty-by-default and loss-aware."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from importlib import import_module
from importlib.resources import as_file, files
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
    Database,
    SubscriptionRepository,
    XhsSubscriptionProgress,
    upgrade_database,
)
from media_sync.infrastructure.db.migration import MIGRATIONS_PACKAGE

PARENT = "0014_bili_delivery_baseline"
HEAD = "0015_xhs_creator_notes"
NOW = datetime(2026, 9, 8, tzinfo=UTC)


def _downgrade(database: Database, *, exclusive: bool = False) -> None:
    with as_file(files(MIGRATIONS_PACKAGE)) as path:
        config = Config()
        config.set_main_option("script_location", str(path))
        config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
        if exclusive:
            config.cmd_opts = SimpleNamespace(x=["exclusive-maintenance=true"])
        command.downgrade(config, PARENT)


def _shape(database: Database, table: str) -> tuple[object, ...]:
    inspector = inspect(database.engine)
    return (
        inspector.get_pk_constraint(table),
        sorted(inspector.get_check_constraints(table), key=lambda item: str(item["name"])),
        sorted(inspector.get_foreign_keys(table), key=lambda item: str(item["name"])),
        [(item["name"], str(item["type"]), item["nullable"], item["default"]) for item in inspector.get_columns(table)],
    )


def _seed(database: Database) -> tuple[str, str, str]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="xhs",
            adapter="mediacrawler",
            display_name="XHS migration",
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="xhs", remote_id="5f1234567890abcdef123456", display_name="XHS migration")
        )
        subscription = SubscriptionRepository(session).create(account_id=account.id, author_id=author.id)
        return account.id, author.id, subscription.id


def test_upgrade_is_empty_matches_metadata_and_empty_roundtrip(tmp_path: Path) -> None:
    migrated = Database(f"sqlite+pysqlite:///{(tmp_path / 'xhs%progress.sqlite3').as_posix()}")
    metadata = Database("sqlite+pysqlite:///:memory:")
    try:
        upgrade_database(migrated.url, PARENT)
        parent_tables = set(inspect(migrated.engine).get_table_names())
        upgrade_database(migrated.url, HEAD)
        assert set(inspect(migrated.engine).get_table_names()) == parent_tables | {"xhs_subscription_progress"}
        with migrated.engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM xhs_subscription_progress")) == 0
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        metadata.create_schema()
        assert _shape(migrated, "xhs_subscription_progress") == _shape(metadata, "xhs_subscription_progress")

        _downgrade(migrated, exclusive=True)
        assert set(inspect(migrated.engine).get_table_names()) == parent_tables
        upgrade_database(migrated.url, HEAD)
        assert "xhs_subscription_progress" in inspect(migrated.engine).get_table_names()
    finally:
        migrated.dispose()
        metadata.dispose()


def test_downgrade_refuses_progress_history_and_preserves_it(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'history.sqlite3').as_posix()}")
    try:
        upgrade_database(database.url, HEAD)
        account_id, author_id, subscription_id = _seed(database)
        with database.session() as session:
            session.add(
                XhsSubscriptionProgress(
                    subscription_id=subscription_id,
                    phase="backfill",
                    generation_id=str(uuid4()),
                    account_id=account_id,
                    auth_revision=0,
                    author_id=author_id,
                    author_fingerprint_sha256=hashlib.sha256(b"5f1234567890abcdef123456").hexdigest(),
                    creator_fingerprint_sha256="a" * 64,
                    scope="notes",
                    policy_fingerprint_sha256="b" * 64,
                    upstream_sha="c" * 40,
                    checkpoint_revision=0,
                    schedule_revision=0,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        with pytest.raises(RuntimeError, match="xhs_creator_notes_history_prevents_downgrade"):
            _downgrade(database, exclusive=True)
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM xhs_subscription_progress")) == 1
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
    finally:
        database.dispose()


def test_sqlite_and_offline_downgrades_require_explicit_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'maintenance.sqlite3').as_posix()}")
    try:
        upgrade_database(database.url, HEAD)
        with pytest.raises(RuntimeError, match="xhs_creator_notes_sqlite_downgrade_requires_exclusive_maintenance"):
            _downgrade(database)
    finally:
        database.dispose()

    migration = import_module(f"media_sync.infrastructure.db.migrations.versions.{HEAD}")
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_context=lambda: SimpleNamespace(as_sql=True)))
    with pytest.raises(RuntimeError, match="xhs_creator_notes_downgrade_requires_online_audit"):
        migration.downgrade()
