"""Paused-only, revision-fenced edits of a closed subscription policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.models import (
    ACTIVE_OPERATION_STATES,
    TERMINAL_JOB_STATUSES,
    TERMINAL_RUN_STATUSES,
    Job,
    Operation,
    OperationSubject,
    Subscription,
    SyncRun,
)
from media_sync.infrastructure.db.repositories import NotFoundError, SubscriptionRemovalError, SubscriptionRepository
from media_sync.integrations.mediacrawler.subscription_policy import (
    BILI_SUBSCRIPTION_POLICY_SCHEMA_VERSION,
    SUBSCRIPTION_POLICY_SCHEMA_VERSION,
    MediaCrawlerSubscriptionPolicy,
    MediaCrawlerSubscriptionPolicyError,
    from_subscription_policy,
)

MAX_SUBSCRIPTION_INTERVAL_SECONDS = 2_147_483_647
MAX_SUBSCRIPTION_SCHEDULE_REVISION = 2_147_483_647

SUBSCRIPTION_POLICY_UPDATE_ERROR_CODES = frozenset(
    {
        "subscription_policy_busy",
        "subscription_policy_invalid",
        "subscription_policy_not_found",
        "subscription_policy_options_invalid",
        "subscription_policy_removed",
        "subscription_policy_requires_paused",
        "subscription_policy_revision_conflict",
        "subscription_policy_revision_exhausted",
        "subscription_policy_unsupported_adapter",
    }
)


class SubscriptionPolicyUpdateError(RuntimeError):
    """One fixed, redaction-safe policy mutation rejection."""

    def __init__(self, code: str) -> None:
        if code not in SUBSCRIPTION_POLICY_UPDATE_ERROR_CODES:
            raise ValueError("unknown subscription policy update error code")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class SubscriptionPolicyUpdate:
    """The complete editable policy set plus optimistic ownership."""

    interval_seconds: int
    max_items: int
    request_delay_seconds: float
    headless: bool
    expected_schedule_revision: int
    bili_scope: str | None = None


@dataclass(frozen=True, slots=True)
class SubscriptionPolicyUpdateResult:
    """Allowlisted result that never carries a secret reference."""

    id: str
    platform: str
    interval_seconds: int
    max_items: int
    schedule_revision: int
    checkpoint_revision: int
    next_run_at: datetime | None
    policy: MediaCrawlerSubscriptionPolicy
    changed: bool

    def to_payload(self) -> dict[str, object]:
        summary: dict[str, object] = {
            "adapter": "mediacrawler",
            "schema_version": (
                BILI_SUBSCRIPTION_POLICY_SCHEMA_VERSION
                if self.policy.bili_scope is not None
                else SUBSCRIPTION_POLICY_SCHEMA_VERSION
            ),
            "allow_full_history": self.policy.allow_full_history,
            "request_delay_seconds": self.policy.request_delay_seconds,
            "headless": self.policy.headless,
            "creator_reference_configured": self.policy.creator_secret_ref is not None,
        }
        if self.policy.bili_scope is not None:
            summary["bili_scope"] = self.policy.bili_scope
        return {
            "id": self.id,
            "platform": self.platform,
            "status": "paused",
            "enabled": False,
            "interval_seconds": self.interval_seconds,
            "max_items": self.max_items,
            "schedule_revision": self.schedule_revision,
            "checkpoint_revision": self.checkpoint_revision,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at is not None else None,
            "policy_summary": summary,
            "changed": self.changed,
            "checkpoint_preserved": True,
            "media_preserved": True,
        }


def _validate_update(update: SubscriptionPolicyUpdate) -> None:
    if (
        type(update.interval_seconds) is not int
        or not 60 <= update.interval_seconds <= MAX_SUBSCRIPTION_INTERVAL_SECONDS
        or type(update.max_items) is not int
        or not 1 <= update.max_items <= 1_000
        or type(update.headless) is not bool
        or type(update.expected_schedule_revision) is not int
        or not 0 <= update.expected_schedule_revision <= MAX_SUBSCRIPTION_SCHEDULE_REVISION
        or (
            update.bili_scope is not None
            and (type(update.bili_scope) is not str or update.bili_scope not in {"uploads", "dynamics", "both"})
        )
    ):
        raise SubscriptionPolicyUpdateError("subscription_policy_options_invalid")


def _job_scope(subscription_id: str) -> Any:
    run_ids = select(SyncRun.id).where(SyncRun.subscription_id == subscription_id)
    return or_(Job.subscription_id == subscription_id, Job.run_id.in_(run_ids))


def _active_operation_scope(subscription_id: str) -> Any:
    return or_(
        and_(Operation.target_type == "subscription", Operation.target_id == subscription_id),
        exists(
            select(OperationSubject.operation_id).where(
                OperationSubject.operation_id == Operation.id,
                OperationSubject.subject_type == "subscription",
                OperationSubject.subject_id == subscription_id,
            )
        ),
    )


def _require_idle(session: Session, subscription_id: str) -> None:
    active_job = session.scalar(
        select(Job.id)
        .where(_job_scope(subscription_id), Job.status.not_in(TERMINAL_JOB_STATUSES))
        .order_by(Job.id)
        .limit(1)
        .with_for_update(nowait=True)
    )
    active_run = session.scalar(
        select(SyncRun.id)
        .where(
            SyncRun.subscription_id == subscription_id,
            SyncRun.status.not_in(TERMINAL_RUN_STATUSES),
        )
        .order_by(SyncRun.id)
        .limit(1)
        .with_for_update(nowait=True)
    )
    active_operation = session.scalar(
        select(Operation.id)
        .where(
            Operation.state.in_(ACTIVE_OPERATION_STATES),
            _active_operation_scope(subscription_id),
        )
        .order_by(Operation.id)
        .limit(1)
        .with_for_update(of=Operation, nowait=True)
    )
    if active_job is not None or active_run is not None or active_operation is not None:
        raise SubscriptionPolicyUpdateError("subscription_policy_busy")


def _target_policy(
    subscription: Subscription,
    current: MediaCrawlerSubscriptionPolicy,
    update: SubscriptionPolicyUpdate,
) -> MediaCrawlerSubscriptionPolicy:
    platform = subscription.account.platform
    if platform == "bili":
        target_scope = current.bili_scope if update.bili_scope is None else update.bili_scope
    else:
        if update.bili_scope is not None or current.bili_scope is not None:
            raise SubscriptionPolicyUpdateError("subscription_policy_options_invalid")
        target_scope = None
    try:
        target = replace(
            current,
            request_delay_seconds=update.request_delay_seconds,
            headless=update.headless,
            bili_scope=target_scope,
        )
        if platform == "bili":
            target.validate_bili_max_items(update.max_items)
    except MediaCrawlerSubscriptionPolicyError:
        raise SubscriptionPolicyUpdateError("subscription_policy_options_invalid") from None
    return target


def update_subscription_policy(
    database: Database,
    subscription_id: UUID,
    update: SubscriptionPolicyUpdate,
) -> SubscriptionPolicyUpdateResult:
    """Apply one all-or-nothing policy edit without touching work or files."""

    if not isinstance(database, Database) or not isinstance(subscription_id, UUID):
        raise SubscriptionPolicyUpdateError("subscription_policy_options_invalid")
    if not isinstance(update, SubscriptionPolicyUpdate):
        raise SubscriptionPolicyUpdateError("subscription_policy_options_invalid")
    _validate_update(update)
    try:
        with database.session() as session:
            if session.get_bind().dialect.name == "sqlite":
                session.connection(execution_options={"media_sync_sqlite_begin_immediate": True})
            try:
                subscription = SubscriptionRepository(session).require_active(str(subscription_id), lock=True)
            except NotFoundError:
                raise SubscriptionPolicyUpdateError("subscription_policy_not_found") from None
            except SubscriptionRemovalError:
                raise SubscriptionPolicyUpdateError("subscription_policy_removed") from None
            if subscription.account.adapter != "mediacrawler":
                raise SubscriptionPolicyUpdateError("subscription_policy_unsupported_adapter")
            if subscription.enabled:
                raise SubscriptionPolicyUpdateError("subscription_policy_requires_paused")
            if subscription.schedule_revision != update.expected_schedule_revision:
                raise SubscriptionPolicyUpdateError("subscription_policy_revision_conflict")
            _require_idle(session, subscription.id)
            try:
                current = from_subscription_policy(subscription.policy)
            except MediaCrawlerSubscriptionPolicyError:
                raise SubscriptionPolicyUpdateError("subscription_policy_invalid") from None
            target = _target_policy(subscription, current, update)
            target_payload = {"mediacrawler": target.to_payload()}
            changed = (
                subscription.interval_seconds != update.interval_seconds
                or subscription.max_items != update.max_items
                or subscription.policy != target_payload
            )
            if changed:
                if subscription.schedule_revision >= MAX_SUBSCRIPTION_SCHEDULE_REVISION:
                    raise SubscriptionPolicyUpdateError("subscription_policy_revision_exhausted")
                subscription.interval_seconds = update.interval_seconds
                subscription.max_items = update.max_items
                subscription.policy = target_payload
                subscription.schedule_revision += 1
                session.flush()
            return SubscriptionPolicyUpdateResult(
                id=subscription.id,
                platform=subscription.account.platform,
                interval_seconds=subscription.interval_seconds,
                max_items=subscription.max_items,
                schedule_revision=subscription.schedule_revision,
                checkpoint_revision=subscription.checkpoint_revision,
                next_run_at=subscription.next_run_at,
                policy=target,
                changed=changed,
            )
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == "55P03" or getattr(error.orig, "pgcode", None) == "55P03":
            raise SubscriptionPolicyUpdateError("subscription_policy_busy") from None
        raise


__all__ = [
    "MAX_SUBSCRIPTION_INTERVAL_SECONDS",
    "MAX_SUBSCRIPTION_SCHEDULE_REVISION",
    "SUBSCRIPTION_POLICY_UPDATE_ERROR_CODES",
    "SubscriptionPolicyUpdate",
    "SubscriptionPolicyUpdateError",
    "SubscriptionPolicyUpdateResult",
    "update_subscription_policy",
]
