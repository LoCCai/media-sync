from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from media_sync.domain import AssetKind, LoginMethod, Platform
from media_sync.infrastructure.db.asset_identity import asset_source_hint, stable_asset_key
from media_sync.integrations.mediacrawler.bilibili_media import (
    BILIBILI_DASH_PAGE_FIELD,
    BILIBILI_PAGES_FIELD,
    BILIBILI_PROGRESSIVE_BACKUPS_FIELD,
    BILIBILI_PROGRESSIVE_FORMAT_FIELD,
    BILIBILI_PROGRESSIVE_PAGE_FIELD,
    BILIBILI_PROGRESSIVE_SEGMENTS_FIELD,
)
from media_sync.integrations.mediacrawler.detail_runner import (
    MediaCrawlerDetailRequest,
    MediaCrawlerDetailResult,
)
from media_sync.integrations.mediacrawler.policies import WatchdogLimits
from media_sync.integrations.mediacrawler.refresh import (
    MediaCrawlerLocatorRefresher,
    MediaCrawlerRefreshContext,
)
from media_sync.integrations.mediacrawler.tieba_media import (
    TIEBA_GALLERY_FIELD,
    TIEBA_IMAGE_FIELD,
    TIEBA_IMAGES_FIELD,
    TIEBA_MAX_GALLERY_IMAGES,
)
from media_sync.integrations.mediacrawler.weibo_media import (
    WEIBO_IMAGES_FIELD,
    WEIBO_VIDEO_FIELD,
    validate_weibo_video_url,
)
from media_sync.integrations.mediacrawler.xhs_media import validate_xhs_video_url
from media_sync.integrations.mediacrawler.zhihu_media import ZHIHU_IMAGE_FIELD
from media_sync.media import (
    AdapterRefreshLocator,
    MediaDownloadError,
    MediaRequestProfile,
    ResolvedDashLocator,
    ResolvedFlvLocator,
    ResolvedFlvSegmentsLocator,
    ResolvedLocator,
    ResolvedSegmentsLocator,
)
from media_sync.security import SecretValue

UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
ASSET_ID = UUID("11111111-1111-4111-8111-111111111111")
ACCOUNT_ID = UUID("22222222-2222-4222-8222-222222222222")
SUBSCRIPTION_ID = UUID("33333333-3333-4333-8333-333333333333")
NOW = datetime(2026, 8, 31, tzinfo=UTC)


@dataclass
class _FakeDetailRunner:
    payload: bytes
    calls: list[MediaCrawlerDetailRequest] = field(default_factory=list)

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        self.calls.append(request)
        return MediaCrawlerDetailResult(self.payload, UPSTREAM_SHA)


def _jsonl(*records: dict[str, object]) -> bytes:
    return b"".join(
        (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode() for record in records
    )


def _context(
    *,
    platform: Platform,
    content_id: str,
    kind: AssetKind,
    position: int,
    signed_url: str | None,
    content_remote_type: str = "content",
    remote_id: str | None = None,
    detail_reference: str | SecretValue | None = None,
    creator_reference: SecretValue | None = None,
    creator_max_items: int | None = None,
    locator: AdapterRefreshLocator | None = None,
    bili_video_remote_ids: tuple[str, ...] = (),
    tieba_image_source_hints: tuple[str, ...] = (),
) -> MediaCrawlerRefreshContext:
    active_remote_id = remote_id or f"{content_id}:{kind.value}:{position}"
    active_locator = locator or AdapterRefreshLocator(
        adapter="mediacrawler",
        asset_key=stable_asset_key(
            platform=platform.value,
            content_remote_type=content_remote_type,
            content_remote_id=content_id,
            kind=kind.value,
            position=position,
            remote_id=active_remote_id,
        ),
    )
    source_hint = asset_source_hint(signed_url)
    return MediaCrawlerRefreshContext(
        asset_id=ASSET_ID,
        account_id=ACCOUNT_ID,
        subscription_id=SUBSCRIPTION_ID,
        platform=platform,
        login_method=LoginMethod.QR,
        content_remote_type=content_remote_type,
        content_remote_id=content_id,
        author_remote_id="creator-42",
        author_display_name="Fixture creator",
        asset_remote_id=active_remote_id,
        asset_kind=kind,
        asset_position=position,
        source_hint=source_hint,
        locator=active_locator,
        bili_video_remote_ids=bili_video_remote_ids,
        tieba_image_source_hints=tieba_image_source_hints,
        detail_reference=detail_reference,
        creator_reference=creator_reference,
        creator_max_items=creator_max_items,
        watchdogs=WatchdogLimits(
            max_seconds=5,
            max_output_bytes=64 * 1024,
            max_output_items=10,
            max_output_files=4,
            max_line_bytes=16 * 1024,
            poll_seconds=0.01,
        ),
    )


@pytest.mark.parametrize(
    ("platform", "content_id", "kind", "position", "signed_url", "record"),
    [
        (
            Platform.DY,
            "7525082444551310602",
            AssetKind.IMAGE,
            0,
            "https://i.example.test/dy/photo.jpg?sign=dy-image-sentinel",
            {
                "aweme_id": "7525082444551310602",
                "title": "photo",
                "desc": "photo",
                "note_download_url": "https://i.example.test/dy/photo.jpg?sign=dy-image-sentinel",
                "video_download_url": "https://v.example.test/dy/ignored.mp4?sign=dy-video-sentinel",
                "cover_url": "https://i.example.test/dy/cover.jpg?sign=dy-cover-sentinel",
            },
        ),
        (
            Platform.DY,
            "7525082444551310602",
            AssetKind.VIDEO,
            0,
            "https://v.example.test/dy/main.mp4?sign=dy-video-sentinel",
            {
                "aweme_id": "7525082444551310602",
                "title": "video",
                "desc": "video",
                "video_download_url": "https://v.example.test/dy/main.mp4?sign=dy-video-sentinel",
                "music_download_url": "https://a.example.test/dy/music.mp3?sign=dy-audio-sentinel",
                "cover_url": "https://i.example.test/dy/cover.jpg?sign=dy-cover-sentinel",
            },
        ),
        (
            Platform.DY,
            "7525082444551310602",
            AssetKind.AUDIO,
            0,
            "https://a.example.test/dy/music.mp3?sign=dy-audio-sentinel",
            {
                "aweme_id": "7525082444551310602",
                "title": "video",
                "desc": "video",
                "video_download_url": "https://v.example.test/dy/main.mp4?sign=dy-video-sentinel",
                "music_download_url": "https://a.example.test/dy/music.mp3?sign=dy-audio-sentinel",
                "cover_url": "https://i.example.test/dy/cover.jpg?sign=dy-cover-sentinel",
            },
        ),
        (
            Platform.DY,
            "7525082444551310602",
            AssetKind.COVER,
            0,
            "https://i.example.test/dy/cover.jpg?sign=dy-cover-sentinel",
            {
                "aweme_id": "7525082444551310602",
                "title": "video",
                "desc": "video",
                "video_download_url": "https://v.example.test/dy/main.mp4?sign=dy-video-sentinel",
                "cover_url": "https://i.example.test/dy/cover.jpg?sign=dy-cover-sentinel",
            },
        ),
        (
            Platform.KS,
            "3x3zxz4mjrsc8ke",
            AssetKind.VIDEO,
            0,
            "https://v.example.test/ks/main.mp4?auth=ks-video-sentinel",
            {
                "video_id": "3x3zxz4mjrsc8ke",
                "title": "video",
                "desc": "video",
                "video_url": "https://www.kuaishou.com/short-video/3x3zxz4mjrsc8ke",
                "video_play_url": "https://v.example.test/ks/main.mp4?auth=ks-video-sentinel",
                "video_cover_url": "https://i.example.test/ks/cover.jpg?auth=ks-cover-sentinel",
            },
        ),
        (
            Platform.KS,
            "3x3zxz4mjrsc8ke",
            AssetKind.COVER,
            0,
            "https://i.example.test/ks/cover.jpg?auth=ks-cover-sentinel",
            {
                "video_id": "3x3zxz4mjrsc8ke",
                "title": "video",
                "desc": "video",
                "video_url": "https://www.kuaishou.com/short-video/3x3zxz4mjrsc8ke",
                "video_play_url": "https://v.example.test/ks/main.mp4?auth=ks-video-sentinel",
                "video_cover_url": "https://i.example.test/ks/cover.jpg?auth=ks-cover-sentinel",
            },
        ),
        (
            Platform.BILI,
            "987654321",
            AssetKind.COVER,
            0,
            "https://i.example.test/bili/cover.jpg@672w?token=bili-cover-sentinel",
            {
                "video_id": "987654321",
                "video_type": "video",
                "title": "video",
                "desc": "video",
                "video_url": "https://www.bilibili.com/video/av987654321",
                "video_cover_url": "https://i.example.test/bili/cover.jpg@672w?token=bili-cover-sentinel",
            },
        ),
        (
            Platform.WB,
            "5123456789012345",
            AssetKind.IMAGE,
            1,
            "https://i1.wp.com/wx2.sinaimg.cn/large/weibo-second.jpg",
            {
                "note_id": "5123456789012345",
                "content": "two images",
                WEIBO_IMAGES_FIELD: [
                    {
                        "pid": "weibo-first",
                        "url": "https://i1.wp.com/wx1.sinaimg.cn/large/weibo-first.jpg",
                    },
                    {
                        "pid": "weibo-second",
                        "url": "https://i1.wp.com/wx2.sinaimg.cn/large/weibo-second.jpg",
                    },
                ],
            },
        ),
    ],
)
def test_bound_refresher_selects_exact_normalized_asset_in_memory(
    platform: Platform,
    content_id: str,
    kind: AssetKind,
    position: int,
    signed_url: str,
    record: dict[str, object],
) -> None:
    context = _context(
        platform=platform,
        content_id=content_id,
        kind=kind,
        position=position,
        signed_url=signed_url,
    )
    runner = _FakeDetailRunner(_jsonl(record))
    refresher = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW)

    resolved = refresher.resolve(context.locator)

    assert resolved.url == signed_url
    assert len(runner.calls) == 1
    assert runner.calls[0].platform is platform
    assert runner.calls[0].content_remote_id == content_id
    assert resolved.request_profile is MediaRequestProfile.DEFAULT
    assert "sentinel" not in repr(resolved)
    assert "sentinel" not in repr(context)


