"""Bounded byte-signature and optional container probing."""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from media_sync.domain import AssetKind
from media_sync.media.errors import MediaDownloadError
from media_sync.security.paths import (
    PathSecurityError,
    assert_regular_file,
    open_regular_read_file,
    read_regular_file_prefix,
)

_SRT_PREFIX = re.compile(rb"(?:\xef\xbb\xbf)?\s*\d{1,9}\s*\r?\n\s*\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->")
_GENERIC_ADVERTISED_MIMES = frozenset({"", "application/octet-stream", "binary/octet-stream"})
_FORBIDDEN_ADVERTISED_MIMES = frozenset(
    {"text/html", "application/xhtml+xml", "application/json", "text/json", "application/xml", "text/xml"}
)
_SUBTITLE_ADVERTISED_MIMES = {
    "srt": frozenset({"application/x-subrip", "text/plain"}),
    "vtt": frozenset({"text/vtt"}),
}
_MAX_STATIC_IMAGE_CHUNKS = 100_000
_STATIC_IMAGE_RESULTS = frozenset(
    {
        ("image/jpeg", "jpg"),
        ("image/png", "png"),
        ("image/webp", "webp"),
    }
)


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """A verified MIME and safe extension pair."""

    mime_type: str
    extension: str

    def __post_init__(self) -> None:
        if not self.mime_type or "/" not in self.mime_type:
            raise ValueError("mime_type must be a concrete media type")
        if not self.extension or not self.extension.isascii() or not self.extension.isalnum():
            raise ValueError("extension must be ASCII alphanumeric")


class MediaProbe(Protocol):
    """Optional bounded ffprobe-equivalent container verifier."""

    def probe(
        self,
        path: Path,
        *,
        timeout_seconds: float,
        max_output_bytes: int,
    ) -> ProbeResult | None:
        """Return a verified result, or None when the container is unsupported."""
        ...


class ProbeProcessRunner(Protocol):
    """Injectable bounded process runner for offline verification."""

    def run(self, argv: Sequence[str], *, timeout_seconds: float, max_output_bytes: int) -> bytes:
        """Return bounded stdout or raise without embedding child output."""
        ...


class SubprocessProbeRunner:
    """Drain both child pipes with a shared hard cap and timeout."""

    def run(self, argv: Sequence[str], *, timeout_seconds: float, max_output_bytes: int) -> bytes:
        if timeout_seconds <= 0 or max_output_bytes <= 0 or not argv:
            raise ValueError("probe process limits and argv must be non-empty")
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            creationflags=creation_flags,
        )
        if process.stdout is None or process.stderr is None:  # pragma: no cover - PIPE contract
            process.kill()
            raise RuntimeError("probe pipes unavailable")
        lock = threading.Lock()
        overflow = threading.Event()
        stdout = bytearray()
        total = 0

        def drain(pipe: BinaryIO, *, capture: bool) -> None:
            nonlocal total
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    return
                with lock:
                    total += len(chunk)
                    if total > max_output_bytes:
                        overflow.set()
                        with contextlib.suppress(OSError):
                            process.kill()
                        return
                    if capture:
                        stdout.extend(chunk)

        threads = (
            threading.Thread(target=drain, args=(process.stdout,), kwargs={"capture": True}, daemon=True),
            threading.Thread(target=drain, args=(process.stderr,), kwargs={"capture": False}, daemon=True),
        )
        for thread in threads:
            thread.start()
        try:
            return_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            with contextlib.suppress(OSError):
                process.kill()
            process.wait()
            for thread in threads:
                thread.join(timeout=1.0)
            raise TimeoutError("probe timed out") from exc
        for thread in threads:
            thread.join(timeout=1.0)
        if any(thread.is_alive() for thread in threads):
            with contextlib.suppress(OSError):
                process.kill()
            raise RuntimeError("probe pipe did not close")
        if overflow.is_set():
            raise OverflowError("probe output exceeded limit")
        if return_code != 0:
            raise RuntimeError("probe exited unsuccessfully")
        return bytes(stdout)


