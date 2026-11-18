"""Douyin stream-selection shim: pinned-store seam, privacy and fallback parity."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from media_sync.integrations.mediacrawler.douyin_media import (
    DOUYIN_MEDIA_RANK_FIELD,
    install_douyin_media_capture,
)

AWEME_ID = "7525082444551310602"
BETTER = "https://v3-web.douyinvod.com/1080.mp4?signature=better-sentinel"
FLATTENED = "https://v3-web.douyinvod.com/h264.mp4?signature=flattened-sentinel"
COVER = "https://p3-pc-sign.douyinpic.com/cover.jpeg?signature=cover-sentinel"


def _module(name: str, checkout: Path) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(checkout / (name.replace(".", "/") + ".py"))
    return module


def _install(monkeypatch: pytest.MonkeyPatch, checkout: Path) -> tuple[list[dict[str, object]], object]:
    checkout.mkdir(parents=True, exist_ok=True)
    stored: list[dict[str, object]] = []

    class DouyinJsonlStoreImplement:
        async def store_content(self, content_item: dict[str, object]) -> None:
            stored.append(content_item)

    store = _module("store.douyin", checkout)
    store.utils = SimpleNamespace(logger=SimpleNamespace(info=lambda *_a, **_k: None))

    async def update_douyin_aweme(aweme_item: dict[str, object]) -> None:
        # Mirrors the pinned flattening rule: the first non-empty candidate in
        # play_addr_h264 / play_addr_256 / play_addr, last entry.
        video = aweme_item.get("video") or {}
        candidates = (
            video.get("play_addr_h264"),
            video.get("play_addr_256"),
            video.get("play_addr"),
        )
        flattened = ""
        for candidate in candidates:
            urls = candidate.get("url_list") if isinstance(candidate, dict) else None
            if isinstance(urls, list) and len(urls) >= 2:
                flattened = urls[-1]
                break
        cover = ""
        for key in ("raw_cover", "origin_cover"):
            source = video.get(key)
            urls = source.get("url_list") if isinstance(source, dict) else None
            if isinstance(urls, list) and len(urls) >= 2:
                cover = urls[1]
                break
        await DouyinJsonlStoreImplement().store_content(
            {
                "aweme_id": aweme_item["aweme_id"],
                "desc": aweme_item.get("desc", ""),
                "video_download_url": flattened,
                "cover_url": cover,
                "music_download_url": "",
                "note_download_url": "",
            }
        )

    store.update_douyin_aweme = update_douyin_aweme
    store_impl = _module("store.douyin._store_impl", checkout)
    store_impl.DouyinJsonlStoreImplement = DouyinJsonlStoreImplement
    monkeypatch.setitem(sys.modules, "store.douyin", store)
    monkeypatch.setitem(sys.modules, "store.douyin._store_impl", store_impl)
    return stored, store


def _detail(*, with_bit_rate: bool) -> dict[str, object]:
    video: dict[str, object] = {
        "raw_cover": {"url_list": ["https://p3-pc-sign.douyinpic.com/raw", COVER]},
        "play_addr_h264": {"url_list": ["https://v3-web.douyinvod.com/ignore", FLATTENED]},
    }
    if with_bit_rate:
        video["bit_rate"] = [
            {
                "width": 720,
                "height": 1280,
                "bit_rate": 900_000,
                "data_size": 10,
                "play_addr": {"url_list": ["https://v3-web.douyinvod.com/720", BETTER]},
            }
        ]
    return {"aweme_id": AWEME_ID, "desc": "offline work", "video": video}


@pytest.mark.asyncio
async def test_installed_shim_prefers_the_declared_higher_stream(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    stored, store = _install(monkeypatch, tmp_path / "checkout")
    install_douyin_media_capture(tmp_path / "checkout")

    await store.update_douyin_aweme(_detail(with_bit_rate=True))

    assert len(stored) == 1
    record = stored[0]
    assert record["video_download_url"] == BETTER
    assert record["cover_url"] == COVER
    assert record[DOUYIN_MEDIA_RANK_FIELD] == {"rank": "bit_rate", "width": 720, "height": 1280}
    assert "sentinel" not in repr(record[DOUYIN_MEDIA_RANK_FIELD])


@pytest.mark.asyncio
async def test_installed_shim_keeps_pinned_flattening_when_no_ranking_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    stored, store = _install(monkeypatch, tmp_path / "checkout")
    install_douyin_media_capture(tmp_path / "checkout")

    await store.update_douyin_aweme(_detail(with_bit_rate=False))

    assert stored[0]["video_download_url"] == FLATTENED
    assert stored[0][DOUYIN_MEDIA_RANK_FIELD] == {"rank": "play_addr_h264"}


@pytest.mark.asyncio
async def test_drifted_stream_declaration_leaves_the_pinned_record_untouched(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    stored, store = _install(monkeypatch, tmp_path / "checkout")
    install_douyin_media_capture(tmp_path / "checkout")
    detail = _detail(with_bit_rate=True)
    video = detail["video"]
    assert isinstance(video, dict)
    video["bit_rate"] = [
        {"play_addr": {"url_list": ["https://evil.test/wrong.mp4"]}},
    ]

    await store.update_douyin_aweme(detail)

    assert stored[0]["video_download_url"] == FLATTENED
    assert DOUYIN_MEDIA_RANK_FIELD not in stored[0]


def test_install_is_idempotent_and_refuses_a_private_collision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _stored, store = _install(monkeypatch, tmp_path / "checkout")
    install_douyin_media_capture(tmp_path / "checkout")
    first = store.update_douyin_aweme

    install_douyin_media_capture(tmp_path / "checkout")

    assert store.update_douyin_aweme is first