@pytest.mark.parametrize("drift", ["reordered", "duplicate-pid"])
def test_weibo_refresh_requires_exact_ordered_identity_and_source_hint(drift: str) -> None:
    first_url = "https://i1.wp.com/wx1.sinaimg.cn/large/weibo-first.jpg"
    second_url = "https://i1.wp.com/wx2.sinaimg.cn/large/weibo-second.jpg"
    images = [
        {"pid": "weibo-first", "url": first_url},
        {"pid": "weibo-second", "url": second_url},
    ]
    if drift == "reordered":
        images.reverse()
    else:
        images[1]["pid"] = images[0]["pid"]
    context = _context(
        platform=Platform.WB,
        content_id="5123456789012345",
        kind=AssetKind.IMAGE,
        position=1,
        signed_url=second_url,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "note_id": "5123456789012345",
                "content": "two images",
                WEIBO_IMAGES_FIELD: images,
            }
        )
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == "locator_refresh_asset_mismatch"
    assert len(runner.calls) == 1


def test_weibo_refresh_context_accepts_only_image_and_video_assets() -> None:
    with pytest.raises(MediaDownloadError) as caught:
        _context(
            platform=Platform.WB,
            content_id="5123456789012345",
            kind=AssetKind.AUDIO,
            position=0,
            signed_url="https://f.us.sinaimg.cn/o0/not-audio.mp4?KID=unistore,video",
        )

    assert caught.value.code == "locator_refresh_unsupported"

    video_context = _context(
        platform=Platform.WB,
        content_id="5123456789012345",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url="https://f.us.sinaimg.cn/o0/weibo-video.mp4?KID=unistore,video&Expires=4102444800",
    )
    assert video_context.detail_request().platform is Platform.WB


def test_weibo_refresh_context_accepts_exact_plain_detail_reference() -> None:
    content_id = "5123456789012345"
    context = _context(
        platform=Platform.WB,
        content_id=content_id,
        kind=AssetKind.IMAGE,
        position=0,
        signed_url="https://i1.wp.com/wx1.sinaimg.cn/large/weibo-first.jpg",
        detail_reference=content_id,
    )

    assert context.detail_request().resolved_detail_reference() == content_id


@pytest.mark.parametrize(
    "detail_reference",
    ["5123456789012346", SecretValue("5123456789012345")],
)
def test_weibo_refresh_context_rejects_mismatched_or_secret_detail_reference(
    detail_reference: str | SecretValue,
) -> None:
    with pytest.raises(MediaDownloadError) as caught:
        _context(
            platform=Platform.WB,
            content_id="5123456789012345",
            kind=AssetKind.IMAGE,
            position=0,
            signed_url="https://i1.wp.com/wx1.sinaimg.cn/large/weibo-first.jpg",
            detail_reference=detail_reference,
        )

    assert caught.value.code == "locator_refresh_configuration_invalid"


