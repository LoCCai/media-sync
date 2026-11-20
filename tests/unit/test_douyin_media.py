"""Bounded Douyin stream selection from one pinned detail response."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from media_sync.domain import ContentKind, Platform
from media_sync.integrations.mediacrawler.douyin_media import (
    DOUYIN_MAX_BIT_RATE_ENTRIES,
    DOUYIN_MEDIA_RANK_FIELD,
    DouyinMediaRank,
    DouyinMediaSelection,
    DouyinMediaSelectionError,
    apply_douyin_media_selection,
    select_douyin_media,
    validate_douyin_media_url,
)
from media_sync.integrations.mediacrawler.normalizers import NormalizationContext, normalize_jsonl_bytes

_HIGH = "https://v3-web.douyinvod.com/high-1080.mp4?signature=high-sentinel"
_LOW = "https://v3-web.douyinvod.com/low-540.mp4?signature=low-sentinel"
_H264 = "https://v3-web.douyinvod.com/h264.mp4?signature=h264-sentinel"
_ADDR_256 = "https://v9-dy.byteimg.com/addr-256.mp4?signature=addr-sentinel"
_ADDR = "https://v9-dy.byteimg.com/addr.mp4?signature=addr-plain-sentinel"
_COVER = "https://p3-pc-sign.douyinpic.com/cover.jpeg?signature=cover-sentinel"


def _video(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {"raw_cover": {"url_list": ["https://p3.example.test/x", _COVER]}}
    payload.update(overrides)
    return payload


def test_bit_rate_wins_over_flattened_play_addr() -> None:
    detail = {
        "aweme_id": "7525082444551310602",
        "video": _video(
            play_addr_h264={"url_list": ["https://v3-web.douyinvod.com/ignored-a.mp4", _H264]},
            bit_rate=[
                {"width": 540, "height": 960, "bit_rate": 800_000, "data_size": 400, "play_addr": {"url_list": [_LOW]}},
                {
                    "width": 1080,
                    "height": 1920,
                    "bit_rate": 1_200_000,
                    "data_size": 900,
                    "play_addr": {"url_list": [_HIGH]},
                },
            ],
        ),
    }

    selection = select_douyin_media(detail)

    assert selection.rank is DouyinMediaRank.BIT_RATE
    assert selection.video_url == _HIGH
    assert selection.cover_url == _COVER
    assert (selection.width, selection.height) == (1080, 1920)
    assert "sentinel" not in repr(selection)
    assert selection.summary() == {"rank": "bit_rate", "width": 1080, "height": 1920}


def test_ordering_prefers_quality_then_fidelity_then_size_then_declaration() -> None:
    same_size_first = "https://v3-web.douyinvod.com/tie-a.mp4"
    same_size_second = "https://v3-web.douyinvod.com/tie-b.mp4"
    highest_quality = "https://v3-web.douyinvod.com/2160.mp4"
    detail = {
        "video": _video(
            bit_rate=[
                {
                    "width": 1080,
                    "height": 1920,
                    "bit_rate": 900,
                    "data_size": 10,
                    "play_addr": {"url_list": [same_size_first]},
                },
                {
                    "width": 1080,
                    "height": 1920,
                    "bit_rate": 900,
                    "data_size": 10,
                    "play_addr": {"url_list": [same_size_second]},
                },
                {
                    "width": 2160,
                    "height": 3840,
                    "bit_rate": 1,
                    "data_size": 1,
                    "play_addr": {"url_list": [highest_quality]},
                },
            ]
        )
    }

    assert select_douyin_media(detail).video_url == highest_quality

    detail["video"]["bit_rate"] = [
        {"width": 1080, "height": 1920, "bit_rate": 900, "data_size": 10, "play_addr": {"url_list": [same_size_first]}},
        {
            "width": 1080,
            "height": 1920,
            "bit_rate": 1_000,
            "data_size": 10,
            "play_addr": {"url_list": [same_size_second]},
        },
    ]
    assert select_douyin_media(detail).video_url == same_size_second

    detail["video"]["bit_rate"] = [
        {"width": 1080, "height": 1920, "bit_rate": 900, "data_size": 10, "play_addr": {"url_list": [same_size_first]}},
        {
            "width": 1080,
            "height": 1920,
            "bit_rate": 900,
            "data_size": 20,
            "play_addr": {"url_list": [same_size_second]},
        },
    ]
    assert select_douyin_media(detail).video_url == same_size_second

    detail["video"]["bit_rate"] = [
        {"width": 1080, "height": 1920, "bit_rate": 900, "data_size": 10, "play_addr": {"url_list": [same_size_first]}},
        {
            "width": 1080,
            "height": 1920,
            "bit_rate": 900,
            "data_size": 10,
            "play_addr": {"url_list": [same_size_second]},
        },
    ]
    assert select_douyin_media(detail).video_url == same_size_first


def test_fallback_reproduces_the_pinned_flattening_order() -> None:
    detail = {
        "video": _video(
            play_addr={"url_list": ["https://v3-web.douyinvod.com/plain-a.mp4", _ADDR]},
            play_addr_256={"url_list": ["https://v9-dy.byteimg.com/lim-a.mp4", _ADDR_256]},
            play_addr_h264={"url_list": ["https://v3-web.douyinvod.com/nope.mp4", _H264]},
        )
    }

    selection = select_douyin_media(detail)

    assert selection.rank is DouyinMediaRank.PLAY_ADDR_H264
    assert selection.video_url == _H264

    detail["video"].pop("play_addr_h264")
    assert select_douyin_media(detail).video_url == _ADDR_256

    detail["video"].pop("play_addr_256")
    assert select_douyin_media(detail).video_url == _ADDR


def test_absent_video_is_an_empty_selection_not_a_failure() -> None:
    selection = select_douyin_media({"aweme_id": "7525082444551310602"})

    assert selection.rank is DouyinMediaRank.NONE
    assert selection.video_url is None
    assert selection.has_video is False
    assert selection.summary() == {"rank": "none"}


@pytest.mark.parametrize(
    ("video", "reason"),
    [
        ({"bit_rate": "nope"}, "douyin_media_field_invalid"),
        ({"bit_rate": []}, "douyin_media_field_invalid"),
        ({"bit_rate": [{}] * (DOUYIN_MAX_BIT_RATE_ENTRIES + 1)}, "douyin_media_field_invalid"),
        ({"bit_rate": [{"play_addr": {"url_list": []}}]}, "douyin_media_field_invalid"),
        (
            {"bit_rate": [{"play_addr": {"url_list": ["http://v3-web.douyinvod.com/a.mp4"]}}]},
            "douyin_media_url_invalid",
        ),
        ({"bit_rate": [{"play_addr": {"url_list": ["https://evil.test/a.mp4"]}}]}, "douyin_media_host_invalid"),
        (
            {
                "play_addr_h264": {
                    "url_list": ["https://v3-web.douyinvod.com/a.mp4", "https://v3-web.douyinvod.com/a.mp4"]
                }
            },
            "douyin_media_field_invalid",
        ),
        ({"play_addr": {"url_list": "https://v3-web.douyinvod.com/a.mp4"}}, "douyin_media_field_invalid"),
    ],
)
def test_drifted_media_declarations_fail_closed(video: dict[str, object], reason: str) -> None:
    with pytest.raises(DouyinMediaSelectionError) as error:
        select_douyin_media({"aweme_id": "7525082444551310602", "video": video})

    assert str(error.value) == reason


def test_selection_rejects_an_inconsistent_rank() -> None:
    with pytest.raises(DouyinMediaSelectionError):
        DouyinMediaSelection(rank=DouyinMediaRank.NONE, video_url=_H264)
    with pytest.raises(DouyinMediaSelectionError):
        DouyinMediaSelection(rank=DouyinMediaRank.BIT_RATE, video_url=None)


@pytest.mark.parametrize(
    "url",
    [
        "http://v3-web.douyinvod.com/a.mp4",
        "https://user:pass@v3-web.douyinvod.com/a.mp4",
        "https://v3-web.douyinvod.com:8443/a.mp4",
        "https://v3-web.douyinvod.com/",
        "https://v3-web.douyinvod.com/a.mp4#fragment",
        "https://notdouyinvod.com/a.mp4",
        "https://v3-web.douyinvod.com.evil.test/a.mp4",
        "",
    ],
)
def test_media_url_gate_rejects_unsafe_shapes(url: str) -> None:
    with pytest.raises(DouyinMediaSelectionError):
        validate_douyin_media_url(url)


def test_media_url_gate_accepts_a_known_host() -> None:
    assert validate_douyin_media_url(_HIGH) == _HIGH


def test_a_realistic_multi_codec_bit_rate_array_still_ranks() -> None:
    """A real `aweme_detail` carries one entry per (quality x codec).

    Four qualities x three codecs is twelve entries. With an 8-entry bound the
    whole selection path was unreachable on such a payload and the shim silently
    fell back to the pinned flattening, so 0083's ranking never engaged.
    """

    entries = []
    for quality, (width, height) in enumerate([(720, 1280), (1080, 1920), (1440, 2560), (2160, 3840)]):
        for codec, _name in enumerate(["h264", "h265", "av1"]):
            tag = f"q{quality}c{codec}"
            entries.append(
                {
                    "play_addr": {
                        "url_list": [
                            f"https://v3-web.douyinvod.com/{tag}-a.mp4?sign={tag}",
                            f"https://v3-web.douyinvod.com/{tag}-b.mp4",
                        ]
                    },
                    "width": width,
                    "height": height,
                    "bit_rate": 1_000 + quality * 500 + codec,
                    "data_size": (quality + 1) * 1_000_000,
                }
            )

    assert len(entries) == 12
    selection = select_douyin_media({"aweme_id": "7525082444551310603", "video": {"bit_rate": entries}})

    assert selection.rank is DouyinMediaRank.BIT_RATE
    assert selection.width == 2160 and selection.height == 3840
    assert selection.video_url is not None and "q3c2" in selection.video_url


def test_a_comma_bearing_signed_url_is_refused_rather_than_silently_downgraded() -> None:
    """The shim writes into comma-delimited fields its own reader splits on.

    `apply_douyin_media_selection` stores the ranked URL into
    `video_download_url`, and `_dy_url_list(..., allow_scalar_commas=False)`
    returns `()` for any scalar containing a comma. Accepting such a URL here
    therefore persisted it and then dropped it, turning a VIDEO work into an
    asset-less TEXT row.
    """

    comma_url = "https://v3-web.douyinvod.com/high.mp4?signature=a,b"

    with pytest.raises(DouyinMediaSelectionError) as error:
        validate_douyin_media_url(comma_url)
    assert str(error.value) == "douyin_media_url_invalid"

    detail = {
        "aweme_id": "7525082444551310604",
        "video": {
            "bit_rate": [
                {
                    "play_addr": {
                        "url_list": [
                            comma_url,
                            "https://v3-web.douyinvod.com/high.mp4?signature=clean",
                        ]
                    }
                }
            ]
        },
    }
    with pytest.raises(DouyinMediaSelectionError):
        select_douyin_media(detail)


def test_selection_application_only_rewrites_the_ranked_stream() -> None:
    flattened = {"aweme_id": "7525082444551310602", "video_download_url": _H264, "cover_url": ""}
    ranked = DouyinMediaSelection(rank=DouyinMediaRank.BIT_RATE, video_url=_HIGH)

    applied = apply_douyin_media_selection(flattened, ranked)

    assert applied["video_download_url"] == _HIGH
    assert flattened["video_download_url"] == _H264

    fallback = DouyinMediaSelection(rank=DouyinMediaRank.PLAY_ADDR_H264, video_url=_H264)
    assert apply_douyin_media_selection(flattened, fallback) is flattened


def test_private_rank_field_never_reaches_the_persisted_envelope() -> None:
    record = {
        "aweme_id": "7525082444551310602",
        "desc": "ranked work",
        "create_time": 1_788_235_200,
        "video_download_url": _HIGH,
        "cover_url": "",
        "music_download_url": "",
        "note_download_url": "",
        DOUYIN_MEDIA_RANK_FIELD: {"rank": "bit_rate", "width": 1080},
    }

    normalized = normalize_jsonl_bytes(
        (json.dumps(record) + "\n").encode(),
        NormalizationContext(
            platform=Platform.DY,
            creator_remote_id="MS4wLjABAAAAcreator",
            creator_display_name="Douyin Creator",
            upstream_sha="d6f7c5bb906b6dac40ddf343ef9e26438a3de092",
            ingested_at=datetime(2026, 9, 5, 8, tzinfo=UTC),
        ),
    )

    assert not normalized.quarantined and not normalized.truncated_tail
    assert len(normalized.records) == 1
    record_out = normalized.records[0]
    assert record_out.content.kind is ContentKind.VIDEO
    assert record_out.assets[0].source_url == _HIGH
    persisted = repr(record_out.content.raw)
    assert DOUYIN_MEDIA_RANK_FIELD not in persisted
    assert "high-sentinel" not in persisted
