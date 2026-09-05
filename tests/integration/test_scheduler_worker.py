"""Offline application coverage for durable scheduler workers and Fake handlers."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event as ThreadEvent
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from media_sync.adapters.fake import FakePlatformAdapter
from media_sync.domain import (
    AccountRef,
    AdapterError,
    AuthExpiredError,
    AuthorSnapshot,
    InteractiveChallengeRequiredError,
    Platform,
    RateLimitedError,
    UpstreamSchemaChangedError,
)
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import Account, Content, Job, RunEvent, SchedulerLane, Subscription, SyncRun
from media_sync.scheduler.handlers import (
    FakeSubscriptionHandler,
    SubscriptionHandlerRegistry,
    SubscriptionHandlerResult,
    SubscriptionJobContext,
)
from media_sync.scheduler.mediacrawler_handler import MediaCrawlerCleanupBlockedError
from media_sync.scheduler.pipeline import (
    PIPELINE_PAYLOAD_SCHEMA_VERSION,
    PIPELINE_SUBSCRIPTION_JOB_TYPE,
    pipeline_subscription_natural_key,
)
from media_sync.scheduler.policy import RetryPolicy
from media_sync.scheduler.repository import SchedulerClaim, SchedulerLeaseLostError, SchedulerRepository
from media_sync.scheduler.service import DurableSchedulerService, SubscriptionWorker, _heartbeat_failure_code

NOW = datetime(2026, 8, 30, 5, 0, tzinfo=UTC)
SECRET = "SENTINEL-scheduler-raw-exception-secret"


class _Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class _CallFailingClock:
    def __init__(self, *, fail_on: set[int]) -> None:
        self.fail_on = fail_on
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        if self.calls in self.fail_on:
            raise RuntimeError(f"clock failure contains {SECRET}")
        return NOW


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    url = f"sqlite+pysqlite:///{(tmp_path / 'worker.sqlite3').as_posix()}"
    instance = Database(url)
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed(
    database: Database,
    *,
    platform: str = "bili",
    login_method: str = "cookie",
    remote_id: str = "creator-001",
    max_items: int = 1,
) -> str:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=platform,
            adapter="fake",
            display_name=f"worker-{platform}-{login_method}-{remote_id}",
            login_method=login_method,
            auth_status="authenticated",
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=platform,
                remote_id=remote_id,
                display_name="Scheduled creator placeholder",
            )
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            interval_seconds=60,
            max_items=max_items,
        )
        return subscription.id


class _InspectingFakeHandler:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.inner = FakeSubscriptionHandler(database)
        self.observed_statuses: list[str] = []

    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        independent = Database(self.database.url)
        try:
            with independent.session() as session:
                job = session.get(Job, str(context.job_id))
                assert job is not None
                self.observed_statuses.append(job.status)
                assert job.status == "running"
                assert job.lease_token is not None
        finally:
            independent.dispose()
        return await self.inner.run(context)


class _AttachingFakeHandler:
    """Model a handler that publishes its run before Job finalization."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.inner = FakeSubscriptionHandler(database)

    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        result = await self.inner.run(context)
        assert result.succeeded and result.run_id is not None
        assert context.run_attacher is not None
        with self.database.session() as session:
            context.run_attacher(session, result.run_id, context.current_run_id)
        return result


class _ResolveFailureAdapter(FakePlatformAdapter):
    def __init__(self, platform: Platform, error: AdapterError) -> None:
        super().__init__(platform)
        self.error = error

    async def resolve_author(self, account: AccountRef, reference: str) -> AuthorSnapshot:
        del account, reference
        raise self.error


class _EnsureFailureAdapter(FakePlatformAdapter):
    async def ensure_session(self, account: AccountRef, interaction: object | None = None) -> object:
        del account, interaction
        raise AuthExpiredError(self.capabilities().platform.value)


class _SuccessHandler:
    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        return SubscriptionHandlerResult.success()


class _CancellingSuccessHandler:
    def __init__(self, cancellation: ThreadEvent) -> None:
        self.cancellation = cancellation
        self.calls = 0

    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        del context
        self.calls += 1
        self.cancellation.set()
        return SubscriptionHandlerResult.success()


class _ResultHandler:
    def __init__(self, result: SubscriptionHandlerResult) -> None:
        self.result = result

    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        del context
        return self.result


class _RaisingHandler:
    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        del context
        raise RuntimeError(f"raw exception contains {SECRET}")


class _BadResultHandler:
    async def run(self, context: SubscriptionJobContext) -> object:
        del context
        return {"raw": SECRET}


class _BlockingHandler:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        del context
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return SubscriptionHandlerResult.success()


class _AttachingBlockingHandler(_BlockingHandler):
    def __init__(self, database: Database, *, committed_success: bool = False) -> None:
        super().__init__()
        self.database = database
        self.committed_success = committed_success
        self.task: asyncio.Task[object] | None = None

    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        self.task = asyncio.current_task()
        if self.committed_success:
            await _AttachingFakeHandler(self.database).run(context)
        else:
            with self.database.session() as session:
                runs = SyncRunRepository(session)
                run = runs.create(subscription_id=str(context.subscription_id), attempt=context.attempt)
                assert context.run_attacher is not None
                context.run_attacher(session, UUID(run.id), context.current_run_id)
                runs.set_status(run.id, "claimed", expected_status="queued", at=NOW)
                runs.set_status(run.id, "running", expected_status="claimed", at=NOW)
        return await super().run(context)


class _CleanupFenceHandler(_BlockingHandler):
    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        try:
            return await super().run(context)
        except asyncio.CancelledError:
            raise MediaCrawlerCleanupBlockedError from None


class _GuardedMutationHandler:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.started = asyncio.Event()
        self.proceed = asyncio.Event()
        self.committed = False

    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        self.started.set()
        await self.proceed.wait()
        with self.database.session() as session:
            assert context.ownership_guard is not None
            context.ownership_guard(session)
            subscription = session.get(Subscription, str(context.subscription_id))
            assert subscription is not None
            subscription.max_items = 99
        self.committed = True
        return SubscriptionHandlerResult.success()


