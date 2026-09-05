"""Synthetic accounts prove that candidate failure never changes old auth."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text

from media_sync.infrastructure.db import Account, AccountRepository, Database, LoginSessionRepository
from media_sync.infrastructure.db.cookie_account_repository import CookieAccountError, CookieAccountRepository
from media_sync.security.secrets import SecretReference


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'cookie.sqlite3').as_posix()}")
    database.create_schema()
    try:
        yield database
    finally:
        database.dispose()


def _account(database: Database, *, method: str = "saved_session", status: str = "authenticated") -> str:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter="mediacrawler",
            display_name=str(uuid4()),
            login_method=method,
            auth_status=status,
            credential_ref="env:SYNTHETIC_OLD_COOKIE" if method == "cookie" else None,
        )
        return account.id


def _reference() -> SecretReference:
    return SecretReference.parse(f"managed:{uuid4()}")


def _state(database: Database, account_id: str) -> tuple[object, ...]:
    with database.engine.connect() as connection:
        return tuple(connection.execute(text("SELECT * FROM accounts WHERE id=:id"), {"id": account_id}).one())


def test_snapshot_failure_and_outer_rollback_leave_every_account_column_unchanged(database: Database) -> None:
    account_id = _account(database, method="cookie")
    original = _state(database, account_id)
    with database.session() as session:
        snapshot = CookieAccountRepository(session).snapshot(account_id, "bili", 0)
    assert "SYNTHETIC_OLD_COOKIE" not in repr(snapshot)
    assert _state(database, account_id) == original
    with pytest.raises(RuntimeError, match="outer rollback"), database.session() as session:
        assert CookieAccountRepository(session).publish(snapshot, _reference()) == 1
        raise RuntimeError("outer rollback")
    assert _state(database, account_id) == original


@pytest.mark.parametrize(
    "method,status",
    [
        ("qr", "required"),
        ("saved_session", "expired"),
        ("saved_session", "authenticated"),
        ("cookie", "authenticated"),
        ("cookie", "failed"),
    ],
)
def test_success_cas_publishes_one_revision_without_modifying_login_history(
    database: Database, method: str, status: str
) -> None:
    account_id = _account(database, method=method, status=status)
    reference = _reference()
    with database.session() as session:
        repository = CookieAccountRepository(session)
        snapshot = repository.snapshot(account_id, "bili", 0)
        assert repository.publish(snapshot, reference) == 1
        account = session.get(Account, account_id)
        assert account is not None
        assert (account.login_method, account.auth_status, account.credential_ref, account.auth_revision) == (
            "cookie",
            "authenticated",
            reference.serialize(),
            1,
        )
        assert account.auth_updated_at is not None
        assert LoginSessionRepository(session).list_for_account(account_id) == []
    with database.session() as session, pytest.raises(CookieAccountError, match="conflict"):
        CookieAccountRepository(session).publish(snapshot, _reference())


@pytest.mark.parametrize(
    "column,value",
    [
        ("adapter", "native"),
        ("platform", "wb"),
        ("login_method", "cookie"),
        ("credential_ref", "env:CHANGED"),
        ("profile_path", "changed-profile"),
        ("auth_status", "expired"),
        ("auth_updated_at", datetime(2030, 1, 1, tzinfo=UTC)),
        ("auth_revision", 2),
    ],
)
def test_every_auth_identity_field_is_refenced(database: Database, column: str, value: object) -> None:
    account_id = _account(database)
    with database.session() as session:
        snapshot = CookieAccountRepository(session).snapshot(account_id, "bili", 0)
    with database.session() as session:
        account = session.get(Account, account_id)
        assert account is not None
        setattr(account, column, value)
    drifted = _state(database, account_id)
    with database.session() as session, pytest.raises(CookieAccountError):
        CookieAccountRepository(session).publish(snapshot, _reference())
    assert _state(database, account_id) == drifted


def test_same_time_auth_aba_and_forged_snapshot_rejected(database: Database) -> None:
    account_id = _account(database)
    with database.session() as session:
        repository = CookieAccountRepository(session)
        snapshot = repository.snapshot(account_id, "bili", 0)
    instant = datetime(2030, 1, 1, tzinfo=UTC)
    with database.session() as session:
        account = session.get(Account, account_id)
        assert account is not None
        account.auth_updated_at = instant
    with database.session() as session:
        snapshot = CookieAccountRepository(session).snapshot(account_id, "bili", 0)
        accounts = AccountRepository(session)
        accounts.set_auth_status(account_id, "expired", expected_status="authenticated", at=instant)
        accounts.set_auth_status(account_id, "authenticating", expected_status="expired", at=instant)
        accounts.set_auth_status(account_id, "authenticated", expected_status="authenticating", at=instant)
    with database.session() as session, pytest.raises(CookieAccountError, match="conflict"):
        CookieAccountRepository(session).publish(snapshot, _reference())
    with database.session() as session, pytest.raises(CookieAccountError, match="conflict"):
        CookieAccountRepository(session).publish(replace(snapshot, credential_ref="env:FORGED"), _reference())


@pytest.mark.parametrize("status", ["pending", "waiting_user"])
def test_active_qr_prevents_snapshot_and_late_publish_without_changing_account(database: Database, status: str) -> None:
    account_id = _account(database)
    with database.session() as session:
        snapshot = CookieAccountRepository(session).snapshot(account_id, "bili", 0)
        login = LoginSessionRepository(session).create(
            account_id=account_id, method="qr", challenge_kind="qr", expires_at=datetime.now(UTC) + timedelta(minutes=1)
        )
        login.status = status
    original = _state(database, account_id)
    with database.session() as session, pytest.raises(CookieAccountError, match="busy"):
        CookieAccountRepository(session).snapshot(account_id, "bili", 0)
    with database.session() as session, pytest.raises(CookieAccountError, match="busy"):
        CookieAccountRepository(session).publish(snapshot, _reference())
    assert _state(database, account_id) == original


@pytest.mark.parametrize("revision", [-1, True, 1, 2**63 - 1])
def test_bad_revision_is_rejected_without_mutation(database: Database, revision: int) -> None:
    account_id = _account(database)
    original = _state(database, account_id)
    with database.session() as session, pytest.raises(CookieAccountError, match="conflict"):
        CookieAccountRepository(session).snapshot(account_id, "bili", revision)
    assert _state(database, account_id) == original


def test_absent_wrong_platform_wrong_backend_and_nonmanaged_reference(database: Database) -> None:
    account_id = _account(database)
    with database.session() as session, pytest.raises(CookieAccountError, match="not_found"):
        CookieAccountRepository(session).snapshot(str(uuid4()), "bili", 0)
    with database.session() as session, pytest.raises(CookieAccountError, match="conflict"):
        CookieAccountRepository(session).snapshot(account_id, "wb", 0)
    with database.session() as session:
        repository = CookieAccountRepository(session)
        snapshot = repository.snapshot(account_id, "bili", 0)
        with pytest.raises(CookieAccountError, match="unavailable"):
            repository.publish(snapshot, "env:UNVERIFIED")
    assert CookieAccountError("SYNTHETIC-SECRET").code == "cookie_login_unavailable"


def test_two_connections_publish_only_one_version(database: Database) -> None:
    account_id = _account(database)
    with database.session() as session:
        snapshot = CookieAccountRepository(session).snapshot(account_id, "bili", 0)
    barrier = Barrier(2)

    def attempt() -> int | str:
        barrier.wait(timeout=10)
        try:
            with database.session() as session:
                return CookieAccountRepository(session).publish(snapshot, _reference())
        except CookieAccountError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(attempt) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]
    assert results.count(1) == 1 and results.count("cookie_login_conflict") == 1
