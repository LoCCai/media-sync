"""Fail-closed filesystem primitives for media-owned trees."""

from __future__ import annotations

import contextlib
import os
import stat
import threading
from collections.abc import Iterator
from pathlib import Path, PurePath
from typing import BinaryIO, cast

_FILE_LOCKS_GUARD = threading.Lock()
_FILE_LOCKS: dict[str, threading.Lock] = {}


class PathSecurityError(Exception):
    """A redaction-safe rejection of an unsafe filesystem object."""

    code = "filesystem_unsafe"

    def __init__(self) -> None:
        super().__init__("filesystem_unsafe: filesystem object is not safe")


class PathLockBusyError(Exception):
    """A safe regular lock file is currently owned by another worker."""

    def __init__(self) -> None:
        super().__init__("filesystem_lock_busy: filesystem lock is already owned")


def _is_reparse(mode_result: os.stat_result) -> bool:
    attributes = getattr(mode_result, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _local_file_lock(path: Path) -> threading.Lock:
    key = os.path.normcase(str(path.absolute()))
    with _FILE_LOCKS_GUARD:
        return _FILE_LOCKS.setdefault(key, threading.Lock())


def _try_os_file_lock(handle: BinaryIO) -> bool:
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
    except (BlockingIOError, OSError):
        return False
    return True


def _unlock_os_file(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


def _validate_relative(relative: str | PurePath) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.anchor or not candidate.parts:
        raise PathSecurityError
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise PathSecurityError
    return candidate


def _assert_plain_directory(path: Path) -> None:
    try:
        details = path.lstat()
    except OSError as exc:
        raise PathSecurityError from exc
    if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode) or _is_reparse(details):
        raise PathSecurityError


def ensure_secure_root(root: Path) -> Path:
    """Create and validate a root that is itself a plain directory."""

    absolute = root.absolute()
    try:
        absolute.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PathSecurityError from exc
    _assert_plain_directory(absolute)
    return absolute


def ensure_secure_directory(root: Path, relative: str | PurePath) -> Path:
    """Create a directory below *root*, rejecting links and reparse points."""

    safe_root = ensure_secure_root(root)
    relative_path = _validate_relative(relative)
    current = safe_root
    for component in relative_path.parts:
        current = current / component
        try:
            current.mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise PathSecurityError from exc
        _assert_plain_directory(current)
    return current


def confined_file(root: Path, relative: str | PurePath, *, must_exist: bool = False) -> Path:
    """Return a lexically confined file path after validating existing parents."""

    safe_root = ensure_secure_root(root)
    relative_path = _validate_relative(relative)
    if len(relative_path.parts) > 1:
        parent = ensure_secure_directory(safe_root, Path(*relative_path.parts[:-1]))
    else:
        parent = safe_root
    candidate = parent / relative_path.name
    if candidate.exists() or candidate.is_symlink():
        assert_regular_file(candidate, root=safe_root)
    elif must_exist:
        raise PathSecurityError
    return candidate


@contextlib.contextmanager
def exclusive_file_lock(root: Path, relative: str | PurePath) -> Iterator[None]:
    """Acquire one non-blocking process/thread lock on a confined regular file."""

    candidate = confined_file(root, relative)
    local = _local_file_lock(candidate)
    if not local.acquire(blocking=False):
        raise PathLockBusyError
    handle: BinaryIO | None = None
    os_locked = False
    try:
        existing = None
        try:
            existing = candidate.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise PathSecurityError from exc
        if existing is not None and (
            not stat.S_ISREG(existing.st_mode)
            or stat.S_ISLNK(existing.st_mode)
            or _is_reparse(existing)
            or existing.st_nlink != 1
        ):
            raise PathSecurityError
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(candidate, flags, 0o600)
            handle = cast(BinaryIO, os.fdopen(descriptor, "r+b"))
        except OSError as exc:
            raise PathSecurityError from exc
        opened = os.fstat(handle.fileno())
        current = assert_regular_file(candidate, root=root)
        if not _same_file(opened, current) or opened.st_size not in {0, 1}:
            raise PathSecurityError
        if opened.st_size == 0:
            handle.seek(0)
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        if not _try_os_file_lock(handle):
            raise PathLockBusyError
        os_locked = True
        final_opened = os.fstat(handle.fileno())
        final_named = assert_regular_file(candidate, root=root)
        if not _same_file(final_opened, final_named) or final_opened.st_size != 1:
            raise PathSecurityError
        yield
    finally:
        if handle is not None:
            if os_locked:
                with contextlib.suppress(OSError):
                    _unlock_os_file(handle)
            handle.close()
        local.release()


def assert_regular_file(path: Path, *, root: Path, single_link: bool = True) -> os.stat_result:
    """Validate a regular, non-link file confined beneath *root*."""

    safe_root = ensure_secure_root(root)
    absolute = path.absolute()
    try:
        relative = absolute.relative_to(safe_root)
    except ValueError as exc:
        raise PathSecurityError from exc
    _validate_relative(relative)
    current = safe_root
    for component in relative.parts[:-1]:
        current /= component
        _assert_plain_directory(current)
    try:
        details = absolute.lstat()
    except OSError as exc:
        raise PathSecurityError from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or _is_reparse(details)
        or (single_link and details.st_nlink != 1)
    ):
        raise PathSecurityError
    return details