class _DisableDatabaseHandler:
    def __init__(self, disable: Callable[[], None]) -> None:
        self.disable = disable

    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        del context
        self.disable()
        return SubscriptionHandlerResult.success()


class _WaitForThreadEventHandler:
    def __init__(self, ready: ThreadEvent) -> None:
        self.ready = ready

    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        del context
        assert await asyncio.to_thread(self.ready.wait, 1)
        return SubscriptionHandlerResult.success()


class _RaisingRandom:
    def __call__(self) -> float:
        raise RuntimeError(f"rng failure contains {SECRET}")


@pytest.mark.asyncio
async def test_subject_hook_failure_rolls_back_scheduler_claim_before_handler(database: Database) -> None:
    _seed(database, remote_id="subject-hook-rollback")
    clock = _Clock()
    cycle = DurableSchedulerService(database, clock=clock).tick(limit=1).cycles[0]
    handler_called = False
    observed_subjects: list[tuple[str, str, str]] = []

    class Handler:
        async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
            nonlocal handler_called
            del context
            handler_called = True
            return SubscriptionHandlerResult.success()

    def fail_hook(session: object, subject: object) -> None:
        observed_subjects.append((subject.subject_type, subject.subject_id, subject.role))
        claimed = session.get(Job, subject.subject_id)
        assert claimed is not None and claimed.status == "claimed"
        raise RuntimeError("subject hook failure")

    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": Handler()}),
        clock=clock,
    )
    with pytest.raises(RuntimeError, match="subject hook failure"):
        await worker.run_once(worker_id="hook-worker", subject_hook=fail_hook)  # type: ignore[arg-type]

    assert handler_called is False
    assert observed_subjects == [("job", cycle.job_id, "execution")]
    with database.session() as session:
        job = session.get(Job, cycle.job_id)
        assert job is not None
        assert (job.status, job.attempts, job.lease_owner, job.lease_token) == ("queued", 0, None, None)


@pytest.mark.asyncio
async def test_worker_commits_start_before_fake_handler_and_finalizes_fixed_delay(database: Database) -> None:
    subscription_id = _seed(database)
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    handler = _InspectingFakeHandler(database)
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": handler}),
        clock=clock,
    )

    tick = scheduler.tick(limit=10)
    result = await worker.run_once(worker_id="fake-worker", global_capacity=2)
    idle = await worker.run_once(worker_id="fake-worker", global_capacity=2)

    assert tick.materialized_count == 1
    assert handler.observed_statuses == ["running"]
    assert result.status == "succeeded"
    assert result.run_id is not None
    assert idle.status == "idle"
    assert scheduler.tick(limit=10).materialized_count == 0

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        sync_job = session.scalar(select(Job).where(Job.job_type == "sync.subscription"))
        pipeline_job = session.scalar(select(Job).where(Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE))
        assert subscription is not None and sync_job is not None and pipeline_job is not None
        assert subscription.schedule_revision == 1
        assert subscription.checkpoint_revision == 1
        assert subscription.next_run_at == NOW + timedelta(seconds=60)
        assert subscription.consecutive_failures == 0
        assert sync_job.status == "succeeded"
        assert sync_job.run_id == result.run_id
        assert session.scalar(select(func.count()).select_from(SyncRun)) == 1
        assert session.scalar(select(func.count()).select_from(Content)) == 1
        assert session.scalar(select(func.count()).select_from(SchedulerLane)) == 2
        assert pipeline_job.natural_key == pipeline_subscription_natural_key(sync_job.id)
        assert pipeline_job.payload == {
            "schema_version": PIPELINE_PAYLOAD_SCHEMA_VERSION,
            "sync_job_id": sync_job.id,
            "subscription_id": subscription_id,
            "run_id": result.run_id,
        }
        assert {job.job_type for job in session.scalars(select(Job)).all()} == {
            "sync.subscription",
            PIPELINE_SUBSCRIPTION_JOB_TYPE,
        }


@pytest.mark.asyncio
async def test_shipped_registry_rejects_due_mediacrawler_without_pipeline_side_effects(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "mediacrawler-runtime"
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_RUNTIME_DIR", str(runtime_root))

    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        pytest.fail("unsupported scheduler handler reached the MediaCrawler pipeline")

    monkeypatch.setattr(
        "media_sync.integrations.mediacrawler.runner.MediaCrawlerProcessRunner.run",
        fail_if_called,
    )
    monkeypatch.setattr(
        "media_sync.infrastructure.db.mediacrawler_ingestion.MediaCrawlerIngestionService.ingest",
        fail_if_called,
    )

    with database.session() as session:
        account = AccountRepository(session).create(
            platform="xhs",
            adapter="mediacrawler",
            display_name="unsupported-scheduled-mediacrawler",
            login_method="cookie",
            auth_status="authenticated",
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform="xhs",
                remote_id="unsupported-scheduled-creator",
                display_name="Unsupported scheduled creator",
            )
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            interval_seconds=60,
            max_items=1,
            next_run_at=NOW - timedelta(seconds=1),
        )
        subscription_id = subscription.id

    clock = _Clock()
    tick = DurableSchedulerService(database, clock=clock).tick(limit=1)
    result = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry.fake_only(database),
        clock=clock,
    ).run_once(worker_id="unsupported-mediacrawler-worker")

    assert tick.materialized_count == 1
    assert (result.status, result.error_code) == ("failed_terminal", "handler_unsupported")
    assert result.subscription_id == subscription_id
    assert result.run_id is None
    with database.session() as session:
        job = session.scalar(select(Job).where(Job.job_type == "sync.subscription"))
        assert job is not None
        assert job.status == "failed_terminal"
        assert job.last_error_code == "handler_unsupported"
        assert job.run_id is None
        assert job.finished_at == NOW
        assert session.scalar(select(func.count()).select_from(SyncRun)) == 0
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        assert (
            session.scalar(
                select(func.count()).select_from(Job).where(Job.job_type.in_(("asset_download", "export.emby")))
            )
            == 0
        )
    assert not runtime_root.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_kind", "expected_status", "expected_code"),
    [
        ("rate", "retry_wait", "rate_limited"),
        ("interactive", "waiting_user", "interactive_required"),
        ("auth", "waiting_auth", "auth_expired"),
        ("schema", "failed_terminal", "schema_invalid"),
    ],
)
async def test_fake_handler_maps_closed_retry_wait_and_terminal_results(
    database: Database,
    failure_kind: str,
    expected_status: str,
    expected_code: str,
) -> None:
    _seed(database)
    clock = _Clock()
    errors: dict[str, AdapterError] = {
        "rate": RateLimitedError("bili", retry_after=45),
        "interactive": InteractiveChallengeRequiredError("bili"),
        "auth": AuthExpiredError("bili"),
        "schema": UpstreamSchemaChangedError("bili"),
    }
    handler = FakeSubscriptionHandler(
        database,
        adapter_factory=lambda platform: _ResolveFailureAdapter(platform, errors[failure_kind]),
    )
    scheduler = DurableSchedulerService(database, clock=clock)
    scheduler.tick(limit=1)
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": handler}),
        clock=clock,
        random_fraction=lambda: 0,
    )

    result = await worker.run_once(worker_id="mapping-worker")
    second = await worker.run_once(worker_id="mapping-worker")

    assert result.status == expected_status
    assert result.error_code == expected_code
    assert second.status == "idle"
    with database.session() as session:
        job = session.scalar(select(Job).where(Job.job_type == "sync.subscription"))
        run = session.scalar(select(SyncRun))
        assert job is not None and run is not None
        assert job.last_error_message is None
        assert job.run_id == run.id
        if failure_kind == "rate":
            assert job.available_at == NOW + timedelta(seconds=45)
            assert run.status == "failed_retryable"
        elif expected_status == "failed_terminal":
            assert job.finished_at == NOW
        else:
            assert job.finished_at is None


