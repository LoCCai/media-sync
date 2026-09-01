"""Isolated MediaCrawler child entry point and bounded parent process runner."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import os
import signal
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .bridge import MediaCrawlerRunSpec, RunnerManifest
    from .policies import OutputStats, RunPaths

_PRIVATE_INPUT_ENV = "MEDIA_SYNC_MEDIACRAWLER_PRIVATE_INPUT"
_CONTROL_ENV = "MEDIA_SYNC_MEDIACRAWLER_CONTROL"
_CONTROL_VERSION = "stdin-v1"
_CONTROL_START = b"media-sync-start-v1\n"
_CONTROL_CANCEL = b"media-sync-cancel-v1\n"
_MAX_CONTROL_BYTES = 64
_COOPERATIVE_STOP_SECONDS = 0.5
_TREE_STOP_SECONDS = 5.0
_CLEANUP_SECURITY_SCHEMA_VERSION = 1
_CLEANUP_SECURITY_ROOT = ".cleanup-security-v1"
_CLEANUP_ACCOUNT_BLOCKS = "account-blocks"
_CLEANUP_INCIDENTS = "incidents"
_CLEANUP_INCIDENT_CODE = "mediacrawler_attempt_cleanup_unresolved"

EXIT_CONFIGURATION = 20
EXIT_TIMEOUT = 21
EXIT_OUTPUT_BYTES = 22
EXIT_OUTPUT_ITEMS = 23
EXIT_OUTPUT_FILES = 24
EXIT_OUTPUT_LINE = 25
EXIT_OUTPUT_TREE = 26
EXIT_CANCELLED = 27
EXIT_AUTH_EXPIRED = 28
EXIT_UPSTREAM = 30


class MediaCrawlerProcessStatus(StrEnum):
    """Stable, secret-free parent outcomes."""

    SUCCEEDED = "succeeded"
    START_FAILED = "start_failed"
    CONFIGURATION_FAILED = "configuration_failed"
    UPSTREAM_FAILED = "upstream_failed"
    TIMED_OUT = "timed_out"
    OUTPUT_BYTES_EXCEEDED = "output_bytes_exceeded"
    OUTPUT_ITEMS_EXCEEDED = "output_items_exceeded"
    OUTPUT_FILES_EXCEEDED = "output_files_exceeded"
    OUTPUT_LINE_EXCEEDED = "output_line_exceeded"
    OUTPUT_TREE_INVALID = "output_tree_invalid"
    COMPLETION_FAILED = "completion_failed"
    ACCOUNT_BUSY = "account_busy"
    CANCELLED = "cancelled"
    AUTH_EXPIRED = "auth_expired"


class AttemptCleanupStatus(StrEnum):
    """Closed outcome for one exact unsealed attempt root."""

    ABSENT = "absent"
    REMOVED = "removed"
    QUARANTINED = "quarantined"
    UNRESOLVED = "unresolved"

    @property
    def clean(self) -> bool:
        return self in {AttemptCleanupStatus.ABSENT, AttemptCleanupStatus.REMOVED}

    @property
    def secured(self) -> bool:
        return self is not AttemptCleanupStatus.UNRESOLVED


class AttemptCleanupError(RuntimeError):
    """An unsealed attempt could not be cleanly removed after isolation."""


@dataclass(frozen=True, slots=True)
class _AttemptCleanupScope:
    integration_root: Path
    platform: str
    account_id: UUID
    execution_id: UUID


@dataclass(frozen=True, slots=True)
class MediaCrawlerProcessResult:
    """Bounded result containing no child-controlled text or private inputs."""

    status: MediaCrawlerProcessStatus
    message: str
    returncode: int | None = None
    bytes_written: int = 0
    jsonl_items: int = 0
    files_written: int = 0

    @property
    def succeeded(self) -> bool:
        return self.status is MediaCrawlerProcessStatus.SUCCEEDED


_STATUS_MESSAGES = {
    MediaCrawlerProcessStatus.SUCCEEDED: "MediaCrawler child completed successfully",
    MediaCrawlerProcessStatus.START_FAILED: "MediaCrawler child could not be started",
    MediaCrawlerProcessStatus.CONFIGURATION_FAILED: "MediaCrawler child configuration was rejected",
    MediaCrawlerProcessStatus.UPSTREAM_FAILED: "MediaCrawler child execution failed",
    MediaCrawlerProcessStatus.TIMED_OUT: "MediaCrawler child exceeded the wall-clock limit",
    MediaCrawlerProcessStatus.OUTPUT_BYTES_EXCEEDED: "MediaCrawler child exceeded the output byte limit",
    MediaCrawlerProcessStatus.OUTPUT_ITEMS_EXCEEDED: "MediaCrawler child exceeded the output item limit",
    MediaCrawlerProcessStatus.OUTPUT_FILES_EXCEEDED: "MediaCrawler child exceeded the output file limit",
    MediaCrawlerProcessStatus.OUTPUT_LINE_EXCEEDED: "MediaCrawler child exceeded the JSONL line limit",
    MediaCrawlerProcessStatus.OUTPUT_TREE_INVALID: "MediaCrawler child produced an invalid output tree",
    MediaCrawlerProcessStatus.COMPLETION_FAILED: "MediaCrawler child output could not be sealed safely",
    MediaCrawlerProcessStatus.ACCOUNT_BUSY: "MediaCrawler account profile is already in use",
    MediaCrawlerProcessStatus.CANCELLED: "MediaCrawler child execution was cancelled",
    MediaCrawlerProcessStatus.AUTH_EXPIRED: "MediaCrawler saved session is no longer authenticated",
}


class _AccountFileLock:
    """One non-blocking OS lock serializes each account profile across processes."""

    def __init__(self, account_root: Path) -> None:
        self.path = account_root / ".mediacrawler-run.lock"
        self._descriptor: int | None = None

    def acquire(self) -> bool:
        flags = os.O_RDWR | os.O_CREAT
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            if self.path.is_symlink():
                return False
            descriptor = os.open(self.path, flags, 0o600)
            opened_stat = os.fstat(descriptor)
            if not stat.S_ISREG(opened_stat.st_mode) or opened_stat.st_nlink != 1:
                os.close(descriptor)
                return False
            if opened_stat.st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.__dict__["flock"](
                    descriptor,
                    int(fcntl.__dict__["LOCK_EX"]) | int(fcntl.__dict__["LOCK_NB"]),
                )
        except (OSError, ImportError):
            with contextlib.suppress(OSError):
                os.close(locals().get("descriptor", -1))
            return False
        self._descriptor = descriptor
        return True

    def release(self) -> None:
        descriptor = self._descriptor
        self._descriptor = None
        if descriptor is None:
            return
        with contextlib.suppress(OSError, ImportError):
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.__dict__["flock"](descriptor, int(fcntl.__dict__["LOCK_UN"]))
        with contextlib.suppress(OSError):
            os.close(descriptor)

    @property
    def descriptor(self) -> int:
        descriptor = self._descriptor
        if descriptor is None:
            raise RuntimeError("account lock is not held")
        return descriptor


class _WindowsJob:
    """Kill-on-close Job Object containing the child and its descendants."""

    def __init__(self, handle: int) -> None:
        self._handle = handle

    @classmethod
    def attach(cls, process: subprocess.Popen[bytes]) -> _WindowsJob | None:
        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            class _IoCounters(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_ulonglong),
                    ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong),
                    ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong),
                    ("OtherTransferCount", ctypes.c_ulonglong),
                ]

            class _BasicLimits(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class _ExtendedLimits(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", _BasicLimits),
                    ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            kernel32.SetInformationJobObject.argtypes = (
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
            )
            kernel32.SetInformationJobObject.restype = wintypes.BOOL
            kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
            kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel32.CloseHandle.restype = wintypes.BOOL

            handle = kernel32.CreateJobObjectW(None, None)
            if not handle:
                return None
            limits = _ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = 0x00002000
            configured = kernel32.SetInformationJobObject(
                handle,
                9,
                ctypes.byref(limits),
                ctypes.sizeof(limits),
            )
            process_handle = getattr(process, "_handle", None)
            assigned = bool(
                configured and process_handle is not None and kernel32.AssignProcessToJobObject(handle, process_handle)
            )
            if not assigned:
                kernel32.CloseHandle(handle)
                return None
            return cls(int(handle))
        except (AttributeError, OSError, TypeError, ValueError):
            return None

    @classmethod
    def attach_current_process(cls) -> _WindowsJob | None:
        """Create a child-owned nested Job inherited by future descendants."""

        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.argtypes = ()
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            current_process: Any = type("_CurrentProcess", (), {})()
            current_process._handle = kernel32.GetCurrentProcess()
            return cls.attach(current_process)
        except (AttributeError, OSError, TypeError, ValueError):
            return None

    def terminate(self) -> bool:
        """Terminate all active Job members without first closing the handle."""

        handle = self._handle
        if not handle or os.name != "nt":
            return False
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
            kernel32.TerminateJobObject.restype = wintypes.BOOL
            return bool(kernel32.TerminateJobObject(handle, EXIT_CANCELLED))
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def close(self) -> None:
        handle = self._handle
        self._handle = 0
        if not handle:
            return
        with contextlib.suppress(AttributeError, OSError):
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel32.CloseHandle.restype = wintypes.BOOL
            kernel32.CloseHandle(handle)

    def terminate_and_wait(
        self,
        process: subprocess.Popen[bytes],
        *,
        timeout: float = _TREE_STOP_SECONDS,
    ) -> bool:
        """Terminate every Job member and confirm that the Job became empty."""

        handle = self._handle
        if not handle:
            return process.poll() is not None
        stopped = False
        deadline = time.monotonic() + timeout
        try:
            import ctypes
            from ctypes import wintypes

            class _BasicAccounting(ctypes.Structure):
                _fields_ = [
                    ("TotalUserTime", ctypes.c_longlong),
                    ("TotalKernelTime", ctypes.c_longlong),
                    ("ThisPeriodTotalUserTime", ctypes.c_longlong),
                    ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                    ("TotalPageFaultCount", wintypes.DWORD),
                    ("TotalProcesses", wintypes.DWORD),
                    ("ActiveProcesses", wintypes.DWORD),
                    ("TotalTerminatedProcesses", wintypes.DWORD),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
            kernel32.TerminateJobObject.restype = wintypes.BOOL
            kernel32.QueryInformationJobObject.argtypes = (
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.c_void_p,
            )
            kernel32.QueryInformationJobObject.restype = wintypes.BOOL
            kernel32.TerminateJobObject(handle, 1)
            while time.monotonic() < deadline:
                accounting = _BasicAccounting()
                queried = kernel32.QueryInformationJobObject(
                    handle,
                    1,
                    ctypes.byref(accounting),
                    ctypes.sizeof(accounting),
                    None,
                )
                if queried and accounting.ActiveProcesses == 0:
                    stopped = True
                    break
                time.sleep(0.01)
        except (AttributeError, OSError, TypeError, ValueError):
            stopped = False
        finally:
            # KILL_ON_JOB_CLOSE remains the final fail-safe if a query failed.
            self.close()

        remaining = max(0.0, deadline - time.monotonic())
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            process.wait(timeout=remaining)
        return stopped and process.poll() is not None


def _parent_result(
    spec: MediaCrawlerRunSpec,
    status: MediaCrawlerProcessStatus,
    *,
    returncode: int | None = None,
    stats: OutputStats | None = None,
) -> MediaCrawlerProcessResult:
    from media_sync.security import redact_text

    # Even fixed messages cross the sink redactor with the exact SecretValue
    # instances retained by the prepared spec.
    message = redact_text(_STATUS_MESSAGES[status], known_secrets=spec.known_secrets)
    return MediaCrawlerProcessResult(
        status=status,
        message=message,
        returncode=returncode,
        bytes_written=stats.bytes_written if stats is not None else 0,
        jsonl_items=stats.jsonl_items if stats is not None else 0,
        files_written=stats.files_written if stats is not None else 0,
    )


def _status_for_output_kind(kind: Any) -> MediaCrawlerProcessStatus:
    from .policies import OutputLimitKind

    return {
        OutputLimitKind.BYTES: MediaCrawlerProcessStatus.OUTPUT_BYTES_EXCEEDED,
        OutputLimitKind.ITEMS: MediaCrawlerProcessStatus.OUTPUT_ITEMS_EXCEEDED,
        OutputLimitKind.FILES: MediaCrawlerProcessStatus.OUTPUT_FILES_EXCEEDED,
        OutputLimitKind.LINE_BYTES: MediaCrawlerProcessStatus.OUTPUT_LINE_EXCEEDED,
        OutputLimitKind.TREE: MediaCrawlerProcessStatus.OUTPUT_TREE_INVALID,
    }[kind]


def _status_for_returncode(returncode: int) -> MediaCrawlerProcessStatus:
    return {
        0: MediaCrawlerProcessStatus.SUCCEEDED,
        EXIT_CONFIGURATION: MediaCrawlerProcessStatus.CONFIGURATION_FAILED,
        EXIT_TIMEOUT: MediaCrawlerProcessStatus.TIMED_OUT,
        EXIT_OUTPUT_BYTES: MediaCrawlerProcessStatus.OUTPUT_BYTES_EXCEEDED,
        EXIT_OUTPUT_ITEMS: MediaCrawlerProcessStatus.OUTPUT_ITEMS_EXCEEDED,
        EXIT_OUTPUT_FILES: MediaCrawlerProcessStatus.OUTPUT_FILES_EXCEEDED,
        EXIT_OUTPUT_LINE: MediaCrawlerProcessStatus.OUTPUT_LINE_EXCEEDED,
        EXIT_OUTPUT_TREE: MediaCrawlerProcessStatus.OUTPUT_TREE_INVALID,
        EXIT_CANCELLED: MediaCrawlerProcessStatus.CANCELLED,
        EXIT_AUTH_EXPIRED: MediaCrawlerProcessStatus.AUTH_EXPIRED,
    }.get(returncode, MediaCrawlerProcessStatus.UPSTREAM_FAILED)


def _write_control(process: subprocess.Popen[bytes], token: bytes) -> bool:
    stream = process.stdin
    if stream is None or process.poll() is not None:
        return False
    try:
        stream.write(token)
        stream.flush()
    except (BrokenPipeError, OSError, ValueError):
        return False
    return True


def _close_control(process: subprocess.Popen[bytes]) -> None:
    stream = process.stdin
    if stream is not None:
        with contextlib.suppress(OSError, ValueError):
            stream.close()


def _spawn_supervised_child(
    spec: MediaCrawlerRunSpec,
    child_environment: dict[str, str],
    lock_descriptor: int,
) -> subprocess.Popen[bytes]:
    """Spawn with the account-lock handle inherited until this child exits."""

    if os.name != "nt":
        return subprocess.Popen(
            spec.command,
            cwd=spec.cwd,
            env=child_environment,
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            pass_fds=(lock_descriptor,),
        )

    import msvcrt

    lock_handle = msvcrt.get_osfhandle(lock_descriptor)
    set_handle_inheritable = getattr(os, "set_handle_inheritable", None)
    if not callable(set_handle_inheritable):  # pragma: no cover - supported Windows runtimes expose it
        raise OSError("Windows handle inheritance is unavailable")
    startup_info: Any = subprocess.STARTUPINFO()
    startup_info.lpAttributeList = {"handle_list": [lock_handle]}
    set_handle_inheritable(lock_handle, True)
    try:
        return subprocess.Popen(
            spec.command,
            cwd=spec.cwd,
            env=child_environment,
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
            startupinfo=startup_info,
        )
    finally:
        set_handle_inheritable(lock_handle, False)


def _taskkill_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name != "nt":
        return
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        subprocess.run(
            ("taskkill.exe", "/PID", str(process.pid), "/T", "/F"),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            shell=False,
        )


def _signal_process_group(process_id: int, signal_number: int) -> None:
    killpg = getattr(os, "killpg", None)
    if callable(killpg):
        killpg(process_id, signal_number)


def _process_group_is_alive(process_id: int) -> bool:
    if os.name == "nt":
        return False
    try:
        _signal_process_group(process_id, 0)
    except ProcessLookupError:
        return False
    except (OSError, PermissionError):
        return True
    return True


def _wait_for_process_group_exit(process_id: int, deadline: float) -> bool:
    while _process_group_is_alive(process_id) and time.monotonic() < deadline:
        time.sleep(0.01)
    return not _process_group_is_alive(process_id)


def _stop_child(process: subprocess.Popen[bytes], windows_job: _WindowsJob | None) -> int | None:
    """Request cooperative cancellation, then join the complete process tree."""

    _write_control(process, _CONTROL_CANCEL)
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=_COOPERATIVE_STOP_SECONDS)
    _close_process_tree(process, windows_job)
    return process.poll()


def _close_process_tree(process: subprocess.Popen[bytes], windows_job: _WindowsJob | None) -> bool:
    """Terminate and join direct child plus descendants before releasing profile ownership."""

    try:
        if os.name == "nt":
            if windows_job is not None:
                return windows_job.terminate_and_wait(process)
            _taskkill_tree(process)
            with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                process.wait(timeout=_TREE_STOP_SECONDS)
            return process.poll() is not None

        deadline = time.monotonic() + _TREE_STOP_SECONDS
        if _process_group_is_alive(process.pid):
            with contextlib.suppress(OSError):
                _signal_process_group(process.pid, signal.SIGTERM)
            cooperative_deadline = min(deadline, time.monotonic() + _COOPERATIVE_STOP_SECONDS)
            if not _wait_for_process_group_exit(process.pid, cooperative_deadline):
                with contextlib.suppress(OSError):
                    _signal_process_group(
                        process.pid,
                        int(getattr(signal, "SIGKILL", signal.SIGTERM)),
                    )
                _wait_for_process_group_exit(process.pid, deadline)
        remaining = max(0.0, deadline - time.monotonic())
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            process.wait(timeout=remaining)
        return process.poll() is not None and not _process_group_is_alive(process.pid)
    finally:
        _close_control(process)


def _is_reparse_point(stat_result: os.stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & flag)


def _attempt_cleanup_scope(paths: RunPaths) -> _AttemptCleanupScope | None:
    """Validate the stable, non-secret scope used by cleanup security markers."""

    from media_sync.domain import Platform

    from .policies import RUNNER_MANIFEST_NAME

    try:
        integration_root = paths.integration_root.absolute()
        account_root = paths.account_root.absolute()
        profile_root = paths.profile_root.absolute()
        job_root = paths.job_root.absolute()
        output_root = paths.output_root.absolute()
        manifest_path = paths.manifest_path.absolute()
        account_parts = account_root.relative_to(integration_root / "accounts").parts
        if len(account_parts) != 2:
            return None
        platform = Platform(account_parts[0])
        account_id = UUID(account_parts[1])
        execution_id = UUID(job_root.name)
        if (
            str(account_id) != account_parts[1]
            or str(execution_id) != job_root.name
            or job_root.parent != integration_root / "jobs"
            or output_root != job_root / "output"
            or manifest_path != job_root / RUNNER_MANIFEST_NAME
            or profile_root != account_root / "browser_data" / f"{platform.value}_user_data_dir"
        ):
            return None
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        return None
    return _AttemptCleanupScope(
        integration_root=integration_root,
        platform=platform.value,
        account_id=account_id,
        execution_id=execution_id,
    )


def _require_real_directory(path: Path) -> None:
    directory_stat = os.lstat(path)
    if (
        not stat.S_ISDIR(directory_stat.st_mode)
        or stat.S_ISLNK(directory_stat.st_mode)
        or _is_reparse_point(directory_stat)
        or path.resolve(strict=True) != path
    ):
        raise OSError("cleanup security directory is not a real directory")


def _ensure_private_directory(parent: Path, name: str) -> Path:
    directory = parent / name
    with contextlib.suppress(FileExistsError):
        directory.mkdir(mode=0o700)
    _require_real_directory(directory)
    with contextlib.suppress(OSError):
        directory.chmod(0o700)
    return directory


def _attempt_cleanup_marker_paths(scope: _AttemptCleanupScope) -> tuple[Path, Path]:
    security_root = scope.integration_root / _CLEANUP_SECURITY_ROOT
    account_block = security_root / _CLEANUP_ACCOUNT_BLOCKS / scope.platform / f"{scope.account_id}.json"
    incident = security_root / _CLEANUP_INCIDENTS / f"{scope.execution_id}.json"
    return account_block, incident


def attempt_cleanup_incident_paths(paths: RunPaths) -> tuple[Path, Path]:
    """Return deterministic account-block and per-attempt incident marker paths."""

    scope = _attempt_cleanup_scope(paths)
    if scope is None:
        raise AttemptCleanupError("MediaCrawler cleanup security scope is invalid")
    return _attempt_cleanup_marker_paths(scope)


def _atomic_write_marker(path: Path, payload: bytes) -> None:
    temporary = path.parent / f".{path.name}.{uuid4()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= int(getattr(os, "O_NOFOLLOW", 0))
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        with contextlib.suppress(OSError):
            path.chmod(0o600)
    finally:
        if descriptor is not None:
            with contextlib.suppress(OSError):
                os.close(descriptor)
        with contextlib.suppress(OSError):
            os.unlink(temporary)


def record_attempt_cleanup_incident(paths: RunPaths) -> None:
    """Atomically block one account after an attempt root cannot be isolated.

    Markers live outside the attempt tree and contain only a fixed code plus
    stable UUID/platform scope. Raw paths, exception text, credentials and
    scheduler ownership material are deliberately excluded.
    """

    scope = _attempt_cleanup_scope(paths)
    if scope is None:
        raise AttemptCleanupError("MediaCrawler cleanup security scope is invalid")
    payload = (
        json.dumps(
            {
                "schema_version": _CLEANUP_SECURITY_SCHEMA_VERSION,
                "code": _CLEANUP_INCIDENT_CODE,
                "scope": {
                    "platform": scope.platform,
                    "account_id": str(scope.account_id),
                    "execution_id": str(scope.execution_id),
                },
                "summary": {
                    "attempt_cleanup": AttemptCleanupStatus.UNRESOLVED.value,
                    "account_access": "blocked",
                },
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    account_block, incident = _attempt_cleanup_marker_paths(scope)
    try:
        _require_real_directory(scope.integration_root)
        security_root = _ensure_private_directory(scope.integration_root, _CLEANUP_SECURITY_ROOT)
        blocks_root = _ensure_private_directory(security_root, _CLEANUP_ACCOUNT_BLOCKS)
        platform_root = _ensure_private_directory(blocks_root, scope.platform)
        incidents_root = _ensure_private_directory(security_root, _CLEANUP_INCIDENTS)
        if account_block.parent != platform_root or incident.parent != incidents_root:
            raise OSError("cleanup security marker scope changed")
        # Persist the account block first. If the incident write then fails, a
        # successor still cannot start, and the caller still hard-stops.
        _atomic_write_marker(account_block, payload)
        _atomic_write_marker(incident, payload)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise AttemptCleanupError("MediaCrawler cleanup incident persistence failed") from None


def is_attempt_cleanup_blocked(paths: RunPaths) -> bool:
    """Fail closed when a durable cleanup block exists or cannot be inspected."""

    scope = _attempt_cleanup_scope(paths)
    if scope is None:
        raise AttemptCleanupError("MediaCrawler cleanup security scope is invalid")
    account_block, _incident = _attempt_cleanup_marker_paths(scope)
    try:
        if not os.path.lexists(scope.integration_root):
            return False
        _require_real_directory(scope.integration_root)
        directories = (
            scope.integration_root / _CLEANUP_SECURITY_ROOT,
            scope.integration_root / _CLEANUP_SECURITY_ROOT / _CLEANUP_ACCOUNT_BLOCKS,
            account_block.parent,
        )
        for directory in directories:
            if not os.path.lexists(directory):
                return False
            _require_real_directory(directory)
        try:
            os.lstat(account_block)
        except FileNotFoundError:
            return False
        return True
    except (OSError, RuntimeError, TypeError, ValueError):
        raise AttemptCleanupError("MediaCrawler cleanup account block inspection failed") from None


def _validated_attempt_root(paths: RunPaths) -> Path | None:
    """Return only the exact canonical attempt root described by ``RunPaths``."""

    from .policies import RUNNER_MANIFEST_NAME

    try:
        integration_root = paths.integration_root.absolute()
        account_root = paths.account_root.absolute()
        profile_root = paths.profile_root.absolute()
        job_root = paths.job_root.absolute()
        output_root = paths.output_root.absolute()
        manifest_path = paths.manifest_path.absolute()
        jobs_root = integration_root / "jobs"
        accounts_root = integration_root / "accounts"
        UUID(job_root.name)
        if (
            integration_root.resolve(strict=True) != integration_root
            or jobs_root.resolve(strict=True) != jobs_root
            or job_root.parent != jobs_root
            or output_root != job_root / "output"
            or manifest_path != job_root / RUNNER_MANIFEST_NAME
            or not account_root.is_relative_to(accounts_root)
            or not profile_root.is_relative_to(account_root)
            or job_root.is_relative_to(account_root)
            or account_root.is_relative_to(job_root)
            or profile_root.is_relative_to(job_root)
        ):
            return None
        jobs_stat = os.lstat(jobs_root)
        if not stat.S_ISDIR(jobs_stat.st_mode) or _is_reparse_point(jobs_stat):
            return None
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        return None
    return job_root


def _remove_directory_no_follow(root: Path) -> None:
    """Remove one exact attempt-owned entry without traversing links/reparses."""

    try:
        root_stat = os.lstat(root)
    except FileNotFoundError:
        # A concurrent cleanup of the same deterministic attempt identity is
        # already the desired result.  The caller still verifies that the
        # declared root is absent before reporting a clean disposition.
        return
    if stat.S_ISLNK(root_stat.st_mode) or _is_reparse_point(root_stat):
        try:
            if stat.S_ISDIR(root_stat.st_mode):
                os.rmdir(root)
            else:
                os.unlink(root)
        except FileNotFoundError:
            return
        return
    if not stat.S_ISDIR(root_stat.st_mode):
        try:
            os.unlink(root)
        except FileNotFoundError:
            return
        return
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                path = Path(entry.path)
                _remove_directory_no_follow(path)
        final_stat = os.lstat(root)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISDIR(final_stat.st_mode)
        or stat.S_ISLNK(final_stat.st_mode)
        or _is_reparse_point(final_stat)
        or (final_stat.st_dev, final_stat.st_ino) != (root_stat.st_dev, root_stat.st_ino)
    ):
        raise OSError("attempt cleanup root changed during traversal")
    try:
        os.rmdir(root)
    except FileNotFoundError:
        return


def _cleanup_failed_attempt(spec: MediaCrawlerRunSpec) -> AttemptCleanupStatus:
    """Remove only this owned attempt tree, never following links or reparses."""

    paths = spec.paths
    manifest = spec.manifest
    try:
        if any(
            Path(getattr(manifest, name)).absolute() != expected.absolute()
            for name, expected in (
                ("integration_root", paths.integration_root),
                ("account_root", paths.account_root),
                ("profile_root", paths.profile_root),
                ("job_root", paths.job_root),
                ("output_root", paths.output_root),
            )
        ):
            return AttemptCleanupStatus.UNRESOLVED
    except (AttributeError, OSError, TypeError, ValueError):
        return AttemptCleanupStatus.UNRESOLVED
    return cleanup_attempt_root(paths)


def _quarantine_attempt_root(paths: RunPaths, attempt_root: Path) -> Path:
    quarantine_root = paths.integration_root.absolute() / ".quarantine"
    quarantine_root.mkdir(mode=0o700, exist_ok=True)
    quarantine_stat = os.lstat(quarantine_root)
    if (
        not stat.S_ISDIR(quarantine_stat.st_mode)
        or stat.S_ISLNK(quarantine_stat.st_mode)
        or _is_reparse_point(quarantine_stat)
        or quarantine_root.resolve(strict=True) != quarantine_root
    ):
        raise OSError("attempt quarantine root is not a real directory")
    with contextlib.suppress(OSError):
        quarantine_root.chmod(0o700)
    quarantine_path = quarantine_root / f"{attempt_root.name}.{uuid4()}"
    os.replace(attempt_root, quarantine_path)
    return quarantine_path


def cleanup_attempt_root(paths: RunPaths) -> AttemptCleanupStatus:
    """Remove or isolate one exact unsealed attempt root without following links.

    The caller decides whether an artifact is sealed and should be retained.
    A quarantined tree is no longer visible at its execution identity, but the
    caller must still surface a fixed security outcome instead of the original
    retryable result. ``UNRESOLVED`` means neither removal nor isolation could
    be proven.
    """

    attempt_root = _validated_attempt_root(paths)
    if attempt_root is None:
        return AttemptCleanupStatus.UNRESOLVED
    if not os.path.lexists(attempt_root):
        return AttemptCleanupStatus.ABSENT
    try:
        cleanup_root = _quarantine_attempt_root(paths, attempt_root)
    except OSError:
        try:
            _remove_directory_no_follow(attempt_root)
        except OSError:
            return AttemptCleanupStatus.UNRESOLVED
        return AttemptCleanupStatus.REMOVED if not os.path.lexists(attempt_root) else AttemptCleanupStatus.UNRESOLVED
    try:
        _remove_directory_no_follow(cleanup_root)
    except OSError:
        return AttemptCleanupStatus.QUARANTINED
    return AttemptCleanupStatus.REMOVED if not os.path.lexists(cleanup_root) else AttemptCleanupStatus.QUARANTINED


class MediaCrawlerProcessRunner:
    """Launch a prepared child without a shell and enforce parent watchdogs."""

    def run(
        self,
        spec: MediaCrawlerRunSpec,
        cancellation: threading.Event | None = None,
    ) -> MediaCrawlerProcessResult:
        account_lock = _AccountFileLock(spec.paths.account_root)
        if not account_lock.acquire():
            return _parent_result(spec, MediaCrawlerProcessStatus.ACCOUNT_BUSY)
        try:
            if cancellation is not None and cancellation.is_set():
                result = _parent_result(spec, MediaCrawlerProcessStatus.CANCELLED)
            else:
                result = self._run_locked(spec, cancellation, account_lock.descriptor)
            if not result.succeeded:
                cleanup_status = _cleanup_failed_attempt(spec)
                if cleanup_status is AttemptCleanupStatus.UNRESOLVED:
                    with contextlib.suppress(AttemptCleanupError):
                        record_attempt_cleanup_incident(spec.paths)
                    raise AttemptCleanupError("MediaCrawler attempt cleanup is unresolved")
                if cleanup_status is AttemptCleanupStatus.QUARANTINED:
                    return _parent_result(
                        spec,
                        MediaCrawlerProcessStatus.COMPLETION_FAILED,
                        returncode=result.returncode,
                    )
            return result
        except AttemptCleanupError:
            raise
        except BaseException:
            cleanup_status = _cleanup_failed_attempt(spec)
            if cleanup_status is AttemptCleanupStatus.UNRESOLVED:
                with contextlib.suppress(AttemptCleanupError):
                    record_attempt_cleanup_incident(spec.paths)
                raise AttemptCleanupError("MediaCrawler attempt cleanup failed") from None
            if cleanup_status is AttemptCleanupStatus.QUARANTINED:
                return _parent_result(spec, MediaCrawlerProcessStatus.COMPLETION_FAILED)
            raise
        finally:
            account_lock.release()

    def _run_locked(
        self,
        spec: MediaCrawlerRunSpec,
        cancellation: threading.Event | None,
        lock_descriptor: int,
    ) -> MediaCrawlerProcessResult:
        from .bridge import RUNNER_SCRIPT
        from .policies import PRIVATE_INPUT_ENV, OutputInspectionError, inspect_output
        from .receipt import (
            CompletionReceiptError,
            require_completion_receipt_absent,
            write_completion_receipt,
        )

        expected_command = (
            str(spec.manifest.python_executable),
            "-I",
            "-u",
            "-B",
            str(RUNNER_SCRIPT),
            "--manifest",
            str(spec.paths.manifest_path),
        )
        if (
            spec.command != expected_command
            or spec.cwd != spec.manifest.checkout_root
            or PRIVATE_INPUT_ENV not in spec.environment
        ):
            return _parent_result(spec, MediaCrawlerProcessStatus.CONFIGURATION_FAILED)
        try:
            require_completion_receipt_absent(spec.manifest)
        except CompletionReceiptError:
            return _parent_result(spec, MediaCrawlerProcessStatus.COMPLETION_FAILED)
        try:
            initial_stats = inspect_output(spec.paths.output_root, spec.manifest.watchdogs)
        except OutputInspectionError as error:
            return _parent_result(
                spec,
                _status_for_output_kind(error.kind),
                stats=error.stats,
            )
        if initial_stats != type(initial_stats)():
            return _parent_result(
                spec,
                MediaCrawlerProcessStatus.CONFIGURATION_FAILED,
                stats=initial_stats,
            )

        child_environment = dict(spec.environment)
        child_environment[_CONTROL_ENV] = _CONTROL_VERSION
        if cancellation is not None and cancellation.is_set():
            child_environment.pop(PRIVATE_INPUT_ENV, None)
            child_environment.pop(_CONTROL_ENV, None)
            return _parent_result(spec, MediaCrawlerProcessStatus.CANCELLED)
        try:
            process = _spawn_supervised_child(
                spec,
                child_environment,
                lock_descriptor,
            )
        except OSError:
            return _parent_result(spec, MediaCrawlerProcessStatus.START_FAILED)
        finally:
            child_environment.pop(PRIVATE_INPUT_ENV, None)
            child_environment.pop(_CONTROL_ENV, None)

        windows_job = _WindowsJob.attach(process)
        if os.name == "nt" and windows_job is None:
            _taskkill_tree(process)
            with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                process.wait(timeout=2)
            _close_control(process)
            return _parent_result(spec, MediaCrawlerProcessStatus.START_FAILED)
        if cancellation is not None and cancellation.is_set():
            returncode = _stop_child(process, windows_job)
            return _parent_result(
                spec,
                MediaCrawlerProcessStatus.CANCELLED,
                returncode=returncode,
            )
        if not _write_control(process, _CONTROL_START):
            returncode = _stop_child(process, windows_job)
            return _parent_result(
                spec,
                MediaCrawlerProcessStatus.START_FAILED,
                returncode=returncode,
            )

        started = time.monotonic()
        limits = spec.manifest.watchdogs
        last_stats = initial_stats
        successful_returncode: int | None = None
        try:
            while True:
                if cancellation is not None and cancellation.is_set():
                    returncode = _stop_child(process, windows_job)
                    return _parent_result(
                        spec,
                        MediaCrawlerProcessStatus.CANCELLED,
                        returncode=returncode,
                        stats=last_stats,
                    )
                try:
                    last_stats = inspect_output(spec.paths.output_root, limits)
                except OutputInspectionError as error:
                    returncode = _stop_child(process, windows_job)
                    if cancellation is not None and cancellation.is_set():
                        return _parent_result(
                            spec,
                            MediaCrawlerProcessStatus.CANCELLED,
                            returncode=returncode,
                            stats=error.stats,
                        )
                    return _parent_result(
                        spec,
                        _status_for_output_kind(error.kind),
                        returncode=returncode,
                        stats=error.stats,
                    )

                if cancellation is not None and cancellation.is_set():
                    returncode = _stop_child(process, windows_job)
                    return _parent_result(
                        spec,
                        MediaCrawlerProcessStatus.CANCELLED,
                        returncode=returncode,
                        stats=last_stats,
                    )
                returncode = process.poll()
                if returncode is not None:
                    if returncode == 0:
                        successful_returncode = returncode
                        break
                    return _parent_result(
                        spec,
                        _status_for_returncode(returncode),
                        returncode=returncode,
                        stats=last_stats,
                    )
                if time.monotonic() - started >= limits.max_seconds:
                    returncode = _stop_child(process, windows_job)
                    return _parent_result(
                        spec,
                        MediaCrawlerProcessStatus.TIMED_OUT,
                        returncode=returncode,
                        stats=last_stats,
                    )
                if cancellation is None:
                    time.sleep(limits.poll_seconds)
                elif cancellation.wait(limits.poll_seconds):
                    continue
        finally:
            _close_process_tree(process, windows_job)

        # The direct child may exit before a descendant. Seal output only after
        # the entire process tree has been stopped and one final inspection has
        # observed a stable, bounded JSONL tree.
        assert successful_returncode == 0
        if cancellation is not None and cancellation.is_set():
            return _parent_result(
                spec,
                MediaCrawlerProcessStatus.CANCELLED,
                returncode=successful_returncode,
                stats=last_stats,
            )
        settle_seconds = min(5.0, max(0.05, limits.poll_seconds))
        if cancellation is None:
            time.sleep(settle_seconds)
        elif cancellation.wait(settle_seconds):
            return _parent_result(
                spec,
                MediaCrawlerProcessStatus.CANCELLED,
                returncode=successful_returncode,
                stats=last_stats,
            )
        try:
            final_stats = inspect_output(spec.paths.output_root, limits)
        except OutputInspectionError as error:
            if cancellation is not None and cancellation.is_set():
                return _parent_result(
                    spec,
                    MediaCrawlerProcessStatus.CANCELLED,
                    returncode=successful_returncode,
                    stats=error.stats,
                )
            return _parent_result(
                spec,
                _status_for_output_kind(error.kind),
                returncode=successful_returncode,
                stats=error.stats,
            )
        if cancellation is not None and cancellation.is_set():
            return _parent_result(
                spec,
                MediaCrawlerProcessStatus.CANCELLED,
                returncode=successful_returncode,
                stats=final_stats,
            )
        try:
            write_completion_receipt(
                spec.manifest,
                final_stats,
                known_secrets=spec.known_secrets,
            )
        except CompletionReceiptError:
            if cancellation is not None and cancellation.is_set():
                return _parent_result(
                    spec,
                    MediaCrawlerProcessStatus.CANCELLED,
                    returncode=successful_returncode,
                    stats=final_stats,
                )
            return _parent_result(
                spec,
                MediaCrawlerProcessStatus.COMPLETION_FAILED,
                returncode=successful_returncode,
                stats=final_stats,
            )
        if cancellation is not None and cancellation.is_set():
            return _parent_result(
                spec,
                MediaCrawlerProcessStatus.CANCELLED,
                returncode=successful_returncode,
                stats=final_stats,
            )
        return _parent_result(
            spec,
            MediaCrawlerProcessStatus.SUCCEEDED,
            returncode=successful_returncode,
            stats=final_stats,
        )


class _ChildWatchdogError(RuntimeError):
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        super().__init__("MediaCrawler child watchdog stopped execution")


class _ChildCancelledError(RuntimeError):
    """The one-way parent control channel requested a bounded child stop."""


def _returncode_for_output_kind(kind: Any) -> int:
    from media_sync.integrations.mediacrawler.policies import OutputLimitKind

    return {
        OutputLimitKind.BYTES: EXIT_OUTPUT_BYTES,
        OutputLimitKind.ITEMS: EXIT_OUTPUT_ITEMS,
        OutputLimitKind.FILES: EXIT_OUTPUT_FILES,
        OutputLimitKind.LINE_BYTES: EXIT_OUTPUT_LINE,
        OutputLimitKind.TREE: EXIT_OUTPUT_TREE,
    }[kind]


@contextlib.contextmanager
def _silenced_upstream() -> Iterator[None]:
    """Suppress Python and file-descriptor writes until fixed child status emission."""

    stdout_copy = os.dup(1)
    stderr_copy = os.dup(2)
    with open(os.devnull, "w", encoding="utf-8") as sink:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                yield
        finally:
            with contextlib.suppress(OSError):
                sink.flush()
            os.dup2(stdout_copy, 1)
            os.dup2(stderr_copy, 2)
            os.close(stdout_copy)
            os.close(stderr_copy)


def _module_belongs_to_checkout(module: Any, checkout: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        return False
    try:
        return Path(module_file).resolve().is_relative_to(checkout)
    except OSError:
        return False


def _configure_upstream(config: Any, manifest: RunnerManifest, creator_reference: str) -> None:
    from media_sync.integrations.mediacrawler.policies import (
        CREATOR_CONFIG_ATTRIBUTES,
        require_confined,
        upstream_login_type,
    )

    profile_parent = require_confined(manifest.account_root, manifest.profile_root.parent)
    profile_parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        profile_parent.chmod(0o700)
    profile_template = f"{str(profile_parent).replace('%', '%%')}{os.sep}%s_user_data_dir"
    resolved_upstream_profile = Path(
        os.path.join(
            os.getcwd(),
            "browser_data",
            profile_template % manifest.platform.value,
        )
    ).resolve()
    if resolved_upstream_profile != manifest.profile_root:
        raise RuntimeError("profile path mismatch")

    config.PLATFORM = manifest.platform.value
    config.LOGIN_TYPE = upstream_login_type(manifest.login_method)
    config.CRAWLER_TYPE = "creator"
    config.START_PAGE = 1
    config.COOKIES = ""
    config.SAVE_DATA_PATH = str(manifest.output_root)
    config.USER_DATA_DIR = profile_template
    config.CRAWLER_MAX_NOTES_COUNT = manifest.max_items
    config.SAVE_DATA_OPTION = "jsonl"
    config.ENABLE_CDP_MODE = False
    config.CDP_CONNECT_EXISTING = False
    config.SAVE_LOGIN_STATE = True
    config.ENABLE_GET_COMMENTS = False
    config.ENABLE_GET_SUB_COMMENTS = False
    config.ENABLE_GET_MEIDAS = False
    config.ENABLE_GET_MEDIAS = False
    config.ENABLE_GET_WORDCLOUD = False
    config.ENABLE_IP_PROXY = False
    config.STATIC_PROXY_URL = ""
    config.MAX_CONCURRENCY_NUM = 1
    if manifest.request_delay_seconds is None:
        raise RuntimeError("legacy manifests are recovery-only")
    config.CRAWLER_MAX_SLEEP_SEC = manifest.request_delay_seconds
    # Saved sessions are background-only.  Even a subscription that formerly
    # requested a headed browser cannot turn expiry into an interactive flow.
    headless = True if manifest.login_method.value == "saved_session" else manifest.headless
    config.HEADLESS = headless
    config.CDP_HEADLESS = headless
    config.AUTO_CLOSE_BROWSER = True
    config.CREATOR_MODE = True
    config.XHS_INTERNATIONAL = False
    config.ENABLE_WEIBO_FULL_TEXT = True
    config.DISABLE_SSL_VERIFY = False
    for attribute in CREATOR_CONFIG_ATTRIBUTES.values():
        setattr(config, attribute, [])
    setattr(config, CREATOR_CONFIG_ATTRIBUTES[manifest.platform], [creator_reference])


async def _watch_upstream(
    upstream_main: Any,
    manifest: RunnerManifest,
    cancellation: threading.Event | None,
) -> None:
    from media_sync.integrations.mediacrawler.policies import OutputInspectionError, inspect_output

    limits = manifest.watchdogs
    cleanup_reserve = min(5.0, max(0.05, limits.max_seconds * 0.1))
    run_seconds = max(0.01, limits.max_seconds - cleanup_reserve)
    deadline = time.monotonic() + run_seconds

    async def guarded_main() -> None:
        try:
            if manifest.login_method.value == "saved_session":
                from media_sync.integrations.mediacrawler.login_runner import (
                    fence_saved_session_qr_fallback,
                )

                with fence_saved_session_qr_fallback(manifest.platform):
                    await upstream_main.main()
            else:
                await upstream_main.main()
        except SystemExit as error:
            # Upstream login paths may use SystemExit(0) for failure.  Convert
            # it inside the task so asyncio cannot turn it into child success.
            raise RuntimeError("upstream exited without a successful result") from error

    task = asyncio.create_task(guarded_main())
    try:
        while True:
            if cancellation is not None and cancellation.is_set():
                raise _ChildCancelledError
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _ChildWatchdogError(EXIT_TIMEOUT)
            done, _pending = await asyncio.wait(
                {task},
                timeout=min(limits.poll_seconds, remaining),
            )
            try:
                inspect_output(manifest.output_root, limits)
            except OutputInspectionError as error:
                raise _ChildWatchdogError(_returncode_for_output_kind(error.kind)) from error
            if task in done:
                await task
                return
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(task, timeout=cleanup_reserve)


async def _execute_child(
    manifest: RunnerManifest,
    creator_reference: str,
    cookie: str | None,
    cancellation: threading.Event | None,
) -> int:
    from media_sync.integrations.mediacrawler.policies import inspect_output

    verified = None
    upstream_main: Any | None = None
    config: Any | None = None
    cleanup_seconds = min(5.0, max(0.05, manifest.watchdogs.max_seconds * 0.1))
    try:
        from media_sync.integrations.mediacrawler.bridge import verify_manifest_checkout

        if cancellation is not None and cancellation.is_set():
            return EXIT_CANCELLED
        if manifest.request_delay_seconds is None:
            return EXIT_CONFIGURATION
        verified = verify_manifest_checkout(manifest)
        if Path(sys.executable).resolve() != manifest.python_executable:
            return EXIT_CONFIGURATION
        os.chdir(verified.root)
        if str(verified.root) not in sys.path:
            sys.path.insert(0, str(verified.root))
        importlib.invalidate_caches()
        if "config" in sys.modules or "main" in sys.modules:
            return EXIT_CONFIGURATION
        initial_stats = inspect_output(manifest.output_root, manifest.watchdogs)
        if initial_stats != type(initial_stats)():
            return EXIT_CONFIGURATION
        if manifest.login_method.value == "saved_session" and (
            not manifest.profile_root.is_dir() or not any(manifest.profile_root.iterdir())
        ):
            return EXIT_AUTH_EXPIRED

        sys.argv = ["mediacrawler"]
        config = importlib.import_module("config")
        if not _module_belongs_to_checkout(config, verified.root):
            return EXIT_CONFIGURATION
        _configure_upstream(config, manifest, creator_reference)
        creator_reference = ""
        upstream_main = importlib.import_module("main")
        if not _module_belongs_to_checkout(upstream_main, verified.root):
            return EXIT_CONFIGURATION
        if manifest.platform.value == "wb":
            from media_sync.integrations.mediacrawler.weibo_media import (
                install_weibo_media_capture,
            )

            install_weibo_media_capture(verified.root)
        elif manifest.platform.value == "tieba":
            from media_sync.integrations.mediacrawler.tieba_media import (
                install_tieba_media_capture,
            )

            install_tieba_media_capture(
                verified.root,
                creator_max_items=manifest.max_items,
            )
        elif manifest.platform.value == "zhihu":
            from media_sync.integrations.mediacrawler.zhihu_media import (
                install_zhihu_media_capture,
            )

            install_zhihu_media_capture(
                verified.root,
                creator_max_items=manifest.max_items,
            )
        config.__dict__["COOKIES"] = cookie or ""
        cookie = None
        if cancellation is not None and cancellation.is_set():
            return EXIT_CANCELLED
        try:
            await _watch_upstream(upstream_main, manifest, cancellation)
        except (_ChildCancelledError, _ChildWatchdogError):
            raise
        except Exception as error:
            if manifest.login_method.value == "saved_session":
                from media_sync.integrations.mediacrawler.login_runner import (
                    SavedSessionQrFallbackBlocked,
                )

                if isinstance(error, SavedSessionQrFallbackBlocked):
                    return EXIT_AUTH_EXPIRED
            raise
        return 0
    except _ChildCancelledError:
        return EXIT_CANCELLED
    except _ChildWatchdogError as error:
        return error.returncode
    except Exception:
        return EXIT_UPSTREAM
    finally:
        if config is not None:
            config.__dict__["COOKIES"] = ""
        cleanup = getattr(upstream_main, "async_cleanup", None)
        if callable(cleanup):
            with contextlib.suppress(asyncio.TimeoutError, Exception):
                await asyncio.wait_for(cleanup(), timeout=cleanup_seconds)


def _emit_fixed_status(returncode: int) -> None:
    status = {
        0: "succeeded",
        EXIT_CONFIGURATION: "configuration_failed",
        EXIT_TIMEOUT: "timed_out",
        EXIT_OUTPUT_BYTES: "output_bytes_exceeded",
        EXIT_OUTPUT_ITEMS: "output_items_exceeded",
        EXIT_OUTPUT_FILES: "output_files_exceeded",
        EXIT_OUTPUT_LINE: "output_line_exceeded",
        EXIT_OUTPUT_TREE: "output_tree_invalid",
        EXIT_CANCELLED: "cancelled",
        EXIT_AUTH_EXPIRED: "auth_expired",
    }.get(returncode, "upstream_failed")
    encoded = json.dumps({"status": status}, separators=(",", ":")).encode("ascii") + b"\n"
    with contextlib.suppress(OSError):
        os.write(1, encoded)


def _read_control_chunk(maximum: int) -> bytes | None:
    """Read at most ``maximum`` bytes without involving buffered stdin."""

    if type(maximum) is not int or maximum < 1:
        raise ValueError("control read maximum must be a positive integer")
    if os.name != "nt":
        try:
            value = os.read(0, maximum)
        except OSError:
            return None
        return value or None

    # A blocking ``os.read(0, ...)`` holds the Windows CRT descriptor lock and
    # deadlocks any concurrent ``subprocess`` spawn that needs to duplicate the
    # standard handles. ReadFile operates on the underlying handle directly.
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.PeekNamedPipe.argtypes = (
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        )
        kernel32.PeekNamedPipe.restype = wintypes.BOOL
        kernel32.ReadFile.argtypes = (
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        )
        kernel32.ReadFile.restype = wintypes.BOOL
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(0))
        available = wintypes.DWORD()
        while True:
            peeked = kernel32.PeekNamedPipe(
                handle,
                None,
                0,
                None,
                ctypes.byref(available),
                None,
            )
            if not peeked:
                return None
            if available.value:
                break
            time.sleep(0.02)
        requested = min(maximum, int(available.value))
        buffer = ctypes.create_string_buffer(requested)
        bytes_read = wintypes.DWORD()
        succeeded = kernel32.ReadFile(
            handle,
            buffer,
            requested,
            ctypes.byref(bytes_read),
            None,
        )
        if not succeeded or not 0 < bytes_read.value <= requested:
            return None
        return bytes(buffer.raw[: bytes_read.value])
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _read_control_byte() -> bytes | None:
    return _read_control_chunk(1)


def _read_control_message() -> bytes | None:
    message = bytearray()
    while len(message) < _MAX_CONTROL_BYTES:
        chunk = _read_control_byte()
        if chunk is None:
            return None
        message.extend(chunk)
        if chunk == b"\n":
            return bytes(message)
    return None


def _watch_parent_control(
    cancellation: threading.Event,
    parent_lost: threading.Event,
    windows_job: _WindowsJob | None,
    result_complete: threading.Event | None = None,
) -> None:
    message = _read_control_message()
    cancellation.set()
    if message == _CONTROL_CANCEL:
        return
    parent_lost.set()
    if os.name == "nt":
        # The child-owned nested Job is independent from the parent Job and
        # contains descendants created after the start handshake.
        if windows_job is not None and windows_job.terminate():
            time.sleep(_TREE_STOP_SECONDS)
            os._exit(EXIT_CANCELLED)
        # Taskkill remains a fail-safe for hosts that reject nested Jobs.
        with contextlib.suppress(OSError):
            subprocess.Popen(
                ("taskkill.exe", "/PID", str(os.getpid()), "/T", "/F"),
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        # Keep the inherited profile lock alive until taskkill closes the tree.
        time.sleep(_TREE_STOP_SECONDS)
        os._exit(EXIT_CANCELLED)
    get_process_group = getattr(os, "getpgrp", None)
    if not callable(get_process_group):
        return
    process_group = int(get_process_group())
    if process_group != os.getpid():
        # Never signal an ambient caller's process group. The production parent
        # always starts this child as a new session/group leader.
        return
    if result_complete is not None and result_complete.is_set():
        # A result guardian has already closed its result pipe, so no upstream
        # cleanup remains to be given a cooperative interval.  Killing the
        # complete owned group in one syscall closes the parent-death window
        # without first allowing the guardian (and its inherited lock) to exit.
        with contextlib.suppress(OSError):
            _signal_process_group(
                process_group,
                int(getattr(signal, "SIGKILL", signal.SIGTERM)),
            )
        return
    with contextlib.suppress(OSError):
        _signal_process_group(process_group, signal.SIGTERM)
    time.sleep(_COOPERATIVE_STOP_SECONDS)
    with contextlib.suppress(OSError):
        _signal_process_group(
            process_group,
            int(getattr(signal, "SIGKILL", signal.SIGTERM)),
        )


def _child_entry(
    private_payload: str | None,
    cancellation: threading.Event | None = None,
) -> int:
    """Load media-sync only after the private environment envelope was popped."""

    source_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(source_root))
    try:
        from media_sync.integrations.mediacrawler.bridge import PrivateRunnerInputs, RunnerManifest
        from media_sync.integrations.mediacrawler.policies import PRIVATE_INPUT_ENV

        if PRIVATE_INPUT_ENV != _PRIVATE_INPUT_ENV or len(sys.argv) != 3 or sys.argv[1] != "--manifest":
            returncode = EXIT_CONFIGURATION
        else:
            manifest = RunnerManifest.load(Path(sys.argv[2]))
            private_inputs = PrivateRunnerInputs.load(private_payload, manifest)
            del private_payload
            creator_reference = private_inputs.creator_reference
            cookie = private_inputs.cookie
            del private_inputs
            with _silenced_upstream():
                returncode = asyncio.run(
                    _execute_child(
                        manifest,
                        creator_reference,
                        cookie,
                        cancellation,
                    )
                )
            creator_reference = ""
            cookie = None
    except Exception:
        returncode = EXIT_CONFIGURATION
    _emit_fixed_status(returncode)
    return returncode


def _start_child() -> int:
    # This is deliberately the first non-stdlib runtime action. The full private
    # input disappears before argv/manifest parsing or any media-sync/upstream import.
    private_input = os.environ.pop(_PRIVATE_INPUT_ENV, None)
    control_version = os.environ.pop(_CONTROL_ENV, None)
    cancellation: threading.Event | None = None
    parent_lost: threading.Event | None = None
    control_thread: threading.Thread | None = None
    child_windows_job: _WindowsJob | None = None
    previous_sigterm: Any | None = None
    try:
        if control_version is not None:
            if control_version != _CONTROL_VERSION or _read_control_message() != _CONTROL_START:
                _emit_fixed_status(EXIT_CONFIGURATION)
                return EXIT_CONFIGURATION
            cancellation = threading.Event()
            parent_lost = threading.Event()

            if os.name == "nt":
                child_windows_job = _WindowsJob.attach_current_process()
                if child_windows_job is None:
                    _emit_fixed_status(EXIT_CONFIGURATION)
                    return EXIT_CONFIGURATION

            get_process_group = getattr(os, "getpgrp", None)
            if os.name != "nt" and callable(get_process_group) and int(get_process_group()) == os.getpid():
                previous_sigterm = signal.getsignal(signal.SIGTERM)

                def request_cancellation(_number: int, _frame: Any) -> None:
                    assert cancellation is not None
                    cancellation.set()

                signal.signal(signal.SIGTERM, request_cancellation)

            control_thread = threading.Thread(
                target=_watch_parent_control,
                args=(cancellation, parent_lost, child_windows_job),
                name="media-sync-parent-control",
                daemon=True,
            )
            control_thread.start()
        return _child_entry(private_input, cancellation)
    finally:
        private_input = None
        if parent_lost is not None and parent_lost.is_set() and control_thread is not None:
            control_thread.join(timeout=_COOPERATIVE_STOP_SECONDS + 1.0)
        if previous_sigterm is not None:
            with contextlib.suppress(ValueError):
                signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    raise SystemExit(_start_child())


__all__ = [
    "AttemptCleanupError",
    "AttemptCleanupStatus",
    "MediaCrawlerProcessResult",
    "MediaCrawlerProcessRunner",
    "MediaCrawlerProcessStatus",
    "attempt_cleanup_incident_paths",
    "cleanup_attempt_root",
    "is_attempt_cleanup_blocked",
    "record_attempt_cleanup_incident",
]
