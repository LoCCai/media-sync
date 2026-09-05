"""Closed account-scoped creator observations with durable request fences."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .base import new_uuid, utc_now
from .models import Account, CreatorProfile, CreatorProfileLookup, Operation
from .repositories import RepositoryError

MAX_AVATAR_BYTES = 2_097_152
_MAX_REVISION = 9_007_199_254_740_991
PROFILE_ERROR_CODES = frozenset(
    {
        "creator_profile_failed",
        "creator_profile_unavailable",
        "creator_profile_invalid",
        "creator_profile_identity_mismatch",
        "creator_profile_auth_changed",
        "creator_profile_auth_required",
        "creator_profile_superseded",
        "creator_profile_cancelled",
        "creator_profile_lease_lost",
        "creator_profile_not_found",
        "creator_profile_receipt_invalid",
        "creator_profile_receipt_expired",
        "creator_profile_busy",
        "creator_profile_unsupported",
        "creator_profile_timeout",
        "creator_profile_runner_failed",
        "creator_profile_operation_invalid",
    }
)


class CreatorProfileError(RepositoryError):
    def __init__(self, code: str) -> None:
        self.code = code if code in PROFILE_ERROR_CODES else "creator_profile_failed"
        super().__init__(self.code)


def _uuid(value: str) -> str:
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise CreatorProfileError("creator_profile_identity_mismatch") from None
    return value


def _identity(platform: str, creator_remote_id: str) -> None:
    if platform != "bili":
        raise CreatorProfileError("creator_profile_unsupported")
    if (
        type(creator_remote_id) is not str
        or re.fullmatch(r"[1-9][0-9]{0,19}", creator_remote_id) is None
        or int(creator_remote_id) > 2**64 - 1
    ):
        raise CreatorProfileError("creator_profile_identity_mismatch")


def _time(value: datetime | None) -> datetime:
    current = utc_now() if value is None else value
    if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
        raise CreatorProfileError("creator_profile_invalid")
    return current


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _reserve_sqlite_writer(session: Session) -> None:
    if session.get_bind().dialect.name == "sqlite":
        session.connection().exec_driver_sql("UPDATE creator_profiles SET generation = generation WHERE 0")


@dataclass(frozen=True, slots=True)
class ProfileValue:
    platform: str
    creator_remote_id: str
    nickname: str
    canonical_homepage: str
    upstream_commit: str

    def validate(self) -> None:
        _identity(self.platform, self.creator_remote_id)
        if (
            type(self.nickname) is not str
            or not 1 <= len(self.nickname) <= 512
            or self.nickname != self.nickname.strip()
            or not self.nickname.isprintable()
            or self.canonical_homepage != f"https://space.bilibili.com/{self.creator_remote_id}"
            or type(self.upstream_commit) is not str
            or re.fullmatch(r"[0-9a-f]{40}", self.upstream_commit) is None
        ):
            raise CreatorProfileError("creator_profile_invalid")


@dataclass(frozen=True, slots=True)
class LookupTicket:
    profile_id: str
    account_id: str
    platform: str
    creator_remote_id: str
    generation: int
    operation_id: str
    frontend_generation: str
    credential_snapshot_digest: str = field(repr=False)

    def to_payload(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "account_id": self.account_id,
            "platform": self.platform,
            "creator_remote_id": self.creator_remote_id,
            "generation": self.generation,
            "operation_id": self.operation_id,
            "frontend_generation": self.frontend_generation,
        }


@dataclass(frozen=True, slots=True)
class ProfileSnapshot:
    profile_id: str
    account_id: str
    platform: str
    creator_remote_id: str
    nickname: str
    canonical_homepage: str
    upstream_commit: str
    observed_at: datetime
    revision: int
    last_success_operation_id: str
    avatar_revision: int
    avatar_observed_at: datetime | None
    avatar_retained: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "account_id": self.account_id,
            "platform": self.platform,
            "creator_remote_id": self.creator_remote_id,
            "nickname": self.nickname,
            "canonical_homepage": self.canonical_homepage,
            "upstream_commit": self.upstream_commit,
            "observed_at": _iso(self.observed_at),
            "revision": self.revision,
            "last_success_operation_id": self.last_success_operation_id,
            "avatar_revision": self.avatar_revision,
            "avatar_observed_at": _iso(self.avatar_observed_at),
            "avatar_retained": self.avatar_retained,
        }


@dataclass(frozen=True, slots=True)
class LookupSnapshot:
    ticket: LookupTicket
    state: Literal["pending", "succeeded", "failed"]
    error_code: str | None
    requested_at: datetime
    completed_at: datetime | None
    result_revision: int | None
    profile: ProfileSnapshot | None

    def to_payload(self) -> dict[str, object]:
        return {
            **self.ticket.to_payload(),
            "state": self.state,
            "error_code": self.error_code,
            "requested_at": _iso(self.requested_at),
            "completed_at": _iso(self.completed_at),
            "result_revision": self.result_revision,
            "profile": self.profile.to_payload() if self.profile is not None else None,
        }


def _credential_digest(account: Account) -> str:
    payload = [
        account.id,
        account.platform,
        account.adapter,
        account.login_method,
        account.auth_status,
        account.auth_revision,
        _iso(account.auth_updated_at),
        account.credential_ref,
        account.profile_path,
    ]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _snapshot(row: CreatorProfile) -> ProfileSnapshot | None:
    if (
        row.nickname is None
        or row.canonical_homepage is None
        or row.upstream_commit is None
        or row.observed_at is None
        or row.last_success_operation_id is None
        or row.revision < 1
    ):
        return None
    return ProfileSnapshot(
        row.id,
        row.account_id,
        row.platform,
        row.creator_remote_id,
        row.nickname,
        row.canonical_homepage,
        row.upstream_commit,
        row.observed_at,
        row.revision,
        row.last_success_operation_id,
        row.avatar_revision,
        row.avatar_observed_at,
        row.avatar_revision > 0 and row.avatar_profile_revision != row.revision,
    )


class CreatorProfileRepository:
    """Flush only. Mutation callers must own the Operation lease transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _account(self, account_id: str, platform: str, *, lock: bool) -> Account:
        statement = select(Account).where(Account.id == _uuid(account_id))
        if lock:
            statement = statement.with_for_update()
        account = self.session.scalar(statement.execution_options(populate_existing=True))
        if account is None or account.platform != platform:
            raise CreatorProfileError("creator_profile_identity_mismatch")
        if (
            account.adapter != "mediacrawler"
            or account.login_method not in {"saved_session", "cookie"}
            or account.auth_status != "authenticated"
            or (account.login_method == "saved_session" and account.credential_ref is not None)
            or (account.login_method == "cookie" and account.credential_ref is None)
            or account.profile_path is not None
        ):
            raise CreatorProfileError("creator_profile_auth_required")
        return account

    def credential_snapshot(self, account_id: str, platform: str) -> str:
        return _credential_digest(self._account(account_id, platform, lock=False))

    def _operation(self, operation_id: str, account_id: str, *, at: datetime) -> Operation:
        operation = self.session.scalar(
            select(Operation)
            .where(Operation.id == _uuid(operation_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            operation is None
            or operation.kind != "creator-profile"
            or operation.target_type != "account"
            or operation.target_id != account_id
            or operation.state != "running"
        ):
            raise CreatorProfileError("creator_profile_operation_invalid")
        if operation.cancel_requested_at is not None:
            raise CreatorProfileError("creator_profile_cancelled")
        if operation.lease_expires_at is None or operation.lease_expires_at <= at:
            raise CreatorProfileError("creator_profile_lease_lost")
        return operation

    @staticmethod
    def _ticket(profile: CreatorProfile, lookup: CreatorProfileLookup) -> LookupTicket:
        return LookupTicket(
            profile.id,
            profile.account_id,
            profile.platform,
            profile.creator_remote_id,
            lookup.generation,
            lookup.operation_id,
            lookup.frontend_generation,
            lookup.credential_snapshot_digest,
        )

    def begin_lookup(
        self,
        *,
        account_id: str,
        platform: str,
        creator_remote_id: str,
        operation_id: str,
        frontend_generation: str,
        expected_credential_digest: str | None = None,
        at: datetime | None = None,
    ) -> LookupTicket:
        _identity(platform, creator_remote_id)
        _uuid(frontend_generation)
        current = _time(at)
        _reserve_sqlite_writer(self.session)
        self._operation(operation_id, account_id, at=current)
        account = self._account(account_id, platform, lock=True)
        digest = _credential_digest(account)
        if expected_credential_digest is not None and expected_credential_digest != digest:
            raise CreatorProfileError("creator_profile_auth_changed")
        existing = self.session.get(CreatorProfileLookup, operation_id)
        if existing is not None:
            profile = self.session.get(CreatorProfile, existing.profile_id)
            if (
                profile is None
                or profile.account_id != account_id
                or profile.platform != platform
                or profile.creator_remote_id != creator_remote_id
                or existing.frontend_generation != frontend_generation
                or existing.credential_snapshot_digest != digest
            ):
                raise CreatorProfileError("creator_profile_identity_mismatch")
            return self._ticket(profile, existing)
        profile = self.session.scalar(
            select(CreatorProfile)
            .where(
                CreatorProfile.account_id == account_id,
                CreatorProfile.platform == platform,
                CreatorProfile.creator_remote_id == creator_remote_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if profile is None:
            profile = CreatorProfile(
                id=new_uuid(),
                account_id=account_id,
                platform=platform,
                creator_remote_id=creator_remote_id,
                generation=0,
                revision=0,
                avatar_revision=0,
            )
            self.session.add(profile)
        if profile.generation >= _MAX_REVISION:
            raise CreatorProfileError("creator_profile_unavailable")
        profile.generation += 1
        profile.latest_operation_id = operation_id
        profile.latest_frontend_generation = frontend_generation
        profile.credential_snapshot_digest = digest
        profile.updated_at = current
        lookup = CreatorProfileLookup(
            operation_id=operation_id,
            profile_id=profile.id,
            generation=profile.generation,
            frontend_generation=frontend_generation,
            credential_snapshot_digest=digest,
            state="pending",
            requested_at=current,
        )
        self.session.add(lookup)
        self.session.flush()
        return self._ticket(profile, lookup)

    def _current(self, ticket: LookupTicket, at: datetime) -> tuple[CreatorProfile, CreatorProfileLookup]:
        if not isinstance(ticket, LookupTicket):
            raise CreatorProfileError("creator_profile_identity_mismatch")
        _reserve_sqlite_writer(self.session)
        self._operation(ticket.operation_id, ticket.account_id, at=at)
        account = self._account(ticket.account_id, ticket.platform, lock=True)
        if _credential_digest(account) != ticket.credential_snapshot_digest:
            raise CreatorProfileError("creator_profile_auth_changed")
        profile = self.session.scalar(
            select(CreatorProfile)
            .where(CreatorProfile.id == ticket.profile_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        lookup = self.session.get(CreatorProfileLookup, ticket.operation_id)
        if profile is None or lookup is None or self._ticket(profile, lookup) != ticket:
            raise CreatorProfileError("creator_profile_identity_mismatch")
        if (
            profile.generation != ticket.generation
            or profile.latest_operation_id != ticket.operation_id
            or profile.latest_frontend_generation != ticket.frontend_generation
            or profile.credential_snapshot_digest != ticket.credential_snapshot_digest
        ):
            raise CreatorProfileError("creator_profile_superseded")
        return profile, lookup

    def publish(
        self,
        ticket: LookupTicket,
        profile_value: ProfileValue,
        *,
        avatar: bytes | None = None,
        at: datetime | None = None,
    ) -> ProfileSnapshot:
        if not isinstance(profile_value, ProfileValue):
            raise CreatorProfileError("creator_profile_invalid")
        profile_value.validate()
        if (profile_value.platform, profile_value.creator_remote_id) != (ticket.platform, ticket.creator_remote_id):
            raise CreatorProfileError("creator_profile_identity_mismatch")
        if avatar is not None and (
            type(avatar) is not bytes
            or not 33 <= len(avatar) <= MAX_AVATAR_BYTES
            or avatar[:8] != b"\x89PNG\r\n\x1a\n"
            or avatar[12:16] != b"IHDR"
            or not 0 < int.from_bytes(avatar[16:20], "big") * int.from_bytes(avatar[20:24], "big") <= 8_000_000
        ):
            raise CreatorProfileError("creator_profile_invalid")
        current = _time(at)
        profile, lookup = self._current(ticket, current)
        if lookup.state != "pending":
            raise CreatorProfileError("creator_profile_superseded")
        if profile.revision >= _MAX_REVISION or profile.avatar_revision >= _MAX_REVISION:
            raise CreatorProfileError("creator_profile_unavailable")
        profile.nickname = profile_value.nickname
        profile.canonical_homepage = profile_value.canonical_homepage
        profile.upstream_commit = profile_value.upstream_commit
        profile.observed_at = current
        profile.revision += 1
        profile.last_success_operation_id = ticket.operation_id
        profile.updated_at = current
        if avatar is not None:
            profile.avatar_png = avatar
            profile.avatar_revision += 1
            profile.avatar_observed_at = current
            profile.avatar_profile_revision = profile.revision
        lookup.state = "succeeded"
        lookup.completed_at = current
        lookup.result_revision = profile.revision
        lookup.error_code = None
        self.session.flush()
        result = _snapshot(profile)
        assert result is not None
        return result

    def mark_failed(self, ticket: LookupTicket, error_code: str, *, at: datetime | None = None) -> None:
        current = _time(at)
        _profile, lookup = self._current(ticket, current)
        if lookup.state != "pending":
            raise CreatorProfileError("creator_profile_superseded")
        lookup.state = "failed"
        lookup.error_code = error_code if error_code in PROFILE_ERROR_CODES else "creator_profile_failed"
        lookup.completed_at = current
        self.session.flush()

    def read_lookup(self, operation_id: str) -> LookupSnapshot | None:
        lookup = self.session.get(CreatorProfileLookup, _uuid(operation_id))
        if lookup is None:
            return None
        profile = self.session.get(CreatorProfile, lookup.profile_id)
        if profile is None:
            return None
        result = _snapshot(profile)
        if lookup.state == "succeeded" and lookup.result_revision != profile.revision:
            result = None
        if lookup.state not in {"pending", "succeeded", "failed"}:
            raise CreatorProfileError("creator_profile_invalid")
        return LookupSnapshot(
            self._ticket(profile, lookup),
            cast(Literal["pending", "succeeded", "failed"], lookup.state),
            (lookup.error_code if lookup.error_code in PROFILE_ERROR_CODES else "creator_profile_failed")
            if lookup.error_code is not None
            else None,
            lookup.requested_at,
            lookup.completed_at,
            lookup.result_revision,
            result,
        )

    def get_profile(self, account_id: str, platform: str, creator_remote_id: str) -> ProfileSnapshot | None:
        _uuid(account_id)
        profile = self.session.scalar(
            select(CreatorProfile).where(
                CreatorProfile.account_id == account_id,
                CreatorProfile.platform == platform,
                CreatorProfile.creator_remote_id == creator_remote_id,
            )
        )
        return _snapshot(profile) if profile is not None else None

    def get_avatar(self, profile_id: str, avatar_revision: int) -> bytes | None:
        _uuid(profile_id)
        if type(avatar_revision) is not int or not 1 <= avatar_revision <= _MAX_REVISION:
            return None
        return self.session.scalar(
            select(CreatorProfile.avatar_png).where(
                CreatorProfile.id == profile_id,
                CreatorProfile.avatar_revision == avatar_revision,
                CreatorProfile.revision > 0,
            )
        )

    def require_receipt(
        self,
        operation_id: str,
        account_id: str,
        platform: str,
        creator_remote_id: str,
        *,
        at: datetime | None = None,
        ttl_seconds: int = 900,
    ) -> ProfileSnapshot:
        current = _time(at)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900:
            raise CreatorProfileError("creator_profile_receipt_invalid")
        operation = self.session.scalar(select(Operation).where(Operation.id == _uuid(operation_id)).with_for_update())
        if (
            operation is None
            or operation.kind != "creator-profile"
            or operation.target_type != "account"
            or operation.target_id != account_id
            or operation.state != "succeeded"
        ):
            raise CreatorProfileError("creator_profile_receipt_invalid")
        account = self._account(account_id, platform, lock=True)
        snapshot = self.read_lookup(operation_id)
        if (
            snapshot is None
            or snapshot.state != "succeeded"
            or snapshot.profile is None
            or snapshot.ticket.account_id != account_id
            or snapshot.ticket.platform != platform
            or snapshot.ticket.creator_remote_id != creator_remote_id
            or snapshot.ticket.credential_snapshot_digest != _credential_digest(account)
            or snapshot.profile.last_success_operation_id != operation_id
        ):
            raise CreatorProfileError("creator_profile_receipt_invalid")
        profile = self.session.get(CreatorProfile, snapshot.ticket.profile_id)
        if (
            profile is None
            or profile.latest_operation_id != operation_id
            or profile.generation != snapshot.ticket.generation
        ):
            raise CreatorProfileError("creator_profile_receipt_invalid")
        if (
            snapshot.completed_at is None
            or snapshot.completed_at > current
            or current - snapshot.completed_at > timedelta(seconds=ttl_seconds)
        ):
            raise CreatorProfileError("creator_profile_receipt_expired")
        return snapshot.profile


__all__ = [
    "CreatorProfileError",
    "CreatorProfileRepository",
    "LookupSnapshot",
    "LookupTicket",
    "ProfileSnapshot",
    "ProfileValue",
]
