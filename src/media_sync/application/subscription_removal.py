"""Reversible subscription removal without erasing history or archive bytes."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from media_sync.infrastructure.db import Database, SubscriptionRemovalError
from media_sync.infrastructure.db.base import utc_now
from media_sync.infrastructure.db.models import (
    ACTIVE_OPERATION_STATES,
    TERMINAL_JOB_STATUSES,
    Asset,
    Content,
    ExportRecord,
    Job,
    Operation,
    OperationEvent,
    OperationSubject,
    SchedulerLane,
    Subscription,
    SyncRun,
)
from media_sync.scheduler.pipeline import PIPELINE_SUBSCRIPTION_JOB_TYPE
from media_sync.scheduler.repository import SYNC_SUBSCRIPTION_JOB_TYPE, SchedulerRepository

_CANCELLABLE = frozenset({"queued", "retry_wait", "waiting_auth", "waiting_user", "failed_retryable"})
_MANAGED_TYPES = frozenset({SYNC_SUBSCRIPTION_JOB_TYPE, PIPELINE_SUBSCRIPTION_JOB_TYPE})


@dataclass(frozen=True, slots=True)
class SubscriptionRemovalResult:
    id: str
    status: Literal["deleted", "paused"]
    changed: bool
    cancelled_jobs: int = 0

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "status": self.status,
            "changed": self.changed,
            "cancelled_jobs": self.cancelled_jobs,
            "media_preserved": True,
        }


def _identifier(value: str) -> str:
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise SubscriptionRemovalError("subscription_not_found") from None
    return value


def _job_scope(subscription_id: str) -> Any:
    run_ids = select(SyncRun.id).where(SyncRun.subscription_id == subscription_id)
    return or_(Job.subscription_id == subscription_id, Job.run_id.in_(run_ids))


def _related_subject(kind: Any, identifier: Any, subscription: Subscription) -> Any:
    """Correlate durable identities only, never inspect request/exception payloads."""

    contents = select(Content.id).where(Content.author_id == subscription.author_id)
    assets = select(Asset.id).where(Asset.content_id.in_(contents))
    exports = select(ExportRecord.id).where(ExportRecord.content_id.in_(contents))
    return or_(
        and_(kind == "subscription", identifier == subscription.id),
        and_(kind == "author", identifier == subscription.author_id),
        and_(kind == "content", identifier.in_(contents)),
        and_(kind == "asset", identifier.in_(assets)),
        and_(kind == "export_record", identifier.in_(exports)),
        and_(kind == "job", identifier.in_(select(Job.id).where(_job_scope(subscription.id)))),
        and_(
            kind == "sync_run",
            identifier.in_(select(SyncRun.id).where(SyncRun.subscription_id == subscription.id)),
        ),
    )


def _reject_busy(session: Session, subscription: Subscription) -> list[Job]:
    jobs = list(
        session.scalars(
            select(Job)
            .where(_job_scope(subscription.id), Job.status.not_in(TERMINAL_JOB_STATUSES))
            .order_by(Job.id)
            .with_for_update(nowait=True)
        ).all()
    )
    if any(
        job.status in {"claimed", "running"}
        or (
            job.status not in TERMINAL_JOB_STATUSES
            and (
                job.job_type not in _MANAGED_TYPES
                or job.status not in _CANCELLABLE
                or job.lease_owner is not None
                or job.lease_token is not None
                or job.lease_expires_at is not None
            )
        )
        for job in jobs
    ):
        raise SubscriptionRemovalError("subscription_busy")
    related = or_(
        _related_subject(Operation.target_type, Operation.target_id, subscription),
        exists(
            select(OperationSubject.operation_id).where(
                OperationSubject.operation_id == Operation.id,
                _related_subject(OperationSubject.subject_type, OperationSubject.subject_id, subscription),
            )
        ),
        exists(
            select(OperationEvent.operation_id).where(
                OperationEvent.operation_id == Operation.id,
                _related_subject(OperationEvent.subject_type, OperationEvent.subject_id, subscription),
            )
        ),
    )
    active = session.scalar(select(Operation.id).where(Operation.state.in_(ACTIVE_OPERATION_STATES), related).limit(1))
    if active is not None:
        raise SubscriptionRemovalError("subscription_busy")
    return jobs


def _locked_lanes(session: Session, jobs: list[Job]) -> list[SchedulerLane]:
    scopes = [
        and_(
            SchedulerLane.platform == job.platform,
            or_(
                SchedulerLane.scope_type == "platform",
                and_(SchedulerLane.scope_type == "account", SchedulerLane.account_id == job.account_id),
            ),
        )
        for job in jobs
        if job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE
    ]
    if not scopes:
        return []
    return list(
        session.scalars(
            select(SchedulerLane).where(or_(*scopes)).order_by(SchedulerLane.id).with_for_update(nowait=True)
        ).all()
    )


class SubscriptionRemovalService:
    """Own the atomic control transaction; never touch the filesystem."""

    def __init__(self, database: Database, *, clock: Callable[[], datetime] = utc_now) -> None:
        self.database = database
        self.clock = clock

    @contextmanager
    def _transaction(self) -> Iterator[Session]:
        try:
            with self.database.session() as session:
                yield session
        except DBAPIError as error:
            # Map only PostgreSQL lock_not_available, after Database.session
            # has rolled back all Job/lane/reconciliation changes. Never wait
            # on rows owned by maintenance that may itself need our sub lock.
            if getattr(error.orig, "sqlstate", None) == "55P03" or getattr(error.orig, "pgcode", None) == "55P03":
                raise SubscriptionRemovalError("subscription_busy") from None
            raise

    @staticmethod
    def _locked_subscription(session: Session, identifier: str) -> Subscription:
        if session.get_bind().dialect.name == "sqlite":
            session.connection(execution_options={"media_sync_sqlite_begin_immediate": True})
        subscription = session.scalar(select(Subscription).where(Subscription.id == identifier).with_for_update())
        if subscription is None:
            raise SubscriptionRemovalError("subscription_not_found")
        return subscription

    def remove(self, subscription_id: str) -> SubscriptionRemovalResult:
        identifier = _identifier(subscription_id)
        with self._transaction() as session:
            subscription = self._locked_subscription(session, identifier)
            if subscription.deleted_at is not None:
                return SubscriptionRemovalResult(identifier, "deleted", changed=False)
            jobs = _reject_busy(session, subscription)
            lanes = _locked_lanes(session, jobs)
            now = self.clock()
            scheduler = SchedulerRepository(session)
            cancelled_count = 0
            for job in jobs:
                if job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE and job.status in _CANCELLABLE:
                    job_lanes = tuple(
                        lane
                        for lane in lanes
                        if lane.platform == job.platform
                        and (lane.scope_type == "platform" or lane.account_id == job.account_id)
                    )
                    result = scheduler.cancel_unstarted_for_removal(job.id, now=now, locked_lanes=job_lanes)
                    cancelled_count += result.status == "cancelled"
            # Reconciliation of an attached succeeded Run can legitimately
            # create a coordinator. Retire that pending coordinator too.
            pipeline_jobs = session.scalars(
                select(Job)
                .where(
                    _job_scope(identifier), Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE, Job.status.in_(_CANCELLABLE)
                )
                .with_for_update(nowait=True)
            ).all()
            for job in pipeline_jobs:
                job.status = "cancelled"
                job.lease_owner = job.lease_token = None
                job.lease_expires_at = None
                job.finished_at = job.updated_at = now
                job.last_error_code = job.last_error_message = None
                cancelled_count += 1
            subscription.deleted_at = subscription.updated_at = now
            subscription.enabled = False
            session.flush()
            return SubscriptionRemovalResult(identifier, "deleted", changed=True, cancelled_jobs=cancelled_count)

    def restore(self, subscription_id: str) -> SubscriptionRemovalResult:
        identifier = _identifier(subscription_id)
        with self._transaction() as session:
            subscription = self._locked_subscription(session, identifier)
            if subscription.deleted_at is None:
                if subscription.enabled:
                    raise SubscriptionRemovalError("subscription_not_removed")
                return SubscriptionRemovalResult(identifier, "paused", changed=False)
            _reject_busy(session, subscription)
            subscription.deleted_at = None
            subscription.enabled = False
            subscription.updated_at = self.clock()
            session.flush()
            return SubscriptionRemovalResult(identifier, "paused", changed=True)


__all__ = ["SubscriptionRemovalError", "SubscriptionRemovalResult", "SubscriptionRemovalService"]
