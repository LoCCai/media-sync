"""Transactional SQLAlchemy repositories.

Every repository accepts an explicit :class:`sqlalchemy.orm.Session`.  Methods
flush when generated identifiers or constraint checks are needed, but never
commit.  The caller owns the outer transaction through ``Database.session()``.
"""

from __future__ import annotations

import builtins
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, joinedload

from media_sync.domain.enums import AuthStatus, RunStatus
from media_sync.domain.transitions import transition_auth, transition_run
from media_sync.security import SecretReference, redact_mapping, redact_text

from .base import new_uuid, utc_now
from .models import (
    JOB_STATUSES,
    RUN_STATUSES,
    TERMINAL_JOB_STATUSES,
    TERMINAL_RUN_STATUSES,
    Account,
    Asset,
    Author,
    Content,
    ExportRecord,
    Job,
    LoginSession,
    RunEvent,
    Subscription,
    SyncRun,
)


class RepositoryError(RuntimeError):
    """Base error raised for repository-level invariants."""


class NotFoundError(RepositoryError):
    """The requested row does not exist."""


class LeaseLostError(RepositoryError):
    """A worker attempted to mutate a job without its current lease."""


class StaleCheckpointError(RepositoryError):
    """A synchronization run attempted to publish an obsolete checkpoint."""

    def __init__(self, subscription_id: str, expected_revision: int, actual_revision: int) -> None:
        self.subscription_id = subscription_id
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision
        super().__init__(
            f"subscription {subscription_id} checkpoint is stale: "
            f"expected revision {expected_revision}, current revision {actual_revision}"
        )


class _UnsetType:
    __slots__ = ()


_UNSET = _UnsetType()


def _aware_utc(value: datetime | None = None) -> datetime:
    result = value or utc_now()
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return result.astimezone(UTC)


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_thaw_json(item) for item in value]
    if isinstance(value, set | frozenset):
        return [_thaw_json(item) for item in sorted(value, key=repr)]
    return value


def _json(value: Mapping[str, Any] | None) -> dict[str, Any]:
    thawed = _thaw_json(redact_mapping(value or {}))
    if not isinstance(thawed, dict):  # pragma: no cover - Mapping always becomes dict
        raise TypeError("JSON object conversion did not produce a dictionary")
    return thawed


def _safe_text(value: str | None) -> str | None:
    return redact_text(value) if value is not None else None


def _require_status(value: str, allowed: frozenset[str], kind: str) -> None:
    if value not in allowed:
        raise ValueError(f"unsupported {kind} status: {value!r}")


@dataclass(frozen=True, slots=True)
class AuthorUpsert:
    platform: str
    remote_id: str
    display_name: str
    handle: str | None = None
    profile_url: str | None = field(default=None, repr=False)
    avatar_url: str | None = field(default=None, repr=False)
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True, slots=True)
class ContentUpsert:
    remote_id: str
    kind: str
    remote_type: str = "content"
    title: str | None = None
    body: str | None = field(default=None, repr=False)
    canonical_url: str | None = field(default=None, repr=False)
    published_at: datetime | None = None
    remote_updated_at: datetime | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict, repr=False)
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)
    metadata_hash: str | None = None


@dataclass(frozen=True, slots=True)
class AssetUpsert:
    kind: str
    position: int
    platform: str
    remote_id: str | None = None
    source_url: str | None = field(default=None, repr=False)
    locator: Mapping[str, Any] = field(default_factory=dict, repr=False)
    mime_type: str | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    local_path: str | None = field(default=None, repr=False)
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    status: str = "discovered"
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)


