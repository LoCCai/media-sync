"""Exact delivery migration preserves audit history and refuses lossy downgrades."""

from __future__ import annotations

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
from sqlalchemy.exc import IntegrityError

from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    JobRepository,
    OperationRepository,
    OperationSubjectInput,
    SubscriptionRepository,
    SyncRunRepository,
    upgrade_database,
)
from media_sync.infrastructure.db.migration import MIGRATIONS_PACKAGE
from media_sync.infrastructure.db.models import OPERATION_KINDS, SubscriptionScanProgress

PARENT = "0012_library_output_policy"
HEAD = "0013_exact_subscription_delivery"
NOW = datetime(2026, 9, 6, tzinfo=UTC)


def _downgrade(database: Database, *, exclusive_maintenance: bool = False) -> None:
    with as_file(files(MIGRATIONS_PACKAGE)) as path:
        config = Config()
        config.set_main_option("script_location", str(path))
        config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
        if exclusive_maintenance:
            config.cmd_opts = SimpleNamespace(x=["exclusive-maintenance=true"])
        command.downgrade(config, PARENT)


def _seed_legacy(database: Database) -> tuple[str, str]:
    with database.session() as session:
        account = AccountRepository(session).create(platform="bili", adapter="fake", display_name="Synthetic")
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="bili", remote_id="12345", display_name="Synthetic author")
        )
        subscription = SubscriptionRepository(session).create(account_id=account.id, author_id=author.id)
        runs = SyncRunRepository(session)
        run = runs.create(subscription_id=subscription.id, attempt=1)
        for expected, status in (
            ("queued", "claimed"),
            ("claimed", "running"),
            ("running", "ingesting"),
            ("ingesting", "succeeded"),
        ):
            runs.set_status(run.id, status, expected_status=expected, at=NOW)
        job = JobRepository(session).enqueue(
            job_type="asset_download",
            natural_key="migration-fixture",
            payload={"fixture": "preserved"},
            subscription_id=subscription.id,
            account_id=account.id,
            platform="bili",
            run_id=run.id,
        )
        operations = OperationRepository(session)
        operation = operations.create_or_replay(
            kind="pipeline-run",
            request_fingerprint="a" * 64,
            idempotency_key_hash="b" * 64,
            exclusive_key="pipeline-run:fixture",
            at=NOW,
        )
        lease = operations.claim(
            operation.operation_id,
            expected_revision=operation.revision,
            lease_owner="migration-fixture",
            lease_seconds=60,
            at=NOW,
        )
        operations.link_subject(
            operation.operation_id,
            OperationSubjectInput("job", job.id, "execution"),
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            at=NOW,
        )
        return subscription.id, run.id


def _snapshot(database: Database, tables: list[str]) -> dict[str, list[tuple[object, ...]]]:
    with database.engine.connect() as connection:
        return {
            table: sorted((tuple(row) for row in connection.execute(text(f"SELECT * FROM {table}"))), key=repr)
            for table in tables
        }


def _assert_foreign_keys(database: Database) -> None:
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_upgrade_and_empty_downgrade_preserve_all_legacy_tables_and_audit_children(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'migration%history.sqlite3').as_posix()}")
    try:
        upgrade_database(database.url, PARENT)
        _seed_legacy(database)
        tables = sorted(set(inspect(database.engine).get_table_names()) - {"alembic_version"})
        before = _snapshot(database, tables)
        assert before["operation_events"] and before["operation_subjects"] and before["jobs"] and before["sync_runs"]
        upgrade_database(database.url, HEAD)
        assert set(inspect(database.engine).get_table_names()) == {
            *tables,
            "alembic_version",
            "subscription_scan_progress",
        }
        assert len(tables) + 1 == 22
        assert _snapshot(database, tables) == before
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
            assert connection.scalar(text("SELECT COUNT(*) FROM subscription_scan_progress")) == 0
        _assert_foreign_keys(database)
        indexes = {item["name"]: item for item in inspect(database.engine).get_indexes("operations")}
        assert indexes["uq_operations_active_exclusive_key"]["unique"] == 1
        assert indexes["uq_operations_kind_idempotency_key_hash"]["unique"] == 1
        assert (
            str(indexes["uq_operations_active_exclusive_key"]["dialect_options"]["sqlite_where"])
            == "exclusive_key IS NOT NULL AND state IN ('queued', 'running')"
        )
        _downgrade(database, exclusive_maintenance=True)
        assert _snapshot(database, tables) == before
        assert "subscription_scan_progress" not in inspect(database.engine).get_table_names()
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == PARENT
        _assert_foreign_keys(database)
        with database.engine.begin() as connection, pytest.raises(IntegrityError):
            connection.execute(text("UPDATE operations SET kind='subscription-delivery'"))
    finally:
        database.dispose()


@pytest.mark.parametrize("metadata", [False, True])
def test_migration_and_metadata_enforce_same_closed_operation_kinds(tmp_path: Path, metadata: bool) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'kinds.sqlite3').as_posix()}")
    try:
        if metadata:
            database.create_schema()
        else:
            upgrade_database(database.url, HEAD)
        check = next(
            item
            for item in inspect(database.engine).get_check_constraints("operations")
            if item["name"] == "ck_operations_kind"
        )
        assert "subscription-delivery" in OPERATION_KINDS
        assert {
            part.strip(" '") for part in check["sqltext"].removeprefix("kind IN (").removesuffix(")").split(",")
        } == set(OPERATION_KINDS)
        for kind in OPERATION_KINDS:
            with database.session() as session:
                OperationRepository(session).create_or_replay(kind=kind, request_fingerprint="a" * 64)
        with database.engine.begin() as connection, pytest.raises(IntegrityError):
            connection.execute(text("UPDATE operations SET kind='unknown-delivery'"))
        _assert_foreign_keys(database)
    finally:
        database.dispose()


