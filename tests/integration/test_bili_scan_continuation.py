"""Offline real worker/ingestion/checkpoint scheduling with sealed observations."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.models import (
    BiliSubscriptionProgress,
    Content,
    Job,
    Subscription,
    SyncRun,
    SyncRunContent,
)
from media_sync.integrations.mediacrawler.bilibili_scan import BiliIdentity
from media_sync.scheduler.bili_delivery_progress import BiliDeliveryProgressRepository
from media_sync.scheduler.bili_scan_continuation import BiliScanContinuationPolicy
from media_sync.scheduler.handlers import SubscriptionHandlerRegistry
from media_sync.scheduler.pipeline_receipt import PipelineDeliveryReceipt
from media_sync.scheduler.pipeline_worker import PipelineHandlerResult, PipelineSubscriptionWorker
from media_sync.scheduler.repository import SchedulerRepository
from media_sync.scheduler.service import DurableSchedulerService, SubscriptionWorker
from tests.integration import test_bili_bounded_scheduler as bounded
from tests.integration import test_mediacrawler_scheduler_handler as support


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'continuation.sqlite3').as_posix()}")
    instance.create_schema()
    yield instance
    instance.dispose()


def _seed(database: Database, tmp_path: Path, *, max_items: int = 1) -> str:
    identifier = bounded._seed(database, tmp_path, max_items=max_items)
    with database.session() as session:
        subscription = session.get(Subscription, identifier)
        assert subscription is not None
        subscription.interval_seconds = 21600
    return identifier


def _policy(delay: int = 300) -> BiliScanContinuationPolicy:
    return BiliScanContinuationPolicy(delay, support.PINNED_SHA)


def _worker(
    database: Database,
    tmp_path: Path,
    runner: bounded._SealedSyntheticUploads,
    clock: support._Clock,
    *,
    policy: BiliScanContinuationPolicy | None = None,
) -> SubscriptionWorker:
    handler = support._protocol_handler(database, tmp_path, runner=runner, clock=clock)
    return SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"mediacrawler": handler}),
        clock=clock,
        bili_scan_continuation=policy or _policy(),
    )


async def _qualify_delivery(
    database: Database,
    clock: support._Clock,
    *,
    policy: BiliScanContinuationPolicy,
    retry_backlog_content_count: int = 0,
    delivered_retry_backlog_content_count: int = 0,
    failed_retry_backlog_content_count: int = 0,
    retryable_failed_content_count: int = 0,
    terminal_failed_content_count: int = 0,
    failure_codes: tuple[str, ...] = (),
) -> None:
    with database.session() as session:
        pipeline = session.scalar(
            select(Job)
            .where(Job.job_type == "pipeline.subscription", Job.status == "queued")
            .order_by(Job.created_at, Job.id)
        )
        assert pipeline is not None and pipeline.subscription_id is not None and pipeline.run_id is not None
        subscription = session.get(Subscription, pipeline.subscription_id)
        assert subscription is not None
        observed = int(
            session.scalar(
                select(func.count())
                .select_from(SyncRunContent)
                .where(
                    SyncRunContent.run_id == pipeline.run_id,
                    SyncRunContent.subscription_id == subscription.id,
                )
            )
            or 0
        )
        export = Job(
            id=str(uuid4()),
            job_type="export.emby",
            natural_key=f"test-export:{pipeline.id}",
            payload={"author_id": subscription.author_id, "result": {"managed_file_count": 2}},
            status="succeeded",
            max_attempts=1,
            available_at=clock.value,
            finished_at=clock.value,
        )
        session.add(export)
        session.flush()
        receipt = PipelineDeliveryReceipt(
            subscription_id=subscription.id,
            account_id=subscription.account_id,
            author_id=subscription.author_id,
            platform="bili",
            export_job_id=export.id,
            selected_asset_count=0,
            verified_asset_count=0,
            downloaded_count=0,
            already_verified_count=0,
            publication_disposition="published",
            managed_file_count=2,
            directory_verified=True,
            schema_version=2,
            source_run_id=pipeline.run_id,
            observed_content_count=observed,
            delivered_content_count=observed,
            retry_backlog_content_count=retry_backlog_content_count,
            delivered_retry_backlog_content_count=delivered_retry_backlog_content_count,
            failed_retry_backlog_content_count=failed_retry_backlog_content_count,
            retryable_failed_content_count=retryable_failed_content_count,
            terminal_failed_content_count=terminal_failed_content_count,
            failure_codes=failure_codes,
            partial=failed_retry_backlog_content_count > 0,
        )

    result = await PipelineSubscriptionWorker(
        database,
        lambda _claim: PipelineHandlerResult.success(receipt),
        clock=clock,
        bili_delivery_policy=policy,
    ).run_once(worker_id=f"delivery-{uuid4()}")
    assert result.status == "succeeded"


async def _fail_delivery(
    database: Database,
    clock: support._Clock,
    *,
    policy: BiliScanContinuationPolicy,
    error_code: str = "pipeline_download_terminal",
) -> str:
    result = await PipelineSubscriptionWorker(
        database,
        lambda _claim: PipelineHandlerResult.failure(error_code),
        clock=clock,
        bili_delivery_policy=policy,
    ).run_once(worker_id=f"delivery-failure-{uuid4()}")
    assert result.job_id is not None and result.status == "failed_terminal"
    return result.job_id


@pytest.mark.asyncio
async def test_paced_pending_continuation_survives_worker_restarts_then_returns_to_ordinary_interval(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database, tmp_path)
    clock = support._Clock()
    scheduler = DurableSchedulerService(database, clock=clock, bili_scan_continuation=_policy())
    runner = bounded._SealedSyntheticUploads()
    delays: list[int] = []
    previous_cursor = None
    for number in range(10):
        started_at = clock.value
        assert scheduler.tick(limit=1).materialized_count == 1
        result = await _worker(database, tmp_path, runner, clock).run_once(worker_id=f"paced-{number}")
        assert result.status == "succeeded"
        assert len(runner.manifests) == number + 1
        assert runner.manifests[-1].bili_scan_input_cursor == previous_cursor
        coverage = runner.coverages[-1]
        assert coverage.list_attempts <= 2 and coverage.detail_attempts <= 1
        # Discovery alone never advances the backfill chain. The exact
        # pipeline receipt is the durable release fence for the next unit.
        assert scheduler.tick().materialized_count == 0
        await _qualify_delivery(database, clock, policy=_policy())
        with database.session() as session:
            subscription = session.get(Subscription, subscription_id)
            run = session.get(SyncRun, result.run_id)
            assert subscription is not None and subscription.next_run_at is not None and run is not None
            assert run.cursor_after == {"value": coverage.next_state.to_cursor()}
            assert run.checkpoint_revision_after is not None
            assert subscription.checkpoint_revision >= run.checkpoint_revision_after
            assert bounded._pipeline_count(session) == number + 1
            previous_cursor = subscription.cursor["value"]
            next_at = subscription.next_run_at
            delays.append(int((next_at - started_at).total_seconds()))
        # No tight loop, request, or materialization before the configured time.
        assert scheduler.tick().materialized_count == 0
        assert (await _worker(database, tmp_path, runner, clock).run_once(worker_id="not-due")).status == "idle"
        clock.value = next_at - timedelta(seconds=1)
        assert scheduler.tick().materialized_count == 0
        assert len(runner.manifests) == number + 1
        clock.value = next_at
    assert delays == [300] * 9 + [21600]
    assert [coverage.lane for coverage in runner.coverages] == ["head", "history"] * 4 + ["head", "head"]
    with database.session() as session:
        progress = session.get(BiliSubscriptionProgress, subscription_id)
        assert progress is not None and progress.phase == "incremental"


@pytest.mark.asyncio
async def test_sixty_seven_uploads_cross_multiple_delivered_batches_and_reconcile_before_incremental(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database, tmp_path, max_items=30)
    clock = support._Clock()
    policy = _policy()
    scheduler = DurableSchedulerService(database, clock=clock, bili_scan_continuation=policy)
    runner = bounded._SealedSyntheticUploads(count=67, max_items=30)
    observed_phases: list[str] = []

    for number in range(20):
        assert scheduler.tick(limit=1).materialized_count == 1
        result = await _worker(database, tmp_path, runner, clock, policy=policy).run_once(
            worker_id=f"sixty-seven-discovery-{number}"
        )
        assert result.status == "succeeded"
        coverage = runner.coverages[-1]
        assert coverage.detail_attempts <= 30 and coverage.list_attempts <= 2
        assert scheduler.tick(limit=1).materialized_count == 0

        # A fresh pipeline worker publishes the exact receipt; no in-memory
        # discovery worker state is needed to release the next durable unit.
        await _qualify_delivery(database, clock, policy=policy)
        with database.session() as session:
            subscription = session.get(Subscription, subscription_id)
            progress = session.get(BiliSubscriptionProgress, subscription_id)
            assert subscription is not None and subscription.next_run_at is not None
            assert progress is not None
            observed_phases.append(progress.phase)
            next_at = subscription.next_run_at
        if observed_phases[-1] == "incremental":
            break
        clock.value = next_at
    else:
        pytest.fail("bounded 67-upload fixture did not reach incremental phase")

    assert "reconciling" in observed_phases
    assert observed_phases[-1] == "incremental"
    assert len(runner.coverages) >= 3
    assert any(item.lane == "history" and item.stop_reason == "source_end" for item in runner.coverages)
    with database.session() as session:
        progress = session.get(BiliSubscriptionProgress, subscription_id)
        assert progress is not None
        assert progress.phase == "incremental" and progress.baseline_snapshot_at is not None
        assert progress.backfill_batch_count >= 3
        assert progress.reconciliation_batch_count >= 1
        assert session.scalar(select(func.count()).select_from(Content)) == 67
        assert session.scalar(select(func.count()).select_from(Job).where(Job.status == "queued")) == 0

    assert scheduler.tick(limit=1).materialized_count == 0


@pytest.mark.asyncio
async def test_incremental_retry_backlog_failure_is_partial_and_uses_continuation_pacing(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database, tmp_path)
    clock = support._Clock()
    policy = _policy()
    scheduler = DurableSchedulerService(database, clock=clock, bili_scan_continuation=policy)
    assert scheduler.tick(limit=1).materialized_count == 1
    discovery = await _worker(
        database,
        tmp_path,
        bounded._SealedSyntheticUploads(empty=True),
        clock,
        policy=policy,
    ).run_once(worker_id="incremental-retry-backlog")
    assert discovery.status == "succeeded" and discovery.run_id is not None

    with database.session() as session:
        progress = session.get(BiliSubscriptionProgress, subscription_id)
        assert progress is not None
        progress.phase = "incremental"
        progress.source_end_observed_at = clock.value
        progress.source_end_run_id = discovery.run_id
        progress.source_end_boundary_sha256 = "a" * 64
        progress.reconciled_at = clock.value
        progress.reconciliation_run_id = discovery.run_id
        progress.baseline_snapshot_at = clock.value

    await _qualify_delivery(
        database,
        clock,
        policy=policy,
        retry_backlog_content_count=1,
        failed_retry_backlog_content_count=1,
        retryable_failed_content_count=1,
        failure_codes=("pipeline_download_retryable",),
    )

    with database.session() as session:
        progress = session.get(BiliSubscriptionProgress, subscription_id)
        subscription = session.get(Subscription, subscription_id)
        assert progress is not None and subscription is not None
        assert (progress.phase, progress.partial_batch_count, progress.batch_count) == ("incremental", 1, 1)
        assert subscription.next_run_at == clock.value + timedelta(seconds=300)


@pytest.mark.asyncio
async def test_new_head_during_backfill_restarts_drift_and_cannot_skip_reconciliation(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database, tmp_path, max_items=30)
    clock = support._Clock()
    policy = _policy()
    scheduler = DurableSchedulerService(database, clock=clock, bili_scan_continuation=policy)
    runner = bounded._SealedSyntheticUploads(count=67, max_items=30)
    new_head = BiliIdentity("999999", "BV9999999999", runner.identities[0].pubdate + 60)
    observed_phases: list[str] = []
    restarted_at: int | None = None

    for number in range(30):
        assert scheduler.tick(limit=1).materialized_count == 1
        result = await _worker(database, tmp_path, runner, clock, policy=policy).run_once(
            worker_id=f"drifting-discovery-{number}"
        )
        assert result.status == "succeeded"
        coverage = runner.coverages[-1]
        assert scheduler.tick(limit=1).materialized_count == 0
        await _qualify_delivery(database, clock, policy=policy)

        with database.session() as session:
            subscription = session.get(Subscription, subscription_id)
            progress = session.get(BiliSubscriptionProgress, subscription_id)
            assert subscription is not None and subscription.next_run_at is not None
            assert progress is not None
            observed_phases.append(progress.phase)
            if coverage.stop_reason == "restarted":
                restarted_at = number
                assert progress.phase == "backfill"
                assert progress.baseline_snapshot_at is None
            next_at = subscription.next_run_at

        # Shift every subsequent page by inserting a newer upload while both
        # lanes still retain bounded page witnesses from the initial backfill.
        if number == 0:
            runner.identities = (new_head, *runner.identities)
        if observed_phases[-1] == "incremental":
            break
        clock.value = next_at
    else:
        pytest.fail("drifting 68-upload fixture did not reach incremental phase")

    assert restarted_at is not None
    assert "reconciling" in observed_phases[restarted_at + 1 :]
    assert observed_phases[-1] == "incremental"
    assert any(item.stop_reason == "restarted" for item in runner.coverages)
    with database.session() as session:
        progress = session.get(BiliSubscriptionProgress, subscription_id)
        assert progress is not None
        assert progress.phase == "incremental" and progress.baseline_snapshot_at is not None
        assert progress.reconciliation_batch_count >= 1
        assert session.scalar(select(func.count()).select_from(Content)) == 68
        assert session.scalar(select(func.count()).select_from(Content).where(Content.remote_id == new_head.aid)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy", [_policy(0), BiliScanContinuationPolicy(), BiliScanContinuationPolicy(300, "e" * 40)]
)
async def test_disabled_unknown_or_changed_lock_keeps_ordinary_interval(
    database: Database,
    tmp_path: Path,
    policy: BiliScanContinuationPolicy,
) -> None:
    subscription_id = _seed(database, tmp_path)
    clock = support._Clock()
    DurableSchedulerService(database, clock=clock).tick()
    result = await _worker(database, tmp_path, bounded._SealedSyntheticUploads(), clock, policy=policy).run_once(
        worker_id="no-pace"
    )
    assert result.status == "succeeded"
    with database.session() as session:
        assert session.get(Subscription, subscription_id).next_run_at == clock.value + timedelta(seconds=21600)


@pytest.mark.asyncio
async def test_pending_success_then_pause_does_not_materialize_continuation(database: Database, tmp_path: Path) -> None:
    subscription_id = _seed(database, tmp_path)
    clock = support._Clock()
    scheduler = DurableSchedulerService(database, clock=clock, bili_scan_continuation=_policy())
    scheduler.tick()
    runner = bounded._SealedSyntheticUploads()
    result = await _worker(database, tmp_path, runner, clock).run_once(worker_id="pause-after-success")
    assert result.status == "succeeded"
    scheduler.pause_subscription(subscription_id)
    clock.value += timedelta(days=1)
    assert scheduler.tick().materialized_count == 0
    assert (await _worker(database, tmp_path, runner, clock).run_once(worker_id="paused")).status == "idle"
    assert len(runner.manifests) == 1


@pytest.mark.asyncio
async def test_failed_next_unit_does_not_accelerate_old_pending_checkpoint(database: Database, tmp_path: Path) -> None:
    subscription_id = _seed(database, tmp_path)
    clock = support._Clock()
    scheduler = DurableSchedulerService(database, clock=clock, bili_scan_continuation=_policy())
    scheduler.tick()
    result = await _worker(database, tmp_path, bounded._SealedSyntheticUploads(), clock).run_once(
        worker_id="success-first"
    )
    assert result.status == "succeeded"
    await _qualify_delivery(database, clock, policy=_policy())
    clock.value += timedelta(seconds=300)
    assert scheduler.tick().materialized_count == 1
    result = await _worker(database, tmp_path, bounded._SealedSyntheticUploads(tamper=True), clock).run_once(
        worker_id="failure-second"
    )
    assert (result.status, result.error_code) == ("failed_terminal", "output_security_failed")
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription.next_run_at == clock.value + timedelta(seconds=21600)
        assert subscription.checkpoint_revision == 1
        assert subscription.consecutive_failures == 1
        assert bounded._pipeline_count(session) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("reconcile", ["claim", "cancel"])
async def test_durable_success_reconciliation_uses_same_pacing_without_duplicate_pipeline_or_requests(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reconcile: str,
) -> None:
    subscription_id = _seed(database, tmp_path)
    clock = support._Clock()
    scheduler = DurableSchedulerService(database, clock=clock, bili_scan_continuation=_policy())
    scheduler.tick()
    original = SchedulerRepository.succeed

    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise OSError("synthetic finalization outage")

    monkeypatch.setattr(SchedulerRepository, "succeed", unavailable)
    runner = bounded._SealedSyntheticUploads()
    result = await _worker(database, tmp_path, runner, clock).run_once(worker_id="before-crash", lease_seconds=60)
    assert result.status == "fenced"
    with database.session() as session:
        job = session.get(Job, result.job_id)
        assert job is not None and job.status == "running"
        assert session.get(SyncRun, job.run_id).status == "succeeded"
        assert bounded._pipeline_count(session) == 0
    monkeypatch.setattr(SchedulerRepository, "succeed", original)
    clock.value += timedelta(seconds=61)
    if reconcile == "claim":
        assert (await _worker(database, tmp_path, runner, clock).run_once(worker_id="after-crash")).status == "idle"
    else:
        assert scheduler.cancel_job(result.job_id).status == "succeeded"
    with database.session() as session:
        assert session.get(Job, result.job_id).status == "succeeded"
        assert session.get(Subscription, subscription_id).next_run_at == clock.value + timedelta(seconds=21600)
        assert bounded._pipeline_count(session) == 1
        assert session.scalar(select(func.count()).select_from(SyncRun)) == 1
    await _qualify_delivery(database, clock, policy=_policy())
    with database.session() as session:
        assert session.get(Subscription, subscription_id).next_run_at == clock.value + timedelta(seconds=300)
        assert bounded._pipeline_count(session) == 1
    assert len(runner.manifests) == 1


@pytest.mark.asyncio
async def test_progress_publication_failure_rolls_back_pipeline_success_and_retry_advances_once(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscription_id = _seed(database, tmp_path)
    clock = support._Clock()
    policy = _policy()
    scheduler = DurableSchedulerService(database, clock=clock, bili_scan_continuation=policy)
    assert scheduler.tick().materialized_count == 1
    discovery = await _worker(database, tmp_path, bounded._SealedSyntheticUploads(), clock).run_once(
        worker_id="publication-failure-discovery"
    )
    assert discovery.status == "succeeded"

    with database.session() as session:
        pipeline = session.scalar(
            select(Job)
            .where(Job.job_type == "pipeline.subscription", Job.status == "queued")
            .order_by(Job.created_at, Job.id)
        )
        assert pipeline is not None and pipeline.subscription_id is not None and pipeline.run_id is not None
        subscription = session.get(Subscription, pipeline.subscription_id)
        assert subscription is not None
        observed = int(
            session.scalar(
                select(func.count())
                .select_from(SyncRunContent)
                .where(
                    SyncRunContent.run_id == pipeline.run_id,
                    SyncRunContent.subscription_id == subscription.id,
                )
            )
            or 0
        )
        assert observed > 0
        export = Job(
            id=str(uuid4()),
            job_type="export.emby",
            natural_key=f"publication-recovery-export:{pipeline.id}",
            payload={"author_id": subscription.author_id, "result": {"managed_file_count": 2}},
            status="succeeded",
            max_attempts=1,
            available_at=clock.value,
            finished_at=clock.value,
        )
        session.add(export)
        session.flush()
        receipt_fields = {
            "subscription_id": subscription.id,
            "account_id": subscription.account_id,
            "author_id": subscription.author_id,
            "platform": "bili",
            "export_job_id": export.id,
            "selected_asset_count": observed,
            "verified_asset_count": observed,
            "managed_file_count": 2,
            "directory_verified": True,
            "schema_version": 2,
            "source_run_id": pipeline.run_id,
            "observed_content_count": observed,
            "delivered_content_count": observed,
        }
        first_receipt = PipelineDeliveryReceipt(
            **receipt_fields,
            downloaded_count=observed,
            already_verified_count=0,
            publication_disposition="published",
        )
        retry_receipt = PipelineDeliveryReceipt(
            **receipt_fields,
            downloaded_count=0,
            already_verified_count=observed,
            publication_disposition="already_exported",
        )
        pipeline_job_id = pipeline.id

    handler_receipts: list[PipelineDeliveryReceipt] = []

    def handler(_claim: object) -> PipelineHandlerResult:
        receipt = first_receipt if not handler_receipts else retry_receipt
        handler_receipts.append(receipt)
        return PipelineHandlerResult.success(receipt)

    original_publish = BiliDeliveryProgressRepository.publish_success
    publish_attempts = 0

    def fail_first_publish(repository: BiliDeliveryProgressRepository, *args: Any, **kwargs: Any) -> Any:
        nonlocal publish_attempts
        publish_attempts += 1
        if publish_attempts == 1:
            raise OSError("synthetic progress publication outage")
        return original_publish(repository, *args, **kwargs)

    monkeypatch.setattr(BiliDeliveryProgressRepository, "publish_success", fail_first_publish)
    first = await PipelineSubscriptionWorker(
        database,
        handler,
        clock=clock,
        bili_delivery_policy=policy,
    ).run_once(worker_id="publication-failure-first")

    assert (first.status, first.error_code, first.receipt) == ("retry_wait", "pipeline_worker_error", None)
    with database.session() as session:
        job = session.get(Job, pipeline_job_id)
        progress = session.get(BiliSubscriptionProgress, subscription_id)
        assert job is not None and progress is not None
        assert (job.status, job.attempts, job.payload["schema_version"]) == ("retry_wait", 1, 1)
        assert (progress.batch_count, progress.last_pipeline_job_id) == (0, None)

    clock.value += timedelta(seconds=30)
    second = await PipelineSubscriptionWorker(
        database,
        handler,
        clock=clock,
        bili_delivery_policy=policy,
    ).run_once(worker_id="publication-failure-retry")

    assert second.status == "succeeded" and second.receipt == retry_receipt
    assert [item.publication_disposition for item in handler_receipts] == ["published", "already_exported"]
    assert [(item.downloaded_count, item.already_verified_count) for item in handler_receipts] == [
        (observed, 0),
        (0, observed),
    ]
    assert publish_attempts == 2
    with database.session() as session:
        job = session.get(Job, pipeline_job_id)
        progress = session.get(BiliSubscriptionProgress, subscription_id)
        subscription = session.get(Subscription, subscription_id)
        assert job is not None and progress is not None and subscription is not None
        assert (job.status, job.attempts) == ("succeeded", 2)
        assert (progress.batch_count, progress.last_pipeline_job_id) == (1, pipeline_job_id)
        assert subscription.next_run_at == clock.value + timedelta(seconds=300)


@pytest.mark.asyncio
async def test_blocked_exact_resume_preserves_source_end_generation_and_requires_current_terminal(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database, tmp_path)
    clock = support._Clock()
    scheduler = DurableSchedulerService(database, clock=clock, bili_scan_continuation=_policy())
    assert scheduler.tick().materialized_count == 1
    sync_result = await _worker(database, tmp_path, bounded._SealedSyntheticUploads(), clock).run_once(
        worker_id="terminal-source"
    )
    assert sync_result.status == "succeeded" and sync_result.run_id is not None
    with database.session() as session:
        progress = session.get(BiliSubscriptionProgress, subscription_id)
        assert progress is not None
        progress.phase = "reconciling"
        progress.source_end_observed_at = clock.value
        progress.source_end_run_id = sync_result.run_id
        progress.source_end_boundary_sha256 = "a" * 64
        generation_id = progress.generation_id

    pipeline_job_id = await _fail_delivery(database, clock, policy=_policy())
    with database.session() as session:
        progress = session.get(BiliSubscriptionProgress, subscription_id)
        subscription = session.get(Subscription, subscription_id)
        assert progress is not None and subscription is not None
        assert (progress.phase, progress.blocked_code, progress.next_eligible_at) == (
            "blocked",
            "pipeline_download_terminal",
            None,
        )
        assert progress.source_end_run_id == sync_result.run_id and progress.generation_id == generation_id
        expected_schedule_revision = subscription.schedule_revision
        assert (
            SchedulerRepository(session, bili_scan_continuation=_policy()).materialize_due(
                limit=1,
                now=clock.value,
            )
            == []
        )

    with database.session() as session:
        cycle = SchedulerRepository(session, bili_scan_continuation=_policy()).materialize_one(
            subscription_id,
            expected_schedule_revision=expected_schedule_revision,
            now=clock.value,
        )
        progress = session.get(BiliSubscriptionProgress, subscription_id)
        assert cycle.subscription_id == subscription_id
        assert progress is not None
        assert (progress.phase, progress.blocked_code, progress.generation_id) == (
            "reconciling",
            None,
            generation_id,
        )
        assert progress.source_end_run_id == sync_result.run_id
        assert session.get(Job, pipeline_job_id).status == "failed_terminal"


@pytest.mark.asyncio
async def test_terminal_pipeline_from_old_auth_generation_cannot_block_rebound_progress(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database, tmp_path)
    clock = support._Clock()
    scheduler = DurableSchedulerService(database, clock=clock, bili_scan_continuation=_policy())
    assert scheduler.tick().materialized_count == 1
    sync_result = await _worker(database, tmp_path, bounded._SealedSyntheticUploads(), clock).run_once(
        worker_id="old-generation"
    )
    assert sync_result.status == "succeeded"

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        old_generation = subscription.bili_delivery_progress.generation_id
        subscription.account.auth_revision += 1
        rebound = BiliDeliveryProgressRepository(session).ensure_for_materialization(
            subscription,
            upstream_sha=support.PINNED_SHA,
            schedule_revision=subscription.schedule_revision,
            now=clock.value,
            resume_blocked=True,
        )
        assert rebound is not None and rebound.generation_id != old_generation
        rebound_generation = rebound.generation_id

    await _fail_delivery(database, clock, policy=_policy())
    with database.session() as session:
        progress = session.get(BiliSubscriptionProgress, subscription_id)
        assert progress is not None
        assert (progress.phase, progress.blocked_code, progress.generation_id) == (
            "backfill",
            None,
            rebound_generation,
        )


@pytest.mark.asyncio
async def test_rebinding_with_an_invalid_preserved_cursor_falls_back_to_fresh_backfill(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database, tmp_path)
    clock = support._Clock()
    scheduler = DurableSchedulerService(database, clock=clock, bili_scan_continuation=_policy())
    assert scheduler.tick().materialized_count == 1
    sync_result = await _worker(database, tmp_path, bounded._SealedSyntheticUploads(), clock).run_once(
        worker_id="invalid-preserved-cursor"
    )
    assert sync_result.status == "succeeded" and sync_result.run_id is not None

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        progress = session.get(BiliSubscriptionProgress, subscription_id)
        assert subscription is not None and progress is not None
        progress.phase = "incremental"
        progress.source_end_observed_at = clock.value
        progress.source_end_run_id = sync_result.run_id
        progress.source_end_boundary_sha256 = "a" * 64
        progress.reconciled_at = clock.value
        progress.reconciliation_run_id = sync_result.run_id
        progress.baseline_snapshot_at = clock.value
        subscription.cursor = {"value": "invalid-preserved-cursor"}
        previous_revision = subscription.checkpoint_revision
        subscription.account.auth_revision += 1

        rebound = BiliDeliveryProgressRepository(session).ensure_for_materialization(
            subscription,
            upstream_sha=support.PINNED_SHA,
            schedule_revision=subscription.schedule_revision,
            now=clock.value,
            resume_blocked=True,
        )

        assert rebound is not None
        assert (rebound.phase, rebound.source_end_observed_at, rebound.baseline_snapshot_at) == (
            "backfill",
            None,
            None,
        )
        assert subscription.cursor is None
        assert subscription.checkpoint_revision == previous_revision + 1