def test_bilibili_locator_only_video_uses_private_detail_gate_and_media_profile() -> None:
    signed_url = "https://v.example.test/bili/first.mp4?" + "signature=private-sentinel"
    backup_url = "https://backup.example.test/bili/first.mp4?signature=backup-private-sentinel"
    context = _context(
        platform=Platform.BILI,
        content_id="987654321",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=None,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": "987654321",
                "video_type": "video",
                "title": "video",
                "video_cover_url": "https://i.example.test/bili/cover.jpg",
                "__media_sync_bili_progressive_url": signed_url,
                BILIBILI_PROGRESSIVE_BACKUPS_FIELD: [backup_url],
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert resolved.url == signed_url
    assert resolved.backup_urls == (backup_url,)
    assert resolved.request_profile is MediaRequestProfile.BILIBILI_MEDIA
    assert runner.calls[0].bili_progressive_detail is True
    assert "private-sentinel" not in repr(resolved)


def test_bilibili_primary_only_progressive_bridge_remains_compatible() -> None:
    signed_url = "https://v.example.test/bili/legacy.mp4?signature=legacy-private"
    context = _context(
        platform=Platform.BILI,
        content_id="987654321",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=None,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": "987654321",
                "video_type": "video",
                "title": "legacy primary-only video",
                "__media_sync_bili_progressive_url": signed_url,
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert resolved.urls == (signed_url,)


def test_bilibili_single_page_flv_marker_reconstructs_typed_ephemeral_target() -> None:
    signed_url = "https://v.example.test/bili/source.flv?signature=flv-private"
    backup_url = "https://backup.example.test/bili/source.flv?signature=backup-private"
    context = _context(
        platform=Platform.BILI,
        content_id="987654321",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=None,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": "987654321",
                "video_type": "video",
                "title": "single-page FLV",
                "__media_sync_bili_progressive_url": signed_url,
                BILIBILI_PROGRESSIVE_BACKUPS_FIELD: [backup_url],
                BILIBILI_PROGRESSIVE_FORMAT_FIELD: "flv",
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert isinstance(resolved, ResolvedFlvLocator)
    assert resolved.source.urls == (signed_url, backup_url)
    assert resolved.source.request_profile is MediaRequestProfile.BILIBILI_MEDIA
    assert "private" not in repr(resolved)


def test_bilibili_multipart_flv_marker_reconstructs_only_requested_page() -> None:
    content_id = "987654321"
    remote_ids = (
        f"{content_id}:video:cid:24680",
        f"{content_id}:video:cid:97531",
    )
    signed_url = "https://v.example.test/bili/p2.flv?signature=flv-private"
    context = _context(
        platform=Platform.BILI,
        content_id=content_id,
        kind=AssetKind.VIDEO,
        position=1,
        signed_url=None,
        remote_id=remote_ids[1],
        bili_video_remote_ids=remote_ids,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": content_id,
                "video_type": "video",
                "title": "multipart FLV",
                BILIBILI_PAGES_FIELD: [
                    {"page": 1, "cid": 24680},
                    {"page": 2, "cid": 97531},
                ],
                BILIBILI_PROGRESSIVE_PAGE_FIELD: {
                    "cid": 97531,
                    "url": signed_url,
                    "format": "flv",
                },
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert isinstance(resolved, ResolvedFlvLocator)
    assert resolved.source.urls == (signed_url,)
    assert runner.calls[0].bili_video_cid == 97531


@pytest.mark.parametrize(
    "private_fields",
    [
        {BILIBILI_PROGRESSIVE_FORMAT_FIELD: "flv"},
        {
            "__media_sync_bili_progressive_url": "https://v.example.test/bili/source.mp4",
            BILIBILI_PROGRESSIVE_FORMAT_FIELD: "mp4",
        },
        {
            "__media_sync_bili_progressive_url": "https://v.example.test/bili/source.flv",
            BILIBILI_PROGRESSIVE_FORMAT_FIELD: True,
        },
    ],
)
def test_bilibili_single_page_flv_marker_fails_closed_when_orphaned_or_malformed(
    private_fields: dict[str, object],
) -> None:
    context = _context(
        platform=Platform.BILI,
        content_id="987654321",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=None,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": "987654321",
                "video_type": "video",
                "title": "invalid FLV marker",
                **private_fields,
            }
        )
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == "locator_refresh_schema_changed"


@pytest.mark.parametrize(
    "backup_value",
    [
        "https://backup.example.test/not-a-list.mp4",
        [42],
        ["https://v.example.test/bili/main.mp4?signature=private"],
        ["https://backup.example.test/duplicate.mp4"] * 2,
        [f"https://backup-{index}.example.test/video.mp4" for index in range(9)],
    ],
)
def test_bilibili_single_page_progressive_bridge_rejects_invalid_backup_shapes(backup_value: object) -> None:
    signed_url = "https://v.example.test/bili/main.mp4?signature=private"
    context = _context(
        platform=Platform.BILI,
        content_id="987654321",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=None,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": "987654321",
                "video_type": "video",
                "title": "invalid progressive backups",
                "__media_sync_bili_progressive_url": signed_url,
                BILIBILI_PROGRESSIVE_BACKUPS_FIELD: backup_value,
            }
        )
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == "locator_refresh_schema_changed"
    assert "backup.example.test" not in str(caught.value)


def test_bilibili_multipart_refresh_targets_one_cid_and_binds_the_complete_page_tuple() -> None:
    content_id = "987654321"
    remote_ids = (
        f"{content_id}:video:cid:24680",
        f"{content_id}:video:cid:97531",
        f"{content_id}:video:cid:86420",
    )
    signed_url = "https://v.example.test/bili/p2.mp4?signature=private-p2-sentinel"
    backup_url = "https://backup.example.test/bili/p2.mp4?signature=backup-p2-sentinel"
    context = _context(
        platform=Platform.BILI,
        content_id=content_id,
        kind=AssetKind.VIDEO,
        position=1,
        signed_url=None,
        remote_id=remote_ids[1],
        bili_video_remote_ids=remote_ids,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": content_id,
                "video_type": "video",
                "title": "three pages",
                BILIBILI_PAGES_FIELD: [
                    {"page": 1, "cid": 24680},
                    {"page": 2, "cid": 97531},
                    {"page": 3, "cid": 86420},
                ],
                BILIBILI_PROGRESSIVE_PAGE_FIELD: {
                    "cid": 97531,
                    "url": signed_url,
                    "backup_urls": [backup_url],
                },
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert resolved.url == signed_url
    assert resolved.backup_urls == (backup_url,)
    assert resolved.request_profile is MediaRequestProfile.BILIBILI_MEDIA
    assert runner.calls[0].bili_progressive_detail is True
    assert runner.calls[0].bili_video_cid == 97531


def test_bilibili_dash_refresh_returns_one_typed_ephemeral_target() -> None:
    content_id = "987654321"
    remote_ids = (
        f"{content_id}:video:cid:24680",
        f"{content_id}:video:cid:97531",
    )
    context = _context(
        platform=Platform.BILI,
        content_id=content_id,
        kind=AssetKind.VIDEO,
        position=1,
        signed_url=None,
        remote_id=remote_ids[1],
        bili_video_remote_ids=remote_ids,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": content_id,
                "video_type": "video",
                "title": "two-page DASH",
                BILIBILI_PAGES_FIELD: [
                    {"page": 1, "cid": 24680},
                    {"page": 2, "cid": 97531},
                ],
                BILIBILI_DASH_PAGE_FIELD: {
                    "cid": 97531,
                    "video": {
                        "url": "https://v.example.test/p2.m4s?signature=dash-video-private",
                        "backup_urls": ["https://backup.example.test/p2.m4s?signature=backup-private"],
                        "quality": 120,
                        "codec": "avc",
                    },
                    "audio": {
                        "url": "https://a.example.test/p2.m4s?signature=dash-audio-private",
                        "backup_urls": [],
                        "quality": 30251,
                    },
                },
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert isinstance(resolved, ResolvedDashLocator)
    assert resolved.selection_key == (120, "avc", 30251)
    assert resolved.video.request_profile is MediaRequestProfile.BILIBILI_MEDIA
    assert resolved.audio is not None
    assert resolved.audio.request_profile is MediaRequestProfile.BILIBILI_MEDIA
    assert "private" not in repr(resolved)
    assert runner.calls[0].bili_video_cid == 97531


@pytest.mark.parametrize(
    "pages",
    [
        [{"page": 1, "cid": 24680}, {"page": 2, "cid": 97531}],
        [
            {"page": 1, "cid": 97531},
            {"page": 2, "cid": 24680},
            {"page": 3, "cid": 86420},
        ],
        [
            {"page": 1, "cid": 24680},
            {"page": 2, "cid": 11111},
            {"page": 3, "cid": 86420},
        ],
        [
            {"page": 1, "cid": 24680},
            {"page": 2, "cid": 97531},
            {"page": 3, "cid": 86420},
            {"page": 4, "cid": 75310},
        ],
    ],
)
def test_bilibili_multipart_refresh_rejects_missing_reordered_replaced_or_added_pages(
    pages: list[dict[str, int]],
) -> None:
    content_id = "987654321"
    remote_ids = (
        f"{content_id}:video:cid:24680",
        f"{content_id}:video:cid:97531",
        f"{content_id}:video:cid:86420",
    )
    context = _context(
        platform=Platform.BILI,
        content_id=content_id,
        kind=AssetKind.VIDEO,
        position=1,
        signed_url=None,
        remote_id=remote_ids[1],
        bili_video_remote_ids=remote_ids,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": content_id,
                "video_type": "video",
                "title": "drifted pages",
                BILIBILI_PAGES_FIELD: pages,
                BILIBILI_PROGRESSIVE_PAGE_FIELD: {
                    "cid": 97531,
                    "url": "https://v.example.test/bili/p2.mp4?signature=drift",
                },
            }
        )
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == "locator_refresh_schema_changed"


def test_bilibili_locator_only_video_requires_the_private_progressive_result() -> None:
    context = _context(
        platform=Platform.BILI,
        content_id="987654321",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=None,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": "987654321",
                "video_type": "video",
                "title": "video",
                "video_cover_url": "https://i.example.test/bili/cover.jpg",
            }
        )
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == "locator_refresh_result_invalid"


def test_bilibili_progressive_video_rejects_a_non_null_persisted_source_hint() -> None:
    with pytest.raises(MediaDownloadError) as caught:
        _context(
            platform=Platform.BILI,
            content_id="987654321",
            kind=AssetKind.VIDEO,
            position=0,
            signed_url="https://v.example.test/bili/first.mp4?signature=must-not-persist",
        )

    assert caught.value.code == "locator_refresh_configuration_invalid"


@pytest.mark.parametrize(
    ("platform", "kind", "position", "remote_type", "remote_id"),
    [
        (Platform.BILI, AssetKind.COVER, 0, "content", "987654321:cover:0"),
        (Platform.BILI, AssetKind.VIDEO, 1, "content", "987654321:video:1"),
        (Platform.BILI, AssetKind.VIDEO, 0, "dynamic", "987654321:video:0"),
        (Platform.BILI, AssetKind.VIDEO, 0, "content", "wrong-video-slot"),
        (Platform.DY, AssetKind.VIDEO, 0, "content", "987654321:video:0"),
    ],
)
def test_missing_source_hint_is_closed_to_the_exact_bilibili_video_slot(
    platform: Platform,
    kind: AssetKind,
    position: int,
    remote_type: str,
    remote_id: str,
) -> None:
    with pytest.raises(MediaDownloadError) as caught:
        _context(
            platform=platform,
            content_id="987654321",
            kind=kind,
            position=position,
            signed_url=None,
            content_remote_type=remote_type,
            remote_id=remote_id,
        )

    assert caught.value.code in {
        "locator_refresh_configuration_invalid",
        "locator_refresh_unsupported",
    }


def test_xhs_requires_explicit_secret_detail_reference_and_uses_it() -> None:
    signed = "https://i.example.test/xhs/photo.jpg?sign=xhs-image-sentinel"
    with pytest.raises(MediaDownloadError) as missing:
        _context(
            platform=Platform.XHS,
            content_id="66fad51c000000001b0224b8",
            kind=AssetKind.IMAGE,
            position=0,
            signed_url=signed,
        )
    assert missing.value.code == "locator_refresh_configuration_invalid"

    detail_url = SecretValue(
        "https://www.xiaohongshu.com/explore/66fad51c000000001b0224b8?xsec_token=xhs-detail-secret&xsec_source=pc_feed"
    )
    context = _context(
        platform=Platform.XHS,
        content_id="66fad51c000000001b0224b8",
        kind=AssetKind.IMAGE,
        position=0,
        signed_url=signed,
        detail_reference=detail_url,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "note_id": "66fad51c000000001b0224b8",
                "type": "normal",
                "title": "photo",
                "desc": "photo",
                "image_list": signed,
            }
        )
    )

    assert MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator).url == signed
    assert runner.calls[0].resolved_detail_reference() == detail_url.reveal()
    assert "xhs-detail-secret" not in repr(runner.calls[0])

    video_signed = "https://v.example.test/xhs/video.mp4?sign=xhs-video-sentinel"
    video_context = _context(
        platform=Platform.XHS,
        content_id="66fad51c000000001b0224b8",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=video_signed,
        detail_reference=detail_url,
    )
    video_runner = _FakeDetailRunner(
        _jsonl(
            {
                "note_id": "66fad51c000000001b0224b8",
                "type": "video",
                "title": "video",
                "desc": "video",
                "video_url": video_signed,
            }
        )
    )
    assert (
        MediaCrawlerLocatorRefresher(video_context, video_runner, clock=lambda: NOW).resolve(video_context.locator).url
        == video_signed
    )


def test_xhs_creator_authority_returns_multiple_records_and_selects_exact_note() -> None:
    content_id = "66fad51c000000001b0224b8"
    signed = "https://i.example.test/xhs/photo.jpg?sign=xhs-creator-image-sentinel"
    creator = SecretValue(
        "https://www.xiaohongshu.com/user/profile/creator-42?xsec_token=xhs-creator-secret&xsec_source=pc_user"
    )
    context = _context(
        platform=Platform.XHS,
        content_id=content_id,
        kind=AssetKind.IMAGE,
        position=0,
        signed_url=signed,
        creator_reference=creator,
        creator_max_items=2,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "note_id": "different-note",
                "type": "normal",
                "title": "other",
                "image_list": "https://i.example.test/xhs/other.jpg?sign=other",
            },
            {
                "note_id": content_id,
                "type": "normal",
                "title": "target",
                "image_list": signed,
            },
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    request = runner.calls[0]
    assert resolved.url == signed
    assert request.detail_reference is None
    assert request.resolved_detail_reference() is None
    assert request.resolved_creator_reference() == creator.reveal()
    assert request.creator_max_items == 2
    assert "xhs-creator-secret" not in repr(context)
    assert "xhs-creator-secret" not in repr(request)


