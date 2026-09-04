"""Same-descriptor validation and bounded streaming for archived media."""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Final, Self, cast

from media_sync.security.paths import (
    PathSecurityError,
    assert_existing_regular_file,
    open_existing_regular_read_file,
)

_VERIFY_CHUNK_BYTES: Final = 1024 * 1024
_STREAM_CHUNK_BYTES: Final = 64 * 1024
_MAX_RANGE_HEADER_BYTES: Final = 128
_READY_STATUSES: Final = frozenset({"verified", "exported"})

ARCHIVE_PREVIEW_ERROR_CODES: Final = frozenset(
    {
        "asset_archive_not_ready",
        "asset_archive_missing",
        "asset_archive_invalid",
        "asset_archive_range_unsatisfiable",
    }
)

SAFE_ARCHIVE_MEDIA_TYPES: Final = frozenset(
    {
        "application/pdf",
        "application/x-subrip",
        "audio/flac",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "image/avif",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
        "text/vtt",
        "video/mp4",
        "video/x-flv",
        "video/x-matroska",
    }
)
FALLBACK_ARCHIVE_MEDIA_TYPE: Final = "application/octet-stream"

_ERROR_MESSAGES: Final = {
    "asset_archive_not_ready": "asset archive is not ready for preview",
    "asset_archive_missing": "asset archive bytes are missing",
    "asset_archive_invalid": "asset archive bytes failed validation",
    "asset_archive_range_unsatisfiable": "asset archive byte range is unsatisfiable",
}


class ArchivePreviewError(RuntimeError):
    """A fixed-code archive error that never reflects filesystem input."""

    def __init__(self, code: str) -> None:
        try:
            message = _ERROR_MESSAGES[code]
        except KeyError as exc:  # pragma: no cover - programmer error
            raise ValueError("unknown archive preview error code") from exc
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _fail(code: str) -> ArchivePreviewError:
    return ArchivePreviewError(code)


@dataclass(frozen=True, slots=True)
class ArchivePreviewSource:
    """The closed persisted-asset projection accepted by archive preview."""

    status: str | None
    local_path: str | Path | None = field(repr=False)
    checksum_sha256: str | None
    size_bytes: int | None
    mime_type: str | None


@dataclass(frozen=True, slots=True)
class _FileSnapshot:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def from_stat(cls, details: os.stat_result) -> _FileSnapshot:
        return cls(
            device=details.st_dev,
            inode=details.st_ino,
            size=details.st_size,
            modified_ns=details.st_mtime_ns,
            changed_ns=details.st_ctime_ns,
        )


def _is_reparse(details: os.stat_result) -> bool:
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def _assert_plain_directory(path: Path) -> None:
    try:
        details = path.lstat()
    except FileNotFoundError:
        raise _fail("asset_archive_missing") from None
    except OSError:
        raise _fail("asset_archive_invalid") from None
    if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode) or _is_reparse(details):
        raise _fail("asset_archive_invalid")


def _assert_safe_file_stat(details: os.stat_result, *, expected_size: int) -> None:
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or _is_reparse(details)
        or details.st_nlink != 1
        or details.st_mode & 0o222
        or details.st_size != expected_size
    ):
        raise _fail("asset_archive_invalid")


def _preflight_named_file(path: Path, *, root: Path, expected_size: int) -> os.stat_result:
    _assert_plain_directory(root)
    _assert_plain_directory(root / "sha256")
    _assert_plain_directory(path.parent)
    try:
        details = path.lstat()
    except FileNotFoundError:
        raise _fail("asset_archive_missing") from None
    except OSError:
        raise _fail("asset_archive_invalid") from None
    _assert_safe_file_stat(details, expected_size=expected_size)
    return details


def _windows_extended_path(path: Path) -> str:
    value = os.fspath(path)
    if value.startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]
    return "\\\\?\\" + value


