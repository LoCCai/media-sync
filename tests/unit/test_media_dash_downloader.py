from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from media_sync.domain import AssetKind
from media_sync.media import (
    AdapterRefreshLocator,
    DownloadLimits,
    DownloadRequest,
    MediaDownloadError,
    MediaRequestProfile,
    ProbeResult,
    ResolvedDashLocator,
    ResolvedLocator,
    SafeHttpClient,
    SecureMediaDownloader,
    ValidatedTarget,
)

ASSET_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
VIDEO_URL = "https://video.dash.test/component.m4s?deadline=4102444800&sig=video-secret"
AUDIO_URL = "https://audio.dash.test/component.m4s?deadline=4102444800&sig=audio-secret"
VIDEO = b"\x00\x00\x00\x18ftypisom" + b"dash-video-component"
AUDIO = b"\x00\x00\x00\x18ftypM4A " + b"dash-audio-component"
MUXED = b"\x00\x00\x00\x18ftypisom" + b"muxed-video-and-audio"
SILENT_MUXED = b"\x00\x00\x00\x18ftypisom" + b"remuxed-silent-video"
VIDEO_ETAG = '"dash-video-v1"'
AUDIO_ETAG = '"dash-audio-v1"'


class _Resolver:
    def __init__(self, *, explode: bool = False) -> None:
        self.explode = explode
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        if self.explode:
            raise AssertionError("published recovery must not perform DNS")
        self.calls.append((hostname, port))
        return ("8.8.8.8",)


class _Refresher:
    def __init__(self, target: ResolvedDashLocator) -> None:
        self.target = target
        self.calls = 0

    def resolve(self, _locator: AdapterRefreshLocator) -> ResolvedDashLocator:
        self.calls += 1
        return self.target


class _Probe:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, float, int]] = []

    def probe(self, path: Path, *, timeout_seconds: float, max_output_bytes: int) -> ProbeResult:
        payload = path.read_bytes()
        self.calls.append((payload, timeout_seconds, max_output_bytes))
        if payload == AUDIO:
            return ProbeResult("audio/mp4", "m4a")
        if payload in {VIDEO, MUXED, SILENT_MUXED}:
            return ProbeResult("video/mp4", "mp4")
        raise AssertionError("unexpected media payload")


class _Muxer:
    def __init__(self, payload: bytes = MUXED, *, fail: bool = False) -> None:
        self.payload = payload
        self.fail = fail
        self.calls: list[tuple[Path, Path | None, Path, Path, float, int, int]] = []

    def mux(
        self,
        video_path: Path,
        audio_path: Path | None,
        output_path: Path,
        *,
        root: Path,
        timeout_seconds: float,
        max_output_bytes: int,
        max_media_bytes: int,
    ) -> None:
        self.calls.append(
            (
                video_path,
                audio_path,
                output_path,
                root,
                timeout_seconds,
                max_output_bytes,
                max_media_bytes,
            )
        )
        assert video_path.read_bytes() == VIDEO
        if audio_path is not None:
            assert audio_path.read_bytes() == AUDIO
        if self.fail:
            raise MediaDownloadError("media_mux_failed")
        output_path.write_bytes(self.payload)


class _BreakingStream(httpx.SyncByteStream):
    def __init__(self, first: bytes) -> None:
        self.first = first

    def __iter__(self) -> Iterator[bytes]:
        yield self.first
        raise httpx.ReadError("offline component interruption")


def _target(*, audio: bool = True) -> ResolvedDashLocator:
    return ResolvedDashLocator(
        video=ResolvedLocator(VIDEO_URL, MediaRequestProfile.BILIBILI_MEDIA),
        audio=ResolvedLocator(AUDIO_URL, MediaRequestProfile.BILIBILI_MEDIA) if audio else None,
        video_quality=127,
        video_codec="avc",
        audio_quality=30251 if audio else None,
    )


def _request(tmp_path: Path) -> DownloadRequest:
    return DownloadRequest(
        asset_id=ASSET_ID,
        generation=4,
        locator=AdapterRefreshLocator("mediacrawler", "bili/video/dash-fixture"),
        work_root=tmp_path / "work",
        archive_root=tmp_path / "archive",
        expected_kind=AssetKind.VIDEO,
    )


def _response(payload: bytes, *, media_type: str, etag: str) -> httpx.Response:
    return httpx.Response(
        200,
        headers={
            "Content-Length": str(len(payload)),
            "Content-Type": media_type,
            "ETag": etag,
        },
        content=payload,
    )


