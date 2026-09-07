"""Delivery-qualified Bili backfill, reconciliation and incremental state."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from media_sync.infrastructure.db.models import (
    ASSET_STATUSES,
    BILI_DELIVERY_PHASES,
    Asset,
    AssetRefreshSource,
    BiliSubscriptionProgress,
    Content,
    Job,
    Subscription,
    SubscriptionScanProgress,
    SyncRun,
    SyncRunContent,
)
from media_sync.infrastructure.db.repositories import RepositoryError
from media_sync.integrations.mediacrawler.bilibili_multifeed import BiliMultiFeedState, state_from_cursor
from media_sync.integrations.mediacrawler.bilibili_scan import BiliLane
from media_sync.integrations.mediacrawler.subscription_policy import from_subscription_policy

from .pipeline_receipt import PipelineDeliveryReceipt

BILI_DELIVERY_SCHEMA_VERSION = 1
_MAX_COUNTER = 9_007_199_254_740_991
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FIXED_CODE = re.compile(r"[a-z][a-z0-9_]{0,127}\Z")
_SYNC_PAYLOAD_KEYS = frozenset({"schema_version", "subscription_id", "schedule_revision", "retry_policy"})
_PIPELINE_PAYLOAD_KEYS = frozenset({"schema_version", "sync_job_id", "subscription_id", "run_id", "result"})
_PIPELINE_SOURCE_KEYS = _PIPELINE_PAYLOAD_KEYS - {"result"}
_STABLE_HEAD_REASONS = frozenset({"head_boundary", "source_end"})
_PENDING_HEAD_REASONS = frozenset({"item_limit", "list_limit", "restarted"})


@dataclass(frozen=True, slots=True)
class BiliDeliveryBinding:
    account_id: str
    auth_revision: int
    author_id: str
    author_fingerprint_sha256: str
    scope: str
    policy_fingerprint_sha256: str
    upstream_sha: str


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Bili delivery timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _canonical_policy(policy: Mapping[str, object], max_items: int) -> str:
    if type(max_items) is not int or not 1 <= max_items <= 1_000:
        raise ValueError("Bili uploads max_items must be between 1 and 1000")
    try:
        encoded = json.dumps(
            {"schema_version": 1, "max_items": max_items, "policy": dict(policy)},
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise ValueError("Bili subscription policy is not canonical JSON") from None
    return hashlib.sha256(encoded).hexdigest()


def bili_policy_fingerprint(policy: Mapping[str, object], max_items: int) -> str:
    """Return a non-secret generation identity for delivery-relevant policy."""

    if not isinstance(policy, Mapping):
        raise ValueError("Bili subscription policy must be a mapping")
    parsed = from_subscription_policy(policy)
    parsed.validate_bili_max_items(max_items)
    if parsed.effective_bili_scope != "uploads":
        raise ValueError("Bili delivery baseline supports exact uploads scope only")
    return _canonical_policy(policy, max_items)


def binding_for_subscription(subscription: Subscription, upstream_sha: str | None) -> BiliDeliveryBinding | None:
    """Resolve an exact public-safe binding, or decline a non-target subscription."""

    if (
        upstream_sha is None
        or _SHA1.fullmatch(upstream_sha) is None
        or subscription.account.adapter != "mediacrawler"
        or subscription.account.platform != "bili"
        or subscription.author.platform != "bili"
    ):
        return None
    try:
        policy_fingerprint = bili_policy_fingerprint(subscription.policy, subscription.max_items)
        UUID(subscription.id)
        UUID(subscription.account_id)
        UUID(subscription.author_id)
    except (AttributeError, TypeError, ValueError):
        return None
    auth_revision = subscription.account.auth_revision
    if type(auth_revision) is not int or not 0 <= auth_revision <= _MAX_COUNTER:
        return None
    return BiliDeliveryBinding(
        account_id=subscription.account_id,
        auth_revision=auth_revision,
        author_id=subscription.author_id,
        author_fingerprint_sha256=hashlib.sha256(subscription.author.remote_id.encode("utf-8")).hexdigest(),
        scope="uploads",
        policy_fingerprint_sha256=policy_fingerprint,
        upstream_sha=upstream_sha,
    )


def _row_binding(row: BiliSubscriptionProgress) -> BiliDeliveryBinding:
    return BiliDeliveryBinding(
        row.account_id,
        row.auth_revision,
        row.author_id,
        row.author_fingerprint_sha256,
        row.scope,
        row.policy_fingerprint_sha256,
        row.upstream_sha,
    )


def _head_cursor(
    subscription: Subscription,
    binding: BiliDeliveryBinding,
    *,
    preserve_history: bool,
) -> dict[str, str] | None:
    if not preserve_history:
        return None
    raw = subscription.cursor
    if not isinstance(raw, Mapping) or set(raw) != {"value"} or type(raw.get("value")) is not str:
        return None
    try:
        parsed = state_from_cursor(raw["value"])
        parsed.require_binding(
            account_id=UUID(binding.account_id),
            author_fingerprint_sha256=binding.author_fingerprint_sha256,
            upstream_sha=binding.upstream_sha,
        )
        uploads = parsed.uploads if isinstance(parsed, BiliMultiFeedState) else parsed
        uploads = replace(uploads, next_lane="head", head=BiliLane(), head_candidate=None, last_unit=None)
        if isinstance(parsed, BiliMultiFeedState):
            return {"value": replace(parsed, uploads=uploads, scope="uploads", next_feed="uploads").to_cursor()}
        return {"value": uploads.to_cursor()}
    except (AttributeError, TypeError, ValueError):
        return None


def _incremental_cursor(subscription: Subscription, binding: BiliDeliveryBinding) -> dict[str, str]:
    raw = subscription.cursor
    if not isinstance(raw, Mapping) or set(raw) != {"value"} or type(raw.get("value")) is not str:
        raise RepositoryError("bili_delivery_cursor_invalid")
    try:
        state = state_from_cursor(raw["value"])
        state.require_binding(
            account_id=UUID(binding.account_id),
            author_fingerprint_sha256=binding.author_fingerprint_sha256,
            upstream_sha=binding.upstream_sha,
        )
        if isinstance(state, BiliMultiFeedState):
            state = replace(
                state,
                uploads=replace(state.uploads, next_lane="head"),
                scope="uploads",
                next_feed="uploads",
            )
        else:
            state = replace(state, next_lane="head")
        return {"value": state.to_cursor()}
    except (AttributeError, TypeError, ValueError):
        raise RepositoryError("bili_delivery_cursor_invalid") from None


def _clear_evidence(row: BiliSubscriptionProgress, *, phase: str, now: datetime) -> None:
    row.phase = phase
    row.generation_id = str(uuid4())
    row.batch_count = 0
    row.content_observation_count = 0
    row.backfill_batch_count = 0
    row.reconciliation_batch_count = 0
    row.incremental_batch_count = 0
    row.partial_batch_count = 0
    row.failed_content_count = 0
    row.last_lane = None
    row.last_stop_reason = None
    row.last_sync_job_id = None
    row.last_run_id = None
    row.last_pipeline_job_id = None
    row.last_delivery_at = None
    row.source_end_observed_at = None
    row.source_end_run_id = None
    row.source_end_boundary_sha256 = None
    row.reconciled_at = None
    row.reconciliation_run_id = None
    row.baseline_snapshot_at = None
    row.next_eligible_at = None
    row.blocked_code = None
    row.updated_at = now


class BiliDeliveryProgressRepository:
    """Own the exact transition from delivered pipeline receipts to scan phase."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure_for_materialization(
        self,
        subscription: Subscription,
        *,
        upstream_sha: str | None,
        schedule_revision: int,
        now: datetime,
        resume_blocked: bool,
    ) -> BiliSubscriptionProgress | None:
        current = _aware(now)
        binding = binding_for_subscription(subscription, upstream_sha)
        if binding is None:
            return None
        row = self.session.get(BiliSubscriptionProgress, subscription.id)
        if row is None:
            row = BiliSubscriptionProgress(
                subscription_id=subscription.id,
                phase="backfill",
                generation_id=str(uuid4()),
                account_id=binding.account_id,
                auth_revision=binding.auth_revision,
                author_id=binding.author_id,
                author_fingerprint_sha256=binding.author_fingerprint_sha256,
                scope=binding.scope,
                policy_fingerprint_sha256=binding.policy_fingerprint_sha256,
                upstream_sha=binding.upstream_sha,
                checkpoint_revision=subscription.checkpoint_revision,
                schedule_revision=schedule_revision,
                next_eligible_at=subscription.next_run_at,
                created_at=current,
                updated_at=current,
            )
            self.session.add(row)
            self.session.flush()
            return row

        if _row_binding(row) == binding:
            if row.phase == "blocked" and resume_blocked:
                # A coordinator failure does not invalidate already-delivered
                # batches or exact source-end evidence. Resume the same
                # generation, while requiring reconciliation before a new
                # baseline can be claimed.
                row.phase = "reconciling" if row.source_end_observed_at is not None else "backfill"
                row.blocked_code = None
                row.next_eligible_at = subscription.next_run_at
                row.checkpoint_revision = subscription.checkpoint_revision
                row.schedule_revision = schedule_revision
                row.updated_at = current
                self.session.flush()
            return row

        same_source_identity = (
            row.account_id == binding.account_id
            and row.author_id == binding.author_id
            and row.author_fingerprint_sha256 == binding.author_fingerprint_sha256
            and row.scope == binding.scope
            and row.upstream_sha == binding.upstream_sha
        )
        preserve_history = same_source_identity and (
            row.baseline_snapshot_at is not None or row.source_end_observed_at is not None
        )
        replacement_cursor = _head_cursor(subscription, binding, preserve_history=preserve_history)
        preserve_history = preserve_history and replacement_cursor is not None
        current_cursor = dict(subscription.cursor) if isinstance(subscription.cursor, Mapping) else None
        if replacement_cursor != current_cursor:
            subscription.cursor = replacement_cursor
            subscription.checkpoint_revision += 1
        _clear_evidence(row, phase="reconciling" if preserve_history else "backfill", now=current)
        row.account_id = binding.account_id
        row.auth_revision = binding.auth_revision
        row.author_id = binding.author_id
        row.author_fingerprint_sha256 = binding.author_fingerprint_sha256
        row.scope = binding.scope
        row.policy_fingerprint_sha256 = binding.policy_fingerprint_sha256
        row.upstream_sha = binding.upstream_sha
        row.checkpoint_revision = subscription.checkpoint_revision
        row.schedule_revision = schedule_revision
        self.session.flush()
        return row

    @staticmethod
    def _source_schedule_revision(source: Job, subscription_id: str) -> int:
        payload = source.payload
        if (
            source.job_type != "sync.subscription"
            or source.status != "succeeded"
            or source.subscription_id != subscription_id
            or not isinstance(payload, Mapping)
            or set(payload) != _SYNC_PAYLOAD_KEYS
            or payload.get("schema_version") != 1
            or payload.get("subscription_id") != subscription_id
            or type(payload.get("schedule_revision")) is not int
            or not 0 <= payload["schedule_revision"] <= _MAX_COUNTER
        ):
            raise RepositoryError("bili_delivery_source_invalid")
        return int(payload["schedule_revision"])

    def publish_success(
        self,
        pipeline_job: Job,
        receipt: PipelineDeliveryReceipt,
        *,
        upstream_sha: str | None,
        continuation_delay_seconds: int,
        now: datetime,
    ) -> BiliSubscriptionProgress | None:
        """Advance exactly once, in the same transaction as pipeline success."""

        if receipt.schema_version != 2:
            return None
        current = _aware(now)
        payload = pipeline_job.payload
        if (
            pipeline_job.job_type != "pipeline.subscription"
            or pipeline_job.status != "succeeded"
            or not isinstance(payload, Mapping)
            or set(payload) != _PIPELINE_PAYLOAD_KEYS
            or payload.get("schema_version") != 2
            or payload.get("result") != receipt.to_mapping()
        ):
            raise RepositoryError("bili_delivery_pipeline_invalid")
        subscription_id = receipt.subscription_id
        if (
            pipeline_job.subscription_id != subscription_id
            or payload.get("subscription_id") != subscription_id
            or payload.get("run_id") != receipt.source_run_id
        ):
            raise RepositoryError("bili_delivery_pipeline_invalid")
        subscription = self.session.get(Subscription, subscription_id)
        row = self.session.get(BiliSubscriptionProgress, subscription_id)
        if subscription is None or row is None:
            return None
        if row.last_pipeline_job_id == pipeline_job.id:
            return row
        binding = binding_for_subscription(subscription, upstream_sha)
        source = self.session.get(Job, payload.get("sync_job_id"))
        run = self.session.get(SyncRun, receipt.source_run_id)
        if source is None or run is None:
            raise RepositoryError("bili_delivery_source_invalid")
        schedule_revision = self._source_schedule_revision(source, subscription_id)
        manifest = run.manifest
        manifest_binding_matches = (
            isinstance(manifest, Mapping)
            and manifest.get("upstream_sha") == upstream_sha
            and manifest.get("account_revision") == (None if binding is None else binding.auth_revision)
            and manifest.get("policy_fingerprint_sha256")
            == (None if binding is None else binding.policy_fingerprint_sha256)
        )
        if binding is None or _row_binding(row) != binding or not manifest_binding_matches:
            if binding is not None:
                self.ensure_for_materialization(
                    subscription,
                    upstream_sha=upstream_sha,
                    schedule_revision=subscription.schedule_revision,
                    now=current,
                    resume_blocked=True,
                )
                if subscription.enabled and subscription.deleted_at is None:
                    delay = min(
                        continuation_delay_seconds or subscription.interval_seconds,
                        subscription.interval_seconds,
                    )
                    subscription.next_run_at = current + timedelta(seconds=delay)
                    row.next_eligible_at = subscription.next_run_at
            return row
        scan = self.session.get(SubscriptionScanProgress, (subscription_id, "uploads"))
        observations = tuple(
            self.session.scalars(
                select(SyncRunContent)
                .where(SyncRunContent.run_id == run.id, SyncRunContent.subscription_id == subscription_id)
                .order_by(SyncRunContent.position)
            ).all()
        )
        if (
            source.run_id != run.id
            or pipeline_job.run_id != run.id
            or run.subscription_id != subscription_id
            or run.status != "succeeded"
            or run.checkpoint_revision_before != row.checkpoint_revision
            or run.checkpoint_revision_after != row.checkpoint_revision + 1
            or subscription.checkpoint_revision != run.checkpoint_revision_after
            or subscription.cursor != run.cursor_after
            or scan is None
            or scan.checkpoint_revision != run.checkpoint_revision_after
            or scan.last_lane not in {"head", "history"}
            or scan.last_stop_reason
            not in {
                "item_limit",
                "list_limit",
                "head_boundary",
                "source_end",
                "restarted",
            }
            or receipt.observed_content_count != len(observations)
            or receipt.delivered_content_count + receipt.failed_content_count != len(observations)
            or schedule_revision < row.schedule_revision
        ):
            raise RepositoryError("bili_delivery_evidence_invalid")

        phase_before = row.phase
        if phase_before not in BILI_DELIVERY_PHASES or phase_before == "blocked":
            raise RepositoryError("bili_delivery_phase_invalid")
        row.batch_count += 1
        row.content_observation_count += len(observations)
        if phase_before == "backfill":
            row.backfill_batch_count += 1
        elif phase_before == "reconciling":
            row.reconciliation_batch_count += 1
        else:
            row.incremental_batch_count += 1
        if receipt.partial:
            row.partial_batch_count += 1

        lane, reason = scan.last_lane, scan.last_stop_reason
        if lane == "history" and reason == "source_end":
            cursor_value = run.cursor_after.get("value") if isinstance(run.cursor_after, Mapping) else None
            if type(cursor_value) is not str:
                raise RepositoryError("bili_delivery_evidence_invalid")
            row.phase = "reconciling"
            row.source_end_observed_at = current
            row.source_end_run_id = run.id
            row.source_end_boundary_sha256 = hashlib.sha256(cursor_value.encode("utf-8")).hexdigest()
            row.reconciled_at = None
            row.reconciliation_run_id = None
            row.baseline_snapshot_at = None
        elif phase_before == "reconciling" and lane == "head" and reason in _STABLE_HEAD_REASONS:
            row.phase = "incremental"
            row.reconciled_at = current
            row.reconciliation_run_id = run.id
            row.baseline_snapshot_at = current
        elif phase_before == "incremental" and lane != "head":
            row.phase = "reconciling"
            row.reconciled_at = None
            row.reconciliation_run_id = None
            row.baseline_snapshot_at = None

        row.last_lane = lane
        row.last_stop_reason = reason
        row.last_sync_job_id = source.id
        row.last_run_id = run.id
        row.last_pipeline_job_id = pipeline_job.id
        row.last_delivery_at = current
        row.schedule_revision = schedule_revision
        row.blocked_code = None
        row.failed_content_count = self._failed_content_count(subscription)

        checkpoint_revision = run.checkpoint_revision_after
        reset_reconciliation_head = lane == "history" and reason == "source_end"
        if reset_reconciliation_head:
            next_cursor = _head_cursor(subscription, binding, preserve_history=True)
            if next_cursor is None:
                raise RepositoryError("bili_delivery_cursor_invalid")
        elif row.phase in {"reconciling", "incremental"}:
            # Reconciliation may span several bounded units, but it must never
            # rotate back into history after source-end evidence was sealed.
            next_cursor = _incremental_cursor(subscription, binding)
        else:
            next_cursor = subscription.cursor
        if row.phase in {"reconciling", "incremental"} and next_cursor != subscription.cursor:
            subscription.cursor = next_cursor
            subscription.checkpoint_revision += 1
            checkpoint_revision = subscription.checkpoint_revision
        row.checkpoint_revision = checkpoint_revision

        pending = row.phase in {"backfill", "reconciling"} or (
            row.phase == "incremental" and reason in _PENDING_HEAD_REASONS
        )
        pending = pending or receipt.retryable_failed_content_count > 0
        if subscription.enabled and subscription.deleted_at is None:
            delay = subscription.interval_seconds
            if pending and continuation_delay_seconds:
                delay = min(delay, continuation_delay_seconds)
            subscription.next_run_at = current + timedelta(seconds=delay)
            row.next_eligible_at = subscription.next_run_at
        else:
            row.next_eligible_at = None

        counters = (
            row.checkpoint_revision,
            row.schedule_revision,
            row.batch_count,
            row.content_observation_count,
            row.backfill_batch_count,
            row.reconciliation_batch_count,
            row.incremental_batch_count,
            row.partial_batch_count,
            row.failed_content_count,
        )
        if any(type(value) is not int or not 0 <= value <= _MAX_COUNTER for value in counters):
            raise RepositoryError("bili_delivery_counter_invalid")
        row.updated_at = current
        subscription.updated_at = current
        self.session.flush()
        return row

    def publish_terminal_failure(
        self,
        pipeline_job: Job,
        *,
        error_code: str,
        upstream_sha: str | None,
        now: datetime,
    ) -> None:
        """Stop automatic continuation after a terminal coordinator failure."""

        if _FIXED_CODE.fullmatch(error_code) is None or pipeline_job.status != "failed_terminal":
            raise RepositoryError("bili_delivery_failure_invalid")
        if pipeline_job.subscription_id is None:
            return
        subscription = self.session.get(Subscription, pipeline_job.subscription_id)
        row = self.session.get(BiliSubscriptionProgress, pipeline_job.subscription_id)
        payload = pipeline_job.payload
        if (
            subscription is None
            or row is None
            or row.phase == "blocked"
            or not isinstance(payload, Mapping)
            or set(payload) != _PIPELINE_SOURCE_KEYS
            or payload.get("schema_version") != 1
            or payload.get("subscription_id") != subscription.id
            or pipeline_job.run_id != payload.get("run_id")
        ):
            return
        binding = binding_for_subscription(subscription, upstream_sha)
        source = self.session.get(Job, payload.get("sync_job_id"))
        run = self.session.get(SyncRun, payload.get("run_id"))
        if binding is None or source is None or run is None or _row_binding(row) != binding:
            return
        try:
            source_schedule_revision = self._source_schedule_revision(source, subscription.id)
        except RepositoryError:
            return
        manifest = run.manifest
        if (
            not isinstance(manifest, Mapping)
            or manifest.get("upstream_sha") != binding.upstream_sha
            or manifest.get("account_revision") != binding.auth_revision
            or manifest.get("policy_fingerprint_sha256") != binding.policy_fingerprint_sha256
            or source.run_id != run.id
            or pipeline_job.subscription_id != subscription.id
            or pipeline_job.account_id != binding.account_id
            or pipeline_job.platform != "bili"
            or run.subscription_id != subscription.id
            or run.status != "succeeded"
            or run.checkpoint_revision_before != row.checkpoint_revision
            or run.checkpoint_revision_after != subscription.checkpoint_revision
            or source_schedule_revision < row.schedule_revision
            or subscription.schedule_revision != source_schedule_revision + 1
        ):
            return
        row.phase = "blocked"
        row.blocked_code = error_code
        row.next_eligible_at = None
        row.reconciled_at = None
        row.reconciliation_run_id = None
        row.baseline_snapshot_at = None
        row.updated_at = _aware(now)
        self.session.flush()

    def _failed_content_count(self, subscription: Subscription) -> int:
        value = self.session.scalar(
            select(func.count(func.distinct(Content.id)))
            .join(Asset, Asset.content_id == Content.id)
            .join(AssetRefreshSource, AssetRefreshSource.asset_id == Asset.id)
            .where(
                Content.author_id == subscription.author_id,
                Content.tombstoned_at.is_(None),
                AssetRefreshSource.subscription_id == subscription.id,
                Asset.status.in_(tuple(ASSET_STATUSES - {"verified", "exported"})),
            )
        )
        return int(value or 0)


