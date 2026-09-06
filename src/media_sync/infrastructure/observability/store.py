"""Bounded asynchronous JSONL storage with process-owned, authenticated segments.

Enqueue acceptance is not durability. Counters are process-local; capacity and
cleanup are coordinated across processes sharing the same private directory.
Segments are ordered by creation identity, not by global event commit time.
"""

from __future__ import annotations

import base64
import contextlib
import ctypes
import hashlib
import hmac
import json
import os
import queue
import re
import secrets
import stat
import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, cast
from uuid import uuid4

from media_sync.infrastructure.observability.events import (
    ENUM_FIELDS,
    EVENT_SCHEMA_VERSION,
    MAX_EVENT_BYTES,
    UUID_FIELDS,
    EventValidationError,
    canonical_time,
    canonical_uuid,
    format_time,
    validate_event,
    validate_record,
)

_MARKER = ".media-sync-log-store-v1"
_LOCK = ".media-sync-log-lock-v1"
_SEGMENT = re.compile(r"log-(\d{8}T\d{12}Z)-([0-9a-f-]{36})-([0-9a-f-]{36})\.(open|jsonl)\Z")
_FOOTER_RESERVE = 512
_MAX_ENTRIES = 4096
_MAX_SCAN_BYTES = 4 * 1024 * 1024
_MAX_SCAN_SECONDS = 2.0
_MAX_CURSOR_BYTES = 2048
_IDLE_SECONDS = 1.0
_ERRORS = frozenset(
    {
        "log_store_unavailable",
        "log_cursor_invalid",
        "log_cursor_stale",
        "log_query_invalid",
        "log_store_scan_limited",
        "log_queue_full",
        "log_event_invalid",
        "log_capacity_exhausted",
        "log_store_closed",
        "log_lock_busy",
        "log_flush_timeout",
    }
)
_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_GUARD = threading.Lock()


