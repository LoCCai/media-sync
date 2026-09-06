"""Per-feed evidence committed with its exact Run; no completeness inference."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from media_sync.integrations.mediacrawler.bilibili_multifeed import (
    BiliMultiFeedCoverage,
    BiliMultiFeedState,
    state_for_cursor,
)
from media_sync.integrations.mediacrawler.bilibili_scan import BiliScanCoverage
from media_sync.integrations.mediacrawler.normalizers import NormalizedMediaRecord
from media_sync.integrations.mediacrawler.subscription_policy import from_subscription_policy

from .base import utc_now
from .models import SCAN_PROGRESS_STATES, SCAN_PROGRESS_STOP_REASONS, Subscription, SubscriptionScanProgress, SyncRun
from .repositories import RepositoryError

MAX_PROGRESS_NUMBER = 9_007_199_254_740_991
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_FEEDS = {
    "bili": ("uploads",),
    "xhs": ("notes",),
    "dy": ("posts",),
    "ks": ("posts",),
    "wb": ("posts",),
    "tieba": ("threads",),
    "zhihu": ("answers",),
}
_COUNTERS = ("checkpoint_revision", "unit_count", "item_count", "history_unit_count", "history_item_count")


@dataclass(frozen=True)
class BiliProgressEvidence:
    feed: str
    lane: str
    stop_reason: str
    contract_version: int
    upstream_sha: str
    item_count: int


def validate_bili_progress_evidence(
    subscription: Subscription,
    run: SyncRun,
    coverage: BiliScanCoverage | BiliMultiFeedCoverage,
    *,
    input_cursor: str | None,
    next_cursor: str,
    records: tuple[NormalizedMediaRecord, ...],
) -> BiliProgressEvidence:
    """Replay coverage under the DB-bound account/author/source and record set."""
    try:
        if (
            type(coverage) not in {BiliScanCoverage, BiliMultiFeedCoverage}
            or subscription.account.adapter != "mediacrawler"
            or subscription.account.platform != "bili"
            or subscription.author.platform != "bili"
            or run.subscription_id != subscription.id
        ):
            raise ValueError
        upstream_sha = run.manifest.get("upstream_sha")
        if type(upstream_sha) is not str or _SHA1.fullmatch(upstream_sha) is None:
            raise ValueError
        scope = from_subscription_policy(subscription.policy).bili_scope if subscription.policy else None
        state = state_for_cursor(
            input_cursor,
            account_id=UUID(subscription.account_id),
            author_fingerprint_sha256=hashlib.sha256(subscription.author.remote_id.encode("utf-8")).hexdigest(),
            upstream_sha=upstream_sha,
            scope=scope,
        )
        if coverage.next_state.to_cursor() != next_cursor:
            raise ValueError
        if isinstance(coverage, BiliMultiFeedCoverage):
            if not isinstance(state, BiliMultiFeedState):
                raise ValueError
            coverage.validate(
                state,
                subscription.max_items,
                normalized_records=tuple((record.content.remote_type, record.content.remote_id) for record in records),
            )
            feed, version = coverage.feed, 2
        else:
            if isinstance(state, BiliMultiFeedState):
                raise ValueError
            if any(record.content.remote_type != "content" for record in records):
                raise ValueError
            coverage.validate(
                state,
                subscription.max_items,
                normalized_remote_ids=tuple(record.content.remote_id for record in records),
            )
            feed, version = "uploads", 1
        return BiliProgressEvidence(feed, coverage.lane, coverage.stop_reason, version, upstream_sha, len(records))
    except (ValueError, TypeError, AttributeError, KeyError):
        raise RepositoryError("scan_progress_evidence_invalid") from None


class ScanProgressRepository:
    """Publish only inside the ingestion transaction after its checkpoint CAS."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def publish(self, subscription: Subscription, run: SyncRun, evidence: BiliProgressEvidence) -> None:
        if (
            not self.session.in_transaction()
            or run.status != "succeeded"
            or run.subscription_id != subscription.id
            or subscription.deleted_at is not None
            or run.checkpoint_revision_after != subscription.checkpoint_revision
            or run.checkpoint_revision_before is None
            or run.checkpoint_revision_after != run.checkpoint_revision_before + 1
            or evidence.feed not in {"uploads", "dynamics"}
            or evidence.lane not in {"head", "history"}
            or evidence.stop_reason not in SCAN_PROGRESS_STOP_REASONS
            or type(evidence.contract_version) is not int
            or evidence.contract_version not in ({2} if evidence.feed == "dynamics" else {1, 2})
            or type(evidence.upstream_sha) is not str
            or _SHA1.fullmatch(evidence.upstream_sha) is None
            or type(evidence.item_count) is not int
            or not 0 <= evidence.item_count <= MAX_PROGRESS_NUMBER
        ):
            raise RepositoryError("scan_progress_commit_invalid")
        now = utc_now()
        row = self.session.get(SubscriptionScanProgress, (subscription.id, evidence.feed))
        if row is not None and row.checkpoint_revision >= subscription.checkpoint_revision:
            raise RepositoryError("scan_progress_revision_invalid")
        if row is None:
            row = SubscriptionScanProgress(subscription_id=subscription.id, feed=evidence.feed)
            self.session.add(row)
        if row.upstream_sha != evidence.upstream_sha or row.contract_version != evidence.contract_version:
            row.generation_id = str(uuid4())
            row.upstream_sha = evidence.upstream_sha
            row.contract_version = evidence.contract_version
            row.state = "unproven"
            row.unit_count = row.item_count = row.history_unit_count = row.history_item_count = 0
            row.started_at = now
            row.source_end_observed_at = None
            row.source_end_run_id = None
        row.unit_count += 1
        row.item_count += evidence.item_count
        if evidence.lane == "history":
            row.history_unit_count += 1
            row.history_item_count += evidence.item_count
            row.state = "scanning"
            if evidence.stop_reason == "source_end":
                row.state = "source_end_observed"
                row.source_end_observed_at = now
                row.source_end_run_id = run.id
        row.last_lane, row.last_stop_reason = evidence.lane, evidence.stop_reason
        row.last_progress_at = now
        row.checkpoint_revision = subscription.checkpoint_revision
        if any(
            type(getattr(row, field)) is not int or not 0 <= getattr(row, field) <= MAX_PROGRESS_NUMBER
            for field in _COUNTERS
        ):
            raise RepositoryError("scan_progress_count_invalid")
        self.session.flush()