def _downloader(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    target: ResolvedDashLocator,
    probe: _Probe,
    muxer: _Muxer,
    limits: DownloadLimits | None = None,
    resolver: _Resolver | None = None,
) -> tuple[SecureMediaDownloader, _Refresher, _Resolver]:
    active_resolver = resolver or _Resolver()
    refresher = _Refresher(target)

    def transport_factory(_target: ValidatedTarget) -> httpx.BaseTransport:
        return httpx.MockTransport(handler)

    return (
        SecureMediaDownloader(
            SafeHttpClient(active_resolver, transport_factory=transport_factory),
            refresher=refresher,
            probe=probe,
            muxer=muxer,
            limits=limits,
        ),
        refresher,
        active_resolver,
    )


def _component_handler(requests: list[httpx.Request]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["referer"] == "https://www.bilibili.com/"
        assert request.headers["origin"] == "https://www.bilibili.com"
        assert request.headers["accept-encoding"] == "identity"
        if str(request.url) == VIDEO_URL:
            return _response(VIDEO, media_type="video/mp4", etag=VIDEO_ETAG)
        if str(request.url) == AUDIO_URL:
            return _response(AUDIO, media_type="audio/mp4", etag=AUDIO_ETAG)
        raise AssertionError("unexpected component URL")

    return handler


def _part_files(root: Path) -> tuple[Path, ...]:
    parts = root / "parts"
    return tuple(sorted((path for path in parts.glob(f"{ASSET_ID}.4*") if path.is_file()), key=lambda path: path.name))


def test_dash_audio_components_are_probed_muxed_archived_and_cleaned(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    probe = _Probe()
    muxer = _Muxer()
    downloader, refresher, resolver = _downloader(
        _component_handler(requests),
        target=_target(),
        probe=probe,
        muxer=muxer,
    )
    request = _request(tmp_path)

    result = downloader.download(request)

    assert result.sha256 == hashlib.sha256(MUXED).hexdigest()
    assert result.size_bytes == len(MUXED)
    assert result.mime_type == "video/mp4"
    assert result.extension == "mp4"
    assert result.archive_path.read_bytes() == MUXED
    assert [str(item.url) for item in requests] == [VIDEO_URL, AUDIO_URL]
    assert resolver.calls == [("video.dash.test", 443), ("audio.dash.test", 443)]
    assert refresher.calls == 1
    assert [payload for payload, _timeout, _cap in probe.calls] == [VIDEO, AUDIO, MUXED]
    assert len(muxer.calls) == 1
    assert muxer.calls[0][1] is not None
    assert len(_part_files(request.work_root)) == 6
    assert "video-secret" not in repr(_target())
    assert "audio-secret" not in repr(_target())

    downloader.cleanup_partial(request.asset_id, request.generation, request.work_root)
    assert _part_files(request.work_root) == ()


def test_silent_dash_remuxes_one_video_component(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    probe = _Probe()
    muxer = _Muxer(SILENT_MUXED)
    downloader, refresher, _resolver = _downloader(
        _component_handler(requests),
        target=_target(audio=False),
        probe=probe,
        muxer=muxer,
    )

    result = downloader.download(_request(tmp_path))

    assert result.archive_path.read_bytes() == SILENT_MUXED
    assert [str(item.url) for item in requests] == [VIDEO_URL]
    assert [payload for payload, _timeout, _cap in probe.calls] == [VIDEO, SILENT_MUXED]
    assert refresher.calls == 1
    assert len(muxer.calls) == 1 and muxer.calls[0][1] is None


def test_failed_mux_keeps_verified_components_for_range_recovery(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        url = str(request.url)
        payload, media_type, etag = (
            (VIDEO, "video/mp4", VIDEO_ETAG) if url == VIDEO_URL else (AUDIO, "audio/mp4", AUDIO_ETAG)
        )
        if "range" in request.headers:
            assert request.headers["range"] == f"bytes={len(payload)}-"
            assert request.headers["if-range"] == etag
            return httpx.Response(
                416,
                headers={"Content-Range": f"bytes */{len(payload)}", "Content-Type": media_type, "ETag": etag},
            )
        return _response(payload, media_type=media_type, etag=etag)

    request = _request(tmp_path)
    failed_muxer = _Muxer(fail=True)
    failed, _refresher, _resolver = _downloader(
        handler,
        target=_target(),
        probe=_Probe(),
        muxer=failed_muxer,
    )

    with pytest.raises(MediaDownloadError) as caught:
        failed.download(request)

    assert caught.value.code == "media_mux_failed"
    assert not tuple((tmp_path / "archive").rglob("*.mp4"))
    retained = _part_files(request.work_root)
    assert len(retained) == 4
    assert any(path.name.endswith("dash-video.part") and path.read_bytes() == VIDEO for path in retained)
    assert any(path.name.endswith("dash-audio.part") and path.read_bytes() == AUDIO for path in retained)

    recovered_muxer = _Muxer()
    recovered, _refresher, _resolver = _downloader(
        handler,
        target=_target(),
        probe=_Probe(),
        muxer=recovered_muxer,
    )
    result = recovered.download(request)

    assert result.archive_path.read_bytes() == MUXED
    assert len(requests) == 4
    assert all("range" not in request.headers for request in requests[:2])
    assert all("range" in request.headers for request in requests[2:])
    assert len(recovered_muxer.calls) == 1


def test_interrupted_video_component_resumes_before_audio_and_mux(tmp_path: Path) -> None:
    split = len(VIDEO) // 2
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url) == VIDEO_URL and len([item for item in requests if str(item.url) == VIDEO_URL]) == 1:
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(VIDEO)),
                    "Content-Type": "video/mp4",
                    "ETag": VIDEO_ETAG,
                },
                stream=_BreakingStream(VIDEO[:split]),
            )
        if str(request.url) == VIDEO_URL:
            assert request.headers["range"] == f"bytes={split}-"
            assert request.headers["if-range"] == VIDEO_ETAG
            remainder = VIDEO[split:]
            return httpx.Response(
                206,
                headers={
                    "Content-Length": str(len(remainder)),
                    "Content-Range": f"bytes {split}-{len(VIDEO) - 1}/{len(VIDEO)}",
                    "Content-Type": "video/mp4",
                    "ETag": VIDEO_ETAG,
                },
                content=remainder,
            )
        assert str(request.url) == AUDIO_URL
        return _response(AUDIO, media_type="audio/mp4", etag=AUDIO_ETAG)

    probe = _Probe()
    muxer = _Muxer()
    downloader, refresher, _resolver = _downloader(handler, target=_target(), probe=probe, muxer=muxer)
    request = _request(tmp_path)

    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(request)
    assert caught.value.code == "download_interrupted"
    assert len(muxer.calls) == 0

    result = downloader.download(request)

    assert result.archive_path.read_bytes() == MUXED
    assert [str(item.url) for item in requests] == [VIDEO_URL, VIDEO_URL, AUDIO_URL]
    assert refresher.calls == 2
    assert [payload for payload, _timeout, _cap in probe.calls] == [VIDEO, AUDIO, MUXED]


