from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from media_sync.domain import AssetKind
from media_sync.media import (
    AdapterRefreshLocator,
    DownloadRequest,
    MediaDownloadError,
    MediaRequestProfile,
    ProbeResult,
    ResolvedFlvLocator,
    ResolvedLocator,
    SafeHttpClient,
    SecureMediaDownloader,
    ValidatedTarget,
)

ASSET_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
PRIMARY_URL = "https://primary.flv.test/source.flv?deadline=4102444800&sig=primary-private"
BACKUP_URL = "https://backup.flv.test/source.flv?deadline=4102444800&sig=backup-private"
FLV = b"FLV\x01\x05\x00\x00\x00\x09" + b"single-segment-mixed-source"
MP4 = b"\x00\x00\x00\x18ftypisom" + b"stream-copy-remuxed-video"
WEBM = b"unknown-container-bytes-for-controlled-probe"
ETAG = '"flv-source-v1"'
FLV_PROBE = ProbeResult("video/x-flv", "flv")
MP4_PROBE = ProbeResult("video/mp4", "mp4")


class _Resolver:
    def __init__(self, *, explode: bool = False) -> None:
        self.explode = explode
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        if self.explode:
            raise AssertionError("published recovery must not perform DNS")
        self.calls.append((hostname, port))
        return ("8.8.8.8",)


def _target(
    primary: str = PRIMARY_URL,
    backups: tuple[str, ...] = (BACKUP_URL,),
) -> ResolvedFlvLocator:
    return ResolvedFlvLocator(ResolvedLocator(primary, MediaRequestProfile.BILIBILI_MEDIA, backups))


class _Refresher:
    def __init__(self, *targets: ResolvedFlvLocator | ResolvedLocator) -> None:
        self.targets = targets
        self.calls = 0

    def resolve(self, _locator: AdapterRefreshLocator) -> ResolvedFlvLocator | ResolvedLocator:
        target = self.targets[min(self.calls, len(self.targets) - 1)]
        self.calls += 1
        return target


class _Probe:
    def __init__(
        self,
        *,
        source: ProbeResult = FLV_PROBE,
        final: ProbeResult = MP4_PROBE,
    ) -> None:
        self.source = source
        self.final = final
        self.calls: list[tuple[bytes, float, int]] = []

    def probe(self, path: Path, *, timeout_seconds: float, max_output_bytes: int) -> ProbeResult:
        payload = path.read_bytes()
        self.calls.append((payload, timeout_seconds, max_output_bytes))
        if payload == FLV:
            return self.source
        if payload in {MP4, WEBM}:
            return self.final
        raise AssertionError("unexpected probe payload")


class _Muxer:
    def __init__(self, payload: bytes = MP4, *, fail: bool = False) -> None:
        self.payload = payload
        self.fail = fail
        self.calls: list[tuple[Path, Path, Path, float, int, int]] = []

    def remux(
        self,
        source_path: Path,
        output_path: Path,
        *,
        root: Path,
        timeout_seconds: float,
        max_output_bytes: int,
        max_media_bytes: int,
    ) -> None:
        self.calls.append(
            (
                source_path,
                output_path,
                root,
                timeout_seconds,
                max_output_bytes,
                max_media_bytes,
            )
        )
        assert source_path.read_bytes() == FLV
        output_path.write_bytes(self.payload)
        if self.fail:
            raise MediaDownloadError("media_mux_failed")


def _request(tmp_path: Path, *, kind: AssetKind = AssetKind.VIDEO) -> DownloadRequest:
    return DownloadRequest(
        asset_id=ASSET_ID,
        generation=3,
        locator=AdapterRefreshLocator("mediacrawler", "bili/video/flv-fixture"),
        work_root=tmp_path / "work",
        archive_root=tmp_path / "archive",
        expected_kind=kind,
    )


def _response() -> httpx.Response:
    return httpx.Response(
        200,
        headers={
            "Content-Length": str(len(FLV)),
            "Content-Type": "video/x-flv",
            "ETag": ETAG,
        },
        content=FLV,
    )


