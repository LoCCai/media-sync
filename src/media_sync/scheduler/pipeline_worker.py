"""Bounded worker for durable ``pipeline.subscription`` coordinators."""

from __future__ import annotations

import asyncio
import inspect
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Literal, Protocol, cast

from media_sync.infrastructure.db import Database, JobRepository, LeaseLostError
from media_sync.infrastructure.db.models import Job

from .pipeline import (
    PIPELINE_SUBSCRIPTION_JOB_TYPE,
    PipelineJobRepository,
    PipelineSubscriptionClaim,
    parse_pipeline_subscription_payload,
)

PIPELINE_RETRY_DELAY_SECONDS = 30
_MAX_JOBS = 1_000


class _PipelineHeartbeatError(RuntimeError):
    """The worker could not prove continued coordinator ownership."""


@dataclass(frozen=True, slots=True)
class PipelineFailureClassification:
    code: str
    message: str
    retryable: bool


_FAILURES: Mapping[str, PipelineFailureClassification] = MappingProxyType(
    {
        failure.code: failure
        for failure in (
            PipelineFailureClassification(
                "pipeline_subscription_not_found",
                "subscription was not found",
                False,
            ),
            PipelineFailureClassification(
                "pipeline_subscription_invalid",
                "subscription scope is inconsistent",
                False,
            ),
            PipelineFailureClassification(
                "pipeline_asset_source_ineligible",
                "asset has no current source for this subscription",
                True,
            ),
            PipelineFailureClassification(
                "pipeline_download_request_scope_mismatch",
                "download request does not target the selected asset",
                False,
            ),
            PipelineFailureClassification(
                "pipeline_download_result_scope_mismatch",
                "download result does not target the selected asset",
                False,
            ),
            PipelineFailureClassification(
                "pipeline_asset_not_verified",
                "an asset is not durably verified",
                True,
            ),
            PipelineFailureClassification(
                "pipeline_selection_changed",
                "subscription assets changed while the pipeline was running",
                True,
            ),
            PipelineFailureClassification(
                "pipeline_export_request_scope_mismatch",
                "export request does not target the selected author",
                False,
            ),
            PipelineFailureClassification(
                "pipeline_download_retryable",
                "asset download did not complete and may be retried",
                True,
            ),
            PipelineFailureClassification(
                "pipeline_download_terminal",
                "asset download cannot be completed",
                False,
            ),
            PipelineFailureClassification(
                "pipeline_export_retryable",
                "Emby export did not complete and may be retried",
                True,
            ),
            PipelineFailureClassification(
                "pipeline_export_terminal",
                "Emby export cannot be completed",
                False,
            ),
            PipelineFailureClassification(
                "pipeline_mediacrawler_not_enabled",
                "MediaCrawler refresh is not enabled for required assets",
                True,
            ),
            PipelineFailureClassification(
                "pipeline_mediacrawler_license_required",
                "MediaCrawler license acknowledgement is required",
                True,
            ),
            PipelineFailureClassification(
                "pipeline_mediacrawler_runtime_unavailable",
                "MediaCrawler runtime is unavailable",
                True,
            ),
            PipelineFailureClassification(
                "pipeline_xhs_detail_authority_required",
                "XHS note detail authority is required",
                True,
            ),
            PipelineFailureClassification(
                "pipeline_media_probe_unavailable",
                "required local media probe is unavailable",
                True,
            ),
            PipelineFailureClassification(
                "pipeline_handler_error",
                "pipeline handler failed unexpectedly",
                True,
            ),
            PipelineFailureClassification(
                "pipeline_handler_invalid",
                "pipeline handler returned an invalid result",
                False,
            ),
            PipelineFailureClassification(
                "pipeline_worker_error",
                "pipeline worker could not finalize the attempt",
                True,
            ),
        )
    }
)


