"""Application-level acceptance for explicit MediaCrawler QR login orchestration."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from media_sync.application.authentication import (
    AccountLoginError,
    AccountLoginRequest,
    MediaCrawlerQrLoginService,
)
from media_sync.domain import AuthStatus, Platform
from media_sync.infrastructure.db import (
    AccountRepository,
    Database,
    LoginSessionRepository,
)
from media_sync.infrastructure.db.models import LoginSession
from media_sync.integrations.mediacrawler import (
    MediaCrawlerLoginMode,
    MediaCrawlerLoginRequest,
    MediaCrawlerLoginResult,
    MediaCrawlerLoginStatus,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
STARTED_AT = datetime(2026, 8, 31, 4, 0, tzinfo=UTC)


def _database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def _alembic_config(database_url: str) -> Config:
    configuration = Config(str(ALEMBIC_INI))
    configuration.set_main_option("sqlalchemy.url", database_url)
    return configuration


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    database_url = _database_url(tmp_path / "login-application.sqlite3")
    command.upgrade(_alembic_config(database_url), "head")
    instance = Database(database_url)
    try:
        yield instance
    finally:
        instance.dispose()


class _Clock:
    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)

    def __call__(self) -> datetime:
        return next(self._values)


class _Runner:
    def __init__(
        self,
        result: object,
        *,
        invoke_hook: bool,
        after_hook: Callable[[], None] | None = None,
    ) -> None:
        self.result = result
        self.invoke_hook = invoke_hook
        self.after_hook = after_hook
        self.requests: list[MediaCrawlerLoginRequest] = []
        self.hook_calls = 0
        self.cancellation: threading.Event | None = None

    def run(
        self,
        request: MediaCrawlerLoginRequest,
        *,
        on_account_locked: Callable[[], None] | None = None,
        cancellation: threading.Event | None = None,
    ) -> MediaCrawlerLoginResult:
        self.requests.append(request)
        self.cancellation = cancellation
        if self.invoke_hook:
            assert on_account_locked is not None
            on_account_locked()
            self.hook_calls += 1
            if self.after_hook is not None:
                self.after_hook()
        if isinstance(self.result, BaseException):
            raise self.result
        return cast(MediaCrawlerLoginResult, self.result)


def _result(status: MediaCrawlerLoginStatus) -> MediaCrawlerLoginResult:
    return MediaCrawlerLoginResult(status, UPSTREAM_SHA)


def _seed_account(
    database: Database,
    *,
    adapter: str = "mediacrawler",
    login_method: str = "qr",
    auth_status: str = "unknown",
    credential_ref: str | None = None,
    profile_path: str | None = None,
) -> UUID:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter=adapter,
            display_name=f"login-app-{uuid4()}",
            login_method=login_method,
            auth_status=auth_status,
            credential_ref=credential_ref,
            profile_path=profile_path,
        )
        return UUID(account.id)


def _session_count(database: Database) -> int:
    with database.session() as session:
        return int(session.scalar(select(func.count()).select_from(LoginSession)) or 0)


@pytest.mark.parametrize(
    ("runner_status", "session_status", "account_status", "login_method", "authenticated"),
    [
        (MediaCrawlerLoginStatus.AUTHENTICATED, "succeeded", "authenticated", "saved_session", True),
        (MediaCrawlerLoginStatus.EXPIRED, "expired", "required", "qr", False),
        (MediaCrawlerLoginStatus.TIMED_OUT, "expired", "required", "qr", False),
        (MediaCrawlerLoginStatus.FAILED, "failed", "failed", "qr", False),
        (MediaCrawlerLoginStatus.CANCELLED, "cancelled", "required", "qr", False),
    ],
)
def test_locked_waiting_session_maps_closed_runner_outcomes(
    database: Database,
    runner_status: MediaCrawlerLoginStatus,
    session_status: str,
    account_status: str,
    login_method: str,
    authenticated: bool,
) -> None:
    account_id = _seed_account(database)
    observed: dict[str, object] = {}

    def observe_waiting() -> None:
        with database.session() as session:
            account = AccountRepository(session).require(str(account_id))
            active = LoginSessionRepository(session).get_active_for_account(str(account_id))
            stored = session.get(LoginSession, active.id if active is not None else "")
            observed.update(
                account_status=account.auth_status,
                login_method=account.login_method,
                session_status=active.status if active is not None else None,
                public_payload=stored.public_payload if stored is not None else None,
            )

    runner = _Runner(_result(runner_status), invoke_hook=True, after_hook=observe_waiting)
    cancellation = threading.Event()
    finished_at = STARTED_AT + timedelta(seconds=2)
    service = MediaCrawlerQrLoginService(
        database,
        runner,
        clock=_Clock(STARTED_AT, finished_at),
    )

    outcome = service.run(
        AccountLoginRequest(account_id=account_id, timeout_seconds=60, poll_seconds=1),
        cancellation=cancellation,
    )

    assert observed == {
        "account_status": "authenticating",
        "login_method": "qr",
        "session_status": "waiting_user",
        "public_payload": {},
    }
    assert runner.hook_calls == 1 and runner.cancellation is cancellation
    assert len(runner.requests) == 1
    integration_request = runner.requests[0]
    assert (
        integration_request.account_id,
        integration_request.platform,
        integration_request.mode,
        integration_request.timeout_seconds,
        integration_request.poll_seconds,
    ) == (account_id, Platform.BILI, MediaCrawlerLoginMode.INTERACTIVE_QR, 60.0, 1.0)
    assert (outcome.runner_status, outcome.session_status, outcome.auth_status, outcome.authenticated) == (
        runner_status,
        session_status,
        AuthStatus(account_status),
        authenticated,
    )
    assert set(asdict(outcome)) == {
        "account_id",
        "login_session_id",
        "platform",
        "runner_status",
        "session_status",
        "auth_status",
        "expires_at",
        "completed_at",
        "created_at",
        "updated_at",
    }

    with database.session() as session:
        account = AccountRepository(session).require(str(account_id))
        stored = session.get(LoginSession, str(outcome.login_session_id))
        assert (account.login_method, account.auth_status, account.auth_updated_at) == (
            login_method,
            account_status,
            finished_at,
        )
        assert account.credential_ref is None and account.profile_path is None
        assert stored is not None
        assert (stored.status, stored.completed_at, stored.public_payload) == (
            session_status,
            finished_at,
            {},
        )


def test_expired_saved_session_reenters_qr_then_hands_back_atomically(database: Database) -> None:
    account_id = _seed_account(database, login_method="saved_session", auth_status="expired")
    observed: dict[str, str] = {}

    def observe_reauthentication() -> None:
        with database.session() as session:
            account = AccountRepository(session).require(str(account_id))
            active = LoginSessionRepository(session).get_active_for_account(str(account_id))
            observed.update(
                login_method=account.login_method,
                auth_status=account.auth_status,
                session_status=active.status if active is not None else "missing",
            )

    finished_at = STARTED_AT + timedelta(seconds=2)
    runner = _Runner(
        _result(MediaCrawlerLoginStatus.AUTHENTICATED),
        invoke_hook=True,
        after_hook=observe_reauthentication,
    )
    outcome = MediaCrawlerQrLoginService(
        database,
        runner,
        clock=_Clock(STARTED_AT, finished_at),
    ).run(AccountLoginRequest(account_id=account_id))

    assert observed == {
        "login_method": "qr",
        "auth_status": "authenticating",
        "session_status": "waiting_user",
    }
    assert outcome.authenticated
    with database.session() as session:
        account = AccountRepository(session).require(str(account_id))
        stored = session.get(LoginSession, str(outcome.login_session_id))
        assert (account.login_method, account.auth_status, account.auth_updated_at) == (
            "saved_session",
            "authenticated",
            finished_at,
        )
        assert stored is not None and stored.status == "succeeded"


def test_expired_saved_session_timeout_leaves_retryable_qr_state(database: Database) -> None:
    account_id = _seed_account(database, login_method="saved_session", auth_status="expired")
    finished_at = STARTED_AT + timedelta(seconds=2)
    outcome = MediaCrawlerQrLoginService(
        database,
        _Runner(_result(MediaCrawlerLoginStatus.TIMED_OUT), invoke_hook=True),
        clock=_Clock(STARTED_AT, finished_at),
    ).run(AccountLoginRequest(account_id=account_id))

    assert (outcome.runner_status, outcome.session_status, outcome.auth_status) == (
        MediaCrawlerLoginStatus.TIMED_OUT,
        "expired",
        AuthStatus.REQUIRED,
    )
    with database.session() as session:
        account = AccountRepository(session).require(str(account_id))
        stored = session.get(LoginSession, str(outcome.login_session_id))
        assert (account.login_method, account.auth_status) == ("qr", "required")
        assert stored is not None and stored.status == "expired"


@pytest.mark.parametrize(
    ("seed", "expected_code"),
    [
        (None, "account_login_not_found"),
        ({"adapter": "fake"}, "account_login_ineligible"),
        ({"login_method": "cookie", "credential_ref": "env:MEDIA_SYNC_TEST_COOKIE"}, "account_login_ineligible"),
        ({"login_method": "phone"}, "account_login_ineligible"),
        ({"login_method": "saved_session", "auth_status": "unknown"}, "account_login_ineligible"),
        ({"login_method": "saved_session", "auth_status": "required"}, "account_login_ineligible"),
        ({"login_method": "saved_session", "auth_status": "authenticated"}, "account_login_ineligible"),
        ({"login_method": "saved_session", "auth_status": "failed"}, "account_login_ineligible"),
        (
            {
                "login_method": "saved_session",
                "auth_status": "expired",
                "credential_ref": "env:MEDIA_SYNC_CORRUPT_SAVED_SESSION",
            },
            "account_login_ineligible",
        ),
        (
            {
                "login_method": "saved_session",
                "auth_status": "expired",
                "profile_path": "legacy-saved-session-marker",
            },
            "account_login_ineligible",
        ),
        ({"auth_status": "authenticated"}, "account_login_ineligible"),
        ({"auth_status": "authenticating"}, "account_login_ineligible"),
        ({"credential_ref": "env:MEDIA_SYNC_CORRUPT_QR"}, "account_login_ineligible"),
        ({"profile_path": "legacy-profile-marker"}, "account_login_ineligible"),
    ],
)
def test_ineligible_scope_never_invokes_runner_or_creates_session(
    database: Database,
    seed: dict[str, str] | None,
    expected_code: str,
) -> None:
    account_id = uuid4() if seed is None else _seed_account(database, **seed)
    runner = _Runner(_result(MediaCrawlerLoginStatus.AUTHENTICATED), invoke_hook=True)
    service = MediaCrawlerQrLoginService(database, runner)

    with pytest.raises(AccountLoginError) as captured:
        service.run(AccountLoginRequest(account_id=account_id))

    assert captured.value.code == expected_code
    assert runner.requests == [] and runner.hook_calls == 0
    assert _session_count(database) == 0


@pytest.mark.parametrize(
    ("runner_status", "expected_code"),
    [
        (MediaCrawlerLoginStatus.ACCOUNT_BUSY, "account_login_busy"),
        (MediaCrawlerLoginStatus.CONFIGURATION_INVALID, "account_login_configuration_invalid"),
        (MediaCrawlerLoginStatus.START_FAILED, "account_login_start_failed"),
        (MediaCrawlerLoginStatus.RESULT_INVALID, "account_login_result_invalid"),
        (MediaCrawlerLoginStatus.AUTHENTICATED, "account_login_result_invalid"),
    ],
)
def test_pre_session_runner_failures_return_fixed_codes_and_zero_sessions(
    database: Database,
    runner_status: MediaCrawlerLoginStatus,
    expected_code: str,
) -> None:
    account_id = _seed_account(database)
    runner = _Runner(_result(runner_status), invoke_hook=False)
    service = MediaCrawlerQrLoginService(database, runner)

    with pytest.raises(AccountLoginError) as captured:
        service.run(AccountLoginRequest(account_id=account_id))

    assert captured.value.code == expected_code
    assert runner.hook_calls == 0
    assert _session_count(database) == 0
    with database.session() as session:
        account = AccountRepository(session).require(str(account_id))
        assert (account.login_method, account.auth_status, account.auth_updated_at) == ("qr", "unknown", None)


def test_repository_conflict_from_locked_hook_leaves_existing_state_unchanged(database: Database) -> None:
    account_id = _seed_account(database, auth_status="required")
    with database.session() as session:
        existing = LoginSessionRepository(session).create(
            account_id=str(account_id),
            method="qr",
            challenge_kind="qr",
            expires_at=STARTED_AT + timedelta(minutes=5),
        )

    runner = _Runner(_result(MediaCrawlerLoginStatus.AUTHENTICATED), invoke_hook=True)
    service = MediaCrawlerQrLoginService(database, runner, clock=_Clock(STARTED_AT))
    with pytest.raises(AccountLoginError) as captured:
        service.run(AccountLoginRequest(account_id=account_id))

    assert captured.value.code == "account_login_conflict"
    assert runner.hook_calls == 0
    with database.session() as session:
        account = AccountRepository(session).require(str(account_id))
        stored = session.get(LoginSession, existing.id)
        assert (account.login_method, account.auth_status, account.auth_updated_at) == ("qr", "required", None)
        assert stored is not None and (stored.status, stored.completed_at) == ("pending", None)
        assert session.scalar(select(func.count()).select_from(LoginSession)) == 1


def test_invalid_result_after_hook_is_failed_best_effort_then_fixed_error(database: Database) -> None:
    account_id = _seed_account(database)
    runner = _Runner(object(), invoke_hook=True)
    service = MediaCrawlerQrLoginService(
        database,
        runner,
        clock=_Clock(STARTED_AT, STARTED_AT + timedelta(seconds=2)),
    )

    with pytest.raises(AccountLoginError) as captured:
        service.run(AccountLoginRequest(account_id=account_id))

    assert captured.value.code == "account_login_result_invalid"
    with database.session() as session:
        account = AccountRepository(session).require(str(account_id))
        sessions = LoginSessionRepository(session).list_for_account(str(account_id))
        assert account.auth_status == "failed" and account.login_method == "qr"
        assert len(sessions) == 1 and sessions[0].status == "failed"


def test_runner_exception_after_hook_is_failed_best_effort_without_secret_echo(database: Database) -> None:
    sentinel = "APPLICATION-LOGIN-SECRET-SENTINEL"
    account_id = _seed_account(database)
    runner = _Runner(RuntimeError(f"Cookie={sentinel}"), invoke_hook=True)
    service = MediaCrawlerQrLoginService(
        database,
        runner,
        clock=_Clock(STARTED_AT, STARTED_AT + timedelta(seconds=2)),
    )

    with pytest.raises(AccountLoginError) as captured:
        service.run(AccountLoginRequest(account_id=account_id))

    assert captured.value.code == "account_login_unexpected"
    assert sentinel not in str(captured.value)
    assert sentinel not in captured.value.message
    with database.session() as session:
        account = AccountRepository(session).require(str(account_id))
        stored = session.scalar(select(LoginSession).where(LoginSession.account_id == str(account_id)))
        assert account.auth_status == "failed" and account.login_method == "qr"
        assert stored is not None and stored.status == "failed"
        assert sentinel not in str(stored.public_payload)


def test_keyboard_interrupt_after_hook_cancels_owned_session_before_reraise(database: Database) -> None:
    account_id = _seed_account(database)
    runner = _Runner(KeyboardInterrupt(), invoke_hook=True)
    interrupted_at = STARTED_AT + timedelta(seconds=2)
    service = MediaCrawlerQrLoginService(
        database,
        runner,
        clock=_Clock(STARTED_AT, interrupted_at),
    )

    with pytest.raises(KeyboardInterrupt):
        service.run(AccountLoginRequest(account_id=account_id))

    with database.session() as session:
        account = AccountRepository(session).require(str(account_id))
        stored = session.scalar(select(LoginSession).where(LoginSession.account_id == str(account_id)))
        assert (account.login_method, account.auth_status, account.auth_updated_at) == (
            "qr",
            "required",
            interrupted_at,
        )
        assert stored is not None
        assert (stored.status, stored.completed_at) == ("cancelled", interrupted_at)
        assert LoginSessionRepository(session).get_active_for_account(str(account_id)) is None


def test_keyboard_interrupt_during_completion_cancels_still_owned_session(database: Database) -> None:
    account_id = _seed_account(database)
    runner = _Runner(_result(MediaCrawlerLoginStatus.AUTHENTICATED), invoke_hook=True)
    interrupted_at = STARTED_AT + timedelta(seconds=2)
    moments: Iterator[datetime | BaseException] = iter((STARTED_AT, KeyboardInterrupt(), interrupted_at))

    def interrupting_clock() -> datetime:
        value = next(moments)
        if isinstance(value, BaseException):
            raise value
        return value

    service = MediaCrawlerQrLoginService(database, runner, clock=interrupting_clock)

    with pytest.raises(KeyboardInterrupt):
        service.run(AccountLoginRequest(account_id=account_id))

    with database.session() as session:
        account = AccountRepository(session).require(str(account_id))
        stored = session.scalar(select(LoginSession).where(LoginSession.account_id == str(account_id)))
        assert (account.login_method, account.auth_status, account.auth_updated_at) == (
            "qr",
            "required",
            interrupted_at,
        )
        assert stored is not None
        assert (stored.status, stored.completed_at) == ("cancelled", interrupted_at)
        assert LoginSessionRepository(session).get_active_for_account(str(account_id)) is None


def test_authenticated_result_at_deadline_expires_still_owned_session(database: Database) -> None:
    account_id = _seed_account(database)
    deadline = STARTED_AT + timedelta(seconds=10)
    runner = _Runner(_result(MediaCrawlerLoginStatus.AUTHENTICATED), invoke_hook=True)
    service = MediaCrawlerQrLoginService(database, runner, clock=_Clock(STARTED_AT, deadline))

    outcome = service.run(
        AccountLoginRequest(
            account_id=account_id,
            timeout_seconds=10,
            poll_seconds=1,
        )
    )

    assert (outcome.runner_status, outcome.session_status, outcome.auth_status, outcome.authenticated) == (
        MediaCrawlerLoginStatus.TIMED_OUT,
        "expired",
        AuthStatus.REQUIRED,
        False,
    )
    with database.session() as session:
        account = AccountRepository(session).require(str(account_id))
        active = LoginSessionRepository(session).get_active_for_account(str(account_id))
        stored = session.get(LoginSession, str(outcome.login_session_id))
        assert (account.login_method, account.auth_status, account.auth_updated_at) == (
            "qr",
            "required",
            deadline,
        )
        assert active is None
        assert stored is not None and (stored.status, stored.completed_at) == ("expired", deadline)


def test_account_drift_after_hook_fences_stale_completion_without_half_handoff(database: Database) -> None:
    account_id = _seed_account(database)
    drifted_at = STARTED_AT + timedelta(seconds=1)

    def drift_account() -> None:
        with database.session() as session:
            AccountRepository(session).set_auth_status(
                str(account_id),
                "required",
                expected_status="authenticating",
                at=drifted_at,
            )

    runner = _Runner(
        _result(MediaCrawlerLoginStatus.AUTHENTICATED),
        invoke_hook=True,
        after_hook=drift_account,
    )
    service = MediaCrawlerQrLoginService(
        database,
        runner,
        clock=_Clock(STARTED_AT, STARTED_AT + timedelta(seconds=2)),
    )

    with pytest.raises(AccountLoginError) as captured:
        service.run(AccountLoginRequest(account_id=account_id))

    assert captured.value.code == "account_login_conflict"
    with database.session() as session:
        account = AccountRepository(session).require(str(account_id))
        stored = session.scalar(select(LoginSession).where(LoginSession.account_id == str(account_id)))
        assert (account.login_method, account.auth_status, account.auth_updated_at) == (
            "qr",
            "required",
            drifted_at,
        )
        assert stored is not None and (stored.status, stored.completed_at) == ("waiting_user", None)