def _iso(value: object) -> str | None:
    return value.astimezone(UTC).isoformat() if isinstance(value, datetime) and value.tzinfo is not None else None


def _uuid(value: object) -> bool:
    try:
        return type(value) is str and str(UUID(value)) == value
    except (AttributeError, TypeError, ValueError):
        return False


def bili_delivery_progress_payload(
    subscription: Subscription,
    *,
    upstream_sha: str | None,
) -> dict[str, object] | None:
    """Project only bounded evidence; incompatible rows never claim completion."""

    binding = binding_for_subscription(subscription, upstream_sha)
    if binding is None:
        return None
    row = subscription.bili_delivery_progress
    fallback: dict[str, object] = {
        "schema_version": BILI_DELIVERY_SCHEMA_VERSION,
        "initialized": False,
        "phase": "backfill",
        "baseline_snapshot_complete": False,
        "generation_id": None,
        "batch_count": 0,
        "content_observation_count": 0,
        "backfill_batch_count": 0,
        "reconciliation_batch_count": 0,
        "incremental_batch_count": 0,
        "partial_batch_count": 0,
        "failed_content_count": 0,
        "last_lane": None,
        "last_stop_reason": None,
        "last_delivery_at": None,
        "source_end_observed_at": None,
        "source_end_run_id": None,
        "reconciled_at": None,
        "reconciliation_run_id": None,
        "baseline_snapshot_at": None,
        "next_eligible_at": _iso(subscription.next_run_at),
        "blocked_code": None,
    }
    if row is None or _row_binding(row) != binding:
        return fallback
    counters = (
        row.batch_count,
        row.content_observation_count,
        row.backfill_batch_count,
        row.reconciliation_batch_count,
        row.incremental_batch_count,
        row.partial_batch_count,
        row.failed_content_count,
    )
    valid = (
        row.schema_version == 1
        and row.phase in BILI_DELIVERY_PHASES
        and _uuid(row.generation_id)
        and all(type(value) is int and 0 <= value <= _MAX_COUNTER for value in counters)
        and row.backfill_batch_count + row.reconciliation_batch_count + row.incremental_batch_count == row.batch_count
        and row.partial_batch_count <= row.batch_count
        and (row.phase == "incremental") == (row.baseline_snapshot_at is not None)
        and (row.phase == "blocked") == (row.blocked_code is not None)
    )
    if not valid:
        return fallback
    return {
        **fallback,
        "initialized": True,
        "phase": row.phase,
        "baseline_snapshot_complete": row.phase == "incremental",
        "generation_id": row.generation_id,
        "batch_count": row.batch_count,
        "content_observation_count": row.content_observation_count,
        "backfill_batch_count": row.backfill_batch_count,
        "reconciliation_batch_count": row.reconciliation_batch_count,
        "incremental_batch_count": row.incremental_batch_count,
        "partial_batch_count": row.partial_batch_count,
        "failed_content_count": row.failed_content_count,
        "last_lane": row.last_lane,
        "last_stop_reason": row.last_stop_reason,
        "last_delivery_at": _iso(row.last_delivery_at),
        "source_end_observed_at": _iso(row.source_end_observed_at),
        "source_end_run_id": row.source_end_run_id,
        "reconciled_at": _iso(row.reconciled_at),
        "reconciliation_run_id": row.reconciliation_run_id,
        "baseline_snapshot_at": _iso(row.baseline_snapshot_at),
        "next_eligible_at": _iso(row.next_eligible_at),
        "blocked_code": row.blocked_code,
    }


__all__ = [
    "BILI_DELIVERY_SCHEMA_VERSION",
    "BiliDeliveryBinding",
    "BiliDeliveryProgressRepository",
    "bili_delivery_progress_payload",
    "bili_policy_fingerprint",
    "binding_for_subscription",
]
