from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import httpx
import pytest

from media_sync.domain import AssetKind
from media_sync.media import (
    AdapterRefreshLocator,
    ArchivePublisher,
    DirectLocator,
    DownloadLimits,
    DownloadRequest,
    MediaDownloadError,
    PartMetadata,
    ProbeResult,
    ResolvedLocator,
    SafeHttpClient,
    SecureMediaDownloader,
    ValidatedTarget,
)
from media_sync.security.paths import (
    PathSecurityError,
    assert_regular_file,
    confined_file,
    read_regular_file_bytes,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"offline-fixture-payload"
MP4 = b"\x00\x00\x00\x18ftypisom" + b"offline-video-payload"
SRT = b"1\n00:00:00,000 --> 00:00:01,000\nOffline subtitle\n"
VTT = b"WEBVTT\n\n00:00.000 --> 00:01.000\nOffline subtitle\n"
ETAG = '"fixture-v1"'


class _Resolver:
    def resolve(self, _hostname: str, _port: int) -> Sequence[str]:
        return ("8.8.8.8",)


class _BreakingStream(httpx.SyncByteStream):
    def __init__(self, first: bytes) -> None:
        self.first = first

    def __iter__(self) -> Iterator[bytes]:
        yield self.first
        raise httpx.ReadError("remote details must not escape")


def _downloader(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    limits: DownloadLimits | None = None,
    probe: object | None = None,
    targets: list[ValidatedTarget] | None = None,
    monotonic: Callable[[], float] | None = None,
) -> SecureMediaDownloader:
    def factory(target: ValidatedTarget) -> httpx.BaseTransport:
        if targets is not None:
            targets.append(target)
        return httpx.MockTransport(handler)

    if monotonic is None:
        return SecureMediaDownloader(
            SafeHttpClient(_Resolver(), transport_factory=factory),
            limits=limits,
            probe=probe,  # type: ignore[arg-type]
        )
    return SecureMediaDownloader(
        SafeHttpClient(_Resolver(), transport_factory=factory),
        limits=limits,
        probe=probe,  # type: ignore[arg-type]
        monotonic=monotonic,
    )


def _request(tmp_path: Path, *, asset_id: UUID | None = None, kind: AssetKind = AssetKind.IMAGE) -> DownloadRequest:
    return DownloadRequest(
        asset_id=asset_id or uuid4(),
        generation=3,
        locator=DirectLocator("https://media.test/original-without-suffix"),
        work_root=tmp_path / "jobs",
        archive_root=tmp_path / "archive",
        expected_kind=kind,
    )


def _ok(content: bytes = PNG, *, etag: str = ETAG, content_type: str = "application/octet-stream") -> httpx.Response:
    return httpx.Response(
        200,
        headers={"Content-Length": str(len(content)), "Content-Type": content_type, "ETag": etag},
        content=content,
    )


def test_download_verifies_magic_and_publishes_content_addressed_blob(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    targets: list[ValidatedTarget] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _ok()

    request = _request(tmp_path)
    downloader = _downloader(handler, targets=targets)
    result = downloader.download(request)

    assert result.archive_path == tmp_path / "archive" / "sha256" / result.sha256[:2] / f"{result.sha256}.png"
    assert result.archive_path.read_bytes() == PNG
    assert result.size_bytes == len(PNG)
    assert result.mime_type == "image/png"
    assert result.etag == ETAG
    assert result.last_modified is None
    assert result.validator == ETAG
    parts = tmp_path / "jobs" / "parts"
    assert (parts / f"{request.asset_id}.{request.generation}.part").read_bytes() == PNG
    assert (parts / f"{request.asset_id}.{request.generation}.part.json").is_file()
    downloader.cleanup_partial(request.asset_id, request.generation, request.work_root)
    assert not tuple(parts.iterdir())
    assert requests[0].headers["accept-encoding"] == "identity"
    assert targets[0].address == "8.8.8.8"


def test_archive_commit_guard_runs_after_temp_rehash_and_cleans_on_failure(tmp_path: Path) -> None:
    observed_temporary: Path | None = None

    def reject_commit() -> None:
        nonlocal observed_temporary
        files = tuple(path for path in (tmp_path / "archive" / "sha256").rglob("*") if path.is_file())
        assert len(files) == 1
        observed_temporary = files[0]
        assert observed_temporary.name.startswith(".")
        assert observed_temporary.name.endswith(".tmp")
        assert observed_temporary.read_bytes() == PNG
        assert observed_temporary.stat().st_mode & 0o222 == 0
        raise RuntimeError("lease guard rejected archive commit")

    request = replace(_request(tmp_path), before_archive_commit=reject_commit)
    with pytest.raises(RuntimeError, match="lease guard rejected"):
        _downloader(lambda _request: _ok()).download(request)

    assert observed_temporary is not None
    assert not observed_temporary.exists()
    assert not tuple(path for path in (tmp_path / "archive" / "sha256").rglob("*") if path.is_file())
    assert (tmp_path / "jobs" / "parts" / f"{request.asset_id}.{request.generation}.part").read_bytes() == PNG


def test_existing_archive_first_guard_rejection_does_not_repair_writable_blob(tmp_path: Path) -> None:
    downloader = _downloader(lambda _request: _ok())
    first = downloader.download(_request(tmp_path))
    first.archive_path.chmod(0o600)
    before = first.archive_path.stat()
    assert before.st_mode & 0o222
    guard_calls = 0

    def reject_existing() -> None:
        nonlocal guard_calls
        guard_calls += 1
        assert first.archive_path.read_bytes() == PNG
        assert first.archive_path.stat().st_mode & 0o222
        raise RuntimeError("existing blob lease guard rejected")

    request = replace(_request(tmp_path), before_archive_commit=reject_existing)
    with pytest.raises(RuntimeError, match="existing blob lease guard rejected"):
        downloader.download(request)

    assert guard_calls == 1
    assert first.archive_path.read_bytes() == PNG
    after = first.archive_path.stat()
    assert (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) == (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    assert after.st_mode & 0o222 == before.st_mode & 0o222
    assert (tmp_path / "jobs" / "parts" / f"{request.asset_id}.{request.generation}.part").read_bytes() == PNG


def test_existing_archive_is_guarded_before_and_after_writable_repair(tmp_path: Path) -> None:
    downloader = _downloader(lambda _request: _ok())
    first = downloader.download(_request(tmp_path))
    first.archive_path.chmod(0o600)
    observed_writable: list[bool] = []

    def observe_existing() -> None:
        observed_writable.append(bool(first.archive_path.stat().st_mode & 0o222))

    request = replace(_request(tmp_path), before_archive_commit=observe_existing)
    result = downloader.download(request)

    assert result.archive_path == first.archive_path
    assert observed_writable == [True, False]
    assert first.archive_path.read_bytes() == PNG
    assert first.archive_path.stat().st_mode & 0o222 == 0


def test_generation_must_start_at_one(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        DownloadRequest(
            asset_id=uuid4(),
            generation=0,
            locator=DirectLocator("https://media.test/file"),
            work_root=tmp_path / "jobs",
            archive_root=tmp_path / "archive",
        )
    with pytest.raises(ValueError, match="positive"):
        DownloadRequest(
            asset_id=uuid4(),
            generation=True,  # type: ignore[arg-type]
            locator=DirectLocator("https://media.test/file"),
            work_root=tmp_path / "jobs",
            archive_root=tmp_path / "archive",
        )
    with pytest.raises(ValueError, match="positive"):
        PartMetadata(
            asset_id=uuid4(),
            generation=0,
            locator_fingerprint="a" * 64,
            validator_kind=None,
            validator=None,
            expected_length=None,
            current_length=0,
        )


def test_interrupted_stream_resumes_with_strict_range_and_if_range(tmp_path: Path) -> None:
    calls = 0
    split = 12

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(PNG)), "ETag": ETAG},
                stream=_BreakingStream(PNG[:split]),
            )
        assert request.headers["range"] == f"bytes={split}-"
        assert request.headers["if-range"] == ETAG
        return httpx.Response(
            206,
            headers={
                "Content-Length": str(len(PNG) - split),
                "Content-Range": f"bytes {split}-{len(PNG) - 1}/{len(PNG)}",
                "ETag": ETAG,
            },
            content=PNG[split:],
        )

    request = _request(tmp_path)
    downloader = _downloader(handler)
    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(request)
    assert caught.value.code == "download_interrupted"

    result = downloader.download(request)
    assert result.archive_path.read_bytes() == PNG
    assert calls == 2


def test_resume_200_response_restarts_once_without_appending(tmp_path: Path) -> None:
    calls = 0
    split = 8

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(PNG)), "ETag": ETAG},
                stream=_BreakingStream(PNG[:split]),
            )
        if calls == 2:
            assert "range" in request.headers
            return _ok()
        assert "range" not in request.headers
        return _ok()

    request = _request(tmp_path)
    downloader = _downloader(handler)
    with pytest.raises(MediaDownloadError):
        downloader.download(request)
    result = downloader.download(request)

    assert result.archive_path.read_bytes() == PNG
    assert calls == 3