@pytest.mark.asyncio
async def test_qr_auth_expiry_is_waiting_auth_not_qr_required(database: Database) -> None:
    _seed(database, login_method="qr")
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    scheduler.tick(limit=1)
    handler = FakeSubscriptionHandler(
        database,
        adapter_factory=lambda platform: _EnsureFailureAdapter(platform),
    )

    result = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": handler}),
        clock=clock,
    ).run_once(worker_id="qr-auth-worker")

    assert (result.status, result.error_code) == ("waiting_auth", "auth_expired")


@pytest.mark.asyncio
async def test_waiting_user_is_dormant_until_explicit_resume(database: Database) -> None:
    _seed(database, login_method="qr")
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    scheduler.tick(limit=1)
    qr_worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry.fake_only(database),
        clock=clock,
    )

    waiting = await qr_worker.run_once(worker_id="qr-worker")
    clock.value += timedelta(days=1)
    dormant = await qr_worker.run_once(worker_id="qr-worker")
    assert (waiting.status, waiting.error_code) == ("waiting_user", "qr_required")
    assert dormant.status == "idle"

    resumed = scheduler.resume_job(waiting.job_id or "")
    success_worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": _SuccessHandler()}),
        clock=clock,
    )
    succeeded = await success_worker.run_once(worker_id="approved-worker")

    assert resumed.status == "queued"
    assert succeeded.status == "succeeded"
    assert succeeded.attempt == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "expected_code"),
    [
        (_RaisingHandler(), "unexpected_handler_failure"),
        (_BadResultHandler(), "schema_invalid"),
    ],
)
async def test_worker_closes_malformed_or_secret_handler_failures(
    database: Database,
    handler: object,
    expected_code: str,
) -> None:
    _seed(database)
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    scheduler.tick(limit=1, retry_policy=RetryPolicy(max_attempts=1))
    registry = SubscriptionHandlerRegistry({"fake": handler})  # type: ignore[dict-item]

    result = await SubscriptionWorker(database, registry, clock=clock).run_once(worker_id="closed-worker")

    assert (result.status, result.error_code) == ("failed_terminal", expected_code)
    assert SECRET not in repr(result)
    with database.session() as session:
        job = session.scalar(select(Job).where(Job.job_type == "sync.subscription"))
        assert job is not None
        assert job.last_error_message is None
        assert SECRET not in repr(
            [
                job.payload,
                job.last_error_code,
                job.last_error_message,
                job.lease_owner,
                job.lease_token,
            ]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "random_fraction",
    [
        pytest.param(lambda: float("nan"), id="nan"),
        pytest.param(lambda: float("inf"), id="positive-infinity"),
        pytest.param(lambda: float("-inf"), id="negative-infinity"),
        pytest.param(lambda: "wrong-type", id="wrong-type"),
        pytest.param(_RaisingRandom(), id="runtime-error"),
    ],
)
async def test_invalid_rng_terminalizes_as_schema_failure_instead_of_leaving_running_job(
    database: Database,
    random_fraction: object,
) -> None:
    _seed(database)
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    scheduler.tick(limit=1)
    handler = _ResultHandler(SubscriptionHandlerResult.failure("rate_limited"))
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": handler}),
        clock=clock,
        random_fraction=cast(Callable[[], float], random_fraction),
    )

    result = await worker.run_once(worker_id="bad-rng-worker")

    assert (result.status, result.error_code) == ("failed_terminal", "schema_invalid")
    with database.session() as session:
        job = session.scalar(select(Job).where(Job.job_type == "sync.subscription"))
        assert job is not None
        assert job.lease_token is None
        assert job.finished_at == NOW
        assert SECRET not in repr([job.last_error_code, job.last_error_message])


def _sqlite_operational_error(native_code: object) -> OperationalError:
    original = sqlite3.OperationalError(SECRET)
    original.sqlite_errorcode = native_code
    return OperationalError(SECRET, {"private": SECRET}, original)


@pytest.mark.parametrize("native_code", [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, 261, 262, 517, 773])
def test_heartbeat_storage_busy_requires_typed_native_sqlite_code(native_code: int) -> None:
    assert _heartbeat_failure_code(_sqlite_operational_error(native_code)) == "scheduler_heartbeat_storage_busy"


