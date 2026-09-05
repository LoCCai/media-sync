"""Atomic bounded Bili upload ingestion, independent of network/scan parsing."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import media_sync.infrastructure.db.mediacrawler_ingestion as ingestion_module
from media_sync.domain import AssetKind, AssetSnapshot, AuthorSnapshot, ContentKind, ContentSnapshot, Platform
from media_sync.infrastructure.db import (
    AccountRepository,
    AssetRefreshSourceRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    LeaseLostError,
    MediaCrawlerIngestionService,
    RepositoryError,
    StaleCheckpointError,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import Asset, AssetRefreshSource, Content, RunEvent, Subscription, SyncRun
from media_sync.integrations.mediacrawler.normalizers import NormalizedMediaRecord

_LEGACY_WATERMARK = datetime(2026, 9, 5, tzinfo=UTC)


class _TrackingDatabase(Database):
    active_sessions = 0
    opened_sessions = 0
    lose_acknowledgement = False

    @contextmanager
    def session(self) -> Iterator[Session]:
        self.active_sessions += 1
        self.opened_sessions += 1
        try:
            with super().session() as session:
                yield session
            if self.lose_acknowledgement:
                self.lose_acknowledgement = False
                raise OSError("synthetic post-commit acknowledgement loss")
        finally:
            self.active_sessions -= 1


@pytest.fixture
def database(tmp_path: Path) -> Iterator[_TrackingDatabase]:
    instance = _TrackingDatabase(f"sqlite+pysqlite:///{(tmp_path / 'bounded.sqlite3').as_posix()}")
    instance.create_schema()
    yield instance
    instance.dispose()


def _seed(database: Database, *, cursor: str | None = None, max_items: int = 30) -> str:
    with database.session() as session:
        account = AccountRepository(session).create(platform="bili", display_name="Synthetic", adapter="mediacrawler")
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="bili", remote_id="123", display_name="Creator")
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            cursor=None if cursor is None else {"value": cursor},
            backfill_cursor={"legacy": "preserve"},
            max_items=max_items,
        )
        subscription.watermarked_at = _LEGACY_WATERMARK
        subscription.watermark_remote_ids = ["legacy-watermark-id"]
        return subscription.id


def _run(database: Database, subscription_id: str) -> str:
    with database.session() as session:
        subscription = SubscriptionRepository(session).get(subscription_id)
        assert subscription is not None
        repository = SyncRunRepository(session)
        run = repository.create(subscription_id=subscription_id, cursor_before=subscription.cursor)
        repository.set_status(run.id, "claimed", expected_status="queued")
        repository.set_status(run.id, "running", expected_status="claimed")
        repository.set_status(run.id, "ingesting", expected_status="running")
        return run.id


def _record(remote_id: str = "100") -> NormalizedMediaRecord:
    author = AuthorSnapshot(platform=Platform.BILI, remote_id="123", display_name="Creator")
    return NormalizedMediaRecord(
        author=author,
        content=ContentSnapshot(
            platform=Platform.BILI,
            remote_id=remote_id,
            author_remote_id=author.remote_id,
            kind=ContentKind.VIDEO,
            title="Synthetic upload",
            published_at=_LEGACY_WATERMARK - timedelta(days=300),
        ),
        assets=(
            AssetSnapshot(
                platform=Platform.BILI,
                remote_id=f"{remote_id}:video",
                content_remote_id=remote_id,
                kind=AssetKind.VIDEO,
            ),
        ),
    )


def _assert_unpublished(database: Database, subscription_id: str, run_id: str) -> None:
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        run = session.get(SyncRun, run_id)
        assert subscription is not None and run is not None
        assert subscription.checkpoint_revision == 0
        assert subscription.cursor is None
        assert subscription.watermarked_at == _LEGACY_WATERMARK
        assert subscription.watermark_remote_ids == ["legacy-watermark-id"]
        assert subscription.backfill_cursor == {"legacy": "preserve"}
        assert subscription.last_success_at is None
        assert run.status == "ingesting"
        assert run.checkpoint_revision_after is None and run.cursor_after is None
        assert run.discovered_count == run.asset_count == 0
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(AssetRefreshSource)) == 0
        assert session.scalar(select(func.count()).select_from(RunEvent).where(RunEvent.to_status == "succeeded")) == 0


def test_old_uploads_sources_cursor_and_success_publish_in_one_session(database: _TrackingDatabase) -> None:
    subscription_id = _seed(database)
    run_id = _run(database, subscription_id)

    def records() -> Iterator[NormalizedMediaRecord]:
        assert database.active_sessions == 0
        yield _record()
        assert database.active_sessions == 0

    before = database.opened_sessions
    result = MediaCrawlerIngestionService(database, batch_size=1).ingest_bili_bounded(
        records(),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=0,
        input_cursor=None,
        next_cursor="scan-1",
    )
    assert database.opened_sessions == before + 1
    assert result.accepted_count == result.discovered_count == result.asset_count == result.committed_batches == 1
    assert result.watermarked_at == _LEGACY_WATERMARK
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        run = session.get(SyncRun, run_id)
        asset = session.scalar(select(Asset))
        assert subscription is not None and run is not None and asset is not None
        assert subscription.cursor == run.cursor_after == {"value": "scan-1"}
        assert subscription.checkpoint_revision == run.checkpoint_revision_after == 1
        assert subscription.watermark_remote_ids == ["legacy-watermark-id"]
        assert subscription.backfill_cursor == {"legacy": "preserve"}
        assert run.status == "succeeded" and subscription.last_success_at is not None
        sources = AssetRefreshSourceRepository(session).list_eligible(asset.id)
        assert len(sources) == 1 and sources[0].last_run_id == run_id
        assert sources[0].subscription_id == subscription_id


def test_zero_content_unit_advances_checkpoint_without_promoting_watermark(database: Database) -> None:
    subscription_id = _seed(database, cursor="legacy-opaque")
    run_id = _run(database, subscription_id)
    result = MediaCrawlerIngestionService(database).ingest_bili_bounded(
        (),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=0,
        input_cursor="legacy-opaque",
        next_cursor="observed-empty-source",
    )
    assert result.accepted_count == result.discovered_count == result.asset_count == 0
    assert result.checkpoint_revision == result.committed_batches == 1
    with database.session() as session:
        run = session.get(SyncRun, run_id)
        assert run is not None and run.status == "succeeded"
        assert run.cursor_before == {"value": "legacy-opaque"}
        assert run.cursor_after == {"value": "observed-empty-source"}


@pytest.mark.parametrize("guard_call", [1, 2, 3])
@pytest.mark.parametrize("error_type", [LeaseLostError, asyncio.CancelledError])
def test_lease_or_cancel_guard_rolls_back_every_effect(
    database: Database,
    guard_call: int,
    error_type: type[BaseException],
) -> None:
    subscription_id = _seed(database)
    run_id = _run(database, subscription_id)
    calls = 0

    def guard(session: Session) -> None:
        nonlocal calls
        calls += 1
        if calls == guard_call:
            raise error_type("synthetic lease loss or cancellation")
        assert session.in_transaction()

    with pytest.raises(error_type):
        MediaCrawlerIngestionService(database).ingest_bili_bounded(
            (_record(),),
            subscription_id=subscription_id,
            run_id=run_id,
            expected_revision=0,
            input_cursor=None,
            next_cursor="scan-1",
            ownership_guard=guard,
        )
    _assert_unpublished(database, subscription_id, run_id)


@pytest.mark.parametrize("failure_boundary", ["provenance", "checkpoint", "run_status"])
def test_failure_at_each_publication_boundary_rolls_back_all_rows(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    failure_boundary: str,
) -> None:
    subscription_id = _seed(database)
    run_id = _run(database, subscription_id)
    if failure_boundary == "provenance":
        original = ingestion_module._record_refresh_observations

        def failed_observation(*args: object, **kwargs: object) -> None:
            original(*args, **kwargs)
            raise RepositoryError("synthetic provenance failure")

        monkeypatch.setattr(ingestion_module, "_record_refresh_observations", failed_observation)
    elif failure_boundary == "checkpoint":

        def failed_checkpoint(*args: object, **kwargs: object) -> None:
            raise StaleCheckpointError(subscription_id, 0, 1)

        monkeypatch.setattr(SubscriptionRepository, "publish_checkpoint", failed_checkpoint)
    else:

        def failed_status(*args: object, **kwargs: object) -> None:
            raise RepositoryError("synthetic final run publication failure")

        monkeypatch.setattr(SyncRunRepository, "set_status", failed_status)
    with pytest.raises(RepositoryError):
        MediaCrawlerIngestionService(database).ingest_bili_bounded(
            (_record(),),
            subscription_id=subscription_id,
            run_id=run_id,
            expected_revision=0,
            input_cursor=None,
            next_cursor="scan-1",
        )
    _assert_unpublished(database, subscription_id, run_id)


def test_exact_completed_replay_does_not_overwrite_later_cursor_or_provenance(database: Database) -> None:
    subscription_id = _seed(database)
    first_run = _run(database, subscription_id)
    service = MediaCrawlerIngestionService(database)
    service.ingest_bili_bounded(
        (_record(),),
        subscription_id=subscription_id,
        run_id=first_run,
        expected_revision=0,
        input_cursor=None,
        next_cursor="scan-1",
    )
    second_run = _run(database, subscription_id)
    second = service.ingest_bili_bounded(
        (_record(), _record("101")),
        subscription_id=subscription_id,
        run_id=second_run,
        expected_revision=1,
        input_cursor="scan-1",
        next_cursor="scan-2",
    )
    assert second.accepted_count == 2 and second.discovered_count == 1
    replay = service.ingest_bili_bounded(
        (_record(),),
        subscription_id=subscription_id,
        run_id=first_run,
        expected_revision=2,
        crawl_revision_before=0,
        input_cursor=None,
        next_cursor="scan-1",
    )
    assert replay.committed_batches == replay.discovered_count == replay.asset_count == 0
    assert replay.checkpoint_revision == 1
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        assert subscription.checkpoint_revision == 2 and subscription.cursor == {"value": "scan-2"}
        assert set(session.scalars(select(AssetRefreshSource.last_run_id))) == {second_run}
        assert session.scalar(select(func.count()).select_from(Content)) == 2


def test_stale_artifact_cannot_borrow_new_run_revision(database: Database) -> None:
    subscription_id = _seed(database)
    first_run = _run(database, subscription_id)
    service = MediaCrawlerIngestionService(database)
    service.ingest_bili_bounded(
        (),
        subscription_id=subscription_id,
        run_id=first_run,
        expected_revision=0,
        input_cursor=None,
        next_cursor="scan-1",
    )
    newer_run = _run(database, subscription_id)
    with pytest.raises(RepositoryError):
        service.ingest_bili_bounded(
            (_record(),),
            subscription_id=subscription_id,
            run_id=newer_run,
            expected_revision=1,
            crawl_revision_before=0,
            input_cursor=None,
            next_cursor="old-next",
        )
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        assert session.get(Subscription, subscription_id).cursor == {"value": "scan-1"}
        assert session.get(SyncRun, newer_run).status == "ingesting"


def test_ambiguous_commit_is_acknowledged_by_exact_run_replay(database: _TrackingDatabase) -> None:
    subscription_id = _seed(database)
    run_id = _run(database, subscription_id)
    service = MediaCrawlerIngestionService(database)
    database.lose_acknowledgement = True
    with pytest.raises(OSError, match="post-commit"):
        service.ingest_bili_bounded(
            (_record(),),
            subscription_id=subscription_id,
            run_id=run_id,
            expected_revision=0,
            input_cursor=None,
            next_cursor="scan-1",
        )
    replay = service.ingest_bili_bounded(
        (_record(),),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=0,
        input_cursor=None,
        next_cursor="scan-1",
    )
    assert replay.committed_batches == 0 and replay.checkpoint_revision == 1
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Content)) == 1
        assert session.scalar(select(func.count()).select_from(AssetRefreshSource)) == 1
        assert session.scalar(select(func.count()).select_from(RunEvent).where(RunEvent.to_status == "succeeded")) == 1


@pytest.mark.parametrize("mutation", ["input", "next", "run_revision"])
def test_replay_requires_exact_durable_input_and_output_identity(database: Database, mutation: str) -> None:
    subscription_id = _seed(database)
    run_id = _run(database, subscription_id)
    service = MediaCrawlerIngestionService(database)
    service.ingest_bili_bounded(
        (),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=0,
        input_cursor=None,
        next_cursor="scan-1",
    )
    with pytest.raises(RepositoryError):
        service.ingest_bili_bounded(
            (),
            subscription_id=subscription_id,
            run_id=run_id,
            expected_revision=1 if mutation == "run_revision" else 0,
            input_cursor="different" if mutation == "input" else None,
            next_cursor="different" if mutation == "next" else "scan-1",
        )


def test_more_than_30_stops_iterator_before_database_io(database: _TrackingDatabase) -> None:
    subscription_id = _seed(database, max_items=100)
    run_id = _run(database, subscription_id)
    seen = 0

    def records() -> Iterator[NormalizedMediaRecord]:
        nonlocal seen
        for number in range(100):
            seen += 1
            yield _record(str(number))

    before = database.opened_sessions
    with pytest.raises(ValueError, match="at most 30"):
        MediaCrawlerIngestionService(database).ingest_bili_bounded(
            records(),
            subscription_id=subscription_id,
            run_id=run_id,
            expected_revision=0,
            input_cursor=None,
            next_cursor="scan-1",
        )
    assert seen == 31 and database.opened_sessions == before


def test_exactly_30_records_are_one_atomic_unit_even_with_batch_size_one(database: _TrackingDatabase) -> None:
    subscription_id = _seed(database)
    run_id = _run(database, subscription_id)
    before = database.opened_sessions
    result = MediaCrawlerIngestionService(database, batch_size=1).ingest_bili_bounded(
        (_record(str(number)) for number in range(30)),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=0,
        input_cursor=None,
        next_cursor="scan-1",
    )
    assert database.opened_sessions == before + 1
    assert result.accepted_count == result.discovered_count == result.asset_count == 30
    assert result.committed_batches == result.checkpoint_revision == 1


@pytest.mark.parametrize("invalid_scope", ["duplicate", "limit", "author", "feed", "adapter", "cursor", "revision"])
def test_invalid_scope_or_budget_never_publishes(database: Database, invalid_scope: str) -> None:
    subscription_id = _seed(database, max_items=1 if invalid_scope == "limit" else 30)
    run_id = _run(database, subscription_id)
    records = (_record(),)
    if invalid_scope == "duplicate":
        records = (_record(), _record())
    elif invalid_scope == "limit":
        records = (_record(), _record("101"))
    elif invalid_scope == "author":
        record = _record()
        records = (
            replace(
                record,
                author=replace(record.author, remote_id="456"),
                content=replace(record.content, author_remote_id="456"),
            ),
        )
    elif invalid_scope == "feed":
        record = _record()
        records = (replace(record, content=replace(record.content, remote_type="dynamic")),)
    elif invalid_scope == "adapter":
        with database.session() as session:
            session.get(Subscription, subscription_id).account.adapter = "fake"
    with pytest.raises(RepositoryError):
        MediaCrawlerIngestionService(database).ingest_bili_bounded(
            records,
            subscription_id=subscription_id,
            run_id=run_id,
            expected_revision=1 if invalid_scope == "revision" else 0,
            input_cursor="other" if invalid_scope == "cursor" else None,
            next_cursor="scan-1",
        )
    _assert_unpublished(database, subscription_id, run_id)


def test_two_competing_units_have_one_atomic_cas_winner(database: Database) -> None:
    subscription_id = _seed(database)
    run_ids = (_run(database, subscription_id), _run(database, subscription_id))
    barrier = Barrier(2)

    def ingest(index: int) -> str:
        barrier.wait(timeout=10)
        try:
            MediaCrawlerIngestionService(database).ingest_bili_bounded(
                (_record(str(100 + index)),),
                subscription_id=subscription_id,
                run_id=run_ids[index],
                expected_revision=0,
                input_cursor=None,
                next_cursor=f"scan-{index}",
            )
        except StaleCheckpointError:
            return "stale"
        return "succeeded"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(ingest, range(2)))
    assert sorted(results) == ["stale", "succeeded"]
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Content)) == 1
        assert session.scalar(select(func.count()).select_from(AssetRefreshSource)) == 1
        assert sorted(session.scalars(select(SyncRun.status))) == ["ingesting", "succeeded"]
        assert session.get(Subscription, subscription_id).checkpoint_revision == 1
