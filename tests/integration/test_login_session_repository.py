"""Transactional acceptance for the interactive QR login repository state."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, update

from media_sync.infrastructure.db import (
    AccountLoginConflictError,
    AccountRepository,
    Database,
    LoginSessionConflictError,
    LoginSessionRepository,
    LoginSessionState,
    NotFoundError,
)
from media_sync.infrastructure.db.models import Account, LoginSession

NOW = datetime(2026, 8, 31, 3, 0, tzinfo=UTC)
EXPIRY = NOW + timedelta(minutes=5)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"


def _database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def _alembic_config(database_url: str) -> Config:
    configuration = Config(str(ALEMBIC_INI))
    configuration.set_main_option("sqlalchemy.url", database_url)
    return configuration


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    database_url = _database_url(tmp_path / "interactive-login.sqlite3")
    command.upgrade(_alembic_config(database_url), "head")
    instance = Database(database_url)
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_account(
    database: Database,
    *,
    adapter: str = "mediacrawler",
    login_method: str = "qr",
    auth_status: str = "unknown",
    credential_ref: str | None = None,
    profile_path: str | None = None,
) -> str:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter=adapter,
            display_name=f"{adapter}-{login_method}-{auth_status}",
            login_method=login_method,
            auth_status=auth_status,
            credential_ref=credential_ref,
            profile_path=profile_path,
        )
        return account.id


def _start_and_wait(database: Database, account_id: str) -> str:
    with database.session() as session:
        repository = LoginSessionRepository(session)
        started = repository.start_mediacrawler_qr(account_id, expires_at=EXPIRY, at=NOW)
        waiting = repository.mark_waiting_user(started.id, at=NOW + timedelta(seconds=1))
        assert waiting.status == "waiting_user"
        return waiting.id


def test_qr_success_handoff_is_atomic_and_returns_only_safe_state(database: Database) -> None:
    account_id = _seed_account(database)

    with database.session() as session:
        repository = LoginSessionRepository(session)
        started = repository.start_mediacrawler_qr(account_id, expires_at=EXPIRY, at=NOW)

        assert isinstance(started, LoginSessionState)
        assert started.status == "pending"
        assert set(asdict(started)) == {
            "id",
            "account_id",
            "status",
            "expires_at",
            "completed_at",
            "created_at",
            "updated_at",
        }
        account = session.get(Account, account_id)
        stored = session.get(LoginSession, started.id)
        assert account is not None
        assert (account.login_method, account.auth_status, account.auth_updated_at) == (
            "qr",
            "authenticating",
            NOW,
        )
        assert account.credential_ref is None and account.profile_path is None
        assert stored is not None
        assert (stored.method, stored.challenge_kind, stored.public_payload) == ("qr", "qr", {})

        waiting = repository.mark_waiting_user(started.id, at=NOW + timedelta(seconds=1))
        succeeded = repository.succeed_mediacrawler_qr(
            waiting.id,
            at=NOW + timedelta(seconds=2),
        )
        assert (succeeded.status, succeeded.completed_at) == (
            "succeeded",
            NOW + timedelta(seconds=2),
        )
        assert repository.get_active_for_account(account_id) is None
        assert repository.list_for_account(account_id) == [succeeded]

    with database.session() as session:
        account = session.get(Account, account_id)
        stored = session.get(LoginSession, succeeded.id)
        assert account is not None
        assert (account.login_method, account.auth_status, account.auth_updated_at) == (
            "saved_session",
            "authenticated",
            NOW + timedelta(seconds=2),
        )
        assert account.credential_ref is None and account.profile_path is None
        assert stored is not None
        assert stored.status == "succeeded" and stored.public_payload == {}


@pytest.mark.parametrize(
    ("login_method", "auth_status"),
    [
        ("qr", "unknown"),
        ("qr", "required"),
        ("qr", "expired"),
        ("qr", "failed"),
        ("saved_session", "expired"),
    ],
)
def test_retryable_account_auth_states_can_start_qr_login(
    database: Database,
    login_method: str,
    auth_status: str,
) -> None:
    account_id = _seed_account(database, login_method=login_method, auth_status=auth_status)

    with database.session() as session:
        started = LoginSessionRepository(session).start_mediacrawler_qr(
            account_id,
            expires_at=EXPIRY,
            at=NOW,
        )
        account = session.get(Account, account_id)
        assert started.status == "pending"
        assert account is not None
        assert (account.login_method, account.auth_status) == ("qr", "authenticating")


@pytest.mark.parametrize(
    ("adapter", "login_method", "auth_status"),
    [
        ("fake", "qr", "unknown"),
        ("mediacrawler", "cookie", "unknown"),
        ("mediacrawler", "saved_session", "unknown"),
        ("mediacrawler", "saved_session", "required"),
        ("mediacrawler", "saved_session", "authenticated"),
        ("mediacrawler", "saved_session", "failed"),
        ("mediacrawler", "phone", "unknown"),
        ("mediacrawler", "qr", "authenticated"),
        ("mediacrawler", "qr", "authenticating"),
    ],
)
def test_ineligible_account_scope_has_zero_session_or_account_writes(
    database: Database,
    adapter: str,
    login_method: str,
    auth_status: str,
) -> None:
    account_id = _seed_account(
        database,
        adapter=adapter,
        login_method=login_method,
        auth_status=auth_status,
    )

    with database.session() as session:
        repository = LoginSessionRepository(session)
        with pytest.raises(AccountLoginConflictError):
            repository.start_mediacrawler_qr(account_id, expires_at=EXPIRY, at=NOW)

        account = session.get(Account, account_id)
        assert account is not None
        assert (account.adapter, account.login_method, account.auth_status, account.auth_updated_at) == (
            adapter,
            login_method,
            auth_status,
            None,
        )
        assert session.scalar(select(func.count()).select_from(LoginSession)) == 0

    with database.session() as session:
        account = session.get(Account, account_id)
        assert account is not None and account.auth_status == auth_status
        assert session.scalar(select(func.count()).select_from(LoginSession)) == 0


def test_missing_account_and_invalid_expiry_have_zero_writes(database: Database) -> None:
    missing_id = "00000000-0000-0000-0000-000000000000"
    account_id = _seed_account(database)

    with database.session() as session:
        repository = LoginSessionRepository(session)
        with pytest.raises(NotFoundError):
            repository.start_mediacrawler_qr(missing_id, expires_at=EXPIRY, at=NOW)
        with pytest.raises(ValueError, match="expiry"):
            repository.start_mediacrawler_qr(account_id, expires_at=NOW, at=NOW)
        with pytest.raises(ValueError, match="timezone-aware"):
            repository.start_mediacrawler_qr(
                account_id,
                expires_at=EXPIRY.replace(tzinfo=None),
                at=NOW,
            )
        account = session.get(Account, account_id)
        assert account is not None and account.auth_status == "unknown"
        assert session.scalar(select(func.count()).select_from(LoginSession)) == 0


@pytest.mark.parametrize(
    ("credential_ref", "profile_path"),
    [
        ("env:MEDIA_SYNC_CORRUPT_QR_CREDENTIAL", None),
        (None, "legacy-profile-marker"),
    ],
)
def test_qr_account_with_persisted_secret_or_profile_reference_is_rejected_without_mutation(
    database: Database,
    credential_ref: str | None,
    profile_path: str | None,
) -> None:
    account_id = _seed_account(
        database,
        credential_ref=credential_ref,
        profile_path=profile_path,
    )

    with database.session() as session:
        repository = LoginSessionRepository(session)
        with pytest.raises(AccountLoginConflictError):
            repository.start_mediacrawler_qr(account_id, expires_at=EXPIRY, at=NOW)
        account = session.get(Account, account_id)
        assert account is not None
        assert (account.auth_status, account.auth_updated_at) == ("unknown", None)
        assert (account.credential_ref, account.profile_path) == (credential_ref, profile_path)
        assert session.scalar(select(func.count()).select_from(LoginSession)) == 0


def test_duplicate_start_is_fenced_without_partial_commit(database: Database) -> None:
    account_id = _seed_account(database)

    with database.session() as session:
        repository = LoginSessionRepository(session)
        started = repository.start_mediacrawler_qr(account_id, expires_at=EXPIRY, at=NOW)
        with pytest.raises(AccountLoginConflictError):
            repository.start_mediacrawler_qr(
                account_id,
                expires_at=EXPIRY + timedelta(minutes=1),
                at=NOW + timedelta(seconds=1),
            )
        account = session.get(Account, account_id)
        sessions = repository.list_for_account(account_id)
        assert account is not None and account.auth_status == "authenticating"
        assert sessions == [started]

    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(LoginSession)) == 1
        account = session.get(Account, account_id)
        assert account is not None and account.auth_updated_at == NOW


@pytest.mark.parametrize(
    ("login_method", "auth_status"),
    [("qr", "unknown"), ("saved_session", "expired")],
)
def test_two_connection_start_race_has_one_winner_and_one_fixed_conflict(
    database: Database,
    login_method: str,
    auth_status: str,
) -> None:
    account_id = _seed_account(database, login_method=login_method, auth_status=auth_status)
    barrier = Barrier(2)

    def contend(offset: int) -> str:
        barrier.wait(timeout=5)
        try:
            with database.session() as session:
                LoginSessionRepository(session).start_mediacrawler_qr(
                    account_id,
                    expires_at=EXPIRY + timedelta(seconds=offset),
                    at=NOW + timedelta(microseconds=offset),
                )
            return "started"
        except AccountLoginConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(contend, [1, 2]))

    assert sorted(outcomes) == ["conflict", "started"]
    with database.session() as session:
        repository = LoginSessionRepository(session)
        active = repository.get_active_for_account(account_id)
        assert active is not None and active.status == "pending"
        assert session.scalar(select(func.count()).select_from(LoginSession)) == 1


@pytest.mark.parametrize(
    ("method_name", "session_status", "account_status"),
    [
        ("expire_mediacrawler_qr", "expired", "required"),
        ("fail_mediacrawler_qr", "failed", "failed"),
        ("cancel_mediacrawler_qr", "cancelled", "required"),
    ],
)
def test_non_success_terminal_states_keep_qr_and_map_account_conservatively(
    database: Database,
    method_name: str,
    session_status: str,
    account_status: str,
) -> None:
    account_id = _seed_account(database)
    login_session_id = _start_and_wait(database, account_id)

    with database.session() as session:
        repository = LoginSessionRepository(session)
        terminal = getattr(repository, method_name)(login_session_id, at=NOW + timedelta(seconds=2))
        account = session.get(Account, account_id)
        assert terminal.status == session_status
        assert account is not None
        assert (account.login_method, account.auth_status, account.auth_updated_at) == (
            "qr",
            account_status,
            NOW + timedelta(seconds=2),
        )
        assert account.profile_path is None


def test_duplicate_and_stale_transitions_do_not_mutate_terminal_handoff(database: Database) -> None:
    account_id = _seed_account(database)
    login_session_id = _start_and_wait(database, account_id)

    with database.session() as session:
        repository = LoginSessionRepository(session)
        succeeded = repository.succeed_mediacrawler_qr(
            login_session_id,
            at=NOW + timedelta(seconds=2),
        )
        with pytest.raises(LoginSessionConflictError):
            repository.fail_mediacrawler_qr(
                login_session_id,
                at=NOW + timedelta(seconds=3),
            )
        with pytest.raises(LoginSessionConflictError):
            repository.mark_waiting_user(login_session_id, at=NOW + timedelta(seconds=3))

        account = session.get(Account, account_id)
        stored = session.get(LoginSession, login_session_id)
        assert succeeded.status == "succeeded"
        assert account is not None
        assert (account.login_method, account.auth_status) == ("saved_session", "authenticated")
        assert stored is not None
        assert (stored.status, stored.completed_at) == ("succeeded", NOW + timedelta(seconds=2))


def test_account_state_drift_fences_completion_without_partial_session_write(database: Database) -> None:
    account_id = _seed_account(database)
    login_session_id = _start_and_wait(database, account_id)

    with database.session() as session:
        session.execute(
            update(Account)
            .where(Account.id == account_id)
            .values(auth_status="required", auth_updated_at=NOW + timedelta(seconds=2))
        )

    with database.session() as session:
        repository = LoginSessionRepository(session)
        with pytest.raises(LoginSessionConflictError):
            repository.succeed_mediacrawler_qr(
                login_session_id,
                at=NOW + timedelta(seconds=3),
            )
        account = session.get(Account, account_id)
        stored = session.get(LoginSession, login_session_id)
        assert account is not None and (account.login_method, account.auth_status) == ("qr", "required")
        assert stored is not None and (stored.status, stored.completed_at) == ("waiting_user", None)

    with database.session() as session:
        stored = session.get(LoginSession, login_session_id)
        assert stored is not None and stored.status == "waiting_user"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("credential_ref", "env:MEDIA_SYNC_LOGIN_DRIFT_SENTINEL"),
        ("profile_path", "legacy-drift-profile"),
    ],
)
def test_account_secret_or_profile_drift_fences_completion_without_overwrite(
    database: Database,
    field: str,
    value: str,
) -> None:
    account_id = _seed_account(database)
    login_session_id = _start_and_wait(database, account_id)

    with database.session() as session:
        session.execute(update(Account).where(Account.id == account_id).values(**{field: value}))

    with database.session() as session:
        repository = LoginSessionRepository(session)
        with pytest.raises(LoginSessionConflictError):
            repository.succeed_mediacrawler_qr(
                login_session_id,
                at=NOW + timedelta(seconds=3),
            )
        account = session.get(Account, account_id)
        stored = session.get(LoginSession, login_session_id)
        assert account is not None
        assert (account.login_method, account.auth_status) == ("qr", "authenticating")
        assert getattr(account, field) == value
        assert stored is not None and (stored.status, stored.completed_at) == ("waiting_user", None)


def test_deadline_fences_waiting_and_success_then_expiry_recovers_account(database: Database) -> None:
    account_id = _seed_account(database)

    with database.session() as session:
        repository = LoginSessionRepository(session)
        pending = repository.start_mediacrawler_qr(account_id, expires_at=EXPIRY, at=NOW)
        with pytest.raises(LoginSessionConflictError):
            repository.mark_waiting_user(pending.id, at=EXPIRY)
        stored = session.get(LoginSession, pending.id)
        assert stored is not None and stored.status == "pending"

    second_account_id = _seed_account(database, auth_status="required")
    waiting_id = _start_and_wait(database, second_account_id)
    with database.session() as session:
        repository = LoginSessionRepository(session)
        with pytest.raises(LoginSessionConflictError):
            repository.succeed_mediacrawler_qr(waiting_id, at=EXPIRY)
        stored = session.get(LoginSession, waiting_id)
        account = session.get(Account, second_account_id)
        assert stored is not None and (stored.status, stored.completed_at) == ("waiting_user", None)
        assert account is not None and account.auth_status == "authenticating"

        expired = repository.expire_mediacrawler_qr(waiting_id, at=EXPIRY)
        account = session.get(Account, second_account_id)
        assert expired.status == "expired"
        assert account is not None and (account.login_method, account.auth_status) == ("qr", "required")


def test_terminal_s1_then_s2_start_fences_stale_s1_completion(database: Database) -> None:
    account_id = _seed_account(database)
    first_id = _start_and_wait(database, account_id)

    with database.session() as session:
        repository = LoginSessionRepository(session)
        cancelled = repository.cancel_mediacrawler_qr(first_id, at=NOW + timedelta(seconds=2))
        second = repository.start_mediacrawler_qr(
            account_id,
            expires_at=EXPIRY + timedelta(minutes=1),
            at=NOW + timedelta(seconds=3),
        )
        with pytest.raises(LoginSessionConflictError):
            repository.succeed_mediacrawler_qr(first_id, at=NOW + timedelta(seconds=4))

        account = session.get(Account, account_id)
        stored_first = session.get(LoginSession, first_id)
        stored_second = session.get(LoginSession, second.id)
        assert cancelled.status == "cancelled"
        assert account is not None and (account.login_method, account.auth_status) == ("qr", "authenticating")
        assert stored_first is not None and stored_first.status == "cancelled"
        assert stored_second is not None and stored_second.status == "pending"


def test_active_sibling_fences_terminal_transition_and_safe_listing(database: Database) -> None:
    account_id = _seed_account(database)

    with database.session() as session:
        repository = LoginSessionRepository(session)
        first = repository.start_mediacrawler_qr(account_id, expires_at=EXPIRY, at=NOW)
        first = repository.mark_waiting_user(first.id, at=NOW + timedelta(seconds=1))
        sibling = repository.create(
            account_id=account_id,
            method="qr",
            challenge_kind="qr",
            public_payload={"cookie": "must-not-escape"},
            expires_at=EXPIRY,
        )

        with pytest.raises(LoginSessionConflictError):
            repository.succeed_mediacrawler_qr(first.id, at=NOW + timedelta(seconds=2))
        with pytest.raises(AccountLoginConflictError):
            repository.get_active_for_account(account_id)

        listed = repository.list_for_account(account_id)
        assert {item.id for item in listed} == {first.id, sibling.id}
        assert all(not hasattr(item, "public_payload") for item in listed)
        account = session.get(Account, account_id)
        stored_first = session.get(LoginSession, first.id)
        assert account is not None and (account.login_method, account.auth_status) == ("qr", "authenticating")
        assert stored_first is not None and (stored_first.status, stored_first.completed_at) == (
            "waiting_user",
            None,
        )

    with database.session() as session:
        account = session.get(Account, account_id)
        stored_first = session.get(LoginSession, first.id)
        assert account is not None and account.auth_status == "authenticating"
        assert stored_first is not None and stored_first.status == "waiting_user"


def test_unknown_session_and_account_auth_cas_are_fixed_zero_write_errors(database: Database) -> None:
    account_id = _seed_account(database)
    missing_id = "00000000-0000-0000-0000-000000000000"

    with database.session() as session:
        repository = LoginSessionRepository(session)
        with pytest.raises(NotFoundError):
            repository.succeed_mediacrawler_qr(missing_id, at=NOW)
        accounts = AccountRepository(session)
        required = accounts.set_auth_status(
            account_id,
            "required",
            expected_status="unknown",
            at=NOW,
        )
        assert required.auth_status == "required"
        with pytest.raises(AccountLoginConflictError):
            accounts.set_auth_status(
                account_id,
                "authenticating",
                expected_status="unknown",
                at=NOW + timedelta(seconds=1),
            )
        account = session.get(Account, account_id)
        assert account is not None and (account.auth_status, account.auth_updated_at) == ("required", NOW)
