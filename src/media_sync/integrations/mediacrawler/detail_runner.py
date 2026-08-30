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
import signal
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
from media_sync.integrations.mediacrawler.policies import (
    RunPaths,
    WatchdogLimits,
    build_run_paths,
    inspect_output,
    upstream_login_type,
)
from media_sync.integrations.mediacrawler.runner import _AccountFileLock
from media_sync.media.errors import MediaDownloadError
from media_sync.security import SecretValue
from media_sync.security.secrets import MAX_SECRET_BYTES

DETAIL_RUNNER_SCHEMA_VERSION = 1
MAX_DETAIL_REQUEST_BYTES = 128 * 1024
MAX_DETAIL_FRAME_OVERHEAD = 8 * 1024

_SUPPORTED_PLATFORMS = frozenset({Platform.XHS, Platform.DY, Platform.KS, Platform.BILI})
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


@dataclass(frozen=True, slots=True)
class MediaCrawlerDetailRequest:
    """One frozen, account-bound detail lookup with no database dependency."""

    account_id: UUID
    subscription_id: UUID
    platform: Platform
    login_method: LoginMethod
    content_remote_id: str
    detail_reference: str | SecretValue | None = field(default=None, repr=False)
    cookie: SecretValue | None = field(default=None, repr=False)
    headless: bool = True
    request_delay_seconds: float = 2.0
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
        if platform not in _SUPPORTED_PLATFORMS or login_method is LoginMethod.PHONE:
            raise MediaDownloadError("locator_refresh_unsupported")
        if self.detail_reference is not None and not isinstance(self.detail_reference, str | SecretValue):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if isinstance(self.detail_reference, str):
            _bounded_text(self.detail_reference, maximum=4_096)
        if login_method is LoginMethod.COOKIE and self.cookie is None:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if login_method is not LoginMethod.COOKIE and self.cookie is not None:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if not isinstance(self.headless, bool):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        delay = self.request_delay_seconds
        if isinstance(delay, bool) or not isinstance(delay, int | float) or not 0 < float(delay) <= 60:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        object.__setattr__(self, "platform", platform)
        object.__setattr__(self, "login_method", login_method)
        object.__setattr__(self, "content_remote_id", content_remote_id)
        object.__setattr__(self, "request_delay_seconds", float(delay))

    def resolved_detail_reference(self) -> str:
        """Reveal an explicit reference only at the child-request boundary."""

        value = self.detail_reference
        if isinstance(value, SecretValue):
            return _bounded_text(value.reveal(), maximum=4_096)
        if isinstance(value, str):
            return _bounded_text(value, maximum=4_096)
        return self.content_remote_id


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
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
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
                "detail_reference": request.resolved_detail_reference(),
                "cookie": cookie,
                "headless": request.headless,
                "request_delay_seconds": request.request_delay_seconds,
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

        cleanup_reserve = max(5.0, min(15.0, limits.max_seconds * 0.1))
        try:
            frame, _stderr = process.communicate(child_payload, timeout=limits.max_seconds + cleanup_reserve)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_tree(process)
            with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                process.communicate(timeout=2)
            raise MediaDownloadError("locator_refresh_temporary") from exc
        finally:
            child_payload = b""

        maximum_frame = ((limits.max_output_bytes + 2) // 3 * 4) + MAX_DETAIL_FRAME_OVERHEAD
        if len(frame) > maximum_frame:
            raise MediaDownloadError("locator_refresh_result_invalid")
        status, payload = _parse_child_frame(frame)
        if process.returncode != 0 or status != "succeeded":
            code = {
                "configuration_invalid": "locator_refresh_configuration_invalid",
                "temporary": "locator_refresh_temporary",
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
    if status not in {"succeeded", "configuration_invalid", "temporary", "result_invalid"}:
        raise MediaDownloadError("locator_refresh_result_invalid")
    if not isinstance(status, str) or not isinstance(payload, str):
        raise MediaDownloadError("locator_refresh_result_invalid")
    return status, payload


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                ("taskkill.exe", "/PID", str(process.pid), "/T", "/F"),
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    else:
        kill_process_group = getattr(os, "killpg", None)
        if callable(kill_process_group):
            with contextlib.suppress(OSError):
                kill_process_group(process.pid, int(getattr(signal, "SIGKILL", signal.SIGTERM)))
    with contextlib.suppress(OSError):
        process.kill()


class _ChildConfigurationError(RuntimeError):
    """A private child request is invalid; its text never crosses the process."""


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
    detail_reference: str = field(repr=False)
    cookie: str | None = field(default=None, repr=False)
    headless: bool = True
    request_delay_seconds: float = 2.0
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
            "detail_reference",
            "cookie",
            "headless",
            "request_delay_seconds",
            "watchdogs",
        }
        if not isinstance(raw, Mapping) or set(raw) != expected or raw.get("schema_version") != 1:
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
            detail_reference = _child_text(raw["detail_reference"], 4_096)
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
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise _ChildConfigurationError from exc
        if platform not in _SUPPORTED_PLATFORMS or login_method is LoginMethod.PHONE:
            raise _ChildConfigurationError
        if (login_method is LoginMethod.COOKIE) != (cookie is not None):
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
            detail_reference=detail_reference,
            cookie=cookie,
            headless=headless,
            request_delay_seconds=float(delay),
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
        raise _ChildConfigurationError

    config.PLATFORM = request.platform.value
    config.LOGIN_TYPE = upstream_login_type(request.login_method)
    config.CRAWLER_TYPE = "detail"
    config.COOKIES = request.cookie or ""
    config.SAVE_DATA_PATH = str(request.output_root)
    config.USER_DATA_DIR = template
    config.START_PAGE = 1
    config.CRAWLER_MAX_NOTES_COUNT = 1
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
    config.HEADLESS = request.headless
    config.CDP_HEADLESS = request.headless
    config.AUTO_CLOSE_BROWSER = True
    config.CREATOR_MODE = False
    config.XHS_INTERNATIONAL = False
    config.DISABLE_SSL_VERIFY = False
    for attribute in _DETAIL_CONFIG_ATTRIBUTES.values():
        setattr(config, attribute, [])
    setattr(config, _DETAIL_CONFIG_ATTRIBUTES[request.platform], [request.detail_reference])


async def _run_bilibili_aid(upstream_main: Any, request: _ChildRequest) -> None:
    """Use the pinned client's aid-capable detail entry when discovery stored av."""

    crawler = upstream_main.CrawlerFactory.create_crawler(platform=request.platform.value)

    async def get_specified_videos(instance: Any, _references: list[str]) -> None:
        semaphore = asyncio.Semaphore(1)
        detail = await instance.get_video_info_task(
            aid=int(request.detail_reference),
            bvid="",
            semaphore=semaphore,
        )
        if detail is None:
            return
        store = importlib.import_module("store.bilibili")
        await store.update_bilibili_video(detail)
        await store.update_up_info(detail)

    crawler.get_specified_videos = MethodType(get_specified_videos, crawler)
    upstream_main.crawler = crawler
    await crawler.start()


async def _run_upstream(request: _ChildRequest) -> Any:
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
    if request.platform is Platform.BILI and request.detail_reference.isdigit():
        await _run_bilibili_aid(upstream_main, request)
    else:
        await upstream_main.main()
    return upstream_main


async def _watch_upstream(request: _ChildRequest) -> Any:
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


async def _execute_child(request: _ChildRequest) -> tuple[str, bytes]:
    upstream_main: Any | None = None
    try:
        upstream_main = await _watch_upstream(request)
        return "succeeded", _read_content_jsonl(request)
    except _ChildConfigurationError:
        return "configuration_invalid", b""
    except TimeoutError:
        return "temporary", b""
    except Exception:
        return "result_invalid", b""
    finally:
        if upstream_main is not None:
            config = sys.modules.get("config")
            if config is not None:
                config.__dict__["COOKIES"] = ""
            cleanup = getattr(upstream_main, "async_cleanup", None)
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