def _open_windows_archive_file(path: Path, *, root: Path) -> BinaryIO:
    """Open one Windows file while denying write and delete sharing."""

    import ctypes
    import msvcrt
    from ctypes import wintypes

    # Keep the shared filesystem policy in front of the native open.  The
    # native OPEN_REPARSE_POINT flag then prevents a final-component swap from
    # turning this check into a followed link.
    assert_existing_regular_file(path, root=root)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    native = kernel32.CreateFileW(
        _windows_extended_path(path),
        0x80000000,  # GENERIC_READ
        0x00000001,  # FILE_SHARE_READ; deliberately deny WRITE and DELETE
        None,
        3,  # OPEN_EXISTING
        0x00200000 | 0x00000080,  # FILE_FLAG_OPEN_REPARSE_POINT | FILE_ATTRIBUTE_NORMAL
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if native is None or int(native) == invalid_handle:
        error_number = ctypes.get_last_error()
        raise PathSecurityError from OSError(error_number, "archive file open failed")

    native_value = int(native)
    try:
        descriptor = msvcrt.open_osfhandle(
            native_value,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0),
        )
    except (OSError, ValueError) as exc:
        kernel32.CloseHandle(native)
        raise PathSecurityError from exc
    try:
        os.set_inheritable(descriptor, False)
        return cast(BinaryIO, os.fdopen(descriptor, "rb"))
    except (OSError, ValueError) as exc:
        with contextlib.suppress(OSError):
            os.close(descriptor)
        raise PathSecurityError from exc


def _open_archive_read_file(path: Path, *, root: Path) -> BinaryIO:
    if os.name == "nt":
        return _open_windows_archive_file(path, root=root)
    return open_existing_regular_read_file(path, root=root)


def safe_archive_media_type(value: str | None) -> str:
    """Return only a MIME type emitted by the verified media probe."""

    if isinstance(value, str) and value in SAFE_ARCHIVE_MEDIA_TYPES:
        return value
    return FALLBACK_ARCHIVE_MEDIA_TYPE


def parse_single_byte_range(value: str, size_bytes: int) -> tuple[int, int]:
    """Parse one strict HTTP ``bytes`` range into inclusive offsets."""

    if (
        not isinstance(value, str)
        or not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes < 0
        or len(value) > _MAX_RANGE_HEADER_BYTES
    ):
        raise _fail("asset_archive_range_unsatisfiable")
    normalized = value.strip(" \t")
    if normalized[:6].lower() != "bytes=":
        raise _fail("asset_archive_range_unsatisfiable")
    if size_bytes == 0:
        raise _fail("asset_archive_range_unsatisfiable")
    raw_range = normalized[6:]
    if raw_range.count("-") != 1 or "," in raw_range:
        raise _fail("asset_archive_range_unsatisfiable")
    raw_start, raw_end = raw_range.split("-", 1)
    if not raw_start and not raw_end:
        raise _fail("asset_archive_range_unsatisfiable")
    if (raw_start and (not raw_start.isascii() or not raw_start.isdecimal())) or (
        raw_end and (not raw_end.isascii() or not raw_end.isdecimal())
    ):
        raise _fail("asset_archive_range_unsatisfiable")

    try:
        if raw_start:
            start = int(raw_start)
            if start >= size_bytes:
                raise _fail("asset_archive_range_unsatisfiable")
            if raw_end:
                requested_end = int(raw_end)
                if requested_end < start:
                    raise _fail("asset_archive_range_unsatisfiable")
                return start, min(requested_end, size_bytes - 1)
            return start, size_bytes - 1

        suffix_size = int(raw_end)
        if suffix_size <= 0:
            raise _fail("asset_archive_range_unsatisfiable")
        return max(0, size_bytes - suffix_size), size_bytes - 1
    except (OverflowError, ValueError):
        raise _fail("asset_archive_range_unsatisfiable") from None


