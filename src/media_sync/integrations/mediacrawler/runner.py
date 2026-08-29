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
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .bridge import MediaCrawlerRunSpec, RunnerManifest
    from .policies import OutputStats

_PRIVATE_INPUT_ENV = "MEDIA_SYNC_MEDIACRAWLER_PRIVATE_INPUT"

EXIT_CONFIGURATION = 20
EXIT_TIMEOUT = 21
EXIT_OUTPUT_BYTES = 22
EXIT_OUTPUT_ITEMS = 23
EXIT_OUTPUT_FILES = 24
EXIT_OUTPUT_LINE = 25
EXIT_OUTPUT_TREE = 26
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
    }.get(returncode, MediaCrawlerProcessStatus.UPSTREAM_FAILED)


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


def _stop_child(process: subprocess.Popen[bytes], windows_job: _WindowsJob | None) -> int | None:
    """Use hard termination only as a parent fallback after child cleanup failed."""

    if os.name == "nt":
        if windows_job is not None:
            windows_job.close()
        else:
            _taskkill_tree(process)
    else:
        with contextlib.suppress(OSError):
            _signal_process_group(process.pid, signal.SIGTERM)
    try:
        return process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            _taskkill_tree(process)
        else:
            with contextlib.suppress(OSError):
                _signal_process_group(process.pid, int(getattr(signal, "SIGKILL", signal.SIGTERM)))
        try:
            process.kill()
            return process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            return process.poll()


def _close_process_tree(process: subprocess.Popen[bytes], windows_job: _WindowsJob | None) -> None:
    """Remove descendants even when the direct child exited without cleaning them."""

    if os.name == "nt":
        if windows_job is not None:
            windows_job.close()
        elif process.poll() is None:
            _taskkill_tree(process)
        return
    with contextlib.suppress(OSError):
        _signal_process_group(process.pid, signal.SIGTERM)
    time.sleep(0.05)
    with contextlib.suppress(OSError):
        _signal_process_group(process.pid, int(getattr(signal, "SIGKILL", signal.SIGTERM)))


class MediaCrawlerProcessRunner:
    """Launch a prepared child without a shell and enforce parent watchdogs."""

    def run(self, spec: MediaCrawlerRunSpec) -> MediaCrawlerProcessResult:
        account_lock = _AccountFileLock(spec.paths.account_root)
        if not account_lock.acquire():
            return _parent_result(spec, MediaCrawlerProcessStatus.ACCOUNT_BUSY)
        try:
            return self._run_locked(spec)
        finally:
            account_lock.release()

    def _run_locked(self, spec: MediaCrawlerRunSpec) -> MediaCrawlerProcessResult:
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
        try:
            process = subprocess.Popen(
                spec.command,
                cwd=spec.cwd,
                env=child_environment,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=os.name != "nt",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
        except OSError:
            return _parent_result(spec, MediaCrawlerProcessStatus.START_FAILED)
        finally:
            child_environment.pop(PRIVATE_INPUT_ENV, None)

        windows_job = _WindowsJob.attach(process)
        if os.name == "nt" and windows_job is None:
            _taskkill_tree(process)
            with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                process.wait(timeout=2)
            return _parent_result(spec, MediaCrawlerProcessStatus.START_FAILED)

        started = time.monotonic()
        limits = spec.manifest.watchdogs
        last_stats = initial_stats
        successful_returncode: int | None = None
        try:
            while True:
                try:
                    last_stats = inspect_output(spec.paths.output_root, limits)
                except OutputInspectionError as error:
                    returncode = _stop_child(process, windows_job)
                    return _parent_result(
                        spec,
                        _status_for_output_kind(error.kind),
                        returncode=returncode,
                        stats=error.stats,
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
                time.sleep(limits.poll_seconds)
        finally:
            _close_process_tree(process, windows_job)

        # The direct child may exit before a descendant. Seal output only after
        # the entire process tree has been stopped and one final inspection has
        # observed a stable, bounded JSONL tree.
        assert successful_returncode == 0
        time.sleep(min(5.0, max(0.05, limits.poll_seconds)))
        try:
            final_stats = inspect_output(spec.paths.output_root, limits)
        except OutputInspectionError as error:
            return _parent_result(
                spec,
                _status_for_output_kind(error.kind),
                returncode=successful_returncode,
                stats=error.stats,
            )
        try:
            write_completion_receipt(
                spec.manifest,
                final_stats,
                known_secrets=spec.known_secrets,
            )
        except CompletionReceiptError:
            return _parent_result(
                spec,
                MediaCrawlerProcessStatus.COMPLETION_FAILED,
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
    config.HEADLESS = manifest.headless
    config.CDP_HEADLESS = manifest.headless
    config.AUTO_CLOSE_BROWSER = True
    config.CREATOR_MODE = True
    config.XHS_INTERNATIONAL = False
    config.ENABLE_WEIBO_FULL_TEXT = True
    config.DISABLE_SSL_VERIFY = False
    for attribute in CREATOR_CONFIG_ATTRIBUTES.values():
        setattr(config, attribute, [])
    setattr(config, CREATOR_CONFIG_ATTRIBUTES[manifest.platform], [creator_reference])


async def _watch_upstream(upstream_main: Any, manifest: RunnerManifest) -> None:
    from media_sync.integrations.mediacrawler.policies import OutputInspectionError, inspect_output

    limits = manifest.watchdogs
    cleanup_reserve = min(5.0, max(0.05, limits.max_seconds * 0.1))
    run_seconds = max(0.01, limits.max_seconds - cleanup_reserve)
    deadline = time.monotonic() + run_seconds
    task = asyncio.create_task(upstream_main.main())
    try:
        while True:
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
) -> int:
    from media_sync.integrations.mediacrawler.policies import inspect_output

    verified = None
    upstream_main: Any | None = None
    config: Any | None = None
    cleanup_seconds = min(5.0, max(0.05, manifest.watchdogs.max_seconds * 0.1))
    try:
        from media_sync.integrations.mediacrawler.bridge import verify_manifest_checkout

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
            return EXIT_CONFIGURATION

        sys.argv = ["mediacrawler"]
        config = importlib.import_module("config")
        if not _module_belongs_to_checkout(config, verified.root):
            return EXIT_CONFIGURATION
        _configure_upstream(config, manifest, creator_reference)
        creator_reference = ""
        upstream_main = importlib.import_module("main")
        if not _module_belongs_to_checkout(upstream_main, verified.root):
            return EXIT_CONFIGURATION
        config.__dict__["COOKIES"] = cookie or ""
        cookie = None
        await _watch_upstream(upstream_main, manifest)
        return 0
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
    }.get(returncode, "upstream_failed")
    encoded = json.dumps({"status": status}, separators=(",", ":")).encode("ascii") + b"\n"
    with contextlib.suppress(OSError):
        os.write(1, encoded)


def _child_entry(private_payload: str | None) -> int:
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
                returncode = asyncio.run(_execute_child(manifest, creator_reference, cookie))
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
    try:
        return _child_entry(private_input)
    finally:
        private_input = None


if __name__ == "__main__":
    raise SystemExit(_start_child())


__all__ = [
    "MediaCrawlerProcessResult",
    "MediaCrawlerProcessRunner",
    "MediaCrawlerProcessStatus",
]
