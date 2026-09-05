"""Verify a candidate independently, then atomically publish its private reference."""

from __future__ import annotations

import contextlib
import stat
import threading
from pathlib import Path
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from media_sync.domain import Platform
from media_sync.infrastructure.db import Database, Operation
from media_sync.infrastructure.db.cookie_account_repository import (
    CookieAccountError,
    CookieAccountRepository,
    CookieAccountSnapshot,
)
from media_sync.integrations.mediacrawler.account_lock import MediaCrawlerAccountLock
from media_sync.integrations.mediacrawler.cookie_login import (
    COOKIE_LOGIN_PLATFORMS,
    CookieLoginRequest,
    CookieLoginResult,
)
from media_sync.integrations.mediacrawler.policies import RunPaths, build_run_paths
from media_sync.integrations.mediacrawler.runner import is_attempt_cleanup_blocked, record_attempt_cleanup_incident
from media_sync.security.managed_credentials import ManagedCredentialStore
from media_sync.security.secrets import SecretError, SecretValue

from .operations import OperationExecutionContext, OperationOutcome

_RETAINED_LOCKS: list[MediaCrawlerAccountLock] = []
_RESULT_ERRORS = {
    "rejected": "cookie_login_rejected",
    "verification_unavailable": "cookie_login_verification_unavailable",
    "timed_out": "cookie_login_timed_out",
    "cancelled": "cookie_login_cancelled",
    "configuration_invalid": "cookie_login_unavailable",
    "result_invalid": "cookie_login_result_invalid",
    "cleanup_failed": "cookie_login_cleanup_failed",
}


class _Runner(Protocol):
    def run(self, request: CookieLoginRequest, *, cancellation: threading.Event | None = None) -> CookieLoginResult: ...


def _prepare_account_root(root: Path, platform: Platform, account_id: UUID, operation_id: UUID) -> RunPaths:
    # Account exclusion is required even before this account has a QR profile.
    declared = root.expanduser().absolute()
    for directory in (
        declared,
        declared / "accounts",
        declared / "accounts" / platform.value,
        declared / "accounts" / platform.value / str(account_id),
    ):
        directory.mkdir(mode=0o700, parents=directory == declared, exist_ok=True)
        info = directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or directory.is_symlink()
            or directory.resolve() != directory
            or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise ValueError("cookie_login_unavailable")
    return build_run_paths(declared, platform, account_id, operation_id)


class CookieLoginService:
    def __init__(
        self, database: Database, runner: _Runner | None, *, integration_root: Path, credential_root: Path
    ) -> None:
        self.database = database
        self.runner = runner
        self.integration_root = integration_root
        self.store = ManagedCredentialStore(credential_root)

    def preflight(self, account_id: str, platform: Platform, expected_auth_revision: int) -> None:
        with self.database.session() as session:
            CookieAccountRepository(session).snapshot(account_id, platform.value, expected_auth_revision)
        if platform not in COOKIE_LOGIN_PLATFORMS:
            raise CookieAccountError("cookie_login_unavailable")
        if self.runner is None:
            raise CookieAccountError("cookie_login_unavailable")

    def execute(
        self,
        context: OperationExecutionContext,
        *,
        account_id: str,
        platform: Platform,
        expected_auth_revision: int,
        candidate: SecretValue,
    ) -> OperationOutcome:
        lock: MediaCrawlerAccountLock | None = None
        acquired = False
        cleanup_uncertain = False
        paths: RunPaths | None = None
        try:
            if platform not in COOKIE_LOGIN_PLATFORMS:
                return OperationOutcome.failed("cookie_login_verification_unavailable", retryable=False)
            if context.cancel_requested:
                return OperationOutcome.cancelled()
            paths = _prepare_account_root(self.integration_root, platform, UUID(account_id), UUID(context.operation_id))
            if is_attempt_cleanup_blocked(paths):
                return OperationOutcome.failed("cookie_login_cleanup_failed", retryable=False)
            lock = MediaCrawlerAccountLock(self.integration_root, platform, UUID(account_id))
            acquired = lock.acquire()
            if not acquired:
                return OperationOutcome.failed("cookie_login_busy", retryable=False)

            def require_scope(session: Session) -> None:
                operation = session.get(Operation, context.operation_id, populate_existing=True)
                if operation is None or (operation.kind, operation.target_type, operation.target_id) != (
                    "account-cookie-login",
                    "account",
                    account_id,
                ):
                    raise CookieAccountError("cookie_login_conflict")

            def snapshot(session: Session) -> CookieAccountSnapshot:
                require_scope(session)
                return CookieAccountRepository(session).snapshot(account_id, platform.value, expected_auth_revision)

            observed = context.commit_effect(snapshot)
            context.phase("verifying_cookie")
            request = CookieLoginRequest(
                UUID(account_id), platform, UUID(context.operation_id), candidate, account_lock_fd=lock.descriptor
            )
            if self.runner is None:
                return OperationOutcome.failed("cookie_login_unavailable", retryable=False)
            try:
                result = self.runner.run(request, cancellation=context.cancellation)
            except Exception:
                # An uncontracted runner exception cannot prove a spawned tree
                # exited; preserve exclusion rather than permit overlapping work.
                cleanup_uncertain = True
                return OperationOutcome.failed("cookie_login_cleanup_failed", retryable=False)
            if not isinstance(result, CookieLoginResult):
                cleanup_uncertain = True
                return OperationOutcome.failed("cookie_login_result_invalid", retryable=False)
            cleanup_uncertain = result.status == "cleanup_failed"
            if (result.account_id, result.platform, result.operation_id) != (
                request.account_id,
                platform,
                request.operation_id,
            ):
                return OperationOutcome.failed("cookie_login_result_invalid", retryable=False)
            if context.cancel_requested:
                return OperationOutcome.cancelled()
            if result.status != "authenticated":
                if result.status == "cancelled":
                    return OperationOutcome.cancelled()
                return OperationOutcome.failed(
                    _RESULT_ERRORS.get(result.status, "cookie_login_result_invalid"), retryable=False
                )
            if result.upstream_sha is None or len(result.upstream_sha) != 40:
                return OperationOutcome.failed("cookie_login_result_invalid", retryable=False)
            context.phase("saving_cookie")
            if context.cancel_requested:
                return OperationOutcome.cancelled()
            try:
                reference = self.store.write(candidate)
            except (OSError, ValueError, SecretError):
                return OperationOutcome.failed("cookie_login_save_failed", retryable=False)

            def publish(session: Session) -> dict[str, object]:
                require_scope(session)
                revision = CookieAccountRepository(session).publish(observed, reference)
                return {
                    "account_id": account_id,
                    "auth_status": "authenticated",
                    "login_method": "cookie",
                    "auth_revision": revision,
                }

            # An immutable file already exists durably. No deletion in any error
            # path: the commit acknowledgement itself can fail after DB commit.
            return OperationOutcome.success(context.commit_success(publish))
        except CookieAccountError as error:
            return OperationOutcome.failed(error.code, retryable=False)
        except (OSError, ValueError, SQLAlchemyError):
            return OperationOutcome.failed("cookie_login_unavailable", retryable=False)
        finally:
            if acquired and lock is not None:
                if cleanup_uncertain:
                    _RETAINED_LOCKS.append(lock)
                    if paths is not None:
                        with contextlib.suppress(Exception):
                            record_attempt_cleanup_incident(paths)
                else:
                    lock.release()