@pytest.mark.parametrize("native_code", [None, True, False, "5", 5.0, -251, 2**40 + 5, sqlite3.SQLITE_ERROR])
def test_heartbeat_diagnostic_rejects_untyped_or_unrelated_native_codes(native_code: object) -> None:
    assert _heartbeat_failure_code(_sqlite_operational_error(native_code)) == "scheduler_heartbeat_failed"


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError(f"database is locked SQLITE_BUSY {SECRET}"),
        sqlite3.OperationalError(f"database is locked {SECRET}"),
        OperationalError(SECRET, None, RuntimeError(f"database is locked {SECRET}")),
        OperationalError(SECRET, None, sqlite3.OperationalError(f"database is locked {SECRET}")),
    ],
    ids=["ordinary", "bare-sqlite", "non-sqlite-orig", "missing-native-code"],
)
def test_heartbeat_diagnostic_never_parses_exception_text(error: Exception) -> None:
    assert _heartbeat_failure_code(error) == "scheduler_heartbeat_failed"


def test_heartbeat_diagnostic_ignores_forged_code_on_non_sqlite_exception() -> None:
    error = RuntimeError(SECRET)
    error.sqlite_errorcode = sqlite3.SQLITE_BUSY  # type: ignore[attr-defined]
    assert _heartbeat_failure_code(error) == "scheduler_heartbeat_failed"
    assert _heartbeat_failure_code(OperationalError(SECRET, None, error)) == "scheduler_heartbeat_failed"