@pytest.mark.parametrize(
    "image_list",
    [
        pytest.param("", id="video-only"),
        pytest.param(
            "https://sns-webpic-qc.xhscdn.com/cover.png?sign=xhs-cover-sentinel",
            id="optional-cover",
        ),
    ],
)
def test_xhs_creator_authority_accepts_one_cdn_video_with_optional_cover(image_list: str) -> None:
    content_id = "66fad51c000000001b0224b8"
    video_url = "http://sns-video-bd.xhscdn.com/video-key.mp4?sign=xhs-video-sentinel"
    context = _context(
        platform=Platform.XHS,
        content_id=content_id,
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=video_url,
        creator_reference=SecretValue(
            "https://www.xiaohongshu.com/user/profile/creator-42?xsec_token=xhs-creator-secret&xsec_source=pc_user"
        ),
        creator_max_items=2,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "note_id": content_id,
                "type": "video",
                "title": "target video",
                "image_list": image_list,
                "video_url": video_url,
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert resolved.url == video_url
    assert resolved.request_profile is MediaRequestProfile.DEFAULT
    assert "xhs-video-sentinel" not in repr(resolved)


@pytest.mark.parametrize(
    ("video_url", "image_list"),
    [
        pytest.param(
            "file:///invalid,http://sns-video-bd.xhscdn.com/target.mp4",
            "",
            id="malformed-plus-valid-video",
        ),
        pytest.param(
            "http://sns-video-bd.xhscdn.com/target.mp4,http://sns-video-bd.xhscdn.com/target.mp4",
            "",
            id="duplicate-video",
        ),
        pytest.param("http://sns-video-bd.xhscdn.com/target.mp4,", "", id="empty-video-item"),
        pytest.param("", "", id="empty-video"),
        pytest.param(" http://sns-video-bd.xhscdn.com/target.mp4", "", id="leading-video-space"),
        pytest.param("http://sns-video-bd.xhscdn.com/target.mp4 ", "", id="trailing-video-space"),
        pytest.param(
            "http://sns-video-bd.xhscdn.com/target.mp4",
            "https://sns-webpic-qc.xhscdn.com/first.jpg,https://sns-webpic-qc.xhscdn.com/second.jpg",
            id="multiple-images",
        ),
        pytest.param(
            "http://sns-video-bd.xhscdn.com/target.mp4",
            "file:///invalid,https://sns-webpic-qc.xhscdn.com/cover.jpg",
            id="malformed-plus-valid-image",
        ),
        pytest.param(
            "http://sns-video-bd.xhscdn.com/target.mp4",
            "https://sns-webpic-qc.xhscdn.com/cover.jpg,https://sns-webpic-qc.xhscdn.com/cover.jpg",
            id="duplicate-image",
        ),
        pytest.param(
            "http://sns-video-bd.xhscdn.com/target.mp4",
            "https://sns-webpic-qc.xhscdn.com/cover.jpg,",
            id="empty-image-item",
        ),
        pytest.param(
            "http://sns-video-bd.xhscdn.com/target.mp4",
            "https://foreign.example/cover.jpg",
            id="foreign-image-host",
        ),
        pytest.param(None, "", id="non-string-video"),
        pytest.param("http://sns-video-bd.xhscdn.com/target.mp4", None, id="non-string-image"),
        pytest.param(
            ["http://sns-video-bd.xhscdn.com/target.mp4"],
            "",
            id="video-container-drift",
        ),
        pytest.param(
            "http://sns-video-bd.xhscdn.com/target.mp4",
            ["https://sns-webpic-qc.xhscdn.com/cover.jpg"],
            id="image-container-drift",
        ),
    ],
)
def test_xhs_creator_video_gate_rejects_ambiguous_raw_scalars(
    video_url: object,
    image_list: object,
) -> None:
    content_id = "66fad51c000000001b0224b8"
    selected = "http://sns-video-bd.xhscdn.com/target.mp4"
    context = _context(
        platform=Platform.XHS,
        content_id=content_id,
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=selected,
        creator_reference=SecretValue(
            "https://www.xiaohongshu.com/user/profile/creator-42?xsec_token=xhs-creator-secret&xsec_source=pc_user"
        ),
        creator_max_items=2,
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(
            context,
            _FakeDetailRunner(
                _jsonl(
                    {
                        "note_id": content_id,
                        "type": "video",
                        "image_list": image_list,
                        "video_url": video_url,
                    }
                )
            ),
            clock=lambda: NOW,
        ).resolve(context.locator)

    assert caught.value.code == "locator_refresh_schema_changed"


@pytest.mark.parametrize(
    "url",
    [
        "http://sns-video-bd.xhscdn.com/video-key",
        "http://xhscdn.com:80/video-key?sign=private",
        "https://xhscdn.com:443/video-key?sign=private",
        "HTTPS://SNS-VIDEO-BD.XHSCDN.COM./video-key?sign=private",
        "https://例子.xhscdn.com/video-key?sign=private",
        f"https://{'e' * 63}.xhscdn.com/video-key",
    ],
)
def test_xhs_video_url_validator_accepts_only_bounded_cdn_paths(url: str) -> None:
    assert validate_xhs_video_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("", id="empty"),
        pytest.param("https://xhscdn.com/video key", id="whitespace"),
        pytest.param("https://xhscdn.com/video\tkey", id="control"),
        pytest.param("ftp://xhscdn.com/video", id="scheme"),
        pytest.param("https://user@xhscdn.com/video", id="userinfo"),
        pytest.param("https://xhscdn.com:444/video", id="custom-port"),
        pytest.param("https://xhscdn.com:80/video", id="https-http-port"),
        pytest.param("http://xhscdn.com:443/video", id="http-https-port"),
        pytest.param("https://xhscdn.com/video#private-fragment", id="fragment"),
        pytest.param("https://xhscdn.com", id="empty-path"),
        pytest.param("https://xhscdn.com/", id="root-path"),
        pytest.param("https://foreign.example/video", id="foreign-host"),
        pytest.param("https://notxhscdn.com/video", id="suffix-confusion"),
        pytest.param("https://[2001:db8::1]/video", id="ipv6-host"),
        pytest.param("https://-edge.xhscdn.com/video", id="leading-label-hyphen"),
        pytest.param("https://edge-.xhscdn.com/video", id="trailing-label-hyphen"),
        pytest.param("https://edge_name.xhscdn.com/video", id="label-underscore"),
        pytest.param(f"https://{'e' * 64}.xhscdn.com/video", id="overlong-label"),
        pytest.param(
            f"https://{'.'.join(['e' * 63] * 4)}.xhscdn.com/video",
            id="overlong-hostname",
        ),
        pytest.param("https://xhscdn.com../video", id="multiple-trailing-dots"),
        pytest.param("https://xhscdn.com:invalid/video", id="malformed-port"),
        pytest.param("https://%65vil.xhscdn.com/video", id="escaped-host"),
        pytest.param("https://xhscdn.com/" + "v" * 4_096, id="over-bound"),
    ],
)
def test_xhs_video_url_validator_rejects_ambiguous_or_foreign_values(url: str) -> None:
    with pytest.raises(ValueError, match="invalid XHS video URL"):
        validate_xhs_video_url(url)


def test_xhs_video_url_validator_rejects_idna_errors_and_non_exact_strings() -> None:
    with pytest.raises(ValueError, match="invalid XHS video URL"):
        validate_xhs_video_url("https://\ud800.xhscdn.com/video")
    with pytest.raises(ValueError, match="invalid XHS video URL"):
        validate_xhs_video_url(True)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "target_record",
    [
        {
            "note_id": "66fad51c000000001b0224b8",
            "type": "video",
            "title": "nonordinary image",
            "image_list": "https://i.example.test/xhs/photo.jpg?sign=xhs-creator-image-sentinel",
        },
        {
            "note_id": "66fad51c000000001b0224b8",
            "type": "normal",
            "title": "mixed media",
            "image_list": "https://i.example.test/xhs/photo.jpg?sign=xhs-creator-image-sentinel",
            "video_url": "https://v.example.test/xhs/video.mp4?sign=xhs-creator-video-sentinel",
        },
    ],
    ids=["nonordinary-type", "mixed-media"],
)
def test_xhs_creator_authority_rejects_nonordinary_or_nonstatic_target(
    target_record: dict[str, object],
) -> None:
    content_id = "66fad51c000000001b0224b8"
    signed = "https://i.example.test/xhs/photo.jpg?sign=xhs-creator-image-sentinel"
    context = _context(
        platform=Platform.XHS,
        content_id=content_id,
        kind=AssetKind.IMAGE,
        position=0,
        signed_url=signed,
        creator_reference=SecretValue(
            "https://www.xiaohongshu.com/user/profile/creator-42?xsec_token=xhs-creator-secret&xsec_source=pc_user"
        ),
        creator_max_items=2,
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(
            context,
            _FakeDetailRunner(_jsonl(target_record)),
            clock=lambda: NOW,
        ).resolve(context.locator)

    assert caught.value.code == "locator_refresh_schema_changed"


def test_refresh_rejects_duplicate_target_content_before_asset_matching() -> None:
    content_id = "66fad51c000000001b0224b8"
    signed = "https://i.example.test/xhs/photo.jpg?sign=xhs-creator-image-sentinel"
    context = _context(
        platform=Platform.XHS,
        content_id=content_id,
        kind=AssetKind.IMAGE,
        position=0,
        signed_url=signed,
        creator_reference=SecretValue(
            "https://www.xiaohongshu.com/user/profile/creator-42?xsec_token=xhs-creator-secret&xsec_source=pc_user"
        ),
        creator_max_items=2,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "note_id": content_id,
                "type": "normal",
                "image_list": "https://i.example.test/xhs/other.jpg?sign=other",
            },
            {
                "note_id": content_id,
                "type": "normal",
                "image_list": signed,
            },
        )
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == "locator_refresh_asset_mismatch"


