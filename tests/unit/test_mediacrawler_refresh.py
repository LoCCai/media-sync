from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import pytest

from media_sync.domain import AssetKind, LoginMethod, Platform
from media_sync.infrastructure.db.asset_identity import asset_source_hint, stable_asset_key
from media_sync.integrations.mediacrawler.detail_runner import (
    MediaCrawlerDetailRequest,
    MediaCrawlerDetailResult,
)
from media_sync.integrations.mediacrawler.policies import WatchdogLimits
from media_sync.integrations.mediacrawler.refresh import (
    MediaCrawlerLocatorRefresher,
    MediaCrawlerRefreshContext,
)
from media_sync.integrations.mediacrawler.weibo_media import WEIBO_IMAGES_FIELD
from media_sync.integrations.mediacrawler.xhs_media import validate_xhs_video_url
from media_sync.media import AdapterRefreshLocator, MediaDownloadError, MediaRequestProfile
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
    if signed_url is not None:
        assert source_hint is not None
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


def test_weibo_refresh_context_accepts_only_image_assets() -> None:
    with pytest.raises(MediaDownloadError) as caught:
        _context(
            platform=Platform.WB,
            content_id="5123456789012345",
            kind=AssetKind.VIDEO,
            position=0,
            signed_url="https://i1.wp.com/wx1.sinaimg.cn/large/not-video.jpg",
        )

    assert caught.value.code == "locator_refresh_unsupported"


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
            }
        )
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner, clock=lambda: NOW).resolve(context.locator)

    assert resolved.url == signed_url
    assert resolved.request_profile is MediaRequestProfile.BILIBILI_MEDIA
    assert runner.calls[0].bili_progressive_detail is True
    assert "private-sentinel" not in repr(resolved)


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
            "http://sns-video-bd.xhscdn.com/target.mp4,http://sns-video-bd.xhscdn.com/second.mp4",
            "",
            id="multiple-video-variants",
        ),
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


@pytest.mark.parametrize("platform", [Platform.TIEBA, Platform.ZHIHU])
def test_platforms_without_normalized_assets_return_unsupported_without_runner_call(platform: Platform) -> None:
    context = _context(
        platform=platform,
        content_id="content-42",
        kind=AssetKind.IMAGE,
        position=0,
        signed_url="https://i.example.test/no-asset/image.jpg?token=sentinel",
    )
    runner = _FakeDetailRunner(b"")

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, runner).resolve(context.locator)

    assert caught.value.code == "locator_refresh_unsupported"
    assert runner.calls == []


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