def test_dash_component_sum_is_bounded_before_audio_bytes_are_written(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    max_bytes = len(VIDEO) + len(AUDIO) - 1
    muxer = _Muxer()
    downloader, _refresher, _resolver = _downloader(
        _component_handler(requests),
        target=_target(),
        probe=_Probe(),
        muxer=muxer,
        limits=DownloadLimits(max_bytes=max_bytes),
    )
    request = _request(tmp_path)

    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(request)

    assert caught.value.code == "download_size_limit"
    assert [str(item.url) for item in requests] == [VIDEO_URL, AUDIO_URL]
    assert not any(path.name.endswith("dash-audio.part") for path in _part_files(request.work_root))
    assert muxer.calls == []


def test_published_dash_result_recovers_without_detail_dns_http_or_ffmpeg(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    request = _request(tmp_path)
    first, _refresher, _resolver = _downloader(
        _component_handler(requests),
        target=_target(),
        probe=_Probe(),
        muxer=_Muxer(),
    )
    published = first.download(request)

    exploding_resolver = _Resolver(explode=True)

    def unexpected_http(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("published recovery must not perform HTTP")

    recovery_probe = _Probe()
    recovery = SecureMediaDownloader(
        SafeHttpClient(
            exploding_resolver,
            transport_factory=lambda _target: httpx.MockTransport(unexpected_http),
        ),
        probe=recovery_probe,
    )

    recovered = recovery.recover_published(request)

    assert recovered == published
    assert exploding_resolver.calls == []
    assert [payload for payload, _timeout, _cap in recovery_probe.calls] == [MUXED]
    assert len(requests) == 2

    recovery.cleanup_partial(request.asset_id, request.generation, request.work_root)
    assert recovery.recover_published(request) is None


def test_dash_requires_video_kind_probe_and_mux_capabilities(tmp_path: Path) -> None:
    target = _target()
    request = _request(tmp_path)
    wrong_kind = DownloadRequest(
        asset_id=request.asset_id,
        generation=request.generation,
        locator=request.locator,
        work_root=request.work_root,
        archive_root=request.archive_root,
        expected_kind=AssetKind.AUDIO,
    )
    handler = _component_handler([])

    without_mux, _refresher, _resolver = _downloader(
        handler,
        target=target,
        probe=_Probe(),
        muxer=_Muxer(),
    )
    with pytest.raises(MediaDownloadError) as wrong:
        without_mux.download(wrong_kind)
    assert wrong.value.code == "media_type_mismatch"

    refresher = _Refresher(target)
    no_mux = SecureMediaDownloader(
        SafeHttpClient(_Resolver(), transport_factory=lambda _target: httpx.MockTransport(handler)),
        refresher=refresher,
        probe=_Probe(),
    )
    with pytest.raises(MediaDownloadError) as unavailable:
        no_mux.download(request)
    assert unavailable.value.code == "media_mux_unavailable"
    assert unavailable.value.retryable is True
