from __future__ import annotations

from dataclasses import dataclass

import pytest

from media_sync.infrastructure.db.asset_identity import asset_source_hint
from media_sync.media import (
    AdapterRefreshLocator,
    DirectLocator,
    MediaDownloadError,
    MediaRequestProfile,
    ResolvedDashLocator,
    ResolvedFlvLocator,
    ResolvedLocator,
    canonical_locator_json,
    locator_fingerprint,
    parse_locator,
    resolve_locator,
)


def test_direct_locator_is_canonical_and_fingerprinted() -> None:
    locator = DirectLocator("HTTPS://MEDIA.Example.TEST:443/video/%41.mp4")

    assert locator.url == "https://media.example.test/video/%41.mp4"
    assert canonical_locator_json(locator) == (
        '{"type":"direct","url":"https://media.example.test/video/%41.mp4","version":1}'
    )
    assert len(locator_fingerprint(locator)) == 64
    assert parse_locator(canonical_locator_json(locator)) == locator
    assert resolve_locator(locator).request_profile is MediaRequestProfile.DEFAULT


@pytest.mark.parametrize(
    "url",
    [
        "ftp://media.test/video.mp4",
        "https://user:pass@media.test/video.mp4",
        "https://media.test/video.mp4?token=do-not-store",
        "https://media.test/video.mp4#fragment",
        "https://media.test\\@127.0.0.1/video.mp4",
        "https://media.test/video/%GG.mp4",
        "https://media.test/video/\x00.mp4",
        "https://media.test/video/\x1f.mp4",
    ],
)
def test_direct_locator_rejects_non_persistable_or_ambiguous_urls(url: str) -> None:
    with pytest.raises(MediaDownloadError) as caught:
        DirectLocator(url)

    assert caught.value.code in {"locator_invalid", "locator_secret_forbidden"}
    assert "do-not-store" not in str(caught.value)


@pytest.mark.parametrize("url", ["https://media.test/image.jpg?", "https://media.test/image.jpg#"])
def test_source_hint_rejects_empty_query_or_fragment_delimiters(url: str) -> None:
    assert asset_source_hint(url) is None


@pytest.mark.parametrize(
    "path",
    [
        "/token/P1_PATH_SECRET_SENTINEL/video.mp4",
        "/token%2FP1_PATH_SECRET_SENTINEL%2Fvideo.mp4",
        "/token%252FP1_PATH_SECRET_SENTINEL%252Fvideo.mp4",
        "/video;signature=P1_PATH_SECRET_SENTINEL/file.mp4",
        "/auth=P1_PATH_SECRET_SENTINEL/file.mp4",
    ],
)
def test_direct_locator_rejects_credential_bearing_paths_without_echo(path: str) -> None:
    sentinel = "P1_PATH_SECRET_SENTINEL"

    with pytest.raises(MediaDownloadError, match="locator_secret_forbidden") as caught:
        DirectLocator(f"https://media.test{path}")

    assert sentinel not in str(caught.value)
    assert asset_source_hint(f"https://media.test{path}") is None


@pytest.mark.parametrize(
    "path",
    [
        "/tokenized-video.mp4",
        "/session-recording.mp4",
        "/mytoken/file.mp4",
        "/token",
        "/public_key/value/video.mp4",
        "/key/value/video.mp4",
    ],
)
def test_direct_locator_preserves_noncredential_path_boundaries(path: str) -> None:
    url = f"https://media.test{path}"

    assert DirectLocator(url).url == url
    assert asset_source_hint(url) == url


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 2, "type": "direct", "url": "https://media.test/v"},
        {"version": True, "type": "direct", "url": "https://media.test/v"},
        {"version": 1, "type": "unknown", "url": "https://media.test/v"},
        {"version": 1, "type": "direct", "url": "https://media.test/v", "future": True},
        {"version": 1, "type": "adapter_refresh", "adapter": "xhs"},
        [],
        "[]",
        '{"version":1,"version":1,"type":"direct","url":"https://media.test/v"}',
    ],
)
def test_locator_schema_is_closed(payload: object) -> None:
    with pytest.raises(MediaDownloadError, match="locator_invalid"):
        parse_locator(payload)  # type: ignore[arg-type]


def test_adapter_refresh_uses_stable_keys_and_fixed_unsupported_code() -> None:
    locator = AdapterRefreshLocator(adapter="mediacrawler", asset_key="xhs/note-42/video/0")

    assert parse_locator(canonical_locator_json(locator)) == locator
    with pytest.raises(MediaDownloadError) as caught:
        resolve_locator(locator)
    assert caught.value.code == "locator_refresh_unsupported"
    assert "xhs/note-42" not in str(caught.value)