class AccountRepository:
    """Persistence operations for platform accounts."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        platform: str,
        display_name: str,
        adapter: str = "native",
        login_method: str | None = None,
        credential_ref: str | None = None,
        profile_path: str | None = None,
        auth_status: str = "unknown",
    ) -> Account:
        safe_credential_ref = SecretReference.parse(credential_ref).serialize() if credential_ref is not None else None
        account = Account(
            platform=platform,
            adapter=adapter,
            display_name=display_name,
            login_method=login_method,
            credential_ref=safe_credential_ref,
            profile_path=profile_path,
            auth_status=auth_status,
        )
        self.session.add(account)
        self.session.flush()
        return account

    def get(self, account_id: str) -> Account | None:
        return self.session.get(Account, account_id)

    def require(self, account_id: str) -> Account:
        account = self.get(account_id)
        if account is None:
            raise NotFoundError(f"account not found: {account_id}")
        return account

    def get_by_platform_and_name(self, platform: str, display_name: str) -> Account | None:
        return self.session.scalar(
            select(Account).where(Account.platform == platform, Account.display_name == display_name)
        )

    def list(self) -> list[Account]:
        return list(
            self.session.scalars(select(Account).order_by(Account.platform, Account.display_name, Account.id)).all()
        )

    def set_auth_status(self, account_id: str, status: str, *, at: datetime | None = None) -> Account:
        account = self.require(account_id)
        transition_auth(AuthStatus(account.auth_status), AuthStatus(status))
        account.auth_status = status
        account.auth_updated_at = _aware_utc(at)
        self.session.flush()
        return account


class LoginSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        account_id: str,
        method: str,
        challenge_kind: str | None = None,
        public_payload: Mapping[str, Any] | None = None,
        expires_at: datetime | None = None,
    ) -> LoginSession:
        login_session = LoginSession(
            account_id=account_id,
            method=method,
            challenge_kind=challenge_kind,
            public_payload=_json(public_payload),
            expires_at=expires_at,
        )
        self.session.add(login_session)
        self.session.flush()
        return login_session

    def get(self, login_session_id: str) -> LoginSession | None:
        return self.session.get(LoginSession, login_session_id)


class AuthorRepository:
    """Atomic author and normalized content ingestion."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, author_id: str) -> Author | None:
        return self.session.get(Author, author_id)

    def get_by_remote(self, platform: str, remote_id: str) -> Author | None:
        return self.session.scalar(select(Author).where(Author.platform == platform, Author.remote_id == remote_id))

    def list(self, *, platform: str | None = None) -> list[Author]:
        statement = select(Author)
        if platform is not None:
            statement = statement.where(Author.platform == platform)
        statement = statement.order_by(Author.platform, Author.display_name, Author.remote_id)
        return list(self.session.scalars(statement).all())

    def upsert(self, value: AuthorUpsert, *, seen_at: datetime | None = None) -> Author:
        now = _aware_utc(seen_at)
        if self.session.get_bind().dialect.name == "sqlite":
            statement = (
                sqlite_insert(Author)
                .values(
                    id=new_uuid(),
                    platform=value.platform,
                    remote_id=value.remote_id,
                    display_name=value.display_name,
                    handle=value.handle,
                    profile_url=_safe_text(value.profile_url),
                    avatar_url=_safe_text(value.avatar_url),
                    raw=_json(value.raw),
                    first_seen_at=now,
                    last_seen_at=now,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=[Author.platform, Author.remote_id],
                    set_={
                        "display_name": value.display_name,
                        "handle": value.handle,
                        "profile_url": _safe_text(value.profile_url),
                        "avatar_url": _safe_text(value.avatar_url),
                        "raw": _json(value.raw),
                        "last_seen_at": now,
                        "updated_at": now,
                    },
                )
                .returning(Author)
                .execution_options(populate_existing=True)
            )
            return self.session.scalars(statement).one()

        author = self.get_by_remote(value.platform, value.remote_id)
        if author is None:
            author = Author(
                platform=value.platform,
                remote_id=value.remote_id,
                display_name=value.display_name,
                handle=value.handle,
                profile_url=_safe_text(value.profile_url),
                avatar_url=_safe_text(value.avatar_url),
                raw=_json(value.raw),
                first_seen_at=now,
                last_seen_at=now,
            )
            self.session.add(author)
        else:
            author.display_name = value.display_name
            author.handle = value.handle
            author.profile_url = _safe_text(value.profile_url)
            author.avatar_url = _safe_text(value.avatar_url)
            author.raw = _json(value.raw)
            author.last_seen_at = now
        self.session.flush()
        return author

    def upsert_with_contents(
        self,
        author_value: AuthorUpsert,
        contents: Sequence[ContentUpsert],
        *,
        seen_at: datetime | None = None,
    ) -> tuple[Author, builtins.list[Content]]:
        """Upsert one author and its content in a savepoint-backed unit.

        The method never commits.  Any constraint or conversion failure rolls
        back every author/content change made by this call while leaving the
        caller's outer transaction available for handling or rollback.
        """

        now = _aware_utc(seen_at)
        with self.session.begin_nested():
            author = self.upsert(author_value, seen_at=now)
            persisted = [self._upsert_content(author, item, seen_at=now) for item in contents]
            self.session.flush()
        return author, persisted

    def upsert_author_with_contents(
        self,
        author_value: AuthorUpsert,
        contents: Sequence[ContentUpsert],
        *,
        seen_at: datetime | None = None,
    ) -> tuple[Author, builtins.list[Content]]:
        """Compatibility alias with an explicit operation name."""

        return self.upsert_with_contents(author_value, contents, seen_at=seen_at)

    def _upsert_content(self, author: Author, value: ContentUpsert, *, seen_at: datetime) -> Content:
        if self.session.get_bind().dialect.name == "sqlite":
            statement = (
                sqlite_insert(Content)
                .values(
                    id=new_uuid(),
                    author_id=author.id,
                    platform=author.platform,
                    remote_type=value.remote_type,
                    remote_id=value.remote_id,
                    kind=value.kind,
                    title=value.title,
                    body=_safe_text(value.body),
                    canonical_url=_safe_text(value.canonical_url),
                    published_at=value.published_at,
                    remote_updated_at=value.remote_updated_at,
                    metrics=_json(value.metrics),
                    raw=_json(value.raw),
                    metadata_hash=value.metadata_hash,
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    created_at=seen_at,
                    updated_at=seen_at,
                )
                .on_conflict_do_update(
                    index_elements=[Content.platform, Content.remote_type, Content.remote_id],
                    set_={
                        "author_id": author.id,
                        "kind": value.kind,
                        "title": value.title,
                        "body": _safe_text(value.body),
                        "canonical_url": _safe_text(value.canonical_url),
                        "published_at": value.published_at,
                        "remote_updated_at": value.remote_updated_at,
                        "metrics": _json(value.metrics),
                        "raw": _json(value.raw),
                        "metadata_hash": value.metadata_hash,
                        "last_seen_at": seen_at,
                        "tombstoned_at": None,
                        "updated_at": seen_at,
                    },
                )
                .returning(Content)
                .execution_options(populate_existing=True)
            )
            return self.session.scalars(statement).one()

        content = self.session.scalar(
            select(Content).where(
                Content.platform == author.platform,
                Content.remote_type == value.remote_type,
                Content.remote_id == value.remote_id,
            )
        )
        if content is None:
            content = Content(
                author_id=author.id,
                platform=author.platform,
                remote_type=value.remote_type,
                remote_id=value.remote_id,
                kind=value.kind,
                title=value.title,
                body=_safe_text(value.body),
                canonical_url=_safe_text(value.canonical_url),
                published_at=value.published_at,
                remote_updated_at=value.remote_updated_at,
                metrics=_json(value.metrics),
                raw=_json(value.raw),
                metadata_hash=value.metadata_hash,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
            self.session.add(content)
        else:
            content.author_id = author.id
            content.kind = value.kind
            content.title = value.title
            content.body = _safe_text(value.body)
            content.canonical_url = _safe_text(value.canonical_url)
            content.published_at = value.published_at
            content.remote_updated_at = value.remote_updated_at
            content.metrics = _json(value.metrics)
            content.raw = _json(value.raw)
            content.metadata_hash = value.metadata_hash
            content.last_seen_at = seen_at
            content.tombstoned_at = None
        self.session.flush()
        return content


class AssetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, asset_id: str) -> Asset | None:
        return self.session.get(Asset, asset_id)

    def upsert_for_content(self, content_id: str, value: AssetUpsert) -> Asset:
        now = utc_now()
        safe_source_url = _safe_text(value.source_url)
        locator = _json(value.locator)
        if value.source_url is not None and safe_source_url != value.source_url:
            locator["refresh_required"] = True
        values: dict[str, Any] = {
            "platform": value.platform,
            "remote_id": value.remote_id,
            "source_url": safe_source_url,
            "locator": locator,
            "mime_type": value.mime_type,
            "size_bytes": value.size_bytes,
            "checksum_sha256": value.checksum_sha256,
            "local_path": value.local_path,
            "width": value.width,
            "height": value.height,
            "duration_ms": value.duration_ms,
            "status": value.status,
            "raw": _json(value.raw),
        }
        if self.session.get_bind().dialect.name == "sqlite":
            statement = (
                sqlite_insert(Asset)
                .values(
                    id=new_uuid(),
                    content_id=content_id,
                    kind=value.kind,
                    position=value.position,
                    created_at=now,
                    updated_at=now,
                    **values,
                )
                .on_conflict_do_update(
                    index_elements=[Asset.content_id, Asset.kind, Asset.position],
                    set_={**values, "updated_at": now},
                )
                .returning(Asset)
                .execution_options(populate_existing=True)
            )
            return self.session.scalars(statement).one()

        asset = self.session.scalar(
            select(Asset).where(
                Asset.content_id == content_id,
                Asset.kind == value.kind,
                Asset.position == value.position,
            )
        )
        if asset is None:
            asset = Asset(content_id=content_id, kind=value.kind, position=value.position, **values)
            self.session.add(asset)
        else:
            for name, item in values.items():
                setattr(asset, name, item)
        self.session.flush()
        return asset