class LogStoreError(ValueError):
    """Only fixed error codes may cross the storage boundary."""

    def __init__(self, code: str = "log_store_unavailable") -> None:
        self.code = code if code in _ERRORS else "log_store_unavailable"
        super().__init__(self.code)


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _plain(details: os.stat_result, *, directory: bool = False) -> bool:
    return (
        (stat.S_ISDIR(details.st_mode) if directory else stat.S_ISREG(details.st_mode))
        and not stat.S_ISLNK(details.st_mode)
        and not (getattr(details, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
        and (directory or details.st_nlink == 1)
    )


def _identity(details: os.stat_result) -> tuple[int, int]:
    return details.st_dev, details.st_ino


def _windows_pin(path: Path) -> int:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    create.restype = ctypes.c_void_p
    handle = create(str(path), 1, 3, None, 3, 0x00200000 | 0x02000000, None)
    if handle is None or handle == ctypes.c_void_p(-1).value:
        raise LogStoreError
    return int(handle)


def _windows_close(handle: int) -> None:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    close = kernel.CloseHandle
    close.argtypes = (ctypes.c_void_p,)
    close.restype = ctypes.c_int
    close(handle)


class _Root:
    """Pin every ancestor; use descriptor-relative POSIX access and Windows pins."""

    def __init__(self, path: Path, *, create: bool) -> None:
        self.path = path
        self.create = create
        self.fd: int | None = None
        self._fds: list[int] = []
        self._pins: list[int] = []
        self._identities: list[tuple[Path, tuple[int, int]]] = []

    def __enter__(self) -> _Root:
        if not self.path.is_absolute() or self.path == Path(self.path.anchor) or ".." in self.path.parts:
            raise LogStoreError
        try:
            current = Path(self.path.anchor)
            for index, part in enumerate(self.path.parts):
                if index:
                    current /= part
                    if self.create:
                        try:
                            if self.fd is None:
                                current.mkdir(mode=0o700)
                            else:
                                os.mkdir(part, mode=0o700, dir_fd=self.fd)
                        except FileExistsError:
                            pass
                before = current.lstat()
                if not _plain(before, directory=True):
                    raise LogStoreError
                if os.name == "nt":
                    self._pins.append(_windows_pin(current))
                else:
                    flags = (
                        os.O_RDONLY
                        | getattr(os, "O_DIRECTORY", 0)
                        | getattr(os, "O_NOFOLLOW", 0)
                        | getattr(os, "O_CLOEXEC", 0)
                    )
                    descriptor = os.open(part, flags, dir_fd=self.fd) if index else os.open(current, flags)
                    self._fds.append(descriptor)
                    self.fd = descriptor
                    if _identity(os.fstat(descriptor)) != _identity(before):
                        raise LogStoreError
                after = current.lstat()
                if not _plain(after, directory=True) or _identity(before) != _identity(after):
                    raise LogStoreError
                self._identities.append((current, _identity(after)))
            self.verify()
            return self
        except (OSError, ValueError):
            self.__exit__(None, None, None)
            raise LogStoreError from None

    def __exit__(self, *_args: object) -> None:
        for descriptor in reversed(self._fds):
            os.close(descriptor)
        for pin in reversed(self._pins):
            _windows_close(pin)
        self._fds.clear()
        self._pins.clear()

    def verify(self) -> None:
        for path, expected in self._identities:
            observed = path.lstat()
            if not _plain(observed, directory=True) or _identity(observed) != expected:
                raise LogStoreError

    def details(self, name: str) -> os.stat_result:
        self.verify()
        details = (
            (self.path / name).lstat() if self.fd is None else os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        )
        if not _plain(details):
            raise LogStoreError
        return details

    def open(self, name: str, *, create: bool = False, append: bool = False, lock: bool = False) -> BinaryIO:
        self.verify()
        before = None if create else self.details(name)
        flags = os.O_RDWR if lock else (os.O_WRONLY if create or append else os.O_RDONLY)
        flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        if create:
            flags |= os.O_CREAT | os.O_EXCL
        if append:
            flags |= os.O_APPEND
        descriptor = (
            os.open(self.path / name, flags, 0o600) if self.fd is None else os.open(name, flags, 0o600, dir_fd=self.fd)
        )
        try:
            opened = os.fstat(descriptor)
            after = self.details(name)
            if (
                not _plain(opened)
                or _identity(opened) != _identity(after)
                or (before is not None and _identity(before) != _identity(opened))
            ):
                raise LogStoreError
            handle = os.fdopen(descriptor, "r+b" if lock else ("ab" if append else "wb" if create else "rb"))
            descriptor = -1
            return handle
        finally:
            if descriptor != -1:
                os.close(descriptor)

    def names(self, deadline: float) -> list[str]:
        self.verify()
        result: list[str] = []
        with os.scandir(self.path if self.fd is None else self.fd) as entries:
            for entry in entries:
                if len(result) >= _MAX_ENTRIES or time.monotonic() >= deadline:
                    raise LogStoreError("log_store_scan_limited")
                result.append(entry.name)
        return result

    def unlink(self, name: str, expected: tuple[int, int]) -> None:
        if _identity(self.details(name)) != expected:
            raise LogStoreError
        if self.fd is None:
            (self.path / name).unlink()
        else:
            os.unlink(name, dir_fd=self.fd)

    def seal(self, name: str) -> str:
        destination = name.removesuffix(".open") + ".jsonl"
        self.details(name)
        try:
            self.details(destination)
        except FileNotFoundError:
            pass
        else:
            raise LogStoreError
        if self.fd is None:
            os.rename(self.path / name, self.path / destination)
        else:
            os.rename(name, destination, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        return destination


@contextlib.contextmanager
def _locked(root: _Root) -> Iterator[None]:
    with _LOCAL_GUARD:
        local = _LOCAL_LOCKS.setdefault(os.path.normcase(str(root.path)), threading.Lock())
    if not local.acquire(timeout=0.1):
        raise LogStoreError("log_lock_busy")
    try:
        try:
            root.details(_LOCK)
        except FileNotFoundError:
            try:
                with root.open(_LOCK, create=True) as created:
                    created.write(b"\0")
            except FileExistsError:
                pass
        with root.open(_LOCK, lock=True) as handle:
            if os.fstat(handle.fileno()).st_size == 0:
                raise LogStoreError("log_lock_busy")
            if os.fstat(handle.fileno()).st_size != 1:
                raise LogStoreError
            if os.name == "nt":
                import msvcrt

                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    raise LogStoreError("log_lock_busy") from None
            else:
                import fcntl

                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
                except OSError:
                    raise LogStoreError("log_lock_busy") from None
            try:
                yield
            finally:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
    finally:
        local.release()


@dataclass(frozen=True)
class _Segment:
    name: str
    size: int
    identity: tuple[int, int]
    header: dict[str, object]
    start: int
    end: int
    sealed: bool


@contextlib.contextmanager
def _read_optional(root: _Root, name: str) -> Iterator[BinaryIO | None]:
    try:
        handle = root.open(name)
    except (OSError, ValueError):
        yield None
        return
    with handle:
        yield handle


class LogStore:
    """Best-effort closed-schema sink. No filesystem I/O occurs in emit()."""

    def __init__(
        self,
        root: Path | str,
        *,
        segment_max_bytes: int = 16 * 1024 * 1024,
        total_max_bytes: int = 1024 * 1024 * 1024,
        retention_days: int = 7,
        queue_capacity: int = 1024,
    ) -> None:
        if (
            type(segment_max_bytes) is not int
            or segment_max_bytes < 1024
            or type(total_max_bytes) is not int
            or total_max_bytes < segment_max_bytes
            or type(retention_days) is not int
            or not 1 <= retention_days <= 3650
            or type(queue_capacity) is not int
            or not 1 <= queue_capacity <= 65536
        ):
            raise LogStoreError("log_query_invalid")
        self.root = Path(root).absolute()
        self.segment_max_bytes = segment_max_bytes
        self.total_max_bytes = total_max_bytes
        self.retention_days = retention_days
        self.writer_id = str(uuid4())
        self._cursor_key = secrets.token_bytes(32)
        self._store_id: str | None = None
        self._key: bytes | None = None
        self._active: str | None = None
        self._active_header: dict[str, object] | None = None
        self._active_size = 0
        self._active_count = 0
        self._active_identity: tuple[int, int] | None = None
        self._active_sealing = False
        self._queue: queue.Queue[dict[str, object]] = queue.Queue(queue_capacity)
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._closed = False
        self._accepted = self._written = self._dropped = self._invalid = self._processed = 0
        self._retention_deleted = self._capacity_deleted = 0
        self._last_error: str | None = None
        self._worker: threading.Thread | None = None

    def emit(self, event: Mapping[str, object]) -> bool:
        try:
            safe = validate_event(event)
        except (EventValidationError, TypeError, ValueError):
            with self._condition:
                self._invalid += 1
                self._dropped += 1
                self._last_error = "log_event_invalid"
            return False
        with self._condition:
            if self._closed:
                self._dropped += 1
                self._last_error = "log_store_closed"
                return False
            safe.update(
                schema_version=EVENT_SCHEMA_VERSION,
                timestamp=format_time(datetime.now(UTC)),
                writer_id=self.writer_id,
                sequence=self._accepted + self._dropped + 1,
            )
            if len(_json(safe)) + 1 > MAX_EVENT_BYTES:
                self._invalid += 1
                self._dropped += 1
                self._last_error = "log_event_invalid"
                return False
            try:
                self._queue.put_nowait(safe)
            except queue.Full:
                self._dropped += 1
                self._last_error = "log_queue_full"
                self._start_worker_locked()
                return False
            self._accepted += 1
            self._start_worker_locked()
            self._condition.notify_all()
            return True

    def _start_worker_locked(self) -> None:
        if self._worker is not None:
            return
        try:
            self._worker = threading.Thread(target=self._run, name="media-sync-log-writer", daemon=True)
            self._worker.start()
        except Exception:
            # Acceptance still means queued, never durable. A later emit,
            # flush or close can restart the retained queue after recovery.
            self._worker = None
            self._last_error = "log_store_unavailable"

    def _prepare(self, root: _Root) -> None:
        try:
            root.details(_MARKER)
        except FileNotFoundError:
            if self._store_id is not None:
                raise LogStoreError from None
            marker = {"schema_version": 1, "store_id": str(uuid4()), "key": secrets.token_hex(32)}
            with root.open(_MARKER, create=True) as handle:
                handle.write(_json(marker))
                handle.flush()
                os.fsync(handle.fileno())
        with root.open(_MARKER) as handle:
            data = handle.read(257)
        marker = json.loads(data)
        if (
            len(data) > 256
            or type(marker) is not dict
            or set(marker) != {"schema_version", "store_id", "key"}
            or type(marker["schema_version"]) is not int
            or marker["schema_version"] != 1
            or type(marker["key"]) is not str
            or not re.fullmatch("[0-9a-f]{64}", marker["key"])
        ):
            raise LogStoreError
        store_id = canonical_uuid(marker["store_id"])
        key = bytes.fromhex(marker["key"])
        if self._store_id is not None and (self._store_id != store_id or self._key != key):
            raise LogStoreError
        self._store_id, self._key = store_id, key

    def _signed(self, payload: dict[str, object]) -> dict[str, object]:
        if self._key is None:
            raise LogStoreError
        return {**payload, "mac": hmac.new(self._key, _json(payload), hashlib.sha256).hexdigest()}

    def _verified(self, line: bytes) -> dict[str, object]:
        if self._key is None or len(line) > _FOOTER_RESERVE:
            raise LogStoreError
        value = json.loads(line)
        if (
            type(value) is not dict
            or type(value.get("mac")) is not str
            or re.fullmatch("[0-9a-f]{64}", value["mac"]) is None
        ):
            raise LogStoreError
        signature = value.pop("mac")
        if not hmac.compare_digest(signature, hmac.new(self._key, _json(value), hashlib.sha256).hexdigest()):
            raise LogStoreError
        return cast(dict[str, object], value)

    def _segment(self, root: _Root, name: str) -> _Segment | None:
        match = _SEGMENT.fullmatch(name)
        if match is None:
            return None
        details = root.details(name)
        with root.open(name) as handle:
            header_line = handle.readline(_FOOTER_RESERVE + 1)
            header = self._verified(header_line)
            if (
                set(header) != {"type", "store_id", "writer_id", "segment_id", "created_at"}
                or header["type"] != "segment_v1"
                or header["store_id"] != self._store_id
                or header["writer_id"] != canonical_uuid(match[2])
                or header["segment_id"] != canonical_uuid(match[3])
                or canonical_time(header["created_at"]).replace("-", "").replace(":", "").replace(".", "") != match[1]
            ):
                raise LogStoreError
            end = details.st_size
            sealed = match[4] == "jsonl"
            if sealed:
                handle.seek(max(len(header_line), details.st_size - _FOOTER_RESERVE))
                tail = handle.read(_FOOTER_RESERVE)
                if not tail.endswith(b"\n"):
                    raise LogStoreError
                footer_line = tail.rstrip(b"\n").rsplit(b"\n", 1)[-1]
                footer = self._verified(footer_line)
                end = details.st_size - len(footer_line) - 1
                if (
                    set(footer) != {"type", "segment_id", "end", "count"}
                    or footer["type"] != "sealed_v1"
                    or footer["segment_id"] != header["segment_id"]
                    or type(footer["end"]) is not int
                    or footer["end"] != end
                    or type(footer["count"]) is not int
                    or footer["count"] < 0
                ):
                    raise LogStoreError
            if _identity(root.details(name)) != _identity(details):
                raise LogStoreError
            return _Segment(name, details.st_size, _identity(details), header, len(header_line), end, sealed)

    def _inventory(self, root: _Root, deadline: float) -> tuple[list[_Segment], int, int]:
        segments: list[_Segment] = []
        total = root.details(_MARKER).st_size + root.details(_LOCK).st_size
        unavailable = 0
        for name in root.names(deadline):
            if name in {_MARKER, _LOCK}:
                continue
            if time.monotonic() >= deadline:
                raise LogStoreError("log_store_scan_limited")
            try:
                total += root.details(name).st_size
                segment = self._segment(root, name)
                if segment is not None:
                    segments.append(segment)
            except (OSError, ValueError):
                unavailable += 1
        return sorted(segments, key=lambda segment: segment.name), total, unavailable

    def _cleanup(self, root: _Root, segments: list[_Segment], total: int, needed: int) -> int:
        cutoff = format_time(datetime.now(UTC) - timedelta(days=self.retention_days))
        reserved = sum(_FOOTER_RESERVE for segment in segments if not segment.sealed)
        for segment in segments:
            if not segment.sealed:
                continue
            aged = str(segment.header["created_at"]) < cutoff
            if not aged and total + reserved + needed <= self.total_max_bytes:
                continue
            # Revalidate the authenticated seal and exact file identity immediately before unlink.
            current = self._segment(root, segment.name)
            if (
                current is None
                or not current.sealed
                or current.identity != segment.identity
                or current.size != segment.size
            ):
                raise LogStoreError
            root.unlink(segment.name, segment.identity)
            total -= segment.size
            with self._condition:
                if aged:
                    self._retention_deleted += 1
                else:
                    self._capacity_deleted += 1
        if total + reserved + needed > self.total_max_bytes:
            raise LogStoreError("log_capacity_exhausted")
        return total

    def _seal_active(self, root: _Root) -> None:
        if self._active is None or self._active_header is None:
            return
        footer = (
            _json(
                self._signed(
                    {
                        "type": "sealed_v1",
                        "segment_id": self._active_header["segment_id"],
                        "end": self._active_size,
                        "count": self._active_count,
                    }
                )
            )
            + b"\n"
        )
        details = root.details(self._active)
        if _identity(details) != self._active_identity or len(footer) > _FOOTER_RESERVE:
            raise LogStoreError
        self._active_sealing = True
        if details.st_size == self._active_size:
            with root.open(self._active, append=True) as handle:
                handle.write(footer)
                handle.flush()
                os.fsync(handle.fileno())
        elif details.st_size == self._active_size + len(footer):
            # A reader may temporarily prevent rename on Windows after the
            # footer is durable. Validate the exact seal and retry only rename.
            with root.open(self._active) as handle:
                handle.seek(self._active_size)
                if handle.read(len(footer) + 1) != footer:
                    raise LogStoreError
            with root.open(self._active, append=True) as handle:
                os.fsync(handle.fileno())
        else:
            raise LogStoreError
        root.seal(self._active)
        self._active = self._active_header = None
        self._active_count = self._active_size = 0
        self._active_identity = None
        self._active_sealing = False

    def _append(self, root: _Root, event: dict[str, object]) -> None:
        line = _json(event) + b"\n"
        now = format_time(datetime.now(UTC))
        if self._active is not None and (
            self._active_sealing
            or self._active_size + len(line) + _FOOTER_RESERVE > self.segment_max_bytes
            or (self._active_header is not None and str(self._active_header["created_at"])[:10] != now[:10])
        ):
            self._seal_active(root)
        header: dict[str, object] | None = None
        prefix = b""
        if self._active is None:
            header = {
                "type": "segment_v1",
                "store_id": self._store_id,
                "writer_id": self.writer_id,
                "segment_id": str(uuid4()),
                "created_at": now,
            }
            prefix = _json(self._signed(header)) + b"\n"
            if len(prefix) + len(line) + _FOOTER_RESERVE > self.segment_max_bytes:
                raise LogStoreError("log_capacity_exhausted")
        segments, total, unavailable = self._inventory(root, time.monotonic() + _MAX_SCAN_SECONDS)
        if unavailable:
            # Unaccountable entries are preserved, and never permit unsafe capacity claims.
            raise LogStoreError
        self._cleanup(root, segments, total, len(prefix) + len(line) + (_FOOTER_RESERVE if header else 0))
        if header is not None:
            stamp = now.replace("-", "").replace(":", "").replace(".", "")
            name = f"log-{stamp}-{self.writer_id}-{header['segment_id']}.open"
            with root.open(name, create=True) as handle:
                handle.write(prefix)
                handle.flush()
                os.fsync(handle.fileno())
                self._active_identity = _identity(os.fstat(handle.fileno()))
            self._active, self._active_header, self._active_size = name, header, len(prefix)
        if self._active is None:
            raise LogStoreError
        details = root.details(self._active)
        if details.st_size != self._active_size or _identity(details) != self._active_identity:
            raise LogStoreError
        with root.open(self._active, append=True) as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        self._active_size += len(line)
        self._active_count += 1

    def _run(self) -> None:
        last_activity = time.monotonic()
        while not self._stop.is_set() or not self._queue.empty():
            try:
                event = self._queue.get(timeout=0.05)
            except queue.Empty:
                if time.monotonic() - last_activity >= _IDLE_SECONDS:
                    with self._condition:
                        if self._stop.is_set():
                            break
                        if self._queue.empty():
                            self._worker = None
                            self._condition.notify_all()
                            return
                    last_activity = time.monotonic()
                continue
            code: str | None = None
            deadline = time.monotonic() + 0.5
            while True:
                try:
                    with _Root(self.root, create=True) as root, _locked(root):
                        self._prepare(root)
                        self._append(root, event)
                    break
                except Exception as exc:
                    code = exc.code if isinstance(exc, LogStoreError) else "log_store_unavailable"
                    if code == "log_lock_busy" and time.monotonic() < deadline:
                        time.sleep(0.01)
                        code = None
                        continue
                    break
            with self._condition:
                if code:
                    self._dropped += 1
                    self._last_error = code
                else:
                    self._written += 1
                self._processed += 1
                self._queue.task_done()
                self._condition.notify_all()
            last_activity = time.monotonic()
        self._finish_writer()
        with self._condition:
            self._worker = None
            self._condition.notify_all()

    def _finish_writer(self) -> None:
        try:
            if self._active is not None:
                with _Root(self.root, create=False) as root, _locked(root):
                    self._prepare(root)
                    self._seal_active(root)
        except Exception as exc:
            with self._condition:
                self._last_error = exc.code if isinstance(exc, LogStoreError) else "log_store_unavailable"

    def flush(self, timeout: float = 2.0) -> bool:
        if type(timeout) not in {int, float} or not 1 <= timeout <= 5:
            raise LogStoreError("log_query_invalid")
        deadline = time.monotonic() + timeout
        with self._condition:
            target = self._accepted
            if self._processed < target:
                self._start_worker_locked()
            while self._processed < target:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._last_error = "log_flush_timeout"
                    return False
                self._condition.wait(remaining)
            return self._written >= target

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._stop.set()
            if self._worker is None and (self._active is not None or not self._queue.empty()):
                # An idle writer retains its open segment. Seal it in the same
                # background lifecycle so fsync never escapes the join budget.
                self._start_worker_locked()
            worker = self._worker
        if worker is not None:
            worker.join(timeout=5)
        if worker is not None and worker.is_alive():
            with self._condition:
                self._last_error = "log_flush_timeout"

    def status(self) -> dict[str, object]:
        with self._condition:
            result: dict[str, object] = {
                "enabled": True,
                "health": "closed" if self._closed else "degraded" if self._last_error else "ok",
                "queued": self._accepted - self._processed,
                "writer_running": self._worker is not None and self._worker.is_alive(),
                "drained": self._accepted == self._processed,
                "shutdown_complete": (
                    self._closed and self._worker is None and self._accepted == self._processed and self._active is None
                ),
                "accepted": self._accepted,
                "written": self._written,
                "dropped": self._dropped,
                "invalid": self._invalid,
                "last_error": self._last_error,
                "segment_max_bytes": self.segment_max_bytes,
                "total_max_bytes": self.total_max_bytes,
                "retention_days": self.retention_days,
                "retention_deleted": self._retention_deleted,
                "capacity_deleted": self._capacity_deleted,
                "scope": "process_counters_shared_storage",
                "ordering": "segment_ascending",
                "global_time_order": False,
                "bounded": True,
                "scan_limited": False,
                "storage_bytes": None,
                "managed_segments": None,
                "sealed_segments": None,
                "active_segments": None,
            }
        try:
            with _Root(self.root, create=True) as root:
                with _locked(root):
                    self._prepare(root)
                segments, total, unavailable = self._inventory(root, time.monotonic() + _MAX_SCAN_SECONDS)
            result.update(
                storage_bytes=total,
                managed_segments=len(segments),
                sealed_segments=sum(segment.sealed for segment in segments),
                active_segments=sum(not segment.sealed for segment in segments),
            )
            if unavailable:
                result.update(health="degraded", last_error="log_store_unavailable")
        except (OSError, ValueError) as exc:
            code = exc.code if isinstance(exc, LogStoreError) else "log_store_unavailable"
            result.update(health="unavailable", last_error=code, scan_limited=code == "log_store_scan_limited")
        return result

    def _filters(self, values: Mapping[str, object]) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, value in values.items():
            if key not in UUID_FIELDS | {"since", "until", "module", "level", "event_code", "platform"}:
                raise LogStoreError("log_query_invalid")
            if value is None:
                continue
            if key in UUID_FIELDS:
                result[key] = canonical_uuid(value)
            elif key in {"since", "until"}:
                result[key] = canonical_time(value)
            elif key in {"module", "level", "event_code", "platform"}:
                if type(value) is not str or value not in ENUM_FIELDS[key]:
                    raise LogStoreError("log_query_invalid")
                result[key] = value
            else:
                raise LogStoreError("log_query_invalid")
        if "since" in result and "until" in result and result["since"] > result["until"]:
            raise LogStoreError("log_query_invalid")
        return result

    def _cursor(self, value: dict[str, object]) -> str:
        payload = _json(value)
        return base64.urlsafe_b64encode(payload + hmac.digest(self._cursor_key, payload, "sha256")).decode("ascii")

    def _decode_cursor(self, cursor: str, filters: dict[str, str]) -> dict[str, object]:
        try:
            if type(cursor) is not str or len(cursor) > _MAX_CURSOR_BYTES:
                raise LogStoreError("log_cursor_invalid")
            raw = base64.b64decode(cursor, altchars=b"-_", validate=True)
            payload, signature = raw[:-32], raw[-32:]
            if not hmac.compare_digest(signature, hmac.digest(self._cursor_key, payload, "sha256")):
                raise LogStoreError("log_cursor_stale")
            data = json.loads(payload)
            if (
                type(data) is not dict
                or set(data) != {"name", "offset", "filters", "store_id"}
                or data["store_id"] != self._store_id
                or data["filters"] != filters
                or type(data["name"]) is not str
                or _SEGMENT.fullmatch(data["name"]) is None
                or type(data["offset"]) is not int
                or data["offset"] < 0
            ):
                raise LogStoreError("log_cursor_invalid")
            return cast(dict[str, object], data)
        except (ValueError, TypeError) as exc:
            if isinstance(exc, LogStoreError):
                raise
            raise LogStoreError("log_cursor_invalid") from None

    def query(self, *, limit: int = 100, cursor: str | None = None, **filters: object) -> dict[str, object]:
        try:
            if type(limit) is not int or not 1 <= limit <= 200:
                raise LogStoreError("log_query_invalid")
            selected = self._filters(filters)
        except EventValidationError:
            raise LogStoreError("log_query_invalid") from None
        coverage: dict[str, object] = {
            "order": "segment_ascending",
            "global_time_order": False,
            "bounded": True,
            "scan_limited": False,
            "corrupt_records": 0,
            "truncated_segments": 0,
            "omitted_segment_tails": 0,
            "unavailable_segments": 0,
            "retention_may_have_removed": True,
        }
        events: list[dict[str, object]] = []
        next_cursor: str | None = None
        deadline = time.monotonic() + _MAX_SCAN_SECONDS
        try:
            with _Root(self.root, create=True) as root:
                with _locked(root):
                    self._prepare(root)
                segments, _total, unavailable = self._inventory(root, deadline)
                coverage["unavailable_segments"] = unavailable
                resume = self._decode_cursor(cursor, selected) if cursor is not None else None
                if resume is not None:
                    name = str(resume["name"])
                    # Rotation changes only the suffix, not the segment identity.
                    matching = [
                        index
                        for index, segment in enumerate(segments)
                        if segment.name.rsplit(".", 1)[0] == name.rsplit(".", 1)[0]
                    ]
                    if not matching:
                        raise LogStoreError("log_cursor_stale")
                    segments = segments[matching[0] :]
                scanned = 0
                for index, segment in enumerate(segments):
                    offset = int(cast(int, resume["offset"])) if resume is not None and index == 0 else segment.start
                    if not segment.start <= offset <= segment.end:
                        raise LogStoreError("log_cursor_stale")
                    with _read_optional(root, segment.name) as handle:
                        if handle is None or _identity(os.fstat(handle.fileno())) != segment.identity:
                            coverage["unavailable_segments"] = cast(int, coverage["unavailable_segments"]) + 1
                            continue
                        handle.seek(offset)
                        while handle.tell() < segment.end:
                            position = handle.tell()
                            if len(events) >= limit or scanned >= _MAX_SCAN_BYTES or time.monotonic() >= deadline:
                                coverage["scan_limited"] = len(events) < limit
                                next_cursor = self._cursor(
                                    {
                                        "name": segment.name,
                                        "offset": position,
                                        "filters": selected,
                                        "store_id": self._store_id,
                                    }
                                )
                                break
                            line = handle.readline(min(MAX_EVENT_BYTES + 1, segment.end - position))
                            scanned += len(line)
                            if not line.endswith(b"\n"):
                                coverage["truncated_segments"] = cast(int, coverage["truncated_segments"]) + 1
                                coverage["omitted_segment_tails"] = cast(int, coverage["omitted_segment_tails"]) + 1
                                break
                            try:
                                if len(line) > MAX_EVENT_BYTES:
                                    raise EventValidationError
                                record = validate_record(json.loads(line))
                                if record["writer_id"] != segment.header["writer_id"]:
                                    raise EventValidationError
                            except (ValueError, TypeError):
                                coverage["corrupt_records"] = cast(int, coverage["corrupt_records"]) + 1
                                continue
                            if all(
                                (
                                    str(record["timestamp"]) >= value
                                    if key == "since"
                                    else str(record["timestamp"]) <= value
                                    if key == "until"
                                    else record.get(key) == value
                                )
                                for key, value in selected.items()
                            ):
                                events.append(record)
                    if next_cursor is not None:
                        break
        except (OSError, ValueError) as exc:
            if isinstance(exc, LogStoreError):
                raise
            raise LogStoreError from None
        return {"events": events, "next_cursor": next_cursor, "coverage": coverage}


__all__ = ["LogStore", "LogStoreError"]