def open_regular_file(path: Path, *, root: Path, append: bool = False) -> BinaryIO:
    """Open an existing regular file and revalidate the opened descriptor."""

    assert_regular_file(path, root=root)
    flags = os.O_WRONLY | (os.O_APPEND if append else os.O_TRUNC)
    flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            os.close(descriptor)
            raise PathSecurityError
        return cast(BinaryIO, os.fdopen(descriptor, "ab" if append else "wb"))
    except PathSecurityError:
        raise
    except OSError as exc:
        raise PathSecurityError from exc


def open_regular_read_file(path: Path, *, root: Path) -> BinaryIO:
    """Open an existing regular file for reading without following links."""

    assert_regular_file(path, root=root)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            os.close(descriptor)
            raise PathSecurityError
        return cast(BinaryIO, os.fdopen(descriptor, "rb"))
    except PathSecurityError:
        raise
    except OSError as exc:
        raise PathSecurityError from exc


def read_regular_file_bytes(path: Path, *, root: Path, max_bytes: int) -> bytes:
    """Read a bounded file and reject path replacement around the opened descriptor."""

    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")
    try:
        with open_regular_read_file(path, root=root) as handle:
            opened = os.fstat(handle.fileno())
            payload = handle.read(max_bytes + 1)
            after_read = os.fstat(handle.fileno())
        current = assert_regular_file(path, root=root)
    except PathSecurityError:
        raise
    except OSError as exc:
        raise PathSecurityError from exc
    identities = (
        (opened.st_dev, opened.st_ino),
        (after_read.st_dev, after_read.st_ino),
        (current.st_dev, current.st_ino),
    )
    if len(set(identities)) != 1 or len(payload) > max_bytes:
        raise PathSecurityError
    return payload


def read_regular_file_prefix(path: Path, *, root: Path, max_bytes: int) -> bytes:
    """Read at most *max_bytes* while detecting replacement of the named file."""

    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")
    try:
        with open_regular_read_file(path, root=root) as handle:
            opened = os.fstat(handle.fileno())
            payload = handle.read(max_bytes)
            after_read = os.fstat(handle.fileno())
        current = assert_regular_file(path, root=root)
    except PathSecurityError:
        raise
    except OSError as exc:
        raise PathSecurityError from exc
    identities = (
        (opened.st_dev, opened.st_ino),
        (after_read.st_dev, after_read.st_ino),
        (current.st_dev, current.st_ino),
    )
    if len(set(identities)) != 1:
        raise PathSecurityError
    return payload


def create_regular_file(path: Path, *, root: Path) -> BinaryIO:
    """Exclusively create a regular file below *root*."""

    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise PathSecurityError from exc
    confined_file(root, relative)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            os.close(descriptor)
            raise PathSecurityError
        return cast(BinaryIO, os.fdopen(descriptor, "wb"))
    except PathSecurityError:
        raise
    except OSError as exc:
        raise PathSecurityError from exc


def safe_unlink(path: Path, *, root: Path, missing_ok: bool = False) -> None:
    """Unlink only a currently safe regular file."""

    if not path.exists() and not path.is_symlink():
        if missing_ok:
            return
        raise PathSecurityError
    assert_regular_file(path, root=root)
    try:
        path.unlink()
    except OSError as exc:
        raise PathSecurityError from exc


def atomic_write_bytes(root: Path, relative: str | PurePath, payload: bytes) -> Path:
    """Atomically replace a small managed file using a same-directory temporary."""

    destination = confined_file(root, relative)
    temporary = destination.with_name(f".{destination.name}.{os.urandom(12).hex()}.tmp")
    handle = create_regular_file(temporary, root=root)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if destination.exists() or destination.is_symlink():
            assert_regular_file(destination, root=root)
        os.replace(temporary, destination)
        assert_regular_file(destination, root=root)
        return destination
    except Exception:
        if temporary.exists() and not temporary.is_symlink():
            safe_unlink(temporary, root=root, missing_ok=True)
        raise


__all__ = [
    "PathLockBusyError",
    "PathSecurityError",
    "assert_regular_file",
    "atomic_write_bytes",
    "confined_file",
    "create_regular_file",
    "ensure_secure_directory",
    "ensure_secure_root",
    "exclusive_file_lock",
    "open_regular_file",
    "open_regular_read_file",
    "read_regular_file_bytes",
    "read_regular_file_prefix",
    "safe_unlink",
]