def test_completed_partial_accepts_only_matching_416_total(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(PNG)), "ETag": ETAG},
                stream=_BreakingStream(PNG),
            )
        assert request.headers["range"] == f"bytes={len(PNG)}-"
        return httpx.Response(416, headers={"Content-Range": f"bytes */{len(PNG)}", "ETag": ETAG})

    request = _request(tmp_path)
    downloader = _downloader(handler)
    with pytest.raises(MediaDownloadError):
        downloader.download(request)
    result = downloader.download(request)

    assert result.archive_path.read_bytes() == PNG
    assert calls == 2


def test_416_same_length_with_changed_validator_restarts_old_bytes(tmp_path: Path) -> None:
    calls = 0
    replacement = b"\x89PNG\r\n\x1a\n" + b"R" * (len(PNG) - 8)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(PNG)), "ETag": ETAG},
                stream=_BreakingStream(PNG),
            )
        if calls == 2:
            assert "range" in request.headers
            return httpx.Response(
                416,
                headers={"Content-Range": f"bytes */{len(PNG)}", "ETag": '"fixture-v2"'},
            )
        assert "range" not in request.headers
        return _ok(replacement, etag='"fixture-v2"')

    request = _request(tmp_path)
    downloader = _downloader(handler)
    with pytest.raises(MediaDownloadError):
        downloader.download(request)
    result = downloader.download(request)

    assert result.archive_path.read_bytes() == replacement
    assert result.etag == '"fixture-v2"'
    assert calls == 3


