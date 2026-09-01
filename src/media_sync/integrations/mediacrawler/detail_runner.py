"""Bounded MediaCrawler detail-mode execution returning ephemeral JSONL bytes.

The production runner uses the locked upstream checkout, the account's stable
browser profile and a short-lived attempt directory.  Detail JSONL is read
back into memory and the attempt directory is removed before this API returns;
callers never receive a path that could accidentally become durable state.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MethodType
from typing import Any, Protocol
from uuid import UUID, uuid4

# ``-I path/to/detail_runner.py --child`` intentionally starts without the
# repository on sys.path.  Bootstrap only this package root before importing
# media-sync; private inputs still arrive over stdin, never the environment.
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from media_sync.domain import LoginMethod, Platform
from media_sync.integrations.mediacrawler.checkout import (
    VerifiedCheckout,
    VerifiedPython,
    verify_mediacrawler_checkout,
    verify_mediacrawler_python,
)
from media_sync.integrations.mediacrawler.normalizers import _BILI_PROGRESSIVE_FIELD
from media_sync.integrations.mediacrawler.policies import (
    CREATOR_CONFIG_ATTRIBUTES,
    RunPaths,
    WatchdogLimits,
    build_run_paths,
    inspect_output,
    upstream_login_type,
)
from media_sync.integrations.mediacrawler.runner import (
    _AccountFileLock,
    _close_process_tree,
    _WindowsJob,
)
from media_sync.integrations.mediacrawler.weibo_media import (
    install_weibo_media_capture,
    is_weibo_numeric_note_id,
)
from media_sync.integrations.mediacrawler.xhs_authority import (
    validate_xhs_creator_reference,
    validate_xhs_detail_reference,
)
from media_sync.media import ResolvedLocator
from media_sync.media.errors import MediaDownloadError
from media_sync.security import SecretValue
from media_sync.security.secrets import MAX_SECRET_BYTES

DETAIL_RUNNER_SCHEMA_VERSION = 3
MAX_DETAIL_REQUEST_BYTES = 128 * 1024
MAX_DETAIL_FRAME_OVERHEAD = 8 * 1024

_SUPPORTED_PLATFORMS = frozenset({Platform.XHS, Platform.DY, Platform.KS, Platform.BILI, Platform.WB})
_DETAIL_CONFIG_ATTRIBUTES = {
    Platform.XHS: "XHS_SPECIFIED_NOTE_URL_LIST",
    Platform.DY: "DY_SPECIFIED_ID_LIST",
    Platform.KS: "KS_SPECIFIED_ID_LIST",
    Platform.BILI: "BILI_SPECIFIED_ID_LIST",
    Platform.WB: "WEIBO_SPECIFIED_ID_LIST",
    Platform.TIEBA: "TIEBA_SPECIFIED_ID_LIST",
    Platform.ZHIHU: "ZHIHU_SPECIFIED_ID_LIST",
}
_CHILD_ENV_ALLOWLIST = frozenset(
    {
        "APPDATA",
        "COMSPEC",
        "DISPLAY",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMW6432",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WAYLAND_DISPLAY",
        "WINDIR",
        "XAUTHORITY",
        "XDG_RUNTIME_DIR",
    }
)


class MediaCrawlerDetailPayloadRunner(Protocol):
    """Dependency-injection boundary used by the context-aware refresher."""

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        """Return bounded content JSONL in memory or one fixed download error."""
        ...


def _is_weibo_detail_reference(value: object, content_remote_id: str) -> bool:
    """Accept only the implicit ID or the exact same non-secret Weibo ID."""

    return is_weibo_numeric_note_id(content_remote_id) and (
        value is None or (type(value) is str and value == content_remote_id)
    )


def _validate_xhs_request_authority(
    *,
    detail_reference: object,
    creator_reference: object,
    creator_max_items: object,
    content_remote_id: str,
    author_remote_id: str,
    watchdogs: WatchdogLimits,
) -> None:
    try:
        if detail_reference is not None:
            if not isinstance(detail_reference, SecretValue):
                raise ValueError
            if creator_reference is not None or creator_max_items is not None:
                raise ValueError
            validate_xhs_detail_reference(detail_reference.reveal(), content_remote_id)
            return
        if not isinstance(creator_reference, SecretValue):
            raise ValueError
        if type(creator_max_items) is not int or not 1 <= creator_max_items <= 1_000:
            raise ValueError
        if creator_max_items > watchdogs.max_output_items:
            raise ValueError
        validate_xhs_creator_reference(creator_reference.reveal(), author_remote_id)
    except ValueError as exc:
        raise MediaDownloadError("locator_refresh_configuration_invalid") from exc


@dataclass(frozen=True, slots=True)
class MediaCrawlerDetailRequest:
    """One frozen, account-bound detail lookup with no database dependency."""

    account_id: UUID
    subscription_id: UUID
    platform: Platform
    login_method: LoginMethod
    content_remote_id: str
    author_remote_id: str
    detail_reference: str | SecretValue | None = field(default=None, repr=False)
    creator_reference: SecretValue | None = field(default=None, repr=False)
    creator_max_items: int | None = None
    cookie: SecretValue | None = field(default=None, repr=False)
    headless: bool = True
    request_delay_seconds: float = 2.0
    bili_progressive_detail: bool = False
    watchdogs: WatchdogLimits = field(default_factory=WatchdogLimits)

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, UUID) or not isinstance(self.subscription_id, UUID):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        try:
            platform = Platform(self.platform)
            login_method = LoginMethod(self.login_method)
        except (TypeError, ValueError) as exc:
            raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
        content_remote_id = _bounded_text(self.content_remote_id)
        author_remote_id = _bounded_text(self.author_remote_id, maximum=255)
        if platform not in _SUPPORTED_PLATFORMS or login_method is LoginMethod.PHONE:
            raise MediaDownloadError("locator_refresh_unsupported")
        if self.detail_reference is not None and not isinstance(self.detail_reference, str | SecretValue):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if isinstance(self.detail_reference, str):
            _bounded_text(self.detail_reference, maximum=4_096)
        if self.creator_reference is not None and not isinstance(self.creator_reference, SecretValue):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if not isinstance(self.watchdogs, WatchdogLimits):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if platform is Platform.XHS:
            _validate_xhs_request_authority(
                detail_reference=self.detail_reference,
                creator_reference=self.creator_reference,
                creator_max_items=self.creator_max_items,
                content_remote_id=content_remote_id,
                author_remote_id=author_remote_id,
                watchdogs=self.watchdogs,
            )
        elif self.creator_reference is not None or self.creator_max_items is not None:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if platform is Platform.WB and not _is_weibo_detail_reference(self.detail_reference, content_remote_id):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if login_method is LoginMethod.COOKIE and self.cookie is None:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if login_method is not LoginMethod.COOKIE and self.cookie is not None:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if not isinstance(self.headless, bool):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if not isinstance(self.bili_progressive_detail, bool) or (
            self.bili_progressive_detail and platform is not Platform.BILI
        ):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        delay = self.request_delay_seconds
        if isinstance(delay, bool) or not isinstance(delay, int | float) or not 0 < float(delay) <= 60:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        object.__setattr__(self, "platform", platform)
        object.__setattr__(self, "login_method", login_method)
        object.__setattr__(self, "content_remote_id", content_remote_id)
        object.__setattr__(self, "author_remote_id", author_remote_id)
        object.__setattr__(self, "request_delay_seconds", float(delay))

    def resolved_detail_reference(self) -> str | None:
        """Reveal an explicit reference only at the child-request boundary."""

        value = self.detail_reference
        if self.platform is Platform.XHS and self.creator_reference is not None:
            return None
        if self.platform is Platform.WB:
            if not _is_weibo_detail_reference(value, self.content_remote_id):
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            if value is None:
                return self.content_remote_id
            if not isinstance(value, str):  # Defensive narrowing after the exact-type predicate.
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            return value
        if isinstance(value, SecretValue):
            resolved = _bounded_text(value.reveal(), maximum=4_096)
        elif isinstance(value, str):
            resolved = _bounded_text(value, maximum=4_096)
        else:
            resolved = self.content_remote_id
        return resolved

    def resolved_creator_reference(self) -> str | None:
        """Reveal creator authority only for an already-validated XHS lookup."""

        value = self.creator_reference
        if value is None:
            return None
        try:
            return validate_xhs_creator_reference(value.reveal(), self.author_remote_id)
        except ValueError as exc:
            raise MediaDownloadError("locator_refresh_configuration_invalid") from exc


@dataclass(frozen=True, slots=True)
class MediaCrawlerDetailResult:
    """An in-memory result tied to the verified upstream revision."""

    jsonl: bytes = field(repr=False)
    upstream_sha: str

    def __post_init__(self) -> None:
        if not isinstance(self.jsonl, bytes):
            raise TypeError("jsonl must be bytes")
        sha = self.upstream_sha.strip().lower()
        if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
            raise ValueError("upstream_sha must be a full Git SHA")
        object.__setattr__(self, "upstream_sha", sha)


CheckoutVerifier = Callable[[Path, bool], VerifiedCheckout]
PythonVerifier = Callable[[Path], VerifiedPython]


def _default_checkout_verifier(lock_path: Path, license_acknowledged: bool) -> VerifiedCheckout:
    return verify_mediacrawler_checkout(lock_path, license_acknowledged=license_acknowledged)


class MediaCrawlerDetailProcessRunner:
    """Run the pinned MediaCrawler detail mode in a supervised local child."""

    def __init__(
        self,
        *,
        lock_path: Path,
        integration_root: Path,
        python_executable: Path,
        license_acknowledged: bool,
        checkout_verifier: CheckoutVerifier = _default_checkout_verifier,
        python_verifier: PythonVerifier = verify_mediacrawler_python,
    ) -> None:
        self._lock_path = lock_path.expanduser().resolve()
        self._integration_root = integration_root.expanduser().resolve()
        self._python_executable = python_executable.expanduser().resolve()
        self._license_acknowledged = license_acknowledged
        self._checkout_verifier = checkout_verifier
        self._python_verifier = python_verifier

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        """Return content JSONL, cleaning only this invocation's attempt root."""

        try:
            checkout = self._checkout_verifier(self._lock_path, self._license_acknowledged)
            runtime = self._python_verifier(self._python_executable)
        except Exception as exc:
            raise MediaDownloadError("locator_refresh_configuration_invalid") from exc

        execution_id = uuid4()
        try:
            paths = build_run_paths(self._integration_root, request.platform, request.account_id, execution_id)
            paths.account_root.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as exc:
            raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
        account_lock = _AccountFileLock(paths.account_root)
        if not account_lock.acquire():
            raise MediaDownloadError("locator_refresh_temporary")
        try:
            try:
                if request.login_method is LoginMethod.SAVED_SESSION and (
                    not paths.profile_root.is_dir() or not any(paths.profile_root.iterdir())
                ):
                    raise MediaDownloadError("locator_refresh_auth_expired")
                paths.output_root.mkdir(parents=True, exist_ok=False)
                child_payload = self._child_payload(request, checkout, paths)
                output = self._execute(runtime.executable, checkout.root, child_payload, request.watchdogs)
                return MediaCrawlerDetailResult(jsonl=output, upstream_sha=checkout.commit)
            except MediaDownloadError:
                raise
            except OSError as exc:
                raise MediaDownloadError("locator_refresh_temporary") from exc
            except Exception as exc:
                raise MediaDownloadError("locator_refresh_result_invalid") from exc
        finally:
            # The stable account profile and its lock file deliberately remain.
            # Only the UUID-scoped detail attempt can contain signed JSONL.
            cleanup_error: OSError | None = None
            try:
                shutil.rmtree(paths.job_root)
            except FileNotFoundError:
                pass
            except OSError as exc:
                cleanup_error = exc
            finally:
                account_lock.release()
            if cleanup_error is not None:
                raise MediaDownloadError("locator_refresh_result_invalid") from cleanup_error

    @staticmethod
    def _child_payload(
        request: MediaCrawlerDetailRequest,
        checkout: VerifiedCheckout,
        paths: RunPaths,
    ) -> bytes:
        limits = request.watchdogs
        cookie = request.cookie.reveal() if request.cookie is not None else None
        payload = json.dumps(
            {
                "schema_version": DETAIL_RUNNER_SCHEMA_VERSION,
                "checkout_root": str(checkout.root),
                "account_root": str(paths.account_root),
                "profile_root": str(paths.profile_root),
                "job_root": str(paths.job_root),
                "output_root": str(paths.output_root),
                "platform": request.platform.value,
                "login_method": request.login_method.value,
                "content_remote_id": request.content_remote_id,
                "author_remote_id": request.author_remote_id,
                "detail_reference": request.resolved_detail_reference(),
                "creator_reference": request.resolved_creator_reference(),
                "creator_max_items": request.creator_max_items,
                "cookie": cookie,
                "headless": request.headless,
                "request_delay_seconds": request.request_delay_seconds,
                "bili_progressive_detail": request.bili_progressive_detail,
                "watchdogs": {
                    "max_seconds": limits.max_seconds,
                    "max_output_bytes": limits.max_output_bytes,
                    "max_output_items": limits.max_output_items,
                    "max_output_files": limits.max_output_files,
                    "max_line_bytes": limits.max_line_bytes,
                    "poll_seconds": limits.poll_seconds,
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > MAX_DETAIL_REQUEST_BYTES:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        return payload

    @staticmethod
    def _execute(
        executable: Path,
        checkout_root: Path,
        child_payload: bytes,
        limits: WatchdogLimits,
    ) -> bytes:
        command = (str(executable), "-I", "-u", "-B", str(Path(__file__).resolve()), "--child")
        environment = {name: value for name, value in os.environ.items() if name.upper() in _CHILD_ENV_ALLOWLIST}
        environment.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"})
        try:
            if os.name == "nt":
                process = subprocess.Popen(
                    command,
                    cwd=checkout_root,
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    close_fds=True,
                    creationflags=(
                        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    ),
                )
            else:
                process = subprocess.Popen(
                    command,
                    cwd=checkout_root,
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    close_fds=True,
                    start_new_session=True,
                )
        except OSError as exc:
            raise MediaDownloadError("locator_refresh_temporary") from exc

        windows_job = _WindowsJob.attach(process)
        if os.name == "nt" and windows_job is None:
            _close_process_tree(process, None)
            raise MediaDownloadError("locator_refresh_temporary")

        cleanup_reserve = max(5.0, min(15.0, limits.max_seconds * 0.1))
        tree_closed = False
        try:
            frame, _stderr = process.communicate(child_payload, timeout=limits.max_seconds + cleanup_reserve)
        except subprocess.TimeoutExpired as exc:
            tree_closed = _close_process_tree(process, windows_job)
            with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                process.communicate(timeout=2)
            raise MediaDownloadError("locator_refresh_temporary") from exc
        finally:
            child_payload = b""
            if not tree_closed:
                tree_closed = _close_process_tree(process, windows_job)

        if not tree_closed:
            raise MediaDownloadError("locator_refresh_result_invalid")

        maximum_frame = ((limits.max_output_bytes + 2) // 3 * 4) + MAX_DETAIL_FRAME_OVERHEAD
        if len(frame) > maximum_frame:
            raise MediaDownloadError("locator_refresh_result_invalid")
        status, payload = _parse_child_frame(frame)
        if process.returncode != 0 or status != "succeeded":
            code = {
                "configuration_invalid": "locator_refresh_configuration_invalid",
                "temporary": "locator_refresh_temporary",
                "auth_expired": "locator_refresh_auth_expired",
                "unsupported": "locator_refresh_unsupported",
            }.get(status, "locator_refresh_result_invalid")
            raise MediaDownloadError(code)
        try:
            decoded = base64.b64decode(payload, validate=True)
        except (ValueError, UnicodeError) as exc:
            raise MediaDownloadError("locator_refresh_result_invalid") from exc
        if len(decoded) > limits.max_output_bytes:
            raise MediaDownloadError("locator_refresh_result_invalid")
        return decoded


def _bounded_text(value: object, *, maximum: int = 512) -> str:
    if not isinstance(value, str):
        raise MediaDownloadError("locator_refresh_configuration_invalid")
    normalized = value.strip()
    if not normalized or normalized != value or len(normalized) > maximum:
        raise MediaDownloadError("locator_refresh_configuration_invalid")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized):
        raise MediaDownloadError("locator_refresh_configuration_invalid")
    return normalized


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-standard JSON number")


def _parse_child_frame(frame: bytes) -> tuple[str, str]:
    try:
        decoded = json.loads(frame, object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise MediaDownloadError("locator_refresh_result_invalid") from exc
    if not isinstance(decoded, Mapping) or set(decoded) != {"schema_version", "status", "payload"}:
        raise MediaDownloadError("locator_refresh_result_invalid")
    if decoded.get("schema_version") != DETAIL_RUNNER_SCHEMA_VERSION:
        raise MediaDownloadError("locator_refresh_result_invalid")
    status = decoded.get("status")
    payload = decoded.get("payload")
    if status not in {
        "succeeded",
        "configuration_invalid",
        "temporary",
        "result_invalid",
        "auth_expired",
        "unsupported",
    }:
        raise MediaDownloadError("locator_refresh_result_invalid")
    if not isinstance(status, str) or not isinstance(payload, str):
        raise MediaDownloadError("locator_refresh_result_invalid")
    return status, payload


class _ChildConfigurationError(RuntimeError):
    """A private child request is invalid; its text never crosses the process."""


class _ChildAuthExpiredError(RuntimeError):
    """The expected saved profile disappeared before the child could probe it."""


class _ChildTemporaryError(RuntimeError):
    """A bounded upstream lookup failed without returning a usable response."""


class _ChildUnsupportedError(RuntimeError):
    """The current media shape is intentionally outside the closed contract."""


@dataclass(frozen=True, slots=True)
class _BiliProgressiveResult:
    """One validated play URL whose value must stay out of repr and disk."""

    aid: int
    cid: int
    url: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.aid) is not int or self.aid <= 0 or type(self.cid) is not int or self.cid <= 0:
            raise ValueError("invalid Bilibili identity")
        try:
            validated = ResolvedLocator(self.url)
        except MediaDownloadError as exc:
            raise ValueError("invalid Bilibili progressive URL") from exc
        object.__setattr__(self, "url", validated.url)


@dataclass(frozen=True, slots=True)
class _ChildRequest:
    checkout_root: Path
    account_root: Path
    profile_root: Path
    job_root: Path
    output_root: Path
    platform: Platform
    login_method: LoginMethod
    content_remote_id: str
    detail_reference: str | None = field(repr=False)
    author_remote_id: str = "unknown"
    creator_reference: str | None = field(default=None, repr=False)
    creator_max_items: int | None = None
    cookie: str | None = field(default=None, repr=False)
    headless: bool = True
    request_delay_seconds: float = 2.0
    bili_progressive_detail: bool = False
    watchdogs: WatchdogLimits = field(default_factory=WatchdogLimits)

    @classmethod
    def load(cls, payload: bytes) -> _ChildRequest:
        try:
            raw = json.loads(payload, object_pairs_hook=_strict_object)
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise _ChildConfigurationError from exc
        expected = {
            "schema_version",
            "checkout_root",
            "account_root",
            "profile_root",
            "job_root",
            "output_root",
            "platform",
            "login_method",
            "content_remote_id",
            "author_remote_id",
            "detail_reference",
            "creator_reference",
            "creator_max_items",
            "cookie",
            "headless",
            "request_delay_seconds",
            "bili_progressive_detail",
            "watchdogs",
        }
        if (
            not isinstance(raw, Mapping)
            or set(raw) != expected
            or raw.get("schema_version") != DETAIL_RUNNER_SCHEMA_VERSION
        ):
            raise _ChildConfigurationError
        try:
            platform = Platform(raw["platform"])
            login_method = LoginMethod(raw["login_method"])
            checkout_root = Path(_child_text(raw["checkout_root"], 32_767)).resolve()
            account_root = Path(_child_text(raw["account_root"], 32_767)).resolve()
            profile_root = Path(_child_text(raw["profile_root"], 32_767)).resolve()
            job_root = Path(_child_text(raw["job_root"], 32_767)).resolve()
            output_root = Path(_child_text(raw["output_root"], 32_767)).resolve()
            content_remote_id = _child_text(raw["content_remote_id"], 512)
            author_remote_id = _child_text(raw["author_remote_id"], 255)
            detail_value = raw["detail_reference"]
            detail_reference = None if detail_value is None else _child_text(detail_value, 4_096)
            creator_value = raw["creator_reference"]
            creator_reference = None if creator_value is None else _child_text(creator_value, 4_096)
            creator_max_items = raw["creator_max_items"]
            cookie_value = raw["cookie"]
            cookie = None if cookie_value is None else _child_text(cookie_value, MAX_SECRET_BYTES)
            watchdog_values = raw["watchdogs"]
            if not isinstance(watchdog_values, Mapping) or set(watchdog_values) != {
                "max_seconds",
                "max_output_bytes",
                "max_output_items",
                "max_output_files",
                "max_line_bytes",
                "poll_seconds",
            }:
                raise _ChildConfigurationError
            watchdogs = WatchdogLimits(**dict(watchdog_values))
            delay = raw["request_delay_seconds"]
            if isinstance(delay, bool) or not isinstance(delay, int | float) or not 0 < float(delay) <= 60:
                raise _ChildConfigurationError
            headless = raw["headless"]
            if not isinstance(headless, bool):
                raise _ChildConfigurationError
            bili_progressive_detail = raw["bili_progressive_detail"]
            if not isinstance(bili_progressive_detail, bool) or (
                bili_progressive_detail and platform is not Platform.BILI
            ):
                raise _ChildConfigurationError
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise _ChildConfigurationError from exc
        if platform not in _SUPPORTED_PLATFORMS or login_method is LoginMethod.PHONE:
            raise _ChildConfigurationError
        if (login_method is LoginMethod.COOKIE) != (cookie is not None):
            raise _ChildConfigurationError
        if platform is Platform.XHS:
            try:
                if detail_reference is not None:
                    if creator_reference is not None or creator_max_items is not None:
                        raise ValueError
                    validate_xhs_detail_reference(detail_reference, content_remote_id)
                else:
                    if creator_reference is None:
                        raise ValueError
                    if type(creator_max_items) is not int or not 1 <= creator_max_items <= 1_000:
                        raise ValueError
                    if creator_max_items > watchdogs.max_output_items:
                        raise ValueError
                    validate_xhs_creator_reference(creator_reference, author_remote_id)
            except ValueError as exc:
                raise _ChildConfigurationError from exc
        elif creator_reference is not None or creator_max_items is not None or detail_reference is None:
            raise _ChildConfigurationError
        if platform is Platform.WB and not _is_weibo_detail_reference(detail_reference, content_remote_id):
            raise _ChildConfigurationError
        if bili_progressive_detail and content_remote_id != detail_reference:
            raise _ChildConfigurationError
        if profile_root.parent.parent != account_root or output_root.parent != job_root:
            raise _ChildConfigurationError
        if checkout_root != Path.cwd().resolve():
            raise _ChildConfigurationError
        return cls(
            checkout_root=checkout_root,
            account_root=account_root,
            profile_root=profile_root,
            job_root=job_root,
            output_root=output_root,
            platform=platform,
            login_method=login_method,
            content_remote_id=content_remote_id,
            author_remote_id=author_remote_id,
            detail_reference=detail_reference,
            creator_reference=creator_reference,
            creator_max_items=creator_max_items,
            cookie=cookie,
            headless=headless,
            request_delay_seconds=float(delay),
            bili_progressive_detail=bili_progressive_detail,
            watchdogs=watchdogs,
        )


def _child_text(value: object, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\0" in value:
        raise _ChildConfigurationError
    return value


@contextlib.contextmanager
def _silenced_upstream() -> Iterator[None]:
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


def _configure_upstream(config: Any, request: _ChildRequest) -> None:
    profile_parent = request.profile_root.parent
    profile_parent.mkdir(parents=True, exist_ok=True)
    template = f"{str(profile_parent).replace('%', '%%')}{os.sep}%s_user_data_dir"
    calculated_profile = Path(
        os.path.join(request.checkout_root, "browser_data", template % request.platform.value)
    ).resolve()
    if calculated_profile != request.profile_root:
        raise _ChildConfigurationError
    if request.login_method is LoginMethod.SAVED_SESSION and (
        not request.profile_root.is_dir() or not any(request.profile_root.iterdir())
    ):
        raise _ChildAuthExpiredError

    config.PLATFORM = request.platform.value
    config.LOGIN_TYPE = upstream_login_type(request.login_method)
    config.COOKIES = request.cookie or ""
    config.SAVE_DATA_PATH = str(request.output_root)
    config.USER_DATA_DIR = template
    config.START_PAGE = 1
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
    config.CRAWLER_MAX_SLEEP_SEC = request.request_delay_seconds
    headless = True if request.login_method is LoginMethod.SAVED_SESSION else request.headless
    config.HEADLESS = headless
    config.CDP_HEADLESS = headless
    config.AUTO_CLOSE_BROWSER = True
    config.XHS_INTERNATIONAL = False
    config.DISABLE_SSL_VERIFY = False
    for attribute in CREATOR_CONFIG_ATTRIBUTES.values():
        setattr(config, attribute, [])
    for attribute in _DETAIL_CONFIG_ATTRIBUTES.values():
        setattr(config, attribute, [])
    if request.platform is Platform.XHS and request.creator_reference is not None:
        if request.creator_max_items is None:
            raise _ChildConfigurationError
        config.CRAWLER_TYPE = "creator"
        config.CREATOR_MODE = True
        config.CRAWLER_MAX_NOTES_COUNT = request.creator_max_items
        config.XHS_CREATOR_ID_LIST = [request.creator_reference]
    else:
        if request.detail_reference is None:
            raise _ChildConfigurationError
        config.CRAWLER_TYPE = "detail"
        config.CREATOR_MODE = False
        config.CRAWLER_MAX_NOTES_COUNT = 1
        setattr(config, _DETAIL_CONFIG_ATTRIBUTES[request.platform], [request.detail_reference])


def _positive_bili_id(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("invalid Bilibili identity")
    return value


def _first_bili_cid(view: Mapping[str, object]) -> int:
    if "pages" in view:
        pages = view["pages"]
        if pages is None or pages == []:
            return _positive_bili_id(view.get("cid"))
        if not isinstance(pages, list) or not isinstance(pages[0], Mapping):
            raise ValueError("invalid Bilibili pages")
        return _positive_bili_id(pages[0].get("cid"))
    return _positive_bili_id(view.get("cid"))


def _bili_progressive_result(play: object, *, aid: int, cid: int) -> _BiliProgressiveResult:
    if not isinstance(play, Mapping):
        raise ValueError("invalid Bilibili play response")
    if "durl" not in play or play.get("durl") is None:
        raise _ChildUnsupportedError
    durl = play["durl"]
    if not isinstance(durl, list):
        raise ValueError("invalid Bilibili durl response")
    if len(durl) != 1:
        raise _ChildUnsupportedError
    segment = durl[0]
    if not isinstance(segment, Mapping) or not isinstance(segment.get("url"), str):
        raise ValueError("invalid Bilibili durl segment")
    return _BiliProgressiveResult(aid=aid, cid=cid, url=segment["url"])


async def _run_bilibili_aid(upstream_main: Any, request: _ChildRequest) -> _BiliProgressiveResult | None:
    """Use the pinned client's aid-capable detail entry when discovery stored av."""

    crawler = upstream_main.CrawlerFactory.create_crawler(platform=request.platform.value)
    if request.detail_reference is None:
        raise _ChildConfigurationError
    try:
        requested_aid = int(request.detail_reference)
    except ValueError as exc:
        raise _ChildConfigurationError from exc
    if requested_aid <= 0 or requested_aid > 2**63 - 1 or str(requested_aid) != request.detail_reference:
        raise _ChildConfigurationError
    progressive: _BiliProgressiveResult | None = None
    callback_called = False

    async def get_specified_videos(instance: Any, _references: list[str]) -> None:
        nonlocal callback_called, progressive
        callback_called = True
        semaphore = asyncio.Semaphore(1)
        detail = await instance.get_video_info_task(
            aid=requested_aid,
            bvid="",
            semaphore=semaphore,
        )
        if detail is None:
            if request.bili_progressive_detail:
                raise _ChildTemporaryError
            return
        if not isinstance(detail, Mapping) or not isinstance(detail.get("View"), Mapping):
            raise ValueError("invalid Bilibili detail response")
        view = detail["View"]
        returned_aid = _positive_bili_id(view.get("aid"))
        if returned_aid != requested_aid:
            raise ValueError("Bilibili aid mismatch")
        store = importlib.import_module("store.bilibili")
        await store.update_bilibili_video(detail)
        await store.update_up_info(detail)
        if request.bili_progressive_detail:
            cid = _first_bili_cid(view)
            try:
                play = await instance.get_video_play_url_task(
                    aid=requested_aid,
                    cid=cid,
                    semaphore=semaphore,
                )
            except Exception as exc:
                raise _ChildTemporaryError from exc
            if play is None:
                raise _ChildTemporaryError
            progressive = _bili_progressive_result(play, aid=requested_aid, cid=cid)

    crawler.get_specified_videos = MethodType(get_specified_videos, crawler)
    upstream_main.crawler = crawler
    await crawler.start()
    if not callback_called:
        raise RuntimeError("Bilibili detail callback did not run")
    return progressive


async def _run_upstream(request: _ChildRequest) -> tuple[Any, _BiliProgressiveResult | None]:
    os.chdir(request.checkout_root)
    if str(request.checkout_root) not in sys.path:
        sys.path.insert(0, str(request.checkout_root))
    importlib.invalidate_caches()
    if "config" in sys.modules or "main" in sys.modules:
        raise _ChildConfigurationError
    sys.argv = ["mediacrawler"]
    config = importlib.import_module("config")
    if not _module_belongs_to_checkout(config, request.checkout_root):
        raise _ChildConfigurationError
    _configure_upstream(config, request)
    upstream_main = importlib.import_module("main")
    if not _module_belongs_to_checkout(upstream_main, request.checkout_root):
        raise _ChildConfigurationError
    if request.platform is Platform.WB:
        install_weibo_media_capture(request.checkout_root)

    async def dispatch() -> _BiliProgressiveResult | None:
        if (
            request.platform is Platform.BILI
            and request.detail_reference is not None
            and request.detail_reference.isdigit()
        ):
            return await _run_bilibili_aid(upstream_main, request)
        await upstream_main.main()
        return None

    try:
        if request.login_method is LoginMethod.SAVED_SESSION:
            from media_sync.integrations.mediacrawler.login_runner import (
                fence_saved_session_qr_fallback,
            )

            with fence_saved_session_qr_fallback(request.platform):
                progressive = await dispatch()
        else:
            progressive = await dispatch()
    except SystemExit as error:
        raise RuntimeError("upstream exited without a successful result") from error
    return upstream_main, progressive


async def _watch_upstream(request: _ChildRequest) -> tuple[Any, _BiliProgressiveResult | None]:
    deadline = time.monotonic() + request.watchdogs.max_seconds
    task = asyncio.create_task(_run_upstream(request))
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            done, _pending = await asyncio.wait(
                {task},
                timeout=min(request.watchdogs.poll_seconds, remaining),
            )
            inspect_output(request.output_root, request.watchdogs)
            if task in done:
                return await task
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(task, timeout=min(5.0, request.watchdogs.max_seconds * 0.1))


def _read_content_jsonl(request: _ChildRequest) -> bytes:
    inspect_output(request.output_root, request.watchdogs)
    payload = bytearray()
    for path in sorted(request.output_root.rglob("*.jsonl")):
        if "_contents_" not in path.name and not path.name.startswith("contents"):
            continue
        data = path.read_bytes()
        payload.extend(data)
        if data and not data.endswith(b"\n"):
            payload.extend(b"\n")
        if len(payload) > request.watchdogs.max_output_bytes:
            raise ValueError("detail payload exceeds output limit")
    return bytes(payload)


def _augment_bili_progressive_jsonl(
    payload: bytes,
    progressive: _BiliProgressiveResult,
    limits: WatchdogLimits,
) -> bytes:
    """Inject one private field into bytes only; never reopen or rewrite output."""

    lines = payload.splitlines()
    if len(lines) > limits.max_output_items:
        raise ValueError("detail payload exceeds record limit")
    output = bytearray()
    matches = 0
    for raw_line in lines:
        if len(raw_line) + 1 > limits.max_line_bytes:
            raise ValueError("detail payload exceeds line limit")
        encoded = raw_line
        if raw_line.strip():
            try:
                decoded = json.loads(
                    raw_line,
                    object_pairs_hook=_strict_object,
                    parse_constant=_reject_json_constant,
                )
            except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError("invalid detail JSONL") from exc
            if not isinstance(decoded, Mapping):
                raise ValueError("invalid detail JSONL record")
            if _contains_private_detail_field(decoded):
                raise ValueError("private detail field collision")
            if decoded.get("video_id") == str(progressive.aid):
                matches += 1
                enriched = dict(decoded)
                enriched[_BILI_PROGRESSIVE_FIELD] = progressive.url
                encoded = json.dumps(
                    enriched,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                if len(encoded) + 1 > limits.max_line_bytes:
                    raise ValueError("detail payload exceeds line limit")
        output.extend(encoded)
        output.extend(b"\n")
        if len(output) > limits.max_output_bytes:
            raise ValueError("detail payload exceeds output limit")
    if matches != 1:
        raise ValueError("Bilibili detail record mismatch")
    return bytes(output)


def _contains_private_detail_field(value: object) -> bool:
    if isinstance(value, Mapping):
        return _BILI_PROGRESSIVE_FIELD in value or any(_contains_private_detail_field(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_private_detail_field(item) for item in value)
    return False


async def _execute_child(request: _ChildRequest) -> tuple[str, bytes]:
    upstream_main: Any | None = None
    try:
        upstream_main, progressive = await _watch_upstream(request)
        payload = _read_content_jsonl(request)
        if request.bili_progressive_detail:
            if progressive is None:
                raise _ChildTemporaryError
            else:
                payload = _augment_bili_progressive_jsonl(payload, progressive, request.watchdogs)
        elif progressive is not None:
            raise ValueError("unexpected Bilibili progressive result")
        return "succeeded", payload
    except _ChildConfigurationError:
        return "configuration_invalid", b""
    except _ChildAuthExpiredError:
        return "auth_expired", b""
    except _ChildTemporaryError:
        return "temporary", b""
    except _ChildUnsupportedError:
        return "unsupported", b""
    except TimeoutError:
        return "temporary", b""
    except Exception as error:
        if request.login_method is LoginMethod.SAVED_SESSION:
            from media_sync.integrations.mediacrawler.login_runner import (
                SavedSessionQrFallbackBlocked,
            )

            if isinstance(error, SavedSessionQrFallbackBlocked):
                return "auth_expired", b""
        return "result_invalid", b""
    finally:
        cleanup_module = upstream_main or sys.modules.get("main")
        if cleanup_module is not None and _module_belongs_to_checkout(cleanup_module, request.checkout_root):
            config = sys.modules.get("config")
            if config is not None:
                config.__dict__["COOKIES"] = ""
            cleanup = getattr(cleanup_module, "async_cleanup", None)
            if callable(cleanup):
                with contextlib.suppress(asyncio.TimeoutError, Exception):
                    await asyncio.wait_for(cleanup(), timeout=5.0)


def _emit_child_frame(status: str, payload: bytes = b"") -> None:
    encoded = json.dumps(
        {
            "schema_version": DETAIL_RUNNER_SCHEMA_VERSION,
            "status": status,
            "payload": base64.b64encode(payload).decode("ascii"),
        },
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _child_entry() -> int:
    try:
        payload = sys.stdin.buffer.read(MAX_DETAIL_REQUEST_BYTES + 1)
        if len(payload) > MAX_DETAIL_REQUEST_BYTES:
            raise _ChildConfigurationError
        request = _ChildRequest.load(payload)
        payload = b""
        with _silenced_upstream():
            status, output = asyncio.run(_execute_child(request))
    except Exception:
        status, output = "configuration_invalid", b""
    _emit_child_frame(status, output)
    return 0 if status == "succeeded" else 20


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "--child":
        raise SystemExit(20)
    raise SystemExit(_child_entry())


__all__ = [
    "DETAIL_RUNNER_SCHEMA_VERSION",
    "MediaCrawlerDetailPayloadRunner",
    "MediaCrawlerDetailProcessRunner",
    "MediaCrawlerDetailRequest",
    "MediaCrawlerDetailResult",
]
