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
from typing import Any, NoReturn, cast

from sqlalchemy import and_, case, exists, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, joinedload

from media_sync.domain.enums import AssetStatus, AuthStatus, RunStatus
from media_sync.domain.transitions import transition_asset, transition_auth, transition_run
from media_sync.media.errors import MediaDownloadError
from media_sync.media.locator import AdapterRefreshLocator, DirectLocator, parse_locator
from media_sync.security import SecretReference, redact_mapping, redact_text

from .asset_identity import AssetFingerprints, asset_fingerprints, asset_source_hint, stable_asset_key
from .base import new_uuid, utc_now
from .models import (
    ASSET_STATUSES,
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


class AssetConflictError(RepositoryError):
    """An asset generation or lifecycle compare-and-swap did not match."""

    def __init__(self, asset_id: str, expected_generation: int, expected_status: str) -> None:
        self.asset_id = asset_id
        self.expected_generation = expected_generation
        self.expected_status = expected_status
        super().__init__(
            f"asset {asset_id} lifecycle changed: expected generation {expected_generation} in status {expected_status}"
        )


class AssetLeaseLostError(LeaseLostError):
    """An asset mutation was attempted without the active download job lease."""


class ExportRecordConflictError(RepositoryError):
    """An export record changed since its caller observed the lifecycle state."""

    def __init__(self, export_record_id: str, expected_status: str) -> None:
        self.export_record_id = export_record_id
        self.expected_status = expected_status
        super().__init__(f"export record {export_record_id} lifecycle changed: expected status {expected_status}")


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
    content_remote_type: str | None = None
    content_remote_id: str | None = None
    remote_id: str | None = None
    source_url: str | None = field(default=None, repr=False)
    locator: Mapping[str, Any] = field(default_factory=dict, repr=False)
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
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
    """Discovery metadata and fenced downloader-owned lifecycle mutations."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, asset_id: str) -> Asset | None:
        return self.session.get(Asset, asset_id)

    def require(self, asset_id: str) -> Asset:
        asset = self.get(asset_id)
        if asset is None:
            raise NotFoundError(f"asset not found: {asset_id}")
        return asset

    def _prepare_discovery(
        self,
        content_id: str,
        value: AssetUpsert,
    ) -> tuple[dict[str, Any], AssetFingerprints]:
        if (value.content_remote_type is None) != (value.content_remote_id is None):
            raise ValueError("content remote type and ID must be provided together")
        if value.content_remote_type is None or value.content_remote_id is None:
            content = self.session.get(Content, content_id)
            if content is None:
                raise NotFoundError(f"content not found: {content_id}")
            if content.platform != value.platform:
                raise RepositoryError("asset and content platforms do not match")
            content_remote_type = content.remote_type
            content_remote_id = content.remote_id
        else:
            content_remote_type = value.content_remote_type
            content_remote_id = value.content_remote_id

        safe_source_url = asset_source_hint(value.source_url)
        safe_source_url = _safe_text(safe_source_url)
        locator = _json(value.locator)
        if not locator:
            try:
                if value.source_url is None:
                    raise MediaDownloadError("locator_invalid")
                locator = DirectLocator(value.source_url).as_dict()
            except MediaDownloadError:
                locator = AdapterRefreshLocator(
                    adapter="database",
                    asset_key=stable_asset_key(
                        platform=value.platform,
                        content_remote_type=content_remote_type,
                        content_remote_id=content_remote_id,
                        kind=value.kind,
                        position=value.position,
                        remote_id=value.remote_id,
                    ),
                ).as_dict()
        try:
            locator = parse_locator(locator).as_dict()
        except MediaDownloadError as error:
            raise RepositoryError("asset locator is invalid") from error
        fingerprints = asset_fingerprints(
            platform=value.platform,
            content_remote_type=content_remote_type,
            content_remote_id=content_remote_id,
            kind=value.kind,
            position=value.position,
            remote_id=value.remote_id,
            source_url=safe_source_url,
            locator=locator,
            width=value.width,
            height=value.height,
            duration_ms=value.duration_ms,
        )
        discovery_values: dict[str, Any] = {
            "platform": value.platform,
            "remote_id": value.remote_id,
            "source_url": safe_source_url,
            "locator": locator,
            "semantic_fingerprint": fingerprints.semantic,
            "locator_fingerprint": fingerprints.locator,
            "width": value.width,
            "height": value.height,
            "duration_ms": value.duration_ms,
            "raw": _json(value.raw),
        }
        return discovery_values, fingerprints

    def upsert_for_content(self, content_id: str, value: AssetUpsert) -> Asset:
        """Upsert discovery-owned fields without downgrading the same bytes.

        The stable ``(content, kind, position)`` slot retains downloader-owned
        fields when remote ID and semantic fingerprint match.  A replacement
        increments ``generation`` and clears those fields in the same CAS.
        """

        now = utc_now()
        values, fingerprints = self._prepare_discovery(content_id, value)
        if self.session.get_bind().dialect.name == "sqlite":
            insert_statement = (
                sqlite_insert(Asset)
                .values(
                    id=new_uuid(),
                    content_id=content_id,
                    kind=value.kind,
                    position=value.position,
                    generation=1,
                    status=AssetStatus.DISCOVERED.value,
                    created_at=now,
                    updated_at=now,
                    **values,
                )
                .on_conflict_do_nothing(index_elements=[Asset.content_id, Asset.kind, Asset.position])
                .returning(Asset)
                .execution_options(populate_existing=True)
            )
            created = self.session.scalars(insert_statement).one_or_none()
            if created is not None:
                return created

        last_observed: tuple[str, int, str] | None = None
        for _attempt in range(5):
            asset = self.session.scalar(
                select(Asset)
                .where(
                    Asset.content_id == content_id,
                    Asset.kind == value.kind,
                    Asset.position == value.position,
                )
                .execution_options(populate_existing=True)
            )
            if asset is None:
                asset = Asset(
                    content_id=content_id,
                    kind=value.kind,
                    position=value.position,
                    generation=1,
                    status=AssetStatus.DISCOVERED.value,
                    **values,
                )
                self.session.add(asset)
                self.session.flush()
                return asset

            expected_generation = asset.generation
            expected_status = asset.status
            last_observed = asset.id, expected_generation, expected_status
            if asset.remote_id == value.remote_id and asset.semantic_fingerprint == fingerprints.semantic:
                update_statement = (
                    update(Asset)
                    .where(
                        Asset.id == asset.id,
                        Asset.generation == expected_generation,
                        Asset.semantic_fingerprint == asset.semantic_fingerprint,
                    )
                    .values(**values, updated_at=now)
                    .returning(Asset)
                    .execution_options(synchronize_session="fetch", populate_existing=True)
                )
                updated = self.session.execute(update_statement).scalar_one_or_none()
                if updated is not None:
                    return updated
                continue

            try:
                return self._reset_prepared(
                    asset.id,
                    expected_generation=expected_generation,
                    expected_status=expected_status,
                    values=values,
                    at=now,
                )
            except AssetConflictError:
                continue

        if last_observed is None:  # pragma: no cover - every loop either inserts or observes
            raise RepositoryError("asset discovery could not observe its conflicting row")
        raise AssetConflictError(*last_observed)

    def queue(
        self,
        asset_id: str,
        *,
        expected_generation: int,
        expected_status: str,
        at: datetime | None = None,
    ) -> Asset:
        """Queue one asset only if its generation and status still match."""

        self._validate_asset_cas(expected_generation, expected_status)
        transition_asset(AssetStatus(expected_status), AssetStatus.QUEUED)
        current = _aware_utc(at)
        return self._cas_update(
            asset_id,
            expected_generation=expected_generation,
            expected_status=expected_status,
            values={
                "status": AssetStatus.QUEUED.value,
                "download_job_id": None,
                "queued_at": current,
                "download_started_at": None,
                "last_error_code": None,
                "last_error_message": None,
                "last_error_at": None,
                "updated_at": current,
            },
        )

    def start(
        self,
        asset_id: str,
        *,
        expected_generation: int,
        expected_status: str,
        job_id: str,
        worker_id: str,
        lease_token: str,
        at: datetime | None = None,
    ) -> Asset:
        """Start downloading under the currently owned, unexpired job lease."""

        self._validate_asset_cas(expected_generation, expected_status)
        transition_asset(AssetStatus(expected_status), AssetStatus.DOWNLOADING)
        current = _aware_utc(at)
        return self._owned_cas_update(
            asset_id,
            expected_generation=expected_generation,
            expected_status=expected_status,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            allowed_job_statuses=("claimed", "running"),
            at=current,
            values={
                "status": AssetStatus.DOWNLOADING.value,
                "download_job_id": job_id,
                "download_started_at": current,
                "downloaded_at": None,
                "verified_at": None,
                "mime_type": None,
                "size_bytes": None,
                "checksum_sha256": None,
                "local_path": None,
                "etag": None,
                "last_modified": None,
                "last_error_code": None,
                "last_error_message": None,
                "last_error_at": None,
                "updated_at": current,
            },
        )

    def fail(
        self,
        asset_id: str,
        *,
        expected_generation: int,
        expected_status: str,
        job_id: str,
        worker_id: str,
        lease_token: str,
        retryable: bool,
        error_code: str,
        error_message: str,
        at: datetime | None = None,
    ) -> Asset:
        """Record a bounded failure while the caller still owns the job."""

        self._validate_asset_cas(expected_generation, expected_status)
        if expected_status != AssetStatus.DOWNLOADING.value:
            raise ValueError("asset failure requires downloading status")
        target = AssetStatus.FAILED_RETRYABLE if retryable else AssetStatus.FAILED_TERMINAL
        transition_asset(AssetStatus(expected_status), target)
        current = _aware_utc(at)
        code = self._bounded_text(error_code, field_name="error_code", max_length=128)
        message = self._bounded_text(error_message, field_name="error_message", max_length=2_000)
        return self._owned_cas_update(
            asset_id,
            expected_generation=expected_generation,
            expected_status=expected_status,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            allowed_job_statuses=("claimed", "running"),
            at=current,
            extra_asset_condition=Asset.download_job_id == job_id,
            values={
                "status": target.value,
                "last_error_code": code,
                "last_error_message": _safe_text(message),
                "last_error_at": current,
                "updated_at": current,
            },
        )

    def verify(
        self,
        asset_id: str,
        *,
        expected_generation: int,
        expected_status: str,
        job_id: str,
        worker_id: str,
        lease_token: str,
        mime_type: str,
        size_bytes: int,
        checksum_sha256: str,
        local_path: str,
        etag: str | None = None,
        last_modified: str | None = None,
        at: datetime | None = None,
    ) -> Asset:
        """Atomically publish verified local bytes under an active job lease."""

        self._validate_asset_cas(expected_generation, expected_status)
        current_status = AssetStatus(expected_status)
        if current_status is AssetStatus.DOWNLOADING:
            transition_asset(current_status, AssetStatus.DOWNLOADED)
            transition_asset(AssetStatus.DOWNLOADED, AssetStatus.VERIFIED)
        elif current_status is AssetStatus.DOWNLOADED:
            transition_asset(current_status, AssetStatus.VERIFIED)
        else:
            raise ValueError("asset verification requires downloading or downloaded status")
        if size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        checksum = checksum_sha256.strip().lower()
        if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
            raise ValueError("checksum_sha256 must contain 64 hexadecimal characters")
        actual_mime = self._bounded_text(mime_type, field_name="mime_type", max_length=255)
        actual_path = self._bounded_text(local_path, field_name="local_path", max_length=4_096)
        safe_etag = self._optional_validator(etag, field_name="etag", max_length=512)
        if safe_etag is not None and safe_etag.startswith("W/"):
            raise ValueError("etag must be a strong validator")
        safe_last_modified = self._optional_validator(
            last_modified,
            field_name="last_modified",
            max_length=255,
        )
        current = _aware_utc(at)
        return self._owned_cas_update(
            asset_id,
            expected_generation=expected_generation,
            expected_status=expected_status,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            allowed_job_statuses=("running",),
            at=current,
            extra_asset_condition=Asset.download_job_id == job_id,
            values={
                "status": AssetStatus.VERIFIED.value,
                "mime_type": actual_mime,
                "size_bytes": size_bytes,
                "checksum_sha256": checksum,
                "local_path": _safe_text(actual_path),
                "etag": _safe_text(safe_etag) if safe_etag is not None else None,
                "last_modified": _safe_text(safe_last_modified) if safe_last_modified is not None else None,
                "downloaded_at": current,
                "verified_at": current,
                "last_error_code": None,
                "last_error_message": None,
                "last_error_at": None,
                "updated_at": current,
            },
        )

    def reset_verified_archive(
        self,
        asset_id: str,
        *,
        expected_generation: int,
        expected_local_path: str,
        expected_checksum_sha256: str,
        expected_size_bytes: int,
        error_code: str,
        error_message: str,
        at: datetime | None = None,
    ) -> Asset:
        """Fence a missing or corrupt verified blob into a fresh generation."""

        if expected_generation < 1 or expected_size_bytes < 0:
            raise ValueError("verified archive reset expectations are invalid")
        code = self._bounded_text(error_code, field_name="error_code", max_length=128)
        message = self._bounded_text(error_message, field_name="error_message", max_length=2_000)
        current = _aware_utc(at)
        statement = (
            update(Asset)
            .where(
                Asset.id == asset_id,
                Asset.generation == expected_generation,
                Asset.status == AssetStatus.VERIFIED.value,
                Asset.local_path == expected_local_path,
                Asset.checksum_sha256 == expected_checksum_sha256,
                Asset.size_bytes == expected_size_bytes,
            )
            .values(
                generation=Asset.generation + 1,
                status=AssetStatus.DISCOVERED.value,
                mime_type=None,
                size_bytes=None,
                checksum_sha256=None,
                local_path=None,
                download_job_id=None,
                etag=None,
                last_modified=None,
                queued_at=None,
                download_started_at=None,
                downloaded_at=None,
                verified_at=None,
                last_error_code=code,
                last_error_message=_safe_text(message),
                last_error_at=current,
                updated_at=current,
            )
            .returning(Asset)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        reset = self.session.execute(statement).scalar_one_or_none()
        if reset is not None:
            return reset
        existing = self.get(asset_id)
        if existing is None:
            raise NotFoundError(f"asset not found: {asset_id}")
        raise AssetConflictError(asset_id, expected_generation, AssetStatus.VERIFIED.value)

    def recover_expired_download(
        self,
        asset_id: str,
        *,
        expected_generation: int,
        expected_status: str,
        job_id: str,
        at: datetime | None = None,
    ) -> Asset:
        """Mirror a reclaimed job failure onto its still-downloading asset.

        This recovery never changes generation or locator identity, so a
        generation-bound ``.part`` file remains eligible for the next attempt.
        """

        self._validate_asset_cas(expected_generation, expected_status)
        if expected_status != AssetStatus.DOWNLOADING.value:
            raise ValueError("expired download recovery requires downloading status")
        current = _aware_utc(at)
        for job_status, target in (
            ("failed_retryable", AssetStatus.FAILED_RETRYABLE),
            ("failed_terminal", AssetStatus.FAILED_TERMINAL),
        ):
            statement = (
                update(Asset)
                .where(
                    Asset.id == asset_id,
                    Asset.generation == expected_generation,
                    Asset.status == expected_status,
                    Asset.download_job_id == job_id,
                    exists(
                        select(Job.id).where(
                            Job.id == job_id,
                            Job.status == job_status,
                            Job.lease_owner.is_(None),
                            Job.lease_token.is_(None),
                            Job.lease_expires_at.is_(None),
                        )
                    ),
                )
                .values(
                    status=target.value,
                    last_error_code="download_lease_expired",
                    last_error_message="download job lease expired",
                    last_error_at=current,
                    updated_at=current,
                )
                .returning(Asset)
                .execution_options(synchronize_session="fetch", populate_existing=True)
            )
            recovered = self.session.execute(statement).scalar_one_or_none()
            if recovered is not None:
                return recovered

        existing = self.session.scalar(
            select(Asset).where(Asset.id == asset_id).execution_options(populate_existing=True)
        )
        if existing is None:
            raise NotFoundError(f"asset not found: {asset_id}")
        if existing.generation != expected_generation or existing.status != expected_status:
            raise AssetConflictError(asset_id, expected_generation, expected_status)
        raise AssetLeaseLostError(f"download job is not reclaimable for asset {asset_id}")

    def resume_reclaimed_prepared_result(
        self,
        asset_id: str,
        *,
        expected_generation: int,
        expected_status: str,
        job_id: str,
        worker_id: str,
        lease_token: str,
        at: datetime | None = None,
    ) -> Asset:
        """Resume an exact lease-expired asset only to commit proven local bytes."""

        if expected_status not in {
            AssetStatus.FAILED_RETRYABLE.value,
            AssetStatus.FAILED_TERMINAL.value,
        }:
            raise ValueError("prepared-result recovery requires a reclaimed asset status")
        self._validate_asset_cas(expected_generation, expected_status)
        current = _aware_utc(at)
        return self._owned_cas_update(
            asset_id,
            expected_generation=expected_generation,
            expected_status=expected_status,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            allowed_job_statuses=("running",),
            at=current,
            extra_asset_condition=and_(
                Asset.download_job_id == job_id,
                Asset.last_error_code == "download_lease_expired",
            ),
            values={
                "status": AssetStatus.DOWNLOADING.value,
                "last_error_code": None,
                "last_error_message": None,
                "last_error_at": None,
                "updated_at": current,
            },
        )

    def resume_terminal_prepared_result(
        self,
        asset_id: str,
        *,
        expected_generation: int,
        job_id: str,
        worker_id: str,
        lease_token: str,
        at: datetime | None = None,
    ) -> Asset:
        """Backward-compatible terminal-only prepared-result recovery."""

        return self.resume_reclaimed_prepared_result(
            asset_id,
            expected_generation=expected_generation,
            expected_status=AssetStatus.FAILED_TERMINAL.value,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            at=at,
        )

    def reset(
        self,
        asset_id: str,
        *,
        expected_generation: int,
        expected_status: str,
        value: AssetUpsert,
        at: datetime | None = None,
    ) -> Asset:
        """Explicitly begin a new generation and clear downloader-owned data."""

        self._validate_asset_cas(expected_generation, expected_status)
        asset = self.require(asset_id)
        if asset.kind != value.kind or asset.position != value.position:
            raise RepositoryError("asset reset cannot change its stable kind/position slot")
        values, _fingerprints = self._prepare_discovery(asset.content_id, value)
        return self._reset_prepared(
            asset_id,
            expected_generation=expected_generation,
            expected_status=expected_status,
            values=values,
            at=_aware_utc(at),
        )

    def _reset_prepared(
        self,
        asset_id: str,
        *,
        expected_generation: int,
        expected_status: str,
        values: Mapping[str, Any],
        at: datetime,
    ) -> Asset:
        return self._cas_update(
            asset_id,
            expected_generation=expected_generation,
            expected_status=expected_status,
            values={
                **dict(values),
                "generation": Asset.generation + 1,
                "status": AssetStatus.DISCOVERED.value,
                "mime_type": None,
                "size_bytes": None,
                "checksum_sha256": None,
                "local_path": None,
                "download_job_id": None,
                "etag": None,
                "last_modified": None,
                "queued_at": None,
                "download_started_at": None,
                "downloaded_at": None,
                "verified_at": None,
                "last_error_code": None,
                "last_error_message": None,
                "last_error_at": None,
                "updated_at": at,
            },
        )

    def _cas_update(
        self,
        asset_id: str,
        *,
        expected_generation: int,
        expected_status: str,
        values: Mapping[str, Any],
    ) -> Asset:
        statement = (
            update(Asset)
            .where(
                Asset.id == asset_id,
                Asset.generation == expected_generation,
                Asset.status == expected_status,
            )
            .values(**dict(values))
            .returning(Asset)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        asset = self.session.execute(statement).scalar_one_or_none()
        if asset is not None:
            return asset
        self._raise_asset_conflict(asset_id, expected_generation, expected_status)

    def _owned_cas_update(
        self,
        asset_id: str,
        *,
        expected_generation: int,
        expected_status: str,
        job_id: str,
        worker_id: str,
        lease_token: str,
        allowed_job_statuses: Sequence[str],
        at: datetime,
        values: Mapping[str, Any],
        extra_asset_condition: Any | None = None,
    ) -> Asset:
        for field_name, field_value in (
            ("job_id", job_id),
            ("worker_id", worker_id),
            ("lease_token", lease_token),
        ):
            self._bounded_text(field_value, field_name=field_name, max_length=512)
        conditions: list[Any] = [
            Asset.id == asset_id,
            Asset.generation == expected_generation,
            Asset.status == expected_status,
            exists(
                select(Job.id).where(
                    Job.id == job_id,
                    Job.lease_owner == worker_id,
                    Job.lease_token == lease_token,
                    Job.status.in_(tuple(allowed_job_statuses)),
                    Job.lease_expires_at.is_not(None),
                    Job.lease_expires_at > at,
                )
            ),
        ]
        if extra_asset_condition is not None:
            conditions.append(extra_asset_condition)
        statement = (
            update(Asset)
            .where(*conditions)
            .values(**dict(values))
            .returning(Asset)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        asset = self.session.execute(statement).scalar_one_or_none()
        if asset is not None:
            return asset
        existing = self.session.scalar(
            select(Asset).where(Asset.id == asset_id).execution_options(populate_existing=True)
        )
        if existing is None:
            raise NotFoundError(f"asset not found: {asset_id}")
        if existing.generation != expected_generation or existing.status != expected_status:
            raise AssetConflictError(asset_id, expected_generation, expected_status)
        raise AssetLeaseLostError(f"download job no longer owns asset {asset_id}")

    def _raise_asset_conflict(
        self,
        asset_id: str,
        expected_generation: int,
        expected_status: str,
    ) -> NoReturn:
        existing = self.session.scalar(
            select(Asset.id).where(Asset.id == asset_id).execution_options(populate_existing=True)
        )
        if existing is None:
            raise NotFoundError(f"asset not found: {asset_id}")
        raise AssetConflictError(asset_id, expected_generation, expected_status)

    @staticmethod
    def _validate_asset_cas(expected_generation: int, expected_status: str) -> None:
        if expected_generation < 1:
            raise ValueError("expected_generation must be positive")
        _require_status(expected_status, ASSET_STATUSES, "asset")

    @staticmethod
    def _bounded_text(value: str, *, field_name: str, max_length: int) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must not be blank")
        if len(normalized) > max_length:
            raise ValueError(f"{field_name} is too long")
        if "\r" in normalized or "\n" in normalized:
            raise ValueError(f"{field_name} must be a single line")
        return normalized

    @classmethod
    def _optional_validator(cls, value: str | None, *, field_name: str, max_length: int) -> str | None:
        if value is None:
            return None
        return cls._bounded_text(value, field_name=field_name, max_length=max_length)


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

    @staticmethod
    def _normalize_job_types(job_types: Sequence[str] | None) -> tuple[str, ...] | None:
        if job_types is None:
            return None
        if isinstance(job_types, str):
            raise ValueError("job_types must be a non-empty sequence of job type names")
        requested = tuple(job_types)
        if not requested:
            raise ValueError("job_types must not be empty")
        if any(
            not isinstance(job_type, str)
            or not job_type
            or len(job_type) > 128
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in job_type)
            for job_type in requested
        ):
            raise ValueError("job_types contains an invalid job type name")
        return tuple(dict.fromkeys(requested))

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

    def reclaim_expired(
        self,
        *,
        now: datetime | None = None,
        job_id: str | None = None,
        job_types: Sequence[str] | None = None,
    ) -> int:
        normalized_job_types = self._normalize_job_types(job_types)
        current = _aware_utc(now)
        expired_conditions: list[Any] = [
            Job.status.in_(("claimed", "running")),
            Job.lease_expires_at.is_not(None),
            Job.lease_expires_at <= current,
        ]
        if job_id is not None:
            expired_conditions.append(Job.id == job_id)
        if normalized_job_types is not None:
            expired_conditions.append(Job.job_type.in_(normalized_job_types))
        expired = and_(*expired_conditions)
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

    def claim(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> Job | None:
        """Claim exactly one requested job without consuming another queue item."""

        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        current = _aware_utc(now)
        self.reclaim_expired(now=current, job_id=job_id)
        self.session.execute(
            update(Job)
            .where(
                Job.id == job_id,
                Job.status.in_(("retry_wait", "failed_retryable")),
                Job.available_at <= current,
                Job.attempts < Job.max_attempts,
            )
            .values(status="queued", updated_at=current)
        )
        eligible = and_(
            Job.id == job_id,
            Job.status == "queued",
            Job.available_at <= current,
            Job.attempts < Job.max_attempts,
        )
        statement = (
            update(Job)
            .where(eligible)
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
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        claimed = self.session.execute(statement).scalar_one_or_none()
        if claimed is not None:
            return claimed
        if self.get(job_id) is None:
            raise NotFoundError(f"job not found: {job_id}")
        return None

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
        normalized_job_types = self._normalize_job_types(job_types)
        current = _aware_utc(now)
        self.reclaim_expired(now=current, job_types=normalized_job_types)
        retryable_conditions: list[Any] = [
            Job.status.in_(("retry_wait", "failed_retryable")),
            Job.available_at <= current,
            Job.attempts < Job.max_attempts,
        ]
        if normalized_job_types is not None:
            retryable_conditions.append(Job.job_type.in_(normalized_job_types))
        self.session.execute(update(Job).where(*retryable_conditions).values(status="queued", updated_at=current))
        eligible_conditions: list[Any] = [
            Job.status == "queued",
            Job.available_at <= current,
            Job.attempts < Job.max_attempts,
        ]
        if normalized_job_types is not None:
            eligible_conditions.append(Job.job_type.in_(normalized_job_types))
        eligible = and_(*eligible_conditions)
        candidate = select(Job.id).where(eligible)
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
        replacement_payload: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> Job:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        current = _aware_utc(now)
        values: dict[str, Any] = {
            "lease_expires_at": current + timedelta(seconds=lease_seconds),
            "updated_at": current,
        }
        if replacement_payload is not None:
            values["payload"] = _json(replacement_payload)
        return self._owned_update(
            job_id,
            worker_id,
            lease_token,
            allowed_statuses=("running",),
            values=values,
            lease_valid_at=current,
        )

    def renew_unreclaimed_lease(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> Job:
        """Renew an exact running token even after expiry if nobody reclaimed it.

        This compare-and-swap deliberately has no ``lease_expires_at > now``
        predicate.  A concurrent reclaim clears the owner and token, so either
        that reclaim or this renewal wins while a stale/replaced token fails.
        """

        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        current = _aware_utc(now)
        statement = (
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == "running",
                Job.lease_owner == worker_id,
                Job.lease_token == lease_token,
                Job.lease_expires_at.is_not(None),
            )
            .values(
                lease_expires_at=current + timedelta(seconds=lease_seconds),
                updated_at=current,
            )
            .returning(Job)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        job = self.session.execute(statement).scalar_one_or_none()
        if job is not None:
            return job
        if self.get(job_id) is None:
            raise NotFoundError(f"job not found: {job_id}")
        raise LeaseLostError(f"worker {worker_id!r} no longer owns job {job_id}")

    def takeover_expired_running_lease(
        self,
        job_id: str,
        *,
        expected_worker_id: str,
        expected_lease_token: str,
        worker_id: str,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> Job:
        """Replace one exact expired running token without consuming an attempt.

        The application may use this only after proving that the previous
        attempt already prepared and published the immutable local result.
        """

        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        current = _aware_utc(now)
        statement = (
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == "running",
                Job.lease_owner == expected_worker_id,
                Job.lease_token == expected_lease_token,
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at <= current,
            )
            .values(
                lease_owner=worker_id,
                lease_token=new_uuid(),
                lease_expires_at=current + timedelta(seconds=lease_seconds),
                updated_at=current,
            )
            .returning(Job)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        job = self.session.execute(statement).scalar_one_or_none()
        if job is not None:
            return job
        if self.get(job_id) is None:
            raise NotFoundError(f"job not found: {job_id}")
        raise LeaseLostError(f"expired running lease changed for job {job_id}")

    def resume_reclaimed_prepared_result(
        self,
        job_id: str,
        *,
        expected_status: str,
        worker_id: str,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> Job:
        """Resume an exact reclaimed attempt solely to commit its prepared result."""

        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        if expected_status not in {"failed_retryable", "failed_terminal"}:
            raise ValueError("prepared-result recovery requires a reclaimed job status")
        current = _aware_utc(now)
        attempt_state = (
            Job.attempts < Job.max_attempts
            if expected_status == "failed_retryable"
            else Job.attempts >= Job.max_attempts
        )
        statement = (
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == expected_status,
                attempt_state,
                Job.lease_owner.is_(None),
                Job.lease_token.is_(None),
                Job.lease_expires_at.is_(None),
                Job.last_error_code == "lease_expired",
            )
            .values(
                status="running",
                lease_owner=worker_id,
                lease_token=new_uuid(),
                lease_expires_at=current + timedelta(seconds=lease_seconds),
                finished_at=None,
                updated_at=current,
                last_error_code=None,
                last_error_message=None,
            )
            .returning(Job)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        job = self.session.execute(statement).scalar_one_or_none()
        if job is not None:
            return job
        if self.get(job_id) is None:
            raise NotFoundError(f"job not found: {job_id}")
        raise LeaseLostError(f"reclaimed prepared result is no longer resumable for job {job_id}")

    def resume_terminal_prepared_result(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> Job:
        """Backward-compatible terminal-only prepared-result recovery."""

        return self.resume_reclaimed_prepared_result(
            job_id,
            expected_status="failed_terminal",
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            now=now,
        )

    def complete(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        replacement_payload: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> Job:
        current = _aware_utc(now)
        values: dict[str, Any] = {
            "status": "succeeded",
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "finished_at": current,
            "updated_at": current,
            "last_error_code": None,
            "last_error_message": None,
        }
        if replacement_payload is not None:
            values["payload"] = _json(replacement_payload)
        return self._owned_update(
            job_id,
            worker_id,
            lease_token,
            allowed_statuses=("running",),
            values=values,
            lease_valid_at=current,
        )

    def complete_recovered_publication(
        self,
        job_id: str,
        *,
        expected_status: str,
        expected_attempts: int,
        expected_lease_token: str | None,
        replacement_payload: Mapping[str, Any],
        now: datetime | None = None,
    ) -> Job:
        """Finalize an exact expired publication after its durable tree was verified.

        The caller must validate the prepared publication against the filesystem
        before entering this transaction.  This CAS accepts only an already
        reclaimable/failed job generation; a live owner can never be displaced.
        """

        if expected_status not in {
            "queued",
            "claimed",
            "running",
            "retry_wait",
            "failed_retryable",
            "failed_terminal",
        }:
            raise ValueError("unsupported recovered publication job status")
        if expected_attempts < 1:
            raise ValueError("expected_attempts must be positive")
        current = _aware_utc(now)
        ownership_state = or_(
            and_(
                Job.status.in_(("claimed", "running")),
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at <= current,
            ),
            Job.status.in_(("queued", "retry_wait", "failed_retryable", "failed_terminal")),
        )
        statement = (
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == expected_status,
                Job.attempts == expected_attempts,
                Job.lease_token.is_(expected_lease_token)
                if expected_lease_token is None
                else Job.lease_token == expected_lease_token,
                ownership_state,
            )
            .values(
                status="succeeded",
                payload=_json(replacement_payload),
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                finished_at=current,
                updated_at=current,
                last_error_code=None,
                last_error_message=None,
            )
            .returning(Job)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        job = self.session.execute(statement).scalar_one_or_none()
        if job is not None:
            return job
        if self.get(job_id) is None:
            raise NotFoundError(f"job not found: {job_id}")
        raise LeaseLostError(f"publication job is no longer recoverable: {job_id}")

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
        retry_available = current if retry_at is None else _aware_utc(retry_at)
        attempts_remain = Job.attempts < Job.max_attempts
        status: Any = case((attempts_remain, retry_status), else_="failed_terminal") if retryable else "failed_terminal"
        available_at: Any = (
            case(
                (attempts_remain, retry_available),
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
    """Idempotent export identities with a strict compare-and-swap lifecycle."""

    _STATUSES = frozenset({"pending", "running", "succeeded", "failed_retryable", "failed_terminal"})

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, export_record_id: str) -> ExportRecord | None:
        return self.session.get(ExportRecord, export_record_id)

    def get_by_identity(
        self,
        *,
        content_id: str,
        exporter: str,
        exporter_version: str,
        source_fingerprint: str,
    ) -> ExportRecord | None:
        return self.session.scalar(
            select(ExportRecord).where(
                ExportRecord.content_id == content_id,
                ExportRecord.exporter == exporter,
                ExportRecord.exporter_version == exporter_version,
                ExportRecord.source_fingerprint == source_fingerprint,
            )
        )

    def list_for_content(self, content_id: str, *, exporter: str | None = None) -> list[ExportRecord]:
        statement = select(ExportRecord).where(ExportRecord.content_id == content_id)
        if exporter is not None:
            statement = statement.where(ExportRecord.exporter == exporter)
        statement = statement.order_by(ExportRecord.created_at, ExportRecord.id)
        return list(self.session.scalars(statement).all())

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
        self._require_status(status)
        self._require_fingerprint(source_fingerprint, field_name="source_fingerprint")
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

    def begin(
        self,
        *,
        content_id: str,
        exporter: str,
        exporter_version: str,
        source_fingerprint: str,
        output_path: str,
        expected_statuses: Sequence[str] = ("pending", "failed_retryable"),
        at: datetime | None = None,
    ) -> ExportRecord:
        """Create an identity or move one observed retryable state to running.

        A succeeded identity is returned unchanged, which makes an already
        exported author snapshot cheap to detect.  Every other mutation is a
        compare-and-swap against the exact status read in this transaction.
        """

        allowed = tuple(expected_statuses)
        if not allowed:
            raise ValueError("expected export record statuses must not be empty")
        for status in allowed:
            self._require_status(status)
        record = self.record(
            content_id=content_id,
            exporter=exporter,
            exporter_version=exporter_version,
            source_fingerprint=source_fingerprint,
            output_path=output_path,
        )
        if record.status == "succeeded":
            return record
        observed_status = record.status
        if observed_status not in allowed:
            raise ExportRecordConflictError(record.id, "|".join(allowed))
        current = _aware_utc(at)
        statement = (
            update(ExportRecord)
            .where(
                ExportRecord.id == record.id,
                ExportRecord.content_id == content_id,
                ExportRecord.exporter == exporter,
                ExportRecord.exporter_version == exporter_version,
                ExportRecord.source_fingerprint == source_fingerprint,
                ExportRecord.output_path == output_path,
                ExportRecord.status == observed_status,
            )
            .values(
                status="running",
                rendered_fingerprint=None,
                error_message=None,
                exported_at=None,
                updated_at=current,
            )
            .returning(ExportRecord)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        updated_record = self.session.execute(statement).scalar_one_or_none()
        if updated_record is None:
            raise ExportRecordConflictError(record.id, observed_status)
        return updated_record

    def complete(
        self,
        export_record_id: str,
        *,
        expected_source_fingerprint: str,
        expected_output_path: str,
        rendered_fingerprint: str,
        expected_status: str = "running",
        at: datetime | None = None,
    ) -> ExportRecord:
        """Complete exactly one running export identity by CAS."""

        self._require_status(expected_status)
        self._require_fingerprint(expected_source_fingerprint, field_name="source_fingerprint")
        self._require_fingerprint(rendered_fingerprint, field_name="rendered_fingerprint")
        current = _aware_utc(at)
        statement = (
            update(ExportRecord)
            .where(
                ExportRecord.id == export_record_id,
                ExportRecord.source_fingerprint == expected_source_fingerprint,
                ExportRecord.output_path == expected_output_path,
                ExportRecord.status == expected_status,
            )
            .values(
                status="succeeded",
                rendered_fingerprint=rendered_fingerprint,
                error_message=None,
                exported_at=current,
                updated_at=current,
            )
            .returning(ExportRecord)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        record = self.session.execute(statement).scalar_one_or_none()
        if record is not None:
            return record
        if self.get(export_record_id) is None:
            raise NotFoundError(f"export record not found: {export_record_id}")
        raise ExportRecordConflictError(export_record_id, expected_status)

    def fail(
        self,
        export_record_id: str,
        *,
        expected_source_fingerprint: str,
        expected_output_path: str,
        retryable: bool,
        error_code: str,
        expected_status: str = "running",
        at: datetime | None = None,
    ) -> ExportRecord:
        """Classify a running export failure without persisting raw errors."""

        self._require_status(expected_status)
        self._require_fingerprint(expected_source_fingerprint, field_name="source_fingerprint")
        if not 1 <= len(error_code) <= 128 or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in error_code
        ):
            raise ValueError("export error code must use lowercase ASCII letters, digits, or underscores")
        current = _aware_utc(at)
        statement = (
            update(ExportRecord)
            .where(
                ExportRecord.id == export_record_id,
                ExportRecord.source_fingerprint == expected_source_fingerprint,
                ExportRecord.output_path == expected_output_path,
                ExportRecord.status == expected_status,
            )
            .values(
                status="failed_retryable" if retryable else "failed_terminal",
                rendered_fingerprint=None,
                error_message=_safe_text(error_code),
                exported_at=None,
                updated_at=current,
            )
            .returning(ExportRecord)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        record = self.session.execute(statement).scalar_one_or_none()
        if record is not None:
            return record
        if self.get(export_record_id) is None:
            raise NotFoundError(f"export record not found: {export_record_id}")
        raise ExportRecordConflictError(export_record_id, expected_status)

    def _require_status(self, status: str) -> None:
        if status not in self._STATUSES:
            raise ValueError(f"unsupported export record status: {status!r}")

    @staticmethod
    def _require_fingerprint(value: str, *, field_name: str) -> None:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


__all__ = [
    "AccountRepository",
    "AssetConflictError",
    "AssetLeaseLostError",
    "AssetRepository",
    "AssetUpsert",
    "AuthorRepository",
    "AuthorUpsert",
    "ContentUpsert",
    "ExportRecordConflictError",
    "ExportRecordRepository",
    "JobRepository",
    "LeaseLostError",
    "LoginSessionRepository",
    "NotFoundError",
    "RepositoryError",
    "SubscriptionRepository",
    "SyncRunRepository",
]