def test_malformed_206_is_rejected_without_appending(tmp_path: Path) -> None:
    calls = 0
    split = 8

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(PNG)), "ETag": ETAG},
                stream=_BreakingStream(PNG[:split]),
            )
        return httpx.Response(
            206,
            headers={
                "Content-Length": str(len(PNG) - split),
                "Content-Range": f"bytes 0-{len(PNG) - split - 1}/{len(PNG)}",
                "ETag": ETAG,
            },
            content=PNG[split:],
        )

    request = _request(tmp_path)
    downloader = _downloader(handler)
    with pytest.raises(MediaDownloadError):
        downloader.download(request)
    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(request)
    assert caught.value.code == "download_range_invalid"


def test_content_length_and_streaming_byte_limits_are_hard(tmp_path: Path) -> None:
    request = _request(tmp_path)
    limit = DownloadLimits(max_bytes=len(PNG) - 1)
    with pytest.raises(MediaDownloadError) as caught:
        _downloader(lambda _request: _ok(), limits=limit).download(request)
    assert caught.value.code == "download_size_limit"

    chunk_limit = DownloadLimits(max_bytes=len(PNG) * 2, max_chunk_bytes=4)
    with pytest.raises(MediaDownloadError) as caught:
        _downloader(lambda _request: _ok(), limits=chunk_limit).download(_request(tmp_path))
    assert caught.value.code == "download_chunk_limit"


