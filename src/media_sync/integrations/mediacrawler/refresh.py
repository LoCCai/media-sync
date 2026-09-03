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
    ResolvedDashLocator,
    ResolvedFlvLocator,
    ResolvedFlvSegmentsLocator,
    ResolvedLocator,
    ResolvedMediaTarget,
    ResolvedSegmentsLocator,
)
from media_sync.security import SecretValue

from .bilibili_media import BILIBILI_MAX_PAGES, bilibili_video_cid
from .detail_runner import (
    MediaCrawlerDetailPayloadRunner,
    MediaCrawlerDetailRequest,
    MediaCrawlerDetailResult,
    _is_tieba_detail_reference,
    _is_weibo_detail_reference,
    _is_zhihu_detail_reference,
)
from .normalizers import NormalizationContext, normalize_jsonl_bytes
from .policies import WatchdogLimits
from .tieba_media import TIEBA_MAX_GALLERY_IMAGES, validate_tieba_image_source_hint, validate_tieba_image_url
from .xhs_authority import validate_xhs_creator_reference, validate_xhs_detail_reference
from .xhs_live import XHS_LIVE_MAX_PAIRS
from .xhs_media import validate_xhs_video_url
from .zhihu_media import ZHIHU_MAX_GALLERY_IMAGES, validate_zhihu_image_url

