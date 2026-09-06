"""Offline real worker/ingestion/checkpoint scheduling with sealed observations."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.models import Job, Subscription, SyncRun
from media_sync.scheduler.bili_scan_continuation import BiliScanContinuationPolicy
from media_sync.scheduler.handlers import SubscriptionHandlerRegistry
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


def _seed(database: Database, tmp_path: Path) -> str:
    identifier = bounded._seed(database, tmp_path)
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
    for number in range(8):
        started_at = clock.value
        assert scheduler.tick(limit=1).materialized_count == 1
        result = await _worker(database, tmp_path, runner, clock).run_once(worker_id=f"paced-{number}")
        assert result.status == "succeeded"
        assert len(runner.manifests) == number + 1
        assert runner.manifests[-1].bili_scan_input_cursor == previous_cursor
        coverage = runner.coverages[-1]
        assert coverage.list_attempts <= 2 and coverage.detail_attempts <= 1
        with database.session() as session:
            subscription = session.get(Subscription, subscription_id)
            run = session.get(SyncRun, result.run_id)
            assert subscription is not None and subscription.next_run_at is not None and run is not None
            assert subscription.cursor == run.cursor_after == {"value": coverage.next_state.to_cursor()}
            assert subscription.checkpoint_revision == number + 1
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
    assert delays == [300] * 7 + [21600]
    assert [coverage.lane for coverage in runner.coverages] == ["head", "history"] * 4


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
        assert session.get(Subscription, subscription_id).next_run_at == clock.value + timedelta(seconds=300)
        assert bounded._pipeline_count(session) == 1
        assert session.scalar(select(func.count()).select_from(SyncRun)) == 1
    assert len(runner.manifests) == 1
