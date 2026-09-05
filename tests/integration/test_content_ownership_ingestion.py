"""Real normalized ingestion and scheduler ownership conflicts, without remote I/O."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from media_sync.domain import Platform
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    ContentOwnershipConflictError,
    Database,
    MediaCrawlerIngestionService,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import (
    Asset,
    AssetRefreshSource,
    Content,
    Job,
    RunEvent,
    SchedulerLane,
    Subscription,
    SyncRun,
)
from media_sync.integrations.mediacrawler.normalizers import (
    NormalizationContext,
    NormalizedMediaRecord,
    normalize_jsonl_bytes,
)
from media_sync.scheduler.service import DurableSchedulerService
from tests.integration import test_bili_bounded_scheduler as bounded

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'ownership-ingestion.sqlite3').as_posix()}")
    instance.create_schema()
    yield instance
    instance.dispose()


def _records(author_id: str, *remote_ids: str) -> tuple[NormalizedMediaRecord, ...]:
    payload = "".join(
        json.dumps(
            {
                "video_id": remote_id,
                "create_time": int(_NOW.timestamp()) + index,
                "title": "Synthetic owned upload",
                "desc": "Original content body",
                "video_url": f"https://www.bilibili.com/video/av{remote_id}",
            }
        )
        + "\n"
        for index, remote_id in enumerate(remote_ids)
    ).encode("utf-8")
    normalized = normalize_jsonl_bytes(
        payload,
        NormalizationContext(
            platform=Platform.BILI,
            creator_remote_id=author_id,
            creator_display_name="Synthetic creator",
            upstream_sha="a" * 40,
            ingested_at=_NOW,
        ),
    )
    assert not normalized.quarantined and len(normalized.records) == len(remote_ids)
    assert all(record.assets for record in normalized.records)
    return normalized.records


def _seed_subscription(database: Database, author_id: str) -> str:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            display_name=f"Synthetic {uuid4()}",
            adapter="mediacrawler",
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="bili", remote_id=author_id, display_name="Stored creator"),
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            enabled=False,
            max_items=30,
        )
        return subscription.id


def _run(database: Database, subscription_id: str) -> str:
    with database.session() as session:
        repository = SyncRunRepository(session)
        run = repository.create(subscription_id=subscription_id)
        repository.set_status(run.id, "claimed", expected_status="queued")
        repository.set_status(run.id, "running", expected_status="claimed")
        repository.set_status(run.id, "ingesting", expected_status="running")
        return run.id


def _seed_existing(database: Database, remote_id: str) -> str:
    subscription_id = _seed_subscription(database, "999999999")
    run_id = _run(database, subscription_id)
    MediaCrawlerIngestionService(database).ingest_bili_bounded(
        _records("999999999", remote_id),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=0,
        input_cursor=None,
        next_cursor="original-owner-cursor",
    )
    return run_id


def _existing_snapshot(database: Database, remote_id: str) -> tuple[object, ...]:
    with database.session() as session:
        content = session.scalar(select(Content).where(Content.remote_id == remote_id))
        assert content is not None
        assets = list(session.scalars(select(Asset).where(Asset.content_id == content.id)))
        sources = list(
            session.scalars(
                select(AssetRefreshSource).where(AssetRefreshSource.asset_id.in_([asset.id for asset in assets]))
            )
        )
        return (
            content.id,
            content.author_id,
            content.title,
            content.body,
            content.raw,
            content.updated_at,
            tuple((asset.id, asset.locator, asset.raw, asset.status, asset.updated_at) for asset in assets),
            tuple(
                (
                    source.asset_id,
                    source.subscription_id,
                    source.last_run_id,
                    source.observed_generation,
                    source.observed_semantic_fingerprint,
                    source.observed_locator_fingerprint,
                    source.first_seen_at,
                    source.last_seen_at,
                )
                for source in sources
            ),
        )


@pytest.mark.parametrize("mode", ["bounded", "legacy_one_batch", "legacy_two_batches"])
def test_normalized_conflicting_unit_rolls_back_but_keeps_previously_committed_legacy_batch(
    database: Database,
    mode: str,
) -> None:
    original_run_id = _seed_existing(database, "200")
    original = _existing_snapshot(database, "200")
    subscription_id = _seed_subscription(database, "123")
    run_id = _run(database, subscription_id)
    records = _records("123", "100", "200")
    service = MediaCrawlerIngestionService(database, batch_size=1 if mode == "legacy_two_batches" else 100)
    with pytest.raises(ContentOwnershipConflictError, match=r"^content_ownership_conflict$"):
        if mode == "bounded":
            service.ingest_bili_bounded(
                records,
                subscription_id=subscription_id,
                run_id=run_id,
                expected_revision=0,
                input_cursor=None,
                next_cursor="unpublished-cursor",
            )
        else:
            service.ingest(records, subscription_id=subscription_id, run_id=run_id, expected_revision=0, mode="forward")
    assert _existing_snapshot(database, "200") == original
    prior_batches = int(mode == "legacy_two_batches")
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        run = session.get(SyncRun, run_id)
        assert subscription is not None and run is not None
        assert subscription.checkpoint_revision == prior_batches
        assert subscription.cursor is None and subscription.last_success_at is None
        assert subscription.watermarked_at == (_NOW if prior_batches else None)
        assert run.status == "ingesting" and run.error_code is None
        assert run.discovered_count == run.asset_count == prior_batches
        assert run.checkpoint_revision_after == (1 if prior_batches else None)
        assert session.scalar(select(func.count()).select_from(Content)) == 1 + prior_batches
        assert session.scalar(select(func.count()).select_from(Asset)) == 1 + prior_batches
        assert session.scalar(select(func.count()).select_from(AssetRefreshSource)) == 1 + prior_batches
        sources = set(session.scalars(select(AssetRefreshSource.last_run_id)))
        assert sources == ({original_run_id, run_id} if prior_batches else {original_run_id})
        assert (
            session.scalar(
                select(func.count())
                .select_from(RunEvent)
                .where(
                    RunEvent.run_id == run_id,
                    RunEvent.to_status == "succeeded",
                )
            )
            == 0
        )
        assert session.scalar(select(func.count()).select_from(Job)) == 0


@pytest.mark.asyncio
async def test_real_sealed_scheduler_conflict_is_terminal_cleans_attempt_and_does_not_publish_pipeline(
    database: Database,
    tmp_path: Path,
) -> None:
    _seed_existing(database, "1000")
    original = _existing_snapshot(database, "1000")
    runtime_root = (tmp_path / "runtime").resolve()
    subscription_id = bounded._seed(database, runtime_root)
    clock = bounded.support._Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    assert scheduler.tick(limit=1).materialized_count == 1
    runner = bounded._SealedSyntheticUploads()
    result = await bounded._worker(
        database,
        runtime_root,
        runner,
        clock,
        ingestion_factory=_MutatedConflict,
    ).run_once(worker_id="ownership-conflict")
    assert (result.status, result.error_code) == ("failed_terminal", "content_ownership_conflict")
    assert _existing_snapshot(database, "1000") == original
    assert len(runner.manifests) == 1 and not runner.manifests[0].job_root.exists()
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        run = session.get(SyncRun, result.run_id)
        job = session.get(Job, result.job_id)
        assert subscription is not None and run is not None and job is not None
        assert run.status == job.status == "failed_terminal"
        assert run.error_code == job.last_error_code == "content_ownership_conflict"
        assert run.error_message is job.last_error_message is None
        assert subscription.checkpoint_revision == 0 and subscription.cursor is None
        assert run.discovered_count == run.asset_count == 0 and run.checkpoint_revision_after is None
        assert subscription.watermarked_at == bounded.support.NOW
        assert subscription.watermark_remote_ids == ["legacy-does-not-prove-coverage"]
        assert session.scalar(select(func.count()).select_from(Content)) == 1
        assert session.scalar(select(func.count()).select_from(Asset)) == 1
        assert session.scalar(select(func.count()).select_from(AssetRefreshSource)) == 1
        assert bounded._pipeline_count(session) == 0
        lanes = list(session.scalars(select(SchedulerLane)))
        assert lanes and all(lane.circuit_state == "closed" and lane.consecutive_failures == 0 for lane in lanes)
    clock.value += timedelta(seconds=30)
    assert (
        await bounded._worker(database, runtime_root, runner, clock).run_once(worker_id="no-retry")
    ).status == "idle"
    assert len(runner.manifests) == 1


class _ConflictAfterCommit(MediaCrawlerIngestionService):
    def ingest_bili_bounded(self, *args: Any, **kwargs: Any) -> Any:
        super().ingest_bili_bounded(*args, **kwargs)
        raise ContentOwnershipConflictError


class _MutatedConflict(MediaCrawlerIngestionService):
    def ingest_bili_bounded(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return super().ingest_bili_bounded(*args, **kwargs)
        except ContentOwnershipConflictError as error:
            error.args = ("private-conflict-must-not-leak",)
            error.code = "private_conflict_code_must_not_leak"
            raise


@pytest.mark.asyncio
async def test_exact_committed_run_wins_over_later_typed_conflict(database: Database, tmp_path: Path) -> None:
    runtime_root = (tmp_path / "runtime").resolve()
    bounded._seed(database, runtime_root)
    clock = bounded.support._Clock()
    DurableSchedulerService(database, clock=clock).tick(limit=1)
    runner = bounded._SealedSyntheticUploads()
    result = await bounded._worker(
        database,
        runtime_root,
        runner,
        clock,
        ingestion_factory=_ConflictAfterCommit,
    ).run_once(worker_id="commit-wins")
    assert (result.status, result.error_code) == ("succeeded", None)
    with database.session() as session:
        run = session.get(SyncRun, result.run_id)
        job = session.get(Job, result.job_id)
        assert run.status == job.status == "succeeded" and run.error_code is job.last_error_code is None
        assert session.scalar(select(Subscription.checkpoint_revision)) == 1
        assert bounded._pipeline_count(session) == 1
    assert not runner.manifests[0].job_root.exists()
