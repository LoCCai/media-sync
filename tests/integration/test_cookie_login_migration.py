"""The new Operation kind preserves QR, profile, event and subject history."""

from __future__ import annotations

from importlib import import_module
from importlib.resources import as_file, files
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from media_sync.infrastructure.db import AccountRepository, Database, LoginSessionRepository, OperationRepository
from media_sync.infrastructure.db.migration import MIGRATIONS_PACKAGE, upgrade_database
from media_sync.infrastructure.db.models import OPERATION_KINDS

PARENT = "0010_creator_profiles"
HEAD = "0011_cookie_login"


def _downgrade(database: Database) -> None:
    with as_file(files(MIGRATIONS_PACKAGE)) as path:
        configuration = Config()
        configuration.set_main_option("script_location", str(path))
        configuration.set_main_option("sqlalchemy.url", database.url)
        command.downgrade(configuration, PARENT)


def test_upgrade_preserves_all_operation_children_qr_and_profile_history(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'upgrade.sqlite3').as_posix()}")
    try:
        upgrade_database(database.url, PARENT)
        with database.session() as session:
            account = AccountRepository(session).create(
                platform="bili",
                adapter="mediacrawler",
                display_name="Synthetic",
                login_method="saved_session",
                auth_status="authenticated",
            )
            LoginSessionRepository(session).create(account_id=account.id, method="qr", challenge_kind="qr")
            operation = OperationRepository(session).create_or_replay(
                kind="creator-profile", request_fingerprint="a" * 64, target_type="account", target_id=account.id
            )
            profile_id = str(uuid4())
            session.execute(
                text(
                    "INSERT INTO creator_profiles (id,account_id,platform,creator_remote_id,latest_operation_id) "
                    "VALUES (:id,:account,'bili','123',:operation)"
                ),
                {"id": profile_id, "account": account.id, "operation": operation.operation_id},
            )
            session.execute(
                text(
                    "INSERT INTO creator_profile_lookups "
                    "(operation_id,profile_id,generation,frontend_generation,credential_snapshot_digest,requested_at) "
                    "VALUES (:operation,:profile,1,:generation,:digest,CURRENT_TIMESTAMP)"
                ),
                {
                    "operation": operation.operation_id,
                    "profile": profile_id,
                    "generation": str(uuid4()),
                    "digest": "b" * 64,
                },
            )
        tables = [
            "accounts",
            "login_sessions",
            "operations",
            "operation_events",
            "operation_subjects",
            "creator_profiles",
            "creator_profile_lookups",
        ]
        with database.engine.connect() as connection:
            before = {table: connection.execute(text(f"SELECT * FROM {table}")).all() for table in tables}
        upgrade_database(database.url, HEAD)
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
            assert {table: connection.execute(text(f"SELECT * FROM {table}")).all() for table in tables} == before
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        _downgrade(database)
        with database.engine.connect() as connection:
            assert {table: connection.execute(text(f"SELECT * FROM {table}")).all() for table in tables} == before
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == PARENT
    finally:
        database.dispose()


def test_current_metadata_and_migration_allow_only_same_kinds(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'fresh.sqlite3').as_posix()}")
    try:
        upgrade_database(database.url)
        check = next(
            item
            for item in inspect(database.engine).get_check_constraints("operations")
            if item["name"] == "ck_operations_kind"
        )
        for kind in OPERATION_KINDS:
            assert f"'{kind}'" in check["sqltext"]
            with database.session() as session:
                OperationRepository(session).create_or_replay(kind=kind, request_fingerprint="a" * 64)
        with database.engine.begin() as connection, pytest.raises(IntegrityError):
            connection.execute(text("UPDATE operations SET kind='not-an-operation'"))
    finally:
        database.dispose()


@pytest.mark.parametrize("blocker", ["operation", "reference"])
def test_downgrade_refuses_cookie_history_or_live_managed_reference(tmp_path: Path, blocker: str) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'history.sqlite3').as_posix()}")
    try:
        upgrade_database(database.url)
        with database.session() as session:
            if blocker == "operation":
                OperationRepository(session).create_or_replay(kind="account-cookie-login", request_fingerprint="a" * 64)
            else:
                AccountRepository(session).create(
                    platform="bili",
                    display_name="Synthetic",
                    adapter="mediacrawler",
                    login_method="cookie",
                    credential_ref=f"managed:{uuid4()}",
                    auth_status="authenticated",
                )
        with pytest.raises(RuntimeError, match="prevent"):
            _downgrade(database)
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            if blocker == "operation":
                assert connection.scalar(text("SELECT kind FROM operations")) == "account-cookie-login"
            else:
                assert str(connection.scalar(text("SELECT credential_ref FROM accounts"))).startswith("managed:")
    finally:
        database.dispose()


def test_offline_downgrade_requires_online_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = import_module("media_sync.infrastructure.db.migrations.versions.0011_cookie_login")
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_context=lambda: SimpleNamespace(as_sql=True)))
    with pytest.raises(RuntimeError, match="requires_online_audit"):
        migration.downgrade()