@pytest.mark.asyncio
async def test_generic_heartbeat_failure_preserves_running_run_and_authenticated_account(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscription_id = _seed(database)
    clock = _Clock()
    cycle = DurableSchedulerService(database, clock=clock).tick(limit=1).cycles[0]
    handler = _AttachingBlockingHandler(database)
    worker = SubscriptionWorker(database, SubscriptionHandlerRegistry({"fake": handler}), clock=clock)
    original_finalize = worker._finalize

    def fail_heartbeat(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(f"database is locked {SECRET}")

    def finalize_after_join(*args: object, **kwargs: object) -> object:
        assert handler.cancelled.is_set()
        assert handler.task is not None and handler.task.done()
        return original_finalize(*args, **kwargs)

    monkeypatch.setattr(worker, "_heartbeat", fail_heartbeat)
    monkeypatch.setattr(worker, "_finalize", finalize_after_join)
    result = await asyncio.wait_for(worker.run_once(worker_id="heartbeat-failure", heartbeat_interval_seconds=0.01), 2)

    assert (result.status, result.error_code) == ("failed_terminal", "scheduler_heartbeat_failed")
    assert result.run_id is not None
    assert SECRET not in repr(result)
    with database.session() as session:
        job = session.get(Job, cycle.job_id)
        subscription = session.get(Subscription, subscription_id)
        run = session.get(SyncRun, result.run_id)
        assert job is not None and run is not None and subscription is not None
        account = session.get(Account, subscription.account_id)
        assert account is not None and account.auth_status == "authenticated"
        assert (job.status, job.last_error_code, job.last_error_message) == (
            "failed_terminal",
            "scheduler_heartbeat_failed",
            None,
        )
        assert (job.run_id, job.attempts, job.lease_token) == (run.id, 1, None)
        assert (run.status, run.error_code, run.error_message, run.finished_at) == ("running", None, None, None)
        assert subscription.consecutive_failures == 1
        assert subscription.checkpoint_revision == 0 and subscription.cursor is None
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        events = session.scalars(select(RunEvent).where(RunEvent.run_id == run.id)).all()
        assert sorted(event.to_status for event in events) == ["claimed", "queued", "running"]


@pytest.mark.asyncio
@pytest.mark.parametrize("storage_busy", [False, True], ids=["generic", "native-busy"])
async def test_heartbeat_failure_cannot_overwrite_committed_success(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    storage_busy: bool,
) -> None:
    subscription_id = _seed(database)
    clock = _Clock()
    cycle = DurableSchedulerService(database, clock=clock).tick(limit=1).cycles[0]
    handler = _AttachingBlockingHandler(database, committed_success=True)
    worker = SubscriptionWorker(database, SubscriptionHandlerRegistry({"fake": handler}), clock=clock)

    def fail_heartbeat(*_args: object, **_kwargs: object) -> None:
        if storage_busy:
            raise _sqlite_operational_error(sqlite3.SQLITE_BUSY)
        raise RuntimeError(SECRET)

    monkeypatch.setattr(worker, "_heartbeat", fail_heartbeat)
    result = await asyncio.wait_for(worker.run_once(worker_id="heartbeat-success", heartbeat_interval_seconds=0.01), 2)

    assert (result.status, result.error_code) == ("succeeded", None)
    assert handler.cancelled.is_set() and handler.task is not None and handler.task.done()
    with database.session() as session:
        job = session.get(Job, cycle.job_id)
        subscription = session.get(Subscription, subscription_id)
        assert job is not None and subscription is not None and job.run_id is not None
        run = session.get(SyncRun, job.run_id)
        assert (job.status, job.last_error_code, job.lease_token) == ("succeeded", None, None)
        assert run is not None and (run.status, run.error_code) == ("succeeded", None)
        assert subscription.consecutive_failures == 0 and subscription.checkpoint_revision == 1
        assert session.scalar(select(func.count()).select_from(Content)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_fence", [False, True], ids=["lease-lost", "cleanup-fence"])
async def test_heartbeat_failure_preserves_lease_and_cleanup_fences(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_fence: bool,
) -> None:
    _seed(database)
    clock = _Clock()
    cycle = DurableSchedulerService(database, clock=clock).tick(limit=1).cycles[0]
    handler = _CleanupFenceHandler() if cleanup_fence else _BlockingHandler()
    worker = SubscriptionWorker(database, SubscriptionHandlerRegistry({"fake": handler}), clock=clock)

    def fail_heartbeat(*_args: object, **_kwargs: object) -> None:
        if cleanup_fence:
            raise RuntimeError(SECRET)
        raise SchedulerLeaseLostError(SECRET)

    def unexpected_finalization(*_args: object, **_kwargs: object) -> None:
        pytest.fail("a lease/cleanup fence must not reach finalization")

    monkeypatch.setattr(worker, "_heartbeat", fail_heartbeat)
    monkeypatch.setattr(worker, "_finalize", unexpected_finalization)
    result = await asyncio.wait_for(worker.run_once(worker_id="heartbeat-fence", heartbeat_interval_seconds=0.01), 2)

    assert (result.status, result.error_code) == ("fenced", None)
    assert handler.cancelled.is_set()
    with database.session() as session:
        job = session.get(Job, cycle.job_id)
        assert job is not None and (job.status, job.last_error_code) == ("running", None)
        assert job.lease_token is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("already_done", [False, True], ids=["pending", "completed"])
@pytest.mark.parametrize("fence", [False, True], ids=["ordinary-error", "cleanup-fence"])
async def test_cancel_task_drains_ordinary_errors_but_propagates_cleanup_fence(already_done: bool, fence: bool) -> None:
    started = asyncio.Event()

    async def handler() -> SubscriptionHandlerResult:
        started.set()
        try:
            if not already_done:
                await asyncio.Event().wait()
        finally:
            if fence:
                raise MediaCrawlerCleanupBlockedError
            raise RuntimeError(SECRET)

    task = asyncio.create_task(handler())
    await started.wait()
    if already_done:
        assert task.done()
    if fence:
        with pytest.raises(MediaCrawlerCleanupBlockedError):
            await SubscriptionWorker._cancel_task(task)
    else:
        await SubscriptionWorker._cancel_task(task)
    assert task.done()


@pytest.mark.asyncio
async def test_simultaneously_completed_heartbeat_and_handler_preserve_cleanup_fence(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(database)
    clock = _Clock()
    cycle = DurableSchedulerService(database, clock=clock).tick(limit=1).cycles[0]
    worker = SubscriptionWorker(database, SubscriptionHandlerRegistry({"fake": _SuccessHandler()}), clock=clock)
    original_wait = asyncio.wait
    observed_both_done = False

    async def failed_handler(*_args: object, **_kwargs: object) -> SubscriptionHandlerResult:
        raise MediaCrawlerCleanupBlockedError

    async def failed_heartbeat(*_args: object, **_kwargs: object) -> str:
        return "scheduler_heartbeat_failed"

    async def wait_for_both(tasks: object, **_kwargs: object) -> object:
        nonlocal observed_both_done
        done, pending = await original_wait(tasks, return_when=asyncio.ALL_COMPLETED)
        observed_both_done = len(done) == 2 and not pending
        return done, pending

    def unexpected_finalization(*_args: object, **_kwargs: object) -> None:
        pytest.fail("the completed handler cleanup fence must take precedence")

    monkeypatch.setattr(worker, "_invoke", failed_handler)
    monkeypatch.setattr(worker, "_heartbeat_loop", failed_heartbeat)
    monkeypatch.setattr(worker, "_finalize", unexpected_finalization)
    monkeypatch.setattr(asyncio, "wait", wait_for_both)
    result = await worker.run_once(worker_id="simultaneous-fence")

    assert observed_both_done
    assert (result.status, result.error_code) == ("fenced", None)
    with database.session() as session:
        job = session.get(Job, cycle.job_id)
        assert job is not None and (job.status, job.last_error_code) == ("running", None)


@pytest.mark.asyncio
async def test_worker_heartbeats_blocking_handler_then_cancel_returns_durable_terminal_state(
    database: Database,
) -> None:
    _seed(database, remote_id="heartbeat-cancel")
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    cycle = scheduler.tick(limit=1).cycles[0]
    handler = _BlockingHandler()
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": handler}),
        clock=clock,
    )

    running = asyncio.create_task(
        worker.run_once(
            worker_id="heartbeat-cancel-worker",
            lease_seconds=2,
            heartbeat_interval_seconds=0.01,
        )
    )
    await asyncio.wait_for(handler.started.wait(), timeout=2)
    clock.value = NOW + timedelta(seconds=1)

    renewed_expiry: datetime | None = None
    for _ in range(100):
        with database.session() as session:
            job = session.get(Job, cycle.job_id)
            assert job is not None
            renewed_expiry = job.lease_expires_at
        if renewed_expiry == NOW + timedelta(seconds=3):
            break
        await asyncio.sleep(0.01)
    assert renewed_expiry == NOW + timedelta(seconds=3)

    assert scheduler.cancel_job(cycle.job_id).status == "cancelled"
    result = await asyncio.wait_for(running, timeout=2)

    assert result.status == "cancelled"
    assert handler.cancelled.is_set()
    with database.session() as session:
        job = session.get(Job, cycle.job_id)
        assert job is not None
        assert job.status == "cancelled"
        assert job.lease_owner is None and job.lease_token is None


@pytest.mark.asyncio
async def test_sqlite_heartbeat_wait_runs_off_loop_and_still_fences_cancel(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(database, remote_id="off-loop-heartbeat")
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    cycle = scheduler.tick(limit=1).cycles[0]
    handler = _BlockingHandler()
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": handler}),
        clock=clock,
    )
    heartbeat_entered = ThreadEvent()
    heartbeat_release = ThreadEvent()
    original_heartbeat = worker._heartbeat

    def delayed_heartbeat(
        claim: SchedulerClaim,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        heartbeat_entered.set()
        if not heartbeat_release.wait(timeout=2):
            raise RuntimeError("heartbeat test release timed out")
        original_heartbeat(
            claim,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )

    monkeypatch.setattr(worker, "_heartbeat", delayed_heartbeat)
    running = asyncio.create_task(
        worker.run_once(
            worker_id="off-loop-heartbeat-worker",
            lease_seconds=2,
            heartbeat_interval_seconds=0.01,
        )
    )
    await asyncio.wait_for(handler.started.wait(), timeout=2)
    assert await asyncio.wait_for(asyncio.to_thread(heartbeat_entered.wait, 1), timeout=1)

    assert scheduler.cancel_job(cycle.job_id).status == "cancelled"
    heartbeat_release.set()
    result = await asyncio.wait_for(running, timeout=2)

    assert result.status == "cancelled"
    assert handler.cancelled.is_set()


@pytest.mark.asyncio
async def test_fast_handler_joins_inflight_heartbeat_before_finalize_and_return(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(database, remote_id="join-inflight-heartbeat")
    clock = _Clock()
    DurableSchedulerService(database, clock=clock).tick(limit=1)
    heartbeat_entered = ThreadEvent()
    heartbeat_release = ThreadEvent()
    heartbeat_finished = ThreadEvent()
    handler = _WaitForThreadEventHandler(heartbeat_entered)
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": handler}),
        clock=clock,
    )
    original_heartbeat = worker._heartbeat

    def delayed_heartbeat(
        claim: SchedulerClaim,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        heartbeat_entered.set()
        try:
            if not heartbeat_release.wait(timeout=2):
                raise RuntimeError("heartbeat test release timed out")
            original_heartbeat(
                claim,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )
        finally:
            heartbeat_finished.set()

    monkeypatch.setattr(worker, "_heartbeat", delayed_heartbeat)
    running = asyncio.create_task(
        worker.run_once(
            worker_id="join-heartbeat-worker",
            lease_seconds=2,
            heartbeat_interval_seconds=0.01,
        )
    )
    assert await asyncio.wait_for(asyncio.to_thread(heartbeat_entered.wait, 1), timeout=1)
    await asyncio.sleep(0.02)
    assert running.done() is False

    heartbeat_release.set()
    result = await asyncio.wait_for(running, timeout=2)

    assert result.status == "succeeded"
    assert heartbeat_finished.is_set()


@pytest.mark.asyncio
async def test_ownership_guard_prevents_handler_commit_after_independent_cancel(database: Database) -> None:
    subscription_id = _seed(database, remote_id="guard-cancel")
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    cycle = scheduler.tick(limit=1).cycles[0]
    handler = _GuardedMutationHandler(database)
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": handler}),
        clock=clock,
    )

    running = asyncio.create_task(
        worker.run_once(
            worker_id="guard-cancel-worker",
            lease_seconds=2,
            heartbeat_interval_seconds=0.5,
        )
    )
    await asyncio.wait_for(handler.started.wait(), timeout=2)
    assert scheduler.cancel_job(cycle.job_id).status == "cancelled"
    handler.proceed.set()
    result = await asyncio.wait_for(running, timeout=2)

    assert result.status == "cancelled"
    assert handler.committed is False
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None and subscription.max_items == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_fence", [False, True], ids=["cancelled", "cleanup-fence"])
async def test_external_cancellation_joins_inflight_heartbeat_even_when_handler_cleanup_fences(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_fence: bool,
) -> None:
    _seed(database)
    clock = _Clock()
    cycle = DurableSchedulerService(database, clock=clock).tick(limit=1).cycles[0]
    handler = _CleanupFenceHandler() if cleanup_fence else _BlockingHandler()
    worker = SubscriptionWorker(database, SubscriptionHandlerRegistry({"fake": handler}), clock=clock)
    entered, release, finished = ThreadEvent(), ThreadEvent(), ThreadEvent()

    def delayed_heartbeat(*_args: object, **_kwargs: object) -> None:
        entered.set()
        try:
            assert release.wait(2), "test heartbeat release timed out"
        finally:
            finished.set()

    def unexpected_finalization(*_args: object, **_kwargs: object) -> None:
        pytest.fail("external cancellation must not publish a diagnostic")

    monkeypatch.setattr(worker, "_heartbeat", delayed_heartbeat)
    monkeypatch.setattr(worker, "_finalize", unexpected_finalization)
    running = asyncio.create_task(worker.run_once(worker_id="cancel-inflight", heartbeat_interval_seconds=0.01))
    try:
        await asyncio.wait_for(handler.started.wait(), 2)
        assert await asyncio.wait_for(asyncio.to_thread(entered.wait, 1), 2)
        running.cancel()
        await asyncio.wait_for(handler.cancelled.wait(), 2)
        await asyncio.sleep(0)
        assert not running.done()
        assert not finished.is_set()
    finally:
        release.set()
    if cleanup_fence:
        result = await asyncio.wait_for(running, 2)
        assert (result.status, result.error_code) == ("fenced", None)
    else:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(running, 2)
    assert finished.is_set()
    assert not any(task.get_coro().__qualname__ == "SubscriptionWorker._heartbeat_loop" for task in asyncio.all_tasks())
    with database.session() as session:
        job = session.get(Job, cycle.job_id)
        assert job is not None and (job.status, job.last_error_code) == ("running", None)
        assert job.lease_token is not None


@pytest.mark.asyncio
async def test_expired_reclaim_aba_cancels_old_handler_and_returns_new_terminal_outcome(database: Database) -> None:
    _seed(database, remote_id="worker-aba")
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    cycle = scheduler.tick(limit=1).cycles[0]
    old_handler = _BlockingHandler()
    old_worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": old_handler}),
        clock=clock,
    )
    old_attempt = asyncio.create_task(
        old_worker.run_once(
            worker_id="old-aba-worker",
            lease_seconds=1,
            heartbeat_interval_seconds=0.2,
        )
    )
    await asyncio.wait_for(old_handler.started.wait(), timeout=2)

    clock.value = NOW + timedelta(seconds=6)
    new_result = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": _SuccessHandler()}),
        clock=clock,
    ).run_once(worker_id="new-aba-worker")
    old_result = await asyncio.wait_for(old_attempt, timeout=2)

    assert new_result.status == "succeeded"
    assert new_result.job_id == cycle.job_id
    assert new_result.attempt == 2
    assert old_result.status == "succeeded"
    assert old_result.job_id == cycle.job_id
    assert old_handler.cancelled.is_set()
    with database.session() as session:
        jobs = list(session.scalars(select(Job).where(Job.job_type == "sync.subscription")))
        assert len(jobs) == 1
        assert jobs[0].status == "succeeded" and jobs[0].attempts == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign", [False, True], ids=["unknown", "foreign-subscription"])
async def test_worker_rejects_unknown_or_foreign_handler_run_id(database: Database, foreign: bool) -> None:
    target_subscription_id = _seed(database, remote_id=f"run-scope-target-{foreign}")
    if foreign:
        foreign_subscription_id = _seed(database, remote_id="run-scope-foreign")
        with database.session() as session:
            foreign_subscription = session.get(Subscription, foreign_subscription_id)
            assert foreign_subscription is not None
            foreign_subscription.enabled = False
            foreign_run = SyncRun(
                subscription_id=foreign_subscription_id,
                status="succeeded",
                attempt=1,
            )
            session.add(foreign_run)
            session.flush()
            returned_run_id = UUID(foreign_run.id)
    else:
        returned_run_id = uuid4()

    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    scheduler.tick(limit=10)
    result = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": _ResultHandler(SubscriptionHandlerResult.success(returned_run_id))}),
        clock=clock,
    ).run_once(worker_id="run-scope-worker")

    assert (result.status, result.error_code, result.run_id) == ("failed_terminal", "schema_invalid", None)
    with database.session() as session:
        job = session.scalar(
            select(Job).where(
                Job.job_type == "sync.subscription",
                Job.subscription_id == target_subscription_id,
            )
        )
        assert job is not None
        assert job.run_id is None
        assert job.status == "failed_terminal"
        assert job.last_error_code == "schema_invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fail_on", "expected_code"),
    [({2}, "schema_invalid"), ({3}, "scheduler_finalize_failed")],
    ids=["start-clock", "finalize-clock"],
)
async def test_post_claim_clock_failures_are_closed_without_raw_exception(
    database: Database,
    fail_on: set[int],
    expected_code: str,
) -> None:
    _seed(database, remote_id=f"clock-failure-{next(iter(fail_on))}")
    DurableSchedulerService(database, clock=_Clock()).tick(limit=1)
    clock = _CallFailingClock(fail_on=fail_on)

    result = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": _SuccessHandler()}),
        clock=clock,
    ).run_once(worker_id="clock-failure-worker")

    assert (result.status, result.error_code) == ("failed_terminal", expected_code)
    assert SECRET not in repr(result)
    with database.session() as session:
        job = session.scalar(select(Job).where(Job.job_type == "sync.subscription"))
        assert job is not None
        assert job.lease_token is None
        assert SECRET not in repr([job.last_error_code, job.last_error_message])


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["_load_context", "_invoke_with_heartbeat", "_validate_result_run"])
async def test_pre_finalize_exception_is_terminalized_as_fixed_schema_failure(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    _seed(database, remote_id="context-failure")
    clock = _Clock()
    DurableSchedulerService(database, clock=clock).tick(limit=1)
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": _SuccessHandler()}),
        clock=clock,
    )

    def fail_context(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError(f"context failure contains {SECRET}")

    monkeypatch.setattr(worker, stage, fail_context)
    result = await worker.run_once(worker_id="context-failure-worker")

    assert (result.status, result.error_code) == ("failed_terminal", "schema_invalid")
    assert SECRET not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("committed_success", [False, True], ids=["no-run", "succeeded-run"])
async def test_first_finalization_failure_has_fixed_diagnostic_without_rewriting_success(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    committed_success: bool,
) -> None:
    _seed(database)
    clock = _Clock()
    cycle = DurableSchedulerService(database, clock=clock).tick(limit=1).cycles[0]
    handler = _AttachingFakeHandler(database) if committed_success else _SuccessHandler()
    worker = SubscriptionWorker(database, SubscriptionHandlerRegistry({"fake": handler}), clock=clock)
    original_finalize = worker._finalize
    calls = 0

    def fail_once(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError(f"first finalization {SECRET}")
        return original_finalize(*args, **kwargs)

    monkeypatch.setattr(worker, "_finalize", fail_once)
    result = await worker.run_once(worker_id="first-finalization")

    expected_status = "succeeded" if committed_success else "failed_terminal"
    expected_code = None if committed_success else "scheduler_finalize_failed"
    assert calls == 2
    assert (result.status, result.error_code) == (expected_status, expected_code)
    assert SECRET not in repr(result)
    with database.session() as session:
        job = session.get(Job, cycle.job_id)
        assert job is not None
        assert (job.status, job.last_error_code, job.last_error_message) == (expected_status, expected_code, None)
        assert job.lease_token is None
        if committed_success:
            assert job.run_id is not None
            run = session.get(SyncRun, job.run_id)
            assert run is not None and (run.status, run.error_code) == ("succeeded", None)
        else:
            assert job.run_id is None


@pytest.mark.asyncio
async def test_database_outage_after_handler_leaves_fenced_lease_for_reclaim(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(database, remote_id="database-outage-reclaim")
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    cycle = scheduler.tick(limit=1).cycles[0]
    original_session = database.session

    def unavailable_session() -> object:
        raise RuntimeError(f"database outage contains {SECRET}")

    def disable_database() -> None:
        monkeypatch.setattr(database, "session", unavailable_session)

    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": _DisableDatabaseHandler(disable_database)}),
        clock=clock,
    )
    fenced = await worker.run_once(
        worker_id="database-outage-worker",
        lease_seconds=1,
        heartbeat_interval_seconds=0.2,
    )
    monkeypatch.setattr(database, "session", original_session)

    assert (fenced.status, fenced.error_code) == ("fenced", "scheduler_finalize_failed")
    assert SECRET not in repr(fenced)
    with database.session() as session:
        running = session.get(Job, cycle.job_id)
        assert running is not None
        assert running.status == "running"
        assert running.lease_token is not None

    clock.value = NOW + timedelta(seconds=6)
    recovered = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": _SuccessHandler()}),
        clock=clock,
    ).run_once(worker_id="database-recovery-worker")

    assert recovered.status == "succeeded"
    assert recovered.job_id == cycle.job_id
    assert recovered.attempt == 2


@pytest.mark.asyncio
async def test_persistent_success_finalizer_outage_reconciles_on_lease_expiry(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscription_id = _seed(database)
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    cycle = scheduler.tick(limit=1).cycles[0]

    def unavailable_success_finalizer(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError(f"success finalizer outage contains {SECRET}")

    monkeypatch.setattr(SchedulerRepository, "succeed", unavailable_success_finalizer)
    fenced = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": _AttachingFakeHandler(database)}),
        clock=clock,
    ).run_once(
        worker_id="persistent-success-finalizer-worker",
        lease_seconds=1,
        heartbeat_interval_seconds=0.2,
    )

    assert (fenced.status, fenced.error_code) == ("fenced", "scheduler_finalize_failed")
    assert SECRET not in repr(fenced)
    with database.session() as session:
        running = session.get(Job, cycle.job_id)
        assert running is not None and running.status == "running"
        assert running.run_id is not None
        run = session.get(SyncRun, running.run_id)
        assert run is not None and run.status == "succeeded"

    clock.value = NOW + timedelta(seconds=6)
    recovered = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": _AttachingFakeHandler(database)}),
        clock=clock,
    ).run_once(worker_id="persistent-success-reclaim-worker")

    assert recovered.status == "idle"
    with database.session() as session:
        job = session.get(Job, cycle.job_id)
        subscription = session.get(Subscription, subscription_id)
        assert job is not None and job.status == "succeeded"
        assert job.run_id is not None and job.last_error_code is None
        assert job.lease_owner is None and job.lease_token is None
        assert subscription is not None and subscription.consecutive_failures == 0
        assert subscription.next_run_at == clock.value + timedelta(seconds=60)


@pytest.mark.asyncio
async def test_post_commit_cancel_reconciles_authoritative_succeeded_run(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscription_id = _seed(database)
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    cycle = scheduler.tick(limit=1).cycles[0]

    def unavailable_success_finalizer(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError(f"success finalizer outage contains {SECRET}")

    monkeypatch.setattr(SchedulerRepository, "succeed", unavailable_success_finalizer)
    fenced = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": _AttachingFakeHandler(database)}),
        clock=clock,
    ).run_once(worker_id="post-commit-cancel-worker")
    assert (fenced.status, fenced.error_code) == ("fenced", "scheduler_finalize_failed")

    reconciled = scheduler.cancel_job(cycle.job_id)

    assert reconciled.status == "succeeded"
    assert reconciled.last_error_code is None
    with database.session() as session:
        job = session.get(Job, cycle.job_id)
        subscription = session.get(Subscription, subscription_id)
        assert job is not None and job.status == "succeeded"
        assert job.run_id is not None
        run = session.get(SyncRun, job.run_id)
        assert run is not None and run.status == "succeeded"
        assert subscription is not None and subscription.consecutive_failures == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("max_jobs", [0, 1_001, True, 1.5])
async def test_run_bounded_rejects_invalid_job_limits(database: Database, max_jobs: object) -> None:
    worker = SubscriptionWorker(database, SubscriptionHandlerRegistry.fake_only(database), clock=_Clock())
    with pytest.raises(ValueError, match="max_jobs"):
        await worker.run_bounded(worker_id="bounded-invalid-worker", max_jobs=cast(int, max_jobs))


@pytest.mark.asyncio
@pytest.mark.parametrize("max_jobs", [1, 1_000])
async def test_run_bounded_accepts_edges_and_stops_at_idle(database: Database, max_jobs: int) -> None:
    worker = SubscriptionWorker(database, SubscriptionHandlerRegistry.fake_only(database), clock=_Clock())
    assert await worker.run_bounded(worker_id="bounded-idle-worker", max_jobs=max_jobs) == ()


@pytest.mark.asyncio
async def test_run_bounded_processes_one_job_then_stops_on_idle(database: Database) -> None:
    _seed(database, remote_id="bounded-one")
    clock = _Clock()
    DurableSchedulerService(database, clock=clock).tick(limit=1)
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": _SuccessHandler()}),
        clock=clock,
    )

    results = await worker.run_bounded(worker_id="bounded-one-worker", max_jobs=1_000)

    assert len(results) == 1
    assert results[0].status == "succeeded"


@pytest.mark.asyncio
async def test_run_bounded_observes_cooperative_cancellation_before_next_job(database: Database) -> None:
    _seed(database, remote_id="bounded-cancel-first")
    _seed(database, remote_id="bounded-cancel-second")
    clock = _Clock()
    assert DurableSchedulerService(database, clock=clock).tick(limit=2).materialized_count == 2
    cancellation = ThreadEvent()
    handler = _CancellingSuccessHandler(cancellation)
    worker = SubscriptionWorker(database, SubscriptionHandlerRegistry({"fake": handler}), clock=clock)

    results = await worker.run_bounded(
        worker_id="bounded-cancel-worker",
        max_jobs=2,
        cancellation=cancellation,
    )

    assert len(results) == 1
    assert results[0].status == "succeeded"
    assert handler.calls == 1
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Job).where(Job.status == "queued")) == 1


@pytest.mark.asyncio
async def test_waiting_auth_is_dormant_until_explicit_resume(database: Database) -> None:
    _seed(database, remote_id="waiting-auth-resume")
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    scheduler.tick(limit=1)
    waiting_worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": _ResultHandler(SubscriptionHandlerResult.failure("auth_expired"))}),
        clock=clock,
    )

    waiting = await waiting_worker.run_once(worker_id="waiting-auth-worker")
    clock.value += timedelta(days=1)
    dormant = await waiting_worker.run_once(worker_id="waiting-auth-worker")
    resumed = scheduler.resume_job(waiting.job_id or "")
    succeeded = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": _SuccessHandler()}),
        clock=clock,
    ).run_once(worker_id="waiting-auth-resumed-worker")

    assert (waiting.status, waiting.error_code) == ("waiting_auth", "auth_expired")
    assert dormant.status == "idle"
    assert resumed.status == "queued"
    assert succeeded.status == "succeeded"
    assert succeeded.attempt == 2