_SUPPORTED_PLATFORMS = frozenset(
    {Platform.XHS, Platform.DY, Platform.KS, Platform.BILI, Platform.WB, Platform.TIEBA, Platform.ZHIHU}
)


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
    bili_video_remote_ids: tuple[str, ...] = field(default=(), repr=False)
    tieba_image_source_hints: tuple[str, ...] = field(default=(), repr=False)
    zhihu_image_source_hints: tuple[str, ...] = field(default=(), repr=False)
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
        if type(self.bili_video_remote_ids) is not tuple:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        bili_video_slot = _is_bili_video_slot(platform, self.content_remote_type, asset_kind)
        bili_video_remote_ids = self.bili_video_remote_ids
        if bili_video_slot:
            legacy_remote_id = f"{self.content_remote_id}:video:0"
            if not bili_video_remote_ids and self.asset_position == 0 and self.asset_remote_id == legacy_remote_id:
                bili_video_remote_ids = (legacy_remote_id,)
            if (
                not 1 <= len(bili_video_remote_ids) <= BILIBILI_MAX_PAGES
                or self.asset_position >= len(bili_video_remote_ids)
                or bili_video_remote_ids[self.asset_position] != self.asset_remote_id
                or len(set(bili_video_remote_ids)) != len(bili_video_remote_ids)
            ):
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            try:
                cids = tuple(
                    bilibili_video_cid(self.content_remote_id, remote_id) for remote_id in bili_video_remote_ids
                )
            except ValueError as exc:
                raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
            if (len(cids) == 1) != (cids == (None,)) or (len(cids) > 1 and any(cid is None for cid in cids)):
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            object.__setattr__(self, "bili_video_remote_ids", bili_video_remote_ids)
        elif bili_video_remote_ids:
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
            video_remote_ids=bili_video_remote_ids,
        )
        if self.source_hint is None:
            if not locator_only_bili_video:
                raise MediaDownloadError("locator_refresh_configuration_invalid")
        elif asset_source_hint(self.source_hint) != self.source_hint:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if bili_video_slot and not locator_only_bili_video:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if platform in _SUPPORTED_PLATFORMS and asset_kind not in _supported_kinds(platform):
            raise MediaDownloadError("locator_refresh_unsupported")
        if not isinstance(self.watchdogs, WatchdogLimits):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if type(self.tieba_image_source_hints) is not tuple:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if type(self.zhihu_image_source_hints) is not tuple:
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
        if platform is Platform.TIEBA:
            if (
                self.content_remote_type != "content"
                or asset_kind is not AssetKind.IMAGE
                or self.asset_position >= TIEBA_MAX_GALLERY_IMAGES
                or self.asset_remote_id != f"{self.content_remote_id}:image:{self.asset_position}"
                or not _is_tieba_detail_reference(self.detail_reference, self.content_remote_id)
            ):
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            source_hint = self.source_hint
            if type(source_hint) is not str:
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            try:
                validate_tieba_image_source_hint(source_hint)
            except ValueError as exc:
                raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
            gallery_hints = self.tieba_image_source_hints
            if not gallery_hints:
                if self.asset_position != 0:
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
                gallery_hints = (source_hint,)
            if not 1 <= len(gallery_hints) <= TIEBA_MAX_GALLERY_IMAGES or self.asset_position >= len(gallery_hints):
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            try:
                for hint in gallery_hints:
                    if type(hint) is not str:
                        raise ValueError
                    validate_tieba_image_source_hint(hint)
            except ValueError as exc:
                raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
            if gallery_hints[self.asset_position] != source_hint or len(set(gallery_hints)) != len(gallery_hints):
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            object.__setattr__(self, "tieba_image_source_hints", gallery_hints)
        elif self.tieba_image_source_hints:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if platform is Platform.ZHIHU:
            if (
                self.content_remote_type != "content"
                or asset_kind is not AssetKind.IMAGE
                or self.asset_remote_id != f"{self.content_remote_id}:image:{self.asset_position}"
                or not _is_zhihu_detail_reference(self.detail_reference, self.content_remote_id)
            ):
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            source_hint = self.source_hint
            if type(source_hint) is not str:
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            try:
                validate_zhihu_image_url(source_hint)
            except ValueError as exc:
                raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
            zhihu_hints = self.zhihu_image_source_hints
            if not zhihu_hints:
                if self.asset_position != 0 or self.asset_remote_id != f"{self.content_remote_id}:image:0":
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
                zhihu_hints = (source_hint,)
            if (
                not 1 <= len(zhihu_hints) <= ZHIHU_MAX_GALLERY_IMAGES
                or self.asset_position >= len(zhihu_hints)
                or zhihu_hints[self.asset_position] != source_hint
                or len(set(zhihu_hints)) != len(zhihu_hints)
            ):
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            try:
                for hint in zhihu_hints:
                    if type(hint) is not str:
                        raise ValueError
                    validate_zhihu_image_url(hint)
            except ValueError as exc:
                raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
            object.__setattr__(self, "zhihu_image_source_hints", zhihu_hints)
        elif self.zhihu_image_source_hints:
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
            video_remote_ids=self.bili_video_remote_ids,
        )

    def _bili_video_cid(self) -> int | None:
        if not self._bili_progressive_detail() or self.asset_remote_id is None:
            return None
        try:
            return bilibili_video_cid(self.content_remote_id, self.asset_remote_id)
        except ValueError as exc:  # pragma: no cover - __post_init__ already fences this
            raise MediaDownloadError("locator_refresh_configuration_invalid") from exc

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
            bili_video_cid=self._bili_video_cid(),
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

    def resolve(self, locator: AdapterRefreshLocator) -> ResolvedMediaTarget:
        """Resolve exactly one current candidate without mutating durable state."""

        context = self._context
        if not isinstance(locator, AdapterRefreshLocator) or locator != context.locator:
            raise MediaDownloadError("locator_refresh_asset_mismatch")
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
        if context.platform is Platform.ZHIHU:
            target = matching_content[0]
            expected_zhihu_hints = context.zhihu_image_source_hints
            if (
                target.content.kind is not ContentKind.ARTICLE
                or target.content.remote_type != "content"
                or target.content.canonical_url != context.detail_reference
                or len(target.assets) != len(expected_zhihu_hints)
                or any(
                    asset.kind is not AssetKind.IMAGE
                    or asset.position != position
                    or asset.remote_id != f"{context.content_remote_id}:image:{position}"
                    or asset_source_hint(asset.source_url) != expected_hint
                    for position, (asset, expected_hint) in enumerate(
                        zip(target.assets, expected_zhihu_hints, strict=True)
                    )
                )
            ):
                raise MediaDownloadError("locator_refresh_schema_changed")
        if context.platform is Platform.TIEBA:
            target = matching_content[0]
            expected_hints = context.tieba_image_source_hints
            if (
                target.content.kind is not ContentKind.ARTICLE
                or target.content.remote_type != "content"
                or target.content.canonical_url != context.detail_reference
                or len(target.assets) != len(expected_hints)
                or any(
                    asset.kind is not AssetKind.IMAGE
                    or asset.position != position
                    or asset.remote_id != f"{context.content_remote_id}:image:{position}"
                    or asset_source_hint(asset.source_url) != expected_hint
                    for position, (asset, expected_hint) in enumerate(zip(target.assets, expected_hints, strict=True))
                )
            ):
                raise MediaDownloadError("locator_refresh_schema_changed")
        if context.platform is Platform.BILI and context._bili_progressive_detail():
            target = matching_content[0]
            videos = tuple(asset for asset in target.assets if asset.kind is AssetKind.VIDEO)
            if (
                target.content.kind is not ContentKind.VIDEO
                or len(videos) != len(context.bili_video_remote_ids)
                or any(
                    asset.position != position or asset.remote_id != expected_remote_id
                    for position, (asset, expected_remote_id) in enumerate(
                        zip(videos, context.bili_video_remote_ids, strict=True)
                    )
                )
            ):
                raise MediaDownloadError("locator_refresh_schema_changed")
        xhs_creator_video = False
        if context.platform is Platform.XHS and context.creator_reference is not None:
            target = matching_content[0]
            envelope = target.content.raw
            source_record = envelope.get("record") if isinstance(envelope, Mapping) else None
            if not isinstance(source_record, Mapping):
                raise MediaDownloadError("locator_refresh_schema_changed")
            source_type = source_record.get("type")
            if source_type == "normal":
                video_assets = tuple(asset for asset in target.assets if asset.kind is AssetKind.VIDEO)
                image_assets = tuple(asset for asset in target.assets if asset.kind is AssetKind.IMAGE)
                if video_assets:
                    # A normal-type note cannot carry a VIDEO asset except through
                    # the live-photo bridge, so the exact shape is unambiguous:
                    # one ordered IMAGE+VIDEO pair per live photo, 1-16 pairs.
                    pair_count = len(video_assets)
                    if (
                        target.content.kind is not ContentKind.MIXED
                        or not 1 <= pair_count <= XHS_LIVE_MAX_PAIRS
                        or len(image_assets) != pair_count
                        or len(target.assets) != 2 * pair_count
                        or any(asset.position != position for position, asset in enumerate(image_assets))
                        or any(asset.position != position for position, asset in enumerate(video_assets))
                        or any(not isinstance(asset.source_url, str) for asset in video_assets)
                    ):
                        raise MediaDownloadError("locator_refresh_schema_changed")
                    try:
                        for asset in video_assets:
                            source_url = asset.source_url
                            if not isinstance(source_url, str):
                                raise ValueError("live source URL is not a string")
                            validate_xhs_video_url(source_url)
                    except ValueError as exc:
                        raise MediaDownloadError("locator_refresh_schema_changed") from exc
                elif (
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
        if context.platform is Platform.ZHIHU:
            try:
                source_url = validate_zhihu_image_url(source_url)
            except ValueError as exc:
                raise MediaDownloadError("locator_refresh_schema_changed") from exc
        if context.platform is Platform.TIEBA:
            try:
                source_url = validate_tieba_image_url(source_url)
            except ValueError as exc:
                raise MediaDownloadError("locator_refresh_schema_changed") from exc
        if context.platform is Platform.BILI and context._bili_progressive_detail():
            runtime_target = matching_content[0].runtime_asset_targets.get(context.asset_remote_id or "")
            if not isinstance(
                runtime_target,
                ResolvedLocator
                | ResolvedFlvLocator
                | ResolvedDashLocator
                | ResolvedSegmentsLocator
                | ResolvedFlvSegmentsLocator,
            ):
                raise MediaDownloadError("locator_refresh_result_invalid")
            if isinstance(runtime_target, ResolvedLocator):
                expected_url = runtime_target.url
            elif isinstance(runtime_target, ResolvedFlvLocator):
                expected_url = runtime_target.source.url
            elif isinstance(runtime_target, ResolvedSegmentsLocator):
                expected_url = runtime_target.segments[0].url
            elif isinstance(runtime_target, ResolvedFlvSegmentsLocator):
                expected_url = runtime_target.source.segments[0].url
            else:
                expected_url = runtime_target.video.url
            if source_url != expected_url:
                raise MediaDownloadError("locator_refresh_result_invalid")
            return runtime_target
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
        Platform.KS: frozenset({AssetKind.VIDEO, AssetKind.COVER, AssetKind.IMAGE}),
        Platform.BILI: frozenset({AssetKind.VIDEO, AssetKind.COVER}),
        Platform.WB: frozenset({AssetKind.IMAGE, AssetKind.VIDEO, AssetKind.COVER}),
        Platform.TIEBA: frozenset({AssetKind.IMAGE}),
        Platform.ZHIHU: frozenset({AssetKind.IMAGE}),
    }.get(platform, frozenset())