@pytest.mark.parametrize("blocker", ["operation", "scanning", "unproven", "source_end_observed"])
def test_downgrade_refuses_any_new_history_without_deleting_rows(tmp_path: Path, blocker: str) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'blocked.sqlite3').as_posix()}")
    try:
        upgrade_database(database.url, HEAD)
        subscription_id, run_id = _seed_legacy(database)
        with database.session() as session:
            if blocker == "operation":
                OperationRepository(session).create_or_replay(
                    kind="subscription-delivery",
                    request_fingerprint="c" * 64,
                    target_type="subscription",
                    target_id=subscription_id,
                    at=NOW,
                )
            else:
                session.add(
                    SubscriptionScanProgress(
                        subscription_id=subscription_id,
                        feed="uploads",
                        state=blocker,
                        contract_version=2,
                        upstream_sha="a" * 40,
                        generation_id=str(uuid4()),
                        checkpoint_revision=1,
                        last_lane="history",
                        last_stop_reason="source_end" if blocker == "source_end_observed" else "list_limit",
                        started_at=NOW,
                        last_progress_at=NOW,
                        source_end_observed_at=NOW if blocker == "source_end_observed" else None,
                        source_end_run_id=run_id if blocker == "source_end_observed" else None,
                    )
                )
        tables = inspect(database.engine).get_table_names()
        before = _snapshot(database, tables)
        error = (
            "exact_delivery_history_prevents_downgrade"
            if blocker == "operation"
            else "scan_progress_history_prevents_downgrade"
        )
        with pytest.raises(RuntimeError, match=error):
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
            match="exact_delivery_sqlite_downgrade_requires_exclusive_maintenance",
        ):
            _downgrade(database)

        assert _snapshot(database, tables) == before
        assert "subscription_scan_progress" in inspect(database.engine).get_table_names()
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        _assert_foreign_keys(database)
    finally:
        database.dispose()


def test_scan_progress_constraints_match_metadata_and_migration(tmp_path: Path) -> None:
    migrated = Database(f"sqlite+pysqlite:///{(tmp_path / 'migrated.sqlite3').as_posix()}")
    metadata = Database(f"sqlite+pysqlite:///{(tmp_path / 'metadata.sqlite3').as_posix()}")
    try:
        upgrade_database(migrated.url, HEAD)
        metadata.create_schema()

        def shape(database: Database) -> tuple[object, ...]:
            inspector = inspect(database.engine)
            table = "subscription_scan_progress"
            return (
                inspector.get_pk_constraint(table),
                sorted(inspector.get_check_constraints(table), key=lambda item: item["name"]),
                sorted(inspector.get_foreign_keys(table), key=lambda item: item["name"]),
                [
                    (item["name"], str(item["type"]), item["nullable"], item["default"])
                    for item in inspector.get_columns(table)
                ],
            )

        assert shape(migrated) == shape(metadata)
    finally:
        migrated.dispose()
        metadata.dispose()


def test_offline_downgrade_requires_online_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = import_module(f"media_sync.infrastructure.db.migrations.versions.{HEAD}")
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_context=lambda: SimpleNamespace(as_sql=True)))
    with pytest.raises(RuntimeError, match="exact_delivery_downgrade_requires_online_audit"):
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

    connection = Connection()
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            get_context=lambda: SimpleNamespace(as_sql=False),
            get_bind=lambda: connection,
            drop_table=lambda _table: None,
        ),
    )
    monkeypatch.setattr(migration, "_replace", lambda _kinds: None)

    migration.downgrade()

    assert statements == [
        "LOCK TABLE operations, subscription_scan_progress IN ACCESS EXCLUSIVE MODE",
        "SELECT 1 FROM operations WHERE kind='subscription-delivery' LIMIT 1",
        "SELECT 1 FROM subscription_scan_progress LIMIT 1",
    ]


def test_postgresql_offline_upgrade_adds_only_scan_table_and_kind_constraint() -> None:
    output = StringIO()
    with as_file(files(MIGRATIONS_PACKAGE)) as path:
        config = Config(output_buffer=output)
        config.set_main_option("script_location", str(path))
        config.set_main_option("sqlalchemy.url", "postgresql://example.invalid/media_sync")
        command.upgrade(config, f"{PARENT}:{HEAD}", sql=True)
    sql = output.getvalue()
    assert "DROP CONSTRAINT ck_operations_kind" in sql
    assert "ADD CONSTRAINT ck_operations_kind CHECK" in sql
    assert "'subscription-delivery'" in sql
    assert "CREATE TABLE subscription_scan_progress" in sql
    assert "source_end_observed_at TIMESTAMP WITH TIME ZONE" in sql
    assert "ON DELETE RESTRICT" in sql and "ON DELETE CASCADE" in sql
    assert "CREATE TABLE operations" not in sql and "DROP TABLE operations" not in sql
    assert "INSERT INTO subscription_scan_progress" not in sql
