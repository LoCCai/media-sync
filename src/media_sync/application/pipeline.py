"""Exact-subscription orchestration for download-to-Emby pipelines.

This module intentionally has no scheduler dependency.  A durable worker can
claim whichever coordinator Job it owns and pass the Job's exact subscription
identifier here; restart recovery remains delegated to the existing download
and Emby application services.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from media_sync.application.downloads import AssetDownloadOutcome, AssetDownloadRequest
from media_sync.application.emby import EmbyExportOutcome, EmbyExportRequest
from media_sync.domain import AssetStatus, Platform
from media_sync.infrastructure.db import AssetRefreshSourceRepository, Database, SubscriptionRepository
from media_sync.infrastructure.db.models import Asset, Content
from media_sync.media import AdapterRefreshLocator, MediaDownloadError, parse_locator

_PIPELINE_ERRORS: dict[str, tuple[str, bool]] = {
    "pipeline_subscription_not_found": ("subscription was not found", False),
    "pipeline_subscription_invalid": ("subscription scope is inconsistent", False),
    "pipeline_asset_source_ineligible": ("asset has no current source for this subscription", True),
    "pipeline_download_request_scope_mismatch": ("download request does not target the selected asset", False),
    "pipeline_download_result_scope_mismatch": ("download result does not target the selected asset", False),
    "pipeline_asset_not_verified": ("an asset is not durably verified", True),
    "pipeline_selection_changed": ("subscription assets changed while the pipeline was running", True),
    "pipeline_export_request_scope_mismatch": ("export request does not target the selected author", False),
    "pipeline_mediacrawler_not_enabled": ("MediaCrawler refresh is not enabled for required assets", True),
    "pipeline_mediacrawler_license_required": ("MediaCrawler license acknowledgement is required", True),
    "pipeline_mediacrawler_runtime_unavailable": ("MediaCrawler runtime is unavailable", True),
    "pipeline_xhs_detail_authority_required": ("XHS note detail authority is required", True),
    "pipeline_media_probe_unavailable": ("required local media probe is unavailable", True),
}


class SubscriptionPipelineError(RuntimeError):
    """A fixed-code application error safe for a durable coordinator Job."""

    def __init__(self, code: str) -> None:
        try:
            message, retryable = _PIPELINE_ERRORS[code]
        except KeyError as exc:  # pragma: no cover - programmer error
            raise ValueError("unknown subscription pipeline error code") from exc
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class SubscriptionPipelineRequest:
    """Exact durable coordinator scope needed to re-enumerate a pipeline."""

    subscription_id: UUID
    expected_account_id: UUID
    expected_platform: str

    def __post_init__(self) -> None:
        for name in ("subscription_id", "expected_account_id"):
            value = getattr(self, name)
            try:
                normalized = value if isinstance(value, UUID) else UUID(str(value).strip())
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a UUID") from exc
            object.__setattr__(self, name, normalized)
        try:
            platform = Platform(str(self.expected_platform).strip()).value
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("expected_platform must be a supported platform") from exc
        object.__setattr__(self, "expected_platform", platform)


@dataclass(frozen=True, slots=True)
class SelectedPipelineAsset:
    """Detached identity for one required asset in deterministic pipeline order."""

    asset_id: UUID
    content_id: UUID
    generation: int
    platform: str
    kind: str
    position: int
    status: AssetStatus
    requires_mediacrawler_refresh: bool


@dataclass(frozen=True, slots=True)
class SubscriptionAssetSelection:
    """A transaction-independent exact Subscription/Account/Author snapshot."""

    subscription_id: UUID
    account_id: UUID
    author_id: UUID
    platform: str
    account_adapter: str
    assets: tuple[SelectedPipelineAsset, ...]


@dataclass(frozen=True, slots=True)
class SubscriptionPipelineOutcome:
    """Successful download and export results for one exact subscription."""

    selection: SubscriptionAssetSelection
    downloads: tuple[AssetDownloadOutcome, ...]
    export: EmbyExportOutcome


class AssetDownloadRunner(Protocol):
    """Narrow surface implemented by :class:`AssetDownloadService`."""

    def run(self, request: AssetDownloadRequest) -> AssetDownloadOutcome: ...


class EmbyExportRunner(Protocol):
    """Narrow surface implemented by :class:`EmbyExportService`."""

    def export_author(self, request: EmbyExportRequest) -> EmbyExportOutcome: ...


AssetDownloadRequestFactory = Callable[[SelectedPipelineAsset], AssetDownloadRequest]
EmbyExportRequestFactory = Callable[[SubscriptionAssetSelection], EmbyExportRequest]
SubscriptionSelectionPreflight = Callable[[SubscriptionAssetSelection], None]


class SubscriptionAssetSelector:
    """Select every active asset belonging to one exact subscription author."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def select(self, subscription_id: UUID) -> SubscriptionAssetSelection:
        """Return stable required work, rejecting cross-subscription refresh sources."""

        canonical_subscription_id = str(subscription_id)
        with self._database.session() as session:
            subscription = SubscriptionRepository(session).get(canonical_subscription_id)
            if subscription is None:
                raise SubscriptionPipelineError("pipeline_subscription_not_found")
            account = subscription.account
            author = subscription.author
            if (
                subscription.account_id != account.id
                or subscription.author_id != author.id
                or account.platform != author.platform
            ):
                raise SubscriptionPipelineError("pipeline_subscription_invalid")

            statement = (
                select(Asset)
                .join(Content, Content.id == Asset.content_id)
                .where(
                    Content.author_id == author.id,
                    Content.tombstoned_at.is_(None),
                )
                .options(joinedload(Asset.content))
                .order_by(
                    Content.platform,
                    Content.remote_type,
                    Content.remote_id,
                    Content.id,
                    Asset.kind,
                    Asset.position,
                    Asset.id,
                )
            )
            assets = list(session.scalars(statement).unique().all())
            provenance = AssetRefreshSourceRepository(session)
            selected: list[SelectedPipelineAsset] = []
            for asset in assets:
                content = asset.content
                if asset.platform != content.platform or content.platform != author.platform:
                    raise SubscriptionPipelineError("pipeline_subscription_invalid")
                requires_refresh = self._requires_mediacrawler_refresh(asset)
                if requires_refresh and not any(
                    source.subscription_id == canonical_subscription_id for source in provenance.list_eligible(asset.id)
                ):
                    raise SubscriptionPipelineError("pipeline_asset_source_ineligible")
                try:
                    selected.append(
                        SelectedPipelineAsset(
                            asset_id=UUID(asset.id),
                            content_id=UUID(content.id),
                            generation=asset.generation,
                            platform=asset.platform,
                            kind=asset.kind,
                            position=asset.position,
                            status=AssetStatus(asset.status),
                            requires_mediacrawler_refresh=requires_refresh,
                        )
                    )
                except (TypeError, ValueError):
                    raise SubscriptionPipelineError("pipeline_subscription_invalid") from None

            try:
                return SubscriptionAssetSelection(
                    subscription_id=UUID(subscription.id),
                    account_id=UUID(account.id),
                    author_id=UUID(author.id),
                    platform=author.platform,
                    account_adapter=account.adapter,
                    assets=tuple(selected),
                )
            except (TypeError, ValueError):
                raise SubscriptionPipelineError("pipeline_subscription_invalid") from None

    @staticmethod
    def _requires_mediacrawler_refresh(asset: Asset) -> bool:
        try:
            locator = parse_locator(asset.locator)
        except MediaDownloadError:
            # A malformed object must not shed the provenance requirement just
            # by failing strict parsing.  The downloader still owns its fixed
            # locator error once an exact source exists.
            return asset.locator.get("type") == "adapter_refresh" and asset.locator.get("adapter") == "mediacrawler"
        return isinstance(locator, AdapterRefreshLocator) and locator.adapter == "mediacrawler"


