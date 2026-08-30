"""Local runtime composition for subscription download-to-Emby pipelines."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from media_sync.application.downloads import AssetDownloadOutcome, AssetDownloadRequest, AssetDownloadService
from media_sync.application.emby import EmbyExportRequest, EmbyExportService
from media_sync.application.mediacrawler_download import LazyMediaCrawlerLocatorRefresher
from media_sync.application.pipeline import (
    SelectedPipelineAsset,
    SubscriptionAssetSelection,
    SubscriptionAssetSelector,
    SubscriptionPipelineError,
    SubscriptionPipelineOutcome,
    SubscriptionPipelineRequest,
    SubscriptionPipelineService,
)
from media_sync.domain import AssetStatus, Platform
from media_sync.exporters.emby import EmbyExporter
from media_sync.infrastructure.db import Asset, Database
from media_sync.integrations.mediacrawler import (
    CheckoutValidationError,
    verify_mediacrawler_checkout,
    verify_mediacrawler_python,
)
from media_sync.media import (
    AdapterRefreshLocator,
    DownloadLimits,
    FFprobeMediaProbe,
    LocatorRefreshPort,
    MediaDownloadError,
    NetworkLimits,
    SafeHttpClient,
    SecureMediaDownloader,
    SocketAddressResolver,
    parse_locator,
)
from media_sync.security import SecretResolver


@dataclass(frozen=True, slots=True)
class LocalPipelineRuntimeConfig:
    """Filesystem, retry and optional MediaCrawler controls for one worker."""

    work_root: Path
    archive_root: Path
    export_root: Path
    export_staging_root: Path
    mediacrawler_lock_path: Path
    mediacrawler_runtime_root: Path
    mediacrawler_python_executable: Path | None
    secret_resolver: SecretResolver = field(repr=False)
    enable_mediacrawler: bool = False
    accept_mediacrawler_license: bool = False
    xhs_detail_reference_ref: str | None = field(default=None, repr=False)
    download_lease_seconds: int = 3_600
    download_max_attempts: int = 5
    export_lease_seconds: int = 300
    export_max_attempts: int = 5
    ffprobe_executable: str | None = None
    http_client_factory: Callable[[], SafeHttpClient] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.enable_mediacrawler) is not bool or type(self.accept_mediacrawler_license) is not bool:
            raise ValueError("MediaCrawler runtime controls must be boolean")
        if self.accept_mediacrawler_license and not self.enable_mediacrawler:
            raise ValueError("MediaCrawler license acknowledgement requires enablement")
        if self.http_client_factory is not None and not callable(self.http_client_factory):
            raise ValueError("http_client_factory must be callable")
        for value, name in (
            (self.download_lease_seconds, "download_lease_seconds"),
            (self.export_lease_seconds, "export_lease_seconds"),
        ):
            if type(value) is not int or not 1 <= value <= 86_400:
                raise ValueError(f"{name} must be between 1 and 86400")
        for value, name in (
            (self.download_max_attempts, "download_max_attempts"),
            (self.export_max_attempts, "export_max_attempts"),
        ):
            if type(value) is not int or not 1 <= value <= 100:
                raise ValueError(f"{name} must be between 1 and 100")
        for name in ("work_root", "archive_root", "export_root", "export_staging_root"):
            value = getattr(self, name)
            if not isinstance(value, Path):
                raise ValueError(f"{name} must be a Path")


class _PerAssetDownloadRunner:
    """Construct a downloader bound to the current exact asset and Subscription."""

    def __init__(
        self,
        database: Database,
        subscription_id: UUID,
        config: LocalPipelineRuntimeConfig,
    ) -> None:
        self._database = database
        self._subscription_id = subscription_id
        self._config = config

    def run(self, request: AssetDownloadRequest) -> AssetDownloadOutcome:
        refresher = self._refresher(request.asset_id)
        limits = DownloadLimits()
        http = (
            self._config.http_client_factory()
            if self._config.http_client_factory is not None
            else SafeHttpClient(
                SocketAddressResolver(),
                limits=NetworkLimits(timeout_seconds=min(limits.total_timeout_seconds, 120.0)),
            )
        )
        probe = (
            FFprobeMediaProbe(self._config.ffprobe_executable) if self._config.ffprobe_executable is not None else None
        )
        downloader = SecureMediaDownloader(
            http,
            refresher=refresher,
            probe=probe,
            limits=limits,
        )
        return AssetDownloadService(self._database, downloader).run(request)

    def _refresher(self, asset_id: UUID) -> LocatorRefreshPort | None:
        with self._database.session() as session:
            asset_scope = session.execute(
                select(Asset.locator, Asset.platform).where(Asset.id == str(asset_id))
            ).one_or_none()
        if asset_scope is None:
            return None
        raw_locator, asset_platform = asset_scope
        try:
            locator = parse_locator(raw_locator)
        except MediaDownloadError:
            return None
        if not isinstance(locator, AdapterRefreshLocator) or locator.adapter != "mediacrawler":
            return None
        config = self._config
        if not config.enable_mediacrawler or not config.accept_mediacrawler_license:
            return None
        return LazyMediaCrawlerLocatorRefresher(
            self._database,
            asset_id=asset_id,
            subscription_id=self._subscription_id,
            lock_path=config.mediacrawler_lock_path,
            integration_root=config.mediacrawler_runtime_root,
            python_executable=config.mediacrawler_python_executable,
            secret_resolver=config.secret_resolver,
            license_acknowledged=True,
            detail_reference_ref=(config.xhs_detail_reference_ref if asset_platform == Platform.XHS.value else None),
        )


class SubscriptionPipelineExecutor:
    """Compose existing durable child services for one coordinator claim."""

    def __init__(self, database: Database, config: LocalPipelineRuntimeConfig) -> None:
        self._database = database
        self._config = config

    def run(
        self,
        subscription_id: UUID,
        *,
        expected_account_id: UUID,
        expected_platform: str,
        worker_id: str,
    ) -> SubscriptionPipelineOutcome:
        download_worker_id = _scoped_worker_id(worker_id, "asset")
        export_worker_id = _scoped_worker_id(worker_id, "emby")
        config = self._config
        service = SubscriptionPipelineService(
            SubscriptionAssetSelector(self._database),
            _PerAssetDownloadRunner(self._database, subscription_id, config),
            EmbyExportService(
                self._database,
                EmbyExporter(config.export_root, staging_root=config.export_staging_root),
            ),
            download_request_factory=lambda asset: _download_request(
                asset,
                config=config,
                worker_id=download_worker_id,
            ),
            export_request_factory=lambda selection: _export_request(
                selection,
                config=config,
                worker_id=export_worker_id,
            ),
            selection_preflight=lambda selection: _preflight_selection(selection, config=config),
        )
        return service.run(
            SubscriptionPipelineRequest(
                subscription_id=subscription_id,
                expected_account_id=expected_account_id,
                expected_platform=expected_platform,
            )
        )


def _preflight_selection(
    selection: SubscriptionAssetSelection,
    *,
    config: LocalPipelineRuntimeConfig,
) -> None:
    """Reject missing local capabilities before any child Job is consumed."""

    requires_mediacrawler = False
    requires_media_probe = False
    for asset in selection.assets:
        if asset.status in {AssetStatus.VERIFIED, AssetStatus.FAILED_TERMINAL}:
            continue
        if asset.requires_mediacrawler_refresh:
            if not config.enable_mediacrawler:
                raise SubscriptionPipelineError("pipeline_mediacrawler_not_enabled")
            if not config.accept_mediacrawler_license:
                raise SubscriptionPipelineError("pipeline_mediacrawler_license_required")
            if config.mediacrawler_python_executable is None:
                raise SubscriptionPipelineError("pipeline_mediacrawler_runtime_unavailable")
            if asset.platform == Platform.XHS.value and config.xhs_detail_reference_ref is None:
                raise SubscriptionPipelineError("pipeline_xhs_detail_authority_required")
            requires_mediacrawler = True
        if asset.kind in {"video", "audio"}:
            if config.ffprobe_executable is None:
                raise SubscriptionPipelineError("pipeline_media_probe_unavailable")
            requires_media_probe = True

    if requires_mediacrawler:
        try:
            verify_mediacrawler_checkout(
                config.mediacrawler_lock_path,
                license_acknowledged=True,
            )
            if config.mediacrawler_python_executable is None:  # pragma: no cover - guarded above
                raise CheckoutValidationError("MediaCrawler Python runtime is unavailable")
            verify_mediacrawler_python(config.mediacrawler_python_executable)
        except CheckoutValidationError:
            raise SubscriptionPipelineError("pipeline_mediacrawler_runtime_unavailable") from None

    if requires_media_probe and not _ffprobe_ready(config.ffprobe_executable):
        raise SubscriptionPipelineError("pipeline_media_probe_unavailable")


def _ffprobe_ready(executable: str | None) -> bool:
    """Prove a configured ffprobe can start before a child Job is created."""

    if not isinstance(executable, str) or not executable.strip():
        return False
    resolved = shutil.which(executable)
    if resolved is None:
        return False
    try:
        completed = subprocess.run(
            (resolved, "-version"),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _download_request(
    asset: SelectedPipelineAsset,
    *,
    config: LocalPipelineRuntimeConfig,
    worker_id: str,
) -> AssetDownloadRequest:
    return AssetDownloadRequest(
        asset_id=asset.asset_id,
        worker_id=worker_id,
        work_root=config.work_root,
        archive_root=config.archive_root,
        lease_seconds=config.download_lease_seconds,
        max_attempts=config.download_max_attempts,
    )


def _export_request(
    selection: SubscriptionAssetSelection,
    *,
    config: LocalPipelineRuntimeConfig,
    worker_id: str,
) -> EmbyExportRequest:
    return EmbyExportRequest(
        author_id=str(selection.author_id),
        worker_id=worker_id,
        lease_seconds=config.export_lease_seconds,
        max_attempts=config.export_max_attempts,
    )


def _scoped_worker_id(worker_id: str, scope: str) -> str:
    normalized = worker_id.strip()
    if not normalized or any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized):
        raise ValueError("worker_id must be printable")
    candidate = f"{normalized}:{scope}"
    if len(candidate) <= 255:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:16]
    return f"{normalized[:230]}:{scope}:{digest}"[:255]


__all__ = ["LocalPipelineRuntimeConfig", "SubscriptionPipelineExecutor"]
