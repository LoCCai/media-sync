"""Account-scoped, redaction-safe preflight for interactive MediaCrawler login."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from media_sync.application.authentication import MediaCrawlerLoginSessionReconciler
from media_sync.config import Settings
from media_sync.domain import Platform
from media_sync.infrastructure.db import (
    AccountLoginConflictError,
    AccountRepository,
    Database,
    LoginSessionRepository,
)
from media_sync.integrations.mediacrawler import MediaCrawlerAccountLock
from media_sync.integrations.mediacrawler.checkout import (
    CheckoutValidationError,
    LicenseAcknowledgementRequired,
    verify_mediacrawler_browser,
    verify_mediacrawler_checkout,
    verify_mediacrawler_python,
)

CheckStatus = Literal["pass", "fail", "not_run"]

_CHECK_NAMES = (
    "database",
    "account",
    "account_eligible",
    "license_acknowledgement",
    "checkout",
    "runtime",
    "browser",
    "profile",
    "account_lock",
)
_STARTABLE_AUTH_STATUSES = frozenset({"unknown", "required", "expired", "failed"})
_RETRYABLE_CODES = frozenset(
    {
        "account_login_busy",
        "browser_launch_failed",
        "database_not_ready",
        "profile_not_writable",
        "runtime_probe_failed",
    }
)


@dataclass(frozen=True, slots=True)
class LoginPreflightCheck:
    """One fixed-name check without paths or exception text."""

    name: str
    status: CheckStatus
    required: bool = True
    detail_code: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "required": self.required,
            "detail_code": self.detail_code,
        }


@dataclass(frozen=True, slots=True)
class AccountLoginPreflight:
    """Closed login readiness result safe for CLI/API/browser projection."""

    ok: bool
    code: str
    retryable: bool
    account_id: UUID
    platform: Platform | None
    checks: tuple[LoginPreflightCheck, ...]

    @property
    def status(self) -> str:
        return "ready" if self.ok else "blocked"

    def to_payload(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "status": self.status,
            "code": self.code,
            "retryable": self.retryable,
            "account_id": str(self.account_id),
            "platform": self.platform.value if self.platform is not None else None,
            "checks": [check.to_payload() for check in self.checks],
            "live_qualification": "NOT_RUN",
        }


class _PreflightBuilder:
    def __init__(self, account_id: UUID) -> None:
        self.account_id = account_id
        self.platform: Platform | None = None
        self._checks: dict[str, LoginPreflightCheck] = {}

    def passed(self, name: str) -> None:
        self._checks[name] = LoginPreflightCheck(name=name, status="pass")

    def failed(self, name: str, code: str, *, retryable: bool | None = None) -> AccountLoginPreflight:
        self._checks[name] = LoginPreflightCheck(name=name, status="fail", detail_code=code)
        checks = tuple(
            self._checks.get(remaining, LoginPreflightCheck(name=remaining, status="not_run"))
            for remaining in _CHECK_NAMES
        )
        return AccountLoginPreflight(
            ok=False,
            code=code,
            retryable=code in _RETRYABLE_CODES if retryable is None else retryable,
            account_id=self.account_id,
            platform=self.platform,
            checks=checks,
        )

    def ready(self) -> AccountLoginPreflight:
        checks = tuple(self._checks[name] for name in _CHECK_NAMES)
        return AccountLoginPreflight(
            ok=True,
            code="ready",
            retryable=False,
            account_id=self.account_id,
            platform=self.platform,
            checks=checks,
        )


def _real_directory(path: Path) -> bool:
    try:
        opened = os.lstat(path)
        return stat.S_ISDIR(opened.st_mode) and not path.is_symlink() and path.resolve() == path.absolute()
    except OSError:
        return False


def _profile_root_ready(runtime_root: Path, platform: Platform, account_id: UUID) -> bool:
    """Check whether the account directory is writable or safely creatable."""

    root = runtime_root.expanduser().resolve()
    candidate = root / "accounts" / platform.value / str(account_id)
    if candidate.exists():
        return _real_directory(candidate) and os.access(candidate, os.W_OK)

    ancestor = candidate.parent
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    return _real_directory(ancestor) and os.access(ancestor, os.W_OK)


def collect_account_login_preflight(
    settings: Settings,
    account_id: UUID,
    *,
    license_acknowledged: bool,
) -> AccountLoginPreflight:
    """Evaluate only prerequisites required to start one interactive login."""

    if not isinstance(settings, Settings):
        raise TypeError("settings must be Settings")
    if not isinstance(account_id, UUID):
        raise TypeError("account_id must be UUID")
    if not isinstance(license_acknowledged, bool):
        raise TypeError("license_acknowledged must be bool")

    builder = _PreflightBuilder(account_id)
    database: Database | None = None
    try:
        database = Database(settings.resolved_database_url)
        MediaCrawlerLoginSessionReconciler(
            database,
            integration_root=settings.resolved_mediacrawler_runtime_dir,
        ).reconcile_account(account_id)
        with database.session() as session:
            account = AccountRepository(session).get(str(account_id))
            if account is None:
                builder.passed("database")
                return builder.failed("account", "account_login_not_found", retryable=False)
            try:
                platform = Platform(account.platform)
            except ValueError:
                builder.passed("database")
                builder.passed("account")
                return builder.failed("account_eligible", "account_login_ineligible", retryable=False)
            login_session_conflict = False
            try:
                active_session = LoginSessionRepository(session).get_active_for_account(account.id)
            except AccountLoginConflictError:
                active_session = None
                login_session_conflict = True
            adapter = account.adapter
            login_method = account.login_method
            auth_status = account.auth_status
            has_credential = account.credential_ref is not None
            has_profile_override = account.profile_path is not None
    except (OSError, SQLAlchemyError, ValueError, TypeError):
        return builder.failed("database", "database_not_ready", retryable=True)
    finally:
        if database is not None:
            database.dispose()

    builder.platform = platform
    builder.passed("database")
    builder.passed("account")
    eligible = (
        adapter == "mediacrawler"
        and not has_credential
        and not has_profile_override
        and (
            (login_method == "qr" and auth_status in _STARTABLE_AUTH_STATUSES)
            or (login_method == "saved_session" and auth_status == "expired")
        )
    )
    if not eligible:
        return builder.failed("account_eligible", "account_login_ineligible", retryable=False)
    builder.passed("account_eligible")

    if active_session is not None or login_session_conflict:
        return builder.failed("account_lock", "account_login_busy", retryable=True)
    if not license_acknowledged:
        return builder.failed("license_acknowledgement", "license_acknowledgement_required", retryable=False)
    builder.passed("license_acknowledgement")

    try:
        verify_mediacrawler_checkout(
            settings.mediacrawler_lock_path,
            license_acknowledged=True,
        )
    except LicenseAcknowledgementRequired:
        return builder.failed("checkout", "license_acknowledgement_required", retryable=False)
    except CheckoutValidationError as error:
        return builder.failed("checkout", error.code, retryable=False)
    builder.passed("checkout")

    executable = settings.mediacrawler_python_executable
    if executable is None:
        return builder.failed("runtime", "runtime_unconfigured", retryable=False)
    try:
        verify_mediacrawler_python(executable)
    except CheckoutValidationError as error:
        return builder.failed("runtime", error.code)
    builder.passed("runtime")

    try:
        verify_mediacrawler_browser(executable)
    except CheckoutValidationError as error:
        return builder.failed("browser", error.code)
    builder.passed("browser")

    runtime_root = settings.resolved_mediacrawler_runtime_dir
    if not _profile_root_ready(runtime_root, platform, account_id):
        return builder.failed("profile", "profile_not_writable", retryable=True)
    builder.passed("profile")

    account_root = runtime_root / "accounts" / platform.value / str(account_id)
    if account_root.exists():
        account_lock = MediaCrawlerAccountLock(runtime_root, platform, account_id)
        if not account_lock.acquire():
            return builder.failed("account_lock", "account_login_busy", retryable=True)
        account_lock.release()
    builder.passed("account_lock")
    return builder.ready()


__all__ = [
    "AccountLoginPreflight",
    "LoginPreflightCheck",
    "collect_account_login_preflight",
]
