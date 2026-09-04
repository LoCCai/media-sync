"""Explicit, redaction-safe orchestration for host-assisted account login."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import UUID

from media_sync.domain import AuthStatus, Platform
from media_sync.infrastructure.db import (
    AccountLoginConflictError,
    AccountRepository,
    Database,
    ExpiredLoginSessionCandidate,
    LoginSessionConflictError,
    LoginSessionRepository,
    LoginSessionState,
    NotFoundError,
    RepositoryError,
)
from media_sync.integrations.mediacrawler import (
    MediaCrawlerAccountLock,
    MediaCrawlerLoginMode,
    MediaCrawlerLoginRequest,
    MediaCrawlerLoginResult,
    MediaCrawlerLoginRunner,
    MediaCrawlerLoginStatus,
)

from .operations import DurableSubjectHook, DurableSubjectRef

_ERROR_MESSAGES = {
    "account_login_not_found": "the account was not found",
    "account_login_ineligible": "the account is not eligible for interactive MediaCrawler QR login",
    "account_login_busy": "another local login owns this account",
    "account_login_configuration_invalid": "the MediaCrawler login runtime is unavailable or invalid",
    "account_login_start_failed": "the MediaCrawler login child could not start",
    "account_login_result_invalid": "the MediaCrawler login child returned no trustworthy result",
    "account_login_conflict": "the account or login session changed during this attempt",
    "account_login_unexpected": "the MediaCrawler login attempt failed unexpectedly",
}
_STARTABLE_AUTH_STATUSES = frozenset({"unknown", "required", "expired", "failed"})


class AccountLoginError(RuntimeError):
    """A fixed-code login orchestration error safe for operator output."""

    def __init__(self, code: str) -> None:
        try:
            message = _ERROR_MESSAGES[code]
        except KeyError as exc:  # pragma: no cover - programmer error
            raise ValueError("unknown account login error code") from exc
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class AccountLoginRequest:
    """Public inputs for one bounded, account-scoped QR login."""

    account_id: UUID
    timeout_seconds: float = 180.0
    poll_seconds: float = 0.05

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, UUID):
            raise ValueError("account_id must be a UUID")
        timeout = self.timeout_seconds
        poll = self.poll_seconds
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not math.isfinite(timeout)
            or not 0 < float(timeout) <= 3_600
        ):
            raise ValueError("timeout_seconds must be finite and between zero and 3600")
        if (
            isinstance(poll, bool)
            or not isinstance(poll, int | float)
            or not math.isfinite(poll)
            or not 0 < float(poll) < float(timeout)
            or float(poll) > 5
        ):
            raise ValueError("poll_seconds must be finite, positive, at most five, and shorter than timeout")
        object.__setattr__(self, "timeout_seconds", float(timeout))
        object.__setattr__(self, "poll_seconds", float(poll))


@dataclass(frozen=True, slots=True)
class AccountLoginOutcome:
    """Redaction-safe durable truth for a completed interactive attempt."""

    account_id: UUID
    login_session_id: UUID
    platform: Platform
    runner_status: MediaCrawlerLoginStatus
    session_status: str
    auth_status: AuthStatus
    expires_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @property
    def authenticated(self) -> bool:
        return (
            self.runner_status is MediaCrawlerLoginStatus.AUTHENTICATED
            and self.session_status == "succeeded"
            and self.auth_status is AuthStatus.AUTHENTICATED
        )


@dataclass(frozen=True, slots=True)
class _AccountLoginScope:
    account_id: UUID
    platform: Platform


@dataclass(frozen=True, slots=True)
class LoginSessionReconciliationSummary:
    """Fixed, redaction-safe counts from one bounded reconciliation pass."""

    scanned: int
    recovered: int
    busy: int
    conflicted: int


class _AccountLock(Protocol):
    def acquire(self) -> bool: ...

    def release(self) -> None: ...


_AccountLockFactory = Callable[[Path, Platform, UUID], _AccountLock]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MediaCrawlerLoginSessionReconciler:
    """Recover deadline-expired login ownership under the shared profile lock."""

    def __init__(
        self,
        database: Database,
        *,
        integration_root: Path,
        clock: Callable[[], datetime] = _utc_now,
        lock_factory: _AccountLockFactory = MediaCrawlerAccountLock,
    ) -> None:
        if not isinstance(database, Database):
            raise TypeError("database must be a Database")
        if not isinstance(integration_root, Path):
            raise TypeError("integration_root must be a Path")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if not callable(lock_factory):
            raise TypeError("lock_factory must be callable")
        self._database = database
        self._integration_root = integration_root.expanduser().resolve()
        self._clock = clock
        self._lock_factory = lock_factory
        self._sweep_lock = threading.Lock()
        self._sweep_cursor: tuple[datetime, str] | None = None

    def sweep(self, *, limit: int = 100) -> LoginSessionReconciliationSummary:
        """Reconcile at most ``limit`` public candidate identities."""

        with self._sweep_lock:
            at = self._now()
            candidates = self._list_candidates(
                at=at,
                limit=limit,
                account_id=None,
                after=self._sweep_cursor,
            )
            if not candidates and self._sweep_cursor is not None:
                candidates = self._list_candidates(
                    at=at,
                    limit=limit,
                    account_id=None,
                    after=None,
                )
            summary = self._recover_candidates(candidates, at=at)
            if candidates:
                last = candidates[-1]
                self._sweep_cursor = last.expected_expires_at, last.login_session_id
            else:
                self._sweep_cursor = None
            return summary

    def reconcile_account(self, account_id: UUID) -> LoginSessionReconciliationSummary:
        """Reconcile the one current expired attempt for an exact account."""

        if not isinstance(account_id, UUID):
            raise ValueError("account_id must be a UUID")
        at = self._now()
        candidates = self._list_candidates(
            at=at,
            limit=1,
            account_id=str(account_id),
            after=None,
        )
        return self._recover_candidates(candidates, at=at)

    def _list_candidates(
        self,
        *,
        at: datetime,
        limit: int,
        account_id: str | None,
        after: tuple[datetime, str] | None,
    ) -> list[ExpiredLoginSessionCandidate]:
        # End the read-only enumeration transaction before touching any account
        # lock. Each identity below receives its own fresh write transaction.
        with self._database.session() as session:
            return LoginSessionRepository(session).list_expired_mediacrawler_qr_candidates(
                at=at,
                limit=limit,
                account_id=account_id,
                after=after,
            )

    def _recover_candidates(
        self,
        candidates: list[ExpiredLoginSessionCandidate],
        *,
        at: datetime,
    ) -> LoginSessionReconciliationSummary:
        recovered = 0
        busy = 0
        conflicted = 0
        for candidate in candidates:
            try:
                platform = Platform(candidate.platform)
                candidate_account_id = UUID(candidate.account_id)
                account_lock = self._lock_factory(
                    self._integration_root,
                    platform,
                    candidate_account_id,
                )
            except (TypeError, ValueError):
                conflicted += 1
                continue
            if not account_lock.acquire():
                busy += 1
                continue
            try:
                try:
                    with self._database.session() as session:
                        LoginSessionRepository(session).recover_expired_mediacrawler_qr(
                            candidate,
                            at=at,
                        )
                except (
                    NotFoundError,
                    AccountLoginConflictError,
                    LoginSessionConflictError,
                    RepositoryError,
                    ValueError,
                ):
                    conflicted += 1
                else:
                    recovered += 1
            finally:
                account_lock.release()
        return LoginSessionReconciliationSummary(
            scanned=len(candidates),
            recovered=recovered,
            busy=busy,
            conflicted=conflicted,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(UTC)


class MediaCrawlerQrLoginService:
    """Hold local account exclusion across durable session start and child join."""

    def __init__(
        self,
        database: Database,
        runner: MediaCrawlerLoginRunner,
        *,
        clock: Callable[[], datetime] = _utc_now,
        reconciler: MediaCrawlerLoginSessionReconciler | None = None,
    ) -> None:
        if not callable(runner.run):
            raise TypeError("runner must implement the MediaCrawler login boundary")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if reconciler is not None and not isinstance(reconciler, MediaCrawlerLoginSessionReconciler):
            raise TypeError("reconciler must be a MediaCrawlerLoginSessionReconciler")
        self._database = database
        self._runner = runner
        self._clock = clock
        self._reconciler = reconciler

    def run(
        self,
        request: AccountLoginRequest,
        *,
        cancellation: threading.Event | None = None,
        subject_hook: DurableSubjectHook | None = None,
    ) -> AccountLoginOutcome:
        """Run one explicit QR attempt; a session starts only after account lock acquisition."""

        if self._reconciler is not None:
            reconciliation = self._reconciler.reconcile_account(request.account_id)
            if reconciliation.busy:
                raise AccountLoginError("account_login_busy")
        scope = self._load_scope(request.account_id)
        integration_request = MediaCrawlerLoginRequest(
            account_id=scope.account_id,
            platform=scope.platform,
            mode=MediaCrawlerLoginMode.INTERACTIVE_QR,
            timeout_seconds=request.timeout_seconds,
            poll_seconds=request.poll_seconds,
        )
        observed: LoginSessionState | None = None

        def start_waiting_session() -> None:
            nonlocal observed
            started_at = self._now()
            with self._database.session() as session:
                repository = LoginSessionRepository(session)
                started = repository.start_mediacrawler_qr(
                    str(scope.account_id),
                    expires_at=started_at + timedelta(seconds=request.timeout_seconds),
                    at=started_at,
                )
                waiting = repository.mark_waiting_user(started.id, at=started_at)
                if subject_hook is not None:
                    subject_hook(
                        session,
                        DurableSubjectRef("login_session", waiting.id),
                    )
                # Publish the exact identity before commit. If commit fails,
                # best-effort terminalization simply finds no durable row.
                observed = waiting

        try:
            raw_result = self._runner.run(
                integration_request,
                on_account_locked=start_waiting_session,
                cancellation=cancellation,
            )
        except NotFoundError:
            raise AccountLoginError("account_login_not_found") from None
        except (AccountLoginConflictError, LoginSessionConflictError):
            raise AccountLoginError("account_login_conflict") from None
        except RepositoryError:
            raise AccountLoginError("account_login_conflict") from None
        except KeyboardInterrupt:
            if observed is not None:
                self._finish_cancelled(observed.id)
            raise
        except Exception:
            if observed is not None:
                self._finish_failed(observed.id)
            raise AccountLoginError("account_login_unexpected") from None

        try:
            if not isinstance(raw_result, MediaCrawlerLoginResult):
                if observed is not None:
                    self._finish_failed(observed.id)
                raise AccountLoginError("account_login_result_invalid")
            if observed is None:
                raise AccountLoginError(self._pre_session_error(raw_result.status))

            return self._finish(scope, observed, raw_result.status)
        except KeyboardInterrupt:
            if observed is not None:
                self._finish_cancelled(observed.id)
            raise

    def _load_scope(self, account_id: UUID) -> _AccountLoginScope:
        with self._database.session() as session:
            account = AccountRepository(session).get(str(account_id))
            if account is None:
                raise AccountLoginError("account_login_not_found")
            eligible_login_state = (
                account.login_method == "qr" and account.auth_status in _STARTABLE_AUTH_STATUSES
            ) or (account.login_method == "saved_session" and account.auth_status == "expired")
            if (
                account.adapter != "mediacrawler"
                or not eligible_login_state
                or account.credential_ref is not None
                or account.profile_path is not None
            ):
                raise AccountLoginError("account_login_ineligible")
            try:
                platform = Platform(account.platform)
            except ValueError:
                raise AccountLoginError("account_login_ineligible") from None
        return _AccountLoginScope(account_id=account_id, platform=platform)

    def _finish(
        self,
        scope: _AccountLoginScope,
        observed: LoginSessionState,
        runner_status: MediaCrawlerLoginStatus,
    ) -> AccountLoginOutcome:
        finished_at = self._now()
        try:
            with self._database.session() as session:
                repository = LoginSessionRepository(session)
                if runner_status is MediaCrawlerLoginStatus.AUTHENTICATED:
                    final = repository.succeed_mediacrawler_qr(observed.id, at=finished_at)
                elif runner_status in {MediaCrawlerLoginStatus.EXPIRED, MediaCrawlerLoginStatus.TIMED_OUT}:
                    final = repository.expire_mediacrawler_qr(observed.id, at=finished_at)
                elif runner_status is MediaCrawlerLoginStatus.CANCELLED:
                    final = repository.cancel_mediacrawler_qr(observed.id, at=finished_at)
                else:
                    final = repository.fail_mediacrawler_qr(observed.id, at=finished_at)
                account = AccountRepository(session).require(final.account_id)
                auth_status = AuthStatus(account.auth_status)
        except (NotFoundError, AccountLoginConflictError, LoginSessionConflictError, RepositoryError, ValueError):
            if (
                runner_status is MediaCrawlerLoginStatus.AUTHENTICATED
                and observed.expires_at is not None
                and observed.expires_at <= finished_at
            ):
                recovered = self._expire_late_authenticated(scope, observed, finished_at)
                if recovered is not None:
                    return recovered
            raise AccountLoginError("account_login_conflict") from None

        return self._outcome(scope, final, runner_status, auth_status)

    def _expire_late_authenticated(
        self,
        scope: _AccountLoginScope,
        observed: LoginSessionState,
        finished_at: datetime,
    ) -> AccountLoginOutcome | None:
        """Expire only the still-owned session when success missed its deadline."""

        try:
            with self._database.session() as session:
                final = LoginSessionRepository(session).expire_mediacrawler_qr(
                    observed.id,
                    at=finished_at,
                )
                account = AccountRepository(session).require(final.account_id)
                auth_status = AuthStatus(account.auth_status)
        except (NotFoundError, AccountLoginConflictError, LoginSessionConflictError, RepositoryError, ValueError):
            return None
        return self._outcome(
            scope,
            final,
            MediaCrawlerLoginStatus.TIMED_OUT,
            auth_status,
        )

    @staticmethod
    def _outcome(
        scope: _AccountLoginScope,
        final: LoginSessionState,
        runner_status: MediaCrawlerLoginStatus,
        auth_status: AuthStatus,
    ) -> AccountLoginOutcome:
        return AccountLoginOutcome(
            account_id=scope.account_id,
            login_session_id=UUID(final.id),
            platform=scope.platform,
            runner_status=runner_status,
            session_status=final.status,
            auth_status=auth_status,
            expires_at=final.expires_at,
            completed_at=final.completed_at,
            created_at=final.created_at,
            updated_at=final.updated_at,
        )

    def _finish_cancelled(self, login_session_id: str) -> None:
        try:
            with self._database.session() as session:
                LoginSessionRepository(session).cancel_mediacrawler_qr(
                    login_session_id,
                    at=self._now(),
                )
        except Exception:
            # Preserve Ctrl+C while making a best effort to release the exact
            # durable login owner. Concurrent drift must remain untouched.
            pass

    def _finish_failed(self, login_session_id: str) -> None:
        try:
            with self._database.session() as session:
                LoginSessionRepository(session).fail_mediacrawler_qr(
                    login_session_id,
                    at=self._now(),
                )
        except Exception:
            # Never replace the fixed outer failure with a second persistence
            # exception or include repository-controlled text in operator output.
            pass

    @staticmethod
    def _pre_session_error(status: MediaCrawlerLoginStatus) -> str:
        return {
            MediaCrawlerLoginStatus.ACCOUNT_BUSY: "account_login_busy",
            MediaCrawlerLoginStatus.CONFIGURATION_INVALID: "account_login_configuration_invalid",
            MediaCrawlerLoginStatus.START_FAILED: "account_login_start_failed",
            MediaCrawlerLoginStatus.RESULT_INVALID: "account_login_result_invalid",
            MediaCrawlerLoginStatus.CANCELLED: "account_login_conflict",
        }.get(status, "account_login_result_invalid")

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(UTC)


__all__ = [
    "AccountLoginError",
    "AccountLoginOutcome",
    "AccountLoginRequest",
    "LoginSessionReconciliationSummary",
    "MediaCrawlerLoginSessionReconciler",
    "MediaCrawlerQrLoginService",
]