class ArchivePreview:
    """A verified range whose bytes remain owned by one open descriptor."""

    def __init__(
        self,
        handle: BinaryIO,
        path: Path,
        root: Path,
        snapshot: _FileSnapshot,
        *,
        expected_size: int,
        start: int,
        end: int,
        partial: bool,
        etag: str,
        media_type: str,
    ) -> None:
        self._handle = handle
        self._path = path
        self._root = root
        self._snapshot = snapshot
        self._expected_size = expected_size
        self._started = False
        self._closed = False
        self._range_selected = partial
        self.start = start
        self.end = end
        self.content_length = 0 if end < start else end - start + 1
        self.partial = partial
        self.etag = etag
        self.media_type = media_type

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> Self:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the owned descriptor exactly once."""

        if self._closed:
            return
        self._closed = True
        try:
            self._handle.close()
        except Exception:
            raise _fail("asset_archive_invalid") from None

    def _assert_stable(self) -> None:
        try:
            opened = os.fstat(self._handle.fileno())
            named = assert_existing_regular_file(self._path, root=self._root)
        except (OSError, PathSecurityError, ValueError):
            raise _fail("asset_archive_invalid") from None
        _assert_safe_file_stat(opened, expected_size=self._expected_size)
        _assert_safe_file_stat(named, expected_size=self._expected_size)
        if _FileSnapshot.from_stat(opened) != self._snapshot or _FileSnapshot.from_stat(named) != self._snapshot:
            raise _fail("asset_archive_invalid")

    def select_range(self, start: int, end: int) -> Self:
        """Select one inclusive range on this already verified descriptor."""

        if (
            self._started
            or self._closed
            or self._range_selected
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or self._expected_size == 0
            or start < 0
            or end < start
            or end >= self._expected_size
        ):
            with contextlib.suppress(ArchivePreviewError):
                self.close()
            raise _fail("asset_archive_range_unsatisfiable")
        try:
            self._assert_stable()
            if self._handle.seek(start) != start:
                raise _fail("asset_archive_invalid")
            self._assert_stable()
        except ArchivePreviewError:
            with contextlib.suppress(ArchivePreviewError):
                self.close()
            raise
        except Exception:
            with contextlib.suppress(ArchivePreviewError):
                self.close()
            raise _fail("asset_archive_invalid") from None
        self.start = start
        self.end = end
        self.content_length = end - start + 1
        self.partial = True
        self._range_selected = True
        return self

    def iter_bytes(self) -> Iterator[bytes]:
        """Return a single-use bounded iterator that always closes the file."""

        if self._started or self._closed:
            raise _fail("asset_archive_invalid")
        self._started = True
        return self._iter_bytes()

    def _iter_bytes(self) -> Iterator[bytes]:
        remaining = self.content_length
        try:
            self._assert_stable()
            while remaining:
                requested = min(remaining, _STREAM_CHUNK_BYTES)
                chunk = self._handle.read(requested)
                if not isinstance(chunk, bytes) or not chunk or len(chunk) > requested:
                    raise _fail("asset_archive_invalid")
                remaining -= len(chunk)
                self._assert_stable()
                yield chunk
            self._assert_stable()
        except ArchivePreviewError:
            raise
        except Exception:
            raise _fail("asset_archive_invalid") from None
        finally:
            self.close()


class ArchivePreviewService:
    """Open only canonical immutable archive blobs for bounded preview."""

    def __init__(self, archive_root: Path) -> None:
        try:
            self._root = Path(archive_root).expanduser().absolute()
        except (OSError, RuntimeError, TypeError):
            raise _fail("asset_archive_invalid") from None

    def _metadata(self, source: ArchivePreviewSource) -> tuple[Path, str, int]:
        if not isinstance(source.status, str) or source.status not in _READY_STATUSES:
            raise _fail("asset_archive_not_ready")
        if source.local_path is None or source.checksum_sha256 is None or source.size_bytes is None:
            raise _fail("asset_archive_not_ready")
        checksum = source.checksum_sha256
        size_bytes = source.size_bytes
        if (
            not isinstance(checksum, str)
            or len(checksum) != 64
            or any(character not in "0123456789abcdef" for character in checksum)
            or not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes < 0
        ):
            raise _fail("asset_archive_invalid")
        try:
            path = Path(source.local_path)
        except (OSError, TypeError, ValueError):
            raise _fail("asset_archive_invalid") from None
        if not path.is_absolute():
            raise _fail("asset_archive_invalid")
        expected_parent = self._root / "sha256" / checksum[:2]
        expected_stem = checksum
        stem, separator, extension = path.name.rpartition(".")
        if (
            path.parent != expected_parent
            or stem != expected_stem
            or separator != "."
            or not extension
            or not extension.isascii()
            or not extension.isalnum()
        ):
            raise _fail("asset_archive_invalid")
        return path, checksum, size_bytes

    @staticmethod
    def _selected_range(size_bytes: int, byte_range: tuple[int, int] | None) -> tuple[int, int, bool]:
        if byte_range is None:
            return 0, size_bytes - 1, False
        if (
            not isinstance(byte_range, tuple)
            or len(byte_range) != 2
            or not all(isinstance(value, int) and not isinstance(value, bool) for value in byte_range)
        ):
            raise _fail("asset_archive_range_unsatisfiable")
        start, end = byte_range
        if size_bytes == 0 or start < 0 or end < start or end >= size_bytes:
            raise _fail("asset_archive_range_unsatisfiable")
        return start, end, True

    def open(
        self,
        source: ArchivePreviewSource,
        *,
        byte_range: tuple[int, int] | None = None,
    ) -> ArchivePreview:
        """Verify and position one descriptor without reopening for streaming."""

        path, checksum, size_bytes = self._metadata(source)
        start, end, partial = self._selected_range(size_bytes, byte_range)
        _preflight_named_file(path, root=self._root, expected_size=size_bytes)
        try:
            handle = _open_archive_read_file(path, root=self._root)
        except PathSecurityError:
            # Reclassify a safe disappearance between preflight and open while
            # keeping every other race or filesystem rejection fail-closed.
            _preflight_named_file(path, root=self._root, expected_size=size_bytes)
            raise _fail("asset_archive_invalid") from None
        except Exception:
            raise _fail("asset_archive_invalid") from None

        transferred = False
        try:
            opened = os.fstat(handle.fileno())
            named = assert_existing_regular_file(path, root=self._root)
            _assert_safe_file_stat(opened, expected_size=size_bytes)
            _assert_safe_file_stat(named, expected_size=size_bytes)
            snapshot = _FileSnapshot.from_stat(opened)
            if _FileSnapshot.from_stat(named) != snapshot:
                raise _fail("asset_archive_invalid")

            digest = hashlib.sha256()
            remaining = size_bytes
            while remaining:
                requested = min(remaining, _VERIFY_CHUNK_BYTES)
                chunk = handle.read(requested)
                if not isinstance(chunk, bytes) or not chunk or len(chunk) > requested:
                    raise _fail("asset_archive_invalid")
                digest.update(chunk)
                remaining -= len(chunk)
            if handle.read(1) != b"":
                raise _fail("asset_archive_invalid")

            after_hash = os.fstat(handle.fileno())
            current_named = assert_existing_regular_file(path, root=self._root)
            _assert_safe_file_stat(after_hash, expected_size=size_bytes)
            _assert_safe_file_stat(current_named, expected_size=size_bytes)
            if (
                _FileSnapshot.from_stat(after_hash) != snapshot
                or _FileSnapshot.from_stat(current_named) != snapshot
                or digest.hexdigest() != checksum
            ):
                raise _fail("asset_archive_invalid")
            if handle.seek(start) != start:
                raise _fail("asset_archive_invalid")
            final_opened = os.fstat(handle.fileno())
            final_named = assert_existing_regular_file(path, root=self._root)
            _assert_safe_file_stat(final_opened, expected_size=size_bytes)
            _assert_safe_file_stat(final_named, expected_size=size_bytes)
            if _FileSnapshot.from_stat(final_opened) != snapshot or _FileSnapshot.from_stat(final_named) != snapshot:
                raise _fail("asset_archive_invalid")
            preview = ArchivePreview(
                handle,
                path,
                self._root,
                snapshot,
                expected_size=size_bytes,
                start=start,
                end=end,
                partial=partial,
                etag=f'"{checksum}"',
                media_type=safe_archive_media_type(source.mime_type),
            )
            transferred = True
            return preview
        except ArchivePreviewError:
            raise
        except Exception:
            raise _fail("asset_archive_invalid") from None
        finally:
            if not transferred:
                with contextlib.suppress(Exception):
                    handle.close()


__all__ = [
    "ARCHIVE_PREVIEW_ERROR_CODES",
    "FALLBACK_ARCHIVE_MEDIA_TYPE",
    "SAFE_ARCHIVE_MEDIA_TYPES",
    "ArchivePreview",
    "ArchivePreviewError",
    "ArchivePreviewService",
    "ArchivePreviewSource",
    "parse_single_byte_range",
    "safe_archive_media_type",
]
