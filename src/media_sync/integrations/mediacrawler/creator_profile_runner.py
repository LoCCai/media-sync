"""One exact supported creator profile, isolated from content and storage.

A trusted guardian owns verification and the upstream-runtime child in one
process tree. The parent owns one execution deadline and retains the shared
account lock until the complete tree has been joined.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import math
import os
import re
import signal
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID, uuid4

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    # Platform modules import the canonical name. Script-mode children must
    # share these exact DTO/exception classes, not load a second module copy.
    sys.modules["media_sync.integrations.mediacrawler.creator_profile_runner"] = sys.modules[__name__]

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler.browser_environment import browser_child_environment
from media_sync.integrations.mediacrawler.checkout import (
    normalize_python_executable,
    verify_mediacrawler_checkout,
    verify_mediacrawler_python,
)
from media_sync.integrations.mediacrawler.cookie_login import cookie_pairs, parse_cookie_header
from media_sync.integrations.mediacrawler.creator_profile_identity import (
    CREATOR_PROFILE_PLATFORMS,
    profile_identifier,
    validate_creator_profile_id,
)
from media_sync.integrations.mediacrawler.login_runner import (
    _guard_completed_login_tree,
    _profile_is_present,
    _silenced_upstream,
    _spawn_login_child,
    fence_saved_session_qr_fallback,
)
from media_sync.integrations.mediacrawler.policies import CREATOR_CONFIG_ATTRIBUTES, RunPaths, build_run_paths
from media_sync.integrations.mediacrawler.runner import (
    _CONTROL_ENV,
    _CONTROL_START,
    _CONTROL_VERSION,
    _AccountFileLock,
    _close_process_tree,
    _read_control_chunk,
    _read_control_message,
    _watch_parent_control,
    _WindowsJob,
    is_attempt_cleanup_blocked,
    record_attempt_cleanup_incident,
)
from media_sync.security.secrets import SecretValue

CREATOR_PROFILE_SCHEMA_VERSION = 1
MAX_PROFILE_REQUEST_BYTES = 64 * 1024
MAX_PROFILE_RESULT_BYTES = 16 * 1024
MAX_PROFILE_API_BYTES = 128 * 1024
MAX_PROFILE_EXECUTION_SECONDS = 45.0
MAX_PROFILE_CLEANUP_SECONDS = 15.0
_UID = re.compile(r"[1-9][0-9]{0,19}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_API_HOST = "api.bilibili.com"
_NAV_PATH = "/x/web-interface/nav"
_PROFILE_PATH = "/x/space/wbi/acc/info"
_WB_ORIGIN = "https://m.weibo.cn"
_WB_CONFIG_PATH = "/api/config"
_WB_PROFILE_PATH = "/api/container/getIndex"
_SUPPORTED_PLATFORMS = CREATOR_PROFILE_PLATFORMS
_RETAINED_LOCKS: list[_AccountFileLock] = []


class MediaCrawlerCreatorProfileStatus(StrEnum):
    SUCCEEDED = "succeeded"
    AUTH_EXPIRED = "auth_expired"
    ACCOUNT_BUSY = "account_busy"
    UNSUPPORTED = "unsupported"
    CONFIGURATION_INVALID = "configuration_invalid"
    BROWSER_LAUNCH_FAILED = "browser_launch_failed"
    TEMPORARY = "temporary"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    RESULT_INVALID = "result_invalid"
    CLEANUP_FAILED = "cleanup_failed"


def _uid(value: object) -> str:
    if type(value) is not str or _UID.fullmatch(value) is None or int(value) > 2**64 - 1:
        raise ValueError("creator_profile_identity_invalid")
    return value


def _text(value: object, maximum: int) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError("creator_profile_result_invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("creator_profile_result_invalid")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValueError("creator_profile_result_invalid") from None
    return value.strip()


@dataclass(frozen=True, slots=True)
class MediaCrawlerCreatorProfileRequest:
    account_id: UUID
    platform: Platform
    creator_remote_id: str
    request_id: UUID
    timeout_seconds: float = MAX_PROFILE_EXECUTION_SECONDS
    poll_seconds: float = 0.05
    cookie: SecretValue | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, UUID) or not isinstance(self.request_id, UUID):
            raise ValueError("creator_profile_identity_invalid")
        object.__setattr__(self, "platform", Platform(self.platform))
        if self.platform in _SUPPORTED_PLATFORMS:
            validate_creator_profile_id(self.platform, self.creator_remote_id)
        else:
            _uid(self.creator_remote_id)
        if self.cookie is not None:
            if not isinstance(self.cookie, SecretValue):
                raise ValueError("creator_profile_identity_invalid")
            object.__setattr__(self, "cookie", parse_cookie_header(self.cookie.reveal()))
        for value in (self.timeout_seconds, self.poll_seconds):
            if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                raise ValueError("creator_profile_budget_invalid")
        if self.timeout_seconds > MAX_PROFILE_EXECUTION_SECONDS or self.poll_seconds >= self.timeout_seconds:
            raise ValueError("creator_profile_budget_invalid")
        if self.poll_seconds > 0.25:
            raise ValueError("creator_profile_budget_invalid")


@dataclass(frozen=True, slots=True)
class MediaCrawlerCreatorProfile:
    remote_id: str
    display_name: str = field(repr=False)
    avatar_url: str | None = field(repr=False)

    def __post_init__(self) -> None:
        profile_identifier(self.remote_id)
        object.__setattr__(self, "display_name", _text(self.display_name, 512))
        if self.avatar_url is not None:
            object.__setattr__(self, "avatar_url", _text(self.avatar_url, 2048))


@dataclass(frozen=True, slots=True)
class MediaCrawlerCreatorProfileResult:
    status: MediaCrawlerCreatorProfileStatus
    account_id: UUID
    platform: Platform
    creator_remote_id: str
    request_id: UUID
    upstream_sha: str | None = None
    profile: MediaCrawlerCreatorProfile | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", MediaCrawlerCreatorProfileStatus(self.status))
        if not isinstance(self.account_id, UUID) or not isinstance(self.request_id, UUID):
            raise ValueError("creator_profile_identity_invalid")
        object.__setattr__(self, "platform", Platform(self.platform))
        if self.platform in _SUPPORTED_PLATFORMS:
            validate_creator_profile_id(self.platform, self.creator_remote_id)
        else:
            _uid(self.creator_remote_id)
        if self.upstream_sha is not None and (
            type(self.upstream_sha) is not str or _SHA.fullmatch(self.upstream_sha) is None
        ):
            raise ValueError("creator_profile_result_invalid")
        if self.status is MediaCrawlerCreatorProfileStatus.SUCCEEDED:
            if (
                self.platform not in _SUPPORTED_PLATFORMS
                or self.upstream_sha is None
                or not isinstance(self.profile, MediaCrawlerCreatorProfile)
                or self.profile.remote_id != self.creator_remote_id
            ):
                raise ValueError("creator_profile_result_invalid")
        elif self.profile is not None:
            raise ValueError("creator_profile_result_invalid")


class MediaCrawlerCreatorProfileRunner(Protocol):
    def run(
        self, request: MediaCrawlerCreatorProfileRequest, *, cancellation: threading.Event | None = None
    ) -> MediaCrawlerCreatorProfileResult: ...


def _result(
    request: MediaCrawlerCreatorProfileRequest,
    status: MediaCrawlerCreatorProfileStatus,
    sha: str | None = None,
    profile: MediaCrawlerCreatorProfile | None = None,
) -> MediaCrawlerCreatorProfileResult:
    return MediaCrawlerCreatorProfileResult(
        status, request.account_id, request.platform, request.creator_remote_id, request.request_id, sha, profile
    )


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("creator_profile_result_invalid")
        result[key] = value
    return result


def _json(payload: bytes, maximum: int) -> dict[str, Any]:
    if not payload or len(payload) > maximum:
        raise ValueError("creator_profile_frame_invalid")
    raw = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object)
    if type(raw) is not dict:
        raise ValueError("creator_profile_frame_invalid")
    return raw


def _encode(raw: Mapping[str, object], maximum: int) -> bytes:
    payload = json.dumps(raw, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if not 0 < len(payload) <= maximum:
        raise ValueError("creator_profile_frame_invalid")
    return len(payload).to_bytes(4, "big") + payload


def _result_frame(result: MediaCrawlerCreatorProfileResult) -> bytes:
    return _encode(
        {
            "schema_version": CREATOR_PROFILE_SCHEMA_VERSION,
            "status": result.status.value,
            "account_id": str(result.account_id),
            "platform": result.platform.value,
            "creator_remote_id": result.creator_remote_id,
            "request_id": str(result.request_id),
            "upstream_sha": result.upstream_sha,
            "profile": None
            if result.profile is None
            else {
                "remote_id": result.profile.remote_id,
                "display_name": result.profile.display_name,
                "avatar_url": result.profile.avatar_url,
            },
        },
        MAX_PROFILE_RESULT_BYTES,
    )


def _parse_result(payload: bytes, request: MediaCrawlerCreatorProfileRequest) -> MediaCrawlerCreatorProfileResult:
    raw = _json(payload, MAX_PROFILE_RESULT_BYTES)
    if (
        set(raw)
        != {
            "schema_version",
            "status",
            "account_id",
            "platform",
            "creator_remote_id",
            "request_id",
            "upstream_sha",
            "profile",
        }
        or type(raw["schema_version"]) is not int
        or raw["schema_version"] != CREATOR_PROFILE_SCHEMA_VERSION
    ):
        raise ValueError("creator_profile_frame_invalid")
    if (raw["account_id"], raw["platform"], raw["creator_remote_id"], raw["request_id"]) != (
        str(request.account_id),
        request.platform.value,
        request.creator_remote_id,
        str(request.request_id),
    ):
        raise ValueError("creator_profile_identity_invalid")
    profile = raw["profile"]
    if profile is not None:
        if type(profile) is not dict or set(profile) != {"remote_id", "display_name", "avatar_url"}:
            raise ValueError("creator_profile_frame_invalid")
        profile = MediaCrawlerCreatorProfile(**profile)
    return _result(request, MediaCrawlerCreatorProfileStatus(raw["status"]), raw["upstream_sha"], profile)


def _read_stream_frame(stream: Any, maximum: int) -> bytes:
    prefix = stream.read(4)
    if len(prefix) != 4:
        raise ValueError("creator_profile_frame_invalid")
    length = int.from_bytes(prefix, "big")
    if not 0 < length <= maximum:
        raise ValueError("creator_profile_frame_invalid")
    payload = stream.read(length)
    if len(payload) != length:
        raise ValueError("creator_profile_frame_invalid")
    return bytes(payload)


def _read_control_frame() -> bytes:
    def exact(size: int) -> bytes:
        value = bytearray()
        while len(value) < size:
            part = _read_control_chunk(size - len(value))
            if part is None:
                raise ValueError("creator_profile_frame_invalid")
            value.extend(part)
        return bytes(value)

    length = int.from_bytes(exact(4), "big")
    if not 0 < length <= MAX_PROFILE_REQUEST_BYTES:
        raise ValueError("creator_profile_frame_invalid")
    return exact(length)


def _safe_directory(directory: Path, *, create: bool = False) -> None:
    if create:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    observed = directory.lstat()
    if not stat.S_ISDIR(observed.st_mode) or directory.is_symlink() or directory.resolve() != directory:
        raise ValueError("creator_profile_configuration_invalid")
    if getattr(observed, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise ValueError("creator_profile_configuration_invalid")


def _command(mode: str, executable: Path) -> tuple[str, ...]:
    return str(executable), "-I", "-u", "-B", str(Path(__file__).resolve()), mode


class MediaCrawlerCreatorProfileProcessRunner:
    def __init__(
        self,
        *,
        lock_path: Path,
        integration_root: Path,
        python_executable: Path,
        enabled: bool,
        license_acknowledged: bool,
    ) -> None:
        if type(enabled) is not bool or type(license_acknowledged) is not bool:
            raise ValueError("creator_profile_configuration_invalid")
        self._lock_path = lock_path.expanduser().resolve()
        self._integration_root = integration_root.expanduser().resolve()
        self._python_executable = normalize_python_executable(python_executable)
        self._enabled = enabled
        self._license_acknowledged = license_acknowledged

    def run(
        self, request: MediaCrawlerCreatorProfileRequest, *, cancellation: threading.Event | None = None
    ) -> MediaCrawlerCreatorProfileResult:
        if not isinstance(request, MediaCrawlerCreatorProfileRequest):
            raise TypeError("creator_profile_request_invalid")
        if cancellation is not None and not isinstance(cancellation, threading.Event):
            raise TypeError("creator_profile_cancellation_invalid")
        deadline = time.monotonic() + request.timeout_seconds
        if request.platform not in _SUPPORTED_PLATFORMS:
            return _result(request, MediaCrawlerCreatorProfileStatus.UNSUPPORTED)
        if not self._enabled or not self._license_acknowledged:
            return _result(request, MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
        if cancellation is not None and cancellation.is_set():
            return _result(request, MediaCrawlerCreatorProfileStatus.CANCELLED)
        try:
            paths = build_run_paths(self._integration_root, request.platform, request.account_id, uuid4())
            # A lookup never creates a new profile or account. Both are proof
            # prerequisites for the noninteractive saved-session operation.
            _safe_directory(paths.integration_root)
            _safe_directory(paths.account_root)
            if is_attempt_cleanup_blocked(paths):
                return _result(request, MediaCrawlerCreatorProfileStatus.CLEANUP_FAILED)
            if request.cookie is None and not _profile_is_present(paths.profile_root):
                return _result(request, MediaCrawlerCreatorProfileStatus.AUTH_EXPIRED)
        except (OSError, ValueError):
            return _result(request, MediaCrawlerCreatorProfileStatus.AUTH_EXPIRED)
        account_lock = _AccountFileLock(paths.account_root)
        if not account_lock.acquire():
            return _result(request, MediaCrawlerCreatorProfileStatus.ACCOUNT_BUSY)
        tree_closed = True
        try:
            payload = _encode(
                {
                    "schema_version": CREATOR_PROFILE_SCHEMA_VERSION,
                    "account_id": str(request.account_id),
                    "platform": request.platform.value,
                    "creator_remote_id": request.creator_remote_id,
                    "request_id": str(request.request_id),
                    "execution_id": paths.job_root.name,
                    "integration_root": str(paths.integration_root),
                    "lock_path": str(self._lock_path),
                    "python_executable": str(self._python_executable),
                    "deadline": deadline,
                    **({"cookie": request.cookie.reveal()} if request.cookie is not None else {}),
                },
                MAX_PROFILE_REQUEST_BYTES,
            )
            result, tree_closed = self._execute(payload, request, account_lock.descriptor, deadline, cancellation)
            return result
        except (OSError, ValueError):
            return _result(request, MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
        finally:
            if tree_closed:
                account_lock.release()
            else:
                # Releasing a POSIX flock here would also unlock its inherited
                # descriptor. Retain parent ownership and the guardian's lock.
                _RETAINED_LOCKS.append(account_lock)
                with contextlib.suppress(Exception):
                    record_attempt_cleanup_incident(paths)

    @staticmethod
    def _execute(
        payload: bytes,
        request: MediaCrawlerCreatorProfileRequest,
        lock_descriptor: int,
        deadline: float,
        cancellation: threading.Event | None,
    ) -> tuple[MediaCrawlerCreatorProfileResult, bool]:
        if time.monotonic() >= deadline:
            return _result(request, MediaCrawlerCreatorProfileStatus.TIMED_OUT), True
        environment = browser_child_environment()
        environment.update({_CONTROL_ENV: _CONTROL_VERSION, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
        try:
            process = _spawn_login_child(
                _command("--guardian", Path(sys.executable)), Path.cwd(), environment, lock_descriptor
            )
        except OSError:
            return _result(request, MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID), True
        windows_job = _WindowsJob.attach(process)
        result = _result(request, MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
        output: list[bytes | None] = []
        completed = threading.Event()
        write_failed = threading.Event()

        def read() -> None:
            try:
                output.append(_read_stream_frame(process.stdout, MAX_PROFILE_RESULT_BYTES))
            except (OSError, ValueError, AttributeError):
                output.append(None)
            finally:
                completed.set()

        def write() -> None:
            nonlocal payload
            try:
                if process.stdin is None:
                    raise OSError
                process.stdin.write(payload + _CONTROL_START)
                process.stdin.flush()
            except (OSError, ValueError):
                write_failed.set()
                completed.set()
            finally:
                payload = b""

        reader = threading.Thread(target=read, name="media-sync-profile-frame", daemon=True)
        writer = threading.Thread(target=write, name="media-sync-profile-input", daemon=True)
        reader_started = writer_started = False
        try:
            reader.start()
            reader_started = True
            if os.name == "nt" and windows_job is None:
                result = _result(request, MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
            else:
                writer.start()
                writer_started = True
                while not completed.is_set():
                    if cancellation is not None and cancellation.is_set():
                        result = _result(request, MediaCrawlerCreatorProfileStatus.CANCELLED)
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        result = _result(request, MediaCrawlerCreatorProfileStatus.TIMED_OUT)
                        break
                    completed.wait(min(request.poll_seconds, remaining))
                else:
                    if cancellation is not None and cancellation.is_set():
                        result = _result(request, MediaCrawlerCreatorProfileStatus.CANCELLED)
                    elif time.monotonic() >= deadline:
                        result = _result(request, MediaCrawlerCreatorProfileStatus.TIMED_OUT)
                    elif not write_failed.is_set() and output and output[0] is not None:
                        result = _parse_result(output[0], request)
        except (OSError, ValueError, TypeError, RuntimeError):
            result = _result(request, MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
        finally:
            payload = b""
            cleanup_deadline = time.monotonic() + MAX_PROFILE_CLEANUP_SECONDS
            # Kill/join first: closing a buffered stdin from another thread
            # could wait forever if the bounded writer is blocked in the pipe.
            tree_closed = _close_process_tree(process, windows_job)
            if reader_started:
                reader.join(timeout=max(0.0, cleanup_deadline - time.monotonic()))
            if writer_started:
                writer.join(timeout=max(0.0, cleanup_deadline - time.monotonic()))
            remainder: bytes | None = None
            if tree_closed and not reader.is_alive() and process.stdout is not None:
                with contextlib.suppress(OSError):
                    remainder = process.stdout.read(1)
                process.stdout.close()
            if not tree_closed or reader.is_alive() or writer.is_alive():
                result = _result(request, MediaCrawlerCreatorProfileStatus.CLEANUP_FAILED)
            elif remainder != b"":
                result = _result(request, MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
        return result, tree_closed


@dataclass(frozen=True, slots=True)
class _Envelope:
    request: MediaCrawlerCreatorProfileRequest
    paths: RunPaths
    deadline: float
    lock_path: Path
    python_executable: Path

    @classmethod
    def load(cls, payload: bytes) -> _Envelope:
        raw = _json(payload, MAX_PROFILE_REQUEST_BYTES)
        if (
            (set(raw) - {"cookie"})
            != {
                "schema_version",
                "account_id",
                "platform",
                "creator_remote_id",
                "request_id",
                "execution_id",
                "integration_root",
                "lock_path",
                "python_executable",
                "deadline",
            }
            or type(raw["schema_version"]) is not int
            or raw["schema_version"] != CREATOR_PROFILE_SCHEMA_VERSION
        ):
            raise ValueError("creator_profile_frame_invalid")
        request = MediaCrawlerCreatorProfileRequest(
            UUID(raw["account_id"]),
            Platform(raw["platform"]),
            raw["creator_remote_id"],
            UUID(raw["request_id"]),
            cookie=parse_cookie_header(raw["cookie"]) if "cookie" in raw else None,
        )
        if request.platform not in _SUPPORTED_PLATFORMS:
            raise ValueError("creator_profile_identity_invalid")
        for key in ("account_id", "request_id", "execution_id"):
            if str(UUID(raw[key])) != raw[key]:
                raise ValueError("creator_profile_identity_invalid")
        deadline = raw["deadline"]
        if type(deadline) not in (float, int) or not math.isfinite(deadline):
            raise ValueError("creator_profile_budget_invalid")
        if not 0 < deadline - time.monotonic() <= MAX_PROFILE_EXECUTION_SECONDS:
            raise ValueError("creator_profile_budget_invalid")
        paths = build_run_paths(
            Path(_text(raw["integration_root"], 32767)), request.platform, request.account_id, UUID(raw["execution_id"])
        )
        return cls(
            request, paths, deadline, Path(_text(raw["lock_path"], 32767)), Path(_text(raw["python_executable"], 32767))
        )


def _emit(frame: bytes) -> None:
    remaining = memoryview(frame)
    while remaining:
        written = os.write(1, remaining)
        if written <= 0:
            raise OSError
        remaining = remaining[written:]
    with contextlib.suppress(OSError):
        os.close(1)


def _run_guardian(envelope: _Envelope) -> MediaCrawlerCreatorProfileResult:
    request = envelope.request
    try:
        checkout = verify_mediacrawler_checkout(envelope.lock_path, license_acknowledged=True)
        runtime = verify_mediacrawler_python(envelope.python_executable)
        if time.monotonic() >= envelope.deadline:
            return _result(request, MediaCrawlerCreatorProfileStatus.TIMED_OUT)
        payload = _encode(
            {
                "schema_version": CREATOR_PROFILE_SCHEMA_VERSION,
                "request": {
                    "account_id": str(request.account_id),
                    "platform": request.platform.value,
                    "creator_remote_id": request.creator_remote_id,
                    "request_id": str(request.request_id),
                    **({"cookie": request.cookie.reveal()} if request.cookie is not None else {}),
                },
                "checkout_root": str(checkout.root),
                "upstream_sha": checkout.commit,
                "integration_root": str(envelope.paths.integration_root),
                "execution_id": envelope.paths.job_root.name,
                "deadline": envelope.deadline,
            },
            MAX_PROFILE_REQUEST_BYTES,
        )
        environment = browser_child_environment()
        environment.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
        process = subprocess.Popen(
            _command("--worker", runtime.executable),
            cwd=checkout.root,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        # Inherit the guardian's group/Job; never start a separate session here.
        if process.stdin is None or process.stdout is None:
            raise ValueError
        process.stdin.write(payload)
        process.stdin.close()
        payload = b""
        frame = _read_stream_frame(process.stdout, MAX_PROFILE_RESULT_BYTES)
        if process.stdout.read(1) != b"":
            raise ValueError
        process.wait(timeout=max(0.01, envelope.deadline - time.monotonic()))
        if process.returncode != 0:
            raise ValueError
        result = _parse_result(frame, request)
        if result.upstream_sha != checkout.commit:
            raise ValueError
        return result
    except subprocess.TimeoutExpired:
        return _result(request, MediaCrawlerCreatorProfileStatus.TIMED_OUT)
    except Exception:
        return _result(request, MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)


def _guardian_entry() -> int:
    if os.environ.pop(_CONTROL_ENV, None) != _CONTROL_VERSION:
        return 20
    try:
        envelope = _Envelope.load(_read_control_frame())
        if _read_control_message() != _CONTROL_START:
            return 20
    except (OSError, ValueError, TypeError, KeyError):
        return 20
    cancellation, parent_lost, result_complete = threading.Event(), threading.Event(), threading.Event()
    child_job = _WindowsJob.attach_current_process() if os.name == "nt" else None
    if os.name == "nt" and child_job is None:
        return 20
    if os.name != "nt":
        get_process_group = getattr(os, "getpgrp", None)
        if not callable(get_process_group) or get_process_group() != os.getpid():
            return 20
        signal.signal(signal.SIGTERM, lambda *_: cancellation.set())
    watcher = threading.Thread(
        target=_watch_parent_control, args=(cancellation, parent_lost, child_job, result_complete), daemon=True
    )
    watcher.start()
    with _silenced_upstream():
        result = _run_guardian(envelope)
    result_complete.set()
    _emit(_result_frame(result))
    _guard_completed_login_tree(cancellation, parent_lost, watcher, child_job, result_complete)
    return 0


class _LookupFailure(RuntimeError):
    def __init__(self, status: MediaCrawlerCreatorProfileStatus) -> None:
        self.status = status
        super().__init__(status.value)


def _fetch_raw_api_json(url: str, headers: Mapping[str, str], deadline: float) -> dict[str, Any]:
    import httpx

    from media_sync.media.network import PinnedHTTPTransport, SocketAddressResolver, validate_target

    remaining = min(10.0, deadline - time.monotonic())
    if remaining <= 0:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
    target = validate_target(url, SocketAddressResolver(), max_url_chars=4096)
    outgoing = {name: value for name, value in headers.items() if name in {"User-Agent", "Cookie", "Origin", "Referer"}}
    if any(
        type(value) is not str or len(value) > 65536 or "\r" in value or "\n" in value for value in outgoing.values()
    ):
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
    outgoing.update({"Host": target.host_header, "Accept": "application/json", "Accept-Encoding": "identity"})
    with (
        httpx.Client(
            transport=PinnedHTTPTransport(target), trust_env=False, follow_redirects=False, timeout=remaining
        ) as client,
        client.stream("GET", target.url, headers=outgoing) as response,
    ):
        if response.status_code != 200:
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TEMPORARY)
        if (
            response.headers.get("content-encoding", "identity").lower() != "identity"
            or response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json"
        ):
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
        length = response.headers.get("content-length")
        if length is not None and (
            not length.isascii() or not length.isdecimal() or int(length) > MAX_PROFILE_API_BYTES
        ):
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
        chunks = bytearray()
        for chunk in response.iter_raw(chunk_size=8192):
            if time.monotonic() >= deadline:
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
            if len(chunks) + len(chunk) > MAX_PROFILE_API_BYTES:
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
            chunks.extend(chunk)
    return _json(bytes(chunks), MAX_PROFILE_API_BYTES)


def _fetch_api_json(url: str, headers: Mapping[str, str], deadline: float) -> dict[str, Any]:
    raw = _fetch_raw_api_json(url, headers, deadline)
    if type(raw.get("code")) is not int or raw["code"] != 0:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TEMPORARY)
    data = raw.get("data")
    if type(data) is not dict:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
    return data


async def _query_weibo_client(client: Any, creator_remote_id: str, deadline: float) -> MediaCrawlerCreatorProfile:
    """Run the exact locked public-profile method only after fresh auth proof."""
    _uid(creator_remote_id)
    expected_urls = (
        _WB_ORIGIN + _WB_CONFIG_PATH,
        _WB_ORIGIN
        + _WB_PROFILE_PATH
        + "?"
        + urlencode(
            {
                "jumpfrom": "weibocom",
                "type": "uid",
                "value": creator_remote_id,
                "containerid": "100505" + creator_remote_id,
            }
        ),
    )
    calls = 0
    auth_confirmed = False
    original_headers = dict(client.headers)

    async def bounded_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        if (
            method != "GET"
            or calls >= 2
            or url != expected_urls[calls]
            or set(kwargs) != {"headers"}
            or not isinstance(kwargs["headers"], Mapping)
            or dict(kwargs["headers"]) != original_headers
            or (calls == 1 and not auth_confirmed)
        ):
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
        calls += 1
        raw = await asyncio.to_thread(_fetch_raw_api_json, url, original_headers, deadline)
        if type(raw.get("ok")) is not int or raw["ok"] != 1:
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TEMPORARY)
        data = raw.get("data")
        if type(data) is not dict:
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
        return data

    # Replace the decorated request itself: do not permit its five retries or
    # malformed-JSON browser navigation/cookie refresh fallback.
    client.request = bounded_request
    authenticated = await client.get(_WB_CONFIG_PATH)
    if type(authenticated) is not dict:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
    if authenticated.get("login") is False:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.AUTH_EXPIRED)
    if calls != 1 or authenticated.get("login") is not True:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
    auth_confirmed = True
    raw = await client.get_creator_info_by_id(creator_remote_id)
    user = raw.get("userInfo") if type(raw) is dict else None
    if (
        calls != 2
        or type(user) is not dict
        or type(user.get("id")) not in (str, int)
        or str(user["id"]) != creator_remote_id
    ):
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
    avatar: str | None = None
    for key in ("avatar_hd", "profile_image_url"):
        try:
            avatar = _text(user.get(key), 2048)
            break
        except ValueError:
            continue
    return MediaCrawlerCreatorProfile(creator_remote_id, _text(user.get("screen_name"), 512), avatar)


async def _query_bili_client(client: Any, creator_remote_id: str, deadline: float) -> MediaCrawlerCreatorProfile:
    calls = {_NAV_PATH: 0, _PROFILE_PATH: 0}

    async def bounded_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        parsed = urlsplit(url)
        if (
            method != "GET"
            or parsed.scheme != "https"
            or parsed.netloc != _API_HOST
            or parsed.path not in calls
            or parsed.fragment
            or set(kwargs) - {"headers"}
        ):
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=3)
        if (parsed.path == _NAV_PATH and query) or (
            parsed.path == _PROFILE_PATH
            and (set(query) - {"mid", "wts", "w_rid"} or query.get("mid") != [creator_remote_id])
        ):
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
        calls[parsed.path] += 1
        if calls[parsed.path] > (2 if parsed.path == _NAV_PATH else 1):
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
        return await asyncio.to_thread(_fetch_api_json, url, client.headers, deadline)

    client.request = bounded_request
    authenticated = await client.get(_NAV_PATH, enable_params_sign=False)
    if authenticated.get("isLogin") is False:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.AUTH_EXPIRED)
    if authenticated.get("isLogin") is not True:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
    raw = await client.get_creator_info(int(creator_remote_id))
    if type(raw) is not dict or type(raw.get("mid")) not in (str, int) or str(raw["mid"]) != creator_remote_id:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
    avatar = raw.get("face")
    return MediaCrawlerCreatorProfile(
        creator_remote_id, _text(raw.get("name"), 512), None if avatar in (None, "") else avatar
    )


def _origin(module: Any, expected: Path) -> None:
    path = getattr(module, "__file__", None)
    if type(path) is not str or Path(path).resolve() != expected.resolve() or expected.is_symlink():
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)


async def _lookup_bili(
    checkout: Path, profile: Path, remote_id: str, deadline: float, *, cookie: SecretValue | None = None
) -> MediaCrawlerCreatorProfile:
    os.chdir(checkout)
    sys.path.insert(0, str(checkout))
    if "config" in sys.modules or "media_platform.bilibili.core" in sys.modules:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
    config: Any = importlib.import_module("config")
    _origin(config, checkout / "config" / "__init__.py")
    config.PLATFORM = "bili"
    config.COOKIES = ""
    config.CRAWLER_TYPE = "media_sync_profile_only"
    config.CREATOR_MODE = False
    config.ENABLE_CDP_MODE = False
    config.ENABLE_IP_PROXY = False
    config.STATIC_PROXY_URL = ""
    for attribute in CREATOR_CONFIG_ATTRIBUTES.values():
        setattr(config, attribute, [])
    core = importlib.import_module("media_platform.bilibili.core")
    client_module = importlib.import_module("media_platform.bilibili.client")
    _origin(core, checkout / "media_platform" / "bilibili" / "core.py")
    _origin(client_module, checkout / "media_platform" / "bilibili" / "client.py")
    if getattr(core.BilibiliCrawler, "__module__", None) != core.__name__:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
    playwright_api = importlib.import_module("playwright.async_api")
    crawler = core.BilibiliCrawler()
    async with playwright_api.async_playwright() as playwright:
        browser = None
        try:
            if cookie is None:
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile),
                    executable_path=playwright.chromium.executable_path,
                    headless=True,
                    accept_downloads=False,
                    service_workers="block",
                    timeout=max(1, int(min(15, deadline - time.monotonic()) * 1000)),
                )
            else:
                browser = await playwright.chromium.launch(
                    executable_path=playwright.chromium.executable_path,
                    headless=True,
                    timeout=max(1, int(min(15, deadline - time.monotonic()) * 1000)),
                )
                context = await browser.new_context(accept_downloads=False, service_workers="block")
                await context.add_cookies(
                    [
                        {"name": name, "value": value, "domain": ".bilibili.com", "path": "/", "secure": True}
                        for name, value in cookie_pairs(cookie.reveal()).items()
                    ]
                )
        except Exception:
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.BROWSER_LAUNCH_FAILED) from None
        try:

            async def route_browser(route: Any) -> None:
                if route.request.is_navigation_request() and route.request.url == "https://www.bilibili.com/":
                    await route.fulfill(status=200, content_type="text/html", body="<!doctype html><title></title>")
                else:
                    await route.abort()

            # A same-origin empty document exposes the existing localStorage
            # without requesting a homepage/feed, image, script or video.
            await context.route("**/*", route_browser)
            crawler.browser_context = context
            crawler.context_page = await context.new_page()
            await crawler.context_page.goto("https://www.bilibili.com/", wait_until="domcontentloaded")
            client = await crawler.create_bilibili_client(None)
            if type(client) is not client_module.BilibiliClient:
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
            with fence_saved_session_qr_fallback(Platform.BILI):
                return await _query_bili_client(client, remote_id, deadline)
        finally:
            config.COOKIES = ""
            with contextlib.suppress(Exception):
                await asyncio.wait_for(context.close(), timeout=max(0.01, min(2.0, deadline - time.monotonic())))
            if browser is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(browser.close(), timeout=max(0.01, min(2.0, deadline - time.monotonic())))


async def _lookup_weibo(
    checkout: Path, profile: Path, remote_id: str, deadline: float, *, cookie: SecretValue | None = None
) -> MediaCrawlerCreatorProfile:
    """Use a scoped browser only for credentials; all profile HTTP is isolated."""
    os.chdir(checkout)
    sys.path.insert(0, str(checkout))
    if "config" in sys.modules or "media_platform.weibo.client" in sys.modules:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
    config: Any = importlib.import_module("config")
    _origin(config, checkout / "config/__init__.py")
    config.PLATFORM = "wb"
    config.COOKIES = ""
    config.ENABLE_IP_PROXY = False
    config.STATIC_PROXY_URL = ""
    client_module = importlib.import_module("media_platform.weibo.client")
    utils = importlib.import_module("tools.utils")
    _origin(client_module, checkout / "media_platform/weibo/client.py")
    _origin(utils, checkout / "tools/utils.py")
    if getattr(client_module.WeiboClient, "__module__", None) != client_module.__name__:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
    playwright_api = importlib.import_module("playwright.async_api")
    async with playwright_api.async_playwright() as playwright:
        browser = None
        try:
            if cookie is None:
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile),
                    executable_path=playwright.chromium.executable_path,
                    headless=True,
                    accept_downloads=False,
                    service_workers="block",
                    timeout=max(1, int(min(15, deadline - time.monotonic()) * 1000)),
                )
            else:
                browser = await playwright.chromium.launch(
                    executable_path=playwright.chromium.executable_path,
                    headless=True,
                    timeout=max(1, int(min(15, deadline - time.monotonic()) * 1000)),
                )
                context = await browser.new_context(accept_downloads=False, service_workers="block")
                await context.add_cookies(
                    [
                        {"name": name, "value": value, "domain": ".weibo.cn", "path": "/", "secure": True}
                        for name, value in cookie_pairs(cookie.reveal()).items()
                    ]
                )
        except Exception:
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.BROWSER_LAUNCH_FAILED) from None
        try:

            async def route_browser(route: Any) -> None:
                if route.request.is_navigation_request() and route.request.url == _WB_ORIGIN + "/":
                    await route.fulfill(status=200, content_type="text/html", body="<!doctype html><title></title>")
                else:
                    await route.abort()

            await context.route("**/*", route_browser)
            page = await context.new_page()
            await page.goto(_WB_ORIGIN + "/", wait_until="domcontentloaded")
            if cookie is None:
                header, _unused = await utils.convert_browser_context_cookies(context, urls=[_WB_ORIGIN])
                if not header:
                    raise _LookupFailure(MediaCrawlerCreatorProfileStatus.AUTH_EXPIRED)
                header = parse_cookie_header(header).reveal()
            else:
                # Use the candidate exactly, never a coalesced browser-cookie
                # reread or a previous saved session as substitute authority.
                header = cookie.reveal()
            client = client_module.WeiboClient(
                proxy=None,
                headers={
                    "User-Agent": utils.get_mobile_user_agent(),
                    "Cookie": header,
                    "Origin": _WB_ORIGIN,
                    "Referer": _WB_ORIGIN + "/",
                },
                playwright_page=page,
                cookie_dict=cookie_pairs(header),
            )
            if type(client) is not client_module.WeiboClient:
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
            return await _query_weibo_client(client, remote_id, deadline)
        finally:
            config.COOKIES = ""
            with contextlib.suppress(Exception):
                await asyncio.wait_for(context.close(), timeout=max(0.01, min(2.0, deadline - time.monotonic())))
            if browser is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(browser.close(), timeout=max(0.01, min(2.0, deadline - time.monotonic())))


def _worker_entry() -> int:
    try:
        raw = _json(_read_control_frame(), MAX_PROFILE_REQUEST_BYTES)
        if set(raw) != {
            "schema_version",
            "request",
            "checkout_root",
            "upstream_sha",
            "integration_root",
            "execution_id",
            "deadline",
        }:
            return 20
        if type(raw["schema_version"]) is not int or raw["schema_version"] != CREATOR_PROFILE_SCHEMA_VERSION:
            return 20
        if type(raw["request"]) is not dict or (set(raw["request"]) - {"cookie"}) != {
            "account_id",
            "platform",
            "creator_remote_id",
            "request_id",
        }:
            return 20
        request = MediaCrawlerCreatorProfileRequest(
            UUID(raw["request"]["account_id"]),
            Platform(raw["request"]["platform"]),
            raw["request"]["creator_remote_id"],
            UUID(raw["request"]["request_id"]),
            cookie=parse_cookie_header(raw["request"]["cookie"]) if "cookie" in raw["request"] else None,
        )
        checkout = Path(raw["checkout_root"])
        paths = build_run_paths(
            Path(raw["integration_root"]), request.platform, request.account_id, UUID(raw["execution_id"])
        )
        profile = paths.profile_root
        sha, deadline = raw["upstream_sha"], raw["deadline"]
        if (
            request.platform not in _SUPPORTED_PLATFORMS
            or _SHA.fullmatch(sha) is None
            or checkout.resolve() != Path.cwd().resolve()
        ):
            return 20
        if (
            request.cookie is None and not _profile_is_present(profile)
        ) or not 0 < deadline - time.monotonic() <= MAX_PROFILE_EXECUTION_SECONDS:
            return 20
    except (ValueError, TypeError, OSError, KeyError):
        return 20
    try:
        with _silenced_upstream():
            if request.platform is Platform.KS:
                from media_sync.integrations.mediacrawler.kuaishou_creator_profile import lookup_kuaishou

                lookup = lookup_kuaishou
            elif request.platform is Platform.ZHIHU:
                from media_sync.integrations.mediacrawler.zhihu_creator_profile import lookup_zhihu

                lookup = lookup_zhihu
            else:
                lookup = _lookup_bili if request.platform is Platform.BILI else _lookup_weibo
            result = asyncio.run(lookup(checkout, profile, request.creator_remote_id, deadline, cookie=request.cookie))
        outcome = _result(request, MediaCrawlerCreatorProfileStatus.SUCCEEDED, sha, result)
    except _LookupFailure as error:
        outcome = _result(request, error.status, sha)
    except (ValueError, TypeError, KeyError):
        outcome = _result(request, MediaCrawlerCreatorProfileStatus.RESULT_INVALID, sha)
    except BaseException:
        outcome = _result(request, MediaCrawlerCreatorProfileStatus.TEMPORARY, sha)
    _emit(_result_frame(outcome))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"--guardian", "--worker"}:
        raise SystemExit(20)
    raise SystemExit(_guardian_entry() if sys.argv[1] == "--guardian" else _worker_entry())


__all__ = [
    "MediaCrawlerCreatorProfile",
    "MediaCrawlerCreatorProfileProcessRunner",
    "MediaCrawlerCreatorProfileRequest",
    "MediaCrawlerCreatorProfileResult",
    "MediaCrawlerCreatorProfileRunner",
    "MediaCrawlerCreatorProfileStatus",
]
