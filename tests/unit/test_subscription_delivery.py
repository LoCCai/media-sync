from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from media_sync.application.downloads import AssetDownloadOutcome
from media_sync.application.emby import EmbyExportOutcome
from media_sync.application.pipeline import (
    SelectedPipelineAsset,
    SubscriptionAssetSelection,
    SubscriptionPipelineOutcome,
)
from media_sync.application.subscription_delivery import (
    SubscriptionDeliveryEvidenceError,
    pipeline_delivery_receipt,
)
from media_sync.domain import AssetStatus
from media_sync.scheduler import PipelineDeliveryReceipt, PipelineHandlerResult

SUBSCRIPTION_ID = UUID("11111111-1111-4111-8111-111111111111")
ACCOUNT_ID = UUID("22222222-2222-4222-8222-222222222222")
AUTHOR_ID = UUID("33333333-3333-4333-8333-333333333333")
ASSET_ONE = UUID("44444444-4444-4444-8444-444444444444")
ASSET_TWO = UUID("55555555-5555-4555-8555-555555555555")
CONTENT_ONE = UUID("66666666-6666-4666-8666-666666666666")
CONTENT_TWO = UUID("77777777-7777-4777-8777-777777777777")
EXPORT_JOB_ID = "88888888-8888-4888-8888-888888888888"


def _outcome(*, mismatched: bool = False) -> SubscriptionPipelineOutcome:
    selected = (
        SelectedPipelineAsset(
            asset_id=ASSET_ONE,
            content_id=CONTENT_ONE,
            generation=1,
            platform="bili",
            kind="video",
            position=0,
            status=AssetStatus.DISCOVERED,
            requires_mediacrawler_refresh=True,
        ),
        SelectedPipelineAsset(
            asset_id=ASSET_TWO,
            content_id=CONTENT_TWO,
            generation=2,
            platform="bili",
            kind="cover",
            position=0,
            status=AssetStatus.VERIFIED,
            requires_mediacrawler_refresh=False,
        ),
    )
    downloads = (
        AssetDownloadOutcome(
            asset_id=ASSET_ONE,
            generation=1,
            job_id=UUID("99999999-9999-4999-8999-999999999999"),
            status=AssetStatus.VERIFIED,
            disposition="downloaded",
            archive_path=Path("archive-one"),
            checksum_sha256="a" * 64,
            size_bytes=10,
            mime_type="video/mp4",
        ),
        AssetDownloadOutcome(
            asset_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa") if mismatched else ASSET_TWO,
            generation=2,
            job_id=None,
            status=AssetStatus.VERIFIED,
            disposition="already_verified",
            archive_path=Path("archive-two"),
            checksum_sha256="b" * 64,
            size_bytes=11,
            mime_type="image/jpeg",
        ),
    )
    return SubscriptionPipelineOutcome(
        selection=SubscriptionAssetSelection(
            subscription_id=SUBSCRIPTION_ID,
            account_id=ACCOUNT_ID,
            author_id=AUTHOR_ID,
            platform="bili",
            account_adapter="mediacrawler",
            assets=selected,
        ),
        downloads=downloads,
        export=EmbyExportOutcome(
            job_id=EXPORT_JOB_ID,
            source_fingerprint="c" * 64,
            output_path="private/path-not-retained",
            rendered_fingerprint="d" * 64,
            managed_file_count=9,
            already_exported=False,
        ),
    )


def test_pipeline_delivery_receipt_retains_only_exact_safe_counts() -> None:
    receipt = pipeline_delivery_receipt(_outcome())

    assert receipt.to_mapping() == {
        "subscription_id": str(SUBSCRIPTION_ID),
        "account_id": str(ACCOUNT_ID),
        "author_id": str(AUTHOR_ID),
        "platform": "bili",
        "export_job_id": EXPORT_JOB_ID,
        "selected_asset_count": 2,
        "verified_asset_count": 2,
        "downloaded_count": 1,
        "already_verified_count": 1,
        "publication_disposition": "published",
        "managed_file_count": 9,
        "directory_verified": True,
    }
    serialized = repr(receipt.to_mapping())
    assert "private/path" not in serialized
    assert "archive-one" not in serialized
    assert "checksum" not in serialized


def test_pipeline_delivery_receipt_rejects_asset_scope_mismatch() -> None:
    with pytest.raises(SubscriptionDeliveryEvidenceError, match="subscription_delivery_evidence_invalid"):
        pipeline_delivery_receipt(_outcome(mismatched=True))


def test_pipeline_handler_rejects_inconsistent_or_failed_receipts() -> None:
    valid = pipeline_delivery_receipt(_outcome())
    with pytest.raises(ValueError, match="inconsistent"):
        PipelineDeliveryReceipt(
            **{
                **valid.to_mapping(),
                "verified_asset_count": valid.verified_asset_count - 1,
            }
        )
    with pytest.raises(ValueError, match="failed pipeline results cannot carry a receipt"):
        PipelineHandlerResult(
            succeeded=False,
            error_code="pipeline_worker_error",
            receipt=valid,
        )
