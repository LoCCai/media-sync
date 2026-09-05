"""Explicit, paused-only Bili scope changes preserving both feed checkpoints."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from sqlalchemy import select

from media_sync.infrastructure.db import Database, SubscriptionRepository
from media_sync.infrastructure.db.models import ACTIVE_SYNC_JOB_STATUSES, Job, SyncRun
from media_sync.integrations.mediacrawler.subscription_policy import from_subscription_policy


def change_bilibili_scope(
    database: Database,
    subscription_id: UUID,
    *,
    scope: str,
    max_items: int,
    expected_schedule_revision: int,
) -> dict[str, object]:
    """Reject active work; never clear cursors, start jobs or mutate files."""
    if (
        type(expected_schedule_revision) is not int
        or expected_schedule_revision < 0
        or scope not in {"uploads", "dynamics", "both"}
    ):
        raise ValueError("bili_scope_options_invalid")
    with database.session() as session:
        if session.get_bind().dialect.name == "sqlite":
            session.connection(execution_options={"media_sync_sqlite_begin_immediate": True})
        subscription = SubscriptionRepository(session).require_active(str(subscription_id), lock=True)
        if subscription.account.platform != "bili" or subscription.account.adapter != "mediacrawler":
            raise ValueError("bili_scope_options_invalid")
        if subscription.enabled or subscription.schedule_revision != expected_schedule_revision:
            raise ValueError("bili_scope_requires_paused_current_revision")
        if (
            session.scalar(
                select(Job.id)
                .where(
                    Job.subscription_id == subscription.id,
                    Job.status.in_(ACTIVE_SYNC_JOB_STATUSES),
                )
                .limit(1)
            )
            is not None
            or session.scalar(
                select(SyncRun.id)
                .where(
                    SyncRun.subscription_id == subscription.id,
                    SyncRun.status.in_({"queued", "claimed", "awaiting_auth", "running", "ingesting"}),
                )
                .limit(1)
            )
            is not None
        ):
            raise ValueError("bili_scope_requires_idle_subscription")
        policy = replace(from_subscription_policy(subscription.policy), bili_scope=scope)
        policy.validate_bili_max_items(max_items)
        payload = {"mediacrawler": policy.to_payload()}
        changed = subscription.policy != payload or subscription.max_items != max_items
        if changed:
            subscription.policy = payload
            subscription.max_items = max_items
            subscription.schedule_revision += 1
            session.flush()
        return {
            "id": subscription.id,
            "bili_scope": scope,
            "max_items": max_items,
            "schedule_revision": subscription.schedule_revision,
            "changed": changed,
            "checkpoint_preserved": True,
            "enabled": False,
        }