def test_total_streaming_time_limit_is_hard(tmp_path: Path) -> None:
    tick = 0.0

    def monotonic() -> float:
        nonlocal tick
        tick += 1.0
        return tick

    limits = DownloadLimits(total_timeout_seconds=1.5)
    with pytest.raises(MediaDownloadError) as caught:
        _downloader(lambda _request: _ok(), limits=limits, monotonic=monotonic).download(_request(tmp_path))
    assert caught.value.code == "download_timeout"


@pytest.mark.parametrize(
    ("content", "content_type", "expected_code"),
    [
        (b"<!doctype html><title>login</title>", "video/mp4", "media_type_unsupported"),
        (PNG, "text/html", "media_type_mismatch"),
        (PNG, "image/png", "media_type_mismatch"),
    ],
)
def test_html_and_kind_mismatches_fail_closed(
    tmp_path: Path,
    content: bytes,
    content_type: str,
    expected_code: str,
) -> None:
    request = _request(tmp_path, kind=AssetKind.VIDEO)
    with pytest.raises(MediaDownloadError) as caught:
        _downloader(lambda _request: _ok(content, content_type=content_type), probe=_Probe(None)).download(request)
    assert caught.value.code == expected_code
    assert content.decode("ascii", errors="ignore") not in str(caught.value)


@pytest.mark.parametrize(
    ("content", "advertised_mime", "expected_mime", "expected_extension"),
    [
        (SRT, "text/plain; charset=utf-8", "application/x-subrip", "srt"),
        (SRT, "application/x-subrip", "application/x-subrip", "srt"),
        (VTT, "text/vtt; charset=utf-8", "text/vtt", "vtt"),
    ],
)
def test_subtitle_advertised_mime_equivalence_allowlist(
    tmp_path: Path,
    content: bytes,
    advertised_mime: str,
    expected_mime: str,
    expected_extension: str,
) -> None:
    result = _downloader(lambda _request: _ok(content, content_type=advertised_mime)).download(
        _request(tmp_path, kind=AssetKind.SUBTITLE)
    )

    assert result.mime_type == expected_mime
    assert result.extension == expected_extension


@pytest.mark.parametrize(
    ("content", "advertised_mime"),
    [
        (SRT, "text/vtt"),
        (VTT, "text/plain"),
        (VTT, "application/x-subrip"),
        (SRT, "text/html"),
        (SRT, "application/problem+json"),
        (SRT, "application/xml"),
        (VTT, "application/xhtml+xml"),
    ],
)
def test_subtitle_advertised_mime_rejects_cross_format_and_markup(
    tmp_path: Path,
    content: bytes,
    advertised_mime: str,
) -> None:
    with pytest.raises(MediaDownloadError) as caught:
        _downloader(lambda _request: _ok(content, content_type=advertised_mime)).download(
            _request(tmp_path, kind=AssetKind.SUBTITLE)
        )

    assert caught.value.code == "media_type_mismatch"


class _Probe:
    def __init__(self, result: ProbeResult | None) -> None:
        self.result = result
        self.calls: list[tuple[float, int]] = []

    def probe(self, _path: Path, *, timeout_seconds: float, max_output_bytes: int) -> ProbeResult | None:
        self.calls.append((timeout_seconds, max_output_bytes))
        return self.result


def test_unknown_magic_can_use_bounded_injected_container_probe(tmp_path: Path) -> None:
    probe = _Probe(ProbeResult("video/mp4", "mp4"))
    unknown = b"generated-container-fixture"
    request = _request(tmp_path, kind=AssetKind.VIDEO)

    result = _downloader(lambda _request: _ok(unknown), probe=probe).download(request)

    assert result.extension == "mp4"
    assert probe.calls == [(10.0, 65536)]


def test_playable_media_requires_structural_probe_before_archive(tmp_path: Path) -> None:
    request = _request(tmp_path, kind=AssetKind.VIDEO)

    with pytest.raises(MediaDownloadError) as unavailable:
        _downloader(lambda _request: _ok(MP4)).download(request)

    assert unavailable.value.code == "media_probe_unavailable"
    assert unavailable.value.retryable is True
    assert not tuple((tmp_path / "archive").rglob("*"))


