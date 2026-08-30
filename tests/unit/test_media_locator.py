from __future__ import annotations

from dataclasses import dataclass

import pytest

from media_sync.infrastructure.db.asset_identity import asset_source_hint
from media_sync.media import (
    AdapterRefreshLocator,
    DirectLocator,
    MediaDownloadError,
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
    assert "ephemeral-secret" not in repr(resolved)
    assert "ephemeral-secret" not in canonical_locator_json(locator)
    assert refresh.calls == 1
