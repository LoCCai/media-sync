"""Paced scheduling for proven pending Bili scan context, without network I/O.

An empty lane is ambiguous (initial or finished), not historical completion.
This policy changes only the delay after an exactly bound durable success.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid5

from media_sync.infrastructure.db.models import Job, Subscription, SyncRun
from media_sync.integrations.mediacrawler.bilibili_multifeed import BiliMultiFeedState, state_from_cursor
from media_sync.integrations.mediacrawler.bilibili_scan import BiliScanState
from media_sync.integrations.mediacrawler.bridge import MANIFEST_SCHEMA_VERSION
from media_sync.integrations.mediacrawler.checkout import CheckoutValidationError, load_mediacrawler_lock
from media_sync.integrations.mediacrawler.subscription_policy import from_subscription_policy

from .bili_delivery_progress import bili_policy_fingerprint

DEFAULT_BILI_SCAN_CONTINUATION_DELAY_SECONDS = 300
MAX_BILI_SCAN_CONTINUATION_DELAY_SECONDS = 604_800
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MANIFEST_BINDING_KEYS = frozenset({"account_revision", "policy_fingerprint_sha256"})
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "adapter",
        "scheduler_job_id",
        "schedule_revision",
        "attempt",
        "execution_id",
        "sync_run_id",
        "platform",
        "mode",
        "crawl_revision_before",
        "account_revision",
        "policy_fingerprint_sha256",
        "artifact_schema_version",
        "upstream_sha",
        "output_fingerprint_sha256",
        "input_records",
        "creator_fingerprint_sha256",
    }
)
_LEGACY_MANIFEST_KEYS = _MANIFEST_KEYS - _MANIFEST_BINDING_KEYS


def validate_continuation_delay(value: object) -> int:
    """Zero disables; an enabled policy always has a bounded nonzero pause."""

    if type(value) is not int or (value != 0 and not 60 <= value <= MAX_BILI_SCAN_CONTINUATION_DELAY_SECONDS):
        raise ValueError("bili_scan_continuation_delay_seconds must be 0 or an integer between 60 and 604800")
    return value


def _has_pending_context(state: BiliScanState | BiliMultiFeedState) -> bool:
    uploads = state.uploads if isinstance(state, BiliMultiFeedState) else state
    scope = state.scope if isinstance(state, BiliMultiFeedState) else "uploads"
    if scope != "dynamics" and any(
        lane.witness is not None or lane.page > 1 for lane in (uploads.head, uploads.history)
    ):
        # Even a consumed witness needs the existing next-unit revalidation.
        return True
    return (
        isinstance(state, BiliMultiFeedState)
        and scope != "uploads"
        and any(
            lane.snapshot is not None or bool(lane.offset) for lane in (state.dynamics.head, state.dynamics.history)
        )
    )


def _bound_manifest(
    job: Job,
    run: SyncRun,
    schedule_revision: int,
    upstream_sha: str,
    *,
    auth_revision: int,
    policy_fingerprint_sha256: str | None,
    creator_fingerprint_sha256: str,
) -> bool:
    metadata = run.manifest
    if not isinstance(metadata, Mapping):
        return False
    metadata_keys = set(metadata)
    if metadata_keys not in {
        _LEGACY_MANIFEST_KEYS,
        _LEGACY_MANIFEST_KEYS | {"recovered_artifact"},
        _MANIFEST_KEYS,
        _MANIFEST_KEYS | {"recovered_artifact"},
    }:
        return False
    expected: dict[str, object] = {
        "schema_version": 1,
        "adapter": "mediacrawler",
        "scheduler_job_id": job.id,
        "schedule_revision": schedule_revision,
        "attempt": run.attempt,
        "sync_run_id": run.id,
        "platform": "bili",
        "mode": "forward",
        "crawl_revision_before": run.checkpoint_revision_before,
        "artifact_schema_version": MANIFEST_SCHEMA_VERSION,
        "upstream_sha": upstream_sha,
        "execution_id": str(uuid5(UUID(job.id), f"media-sync/mediacrawler/attempt/{run.attempt}")),
        "creator_fingerprint_sha256": creator_fingerprint_sha256,
    }
    if metadata_keys >= _MANIFEST_BINDING_KEYS:
        expected.update(
            account_revision=auth_revision,
            policy_fingerprint_sha256=policy_fingerprint_sha256,
        )
    if any(type(metadata.get(key)) is not type(value) or metadata[key] != value for key, value in expected.items()):
        return False
    fingerprint = metadata.get("output_fingerprint_sha256")
    records = metadata.get("input_records")
    if (
        type(fingerprint) is not str
        or _SHA256.fullmatch(fingerprint) is None
        or type(records) is not int
        or records < 0
    ):
        return False
    if "recovered_artifact" in metadata:
        recovered = metadata["recovered_artifact"]
        if not isinstance(recovered, Mapping) or set(recovered) != {
            "schema_version",
            "attempt",
            "execution_id",
            "sync_run_id",
        }:
            return False
        attempt = recovered.get("attempt")
        source_run_id = recovered.get("sync_run_id")
        if (
            type(recovered.get("schema_version")) is not int
            or recovered["schema_version"] != MANIFEST_SCHEMA_VERSION
            or type(attempt) is not int
            or not 1 <= attempt < run.attempt
            or type(source_run_id) is not str
            or str(UUID(source_run_id)) != source_run_id
            or source_run_id == run.id
            or recovered.get("execution_id") != str(uuid5(UUID(job.id), f"media-sync/mediacrawler/attempt/{attempt}"))
        ):
            return False
    return True


@dataclass(frozen=True, slots=True)
class BiliScanContinuationPolicy:
    """An injected current lock identity; unknown lock means ordinary scheduling."""

    delay_seconds: int = DEFAULT_BILI_SCAN_CONTINUATION_DELAY_SECONDS
    upstream_sha: str | None = None

    def __post_init__(self) -> None:
        validate_continuation_delay(self.delay_seconds)
        if self.upstream_sha is not None and (
            type(self.upstream_sha) is not str or _SHA1.fullmatch(self.upstream_sha) is None
        ):
            raise ValueError("continuation upstream SHA must be a full lowercase Git SHA")

    @classmethod
    def from_lock(
        cls, lock_path: Path, *, delay_seconds: int = DEFAULT_BILI_SCAN_CONTINUATION_DELAY_SECONDS
    ) -> BiliScanContinuationPolicy:
        validate_continuation_delay(delay_seconds)
        if delay_seconds == 0:
            return cls(delay_seconds=0)
        try:
            upstream_sha = load_mediacrawler_lock(lock_path).commit
        except (CheckoutValidationError, OSError, ValueError):
            upstream_sha = None
        return cls(delay_seconds=delay_seconds, upstream_sha=upstream_sha)

    def delay_after_success(
        self,
        *,
        job: Job,
        run: SyncRun | None,
        subscription: Subscription,
        schedule_revision: int,
        ordinary_interval: int,
    ) -> int:
        """Unknown/malformed/stale state retains its ordinary scheduling delay."""

        if self.delay_seconds == 0 or self.upstream_sha is None or run is None:
            return ordinary_interval
        try:
            account, author = subscription.account, subscription.author
            before, after = run.checkpoint_revision_before, run.checkpoint_revision_after
            policy = from_subscription_policy(subscription.policy)
            policy.validate_bili_max_items(subscription.max_items)
            if (
                job.job_type != "sync.subscription"
                or job.status != "succeeded"
                or job.run_id != run.id
                or job.subscription_id != subscription.id
                or run.subscription_id != subscription.id
                or run.status != "succeeded"
                or run.finished_at is None
                or run.error_code is not None
                or job.platform != "bili"
                or job.account_id != subscription.account_id
                or account.id != subscription.account_id
                or account.platform != "bili"
                or account.adapter != "mediacrawler"
                or account.auth_status != "authenticated"
                or author.id != subscription.author_id
                or author.platform != "bili"
                or not subscription.enabled
                or subscription.deleted_at is not None
                or type(schedule_revision) is not int
                or type(subscription.schedule_revision) is not int
                or subscription.schedule_revision != schedule_revision + 1
                or type(run.attempt) is not int
                or run.attempt < 1
                or type(job.attempts) is not int
                or job.attempts != run.attempt
                or type(before) is not int
                or before < 0
                or type(after) is not int
                or after != before + 1
                or type(subscription.checkpoint_revision) is not int
                or subscription.checkpoint_revision != after
                or subscription.cursor != run.cursor_after
                or not isinstance(run.cursor_after, Mapping)
                or set(run.cursor_after) != {"value"}
                or not _bound_manifest(
                    job,
                    run,
                    schedule_revision,
                    self.upstream_sha,
                    auth_revision=account.auth_revision,
                    policy_fingerprint_sha256=(
                        bili_policy_fingerprint(subscription.policy, subscription.max_items)
                        if policy.effective_bili_scope == "uploads"
                        else None
                    ),
                    creator_fingerprint_sha256=hashlib.sha256(author.remote_id.encode("utf-8")).hexdigest(),
                )
            ):
                return ordinary_interval
            state = state_from_cursor(run.cursor_after["value"])
            state.require_binding(
                account_id=UUID(account.id),
                author_fingerprint_sha256=hashlib.sha256(author.remote_id.encode("utf-8")).hexdigest(),
                upstream_sha=self.upstream_sha,
            )
            state_scope = state.scope if isinstance(state, BiliMultiFeedState) else "uploads"
            if state_scope != policy.effective_bili_scope or not _has_pending_context(state):
                return ordinary_interval
        except (ValueError, TypeError, KeyError, AttributeError):
            return ordinary_interval
        return min(self.delay_seconds, ordinary_interval)