def classify_pipeline_failure(error_code: str) -> PipelineFailureClassification:
    """Return one immutable classification from the closed worker vocabulary."""

    if not isinstance(error_code, str):
        raise ValueError("pipeline error_code is outside the closed vocabulary")
    try:
        return _FAILURES[error_code]
    except KeyError as exc:
        raise ValueError("pipeline error_code is outside the closed vocabulary") from exc


@dataclass(frozen=True, slots=True)
class PipelineHandlerResult:
    """Closed result returned by a sync or async pipeline handler."""

    succeeded: bool
    error_code: str | None = None

    def __post_init__(self) -> None:
        if type(self.succeeded) is not bool:
            raise ValueError("succeeded must be boolean")
        if self.succeeded:
            if self.error_code is not None:
                raise ValueError("successful pipeline results cannot carry an error code")
            return
        if self.error_code is None:
            raise ValueError("failed pipeline results require an error code")
        classify_pipeline_failure(self.error_code)

    @classmethod
    def success(cls) -> PipelineHandlerResult:
        return cls(succeeded=True)

    @classmethod
    def failure(cls, error_code: str) -> PipelineHandlerResult:
        return cls(succeeded=False, error_code=error_code)


class PipelineHandler(Protocol):
    """Callable handler receiving the exact durable coordinator claim."""

    def __call__(
        self,
        claim: PipelineSubscriptionClaim,
    ) -> PipelineHandlerResult | Awaitable[PipelineHandlerResult]: ...


