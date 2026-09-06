"""Exact-account CAS publication for an independently verified browser profile."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from .models import PLATFORMS, Account, LoginSession

PROFILE_ADOPTION_ACCOUNT_ERROR_CODES = frozenset(
    {
        "profile_adoption_account_not_found",
        "profile_adoption_account_ineligible",
        "profile_adoption_busy",
        "profile_adoption_conflict",
    }
)


class ProfileAdoptionAccountError(RuntimeError):
    """A closed repository failure containing no persisted account values."""

    def __init__(self, code: str) -> None:
        self.code = code if code in PROFILE_ADOPTION_ACCOUNT_ERROR_CODES else "profile_adoption_conflict"
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class ProfileAdoptionAccountSnapshot:
    """The complete authentication identity observed before profile verification."""

    account_id: str
    platform: str
    auth_revision: int
    adapter: str = field(repr=False)
    login_method: str | None = field(repr=False)
    credential_ref: str | None = field(repr=False)
    profile_path: str | None = field(repr=False)
    auth_status: str = field(repr=False)
    auth_updated_at: datetime | None = field(repr=False)


def _snapshot(account: Account) -> ProfileAdoptionAccountSnapshot:
    return ProfileAdoptionAccountSnapshot(
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


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("at must be timezone-aware")
    return value.astimezone(UTC)


class ProfileAdoptionAccountRepository:
    """Snapshot and publish one MediaCrawler account while the caller owns its profile lock."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _account(self, account_id: str) -> Account:
        try:
            if str(UUID(account_id)) != account_id:
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            raise ProfileAdoptionAccountError("profile_adoption_conflict") from None
        if self.session.get_bind().dialect.name == "sqlite":
            # Reserve the single SQLite writer before making eligibility and
            # active-session decisions that publication must keep coherent.
            self.session.connection().exec_driver_sql("UPDATE accounts SET auth_revision=auth_revision WHERE 0")
        account = self.session.scalar(
            select(Account).where(Account.id == account_id).with_for_update().execution_options(populate_existing=True)
        )
        if account is None:
            raise ProfileAdoptionAccountError("profile_adoption_account_not_found")
        if account.adapter != "mediacrawler" or account.platform not in PLATFORMS:
            raise ProfileAdoptionAccountError("profile_adoption_account_ineligible")
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
            raise ProfileAdoptionAccountError("profile_adoption_busy")
        return account

    def snapshot(self, account_id: str, expected_auth_revision: int) -> ProfileAdoptionAccountSnapshot:
        """Observe one eligible account at the caller-provided auth generation."""

        if type(expected_auth_revision) is not int or not 0 <= expected_auth_revision < 2**63 - 1:
            raise ProfileAdoptionAccountError("profile_adoption_conflict")
        account = self._account(account_id)
        if account.auth_revision != expected_auth_revision:
            raise ProfileAdoptionAccountError("profile_adoption_conflict")
        return _snapshot(account)

    def publish(self, snapshot: ProfileAdoptionAccountSnapshot, *, at: datetime) -> int:
        """CAS the observed auth revision to the conventional saved-session state."""

        if not isinstance(snapshot, ProfileAdoptionAccountSnapshot) or type(snapshot.auth_revision) is not int:
            raise ProfileAdoptionAccountError("profile_adoption_conflict")
        current = _aware_utc(at)
        account = self._account(snapshot.account_id)
        if _snapshot(account) != snapshot or not 0 <= snapshot.auth_revision < 2**63 - 1:
            raise ProfileAdoptionAccountError("profile_adoption_conflict")
        active_qr = exists().where(
            LoginSession.account_id == Account.id,
            LoginSession.method == "qr",
            LoginSession.status.in_(("pending", "waiting_user")),
        )
        revision = self.session.execute(
            update(Account)
            .where(
                Account.id == snapshot.account_id,
                Account.platform == snapshot.platform,
                Account.adapter == "mediacrawler",
                Account.auth_revision == snapshot.auth_revision,
                Account.auth_status != "authenticating",
                ~active_qr,
            )
            .values(
                login_method="saved_session",
                credential_ref=None,
                profile_path=None,
                auth_status="authenticated",
                auth_updated_at=current,
                auth_revision=Account.auth_revision + 1,
                updated_at=current,
            )
            .returning(Account.auth_revision)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()
        if revision is None:
            raise ProfileAdoptionAccountError("profile_adoption_conflict")
        self.session.expire(account)
        return int(revision)


__all__ = [
    "PROFILE_ADOPTION_ACCOUNT_ERROR_CODES",
    "ProfileAdoptionAccountError",
    "ProfileAdoptionAccountRepository",
    "ProfileAdoptionAccountSnapshot",
]
