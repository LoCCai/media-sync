"""Real scheduler/bridge/seal/normalizer/DB with synthetic upload observations."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path
from threading import Event
from typing import Any
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import func, select

from media_sync.application.mediacrawler import load_normalized_output
from media_sync.domain import LoginMethod, Platform
from media_sync.infrastructure.db import Database, MediaCrawlerIngestionService, SubscriptionRepository
from media_sync.infrastructure.db.models import AssetRefreshSource, Content, Job, Subscription, SyncRun
from media_sync.integrations.mediacrawler.bilibili_scan import (
    BILI_SCAN_COVERAGE_FILENAME,
    BILI_SCAN_IDENTITY_FIELD,
    BiliIdentity,
    BiliPage,
    BiliScanCoverage,
    BiliScanState,
    BiliScanUnit,
)
from media_sync.integrations.mediacrawler.bridge import (
    BridgeRequest,
    MediaCrawlerRunMode,
    MediaCrawlerRunSpec,
    RunnerManifest,
)
from media_sync.integrations.mediacrawler.policies import build_run_paths, inspect_output
from media_sync.integrations.mediacrawler.receipt import load_validated_output_snapshot, write_completion_receipt
from media_sync.integrations.mediacrawler.runner import MediaCrawlerProcessResult, MediaCrawlerProcessStatus
from media_sync.scheduler.handlers import SubscriptionHandlerRegistry
from media_sync.scheduler.repository import SchedulerRepository
from media_sync.scheduler.service import DurableSchedulerService, SubscriptionWorker
from media_sync.security import SecretValue
from tests.integration import test_mediacrawler_scheduler_handler as support


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'bili-scheduler.sqlite3').as_posix()}")
    instance.create_schema()
    yield instance
    instance.dispose()


class _SealedSyntheticUploads:
    """Replace only remote I/O, retaining actual manifest and sealed artifacts.

    The separate inherited protocol suite executes the real child supervisor;
    this deterministic composition exercises durable continuation cheaply.
    """

    def __init__(self, *, empty: bool = False, tamper: bool = False) -> None:
        self.identities = (
            ()
            if empty
            else tuple(BiliIdentity(str(1000 + index), f"BV{index:010d}", 1767225600 - index) for index in range(3))
        )
        self.tamper = tamper
        self.manifests: list[RunnerManifest] = []
        self.coverages: list[BiliScanCoverage] = []

    def run(self, spec: MediaCrawlerRunSpec, cancellation: Event | None = None) -> MediaCrawlerProcessResult:
        assert cancellation is not None and not cancellation.is_set()
        manifest = RunnerManifest.load(spec.paths.manifest_path)
        assert manifest == spec.manifest and manifest.bili_scan is not None
        assert manifest.max_items == 1 and manifest.allow_full_history is False
        self.manifests.append(manifest)
        unit = BiliScanUnit(manifest.bili_scan, manifest.max_items)
        rows: list[dict[str, object]] = []
        while (action := unit.next_action()).kind != "stop":
            if action.kind == "list":
                assert action.page is not None
                start = (action.page - 1) * 30
                unit.observe_page(BiliPage(action.page, len(self.identities), self.identities[start : start + 30]))
            else:
                identity = action.identity
                assert identity is not None and identity in self.identities
                rows.append(
                    {
                        "video_id": identity.aid,
                        "create_time": identity.pubdate,
                        "title": "Synthetic bounded scheduler upload",
                        "video_url": f"https://www.bilibili.com/video/av{identity.aid}",
                        BILI_SCAN_IDENTITY_FIELD: {
                            **identity.as_mapping(),
                            "author_fingerprint_sha256": manifest.author_remote_id_fingerprint_sha256,
                        },
                    }
                )
                unit.consume(identity)
        coverage = unit.coverage()
        self.coverages.append(coverage)
        if rows:
            if self.tamper:
                rows[0]["create_time"] = 1767225999
            (manifest.output_root / "uploads.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in rows),
                encoding="utf-8",
                newline="\n",
            )
        (manifest.output_root / BILI_SCAN_COVERAGE_FILENAME).write_text(
            coverage.to_json_line(),
            encoding="utf-8",
            newline="\n",
        )
        write_completion_receipt(manifest, inspect_output(manifest.output_root, manifest.watchdogs), known_secrets=())
        snapshot = load_validated_output_snapshot(manifest)
        assert snapshot.receipt.sync_run_id == manifest.sync_run_id
        return MediaCrawlerProcessResult(MediaCrawlerProcessStatus.SUCCEEDED, "Synthetic sealed upload unit")


def _seed(database: Database, runtime_root: Path, *, login_method: LoginMethod = LoginMethod.COOKIE) -> str:
    subscription_id = support._seed(
        database,
        creator_remote_id="252671524",
        login_method=login_method,
        credential_ref="env:SYNTHETIC_BILI_COOKIE" if login_method is LoginMethod.COOKIE else None,
    )
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        subscription.max_items = 1
        subscription.policy = {
            "mediacrawler": {**subscription.policy["mediacrawler"], "allow_full_history": False},
        }
        subscription.watermarked_at = support.NOW
        subscription.watermark_remote_ids = ["legacy-does-not-prove-coverage"]
        if login_method is LoginMethod.SAVED_SESSION:
            paths = build_run_paths(runtime_root, Platform.BILI, UUID(subscription.account_id), uuid4())
            paths.profile_root.mkdir(parents=True)
            (paths.profile_root / "Synthetic-profile-marker").write_text("offline only", encoding="utf-8")
    return subscription_id


def _worker(
    database: Database,
    runtime_root: Path,
    runner: _SealedSyntheticUploads,
    clock: support._Clock,
    *,
    ingestion_factory: Callable[[Database], object] = MediaCrawlerIngestionService,
    normalizer: Callable[..., Any] = load_normalized_output,
) -> SubscriptionWorker:
    handler = support._protocol_handler(
        database,
        runtime_root,
        runner=runner,
        clock=clock,
        ingestion_factory=ingestion_factory,
        normalizer=normalizer,
    )
    return SubscriptionWorker(database, SubscriptionHandlerRegistry({"mediacrawler": handler}), clock=clock)


def _pipeline_count(session: Any) -> int:
    return session.scalar(select(func.count()).select_from(Job).where(Job.job_type == "pipeline.subscription"))


@pytest.mark.asyncio
@pytest.mark.parametrize("login_method", [LoginMethod.COOKIE, LoginMethod.SAVED_SESSION])
async def test_max_items_one_continues_after_worker_restarts_without_history_ack_or_watermark_loss(
    database: Database,
    tmp_path: Path,
    login_method: LoginMethod,
) -> None:
    runtime_root = (tmp_path / "runtime").resolve()
    subscription_id = _seed(database, runtime_root, login_method=login_method)
    clock = support._Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    runner = _SealedSyntheticUploads()
    previous_cursor = None
    for number in range(8):
        assert scheduler.tick(limit=1).materialized_count == 1
        # A new handler/worker reads state from SQLite each time.
        result = await _worker(database, runtime_root, runner, clock).run_once(worker_id=f"bounded-{number}")
        assert (result.status, result.error_code) == ("succeeded", None)
        manifest = runner.manifests[-1]
        assert manifest.bili_scan_input_cursor == previous_cursor
        coverage = runner.coverages[-1]
        assert coverage.detail_attempts <= 1 and coverage.list_attempts <= 2
        with database.session() as session:
            subscription = session.get(Subscription, subscription_id)
            run = session.get(SyncRun, result.run_id)
            assert subscription is not None and run is not None
            assert subscription.cursor == {"value": coverage.next_state.to_cursor()}
            assert run.cursor_before == (None if previous_cursor is None else {"value": previous_cursor})
            assert run.cursor_after == subscription.cursor
            previous_cursor = subscription.cursor["value"]
            assert subscription.checkpoint_revision == number + 1
            assert subscription.watermarked_at == support.NOW
            assert subscription.watermark_remote_ids == ["legacy-does-not-prove-coverage"]
            assert _pipeline_count(session) == number + 1
            assert subscription.next_run_at is not None
            clock.value = subscription.next_run_at + timedelta(seconds=1)
        assert not manifest.job_root.exists()
    with database.session() as session:
        assert set(session.scalars(select(Content.remote_id))) == {identity.aid for identity in runner.identities}
        assert session.scalar(select(func.count()).select_from(AssetRefreshSource)) == 3
        assert set(session.scalars(select(Job.status).where(Job.job_type == "pipeline.subscription"))) == {"queued"}
    assert {coverage.stop_reason for coverage in runner.coverages} == {"item_limit", "source_end"}
    assert BiliScanState.from_cursor(previous_cursor).head_boundary == runner.identities[0].pubdate


class _LoseCommitAcknowledgement(MediaCrawlerIngestionService):
    def ingest_bili_bounded(self, *args: Any, **kwargs: Any) -> Any:
        super().ingest_bili_bounded(*args, **kwargs)
        raise OSError("synthetic post-commit acknowledgement loss")


@pytest.mark.asyncio
async def test_committed_run_wins_over_lost_ack_and_finalize_retry_enqueues_pipeline_once(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = (tmp_path / "runtime").resolve()
    _seed(database, runtime_root)
    clock = support._Clock()
    DurableSchedulerService(database, clock=clock).tick(limit=1)
    original = SchedulerRepository.succeed
    calls = 0

    def fail_first_finalization(self: SchedulerRepository, *args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("synthetic finalization failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(SchedulerRepository, "succeed", fail_first_finalization)
    runner = _SealedSyntheticUploads()
    result = await _worker(
        database,
        runtime_root,
        runner,
        clock,
        ingestion_factory=_LoseCommitAcknowledgement,
    ).run_once(worker_id="bounded-lost-ack")
    assert (result.status, result.error_code) == ("succeeded", None)
    assert calls == 2 and len(runner.manifests) == 1
    with database.session() as session:
        assert session.get(SyncRun, result.run_id).status == "succeeded"
        assert session.scalar(select(Subscription.checkpoint_revision)) == 1
        assert session.scalar(select(func.count()).select_from(Content)) == _pipeline_count(session) == 1
    # Repeated cancellation of a succeeded Job must reconcile, not add work.
    scheduler = DurableSchedulerService(database, clock=clock)
    scheduler.cancel_job(result.job_id)
    scheduler.cancel_job(result.job_id)
    with database.session() as session:
        assert _pipeline_count(session) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [False, True])
async def test_zero_content_checkpoint_and_tampered_output_have_distinct_durable_outcomes(
    database: Database,
    tmp_path: Path,
    empty: bool,
) -> None:
    runtime_root = (tmp_path / "runtime").resolve()
    _seed(database, runtime_root)
    clock = support._Clock()
    DurableSchedulerService(database, clock=clock).tick(limit=1)
    runner = _SealedSyntheticUploads(empty=empty, tamper=not empty)
    result = await _worker(database, runtime_root, runner, clock).run_once(worker_id="bounded-empty-or-tamper")
    assert result.status == ("succeeded" if empty else "failed_terminal")
    assert result.error_code == (None if empty else "output_security_failed")
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        assert session.scalar(select(Subscription.checkpoint_revision)) == (1 if empty else 0)
        assert _pipeline_count(session) == (1 if empty else 0)


class _WaitBeforeBoundedIngestion(MediaCrawlerIngestionService):
    def __init__(self, database: Database, entered: Event, release: Event) -> None:
        super().__init__(database)
        self.entered = entered
        self.release = release

    def ingest_bili_bounded(self, *args: Any, **kwargs: Any) -> Any:
        self.entered.set()
        assert self.release.wait(timeout=10)
        return super().ingest_bili_bounded(*args, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["task_cancel", "lease_cancel", "checkpoint_conflict"])
async def test_cancel_lease_or_checkpoint_conflict_cannot_consume_sealed_pending_identity(
    database: Database,
    tmp_path: Path,
    stop: str,
) -> None:
    runtime_root = (tmp_path / "runtime").resolve()
    subscription_id = _seed(database, runtime_root)
    clock = support._Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    scheduler.tick(limit=1)
    runner = _SealedSyntheticUploads()
    entered, release = Event(), Event()
    worker = _worker(
        database,
        runtime_root,
        runner,
        clock,
        ingestion_factory=lambda active: _WaitBeforeBoundedIngestion(active, entered, release),
    )
    task = asyncio.create_task(worker.run_once(worker_id=f"bounded-{stop}"))
    try:
        assert await asyncio.to_thread(entered.wait, 10)
        with database.session() as session:
            job_id = session.scalar(select(Job.id).where(Job.job_type == "sync.subscription"))
        assert job_id is not None
        if stop == "task_cancel":
            task.cancel()
            await asyncio.sleep(0)
        elif stop == "lease_cancel":
            scheduler.cancel_job(job_id)
        else:
            with database.session() as session:
                SubscriptionRepository(session).publish_checkpoint(
                    subscription_id,
                    expected_revision=0,
                    cursor={"value": "newer-external-cursor"},
                )
    finally:
        release.set()
    if stop == "task_cancel":
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        result = await task
        assert result.status == ("cancelled" if stop == "lease_cancel" else "retry_wait")
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        assert subscription.cursor == ({"value": "newer-external-cursor"} if stop == "checkpoint_conflict" else None)
        assert subscription.checkpoint_revision == (1 if stop == "checkpoint_conflict" else 0)
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        assert session.scalar(select(func.count()).select_from(AssetRefreshSource)) == _pipeline_count(session) == 0
    assert not runner.manifests[0].job_root.exists()


@pytest.mark.asyncio
async def test_actual_bounded_sealed_recovery_uses_atomic_ingestion_without_another_capture(
    database: Database,
    tmp_path: Path,
) -> None:
    runtime_root = (tmp_path / "runtime").resolve()
    subscription_id = _seed(database, runtime_root)
    clock = support._Clock()
    assert DurableSchedulerService(database, clock=clock).tick(limit=1).materialized_count == 1
    with database.session() as session:
        repository = SchedulerRepository(session)
        claim = repository.claim_next(
            worker_id="crashed-before-ingestion",
            global_capacity=1,
            lease_seconds=1,
            now=clock(),
        )
        assert claim is not None and claim.attempt == 1
        claim = repository.start(
            claim.job_id,
            worker_id="crashed-before-ingestion",
            lease_token=claim.lease_token,
            now=clock(),
        )
    context_loader = SubscriptionWorker(database, SubscriptionHandlerRegistry({}), clock=clock)
    context, handler_key = context_loader._load_context(claim, worker_id="crashed-before-ingestion")
    assert context is not None and handler_key == "mediacrawler"
    runner = _SealedSyntheticUploads()
    first_handler = support._protocol_handler(database, runtime_root, runner=runner, clock=clock)
    execution_id = uuid5(context.job_id, "media-sync/mediacrawler/attempt/1")
    paths = build_run_paths(runtime_root, Platform.BILI, context.account.account_id, execution_id)
    prepared = first_handler._create_attached_run(context, execution_id=execution_id, attempt_paths=paths)
    # Stop the first attempt at the precise durable seam after real sealing,
    # before normalization/ingestion. No handler exception cleanup is invoked.
    spec = first_handler.bridge.prepare(
        BridgeRequest(
            lock_path=first_handler.lock_path,
            integration_root=runtime_root,
            python_executable=first_handler.python_executable,
            account_id=context.account.account_id,
            subscription_id=context.subscription_id,
            job_id=context.job_id,
            scheduler_job_id=context.job_id,
            schedule_revision=context.schedule_revision,
            attempt=context.attempt,
            execution_id=execution_id,
            sync_run_id=prepared.run_id,
            checkpoint_revision_before=prepared.checkpoint_revision,
            intended_mode=MediaCrawlerRunMode.FORWARD,
            platform=Platform.BILI,
            login_method=LoginMethod.COOKIE,
            author_remote_id=prepared.creator_remote_id,
            creator_reference=prepared.creator_remote_id,
            cookie=SecretValue("session=synthetic-offline"),
            license_acknowledged=True,
            allow_full_history=False,
            headless=True,
            max_items=1,
            watchdogs=first_handler.watchdogs,
            request_delay_seconds=3.5,
            bili_bounded_capture=True,
            bili_scan_cursor_before=prepared.cursor_before,
        )
    )
    assert runner.run(spec, Event()).succeeded
    original_manifest = RunnerManifest.load(paths.manifest_path)
    original_snapshot = load_validated_output_snapshot(original_manifest)
    assert original_manifest.bili_scan is not None
    assert original_snapshot.receipt.sync_run_id == prepared.run_id
    with database.session() as session:
        assert session.get(SyncRun, str(prepared.run_id)).status == "running"
        assert session.get(Subscription, subscription_id).cursor is None
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        assert _pipeline_count(session) == 0

    calls: list[dict[str, Any]] = []

    class BoundedOnlyIngestion(MediaCrawlerIngestionService):
        def ingest(self, *args: Any, **kwargs: Any) -> Any:
            pytest.fail("bounded recovery must not use legacy watermark ingestion")

        def ingest_bili_bounded(self, *args: Any, **kwargs: Any) -> Any:
            calls.append(kwargs.copy())
            return super().ingest_bili_bounded(*args, **kwargs)

    # Reclaim the real expired lease using a new worker/handler. The real
    # manifest loader, checkout verifier, receipt and normalizer stay enabled.
    clock.value += timedelta(seconds=5)
    result = await _worker(
        database,
        runtime_root,
        runner,
        clock,
        ingestion_factory=BoundedOnlyIngestion,
    ).run_once(worker_id="bounded-sealed-recovery")
    assert (result.status, result.error_code) == ("succeeded", None)
    assert result.job_id == claim.job_id and result.run_id != str(prepared.run_id)
    assert len(runner.manifests) == 1 and len(calls) == 1
    assert calls[0]["input_cursor"] is None
    assert calls[0]["expected_revision"] == calls[0]["crawl_revision_before"] == 0
    assert calls[0]["next_cursor"] == runner.coverages[0].next_state.to_cursor()
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        old_run = session.get(SyncRun, str(prepared.run_id))
        recovered_run = session.get(SyncRun, result.run_id)
        job = session.get(Job, result.job_id)
        assert subscription is not None and old_run is not None and recovered_run is not None and job is not None
        assert old_run.status == "cancelled" and old_run.error_code == "scheduler_lease_lost"
        assert old_run.cursor_after is None and old_run.checkpoint_revision_after is None
        assert recovered_run.status == "succeeded" and recovered_run.attempt == job.attempts == 2
        assert recovered_run.manifest["recovered_artifact"] == {
            "schema_version": original_manifest.schema_version,
            "attempt": 1,
            "execution_id": str(execution_id),
            "sync_run_id": str(prepared.run_id),
        }
        assert recovered_run.cursor_before is None
        assert recovered_run.cursor_after == subscription.cursor == {"value": calls[0]["next_cursor"]}
        assert recovered_run.checkpoint_revision_after == subscription.checkpoint_revision == 1
        assert subscription.watermarked_at == support.NOW
        assert subscription.watermark_remote_ids == ["legacy-does-not-prove-coverage"]
        assert session.scalar(select(func.count()).select_from(Content)) == 1
        observation = session.scalar(select(AssetRefreshSource))
        assert observation is not None and observation.last_run_id == result.run_id
        assert _pipeline_count(session) == 1
    assert not paths.job_root.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("lose_acknowledgement", [False, True])
async def test_exact_success_survives_a_later_checkpoint_without_overwriting_it(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lose_acknowledgement: bool,
) -> None:
    runtime_root = (tmp_path / "runtime").resolve()
    subscription_id = _seed(database, runtime_root)
    clock = support._Clock()
    assert DurableSchedulerService(database, clock=clock).tick(limit=1).materialized_count == 1
    later_cursor = {"value": "unrelated-newer-checkpoint"}

    class AdvanceAfterCommit(MediaCrawlerIngestionService):
        def ingest_bili_bounded(self, *args: Any, **kwargs: Any) -> Any:
            result = super().ingest_bili_bounded(*args, **kwargs)
            # Model an independent, authorized checkpoint publication after
            # this exact Run committed but before its caller receives the ack.
            with self.database.session() as session:
                run = session.get(SyncRun, str(kwargs["run_id"]))
                assert run is not None and run.status == "succeeded" and run.checkpoint_revision_after == 1
                SubscriptionRepository(session).publish_checkpoint(
                    subscription_id,
                    expected_revision=1,
                    cursor=later_cursor,
                )
            if lose_acknowledgement:
                raise OSError("synthetic acknowledgement lost after later checkpoint")
            return result

    runner = _SealedSyntheticUploads()
    handler = support._protocol_handler(
        database,
        runtime_root,
        runner=runner,
        clock=clock,
        ingestion_factory=AdvanceAfterCommit,
    )
    actual_run = handler.run
    observed = []

    async def observe_handler(context: Any) -> Any:
        result = await actual_run(context)
        observed.append(result)
        return result

    monkeypatch.setattr(handler, "run", observe_handler)
    worker = SubscriptionWorker(database, SubscriptionHandlerRegistry({"mediacrawler": handler}), clock=clock)
    result = await worker.run_once(worker_id="bounded-newer-checkpoint")
    # Assert the handler itself succeeded: scheduler reconciliation of a
    # failed handler must not hide an incorrect exact-Run readback predicate.
    assert len(observed) == 1 and observed[0].succeeded and observed[0].error_code is None
    assert (result.status, result.error_code) == ("succeeded", None)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        run = session.get(SyncRun, result.run_id)
        assert subscription is not None and run is not None
        assert subscription.checkpoint_revision == 2 and subscription.cursor == later_cursor
        assert run.status == "succeeded" and run.checkpoint_revision_before == 0 and run.checkpoint_revision_after == 1
        assert run.cursor_before is None
        assert run.cursor_after == {"value": runner.coverages[0].next_state.to_cursor()}
        assert run.cursor_after != subscription.cursor
        assert session.scalar(select(func.count()).select_from(Content)) == 1
        assert session.scalar(select(AssetRefreshSource.last_run_id)) == result.run_id
        assert _pipeline_count(session) == 1
    assert not runner.manifests[0].job_root.exists()
