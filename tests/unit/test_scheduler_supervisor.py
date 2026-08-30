"""Deterministic phase and shutdown tests for the foreground supervisor."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event as ThreadEvent
from typing import Any

import pytest

from media_sync.scheduler import (
    PipelineWorkerResult,
    ResidentSchedulerSupervisor,
    ResidentSupervisorConfig,
    SchedulerWorkerResult,
)


@dataclass(frozen=True, slots=True)
class _SweepSummary:
    scanned: int = 0
    recovered: int = 0
    busy: int = 0
    conflicted: int = 0


@dataclass(frozen=True, slots=True)
class _TickResult:
    materialized_count: int = 0


class _Sweep:
    def __init__(
        self,
        trace: list[str],
        *,
        summary: _SweepSummary | None = None,
        entered: ThreadEvent | None = None,
        release: ThreadEvent | None = None,
        effect: Callable[[], None] | None = None,
    ) -> None:
        self.trace = trace
        self.summary = summary or _SweepSummary()
        self.entered = entered
        self.release = release
        self.effect = effect
        self.calls: list[int] = []

    def __call__(self, *, limit: int) -> _SweepSummary:
        self.calls.append(limit)
        self.trace.append("login_sweep")
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            assert self.release.wait(timeout=2)
        if self.effect is not None:
            self.effect()
        return self.summary


class _Scheduler:
    def __init__(
        self,
        trace: list[str],
        *,
        materialized: int = 0,
        entered: ThreadEvent | None = None,
        release: ThreadEvent | None = None,
    ) -> None:
        self.trace = trace
        self.materialized = materialized
        self.entered = entered
        self.release = release
        self.calls: list[int] = []

    def tick(self, *, limit: int) -> _TickResult:
        self.calls.append(limit)
        self.trace.append("scheduler_tick")
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            assert self.release.wait(timeout=2)
        return _TickResult(self.materialized)


class _SubscriptionWorker:
    def __init__(
        self,
        trace: list[str],
        *,
        statuses: tuple[str, ...] = ("idle",),
        block: bool = False,
        block_cancel_join: bool = False,
    ) -> None:
        self.trace = trace
        self.statuses = statuses
        self.block = block
        self.block_cancel_join = block_cancel_join
        self.calls: list[dict[str, object]] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.cancel_join_started = asyncio.Event()
        self.cancel_join_release = asyncio.Event()
        self.joined = asyncio.Event()

    async def run_once(self, **kwargs: object) -> SchedulerWorkerResult:
        self.calls.append(kwargs)
        self.trace.append("subscription")
        index = min(len(self.calls) - 1, len(self.statuses) - 1)
        self.started.set()
        try:
            if self.block:
                await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            if self.block_cancel_join:
                self.cancel_join_started.set()
                while not self.cancel_join_release.is_set():
                    try:
                        await self.cancel_join_release.wait()
                    except asyncio.CancelledError:
                        continue
            raise
        finally:
            self.joined.set()
        status = self.statuses[index]
        return SchedulerWorkerResult(
            job_id="SENTINEL-subscription-job" if status != "idle" else None,
            subscription_id="SENTINEL-subscription" if status != "idle" else None,
            status=status,
        )


class _PipelineWorker:
    def __init__(
        self,
        trace: list[str],
        *,
        statuses: tuple[str, ...] = ("idle",),
        block: bool = False,
    ) -> None:
        self.trace = trace
        self.statuses = statuses
        self.block = block
        self.calls: list[dict[str, object]] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.joined = asyncio.Event()

    async def run_once(self, **kwargs: object) -> PipelineWorkerResult:
        self.calls.append(kwargs)
        self.trace.append("pipeline")
        index = min(len(self.calls) - 1, len(self.statuses) - 1)
        self.started.set()
        try:
            if self.block:
                await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        finally:
            self.joined.set()
        status = self.statuses[index]
        return PipelineWorkerResult(
            job_id="SENTINEL-pipeline-job" if status != "idle" else None,
            subscription_id="SENTINEL-subscription" if status != "idle" else None,
            status=status,
        )


def _supervisor(
    *,
    sweep: _Sweep,
    scheduler: _Scheduler,
    subscription: _SubscriptionWorker,
    pipeline: _PipelineWorker,
    config: ResidentSupervisorConfig | None = None,
    idle_wait: Callable[[asyncio.Event, float], Any] | None = None,
) -> ResidentSchedulerSupervisor:
    return ResidentSchedulerSupervisor(
        stale_login_sweep=sweep,
        scheduler=scheduler,
        subscription_worker=subscription,
        pipeline_worker=pipeline,
        subscription_worker_id="resident-sync-unique",
        pipeline_worker_id="resident-pipeline-unique",
        config=config,
        idle_wait=idle_wait,
    )


@pytest.mark.asyncio
async def test_cycle_is_ordered_bounded_fair_and_uses_stable_worker_ids() -> None:
    trace: list[str] = []
    sweep = _Sweep(trace, summary=_SweepSummary(scanned=1, recovered=1))
    scheduler = _Scheduler(trace, materialized=2)
    subscription = _SubscriptionWorker(trace, statuses=("succeeded",))
    pipeline = _PipelineWorker(trace, statuses=("succeeded",))
    supervisor = _supervisor(
        sweep=sweep,
        scheduler=scheduler,
        subscription=subscription,
        pipeline=pipeline,
        config=ResidentSupervisorConfig(
            login_sweep_limit=7,
            materialize_limit=8,
            subscription_jobs_per_cycle=2,
            pipeline_jobs_per_cycle=3,
            subscription_global_capacity=4,
            subscription_lease_seconds=20,
            subscription_scan_limit=9,
            subscription_heartbeat_interval_seconds=2.5,
            pipeline_lease_seconds=30,
            pipeline_scan_limit=10,
            pipeline_heartbeat_interval_seconds=3.5,
        ),
    )

    first = await supervisor.run_cycle()
    second = await supervisor.run_cycle()

    expected_cycle = [
        "login_sweep",
        "scheduler_tick",
        "subscription",
        "subscription",
        "pipeline",
        "pipeline",
        "pipeline",
    ]
    assert trace == expected_cycle * 2
    assert first == second
    assert (
        first.cycles,
        first.login_scanned,
        first.login_recovered,
        first.materialized,
        first.subscription_attempts,
        first.pipeline_attempts,
        first.outcome,
    ) == (1, 1, 1, 2, 2, 3, "cycle_complete")
    assert first.made_progress is True and first.stopped is False
    assert sweep.calls == [7, 7]
    assert scheduler.calls == [8, 8]
    assert {call["worker_id"] for call in subscription.calls} == {"resident-sync-unique"}
    assert {call["worker_id"] for call in pipeline.calls} == {"resident-pipeline-unique"}
    assert subscription.calls[0] == {
        "worker_id": "resident-sync-unique",
        "global_capacity": 4,
        "lease_seconds": 20,
        "scan_limit": 9,
        "heartbeat_interval_seconds": 2.5,
    }
    assert pipeline.calls[0] == {
        "worker_id": "resident-pipeline-unique",
        "lease_seconds": 30,
        "scan_limit": 10,
        "heartbeat_interval_seconds": 3.5,
    }
    assert "SENTINEL" not in repr(first)


@pytest.mark.asyncio
async def test_idle_run_waits_only_after_all_phases_are_idle_and_stop_wakes_it() -> None:
    trace: list[str] = []
    wait_entered = asyncio.Event()
    wait_calls: list[float] = []

    async def idle_wait(stop: asyncio.Event, timeout: float) -> None:
        wait_calls.append(timeout)
        wait_entered.set()
        await stop.wait()

    sweep = _Sweep(trace)
    scheduler = _Scheduler(trace)
    subscription = _SubscriptionWorker(trace)
    pipeline = _PipelineWorker(trace)
    supervisor = _supervisor(
        sweep=sweep,
        scheduler=scheduler,
        subscription=subscription,
        pipeline=pipeline,
        config=ResidentSupervisorConfig(idle_interval_seconds=17.25),
        idle_wait=idle_wait,
    )

    task = asyncio.create_task(supervisor.run())
    await asyncio.wait_for(wait_entered.wait(), timeout=1)
    supervisor.request_stop()
    result = await asyncio.wait_for(task, timeout=1)

    assert trace == ["login_sweep", "scheduler_tick", "subscription", "pipeline"]
    assert wait_calls == [17.25]
    assert result.cycles == 1
    assert result.made_progress is False
    assert (result.stopped, result.outcome) == (True, "stopped_during_idle_wait")


@pytest.mark.asyncio
async def test_progress_starts_the_next_cycle_without_entering_idle_wait() -> None:
    trace: list[str] = []
    wait_calls = 0
    supervisor_ref: list[ResidentSchedulerSupervisor] = []

    async def idle_wait(_stop: asyncio.Event, _timeout: float) -> None:
        nonlocal wait_calls
        wait_calls += 1

    sweep = _Sweep(trace, summary=_SweepSummary(scanned=1, recovered=1))
    scheduler = _Scheduler(trace)
    subscription = _SubscriptionWorker(trace)
    pipeline = _PipelineWorker(trace)

    def stop_on_second_sweep() -> None:
        if len(sweep.calls) == 2:
            supervisor_ref[0].request_stop()

    sweep.effect = stop_on_second_sweep
    supervisor = _supervisor(
        sweep=sweep,
        scheduler=scheduler,
        subscription=subscription,
        pipeline=pipeline,
        idle_wait=idle_wait,
    )
    supervisor_ref.append(supervisor)

    result = await supervisor.run()

    assert sweep.calls == [100, 100]
    assert wait_calls == 0
    assert result.cycles == 2
    assert result.outcome == "stopped_after_login_sweep"


@pytest.mark.asyncio
async def test_stop_during_threaded_login_sweep_prevents_tick_and_claims() -> None:
    trace: list[str] = []
    entered = ThreadEvent()
    release = ThreadEvent()
    sweep = _Sweep(trace, entered=entered, release=release)
    scheduler = _Scheduler(trace)
    subscription = _SubscriptionWorker(trace, statuses=("succeeded",))
    pipeline = _PipelineWorker(trace, statuses=("succeeded",))
    supervisor = _supervisor(
        sweep=sweep,
        scheduler=scheduler,
        subscription=subscription,
        pipeline=pipeline,
    )

    task = asyncio.create_task(supervisor.run_cycle())
    assert await asyncio.to_thread(entered.wait, 1)
    supervisor.request_stop()
    release.set()
    result = await asyncio.wait_for(task, timeout=1)

    assert result.outcome == "stopped_after_login_sweep"
    assert scheduler.calls == []
    assert subscription.calls == []
    assert pipeline.calls == []


@pytest.mark.asyncio
async def test_stop_during_threaded_tick_prevents_every_later_claim() -> None:
    trace: list[str] = []
    entered = ThreadEvent()
    release = ThreadEvent()
    sweep = _Sweep(trace)
    scheduler = _Scheduler(trace, materialized=1, entered=entered, release=release)
    subscription = _SubscriptionWorker(trace, statuses=("succeeded",))
    pipeline = _PipelineWorker(trace, statuses=("succeeded",))
    supervisor = _supervisor(
        sweep=sweep,
        scheduler=scheduler,
        subscription=subscription,
        pipeline=pipeline,
    )

    task = asyncio.create_task(supervisor.run_cycle())
    assert await asyncio.to_thread(entered.wait, 1)
    supervisor.request_stop()
    release.set()
    result = await asyncio.wait_for(task, timeout=1)

    assert (result.materialized, result.outcome) == (1, "stopped_after_scheduler_tick")
    assert subscription.calls == []
    assert pipeline.calls == []


@pytest.mark.asyncio
async def test_stop_cancels_and_awaits_active_subscription_before_exit() -> None:
    trace: list[str] = []
    subscription = _SubscriptionWorker(trace, statuses=("succeeded",), block=True)
    pipeline = _PipelineWorker(trace, statuses=("succeeded",))
    supervisor = _supervisor(
        sweep=_Sweep(trace),
        scheduler=_Scheduler(trace, materialized=1),
        subscription=subscription,
        pipeline=pipeline,
        config=ResidentSupervisorConfig(subscription_jobs_per_cycle=3, pipeline_jobs_per_cycle=3),
    )

    task = asyncio.create_task(supervisor.run_cycle())
    await asyncio.wait_for(subscription.started.wait(), timeout=1)
    supervisor.request_stop()
    result = await asyncio.wait_for(task, timeout=1)

    assert subscription.cancelled.is_set() and subscription.joined.is_set()
    assert len(subscription.calls) == 1
    assert pipeline.calls == []
    assert (result.subscription_attempts, result.outcome) == (0, "stopped_during_subscription")
    again = await supervisor.run_cycle()
    assert again.outcome == "stopped_before_cycle"
    assert len(subscription.calls) == 1


@pytest.mark.asyncio
async def test_task_cancellation_also_joins_active_subscription() -> None:
    trace: list[str] = []
    subscription = _SubscriptionWorker(trace, statuses=("succeeded",), block=True)
    supervisor = _supervisor(
        sweep=_Sweep(trace),
        scheduler=_Scheduler(trace, materialized=1),
        subscription=subscription,
        pipeline=_PipelineWorker(trace),
    )

    task = asyncio.create_task(supervisor.run_cycle())
    await asyncio.wait_for(subscription.started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert supervisor.stop_event.is_set()
    assert subscription.cancelled.is_set() and subscription.joined.is_set()


@pytest.mark.asyncio
async def test_repeated_task_cancellation_during_subscription_join_waits_for_exact_attempt() -> None:
    trace: list[str] = []
    subscription = _SubscriptionWorker(
        trace,
        statuses=("succeeded",),
        block=True,
        block_cancel_join=True,
    )
    pipeline = _PipelineWorker(trace)
    supervisor = _supervisor(
        sweep=_Sweep(trace),
        scheduler=_Scheduler(trace, materialized=1),
        subscription=subscription,
        pipeline=pipeline,
    )

    task = asyncio.create_task(supervisor.run_cycle())
    await asyncio.wait_for(subscription.started.wait(), timeout=1)
    supervisor.request_stop()
    await asyncio.wait_for(subscription.cancel_join_started.wait(), timeout=1)

    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert task.done() is False
    assert subscription.joined.is_set() is False
    assert pipeline.calls == []

    subscription.cancel_join_release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)

    assert subscription.cancelled.is_set() and subscription.joined.is_set()
    assert len(subscription.calls) == 1


@pytest.mark.asyncio
async def test_stop_drains_active_pipeline_without_cancelling_or_claiming_successor() -> None:
    trace: list[str] = []
    subscription = _SubscriptionWorker(trace)
    pipeline = _PipelineWorker(trace, statuses=("succeeded",), block=True)
    supervisor = _supervisor(
        sweep=_Sweep(trace),
        scheduler=_Scheduler(trace),
        subscription=subscription,
        pipeline=pipeline,
        config=ResidentSupervisorConfig(pipeline_jobs_per_cycle=3),
    )

    task = asyncio.create_task(supervisor.run_cycle())
    await asyncio.wait_for(pipeline.started.wait(), timeout=1)
    supervisor.request_stop()
    await asyncio.sleep(0)
    assert task.done() is False
    assert pipeline.cancelled.is_set() is False
    pipeline.release.set()
    result = await asyncio.wait_for(task, timeout=1)

    assert pipeline.cancelled.is_set() is False
    assert pipeline.joined.is_set() is True
    assert len(pipeline.calls) == 1
    assert (result.pipeline_attempts, result.outcome) == (1, "stopped_during_pipeline")


@pytest.mark.asyncio
async def test_task_cancellation_drains_pipeline_before_propagating_cancel() -> None:
    trace: list[str] = []
    pipeline = _PipelineWorker(trace, statuses=("succeeded",), block=True)
    supervisor = _supervisor(
        sweep=_Sweep(trace),
        scheduler=_Scheduler(trace),
        subscription=_SubscriptionWorker(trace),
        pipeline=pipeline,
    )

    task = asyncio.create_task(supervisor.run_cycle())
    await asyncio.wait_for(pipeline.started.wait(), timeout=1)
    task.cancel()
    await asyncio.sleep(0)
    assert task.done() is False
    assert pipeline.cancelled.is_set() is False
    pipeline.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert supervisor.stop_event.is_set()
    assert pipeline.cancelled.is_set() is False
    assert pipeline.joined.is_set()
    assert len(pipeline.calls) == 1


@pytest.mark.asyncio
async def test_repeated_task_cancellation_after_stop_still_drains_exact_pipeline_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace: list[str] = []
    pipeline = _PipelineWorker(trace, statuses=("succeeded",), block=True)
    supervisor = _supervisor(
        sweep=_Sweep(trace),
        scheduler=_Scheduler(trace),
        subscription=_SubscriptionWorker(trace),
        pipeline=pipeline,
    )
    drain_started = asyncio.Event()
    original_drain = supervisor._drain_pipeline_attempt

    async def observed_drain(
        attempt: asyncio.Task[PipelineWorkerResult | None],
        *,
        cancellation: asyncio.CancelledError | None = None,
    ) -> PipelineWorkerResult | None:
        drain_started.set()
        return await original_drain(attempt, cancellation=cancellation)

    monkeypatch.setattr(supervisor, "_drain_pipeline_attempt", observed_drain)
    task = asyncio.create_task(supervisor.run_cycle())
    await asyncio.wait_for(pipeline.started.wait(), timeout=1)
    supervisor.request_stop()
    await asyncio.wait_for(drain_started.wait(), timeout=1)

    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert task.done() is False
    assert pipeline.cancelled.is_set() is False
    assert pipeline.joined.is_set() is False

    pipeline.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)

    assert pipeline.cancelled.is_set() is False
    assert pipeline.joined.is_set()
    assert len(pipeline.calls) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("idle_interval_seconds", 0),
        ("idle_interval_seconds", True),
        ("idle_interval_seconds", float("inf")),
        ("idle_interval_seconds", float("nan")),
        ("idle_interval_seconds", 3_600.01),
        ("login_sweep_limit", 0),
        ("materialize_limit", 1_001),
        ("subscription_jobs_per_cycle", True),
        ("pipeline_jobs_per_cycle", 0),
        ("subscription_global_capacity", 1_001),
        ("subscription_lease_seconds", 0),
        ("subscription_lease_seconds", 86_401),
        ("subscription_scan_limit", 0),
        ("subscription_heartbeat_interval_seconds", 60),
        ("subscription_heartbeat_interval_seconds", float("nan")),
        ("pipeline_lease_seconds", True),
        ("pipeline_scan_limit", 1_001),
        ("pipeline_heartbeat_interval_seconds", 300),
        ("pipeline_heartbeat_interval_seconds", float("inf")),
    ],
)
def test_config_rejects_unbounded_or_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        ResidentSupervisorConfig(**{field: value})


def test_supervisor_rejects_invalid_or_reused_worker_ids() -> None:
    trace: list[str] = []
    dependencies = {
        "stale_login_sweep": _Sweep(trace),
        "scheduler": _Scheduler(trace),
        "subscription_worker": _SubscriptionWorker(trace),
        "pipeline_worker": _PipelineWorker(trace),
    }
    with pytest.raises(ValueError, match="subscription_worker_id"):
        ResidentSchedulerSupervisor(
            **dependencies,
            subscription_worker_id=" ",
            pipeline_worker_id="pipeline",
        )
    with pytest.raises(ValueError, match="distinct"):
        ResidentSchedulerSupervisor(
            **dependencies,
            subscription_worker_id="same-worker",
            pipeline_worker_id="same-worker",
        )


@pytest.mark.asyncio
async def test_supervisor_rejects_malformed_sweep_summary_without_leaking_it() -> None:
    trace: list[str] = []
    supervisor = _supervisor(
        sweep=_Sweep(trace, summary=_SweepSummary(scanned=2, recovered=1)),
        scheduler=_Scheduler(trace),
        subscription=_SubscriptionWorker(trace),
        pipeline=_PipelineWorker(trace),
    )

    with pytest.raises(ValueError, match="redaction-safe summary"):
        await supervisor.run_cycle()

    assert trace == ["login_sweep"]