class SubscriptionRepository:
    """Account/author subscription storage with eagerly loaded list results."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        account_id: str,
        author_id: str,
        enabled: bool = True,
        interval_seconds: int = 21_600,
        max_items: int = 30,
        cursor: Mapping[str, Any] | None = None,
        cursor_version: int = 1,
        backfill_cursor: Mapping[str, Any] | None = None,
        policy: Mapping[str, Any] | None = None,
        next_run_at: datetime | None = None,
    ) -> Subscription:
        account = self.session.get(Account, account_id)
        if account is None:
            raise NotFoundError(f"account not found: {account_id}")
        author = self.session.get(Author, author_id)
        if author is None:
            raise NotFoundError(f"author not found: {author_id}")
        if account.platform != author.platform:
            raise RepositoryError("subscription account and author platforms do not match")

        subscription = Subscription(
            account_id=account_id,
            author_id=author_id,
            enabled=enabled,
            interval_seconds=interval_seconds,
            max_items=max_items,
            cursor=_json(cursor) if cursor is not None else None,
            cursor_version=cursor_version,
            backfill_cursor=_json(backfill_cursor) if backfill_cursor is not None else None,
            policy=_json(policy),
            next_run_at=next_run_at,
        )
        self.session.add(subscription)
        self.session.flush()
        return self.get(subscription.id) or subscription

    def get(self, subscription_id: str) -> Subscription | None:
        return self.session.scalar(
            select(Subscription)
            .where(Subscription.id == subscription_id)
            .options(joinedload(Subscription.account), joinedload(Subscription.author))
        )

    def get_by_account_and_author(self, account_id: str, author_id: str) -> Subscription | None:
        return self.session.scalar(
            select(Subscription)
            .where(Subscription.account_id == account_id, Subscription.author_id == author_id)
            .options(joinedload(Subscription.account), joinedload(Subscription.author))
        )

    def list(self, *, enabled: bool | None = None) -> list[Subscription]:
        statement = select(Subscription).options(
            joinedload(Subscription.account),
            joinedload(Subscription.author),
        )
        if enabled is not None:
            statement = statement.where(Subscription.enabled.is_(enabled))
        statement = statement.order_by(Subscription.created_at, Subscription.id)
        return list(self.session.scalars(statement).unique().all())

    def update_cursor(
        self,
        subscription_id: str,
        cursor: Mapping[str, Any] | None,
        *,
        cursor_version: int | None = None,
        backfill_cursor: Mapping[str, Any] | _UnsetType | None = _UNSET,
        next_run_at: datetime | _UnsetType | None = _UNSET,
        succeeded_at: datetime | None = None,
        watermarked_at: datetime | None = None,
        watermark_remote_ids: Sequence[str] | None = None,
    ) -> Subscription:
        """Publish against the latest revision for legacy single-writer callers.

        Long-running or concurrent workers must use :meth:`publish_checkpoint`
        with the revision read before their external work begins.
        """

        revision = self.session.scalar(
            select(Subscription.checkpoint_revision).where(Subscription.id == subscription_id)
        )
        if revision is None:
            raise NotFoundError(f"subscription not found: {subscription_id}")
        return self.publish_checkpoint(
            subscription_id,
            expected_revision=revision,
            cursor=cursor,
            cursor_version=cursor_version,
            backfill_cursor=backfill_cursor,
            next_run_at=next_run_at,
            succeeded_at=succeeded_at,
            watermarked_at=watermarked_at,
            watermark_remote_ids=watermark_remote_ids,
        )

    def publish_checkpoint(
        self,
        subscription_id: str,
        *,
        expected_revision: int,
        cursor: Mapping[str, Any] | _UnsetType | None = _UNSET,
        cursor_version: int | None = None,
        backfill_cursor: Mapping[str, Any] | _UnsetType | None = _UNSET,
        next_run_at: datetime | _UnsetType | None = _UNSET,
        succeeded_at: datetime | None = None,
        watermarked_at: datetime | None = None,
        watermark_remote_ids: Sequence[str] | None = None,
    ) -> Subscription:
        """Atomically publish forward/backfill state using optimistic fencing.

        The first update only claims ``expected_revision`` and acquires the
        database writer lock.  Every checkpoint field is then changed in the
        same caller-owned transaction.  A stale revision therefore changes
        neither checkpoint data nor scheduling state.  Omitting
        ``backfill_cursor`` or ``next_run_at`` preserves it; passing ``None``
        clears that individual field.
        """

        if expected_revision < 0:
            raise ValueError("expected_revision must be nonnegative")
        if watermark_remote_ids and watermarked_at is None:
            raise ValueError("watermark_remote_ids require watermarked_at")

        safe_cursor: dict[str, Any] | _UnsetType | None = (
            cursor if isinstance(cursor, _UnsetType) or cursor is None else _json(cursor)
        )
        safe_backfill_cursor: dict[str, Any] | _UnsetType | None = (
            backfill_cursor
            if isinstance(backfill_cursor, _UnsetType) or backfill_cursor is None
            else _json(backfill_cursor)
        )
        normalized_next_run_at = (
            next_run_at if isinstance(next_run_at, _UnsetType) or next_run_at is None else _aware_utc(next_run_at)
        )
        normalized_succeeded_at = _aware_utc(succeeded_at) if succeeded_at is not None else None
        normalized_watermark = _aware_utc(watermarked_at) if watermarked_at is not None else None
        incoming_remote_ids = sorted(set(watermark_remote_ids or ()))
        now = utc_now()

        subscription = self.session.scalars(
            update(Subscription)
            .where(
                Subscription.id == subscription_id,
                Subscription.checkpoint_revision == expected_revision,
            )
            .values(
                checkpoint_revision=Subscription.checkpoint_revision + 1,
                updated_at=now,
            )
            .returning(Subscription)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        ).one_or_none()
        if subscription is None:
            actual_revision = self.session.scalar(
                select(Subscription.checkpoint_revision).where(Subscription.id == subscription_id)
            )
            if actual_revision is None:
                raise NotFoundError(f"subscription not found: {subscription_id}")
            raise StaleCheckpointError(subscription_id, expected_revision, actual_revision)

        if not isinstance(safe_cursor, _UnsetType):
            subscription.cursor = safe_cursor
        if cursor_version is not None:
            subscription.cursor_version = cursor_version
        if not isinstance(safe_backfill_cursor, _UnsetType):
            subscription.backfill_cursor = safe_backfill_cursor
        subscription.last_run_at = normalized_succeeded_at or now
        if not isinstance(normalized_next_run_at, _UnsetType):
            subscription.next_run_at = normalized_next_run_at
        if normalized_watermark is not None:
            if subscription.watermarked_at is None or normalized_watermark > subscription.watermarked_at:
                subscription.watermarked_at = normalized_watermark
                subscription.watermark_remote_ids = incoming_remote_ids
            elif normalized_watermark == subscription.watermarked_at:
                subscription.watermark_remote_ids = sorted(
                    set(subscription.watermark_remote_ids).union(incoming_remote_ids)
                )
        if normalized_succeeded_at is not None:
            subscription.last_success_at = normalized_succeeded_at
            subscription.consecutive_failures = 0
        self.session.flush()
        return subscription


class SyncRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        subscription_id: str,
        status: str = "queued",
        cursor_before: Mapping[str, Any] | None = None,
        checkpoint_revision_before: int | None = None,
        manifest: Mapping[str, Any] | None = None,
    ) -> SyncRun:
        _require_status(status, RUN_STATUSES, "run")
        if checkpoint_revision_before is None:
            checkpoint_revision_before = self.session.scalar(
                select(Subscription.checkpoint_revision).where(Subscription.id == subscription_id)
            )
            if checkpoint_revision_before is None:
                raise NotFoundError(f"subscription not found: {subscription_id}")
        if checkpoint_revision_before < 0:
            raise ValueError("checkpoint_revision_before must be nonnegative")
        run = SyncRun(
            subscription_id=subscription_id,
            status=status,
            cursor_before=_json(cursor_before) if cursor_before is not None else None,
            checkpoint_revision_before=checkpoint_revision_before,
            manifest=_json(manifest),
        )
        self.session.add(run)
        self.session.flush()
        self.add_event(run.id, "run_created", to_status=status)
        return run

    def get(self, run_id: str) -> SyncRun | None:
        return self.session.get(SyncRun, run_id)

    def require(self, run_id: str) -> SyncRun:
        run = self.get(run_id)
        if run is None:
            raise NotFoundError(f"sync run not found: {run_id}")
        return run

    def record_checkpoint_publication(
        self,
        run_id: str,
        *,
        expected_revision: int,
        published_revision: int,
        expected_status: str | None = None,
    ) -> SyncRun:
        """Record one successful checkpoint publication on its owning run."""

        if expected_revision < 0:
            raise ValueError("expected_revision must be nonnegative")
        if published_revision != expected_revision + 1:
            raise ValueError("published_revision must immediately follow expected_revision")
        if expected_status is not None:
            _require_status(expected_status, RUN_STATUSES, "run")
        now = utc_now()
        conditions: list[Any] = [
            SyncRun.id == run_id,
            or_(
                and_(
                    SyncRun.checkpoint_revision_before == expected_revision,
                    SyncRun.checkpoint_revision_after.is_(None),
                ),
                SyncRun.checkpoint_revision_after == expected_revision,
            ),
        ]
        if expected_status is not None:
            conditions.append(SyncRun.status == expected_status)
        run = self.session.scalars(
            update(SyncRun)
            .where(*conditions)
            .values(checkpoint_revision_after=published_revision, updated_at=now)
            .returning(SyncRun)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        ).one_or_none()
        if run is None:
            if self.session.scalar(select(SyncRun.id).where(SyncRun.id == run_id)) is None:
                raise NotFoundError(f"sync run not found: {run_id}")
            raise RepositoryError("sync run cannot publish the requested checkpoint")
        self.session.flush()
        return run

    def set_status(
        self,
        run_id: str,
        status: str,
        *,
        expected_status: str,
        message: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        at: datetime | None = None,
    ) -> SyncRun:
        _require_status(status, RUN_STATUSES, "run")
        _require_status(expected_status, RUN_STATUSES, "run")
        now = _aware_utc(at)
        transition_run(RunStatus(expected_status), RunStatus(status))
        values: dict[str, Any] = {
            "status": status,
            "error_code": error_code,
            "error_message": _safe_text(error_message),
            "updated_at": now,
        }
        if status in {"claimed", "running"}:
            values["started_at"] = func.coalesce(SyncRun.started_at, now)
        if status in TERMINAL_RUN_STATUSES:
            values["finished_at"] = now
        statement = (
            update(SyncRun)
            .where(SyncRun.id == run_id, SyncRun.status == expected_status)
            .values(**values)
            .returning(SyncRun)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        updated = self.session.execute(statement).scalar_one_or_none()
        if updated is None:
            raise RepositoryError(f"sync run {run_id} is missing or no longer has status {expected_status!r}")
        self.add_event(
            run_id,
            "status_changed",
            from_status=expected_status,
            to_status=status,
            message=_safe_text(message),
            created_at=now,
        )
        self.session.flush()
        return updated

    def add_event(
        self,
        run_id: str,
        event_type: str,
        *,
        from_status: str | None = None,
        to_status: str | None = None,
        message: str | None = None,
        payload: Mapping[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> RunEvent:
        now = _aware_utc(created_at)
        sequence = self.session.scalar(
            update(SyncRun)
            .where(SyncRun.id == run_id)
            .values(event_sequence=SyncRun.event_sequence + 1, updated_at=now)
            .returning(SyncRun.event_sequence)
        )
        if sequence is None:
            raise NotFoundError(f"sync run not found: {run_id}")
        event = RunEvent(
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            message=_safe_text(message),
            payload=_json(payload),
            created_at=now,
        )
        self.session.add(event)
        self.session.flush()
        return event


class JobRepository:
    """Idempotent enqueue and conditional lease-based job claiming."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, job_id: str) -> Job | None:
        return self.session.get(Job, job_id)

    def get_by_key(self, job_type: str, natural_key: str) -> Job | None:
        return self.session.scalar(select(Job).where(Job.job_type == job_type, Job.natural_key == natural_key))

    def list(self, *, status: str | None = None) -> list[Job]:
        statement = select(Job)
        if status is not None:
            _require_status(status, JOB_STATUSES, "job")
            statement = statement.where(Job.status == status)
        statement = statement.order_by(Job.created_at, Job.id)
        return list(self.session.scalars(statement).all())

    def enqueue(
        self,
        *,
        job_type: str,
        natural_key: str,
        payload: Mapping[str, Any] | None = None,
        run_id: str | None = None,
        priority: int = 0,
        max_attempts: int = 5,
        available_at: datetime | None = None,
    ) -> Job:
        values = {
            "id": new_uuid(),
            "run_id": run_id,
            "job_type": job_type,
            "natural_key": natural_key,
            "payload": _json(payload),
            "status": "queued",
            "priority": priority,
            "attempts": 0,
            "max_attempts": max_attempts,
            "available_at": _aware_utc(available_at),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        if self.session.get_bind().dialect.name == "sqlite":
            statement = (
                sqlite_insert(Job)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[Job.job_type, Job.natural_key])
                .returning(Job.id)
            )
            created_id = self.session.scalar(statement)
            if created_id is not None:
                job = self.session.get(Job, created_id)
                if job is None:  # pragma: no cover - RETURNING guarantees visibility
                    raise RepositoryError(f"inserted job is not visible: {created_id}")
                return job
            existing = self.get_by_key(job_type, natural_key)
            if existing is None:  # pragma: no cover - protected by the unique constraint
                raise RepositoryError("idempotent job insert lost its conflicting row")
            return existing

        existing = self.get_by_key(job_type, natural_key)
        if existing is not None:
            return existing
        job = Job(**values)
        self.session.add(job)
        self.session.flush()
        return job

    def reclaim_expired(self, *, now: datetime | None = None) -> int:
        current = _aware_utc(now)
        expired = and_(
            Job.status.in_(("claimed", "running")),
            Job.lease_expires_at.is_not(None),
            Job.lease_expires_at <= current,
        )
        terminal_result = cast(
            CursorResult[Any],
            self.session.execute(
                update(Job)
                .where(expired, Job.attempts >= Job.max_attempts)
                .values(
                    status="failed_terminal",
                    lease_owner=None,
                    lease_token=None,
                    lease_expires_at=None,
                    finished_at=current,
                    updated_at=current,
                    last_error_code="lease_expired",
                    last_error_message="job lease expired after the final attempt",
                )
            ),
        )
        queued_result = cast(
            CursorResult[Any],
            self.session.execute(
                update(Job)
                .where(expired, Job.attempts < Job.max_attempts)
                .values(
                    status="failed_retryable",
                    lease_owner=None,
                    lease_token=None,
                    lease_expires_at=None,
                    available_at=current,
                    updated_at=current,
                    last_error_code="lease_expired",
                    last_error_message="job lease expired and was reclaimed",
                )
            ),
        )
        return int(terminal_result.rowcount or 0) + int(queued_result.rowcount or 0)

    def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int = 60,
        now: datetime | None = None,
        job_types: Sequence[str] | None = None,
    ) -> Job | None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        current = _aware_utc(now)
        self.reclaim_expired(now=current)
        self.session.execute(
            update(Job)
            .where(
                Job.status.in_(("retry_wait", "failed_retryable")),
                Job.available_at <= current,
                Job.attempts < Job.max_attempts,
            )
            .values(status="queued", updated_at=current)
        )
        eligible = and_(
            Job.status == "queued",
            Job.available_at <= current,
            Job.attempts < Job.max_attempts,
        )
        candidate = select(Job.id).where(eligible)
        if job_types:
            candidate = candidate.where(Job.job_type.in_(tuple(job_types)))
        candidate = candidate.order_by(Job.priority.desc(), Job.available_at, Job.created_at, Job.id).limit(1)

        statement = (
            update(Job)
            .where(Job.id == candidate.scalar_subquery(), eligible)
            .values(
                status="claimed",
                lease_owner=worker_id,
                lease_token=new_uuid(),
                lease_expires_at=current + timedelta(seconds=lease_seconds),
                attempts=Job.attempts + 1,
                started_at=None,
                finished_at=None,
                updated_at=current,
            )
            .returning(Job)
            .execution_options(synchronize_session="fetch")
        )
        return self.session.execute(statement).scalar_one_or_none()

    def start(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        now: datetime | None = None,
    ) -> Job:
        current = _aware_utc(now)
        return self._owned_update(
            job_id,
            worker_id,
            lease_token,
            allowed_statuses=("claimed",),
            values={"status": "running", "started_at": current, "updated_at": current},
            lease_valid_at=current,
        )

    def renew_lease(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> Job:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        current = _aware_utc(now)
        return self._owned_update(
            job_id,
            worker_id,
            lease_token,
            allowed_statuses=("running",),
            values={
                "lease_expires_at": current + timedelta(seconds=lease_seconds),
                "updated_at": current,
            },
            lease_valid_at=current,
        )

    def complete(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        now: datetime | None = None,
    ) -> Job:
        current = _aware_utc(now)
        return self._owned_update(
            job_id,
            worker_id,
            lease_token,
            allowed_statuses=("running",),
            values={
                "status": "succeeded",
                "lease_owner": None,
                "lease_token": None,
                "lease_expires_at": None,
                "finished_at": current,
                "updated_at": current,
                "last_error_code": None,
                "last_error_message": None,
            },
            lease_valid_at=current,
        )

    def fail(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        retryable: bool,
        error_code: str,
        error_message: str,
        retry_at: datetime | None = None,
        now: datetime | None = None,
    ) -> Job:
        current = _aware_utc(now)
        retry_status = "retry_wait" if retry_at is not None and _aware_utc(retry_at) > current else "failed_retryable"
        attempts_remain = Job.attempts < Job.max_attempts
        status: Any = case((attempts_remain, retry_status), else_="failed_terminal") if retryable else "failed_terminal"
        available_at: Any = (
            case(
                (attempts_remain, _aware_utc(retry_at)),
                else_=Job.available_at,
            )
            if retryable
            else Job.available_at
        )
        finished_at: Any = case((attempts_remain, None), else_=current) if retryable else current
        values: dict[str, Any] = {
            "status": status,
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "last_error_code": error_code,
            "last_error_message": _safe_text(error_message),
            "updated_at": current,
            "available_at": available_at,
            "finished_at": finished_at,
        }
        return self._owned_update(
            job_id,
            worker_id,
            lease_token,
            allowed_statuses=("claimed", "running"),
            values=values,
            lease_valid_at=current,
        )

    def cancel(self, job_id: str, *, now: datetime | None = None) -> Job:
        current = _aware_utc(now)
        statement = (
            update(Job)
            .where(Job.id == job_id, Job.status.not_in(TERMINAL_JOB_STATUSES))
            .values(
                status="cancelled",
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                finished_at=current,
                updated_at=current,
            )
            .returning(Job)
            .execution_options(synchronize_session="fetch")
        )
        job = self.session.execute(statement).scalar_one_or_none()
        if job is None:
            existing = self.get(job_id)
            if existing is None:
                raise NotFoundError(f"job not found: {job_id}")
            return existing
        return job

    def _owned_update(
        self,
        job_id: str,
        worker_id: str,
        lease_token: str,
        *,
        allowed_statuses: Sequence[str],
        values: Mapping[str, Any],
        lease_valid_at: datetime,
    ) -> Job:
        statement = (
            update(Job)
            .where(
                Job.id == job_id,
                Job.lease_owner == worker_id,
                Job.lease_token == lease_token,
                Job.status.in_(tuple(allowed_statuses)),
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at > lease_valid_at,
            )
            .values(**dict(values))
            .returning(Job)
            .execution_options(synchronize_session="fetch")
        )
        job = self.session.execute(statement).scalar_one_or_none()
        if job is not None:
            return job
        if self.get(job_id) is None:
            raise NotFoundError(f"job not found: {job_id}")
        raise LeaseLostError(f"worker {worker_id!r} no longer owns job {job_id}")


class ExportRecordRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, export_record_id: str) -> ExportRecord | None:
        return self.session.get(ExportRecord, export_record_id)

    def record(
        self,
        *,
        content_id: str,
        exporter: str,
        exporter_version: str,
        source_fingerprint: str,
        output_path: str,
        status: str = "pending",
    ) -> ExportRecord:
        if self.session.get_bind().dialect.name == "sqlite":
            now = utc_now()
            statement = (
                sqlite_insert(ExportRecord)
                .values(
                    id=new_uuid(),
                    content_id=content_id,
                    exporter=exporter,
                    exporter_version=exporter_version,
                    source_fingerprint=source_fingerprint,
                    output_path=output_path,
                    status=status,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        ExportRecord.content_id,
                        ExportRecord.exporter,
                        ExportRecord.exporter_version,
                        ExportRecord.source_fingerprint,
                    ]
                )
                .returning(ExportRecord)
            )
            created = self.session.scalars(statement).one_or_none()
            if created is not None:
                return created

        existing = self.session.scalar(
            select(ExportRecord).where(
                ExportRecord.content_id == content_id,
                ExportRecord.exporter == exporter,
                ExportRecord.exporter_version == exporter_version,
                ExportRecord.source_fingerprint == source_fingerprint,
            )
        )
        if existing is not None:
            return existing
        record = ExportRecord(
            content_id=content_id,
            exporter=exporter,
            exporter_version=exporter_version,
            source_fingerprint=source_fingerprint,
            output_path=output_path,
            status=status,
        )
        self.session.add(record)
        self.session.flush()
        return record


__all__ = [
    "AccountRepository",
    "AssetRepository",
    "AssetUpsert",
    "AuthorRepository",
    "AuthorUpsert",
    "ContentUpsert",
    "ExportRecordRepository",
    "JobRepository",
    "LeaseLostError",
    "LoginSessionRepository",
    "NotFoundError",
    "RepositoryError",
    "SubscriptionRepository",
    "SyncRunRepository",
]