def test_container_signature_must_agree_with_structural_probe(tmp_path: Path) -> None:
    probe = _Probe(ProbeResult("audio/flac", "flac"))
    request = _request(tmp_path, kind=AssetKind.AUDIO)

    with pytest.raises(MediaDownloadError) as mismatch:
        _downloader(lambda _request: _ok(b"ID3" + b"offline-audio"), probe=probe).download(request)

    assert mismatch.value.code == "media_probe_mismatch"


def test_short_ebml_header_is_never_accepted_without_structural_probe(tmp_path: Path) -> None:
    request = _request(tmp_path, kind=AssetKind.VIDEO)

    with pytest.raises(MediaDownloadError) as unavailable:
        _downloader(lambda _request: _ok(b"\x1aE\xdf\xa3junk")).download(request)

    assert unavailable.value.code == "media_probe_unavailable"


@pytest.mark.parametrize(
    ("content", "kind", "extension", "mime_type", "probe"),
    [
        (
            b"\x00\x00\x00\x18ftypM4A " + b"audio",
            AssetKind.AUDIO,
            "m4a",
            "audio/mp4",
            _Probe(ProbeResult("audio/mp4", "m4a")),
        ),
        (b"\x00\x00\x00\x18ftypavif" + b"image", AssetKind.IMAGE, "avif", "image/avif", None),
    ],
)
def test_bmff_brands_do_not_default_to_video(
    tmp_path: Path,
    content: bytes,
    kind: AssetKind,
    extension: str,
    mime_type: str,
    probe: _Probe | None,
) -> None:
    result = _downloader(lambda _request: _ok(content), probe=probe).download(_request(tmp_path, kind=kind))
    assert result.extension == extension
    assert result.mime_type == mime_type


def test_existing_archive_blob_is_revalidated_and_never_overwritten(tmp_path: Path) -> None:
    request = _request(tmp_path)
    downloader = _downloader(lambda _request: _ok())
    first = downloader.download(request)
    first.archive_path.chmod(0o600)
    first.archive_path.write_bytes(b"X" * len(PNG))

    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(request)

    assert caught.value.code == "archive_blob_invalid"
    assert first.archive_path.read_bytes() == b"X" * len(PNG)


@pytest.mark.parametrize("unsafe_kind", ["symlink", "hardlink", "directory"])
def test_invalid_blob_quarantine_rejects_links_and_directories(tmp_path: Path, unsafe_kind: str) -> None:
    archive_root = tmp_path / "archive"
    digest = hashlib.sha256(PNG).hexdigest()
    parent = archive_root / "sha256" / digest[:2]
    parent.mkdir(parents=True)
    canonical = parent / f"{digest}.png"
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside-evidence")
    if unsafe_kind == "symlink":
        try:
            canonical.symlink_to(outside)
        except OSError:
            pytest.skip("file symlinks are unavailable on this host")
    elif unsafe_kind == "hardlink":
        os.link(outside, canonical)
    else:
        canonical.mkdir()

    with pytest.raises(MediaDownloadError) as caught:
        ArchivePublisher(archive_root).quarantine_invalid(
            canonical,
            sha256=digest,
            size_bytes=len(PNG),
        )

    assert caught.value.code == "filesystem_unsafe"
    assert outside.read_bytes() == b"outside-evidence"
    assert not (archive_root / ".quarantine").exists()


def test_concurrent_same_digest_publication_converges_without_overwrite(tmp_path: Path) -> None:
    requests = (_request(tmp_path, asset_id=uuid4()), _request(tmp_path, asset_id=uuid4()))
    downloader = _downloader(lambda _request: _ok())

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(downloader.download, requests))

    assert results[0].archive_path == results[1].archive_path
    assert results[0].archive_path.read_bytes() == PNG
    assert assert_regular_file(results[0].archive_path, root=tmp_path / "archive").st_nlink == 1


