"""Staged rendering and conflict-safe publication for Emby/Jellyfin."""

from __future__ import annotations

import contextlib
import ctypes
import errno
import hashlib
import json
import math
import os
import re
import stat
import sys
import threading
import time
import unicodedata
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import uuid4

from .errors import ExportConflictError, ExportError
from .layout import (
    LAYOUT_VERSION,
    MANIFEST_NAME,
    LayoutPlan,
    PlannedFile,
    author_relative_directory,
    build_layout_plan,
)
from .models import (
    ExportAuthor,
    ExportContent,
    ExportResult,
    ManagedFile,
    ManagedFileInspection,
    PublishedIdentity,
    PublishedTreeInspection,
    RenderedExport,
)

_CHUNK_BYTES = 1024 * 1024
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_TRANSACTION_ROOT_NAME = ".media-sync-transactions-v1"
_TRANSACTION_CONFLICT_MARKER = "RECOVERY_REQUIRED"
_TRANSACTION_SCHEMA_VERSION = 2
_PUBLISHED_EXPORT_INVALID = "published_export_invalid"
_PUBLISHED_INSPECTION_DRIFTED = "published_tree_drifted"
_PUBLISHED_INSPECTION_DEADLINE = "published_inspection_deadline"
_PUBLISHED_INSPECTION_BUSY = "published_inspection_busy"
_LOCK_ROOT_NAME = ".media-sync-locks-v1"
_MAX_INSPECTION_FILES = 128
_JOB_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_WINDOWS_ILLEGAL = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul", "clock$"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)
_LOCKS_GUARD = threading.Lock()
_LOCAL_LOCKS: dict[str, threading.Lock] = {}

FaultInjector = Callable[[str, str | None], None]


@dataclass(frozen=True, slots=True)
class _Manifest:
    author_platform: str
    author_remote_id: str
    source_fingerprint: str
    tree_sha256: str
    files: tuple[ManagedFile, ...]


@dataclass(frozen=True, slots=True)
class _FileSignature:
    device: int
    inode: int
    mode: int
    links: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True, slots=True)
class _BoundDirectory:
    """An existing directory pinned for one read-only tree inspection."""

    path: Path
    signature: _FileSignature
    parent: _BoundDirectory | None
    descriptor: int | None
    windows_handle: int | None


@dataclass(frozen=True, slots=True)
class _TransactionOperation:
    kind: str
    relative_path: str
    old_file: ManagedFile | None
    new_file: ManagedFile | None
    capture_path: Path
    candidate_path: Path | None
    verification_path: Path | None


@dataclass(frozen=True, slots=True)
class _PublishTransaction:
    directory: Path
    journal_path: Path
    author_directory: Path
    manifest_path: Path
    predecessor_manifest: ManagedFile | None
    desired_manifest: ManagedFile
    manifest_capture_path: Path
    manifest_candidate_path: Path
    manifest_verification_path: Path
    operations: tuple[_TransactionOperation, ...]


@dataclass(slots=True)
class _TransactionRuntime:
    captured_operations: set[str]
    installed_operations: set[str]
    manifest_captured: bool = False
    manifest_installed: bool = False


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_reparse(path_stat: os.stat_result) -> bool:
    attributes = getattr(path_stat, "st_file_attributes", 0)
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & flag)


def _signature(path_stat: os.stat_result) -> _FileSignature:
    return _FileSignature(
        device=path_stat.st_dev,
        inode=path_stat.st_ino,
        mode=path_stat.st_mode,
        links=path_stat.st_nlink,
        size=path_stat.st_size,
        modified_ns=int(getattr(path_stat, "st_mtime_ns", path_stat.st_mtime * 1_000_000_000)),
        changed_ns=int(getattr(path_stat, "st_ctime_ns", path_stat.st_ctime * 1_000_000_000)),
    )


def _same_identity(first: _FileSignature, second: _FileSignature) -> bool:
    return (first.device, first.inode, stat.S_IFMT(first.mode)) == (
        second.device,
        second.inode,
        stat.S_IFMT(second.mode),
    )


def _safe_lstat(path: Path) -> os.stat_result | None:
    try:
        result = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(result.st_mode) or _is_reparse(result):
        raise ExportConflictError("unsafe_existing_path")
    return result


def _safe_lstat_as(path: Path, error_code: str) -> os.stat_result | None:
    try:
        return _safe_lstat(path)
    except ExportConflictError:
        raise ExportConflictError(error_code) from None


