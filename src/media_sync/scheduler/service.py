"""Short-transaction scheduler and worker application services."""

from __future__ import annotations

import asyncio
import math
import random
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, joinedload

from media_sync.application.operations import DurableSubjectHook, DurableSubjectRef
from media_sync.domain import AccountRef, Cursor, DomainError, LoginMethod, Platform
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.models import Job, Subscription, SyncRun

from .handlers import (
    SubscriptionHandlerRegistry,
    SubscriptionHandlerResult,
    SubscriptionJobContext,
)
from .policy import FailureDisposition, RetryPolicy, classify_failure
from .policy import retry_at as calculate_retry_at
from .repository import (
    LanePolicy,
    LaneScope,
    LaneSnapshot,
    MaterializedCycle,
    SchedulerClaim,
    SchedulerJobSummary,
    SchedulerLeaseLostError,
    SchedulerRepository,
    SubscriptionSchedule,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _heartbeat_failure_code(
    error: Exception,
) -> Literal["scheduler_heartbeat_failed", "scheduler_heartbeat_storage_busy"]:
    if isinstance(error, OperationalError) and isinstance(error.orig, sqlite3.Error):
        native_code = getattr(error.orig, "sqlite_errorcode", None)
        if (
            type(native_code) is int
            and 0 <= native_code <= 2**31 - 1
            and native_code & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
        ):
            return "scheduler_heartbeat_storage_busy"
    return "scheduler_heartbeat_failed"


@dataclass(frozen=True, slots=True)
class SchedulerTickResult:
    cycles: tuple[MaterializedCycle, ...]

    @property
    def materialized_count(self) -> int:
        return len(self.cycles)


@dataclass(frozen=True, slots=True)
class SchedulerWorkerResult:
    """Redaction-safe observation of one bounded worker attempt."""

    job_id: str | None
    subscription_id: str | None
    status: str
    attempt: int | None = None
    run_id: str | None = None
    error_code: str | None = None

    @classmethod
    def idle(cls) -> SchedulerWorkerResult:
        return cls(job_id=None, subscription_id=None, status="idle")


class DurableSchedulerService:
    """Open one transaction per control-plane operation."""

    def __init__(self, database: Database, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self.database = database
        self.clock = clock

    def tick(self, *, limit: int = 100, retry_policy: RetryPolicy | None = None) -> SchedulerTickResult:
        with self.database.session() as session:
            cycles = SchedulerRepository(session).materialize_due(
                limit=limit,
                now=self.clock(),
                retry_policy=retry_policy,
            )
        return SchedulerTickResult(tuple(cycles))

    def pause_subscription(self, subscription_id: str) -> SubscriptionSchedule:
        with self.database.session() as session:
            return SchedulerRepository(session).pause_subscription(subscription_id, now=self.clock())

    def resume_subscription(self, subscription_id: str) -> SubscriptionSchedule:
        with self.database.session() as session:
            return SchedulerRepository(session).resume_subscription(subscription_id, now=self.clock())

    def run_now(self, subscription_id: str) -> SubscriptionSchedule:
        with self.database.session() as session:
            return SchedulerRepository(session).run_now(subscription_id, now=self.clock())

    def list_jobs(
        self,
        *,
        status: str | None = None,
        subscription_id: str | None = None,
        limit: int = 100,
    ) -> list[SchedulerJobSummary]:
        with self.database.session() as session:
            return SchedulerRepository(session).list_jobs(
                status=status,
                subscription_id=subscription_id,
                limit=limit,
            )

    def resume_job(self, job_id: str) -> SchedulerJobSummary:
        with self.database.session() as session:
            return SchedulerRepository(session).resume(job_id, now=self.clock())

    def cancel_job(self, job_id: str) -> SchedulerJobSummary:
        with self.database.session() as session:
            return SchedulerRepository(session).cancel(job_id, now=self.clock())

    def list_lanes(self) -> list[LaneSnapshot]:
        with self.database.session() as session:
            return SchedulerRepository(session).list_lanes()

    def update_lane(self, policy: LanePolicy, *, expected_revision: int | None = None) -> LaneSnapshot:
        with self.database.session() as session:
            return SchedulerRepository(session).update_lane(
                policy,
                expected_revision=expected_revision,
                now=self.clock(),
            )

    def reset_lane(
        self,
        *,
        scope_type: LaneScope,
        platform: str,
        account_id: str | None = None,
        expected_revision: int | None = None,
    ) -> LaneSnapshot:
        if scope_type not in {"platform", "account"}:
            raise ValueError("scope_type must be platform or account")
        with self.database.session() as session:
            return SchedulerRepository(session).reset_lane_circuit(
                scope_type=scope_type,
                platform=platform,
                account_id=account_id,
                expected_revision=expected_revision,
                now=self.clock(),
            )


class SubscriptionWorker:
    """Claim, start, invoke and finalize one subscription attempt without sleeping."""

    def __init__(
        self,
        database: Database,
        handlers: SubscriptionHandlerRegistry,
        *,
        clock: Callable[[], datetime] = _utc_now,
        random_fraction: Callable[[], float] = random.random,
        claim_registered_only: bool = False,
    ) -> None:
        if type(claim_registered_only) is not bool:
            raise ValueError("claim_registered_only must be boolean")
        self.database = database
        self.handlers = handlers
        self.clock = clock
        self.random_fraction = random_fraction
        self.claim_adapter_allowlist = handlers.keys if claim_registered_only else None

    @staticmethod
    def _heartbeat_interval(value: float | None, *, lease_seconds: int) -> float:
        if value is None:
            return min(20.0, lease_seconds / 3.0)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0 < float(value) < lease_seconds
        ):
            raise ValueError("heartbeat_interval_seconds must be finite, positive and shorter than the lease")
        return float(value)

    @staticmethod
    def _worker_result(summary: SchedulerJobSummary) -> SchedulerWorkerResult:
        return SchedulerWorkerResult(
            job_id=summary.job_id,
            subscription_id=summary.subscription_id,
            status=summary.status,
            attempt=summary.attempts,
            run_id=summary.run_id,
            error_code=summary.last_error_code,
        )

    @staticmethod
    def _fenced_result(
        claim: SchedulerClaim,
        *,
        error_code: str | None = None,
    ) -> SchedulerWorkerResult:
        return SchedulerWorkerResult(
            job_id=claim.job_id,
            subscription_id=claim.subscription_id,
            status="fenced",
            attempt=claim.attempt,
            error_code=error_code,
        )

    def _observed_or_fenced(
        self,
        claim: SchedulerClaim,
        *,
        error_code: str | None = None,
    ) -> SchedulerWorkerResult:
        try:
            with self.database.session() as session:
                summary = SchedulerRepository(session).get_job(claim.job_id)
        except Exception:
            return self._fenced_result(claim, error_code=error_code)
        if summary.status in {"queued", "claimed", "running"}:
            return self._fenced_result(claim, error_code=error_code)
        return self._worker_result(summary)

    def _load_context(
        self,
        claim: SchedulerClaim,
        *,
        worker_id: str,
    ) -> tuple[SubscriptionJobContext | None, str | None]:
        context: SubscriptionJobContext | None = None
        handler_key: str | None = None

        def ownership_guard(handler_session: Session) -> None:
            SchedulerRepository(handler_session).assert_owned(
                claim.job_id,
                worker_id=worker_id,
                lease_token=claim.lease_token,
                now=self.clock(),
            )

        def run_attacher(
            handler_session: Session,
            run_id: UUID,
            expected_current_run_id: UUID | None,
        ) -> None:
            SchedulerRepository(handler_session).attach_run(
                claim.job_id,
                worker_id=worker_id,
                lease_token=claim.lease_token,
                run_id=str(run_id),
                expected_current_run_id=(str(expected_current_run_id) if expected_current_run_id is not None else None),
                now=self.clock(),
            )

        with self.database.session() as session:
            subscription = session.scalar(
                select(Subscription)
                .where(Subscription.id == claim.subscription_id)
                .options(joinedload(Subscription.account), joinedload(Subscription.author))
            )
            if subscription is None:
                return None, None
            account = subscription.account
            try:
                if account.id != claim.account_id or account.platform != claim.platform:
                    raise ValueError("scheduler job scope does not match its subscription")
                if account.login_method is None:
                    raise ValueError("scheduled account has no login method")
                cursor: Cursor | None = None
                if subscription.cursor is not None:
                    if not isinstance(subscription.cursor, Mapping):
                        raise ValueError("subscription cursor is invalid")
                    cursor_value = subscription.cursor.get("value")
                    if not isinstance(cursor_value, str):
                        raise ValueError("subscription cursor is invalid")
                    cursor = Cursor(cursor_value)
                if not isinstance(subscription.policy, Mapping):
                    raise ValueError("subscription policy is invalid")
                current_run_id = UUID(claim.run_id) if claim.run_id is not None else None
                handler_key = account.adapter
                context = SubscriptionJobContext(
                    job_id=UUID(claim.job_id),
                    subscription_id=UUID(claim.subscription_id),
                    account=AccountRef(
                        account_id=UUID(account.id),
                        platform=Platform(account.platform),
                        login_method=LoginMethod(account.login_method),
                        adapter=account.adapter,
                        credential_ref=account.credential_ref,
                    ),
                    creator_reference=subscription.author.remote_id,
                    cursor=cursor,
                    subscription_policy=subscription.policy,
                    schedule_revision=claim.schedule_revision,
                    max_items=subscription.max_items,
                    attempt=claim.attempt,
                    current_run_id=current_run_id,
                    ownership_guard=ownership_guard,
                    run_attacher=run_attacher,
                )
            except (DomainError, TypeError, ValueError):
                context = None
                handler_key = None
        return context, handler_key

    async def _invoke(
        self,
        context: SubscriptionJobContext | None,
        handler_key: str | None,
    ) -> SubscriptionHandlerResult:
        if context is None:
            return SubscriptionHandlerResult.failure("schema_invalid")
        try:
            handler = self.handlers.resolve(handler_key or "")
        except Exception:
            return SubscriptionHandlerResult.failure("schema_invalid")
        if handler is None:
            return SubscriptionHandlerResult.failure("handler_unsupported")
        try:
            result = await handler.run(context)
        except SchedulerLeaseLostError:
            raise
        except Exception:
            return SubscriptionHandlerResult.failure("unexpected_handler_failure")
        if not isinstance(result, SubscriptionHandlerResult):
            return SubscriptionHandlerResult.failure("schema_invalid")
        try:
            return SubscriptionHandlerResult(
                succeeded=result.succeeded,
                run_id=result.run_id,
                error_code=result.error_code,
                retry_after=result.retry_after,
            )
        except (TypeError, ValueError):
            return SubscriptionHandlerResult.failure("schema_invalid")

    def _heartbeat(
        self,
        claim: SchedulerClaim,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        with self.database.session() as session:
            SchedulerRepository(session).heartbeat(
                claim.job_id,
                worker_id=worker_id,
                lease_token=claim.lease_token,
                lease_seconds=lease_seconds,
                now=self.clock(),
            )

    async def _heartbeat_loop(
        self,
        claim: SchedulerClaim,
        *,
        worker_id: str,
        lease_seconds: int,
        heartbeat_interval_seconds: float,
        stop: asyncio.Event,
    ) -> Literal["lease_lost", "scheduler_heartbeat_failed", "scheduler_heartbeat_storage_busy"] | None:
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=heartbeat_interval_seconds)
            except TimeoutError:
                try:
                    await asyncio.to_thread(
                        self._heartbeat,
                        claim,
                        worker_id=worker_id,
                        lease_seconds=lease_seconds,
                    )
                except SchedulerLeaseLostError:
                    return "lease_lost"
                except Exception as error:
                    return _heartbeat_failure_code(error)
            else:
                return None

    @staticmethod
    async def _cancel_task(task: asyncio.Task[SubscriptionHandlerResult]) -> None:
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except SchedulerLeaseLostError:
            raise
        except Exception:
            pass

    async def _invoke_with_heartbeat(
        self,
        claim: SchedulerClaim,
        *,
        worker_id: str,
        lease_seconds: int,
        heartbeat_interval_seconds: float,
        context: SubscriptionJobContext | None,
        handler_key: str | None,
    ) -> SubscriptionHandlerResult:
        stop = asyncio.Event()
        handler_task = asyncio.create_task(self._invoke(context, handler_key))
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(
                claim,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                stop=stop,
            )
        )
        try:
            done, _pending = await asyncio.wait(
                {handler_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done:
                heartbeat_outcome = heartbeat_task.result()
                if heartbeat_outcome is not None:
                    await self._cancel_task(handler_task)
                    if heartbeat_outcome == "lease_lost":
                        raise SchedulerLeaseLostError("scheduler lease ownership changed")
                    return SubscriptionHandlerResult.failure(heartbeat_outcome)
            return await handler_task
        finally:
            stop.set()
            try:
                if not handler_task.done():
                    await self._cancel_task(handler_task)
            finally:
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

    def _validate_result_run(
        self,
        claim: SchedulerClaim,
        result: SubscriptionHandlerResult,
    ) -> SubscriptionHandlerResult:
        if result.run_id is None:
            return result
        with self.database.session() as session:
            run = session.get(SyncRun, str(result.run_id))
        if run is None or run.subscription_id != claim.subscription_id:
            return SubscriptionHandlerResult.failure("schema_invalid")
        if run.status == "succeeded":
            return SubscriptionHandlerResult.success(result.run_id)
        return result

    def _authoritative_success(
        self,
        claim: SchedulerClaim,
        result: SubscriptionHandlerResult | None,
    ) -> SubscriptionHandlerResult | None:
        try:
            with self.database.session() as session:
                job = session.get(Job, claim.job_id)
                candidate_run_id = str(result.run_id) if result is not None and result.run_id is not None else None
                if job is None or job.subscription_id != claim.subscription_id:
                    return None
                if candidate_run_id is None:
                    candidate_run_id = job.run_id
                elif job.run_id is not None and job.run_id != candidate_run_id:
                    return None
                if candidate_run_id is None:
                    return None
                run = session.get(SyncRun, candidate_run_id)
                if run is None or run.subscription_id != claim.subscription_id or run.status != "succeeded":
                    return None
            return SubscriptionHandlerResult.success(UUID(candidate_run_id))
        except Exception:
            # This probe is advisory.  If storage is unavailable, the caller
            # must retain the lease for reclaim and return only a fixed fenced
            # result; raw database failures must never escape operator output.
            return None

    def _finalize(
        self,
        claim: SchedulerClaim,
        *,
        worker_id: str,
        result: SubscriptionHandlerResult,
        finished_at: datetime | None = None,
    ) -> SchedulerJobSummary:
        completed_at = self.clock() if finished_at is None else finished_at
        with self.database.session() as session:
            repository = SchedulerRepository(session)
            if result.succeeded:
                return repository.succeed(
                    claim.job_id,
                    worker_id=worker_id,
                    lease_token=claim.lease_token,
                    run_id=result.run_id,
                    now=completed_at,
                )

            classification = classify_failure(result.error_code or "schema_invalid")
            if classification.disposition in {
                FailureDisposition.WAITING_AUTH,
                FailureDisposition.WAITING_USER,
            }:
                waiting_status: Literal["waiting_auth", "waiting_user"] = (
                    "waiting_auth" if classification.disposition is FailureDisposition.WAITING_AUTH else "waiting_user"
                )
                return repository.wait(
                    claim.job_id,
                    worker_id=worker_id,
                    lease_token=claim.lease_token,
                    status=waiting_status,
                    error_code=classification.code,
                    affects_circuit=classification.affects_circuit,
                    run_id=result.run_id,
                    now=completed_at,
                )

            retry_time: datetime | None = None
            if classification.disposition is FailureDisposition.RETRY and claim.attempt < claim.max_attempts:
                try:
                    retry_time = calculate_retry_at(
                        claim.retry_policy,
                        attempt=claim.attempt,
                        now=completed_at,
                        jitter_value=self.random_fraction(),
                        retry_after=result.retry_after,
                    )
                except Exception:
                    classification = classify_failure("schema_invalid")
            return repository.fail(
                claim.job_id,
                worker_id=worker_id,
                lease_token=claim.lease_token,
                error_code=classification.code,
                retry_at=retry_time,
                affects_circuit=classification.affects_circuit,
                run_id=result.run_id,
                now=completed_at,
            )

    def _fail_closed(
        self,
        claim: SchedulerClaim,
        *,
        worker_id: str,
        result: SubscriptionHandlerResult | None = None,
        failure_code: Literal["schema_invalid", "scheduler_finalize_failed"] = "schema_invalid",
    ) -> SchedulerWorkerResult:
        authoritative_success = self._authoritative_success(claim, result)
        if authoritative_success is not None:
            try:
                summary = self._finalize(
                    claim,
                    worker_id=worker_id,
                    result=authoritative_success,
                )
            except SchedulerLeaseLostError:
                return self._observed_or_fenced(claim)
            except Exception:
                # Once the attached run committed success, never replace that
                # durable truth with a scheduler failure. Lease reclaim or an
                # operator retry may safely reconcile the Job later.
                return self._observed_or_fenced(claim, error_code=failure_code)
            return self._worker_result(summary)
        try:
            fallback_time = self.clock()
            if (
                not isinstance(fallback_time, datetime)
                or fallback_time.tzinfo is None
                or fallback_time.utcoffset() is None
            ):
                raise ValueError("clock must return an aware datetime")
        except Exception:
            fallback_time = _utc_now()
        try:
            summary = self._finalize(
                claim,
                worker_id=worker_id,
                result=SubscriptionHandlerResult.failure(failure_code),
                finished_at=fallback_time,
            )
        except SchedulerLeaseLostError:
            return self._observed_or_fenced(claim)
        except Exception:
            # An unavailable database is intentionally left for lease reclaim.
            return self._observed_or_fenced(claim, error_code=failure_code)
        return self._worker_result(summary)

    async def run_once(
        self,
        *,
        worker_id: str,
        global_capacity: int = 1,
        lease_seconds: int = 60,
        scan_limit: int = 100,
        heartbeat_interval_seconds: float | None = None,
        subject_hook: DurableSubjectHook | None = None,
    ) -> SchedulerWorkerResult:
        heartbeat_interval = self._heartbeat_interval(
            heartbeat_interval_seconds,
            lease_seconds=lease_seconds,
        )
        with self.database.session() as session:
            claim = SchedulerRepository(session).claim_next(
                worker_id=worker_id,
                global_capacity=global_capacity,
                lease_seconds=lease_seconds,
                scan_limit=scan_limit,
                adapter_allowlist=self.claim_adapter_allowlist,
                now=self.clock(),
            )
            if claim is not None and subject_hook is not None:
                subject_hook(session, DurableSubjectRef("job", claim.job_id))
        if claim is None:
            return SchedulerWorkerResult.idle()

        result: SubscriptionHandlerResult | None = None
        try:
            with self.database.session() as session:
                started = SchedulerRepository(session).start(
                    claim.job_id,
                    worker_id=worker_id,
                    lease_token=claim.lease_token,
                    now=self.clock(),
                )
        except SchedulerLeaseLostError:
            return self._observed_or_fenced(claim)
        except Exception:
            return self._fail_closed(claim, worker_id=worker_id)
        try:
            context, handler_key = self._load_context(started, worker_id=worker_id)
            result = await self._invoke_with_heartbeat(
                started,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
                heartbeat_interval_seconds=heartbeat_interval,
                context=context,
                handler_key=handler_key,
            )
            result = self._validate_result_run(started, result)
        except SchedulerLeaseLostError:
            return self._observed_or_fenced(started)
        except Exception:
            return self._fail_closed(started, worker_id=worker_id, result=result)
        try:
            summary = self._finalize(started, worker_id=worker_id, result=result)
        except SchedulerLeaseLostError:
            return self._observed_or_fenced(started)
        except Exception:
            return self._fail_closed(
                started,
                worker_id=worker_id,
                result=result,
                failure_code="scheduler_finalize_failed",
            )
        return self._worker_result(summary)

    async def run_bounded(
        self,
        *,
        worker_id: str,
        max_jobs: int,
        global_capacity: int = 1,
        lease_seconds: int = 60,
        scan_limit: int = 100,
        heartbeat_interval_seconds: float | None = None,
        cancellation: Event | None = None,
        subject_hook: DurableSubjectHook | None = None,
    ) -> tuple[SchedulerWorkerResult, ...]:
        """Run a bounded batch, observing cooperative cancellation between Jobs."""

        if isinstance(max_jobs, bool) or not isinstance(max_jobs, int) or not 1 <= max_jobs <= 1_000:
            raise ValueError("max_jobs must be an integer between 1 and 1000")
        if cancellation is not None and not isinstance(cancellation, Event):
            raise TypeError("cancellation must be a threading.Event")
        results: list[SchedulerWorkerResult] = []
        for _ in range(max_jobs):
            if cancellation is not None and cancellation.is_set():
                break
            result = await self.run_once(
                worker_id=worker_id,
                global_capacity=global_capacity,
                lease_seconds=lease_seconds,
                scan_limit=scan_limit,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                subject_hook=subject_hook,
            )
            if result.status == "idle":
                break
            results.append(result)
        return tuple(results)


__all__ = [
    "DurableSchedulerService",
    "SchedulerTickResult",
    "SchedulerWorkerResult",
    "SubscriptionWorker",
]
