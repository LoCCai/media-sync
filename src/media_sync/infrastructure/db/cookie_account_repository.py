"""Database-only, exact-identity publication of independently verified Cookies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from media_sync.security.secrets import SecretError, SecretReference, SecretScheme

from .base import utc_now
from .models import PLATFORMS, Account, LoginSession

_CODES = frozenset(
    {"cookie_login_account_not_found", "cookie_login_conflict", "cookie_login_busy", "cookie_login_unavailable"}
)


class CookieAccountError(RuntimeError):
    """A closed failure, never an account field or database exception string."""

    def __init__(self, code: str) -> None:
        self.code = code if code in _CODES else "cookie_login_unavailable"
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class CookieAccountSnapshot:
    """Process-local auth identity; no secret locator is printable or projected."""

    account_id: str
    platform: str
    auth_revision: int
    adapter: str = field(repr=False)
    login_method: str | None = field(repr=False)
    credential_ref: str | None = field(repr=False)
    profile_path: str | None = field(repr=False)
    auth_status: str = field(repr=False)
    auth_updated_at: datetime | None = field(repr=False)


def _snapshot(account: Account) -> CookieAccountSnapshot:
    return CookieAccountSnapshot(
        account.id,
        account.platform,
        account.auth_revision,
        account.adapter,
        account.login_method,
        account.credential_ref,
        account.profile_path,
        account.auth_status,
        account.auth_updated_at,
    )


class CookieAccountRepository:
    """Caller owns the shared account lock and outer Operation-fenced transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _account(self, account_id: str, platform: str) -> Account:
        try:
            if str(UUID(account_id)) != account_id or platform not in PLATFORMS:
                raise ValueError
        except (TypeError, ValueError, AttributeError):
            raise CookieAccountError("cookie_login_unavailable") from None
        if self.session.get_bind().dialect.name == "sqlite":
            # Reserve a writer without modifying an Account, even on rejection.
            self.session.connection().exec_driver_sql("UPDATE accounts SET auth_revision=auth_revision WHERE 0")
        account = self.session.scalar(
            select(Account).where(Account.id == account_id).with_for_update().execution_options(populate_existing=True)
        )
        if account is None:
            raise CookieAccountError("cookie_login_account_not_found")
        if account.platform != platform:
            raise CookieAccountError("cookie_login_conflict")
        if (
            account.adapter != "mediacrawler"
            or account.login_method not in {"qr", "cookie", "saved_session"}
            or account.profile_path is not None
        ):
            raise CookieAccountError("cookie_login_unavailable")
        active_qr = self.session.scalar(
            select(
                exists().where(
                    LoginSession.account_id == account_id,
                    LoginSession.method == "qr",
                    LoginSession.status.in_(("pending", "waiting_user")),
                )
            )
        )
        if account.auth_status == "authenticating" or active_qr:
            raise CookieAccountError("cookie_login_busy")
        return account

    def snapshot(self, account_id: str, platform: str, expected_auth_revision: int) -> CookieAccountSnapshot:
        if type(expected_auth_revision) is not int or not 0 <= expected_auth_revision < 2**63 - 1:
            raise CookieAccountError("cookie_login_conflict")
        account = self._account(account_id, platform)
        if account.auth_revision != expected_auth_revision:
            raise CookieAccountError("cookie_login_conflict")
        return _snapshot(account)

    def publish(self, snapshot: CookieAccountSnapshot, credential_ref: SecretReference | str) -> int:
        """CAS the entire observed authentication identity; never commit here."""

        if not isinstance(snapshot, CookieAccountSnapshot) or type(snapshot.auth_revision) is not int:
            raise CookieAccountError("cookie_login_conflict")
        try:
            raw = credential_ref.serialize() if isinstance(credential_ref, SecretReference) else credential_ref
            reference = SecretReference.parse(raw)
            if reference.scheme is not SecretScheme.MANAGED:
                raise CookieAccountError("cookie_login_unavailable")
        except (SecretError, AttributeError, TypeError):
            raise CookieAccountError("cookie_login_unavailable") from None
        account = self._account(snapshot.account_id, snapshot.platform)
        if _snapshot(account) != snapshot or not 0 <= snapshot.auth_revision < 2**63 - 1:
            raise CookieAccountError("cookie_login_conflict")
        current = utc_now()
        changed = self.session.execute(
            update(Account)
            .where(
                Account.id == snapshot.account_id,
                Account.platform == snapshot.platform,
                Account.adapter == snapshot.adapter,
                Account.login_method == snapshot.login_method,
                Account.credential_ref == snapshot.credential_ref,
                Account.profile_path == snapshot.profile_path,
                Account.auth_status == snapshot.auth_status,
                Account.auth_updated_at == snapshot.auth_updated_at,
                Account.auth_revision == snapshot.auth_revision,
            )
            .values(
                credential_ref=reference.serialize(),
                login_method="cookie",
                auth_status="authenticated",
                auth_revision=Account.auth_revision + 1,
                auth_updated_at=current,
                updated_at=current,
            )
            .returning(Account.auth_revision)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()
        if changed is None:
            raise CookieAccountError("cookie_login_conflict")
        self.session.expire(account)
        return int(changed)


__all__ = ["CookieAccountError", "CookieAccountRepository", "CookieAccountSnapshot"]