def _uuid(value: object) -> bool:
    try:
        return type(value) is str and str(UUID(value)) == value
    except ValueError:
        return False


def _time(value: object) -> str | None:
    return value.astimezone(UTC).isoformat() if isinstance(value, datetime) and value.tzinfo is not None else None


def scan_progress_payload(subscription: Subscription, *, upstream_sha: str | None) -> dict[str, object]:
    """Read-only fixed projection; missing, legacy and unbound rows stay unproven."""
    feeds: tuple[str, ...] = _FEEDS.get(subscription.account.platform, ())
    policy_valid = True
    if subscription.account.platform == "bili":
        try:
            scope = from_subscription_policy(subscription.policy).effective_bili_scope
            feeds = ("uploads", "dynamics") if scope == "both" else (scope,)
        except ValueError:
            policy_valid = False
    rows = {row.feed: row for row in subscription.scan_progress}
    result: list[dict[str, object]] = []
    for feed in feeds:
        payload: dict[str, object] = {
            "feed": feed,
            "state": "unproven",
            "contract_version": None,
            "upstream_sha": None,
            "generation_id": None,
            "checkpoint_revision": None,
            "unit_count": 0,
            "item_count": 0,
            "history_unit_count": 0,
            "history_item_count": 0,
            "last_lane": None,
            "last_stop_reason": None,
            "started_at": None,
            "last_progress_at": None,
            "source_end_observed_at": None,
            "source_end_run_id": None,
        }
        row = rows.get(feed)
        if (
            subscription.account.platform == "bili"
            and subscription.account.adapter == "mediacrawler"
            and subscription.author.platform == "bili"
            and policy_valid
            and row is not None
            and row.subscription_id == subscription.id
            and upstream_sha is not None
            and row.upstream_sha == upstream_sha
            and _SHA1.fullmatch(upstream_sha) is not None
            and row.state in SCAN_PROGRESS_STATES
            and type(row.contract_version) is int
            and row.contract_version in ({2} if feed == "dynamics" else {1, 2})
            and _uuid(row.generation_id)
            and row.last_lane in {"head", "history"}
            and row.last_stop_reason in SCAN_PROGRESS_STOP_REASONS
            and all(
                type(getattr(row, field)) is int and 0 <= getattr(row, field) <= MAX_PROGRESS_NUMBER
                for field in _COUNTERS
            )
            and row.checkpoint_revision <= subscription.checkpoint_revision
            and row.checkpoint_revision > 0
            and row.unit_count > 0
            and row.history_unit_count <= row.unit_count
            and row.history_item_count <= row.item_count
            and _time(row.started_at) is not None
            and _time(row.last_progress_at) is not None
            and (
                (
                    row.source_end_run_id is None
                    and row.source_end_observed_at is None
                    and row.state != "source_end_observed"
                )
                or (
                    _uuid(row.source_end_run_id)
                    and _time(row.source_end_observed_at) is not None
                    and row.history_unit_count > 0
                )
            )
        ):
            for field in payload.keys() - {"feed"}:
                value = getattr(row, field)
                payload[field] = _time(value) if field.endswith("_at") else value
        result.append(payload)
    return {"schema_version": 1, "history_complete": False, "feeds": result}


__all__ = ["BiliProgressEvidence", "ScanProgressRepository", "scan_progress_payload", "validate_bili_progress_evidence"]