class FFprobeMediaProbe:
    """Run ffprobe with fixed arguments and map only allowlisted formats."""

    def __init__(self, executable: str = "ffprobe", *, runner: ProbeProcessRunner | None = None) -> None:
        if not executable or "\x00" in executable:
            raise ValueError("ffprobe executable must not be blank")
        self._executable = executable
        self._runner = runner or SubprocessProbeRunner()

    def probe(
        self,
        path: Path,
        *,
        timeout_seconds: float,
        max_output_bytes: int,
    ) -> ProbeResult | None:
        argv = (
            self._executable,
            "-v",
            "error",
            "-show_entries",
            "format=format_name:stream=codec_type,codec_name",
            "-of",
            "json",
            str(path.absolute()),
        )
        payload = self._runner.run(argv, timeout_seconds=timeout_seconds, max_output_bytes=max_output_bytes)
        if len(payload) > max_output_bytes:
            raise OverflowError("probe output exceeded limit")
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("probe output is invalid") from exc
        if not isinstance(decoded, dict):
            raise ValueError("probe output is invalid")
        raw_format = decoded.get("format")
        raw_streams = decoded.get("streams", [])
        if not isinstance(raw_format, dict) or not isinstance(raw_streams, list) or len(raw_streams) > 32:
            raise ValueError("probe output is invalid")
        format_name = raw_format.get("format_name")
        if not isinstance(format_name, str) or len(format_name) > 512:
            raise ValueError("probe output is invalid")
        formats = frozenset(format_name.split(","))
        stream_types: set[str] = set()
        for stream in raw_streams:
            if not isinstance(stream, dict):
                raise ValueError("probe output is invalid")
            codec_type = stream.get("codec_type")
            if codec_type in {"audio", "video"}:
                stream_types.add(codec_type)
        if formats & {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}:
            if "video" in stream_types:
                return ProbeResult("video/mp4", "mp4")
            if "audio" in stream_types:
                return ProbeResult("audio/mp4", "m4a")
        if formats & {"matroska", "webm"}:
            if "video" in stream_types:
                return ProbeResult("video/x-matroska", "mkv")
            if "audio" in stream_types:
                return ProbeResult("audio/webm", "webm")
        if "flv" in formats and "video" in stream_types:
            return ProbeResult("video/x-flv", "flv")
        simple_audio = {
            "flac": ProbeResult("audio/flac", "flac"),
            "mp3": ProbeResult("audio/mpeg", "mp3"),
            "ogg": ProbeResult("audio/ogg", "ogg"),
            "wav": ProbeResult("audio/wav", "wav"),
        }
        for name, result in simple_audio.items():
            if name in formats and "audio" in stream_types:
                return result
        return None


def _sniff(prefix: bytes) -> ProbeResult | None:
    lowered = prefix[:1024].lstrip().lower()
    if lowered.startswith((b"<!doctype html", b"<html", b"<?xml", b"{")):
        return None
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return ProbeResult("image/png", "png")
    if prefix.startswith(b"\xff\xd8\xff"):
        return ProbeResult("image/jpeg", "jpg")
    if prefix.startswith((b"GIF87a", b"GIF89a")):
        return ProbeResult("image/gif", "gif")
    if len(prefix) >= 12 and prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP":
        return ProbeResult("image/webp", "webp")
    if len(prefix) >= 12 and prefix[4:8] == b"ftyp":
        brand = prefix[8:12]
        if brand in {b"avif", b"avis"}:
            return ProbeResult("image/avif", "avif")
        if brand in {b"M4A ", b"M4B ", b"M4P "}:
            return ProbeResult("audio/mp4", "m4a")
        return None
    # EBML identifies a container family, not whether the payload has a video
    # stream (or is even a structurally valid Matroska/WebM file).  Leave the
    # decision to the bounded structural probe.
    if prefix.startswith(b"\x1aE\xdf\xa3"):
        return None
    if prefix.startswith(b"ID3") or (len(prefix) >= 2 and prefix[0] == 0xFF and prefix[1] & 0xE0 == 0xE0):
        return ProbeResult("audio/mpeg", "mp3")
    if prefix.startswith(b"fLaC"):
        return ProbeResult("audio/flac", "flac")
    if len(prefix) >= 12 and prefix.startswith(b"RIFF") and prefix[8:12] == b"WAVE":
        return ProbeResult("audio/wav", "wav")
    if prefix.startswith(b"OggS"):
        return ProbeResult("audio/ogg", "ogg")
    if prefix.startswith(b"%PDF-"):
        return ProbeResult("application/pdf", "pdf")
    if lowered.startswith(b"webvtt"):
        return ProbeResult("text/vtt", "vtt")
    if _SRT_PREFIX.match(prefix):
        return ProbeResult("application/x-subrip", "srt")
    return None