@pytest.mark.parametrize(
    ("creator", "maximum", "detail"),
    [
        (
            "http://www.xiaohongshu.com/user/profile/creator-42?xsec_token=t&xsec_source=s",
            2,
            None,
        ),
        (
            "https://www.xiaohongshu.com/user/profile/wrong?xsec_token=t&xsec_source=s",
            2,
            None,
        ),
        (
            "https://www.xiaohongshu.com/user/profile/creator-42?xsec_token=t&xsec_token=u&xsec_source=s",
            2,
            None,
        ),
        (
            "https://www.xiaohongshu.com/user/profile/creator-42?xsec_token=t&xsec_source=s",
            11,
            None,
        ),
        (
            "https://www.xiaohongshu.com/user/profile/creator-42?xsec_token=t&xsec_source=s",
            2,
            SecretValue("https://www.xiaohongshu.com/explore/66fad51c000000001b0224b8?xsec_token=t&xsec_source=s"),
        ),
    ],
)
def test_xhs_creator_authority_rejects_invalid_or_ambiguous_inputs(
    creator: str,
    maximum: int,
    detail: SecretValue | None,
) -> None:
    with pytest.raises(MediaDownloadError, match="locator_refresh_configuration_invalid"):
        _context(
            platform=Platform.XHS,
            content_id="66fad51c000000001b0224b8",
            kind=AssetKind.IMAGE,
            position=0,
            signed_url="https://i.example.test/xhs/photo.jpg?sign=fixture",
            detail_reference=detail,
            creator_reference=SecretValue(creator),
            creator_max_items=maximum,
        )


