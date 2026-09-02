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
    DownloadLimits,
    DownloadRequest,
    MediaDownloadError,
    MediaRequestProfile,
    ProbeResult,
    ResolvedFlvSegmentsLocator,
    ResolvedLocator,
    ResolvedSegmentsLocator,
    SafeHttpClient,
    SecureMediaDownloader,
    ValidatedTarget,
)

ASSET_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
GENERATION = 5
FIRST_PRIMARY = "https://primary.bili.test/segment-0.mp4?deadline=4102444800&sig=first-private"
FIRST_BACKUP = "https://backup.bili.test/segment-0.mp4?deadline=4102444800&sig=first-backup-private"
SECOND_PRIMARY = "https://primary.bili.test/segment-1.mp4?deadline=4102444800&sig=second-private"
SECOND_BACKUP = "https://backup.bili.test/segment-1.mp4?deadline=4102444800&sig=second-backup-private"
FIRST_MP4 = b"\x00\x00\x00\x18ftypisom" + b"multi-segment-first-mp4-payload"
SECOND_MP4 = b"\x00\x00\x00\x18ftypisom" + b"multi-segment-second-mp4-payload"
FINAL_MP4 = b"\x00\x00\x00\x20ftypisom" + b"concatenated-final-mp4-payload"
MP4_PROBE = ProbeResult("video/mp4", "mp4")
FLV_PROBE = ProbeResult("video/x-flv", "flv")
FIRST_ETAG = '"segments-first-v1"'
SECOND_ETAG = '"segments-second-v1"'


class _Resolver:
    def __init__(self, *, explode: bool = False) -> None:
        self.explode = explode
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        if self.explode:
            raise AssertionError("recovery must not perform DNS")
        self.calls.append((hostname, port))
        return ("8.8.8.8",)


def _segment(primary: str, backups: tuple[str, ...] = ()) -> ResolvedLocator:
    return ResolvedLocator(primary, MediaRequestProfile.BILIBILI_MEDIA, backups)


def _target() -> ResolvedSegmentsLocator:
    return ResolvedSegmentsLocator(
        (
            _segment(FIRST_PRIMARY, (FIRST_BACKUP,)),
            _segment(SECOND_PRIMARY, (SECOND_BACKUP,)),
        )
    )


class _Refresher:
    def __init__(self, *targets: ResolvedSegmentsLocator | ResolvedLocator) -> None:
        self.targets = targets
        self.calls = 0

    def resolve(self, _locator: AdapterRefreshLocator) -> ResolvedSegmentsLocator | ResolvedLocator:
        target = self.targets[min(self.calls, len(self.targets) - 1)]
        self.calls += 1
        return target


class _Probe:
    def __init__(self, *, second: ProbeResult = MP4_PROBE, final: ProbeResult = MP4_PROBE) -> None:
        self.second = second
        self.final = final
        self.calls: list[bytes] = []

    def probe(self, path: Path, *, timeout_seconds: float, max_output_bytes: int) -> ProbeResult:
        payload = path.read_bytes()
        self.calls.append(payload)
        if payload == FIRST_MP4:
            return MP4_PROBE
        if payload == SECOND_MP4:
            return self.second
        if payload == FINAL_MP4:
            return self.final
        raise AssertionError("unexpected probe payload")


class _Muxer:
    def __init__(self, payload: bytes = FINAL_MP4, *, fail: bool = False) -> None:
        self.payload = payload
        self.fail = fail
        self.concat_calls: list[tuple[Path, Path, str]] = []

    def concat(
        self,
        list_path: Path,
        output_path: Path,
        *,
        root: Path,
        timeout_seconds: float,
        max_output_bytes: int,
        max_media_bytes: int,
    ) -> None:
        del root, timeout_seconds, max_output_bytes, max_media_bytes
        script = list_path.read_text("ascii")
        self.concat_calls.append((list_path, output_path, script))
        entries = [line.removeprefix("file '").removesuffix("'") for line in script.splitlines()]
        assert [entry for entry in entries] == sorted(
            path.name for path in list_path.parent.glob(f"{ASSET_ID}.{GENERATION}.bili-segment-*.part")
        )
        output_path.write_bytes(self.payload)
        if self.fail:
            raise MediaDownloadError("media_mux_failed")


