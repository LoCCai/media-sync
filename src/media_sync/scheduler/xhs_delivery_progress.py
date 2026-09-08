"""Delivery-qualified XHS creator-note backfill and incremental state."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from media_sync.infrastructure.db.models import (
    XHS_DELIVERY_PHASES,
    Job,
    Subscription,
    SyncRun,
    SyncRunContent,
    XhsSubscriptionProgress,
)
from media_sync.infrastructure.db.repositories import RepositoryError
from media_sync.integrations.mediacrawler.subscription_policy import from_subscription_policy
from media_sync.integrations.mediacrawler.xhs_creator_notes import XhsListingIdentity, XhsScanState

from .pipeline_receipt import PipelineDeliveryReceipt

XHS_DELIVERY_SCHEMA_VERSION = 1
_MAX_COUNTER = 9_007_199_254_740_991
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FIXED_CODE = re.compile(r"[a-z][a-z0-9_]{0,127}\Z")
_SYNC_PAYLOAD_KEYS = frozenset({"schema_version", "subscription_id", "schedule_revision", "retry_policy"})
_PIPELINE_PAYLOAD_KEYS = frozenset({"schema_version", "sync_job_id", "subscription_id", "run_id", "result"})
_PIPELINE_SOURCE_KEYS = _PIPELINE_PAYLOAD_KEYS - {"result"}


@dataclass(frozen=True, slots=True)
class XhsDeliveryBinding:
    account_id: str
    auth_revision: int
    author_id: str
    author_fingerprint_sha256: str
    scope: str
    policy_fingerprint_sha256: str
    upstream_sha: str


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("XHS delivery timestamps must be timezone-aware")
    return value.astimezone(UTC)


def xhs_policy_fingerprint(policy: Mapping[str, object], max_items: int) -> str:
    """Return a non-secret identity for XHS delivery-relevant policy."""

    if not isinstance(policy, Mapping) or type(max_items) is not int or not 1 <= max_items <= 1_000:
        raise ValueError("XHS subscription policy is invalid")
    parsed = from_subscription_policy(policy)
    if parsed.creator_secret_ref is None or parsed.bili_scope is not None:
        raise ValueError("XHS creator delivery requires one creator authority reference")
    try:
        encoded = json.dumps(
            {"schema_version": 1, "max_items": max_items, "policy": dict(policy)},
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise ValueError("XHS subscription policy is not canonical JSON") from None
    return hashlib.sha256(encoded).hexdigest()


def binding_for_xhs_subscription(
    subscription: Subscription,
    upstream_sha: str | None,
) -> XhsDeliveryBinding | None:
    if (
        upstream_sha is None
        or _SHA1.fullmatch(upstream_sha) is None
        or subscription.account.adapter != "mediacrawler"
        or subscription.account.platform != "xhs"
        or subscription.author.platform != "xhs"
    ):
        return None
    try:
        policy_fingerprint = xhs_policy_fingerprint(subscription.policy, subscription.max_items)
        UUID(subscription.id)
        UUID(subscription.account_id)
        UUID(subscription.author_id)
    except (AttributeError, TypeError, ValueError):
        return None
    auth_revision = subscription.account.auth_revision
    if type(auth_revision) is not int or not 0 <= auth_revision <= _MAX_COUNTER:
        return None
    return XhsDeliveryBinding(
        subscription.account_id,
        auth_revision,
        subscription.author_id,
        hashlib.sha256(subscription.author.remote_id.encode("utf-8")).hexdigest(),
        "notes",
        policy_fingerprint,
        upstream_sha,
    )


def _row_binding(row: XhsSubscriptionProgress) -> XhsDeliveryBinding:
    return XhsDeliveryBinding(
        row.account_id,
        row.auth_revision,
        row.author_id,
        row.author_fingerprint_sha256,
        row.scope,
        row.policy_fingerprint_sha256,
        row.upstream_sha,
    )


def _clear_evidence(row: XhsSubscriptionProgress, *, now: datetime) -> None:
    row.phase = "backfill"
    row.generation_id = str(uuid4())
    row.creator_fingerprint_sha256 = None
    row.batch_count = 0
    row.note_observation_count = 0
    row.cursor_step_count = 0
    row.backfill_batch_count = 0
    row.reconciliation_batch_count = 0
    row.incremental_batch_count = 0
    row.partial_batch_count = 0
    row.failed_note_count = 0
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


def _boundary_sha(identities: tuple[XhsListingIdentity, ...]) -> str:
    encoded = json.dumps(
        [item.as_mapping() for item in identities],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


class XhsDeliveryProgressRepository:
    """Advance XHS state only from a closed pipeline receipt."""

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
    ) -> XhsSubscriptionProgress | None:
        current = _aware(now)
        binding = binding_for_xhs_subscription(subscription, upstream_sha)
        if binding is None:
            return None
        row = self.session.get(XhsSubscriptionProgress, subscription.id)
        if row is None:
            row = XhsSubscriptionProgress(
                subscription_id=subscription.id,
                phase="backfill",
                generation_id=str(uuid4()),
                account_id=binding.account_id,
                auth_revision=binding.auth_revision,
                author_id=binding.author_id,
                author_fingerprint_sha256=binding.author_fingerprint_sha256,
                creator_fingerprint_sha256=None,
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
                row.phase = (
                    "incremental"
                    if row.baseline_snapshot_at is not None
                    else "reconciling"
                    if row.source_end_observed_at is not None
                    else "backfill"
                )
                row.blocked_code = None
                row.next_eligible_at = subscription.next_run_at
                row.checkpoint_revision = subscription.checkpoint_revision
                row.schedule_revision = schedule_revision
                row.updated_at = current
                self.session.flush()
            return row

        subscription.cursor = None
        subscription.checkpoint_revision += 1
        _clear_evidence(row, now=current)
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

    def ensure_creator_binding(
        self,
        subscription: Subscription,
        *,
        upstream_sha: str,
        creator_fingerprint_sha256: str,
        now: datetime,
    ) -> bool:
        """Reset an old/generic cursor before a child can consume new authority."""

        current = _aware(now)
        binding = binding_for_xhs_subscription(subscription, upstream_sha)
        if binding is None or _SHA256.fullmatch(creator_fingerprint_sha256) is None:
            raise RepositoryError("xhs_delivery_binding_invalid")
        row = self.session.get(XhsSubscriptionProgress, subscription.id)
        if row is None:
            raise RepositoryError("xhs_delivery_progress_missing")
        reset = row.creator_fingerprint_sha256 not in {None, creator_fingerprint_sha256}
        cursor_value = subscription.cursor.get("value") if isinstance(subscription.cursor, Mapping) else None
        if subscription.cursor is not None:
            try:
                if type(cursor_value) is not str:
                    raise ValueError("cursor is not text")
                state = XhsScanState.from_cursor(cursor_value)
                state.require_binding(
                    account_id=UUID(binding.account_id),
                    author_fingerprint_sha256=binding.author_fingerprint_sha256,
                    creator_fingerprint_sha256=creator_fingerprint_sha256,
                    upstream_sha=binding.upstream_sha,
                )
            except (AttributeError, TypeError, ValueError):
                reset = True
        if reset:
            subscription.cursor = None
            subscription.checkpoint_revision += 1
            _clear_evidence(row, now=current)
            row.checkpoint_revision = subscription.checkpoint_revision
        row.creator_fingerprint_sha256 = creator_fingerprint_sha256
        row.updated_at = current
        self.session.flush()
        return reset

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
            raise RepositoryError("xhs_delivery_source_invalid")
        return int(payload["schedule_revision"])

    def publish_success(
        self,
        pipeline_job: Job,
        receipt: PipelineDeliveryReceipt,
        *,
        upstream_sha: str | None,
        continuation_delay_seconds: int,
        now: datetime,
    ) -> XhsSubscriptionProgress | None:
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
            raise RepositoryError("xhs_delivery_pipeline_invalid")
        subscription_id = receipt.subscription_id
        if (
            pipeline_job.subscription_id != subscription_id
            or payload.get("subscription_id") != subscription_id
            or payload.get("run_id") != receipt.source_run_id
        ):
            raise RepositoryError("xhs_delivery_pipeline_invalid")
        subscription = self.session.get(Subscription, subscription_id)
        row = self.session.get(XhsSubscriptionProgress, subscription_id)
        if subscription is None or row is None:
            return None
        if row.last_pipeline_job_id == pipeline_job.id:
            return row
        binding = binding_for_xhs_subscription(subscription, upstream_sha)
        source = self.session.get(Job, payload.get("sync_job_id"))
        run = self.session.get(SyncRun, receipt.source_run_id)
        if binding is None or source is None or run is None or _row_binding(row) != binding:
            return row
        schedule_revision = self._source_schedule_revision(source, subscription_id)
        manifest = run.manifest
        creator_fingerprint = manifest.get("creator_fingerprint_sha256") if isinstance(manifest, Mapping) else None
        if type(creator_fingerprint) is not str or _SHA256.fullmatch(creator_fingerprint) is None:
            raise RepositoryError("xhs_delivery_source_invalid")
        if row.creator_fingerprint_sha256 is None and row.batch_count == 0:
            row.creator_fingerprint_sha256 = creator_fingerprint
        if (
            row.creator_fingerprint_sha256 != creator_fingerprint
            or not isinstance(manifest, Mapping)
            or manifest.get("upstream_sha") != upstream_sha
            or manifest.get("account_revision") != binding.auth_revision
            or manifest.get("policy_fingerprint_sha256") != binding.policy_fingerprint_sha256
            or source.run_id != run.id
            or pipeline_job.run_id != run.id
            or pipeline_job.account_id != binding.account_id
            or pipeline_job.platform != "xhs"
            or run.subscription_id != subscription_id
            or run.status != "succeeded"
            or run.checkpoint_revision_before != row.checkpoint_revision
            or run.checkpoint_revision_after != row.checkpoint_revision + 1
            or subscription.checkpoint_revision != run.checkpoint_revision_after
            or subscription.cursor != run.cursor_after
            or receipt.observed_content_count != receipt.delivered_content_count + receipt.failed_content_count
            or schedule_revision < row.schedule_revision
        ):
            raise RepositoryError("xhs_delivery_evidence_invalid")
        observations = tuple(
            self.session.scalars(
                select(SyncRunContent)
                .where(
                    SyncRunContent.run_id == run.id,
                    SyncRunContent.subscription_id == subscription_id,
                )
                .order_by(SyncRunContent.position)
            ).all()
        )
        before_value = run.cursor_before.get("value") if isinstance(run.cursor_before, Mapping) else None
        after_value = run.cursor_after.get("value") if isinstance(run.cursor_after, Mapping) else None
        try:
            if before_value is not None and type(before_value) is not str:
                raise ValueError("input cursor is not text")
            if type(after_value) is not str:
                raise ValueError("output cursor is not text")
            before_state = XhsScanState.for_cursor(
                before_value,
                account_id=UUID(binding.account_id),
                author_fingerprint_sha256=binding.author_fingerprint_sha256,
                creator_fingerprint_sha256=creator_fingerprint,
                upstream_sha=binding.upstream_sha,
            )
            after_state = XhsScanState.from_cursor(after_value)
            after_state.require_binding(
                account_id=UUID(binding.account_id),
                author_fingerprint_sha256=binding.author_fingerprint_sha256,
                creator_fingerprint_sha256=creator_fingerprint,
                upstream_sha=binding.upstream_sha,
            )
            summary = after_state.last_unit
        except (AttributeError, TypeError, ValueError):
            raise RepositoryError("xhs_delivery_cursor_invalid") from None
        if (
            summary is None
            or before_state.lane != summary.lane
            or summary.stored_count != len(observations)
            or receipt.observed_content_count != len(observations)
        ):
            raise RepositoryError("xhs_delivery_evidence_invalid")

        phase_before = row.phase
        if phase_before not in XHS_DELIVERY_PHASES or phase_before == "blocked":
            raise RepositoryError("xhs_delivery_phase_invalid")
        row.batch_count += 1
        row.note_observation_count += summary.stored_count
        if summary.page_complete:
            row.cursor_step_count += 1
        if phase_before == "backfill":
            row.backfill_batch_count += 1
        elif phase_before == "reconciling":
            row.reconciliation_batch_count += 1
        else:
            row.incremental_batch_count += 1
        if receipt.partial or summary.failed_count:
            row.partial_batch_count += 1
        row.failed_note_count = (
            summary.failed_count + receipt.failed_content_count + receipt.failed_retry_backlog_content_count
        )

        reason = summary.stop_reason
        checkpoint_revision = run.checkpoint_revision_after
        if reason in {"access_restricted", "empty_page_stalled"}:
            row.phase = "blocked"
            row.blocked_code = "xhs_access_restricted" if reason == "access_restricted" else "xhs_empty_page_stalled"
        elif phase_before == "backfill" and reason == "has_more_false" and summary.page_complete:
            if after_state.head_boundary is None:
                raise RepositoryError("xhs_delivery_boundary_invalid")
            row.phase = "reconciling"
            row.source_end_observed_at = current
            row.source_end_run_id = run.id
            row.source_end_boundary_sha256 = _boundary_sha(after_state.head_boundary)
            row.reconciled_at = None
            row.reconciliation_run_id = None
            row.baseline_snapshot_at = None
            subscription.cursor = {"value": after_state.for_head().to_cursor()}
            subscription.checkpoint_revision += 1
            checkpoint_revision = subscription.checkpoint_revision
        elif phase_before == "reconciling" and summary.lane == "head" and summary.page_complete:
            if before_state.head_boundary == after_state.head_boundary:
                row.phase = "incremental"
                row.reconciled_at = current
                row.reconciliation_run_id = run.id
                row.baseline_snapshot_at = current
            else:
                row.phase = "reconciling"
                row.reconciled_at = None
                row.reconciliation_run_id = None
                row.baseline_snapshot_at = None
            subscription.cursor = {"value": after_state.for_head().to_cursor()}
            if subscription.cursor != run.cursor_after:
                subscription.checkpoint_revision += 1
                checkpoint_revision = subscription.checkpoint_revision
        elif phase_before == "incremental" and summary.lane == "head" and summary.page_complete:
            subscription.cursor = {"value": after_state.for_head().to_cursor()}
            if subscription.cursor != run.cursor_after:
                subscription.checkpoint_revision += 1
                checkpoint_revision = subscription.checkpoint_revision

        row.last_stop_reason = reason
        row.last_sync_job_id = source.id
        row.last_run_id = run.id
        row.last_pipeline_job_id = pipeline_job.id
        row.last_delivery_at = current
        row.schedule_revision = schedule_revision
        row.checkpoint_revision = checkpoint_revision

        pending = row.phase in {"backfill", "reconciling"} or after_state.witness is not None
        pending = pending or receipt.retryable_failed_content_count > 0
        if subscription.enabled and subscription.deleted_at is None:
            delay = subscription.interval_seconds
            if row.phase != "blocked" and pending and continuation_delay_seconds:
                delay = min(delay, continuation_delay_seconds)
            subscription.next_run_at = current + timedelta(seconds=delay)
            row.next_eligible_at = subscription.next_run_at
        else:
            row.next_eligible_at = None
        counters = (
            row.checkpoint_revision,
            row.schedule_revision,
            row.batch_count,
            row.note_observation_count,
            row.cursor_step_count,
            row.backfill_batch_count,
            row.reconciliation_batch_count,
            row.incremental_batch_count,
            row.partial_batch_count,
            row.failed_note_count,
        )
        if any(type(value) is not int or not 0 <= value <= _MAX_COUNTER for value in counters):
            raise RepositoryError("xhs_delivery_counter_invalid")
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
        if _FIXED_CODE.fullmatch(error_code) is None or pipeline_job.status != "failed_terminal":
            raise RepositoryError("xhs_delivery_failure_invalid")
        if pipeline_job.subscription_id is None:
            return
        subscription = self.session.get(Subscription, pipeline_job.subscription_id)
        row = self.session.get(XhsSubscriptionProgress, pipeline_job.subscription_id)
        payload = pipeline_job.payload
        if (
            subscription is None
            or row is None
            or not isinstance(payload, Mapping)
            or set(payload) != _PIPELINE_SOURCE_KEYS
            or payload.get("schema_version") != 1
            or payload.get("subscription_id") != subscription.id
            or pipeline_job.run_id != payload.get("run_id")
            or binding_for_xhs_subscription(subscription, upstream_sha) != _row_binding(row)
        ):
            return
        row.phase = "blocked"
        row.blocked_code = error_code
        row.next_eligible_at = None
        row.updated_at = _aware(now)
        self.session.flush()


def _iso(value: object) -> str | None:
    return value.astimezone(UTC).isoformat() if isinstance(value, datetime) and value.tzinfo is not None else None


def xhs_delivery_progress_payload(
    subscription: Subscription,
    *,
    upstream_sha: str | None,
) -> dict[str, object] | None:
    binding = binding_for_xhs_subscription(subscription, upstream_sha)
    if binding is None:
        return None
    fallback: dict[str, object] = {
        "schema_version": XHS_DELIVERY_SCHEMA_VERSION,
        "initialized": False,
        "phase": "backfill",
        "baseline_snapshot_complete": False,
        "generation_id": None,
        "batch_count": 0,
        "note_observation_count": 0,
        "cursor_step_count": 0,
        "backfill_batch_count": 0,
        "reconciliation_batch_count": 0,
        "incremental_batch_count": 0,
        "partial_batch_count": 0,
        "failed_note_count": 0,
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
    row = subscription.xhs_delivery_progress
    if row is None or _row_binding(row) != binding:
        return fallback
    counters = (
        row.batch_count,
        row.note_observation_count,
        row.cursor_step_count,
        row.backfill_batch_count,
        row.reconciliation_batch_count,
        row.incremental_batch_count,
        row.partial_batch_count,
        row.failed_note_count,
    )
    valid = (
        row.schema_version == 1
        and row.phase in XHS_DELIVERY_PHASES
        and row.creator_fingerprint_sha256 is not None
        and _SHA256.fullmatch(row.creator_fingerprint_sha256) is not None
        and all(type(value) is int and 0 <= value <= _MAX_COUNTER for value in counters)
        and row.backfill_batch_count + row.reconciliation_batch_count + row.incremental_batch_count == row.batch_count
        and row.partial_batch_count <= row.batch_count
        and (row.phase != "incremental" or row.baseline_snapshot_at is not None)
        and (row.baseline_snapshot_at is None or row.phase in {"incremental", "blocked"})
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
        "note_observation_count": row.note_observation_count,
        "cursor_step_count": row.cursor_step_count,
        "backfill_batch_count": row.backfill_batch_count,
        "reconciliation_batch_count": row.reconciliation_batch_count,
        "incremental_batch_count": row.incremental_batch_count,
        "partial_batch_count": row.partial_batch_count,
        "failed_note_count": row.failed_note_count,
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
    "XHS_DELIVERY_SCHEMA_VERSION",
    "XhsDeliveryBinding",
    "XhsDeliveryProgressRepository",
    "binding_for_xhs_subscription",
    "xhs_delivery_progress_payload",
    "xhs_policy_fingerprint",
]