def test_same_asset_generation_partial_lock_prevents_overlapping_workers(tmp_path: Path) -> None:
    entered = Event()
    release = Event()
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(timeout=5.0)
        return _ok()

    request = _request(tmp_path)
    downloader = _downloader(handler)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(downloader.download, request)
        assert entered.wait(timeout=5.0)
        try:
            with pytest.raises(MediaDownloadError) as busy:
                downloader.download(request)
            assert busy.value.code == "download_part_busy"
            assert busy.value.retryable is True
        finally:
            release.set()
        completed = first.result(timeout=5.0)

    assert completed.archive_path.read_bytes() == PNG
    assert calls == 1


def test_partial_metadata_symlink_is_rejected_without_following(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(PNG)), "ETag": ETAG},
            stream=_BreakingStream(PNG[:8]),
        )

    request = _request(tmp_path)
    downloader = _downloader(handler)
    with pytest.raises(MediaDownloadError):
        downloader.download(request)
    metadata = next((tmp_path / "jobs" / "parts").glob("*.part.json"))
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    metadata.unlink()
    try:
        metadata.symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks are unavailable on this host")

    with pytest.raises(MediaDownloadError) as caught:
        downloader.download(request)
    assert caught.value.code == "filesystem_unsafe"


def test_cross_origin_resume_clears_validator_then_restarts_from_zero(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(PNG)), "ETag": ETAG},
                stream=_BreakingStream(PNG[:8]),
            )
        if request.url.host == "media.test":
            if calls == 2:
                assert request.headers["if-range"] == ETAG
            else:
                assert "if-range" not in request.headers
            return httpx.Response(307, headers={"Location": "https://cdn.test/final?signature=ephemeral"})
        assert "if-range" not in request.headers
        assert "range" not in request.headers
        return _ok()

    request = _request(tmp_path)
    downloader = _downloader(handler)
    with pytest.raises(MediaDownloadError):
        downloader.download(request)
    result = downloader.download(request)
    assert result.archive_path.read_bytes() == PNG
    assert calls == 5


class _SignedRefresh:
    def resolve(self, _locator: AdapterRefreshLocator) -> ResolvedLocator:
        return ResolvedLocator("https://media.test/runtime?signature=never-persist")


def test_adapter_refresh_signed_query_is_ephemeral_but_downloadable(tmp_path: Path) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return _ok()

    request = DownloadRequest(
        asset_id=uuid4(),
        generation=1,
        locator=AdapterRefreshLocator("mediacrawler", "xhs/note-1/video/0"),
        work_root=tmp_path / "jobs",
        archive_root=tmp_path / "archive",
        expected_kind=AssetKind.IMAGE,
    )
    downloader = SecureMediaDownloader(
        SafeHttpClient(_Resolver(), transport_factory=lambda _target: httpx.MockTransport(handler)),
        refresher=_SignedRefresh(),
    )

    assert downloader.download(request).archive_path.read_bytes() == PNG
    assert seen == ["https://media.test/runtime?signature=never-persist"]
    assert "never-persist" not in repr(request)


def test_confined_paths_reject_escape_symlink_and_hardlink(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(PathSecurityError):
        confined_file(root, "../escape")

    outside = tmp_path / "outside"
    outside.mkdir()
    linked = root / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this host")
    with pytest.raises(PathSecurityError):
        confined_file(root, Path("linked") / "file")

    regular = root / "regular"
    regular.write_bytes(b"data")
    hardlink = root / "hardlink"
    os.link(regular, hardlink)
    with pytest.raises(PathSecurityError):
        assert_regular_file(regular, root=root)


def test_bounded_read_detects_open_descriptor_identity_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "metadata.json"
    target.write_bytes(b"{}")
    real_fstat = os.fstat
    calls = 0

    def changed_fstat(descriptor: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        result = real_fstat(descriptor)
        if calls == 3:
            values = list(result)
            values[1] += 1
            return os.stat_result(values)
        return result

    monkeypatch.setattr(os, "fstat", changed_fstat)
    with pytest.raises(PathSecurityError):
        read_regular_file_bytes(target, root=root, max_bytes=10)