@dataclass(frozen=True, slots=True)
class PipelineWorkerResult:
    """Redaction-safe observation of one coordinator attempt."""

    job_id: str | None
    subscription_id: str | None
    status: str
    attempt: int | None = None
    error_code: str | None = None

    @classmethod
    def idle(cls) -> PipelineWorkerResult:
        return cls(job_id=None, subscription_id=None, status="idle")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PipelineSubscriptionWorker:
    """Claim, invoke and lease-fence one coordinator without sleeping."""

    def __init__(
        self,
        database: Database,
        handler: PipelineHandler,
        *,
        clock: Callable[[], datetime] = _utc_now,
        retry_delay_seconds: int = PIPELINE_RETRY_DELAY_SECONDS,
    ) -> None:
        if not callable(handler):
            raise TypeError("pipeline handler must be callable")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if type(retry_delay_seconds) is not int or not 1 <= retry_delay_seconds <= 86_400:
            raise ValueError("retry_delay_seconds must be between 1 and 86400")
        self.database = database
        self.handler = handler
        self.clock = clock
        self.retry_delay_seconds = retry_delay_seconds

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
    def _result(job: Job) -> PipelineWorkerResult:
        payload = parse_pipeline_subscription_payload(job)
        return PipelineWorkerResult(
            job_id=job.id,
            subscription_id=payload.subscription_id,
            status=job.status,
            attempt=job.attempts,
            error_code=job.last_error_code,
        )

    @staticmethod
    def _fenced(
        claim: PipelineSubscriptionClaim,
        *,
        error_code: str,
    ) -> PipelineWorkerResult:
        return PipelineWorkerResult(
            job_id=claim.job_id,
            subscription_id=claim.subscription_id,
            status="fenced",
            attempt=claim.attempt,
            error_code=error_code,
        )

    def _observed_or_fenced(
        self,
        claim: PipelineSubscriptionClaim,
        *,
        error_code: str,
    ) -> PipelineWorkerResult:
        try:
            with self.database.session() as session:
                job = session.get(Job, claim.job_id)
                if job is None or job.job_type != PIPELINE_SUBSCRIPTION_JOB_TYPE:
                    return self._fenced(claim, error_code=error_code)
                observed = self._result(job)
        except Exception:
            return self._fenced(claim, error_code=error_code)
        if observed.status in {"queued", "claimed", "running"}:
            return self._fenced(claim, error_code=error_code)
        return observed

    async def _invoke(self, claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        try:
            if inspect.iscoroutinefunction(self.handler) or inspect.iscoroutinefunction(type(self.handler).__call__):
                raw: object = self.handler(claim)
            else:
                raw = await asyncio.to_thread(self.handler, claim)
            if inspect.isawaitable(raw):
                raw = await cast(Awaitable[object], raw)
        except LeaseLostError:
            raise
        except Exception:
            return PipelineHandlerResult.failure("pipeline_handler_error")
        if not isinstance(raw, PipelineHandlerResult):
            return PipelineHandlerResult.failure("pipeline_handler_invalid")
        try:
            return PipelineHandlerResult(succeeded=raw.succeeded, error_code=raw.error_code)
        except (TypeError, ValueError):
            return PipelineHandlerResult.failure("pipeline_handler_invalid")

    def _heartbeat(
        self,
        claim: PipelineSubscriptionClaim,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        with self.database.session() as session:
            job = JobRepository(session).renew_lease(
                claim.job_id,
                worker_id=worker_id,
                lease_token=claim.lease_token,
                lease_seconds=lease_seconds,
                now=self.clock(),
            )
            if job.job_type != PIPELINE_SUBSCRIPTION_JOB_TYPE:
                raise LeaseLostError("pipeline worker renewed a foreign job type")

    async def _heartbeat_loop(
        self,
        claim: PipelineSubscriptionClaim,
        *,
        worker_id: str,
        lease_seconds: int,
        heartbeat_interval_seconds: float,
        stop: asyncio.Event,
    ) -> Literal["lease_lost", "heartbeat_failed"] | None:
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
                except LeaseLostError:
                    return "lease_lost"
                except Exception:
                    return "heartbeat_failed"
            else:
                return None

    @staticmethod
    async def _cancel_task(task: asyncio.Task[PipelineHandlerResult]) -> None:
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _invoke_with_heartbeat(
        self,
        claim: PipelineSubscriptionClaim,
        *,
        worker_id: str,
        lease_seconds: int,
        heartbeat_interval_seconds: float,
    ) -> PipelineHandlerResult:
        stop = asyncio.Event()
        handler_task = asyncio.create_task(self._invoke(claim))
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
                        raise LeaseLostError("pipeline lease ownership changed")
                    raise _PipelineHeartbeatError("pipeline heartbeat failed")
            return await handler_task
        finally:
            stop.set()
            if not handler_task.done():
                await self._cancel_task(handler_task)
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    def _finalize(
        self,
        claim: PipelineSubscriptionClaim,
        *,
        worker_id: str,
        result: PipelineHandlerResult,
    ) -> PipelineWorkerResult:
        current = self.clock()
        with self.database.session() as session:
            jobs = JobRepository(session)
            if result.succeeded:
                job = jobs.complete(
                    claim.job_id,
                    worker_id=worker_id,
                    lease_token=claim.lease_token,
                    now=current,
                )
            else:
                classification = classify_pipeline_failure(result.error_code or "")
                retry_at = current + timedelta(seconds=self.retry_delay_seconds) if classification.retryable else None
                job = jobs.fail(
                    claim.job_id,
                    worker_id=worker_id,
                    lease_token=claim.lease_token,
                    retryable=classification.retryable,
                    error_code=classification.code,
                    error_message=classification.message,
                    retry_at=retry_at,
                    now=current,
                )
            if job.job_type != PIPELINE_SUBSCRIPTION_JOB_TYPE:
                raise LeaseLostError("pipeline worker observed a foreign job type")
            return self._result(job)

    def _fail_closed(
        self,
        claim: PipelineSubscriptionClaim,
        *,
        worker_id: str,
    ) -> PipelineWorkerResult:
        try:
            return self._finalize(
                claim,
                worker_id=worker_id,
                result=PipelineHandlerResult.failure("pipeline_worker_error"),
            )
        except LeaseLostError:
            return self._observed_or_fenced(claim, error_code="pipeline_lease_lost")
        except Exception:
            return self._observed_or_fenced(claim, error_code="pipeline_worker_error")

    async def run_once(
        self,
        *,
        worker_id: str,
        lease_seconds: int = 300,
        scan_limit: int = 100,
        heartbeat_interval_seconds: float | None = None,
    ) -> PipelineWorkerResult:
        """Run at most one coordinator attempt."""

        heartbeat_interval = self._heartbeat_interval(
            heartbeat_interval_seconds,
            lease_seconds=lease_seconds,
        )

        with self.database.session() as session:
            claim = PipelineJobRepository(session).claim_next(
                worker_id=worker_id,
                lease_seconds=lease_seconds,
                scan_limit=scan_limit,
                now=self.clock(),
            )
        if claim is None:
            return PipelineWorkerResult.idle()

        try:
            with self.database.session() as session:
                jobs = JobRepository(session)
                started_at = self.clock()
                started = jobs.start(
                    claim.job_id,
                    worker_id=worker_id,
                    lease_token=claim.lease_token,
                    now=started_at,
                )
                if started.job_type != PIPELINE_SUBSCRIPTION_JOB_TYPE:
                    raise LeaseLostError("pipeline worker started a foreign job type")
                # Claim validation and transaction handoff consume part of the
                # original lease.  Rebase the running lease before invoking the
                # handler so the first periodic heartbeat always has a complete
                # interval in which to run.
                renewed = jobs.renew_lease(
                    claim.job_id,
                    worker_id=worker_id,
                    lease_token=claim.lease_token,
                    lease_seconds=lease_seconds,
                    now=started_at,
                )
                if renewed.job_type != PIPELINE_SUBSCRIPTION_JOB_TYPE:
                    raise LeaseLostError("pipeline worker renewed a foreign job type")
        except LeaseLostError:
            return self._observed_or_fenced(claim, error_code="pipeline_lease_lost")
        except Exception:
            return self._fail_closed(claim, worker_id=worker_id)

        try:
            handler_result = await self._invoke_with_heartbeat(
                claim,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
                heartbeat_interval_seconds=heartbeat_interval,
            )
            return self._finalize(claim, worker_id=worker_id, result=handler_result)
        except _PipelineHeartbeatError:
            # A synchronous handler runs in a worker thread and cannot be
            # force-stopped by cancelling its asyncio wrapper.  Leave the Job
            # running under its existing lease for fenced reclaim instead of
            # releasing it into an immediate duplicate retry.
            return self._observed_or_fenced(claim, error_code="pipeline_heartbeat_failed")
        except LeaseLostError:
            return self._observed_or_fenced(claim, error_code="pipeline_lease_lost")
        except Exception:
            return self._fail_closed(claim, worker_id=worker_id)

    async def run_bounded(
        self,
        *,
        worker_id: str,
        max_jobs: int,
        lease_seconds: int = 300,
        scan_limit: int = 100,
        heartbeat_interval_seconds: float | None = None,
    ) -> tuple[PipelineWorkerResult, ...]:
        """Run no more than ``max_jobs`` available coordinators."""

        if type(max_jobs) is not int or not 1 <= max_jobs <= _MAX_JOBS:
            raise ValueError("max_jobs must be an integer between 1 and 1000")
        results: list[PipelineWorkerResult] = []
        for _ in range(max_jobs):
            result = await self.run_once(
                worker_id=worker_id,
                lease_seconds=lease_seconds,
                scan_limit=scan_limit,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
            )
            if result.status == "idle":
                break
            results.append(result)
            if result.status == "fenced":
                break
        return tuple(results)


__all__ = [
    "PIPELINE_RETRY_DELAY_SECONDS",
    "PipelineFailureClassification",
    "PipelineHandler",
    "PipelineHandlerResult",
    "PipelineSubscriptionWorker",
    "PipelineWorkerResult",
    "classify_pipeline_failure",
]
