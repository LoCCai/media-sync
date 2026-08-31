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
