"""Ongoing lifecycle events are committed, bounded and independent of log IO."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator, Mapping
from pathlib import Path
from uuid import uuid4

import pytest

from media_sync.application.observability import emit_event, event_context
from media_sync.application.operation_payloads import OperationKind
from media_sync.application.operations import (
    OperationCoordinator,
    OperationExecution,
    OperationExecutionContext,
    OperationOutcome,
)
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.observability.events import validate_event
from media_sync.scheduler.handlers import FakeSubscriptionHandler, SubscriptionHandlerRegistry
from media_sync.scheduler.pipeline_worker import PipelineHandlerResult, PipelineSubscriptionWorker
from media_sync.scheduler.service import DurableSchedulerService, SubscriptionWorker
from tests.integration.test_operation_coordinator import _wait_terminal
from tests.integration.test_pipeline_worker import NOW as PIPELINE_NOW
from tests.integration.test_pipeline_worker import _seed_pipeline
from tests.integration.test_scheduler_worker import NOW, _seed
from tests.unit.test_scheduler_supervisor import _PipelineWorker, _Scheduler, _SubscriptionWorker, _supervisor, _Sweep


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'lifecycle.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


@pytest.mark.parametrize(
    ("kind", "target_type", "module"),
    [
        ("account-cookie-login", "account", "cookie_login"),
        ("creator-profile", "account", "creator_profile"),
        ("account-login", "account", "login"),
        ("asset-download", "asset", "download"),
        ("scheduler-run", None, "scheduler"),
        ("pipeline-run", None, "pipeline"),
        ("emby-export", "author", "exporter"),
        ("media-server-probe", None, "media_server"),
        ("media-server-scan", None, "media_server"),
    ],
)
def test_all_operation_kinds_emit_live_safe_committed_lifecycle(
    database: Database,
    kind: OperationKind,
    target_type: str | None,
    module: str,
) -> None:
    events: list[Mapping[str, object]] = []
    observed_states: list[str] = []
    correlation_id = str(uuid4())
    entered, release = threading.Event(), threading.Event()

    def sink(event: Mapping[str, object]) -> None:
        events.append(event)
        if event["event_code"] in {"operation_started", "operation_finished"}:
            observed_states.append(coordinator.get(str(event["operation_id"])).state)

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        context.phase("preparing")
        context.phase("preparing")
        context.phase("secret-phase-sentinel")
        emit_event(sink, event_code="application_log_redacted", module=module, count=1)
        entered.set()
        assert release.wait(5)
        return OperationOutcome.cancelled()

    execution = OperationExecution(
        kind=kind,
        request_fingerprint="a" * 64,
        idempotency_key_hash="b" * 64,
        execute=execute,
        correlation_id=correlation_id,
        target_type=target_type,
        target_id=str(uuid4()) if target_type else None,
        requested_by="SENTINEL-private-requester",
    )
    coordinator = OperationCoordinator(database, event_sink=sink, heartbeat_interval_seconds=0.05)
    try:
        with event_context(operation_id=str(uuid4()), job_id=str(uuid4())):
            submission = coordinator.submit(execution)
        assert entered.wait(5)
        assert [event["event_code"] for event in events] == [
            "operation_started",
            "operation_phase_changed",
            "operation_phase_changed",
            "application_log_redacted",
        ]
        assert events[2]["phase"] == "unknown"
        assert coordinator.submit(execution).replayed
        assert len(events) == 4
        release.set()
        assert _wait_terminal(coordinator, submission.operation_id).state == "cancelled"
    finally:
        release.set()
        coordinator.shutdown()
    assert [event["event_code"] for event in events][-1] == "operation_finished"
    assert events[-1]["outcome"] == "cancelled"
    assert observed_states == ["running", "cancelled"]
    assert all(event["operation_id"] == submission.operation_id for event in events)
    assert all(event["correlation_id"] == correlation_id for event in events)
    assert all(event["module"] == module for event in events)
    assert all("job_id" not in event for event in events)
    assert "SENTINEL" not in repr(events) and "secret-phase" not in repr(events)
    assert all(validate_event(event) == event for event in events)


@pytest.mark.parametrize("state", ["succeeded", "failed_retryable", "failed_terminal", "cancelled"])
@pytest.mark.parametrize("error", [RuntimeError, SystemExit])
def test_operation_sink_failure_does_not_change_outcome(
    database: Database,
    state: str,
    error: type[BaseException],
) -> None:
    def sink(_event: Mapping[str, object]) -> None:
        raise error("SENTINEL-log-disk-full")

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        context.phase("preparing")
        if state == "succeeded":
            return OperationOutcome.success({"statuses": []})
        if state == "cancelled":
            return OperationOutcome.cancelled()
        return OperationOutcome.failed("operation_execution_failed", retryable=state == "failed_retryable")

    with OperationCoordinator(database, event_sink=sink, heartbeat_interval_seconds=0.05) as coordinator:
        submission = coordinator.submit(
            OperationExecution(kind="scheduler-run", request_fingerprint="c" * 64, execute=execute)
        )
        assert _wait_terminal(coordinator, submission.operation_id).state == state


async def test_scheduler_attempt_links_durable_job_run_and_parent_context_without_idle_noise(
    database: Database,
) -> None:
    subscription_id = _seed(database)
    cycle = DurableSchedulerService(database, clock=lambda: NOW).tick(limit=1).cycles[0]
    events: list[Mapping[str, object]] = []
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": FakeSubscriptionHandler(database)}),
        clock=lambda: NOW,
        event_sink=events.append,
    )
    parent_id, correlation_id = str(uuid4()), str(uuid4())
    with event_context(operation_id=parent_id, correlation_id=correlation_id, run_id=str(uuid4())):
        result = await worker.run_once(worker_id="SENTINEL-owner")
        assert (await worker.run_once(worker_id="SENTINEL-owner")).status == "idle"
    assert result.status == "succeeded"
    assert [event["event_code"] for event in events] == ["job_started", "job_finished"]
    assert all(event["job_id"] == cycle.job_id and event["subscription_id"] == subscription_id for event in events)
    assert all(event["operation_id"] == parent_id and event["correlation_id"] == correlation_id for event in events)
    assert "run_id" not in events[0]
    assert events[-1]["run_id"] == result.run_id
    assert events[-1]["outcome"] == "succeeded"
    assert "SENTINEL" not in repr(events)


@pytest.mark.parametrize("failure", [False, True])
async def test_pipeline_attempt_links_source_run_and_matches_durable_outcome(database: Database, failure: bool) -> None:
    job_id, _, subscription_id, account_id, run_id = _seed_pipeline(database, remote_id="SENTINEL-remote-id")
    events: list[Mapping[str, object]] = []
    worker = PipelineSubscriptionWorker(
        database,
        lambda _claim: (
            PipelineHandlerResult.failure("pipeline_worker_error") if failure else PipelineHandlerResult.success()
        ),
        clock=lambda: PIPELINE_NOW,
        event_sink=events.append,
    )
    result = await worker.run_once(worker_id="SENTINEL-owner")
    assert (await worker.run_once(worker_id="SENTINEL-owner")).status == "idle"
    assert [event["event_code"] for event in events] == ["job_started", "job_finished"]
    assert all(event["job_id"] == job_id and event["subscription_id"] == subscription_id for event in events)
    assert all(event["run_id"] == run_id and event["account_id"] == account_id for event in events)
    assert events[-1]["outcome"] == result.status == ("retry_wait" if failure else "succeeded")
    assert "SENTINEL" not in repr(events)


@pytest.mark.parametrize("mode", ["stop", "fail", "cancel"])
async def test_supervisor_events_are_lifecycle_only_even_after_idle_cycles(mode: str) -> None:
    trace: list[str] = []
    events: list[Mapping[str, object]] = []
    idle_cycles = 0

    async def idle_wait(stop: asyncio.Event, _timeout: float) -> None:
        nonlocal idle_cycles
        idle_cycles += 1
        if idle_cycles < 3:
            return
        if mode == "fail":
            raise RuntimeError("SENTINEL-idle-failure")
        if mode == "cancel":
            raise asyncio.CancelledError("SENTINEL-idle-cancel")
        stop.set()

    supervisor = _supervisor(
        sweep=_Sweep(trace),
        scheduler=_Scheduler(trace),
        subscription=_SubscriptionWorker(trace),
        pipeline=_PipelineWorker(trace),
        idle_wait=idle_wait,
    )
    supervisor.event_sink = events.append
    if mode == "stop":
        assert (await supervisor.run()).stopped
    else:
        with pytest.raises(RuntimeError if mode == "fail" else asyncio.CancelledError):
            await supervisor.run()
    assert idle_cycles == 3
    assert len(events) == 2
    assert events[0]["event_code"] == "supervisor_started"
    assert events[-1]["event_code"] == ("supervisor_failed" if mode == "fail" else "supervisor_stopped")
    assert events[-1]["outcome"] == {"stop": "stopped", "fail": "failed", "cancel": "cancelled"}[mode]
    assert "SENTINEL" not in repr(events)


def test_parallel_operation_threads_use_their_own_committed_correlation(database: Database) -> None:
    events: list[Mapping[str, object]] = []
    barrier = threading.Barrier(2)
    correlations = [str(uuid4()), str(uuid4())]

    def execute(_context: OperationExecutionContext) -> OperationOutcome:
        barrier.wait(timeout=5)
        emit_event(events.append, event_code="application_log_redacted", module="scheduler", count=1)
        return OperationOutcome.success({"statuses": []})

    with OperationCoordinator(database, event_sink=events.append, heartbeat_interval_seconds=0.05) as coordinator:
        submissions = [
            coordinator.submit(
                OperationExecution(
                    kind="scheduler-run",
                    request_fingerprint=f"{index + 1:064x}",
                    execute=execute,
                    correlation_id=correlation,
                )
            )
            for index, correlation in enumerate(correlations)
        ]
        for submission in submissions:
            assert _wait_terminal(coordinator, submission.operation_id).state == "succeeded"
    for submission, correlation in zip(submissions, correlations, strict=True):
        own_events = [event for event in events if event["operation_id"] == submission.operation_id]
        assert len(own_events) == 3
        assert all(event["correlation_id"] == correlation for event in own_events)
        assert own_events[-1]["outcome"] == "succeeded"


@pytest.mark.parametrize("error", [RuntimeError, SystemExit])
async def test_worker_and_supervisor_sink_failure_never_changes_outcomes(
    database: Database,
    error: type[BaseException],
) -> None:
    def sink(_event: Mapping[str, object]) -> None:
        raise error("SENTINEL-log-io-failure")

    _seed(database)
    DurableSchedulerService(database, clock=lambda: NOW).tick(limit=1)
    subscription = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"fake": FakeSubscriptionHandler(database)}),
        clock=lambda: NOW,
        event_sink=sink,
    )
    assert (await subscription.run_once(worker_id="sync-owner")).status == "succeeded"
    pipeline = PipelineSubscriptionWorker(
        database,
        lambda _claim: PipelineHandlerResult.success(),
        clock=lambda: PIPELINE_NOW,
        event_sink=sink,
    )
    assert (await pipeline.run_once(worker_id="pipeline-owner")).status == "succeeded"
    trace: list[str] = []

    async def idle_wait(stop: asyncio.Event, _timeout: float) -> None:
        stop.set()

    supervisor = _supervisor(
        sweep=_Sweep(trace),
        scheduler=_Scheduler(trace),
        subscription=_SubscriptionWorker(trace),
        pipeline=_PipelineWorker(trace),
        idle_wait=idle_wait,
    )
    supervisor.event_sink = sink
    assert (await supervisor.run()).stopped


@pytest.mark.parametrize("worker_kind", ["scheduler", "pipeline"])
async def test_rolled_back_claim_emits_no_false_job_started(database: Database, worker_kind: str) -> None:
    events: list[Mapping[str, object]] = []
    if worker_kind == "scheduler":
        _seed(database)
        DurableSchedulerService(database, clock=lambda: NOW).tick(limit=1)
        worker = SubscriptionWorker(
            database,
            SubscriptionHandlerRegistry({"fake": FakeSubscriptionHandler(database)}),
            clock=lambda: NOW,
            event_sink=events.append,
        )
    else:
        _seed_pipeline(database, remote_id="rollback-author")
        worker = PipelineSubscriptionWorker(  # type: ignore[assignment]
            database,
            lambda _claim: PipelineHandlerResult.success(),
            clock=lambda: PIPELINE_NOW,
            event_sink=events.append,
        )

    def failed_hook(_session: object, _subject: object) -> None:
        raise RuntimeError("SENTINEL-claim-rollback")

    with pytest.raises(RuntimeError, match="SENTINEL-claim-rollback"):
        await worker.run_once(worker_id="rollback-owner", subject_hook=failed_hook)
    assert events == []
    assert (await worker.run_once(worker_id="rollback-owner")).status == "succeeded"
    assert events[0]["event_code"] == "job_started"