def _is_bili_video_slot(
    platform: Platform,
    content_remote_type: str,
    kind: AssetKind,
) -> bool:
    return platform is Platform.BILI and content_remote_type == "content" and kind is AssetKind.VIDEO


def _is_locator_only_bili_video(
    *,
    platform: Platform,
    content_remote_type: str,
    content_remote_id: str,
    asset_remote_id: str | None,
    kind: AssetKind,
    position: int,
    source_hint: str | None,
    video_remote_ids: tuple[str, ...],
) -> bool:
    return (
        _is_bili_video_slot(platform, content_remote_type, kind)
        and 0 <= position < len(video_remote_ids)
        and asset_remote_id == video_remote_ids[position]
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
        or len(video_assets) != len(raw_videos)
        or tuple(asset.position for asset in video_assets) != tuple(range(len(raw_videos)))
        or len(image_assets) > 1
        or (image_assets and image_assets[0].position != 0)
        or len(video_assets) + len(image_assets) != len(assets)
        or tuple(asset.source_url for asset in video_assets) != raw_videos
        or tuple(asset.source_url for asset in image_assets) != raw_images
    ):
        raise MediaDownloadError("locator_refresh_schema_changed")


XHS_MAX_VIDEOS = 16


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
    if not 1 <= len(candidates) <= XHS_MAX_VIDEOS:
        raise ValueError("invalid XHS media scalar")
    return tuple(validate_xhs_video_url(candidate) for candidate in candidates)


__all__ = ["MediaCrawlerLocatorRefresher", "MediaCrawlerRefreshContext"]
