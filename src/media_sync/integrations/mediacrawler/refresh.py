"""Context-aware MediaCrawler signed-locator refresh.

Discovery persists only a stable adapter key and a query-free source hint.
This module binds that identity to an exact account/subscription context,
runs one detail lookup and selects the refreshed URL in memory using the same
normalizer as ingestion.  No persistence API is reachable from this layer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from media_sync.domain import AssetKind, AssetSnapshot, ContentKind, LoginMethod, Platform
from media_sync.infrastructure.db.asset_identity import asset_source_hint, stable_asset_key
from media_sync.media import (
    AdapterRefreshLocator,
    MediaDownloadError,
    MediaRequestProfile,
    ResolvedLocator,
)
from media_sync.security import SecretValue

from .detail_runner import (
    MediaCrawlerDetailPayloadRunner,
    MediaCrawlerDetailRequest,
    MediaCrawlerDetailResult,
    _is_weibo_detail_reference,
)
from .normalizers import NormalizationContext, normalize_jsonl_bytes
from .policies import WatchdogLimits
from .xhs_authority import validate_xhs_creator_reference, validate_xhs_detail_reference
from .xhs_media import validate_xhs_video_url

_SUPPORTED_PLATFORMS = frozenset({Platform.XHS, Platform.DY, Platform.KS, Platform.BILI, Platform.WB})
_NO_ASSET_PLATFORMS = frozenset({Platform.TIEBA, Platform.ZHIHU})


@dataclass(frozen=True, slots=True)
class MediaCrawlerRefreshContext:
    """Frozen database/runtime facts needed to refresh exactly one Asset."""

    asset_id: UUID
    account_id: UUID
    subscription_id: UUID
    platform: Platform
    login_method: LoginMethod
    content_remote_type: str
    content_remote_id: str
    author_remote_id: str
    author_display_name: str
    asset_remote_id: str | None
    asset_kind: AssetKind
    asset_position: int
    source_hint: str | None = field(repr=False)
    locator: AdapterRefreshLocator = field(repr=False)
    detail_reference: str | SecretValue | None = field(default=None, repr=False)
    creator_reference: SecretValue | None = field(default=None, repr=False)
    creator_max_items: int | None = None
    cookie: SecretValue | None = field(default=None, repr=False)
    headless: bool = True
    request_delay_seconds: float = 2.0
    watchdogs: WatchdogLimits = field(default_factory=WatchdogLimits)

    def __post_init__(self) -> None:
        if not all(isinstance(value, UUID) for value in (self.asset_id, self.account_id, self.subscription_id)):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        try:
            platform = Platform(self.platform)
            login_method = LoginMethod(self.login_method)
            asset_kind = AssetKind(self.asset_kind)
        except (TypeError, ValueError) as exc:
            raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
        for value in (
            self.content_remote_type,
            self.content_remote_id,
            self.author_remote_id,
            self.author_display_name,
        ):
            _context_text(value)
        if self.asset_remote_id is not None:
            _context_text(self.asset_remote_id, maximum=512)
        if isinstance(self.asset_position, bool) or not isinstance(self.asset_position, int) or self.asset_position < 0:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if not isinstance(self.locator, AdapterRefreshLocator) or self.locator.adapter != "mediacrawler":
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        expected_key = stable_asset_key(
            platform=platform.value,
            content_remote_type=self.content_remote_type,
            content_remote_id=self.content_remote_id,
            kind=asset_kind.value,
            position=self.asset_position,
            remote_id=self.asset_remote_id,
        )
        if self.locator.asset_key != expected_key:
            raise MediaDownloadError("locator_refresh_asset_mismatch")
        locator_only_bili_video = _is_locator_only_bili_video(
            platform=platform,
            content_remote_type=self.content_remote_type,
            content_remote_id=self.content_remote_id,
            asset_remote_id=self.asset_remote_id,
            kind=asset_kind,
            position=self.asset_position,
            source_hint=self.source_hint,
        )
        if self.source_hint is None:
            if not locator_only_bili_video:
                raise MediaDownloadError("locator_refresh_configuration_invalid")
        elif asset_source_hint(self.source_hint) != self.source_hint:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if _is_bili_video_slot(platform, self.content_remote_type, asset_kind, self.asset_position) and not (
            locator_only_bili_video
        ):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if platform in _SUPPORTED_PLATFORMS and asset_kind not in _supported_kinds(platform):
            raise MediaDownloadError("locator_refresh_unsupported")
        if platform is Platform.BILI and asset_kind is AssetKind.VIDEO and self.asset_position != 0:
            raise MediaDownloadError("locator_refresh_unsupported")
        if not isinstance(self.watchdogs, WatchdogLimits):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if platform is Platform.XHS:
            _validate_xhs_authority(
                detail_reference=self.detail_reference,
                creator_reference=self.creator_reference,
                creator_max_items=self.creator_max_items,
                content_remote_id=self.content_remote_id,
                author_remote_id=self.author_remote_id,
                watchdogs=self.watchdogs,
            )
        elif self.creator_reference is not None or self.creator_max_items is not None:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if platform is Platform.WB and not _is_weibo_detail_reference(self.detail_reference, self.content_remote_id):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if login_method is LoginMethod.PHONE:
            raise MediaDownloadError("locator_refresh_unsupported")
        if login_method is LoginMethod.COOKIE and self.cookie is None:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if login_method is not LoginMethod.COOKIE and self.cookie is not None:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if not isinstance(self.headless, bool):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        delay = self.request_delay_seconds
        if isinstance(delay, bool) or not isinstance(delay, int | float) or not 0 < float(delay) <= 60:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        object.__setattr__(self, "platform", platform)
        object.__setattr__(self, "login_method", login_method)
        object.__setattr__(self, "asset_kind", asset_kind)
        object.__setattr__(self, "request_delay_seconds", float(delay))

    def _bili_progressive_detail(self) -> bool:
        return _is_locator_only_bili_video(
            platform=self.platform,
            content_remote_type=self.content_remote_type,
            content_remote_id=self.content_remote_id,
            asset_remote_id=self.asset_remote_id,
            kind=self.asset_kind,
            position=self.asset_position,
            source_hint=self.source_hint,
        )

    def detail_request(self) -> MediaCrawlerDetailRequest:
        """Project only child/runtime facts; discovery metadata stays parent-side."""

        return MediaCrawlerDetailRequest(
            account_id=self.account_id,
            subscription_id=self.subscription_id,
            platform=self.platform,
            login_method=self.login_method,
            content_remote_id=self.content_remote_id,
            author_remote_id=self.author_remote_id,
            detail_reference=self.detail_reference,
            creator_reference=self.creator_reference,
            creator_max_items=self.creator_max_items,
            cookie=self.cookie,
            headless=self.headless,
            request_delay_seconds=self.request_delay_seconds,
            bili_progressive_detail=self._bili_progressive_detail(),
            watchdogs=self.watchdogs,
        )


class MediaCrawlerLocatorRefresher:
    """A bound ``LocatorRefreshPort`` for one immutable Asset generation."""

    def __init__(
        self,
        context: MediaCrawlerRefreshContext,
        runner: MediaCrawlerDetailPayloadRunner,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._context = context
        self._runner = runner
        self._clock = clock or (lambda: datetime.now(UTC))

    def resolve(self, locator: AdapterRefreshLocator) -> ResolvedLocator:
        """Resolve exactly one current candidate without mutating durable state."""

        context = self._context
        if not isinstance(locator, AdapterRefreshLocator) or locator != context.locator:
            raise MediaDownloadError("locator_refresh_asset_mismatch")
        if context.platform in _NO_ASSET_PLATFORMS:
            # These pinned normalizers emit no Asset, so spawning detail work
            # cannot produce a valid locator.
            raise MediaDownloadError("locator_refresh_unsupported")
        if context.platform not in _SUPPORTED_PLATFORMS:
            raise MediaDownloadError("locator_refresh_unsupported")

        try:
            result = self._runner.run(context.detail_request())
        except MediaDownloadError:
            raise
        except Exception as exc:
            raise MediaDownloadError("locator_refresh_result_invalid") from exc
        if not isinstance(result, MediaCrawlerDetailResult):
            raise MediaDownloadError("locator_refresh_result_invalid")
        try:
            batch = normalize_jsonl_bytes(
                result.jsonl,
                NormalizationContext(
                    platform=context.platform,
                    upstream_sha=result.upstream_sha,
                    creator_remote_id=context.author_remote_id,
                    creator_display_name=context.author_display_name,
                    ingested_at=self._clock(),
                    allow_bili_progressive_detail=context._bili_progressive_detail(),
                ),
                max_bytes=context.watchdogs.max_output_bytes,
                max_line_bytes=context.watchdogs.max_line_bytes,
                max_records=context.watchdogs.max_output_items,
            )
        except Exception as exc:
            if isinstance(exc, MediaDownloadError):
                raise
            raise MediaDownloadError("locator_refresh_result_invalid") from exc
        if batch.truncated_tail or batch.quarantined:
            raise MediaDownloadError("locator_refresh_schema_changed")
        if not batch.records:
            raise MediaDownloadError("locator_refresh_asset_not_found")

        matching_content = [
            record
            for record in batch.records
            if record.content.platform is context.platform
            and record.content.remote_type == context.content_remote_type
            and record.content.remote_id == context.content_remote_id
        ]
        if not matching_content:
            raise MediaDownloadError("locator_refresh_asset_not_found")
        if len(matching_content) != 1:
            raise MediaDownloadError("locator_refresh_asset_mismatch")
        xhs_creator_video = False
        if context.platform is Platform.XHS and context.creator_reference is not None:
            target = matching_content[0]
            envelope = target.content.raw
            source_record = envelope.get("record") if isinstance(envelope, Mapping) else None
            if not isinstance(source_record, Mapping):
                raise MediaDownloadError("locator_refresh_schema_changed")
            source_type = source_record.get("type")
            if source_type == "normal":
                if (
                    target.content.kind not in {ContentKind.IMAGE, ContentKind.GALLERY}
                    or not target.assets
                    or any(asset.kind is not AssetKind.IMAGE for asset in target.assets)
                ):
                    raise MediaDownloadError("locator_refresh_schema_changed")
            elif source_type == "video":
                _validate_xhs_creator_video_target(source_record, target.assets, target.content.kind)
                xhs_creator_video = True
            else:
                raise MediaDownloadError("locator_refresh_schema_changed")
        candidates = [
            asset
            for record in matching_content
            for asset in record.assets
            if asset.remote_id == context.asset_remote_id
            and asset.kind is context.asset_kind
            and asset.position == context.asset_position
            and (context._bili_progressive_detail() or asset_source_hint(asset.source_url) == context.source_hint)
        ]
        if len(candidates) != 1:
            raise MediaDownloadError("locator_refresh_asset_mismatch")
        source_url = candidates[0].source_url
        if source_url is None:
            raise MediaDownloadError("locator_refresh_result_invalid")
        if xhs_creator_video and candidates[0].kind is AssetKind.VIDEO:
            try:
                source_url = validate_xhs_video_url(source_url)
            except ValueError as exc:
                raise MediaDownloadError("locator_refresh_schema_changed") from exc
        profile = (
            MediaRequestProfile.BILIBILI_MEDIA if context._bili_progressive_detail() else MediaRequestProfile.DEFAULT
        )
        try:
            return ResolvedLocator(source_url, profile)
        except MediaDownloadError as exc:
            raise MediaDownloadError("locator_refresh_result_invalid") from exc


def _supported_kinds(platform: Platform) -> frozenset[AssetKind]:
    return {
        Platform.XHS: frozenset({AssetKind.IMAGE, AssetKind.VIDEO}),
        Platform.DY: frozenset({AssetKind.IMAGE, AssetKind.VIDEO, AssetKind.AUDIO, AssetKind.COVER}),
        Platform.KS: frozenset({AssetKind.VIDEO, AssetKind.COVER}),
        Platform.BILI: frozenset({AssetKind.VIDEO, AssetKind.COVER}),
        Platform.WB: frozenset({AssetKind.IMAGE}),
    }.get(platform, frozenset())


def _is_bili_video_slot(
    platform: Platform,
    content_remote_type: str,
    kind: AssetKind,
    position: int,
) -> bool:
    return platform is Platform.BILI and content_remote_type == "content" and kind is AssetKind.VIDEO and position == 0


def _is_locator_only_bili_video(
    *,
    platform: Platform,
    content_remote_type: str,
    content_remote_id: str,
    asset_remote_id: str | None,
    kind: AssetKind,
    position: int,
    source_hint: str | None,
) -> bool:
    return (
        _is_bili_video_slot(platform, content_remote_type, kind, position)
        and asset_remote_id == f"{content_remote_id}:video:0"
        and source_hint is None
    )


def _context_text(value: object, *, maximum: int = 255) -> str:
    if not isinstance(value, str):
        raise MediaDownloadError("locator_refresh_configuration_invalid")
    normalized = value.strip()
    if not normalized or normalized != value or len(normalized) > maximum:
        raise MediaDownloadError("locator_refresh_configuration_invalid")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized):
        raise MediaDownloadError("locator_refresh_configuration_invalid")
    return normalized


def _validate_xhs_authority(
    *,
    detail_reference: object,
    creator_reference: object,
    creator_max_items: object,
    content_remote_id: str,
    author_remote_id: str,
    watchdogs: WatchdogLimits,
) -> None:
    try:
        if detail_reference is not None:
            if not isinstance(detail_reference, SecretValue):
                raise ValueError
            if creator_reference is not None or creator_max_items is not None:
                raise ValueError
            validate_xhs_detail_reference(detail_reference.reveal(), content_remote_id)
            return
        if not isinstance(creator_reference, SecretValue):
            raise ValueError
        if type(creator_max_items) is not int or not 1 <= creator_max_items <= 1_000:
            raise ValueError
        if creator_max_items > watchdogs.max_output_items:
            raise ValueError
        validate_xhs_creator_reference(creator_reference.reveal(), author_remote_id)
    except ValueError as exc:
        raise MediaDownloadError("locator_refresh_configuration_invalid") from exc


def _validate_xhs_creator_video_target(
    source_record: Mapping[str, object],
    assets: tuple[AssetSnapshot, ...],
    content_kind: ContentKind,
) -> None:
    """Freeze the pinned store's scalar video row before trusting Assets."""

    try:
        raw_videos = _validated_xhs_media_scalar(source_record.get("video_url"), allow_empty=False)
        raw_images = _validated_xhs_media_scalar(source_record.get("image_list"), allow_empty=True)
    except ValueError as exc:
        raise MediaDownloadError("locator_refresh_schema_changed") from exc

    video_assets = tuple(asset for asset in assets if asset.kind is AssetKind.VIDEO)
    image_assets = tuple(asset for asset in assets if asset.kind is AssetKind.IMAGE)
    if (
        content_kind not in {ContentKind.VIDEO, ContentKind.MIXED}
        or (not raw_images and content_kind is not ContentKind.VIDEO)
        or (len(raw_images) == 1 and content_kind is not ContentKind.MIXED)
        or len(video_assets) != 1
        or video_assets[0].position != 0
        or len(image_assets) > 1
        or (image_assets and image_assets[0].position != 0)
        or len(video_assets) + len(image_assets) != len(assets)
        or tuple(asset.source_url for asset in video_assets) != raw_videos
        or tuple(asset.source_url for asset in image_assets) != raw_images
    ):
        raise MediaDownloadError("locator_refresh_schema_changed")


def _validated_xhs_media_scalar(value: object, *, allow_empty: bool) -> tuple[str, ...]:
    if type(value) is not str:
        raise ValueError("invalid XHS media scalar")
    if value == "":
        if allow_empty:
            return ()
        raise ValueError("invalid XHS media scalar")
    candidates = value.split(",")
    if any(not candidate or candidate.strip() != candidate for candidate in candidates):
        raise ValueError("invalid XHS media scalar")
    if len(set(candidates)) != len(candidates):
        raise ValueError("invalid XHS media scalar")
    if len(candidates) != 1:
        raise ValueError("invalid XHS media scalar")
    return tuple(validate_xhs_video_url(candidate) for candidate in candidates)


__all__ = ["MediaCrawlerLocatorRefresher", "MediaCrawlerRefreshContext"]