def test_tieba_refresh_uses_canonical_thread_authority_and_exact_current_image() -> None:
    content_id = "10376710029"
    canonical_url = f"https://tieba.baidu.com/p/{content_id}"
    identity = "489c9a3df8dcd1009420153b348b4710b8122fc3"
    previous_url = f"https://tiebapic.baidu.com/forum/pic/item/{identity}.jpg?tbpicau=2026-09-02-17_previous"
    current_url = f"https://tiebapic.baidu.com/forum/pic/item/{identity}.jpg?tbpicau=2026-09-02-17_current"
    context = _context(
        platform=Platform.TIEBA,
        content_id=content_id,
        kind=AssetKind.IMAGE,
        position=0,
        signed_url=previous_url,
        detail_reference=canonical_url,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "note_id": content_id,
                "title": "fixture",
                "desc": "fixture body",
                "note_url": canonical_url,
                TIEBA_IMAGE_FIELD: current_url,
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert resolved.url == current_url
    assert resolved.request_profile is MediaRequestProfile.DEFAULT
    assert len(runner.calls) == 1
    assert runner.calls[0].resolved_detail_reference() == canonical_url


@pytest.mark.parametrize("position", [0, 1])
def test_tieba_refresh_revalidates_complete_ordered_two_image_gallery(position: int) -> None:
    content_id = "10376710029"
    canonical_url = f"https://tieba.baidu.com/p/{content_id}"
    identities = (
        "489c9a3df8dcd1009420153b348b4710b8122fc3",
        "0123456789abcdef0123456789abcdef01234567",
    )
    hints = tuple(f"https://tiebapic.baidu.com/forum/pic/item/{identity}.jpg" for identity in identities)
    previous = tuple(f"{hint}?tbpicau=2026-09-02-17_previous_{index}" for index, hint in enumerate(hints))
    current = tuple(f"{hint}?tbpicau=2026-09-02-17_current_{index}" for index, hint in enumerate(hints))
    context = _context(
        platform=Platform.TIEBA,
        content_id=content_id,
        kind=AssetKind.IMAGE,
        position=position,
        signed_url=previous[position],
        detail_reference=canonical_url,
        tieba_image_source_hints=hints,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "note_id": content_id,
                "title": "fixture",
                "desc": "fixture body",
                "note_url": canonical_url,
                TIEBA_IMAGES_FIELD: list(current),
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert resolved == ResolvedLocator(current[position], MediaRequestProfile.DEFAULT)
    assert runner.calls[0].resolved_detail_reference() == canonical_url


@pytest.mark.parametrize("position", [0, 1, 2])
def test_tieba_refresh_revalidates_complete_ordered_v3_gallery(position: int) -> None:
    content_id = "10376710029"
    canonical_url = f"https://tieba.baidu.com/p/{content_id}"
    hints = tuple(f"https://tiebapic.baidu.com/forum/pic/item/{index + 1:040x}.jpg" for index in range(3))
    previous = tuple(f"{hint}?tbpicau=2026-09-02-17_previous_{index}" for index, hint in enumerate(hints))
    current = tuple(f"{hint}?tbpicau=2026-09-02-17_current_{index}" for index, hint in enumerate(hints))
    context = _context(
        platform=Platform.TIEBA,
        content_id=content_id,
        kind=AssetKind.IMAGE,
        position=position,
        signed_url=previous[position],
        detail_reference=canonical_url,
        tieba_image_source_hints=hints,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "note_id": content_id,
                "title": "fixture",
                "desc": "fixture body",
                "note_url": canonical_url,
                TIEBA_GALLERY_FIELD: list(current),
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert resolved == ResolvedLocator(current[position], MediaRequestProfile.DEFAULT)
    assert runner.calls[0].resolved_detail_reference() == canonical_url


@pytest.mark.parametrize("drift", ["reordered", "replacement", "missing", "added", "duplicate", "dual-claim"])
def test_tieba_v3_refresh_rejects_complete_gallery_drift(drift: str) -> None:
    content_id = "10376710029"
    canonical_url = f"https://tieba.baidu.com/p/{content_id}"
    hints = tuple(f"https://tiebapic.baidu.com/forum/pic/item/{index + 1:040x}.jpg" for index in range(3))
    current = [f"{hint}?tbpicau=2026-09-02-17_current_{index}" for index, hint in enumerate(hints)]
    replacement = (
        "https://tiebapic.baidu.com/forum/pic/item/"
        "abcdef0123456789abcdef0123456789abcdef01.jpg?tbpicau=2026-09-02-17_replaced"
    )
    record: dict[str, object] = {
        "note_id": content_id,
        "title": "fixture",
        "desc": "fixture body",
        "note_url": canonical_url,
    }
    if drift == "reordered":
        record[TIEBA_GALLERY_FIELD] = [current[1], current[0], current[2]]
    elif drift == "replacement":
        record[TIEBA_GALLERY_FIELD] = [current[0], current[1], replacement]
    elif drift == "missing":
        record[TIEBA_IMAGES_FIELD] = current[:2]
    elif drift == "added":
        record[TIEBA_GALLERY_FIELD] = [*current, replacement]
    elif drift == "duplicate":
        record[TIEBA_GALLERY_FIELD] = [current[0], current[1], current[0].replace("current_0", "changed")]
    else:
        record[TIEBA_GALLERY_FIELD] = current
        record[TIEBA_IMAGES_FIELD] = current[:2]
    context = _context(
        platform=Platform.TIEBA,
        content_id=content_id,
        kind=AssetKind.IMAGE,
        position=2,
        signed_url=current[2],
        detail_reference=canonical_url,
        tieba_image_source_hints=hints,
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, _FakeDetailRunner(_jsonl(record)), clock=lambda: NOW).resolve(
            context.locator
        )

    assert caught.value.code == "locator_refresh_schema_changed"


@pytest.mark.parametrize("drift", ["reordered", "replacement", "missing", "dual-claim"])
def test_tieba_two_image_refresh_rejects_complete_gallery_drift(drift: str) -> None:
    content_id = "10376710029"
    canonical_url = f"https://tieba.baidu.com/p/{content_id}"
    hints = (
        "https://tiebapic.baidu.com/forum/pic/item/489c9a3df8dcd1009420153b348b4710b8122fc3.jpg",
        "https://tiebapic.baidu.com/forum/pic/item/0123456789abcdef0123456789abcdef01234567.jpg",
    )
    current = [f"{hint}?tbpicau=2026-09-02-17_current_{index}" for index, hint in enumerate(hints)]
    record: dict[str, object] = {
        "note_id": content_id,
        "title": "fixture",
        "desc": "fixture body",
        "note_url": canonical_url,
    }
    if drift == "reordered":
        record[TIEBA_IMAGES_FIELD] = list(reversed(current))
    elif drift == "replacement":
        replacement = (
            "https://tiebapic.baidu.com/forum/pic/item/"
            "abcdef0123456789abcdef0123456789abcdef01.jpg?tbpicau=2026-09-02-17_replaced"
        )
        record[TIEBA_IMAGES_FIELD] = [current[0], replacement]
    elif drift == "missing":
        record[TIEBA_IMAGE_FIELD] = current[0]
    else:
        record[TIEBA_IMAGES_FIELD] = current
        record[TIEBA_IMAGE_FIELD] = current[0]
    context = _context(
        platform=Platform.TIEBA,
        content_id=content_id,
        kind=AssetKind.IMAGE,
        position=0,
        signed_url=current[0],
        detail_reference=canonical_url,
        tieba_image_source_hints=hints,
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, _FakeDetailRunner(_jsonl(record)), clock=lambda: NOW).resolve(
            context.locator
        )

    assert caught.value.code == "locator_refresh_schema_changed"


@pytest.mark.parametrize(
    ("position", "hints"),
    [
        (1, ()),
        (1, ("https://tiebapic.baidu.com/forum/pic/item/0123456789abcdef0123456789abcdef01234567.jpg",)),
        (
            0,
            (
                "https://tiebapic.baidu.com/forum/pic/item/489c9a3df8dcd1009420153b348b4710b8122fc3.jpg",
                "https://tiebapic.baidu.com/forum/pic/item/489c9a3df8dcd1009420153b348b4710b8122fc3.jpg",
            ),
        ),
    ],
)
def test_tieba_refresh_context_rejects_unbound_or_duplicate_gallery(position: int, hints: tuple[str, ...]) -> None:
    content_id = "10376710029"
    selected_hint = (
        "https://tiebapic.baidu.com/forum/pic/item/489c9a3df8dcd1009420153b348b4710b8122fc3.jpg"
        if position == 0
        else "https://tiebapic.baidu.com/forum/pic/item/0123456789abcdef0123456789abcdef01234567.jpg"
    )
    with pytest.raises(MediaDownloadError) as caught:
        _context(
            platform=Platform.TIEBA,
            content_id=content_id,
            kind=AssetKind.IMAGE,
            position=position,
            signed_url=f"{selected_hint}?tbpicau=2026-09-02-17_previous",
            detail_reference=f"https://tieba.baidu.com/p/{content_id}",
            tieba_image_source_hints=hints,
        )

    assert caught.value.code == "locator_refresh_configuration_invalid"


def test_tieba_refresh_context_accepts_64_hints_and_rejects_65() -> None:
    content_id = "10376710029"
    hints = tuple(
        f"https://tiebapic.baidu.com/forum/pic/item/{index + 1:040x}.jpg"
        for index in range(TIEBA_MAX_GALLERY_IMAGES + 1)
    )
    accepted = _context(
        platform=Platform.TIEBA,
        content_id=content_id,
        kind=AssetKind.IMAGE,
        position=TIEBA_MAX_GALLERY_IMAGES - 1,
        signed_url=f"{hints[TIEBA_MAX_GALLERY_IMAGES - 1]}?tbpicau=2026-09-02-17_previous",
        detail_reference=f"https://tieba.baidu.com/p/{content_id}",
        tieba_image_source_hints=hints[:TIEBA_MAX_GALLERY_IMAGES],
    )
    assert len(accepted.tieba_image_source_hints) == TIEBA_MAX_GALLERY_IMAGES

    with pytest.raises(MediaDownloadError) as caught:
        _context(
            platform=Platform.TIEBA,
            content_id=content_id,
            kind=AssetKind.IMAGE,
            position=0,
            signed_url=f"{hints[0]}?tbpicau=2026-09-02-17_previous",
            detail_reference=f"https://tieba.baidu.com/p/{content_id}",
            tieba_image_source_hints=hints,
        )

    assert caught.value.code == "locator_refresh_configuration_invalid"


def test_zhihu_refresh_uses_canonical_answer_authority_and_exact_current_image() -> None:
    answer_id = "987654321"
    answer_url = f"https://www.zhihu.com/question/246810/answer/{answer_id}"
    previous_url = "https://picx.zhimg.com/v2-answer.jpg?source=previous"
    current_url = "https://picx.zhimg.com/v2-answer.jpg?source=current"
    context = _context(
        platform=Platform.ZHIHU,
        content_id=answer_id,
        kind=AssetKind.IMAGE,
        position=0,
        signed_url=previous_url,
        detail_reference=answer_url,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "content_id": answer_id,
                "content_type": "answer",
                "content_text": "answer body",
                "question_id": "246810",
                "content_url": answer_url,
                ZHIHU_IMAGE_FIELD: current_url,
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert resolved.url == current_url
    assert resolved.request_profile is MediaRequestProfile.DEFAULT
    assert runner.calls[0].resolved_detail_reference() == answer_url
    assert type(runner.calls[0].detail_reference) is str


@pytest.mark.parametrize(
    "detail_reference",
    [
        None,
        SecretValue("https://www.zhihu.com/question/246810/answer/987654321"),
        "https://www.zhihu.com/question/246810/answer/987654322",
        "https://www.zhihu.com/question/246810/answer/987654321?",
        "https://www.zhihu.com/question/246811/answer/987654321?utm_source=drift",
        "http://www.zhihu.com/question/246810/answer/987654321",
    ],
)
def test_zhihu_refresh_rejects_missing_secret_or_noncanonical_detail_authority(
    detail_reference: str | SecretValue | None,
) -> None:
    with pytest.raises(MediaDownloadError) as caught:
        _context(
            platform=Platform.ZHIHU,
            content_id="987654321",
            kind=AssetKind.IMAGE,
            position=0,
            signed_url="https://picx.zhimg.com/v2-answer.jpg?source=previous",
            detail_reference=detail_reference,
        )

    assert caught.value.code == "locator_refresh_configuration_invalid"


@pytest.mark.parametrize(
    ("kind", "position", "remote_type", "remote_id"),
    [
        (AssetKind.VIDEO, 0, "content", "987654321:video:0"),
        (AssetKind.IMAGE, 1, "content", "987654321:image:1"),
        (AssetKind.IMAGE, 0, "answer", "987654321:image:0"),
        (AssetKind.IMAGE, 0, "content", "987654321:image:other"),
    ],
)
def test_zhihu_refresh_context_closes_the_single_answer_image_slot(
    kind: AssetKind,
    position: int,
    remote_type: str,
    remote_id: str,
) -> None:
    with pytest.raises(MediaDownloadError) as caught:
        _context(
            platform=Platform.ZHIHU,
            content_id="987654321",
            kind=kind,
            position=position,
            content_remote_type=remote_type,
            remote_id=remote_id,
            signed_url="https://picx.zhimg.com/v2-answer.jpg?source=previous",
            detail_reference="https://www.zhihu.com/question/246810/answer/987654321",
        )

    assert caught.value.code in {"locator_refresh_configuration_invalid", "locator_refresh_unsupported"}


@pytest.mark.parametrize(
    "persisted_hint",
    [
        "https://evil.example/v2-answer.jpg?source=previous",
        "https://picx.zhimg.com/v2-answer.jpg?",
    ],
    ids=["foreign-host", "empty-query-delimiter"],
)
def test_zhihu_refresh_context_rejects_invalid_persisted_hint_before_runner(persisted_hint: str) -> None:
    valid = _context(
        platform=Platform.ZHIHU,
        content_id="987654321",
        kind=AssetKind.IMAGE,
        position=0,
        signed_url="https://picx.zhimg.com/v2-answer.jpg",
        detail_reference="https://www.zhihu.com/question/246810/answer/987654321",
    )

    with pytest.raises(MediaDownloadError) as caught:
        replace(valid, source_hint=persisted_hint)

    assert caught.value.code == "locator_refresh_configuration_invalid"


@pytest.mark.parametrize(
    "drift",
    ["missing-image", "source-hint", "canonical-url", "duplicate-content", "empty-query-delimiter"],
)
def test_zhihu_refresh_rejects_missing_drifted_or_duplicate_target(drift: str) -> None:
    answer_id = "987654321"
    answer_url = f"https://www.zhihu.com/question/246810/answer/{answer_id}"
    previous_url = "https://picx.zhimg.com/v2-answer.jpg?source=previous"
    base: dict[str, object] = {
        "content_id": answer_id,
        "content_type": "answer",
        "content_text": "answer body",
        "question_id": "246810",
        "content_url": answer_url,
    }
    if drift != "missing-image":
        if drift == "source-hint":
            base[ZHIHU_IMAGE_FIELD] = "https://picx.zhimg.com/v2-different.jpg?source=current"
        elif drift == "empty-query-delimiter":
            base[ZHIHU_IMAGE_FIELD] = "https://picx.zhimg.com/v2-answer.jpg?"
        else:
            base[ZHIHU_IMAGE_FIELD] = "https://picx.zhimg.com/v2-answer.jpg?source=current"
    if drift == "canonical-url":
        base["question_id"] = "246811"
        base["content_url"] = f"https://www.zhihu.com/question/246811/answer/{answer_id}"
    payload = _jsonl(base, base) if drift == "duplicate-content" else _jsonl(base)
    context = _context(
        platform=Platform.ZHIHU,
        content_id=answer_id,
        kind=AssetKind.IMAGE,
        position=0,
        signed_url=previous_url,
        detail_reference=answer_url,
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, _FakeDetailRunner(payload), clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == (
        "locator_refresh_asset_mismatch" if drift == "duplicate-content" else "locator_refresh_schema_changed"
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"", "locator_refresh_asset_not_found"),
        (_jsonl({"unknown": True}), "locator_refresh_schema_changed"),
        (
            _jsonl(
                {
                    "aweme_id": "different-content",
                    "video_download_url": "https://v.example.test/dy/main.mp4?sign=secret",
                }
            ),
            "locator_refresh_asset_not_found",
        ),
        (
            _jsonl(
                {
                    "aweme_id": "7525082444551310602",
                    "video_download_url": "https://v.example.test/dy/different.mp4?sign=secret",
                }
            ),
            "locator_refresh_asset_mismatch",
        ),
    ],
)
def test_refresh_failures_use_fixed_codes_without_echo(payload: bytes, expected: str) -> None:
    signed = "https://v.example.test/dy/main.mp4?sign=private-sentinel"
    context = _context(
        platform=Platform.DY,
        content_id="7525082444551310602",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=signed,
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, _FakeDetailRunner(payload), clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == expected
    assert "private-sentinel" not in str(caught.value)


def test_duplicate_candidate_and_wrong_bound_locator_fail_closed() -> None:
    signed = "https://v.example.test/dy/main.mp4?sign=private-sentinel"
    record = {"aweme_id": "7525082444551310602", "video_download_url": signed}
    context = _context(
        platform=Platform.DY,
        content_id="7525082444551310602",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=signed,
    )
    runner = _FakeDetailRunner(_jsonl(record, record))
    refresher = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW)

    with pytest.raises(MediaDownloadError, match="locator_refresh_asset_mismatch"):
        refresher.resolve(context.locator)

    wrong = AdapterRefreshLocator(adapter="mediacrawler", asset_key="different-stable-identity")
    calls_before = len(runner.calls)
    with pytest.raises(MediaDownloadError, match="locator_refresh_asset_mismatch"):
        refresher.resolve(wrong)
    assert len(runner.calls) == calls_before


def test_context_rejects_a_stable_key_that_does_not_describe_the_asset() -> None:
    with pytest.raises(MediaDownloadError) as caught:
        _context(
            platform=Platform.DY,
            content_id="7525082444551310602",
            kind=AssetKind.VIDEO,
            position=0,
            signed_url="https://v.example.test/dy/main.mp4?sign=private-sentinel",
            locator=AdapterRefreshLocator(adapter="mediacrawler", asset_key="wrong-stable-identity"),
        )

    assert caught.value.code == "locator_refresh_asset_mismatch"


def test_runner_controlled_exception_is_mapped_to_a_fixed_result_code() -> None:
    signed = "https://v.example.test/dy/main.mp4?sign=private-sentinel"
    context = _context(
        platform=Platform.DY,
        content_id="7525082444551310602",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=signed,
    )

    class BrokenRunner:
        def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
            del request
            raise RuntimeError("child-controlled-private-sentinel")

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, BrokenRunner()).resolve(context.locator)

    assert caught.value.code == "locator_refresh_result_invalid"
    assert "child-controlled-private-sentinel" not in str(caught.value)


def _segments_payload(
    *,
    cid: int = 24680,
    segments: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "cid": cid,
        "segments": segments
        if segments is not None
        else [
            {
                "url": "https://v.example.test/bili/segment-0.mp4?signature=first-private",
                "backup_urls": ["https://backup.example.test/bili/segment-0.mp4?signature=first-backup-private"],
            },
            {"url": "https://v.example.test/bili/segment-1.mp4?signature=second-private"},
        ],
    }


def test_bilibili_single_page_segments_bridge_reconstructs_ordered_typed_target() -> None:
    context = _context(
        platform=Platform.BILI,
        content_id="987654321",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=None,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": "987654321",
                "video_type": "video",
                "title": "single-page multi-segment",
                BILIBILI_PAGES_FIELD: [{"page": 1, "cid": 24680}],
                BILIBILI_PROGRESSIVE_SEGMENTS_FIELD: _segments_payload(),
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert isinstance(resolved, ResolvedSegmentsLocator)
    assert [segment.urls for segment in resolved.segments] == [
        (
            "https://v.example.test/bili/segment-0.mp4?signature=first-private",
            "https://backup.example.test/bili/segment-0.mp4?signature=first-backup-private",
        ),
        ("https://v.example.test/bili/segment-1.mp4?signature=second-private",),
    ]
    assert all(segment.request_profile is MediaRequestProfile.BILIBILI_MEDIA for segment in resolved.segments)
    assert "private" not in repr(resolved)
    assert runner.calls[0].bili_progressive_detail is True
    assert runner.calls[0].bili_video_cid is None


def test_bilibili_multipart_segments_bridge_binds_only_the_requested_cid() -> None:
    content_id = "987654321"
    remote_ids = (
        f"{content_id}:video:cid:24680",
        f"{content_id}:video:cid:97531",
    )
    context = _context(
        platform=Platform.BILI,
        content_id=content_id,
        kind=AssetKind.VIDEO,
        position=1,
        signed_url=None,
        remote_id=remote_ids[1],
        bili_video_remote_ids=remote_ids,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": content_id,
                "video_type": "video",
                "title": "multipart multi-segment",
                BILIBILI_PAGES_FIELD: [
                    {"page": 1, "cid": 24680},
                    {"page": 2, "cid": 97531},
                ],
                BILIBILI_PROGRESSIVE_SEGMENTS_FIELD: _segments_payload(cid=97531),
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert isinstance(resolved, ResolvedSegmentsLocator)
    assert resolved.segments[0].url == "https://v.example.test/bili/segment-0.mp4?signature=first-private"
    assert runner.calls[0].bili_video_cid == 97531


@pytest.mark.parametrize(
    "extra_fields",
    [
        {"__media_sync_bili_progressive_url": "https://v.example.test/bili/segment-0.mp4"},
        {BILIBILI_PROGRESSIVE_BACKUPS_FIELD: ["https://backup.example.test/bili/segment-0.mp4"]},
        {BILIBILI_PROGRESSIVE_FORMAT_FIELD: "flv"},
        {BILIBILI_PROGRESSIVE_PAGE_FIELD: {"cid": 24680, "url": "https://v.example.test/bili/page.mp4"}},
    ],
)
def test_bilibili_segments_bridge_rejects_any_colliding_private_field(extra_fields: dict[str, object]) -> None:
    context = _context(
        platform=Platform.BILI,
        content_id="987654321",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=None,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": "987654321",
                "video_type": "video",
                "title": "colliding segments bridge",
                BILIBILI_PAGES_FIELD: [{"page": 1, "cid": 24680}],
                BILIBILI_PROGRESSIVE_SEGMENTS_FIELD: _segments_payload(),
                **extra_fields,
            }
        )
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == "locator_refresh_schema_changed"


@pytest.mark.parametrize(
    "payload",
    [
        "not-a-mapping",
        {"segments": []},
        {"cid": 24680},
        {"cid": 24680, "segments": [], "extra": 1},
        {"cid": "24680", "segments": []},
        {"cid": 24680, "segments": [{"url": "https://v.example.test/bili/only.mp4"}]},
        {
            "cid": 24680,
            "segments": [{"url": f"https://v.example.test/bili/segment-{index}.mp4"} for index in range(65)],
        },
        {"cid": 24680, "segments": [{"url": 42}, {"url": "https://v.example.test/bili/segment-1.mp4"}]},
        {"cid": 24680, "segments": [{"url": "https://v.example.test/bili/segment-0.mp4"}, {"url": None}]},
        {
            "cid": 24680,
            "segments": [
                {"url": "https://v.example.test/bili/segment.mp4"},
                {"url": "https://v.example.test/bili/segment.mp4"},
            ],
        },
        {
            "cid": 24680,
            "segments": [
                {"url": "https://v.example.test/bili/segment-0.mp4", "backup_urls": "not-a-list"},
                {"url": "https://v.example.test/bili/segment-1.mp4"},
            ],
        },
        {
            "cid": 24680,
            "segments": [
                {"url": "https://v.example.test/bili/segment-0.mp4", "backup_urls": [42]},
                {"url": "https://v.example.test/bili/segment-1.mp4"},
            ],
        },
        {
            "cid": 24680,
            "segments": [
                {
                    "url": "https://v.example.test/bili/segment-0.mp4",
                    "backup_urls": [f"https://backup-{index}.example.test/bili/segment-0.mp4" for index in range(9)],
                },
                {"url": "https://v.example.test/bili/segment-1.mp4"},
            ],
        },
        {
            "cid": 24680,
            "segments": [
                {"url": "file:///private/segment-0.mp4"},
                {"url": "https://v.example.test/bili/segment-1.mp4"},
            ],
        },
        {"cid": 99999, "segments": []},
    ],
)
def test_bilibili_segments_bridge_fails_closed_on_malformed_payloads(payload: object) -> None:
    context = _context(
        platform=Platform.BILI,
        content_id="987654321",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=None,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": "987654321",
                "video_type": "video",
                "title": "malformed segments bridge",
                BILIBILI_PAGES_FIELD: [{"page": 1, "cid": 24680}],
                BILIBILI_PROGRESSIVE_SEGMENTS_FIELD: payload,
            }
        )
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == "locator_refresh_schema_changed"


def test_bilibili_segments_bridge_requires_a_page_tuple_to_bind_the_cid() -> None:
    context = _context(
        platform=Platform.BILI,
        content_id="987654321",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=None,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": "987654321",
                "video_type": "video",
                "title": "page-less segments bridge",
                BILIBILI_PROGRESSIVE_SEGMENTS_FIELD: _segments_payload(),
            }
        )
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == "locator_refresh_schema_changed"


def test_bilibili_single_page_flv_segments_bridge_reconstructs_typed_target() -> None:
    context = _context(
        platform=Platform.BILI,
        content_id="987654321",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=None,
    )
    payload = _segments_payload()
    payload["format"] = "flv"
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": "987654321",
                "video_type": "video",
                "title": "single-page FLV multi-segment",
                BILIBILI_PAGES_FIELD: [{"page": 1, "cid": 24680}],
                BILIBILI_PROGRESSIVE_SEGMENTS_FIELD: payload,
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert isinstance(resolved, ResolvedFlvSegmentsLocator)
    assert isinstance(resolved.source, ResolvedSegmentsLocator)
    assert resolved.source.segments[0].urls == (
        "https://v.example.test/bili/segment-0.mp4?signature=first-private",
        "https://backup.example.test/bili/segment-0.mp4?signature=first-backup-private",
    )
    assert "private" not in repr(resolved)
    assert runner.calls[0].bili_video_cid is None


@pytest.mark.parametrize("format_value", ["mp4", "flv2", True, 1])
def test_bilibili_flv_segments_bridge_rejects_non_exact_format_markers(format_value: object) -> None:
    context = _context(
        platform=Platform.BILI,
        content_id="987654321",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=None,
    )
    payload: dict[str, object] = _segments_payload()
    payload["format"] = format_value
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": "987654321",
                "video_type": "video",
                "title": "invalid FLV segments marker",
                BILIBILI_PAGES_FIELD: [{"page": 1, "cid": 24680}],
                BILIBILI_PROGRESSIVE_SEGMENTS_FIELD: payload,
            }
        )
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == "locator_refresh_schema_changed"


