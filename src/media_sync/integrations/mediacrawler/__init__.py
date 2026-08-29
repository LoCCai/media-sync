"""License-gated external MediaCrawler process integration."""

from .bridge import (
    BridgeConfigurationError,
    BridgeRequest,
    MediaCrawlerBridge,
    MediaCrawlerRunMode,
    MediaCrawlerRunSpec,
    PrivateRunnerInputs,
    RunnerManifest,
)
from .checkout import (
    CheckoutValidationError,
    LicenseAcknowledgementRequired,
    VerifiedCheckout,
    VerifiedPython,
    verify_mediacrawler_checkout,
    verify_mediacrawler_python,
)
from .envelope import MediaCrawlerEnvelope
from .policies import (
    FullHistoryAcknowledgementRequired,
    MediaCrawlerPolicyError,
    OutputInspectionError,
    OutputLimitKind,
    OutputStats,
    WatchdogLimits,
)
from .receipt import (
    CompletionReceipt,
    CompletionReceiptError,
    CompletionReceiptErrorCode,
    CompletionReceiptFile,
    JsonlSnapshotFile,
    ValidatedOutputSnapshot,
    completion_receipt_path,
    load_validated_output_snapshot,
)
from .runner import MediaCrawlerProcessResult, MediaCrawlerProcessRunner, MediaCrawlerProcessStatus

__all__ = [
    "BridgeConfigurationError",
    "BridgeRequest",
    "CheckoutValidationError",
    "CompletionReceipt",
    "CompletionReceiptError",
    "CompletionReceiptErrorCode",
    "CompletionReceiptFile",
    "FullHistoryAcknowledgementRequired",
    "JsonlSnapshotFile",
    "LicenseAcknowledgementRequired",
    "MediaCrawlerBridge",
    "MediaCrawlerEnvelope",
    "MediaCrawlerPolicyError",
    "MediaCrawlerProcessResult",
    "MediaCrawlerProcessRunner",
    "MediaCrawlerProcessStatus",
    "MediaCrawlerRunMode",
    "MediaCrawlerRunSpec",
    "OutputInspectionError",
    "OutputLimitKind",
    "OutputStats",
    "PrivateRunnerInputs",
    "RunnerManifest",
    "ValidatedOutputSnapshot",
    "VerifiedCheckout",
    "VerifiedPython",
    "WatchdogLimits",
    "completion_receipt_path",
    "load_validated_output_snapshot",
    "verify_mediacrawler_checkout",
    "verify_mediacrawler_python",
]