@pytest.mark.parametrize("value", ["access_token", "xhs?token=abc", "a=b", " leading"])
def test_adapter_refresh_rejects_secret_shaped_keys(value: str) -> None:
    with pytest.raises(MediaDownloadError):
        AdapterRefreshLocator(adapter="mediacrawler", asset_key=value)


@dataclass
class _Refresh:
    calls: int = 0

    def resolve(self, locator: AdapterRefreshLocator) -> ResolvedLocator:
        self.calls += 1
        assert locator.adapter == "mediacrawler"
        return ResolvedLocator("https://media.test/refreshed.mp4?signature=ephemeral-secret")


def test_injected_refresh_port_returns_ephemeral_direct_locator() -> None:
    refresh = _Refresh()
    locator = AdapterRefreshLocator(adapter="mediacrawler", asset_key="asset-42")

    resolved = resolve_locator(locator, refresh)
    assert resolved.url == "https://media.test/refreshed.mp4?signature=ephemeral-secret"
    assert resolved.request_profile is MediaRequestProfile.DEFAULT
    assert "ephemeral-secret" not in repr(resolved)
    assert "ephemeral-secret" not in canonical_locator_json(locator)
    assert refresh.calls == 1


def test_resolved_locator_carries_only_a_closed_non_secret_request_profile() -> None:
    signed_url = "https://media.test/refreshed.mp4?signature=ephemeral-secret"
    resolved = ResolvedLocator(signed_url, MediaRequestProfile.BILIBILI_MEDIA)

    assert resolved.request_profile is MediaRequestProfile.BILIBILI_MEDIA
    assert "ephemeral-secret" not in repr(resolved)
    assert signed_url not in repr(resolved)

    with pytest.raises(MediaDownloadError, match="locator_invalid"):
        ResolvedLocator(signed_url, "bilibili_media")  # type: ignore[arg-type]


def test_resolved_dash_locator_is_closed_repr_safe_and_selection_bound() -> None:
    video = ResolvedLocator(
        "https://video.test/v.m4s?signature=video-private",
        MediaRequestProfile.BILIBILI_MEDIA,
        ("https://backup.test/v.m4s?signature=backup-private",),
    )
    audio = ResolvedLocator(
        "https://audio.test/a.m4s?signature=audio-private",
        MediaRequestProfile.BILIBILI_MEDIA,
    )

    resolved = ResolvedDashLocator(
        video=video,
        audio=audio,
        video_quality=120,
        video_codec="avc",
        audio_quality=30251,
    )

    assert resolved.selection_key == (120, "avc", 30251)
    assert video.urls == (video.url, video.backup_urls[0])
    assert "private" not in repr(resolved)
    assert "private" not in repr(video)


def test_resolved_flv_locator_is_bilibili_only_repr_safe_and_resolver_accepted() -> None:
    source = ResolvedLocator(
        "https://video.test/source.flv?signature=flv-private",
        MediaRequestProfile.BILIBILI_MEDIA,
        ("https://backup.test/source.flv?signature=backup-private",),
    )
    target = ResolvedFlvLocator(source)

    assert target.source.urls == (source.url, source.backup_urls[0])
    assert "flv-private" not in repr(target)
    assert "backup-private" not in repr(target)

    @dataclass
    class _FlvRefresh:
        def resolve(self, _locator: AdapterRefreshLocator) -> ResolvedFlvLocator:
            return target

    assert resolve_locator(AdapterRefreshLocator("mediacrawler", "bili/video/flv"), _FlvRefresh()) is target


def test_resolved_flv_locator_rejects_non_bilibili_or_non_resolved_sources() -> None:
    with pytest.raises(MediaDownloadError, match="locator_invalid"):
        ResolvedFlvLocator(ResolvedLocator("https://video.test/source.flv"))
    with pytest.raises(MediaDownloadError, match="locator_invalid"):
        ResolvedFlvLocator("https://video.test/source.flv")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("quality", "codec", "audio_quality"),
    [(999, "avc", None), (120, "vp9", None), (120, "avc", 999)],
)
def test_resolved_dash_locator_rejects_unknown_selection_values(
    quality: int,
    codec: str,
    audio_quality: int | None,
) -> None:
    video = ResolvedLocator("https://video.test/v.m4s", MediaRequestProfile.BILIBILI_MEDIA)
    audio = (
        None
        if audio_quality is None
        else ResolvedLocator("https://audio.test/a.m4s", MediaRequestProfile.BILIBILI_MEDIA)
    )

    with pytest.raises(MediaDownloadError, match="locator_invalid"):
        ResolvedDashLocator(video, audio, quality, codec, audio_quality)
