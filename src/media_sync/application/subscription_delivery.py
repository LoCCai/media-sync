"""Closed evidence contracts for one exact subscription delivery.

The scheduler owns durable claiming and the pipeline owns filesystem work.  This
module joins only their already-safe successful observations and re-reads the
authoritative database identities before an Operation may claim delivery.
Paths, locators, credentials and per-asset details have no representation here.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final
from uuid import UUID

from sqlalchemy.orm import Session

from media_sync.application.pipeline import SubscriptionPipelineOutcome
from media_sync.domain import AssetStatus
from media_sync.infrastructure.db import Database, RepositoryError
from media_sync.infrastructure.db.models import Job, Subscription, SyncRun
from media_sync.scheduler.pipeline import PipelineJobRepository
from media_sync.scheduler.pipeline_receipt import PipelineDeliveryReceipt

_SYNC_JOB_TYPE: Final = "sync.subscription"
_PIPELINE_JOB_TYPE: Final = "pipeline.subscription"
_EXPORT_JOB_TYPE: Final = "export.emby"
_ADAPTER_DISCOVERY_SEMANTICS: Final = MappingProxyType({"fake": "processed_items", "mediacrawler": "created_rows"})


class SubscriptionDeliveryEvidenceError(RuntimeError):
    """A fixed-code rejection safe for the durable Operation boundary."""

    def __init__(self, code: str = "subscription_delivery_evidence_invalid") -> None:
        if code not in {
            "subscription_delivery_evidence_invalid",
            "subscription_delivery_scope_changed",
            "subscription_delivery_mediacrawler_not_enabled",
            "subscription_delivery_license_required",
        }:
            raise ValueError("unknown subscription delivery evidence code")
        self.code = code
        self.retryable = code == "subscription_delivery_evidence_invalid"
        super().__init__(code)


def _uuid(value: object) -> str:
    try:
        normalized = str(UUID(str(value)))
    except (AttributeError, TypeError, ValueError):
        raise SubscriptionDeliveryEvidenceError() from None
    if value != normalized:
        raise SubscriptionDeliveryEvidenceError()
    return normalized


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 9_223_372_036_854_775_807:
        raise SubscriptionDeliveryEvidenceError()
    return value


def pipeline_delivery_receipt(outcome: SubscriptionPipelineOutcome) -> PipelineDeliveryReceipt:
    """Reduce an in-memory pipeline outcome to bounded non-sensitive facts."""

    if not isinstance(outcome, SubscriptionPipelineOutcome):
        raise SubscriptionDeliveryEvidenceError()
    selected = outcome.selection.assets
    downloads = outcome.downloads
    expected = {(item.asset_id, item.generation) for item in selected}
    observed = {(item.asset_id, item.generation) for item in downloads}
    exact_run = outcome.source_run_id is not None
    if (
        len(expected) != len(selected)
        or len(observed) != len(downloads)
        or any(item.status is not AssetStatus.VERIFIED for item in downloads)
    ):
        raise SubscriptionDeliveryEvidenceError()
    if (not exact_run and expected != observed) or (exact_run and not observed.issubset(expected)):
        raise SubscriptionDeliveryEvidenceError()
    if exact_run and (
        outcome.observed_content_count != outcome.delivered_content_count + outcome.failed_content_count
        or outcome.retry_backlog_content_count
        != outcome.delivered_retry_backlog_content_count + outcome.failed_retry_backlog_content_count
        or outcome.failed_content_count + outcome.failed_retry_backlog_content_count
        != outcome.retryable_failed_content_count + outcome.terminal_failed_content_count
        or tuple(sorted(set(outcome.failure_codes))) != outcome.failure_codes
        or bool(outcome.failure_codes)
        != (outcome.failed_content_count + outcome.failed_retry_backlog_content_count > 0)
    ):
        raise SubscriptionDeliveryEvidenceError()
    downloaded = sum(item.disposition == "downloaded" for item in downloads)
    reused = sum(item.disposition == "already_verified" for item in downloads)
    if downloaded + reused != len(downloads):
        raise SubscriptionDeliveryEvidenceError()
    export = outcome.export
    return PipelineDeliveryReceipt(
        subscription_id=str(outcome.selection.subscription_id),
        account_id=str(outcome.selection.account_id),
        author_id=str(outcome.selection.author_id),
        platform=outcome.selection.platform,
        export_job_id=export.job_id,
        selected_asset_count=len(downloads) if exact_run else len(selected),
        verified_asset_count=len(downloads),
        downloaded_count=downloaded,
        already_verified_count=reused,
        publication_disposition="already_exported" if export.already_exported else "published",
        managed_file_count=export.managed_file_count,
        # EmbyExportService returns only after validating either the existing
        # publication or the newly installed tree and its durable result.
        directory_verified=True,
        schema_version=2 if exact_run else 1,
        source_run_id=str(outcome.source_run_id) if outcome.source_run_id is not None else None,
        observed_content_count=outcome.observed_content_count,
        delivered_content_count=outcome.delivered_content_count,
        failed_content_count=outcome.failed_content_count,
        retry_backlog_content_count=outcome.retry_backlog_content_count,
        delivered_retry_backlog_content_count=outcome.delivered_retry_backlog_content_count,
        failed_retry_backlog_content_count=outcome.failed_retry_backlog_content_count,
        retryable_failed_content_count=outcome.retryable_failed_content_count,
        terminal_failed_content_count=outcome.terminal_failed_content_count,
        failure_codes=outcome.failure_codes,
        partial=outcome.failed_content_count + outcome.failed_retry_backlog_content_count > 0,
    )


def build_subscription_delivery_result(
    database: Database,
    *,
    subscription_id: str,
    sync_job_id: str,
    run_id: str,
    pipeline_job_id: str,
    pipeline_receipt: PipelineDeliveryReceipt | None = None,
) -> dict[str, object]:
    with database.session() as session:
        return build_subscription_delivery_result_in_session(
            session,
            subscription_id=subscription_id,
            sync_job_id=sync_job_id,
            run_id=run_id,
            pipeline_job_id=pipeline_job_id,
            pipeline_receipt=pipeline_receipt,
        )


def build_subscription_delivery_result_in_session(
    session: Session,
    *,
    subscription_id: str,
    sync_job_id: str,
    run_id: str,
    pipeline_job_id: str,
    pipeline_receipt: PipelineDeliveryReceipt | None = None,
) -> dict[str, object]:
    """Re-read the exact successful chain and build the Operation result."""

    expected_subscription = _uuid(subscription_id)
    expected_sync_job = _uuid(sync_job_id)
    expected_run = _uuid(run_id)
    expected_pipeline_job = _uuid(pipeline_job_id)
    try:
        durable = PipelineJobRepository(session).get(expected_pipeline_job)
    except (RepositoryError, ValueError, TypeError):
        raise SubscriptionDeliveryEvidenceError() from None
    if durable.receipt is None or (pipeline_receipt is not None and pipeline_receipt != durable.receipt):
        raise SubscriptionDeliveryEvidenceError()
    pipeline_receipt = durable.receipt

    subscription = session.get(Subscription, expected_subscription)
    sync_job = session.get(Job, expected_sync_job)
    run = session.get(SyncRun, expected_run)
    pipeline_job = session.get(Job, expected_pipeline_job)
    export_job = session.get(Job, pipeline_receipt.export_job_id)
    if any(item is None for item in (subscription, sync_job, run, pipeline_job, export_job)):
        raise SubscriptionDeliveryEvidenceError()
    assert subscription is not None and sync_job is not None and run is not None
    assert pipeline_job is not None and export_job is not None
    account = subscription.account
    author = subscription.author
    if (
        subscription.deleted_at is not None
        or sync_job.job_type != _SYNC_JOB_TYPE
        or sync_job.status != "succeeded"
        or sync_job.subscription_id != subscription.id
        or sync_job.account_id != account.id
        or sync_job.platform != account.platform
        or sync_job.run_id != run.id
        or run.subscription_id != subscription.id
        or run.status != "succeeded"
        or pipeline_job.job_type != _PIPELINE_JOB_TYPE
        or pipeline_job.status != "succeeded"
        or pipeline_job.subscription_id != subscription.id
        or pipeline_job.account_id != account.id
        or pipeline_job.platform != account.platform
        or pipeline_job.run_id != run.id
        or not isinstance(pipeline_job.payload, Mapping)
        or pipeline_job.payload.get("sync_job_id") != sync_job.id
        or pipeline_job.payload.get("run_id") != run.id
        or pipeline_job.payload.get("subscription_id") != subscription.id
        or pipeline_receipt.subscription_id != subscription.id
        or pipeline_receipt.account_id != account.id
        or pipeline_receipt.author_id != author.id
        or pipeline_receipt.platform != account.platform
        or (pipeline_receipt.schema_version == 2 and pipeline_receipt.source_run_id != run.id)
        or author.platform != account.platform
        or export_job.job_type != _EXPORT_JOB_TYPE
        or export_job.status != "succeeded"
        or not isinstance(export_job.payload, Mapping)
        or export_job.payload.get("author_id") != author.id
    ):
        raise SubscriptionDeliveryEvidenceError("subscription_delivery_scope_changed")
    raw_export_result = export_job.payload.get("result")
    if (
        not isinstance(raw_export_result, Mapping)
        or raw_export_result.get("managed_file_count") != pipeline_receipt.managed_file_count
    ):
        raise SubscriptionDeliveryEvidenceError()
    try:
        discovery_semantics = _ADAPTER_DISCOVERY_SEMANTICS[account.adapter]
    except KeyError:
        raise SubscriptionDeliveryEvidenceError("subscription_delivery_scope_changed") from None

    result: dict[str, object] = {
        "subscription_id": subscription.id,
        "account_id": account.id,
        "author_id": author.id,
        "platform": account.platform,
        "sync_job_id": sync_job.id,
        "run_id": run.id,
        "pipeline_job_id": pipeline_job.id,
        "export_job_id": pipeline_receipt.export_job_id,
        "discovery_count": _count(run.discovered_count),
        "asset_identity_count": _count(run.asset_count),
        # Neither adapter currently owns a trustworthy updated-row
        # comparator.  The persisted zero must not be presented as proof.
        "updated_count": None,
        "discovery_count_semantics": discovery_semantics,
        "selection_scope": (
            "source_run_plus_retry_backlog" if pipeline_receipt.schema_version == 2 else "author_active_snapshot"
        ),
        "selected_asset_count": pipeline_receipt.selected_asset_count,
        "verified_asset_count": pipeline_receipt.verified_asset_count,
        "downloaded_count": pipeline_receipt.downloaded_count,
        "already_verified_count": pipeline_receipt.already_verified_count,
        "publication_disposition": pipeline_receipt.publication_disposition,
        "managed_file_count": pipeline_receipt.managed_file_count,
        "directory_verified": pipeline_receipt.directory_verified,
    }
    if pipeline_receipt.schema_version == 2:
        result.update(
            observed_content_count=pipeline_receipt.observed_content_count,
            delivered_content_count=pipeline_receipt.delivered_content_count,
            failed_content_count=pipeline_receipt.failed_content_count,
            retry_backlog_content_count=pipeline_receipt.retry_backlog_content_count,
            delivered_retry_backlog_content_count=pipeline_receipt.delivered_retry_backlog_content_count,
            failed_retry_backlog_content_count=pipeline_receipt.failed_retry_backlog_content_count,
            retryable_failed_content_count=pipeline_receipt.retryable_failed_content_count,
            terminal_failed_content_count=pipeline_receipt.terminal_failed_content_count,
            failure_codes=list(pipeline_receipt.failure_codes),
            partial=pipeline_receipt.partial,
        )
    return result


__all__ = [
    "PipelineDeliveryReceipt",
    "SubscriptionDeliveryEvidenceError",
    "build_subscription_delivery_result",
    "build_subscription_delivery_result_in_session",
    "pipeline_delivery_receipt",
]