def _kind_accepts(kind: AssetKind | None, result: ProbeResult) -> bool:
    if kind is None:
        return True
    major = result.mime_type.partition("/")[0]
    if kind in {AssetKind.IMAGE, AssetKind.COVER, AssetKind.AVATAR}:
        return major == "image"
    if kind is AssetKind.VIDEO:
        return major == "video"
    if kind is AssetKind.AUDIO:
        return major == "audio"
    if kind is AssetKind.SUBTITLE:
        return result.extension in {"srt", "vtt"}
    return kind is AssetKind.ATTACHMENT


def _advertised_mime_is_forbidden(mime_type: str) -> bool:
    major, separator, subtype = mime_type.partition("/")
    if separator != "/":
        return False
    return (
        mime_type in _FORBIDDEN_ADVERTISED_MIMES
        or subtype.endswith("+json")
        or subtype.endswith("+xml")
        or (major == "text" and subtype == "html")
    )


def _is_static_png(handle: BinaryIO, size: int) -> bool:
    if size < 33 or handle.read(8) != b"\x89PNG\r\n\x1a\n":
        return False
    position = 8
    chunks = 0
    saw_ihdr = False
    saw_idat = False
    while position < size and chunks < _MAX_STATIC_IMAGE_CHUNKS:
        header = handle.read(8)
        if len(header) != 8:
            return False
        length = int.from_bytes(header[:4], "big")
        chunk_type = header[4:]
        chunks += 1
        chunk_end = position + 12 + length
        if (
            length > 0x7FFF_FFFF
            or chunk_end > size
            or any(byte not in range(65, 91) and byte not in range(97, 123) for byte in chunk_type)
        ):
            return False
        if chunks == 1:
            if chunk_type != b"IHDR" or length != 13:
                return False
            saw_ihdr = True
        elif chunk_type == b"IHDR":
            return False
        if chunk_type in {b"acTL", b"fcTL", b"fdAT"}:
            return False
        if chunk_type == b"IDAT":
            saw_idat = True
        handle.seek(length + 4, os.SEEK_CUR)
        position = chunk_end
        if chunk_type == b"IEND":
            return length == 0 and saw_ihdr and saw_idat and position == size
    return False


def _is_static_webp(handle: BinaryIO, size: int) -> bool:
    header = handle.read(12)
    if (
        size < 20
        or len(header) != 12
        or header[:4] != b"RIFF"
        or header[8:] != b"WEBP"
        or int.from_bytes(header[4:8], "little") + 8 != size
    ):
        return False
    position = 12
    chunks = 0
    saw_image_payload = False
    saw_vp8x = False
    while position < size and chunks < _MAX_STATIC_IMAGE_CHUNKS:
        chunk_header = handle.read(8)
        if len(chunk_header) != 8:
            return False
        chunk_type = chunk_header[:4]
        length = int.from_bytes(chunk_header[4:], "little")
        chunks += 1
        padded_length = length + (length & 1)
        chunk_end = position + 8 + padded_length
        if chunk_end > size or chunk_type in {b"ANIM", b"ANMF"}:
            return False
        if chunk_type == b"VP8X":
            if saw_vp8x or length != 10:
                return False
            flags = handle.read(1)
            if len(flags) != 1 or flags[0] & 0x02:
                return False
            handle.seek(length - 1 + (length & 1), os.SEEK_CUR)
            saw_vp8x = True
        else:
            handle.seek(padded_length, os.SEEK_CUR)
        if chunk_type in {b"VP8 ", b"VP8L"}:
            saw_image_payload = True
        position = chunk_end
    return position == size and saw_image_payload and chunks < _MAX_STATIC_IMAGE_CHUNKS


def _is_static_image(handle: BinaryIO, size: int, result: ProbeResult) -> bool:
    if (result.mime_type, result.extension) not in _STATIC_IMAGE_RESULTS:
        return False
    if result.mime_type == "image/jpeg":
        if size < 4 or handle.read(2) != b"\xff\xd8":
            return False
        handle.seek(-2, os.SEEK_END)
        return handle.read(2) == b"\xff\xd9"
    if result.mime_type == "image/png":
        return _is_static_png(handle, size)
    return _is_static_webp(handle, size)