def test_bilibili_multipart_flv_segments_bridge_binds_only_the_requested_cid() -> None:
    content_id = "987654321"
    remote_ids = (
        f"{content_id}:video:cid:24680",
        f"{content_id}:video:cid:97531",
    )
    context = _context(
        platform=Platform.BILI,
        content_id=content_id,
        kind=AssetKind.VIDEO,
        position=1,
        signed_url=None,
        remote_id=remote_ids[1],
        bili_video_remote_ids=remote_ids,
    )
    payload = _segments_payload(cid=97531)
    payload["format"] = "flv"
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "video_id": content_id,
                "video_type": "video",
                "title": "multipart FLV multi-segment",
                BILIBILI_PAGES_FIELD: [
                    {"page": 1, "cid": 24680},
                    {"page": 2, "cid": 97531},
                ],
                BILIBILI_PROGRESSIVE_SEGMENTS_FIELD: payload,
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert isinstance(resolved, ResolvedFlvSegmentsLocator)
    assert resolved.source.segments[1].url == "https://v.example.test/bili/segment-1.mp4?signature=second-private"
    assert runner.calls[0].bili_video_cid == 97531


WEIBO_VIDEO_URL = (
    "https://f.us.sinaimg.cn/o0/weibo-offline.mp4?KID=unistore,video&Expires=4102444800&ssig=weibo-private"
)


