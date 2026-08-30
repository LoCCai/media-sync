"""Fair foreground supervision for the local scheduler and media pipeline."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal, Protocol

from .pipeline_worker import PipelineSubscriptionWorker, PipelineWorkerResult
from .service import (
    DurableSchedulerService,
    SchedulerTickResult,
    SchedulerWorkerResult,
    SubscriptionWorker,
)

_MAX_BATCH = 1_000
_MAX_LEASE_SECONDS = 86_400
_MAX_IDLE_INTERVAL_SECONDS = 3_600.0

ResidentSupervisorOutcome = Literal[
    "cycle_complete",
    "stopped_before_cycle",
    "stopped_after_login_sweep",
    "stopped_after_scheduler_tick",
    "stopped_during_subscription",
    "stopped_before_pipeline",
    "stopped_during_pipeline",
    "stopped_during_idle_wait",
]


class _LoginSweepSummary(Protocol):
    """Structural boundary implemented by the authentication reconciler."""

    @property
    def scanned(self) -> int: ...

    @property
    def recovered(self) -> int: ...

    @property
    def busy(self) -> int: ...

    @property
    def conflicted(self) -> int: ...


class _StaleLoginSweep(Protocol):
    def __call__(self, *, limit: int) -> _LoginSweepSummary: ...


IdleWait = Callable[[asyncio.Event, float], Awaitable[None]]


def _bounded_int(value: int, *, name: str, maximum: int = _MAX_BATCH) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


def _heartbeat_interval(value: float | None, *, name: str, lease_seconds: int) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0 < float(value) < lease_seconds
    ):
        raise ValueError(f"{name} must be finite, positive and shorter than its lease")


def _worker_id(value: str, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 255
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized)
    ):
        raise ValueError(f"{name} is invalid")
    return normalized


@dataclass(frozen=True, slots=True)
class ResidentSupervisorConfig:
    """Bound every unit of work performed by one resident cycle."""

    idle_interval_seconds: float = 1.0
    login_sweep_limit: int = 100
    materialize_limit: int = 100
    subscription_jobs_per_cycle: int = 1
    pipeline_jobs_per_cycle: int = 1
    subscription_global_capacity: int = 1
    subscription_lease_seconds: int = 60
    subscription_scan_limit: int = 100
    subscription_heartbeat_interval_seconds: float | None = None
    pipeline_lease_seconds: int = 300
    pipeline_scan_limit: int = 100
    pipeline_heartbeat_interval_seconds: float | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.idle_interval_seconds, bool)
            or not isinstance(self.idle_interval_seconds, (int, float))
            or not math.isfinite(float(self.idle_interval_seconds))
            or not 0 < float(self.idle_interval_seconds) <= _MAX_IDLE_INTERVAL_SECONDS
        ):
            raise ValueError("idle_interval_seconds must be finite and between 0 and 3600")
        for name in (
            "login_sweep_limit",
            "materialize_limit",
            "subscription_jobs_per_cycle",
            "pipeline_jobs_per_cycle",
            "subscription_global_capacity",
            "subscription_scan_limit",
            "pipeline_scan_limit",
        ):
            _bounded_int(getattr(self, name), name=name)
        _bounded_int(
            self.subscription_lease_seconds,
            name="subscription_lease_seconds",
            maximum=_MAX_LEASE_SECONDS,
        )
        _bounded_int(
            self.pipeline_lease_seconds,
            name="pipeline_lease_seconds",
            maximum=_MAX_LEASE_SECONDS,
        )
        _heartbeat_interval(
            self.subscription_heartbeat_interval_seconds,
            name="subscription_heartbeat_interval_seconds",
            lease_seconds=self.subscription_lease_seconds,
        )
        _heartbeat_interval(
            self.pipeline_heartbeat_interval_seconds,
            name="pipeline_heartbeat_interval_seconds",
            lease_seconds=self.pipeline_lease_seconds,
        )


@dataclass(frozen=True, slots=True)
class ResidentSupervisorResult:
    """Fixed redaction-safe counts from one cycle or a complete foreground run."""

    cycles: int = 0
    login_scanned: int = 0
    login_recovered: int = 0
    login_busy: int = 0
    login_conflicted: int = 0
    materialized: int = 0
    subscription_attempts: int = 0
    pipeline_attempts: int = 0
    outcome: ResidentSupervisorOutcome = "cycle_complete"

    @property
    def made_progress(self) -> bool:
        """Scanning alone is observation; recovery or durable work is progress."""

        return any(
            (
                self.login_recovered,
                self.materialized,
                self.subscription_attempts,
                self.pipeline_attempts,
            )
        )

    @property
    def stopped(self) -> bool:
        return self.outcome != "cycle_complete"


@dataclass(slots=True)
class _Counts:
    cycles: int = 0
    login_scanned: int = 0
    login_recovered: int = 0
    login_busy: int = 0
    login_conflicted: int = 0
    materialized: int = 0
    subscription_attempts: int = 0
    pipeline_attempts: int = 0

    def result(self, outcome: ResidentSupervisorOutcome) -> ResidentSupervisorResult:
        return ResidentSupervisorResult(
            cycles=self.cycles,
            login_scanned=self.login_scanned,
            login_recovered=self.login_recovered,
            login_busy=self.login_busy,
            login_conflicted=self.login_conflicted,
            materialized=self.materialized,
            subscription_attempts=self.subscription_attempts,
            pipeline_attempts=self.pipeline_attempts,
            outcome=outcome,
        )

    def add(self, result: ResidentSupervisorResult) -> None:
        self.cycles += result.cycles
        self.login_scanned += result.login_scanned
        self.login_recovered += result.login_recovered
        self.login_busy += result.login_busy
        self.login_conflicted += result.login_conflicted
        self.materialized += result.materialized
        self.subscription_attempts += result.subscription_attempts
        self.pipeline_attempts += result.pipeline_attempts


class ResidentSchedulerSupervisor:
    """Drive fair local cycles until a cooperative foreground stop is requested.

    Subscription attempts are cancellable because their handlers own a child
    process join boundary.  Pipeline attempts can wrap synchronous thread work,
    so an already-started attempt is shielded and drained before shutdown.
    """

    def __init__(
        self,
        *,
        stale_login_sweep: _StaleLoginSweep,
        scheduler: DurableSchedulerService,
        subscription_worker: SubscriptionWorker,
        pipeline_worker: PipelineSubscriptionWorker,
        subscription_worker_id: str,
        pipeline_worker_id: str,
        config: ResidentSupervisorConfig | None = None,
        stop_event: asyncio.Event | None = None,
        idle_wait: IdleWait | None = None,
    ) -> None:
        if not callable(stale_login_sweep):
            raise TypeError("stale_login_sweep must be callable")
        subscription_id = _worker_id(subscription_worker_id, name="subscription_worker_id")
        pipeline_id = _worker_id(pipeline_worker_id, name="pipeline_worker_id")
        if subscription_id == pipeline_id:
            raise ValueError("subscription and pipeline worker IDs must be distinct")
        if stop_event is not None and not isinstance(stop_event, asyncio.Event):
            raise TypeError("stop_event must be an asyncio.Event")
        if idle_wait is not None and not callable(idle_wait):
            raise TypeError("idle_wait must be callable")
        if config is not None and not isinstance(config, ResidentSupervisorConfig):
            raise TypeError("config must be a ResidentSupervisorConfig")

        self.stale_login_sweep = stale_login_sweep
        self.scheduler = scheduler
        self.subscription_worker = subscription_worker
        self.pipeline_worker = pipeline_worker
        self.subscription_worker_id = subscription_id
        self.pipeline_worker_id = pipeline_id
        self.config = config or ResidentSupervisorConfig()
        self.stop_event = stop_event or asyncio.Event()
        self.idle_wait = idle_wait or self._default_idle_wait

    @staticmethod
    async def _default_idle_wait(stop_event: asyncio.Event, timeout: float) -> None:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=timeout)
        except TimeoutError:
            return

    def request_stop(self) -> None:
        """Wake an idle run and prevent every later tick or claim boundary."""

        self.stop_event.set()

    @staticmethod
    def _login_counts(summary: _LoginSweepSummary, *, limit: int) -> tuple[int, int, int, int]:
        values: list[int] = []
        for name in ("scanned", "recovered", "busy", "conflicted"):
            value = getattr(summary, name, None)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("stale login sweep returned an invalid redaction-safe summary")
            values.append(value)
        scanned, recovered, busy, conflicted = values
        if scanned > limit or recovered + busy + conflicted != scanned:
            raise ValueError("stale login sweep returned an invalid redaction-safe summary")
        return scanned, recovered, busy, conflicted

    @staticmethod
    def _materialized_count(result: SchedulerTickResult, *, limit: int) -> int:
        count = getattr(result, "materialized_count", None)
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= limit:
            raise ValueError("scheduler tick returned an invalid materialized count")
        return count

    @staticmethod
    async def _discard_waiter(task: asyncio.Task[bool]) -> None:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    @staticmethod
    def _caller_is_cancelling() -> bool:
        task = asyncio.current_task()
        return task is not None and task.cancelling() > 0

    async def _cancel_and_join_subscription_attempt(
        self,
        attempt: asyncio.Task[SchedulerWorkerResult | None],
        *,
        cancellation: asyncio.CancelledError | None = None,
    ) -> None:
        """Cancel once, then survive later caller cancellation until join."""

        if not attempt.done():
            attempt.cancel()
        while not attempt.done():
            try:
                await asyncio.shield(attempt)
            except asyncio.CancelledError as error:
                # ``shield`` also raises when the deliberately cancelled child
                # reaches its terminal state. Only a cancellation request on
                # this supervisor task is caller cancellation to propagate.
                if cancellation is None and self._caller_is_cancelling():
                    cancellation = error
            except BaseException:
                break

        if cancellation is not None:
            with suppress(BaseException):
                attempt.result()
            raise cancellation
        with suppress(asyncio.CancelledError):
            attempt.result()

    async def _drain_pipeline_attempt(
        self,
        attempt: asyncio.Task[PipelineWorkerResult | None],
        *,
        cancellation: asyncio.CancelledError | None = None,
    ) -> PipelineWorkerResult | None:
        """Keep one thread-backed attempt alive until its exact task is done."""

        while not attempt.done():
            try:
                await asyncio.shield(attempt)
            except asyncio.CancelledError as error:
                if cancellation is None and self._caller_is_cancelling():
                    cancellation = error
            except BaseException:
                break

        if cancellation is not None:
            with suppress(BaseException):
                attempt.result()
            raise cancellation
        return attempt.result()

    async def _run_subscription_if_active(self) -> SchedulerWorkerResult | None:
        if self.stop_event.is_set():
            return None
        return await self.subscription_worker.run_once(
            worker_id=self.subscription_worker_id,
            global_capacity=self.config.subscription_global_capacity,
            lease_seconds=self.config.subscription_lease_seconds,
            scan_limit=self.config.subscription_scan_limit,
            heartbeat_interval_seconds=self.config.subscription_heartbeat_interval_seconds,
        )

    async def _subscription_attempt(self) -> tuple[SchedulerWorkerResult | None, bool]:
        attempt = asyncio.create_task(self._run_subscription_if_active())
        stop_waiter = asyncio.create_task(self.stop_event.wait())
        try:
            try:
                done, _pending = await asyncio.wait(
                    {attempt, stop_waiter},
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError as error:
                self.request_stop()
                await self._cancel_and_join_subscription_attempt(attempt, cancellation=error)
                raise  # pragma: no cover - the join re-raises cancellation

            if stop_waiter in done and attempt not in done:
                await self._cancel_and_join_subscription_attempt(attempt)
                return None, True
            result = attempt.result()
            return result, result is None or self.stop_event.is_set()
        finally:
            await self._discard_waiter(stop_waiter)

    async def _run_pipeline_if_active(self) -> PipelineWorkerResult | None:
        if self.stop_event.is_set():
            return None
        return await self.pipeline_worker.run_once(
            worker_id=self.pipeline_worker_id,
            lease_seconds=self.config.pipeline_lease_seconds,
            scan_limit=self.config.pipeline_scan_limit,
            heartbeat_interval_seconds=self.config.pipeline_heartbeat_interval_seconds,
        )

    async def _pipeline_attempt(self) -> tuple[PipelineWorkerResult | None, bool]:
        attempt = asyncio.create_task(self._run_pipeline_if_active())
        stop_waiter = asyncio.create_task(self.stop_event.wait())
        try:
            try:
                done, _pending = await asyncio.wait(
                    {attempt, stop_waiter},
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError as error:
                self.request_stop()
                await self._drain_pipeline_attempt(attempt, cancellation=error)
                raise  # pragma: no cover - the drain re-raises cancellation

            if stop_waiter in done and attempt not in done:
                result = await self._drain_pipeline_attempt(attempt)
                return result, True
            result = attempt.result()
            return result, result is None or self.stop_event.is_set()
        finally:
            await self._discard_waiter(stop_waiter)

    async def run_cycle(self) -> ResidentSupervisorResult:
        """Run one ordered, bounded and fair sweep/tick/sync/pipeline cycle."""

        counts = _Counts()
        if self.stop_event.is_set():
            return counts.result("stopped_before_cycle")

        counts.cycles = 1
        login_summary = await asyncio.to_thread(
            self.stale_login_sweep,
            limit=self.config.login_sweep_limit,
        )
        (
            counts.login_scanned,
            counts.login_recovered,
            counts.login_busy,
            counts.login_conflicted,
        ) = self._login_counts(login_summary, limit=self.config.login_sweep_limit)
        if self.stop_event.is_set():
            return counts.result("stopped_after_login_sweep")

        tick = await asyncio.to_thread(
            self.scheduler.tick,
            limit=self.config.materialize_limit,
        )
        counts.materialized = self._materialized_count(tick, limit=self.config.materialize_limit)
        if self.stop_event.is_set():
            return counts.result("stopped_after_scheduler_tick")

        for _ in range(self.config.subscription_jobs_per_cycle):
            if self.stop_event.is_set():
                return counts.result("stopped_during_subscription")
            subscription_result, stopped = await self._subscription_attempt()
            if subscription_result is not None and subscription_result.status != "idle":
                counts.subscription_attempts += 1
            if stopped:
                return counts.result("stopped_during_subscription")
            if subscription_result is not None and subscription_result.status == "idle":
                break

        if self.stop_event.is_set():
            return counts.result("stopped_before_pipeline")

        for _ in range(self.config.pipeline_jobs_per_cycle):
            if self.stop_event.is_set():
                return counts.result("stopped_before_pipeline")
            pipeline_result, stopped = await self._pipeline_attempt()
            if pipeline_result is not None and pipeline_result.status != "idle":
                counts.pipeline_attempts += 1
            if stopped:
                return counts.result("stopped_during_pipeline")
            if pipeline_result is not None and pipeline_result.status in {"idle", "fenced"}:
                break

        return counts.result("cycle_complete")

    async def run(self) -> ResidentSupervisorResult:
        """Run foreground cycles until ``request_stop`` wakes the supervisor."""

        aggregate = _Counts()
        while True:
            cycle = await self.run_cycle()
            aggregate.add(cycle)
            if cycle.stopped:
                return aggregate.result(cycle.outcome)
            if cycle.made_progress:
                continue
            if self.stop_event.is_set():
                return aggregate.result("stopped_during_idle_wait")
            try:
                await self.idle_wait(self.stop_event, float(self.config.idle_interval_seconds))
            except asyncio.CancelledError:
                self.request_stop()
                raise
            if self.stop_event.is_set():
                return aggregate.result("stopped_during_idle_wait")


__all__ = [
    "ResidentSchedulerSupervisor",
    "ResidentSupervisorConfig",
    "ResidentSupervisorOutcome",
    "ResidentSupervisorResult",
]
