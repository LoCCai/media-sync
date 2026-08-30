"""Short-transaction ingestion for already-normalized MediaCrawler output.

File discovery, JSONL reading and normalization intentionally happen before
this service is called.  The input iterable is fully materialized before the
first database session opens, and every bounded batch gets a fresh transaction.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from media_sync.domain import AssetSnapshot, AuthorSnapshot, ContentSnapshot, RunStatus, freeze_mapping
from media_sync.integrations.mediacrawler.normalizers import NormalizedMediaRecord
from media_sync.media.locator import AdapterRefreshLocator

from .asset_identity import stable_asset_key
from .base import utc_now
from .database import Database
from .models import Asset, Content
from .repositories import (
    AssetRefreshSourceRepository,
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    NotFoundError,
    RepositoryError,
    StaleCheckpointError,
    SubscriptionRepository,
    SyncRunRepository,
)

DEFAULT_INGESTION_BATCH_SIZE = 100
MAX_INGESTION_BATCH_SIZE = 1_000
_EXISTING_KEY_QUERY_BATCH_SIZE = 400


class IngestionMode(StrEnum):
    """Which independent subscription checkpoint a crawl advances."""

    FORWARD = "forward"
    BACKFILL = "backfill"


@dataclass(frozen=True, slots=True)
class MediaCrawlerIngestionResult:
    """Secret-free summary of committed normalized ingestion batches."""

    mode: IngestionMode
    input_count: int
    accepted_count: int
    skipped_count: int
    discovered_count: int
    asset_count: int
    committed_batches: int
    checkpoint_revision: int
    watermarked_at: datetime | None
    watermark_remote_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _StartState:
    platform: str
    author_remote_id: str
    watermarked_at: datetime | None
    watermark_remote_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class _ContinuationUnset:
    """Distinguish an unknown continuation from an explicit checkpoint clear."""


_CONTINUATION_UNSET = _ContinuationUnset()


def _database_id(value: str | UUID) -> str:
    return str(value)


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
        remote_type=snapshot.remote_type,
        kind=snapshot.kind.value,
        title=snapshot.title,
        body=snapshot.body,
        canonical_url=snapshot.canonical_url,
        published_at=snapshot.published_at,
        metrics=snapshot.metrics,
        raw=snapshot.raw,
    )


def _asset_upsert(snapshot: AssetSnapshot, *, content_remote_type: str) -> AssetUpsert:
    locator = AdapterRefreshLocator(
        adapter="mediacrawler",
        asset_key=stable_asset_key(
            platform=snapshot.platform.value,
            content_remote_type=content_remote_type,
            content_remote_id=snapshot.content_remote_id,
            kind=snapshot.kind.value,
            position=snapshot.position,
            remote_id=snapshot.remote_id,
        ),
    ).as_dict()
    return AssetUpsert(
        platform=snapshot.platform.value,
        content_remote_type=content_remote_type,
        content_remote_id=snapshot.content_remote_id,
        remote_id=snapshot.remote_id,
        kind=snapshot.kind.value,
        position=snapshot.position,
        source_url=snapshot.source_url,
        locator=locator,
        raw=snapshot.raw,
    )


def _record_key(record: NormalizedMediaRecord) -> tuple[str, str, str]:
    content = record.content
    return content.platform.value, content.remote_type, content.remote_id


def _watermark_id(content: ContentSnapshot) -> str:
    """Keep legacy content IDs stable while namespacing alternate remote types."""

    return content.remote_id if content.remote_type == "content" else f"{content.remote_type}:{content.remote_id}"


def _validate_aggregate(record: NormalizedMediaRecord) -> None:
    author = record.author
    content = record.content
    if content.platform is not author.platform or content.author_remote_id != author.remote_id:
        raise RepositoryError("normalized content does not belong to its author")
    for asset in record.assets:
        if asset.platform is not content.platform or asset.content_remote_id != content.remote_id:
            raise RepositoryError("normalized asset does not belong to its content")


def _deduplicate(records: Sequence[NormalizedMediaRecord]) -> tuple[NormalizedMediaRecord, ...]:
    # Dict assignment keeps the first position while the last replayed value
    # wins, so duplicate output cannot inflate a batch or retain stale metadata.
    unique: dict[tuple[str, str, str], NormalizedMediaRecord] = {}
    for record in records:
        _validate_aggregate(record)
        unique[_record_key(record)] = record
    return tuple(unique.values())


def _accept_forward(record: NormalizedMediaRecord, state: _StartState) -> bool:
    published_at = record.content.published_at
    if published_at is None or state.watermarked_at is None:
        return True
    normalized = published_at.astimezone(UTC)
    if normalized < state.watermarked_at:
        return False
    if normalized == state.watermarked_at:
        return _watermark_id(record.content) not in state.watermark_remote_ids
    return True


def _watermark_boundary(records: Sequence[NormalizedMediaRecord]) -> tuple[datetime | None, tuple[str, ...]]:
    boundary_at: datetime | None = None
    boundary_ids: set[str] = set()
    for record in records:
        published_at = record.content.published_at
        if published_at is None:
            continue
        normalized = published_at.astimezone(UTC)
        watermark_id = _watermark_id(record.content)
        if boundary_at is None or normalized > boundary_at:
            boundary_at = normalized
            boundary_ids = {watermark_id}
        elif normalized == boundary_at:
            boundary_ids.add(watermark_id)
    return boundary_at, tuple(sorted(boundary_ids))


def _forward_batch_key(record: NormalizedMediaRecord) -> tuple[bool, datetime, str]:
    """Order forward batches oldest-first so every partial watermark is resumable."""

    published_at = record.content.published_at
    normalized = published_at.astimezone(UTC) if published_at is not None else datetime.min.replace(tzinfo=UTC)
    return published_at is not None, normalized, _watermark_id(record.content)


def _partition(
    records: Sequence[NormalizedMediaRecord],
    batch_size: int,
) -> tuple[tuple[NormalizedMediaRecord, ...], ...]:
    if not records:
        return ((),)
    return tuple(tuple(records[index : index + batch_size]) for index in range(0, len(records), batch_size))


def _upsert_batch(session: Session, records: Sequence[NormalizedMediaRecord]) -> tuple[int, int]:
    discovered_count = 0
    asset_count = 0
    author_repository = AuthorRepository(session)
    asset_repository = AssetRepository(session)

    for record in records:
        content_snapshot = record.content
        existing_content_id = session.scalar(
            select(Content.id).where(
                Content.platform == content_snapshot.platform.value,
                Content.remote_type == content_snapshot.remote_type,
                Content.remote_id == content_snapshot.remote_id,
            )
        )
        _author, contents = author_repository.upsert_with_contents(
            _author_upsert(record.author),
            [_content_upsert(content_snapshot)],
        )
        content = contents[0]
        if existing_content_id is None:
            discovered_count += 1

        existing_asset_keys = {
            (kind, position)
            for kind, position in session.execute(
                select(Asset.kind, Asset.position).where(Asset.content_id == content.id)
            )
        }
        for asset in record.assets:
            asset_key = (asset.kind.value, asset.position)
            if asset_key not in existing_asset_keys:
                asset_count += 1
                existing_asset_keys.add(asset_key)
            asset_repository.upsert_for_content(
                content.id,
                _asset_upsert(asset, content_remote_type=content_snapshot.remote_type),
            )

    return discovered_count, asset_count


def _record_refresh_observations(
    session: Session,
    records: Sequence[NormalizedMediaRecord],
    *,
    subscription_id: str,
    run_id: str,
) -> None:
    """Bind every authoritative batch Asset to its exact observing run.

    This deliberately runs after discovery upserts but before checkpoint
    publication in the same caller-owned transaction.  The provenance
    repository revalidates the full Asset/Content/Author/Subscription/Account
    chain and the run relationship, so any mismatch rolls the whole batch
    back instead of leaving either discovery or checkpoint state unbound.
    """

    repository = AssetRefreshSourceRepository(session)
    for record in records:
        content = record.content
        for asset_snapshot in record.assets:
            asset = session.scalar(
                select(Asset)
                .join(Content, Content.id == Asset.content_id)
                .where(
                    Content.platform == content.platform.value,
                    Content.remote_type == content.remote_type,
                    Content.remote_id == content.remote_id,
                    Asset.kind == asset_snapshot.kind.value,
                    Asset.position == asset_snapshot.position,
                )
                .execution_options(populate_existing=True)
            )
            if asset is None:  # pragma: no cover - guarded by the preceding upsert
                raise RepositoryError("ingested asset observation target is missing")
            repository.upsert_observation(
                asset_id=asset.id,
                subscription_id=subscription_id,
                last_run_id=run_id,
            )


class MediaCrawlerIngestionService:
    """Commit normalized MediaCrawler records in independently fenced batches."""

    def __init__(self, database: Database, *, batch_size: int = DEFAULT_INGESTION_BATCH_SIZE) -> None:
        if isinstance(batch_size, bool) or not 1 <= batch_size <= MAX_INGESTION_BATCH_SIZE:
            raise ValueError(f"batch_size must be between 1 and {MAX_INGESTION_BATCH_SIZE}")
        self.database = database
        self.batch_size = batch_size

    def ingest(
        self,
        records: Iterable[NormalizedMediaRecord],
        *,
        subscription_id: str | UUID,
        run_id: str | UUID,
        expected_revision: int,
        crawl_revision_before: int | None = None,
        mode: IngestionMode | str,
        continuation: Mapping[str, object] | _ContinuationUnset | None = _CONTINUATION_UNSET,
        ownership_guard: Callable[[Session], None] | None = None,
    ) -> MediaCrawlerIngestionResult:
        """Materialize outside SQLite, then atomically ingest and fence each batch."""

        if expected_revision < 0:
            raise ValueError("expected_revision must be nonnegative")
        origin_revision = expected_revision if crawl_revision_before is None else crawl_revision_before
        if origin_revision < 0 or origin_revision > expected_revision:
            raise ValueError("crawl_revision_before must be between zero and expected_revision")
        try:
            normalized_mode = IngestionMode(mode)
        except ValueError as error:
            raise ValueError("mode must be 'forward' or 'backfill'") from error
        if origin_revision < expected_revision and not isinstance(continuation, _ContinuationUnset):
            raise ValueError("continuation must be omitted when recovering a prior crawl")

        # Consuming this iterable may read files or normalize records.  It must
        # complete before even the read-only preflight session is opened.
        materialized = tuple(records)
        unique_records = _deduplicate(materialized)
        materialized_continuation: Mapping[str, object] | _ContinuationUnset | None
        if isinstance(continuation, _ContinuationUnset):
            materialized_continuation = continuation
        elif continuation is None:
            materialized_continuation = None
        else:
            materialized_continuation = freeze_mapping(continuation)
        database_subscription_id = _database_id(subscription_id)
        database_run_id = _database_id(run_id)

        start_state = self._load_start_state(
            database_subscription_id,
            database_run_id,
            expected_revision,
            ownership_guard=ownership_guard,
        )
        for record in unique_records:
            if (
                record.author.platform.value != start_state.platform
                or record.author.remote_id != start_state.author_remote_id
            ):
                raise RepositoryError("normalized record does not belong to the subscription")

        recovering_prior_crawl = normalized_mode is IngestionMode.FORWARD and origin_revision < expected_revision
        recovery_existing_keys = (
            self._load_existing_record_keys(unique_records) if recovering_prior_crawl else frozenset()
        )
        accepted = (
            tuple(
                sorted(
                    (
                        record
                        for record in unique_records
                        if _accept_forward(record, start_state)
                        or (recovering_prior_crawl and _record_key(record) not in recovery_existing_keys)
                    ),
                    key=_forward_batch_key,
                )
            )
            if normalized_mode is IngestionMode.FORWARD
            else unique_records
        )
        batches = _partition(accepted, self.batch_size)

        current_revision = expected_revision
        discovered_count = 0
        asset_count = 0
        final_watermarked_at = start_state.watermarked_at
        final_watermark_remote_ids = tuple(sorted(start_state.watermark_remote_ids))

        for batch_number, batch in enumerate(batches, start=1):
            final_batch = batch_number == len(batches)
            batch_watermark, batch_boundary_ids = (
                _watermark_boundary(batch) if normalized_mode is IngestionMode.FORWARD else (None, ())
            )
            with self.database.session() as session:
                if ownership_guard is not None:
                    ownership_guard(session)
                batch_discovered, batch_assets = _upsert_batch(session, batch)
                _record_refresh_observations(
                    session,
                    batch,
                    subscription_id=database_subscription_id,
                    run_id=database_run_id,
                )
                subscription_repository = SubscriptionRepository(session)
                publication_arguments: dict[str, Any] = {
                    "expected_revision": current_revision,
                    "watermarked_at": batch_watermark,
                    "watermark_remote_ids": batch_boundary_ids,
                    "succeeded_at": utc_now() if final_batch else None,
                }
                if final_batch and not isinstance(materialized_continuation, _ContinuationUnset):
                    checkpoint_field = "cursor" if normalized_mode is IngestionMode.FORWARD else "backfill_cursor"
                    publication_arguments[checkpoint_field] = materialized_continuation
                published = subscription_repository.publish_checkpoint(
                    database_subscription_id,
                    **publication_arguments,
                )

                run_repository = SyncRunRepository(session)
                run = run_repository.require(database_run_id)
                if run.subscription_id != database_subscription_id:
                    raise RepositoryError("sync run belongs to a different subscription")
                run = run_repository.record_checkpoint_publication(
                    database_run_id,
                    expected_revision=current_revision,
                    published_revision=published.checkpoint_revision,
                    expected_status=RunStatus.INGESTING.value,
                )
                # Counts intentionally describe newly materialized rows.  A
                # replay therefore cannot inflate them; updated_count remains
                # reserved for a future deterministic metadata comparator.
                run.discovered_count += batch_discovered
                run.asset_count += batch_assets
                run.cursor_after = dict(published.cursor) if published.cursor is not None else None
                session.flush()
                if final_batch:
                    run_repository.set_status(
                        database_run_id,
                        RunStatus.SUCCEEDED.value,
                        expected_status=RunStatus.INGESTING.value,
                    )

                current_revision = published.checkpoint_revision
                discovered_count += batch_discovered
                asset_count += batch_assets
                final_watermarked_at = published.watermarked_at
                final_watermark_remote_ids = tuple(published.watermark_remote_ids)

        return MediaCrawlerIngestionResult(
            mode=normalized_mode,
            input_count=len(materialized),
            accepted_count=len(accepted),
            skipped_count=len(materialized) - len(accepted),
            discovered_count=discovered_count,
            asset_count=asset_count,
            committed_batches=len(batches),
            checkpoint_revision=current_revision,
            watermarked_at=final_watermarked_at,
            watermark_remote_ids=final_watermark_remote_ids,
        )

    def _load_start_state(
        self,
        subscription_id: str,
        run_id: str,
        expected_revision: int,
        *,
        ownership_guard: Callable[[Session], None] | None = None,
    ) -> _StartState:
        with self.database.session() as session:
            if ownership_guard is not None:
                ownership_guard(session)
            subscription = SubscriptionRepository(session).get(subscription_id)
            if subscription is None:
                raise NotFoundError(f"subscription not found: {subscription_id}")
            if subscription.checkpoint_revision != expected_revision:
                raise StaleCheckpointError(
                    subscription_id,
                    expected_revision,
                    subscription.checkpoint_revision,
                )
            run = SyncRunRepository(session).require(run_id)
            if run.subscription_id != subscription_id:
                raise RepositoryError("sync run belongs to a different subscription")
            if run.status != RunStatus.INGESTING.value:
                raise RepositoryError("sync run is not ready for ingestion")
            run_revision = (
                run.checkpoint_revision_after
                if run.checkpoint_revision_after is not None
                else run.checkpoint_revision_before
            )
            if run_revision != expected_revision:
                raise RepositoryError("sync run does not own the expected checkpoint revision")
            return _StartState(
                platform=subscription.author.platform,
                author_remote_id=subscription.author.remote_id,
                watermarked_at=subscription.watermarked_at,
                watermark_remote_ids=frozenset(subscription.watermark_remote_ids),
            )

    def _load_existing_record_keys(
        self,
        records: Sequence[NormalizedMediaRecord],
    ) -> frozenset[tuple[str, str, str]]:
        """Bound recovery overlap by querying only remote IDs present in the sealed output."""

        remote_ids = tuple(sorted({record.content.remote_id for record in records}))
        existing: set[tuple[str, str, str]] = set()
        with self.database.session() as session:
            for index in range(0, len(remote_ids), _EXISTING_KEY_QUERY_BATCH_SIZE):
                candidate_ids = remote_ids[index : index + _EXISTING_KEY_QUERY_BATCH_SIZE]
                if not candidate_ids:
                    continue
                rows = session.execute(
                    select(Content.platform, Content.remote_type, Content.remote_id).where(
                        Content.remote_id.in_(candidate_ids)
                    )
                )
                existing.update((platform, remote_type, remote_id) for platform, remote_type, remote_id in rows)
        return frozenset(existing)


__all__ = [
    "DEFAULT_INGESTION_BATCH_SIZE",
    "MAX_INGESTION_BATCH_SIZE",
    "IngestionMode",
    "MediaCrawlerIngestionResult",
    "MediaCrawlerIngestionService",
]
