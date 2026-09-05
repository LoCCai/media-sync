"""Durable coordinator jobs emitted by successful subscription syncs.

The coordinator payload is deliberately small and closed.  Mutable author and
account details are re-read from the subscription when the pipeline executes;
the durable job only identifies the exact successful sync that caused it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from media_sync.infrastructure.db.base import utc_now
from media_sync.infrastructure.db.models import PLATFORMS, Account, Job, Subscription, SyncRun
from media_sync.infrastructure.db.repositories import (
    JobRepository,
    NotFoundError,
    RepositoryError,
    SubscriptionRemovalError,
    SubscriptionRepository,
)

from .repository import validate_sync_subscription_job

PIPELINE_SUBSCRIPTION_JOB_TYPE = "pipeline.subscription"
PIPELINE_PAYLOAD_SCHEMA_VERSION = 1
# A coordinator may revisit many independently durable asset/export children.
# Keep its retry budget deliberately separate from each child's smaller budget
# so one author's earlier transient failures do not exhaust later assets.
PIPELINE_MAX_ATTEMPTS = 100
PIPELINE_COORDINATOR_INVALID_ERROR_CODE = "pipeline_coordinator_invalid"
PIPELINE_COORDINATOR_STALE_ERROR_CODE = "pipeline_coordinator_stale"

_SOURCE_SYNC_JOB_TYPE = "sync.subscription"
_PAYLOAD_KEYS = frozenset({"schema_version", "sync_job_id", "subscription_id", "run_id"})
_MAX_LEASE_SECONDS = 86_400
_DEFAULT_CLAIM_SCAN_LIMIT = 100
_MAX_CLAIM_SCAN_LIMIT = 1_000
_INVALID_COORDINATOR_MESSAGE = "pipeline coordinator violated its durable contract"
_STALE_COORDINATOR_MESSAGE = "pipeline coordinator no longer matches its succeeded source"


class PipelineJobRepositoryError(RepositoryError):
    """A pipeline coordinator row violated its durable closed contract."""


def _aware_utc(value: datetime | None = None) -> datetime:
    result = value or utc_now()
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return result.astimezone(UTC)


def _uuid_text(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a canonical UUID string")
    try:
        normalized = str(UUID(value))
    except ValueError as exc:
        raise ValueError(f"{name} must be a canonical UUID string") from exc
    if normalized != value:
        raise ValueError(f"{name} must be a canonical UUID string")
    return normalized


def pipeline_subscription_natural_key(sync_job_id: str | UUID) -> str:
    """Return the one durable coordinator identity for a source sync Job."""

    normalized = _uuid_text(str(sync_job_id), name="sync_job_id")
    return f"sync-job:{normalized}"


@dataclass(frozen=True, slots=True)
class PipelineSubscriptionPayload:
    schema_version: int
    sync_job_id: str
    subscription_id: str
    run_id: str

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sync_job_id": self.sync_job_id,
            "subscription_id": self.subscription_id,
            "run_id": self.run_id,
        }


@dataclass(frozen=True, slots=True)
class PipelineSubscriptionJob:
    """Redaction-safe durable coordinator projection."""

    job_id: str
    sync_job_id: str
    subscription_id: str
    account_id: str
    platform: str
    run_id: str
    status: str
    attempts: int
    max_attempts: int
    available_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PipelineSubscriptionClaim:
    """One exact coordinator lease; its fencing token stays out of repr output."""

    job_id: str
    sync_job_id: str
    subscription_id: str
    account_id: str
    platform: str
    run_id: str
    attempt: int
    max_attempts: int
    lease_token: str = field(repr=False)
    lease_expires_at: datetime


def parse_pipeline_subscription_payload(job: Job) -> PipelineSubscriptionPayload:
    """Validate and parse the payload together with all duplicated Job scope."""

    if job.job_type != PIPELINE_SUBSCRIPTION_JOB_TYPE:
        raise PipelineJobRepositoryError("pipeline projection rejected a foreign job type")
    payload = job.payload
    if not isinstance(payload, Mapping) or set(payload) != _PAYLOAD_KEYS:
        raise PipelineJobRepositoryError("pipeline.subscription payload is not closed schema v1")
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version != PIPELINE_PAYLOAD_SCHEMA_VERSION:
        raise PipelineJobRepositoryError("pipeline.subscription payload schema_version is unsupported")
    try:
        sync_job_id = _uuid_text(payload.get("sync_job_id"), name="sync_job_id")
        subscription_id = _uuid_text(payload.get("subscription_id"), name="subscription_id")
        run_id = _uuid_text(payload.get("run_id"), name="run_id")
    except ValueError as exc:
        raise PipelineJobRepositoryError(str(exc)) from exc
    if job.natural_key != pipeline_subscription_natural_key(sync_job_id):
        raise PipelineJobRepositoryError("pipeline.subscription natural key does not match its payload")
    if job.subscription_id != subscription_id or job.run_id != run_id:
        raise PipelineJobRepositoryError("pipeline.subscription payload does not match its durable scope")
    return PipelineSubscriptionPayload(
        schema_version=schema_version,
        sync_job_id=sync_job_id,
        subscription_id=subscription_id,
        run_id=run_id,
    )


def _projection(job: Job) -> PipelineSubscriptionJob:
    payload = parse_pipeline_subscription_payload(job)
    if job.account_id is None or job.platform not in PLATFORMS:
        raise PipelineJobRepositoryError("pipeline.subscription account or platform scope is incomplete")
    if job.max_attempts != PIPELINE_MAX_ATTEMPTS:
        raise PipelineJobRepositoryError("pipeline.subscription attempt policy is invalid")
    return PipelineSubscriptionJob(
        job_id=job.id,
        sync_job_id=payload.sync_job_id,
        subscription_id=payload.subscription_id,
        account_id=job.account_id,
        platform=job.platform,
        run_id=payload.run_id,
        status=job.status,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        available_at=job.available_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


class PipelineJobRepository:
    """Idempotent enqueue and type-isolated claim for coordinator Jobs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _source_scope(self, sync_job_id: str, run_id: str) -> tuple[Job, SyncRun, Subscription, Account]:
        source = self.session.get(Job, sync_job_id)
        if source is None:
            raise NotFoundError(f"source sync job not found: {sync_job_id}")
        if source.job_type != _SOURCE_SYNC_JOB_TYPE:
            raise PipelineJobRepositoryError("pipeline source is not a sync.subscription job")
        try:
            validate_sync_subscription_job(source)
        except ValueError as exc:
            raise PipelineJobRepositoryError("pipeline source durable contract is invalid") from exc
        if source.status != "succeeded" or source.run_id != run_id:
            raise PipelineJobRepositoryError("pipeline source is not bound to the exact succeeded run")
        if source.subscription_id is None or source.account_id is None or source.platform not in PLATFORMS:
            raise PipelineJobRepositoryError("pipeline source scope is incomplete")

        run = self.session.get(SyncRun, run_id)
        if run is None or run.status != "succeeded" or run.subscription_id != source.subscription_id:
            raise PipelineJobRepositoryError("pipeline run is not a succeeded run for the source subscription")
        try:
            subscription = SubscriptionRepository(self.session).require_active(source.subscription_id, lock=True)
        except SubscriptionRemovalError:
            raise PipelineJobRepositoryError("subscription_removed") from None
        if subscription is None or subscription.account_id != source.account_id:
            raise PipelineJobRepositoryError("pipeline source does not match the current subscription account")
        account = self.session.get(Account, source.account_id)
        if account is None or account.platform != source.platform:
            raise PipelineJobRepositoryError("pipeline source does not match the current account platform")
        return source, run, subscription, account

    def enqueue_succeeded_sync(
        self,
        sync_job_id: str | UUID,
        *,
        run_id: str | UUID,
        now: datetime | None = None,
    ) -> PipelineSubscriptionJob:
        """Create or return the exact coordinator for a succeeded sync Job."""

        source_id = _uuid_text(str(sync_job_id), name="sync_job_id")
        normalized_run_id = _uuid_text(str(run_id), name="run_id")
        current = _aware_utc(now)
        source, _run, _subscription, _account = self._source_scope(source_id, normalized_run_id)
        if source.subscription_id is None or source.account_id is None or source.platform is None:
            raise PipelineJobRepositoryError("pipeline source scope is incomplete")
        payload = PipelineSubscriptionPayload(
            schema_version=PIPELINE_PAYLOAD_SCHEMA_VERSION,
            sync_job_id=source.id,
            subscription_id=source.subscription_id,
            run_id=normalized_run_id,
        )
        job = JobRepository(self.session).enqueue(
            job_type=PIPELINE_SUBSCRIPTION_JOB_TYPE,
            natural_key=pipeline_subscription_natural_key(source.id),
            payload=payload.to_mapping(),
            run_id=normalized_run_id,
            subscription_id=source.subscription_id,
            account_id=source.account_id,
            platform=source.platform,
            max_attempts=PIPELINE_MAX_ATTEMPTS,
            available_at=current,
            scheduled_for=current,
        )
        try:
            result = _projection(job)
        except PipelineJobRepositoryError:
            repaired = self._repair_rejected_collision(
                job,
                source=source,
                payload=payload,
                run_id=normalized_run_id,
                now=current,
            )
            if repaired is None:
                raise
            job = repaired
            result = _projection(job)
        if not self._matches_source(result, source=source, run_id=normalized_run_id):
            repaired = self._repair_rejected_collision(
                job,
                source=source,
                payload=payload,
                run_id=normalized_run_id,
                now=current,
            )
            if repaired is None:
                raise PipelineJobRepositoryError("idempotent pipeline job conflicts with the succeeded sync scope")
            job = repaired
            result = _projection(job)
        if not self._matches_source(result, source=source, run_id=normalized_run_id):
            raise PipelineJobRepositoryError("repaired pipeline job conflicts with the succeeded sync scope")
        return result

    @staticmethod
    def _matches_source(
        result: PipelineSubscriptionJob,
        *,
        source: Job,
        run_id: str,
    ) -> bool:
        return not (
            result.sync_job_id != source.id
            or result.subscription_id != source.subscription_id
            or result.account_id != source.account_id
            or result.platform != source.platform
            or result.run_id != run_id
        )

    def _repair_rejected_collision(
        self,
        job: Job,
        *,
        source: Job,
        payload: PipelineSubscriptionPayload,
        run_id: str,
        now: datetime,
    ) -> Job | None:
        """Requeue only a row this repository previously rejected as invalid."""

        if (
            job.status != "failed_terminal"
            or job.last_error_code
            not in {
                PIPELINE_COORDINATOR_INVALID_ERROR_CODE,
                PIPELINE_COORDINATOR_STALE_ERROR_CODE,
            }
            or job.lease_owner is not None
            or job.lease_token is not None
            or job.lease_expires_at is not None
        ):
            return None
        statement = (
            update(Job)
            .where(
                Job.id == job.id,
                Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE,
                Job.natural_key == pipeline_subscription_natural_key(source.id),
                Job.status == "failed_terminal",
                Job.last_error_code.in_(
                    (
                        PIPELINE_COORDINATOR_INVALID_ERROR_CODE,
                        PIPELINE_COORDINATOR_STALE_ERROR_CODE,
                    )
                ),
                Job.lease_owner.is_(None),
                Job.lease_token.is_(None),
                Job.lease_expires_at.is_(None),
            )
            .values(
                payload=payload.to_mapping(),
                run_id=run_id,
                subscription_id=source.subscription_id,
                account_id=source.account_id,
                platform=source.platform,
                status="queued",
                priority=0,
                attempts=0,
                max_attempts=PIPELINE_MAX_ATTEMPTS,
                available_at=now,
                scheduled_for=now,
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                started_at=None,
                finished_at=None,
                last_error_code=None,
                last_error_message=None,
                updated_at=now,
            )
            .returning(Job)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        repaired = self.session.execute(statement).scalar_one_or_none()
        if repaired is None:
            raise PipelineJobRepositoryError("pipeline idempotency collision changed during repair")
        return repaired

    def get(self, job_id: str | UUID) -> PipelineSubscriptionJob:
        normalized_id = _uuid_text(str(job_id), name="job_id")
        job = self.session.get(Job, normalized_id)
        if job is None:
            raise NotFoundError(f"pipeline job not found: {normalized_id}")
        return _projection(job)

    def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int = 60,
        scan_limit: int = _DEFAULT_CLAIM_SCAN_LIMIT,
        now: datetime | None = None,
    ) -> PipelineSubscriptionClaim | None:
        """Claim the next valid coordinator, terminalizing rejected queue rows."""

        if not isinstance(worker_id, str) or not worker_id.strip() or len(worker_id) > 255:
            raise ValueError("worker_id is invalid")
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= _MAX_LEASE_SECONDS:
            raise ValueError("lease_seconds must be between 1 and 86400")
        if type(scan_limit) is not int or not 1 <= scan_limit <= _MAX_CLAIM_SCAN_LIMIT:
            raise ValueError("scan_limit must be between 1 and 1000")
        current = _aware_utc(now)
        jobs = JobRepository(self.session)
        for _ in range(scan_limit):
            job = jobs.claim_next(
                worker_id=worker_id,
                lease_seconds=lease_seconds,
                now=current,
                job_types=(PIPELINE_SUBSCRIPTION_JOB_TYPE,),
            )
            if job is None:
                return None
            if job.lease_token is None or job.lease_expires_at is None:
                raise PipelineJobRepositoryError("claimed pipeline.subscription lease is incomplete")

            try:
                result = _projection(job)
            except PipelineJobRepositoryError:
                jobs.fail(
                    job.id,
                    worker_id=worker_id,
                    lease_token=job.lease_token,
                    retryable=False,
                    error_code=PIPELINE_COORDINATOR_INVALID_ERROR_CODE,
                    error_message=_INVALID_COORDINATOR_MESSAGE,
                    now=current,
                )
                continue

            try:
                source, _run, _subscription, _account = self._source_scope(result.sync_job_id, result.run_id)
            except (NotFoundError, PipelineJobRepositoryError):
                jobs.fail(
                    job.id,
                    worker_id=worker_id,
                    lease_token=job.lease_token,
                    retryable=False,
                    error_code=PIPELINE_COORDINATOR_STALE_ERROR_CODE,
                    error_message=_STALE_COORDINATOR_MESSAGE,
                    now=current,
                )
                continue
            if (
                result.subscription_id != source.subscription_id
                or result.account_id != source.account_id
                or result.platform != source.platform
            ):
                jobs.fail(
                    job.id,
                    worker_id=worker_id,
                    lease_token=job.lease_token,
                    retryable=False,
                    error_code=PIPELINE_COORDINATOR_STALE_ERROR_CODE,
                    error_message=_STALE_COORDINATOR_MESSAGE,
                    now=current,
                )
                continue

            return PipelineSubscriptionClaim(
                job_id=result.job_id,
                sync_job_id=result.sync_job_id,
                subscription_id=result.subscription_id,
                account_id=result.account_id,
                platform=result.platform,
                run_id=result.run_id,
                attempt=result.attempts,
                max_attempts=result.max_attempts,
                lease_token=job.lease_token,
                lease_expires_at=job.lease_expires_at,
            )
        return None


__all__ = [
    "PIPELINE_COORDINATOR_INVALID_ERROR_CODE",
    "PIPELINE_COORDINATOR_STALE_ERROR_CODE",
    "PIPELINE_MAX_ATTEMPTS",
    "PIPELINE_PAYLOAD_SCHEMA_VERSION",
    "PIPELINE_SUBSCRIPTION_JOB_TYPE",
    "PipelineJobRepository",
    "PipelineJobRepositoryError",
    "PipelineSubscriptionClaim",
    "PipelineSubscriptionJob",
    "PipelineSubscriptionPayload",
    "parse_pipeline_subscription_payload",
    "pipeline_subscription_natural_key",
]