@pytest.mark.parametrize(
    "value",
    [
        WEIBO_VIDEO_URL,
        "https://f.video.weibocdn.com/o0/alternate.mp4?KID=unistore,video",
        "https://sinaimg.cn/o0/root-host.mp4",
        "https://f.us.sinaimg.cn/o0/video.MP4?KID=unistore",
    ],
)
def test_weibo_video_url_validator_accepts_the_closed_signed_shape(value: str) -> None:
    assert validate_weibo_video_url(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "not-a-url",
        42,
        None,
        "http://f.us.sinaimg.cn/o0/insecure.mp4?KID=unistore",
        "https://f.us.sinaimg.cn/weibo-offline.mp4?KID=unistore",
        "https://f.us.sinaimg.cn/o0/video.flv?KID=unistore",
        "https://evil.example.test/o0/weibo-offline.mp4?KID=unistore",
        "https://f.us.sinaimg.cn/o0/weibo-offline.mp4?KID=unistore#fragment",
        "https://user:pass@f.us.sinaimg.cn/o0/weibo-offline.mp4?KID=unistore",
        "https://f.us.sinaimg.cn:8443/o0/weibo-offline.mp4?KID=unistore",
        "https://f.us.sinaimg.cn/o0//double-slash.mp4",
        "https://f.us.sinaimg.cn/o0/.dot.mp4",
        f"https://f.us.sinaimg.cn/o0/{'x' * 300}.mp4",
    ],
)
def test_weibo_video_url_validator_rejects_drifted_shapes(value: object) -> None:
    with pytest.raises(ValueError, match="invalid Weibo video URL"):
        validate_weibo_video_url(value)


def test_weibo_video_refresh_resolves_the_fresh_signed_locator_in_memory() -> None:
    context = _context(
        platform=Platform.WB,
        content_id="5123456789012345",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=WEIBO_VIDEO_URL,
    )
    runner = _FakeDetailRunner(
        _jsonl(
            {
                "note_id": "5123456789012345",
                "content": "ordinary original weibo video",
                WEIBO_VIDEO_FIELD: {"url": WEIBO_VIDEO_URL},
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert resolved.url == WEIBO_VIDEO_URL
    assert resolved.backup_urls == ()
    assert resolved.request_profile is MediaRequestProfile.DEFAULT
    assert runner.calls[0].bili_progressive_detail is False
    assert "weibo-private" not in repr(resolved)


def test_weibo_video_refresh_rejects_hint_or_identity_drift() -> None:
    context = _context(
        platform=Platform.WB,
        content_id="5123456789012345",
        kind=AssetKind.VIDEO,
        position=0,
        signed_url=WEIBO_VIDEO_URL,
    )
    drift_runner = _FakeDetailRunner(
        _jsonl(
            {
                "note_id": "5123456789012345",
                "content": "replaced video path",
                WEIBO_VIDEO_FIELD: {"url": "https://f.us.sinaimg.cn/o0/replaced-path.mp4?KID=unistore"},
            }
        )
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, drift_runner, clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == "locator_refresh_asset_mismatch"

    missing_runner = _FakeDetailRunner(
        _jsonl(
            {
                "note_id": "5123456789012345",
                "content": "video disappeared",
            }
        )
    )

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, missing_runner, clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == "locator_refresh_asset_mismatch"


DY_GALLERY_FIRST = "https://image.example.test/dy/gallery-first.png?sign=dy-gallery-first-sentinel"
DY_GALLERY_SECOND = "https://image.example.test/dy/gallery-second.png?sign=dy-gallery-second-sentinel"


def _dy_gallery_record() -> dict[str, object]:
    return {
        "aweme_id": "7525082444551310602",
        "title": "gallery",
        "desc": "gallery",
        "aweme_url": "https://www.douyin.com/video/7525082444551310602",
        "cover_url": "https://i.example.test/dy/cover.jpg?sign=dy-cover-sentinel",
        "video_download_url": "",
        "music_download_url": "",
        "note_download_url": f"{DY_GALLERY_FIRST},{DY_GALLERY_SECOND}",
    }


@pytest.mark.parametrize("position", [0, 1])
def test_douyin_note_gallery_refresh_resolves_each_position(position: int) -> None:
    signed_url = DY_GALLERY_FIRST if position == 0 else DY_GALLERY_SECOND
    context = _context(
        platform=Platform.DY,
        content_id="7525082444551310602",
        kind=AssetKind.IMAGE,
        position=position,
        signed_url=signed_url,
    )
    runner = _FakeDetailRunner(_jsonl(_dy_gallery_record()))

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert resolved.url == signed_url
    assert resolved.request_profile is MediaRequestProfile.DEFAULT
    assert "sentinel" not in repr(resolved)


def test_douyin_note_gallery_refresh_rejects_position_path_drift() -> None:
    context = _context(
        platform=Platform.DY,
        content_id="7525082444551310602",
        kind=AssetKind.IMAGE,
        position=1,
        signed_url=DY_GALLERY_SECOND,
    )
    drifted = _dy_gallery_record()
    drifted["note_download_url"] = f"{DY_GALLERY_FIRST},https://image.example.test/dy/replaced.png?sign=drift"
    runner = _FakeDetailRunner(_jsonl(drifted))

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert caught.value.code == "locator_refresh_asset_mismatch"


XHS_MULTI_FIRST = "http://sns-video-bd.xhscdn.com/multi-first.mp4"
XHS_MULTI_SECOND = "http://sns-video-bd.xhscdn.com/multi-second.mp4"


def _xhs_multi_video_record() -> dict[str, object]:
    return {
        "note_id": "66fad51c000000001b0224b8",
        "type": "video",
        "title": "multi video",
        "desc": "multi video",
        "video_url": f"{XHS_MULTI_FIRST},{XHS_MULTI_SECOND}",
        "image_list": "",
    }


@pytest.mark.parametrize("position", [0, 1])
def test_xhs_multi_video_refresh_resolves_each_position(position: int) -> None:
    selected = XHS_MULTI_FIRST if position == 0 else XHS_MULTI_SECOND
    context = _context(
        platform=Platform.XHS,
        content_id="66fad51c000000001b0224b8",
        kind=AssetKind.VIDEO,
        position=position,
        signed_url=selected,
        creator_reference=SecretValue(
            "https://www.xiaohongshu.com/user/profile/creator-42?xsec_token=xhs-creator-secret&xsec_source=pc_user"
        ),
        creator_max_items=2,
    )
    runner = _FakeDetailRunner(_jsonl(_xhs_multi_video_record()))

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert resolved.url == selected
    assert resolved.request_profile is MediaRequestProfile.DEFAULT


def test_xhs_multi_video_refresh_rejects_replaced_or_above_bound_drift() -> None:
    context = _context(
        platform=Platform.XHS,
        content_id="66fad51c000000001b0224b8",
        kind=AssetKind.VIDEO,
        position=1,
        signed_url=XHS_MULTI_SECOND,
        creator_reference=SecretValue(
            "https://www.xiaohongshu.com/user/profile/creator-42?xsec_token=xhs-creator-secret&xsec_source=pc_user"
        ),
        creator_max_items=2,
    )
    replaced = _xhs_multi_video_record()
    replaced["video_url"] = f"{XHS_MULTI_FIRST},http://sns-video-bd.xhscdn.com/replaced.mp4"
    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, _FakeDetailRunner(_jsonl(replaced)), clock=lambda: NOW).resolve(
            context.locator
        )
    assert caught.value.code == "locator_refresh_asset_mismatch"

    above_bound = _xhs_multi_video_record()
    above_bound["video_url"] = ",".join(f"http://sns-video-bd.xhscdn.com/over-{index}.mp4" for index in range(17))
    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, _FakeDetailRunner(_jsonl(above_bound)), clock=lambda: NOW).resolve(
            context.locator
        )
    assert caught.value.code == "locator_refresh_schema_changed"
