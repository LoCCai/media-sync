"""Durable, SQLite-safe persistence for subscription scheduling.

The repository keeps every transaction short and accepts an explicit SQLAlchemy
``Session``.  It only operates on ``sync.subscription`` jobs; execution 0005
download and Emby jobs remain owned by their exact-claim application services.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import case, exists, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from media_sync.infrastructure.db.base import new_uuid, utc_now
from media_sync.infrastructure.db.models import (
    ACTIVE_SYNC_JOB_STATUSES,
    JOB_STATUSES,
    PLATFORMS,
    TERMINAL_JOB_STATUSES,
    TERMINAL_RUN_STATUSES,
    Account,
    Job,
    SchedulerLane,
    Subscription,
    SyncRun,
)
from media_sync.infrastructure.db.repositories import (
    LeaseLostError,
    NotFoundError,
    RepositoryError,
    SubscriptionRemovalError,
    SubscriptionRepository,
    SyncRunRepository,
)

from .policy import FailureDisposition, RetryPolicy, classify_failure

SYNC_SUBSCRIPTION_JOB_TYPE = "sync.subscription"
SCHEDULE_PAYLOAD_SCHEMA_VERSION = 1

_ACTIVE_WORK_STATUSES = ("claimed", "running")
_REQUEUE_STATUSES = ("retry_wait", "failed_retryable")
_WAITING_STATUSES = ("waiting_auth", "waiting_user")
_PAYLOAD_KEYS = frozenset({"schema_version", "subscription_id", "schedule_revision", "retry_policy"})
_FIXED_CODE = re.compile(r"[a-z][a-z0-9_]{0,127}\Z")
_ADAPTER_KEY = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_MAX_BATCH = 1_000
_MAX_LEASE_SECONDS = 86_400
_MAX_LANE_SECONDS = 604_800


class SchedulerRepositoryError(RepositoryError):
    """A scheduler row violated the closed durable contract."""


class StaleLaneError(SchedulerRepositoryError):
    """A lane policy/state compare-and-swap lost to another writer."""


class SchedulerLeaseLostError(LeaseLostError):
    """A subscription worker no longer owns the exact scheduler lease."""


def _aware_utc(value: datetime | None = None) -> datetime:
    result = value or utc_now()
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return result.astimezone(UTC)


def _bounded_int(value: int, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def _required_text(value: str, *, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > maximum
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized)
    ):
        raise ValueError(f"{name} is invalid")
    return normalized


def _optional_identifier(value: str | UUID | None, *, name: str) -> str | None:
    if value is None:
        return None
    return _required_text(str(value), name=name, maximum=36)


def _safe_add(value: datetime, seconds: int, *, name: str) -> datetime:
    _bounded_int(seconds, name=name, minimum=0, maximum=_MAX_LANE_SECONDS)
    try:
        return value + timedelta(seconds=seconds)
    except OverflowError as exc:
        raise ValueError(f"{name} overflows datetime") from exc


def _adapter_allowlist(values: Collection[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    if isinstance(values, (str, bytes)):
        raise ValueError("adapter_allowlist must be a collection of adapter keys")
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError("adapter_allowlist contains an invalid adapter key")
        key = value.strip()
        if _ADAPTER_KEY.fullmatch(key) is None:
            raise ValueError("adapter_allowlist contains an invalid adapter key")
        normalized.add(key)
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class MaterializedCycle:
    job_id: str
    subscription_id: str
    schedule_revision: int
    scheduled_for: datetime


@dataclass(frozen=True, slots=True)
class SchedulerClaim:
    """Internal worker claim; the fencing token is intentionally repr-hidden."""

    job_id: str
    subscription_id: str
    account_id: str
    platform: str
    schedule_revision: int
    attempt: int
    max_attempts: int
    lease_token: str = field(repr=False)
    lease_expires_at: datetime
    retry_policy: RetryPolicy
    run_id: str | None = None


@dataclass(frozen=True, slots=True)
class SchedulerJobSummary:
    """Redaction-safe job projection for application and CLI control surfaces."""

    job_id: str
    subscription_id: str
    account_id: str
    platform: str
    status: str
    attempts: int
    max_attempts: int
    available_at: datetime
    scheduled_for: datetime | None
    run_id: str | None
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class SubscriptionSchedule:
    """Redaction-safe subscription scheduling projection."""

    subscription_id: str
    enabled: bool
    interval_seconds: int
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_success_at: datetime | None
    schedule_revision: int
    consecutive_failures: int


LaneScope = Literal["platform", "account"]


@dataclass(frozen=True, slots=True)
class LanePolicy:
    scope_type: LaneScope
    platform: str
    account_id: str | None = None
    max_concurrency: int = 1
    min_start_interval_seconds: int = 5
    failure_threshold: int = 3
    cooldown_seconds: int = 900

    def __post_init__(self) -> None:
        if self.scope_type not in {"platform", "account"}:
            raise ValueError("scope_type must be 'platform' or 'account'")
        if not isinstance(self.platform, str) or self.platform not in PLATFORMS:
            raise ValueError("platform is unsupported")
        if self.scope_type == "platform" and self.account_id is not None:
            raise ValueError("platform lanes cannot have account_id")
        if self.scope_type == "account" and self.account_id is None:
            raise ValueError("account lanes require account_id")
        if self.account_id is not None:
            _required_text(self.account_id, name="account_id", maximum=36)
        _bounded_int(self.max_concurrency, name="max_concurrency", minimum=1, maximum=_MAX_BATCH)
        _bounded_int(
            self.min_start_interval_seconds,
            name="min_start_interval_seconds",
            minimum=0,
            maximum=_MAX_LANE_SECONDS,
        )
        _bounded_int(self.failure_threshold, name="failure_threshold", minimum=1, maximum=2_147_483_647)
        _bounded_int(
            self.cooldown_seconds,
            name="cooldown_seconds",
            minimum=1,
            maximum=_MAX_LANE_SECONDS,
        )


@dataclass(frozen=True, slots=True)
class LaneSnapshot:
    lane_id: str
    policy: LanePolicy
    next_start_at: datetime | None
    consecutive_failures: int
    circuit_state: Literal["closed", "open", "half_open"]
    circuit_open_until: datetime | None
    half_open_job_id: str | None
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class _Payload:
    subscription_id: str
    schedule_revision: int
    retry_policy: RetryPolicy


def _schedule_payload(subscription_id: str, schedule_revision: int, retry_policy: RetryPolicy) -> dict[str, object]:
    return {
        "schema_version": SCHEDULE_PAYLOAD_SCHEMA_VERSION,
        "subscription_id": subscription_id,
        "schedule_revision": schedule_revision,
        "retry_policy": retry_policy.to_payload(),
    }


def _parse_payload(job: Job) -> _Payload:
    payload = job.payload
    if not isinstance(payload, Mapping) or set(payload) != _PAYLOAD_KEYS:
        raise ValueError("sync.subscription payload is not closed schema v1")
    if payload.get("schema_version") != SCHEDULE_PAYLOAD_SCHEMA_VERSION:
        raise ValueError("sync.subscription payload schema_version is unsupported")
    subscription_id = payload.get("subscription_id")
    schedule_revision = payload.get("schedule_revision")
    retry_payload = payload.get("retry_policy")
    if not isinstance(subscription_id, str) or subscription_id != job.subscription_id:
        raise ValueError("sync.subscription payload subscription_id does not match its scope")
    if isinstance(schedule_revision, bool) or not isinstance(schedule_revision, int) or schedule_revision < 0:
        raise ValueError("sync.subscription payload schedule_revision is invalid")
    if not isinstance(retry_payload, Mapping):
        raise ValueError("sync.subscription payload retry_policy is invalid")
    retry_policy = RetryPolicy.from_payload(cast(Mapping[str, object], retry_payload))
    expected_key = f"subscription:{subscription_id}:schedule:{schedule_revision}"
    if job.natural_key != expected_key or job.max_attempts != retry_policy.max_attempts:
        raise ValueError("sync.subscription durable identity does not match its payload")
    return _Payload(subscription_id, schedule_revision, retry_policy)


def validate_sync_subscription_job(job: Job) -> None:
    """Validate the closed durable identity of one source sync Job."""

    if job.job_type != SYNC_SUBSCRIPTION_JOB_TYPE:
        raise ValueError("source job is not sync.subscription")
    _parse_payload(job)


def _summary(job: Job) -> SchedulerJobSummary:
    if job.job_type != SYNC_SUBSCRIPTION_JOB_TYPE:
        raise SchedulerRepositoryError("scheduler projection rejected a foreign job type")
    if job.subscription_id is None or job.account_id is None or job.platform is None:
        raise SchedulerRepositoryError("sync.subscription job scope is incomplete")
    return SchedulerJobSummary(
        job_id=job.id,
        subscription_id=job.subscription_id,
        account_id=job.account_id,
        platform=job.platform,
        status=job.status,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        available_at=job.available_at,
        scheduled_for=job.scheduled_for,
        run_id=job.run_id,
        last_error_code=job.last_error_code,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _subscription_schedule(subscription: Subscription) -> SubscriptionSchedule:
    return SubscriptionSchedule(
        subscription_id=subscription.id,
        enabled=subscription.enabled,
        interval_seconds=subscription.interval_seconds,
        next_run_at=subscription.next_run_at,
        last_run_at=subscription.last_run_at,
        last_success_at=subscription.last_success_at,
        schedule_revision=subscription.schedule_revision,
        consecutive_failures=subscription.consecutive_failures,
    )


def _claim(job: Job) -> SchedulerClaim:
    payload = _parse_payload(job)
    if (
        job.subscription_id is None
        or job.account_id is None
        or job.platform is None
        or job.lease_token is None
        or job.lease_expires_at is None
    ):
        raise SchedulerRepositoryError("claimed sync.subscription job scope or lease is incomplete")
    return SchedulerClaim(
        job_id=job.id,
        subscription_id=job.subscription_id,
        account_id=job.account_id,
        platform=job.platform,
        schedule_revision=payload.schedule_revision,
        attempt=job.attempts,
        max_attempts=job.max_attempts,
        lease_token=job.lease_token,
        lease_expires_at=job.lease_expires_at,
        retry_policy=payload.retry_policy,
        run_id=job.run_id,
    )


def _lane_snapshot(lane: SchedulerLane) -> LaneSnapshot:
    if lane.scope_type not in {"platform", "account"} or lane.circuit_state not in {
        "closed",
        "open",
        "half_open",
    }:
        raise SchedulerRepositoryError("scheduler lane contains unsupported durable state")
    policy = LanePolicy(
        scope_type=cast(LaneScope, lane.scope_type),
        platform=lane.platform,
        account_id=lane.account_id,
        max_concurrency=lane.max_concurrency,
        min_start_interval_seconds=lane.min_start_interval_seconds,
        failure_threshold=lane.failure_threshold,
        cooldown_seconds=lane.cooldown_seconds,
    )
    return LaneSnapshot(
        lane_id=lane.id,
        policy=policy,
        next_start_at=lane.next_start_at,
        consecutive_failures=lane.consecutive_failures,
        circuit_state=cast(Literal["closed", "open", "half_open"], lane.circuit_state),
        circuit_open_until=lane.circuit_open_until,
        half_open_job_id=lane.half_open_job_id,
        revision=lane.revision,
        created_at=lane.created_at,
        updated_at=lane.updated_at,
    )


class SchedulerRepository:
    """Transactional repository for the one closed subscription Job type."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _serialize_sqlite_writer(self) -> None:
        """Acquire SQLite's writer slot before making a read/decide/CAS choice."""

        if self.session.get_bind().dialect.name == "sqlite":
            self.session.connection().exec_driver_sql("UPDATE jobs SET updated_at = updated_at WHERE 0")

    def _get_sync_job(self, job_id: str) -> Job:
        normalized_id = _required_text(job_id, name="job_id", maximum=36)
        job = self.session.get(Job, normalized_id)
        if job is None:
            raise NotFoundError(f"job not found: {normalized_id}")
        if job.job_type != SYNC_SUBSCRIPTION_JOB_TYPE:
            raise SchedulerRepositoryError("scheduler operation rejected a foreign job type")
        return job

    def _current_sync_job(self, job_id: str) -> Job:
        self.session.expire_all()
        return self._get_sync_job(job_id)

    def _locked_sync_job(self, job_id: str) -> Job:
        """Read current finalization identity while fencing attachment changes."""

        job = self.session.scalar(
            select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True)
        )
        if job is None:
            raise NotFoundError(f"job not found: {job_id}")
        if job.job_type != SYNC_SUBSCRIPTION_JOB_TYPE:
            raise SchedulerRepositoryError("scheduler operation rejected a foreign job type")
        return job

    def _enqueue_pipeline_for_succeeded_run(self, job: Job, *, now: datetime) -> None:
        """Atomically emit the one coordinator only for durable run success."""

        from .pipeline import PipelineJobRepository

        if job.run_id is None:
            return
        run = self.session.get(SyncRun, job.run_id)
        if run is None or run.subscription_id != job.subscription_id or run.status != "succeeded":
            return
        PipelineJobRepository(self.session).enqueue_succeeded_sync(job.id, run_id=run.id, now=now)

    def _validated_result_run_id(
        self, job: Job, run_id: str | None, *, explicit_ownership_conflict: bool = False
    ) -> str | None:
        """Bind a handler run only when it belongs to the claimed subscription."""

        if run_id is None:
            return None
        if job.run_id is not None and job.run_id != run_id:
            raise SchedulerRepositoryError("scheduler result run does not match its attachment")
        run = self.session.execute(
            select(SyncRun.subscription_id, SyncRun.status, SyncRun.error_code).where(SyncRun.id == run_id)
        ).one_or_none()
        if run is None or run.subscription_id != job.subscription_id:
            raise SchedulerRepositoryError("scheduler result run scope is invalid")
        if (
            job.run_id is None
            and run.status == "failed_terminal"
            and run.error_code == "content_ownership_conflict"
            and not explicit_ownership_conflict
        ):
            # Legacy handlers can bind their Run while finalizing, including an
            # explicitly reported typed conflict. An unrelated advisory outcome
            # must not adopt a historical conflict for later retry recovery.
            raise SchedulerRepositoryError("scheduler conflict result requires its current attachment")
        return run_id

    def _cancel_attached_run(self, job: Job, *, now: datetime, error_code: str) -> None:
        """Terminalize only this subscription Job's currently attached run."""

        if job.run_id is None:
            return
        run = self.session.get(SyncRun, job.run_id)
        if run is None or run.subscription_id != job.subscription_id:
            raise SchedulerRepositoryError("scheduler attached run scope is invalid")
        if run.status in TERMINAL_RUN_STATUSES:
            return
        SyncRunRepository(self.session).set_status(
            run.id,
            "cancelled",
            expected_status=run.status,
            error_code=error_code,
            error_message=None,
            at=now,
        )

    def _reconcile_succeeded_attachment(
        self,
        job: Job,
        *,
        now: datetime,
        expired_only: bool,
        locked_lanes: tuple[SchedulerLane, ...] | None = None,
    ) -> Job | None:
        """Make an attached succeeded SyncRun authoritative for its scheduler Job.

        Media ingestion and scheduler finalization intentionally commit in
        separate transactions.  If the latter is unavailable, the succeeded
        SyncRun is the durable application truth.  Reclaim and operator cancel
        therefore reconcile the Job, lanes and subscription to success in one
        writer transaction instead of manufacturing a contradictory outcome.
        """

        if job.run_id is None:
            return None
        run = self.session.get(SyncRun, job.run_id)
        if run is None or run.subscription_id != job.subscription_id:
            raise SchedulerRepositoryError("scheduler attached run scope is invalid")
        if run.status != "succeeded":
            return None

        conditions: list[Any] = [
            Job.id == job.id,
            Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
            Job.status == job.status,
            Job.run_id == run.id,
        ]
        if expired_only:
            token_condition = (
                Job.lease_token.is_(None) if job.lease_token is None else Job.lease_token == job.lease_token
            )
            conditions.extend(
                (
                    token_condition,
                    Job.lease_expires_at.is_not(None),
                    Job.lease_expires_at <= now,
                )
            )
        reconciled = self.session.scalar(
            update(Job)
            .where(*conditions)
            .values(
                status="succeeded",
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                finished_at=run.finished_at or now,
                updated_at=now,
                last_error_code=None,
                last_error_message=None,
            )
            .returning(Job)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        if reconciled is None:
            return None
        self._apply_lane_success(reconciled, now=now, locked_lanes=locked_lanes)
        self._finalize_subscription(reconciled, now=now, outcome="success")
        self._enqueue_pipeline_for_succeeded_run(reconciled, now=now)
        return reconciled

    @staticmethod
    def _has_ownership_conflict_attachment() -> Any:
        """Only the exact current attachment and literal terminal code are truth."""

        return exists(
            select(SyncRun.id).where(
                SyncRun.id == Job.run_id,
                SyncRun.subscription_id == Job.subscription_id,
                SyncRun.status == "failed_terminal",
                SyncRun.error_code == "content_ownership_conflict",
            )
        )

    def _reconcile_ownership_conflict_attachment(
        self,
        job: Job,
        *,
        now: datetime,
        expired_only: bool = False,
        owned_by: tuple[str, str] | None = None,
        allowed_statuses: tuple[str, ...] = _ACTIVE_WORK_STATUSES,
        locked_lanes: tuple[SchedulerLane, ...] | None = None,
    ) -> Job | None:
        """Recover a committed conflict without retrying or changing circuit counts.

        The handler's Run commit can outlive its acknowledgement or its worker.
        Read columns (not an ORM-cached Run), then CAS the exact attachment,
        observed Job status and lease. A returned historical Run is never used.
        """

        if job.run_id is None or job.status in TERMINAL_JOB_STATUSES:
            return None
        run = self.session.execute(
            select(SyncRun.subscription_id, SyncRun.status, SyncRun.error_code, SyncRun.finished_at).where(
                SyncRun.id == job.run_id
            )
        ).one_or_none()
        if run is None or run.subscription_id != job.subscription_id:
            raise SchedulerRepositoryError("scheduler attached run scope is invalid")
        if run.status != "failed_terminal" or run.error_code != "content_ownership_conflict":
            return None

        conditions: list[Any] = [
            Job.id == job.id,
            Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
            Job.subscription_id == job.subscription_id,
            Job.status == job.status,
            Job.run_id == job.run_id,
            Job.lease_owner.is_(None) if job.lease_owner is None else Job.lease_owner == job.lease_owner,
            Job.lease_token.is_(None) if job.lease_token is None else Job.lease_token == job.lease_token,
            self._has_ownership_conflict_attachment(),
        ]
        if expired_only:
            conditions.extend(
                (Job.status.in_(_ACTIVE_WORK_STATUSES), Job.lease_expires_at.is_not(None), Job.lease_expires_at <= now)
            )
        if owned_by is not None:
            owner, token = owned_by
            conditions.extend(
                (
                    Job.lease_owner == owner,
                    Job.lease_token == token,
                    Job.status.in_(allowed_statuses),
                    Job.lease_expires_at.is_not(None),
                    Job.lease_expires_at > now,
                    exists(
                        select(Subscription.id).where(
                            Subscription.id == Job.subscription_id, Subscription.deleted_at.is_(None)
                        )
                    ),
                )
            )
        reconciled = self.session.scalar(
            update(Job)
            .where(*conditions)
            .values(
                status="failed_terminal",
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                finished_at=run.finished_at or now,
                updated_at=now,
                last_error_code="content_ownership_conflict",
                last_error_message=None,
            )
            .returning(Job)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        if reconciled is None:
            if owned_by is not None:
                raise self._lease_failure(job.id, worker_id=owned_by[0])
            raise SchedulerRepositoryError("scheduler conflict attachment changed during reconciliation")
        self._apply_lane_failure(reconciled, now=now, affects_circuit=False, locked_lanes=locked_lanes)
        try:
            _parse_payload(reconciled)
        except ValueError:
            # The exact Run still proves this Job's outcome, but malformed
            # cycle identity cannot authorize any subscription schedule write.
            # Retire this Job without poisoning unrelated queued subscriptions.
            return reconciled
        self._finalize_subscription(reconciled, now=now, outcome="failure")
        return reconciled

    def materialize_due(
        self,
        *,
        limit: int,
        now: datetime | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> list[MaterializedCycle]:
        """Materialize a bounded due set using schedule-revision fencing."""

        batch_limit = _bounded_int(limit, name="limit", minimum=1, maximum=_MAX_BATCH)
        current = _aware_utc(now)
        frozen_retry = retry_policy or RetryPolicy()
        self._serialize_sqlite_writer()

        active_cycle = exists(
            select(Job.id).where(
                Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                Job.subscription_id == Subscription.id,
                Job.status.in_(tuple(ACTIVE_SYNC_JOB_STATUSES)),
            )
        )
        due = or_(Subscription.next_run_at.is_(None), Subscription.next_run_at <= current)
        candidates = self.session.execute(
            select(
                Subscription.id,
                Subscription.account_id,
                Subscription.schedule_revision,
                Subscription.next_run_at,
                Account.platform,
            )
            .join(Account, Account.id == Subscription.account_id)
            .where(Subscription.enabled.is_(True), Subscription.deleted_at.is_(None), due, ~active_cycle)
            .order_by(
                case((Subscription.next_run_at.is_(None), 0), else_=1),
                Subscription.next_run_at,
                Subscription.created_at,
                Subscription.id,
            )
            .limit(batch_limit)
        ).all()

        materialized: list[MaterializedCycle] = []
        for subscription_id, account_id, schedule_revision, next_run_at, platform in candidates:
            fenced_active_cycle = exists(
                select(Job.id).where(
                    Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                    Job.subscription_id == subscription_id,
                    Job.status.in_(tuple(ACTIVE_SYNC_JOB_STATUSES)),
                )
            )
            claimed_revision = self.session.scalar(
                update(Subscription)
                .where(
                    Subscription.id == subscription_id,
                    Subscription.enabled.is_(True),
                    Subscription.deleted_at.is_(None),
                    Subscription.schedule_revision == schedule_revision,
                    or_(Subscription.next_run_at.is_(None), Subscription.next_run_at <= current),
                    ~fenced_active_cycle,
                )
                .values(
                    schedule_revision=Subscription.schedule_revision + 1,
                    updated_at=current,
                )
                .returning(Subscription.schedule_revision)
                .execution_options(synchronize_session=False)
            )
            if claimed_revision != schedule_revision + 1:
                continue

            scheduled_for = current if next_run_at is None else _aware_utc(next_run_at)
            job = Job(
                id=new_uuid(),
                subscription_id=subscription_id,
                account_id=account_id,
                platform=platform,
                job_type=SYNC_SUBSCRIPTION_JOB_TYPE,
                natural_key=f"subscription:{subscription_id}:schedule:{schedule_revision}",
                payload=_schedule_payload(subscription_id, schedule_revision, frozen_retry),
                status="queued",
                priority=0,
                attempts=0,
                max_attempts=frozen_retry.max_attempts,
                available_at=current,
                scheduled_for=scheduled_for,
                created_at=current,
                updated_at=current,
            )
            self.session.add(job)
            self.session.flush()
            materialized.append(
                MaterializedCycle(
                    job_id=job.id,
                    subscription_id=subscription_id,
                    schedule_revision=schedule_revision,
                    scheduled_for=scheduled_for,
                )
            )
        return materialized

    def list_jobs(
        self,
        *,
        status: str | None = None,
        subscription_id: str | None = None,
        limit: int = 100,
    ) -> list[SchedulerJobSummary]:
        batch_limit = _bounded_int(limit, name="limit", minimum=1, maximum=_MAX_BATCH)
        statement = select(Job).where(Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE)
        if status is not None:
            if status not in JOB_STATUSES:
                raise ValueError("unsupported scheduler job status")
            statement = statement.where(Job.status == status)
        if subscription_id is not None:
            statement = statement.where(
                Job.subscription_id
                == _required_text(
                    subscription_id,
                    name="subscription_id",
                    maximum=36,
                )
            )
        jobs = self.session.scalars(statement.order_by(Job.created_at.desc(), Job.id.desc()).limit(batch_limit)).all()
        return [_summary(job) for job in jobs]

    def get_job(self, job_id: str) -> SchedulerJobSummary:
        return _summary(self._get_sync_job(job_id))

    @staticmethod
    def _lane_filter(
        scope_type: LaneScope,
        *,
        platform: str,
        account_id: str | None,
    ) -> tuple[Any, ...]:
        if scope_type == "platform":
            return (
                SchedulerLane.scope_type == "platform",
                SchedulerLane.platform == platform,
                SchedulerLane.account_id.is_(None),
            )
        return (
            SchedulerLane.scope_type == "account",
            SchedulerLane.platform == platform,
            SchedulerLane.account_id == account_id,
        )

    def _find_lane(self, policy: LanePolicy) -> SchedulerLane | None:
        return self.session.scalar(
            select(SchedulerLane).where(
                *self._lane_filter(
                    policy.scope_type,
                    platform=policy.platform,
                    account_id=policy.account_id,
                )
            )
        )

    def _ensure_lane(self, policy: LanePolicy, *, now: datetime) -> SchedulerLane:
        if policy.account_id is not None:
            account_platform = self.session.scalar(select(Account.platform).where(Account.id == policy.account_id))
            if account_platform is None:
                raise NotFoundError(f"account not found: {policy.account_id}")
            if account_platform != policy.platform:
                raise SchedulerRepositoryError("account lane platform does not match its account")
        if self.session.get_bind().dialect.name == "sqlite":
            self.session.execute(
                sqlite_insert(SchedulerLane)
                .values(
                    id=new_uuid(),
                    scope_type=policy.scope_type,
                    platform=policy.platform,
                    account_id=policy.account_id,
                    max_concurrency=policy.max_concurrency,
                    min_start_interval_seconds=policy.min_start_interval_seconds,
                    failure_threshold=policy.failure_threshold,
                    cooldown_seconds=policy.cooldown_seconds,
                    consecutive_failures=0,
                    circuit_state="closed",
                    revision=0,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing()
                .execution_options(synchronize_session=False)
            )
        else:
            existing = self._find_lane(policy)
            if existing is None:
                self.session.add(
                    SchedulerLane(
                        scope_type=policy.scope_type,
                        platform=policy.platform,
                        account_id=policy.account_id,
                        max_concurrency=policy.max_concurrency,
                        min_start_interval_seconds=policy.min_start_interval_seconds,
                        failure_threshold=policy.failure_threshold,
                        cooldown_seconds=policy.cooldown_seconds,
                        created_at=now,
                        updated_at=now,
                    )
                )
                self.session.flush()
        lane = self._find_lane(policy)
        if lane is None:  # pragma: no cover - insert and unique index guarantee visibility
            raise SchedulerRepositoryError("scheduler lane insert lost its durable row")
        return lane

    def _job_lanes(self, job: Job, *, now: datetime) -> tuple[SchedulerLane, SchedulerLane]:
        if job.platform not in PLATFORMS or job.account_id is None:
            raise SchedulerRepositoryError("sync.subscription job lane scope is incomplete")
        platform_lane = self._ensure_lane(
            LanePolicy(scope_type="platform", platform=job.platform),
            now=now,
        )
        account_lane = self._ensure_lane(
            LanePolicy(scope_type="account", platform=job.platform, account_id=job.account_id),
            now=now,
        )
        return platform_lane, account_lane

    def get_lane(
        self,
        *,
        scope_type: LaneScope,
        platform: str,
        account_id: str | None = None,
    ) -> LaneSnapshot | None:
        policy = LanePolicy(scope_type=scope_type, platform=platform, account_id=account_id)
        lane = self._find_lane(policy)
        return None if lane is None else _lane_snapshot(lane)

    def list_lanes(self) -> list[LaneSnapshot]:
        lanes = self.session.scalars(
            select(SchedulerLane).order_by(
                SchedulerLane.platform,
                SchedulerLane.scope_type.desc(),
                SchedulerLane.account_id,
                SchedulerLane.id,
            )
        ).all()
        return [_lane_snapshot(lane) for lane in lanes]

    def update_lane(
        self,
        policy: LanePolicy,
        *,
        expected_revision: int | None = None,
        now: datetime | None = None,
    ) -> LaneSnapshot:
        current = _aware_utc(now)
        if expected_revision is not None:
            _bounded_int(
                expected_revision,
                name="expected_revision",
                minimum=0,
                maximum=2_147_483_647,
            )
        self._serialize_sqlite_writer()
        lane = self._ensure_lane(policy, now=current)
        revision = lane.revision if expected_revision is None else expected_revision
        updated = self.session.scalar(
            update(SchedulerLane)
            .where(SchedulerLane.id == lane.id, SchedulerLane.revision == revision)
            .values(
                max_concurrency=policy.max_concurrency,
                min_start_interval_seconds=policy.min_start_interval_seconds,
                failure_threshold=policy.failure_threshold,
                cooldown_seconds=policy.cooldown_seconds,
                revision=SchedulerLane.revision + 1,
                updated_at=current,
            )
            .returning(SchedulerLane)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        if updated is None:
            raise StaleLaneError("scheduler lane policy revision changed")
        return _lane_snapshot(updated)

    def reset_lane(
        self,
        *,
        scope_type: LaneScope,
        platform: str,
        account_id: str | None = None,
        expected_revision: int | None = None,
        now: datetime | None = None,
    ) -> LaneSnapshot:
        current = _aware_utc(now)
        policy = LanePolicy(scope_type=scope_type, platform=platform, account_id=account_id)
        if expected_revision is not None:
            _bounded_int(
                expected_revision,
                name="expected_revision",
                minimum=0,
                maximum=2_147_483_647,
            )
        self._serialize_sqlite_writer()
        lane = self._find_lane(policy)
        if lane is None:
            raise NotFoundError("scheduler lane not found")
        revision = lane.revision if expected_revision is None else expected_revision
        reset = self.session.scalar(
            update(SchedulerLane)
            .where(SchedulerLane.id == lane.id, SchedulerLane.revision == revision)
            .values(
                consecutive_failures=0,
                circuit_state="closed",
                circuit_open_until=None,
                half_open_job_id=None,
                revision=SchedulerLane.revision + 1,
                updated_at=current,
            )
            .returning(SchedulerLane)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        if reset is None:
            raise StaleLaneError("scheduler lane state revision changed")
        return _lane_snapshot(reset)

    def reset_lane_circuit(
        self,
        *,
        scope_type: LaneScope,
        platform: str,
        account_id: str | None = None,
        expected_revision: int | None = None,
        now: datetime | None = None,
    ) -> LaneSnapshot:
        """Explicitly named compatibility alias for control-plane callers."""

        return self.reset_lane(
            scope_type=scope_type,
            platform=platform,
            account_id=account_id,
            expected_revision=expected_revision,
            now=now,
        )

    def _reclaim_expired_sync(self, *, now: datetime) -> None:
        expired_jobs = self.session.scalars(
            select(Job)
            .where(
                Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                Job.status.in_(_ACTIVE_WORK_STATUSES),
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at <= now,
            )
            .order_by(Job.lease_expires_at, Job.created_at, Job.id)
            .limit(_MAX_BATCH)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        ).all()
        for observed in expired_jobs:
            if self._reconcile_succeeded_attachment(observed, now=now, expired_only=True) is not None:
                continue
            if self._reconcile_ownership_conflict_attachment(observed, now=now, expired_only=True) is not None:
                continue
            is_terminal = observed.attempts >= observed.max_attempts
            expected_token = observed.lease_token
            token_condition = Job.lease_token.is_(None) if expected_token is None else Job.lease_token == expected_token
            values: dict[str, Any] = {
                "status": "failed_terminal" if is_terminal else "failed_retryable",
                "lease_owner": None,
                "lease_token": None,
                "lease_expires_at": None,
                "available_at": now,
                "finished_at": now if is_terminal else None,
                "updated_at": now,
                "last_error_code": "unexpected_handler_failure",
                "last_error_message": None,
            }
            reclaimed = self.session.scalar(
                update(Job)
                .where(
                    Job.id == observed.id,
                    Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                    Job.status == observed.status,
                    token_condition,
                    Job.lease_expires_at.is_not(None),
                    Job.lease_expires_at <= now,
                )
                .values(**values)
                .returning(Job)
                .execution_options(synchronize_session="fetch", populate_existing=True)
            )
            if reclaimed is None:
                continue
            self._cancel_attached_run(
                reclaimed,
                now=now,
                error_code="scheduler_lease_lost",
            )
            self._apply_lane_failure(reclaimed, now=now, affects_circuit=True)
            if is_terminal:
                self._finalize_subscription(reclaimed, now=now, outcome="failure")

    def _requeue_due_sync(self, *, now: datetime) -> None:
        # Old interrupted finalizers may already have put the Job in retry_wait.
        # Recover these before the bulk requeue; the exclusion also fences any
        # remaining rows beyond the bounded recovery batch.
        conflicts = self.session.scalars(
            select(Job)
            .where(
                Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                Job.status.in_(_REQUEUE_STATUSES),
                self._has_ownership_conflict_attachment(),
            )
            .order_by(Job.available_at, Job.id)
            .limit(_MAX_BATCH)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        ).all()
        for observed in conflicts:
            self._reconcile_ownership_conflict_attachment(observed, now=now)
        self.session.execute(
            update(Job)
            .where(
                Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                Job.status.in_(_REQUEUE_STATUSES),
                Job.available_at <= now,
                Job.attempts < Job.max_attempts,
                ~self._has_ownership_conflict_attachment(),
            )
            .values(status="queued", updated_at=now)
            .execution_options(synchronize_session=False)
        )

    def _lane_active_count(self, lane: SchedulerLane) -> int:
        conditions: list[Any] = [
            Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
            Job.status.in_(_ACTIVE_WORK_STATUSES),
        ]
        if lane.scope_type == "platform":
            conditions.append(Job.platform == lane.platform)
        else:
            conditions.append(Job.account_id == lane.account_id)
        return int(self.session.scalar(select(func.count(Job.id)).where(*conditions)) or 0)

    def _lane_allows(self, lane: SchedulerLane, *, job_id: str, now: datetime) -> bool:
        if lane.next_start_at is not None and _aware_utc(lane.next_start_at) > now:
            return False
        if self._lane_active_count(lane) >= lane.max_concurrency:
            return False
        if lane.circuit_state == "closed":
            return True
        if lane.circuit_state == "open":
            return lane.circuit_open_until is not None and _aware_utc(lane.circuit_open_until) <= now
        if lane.circuit_state == "half_open":
            return lane.half_open_job_id in {None, job_id}
        return False

    def _reserve_lane(self, lane: SchedulerLane, *, job_id: str, now: datetime) -> SchedulerLane:
        next_start_at = _safe_add(
            now,
            lane.min_start_interval_seconds,
            name="min_start_interval_seconds",
        )
        conditions: list[Any] = [
            SchedulerLane.id == lane.id,
            SchedulerLane.revision == lane.revision,
            or_(SchedulerLane.next_start_at.is_(None), SchedulerLane.next_start_at <= now),
        ]
        values: dict[str, Any] = {
            "next_start_at": next_start_at,
            "revision": SchedulerLane.revision + 1,
            "updated_at": now,
        }
        if lane.circuit_state == "closed":
            conditions.append(SchedulerLane.circuit_state == "closed")
            values.update(circuit_open_until=None, half_open_job_id=None)
        elif lane.circuit_state == "open":
            conditions.extend(
                (
                    SchedulerLane.circuit_state == "open",
                    SchedulerLane.circuit_open_until.is_not(None),
                    SchedulerLane.circuit_open_until <= now,
                )
            )
            values.update(
                circuit_state="half_open",
                circuit_open_until=None,
                half_open_job_id=job_id,
            )
        elif lane.circuit_state == "half_open":
            conditions.extend(
                (
                    SchedulerLane.circuit_state == "half_open",
                    or_(
                        SchedulerLane.half_open_job_id.is_(None),
                        SchedulerLane.half_open_job_id == job_id,
                    ),
                )
            )
            values.update(circuit_open_until=None, half_open_job_id=job_id)
        else:
            raise SchedulerRepositoryError("scheduler lane circuit state is unsupported")
        reserved = self.session.scalar(
            update(SchedulerLane)
            .where(*conditions)
            .values(**values)
            .returning(SchedulerLane)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        if reserved is None:
            raise StaleLaneError("scheduler lane reservation changed concurrently")
        return reserved

    def _terminalize_invalid_candidate(self, job: Job, *, now: datetime) -> None:
        terminal = self.session.scalar(
            update(Job)
            .where(
                Job.id == job.id,
                Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                Job.status == "queued",
            )
            .values(
                status="failed_terminal",
                finished_at=now,
                updated_at=now,
                last_error_code="schema_invalid",
                last_error_message=None,
            )
            .returning(Job)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        if terminal is not None:
            self._finalize_subscription(terminal, now=now, outcome="failure", require_payload=False)

    def claim_next(
        self,
        *,
        worker_id: str,
        global_capacity: int,
        lease_seconds: int = 60,
        scan_limit: int = 100,
        adapter_allowlist: Collection[str] | None = None,
        now: datetime | None = None,
    ) -> SchedulerClaim | None:
        """Claim one lane-eligible job while scanning past blocked queue heads."""

        owner = _required_text(worker_id, name="worker_id", maximum=255)
        capacity = _bounded_int(
            global_capacity,
            name="global_capacity",
            minimum=1,
            maximum=_MAX_BATCH,
        )
        lease = _bounded_int(
            lease_seconds,
            name="lease_seconds",
            minimum=1,
            maximum=_MAX_LEASE_SECONDS,
        )
        candidate_limit = _bounded_int(
            scan_limit,
            name="scan_limit",
            minimum=1,
            maximum=_MAX_BATCH,
        )
        allowed_adapters = _adapter_allowlist(adapter_allowlist)
        current = _aware_utc(now)
        self._serialize_sqlite_writer()
        self._reclaim_expired_sync(now=current)
        self._requeue_due_sync(now=current)
        self.session.expire_all()

        active_count = int(
            self.session.scalar(
                select(func.count(Job.id)).where(
                    Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                    Job.status.in_(_ACTIVE_WORK_STATUSES),
                )
            )
            or 0
        )
        if active_count >= capacity:
            return None

        candidate_statement = select(Job)
        if allowed_adapters is not None:
            if not allowed_adapters:
                return None
            candidate_statement = candidate_statement.join(Account, Account.id == Job.account_id).where(
                Account.adapter.in_(allowed_adapters)
            )
        candidates = self.session.scalars(
            candidate_statement.where(
                Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                Job.status == "queued",
                Job.available_at <= current,
                Job.attempts < Job.max_attempts,
            )
            .order_by(
                Job.priority.desc(),
                Job.available_at,
                Job.scheduled_for,
                Job.created_at,
                Job.id,
            )
            .limit(candidate_limit)
        ).all()
        for candidate in candidates:
            if candidate.subscription_id is None:
                self._terminalize_invalid_candidate(candidate, now=current)
                continue
            try:
                SubscriptionRepository(self.session).require_active(candidate.subscription_id, lock=True)
            except (NotFoundError, SubscriptionRemovalError):
                continue
            try:
                _parse_payload(candidate)
                lanes = self._job_lanes(candidate, now=current)
                if (
                    self._reconcile_ownership_conflict_attachment(candidate, now=current, locked_lanes=lanes)
                    is not None
                ):
                    continue
            except (ValueError, SchedulerRepositoryError):
                self._terminalize_invalid_candidate(candidate, now=current)
                continue
            if not all(self._lane_allows(lane, job_id=candidate.id, now=current) for lane in lanes):
                continue

            lease_token = new_uuid()
            claimed = self.session.scalar(
                update(Job)
                .where(
                    Job.id == candidate.id,
                    Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                    Job.status == "queued",
                    Job.available_at <= current,
                    Job.attempts < Job.max_attempts,
                    ~self._has_ownership_conflict_attachment(),
                )
                .values(
                    status="claimed",
                    lease_owner=owner,
                    lease_token=lease_token,
                    lease_expires_at=_safe_add(current, lease, name="lease_seconds"),
                    attempts=Job.attempts + 1,
                    started_at=None,
                    finished_at=None,
                    updated_at=current,
                )
                .returning(Job)
                .execution_options(synchronize_session="fetch", populate_existing=True)
            )
            if claimed is None:
                continue
            for lane in lanes:
                self._reserve_lane(lane, job_id=claimed.id, now=current)
            return _claim(claimed)
        return None

    def _reject_failure_for_succeeded_run(self, job: Job, run_id: str | None) -> None:
        effective_run_id = run_id or job.run_id
        if effective_run_id is None:
            return
        run = self.session.get(SyncRun, effective_run_id)
        if run is not None and run.status == "succeeded":
            raise SchedulerRepositoryError("a succeeded attached run cannot be finalized as a scheduler failure")

    def _lease_failure(self, job_id: str, *, worker_id: str) -> SchedulerLeaseLostError:
        current = self.session.get(Job, job_id)
        if current is None:
            raise NotFoundError(f"job not found: {job_id}")
        if current.job_type != SYNC_SUBSCRIPTION_JOB_TYPE:
            raise SchedulerRepositoryError("scheduler operation rejected a foreign job type")
        return SchedulerLeaseLostError(f"worker {worker_id!r} no longer owns scheduler job {job_id}")

    def _owned_update(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        allowed_statuses: tuple[str, ...],
        values: Mapping[str, Any],
        now: datetime,
    ) -> Job:
        updated = self.session.scalar(
            update(Job)
            .where(
                Job.id == job_id,
                Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                Job.lease_owner == worker_id,
                Job.lease_token == lease_token,
                Job.status.in_(allowed_statuses),
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at > now,
                exists(
                    select(Subscription.id).where(
                        Subscription.id == Job.subscription_id, Subscription.deleted_at.is_(None)
                    )
                ),
            )
            .values(**dict(values))
            .returning(Job)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        if updated is None:
            raise self._lease_failure(job_id, worker_id=worker_id)
        return updated

    def start(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        now: datetime | None = None,
    ) -> SchedulerClaim:
        normalized_id = _required_text(job_id, name="job_id", maximum=36)
        owner = _required_text(worker_id, name="worker_id", maximum=255)
        token = _required_text(lease_token, name="lease_token", maximum=36)
        current = _aware_utc(now)
        self._serialize_sqlite_writer()
        self._get_sync_job(normalized_id)
        started = self._owned_update(
            normalized_id,
            worker_id=owner,
            lease_token=token,
            allowed_statuses=("claimed",),
            values={"status": "running", "started_at": current, "updated_at": current},
            now=current,
        )
        return _claim(started)

    def heartbeat(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> SchedulerClaim:
        normalized_id = _required_text(job_id, name="job_id", maximum=36)
        owner = _required_text(worker_id, name="worker_id", maximum=255)
        token = _required_text(lease_token, name="lease_token", maximum=36)
        lease = _bounded_int(
            lease_seconds,
            name="lease_seconds",
            minimum=1,
            maximum=_MAX_LEASE_SECONDS,
        )
        current = _aware_utc(now)
        self._serialize_sqlite_writer()
        self._get_sync_job(normalized_id)
        renewed = self._owned_update(
            normalized_id,
            worker_id=owner,
            lease_token=token,
            allowed_statuses=("running",),
            values={
                "lease_expires_at": _safe_add(current, lease, name="lease_seconds"),
                "updated_at": current,
            },
            now=current,
        )
        return _claim(renewed)

    def assert_owned(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        now: datetime | None = None,
    ) -> SchedulerClaim:
        """Fence a handler write in its transaction without extending the lease.

        The exact no-op update obtains SQLite's writer slot before the caller's
        application mutation.  A concurrent cancel/reclaim therefore wins
        either before this guard or after the guarded transaction commits, and
        an old token can never authorize a later write.
        """

        normalized_id = _required_text(job_id, name="job_id", maximum=36)
        owner = _required_text(worker_id, name="worker_id", maximum=255)
        token = _required_text(lease_token, name="lease_token", maximum=36)
        current = _aware_utc(now)
        guarded = self._owned_update(
            normalized_id,
            worker_id=owner,
            lease_token=token,
            allowed_statuses=("running",),
            values={"updated_at": Job.updated_at},
            now=current,
        )
        return _claim(guarded)

    def attach_run(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        run_id: str,
        expected_current_run_id: str | None,
        now: datetime | None = None,
    ) -> SchedulerClaim:
        """Attach one subscription-owned SyncRun behind the exact active lease.

        ``assert_owned`` obtains the writer slot and row lock before either the
        current attachment or candidate run is inspected.  The explicit
        expected attachment prevents an attempt from replacing a successor's
        run after an ABA reclaim.
        """

        normalized_id = _required_text(job_id, name="job_id", maximum=36)
        owner = _required_text(worker_id, name="worker_id", maximum=255)
        token = _required_text(lease_token, name="lease_token", maximum=36)
        normalized_run_id = _required_text(run_id, name="run_id", maximum=36)
        expected_run_id = _optional_identifier(expected_current_run_id, name="expected_current_run_id")
        current = _aware_utc(now)
        self.assert_owned(
            normalized_id,
            worker_id=owner,
            lease_token=token,
            now=current,
        )
        job = self._get_sync_job(normalized_id)
        if job.run_id != expected_run_id:
            raise SchedulerLeaseLostError("scheduler run attachment changed")
        run = self.session.get(SyncRun, normalized_run_id)
        if run is None or run.subscription_id != job.subscription_id:
            raise SchedulerRepositoryError("scheduler run attachment scope is invalid")
        if job.run_id is not None and job.run_id != normalized_run_id:
            previous = self.session.get(SyncRun, job.run_id)
            if (
                previous is None
                or previous.subscription_id != job.subscription_id
                or previous.status not in TERMINAL_RUN_STATUSES
            ):
                raise SchedulerRepositoryError("scheduler current run is not terminal")
        already_attached = self.session.scalar(
            select(
                exists().where(
                    Job.id != normalized_id,
                    Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                    Job.run_id == normalized_run_id,
                )
            )
        )
        if already_attached:
            raise SchedulerRepositoryError("scheduler run is already attached to another job")
        job.run_id = normalized_run_id
        job.updated_at = current
        self.session.flush()
        return _claim(job)

    def _update_lane_values(
        self,
        lane: SchedulerLane,
        *,
        values: Mapping[str, Any],
        now: datetime,
    ) -> SchedulerLane:
        updated = self.session.scalar(
            update(SchedulerLane)
            .where(SchedulerLane.id == lane.id, SchedulerLane.revision == lane.revision)
            .values(
                **dict(values),
                revision=SchedulerLane.revision + 1,
                updated_at=now,
            )
            .returning(SchedulerLane)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        if updated is None:
            raise StaleLaneError("scheduler lane result revision changed")
        return updated

    def _apply_lane_success(
        self, job: Job, *, now: datetime, locked_lanes: tuple[SchedulerLane, ...] | None = None
    ) -> None:
        for lane in self._job_lanes(job, now=now) if locked_lanes is None else locked_lanes:
            if lane.circuit_state == "closed":
                self._update_lane_values(
                    lane,
                    values={
                        "consecutive_failures": 0,
                        "circuit_open_until": None,
                        "half_open_job_id": None,
                    },
                    now=now,
                )
            elif lane.circuit_state == "half_open" and lane.half_open_job_id == job.id:
                self._update_lane_values(
                    lane,
                    values={
                        "consecutive_failures": 0,
                        "circuit_state": "closed",
                        "circuit_open_until": None,
                        "half_open_job_id": None,
                    },
                    now=now,
                )

    def _apply_lane_failure(
        self,
        job: Job,
        *,
        now: datetime,
        affects_circuit: bool,
        locked_lanes: tuple[SchedulerLane, ...] | None = None,
    ) -> None:
        if not isinstance(affects_circuit, bool):
            raise ValueError("affects_circuit must be boolean")
        for lane in self._job_lanes(job, now=now) if locked_lanes is None else locked_lanes:
            if not affects_circuit:
                if (
                    job.status in TERMINAL_JOB_STATUSES
                    and lane.circuit_state == "half_open"
                    and lane.half_open_job_id == job.id
                ):
                    self._update_lane_values(
                        lane,
                        values={
                            "circuit_state": "closed",
                            "circuit_open_until": None,
                            "half_open_job_id": None,
                        },
                        now=now,
                    )
                continue

            if lane.circuit_state == "half_open" and lane.half_open_job_id not in {None, job.id}:
                continue
            failures = min(2_147_483_647, lane.consecutive_failures + 1)
            should_open = lane.circuit_state in {"open", "half_open"} or failures >= lane.failure_threshold
            if should_open:
                open_until = _safe_add(now, lane.cooldown_seconds, name="cooldown_seconds")
                if lane.circuit_state == "open" and lane.circuit_open_until is not None:
                    open_until = max(open_until, _aware_utc(lane.circuit_open_until))
                self._update_lane_values(
                    lane,
                    values={
                        "consecutive_failures": failures,
                        "circuit_state": "open",
                        "circuit_open_until": open_until,
                        "half_open_job_id": None,
                    },
                    now=now,
                )
            else:
                self._update_lane_values(
                    lane,
                    values={
                        "consecutive_failures": failures,
                        "circuit_state": "closed",
                        "circuit_open_until": None,
                        "half_open_job_id": None,
                    },
                    now=now,
                )

    def _release_lane_probe(
        self,
        job: Job,
        *,
        now: datetime,
        reset_all: bool,
        locked_lanes: tuple[SchedulerLane, ...] | None = None,
    ) -> None:
        for lane in self._job_lanes(job, now=now) if locked_lanes is None else locked_lanes:
            if reset_all or (lane.circuit_state == "half_open" and lane.half_open_job_id == job.id):
                self._update_lane_values(
                    lane,
                    values={
                        "consecutive_failures": 0 if reset_all else lane.consecutive_failures,
                        "circuit_state": "closed",
                        "circuit_open_until": None,
                        "half_open_job_id": None,
                    },
                    now=now,
                )

    def _finalize_subscription(
        self,
        job: Job,
        *,
        now: datetime,
        outcome: Literal["success", "failure", "cancelled"],
        require_payload: bool = True,
    ) -> None:
        payload: _Payload | None
        try:
            payload = _parse_payload(job)
        except ValueError:
            if require_payload:
                raise SchedulerRepositoryError("terminal scheduler job payload is invalid") from None
            payload = None
        subscription_id = payload.subscription_id if payload is not None else job.subscription_id
        if subscription_id is None:
            return
        subscription = self.session.get(Subscription, subscription_id)
        if subscription is None:
            return
        try:
            interval = _bounded_int(
                subscription.interval_seconds,
                name="interval_seconds",
                minimum=60,
                maximum=2_147_483_647,
            )
            next_run_at = now + timedelta(seconds=interval)
        except (OverflowError, ValueError) as exc:
            if require_payload:
                raise SchedulerRepositoryError("subscription fixed delay is invalid") from exc
            self.session.execute(
                update(Subscription)
                .where(Subscription.id == subscription_id)
                .values(
                    enabled=False,
                    next_run_at=None,
                    last_run_at=now,
                    consecutive_failures=Subscription.consecutive_failures + 1,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            return
        values: dict[str, Any] = {
            "next_run_at": next_run_at,
            "last_run_at": now,
            "updated_at": now,
        }
        if outcome == "success":
            values.update(last_success_at=now, consecutive_failures=0)
        elif outcome == "failure":
            values["consecutive_failures"] = Subscription.consecutive_failures + 1
        conditions: list[Any] = [Subscription.id == subscription_id]
        if payload is not None:
            conditions.append(Subscription.schedule_revision == payload.schedule_revision + 1)
        self.session.execute(
            update(Subscription).where(*conditions).values(**values).execution_options(synchronize_session=False)
        )

    def succeed(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        run_id: str | UUID | None = None,
        now: datetime | None = None,
    ) -> SchedulerJobSummary:
        normalized_id = _required_text(job_id, name="job_id", maximum=36)
        owner = _required_text(worker_id, name="worker_id", maximum=255)
        token = _required_text(lease_token, name="lease_token", maximum=36)
        normalized_run_id = _optional_identifier(run_id, name="run_id")
        current = _aware_utc(now)
        self._serialize_sqlite_writer()
        observed = self._locked_sync_job(normalized_id)
        normalized_run_id = self._validated_result_run_id(observed, normalized_run_id)
        reconciled = self._reconcile_ownership_conflict_attachment(
            observed, now=current, owned_by=(owner, token), allowed_statuses=("running",)
        )
        if reconciled is not None:
            return _summary(reconciled)
        values: dict[str, Any] = {
            "status": "succeeded",
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "finished_at": current,
            "updated_at": current,
            "last_error_code": None,
            "last_error_message": None,
        }
        if normalized_run_id is not None:
            values["run_id"] = normalized_run_id
        completed = self._owned_update(
            normalized_id,
            worker_id=owner,
            lease_token=token,
            allowed_statuses=("running",),
            values=values,
            now=current,
        )
        self._apply_lane_success(completed, now=current)
        self._finalize_subscription(completed, now=current, outcome="success")
        self._enqueue_pipeline_for_succeeded_run(completed, now=current)
        return _summary(completed)

    def complete_success(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        run_id: str | UUID | None = None,
        now: datetime | None = None,
    ) -> SchedulerJobSummary:
        return self.succeed(
            job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            run_id=run_id,
            now=now,
        )

    def fail(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        error_code: str,
        retry_at: datetime | None = None,
        affects_circuit: bool | None = None,
        run_id: str | UUID | None = None,
        now: datetime | None = None,
    ) -> SchedulerJobSummary:
        normalized_id = _required_text(job_id, name="job_id", maximum=36)
        owner = _required_text(worker_id, name="worker_id", maximum=255)
        token = _required_text(lease_token, name="lease_token", maximum=36)
        code = _required_text(error_code, name="error_code", maximum=128)
        if _FIXED_CODE.fullmatch(code) is None:
            raise ValueError("error_code is outside the closed scheduler vocabulary")
        classification = classify_failure(code)
        if classification.code != code or classification.disposition in {
            FailureDisposition.WAITING_AUTH,
            FailureDisposition.WAITING_USER,
        }:
            raise ValueError("fail requires a closed retry or terminal error code")
        if affects_circuit is not None and affects_circuit is not classification.affects_circuit:
            raise ValueError("affects_circuit must match the closed failure classification")
        circuit_effect = classification.affects_circuit
        normalized_retry_at = _aware_utc(retry_at) if retry_at is not None else None
        if normalized_retry_at is not None and classification.disposition is not FailureDisposition.RETRY:
            raise ValueError("retry_at is valid only for a retryable failure")
        normalized_run_id = _optional_identifier(run_id, name="run_id")
        current = _aware_utc(now)
        self._serialize_sqlite_writer()
        observed = self._locked_sync_job(normalized_id)
        normalized_run_id = self._validated_result_run_id(
            observed, normalized_run_id, explicit_ownership_conflict=code == "content_ownership_conflict"
        )
        reconciled = self._reconcile_ownership_conflict_attachment(observed, now=current, owned_by=(owner, token))
        if reconciled is not None:
            return _summary(reconciled)
        self._reject_failure_for_succeeded_run(observed, normalized_run_id)
        attempts_remain = observed.attempts < observed.max_attempts
        retryable = classification.disposition is FailureDisposition.RETRY and attempts_remain
        status = (
            "retry_wait"
            if retryable and normalized_retry_at is not None and normalized_retry_at > current
            else "failed_retryable"
            if retryable
            else "failed_terminal"
        )
        values: dict[str, Any] = {
            "status": status,
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "available_at": normalized_retry_at or current if retryable else observed.available_at,
            "finished_at": None if retryable else current,
            "updated_at": current,
            "last_error_code": code,
            "last_error_message": None,
        }
        if normalized_run_id is not None:
            values["run_id"] = normalized_run_id
        failed = self._owned_update(
            normalized_id,
            worker_id=owner,
            lease_token=token,
            allowed_statuses=("claimed", "running"),
            values=values,
            now=current,
        )
        self._apply_lane_failure(failed, now=current, affects_circuit=circuit_effect)
        if failed.status == "failed_terminal":
            self._finalize_subscription(failed, now=current, outcome="failure")
        return _summary(failed)

    def complete_failure(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        error_code: str,
        retry_at: datetime | None = None,
        affects_circuit: bool | None = None,
        run_id: str | UUID | None = None,
        now: datetime | None = None,
    ) -> SchedulerJobSummary:
        return self.fail(
            job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            error_code=error_code,
            retry_at=retry_at,
            affects_circuit=affects_circuit,
            run_id=run_id,
            now=now,
        )

    def wait(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        status: Literal["waiting_auth", "waiting_user"],
        error_code: str,
        affects_circuit: bool | None = None,
        run_id: str | UUID | None = None,
        now: datetime | None = None,
    ) -> SchedulerJobSummary:
        if status not in _WAITING_STATUSES:
            raise ValueError("status must be waiting_auth or waiting_user")
        normalized_id = _required_text(job_id, name="job_id", maximum=36)
        owner = _required_text(worker_id, name="worker_id", maximum=255)
        token = _required_text(lease_token, name="lease_token", maximum=36)
        code = _required_text(error_code, name="error_code", maximum=128)
        classification = classify_failure(code)
        expected_disposition = (
            FailureDisposition.WAITING_AUTH if status == "waiting_auth" else FailureDisposition.WAITING_USER
        )
        if classification.code != code or classification.disposition is not expected_disposition:
            raise ValueError("waiting status and error_code classification do not match")
        if affects_circuit is not None and affects_circuit is not classification.affects_circuit:
            raise ValueError("affects_circuit must match the closed failure classification")
        normalized_run_id = _optional_identifier(run_id, name="run_id")
        current = _aware_utc(now)
        self._serialize_sqlite_writer()
        observed = self._locked_sync_job(normalized_id)
        normalized_run_id = self._validated_result_run_id(observed, normalized_run_id)
        reconciled = self._reconcile_ownership_conflict_attachment(observed, now=current, owned_by=(owner, token))
        if reconciled is not None:
            return _summary(reconciled)
        self._reject_failure_for_succeeded_run(observed, normalized_run_id)
        values: dict[str, Any] = {
            "status": status,
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "finished_at": None,
            "updated_at": current,
            "last_error_code": code,
            "last_error_message": None,
        }
        if normalized_run_id is not None:
            values["run_id"] = normalized_run_id
        waiting = self._owned_update(
            normalized_id,
            worker_id=owner,
            lease_token=token,
            allowed_statuses=("claimed", "running"),
            values=values,
            now=current,
        )
        self._apply_lane_failure(
            waiting,
            now=current,
            affects_circuit=classification.affects_circuit,
        )
        return _summary(waiting)

    def resume(self, job_id: str, *, now: datetime | None = None) -> SchedulerJobSummary:
        normalized_id = _required_text(job_id, name="job_id", maximum=36)
        current = _aware_utc(now)
        self._serialize_sqlite_writer()
        observed = self._get_sync_job(normalized_id)
        if observed.subscription_id is not None:
            SubscriptionRepository(self.session).require_active(observed.subscription_id, lock=True)
        observed = self._locked_sync_job(normalized_id)
        if observed.status in _WAITING_STATUSES:
            reconciled = self._reconcile_ownership_conflict_attachment(observed, now=current)
            if reconciled is not None:
                return _summary(reconciled)
        resumed = self.session.scalar(
            update(Job)
            .where(
                Job.id == normalized_id,
                Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                Job.status.in_(_WAITING_STATUSES),
            )
            .values(
                status="queued",
                attempts=case(
                    (Job.attempts >= Job.max_attempts, Job.max_attempts - 1),
                    else_=Job.attempts,
                ),
                available_at=current,
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                finished_at=None,
                updated_at=current,
                last_error_code=None,
                last_error_message=None,
            )
            .returning(Job)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        if resumed is None:
            raise SchedulerRepositoryError("only an explicit waiting scheduler job can be resumed")
        self._release_lane_probe(resumed, now=current, reset_all=False)
        return _summary(resumed)

    def resume_waiting(self, job_id: str, *, now: datetime | None = None) -> SchedulerJobSummary:
        return self.resume(job_id, now=now)

    def cancel_unstarted_for_removal(
        self, job_id: str, *, now: datetime, locked_lanes: tuple[SchedulerLane, ...]
    ) -> SchedulerJobSummary:
        """Retire a non-running cycle without rewriting its historical Run."""

        self._serialize_sqlite_writer()
        observed = self._locked_sync_job(job_id)
        if any(
            lane.platform != observed.platform
            or lane.scope_type not in {"platform", "account"}
            or (lane.scope_type == "account" and lane.account_id != observed.account_id)
            for lane in locked_lanes
        ):
            raise SchedulerRepositoryError("removal lane scope is invalid")
        if observed.status not in {"queued", "retry_wait", "waiting_auth", "waiting_user", "failed_retryable"}:
            raise SubscriptionRemovalError("subscription_busy")
        reconciled = self._reconcile_succeeded_attachment(
            observed, now=now, expired_only=False, locked_lanes=locked_lanes
        )
        if reconciled is not None:
            return _summary(reconciled)
        reconciled = self._reconcile_ownership_conflict_attachment(observed, now=now, locked_lanes=locked_lanes)
        if reconciled is not None:
            return _summary(reconciled)
        observed.status = "cancelled"
        observed.lease_owner = observed.lease_token = None
        observed.lease_expires_at = None
        observed.finished_at = observed.updated_at = now
        observed.last_error_code = observed.last_error_message = None
        self.session.flush()
        self._release_lane_probe(observed, now=now, reset_all=False, locked_lanes=locked_lanes)
        return _summary(observed)

    def cancel(self, job_id: str, *, now: datetime | None = None) -> SchedulerJobSummary:
        normalized_id = _required_text(job_id, name="job_id", maximum=36)
        current = _aware_utc(now)
        self._serialize_sqlite_writer()
        observed = self._locked_sync_job(normalized_id)
        if observed.status in TERMINAL_JOB_STATUSES:
            return _summary(observed)
        reconciled = self._reconcile_succeeded_attachment(observed, now=current, expired_only=False)
        if reconciled is not None:
            return _summary(reconciled)
        reconciled = self._reconcile_ownership_conflict_attachment(observed, now=current)
        if reconciled is not None:
            return _summary(reconciled)
        cancelled = self.session.scalar(
            update(Job)
            .where(
                Job.id == normalized_id,
                Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                Job.status.not_in(tuple(TERMINAL_JOB_STATUSES)),
            )
            .values(
                status="cancelled",
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                finished_at=current,
                updated_at=current,
                last_error_code=None,
                last_error_message=None,
            )
            .returning(Job)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        if cancelled is None:
            return _summary(self._current_sync_job(normalized_id))
        self._cancel_attached_run(
            cancelled,
            now=current,
            error_code="scheduler_cancelled",
        )
        self._release_lane_probe(cancelled, now=current, reset_all=False)
        self._finalize_subscription(
            cancelled,
            now=current,
            outcome="cancelled",
            require_payload=False,
        )
        return _summary(cancelled)

    def get_subscription_schedule(self, subscription_id: str) -> SubscriptionSchedule:
        normalized_id = _required_text(
            subscription_id,
            name="subscription_id",
            maximum=36,
        )
        subscription = self.session.get(Subscription, normalized_id)
        if subscription is None:
            raise NotFoundError(f"subscription not found: {normalized_id}")
        return _subscription_schedule(subscription)

    def _set_subscription_schedule(
        self,
        subscription_id: str,
        *,
        values: Mapping[str, Any],
        now: datetime,
    ) -> SubscriptionSchedule:
        normalized_id = _required_text(
            subscription_id,
            name="subscription_id",
            maximum=36,
        )
        self._serialize_sqlite_writer()
        SubscriptionRepository(self.session).require_active(normalized_id, lock=True)
        updated = self.session.scalar(
            update(Subscription)
            .where(Subscription.id == normalized_id)
            .values(**dict(values), updated_at=now)
            .returning(Subscription)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        )
        if updated is None:
            raise NotFoundError(f"subscription not found: {normalized_id}")
        return _subscription_schedule(updated)

    def pause_subscription(
        self,
        subscription_id: str,
        *,
        now: datetime | None = None,
    ) -> SubscriptionSchedule:
        return self._set_subscription_schedule(
            subscription_id,
            values={"enabled": False},
            now=_aware_utc(now),
        )

    def resume_subscription(
        self,
        subscription_id: str,
        *,
        now: datetime | None = None,
    ) -> SubscriptionSchedule:
        return self._set_subscription_schedule(
            subscription_id,
            values={"enabled": True},
            now=_aware_utc(now),
        )

    def run_now(
        self,
        subscription_id: str,
        *,
        now: datetime | None = None,
    ) -> SubscriptionSchedule:
        """Make an enabled subscription immediately due without resuming it."""

        return self._set_subscription_schedule(
            subscription_id,
            values={"next_run_at": None},
            now=_aware_utc(now),
        )


__all__ = [
    "SCHEDULE_PAYLOAD_SCHEMA_VERSION",
    "SYNC_SUBSCRIPTION_JOB_TYPE",
    "LanePolicy",
    "LaneScope",
    "LaneSnapshot",
    "MaterializedCycle",
    "SchedulerClaim",
    "SchedulerJobSummary",
    "SchedulerLeaseLostError",
    "SchedulerRepository",
    "SchedulerRepositoryError",
    "StaleLaneError",
    "SubscriptionSchedule",
    "validate_sync_subscription_job",
]