def _downloader(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    refresher: _Refresher,
    probe: _Probe,
    muxer: _Muxer | None,
    resolver: _Resolver | None = None,
) -> tuple[SecureMediaDownloader, _Resolver]:
    active_resolver = resolver or _Resolver()

    def transport_factory(_target: ValidatedTarget) -> httpx.BaseTransport:
        return httpx.MockTransport(handler)

    return (
        SecureMediaDownloader(
            SafeHttpClient(active_resolver, transport_factory=transport_factory),
            refresher=refresher,
            probe=probe,
            muxer=muxer,
        ),
        active_resolver,
    )


def _part_files(root: Path) -> tuple[Path, ...]:
    parts = root / "parts"
    return tuple(
        sorted(
            (path for path in parts.glob(f"{ASSET_ID}.3*") if path.is_file()),
            key=lambda path: path.name,
        )
    )


def test_flv_primary_failure_uses_backup_then_remuxes_and_publishes_only_mp4(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["referer"] == "https://www.bilibili.com/"
        assert request.headers["origin"] == "https://www.bilibili.com"
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(503) if str(request.url) == PRIMARY_URL else _response()

    refresher = _Refresher(_target())
    probe = _Probe()
    muxer = _Muxer()
    downloader, resolver = _downloader(handler, refresher=refresher, probe=probe, muxer=muxer)
    request = _request(tmp_path)

    result = downloader.download(request)

    assert result.sha256 == hashlib.sha256(MP4).hexdigest()
    assert result.size_bytes == len(MP4)
    assert (result.mime_type, result.extension) == ("video/mp4", "mp4")
    assert result.archive_path.read_bytes() == MP4
    assert result.archive_path.suffix == ".mp4"
    assert not tuple(request.archive_root.rglob("*.flv"))
    assert [str(item.url) for item in requests] == [PRIMARY_URL, BACKUP_URL]
    assert resolver.calls == [("primary.flv.test", 443), ("backup.flv.test", 443)]
    assert refresher.calls == 1
    assert [payload for payload, _timeout, _cap in probe.calls] == [FLV, MP4]
    assert len(muxer.calls) == 1
    assert len(_part_files(request.work_root)) == 4
    assert "private" not in repr(_target())

    downloader.cleanup_partial(request.asset_id, request.generation, request.work_root)
    assert _part_files(request.work_root) == ()


def test_flv_all_auth_pass_refreshes_once_and_rejects_type_drift(tmp_path: Path) -> None:
    first = _target(
        "https://primary.flv.test/source-1.flv?sig=first",
        ("https://backup.flv.test/source-1.flv?sig=first-backup",),
    )
    second = _target(
        "https://primary.flv.test/source-2.flv?sig=second",
        ("https://backup.flv.test/source-2.flv?sig=second-backup",),
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "source-1.flv" in request.url.path:
            return httpx.Response(403)
        if request.url.host == "primary.flv.test":
            return httpx.Response(503)
        return _response()

    refresher = _Refresher(first, second)
    downloader, _resolver = _downloader(handler, refresher=refresher, probe=_Probe(), muxer=_Muxer())

    assert downloader.download(_request(tmp_path)).archive_path.read_bytes() == MP4
    assert [item.url.path for item in requests] == [
        "/source-1.flv",
        "/source-1.flv",
        "/source-2.flv",
        "/source-2.flv",
    ]
    assert refresher.calls == 2

    drift_refresher = _Refresher(
        first,
        ResolvedLocator("https://ordinary.test/video.mp4", MediaRequestProfile.BILIBILI_MEDIA),
    )

    def all_auth(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    drift, _resolver = _downloader(
        all_auth,
        refresher=drift_refresher,
        probe=_Probe(),
        muxer=_Muxer(),
    )
    with pytest.raises(MediaDownloadError) as caught:
        drift.download(_request(tmp_path / "drift"))
    assert caught.value.code == "locator_refresh_schema_changed"
    assert drift_refresher.calls == 2


@pytest.mark.parametrize(
    ("probe", "muxer", "expected"),
    [
        (_Probe(source=ProbeResult("video/mp4", "mp4")), _Muxer(), "media_type_mismatch"),
        (
            _Probe(final=ProbeResult("video/webm", "webm")),
            _Muxer(WEBM),
            "media_type_mismatch",
        ),
    ],
)
def test_flv_source_and_final_container_gates_fail_closed(
    tmp_path: Path,
    probe: _Probe,
    muxer: _Muxer,
    expected: str,
) -> None:
    downloader, _resolver = _downloader(
        lambda _request: _response(),
        refresher=_Refresher(_target(backups=())),
        probe=probe,
        muxer=muxer,
    )
    request = _request(tmp_path)

    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(request)

    assert caught.value.code == expected
    assert not tuple(request.archive_root.rglob("*"))
    retained = _part_files(request.work_root)
    assert any(path.name.endswith("bili-flv-source.part") and path.read_bytes() == FLV for path in retained)
    assert not any(path.name == f"{ASSET_ID}.3.part" for path in retained)
    if probe.source.extension != "flv":
        assert muxer.calls == []


def test_failed_flv_remux_keeps_source_but_discards_incomplete_final_for_retry(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "range" in request.headers:
            assert request.headers["range"] == f"bytes={len(FLV)}-"
            assert request.headers["if-range"] == ETAG
            return httpx.Response(
                416,
                headers={
                    "Content-Range": f"bytes */{len(FLV)}",
                    "Content-Type": "video/x-flv",
                    "ETag": ETAG,
                },
            )
        return _response()

    request = _request(tmp_path)
    failed_muxer = _Muxer(b"incomplete-final", fail=True)
    failed, _resolver = _downloader(
        handler,
        refresher=_Refresher(_target(backups=())),
        probe=_Probe(),
        muxer=failed_muxer,
    )

    with pytest.raises(MediaDownloadError, match="media_mux_failed"):
        failed.download(request)

    retained = _part_files(request.work_root)
    assert len(retained) == 2
    assert any(path.name.endswith("bili-flv-source.part") and path.read_bytes() == FLV for path in retained)
    assert not tuple(request.archive_root.rglob("*.mp4"))

    recovered_muxer = _Muxer()
    recovered, _resolver = _downloader(
        handler,
        refresher=_Refresher(_target(backups=())),
        probe=_Probe(),
        muxer=recovered_muxer,
    )
    result = recovered.download(request)

    assert result.archive_path.read_bytes() == MP4
    assert len(requests) == 2
    assert "range" not in requests[0].headers
    assert "range" in requests[1].headers
    assert len(recovered_muxer.calls) == 1


def test_published_flv_result_recovers_and_cleanup_removes_source_and_final(tmp_path: Path) -> None:
    request = _request(tmp_path)
    first, _resolver = _downloader(
        lambda _request: _response(),
        refresher=_Refresher(_target(backups=())),
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
    assert [payload for payload, _timeout, _cap in recovery_probe.calls] == [MP4]

    recovery.cleanup_partial(request.asset_id, request.generation, request.work_root)
    assert _part_files(request.work_root) == ()
    assert recovery.recover_published(request) is None


def test_flv_requires_video_kind_and_mux_capability_before_network(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def unexpected_http(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _response()

    refresher = _Refresher(_target())
    wrong_kind, _resolver = _downloader(
        unexpected_http,
        refresher=refresher,
        probe=_Probe(),
        muxer=_Muxer(),
    )
    with pytest.raises(MediaDownloadError) as wrong:
        wrong_kind.download(_request(tmp_path / "wrong", kind=AssetKind.AUDIO))
    assert wrong.value.code == "media_type_mismatch"

    no_mux, _resolver = _downloader(
        unexpected_http,
        refresher=_Refresher(_target()),
        probe=_Probe(),
        muxer=None,
    )
    with pytest.raises(MediaDownloadError) as unavailable:
        no_mux.download(_request(tmp_path / "missing"))
    assert unavailable.value.code == "media_mux_unavailable"
    assert unavailable.value.retryable is True
    assert requests == []