def _verify_static_image(path: Path, *, root: Path, result: ProbeResult) -> None:
    try:
        with open_regular_read_file(path, root=root) as handle:
            opened = os.fstat(handle.fileno())
            qualified = _is_static_image(handle, opened.st_size, result)
            after_read = os.fstat(handle.fileno())
        current = assert_regular_file(path, root=root)
    except PathSecurityError as exc:
        raise MediaDownloadError("filesystem_unsafe") from exc
    except OSError as exc:
        raise MediaDownloadError("filesystem_write_failed") from exc
    identities = (
        (opened.st_dev, opened.st_ino),
        (after_read.st_dev, after_read.st_ino),
        (current.st_dev, current.st_ino),
    )
    if len(set(identities)) != 1:
        raise MediaDownloadError("filesystem_unsafe")
    if not qualified:
        raise MediaDownloadError("media_image_not_static")


def verify_media(
    path: Path,
    *,
    root: Path,
    expected_kind: AssetKind | None,
    advertised_mime: str | None,
    probe: MediaProbe | None,
    require_static_image: bool = False,
    sniff_bytes: int = 65536,
    probe_timeout_seconds: float = 10.0,
    probe_output_bytes: int = 65536,
) -> ProbeResult:
    """Verify bytes without trusting URL suffix or disposition metadata."""

    if type(require_static_image) is not bool:
        raise ValueError("require_static_image must be a boolean")
    if sniff_bytes <= 0 or probe_timeout_seconds <= 0 or probe_output_bytes <= 0:
        raise ValueError("probe limits must be positive")
    try:
        assert_regular_file(path, root=root)
        prefix = read_regular_file_prefix(path, root=root, max_bytes=sniff_bytes)
    except PathSecurityError as exc:
        raise MediaDownloadError("filesystem_unsafe") from exc
    except OSError as exc:
        raise MediaDownloadError("filesystem_write_failed") from exc
    sniffed = _sniff(prefix)
    if sniffed is not None and not _kind_accepts(expected_kind, sniffed):
        raise MediaDownloadError("media_type_mismatch")
    sniffed_major = None if sniffed is None else sniffed.mime_type.partition("/")[0]
    requires_structural_probe = expected_kind in {AssetKind.VIDEO, AssetKind.AUDIO} or sniffed_major in {
        "video",
        "audio",
    }
    result = sniffed
    if requires_structural_probe and probe is None:
        raise MediaDownloadError("media_probe_unavailable")
    if probe is not None and (requires_structural_probe or result is None):
        try:
            probed = probe.probe(
                path,
                timeout_seconds=probe_timeout_seconds,
                max_output_bytes=probe_output_bytes,
            )
        except Exception as exc:
            raise MediaDownloadError("media_probe_failed") from exc
        if probed is None:
            result = None
        elif sniffed is not None and (sniffed.mime_type != probed.mime_type or sniffed.extension != probed.extension):
            raise MediaDownloadError("media_probe_mismatch")
        else:
            result = probed
    if result is None:
        raise MediaDownloadError("media_type_unsupported")
    if not _kind_accepts(expected_kind, result):
        raise MediaDownloadError("media_type_mismatch")
    if require_static_image:
        if expected_kind not in {None, AssetKind.IMAGE, AssetKind.COVER, AssetKind.AVATAR}:
            raise MediaDownloadError("media_type_mismatch")
        _verify_static_image(path, root=root, result=result)
    if advertised_mime:
        advertised = advertised_mime.partition(";")[0].strip().lower()
        if _advertised_mime_is_forbidden(advertised):
            raise MediaDownloadError("media_type_mismatch")
        if advertised not in _GENERIC_ADVERTISED_MIMES:
            subtitle_mimes = _SUBTITLE_ADVERTISED_MIMES.get(result.extension)
            if subtitle_mimes is not None and advertised not in subtitle_mimes:
                raise MediaDownloadError("media_type_mismatch")
            advertised_major = advertised.partition("/")[0]
            verified_major = result.mime_type.partition("/")[0]
            if subtitle_mimes is None and advertised_major != verified_major:
                raise MediaDownloadError("media_type_mismatch")
    return result


__all__ = [
    "FFprobeMediaProbe",
    "MediaProbe",
    "ProbeProcessRunner",
    "ProbeResult",
    "SubprocessProbeRunner",
    "verify_media",
]