class SubscriptionPipelineService:
    """Sequentially download an exact author snapshot and then export it."""

    def __init__(
        self,
        selector: SubscriptionAssetSelector,
        download_service: AssetDownloadRunner,
        export_service: EmbyExportRunner,
        *,
        download_request_factory: AssetDownloadRequestFactory,
        export_request_factory: EmbyExportRequestFactory,
        selection_preflight: SubscriptionSelectionPreflight | None = None,
    ) -> None:
        self._selector = selector
        self._download_service = download_service
        self._export_service = export_service
        self._download_request_factory = download_request_factory
        self._export_request_factory = export_request_factory
        self._selection_preflight = selection_preflight

    def run(self, request: SubscriptionPipelineRequest) -> SubscriptionPipelineOutcome:
        """Converge durable child services; any download failure skips export."""

        initial = self._selector.select(request.subscription_id)
        if initial.account_id != request.expected_account_id or initial.platform != request.expected_platform:
            # The coordinator's duplicated durable scope is authoritative.
            # Reject mutable Subscription drift before constructing or running
            # any child download request.
            raise SubscriptionPipelineError("pipeline_subscription_invalid")
        if self._selection_preflight is not None:
            self._selection_preflight(initial)
        outcomes: list[AssetDownloadOutcome] = []
        by_asset: dict[UUID, AssetDownloadOutcome] = {}
        for asset in initial.assets:
            download_request = self._download_request_factory(asset)
            if download_request.asset_id != asset.asset_id:
                raise SubscriptionPipelineError("pipeline_download_request_scope_mismatch")
            outcome = self._download_service.run(download_request)
            if outcome.asset_id != asset.asset_id:
                raise SubscriptionPipelineError("pipeline_download_result_scope_mismatch")
            if outcome.status is not AssetStatus.VERIFIED:
                raise SubscriptionPipelineError("pipeline_asset_not_verified")
            outcomes.append(outcome)
            by_asset[asset.asset_id] = outcome

        # Re-read the authoritative scope before export.  This both proves the
        # service results were durably finalized and makes newly ingested or
        # replaced assets a retryable stop instead of publishing a stale tree.
        current = self._selector.select(request.subscription_id)
        if self._context_identity(initial) != self._context_identity(current):
            raise SubscriptionPipelineError("pipeline_selection_changed")
        for asset in current.assets:
            current_outcome = by_asset.get(asset.asset_id)
            if (
                current_outcome is None
                or current_outcome.generation != asset.generation
                or current_outcome.status is not AssetStatus.VERIFIED
                or asset.status is not AssetStatus.VERIFIED
            ):
                raise SubscriptionPipelineError("pipeline_asset_not_verified")

        export_request = self._export_request_factory(current)
        if export_request.author_id != str(current.author_id):
            raise SubscriptionPipelineError("pipeline_export_request_scope_mismatch")
        export_outcome = self._export_service.export_author(export_request)
        return SubscriptionPipelineOutcome(
            selection=current,
            downloads=tuple(outcomes),
            export=export_outcome,
        )

    @staticmethod
    def _context_identity(selection: SubscriptionAssetSelection) -> tuple[UUID, UUID, UUID, str, str]:
        return (
            selection.subscription_id,
            selection.account_id,
            selection.author_id,
            selection.platform,
            selection.account_adapter,
        )


__all__ = [
    "AssetDownloadRequestFactory",
    "AssetDownloadRunner",
    "EmbyExportRequestFactory",
    "EmbyExportRunner",
    "SelectedPipelineAsset",
    "SubscriptionAssetSelection",
    "SubscriptionAssetSelector",
    "SubscriptionPipelineError",
    "SubscriptionPipelineOutcome",
    "SubscriptionPipelineRequest",
    "SubscriptionPipelineService",
    "SubscriptionSelectionPreflight",
]
