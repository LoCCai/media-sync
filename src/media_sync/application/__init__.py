"""Framework-independent application use cases."""

from media_sync.application.authentication import (
    AccountLoginError,
    AccountLoginOutcome,
    AccountLoginRequest,
    LoginSessionReconciliationSummary,
    MediaCrawlerLoginSessionReconciler,
    MediaCrawlerQrLoginService,
)
from media_sync.application.downloads import (
    ASSET_DOWNLOAD_JOB_TYPE,
    AssetDownloadOrchestrationError,
    AssetDownloadOutcome,
    AssetDownloadRequest,
    AssetDownloadService,
    asset_download_io_scope_fingerprint,
    asset_download_natural_key,
)
from media_sync.application.emby import (
    EMBY_EXPORT_JOB_TYPE,
    EMBY_EXPORTER_NAME,
    EmbyExportOutcome,
    EmbyExportRequest,
    EmbyExportService,
    emby_export_natural_key,
    export_error_is_retryable,
)
from media_sync.application.mediacrawler import (
    MediaCrawlerOutputRejected,
    NormalizedMediaCrawlerOutput,
    load_normalized_output,
)
from media_sync.application.mediacrawler_download import LazyMediaCrawlerLocatorRefresher
from media_sync.application.pipeline import (
    SelectedPipelineAsset,
    SubscriptionAssetSelection,
    SubscriptionAssetSelector,
    SubscriptionPipelineError,
    SubscriptionPipelineOutcome,
    SubscriptionPipelineRequest,
    SubscriptionPipelineService,
    SubscriptionSelectionPreflight,
)
from media_sync.application.pipeline_runtime import (
    LocalPipelineRuntimeConfig,
    SubscriptionPipelineExecutor,
)
from media_sync.application.sync import SyncRequest, SyncResult, SyncService

__all__ = [
    "ASSET_DOWNLOAD_JOB_TYPE",
    "EMBY_EXPORTER_NAME",
    "EMBY_EXPORT_JOB_TYPE",
    "AccountLoginError",
    "AccountLoginOutcome",
    "AccountLoginRequest",
    "AssetDownloadOrchestrationError",
    "AssetDownloadOutcome",
    "AssetDownloadRequest",
    "AssetDownloadService",
    "EmbyExportOutcome",
    "EmbyExportRequest",
    "EmbyExportService",
    "LazyMediaCrawlerLocatorRefresher",
    "LocalPipelineRuntimeConfig",
    "LoginSessionReconciliationSummary",
    "MediaCrawlerLoginSessionReconciler",
    "MediaCrawlerOutputRejected",
    "MediaCrawlerQrLoginService",
    "NormalizedMediaCrawlerOutput",
    "SelectedPipelineAsset",
    "SubscriptionAssetSelection",
    "SubscriptionAssetSelector",
    "SubscriptionPipelineError",
    "SubscriptionPipelineExecutor",
    "SubscriptionPipelineOutcome",
    "SubscriptionPipelineRequest",
    "SubscriptionPipelineService",
    "SubscriptionSelectionPreflight",
    "SyncRequest",
    "SyncResult",
    "SyncService",
    "asset_download_io_scope_fingerprint",
    "asset_download_natural_key",
    "emby_export_natural_key",
    "export_error_is_retryable",
    "load_normalized_output",
]