def _safe_bound_lstat(
    directory: _BoundDirectory,
    name: str,
    *,
    error_code: str,
) -> os.stat_result | None:
    """Stat one direct child without following it or an unpinned POSIX parent."""

    if directory.descriptor is None:
        return _safe_lstat_as(directory.path / name, error_code)
    try:
        result = os.stat(name, dir_fd=directory.descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError:
        raise ExportConflictError(error_code) from None
    if stat.S_ISLNK(result.st_mode) or _is_reparse(result):
        raise ExportConflictError(error_code)
    return result


def _verify_bound_directory(directory: _BoundDirectory, *, error_code: str) -> None:
    """Require every pinned directory to remain at its original tree edge."""

    parent = directory.parent
    if parent is None:
        current_stat = _safe_lstat_as(directory.path, error_code)
    else:
        _verify_bound_directory(parent, error_code=error_code)
        current_stat = _safe_bound_lstat(parent, directory.path.name, error_code=error_code)
    if current_stat is None or not stat.S_ISDIR(current_stat.st_mode):
        raise ExportConflictError(error_code)
    current = _signature(current_stat)
    if not _same_identity(directory.signature, current):
        raise ExportConflictError(error_code)
    if directory.descriptor is not None:
        opened_stat = os.fstat(directory.descriptor)
        if not stat.S_ISDIR(opened_stat.st_mode) or not _same_identity(directory.signature, _signature(opened_stat)):
            raise ExportConflictError(error_code)


def _open_windows_directory_handle(path: Path) -> int:
    """Pin a Windows directory without granting a concurrent delete/rename share."""

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    create_file.restype = ctypes.c_void_p
    file_share_read = 0x00000001
    file_share_write = 0x00000002
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000
    file_flag_backup_semantics = 0x02000000
    raw_handle = create_file(
        str(path),
        0,
        file_share_read | file_share_write,
        None,
        open_existing,
        file_flag_open_reparse_point | file_flag_backup_semantics,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if raw_handle is None or raw_handle == invalid_handle:
        raise OSError(ctypes.get_last_error(), "could not bind existing directory")
    return int(raw_handle)


def _close_windows_handle(handle: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (ctypes.c_void_p,)
    close_handle.restype = ctypes.c_int
    close_handle(ctypes.c_void_p(handle))


@contextlib.contextmanager
def _bind_existing_directory(
    path: Path,
    *,
    error_code: str,
    parent: _BoundDirectory | None = None,
) -> Iterator[_BoundDirectory]:
    """Open an existing directory as a stable, non-link inspection anchor."""

    declared_stat = (
        _safe_lstat_as(path, error_code)
        if parent is None
        else _safe_bound_lstat(parent, path.name, error_code=error_code)
    )
    if declared_stat is None or not stat.S_ISDIR(declared_stat.st_mode):
        raise ExportConflictError(error_code)
    declared = _signature(declared_stat)
    descriptor: int | None = None
    windows_handle: int | None = None
    try:
        if os.name == "nt":
            windows_handle = _open_windows_directory_handle(path)
            opened = declared
        else:
            flags = (
                os.O_RDONLY
                | getattr(os, "O_BINARY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(path, flags) if parent is None else os.open(path.name, flags, dir_fd=parent.descriptor)
            opened_stat = os.fstat(descriptor)
            if not stat.S_ISDIR(opened_stat.st_mode) or _is_reparse(opened_stat):
                raise ExportConflictError(error_code)
            opened = _signature(opened_stat)
        current_stat = (
            _safe_lstat_as(path, error_code)
            if parent is None
            else _safe_bound_lstat(parent, path.name, error_code=error_code)
        )
        if current_stat is None or not stat.S_ISDIR(current_stat.st_mode):
            raise ExportConflictError(error_code)
        if not _same_identity(declared, opened) or not _same_identity(opened, _signature(current_stat)):
            raise ExportConflictError(error_code)
        bound = _BoundDirectory(path, opened, parent, descriptor, windows_handle)
        _verify_bound_directory(bound, error_code=error_code)
        try:
            yield bound
        finally:
            _verify_bound_directory(bound, error_code=error_code)
    except OSError:
        raise ExportConflictError(error_code) from None
    finally:
        if descriptor is not None:
            with contextlib.suppress(OSError):
                os.close(descriptor)
        if windows_handle is not None:
            _close_windows_handle(windows_handle)


def _exact_bound_child_name(directory: _BoundDirectory, expected: str, *, error_code: str) -> str | None:
    """Resolve one direct child with the exporter's cross-platform case contract."""

    _verify_bound_directory(directory, error_code=error_code)
    try:
        if directory.descriptor is None:
            with os.scandir(directory.path) as entries:
                names = [entry.name for entry in entries]
        else:
            names = os.listdir(directory.descriptor)
    except OSError:
        raise ExportConflictError(error_code) from None
    folded = unicodedata.normalize("NFC", expected).casefold()
    matches = [name for name in names if unicodedata.normalize("NFC", name).casefold() == folded]
    _verify_bound_directory(directory, error_code=error_code)
    if len(matches) > 1 or (matches and matches[0] != expected):
        raise ExportConflictError(error_code)
    return None if not matches else matches[0]


def _bind_directory_parts(
    stack: contextlib.ExitStack,
    root: _BoundDirectory,
    parts: Sequence[str],
    *,
    error_code: str,
) -> _BoundDirectory:
    current = root
    for part in parts:
        if _exact_bound_child_name(current, part, error_code=error_code) is None:
            raise ExportConflictError(error_code)
        current = stack.enter_context(
            _bind_existing_directory(current.path / part, error_code=error_code, parent=current)
        )
    return current


@contextlib.contextmanager
def _safe_bound_regular_reader(
    directory: _BoundDirectory,
    name: str,
    *,
    error_code: str,
    single_link: bool,
) -> Iterator[BinaryIO]:
    """Open a direct child from a pinned directory and fence its exact entry."""

    _verify_bound_directory(directory, error_code=error_code)
    declared_stat = _safe_bound_lstat(directory, name, error_code=error_code)
    if (
        declared_stat is None
        or not stat.S_ISREG(declared_stat.st_mode)
        or (single_link and declared_stat.st_nlink != 1)
    ):
        raise ExportConflictError(error_code)
    declared = _signature(declared_stat)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = (
            os.open(directory.path / name, flags)
            if directory.descriptor is None
            else os.open(name, flags, dir_fd=directory.descriptor)
        )
    except OSError:
        raise ExportConflictError(error_code) from None
    handle = os.fdopen(descriptor, "rb")
    try:
        opened_stat = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or _is_reparse(opened_stat)
            or (single_link and opened_stat.st_nlink != 1)
        ):
            raise ExportConflictError(error_code)
        opened = _signature(opened_stat)
        current_stat = _safe_bound_lstat(directory, name, error_code=error_code)
        if current_stat is None or (single_link and current_stat.st_nlink != 1):
            raise ExportConflictError(error_code)
        if not _same_identity(declared, opened) or not _same_identity(opened, _signature(current_stat)):
            raise ExportConflictError(error_code)
        _verify_bound_directory(directory, error_code=error_code)
        yield handle
        final = _signature(os.fstat(handle.fileno()))
        final_path_stat = _safe_bound_lstat(directory, name, error_code=error_code)
        if final_path_stat is None or (single_link and final_path_stat.st_nlink != 1):
            raise ExportConflictError(error_code)
        if final != opened or not _same_identity(final, _signature(final_path_stat)):
            raise ExportConflictError(error_code)
        _verify_bound_directory(directory, error_code=error_code)
    finally:
        handle.close()


@contextlib.contextmanager
def _safe_regular_reader(path: Path, *, error_code: str) -> Iterator[BinaryIO]:
    declared_stat = _safe_lstat_as(path, error_code)
    if declared_stat is None or not stat.S_ISREG(declared_stat.st_mode):
        raise ExportConflictError(error_code)
    declared = _signature(declared_stat)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise ExportConflictError(error_code) from None
    handle = os.fdopen(descriptor, "rb")
    try:
        opened_stat = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened_stat.st_mode) or _is_reparse(opened_stat):
            raise ExportConflictError(error_code)
        opened = _signature(opened_stat)
        current_stat = _safe_lstat_as(path, error_code)
        if current_stat is None:
            raise ExportConflictError(error_code)
        current = _signature(current_stat)
        if not _same_identity(declared, opened) or not _same_identity(opened, current):
            raise ExportConflictError(error_code)
        yield handle
        final = _signature(os.fstat(handle.fileno()))
        final_path_stat = _safe_lstat_as(path, error_code)
        if final_path_stat is None:
            raise ExportConflictError(error_code)
        final_path = _signature(final_path_stat)
        if final != opened or not _same_identity(final, final_path):
            raise ExportConflictError(error_code)
    finally:
        handle.close()


def _read_safe_regular(path: Path, *, error_code: str, max_bytes: int | None = None) -> bytes:
    with _safe_regular_reader(path, error_code=error_code) as source:
        payload = source.read() if max_bytes is None else source.read(max_bytes + 1)
    if max_bytes is not None and len(payload) > max_bytes:
        raise ExportConflictError(error_code)
    return payload


def _sha256_file(path: Path, *, error_code: str = "unsafe_existing_path") -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with _safe_regular_reader(path, error_code=error_code) as source:
        while chunk := source.read(_CHUNK_BYTES):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def _ensure_directory(path: Path) -> None:
    existing = _safe_lstat(path)
    if existing is None:
        if path.parent == path:
            raise ExportConflictError("unsafe_existing_path")
        _ensure_directory(path.parent)
        try:
            path.mkdir(exist_ok=False)
        except FileExistsError:
            existing = _safe_lstat(path)
            if existing is None or not stat.S_ISDIR(existing.st_mode):
                raise ExportConflictError("unsafe_existing_path") from None
    elif not stat.S_ISDIR(existing.st_mode):
        raise ExportConflictError("unsafe_existing_path")
    verified = _safe_lstat(path)
    if verified is None or not stat.S_ISDIR(verified.st_mode):
        raise ExportConflictError("unsafe_existing_path")


def _ensure_child_directories(root: Path, relative_parent: PurePosixPath) -> Path:
    current = root
    for part in relative_parent.parts:
        current = current / part
        _ensure_directory(current)
    return current


def _validate_relative_path(value: str) -> PurePosixPath:
    if not value or "\\" in value or unicodedata.normalize("NFC", value) != value:
        raise ExportConflictError("managed_manifest_invalid")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ExportConflictError("managed_manifest_invalid")
    if value == MANIFEST_NAME:
        raise ExportConflictError("managed_manifest_invalid")
    for part in relative.parts:
        if (
            len(part.encode("utf-8")) > 255
            or part.rstrip(" .") != part
            or any(character in _WINDOWS_ILLEGAL or ord(character) < 32 or ord(character) == 127 for character in part)
            or part.split(".", maxsplit=1)[0].casefold() in _WINDOWS_RESERVED
        ):
            raise ExportConflictError("managed_manifest_invalid")
    return relative


def _manifest_payload(rendered: RenderedExport) -> dict[str, object]:
    return {
        "author": {
            "platform": rendered.author.platform,
            "remote_id": rendered.author.remote_id,
        },
        "content_fingerprints": [
            {
                "platform": item.platform,
                "remote_id": item.remote_id,
                "remote_type": item.remote_type,
                "sha256": item.sha256,
            }
            for item in rendered.content_fingerprints
        ],
        "files": [
            {
                "path": item.relative_path,
                "sha256": item.sha256,
                "size_bytes": item.size_bytes,
            }
            for item in rendered.files
        ],
        "layout_version": rendered.layout_version,
        "schema_version": 1,
        "source_fingerprint": rendered.source_fingerprint,
        "tree_sha256": rendered.tree_sha256,
    }


def _manifest_bytes(rendered: RenderedExport) -> bytes:
    return _canonical_json_bytes(_manifest_payload(rendered))


def _parse_manifest(payload: bytes, author: ExportAuthor) -> _Manifest:
    if len(payload) > _MAX_MANIFEST_BYTES:
        raise ExportConflictError("managed_manifest_invalid")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ExportConflictError("managed_manifest_invalid") from None
    if not isinstance(decoded, dict) or set(decoded) != {
        "author",
        "content_fingerprints",
        "files",
        "layout_version",
        "schema_version",
        "source_fingerprint",
        "tree_sha256",
    }:
        raise ExportConflictError("managed_manifest_invalid")
    if decoded["schema_version"] != 1 or decoded["layout_version"] != LAYOUT_VERSION:
        raise ExportConflictError("managed_manifest_invalid")
    author_payload = decoded["author"]
    if not isinstance(author_payload, dict) or set(author_payload) != {"platform", "remote_id"}:
        raise ExportConflictError("managed_manifest_invalid")
    if author_payload != {"platform": author.platform, "remote_id": author.remote_id}:
        raise ExportConflictError("managed_manifest_identity_mismatch")
    source_fingerprint = decoded["source_fingerprint"]
    tree_sha256 = decoded["tree_sha256"]
    if not isinstance(source_fingerprint, str) or _SHA256_PATTERN.fullmatch(source_fingerprint) is None:
        raise ExportConflictError("managed_manifest_invalid")
    if not isinstance(tree_sha256, str) or _SHA256_PATTERN.fullmatch(tree_sha256) is None:
        raise ExportConflictError("managed_manifest_invalid")
    content_fingerprints = decoded["content_fingerprints"]
    if not isinstance(content_fingerprints, list):
        raise ExportConflictError("managed_manifest_invalid")
    for item in content_fingerprints:
        if (
            not isinstance(item, dict)
            or set(item) != {"platform", "remote_id", "remote_type", "sha256"}
            or not all(isinstance(item[key], str) for key in ("platform", "remote_id", "remote_type", "sha256"))
            or _SHA256_PATTERN.fullmatch(item["sha256"]) is None
        ):
            raise ExportConflictError("managed_manifest_invalid")
    files_payload = decoded["files"]
    if not isinstance(files_payload, list):
        raise ExportConflictError("managed_manifest_invalid")
    files: list[ManagedFile] = []
    seen: set[str] = set()
    for item in files_payload:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size_bytes"}:
            raise ExportConflictError("managed_manifest_invalid")
        path_value = item["path"]
        checksum = item["sha256"]
        size = item["size_bytes"]
        if (
            not isinstance(path_value, str)
            or not isinstance(checksum, str)
            or _SHA256_PATTERN.fullmatch(checksum) is None
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            raise ExportConflictError("managed_manifest_invalid")
        relative = _validate_relative_path(path_value)
        folded = relative.as_posix().casefold()
        if folded in seen:
            raise ExportConflictError("managed_manifest_invalid")
        seen.add(folded)
        files.append(ManagedFile(relative.as_posix(), checksum, size))
    if files != sorted(files, key=lambda item: (item.relative_path.casefold(), item.relative_path)):
        raise ExportConflictError("managed_manifest_invalid")
    if _tree_sha256(files) != tree_sha256:
        raise ExportConflictError("managed_manifest_invalid")
    return _Manifest(
        author_platform=author.platform,
        author_remote_id=author.remote_id,
        source_fingerprint=source_fingerprint,
        tree_sha256=tree_sha256,
        files=tuple(files),
    )


def _read_manifest_payload(path: Path) -> bytes | None:
    existing = _safe_lstat(path)
    if existing is None:
        return None
    if not stat.S_ISREG(existing.st_mode) or existing.st_size > _MAX_MANIFEST_BYTES:
        raise ExportConflictError("managed_manifest_invalid")
    return _read_safe_regular(
        path,
        error_code="managed_manifest_invalid",
        max_bytes=_MAX_MANIFEST_BYTES,
    )


def _load_manifest(path: Path, author: ExportAuthor) -> tuple[_Manifest | None, bytes | None]:
    payload = _read_manifest_payload(path)
    if payload is None:
        return None, None
    return _parse_manifest(payload, author), payload


def _read_predecessor(
    export_root: Path,
    author_directory: Path,
    manifest_path: Path,
    author: ExportAuthor,
) -> tuple[_Manifest | None, bytes | None]:
    root_stat = _safe_lstat(export_root)
    if root_stat is not None and not stat.S_ISDIR(root_stat.st_mode):
        raise ExportConflictError("unsafe_existing_path")
    author_stat = _safe_lstat(author_directory)
    if author_stat is not None and not stat.S_ISDIR(author_stat.st_mode):
        raise ExportConflictError("unsafe_existing_path")
    return _load_manifest(manifest_path, author)


def _verify_published_files(
    author_directory: Path,
    files: Sequence[ManagedFile],
    *,
    error_code: str,
) -> None:
    for item in files:
        relative = _validate_relative_path(item.relative_path)
        existing = _existing_case_variant(author_directory, relative)
        if existing is None:
            raise ExportConflictError(error_code)
        _verify_exact_file(existing, item, error_code=error_code)


def _fence_render_predecessor(
    export_root: Path,
    author_directory: Path,
    manifest_path: Path,
    author: ExportAuthor,
    expected_predecessor: PublishedIdentity | None,
    desired: RenderedExport,
) -> bytes | None:
    error_code = "predecessor_mismatch"
    try:
        current, current_bytes = _read_predecessor(
            export_root,
            author_directory,
            manifest_path,
            author,
        )
    except ExportError as error:
        raise ExportConflictError(error_code) from error
    if current is None or current_bytes is None:
        if expected_predecessor is None:
            return None
        raise ExportConflictError(error_code)
    manifest_stat = _safe_lstat_as(manifest_path, error_code)
    if manifest_stat is None or not stat.S_ISREG(manifest_stat.st_mode) or manifest_stat.st_nlink != 1:
        raise ExportConflictError(error_code)

    desired_bytes = _manifest_bytes(desired)
    if current_bytes == desired_bytes:
        _verify_published_files(author_directory, desired.files, error_code=error_code)
        return current_bytes
    desired_identity = PublishedIdentity(
        desired.source_fingerprint,
        desired.tree_sha256,
        desired.manifest_sha256,
    )
    if (
        expected_predecessor is None
        or expected_predecessor == desired_identity
        or current.source_fingerprint != expected_predecessor.source_fingerprint
        or current.tree_sha256 != expected_predecessor.tree_sha256
        or _sha256_bytes(current_bytes) != expected_predecessor.manifest_sha256
    ):
        raise ExportConflictError(error_code)
    _verify_published_files(author_directory, current.files, error_code=error_code)
    return current_bytes


def _write_new_bytes(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    finally:
        os.close(descriptor)


def _copy_stream(source: BinaryIO, destination: BinaryIO) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    while chunk := source.read(_CHUNK_BYTES):
        destination.write(chunk)
        hasher.update(chunk)
        size += len(chunk)
    return hasher.hexdigest(), size


def _copy_verified_asset(asset: object, destination: Path) -> ManagedFile:
    from .models import VerifiedAsset

    if not isinstance(asset, VerifiedAsset):  # pragma: no cover - private contract guard
        raise TypeError("expected VerifiedAsset")
    source_stat = _safe_lstat_as(asset.local_path, "asset_source_not_regular")
    if source_stat is None:
        raise ExportError("asset_source_missing")
    if not stat.S_ISREG(source_stat.st_mode):
        raise ExportError("asset_source_not_regular")
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        try:
            with (
                _safe_regular_reader(asset.local_path, error_code="asset_source_not_regular") as source,
                os.fdopen(descriptor, "wb", closefd=False) as output,
            ):
                checksum, size = _copy_stream(source, output)
                output.flush()
                os.fsync(output.fileno())
        except ExportConflictError as error:
            raise ExportError(error.code) from error
    except BaseException:
        with contextlib.suppress(OSError):
            destination.unlink()
        raise
    finally:
        os.close(descriptor)
    if size != asset.size_bytes:
        destination.unlink(missing_ok=True)
        raise ExportError("asset_source_size_mismatch")
    if checksum != asset.checksum_sha256:
        destination.unlink(missing_ok=True)
        raise ExportError("asset_source_checksum_mismatch")
    return ManagedFile("", checksum, size)


def _render_file(stage: Path, planned: PlannedFile) -> ManagedFile:
    parent = _ensure_child_directories(stage, planned.relative_path.parent)
    destination = parent / planned.relative_path.name
    if planned.payload is not None:
        _write_new_bytes(destination, planned.payload)
        checksum = _sha256_bytes(planned.payload)
        size = len(planned.payload)
    else:
        copied = _copy_verified_asset(planned.asset, destination)
        checksum = copied.sha256
        size = copied.size_bytes
    return ManagedFile(planned.relative_path.as_posix(), checksum, size)


def _tree_sha256(files: Sequence[ManagedFile]) -> str:
    rows = [{"path": item.relative_path, "sha256": item.sha256, "size_bytes": item.size_bytes} for item in files]
    return hashlib.sha256(_canonical_json_bytes(rows)).hexdigest()


def _copy_to_new_file(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str,
    expected_size: int,
    mismatch_code: str,
) -> None:
    _ensure_directory(destination.parent)
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        with (
            _safe_regular_reader(source, error_code=mismatch_code) as input_file,
            os.fdopen(descriptor, "wb", closefd=False) as output_file,
        ):
            checksum, size = _copy_stream(input_file, output_file)
            output_file.flush()
            os.fsync(output_file.fileno())
        if checksum != expected_sha256 or size != expected_size:
            raise ExportConflictError(mismatch_code)
    except BaseException:
        with contextlib.suppress(OSError):
            destination.unlink()
        raise
    finally:
        os.close(descriptor)


def _verify_exact_file(path: Path, expected: ManagedFile, *, error_code: str) -> None:
    checksum, size = _verify_regular_file(path, unsafe_code=error_code)
    path_stat = _safe_lstat_as(path, error_code)
    if checksum != expected.sha256 or size != expected.size_bytes or path_stat is None or path_stat.st_nlink != 1:
        raise ExportConflictError(error_code)


def _verify_complete_publication(
    author_directory: Path,
    manifest_path: Path,
    desired_manifest: ManagedFile,
    files: Sequence[ManagedFile],
    *,
    error_code: str,
    managed_file_error_code: str | None = None,
) -> None:
    """Revalidate the complete desired tree while publication evidence is retained."""

    _verify_exact_file(manifest_path, desired_manifest, error_code=error_code)
    _verify_published_files(
        author_directory,
        files,
        error_code=managed_file_error_code or error_code,
    )
    # Keep the manifest as the final fence: it binds the file list checked above.
    _verify_exact_file(manifest_path, desired_manifest, error_code=error_code)


def _mark_recovery_required(directory: Path) -> None:
    marker = directory / _TRANSACTION_CONFLICT_MARKER
    if _safe_lstat(marker) is None:
        _write_new_bytes(marker, b"media-sync publish recovery required\n")
        _fsync_directory(directory)


def _preserve_link_conflict(
    source: Path | None,
    destination: Path,
    transaction_directory: Path,
) -> None:
    """Move a raced destination into durable transaction storage before failing."""

    _mark_recovery_required(transaction_directory)
    conflict_directory = transaction_directory / "conflicts"
    _ensure_directory(conflict_directory)
    conflict = conflict_directory / f"{uuid4().hex}.current"
    try:
        _rename_no_replace(destination, conflict)
    except FileNotFoundError:
        return
    except (FileExistsError, OSError):
        raise ExportError("publish_rollback_failed") from None
    _fsync_directory(destination.parent)
    _fsync_directory(conflict_directory)

    if source is None:
        return
    source_stat = _safe_lstat_as(source, "publish_rollback_failed")
    conflict_stat = _safe_lstat_as(conflict, "publish_rollback_failed")
    if source_stat is None or conflict_stat is None:
        return
    if not _same_identity(_signature(source_stat), _signature(conflict_stat)):
        return
    current_source = _safe_lstat_as(source, "publish_rollback_failed")
    current_conflict = _safe_lstat_as(conflict, "publish_rollback_failed")
    if (
        current_source is None
        or current_conflict is None
        or not _same_identity(_signature(current_source), _signature(current_conflict))
    ):
        return
    try:
        source.unlink()
    except OSError:
        raise ExportError("publish_rollback_failed") from None
    _fsync_directory(source.parent)


def _link_no_clobber(
    source: Path,
    destination: Path,
    *,
    expected: ManagedFile,
    conflict_code: str,
    transaction_directory: Path,
    require_final_single_link: bool = True,
) -> bool:
    checksum, size = _verify_regular_file(source, unsafe_code=conflict_code)
    source_stat = _safe_lstat_as(source, conflict_code)
    if source_stat is None or checksum != expected.sha256 or size != expected.size_bytes:
        raise ExportConflictError(conflict_code)
    if require_final_single_link and source_stat.st_nlink != 1:
        raise ExportConflictError(conflict_code)
    try:
        os.link(source, destination, follow_symlinks=False)
    except FileExistsError:
        return False
    except OSError:
        if _safe_lstat(destination) is not None:
            return False
        raise ExportError("no_clobber_unsupported") from None
    linked_stat = _safe_lstat_as(destination, conflict_code)
    source_after_link = _safe_lstat_as(source, conflict_code)
    if (
        linked_stat is None
        or source_after_link is None
        or not stat.S_ISREG(linked_stat.st_mode)
        or not _same_identity(_signature(linked_stat), _signature(source_after_link))
    ):
        with contextlib.suppress(OSError):
            current = _safe_lstat(destination)
            if (
                current is not None
                and source_after_link is not None
                and _same_identity(_signature(current), _signature(source_after_link))
            ):
                destination.unlink()
        raise ExportConflictError(conflict_code)
    linked_checksum, linked_size = _verify_regular_file(destination, unsafe_code=conflict_code)
    if linked_checksum != expected.sha256 or linked_size != expected.size_bytes:
        _preserve_link_conflict(source, destination, transaction_directory)
        raise ExportError("publish_rollback_failed")
    try:
        source.unlink()
    except OSError as error:
        try:
            current = _safe_lstat_as(destination, conflict_code)
            remaining_source = _safe_lstat_as(source, conflict_code)
            if (
                current is not None
                and remaining_source is not None
                and _same_identity(_signature(current), _signature(remaining_source))
            ):
                destination.unlink()
        except ExportError:
            raise ExportError("publish_rollback_failed") from error
        raise ExportError("no_clobber_publish_failed") from error
    _fsync_directory(source.parent)
    _fsync_directory(destination.parent)
    try:
        final_checksum, final_size = _verify_regular_file(destination, unsafe_code=conflict_code)
        final_stat = _safe_lstat_as(destination, conflict_code)
        exact = (
            final_checksum == expected.sha256
            and final_size == expected.size_bytes
            and final_stat is not None
            and stat.S_ISREG(final_stat.st_mode)
            and (not require_final_single_link or final_stat.st_nlink == 1)
        )
    except ExportError as error:
        _preserve_link_conflict(None, destination, transaction_directory)
        raise ExportError("publish_rollback_failed") from error
    if not exact:
        _preserve_link_conflict(None, destination, transaction_directory)
        raise ExportError("publish_rollback_failed")
    return True


def _restore_capture_no_clobber(capture: Path, destination: Path, actual: ManagedFile) -> bool:
    checksum, size = _verify_regular_file(capture, unsafe_code="publish_rollback_failed")
    if checksum != actual.sha256 or size != actual.size_bytes:
        raise ExportError("publish_rollback_failed")
    return _restore_entry_no_clobber(capture, destination)


def _rename_no_replace(source: Path, destination: Path) -> None:
    if os.name == "nt":
        os.rename(source, destination)
        return
    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    result = -1
    if sys.platform.startswith("linux"):
        renameat2 = getattr(library, "renameat2", None)
        if renameat2 is None:
            raise ExportError("no_clobber_unsupported")
        result = renameat2(
            ctypes.c_int(-100),
            ctypes.c_char_p(source_bytes),
            ctypes.c_int(-100),
            ctypes.c_char_p(destination_bytes),
            ctypes.c_uint(1),
        )
    elif sys.platform == "darwin":
        renamex_np = getattr(library, "renamex_np", None)
        if renamex_np is None:
            raise ExportError("no_clobber_unsupported")
        result = renamex_np(
            ctypes.c_char_p(source_bytes),
            ctypes.c_char_p(destination_bytes),
            ctypes.c_uint(4),
        )
    else:
        raise ExportError("no_clobber_unsupported")
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error_number, os.strerror(error_number), destination)
    if error_number == errno.ENOENT:
        raise FileNotFoundError(error_number, os.strerror(error_number), source)
    raise OSError(error_number, os.strerror(error_number), source, destination)


def _restore_entry_no_clobber(capture: Path, destination: Path) -> bool:
    try:
        destination.lstat()
    except FileNotFoundError:
        pass
    else:
        return False
    try:
        _rename_no_replace(capture, destination)
    except FileExistsError:
        return False
    except FileNotFoundError:
        raise ExportError("publish_rollback_failed") from None
    except OSError:
        raise ExportError("publish_rollback_failed") from None
    _fsync_directory(capture.parent)
    _fsync_directory(destination.parent)
    return True


def _capture_existing(
    source: Path,
    capture: Path,
    *,
    expected: ManagedFile,
    mismatch_code: str,
) -> None:
    _ensure_directory(capture.parent)
    if _safe_lstat(capture) is not None:
        raise ExportError("publish_transaction_invalid")
    try:
        _rename_no_replace(source, capture)
    except FileExistsError:
        raise ExportError("publish_transaction_invalid") from None
    except FileNotFoundError:
        raise ExportConflictError(mismatch_code) from None
    except OSError:
        raise ExportError("publish_capture_failed") from None
    _fsync_directory(source.parent)
    _fsync_directory(capture.parent)
    try:
        _verify_exact_file(capture, expected, error_code=mismatch_code)
    except ExportError as error:
        try:
            restored = _restore_entry_no_clobber(capture, source)
        except ExportError:
            restored = False
        if not restored:
            raise ExportError("publish_rollback_failed") from error
        raise


def _managed_payload(item: ManagedFile | None) -> dict[str, object] | None:
    if item is None:
        return None
    return {"sha256": item.sha256, "size_bytes": item.size_bytes}


def _transaction_payload(transaction: _PublishTransaction, rendered: RenderedExport) -> dict[str, object]:
    return {
        "author": {"platform": rendered.author.platform, "remote_id": rendered.author.remote_id},
        "desired_manifest": _managed_payload(transaction.desired_manifest),
        "job_id": rendered.job_id,
        "layout_version": LAYOUT_VERSION,
        "manifest_candidate": transaction.manifest_candidate_path.relative_to(transaction.directory).as_posix(),
        "manifest_capture": transaction.manifest_capture_path.relative_to(transaction.directory).as_posix(),
        "manifest_verification": transaction.manifest_verification_path.relative_to(transaction.directory).as_posix(),
        "operations": [
            {
                "candidate": (
                    None
                    if operation.candidate_path is None
                    else operation.candidate_path.relative_to(transaction.directory).as_posix()
                ),
                "capture": operation.capture_path.relative_to(transaction.directory).as_posix(),
                "kind": operation.kind,
                "new": _managed_payload(operation.new_file),
                "old": _managed_payload(operation.old_file),
                "path": operation.relative_path,
                "verification": (
                    None
                    if operation.verification_path is None
                    else operation.verification_path.relative_to(transaction.directory).as_posix()
                ),
            }
            for operation in transaction.operations
        ],
        "predecessor_manifest": _managed_payload(transaction.predecessor_manifest),
        "schema_version": _TRANSACTION_SCHEMA_VERSION,
        "state": "prepared",
    }


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _cleanup_transaction(transaction: _PublishTransaction) -> None:
    transaction_root = transaction.directory.parent
    _remove_safe_tree(transaction.directory, transaction.author_directory)
    _fsync_directory(transaction_root)
    with contextlib.suppress(OSError):
        transaction_root.rmdir()
    _fsync_directory(transaction.author_directory)


def _mark_transaction_conflict(transaction: _PublishTransaction) -> None:
    _mark_recovery_required(transaction.directory)


def _prepare_transaction(
    rendered: RenderedExport,
    author_directory: Path,
    manifest_path: Path,
    old_manifest_bytes: bytes | None,
    old_files: Mapping[str, ManagedFile],
    replacements: Sequence[tuple[ManagedFile, Path, Path]],
    created: Sequence[tuple[ManagedFile, Path, Path]],
    stale: Sequence[tuple[ManagedFile, Path]],
) -> _PublishTransaction:
    transaction_root = author_directory / _TRANSACTION_ROOT_NAME
    _ensure_directory(transaction_root)
    transaction_directory = transaction_root / f"{rendered.job_id}-{uuid4().hex}"
    transaction_directory.mkdir()
    candidates = transaction_directory / "candidates"
    captures = transaction_directory / "captures"
    verifications = transaction_directory / "verifications"
    _ensure_directory(candidates)
    _ensure_directory(captures)
    _ensure_directory(verifications)
    operations: list[_TransactionOperation] = []
    desired_manifest_bytes = _manifest_bytes(rendered)
    predecessor_manifest = (
        None
        if old_manifest_bytes is None
        else ManagedFile(MANIFEST_NAME, _sha256_bytes(old_manifest_bytes), len(old_manifest_bytes))
    )
    desired_manifest = ManagedFile(
        MANIFEST_NAME,
        _sha256_bytes(desired_manifest_bytes),
        len(desired_manifest_bytes),
    )
    manifest_candidate = candidates / "manifest.new"
    manifest_capture = captures / "manifest.old"
    manifest_verification = verifications / "manifest.check"
    try:
        indexed_rows: list[tuple[str, ManagedFile, Path | None, Path]] = []
        indexed_rows.extend(("replace", item, staged, target) for item, staged, target in replacements)
        indexed_rows.extend(("create", item, staged, target) for item, staged, target in created)
        indexed_rows.extend(("delete", item, None, target) for item, target in stale)
        indexed_rows.sort(key=lambda row: (row[1].relative_path.casefold(), row[1].relative_path, row[0]))
        for index, (kind, item, staged, _target) in enumerate(indexed_rows):
            capture = captures / f"{index:04d}.old"
            candidate: Path | None = None
            verification = None if kind == "delete" else verifications / f"{index:04d}.check"
            old_file = item if kind in {"replace", "delete"} else None
            new_file = item if kind == "create" else None
            if kind == "replace":
                old_file = old_files[item.relative_path]
                new_file = item
            if staged is not None:
                candidate = candidates / f"{index:04d}.new"
                _copy_to_new_file(
                    staged,
                    candidate,
                    expected_sha256=item.sha256,
                    expected_size=item.size_bytes,
                    mismatch_code="staging_file_mismatch",
                )
            operations.append(
                _TransactionOperation(
                    kind=kind,
                    relative_path=item.relative_path,
                    old_file=old_file,
                    new_file=new_file,
                    capture_path=capture,
                    candidate_path=candidate,
                    verification_path=verification,
                )
            )
        _write_new_bytes(manifest_candidate, desired_manifest_bytes)
        transaction = _PublishTransaction(
            directory=transaction_directory,
            journal_path=transaction_directory / "transaction.json",
            author_directory=author_directory,
            manifest_path=manifest_path,
            predecessor_manifest=predecessor_manifest,
            desired_manifest=desired_manifest,
            manifest_capture_path=manifest_capture,
            manifest_candidate_path=manifest_candidate,
            manifest_verification_path=manifest_verification,
            operations=tuple(operations),
        )
        _write_new_bytes(transaction.journal_path, _canonical_json_bytes(_transaction_payload(transaction, rendered)))
        _fsync_directory(candidates)
        _fsync_directory(captures)
        _fsync_directory(verifications)
        _fsync_directory(transaction_directory)
        _fsync_directory(transaction_root)
        return transaction
    except BaseException:
        with contextlib.suppress(ExportError, OSError):
            _remove_safe_tree(transaction_directory, author_directory)
        with contextlib.suppress(OSError):
            transaction_root.rmdir()
        raise


def _parse_transaction_managed(value: object, relative_path: str) -> ManagedFile | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"sha256", "size_bytes"}:
        raise ExportError("publish_recovery_required")
    checksum = value["sha256"]
    size = value["size_bytes"]
    if (
        not isinstance(checksum, str)
        or _SHA256_PATTERN.fullmatch(checksum) is None
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
    ):
        raise ExportError("publish_recovery_required")
    return ManagedFile(relative_path, checksum, size)


def _transaction_child(directory: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ExportError("publish_recovery_required")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ExportError("publish_recovery_required")
    child = directory.joinpath(*relative.parts)
    try:
        child.absolute().relative_to(directory.absolute())
    except ValueError:
        raise ExportError("publish_recovery_required") from None
    return child


def _load_transaction(
    directory: Path,
    author_directory: Path,
    manifest_path: Path,
    author: ExportAuthor,
) -> _PublishTransaction:
    journal_path = directory / "transaction.json"
    try:
        payload = json.loads(
            _read_safe_regular(
                journal_path,
                error_code="publish_recovery_required",
                max_bytes=_MAX_MANIFEST_BYTES,
            ).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ExportError):
        raise ExportError("publish_recovery_required") from None
    if not isinstance(payload, dict) or set(payload) != {
        "author",
        "desired_manifest",
        "job_id",
        "layout_version",
        "manifest_candidate",
        "manifest_capture",
        "manifest_verification",
        "operations",
        "predecessor_manifest",
        "schema_version",
        "state",
    }:
        raise ExportError("publish_recovery_required")
    if (
        payload["schema_version"] != _TRANSACTION_SCHEMA_VERSION
        or payload["layout_version"] != LAYOUT_VERSION
        or payload["state"] != "prepared"
    ):
        raise ExportError("publish_recovery_required")
    author_payload = payload["author"]
    if not isinstance(author_payload, dict) or author_payload != {
        "platform": author.platform,
        "remote_id": author.remote_id,
    }:
        raise ExportError("publish_recovery_required")
    operations_payload = payload["operations"]
    if not isinstance(operations_payload, list):
        raise ExportError("publish_recovery_required")
    operations: list[_TransactionOperation] = []
    seen: set[str] = set()
    for item in operations_payload:
        if not isinstance(item, dict) or set(item) != {
            "candidate",
            "capture",
            "kind",
            "new",
            "old",
            "path",
            "verification",
        }:
            raise ExportError("publish_recovery_required")
        kind = item["kind"]
        relative_value = item["path"]
        if kind not in {"create", "delete", "replace"} or not isinstance(relative_value, str):
            raise ExportError("publish_recovery_required")
        relative = _validate_relative_path(relative_value).as_posix()
        if relative.casefold() in seen:
            raise ExportError("publish_recovery_required")
        seen.add(relative.casefold())
        old_file = _parse_transaction_managed(item["old"], relative)
        new_file = _parse_transaction_managed(item["new"], relative)
        if (
            (kind == "create" and (old_file is not None or new_file is None))
            or (kind == "delete" and (old_file is None or new_file is not None))
            or (kind == "replace" and (old_file is None or new_file is None))
        ):
            raise ExportError("publish_recovery_required")
        candidate = None if item["candidate"] is None else _transaction_child(directory, item["candidate"])
        verification = None if item["verification"] is None else _transaction_child(directory, item["verification"])
        if (kind == "delete") != (candidate is None):
            raise ExportError("publish_recovery_required")
        if (kind == "delete") != (verification is None):
            raise ExportError("publish_recovery_required")
        operations.append(
            _TransactionOperation(
                kind=kind,
                relative_path=relative,
                old_file=old_file,
                new_file=new_file,
                capture_path=_transaction_child(directory, item["capture"]),
                candidate_path=candidate,
                verification_path=verification,
            )
        )
    predecessor = _parse_transaction_managed(payload["predecessor_manifest"], MANIFEST_NAME)
    desired = _parse_transaction_managed(payload["desired_manifest"], MANIFEST_NAME)
    if desired is None:
        raise ExportError("publish_recovery_required")
    return _PublishTransaction(
        directory=directory,
        journal_path=journal_path,
        author_directory=author_directory,
        manifest_path=manifest_path,
        predecessor_manifest=predecessor,
        desired_manifest=desired,
        manifest_capture_path=_transaction_child(directory, payload["manifest_capture"]),
        manifest_candidate_path=_transaction_child(directory, payload["manifest_candidate"]),
        manifest_verification_path=_transaction_child(directory, payload["manifest_verification"]),
        operations=tuple(operations),
    )


def _file_matches(path: Path, expected: ManagedFile | None) -> bool:
    try:
        path_stat = _safe_lstat(path)
    except ExportError:
        raise ExportError("publish_recovery_required") from None
    if expected is None:
        return path_stat is None
    if path_stat is None or not stat.S_ISREG(path_stat.st_mode) or path_stat.st_nlink != 1:
        return False
    checksum, size = _verify_regular_file(path, unsafe_code="publish_recovery_required")
    return checksum == expected.sha256 and size == expected.size_bytes


def _finish_interrupted_link(source: Path, destination: Path, expected: ManagedFile) -> bool:
    source_stat = _safe_lstat(source)
    destination_stat = _safe_lstat(destination)
    if source_stat is None or destination_stat is None:
        return False
    if (
        not stat.S_ISREG(source_stat.st_mode)
        or not stat.S_ISREG(destination_stat.st_mode)
        or not _same_identity(_signature(source_stat), _signature(destination_stat))
    ):
        return False
    checksum, size = _verify_regular_file(destination, unsafe_code="publish_recovery_required")
    if checksum != expected.sha256 or size != expected.size_bytes:
        return False
    source.unlink()
    _fsync_directory(source.parent)
    _fsync_directory(destination.parent)
    _verify_exact_file(destination, expected, error_code="publish_recovery_required")
    return True


def _recover_remove_new(transaction: _PublishTransaction, operation: _TransactionOperation) -> None:
    if operation.new_file is None:
        raise ExportError("publish_recovery_required")
    target = transaction.author_directory.joinpath(*PurePosixPath(operation.relative_path).parts)
    recovery_capture = transaction.directory / "recovery" / f"{uuid4().hex}.new"
    _capture_existing(
        target,
        recovery_capture,
        expected=operation.new_file,
        mismatch_code="publish_recovery_required",
    )


def _recover_rollback_operation(transaction: _PublishTransaction, operation: _TransactionOperation) -> None:
    target = transaction.author_directory.joinpath(*PurePosixPath(operation.relative_path).parts)
    if operation.verification_path is not None:
        if operation.new_file is None:
            raise ExportError("publish_recovery_required")
        _finish_interrupted_link(operation.verification_path, target, operation.new_file)
        if _safe_lstat(operation.verification_path) is not None:
            if _safe_lstat(target) is not None:
                raise ExportError("publish_recovery_required")
            try:
                checksum, size = _verify_regular_file(
                    operation.verification_path,
                    unsafe_code="publish_recovery_required",
                )
                actual = ManagedFile(operation.relative_path, checksum, size)
                matches = (
                    actual.sha256 == operation.new_file.sha256 and actual.size_bytes == operation.new_file.size_bytes
                )
            except ExportError:
                matches = False
            if not _restore_entry_no_clobber(operation.verification_path, target):
                raise ExportError("publish_recovery_required")
            if not matches:
                raise ExportError("publish_recovery_required")
    if operation.new_file is not None and operation.candidate_path is not None:
        _finish_interrupted_link(operation.candidate_path, target, operation.new_file)
    if operation.old_file is not None:
        _finish_interrupted_link(operation.capture_path, target, operation.old_file)
    capture_exists = _safe_lstat(operation.capture_path) is not None
    target_exists = _safe_lstat(target) is not None
    if operation.kind == "create":
        if not target_exists:
            return
        if operation.new_file is None or not _file_matches(target, operation.new_file):
            raise ExportError("publish_recovery_required")
        _recover_remove_new(transaction, operation)
        return
    if operation.old_file is None:
        raise ExportError("publish_recovery_required")
    if not capture_exists:
        if not _file_matches(target, operation.old_file):
            raise ExportError("publish_recovery_required")
        return
    if not _file_matches(operation.capture_path, operation.old_file):
        raise ExportError("publish_recovery_required")
    if target_exists:
        if operation.kind == "replace" and operation.new_file is not None and _file_matches(target, operation.new_file):
            _recover_remove_new(transaction, operation)
        elif _file_matches(target, operation.old_file):
            return
        else:
            raise ExportError("publish_recovery_required")
    if _safe_lstat(target) is None and not _restore_capture_no_clobber(
        operation.capture_path,
        target,
        operation.old_file,
    ):
        raise ExportError("publish_recovery_required")


def _raw_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        raise ExportError("publish_recovery_required") from None
    return True


def _recover_manifest_verification(transaction: _PublishTransaction) -> None:
    verification = transaction.manifest_verification_path
    if not _raw_entry_exists(verification):
        return
    if _raw_entry_exists(transaction.manifest_path):
        raise ExportError("publish_recovery_required")
    try:
        matches = _file_matches(verification, transaction.desired_manifest)
    except ExportError:
        matches = False
    if not _restore_entry_no_clobber(verification, transaction.manifest_path):
        raise ExportError("publish_recovery_required")
    if not matches:
        raise ExportError("publish_recovery_required")
    _verify_exact_file(
        transaction.manifest_path,
        transaction.desired_manifest,
        error_code="publish_recovery_required",
    )


def _recover_transaction(transaction: _PublishTransaction, author: ExportAuthor) -> None:
    _recover_manifest_verification(transaction)
    _finish_interrupted_link(
        transaction.manifest_candidate_path,
        transaction.manifest_path,
        transaction.desired_manifest,
    )
    if transaction.predecessor_manifest is not None:
        _finish_interrupted_link(
            transaction.manifest_capture_path,
            transaction.manifest_path,
            transaction.predecessor_manifest,
        )
    if _file_matches(transaction.manifest_path, transaction.desired_manifest):
        try:
            manifest_bytes = _read_safe_regular(
                transaction.manifest_path,
                error_code="publish_recovery_required",
                max_bytes=_MAX_MANIFEST_BYTES,
            )
            desired = _parse_manifest(manifest_bytes, author)
            _verify_complete_publication(
                transaction.author_directory,
                transaction.manifest_path,
                transaction.desired_manifest,
                desired.files,
                error_code="publish_recovery_required",
            )
        except (ExportError, OSError) as error:
            with contextlib.suppress(ExportError, OSError):
                _mark_transaction_conflict(transaction)
            if isinstance(error, ExportError) and error.code == "publish_recovery_required":
                raise
            raise ExportError("publish_recovery_required") from error
        _cleanup_transaction(transaction)
        return
    predecessor = transaction.predecessor_manifest
    manifest_capture_exists = _safe_lstat(transaction.manifest_capture_path) is not None
    if not _file_matches(transaction.manifest_path, predecessor) and not (
        predecessor is not None
        and manifest_capture_exists
        and _safe_lstat(transaction.manifest_path) is None
        and _file_matches(transaction.manifest_capture_path, predecessor)
    ):
        raise ExportError("publish_recovery_required")
    for operation in reversed(transaction.operations):
        _recover_rollback_operation(transaction, operation)
    if (
        predecessor is not None
        and manifest_capture_exists
        and _safe_lstat(transaction.manifest_path) is None
        and not _restore_capture_no_clobber(
            transaction.manifest_capture_path,
            transaction.manifest_path,
            predecessor,
        )
    ):
        raise ExportError("publish_recovery_required")
    _cleanup_transaction(transaction)


def _recover_pending_transactions(author_directory: Path, manifest_path: Path, author: ExportAuthor) -> None:
    transaction_root = author_directory / _TRANSACTION_ROOT_NAME
    root_stat = _safe_lstat(transaction_root)
    if root_stat is None:
        return
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ExportError("publish_recovery_required")
    entries = sorted(transaction_root.iterdir(), key=lambda item: item.name)
    for directory in entries:
        directory_stat = _safe_lstat(directory)
        if directory_stat is None:
            continue
        if not stat.S_ISDIR(directory_stat.st_mode):
            raise ExportError("publish_recovery_required")
        if _safe_lstat(directory / _TRANSACTION_CONFLICT_MARKER) is not None:
            raise ExportError("publish_recovery_required")
        transaction = _load_transaction(directory, author_directory, manifest_path, author)
        _recover_transaction(transaction, author)
    with contextlib.suppress(OSError):
        transaction_root.rmdir()


def _rollback_remove_installed(
    target: Path,
    expected: ManagedFile,
    rollback_capture: Path,
) -> bool:
    try:
        _capture_existing(
            target,
            rollback_capture,
            expected=expected,
            mismatch_code="publish_rollback_failed",
        )
    except ExportError:
        return False
    return True


def _rollback_operation(
    operation: _TransactionOperation,
    runtime: _TransactionRuntime,
    transaction: _PublishTransaction,
) -> bool:
    key = operation.relative_path
    target = transaction.author_directory.joinpath(*PurePosixPath(key).parts)
    rollback_capture = transaction.directory / "rollback" / f"{uuid4().hex}.current"
    if operation.kind == "create":
        if key not in runtime.installed_operations or operation.new_file is None:
            return True
        return _rollback_remove_installed(target, operation.new_file, rollback_capture)
    if key not in runtime.captured_operations or operation.old_file is None:
        return True
    if key in runtime.installed_operations:
        if operation.new_file is None or not _rollback_remove_installed(target, operation.new_file, rollback_capture):
            return False
    elif _safe_lstat(target) is not None:
        return False
    return _restore_capture_no_clobber(operation.capture_path, target, operation.old_file)


def _rollback_manifest(transaction: _PublishTransaction, runtime: _TransactionRuntime) -> bool:
    rollback_capture = transaction.directory / "rollback" / f"manifest-{uuid4().hex}.current"
    if runtime.manifest_installed:
        if not _rollback_remove_installed(
            transaction.manifest_path,
            transaction.desired_manifest,
            rollback_capture,
        ):
            return False
    elif runtime.manifest_captured and _safe_lstat(transaction.manifest_path) is not None:
        return False
    if runtime.manifest_captured:
        predecessor = transaction.predecessor_manifest
        if predecessor is None:
            return False
        return _restore_capture_no_clobber(
            transaction.manifest_capture_path,
            transaction.manifest_path,
            predecessor,
        )
    return True


def _rollback_transaction(transaction: _PublishTransaction, runtime: _TransactionRuntime) -> bool:
    succeeded = _rollback_manifest(transaction, runtime)
    for operation in reversed(transaction.operations):
        try:
            if not _rollback_operation(operation, runtime, transaction):
                succeeded = False
        except ExportError:
            succeeded = False
    return succeeded


def _existing_case_variant(root: Path, relative: PurePosixPath) -> Path | None:
    current = root
    for index, part in enumerate(relative.parts):
        current_stat = _safe_lstat(current)
        if current_stat is None:
            return None
        if not stat.S_ISDIR(current_stat.st_mode):
            raise ExportConflictError("unsafe_existing_path")
        matches = [
            child
            for child in current.iterdir()
            if unicodedata.normalize("NFC", child.name).casefold() == unicodedata.normalize("NFC", part).casefold()
        ]
        if len(matches) > 1:
            raise ExportConflictError("casefold_path_conflict")
        if not matches:
            return None
        match = matches[0]
        if match.name != part:
            raise ExportConflictError("casefold_path_conflict")
        current = match
        if index < len(relative.parts) - 1:
            path_stat = _safe_lstat(current)
            if path_stat is None or not stat.S_ISDIR(path_stat.st_mode):
                raise ExportConflictError("unsafe_existing_path")
    return current


def _verify_regular_file(path: Path, *, unsafe_code: str = "unsafe_existing_path") -> tuple[str, int]:
    return _sha256_file(path, error_code=unsafe_code)


def _safe_remove_staging(path: Path, staging_root: Path) -> None:
    try:
        path.relative_to(staging_root)
    except ValueError:
        raise ExportError("unsafe_staging_path") from None
    path_stat = _safe_lstat(path)
    if path_stat is None:
        return
    if not stat.S_ISDIR(path_stat.st_mode):
        raise ExportError("unsafe_staging_path")
    _remove_safe_tree(path, staging_root)


def _remove_safe_tree(path: Path, confinement: Path) -> None:
    try:
        path.absolute().relative_to(confinement.absolute())
    except ValueError:
        raise ExportError("unsafe_staging_path") from None
    path_stat = _safe_lstat(path)
    if path_stat is None:
        return
    if not stat.S_ISDIR(path_stat.st_mode):
        raise ExportError("unsafe_staging_path")
    try:
        entries = tuple(os.scandir(path))
    except OSError:
        raise ExportError("unsafe_staging_path") from None
    for entry in entries:
        child = Path(entry.path)
        try:
            child.absolute().relative_to(confinement.absolute())
        except ValueError:
            raise ExportError("unsafe_staging_path") from None
        child_stat = _safe_lstat(child)
        if child_stat is None:
            continue
        if stat.S_ISDIR(child_stat.st_mode):
            _remove_safe_tree(child, confinement)
        elif stat.S_ISREG(child_stat.st_mode):
            current = _safe_lstat(child)
            if current is None:
                continue
            if not _same_identity(_signature(child_stat), _signature(current)):
                raise ExportError("unsafe_staging_path")
            child.unlink()
        else:
            raise ExportError("unsafe_staging_path")
    final_stat = _safe_lstat(path)
    if final_stat is None:
        return
    if not _same_identity(_signature(path_stat), _signature(final_stat)):
        raise ExportError("unsafe_staging_path")
    path.rmdir()


def _prune_empty_parents(path: Path, author_directory: Path) -> None:
    current = path
    while current != author_directory:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _local_lock(path: Path) -> threading.Lock:
    key = os.path.normcase(str(path.absolute()))
    with _LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(key, threading.Lock())


def _open_lock_file(path: Path) -> BinaryIO:
    existing_stat = _safe_lstat(path)
    if existing_stat is not None and (not stat.S_ISREG(existing_stat.st_mode) or existing_stat.st_nlink != 1):
        raise ExportConflictError("unsafe_existing_path")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError:
        raise ExportConflictError("unsafe_existing_path") from None
    handle = os.fdopen(descriptor, "r+b")
    try:
        opened_stat = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened_stat.st_mode) or _is_reparse(opened_stat) or opened_stat.st_nlink != 1:
            raise ExportConflictError("unsafe_existing_path")
        current_stat = _safe_lstat(path)
        if current_stat is None or current_stat.st_nlink != 1:
            raise ExportConflictError("unsafe_existing_path")
        if not _same_identity(_signature(opened_stat), _signature(current_stat)):
            raise ExportConflictError("unsafe_existing_path")
        if opened_stat.st_size == 0:
            handle.seek(0)
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        final_stat = _safe_lstat(path)
        if final_stat is None or final_stat.st_nlink != 1:
            raise ExportConflictError("unsafe_existing_path")
        if not _same_identity(_signature(os.fstat(handle.fileno())), _signature(final_stat)):
            raise ExportConflictError("unsafe_existing_path")
        return handle
    except BaseException:
        handle.close()
        raise


def _open_existing_lock_file(path: Path, *, parent: _BoundDirectory) -> BinaryIO:
    """Open a publication lock without creating or changing any bytes."""

    _verify_bound_directory(parent, error_code=_PUBLISHED_INSPECTION_DRIFTED)
    existing_stat = _safe_bound_lstat(parent, path.name, error_code=_PUBLISHED_INSPECTION_DRIFTED)
    if (
        existing_stat is None
        or not stat.S_ISREG(existing_stat.st_mode)
        or existing_stat.st_nlink != 1
        or existing_stat.st_size < 1
    ):
        raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
    declared = _signature(existing_stat)
    flags = os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = (
            os.open(path, flags) if parent.descriptor is None else os.open(path.name, flags, dir_fd=parent.descriptor)
        )
    except OSError:
        raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED) from None
    handle = os.fdopen(descriptor, "r+b")
    try:
        opened_stat = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or _is_reparse(opened_stat)
            or opened_stat.st_nlink != 1
            or opened_stat.st_size < 1
        ):
            raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
        opened = _signature(opened_stat)
        current_stat = _safe_bound_lstat(parent, path.name, error_code=_PUBLISHED_INSPECTION_DRIFTED)
        if current_stat is None or current_stat.st_nlink != 1:
            raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
        if not _same_identity(declared, opened) or not _same_identity(opened, _signature(current_stat)):
            raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
        _verify_bound_directory(parent, error_code=_PUBLISHED_INSPECTION_DRIFTED)
        return handle
    except BaseException:
        handle.close()
        raise


def _try_os_lock(handle: BinaryIO) -> bool:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
    except BlockingIOError:
        return False
    return True


def _unlock_os(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


@contextlib.contextmanager
def _author_lock(path: Path, timeout_seconds: float) -> Iterator[None]:
    local = _local_lock(path)
    if not local.acquire(timeout=timeout_seconds):
        raise ExportConflictError("author_lock_timeout")
    handle: BinaryIO | None = None
    locked = False
    try:
        _ensure_directory(path.parent)
        path_stat = _safe_lstat(path)
        if path_stat is not None and not stat.S_ISREG(path_stat.st_mode):
            raise ExportConflictError("unsafe_existing_path")
        handle = _open_lock_file(path)
        deadline = time.monotonic() + timeout_seconds
        while not _try_os_lock(handle):
            if time.monotonic() >= deadline:
                raise ExportConflictError("author_lock_timeout")
            time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
        locked = True
        locked_path_stat = _safe_lstat(path)
        if locked_path_stat is None or locked_path_stat.st_nlink != 1:
            raise ExportConflictError("unsafe_existing_path")
        if not _same_identity(_signature(os.fstat(handle.fileno())), _signature(locked_path_stat)):
            raise ExportConflictError("unsafe_existing_path")
        yield
    finally:
        if handle is not None:
            if locked:
                _unlock_os(handle)
            handle.close()
        local.release()


@contextlib.contextmanager
def _existing_author_lock(
    path: Path,
    *,
    parent: _BoundDirectory,
    timeout_seconds: float,
    deadline: float,
    monotonic: Callable[[], float],
) -> Iterator[None]:
    """Acquire an already-published author lock without filesystem mutation."""

    local = _local_lock(path)
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise ExportConflictError(_PUBLISHED_INSPECTION_DEADLINE)
    wait_seconds = min(timeout_seconds, remaining)
    if not local.acquire(timeout=wait_seconds):
        code = _PUBLISHED_INSPECTION_DEADLINE if monotonic() >= deadline else _PUBLISHED_INSPECTION_BUSY
        raise ExportConflictError(code)
    handle: BinaryIO | None = None
    locked = False
    try:
        _verify_bound_directory(parent, error_code=_PUBLISHED_INSPECTION_DRIFTED)
        handle = _open_existing_lock_file(path, parent=parent)
        lock_deadline = min(deadline, monotonic() + timeout_seconds)
        while not _try_os_lock(handle):
            now = monotonic()
            if now >= lock_deadline:
                code = _PUBLISHED_INSPECTION_DEADLINE if now >= deadline else _PUBLISHED_INSPECTION_BUSY
                raise ExportConflictError(code)
            time.sleep(min(0.01, max(0.0, lock_deadline - now)))
        locked = True
        locked_path_stat = _safe_bound_lstat(parent, path.name, error_code=_PUBLISHED_INSPECTION_DRIFTED)
        if locked_path_stat is None or locked_path_stat.st_nlink != 1:
            raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
        if not _same_identity(_signature(os.fstat(handle.fileno())), _signature(locked_path_stat)):
            raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
        _verify_bound_directory(parent, error_code=_PUBLISHED_INSPECTION_DRIFTED)
        yield
        final_path_stat = _safe_bound_lstat(parent, path.name, error_code=_PUBLISHED_INSPECTION_DRIFTED)
        if final_path_stat is None or final_path_stat.st_nlink != 1:
            raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
        if not _same_identity(_signature(os.fstat(handle.fileno())), _signature(final_path_stat)):
            raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
        _verify_bound_directory(parent, error_code=_PUBLISHED_INSPECTION_DRIFTED)
    finally:
        if handle is not None:
            if locked:
                _unlock_os(handle)
            handle.close()
        local.release()


def _inspect_managed_file(
    directory: _BoundDirectory,
    name: str,
    expected: ManagedFile,
    *,
    byte_budget: int,
    deadline: float,
    monotonic: Callable[[], float],
    opened: Callable[[], None],
) -> tuple[bool, int]:
    """Hash one file on its opened descriptor, returning partial budget use safely."""

    if monotonic() >= deadline:
        return False, 0
    hasher = hashlib.sha256()
    bytes_read = 0
    with _safe_bound_regular_reader(
        directory,
        name,
        error_code=_PUBLISHED_INSPECTION_DRIFTED,
        single_link=True,
    ) as source:
        opened_stat = os.fstat(source.fileno())
        if opened_stat.st_nlink != 1 or opened_stat.st_size != expected.size_bytes:
            raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
        opened()
        _verify_bound_directory(directory, error_code=_PUBLISHED_INSPECTION_DRIFTED)
        while bytes_read < expected.size_bytes:
            if monotonic() >= deadline or bytes_read >= byte_budget:
                return False, bytes_read
            requested = min(_CHUNK_BYTES, expected.size_bytes - bytes_read, byte_budget - bytes_read)
            if requested <= 0:
                return False, bytes_read
            chunk = source.read(requested)
            if not chunk:
                raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
            hasher.update(chunk)
            bytes_read += len(chunk)
            _verify_bound_directory(directory, error_code=_PUBLISHED_INSPECTION_DRIFTED)
        if hasher.hexdigest() != expected.sha256:
            raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
    return True, bytes_read


class EmbyExporter:
    """Render immutable inputs, then atomically publish only exporter-owned files."""

    def __init__(
        self,
        export_root: Path,
        *,
        staging_root: Path | None = None,
        lock_timeout_seconds: float = 30.0,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        if lock_timeout_seconds <= 0:
            raise ExportError("invalid_lock_timeout")
        self._export_root = Path(export_root).expanduser().resolve(strict=False)
        self._staging_root = (
            Path(staging_root).expanduser().absolute()
            if staging_root is not None
            else self._export_root.parent / f".{self._export_root.name}.media-sync-work"
        )
        canonical_root = os.path.normcase(str(self._export_root.resolve(strict=False)))
        self._coordination_scope = hashlib.sha256(
            _canonical_json_bytes(
                {
                    "export_root": canonical_root,
                    "lock_domain": ".media-sync-locks-v1",
                    "schema_version": 1,
                }
            )
        ).hexdigest()
        self._lock_timeout_seconds = lock_timeout_seconds
        self._fault_injector = fault_injector

    @property
    def export_root(self) -> Path:
        return self._export_root

    @property
    def staging_root(self) -> Path:
        return self._staging_root

    @property
    def coordination_scope(self) -> str:
        """Return a non-disclosing identity for the shared publication/lock domain."""

        return self._coordination_scope

    def _fault(self, event: str, relative_path: str | None = None) -> None:
        if self._fault_injector is not None:
            self._fault_injector(event, relative_path)

    def _author_lock_path(self, author_segment: str) -> Path:
        return self._export_root / _LOCK_ROOT_NAME / f"{author_segment}.lock"

    def validate_published(
        self,
        author: ExportAuthor,
        expected_source_fingerprint: str,
        expected_tree_sha256: str,
        expected_manifest_sha256: str,
    ) -> int:
        """Validate one expected publication identity without repairing it."""

        _, managed_file_count = self._validate_published_once(
            author,
            expected_source_fingerprint,
            expected_tree_sha256=expected_tree_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
        )
        return managed_file_count

    def inspect_published(
        self,
        author: ExportAuthor,
        expected_identity: PublishedIdentity,
        *,
        start_index: int,
        limit: int,
        max_bytes: int,
        deadline: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> PublishedTreeInspection:
        """Verify one bounded manifest page under an existing-only author lock."""

        if (
            not isinstance(expected_identity, PublishedIdentity)
            or isinstance(start_index, bool)
            or not isinstance(start_index, int)
            or start_index < 0
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= _MAX_INSPECTION_FILES
            or isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or max_bytes < 0
            or isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
            or not math.isfinite(deadline)
            or not callable(monotonic)
        ):
            raise ExportError("invalid_published_inspection")

        author_segment = author_relative_directory(author).as_posix()
        lock_path = self._author_lock_path(author_segment)
        try:
            with contextlib.ExitStack() as binding_stack:
                root = binding_stack.enter_context(
                    _bind_existing_directory(self._export_root, error_code=_PUBLISHED_INSPECTION_DRIFTED)
                )
                lock_parent_parts = lock_path.parent.relative_to(self._export_root).parts
                lock_parent = _bind_directory_parts(
                    binding_stack,
                    root,
                    lock_parent_parts,
                    error_code=_PUBLISHED_INSPECTION_DRIFTED,
                )
                with _existing_author_lock(
                    lock_path,
                    parent=lock_parent,
                    timeout_seconds=self._lock_timeout_seconds,
                    deadline=float(deadline),
                    monotonic=monotonic,
                ):
                    author_directory_bound = _bind_directory_parts(
                        binding_stack,
                        root,
                        PurePosixPath(author_segment).parts,
                        error_code=_PUBLISHED_INSPECTION_DRIFTED,
                    )
                    if (
                        _exact_bound_child_name(
                            author_directory_bound,
                            MANIFEST_NAME,
                            error_code=_PUBLISHED_INSPECTION_DRIFTED,
                        )
                        is None
                    ):
                        raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
                    manifest_stat = _safe_bound_lstat(
                        author_directory_bound,
                        MANIFEST_NAME,
                        error_code=_PUBLISHED_INSPECTION_DRIFTED,
                    )
                    if (
                        manifest_stat is None
                        or not stat.S_ISREG(manifest_stat.st_mode)
                        or manifest_stat.st_nlink != 1
                        or manifest_stat.st_size > _MAX_MANIFEST_BYTES
                    ):
                        raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)

                    inspected: list[ManagedFileInspection] = []
                    bytes_read = 0
                    budget_exhausted = False
                    with _safe_bound_regular_reader(
                        author_directory_bound,
                        MANIFEST_NAME,
                        error_code=_PUBLISHED_INSPECTION_DRIFTED,
                        single_link=True,
                    ) as manifest_file:
                        self._fault("inspect_manifest_opened")
                        _verify_bound_directory(
                            author_directory_bound,
                            error_code=_PUBLISHED_INSPECTION_DRIFTED,
                        )
                        raw_manifest = bytearray()
                        while True:
                            if monotonic() >= deadline:
                                raise ExportConflictError(_PUBLISHED_INSPECTION_DEADLINE)
                            chunk = manifest_file.read(min(_CHUNK_BYTES, _MAX_MANIFEST_BYTES + 1 - len(raw_manifest)))
                            _verify_bound_directory(
                                author_directory_bound,
                                error_code=_PUBLISHED_INSPECTION_DRIFTED,
                            )
                            if not chunk:
                                break
                            raw_manifest.extend(chunk)
                            if len(raw_manifest) > _MAX_MANIFEST_BYTES:
                                raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
                        manifest_bytes = bytes(raw_manifest)
                        if _sha256_bytes(manifest_bytes) != expected_identity.manifest_sha256:
                            raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
                        manifest = _parse_manifest(manifest_bytes, author)
                        if (
                            manifest.source_fingerprint != expected_identity.source_fingerprint
                            or manifest.tree_sha256 != expected_identity.tree_sha256
                            or start_index > len(manifest.files)
                        ):
                            raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)

                        stop_index = min(len(manifest.files), start_index + limit)
                        next_index = start_index
                        for item in manifest.files[start_index:stop_index]:
                            relative = _validate_relative_path(item.relative_path)
                            with contextlib.ExitStack() as file_stack:
                                file_parent = _bind_directory_parts(
                                    file_stack,
                                    author_directory_bound,
                                    relative.parts[:-1],
                                    error_code=_PUBLISHED_INSPECTION_DRIFTED,
                                )
                                file_name = _exact_bound_child_name(
                                    file_parent,
                                    relative.name,
                                    error_code=_PUBLISHED_INSPECTION_DRIFTED,
                                )
                                if file_name is None:
                                    raise ExportConflictError(_PUBLISHED_INSPECTION_DRIFTED)
                                verified, consumed = _inspect_managed_file(
                                    file_parent,
                                    file_name,
                                    item,
                                    byte_budget=max_bytes - bytes_read,
                                    deadline=float(deadline),
                                    monotonic=monotonic,
                                    opened=partial(self._fault, "inspect_file_opened", item.relative_path),
                                )
                            bytes_read += consumed
                            if not verified:
                                budget_exhausted = True
                                break
                            inspected.append(ManagedFileInspection(item.relative_path, item.sha256, item.size_bytes))
                            next_index += 1

                    managed_file_count = len(manifest.files)
                    return PublishedTreeInspection(
                        layout_version=LAYOUT_VERSION,
                        source_fingerprint=manifest.source_fingerprint,
                        tree_sha256=manifest.tree_sha256,
                        manifest_sha256=expected_identity.manifest_sha256,
                        managed_file_count=managed_file_count,
                        start_index=start_index,
                        next_index=next_index,
                        files=tuple(inspected),
                        bytes_read=bytes_read,
                        complete=(start_index == 0 and next_index == managed_file_count and not budget_exhausted),
                        budget_exhausted=budget_exhausted,
                    )
        except (ExportError, OSError) as error:
            if isinstance(error, ExportError) and error.code in {
                _PUBLISHED_INSPECTION_DRIFTED,
                _PUBLISHED_INSPECTION_DEADLINE,
                _PUBLISHED_INSPECTION_BUSY,
            }:
                raise ExportError(error.code) from None
            raise ExportError(_PUBLISHED_INSPECTION_DRIFTED) from None

    def _validate_published_once(
        self,
        author: ExportAuthor,
        expected_source_fingerprint: str,
        *,
        expected_tree_sha256: str,
        expected_manifest_sha256: str,
    ) -> tuple[str, int]:
        """Inspect under exactly one author-lock acquisition."""

        author_segment = author_relative_directory(author).as_posix()
        author_directory = self._export_root / author_segment
        manifest_path = author_directory / MANIFEST_NAME
        lock_path = self._author_lock_path(author_segment)
        try:
            with _author_lock(lock_path, self._lock_timeout_seconds):
                if (
                    not isinstance(expected_source_fingerprint, str)
                    or _SHA256_PATTERN.fullmatch(expected_source_fingerprint) is None
                    or not isinstance(expected_tree_sha256, str)
                    or _SHA256_PATTERN.fullmatch(expected_tree_sha256) is None
                    or not isinstance(expected_manifest_sha256, str)
                    or _SHA256_PATTERN.fullmatch(expected_manifest_sha256) is None
                ):
                    raise ExportError(_PUBLISHED_EXPORT_INVALID)
                root_stat = _safe_lstat(self._export_root)
                author_stat = _safe_lstat(author_directory)
                if (
                    root_stat is None
                    or not stat.S_ISDIR(root_stat.st_mode)
                    or author_stat is None
                    or not stat.S_ISDIR(author_stat.st_mode)
                ):
                    raise ExportError(_PUBLISHED_EXPORT_INVALID)
                manifest_stat = _safe_lstat(manifest_path)
                if manifest_stat is None or not stat.S_ISREG(manifest_stat.st_mode) or manifest_stat.st_nlink != 1:
                    raise ExportError(_PUBLISHED_EXPORT_INVALID)
                manifest, manifest_bytes = _load_manifest(manifest_path, author)
                if (
                    manifest is None
                    or manifest_bytes is None
                    or manifest.source_fingerprint != expected_source_fingerprint
                    or manifest.tree_sha256 != expected_tree_sha256
                    or _sha256_bytes(manifest_bytes) != expected_manifest_sha256
                ):
                    raise ExportError(_PUBLISHED_EXPORT_INVALID)
                for item in manifest.files:
                    relative = _validate_relative_path(item.relative_path)
                    existing = _existing_case_variant(author_directory, relative)
                    if existing is None:
                        raise ExportError(_PUBLISHED_EXPORT_INVALID)
                    _verify_exact_file(existing, item, error_code=_PUBLISHED_EXPORT_INVALID)
                final_manifest_stat = _safe_lstat(manifest_path)
                if (
                    final_manifest_stat is None
                    or final_manifest_stat.st_nlink != 1
                    or _read_manifest_payload(manifest_path) != manifest_bytes
                ):
                    raise ExportError(_PUBLISHED_EXPORT_INVALID)
                return manifest.tree_sha256, len(manifest.files)
        except (ExportError, OSError) as error:
            if isinstance(error, ExportError) and error.code == _PUBLISHED_EXPORT_INVALID:
                raise
            raise ExportError(_PUBLISHED_EXPORT_INVALID) from error

    def render(
        self,
        author: ExportAuthor,
        contents: Sequence[ExportContent],
        *,
        job_id: str,
        expected_predecessor: PublishedIdentity | None,
    ) -> RenderedExport:
        """Render a byte-complete tree fenced by one trusted predecessor."""

        if _JOB_ID_PATTERN.fullmatch(job_id) is None:
            raise ExportError("invalid_job_id")
        if expected_predecessor is not None and not isinstance(expected_predecessor, PublishedIdentity):
            raise ExportError("invalid_published_identity")
        plan: LayoutPlan = build_layout_plan(author, tuple(contents))
        _ensure_directory(self._staging_root)
        author_directory = self._export_root / plan.author_segment
        manifest_path = author_directory / MANIFEST_NAME
        lock_path = self._author_lock_path(plan.author_segment)
        author_staging = self._staging_root / "staging" / plan.author_segment
        _ensure_child_directories(self._staging_root, PurePosixPath("staging") / plan.author_segment)
        stage = author_staging / job_id
        if _safe_lstat(stage) is not None:
            raise ExportConflictError("staging_exists")
        stage.mkdir()
        try:
            managed: list[ManagedFile] = []
            for planned in plan.files:
                item = _render_file(stage, planned)
                managed.append(item)
                self._fault("after_stage_file", item.relative_path)
            files = tuple(sorted(managed, key=lambda item: (item.relative_path.casefold(), item.relative_path)))
            tree_sha256 = _tree_sha256(files)
            rendered = RenderedExport(
                layout_version=LAYOUT_VERSION,
                job_id=job_id,
                author=author,
                author_segment=plan.author_segment,
                staging_directory=stage,
                predecessor_manifest_sha256=None,
                source_fingerprint=plan.source_fingerprint,
                content_fingerprints=plan.content_fingerprints,
                files=files,
                tree_sha256=tree_sha256,
                manifest_sha256="0" * 64,
            )
            manifest_bytes = _manifest_bytes(rendered)
            rendered = replace(rendered, manifest_sha256=_sha256_bytes(manifest_bytes))
            _write_new_bytes(stage / MANIFEST_NAME, manifest_bytes)
            with _author_lock(lock_path, self._lock_timeout_seconds):
                _recover_pending_transactions(author_directory, manifest_path, author)
                predecessor_bytes = _fence_render_predecessor(
                    self._export_root,
                    author_directory,
                    manifest_path,
                    author,
                    expected_predecessor,
                    rendered,
                )
            predecessor_sha256 = None if predecessor_bytes is None else _sha256_bytes(predecessor_bytes)
            return replace(rendered, predecessor_manifest_sha256=predecessor_sha256)
        except BaseException:
            with contextlib.suppress(OSError, ExportError):
                _safe_remove_staging(stage, self._staging_root)
            raise

    def publish(self, rendered: RenderedExport) -> ExportResult:
        """Publish one rendered tree under its creator lock with managed-file CAS."""

        if rendered.layout_version != LAYOUT_VERSION:
            raise ExportError("layout_version_mismatch")
        if author_relative_directory(rendered.author).as_posix() != rendered.author_segment:
            raise ExportError("author_identity_mismatch")
        if _JOB_ID_PATTERN.fullmatch(rendered.job_id) is None:
            raise ExportError("invalid_job_id")
        expected_stage = self._staging_root / "staging" / rendered.author_segment / rendered.job_id
        if rendered.staging_directory.absolute() != expected_stage.absolute():
            raise ExportError("unsafe_staging_path")
        author_directory = self._export_root / rendered.author_segment
        manifest_path = author_directory / MANIFEST_NAME
        lock_path = self._author_lock_path(rendered.author_segment)
        with _author_lock(lock_path, self._lock_timeout_seconds):
            _recover_pending_transactions(author_directory, manifest_path, rendered.author)
            self._publish_locked(rendered, author_directory, manifest_path)
        with contextlib.suppress(OSError, ExportError):
            _safe_remove_staging(rendered.staging_directory, self._staging_root)
        return ExportResult.from_rendered(rendered, author_directory, manifest_path)

    def discard(self, rendered: RenderedExport) -> None:
        """Safely remove an unpublished staging tree owned by this exporter."""

        if rendered.layout_version != LAYOUT_VERSION or _JOB_ID_PATTERN.fullmatch(rendered.job_id) is None:
            raise ExportError("invalid_rendered_export")
        expected_stage = self._staging_root / "staging" / rendered.author_segment / rendered.job_id
        if rendered.staging_directory.absolute() != expected_stage.absolute():
            raise ExportError("unsafe_staging_path")
        _safe_remove_staging(rendered.staging_directory, self._staging_root)

    def export(
        self,
        author: ExportAuthor,
        contents: Sequence[ExportContent],
        *,
        job_id: str,
        expected_predecessor: PublishedIdentity | None,
    ) -> ExportResult:
        """Render and publish one complete author snapshot."""

        return self.publish(
            self.render(
                author,
                contents,
                job_id=job_id,
                expected_predecessor=expected_predecessor,
            )
        )

    def _verify_staging(self, rendered: RenderedExport) -> None:
        stage_stat = _safe_lstat(rendered.staging_directory)
        if stage_stat is None or not stat.S_ISDIR(stage_stat.st_mode):
            raise ExportError("staging_missing")
        expected_manifest = _manifest_bytes(rendered)
        if _sha256_bytes(expected_manifest) != rendered.manifest_sha256:
            raise ExportError("staging_manifest_mismatch")
        stage_manifest = rendered.staging_directory / MANIFEST_NAME
        manifest_stat = _safe_lstat(stage_manifest)
        if manifest_stat is None or not stat.S_ISREG(manifest_stat.st_mode):
            raise ExportError("staging_manifest_mismatch")
        if (
            _read_safe_regular(
                stage_manifest,
                error_code="staging_manifest_mismatch",
                max_bytes=_MAX_MANIFEST_BYTES,
            )
            != expected_manifest
        ):
            raise ExportError("staging_manifest_mismatch")
        for item in rendered.files:
            relative = _validate_relative_path(item.relative_path)
            staged = rendered.staging_directory.joinpath(*relative.parts)
            checksum, size = _verify_regular_file(staged, unsafe_code="unsafe_staging_path")
            if checksum != item.sha256 or size != item.size_bytes:
                raise ExportError("staging_file_mismatch")
        if _tree_sha256(rendered.files) != rendered.tree_sha256:
            raise ExportError("staging_tree_mismatch")

    def _execute_transaction(
        self,
        transaction: _PublishTransaction,
        desired_files: Sequence[ManagedFile],
    ) -> None:
        runtime = _TransactionRuntime(captured_operations=set(), installed_operations=set())
        try:
            for operation in transaction.operations:
                relative = PurePosixPath(operation.relative_path)
                _ensure_child_directories(transaction.author_directory, relative.parent)
                target = transaction.author_directory.joinpath(*relative.parts)
                if operation.kind in {"replace", "delete"}:
                    if operation.old_file is None:
                        raise ExportError("publish_transaction_invalid")
                    event = "before_publish_file" if operation.kind == "replace" else "before_delete_file"
                    self._fault(event, operation.relative_path)
                    _capture_existing(
                        target,
                        operation.capture_path,
                        expected=operation.old_file,
                        mismatch_code="managed_file_modified",
                    )
                    runtime.captured_operations.add(operation.relative_path)
                elif operation.kind == "create":
                    self._fault("before_publish_file", operation.relative_path)
                else:  # pragma: no cover - private construction guard
                    raise ExportError("publish_transaction_invalid")
                if operation.kind in {"replace", "create"}:
                    if operation.new_file is None or operation.candidate_path is None:
                        raise ExportError("publish_transaction_invalid")
                    conflict_code = (
                        "managed_file_modified" if operation.kind == "replace" else "unmanaged_path_conflict"
                    )
                    if not _link_no_clobber(
                        operation.candidate_path,
                        target,
                        expected=operation.new_file,
                        conflict_code=conflict_code,
                        transaction_directory=transaction.directory,
                    ):
                        raise ExportConflictError(conflict_code)
                    runtime.installed_operations.add(operation.relative_path)
                    self._fault("after_publish_file", operation.relative_path)
                else:
                    self._fault("after_delete_file", operation.relative_path)

            self._fault("before_manifest", None)
            for operation in transaction.operations:
                if operation.relative_path not in runtime.installed_operations:
                    continue
                if (
                    operation.new_file is None or operation.verification_path is None
                ):  # pragma: no cover - private construction guard
                    raise ExportError("publish_transaction_invalid")
                target = transaction.author_directory.joinpath(*PurePosixPath(operation.relative_path).parts)
                _capture_existing(
                    target,
                    operation.verification_path,
                    expected=operation.new_file,
                    mismatch_code="managed_file_modified",
                )
                if not _restore_capture_no_clobber(
                    operation.verification_path,
                    target,
                    operation.new_file,
                ):
                    raise ExportError("publish_rollback_failed")
            predecessor = transaction.predecessor_manifest
            if predecessor is not None:
                _capture_existing(
                    transaction.manifest_path,
                    transaction.manifest_capture_path,
                    expected=predecessor,
                    mismatch_code="stale_publish",
                )
                runtime.manifest_captured = True
            if not _link_no_clobber(
                transaction.manifest_candidate_path,
                transaction.manifest_path,
                expected=transaction.desired_manifest,
                conflict_code="stale_publish",
                transaction_directory=transaction.directory,
            ):
                raise ExportConflictError("stale_publish")
            runtime.manifest_installed = True
            self._fault("after_manifest", None)
            _capture_existing(
                transaction.manifest_path,
                transaction.manifest_verification_path,
                expected=transaction.desired_manifest,
                mismatch_code="stale_publish",
            )
            if not _restore_capture_no_clobber(
                transaction.manifest_verification_path,
                transaction.manifest_path,
                transaction.desired_manifest,
            ):
                raise ExportError("publish_rollback_failed")
            _verify_complete_publication(
                transaction.author_directory,
                transaction.manifest_path,
                transaction.desired_manifest,
                desired_files,
                error_code="stale_publish",
                managed_file_error_code="managed_file_modified",
            )
        except BaseException as error:
            try:
                rolled_back = _rollback_transaction(transaction, runtime)
            except BaseException:
                rolled_back = False
            forced_conflict = isinstance(error, ExportError) and error.code == "publish_rollback_failed"
            if not rolled_back or forced_conflict:
                with contextlib.suppress(ExportError, OSError):
                    _mark_transaction_conflict(transaction)
                raise ExportError("publish_rollback_failed") from error
            with contextlib.suppress(ExportError, OSError):
                _cleanup_transaction(transaction)
            if isinstance(error, ExportError):
                raise
            raise ExportError("publish_failed") from error
        with contextlib.suppress(ExportError, OSError):
            _cleanup_transaction(transaction)

    def _publish_locked(self, rendered: RenderedExport, author_directory: Path, manifest_path: Path) -> None:
        self._verify_staging(rendered)
        _ensure_directory(self._export_root)
        _ensure_directory(author_directory)
        root_stat = _safe_lstat(self._export_root)
        author_stat = _safe_lstat(author_directory)
        if root_stat is None or not stat.S_ISDIR(root_stat.st_mode):
            raise ExportConflictError("unsafe_existing_path")
        if author_stat is None or not stat.S_ISDIR(author_stat.st_mode):
            raise ExportConflictError("unsafe_existing_path")
        old_manifest_bytes = _read_manifest_payload(manifest_path)
        current_predecessor = None if old_manifest_bytes is None else _sha256_bytes(old_manifest_bytes)
        if current_predecessor != rendered.predecessor_manifest_sha256:
            raise ExportConflictError("stale_publish")
        old_manifest = None if old_manifest_bytes is None else _parse_manifest(old_manifest_bytes, rendered.author)
        old_files = {item.relative_path: item for item in old_manifest.files} if old_manifest is not None else {}
        desired_files = {item.relative_path: item for item in rendered.files}
        replacements: list[tuple[ManagedFile, Path, Path]] = []
        created: list[tuple[ManagedFile, Path, Path]] = []
        stale: list[tuple[ManagedFile, Path]] = []

        for relative_value, item in desired_files.items():
            relative = _validate_relative_path(relative_value)
            existing = _existing_case_variant(author_directory, relative)
            target = author_directory.joinpath(*relative.parts)
            staged = rendered.staging_directory.joinpath(*relative.parts)
            if existing is None:
                created.append((item, staged, target))
                continue
            previous = old_files.get(relative_value)
            if previous is None:
                raise ExportConflictError("unmanaged_path_conflict")
            checksum, size = _verify_regular_file(existing)
            existing_stat = _safe_lstat(existing)
            if (
                checksum != previous.sha256
                or size != previous.size_bytes
                or existing_stat is None
                or existing_stat.st_nlink != 1
            ):
                raise ExportConflictError("managed_file_modified")
            if checksum != item.sha256 or size != item.size_bytes:
                replacements.append((item, staged, target))

        for relative_value, previous in old_files.items():
            if relative_value in desired_files:
                continue
            relative = _validate_relative_path(relative_value)
            target = author_directory.joinpath(*relative.parts)
            try:
                existing = _existing_case_variant(author_directory, relative)
            except ExportConflictError:
                continue
            if existing is None:
                continue
            try:
                checksum, size = _verify_regular_file(existing)
            except ExportConflictError:
                continue
            if checksum == previous.sha256 and size == previous.size_bytes:
                stale.append((previous, target))

        transaction = _prepare_transaction(
            rendered,
            author_directory,
            manifest_path,
            old_manifest_bytes,
            old_files,
            replacements,
            created,
            stale,
        )
        self._execute_transaction(transaction, rendered.files)

        for _, target in stale:
            _prune_empty_parents(target.parent, author_directory)


__all__ = ["EmbyExporter", "FaultInjector"]