def _request(tmp_path: Path, *, kind: AssetKind = AssetKind.VIDEO) -> DownloadRequest:
    return DownloadRequest(
        asset_id=ASSET_ID,
        generation=GENERATION,
        locator=AdapterRefreshLocator("mediacrawler", "bili/video/segments-fixture"),
        work_root=tmp_path / "work",
        archive_root=tmp_path / "archive",
        expected_kind=kind,
    )


def _response(payload: bytes, etag: str) -> httpx.Response:
    return httpx.Response(
        200,
        headers={
            "Content-Length": str(len(payload)),
            "Content-Type": "video/mp4",
            "ETag": etag,
        },
        content=payload,
    )


def _downloader(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    refresher: _Refresher,
    probe: _Probe,
    muxer: _Muxer | None,
    limits: DownloadLimits | None = None,
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
            limits=limits,
        ),
        active_resolver,
    )


def _happy_handler(requests: list[httpx.Request]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["referer"] == "https://www.bilibili.com/"
        assert request.headers["origin"] == "https://www.bilibili.com"
        assert request.headers["accept-encoding"] == "identity"
        assert "cookie" not in request.headers and "authorization" not in request.headers
        if str(request.url) == FIRST_PRIMARY:
            return httpx.Response(503)
        if str(request.url) == FIRST_BACKUP:
            return _response(FIRST_MP4, FIRST_ETAG)
        if str(request.url) == SECOND_PRIMARY:
            return _response(SECOND_MP4, SECOND_ETAG)
        raise AssertionError(f"unexpected request {request.url}")

    return handler


def _part_files(root: Path, pattern: str = "*") -> tuple[Path, ...]:
    parts = root / "parts"
    return tuple(sorted((path for path in parts.glob(f"{ASSET_ID}.{GENERATION}{pattern}") if path.is_file()), key=str))


def test_segments_primary_failure_uses_ordered_backup_then_concat_publishes_one_mp4(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    refresher = _Refresher(_target())
    probe = _Probe()
    muxer = _Muxer()
    downloader, resolver = _downloader(
        _happy_handler(requests),
        refresher=refresher,
        probe=probe,
        muxer=muxer,
    )
    request = _request(tmp_path)

    result = downloader.download(request)

    assert result.sha256 == hashlib.sha256(FINAL_MP4).hexdigest()
    assert result.size_bytes == len(FINAL_MP4)
    assert (result.mime_type, result.extension) == ("video/mp4", "mp4")
    assert result.archive_path.read_bytes() == FINAL_MP4
    assert result.archive_path.suffix == ".mp4"
    assert [str(item.url) for item in requests] == [FIRST_PRIMARY, FIRST_BACKUP, SECOND_PRIMARY]
    assert resolver.calls == [("primary.bili.test", 443), ("backup.bili.test", 443), ("primary.bili.test", 443)]
    assert refresher.calls == 1
    assert probe.calls == [FIRST_MP4, SECOND_MP4, FINAL_MP4]
    assert len(muxer.concat_calls) == 1
    list_path, output_path, script = muxer.concat_calls[0]
    assert output_path.name == f"{ASSET_ID}.{GENERATION}.part"
    assert list_path.name == f"{ASSET_ID}.{GENERATION}.segments.txt"
    assert script == (
        f"file '{ASSET_ID}.{GENERATION}.bili-segment-000.part'\nfile '{ASSET_ID}.{GENERATION}.bili-segment-001.part'\n"
    )
    assert not list_path.exists()
    assert len(_part_files(request.work_root, ".bili-segment-*.part")) == 2
    assert len(_part_files(request.work_root, ".bili-segment-*.part.json")) == 2
    assert "private" not in repr(_target())

    downloader.cleanup_partial(request.asset_id, request.generation, request.work_root)
    assert _part_files(request.work_root) == ()


def test_segments_require_exactly_mp4_structural_probes_per_segment(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    downloader, _resolver = _downloader(
        _happy_handler(requests),
        refresher=_Refresher(_target()),
        probe=_Probe(second=FLV_PROBE),
        muxer=_Muxer(),
    )
    request = _request(tmp_path)

    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(request)

    assert caught.value.code == "media_type_mismatch"
    assert [str(item.url) for item in requests] == [FIRST_PRIMARY, FIRST_BACKUP, SECOND_PRIMARY]
    assert len(_part_files(request.work_root, ".bili-segment-000.*")) == 2
    assert not tuple(request.archive_root.rglob("*"))


def test_segments_concat_failure_retains_resumable_segments_and_removes_final_and_script(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []
    downloader, _resolver = _downloader(
        _happy_handler(requests),
        refresher=_Refresher(_target()),
        probe=_Probe(),
        muxer=_Muxer(fail=True),
    )
    request = _request(tmp_path)

    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(request)

    assert caught.value.code == "media_mux_failed"
    assert len(_part_files(request.work_root, ".bili-segment-*.part")) == 2
    assert not _part_files(request.work_root, ".part")
    assert not _part_files(request.work_root, ".part.json")
    assert not (request.work_root / "parts" / f"{ASSET_ID}.{GENERATION}.segments.txt").exists()
    assert not tuple(request.archive_root.rglob("*"))


def test_segments_final_gate_rejects_non_mp4_final_but_keeps_segments(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    downloader, _resolver = _downloader(
        _happy_handler(requests),
        refresher=_Refresher(_target()),
        probe=_Probe(final=FLV_PROBE),
        muxer=_Muxer(),
    )
    request = _request(tmp_path)

    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(request)

    assert caught.value.code == "media_type_mismatch"
    assert len(_part_files(request.work_root, ".bili-segment-*.part")) == 2
    assert not _part_files(request.work_root, ".part")
    assert not tuple(request.archive_root.rglob("*"))


def test_segments_all_auth_exhaustion_refreshes_once_and_rejects_drift(tmp_path: Path) -> None:
    refreshed = ResolvedSegmentsLocator(
        (
            _segment(
                "https://primary.bili.test/segment-0b.mp4?sig=refreshed",
                ("https://backup.bili.test/segment-0b.mp4?sig=refreshed-backup",),
            ),
            _segment(SECOND_PRIMARY),
        )
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        url = str(request.url)
        if url in {FIRST_PRIMARY, FIRST_BACKUP}:
            return httpx.Response(403)
        if url == "https://primary.bili.test/segment-0b.mp4?sig=refreshed":
            return httpx.Response(503)
        if url == "https://backup.bili.test/segment-0b.mp4?sig=refreshed-backup":
            return _response(FIRST_MP4, FIRST_ETAG)
        if url == SECOND_PRIMARY:
            return _response(SECOND_MP4, SECOND_ETAG)
        raise AssertionError(f"unexpected request {request.url}")

    refresher = _Refresher(_target(), refreshed)
    downloader, _resolver = _downloader(handler, refresher=refresher, probe=_Probe(), muxer=_Muxer())

    result = downloader.download(_request(tmp_path))

    assert result.archive_path.read_bytes() == FINAL_MP4
    assert [str(item.url) for item in requests] == [
        FIRST_PRIMARY,
        FIRST_BACKUP,
        "https://primary.bili.test/segment-0b.mp4?sig=refreshed",
        "https://backup.bili.test/segment-0b.mp4?sig=refreshed-backup",
        SECOND_PRIMARY,
    ]
    assert refresher.calls == 2

    def all_auth(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    count_drift = _Refresher(
        _target(),
        ResolvedSegmentsLocator(
            (
                _segment("https://primary.bili.test/only-0.mp4?sig=x"),
                _segment("https://primary.bili.test/only-1.mp4?sig=x"),
                _segment("https://primary.bili.test/only-2.mp4?sig=x"),
            )
        ),
    )
    drift_downloader, _resolver = _downloader(
        all_auth,
        refresher=count_drift,
        probe=_Probe(),
        muxer=_Muxer(),
    )
    with pytest.raises(MediaDownloadError) as caught:
        drift_downloader.download(_request(tmp_path / "count-drift"))
    assert caught.value.code == "locator_refresh_schema_changed"

    type_drift = _Refresher(_target(), _segment("https://ordinary.test/video.mp4"))
    type_downloader, _resolver = _downloader(
        all_auth,
        refresher=type_drift,
        probe=_Probe(),
        muxer=_Muxer(),
    )
    with pytest.raises(MediaDownloadError) as caught:
        type_downloader.download(_request(tmp_path / "type-drift"))
    assert caught.value.code == "locator_refresh_schema_changed"

    twice = _Refresher(_target(), refreshed)
    twice_downloader, _resolver = _downloader(
        all_auth,
        refresher=twice,
        probe=_Probe(),
        muxer=_Muxer(),
    )
    with pytest.raises(MediaDownloadError) as caught:
        twice_downloader.download(_request(tmp_path / "twice"))
    assert caught.value.code == "locator_refresh_auth_expired"
    assert twice.calls == 2


def test_segments_share_one_byte_cap(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    limits = DownloadLimits(max_bytes=len(FIRST_MP4) + len(SECOND_MP4) - 1)
    downloader, _resolver = _downloader(
        _happy_handler(requests),
        refresher=_Refresher(_target()),
        probe=_Probe(),
        muxer=_Muxer(),
        limits=limits,
    )
    request = _request(tmp_path)

    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(request)

    assert caught.value.code == "download_size_limit"
    assert [str(item.url) for item in requests] == [FIRST_PRIMARY, FIRST_BACKUP, SECOND_PRIMARY]
    assert len(_part_files(request.work_root, ".bili-segment-000.*")) == 2


@pytest.mark.parametrize("kind", [AssetKind.IMAGE, AssetKind.AUDIO])
def test_segments_reject_non_video_kinds(tmp_path: Path, kind: AssetKind) -> None:
    requests: list[httpx.Request] = []
    downloader, _resolver = _downloader(
        _happy_handler(requests),
        refresher=_Refresher(_target()),
        probe=_Probe(),
        muxer=_Muxer(),
    )

    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(_request(tmp_path, kind=kind))

    assert caught.value.code == "media_type_mismatch"
    assert requests == []


def test_segments_require_a_muxer(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    downloader, _resolver = _downloader(
        _happy_handler(requests),
        refresher=_Refresher(_target()),
        probe=_Probe(),
        muxer=None,
    )

    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(_request(tmp_path))

    assert caught.value.code == "media_mux_unavailable"
    assert requests == []


def test_segments_prepared_final_recovers_without_network(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    refresher = _Refresher(_target())
    probe = _Probe()
    muxer = _Muxer()
    downloader, _resolver = _downloader(_happy_handler(requests), refresher=refresher, probe=probe, muxer=muxer)
    request = _request(tmp_path)
    downloaded = downloader.download(request)
    assert downloaded.archive_path.read_bytes() == FINAL_MP4

    offline_resolver = _Resolver(explode=True)
    offline_downloader = _downloader(
        lambda _request: pytest.fail("recovery must not perform HTTP"),
        refresher=_Refresher(_target()),
        probe=probe,
        muxer=_Muxer(),
        resolver=offline_resolver,
    )[0]

    recovered = offline_downloader.recover_published(request)

    assert recovered is not None
    assert recovered.archive_path == downloaded.archive_path
    assert recovered.sha256 == downloaded.sha256
    assert (recovered.mime_type, recovered.extension) == ("video/mp4", "mp4")
    assert probe.calls == [FIRST_MP4, SECOND_MP4, FINAL_MP4, FINAL_MP4]


FIRST_FLV = b"FLV\x01\x05\x00\x00\x00\x09" + b"multi-segment-flv-first-payload"
SECOND_FLV = b"FLV\x01\x05\x00\x00\x00\x09" + b"multi-segment-flv-second-payload"
FLV_PROBE = ProbeResult("video/x-flv", "flv")


def _flv_target() -> ResolvedFlvSegmentsLocator:
    return ResolvedFlvSegmentsLocator(
        ResolvedSegmentsLocator(
            (
                _segment(FIRST_PRIMARY, (FIRST_BACKUP,)),
                _segment(SECOND_PRIMARY, (SECOND_BACKUP,)),
            )
        )
    )


class _FlvRefresher:
    def __init__(self, *targets: ResolvedFlvSegmentsLocator | ResolvedSegmentsLocator | ResolvedLocator) -> None:
        self.targets = targets
        self.calls = 0

    def resolve(
        self, _locator: AdapterRefreshLocator
    ) -> ResolvedFlvSegmentsLocator | ResolvedSegmentsLocator | ResolvedLocator:
        target = self.targets[min(self.calls, len(self.targets) - 1)]
        self.calls += 1
        return target


class _FlvProbe:
    def __init__(self, *, second: ProbeResult = FLV_PROBE, final: ProbeResult = MP4_PROBE) -> None:
        self.second = second
        self.final = final
        self.calls: list[bytes] = []

    def probe(self, path: Path, *, timeout_seconds: float, max_output_bytes: int) -> ProbeResult:
        payload = path.read_bytes()
        self.calls.append(payload)
        if payload == FIRST_FLV:
            return FLV_PROBE
        if payload == SECOND_FLV:
            return self.second
        if payload == FINAL_MP4:
            return self.final
        raise AssertionError("unexpected probe payload")


def _flv_handler(requests: list[httpx.Request]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url) == FIRST_PRIMARY:
            return httpx.Response(503)
        if str(request.url) == FIRST_BACKUP:
            return _response(FIRST_FLV, FIRST_ETAG)
        if str(request.url) == SECOND_PRIMARY:
            return _response(SECOND_FLV, SECOND_ETAG)
        raise AssertionError(f"unexpected request {request.url}")

    return handler


def _flv_downloader(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    refresher: _FlvRefresher,
    probe: _FlvProbe,
    muxer: _Muxer | None,
) -> SecureMediaDownloader:
    def transport_factory(_target: ValidatedTarget) -> httpx.BaseTransport:
        return httpx.MockTransport(handler)

    return SecureMediaDownloader(
        SafeHttpClient(_Resolver(), transport_factory=transport_factory),
        refresher=refresher,
        probe=probe,
        muxer=muxer,
    )


def test_flv_segments_primary_failure_uses_backup_then_concat_publishes_only_mp4(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    refresher = _FlvRefresher(_flv_target())
    probe = _FlvProbe()
    muxer = _Muxer()
    downloader = _flv_downloader(_flv_handler(requests), refresher=refresher, probe=probe, muxer=muxer)
    request = _request(tmp_path / "flv")

    result = downloader.download(request)

    assert result.sha256 == hashlib.sha256(FINAL_MP4).hexdigest()
    assert (result.mime_type, result.extension) == ("video/mp4", "mp4")
    assert result.archive_path.read_bytes() == FINAL_MP4
    assert not tuple(request.archive_root.rglob("*.flv"))
    assert [str(item.url) for item in requests] == [FIRST_PRIMARY, FIRST_BACKUP, SECOND_PRIMARY]
    assert refresher.calls == 1
    assert probe.calls == [FIRST_FLV, SECOND_FLV, FINAL_MP4]
    assert len(muxer.concat_calls) == 1
    assert not muxer.concat_calls[0][0].exists()
    assert "private" not in repr(_flv_target())

    downloader.cleanup_partial(request.asset_id, request.generation, request.work_root)
    assert _part_files(request.work_root) == ()


def test_flv_segments_require_exactly_flv_structural_probes_per_segment(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    downloader = _flv_downloader(
        _flv_handler(requests),
        refresher=_FlvRefresher(_flv_target()),
        probe=_FlvProbe(second=MP4_PROBE),
        muxer=_Muxer(),
    )
    request = _request(tmp_path / "flv-mp4-mix")

    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(request)

    assert caught.value.code == "media_type_mismatch"
    assert [str(item.url) for item in requests] == [FIRST_PRIMARY, FIRST_BACKUP, SECOND_PRIMARY]
    assert not tuple(request.archive_root.rglob("*"))


def test_flv_segments_final_gate_rejects_non_mp4_final_but_keeps_segments(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    downloader = _flv_downloader(
        _flv_handler(requests),
        refresher=_FlvRefresher(_flv_target()),
        probe=_FlvProbe(final=FLV_PROBE),
        muxer=_Muxer(),
    )
    request = _request(tmp_path / "flv-final-gate")

    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(request)

    assert caught.value.code == "media_type_mismatch"
    assert len(_part_files(request.work_root, ".bili-segment-*.part")) == 2
    assert not _part_files(request.work_root, ".part")
    assert not (request.work_root / "parts" / f"{ASSET_ID}.{GENERATION}.segments.txt").exists()


def test_flv_segments_all_auth_refresh_keeps_the_typed_shape_or_closes(tmp_path: Path) -> None:
    refreshed = ResolvedFlvSegmentsLocator(
        ResolvedSegmentsLocator(
            (
                _segment(
                    "https://primary.bili.test/segment-0b.flv?sig=refreshed",
                    ("https://backup.bili.test/segment-0b.flv?sig=refreshed-backup",),
                ),
                _segment(SECOND_PRIMARY),
            )
        )
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        url = str(request.url)
        if url in {FIRST_PRIMARY, FIRST_BACKUP}:
            return httpx.Response(403)
        if url == "https://primary.bili.test/segment-0b.flv?sig=refreshed":
            return httpx.Response(503)
        if url == "https://backup.bili.test/segment-0b.flv?sig=refreshed-backup":
            return _response(FIRST_FLV, FIRST_ETAG)
        if url == SECOND_PRIMARY:
            return _response(SECOND_FLV, SECOND_ETAG)
        raise AssertionError(f"unexpected request {request.url}")

    refresher = _FlvRefresher(_flv_target(), refreshed)
    downloader = _flv_downloader(handler, refresher=refresher, probe=_FlvProbe(), muxer=_Muxer())

    assert downloader.download(_request(tmp_path / "flv-refresh")).archive_path.read_bytes() == FINAL_MP4
    assert refresher.calls == 2

    def all_auth(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    ordinary_drift = _FlvRefresher(_flv_target(), _target())
    ordinary_downloader = _flv_downloader(
        all_auth,
        refresher=ordinary_drift,
        probe=_FlvProbe(),
        muxer=_Muxer(),
    )
    with pytest.raises(MediaDownloadError) as caught:
        ordinary_downloader.download(_request(tmp_path / "flv-ordinary-drift"))
    assert caught.value.code == "locator_refresh_schema_changed"

    count_drift = _FlvRefresher(
        _flv_target(),
        ResolvedFlvSegmentsLocator(
            ResolvedSegmentsLocator(
                (
                    _segment("https://primary.bili.test/only-0.flv?sig=x"),
                    _segment("https://primary.bili.test/only-1.flv?sig=x"),
                    _segment("https://primary.bili.test/only-2.flv?sig=x"),
                )
            )
        ),
    )
    count_downloader = _flv_downloader(
        all_auth,
        refresher=count_drift,
        probe=_FlvProbe(),
        muxer=_Muxer(),
    )
    with pytest.raises(MediaDownloadError) as caught:
        count_downloader.download(_request(tmp_path / "flv-count-drift"))
    assert caught.value.code == "locator_refresh_schema_changed"

    twice = _FlvRefresher(_flv_target(), refreshed)
    twice_downloader = _flv_downloader(
        all_auth,
        refresher=twice,
        probe=_FlvProbe(),
        muxer=_Muxer(),
    )
    with pytest.raises(MediaDownloadError) as caught:
        twice_downloader.download(_request(tmp_path / "flv-twice"))
    assert caught.value.code == "locator_refresh_auth_expired"
    assert twice.calls == 2
