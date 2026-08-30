from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from media_sync.application.downloads import (
    AssetDownloadOrchestrationError,
    AssetDownloadOutcome,
    AssetDownloadRequest,
    asset_download_io_scope_fingerprint,
    asset_download_natural_key,
)
from media_sync.domain import AssetStatus
from media_sync.media import MediaDownloadError


def test_download_request_is_frozen_normalized_and_generation_keyed(tmp_path: Path) -> None:
    asset_id = uuid4()
    request = AssetDownloadRequest(
        asset_id=asset_id,
        worker_id="  worker-1  ",
        work_root=tmp_path / "nested" / ".." / "work",
        archive_root=tmp_path / "archive",
        lease_seconds=30,
        max_attempts=3,
        priority=7,
    )

    assert request.worker_id == "worker-1"
    assert request.asset_id == asset_id
    assert request.work_root == (tmp_path / "work").absolute()
    assert request.archive_root.is_absolute()
    assert request.io_scope_fingerprint == asset_download_io_scope_fingerprint(
        request.work_root,
        request.archive_root,
    )
    assert len(request.io_scope_fingerprint) == 64
    assert request.io_scope_fingerprint != asset_download_io_scope_fingerprint(
        request.work_root,
        tmp_path / "other-archive",
    )
    assert asset_download_natural_key(asset_id, 4) == f"{asset_id}:4"
    with pytest.raises(AttributeError):
        request.worker_id = "replacement"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"worker_id": " \n "}, "worker_id"),
        ({"worker_id": "worker\x00hidden"}, "worker_id"),
        ({"worker_id": 1}, "worker_id"),
        ({"lease_seconds": 0}, "lease_seconds"),
        ({"lease_seconds": 86_401}, "lease_seconds"),
        ({"lease_seconds": "60"}, "lease_seconds"),
        ({"max_attempts": 0}, "max_attempts"),
        ({"max_attempts": 101}, "max_attempts"),
        ({"max_attempts": "5"}, "max_attempts"),
        ({"priority": True}, "priority"),
    ],
)
def test_download_request_rejects_invalid_control_fields(
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "asset_id": uuid4(),
        "worker_id": "worker",
        "work_root": tmp_path / "work",
        "archive_root": tmp_path / "archive",
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        AssetDownloadRequest(**values)  # type: ignore[arg-type]


def test_outcome_is_frozen_and_uses_typed_verified_status(tmp_path: Path) -> None:
    outcome = AssetDownloadOutcome(
        asset_id=uuid4(),
        generation=2,
        job_id=uuid4(),
        status=AssetStatus.VERIFIED,
        disposition="downloaded",
        archive_path=tmp_path / "archive" / "blob.png",
        checksum_sha256="a" * 64,
        size_bytes=12,
        mime_type="image/png",
    )

    assert outcome.status is AssetStatus.VERIFIED
    with pytest.raises(AttributeError):
        outcome.size_bytes = 13  # type: ignore[misc]


def test_orchestration_and_media_errors_are_fixed_and_redaction_safe() -> None:
    orchestration = AssetDownloadOrchestrationError("asset_download_busy")
    scope_mismatch = AssetDownloadOrchestrationError("asset_download_io_scope_mismatch")
    media = MediaDownloadError("download_http_retryable")
    translated = AssetDownloadOrchestrationError._from_media(media, retryable=False)
    final_worker_failure = AssetDownloadOrchestrationError._from_fixed(
        "asset_download_worker_failed",
        retryable=False,
    )

    assert orchestration.code == "asset_download_busy"
    assert orchestration.retryable is True
    assert scope_mismatch.retryable is False
    assert translated.code == "download_http_retryable"
    assert translated.retryable is False
    assert final_worker_failure.code == "asset_download_worker_failed"
    assert final_worker_failure.retryable is False
    assert "https://" not in str(orchestration)
    assert "https://" not in str(translated)
    with pytest.raises(ValueError, match="unknown"):
        AssetDownloadOrchestrationError("sentinel-not-a-fixed-code")


def test_missing_refresh_capability_is_retryable_for_future_adapter_support() -> None:
    error = MediaDownloadError("locator_refresh_unsupported")

    assert error.retryable is True
    assert "https://" not in str(error)


def test_natural_key_rejects_non_uuid_and_invalid_generation() -> None:
    with pytest.raises(TypeError, match="UUID"):
        asset_download_natural_key("not-a-uuid", 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive"):
        asset_download_natural_key(UUID(int=0), 0)
