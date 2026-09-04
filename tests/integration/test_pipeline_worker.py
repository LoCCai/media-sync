"""Offline integration coverage for bounded pipeline coordinator workers."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event as ThreadEvent
from typing import cast

import pytest
from sqlalchemy import func, select

from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    JobRepository,
    SubscriptionRepository,
    SyncRunRepository,
    new_uuid,
)
from media_sync.infrastructure.db.models import Job
from media_sync.scheduler.pipeline import PipelineJobRepository, PipelineSubscriptionClaim
from media_sync.scheduler.pipeline_worker import (
    PipelineHandler,
    PipelineHandlerResult,
    PipelineSubscriptionWorker,
    classify_pipeline_failure,
)
from media_sync.scheduler.policy import RetryPolicy
from media_sync.scheduler.repository import SCHEDULE_PAYLOAD_SCHEMA_VERSION

NOW = datetime(2026, 8, 31, 2, 30, tzinfo=UTC)
SECRET = "SENTINEL-pipeline-worker-exception-secret"


def test_download_result_scope_mismatch_is_fixed_terminal_worker_failure() -> None:
    classification = classify_pipeline_failure("pipeline_download_result_scope_mismatch")

    assert classification.retryable is False


@pytest.mark.parametrize(
    "error_code",
    [
        "pipeline_mediacrawler_not_enabled",
        "pipeline_mediacrawler_license_required",
        "pipeline_mediacrawler_runtime_unavailable",
        "pipeline_xhs_detail_authority_required",
        "pipeline_media_probe_unavailable",
    ],
)
def test_runtime_preflight_failures_are_fixed_retryable_worker_results(error_code: str) -> None:
    assert classify_pipeline_failure(error_code).retryable is True


@pytest.mark.parametrize(
    ("error_code", "retryable"),
    [
        ("pipeline_locator_refresh_configuration_invalid", False),
        ("pipeline_locator_refresh_credentials_unavailable", True),
        ("pipeline_locator_refresh_temporary", True),
        ("pipeline_locator_refresh_asset_not_found", False),
        ("pipeline_locator_refresh_retryable", True),
        ("pipeline_locator_refresh_terminal", False),
    ],
)
def test_locator_refresh_preflight_failures_keep_closed_worker_retryability(
    error_code: str,
    retryable: bool,
) -> None:
    assert classify_pipeline_failure(error_code).retryable is retryable


class _Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class _SequenceClock:
    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)

    def __call__(self) -> datetime:
        return next(self._values)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'pipeline-worker.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_pipeline(database: Database, *, remote_id: str) -> tuple[str, str, str, str, str]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter="fake",
            display_name=f"pipeline-account-{remote_id}",
            login_method="qr",
            auth_status="authenticated",
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="bili", remote_id=remote_id, display_name=f"pipeline-author-{remote_id}")
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            interval_seconds=60,
            next_run_at=NOW + timedelta(hours=1),
            policy={"handler": "fake"},
        )
        runs = SyncRunRepository(session)
        run = runs.create(subscription_id=subscription.id, attempt=1)
        runs.set_status(run.id, "claimed", expected_status="queued", at=NOW)
        runs.set_status(run.id, "running", expected_status="claimed", at=NOW)
        runs.set_status(run.id, "ingesting", expected_status="running", at=NOW)
        runs.set_status(run.id, "succeeded", expected_status="ingesting", at=NOW)
        retry_policy = RetryPolicy()
        source = JobRepository(session).enqueue(
            job_type="sync.subscription",
            natural_key=f"subscription:{subscription.id}:schedule:{subscription.schedule_revision}",
            payload={
                "schema_version": SCHEDULE_PAYLOAD_SCHEMA_VERSION,
                "subscription_id": subscription.id,
                "schedule_revision": subscription.schedule_revision,
                "retry_policy": retry_policy.to_payload(),
            },
            run_id=run.id,
            subscription_id=subscription.id,
            account_id=account.id,
            platform="bili",
            max_attempts=retry_policy.max_attempts,
            available_at=NOW,
        )
        source.status = "succeeded"
        source.finished_at = NOW
        session.flush()
        coordinator = PipelineJobRepository(session).enqueue_succeeded_sync(
            source.id,
            run_id=run.id,
            now=NOW,
        )
        return coordinator.job_id, source.id, subscription.id, account.id, run.id


@pytest.mark.asyncio
async def test_subject_hook_failure_rolls_back_pipeline_claim_before_handler(database: Database) -> None:
    coordinator_id, _source_id, _subscription_id, _account_id, _run_id = _seed_pipeline(
        database,
        remote_id="subject-hook-rollback",
    )
    handler_called = False
    observed_subjects: list[tuple[str, str, str]] = []

    def handler(_claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        nonlocal handler_called
        handler_called = True
        return PipelineHandlerResult.success()

    def fail_hook(session: object, subject: object) -> None:
        observed_subjects.append((subject.subject_type, subject.subject_id, subject.role))
        claimed = session.get(Job, subject.subject_id)
        assert claimed is not None and claimed.status == "claimed"
        raise RuntimeError("subject hook failure")

    worker = PipelineSubscriptionWorker(database, handler, clock=_Clock())
    with pytest.raises(RuntimeError, match="subject hook failure"):
        await worker.run_once(worker_id="hook-worker", subject_hook=fail_hook)  # type: ignore[arg-type]

    assert handler_called is False
    assert observed_subjects == [("job", coordinator_id, "execution")]
    with database.session() as session:
        job = session.get(Job, coordinator_id)
        assert job is not None
        assert (job.status, job.attempts, job.lease_owner, job.lease_token) == ("queued", 0, None, None)


@pytest.mark.asyncio
async def test_worker_is_idle_and_never_claims_a_foreign_job(database: Database) -> None:
    called = False

    def handler(_claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        nonlocal called
        called = True
        return PipelineHandlerResult.success()

    with database.session() as session:
        foreign = JobRepository(session).enqueue(
            job_type="asset_download",
            natural_key="pipeline-worker-foreign",
            payload={"marker": "foreign-value"},
            available_at=NOW,
        )
        foreign_id = foreign.id

    result = await PipelineSubscriptionWorker(database, handler, clock=_Clock()).run_once(
        worker_id="pipeline-idle-worker"
    )

    assert result.status == "idle"
    assert called is False
    with database.session() as session:
        foreign = session.get(Job, foreign_id)
        assert foreign is not None
        assert (foreign.status, foreign.attempts, foreign.payload) == (
            "queued",
            0,
            {"marker": "foreign-value"},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("async_handler", [False, True], ids=["sync-handler", "async-handler"])
async def test_worker_passes_exact_claim_and_completes_success(
    database: Database,
    async_handler: bool,
) -> None:
    coordinator_id, source_id, subscription_id, account_id, run_id = _seed_pipeline(
        database,
        remote_id=f"success-{async_handler}",
    )
    claims: list[PipelineSubscriptionClaim] = []

    def sync_handler(claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        claims.append(claim)
        return PipelineHandlerResult.success()

    async def async_handler_impl(claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        claims.append(claim)
        return PipelineHandlerResult.success()

    handler: PipelineHandler = async_handler_impl if async_handler else sync_handler
    result = await PipelineSubscriptionWorker(database, handler, clock=_Clock()).run_once(
        worker_id="pipeline-success-worker"
    )

    assert (result.job_id, result.subscription_id, result.status, result.attempt, result.error_code) == (
        coordinator_id,
        subscription_id,
        "succeeded",
        1,
        None,
    )
    assert len(claims) == 1
    claim = claims[0]
    assert (
        claim.job_id,
        claim.sync_job_id,
        claim.subscription_id,
        claim.account_id,
        claim.platform,
        claim.run_id,
    ) == (coordinator_id, source_id, subscription_id, account_id, "bili", run_id)
    with database.session() as session:
        job = session.get(Job, coordinator_id)
        assert job is not None
        assert job.status == "succeeded"
        assert job.lease_owner is None and job.lease_token is None and job.lease_expires_at is None


@pytest.mark.asyncio
async def test_retryable_result_uses_fixed_delay_and_does_not_spin(database: Database) -> None:
    coordinator_id, _source_id, subscription_id, _account_id, _run_id = _seed_pipeline(
        database,
        remote_id="retryable",
    )
    clock = _Clock()

    def handler(_claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        return PipelineHandlerResult.failure("pipeline_asset_not_verified")

    worker = PipelineSubscriptionWorker(database, handler, clock=clock, retry_delay_seconds=17)
    result = await worker.run_once(worker_id="pipeline-retry-worker")
    idle = await worker.run_once(worker_id="pipeline-retry-worker")

    assert (result.job_id, result.subscription_id, result.status, result.error_code) == (
        coordinator_id,
        subscription_id,
        "retry_wait",
        "pipeline_asset_not_verified",
    )
    assert idle.status == "idle"
    with database.session() as session:
        job = session.get(Job, coordinator_id)
        assert job is not None
        assert job.available_at == NOW + timedelta(seconds=17)
        assert job.finished_at is None
        assert job.last_error_message == "an asset is not durably verified"


@pytest.mark.asyncio
async def test_terminal_result_never_requeues(database: Database) -> None:
    coordinator_id, _source_id, _subscription_id, _account_id, _run_id = _seed_pipeline(
        database,
        remote_id="terminal",
    )

    result = await PipelineSubscriptionWorker(
        database,
        lambda _claim: PipelineHandlerResult.failure("pipeline_subscription_invalid"),
        clock=_Clock(),
    ).run_once(worker_id="pipeline-terminal-worker")

    assert (result.status, result.error_code) == ("failed_terminal", "pipeline_subscription_invalid")
    with database.session() as session:
        job = session.get(Job, coordinator_id)
        assert job is not None
        assert job.finished_at == NOW
        assert job.last_error_message == "subscription scope is inconsistent"


@pytest.mark.asyncio
async def test_bounded_worker_stops_after_available_coordinators(database: Database) -> None:
    first_id, *_first_scope = _seed_pipeline(database, remote_id="bounded-one")
    second_id, *_second_scope = _seed_pipeline(database, remote_id="bounded-two")
    calls: list[str] = []

    def handler(claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        calls.append(claim.job_id)
        return PipelineHandlerResult.success()

    results = await PipelineSubscriptionWorker(database, handler, clock=_Clock()).run_bounded(
        worker_id="pipeline-bounded-worker",
        max_jobs=10,
    )

    assert len(results) == 2
    assert {result.job_id for result in results} == {first_id, second_id}
    assert all(result.status == "succeeded" for result in results)
    assert set(calls) == {first_id, second_id}


@pytest.mark.asyncio
async def test_bounded_worker_observes_cooperative_cancellation_before_next_coordinator(
    database: Database,
) -> None:
    first_id, *_first_scope = _seed_pipeline(database, remote_id="bounded-cancel-one")
    second_id, *_second_scope = _seed_pipeline(database, remote_id="bounded-cancel-two")
    cancellation = ThreadEvent()
    calls: list[str] = []

    def handler(claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        calls.append(claim.job_id)
        cancellation.set()
        return PipelineHandlerResult.success()

    results = await PipelineSubscriptionWorker(database, handler, clock=_Clock()).run_bounded(
        worker_id="pipeline-bounded-cancel-worker",
        max_jobs=2,
        cancellation=cancellation,
    )

    assert len(results) == 1
    assert results[0].status == "succeeded"
    assert calls in ([first_id], [second_id])
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Job).where(Job.status == "queued")) == 1


@pytest.mark.asyncio
async def test_replaced_lease_fences_success_without_overwriting_new_owner(database: Database) -> None:
    coordinator_id, _source_id, _subscription_id, _account_id, _run_id = _seed_pipeline(
        database,
        remote_id="lease-lost",
    )
    replacement_token = new_uuid()

    def handler(claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        with database.session() as session:
            job = session.get(Job, claim.job_id)
            assert job is not None and job.status == "running"
            job.lease_owner = "replacement-worker"
            job.lease_token = replacement_token
            job.lease_expires_at = NOW + timedelta(minutes=5)
            session.flush()
        return PipelineHandlerResult.success()

    result = await PipelineSubscriptionWorker(database, handler, clock=_Clock()).run_once(
        worker_id="pipeline-stale-worker"
    )

    assert (result.status, result.error_code) == ("fenced", "pipeline_lease_lost")
    with database.session() as session:
        job = session.get(Job, coordinator_id)
        assert job is not None
        assert (job.status, job.lease_owner, job.lease_token) == (
            "running",
            "replacement-worker",
            replacement_token,
        )


@pytest.mark.asyncio
async def test_worker_heartbeats_blocking_handler_until_success(database: Database) -> None:
    coordinator_id, _source_id, _subscription_id, _account_id, _run_id = _seed_pipeline(
        database,
        remote_id="heartbeat-success",
    )
    clock = _Clock()
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(_claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        started.set()
        await release.wait()
        return PipelineHandlerResult.success()

    running = asyncio.create_task(
        PipelineSubscriptionWorker(database, handler, clock=clock).run_once(
            worker_id="pipeline-heartbeat-worker",
            lease_seconds=2,
            heartbeat_interval_seconds=0.01,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    clock.value = NOW + timedelta(seconds=1)

    renewed_expiry: datetime | None = None
    for _ in range(100):
        with database.session() as session:
            job = session.get(Job, coordinator_id)
            assert job is not None
            renewed_expiry = job.lease_expires_at
        if renewed_expiry == NOW + timedelta(seconds=3):
            break
        await asyncio.sleep(0.01)
    assert renewed_expiry == NOW + timedelta(seconds=3)

    release.set()
    result = await asyncio.wait_for(running, timeout=2)

    assert result.status == "succeeded"


@pytest.mark.asyncio
async def test_worker_rebases_full_lease_after_delayed_claim_to_start_handoff(database: Database) -> None:
    coordinator_id, _source_id, _subscription_id, _account_id, _run_id = _seed_pipeline(
        database,
        remote_id="heartbeat-start-rebase",
    )
    observed_expiry: datetime | None = None
    started_at = NOW + timedelta(seconds=1, milliseconds=500)
    clock = _SequenceClock(NOW, started_at, NOW + timedelta(seconds=1, milliseconds=600))

    async def handler(_claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        nonlocal observed_expiry
        with database.session() as session:
            job = session.get(Job, coordinator_id)
            assert job is not None
            observed_expiry = job.lease_expires_at
        return PipelineHandlerResult.success()

    result = await PipelineSubscriptionWorker(database, handler, clock=clock).run_once(
        worker_id="pipeline-start-rebase-worker",
        lease_seconds=2,
        heartbeat_interval_seconds=1.9,
    )

    assert result.status == "succeeded"
    assert observed_expiry == started_at + timedelta(seconds=2)


@pytest.mark.asyncio
async def test_heartbeat_lease_loss_cancels_handler_and_never_finalizes(database: Database) -> None:
    coordinator_id, _source_id, _subscription_id, _account_id, _run_id = _seed_pipeline(
        database,
        remote_id="heartbeat-lease-lost",
    )
    replacement_token = new_uuid()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def handler(_claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return PipelineHandlerResult.success()

    running = asyncio.create_task(
        PipelineSubscriptionWorker(database, handler, clock=_Clock()).run_once(
            worker_id="pipeline-heartbeat-stale-worker",
            lease_seconds=2,
            heartbeat_interval_seconds=0.01,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    with database.session() as session:
        job = session.get(Job, coordinator_id)
        assert job is not None and job.status == "running"
        job.lease_owner = "pipeline-replacement-worker"
        job.lease_token = replacement_token
        job.lease_expires_at = NOW + timedelta(minutes=5)
        session.flush()

    result = await asyncio.wait_for(running, timeout=2)

    assert (result.status, result.error_code) == ("fenced", "pipeline_lease_lost")
    assert cancelled.is_set()
    with database.session() as session:
        job = session.get(Job, coordinator_id)
        assert job is not None
        assert (job.status, job.lease_owner, job.lease_token) == (
            "running",
            "pipeline-replacement-worker",
            replacement_token,
        )


@pytest.mark.asyncio
async def test_heartbeat_storage_failure_stays_fenced_and_stops_bounded_batch(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_id, _source_id, _subscription_id, _account_id, _run_id = _seed_pipeline(
        database,
        remote_id="heartbeat-storage-first",
    )
    second_id, _source_id, _subscription_id, _account_id, _run_id = _seed_pipeline(
        database,
        remote_id="heartbeat-storage-second",
    )
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def handler(_claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    worker = PipelineSubscriptionWorker(database, handler, clock=_Clock())

    def fail_heartbeat(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("synthetic heartbeat storage outage")

    monkeypatch.setattr(worker, "_heartbeat", fail_heartbeat)
    running = asyncio.create_task(
        worker.run_bounded(
            worker_id="pipeline-heartbeat-storage-worker",
            max_jobs=2,
            lease_seconds=2,
            heartbeat_interval_seconds=0.01,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    results = await asyncio.wait_for(running, timeout=2)

    assert len(results) == 1
    assert (results[0].status, results[0].error_code) == ("fenced", "pipeline_heartbeat_failed")
    assert cancelled.is_set()
    with database.session() as session:
        first = session.get(Job, first_id)
        second = session.get(Job, second_id)
        assert first is not None and second is not None
        assert {first.status, second.status} == {"running", "queued"}


@pytest.mark.asyncio
@pytest.mark.parametrize("heartbeat_interval", [0, -1, 2, True, float("inf"), float("nan")])
async def test_worker_rejects_invalid_heartbeat_intervals(
    database: Database,
    heartbeat_interval: object,
) -> None:
    worker = PipelineSubscriptionWorker(database, lambda _claim: PipelineHandlerResult.success(), clock=_Clock())

    with pytest.raises(ValueError, match="heartbeat_interval_seconds"):
        await worker.run_once(
            worker_id="pipeline-invalid-heartbeat-worker",
            lease_seconds=2,
            heartbeat_interval_seconds=cast(float, heartbeat_interval),
        )


@pytest.mark.asyncio
async def test_handler_exception_is_redacted_to_fixed_retryable_code(database: Database) -> None:
    coordinator_id, _source_id, _subscription_id, _account_id, _run_id = _seed_pipeline(
        database,
        remote_id="handler-exception",
    )

    def handler(_claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        raise RuntimeError(SECRET)

    result = await PipelineSubscriptionWorker(database, handler, clock=_Clock()).run_once(
        worker_id="pipeline-exception-worker"
    )

    assert (result.status, result.error_code) == ("retry_wait", "pipeline_handler_error")
    assert SECRET not in repr(result)
    with database.session() as session:
        job = session.get(Job, coordinator_id)
        assert job is not None
        assert job.last_error_code == "pipeline_handler_error"
        assert job.last_error_message == "pipeline handler failed unexpectedly"
        assert SECRET not in repr(job.payload)
        assert SECRET not in (job.last_error_message or "")


@pytest.mark.asyncio
async def test_invalid_handler_return_is_fixed_terminal_failure(database: Database) -> None:
    coordinator_id, _source_id, _subscription_id, _account_id, _run_id = _seed_pipeline(
        database,
        remote_id="handler-invalid",
    )

    def invalid_handler(_claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        return cast(PipelineHandlerResult, {"succeeded": True, "secret": SECRET})

    result = await PipelineSubscriptionWorker(database, invalid_handler, clock=_Clock()).run_once(
        worker_id="pipeline-invalid-worker"
    )

    assert (result.status, result.error_code) == ("failed_terminal", "pipeline_handler_invalid")
    with database.session() as session:
        job = session.get(Job, coordinator_id)
        assert job is not None
        assert job.last_error_message == "pipeline handler returned an invalid result"
        assert SECRET not in (job.last_error_message or "")
