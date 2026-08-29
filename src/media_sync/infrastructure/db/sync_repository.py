"""SQLAlchemy implementation of the application synchronization port.

The adapter is intentionally transaction-scoped: it flushes through the
lower-level repositories but never commits.  A caller can therefore execute a
complete :class:`~media_sync.application.sync.SyncService` run inside one
``Database.session()`` boundary and decide whether the complete run commits.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from media_sync.domain import (
    AssetSnapshot,
    AuthorSnapshot,
    ContentSnapshot,
    Cursor,
    RunStatus,
    transition_run,
)

from .base import utc_now
from .models import SyncRun
from .repositories import (
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    NotFoundError,
    RepositoryError,
    SubscriptionRepository,
    SyncRunRepository,
)


def _database_id(value: UUID) -> str:
    """Convert a domain UUID to the portable string representation in SQL."""

    return str(value)


def _domain_id(value: str | UUID, *, entity: str) -> UUID:
    """Convert and validate an identifier returned by persistence."""

    if isinstance(value, UUID):
        return value
    try:
        return UUID(value)
    except (AttributeError, ValueError) as error:  # pragma: no cover - corrupt database defense
        raise RepositoryError(f"{entity} has a malformed UUID identifier") from error


def _author_upsert(snapshot: AuthorSnapshot) -> AuthorUpsert:
    return AuthorUpsert(
        platform=snapshot.platform.value,
        remote_id=snapshot.remote_id,
        display_name=snapshot.display_name,
        handle=snapshot.handle,
        profile_url=snapshot.profile_url,
        avatar_url=snapshot.avatar_url,
        raw=snapshot.raw,
    )


def _content_upsert(snapshot: ContentSnapshot) -> ContentUpsert:
    return ContentUpsert(
        remote_id=snapshot.remote_id,
        kind=snapshot.kind.value,
        remote_type=snapshot.remote_type,
        title=snapshot.title,
        body=snapshot.body,
        canonical_url=snapshot.canonical_url,
        published_at=snapshot.published_at,
        metrics=snapshot.metrics,
        raw=snapshot.raw,
    )


def _asset_upsert(snapshot: AssetSnapshot) -> AssetUpsert:
    return AssetUpsert(
        platform=snapshot.platform.value,
        remote_id=snapshot.remote_id,
        kind=snapshot.kind.value,
        position=snapshot.position,
        source_url=snapshot.source_url,
        mime_type=snapshot.mime_type,
        size_bytes=snapshot.size_bytes,
        checksum_sha256=snapshot.checksum_sha256,
        raw=snapshot.raw,
    )


def _cursor_payload(cursor: Cursor | None) -> dict[str, str] | None:
    return None if cursor is None else {"value": cursor.value}


class SQLAlchemySyncRepository:
    """Map immutable domain snapshots onto normalized SQLAlchemy storage.

    One instance is intended for one session and one synchronization at a
    time.  The small amount of per-run state records IDs at the current
    publish-time boundary; a continuation cursor alone cannot safely identify
    all items that share that timestamp.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self._active_run_id: UUID | None = None
        self._active_subscription_id: UUID | None = None
        self._expected_checkpoint_revision: int | None = None
        self._boundary_at: datetime | None = None
        self._boundary_remote_ids: set[str] = set()
        self._processed_content_keys: set[tuple[str, str, str]] = set()
        self._processed_asset_count = 0

    def upsert_author(self, snapshot: AuthorSnapshot) -> UUID:
        author = AuthorRepository(self.session).upsert(_author_upsert(snapshot))
        return _domain_id(author.id, entity="author")

    def upsert_content_with_assets(
        self,
        snapshot: ContentSnapshot,
        assets: Sequence[AssetSnapshot],
    ) -> UUID:
        for asset in assets:
            if asset.platform is not snapshot.platform or asset.content_remote_id != snapshot.remote_id:
                raise RepositoryError("asset snapshot does not belong to the content snapshot")

        author_repository = AuthorRepository(self.session)
        author = author_repository.get_by_remote(snapshot.platform.value, snapshot.author_remote_id)
        if author is None:
            raise NotFoundError(f"author not found for {snapshot.platform.value}:{snapshot.author_remote_id}")

        # Include content and every asset in one savepoint.  This keeps the
        # Session usable for a classified run transition if a write fails,
        # while the owner still controls rollback of the complete outer run.
        with self.session.begin_nested():
            _persisted_author, contents = author_repository.upsert_with_contents(
                AuthorUpsert(
                    platform=author.platform,
                    remote_id=author.remote_id,
                    display_name=author.display_name,
                    handle=author.handle,
                    profile_url=author.profile_url,
                    avatar_url=author.avatar_url,
                    raw=author.raw,
                ),
                [_content_upsert(snapshot)],
            )
            content = contents[0]
            asset_repository = AssetRepository(self.session)
            for asset in assets:
                asset_repository.upsert_for_content(content.id, _asset_upsert(asset))
            self.session.flush()

        self._observe_watermark_boundary(snapshot)
        content_key = (snapshot.platform.value, snapshot.remote_type, snapshot.remote_id)
        if content_key not in self._processed_content_keys:
            self._processed_content_keys.add(content_key)
            self._processed_asset_count += len(assets)
        return _domain_id(content.id, entity="content")

    def create_run(
        self,
        subscription_id: UUID,
        manifest: Mapping[str, object] | None = None,
    ) -> UUID:
        database_subscription_id = _database_id(subscription_id)
        subscription = SubscriptionRepository(self.session).get(database_subscription_id)
        if subscription is None:
            raise NotFoundError(f"subscription not found: {database_subscription_id}")

        run = SyncRunRepository(self.session).create(
            subscription_id=database_subscription_id,
            cursor_before=subscription.cursor,
            checkpoint_revision_before=subscription.checkpoint_revision,
            manifest=manifest,
        )
        run_id = _domain_id(run.id, entity="sync run")
        self._active_run_id = run_id
        self._active_subscription_id = subscription_id
        self._expected_checkpoint_revision = subscription.checkpoint_revision
        self._boundary_at = None
        self._boundary_remote_ids.clear()
        self._processed_content_keys.clear()
        self._processed_asset_count = 0
        return run_id

    def transition_run(
        self,
        run_id: UUID,
        target: RunStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        database_run_id = _database_id(run_id)
        current_value = self.session.scalar(select(SyncRun.status).where(SyncRun.id == database_run_id))
        if current_value is None:
            raise NotFoundError(f"sync run not found: {database_run_id}")
        current = RunStatus(current_value)

        # Validate here so this adapter cannot bypass the domain even if the
        # lower-level repository implementation changes.  set_status repeats
        # the validation and applies a compare-and-swap using this status.
        transition_run(current, target)
        SyncRunRepository(self.session).set_status(
            database_run_id,
            target.value,
            expected_status=current.value,
            error_code=error_code,
            error_message=error_message,
        )

    def advance_cursor(
        self,
        subscription_id: UUID,
        cursor: Cursor | None,
        *,
        watermark: datetime | None = None,
    ) -> None:
        if self._active_subscription_id is not None and subscription_id != self._active_subscription_id:
            raise RepositoryError("cursor advancement does not belong to the active synchronization run")

        normalized_watermark = watermark.astimezone(UTC) if watermark is not None else None
        boundary_ids: tuple[str, ...] | None = None
        if normalized_watermark is not None and normalized_watermark == self._boundary_at:
            boundary_ids = tuple(sorted(self._boundary_remote_ids))

        payload = _cursor_payload(cursor)
        if self._expected_checkpoint_revision is None:
            raise RepositoryError("cursor advancement requires an active synchronization run")
        expected_revision = self._expected_checkpoint_revision
        published = SubscriptionRepository(self.session).publish_checkpoint(
            _database_id(subscription_id),
            expected_revision=expected_revision,
            cursor=payload,
            cursor_version=1,
            succeeded_at=utc_now(),
            watermarked_at=normalized_watermark,
            watermark_remote_ids=boundary_ids,
        )
        self._expected_checkpoint_revision = published.checkpoint_revision

        if self._active_run_id is not None:
            run_repository = SyncRunRepository(self.session)
            run = run_repository.require(_database_id(self._active_run_id))
            if run.subscription_id != _database_id(subscription_id):
                raise RepositoryError("active synchronization run belongs to a different subscription")
            run_repository.record_checkpoint_publication(
                run.id,
                expected_revision=expected_revision,
                published_revision=published.checkpoint_revision,
                expected_status=RunStatus.INGESTING.value,
            )
            run.cursor_after = payload
            run.discovered_count = len(self._processed_content_keys)
            # The current port does not provide an old/new metadata comparison,
            # so reporting an update count would be guesswork.  Leave it zero
            # until a reliable change detector is part of the contract.
            run.updated_count = 0
            run.asset_count = self._processed_asset_count
            self.session.flush()

    def _observe_watermark_boundary(self, snapshot: ContentSnapshot) -> None:
        if self._active_run_id is None or snapshot.published_at is None:
            return
        published_at = snapshot.published_at.astimezone(UTC)
        if self._boundary_at is None or published_at > self._boundary_at:
            self._boundary_at = published_at
            self._boundary_remote_ids = {snapshot.remote_id}
        elif published_at == self._boundary_at:
            self._boundary_remote_ids.add(snapshot.remote_id)


__all__ = ["SQLAlchemySyncRepository"]
