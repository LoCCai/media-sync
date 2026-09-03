"""Supervised, login-only execution against the pinned MediaCrawler checkout."""

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
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MethodType
from typing import Any
from uuid import UUID, uuid4

# An isolated child starts with only this script directory on ``sys.path``.
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler.checkout import (
    VerifiedCheckout,
    VerifiedPython,
    verify_mediacrawler_checkout,
    verify_mediacrawler_python,
)
from media_sync.integrations.mediacrawler.login import (
    MediaCrawlerLoginMode,
    MediaCrawlerLoginRequest,
    MediaCrawlerLoginResult,
    MediaCrawlerLoginStatus,
)
from media_sync.integrations.mediacrawler.policies import (
    CREATOR_CONFIG_ATTRIBUTES,
    RunPaths,
    build_run_paths,
)
from media_sync.integrations.mediacrawler.runner import (
    _CONTROL_ENV,
    _CONTROL_START,
    _CONTROL_VERSION,
    _COOPERATIVE_STOP_SECONDS,
    AttemptCleanupStatus,
    _AccountFileLock,
    _close_control,
    _close_process_tree,
    _read_control_chunk,
    _read_control_message,
    _stop_child,
    _watch_parent_control,
    _WindowsJob,
    cleanup_attempt_root,
)

LOGIN_RUNNER_SCHEMA_VERSION = 1
LOGIN_ONLY_CRAWLER_TYPE = "media_sync_login_only"
MAX_LOGIN_REQUEST_BYTES = 64 * 1024
MAX_LOGIN_RESULT_BYTES = 4 * 1024
LOGIN_QR_IMAGE_NAME = "login-qr.png"
_MAX_QR_IMAGE_BYTES = 2 * 1024 * 1024
_LOGIN_REQUEST_LENGTH_BYTES = 4
_LOGIN_RESULT_LENGTH_BYTES = 4
_LOGIN_CONTROL_POLL_SECONDS = 0.02

_CHILD_ENV_ALLOWLIST = frozenset(
    {
        "APPDATA",
        "COMSPEC",
        "DISPLAY",
        "HOMEDRIVE",
        "HOMEPATH",
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
_CLIENT_FACTORY_NAMES = {
    Platform.XHS: "create_xhs_client",
    Platform.DY: "create_douyin_client",
    Platform.KS: "create_ks_client",
    Platform.BILI: "create_bilibili_client",
    Platform.WB: "create_weibo_client",
    Platform.TIEBA: "create_tieba_client",
    Platform.ZHIHU: "create_zhihu_client",
}
_LOGIN_CLASSES = {
    Platform.XHS: ("media_platform.xhs.core", "XiaoHongShuLogin"),
    Platform.DY: ("media_platform.douyin.core", "DouYinLogin"),
    Platform.KS: ("media_platform.kuaishou.core", "KuaishouLogin"),
    Platform.BILI: ("media_platform.bilibili.core", "BilibiliLogin"),
    Platform.WB: ("media_platform.weibo.core", "WeiboLogin"),
    Platform.TIEBA: ("media_platform.tieba.core", "BaiduTieBaLogin"),
    Platform.ZHIHU: ("media_platform.zhihu.core", "ZhiHuLogin"),
}
_CONTENT_CONFIG_ATTRIBUTES = (
    "XHS_SPECIFIED_NOTE_URL_LIST",
    "DY_SPECIFIED_ID_LIST",
    "KS_SPECIFIED_ID_LIST",
    "BILI_SPECIFIED_ID_LIST",
    "WEIBO_SPECIFIED_ID_LIST",
    "TIEBA_SPECIFIED_ID_LIST",
    "ZHIHU_SPECIFIED_ID_LIST",
)
_CHILD_STATUSES = frozenset(
    {
        MediaCrawlerLoginStatus.AUTHENTICATED,
        MediaCrawlerLoginStatus.CANCELLED,
        MediaCrawlerLoginStatus.EXPIRED,
        MediaCrawlerLoginStatus.FAILED,
        MediaCrawlerLoginStatus.CONFIGURATION_INVALID,
    }
)

CheckoutVerifier = Callable[[Path, bool], VerifiedCheckout]
PythonVerifier = Callable[[Path], VerifiedPython]


def _default_checkout_verifier(lock_path: Path, license_acknowledged: bool) -> VerifiedCheckout:
    return verify_mediacrawler_checkout(lock_path, license_acknowledged=license_acknowledged)


class MediaCrawlerLoginProcessRunner:
    """Run one exact interactive login or non-interactive saved-session probe."""

    def __init__(
        self,
        *,
        lock_path: Path,
        integration_root: Path,
        python_executable: Path,
        enabled: bool,
        license_acknowledged: bool,
        checkout_verifier: CheckoutVerifier = _default_checkout_verifier,
        python_verifier: PythonVerifier = verify_mediacrawler_python,
    ) -> None:
        if not isinstance(enabled, bool) or not isinstance(license_acknowledged, bool):
            raise TypeError("MediaCrawler gates must be booleans")
        self._lock_path = lock_path.expanduser().resolve()
        self._integration_root = integration_root.expanduser().resolve()
        self._python_executable = python_executable.expanduser().resolve()
        self._enabled = enabled
        self._license_acknowledged = license_acknowledged
        self._checkout_verifier = checkout_verifier
        self._python_verifier = python_verifier

    def run(
        self,
        request: MediaCrawlerLoginRequest,
        *,
        on_account_locked: Callable[[], None] | None = None,
        cancellation: threading.Event | None = None,
    ) -> MediaCrawlerLoginResult:
        """Hold exact profile ownership from the optional state hook through tree join."""

        if not isinstance(request, MediaCrawlerLoginRequest):
            raise TypeError("request must be a MediaCrawlerLoginRequest")
        if on_account_locked is not None and not callable(on_account_locked):
            raise TypeError("on_account_locked must be callable")
        if cancellation is not None and not isinstance(cancellation, threading.Event):
            raise TypeError("cancellation must be a threading.Event")
        if not self._enabled or not self._license_acknowledged:
            return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.CONFIGURATION_INVALID)

        try:
            checkout = self._checkout_verifier(self._lock_path, self._license_acknowledged)
            runtime = self._python_verifier(self._python_executable)
            paths = self._prepare_paths(request)
        except Exception:
            return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.CONFIGURATION_INVALID)

        account_lock = _AccountFileLock(paths.account_root)
        if not account_lock.acquire():
            return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.ACCOUNT_BUSY, checkout.commit)
        result = MediaCrawlerLoginResult(MediaCrawlerLoginStatus.RESULT_INVALID, checkout.commit)
        cleanup_status = AttemptCleanupStatus.UNRESOLVED
        try:
            if cancellation is not None and cancellation.is_set():
                result = MediaCrawlerLoginResult(MediaCrawlerLoginStatus.CANCELLED, checkout.commit)
            elif request.mode is MediaCrawlerLoginMode.SAVED_SESSION_PROBE and not _profile_is_present(
                paths.profile_root
            ):
                result = MediaCrawlerLoginResult(MediaCrawlerLoginStatus.EXPIRED, checkout.commit)
            else:
                if on_account_locked is not None:
                    on_account_locked()
                if cancellation is not None and cancellation.is_set():
                    result = MediaCrawlerLoginResult(MediaCrawlerLoginStatus.CANCELLED, checkout.commit)
                else:
                    payload = _child_payload(request, checkout, paths)
                    result = self._execute(
                        runtime.executable,
                        checkout.root,
                        payload,
                        request,
                        account_lock.descriptor,
                        cancellation,
                        checkout.commit,
                    )
        finally:
            with contextlib.suppress(OSError):
                (paths.account_root / LOGIN_QR_IMAGE_NAME).unlink(missing_ok=True)
            try:
                cleanup_status = cleanup_attempt_root(paths)
            finally:
                account_lock.release()
        if cleanup_status not in {AttemptCleanupStatus.ABSENT, AttemptCleanupStatus.REMOVED}:
            return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.RESULT_INVALID, checkout.commit)
        return result

    def _prepare_paths(self, request: MediaCrawlerLoginRequest) -> RunPaths:
        self._integration_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            self._integration_root.chmod(0o700)
        execution_id = uuid4()
        paths = build_run_paths(self._integration_root, request.platform, request.account_id, execution_id)
        jobs_root = paths.integration_root / "jobs"
        jobs_root.mkdir(mode=0o700, exist_ok=True)
        paths.account_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        for directory in (paths.integration_root, jobs_root, paths.account_root):
            opened = os.lstat(directory)
            if not stat.S_ISDIR(opened.st_mode) or directory.is_symlink() or directory.resolve() != directory:
                raise OSError("MediaCrawler login root is not a real directory")
            with contextlib.suppress(OSError):
                directory.chmod(0o700)
        return paths

    @staticmethod
    def _execute(
        executable: Path,
        checkout_root: Path,
        payload: bytes,
        request: MediaCrawlerLoginRequest,
        lock_descriptor: int,
        cancellation: threading.Event | None,
        upstream_sha: str,
    ) -> MediaCrawlerLoginResult:
        command = (str(executable), "-I", "-u", "-B", str(Path(__file__).resolve()), "--child")
        environment = {name: value for name, value in os.environ.items() if name.upper() in _CHILD_ENV_ALLOWLIST}
        environment.update(
            {
                _CONTROL_ENV: _CONTROL_VERSION,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
                "PYTHONUNBUFFERED": "1",
            }
        )
        try:
            process = _spawn_login_child(command, checkout_root, environment, lock_descriptor)
        except OSError:
            return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.START_FAILED, upstream_sha)
        finally:
            environment.pop(_CONTROL_ENV, None)

        windows_job = _WindowsJob.attach(process)
        if os.name == "nt" and windows_job is None:
            _stop_child(process, None)
            joined = _close_process_tree(process, None)
            status = MediaCrawlerLoginStatus.START_FAILED if joined else MediaCrawlerLoginStatus.RESULT_INVALID
            return MediaCrawlerLoginResult(status, upstream_sha)

        output: list[bytes | None] = []
        output_complete = threading.Event()

        def read_fixed_frame() -> None:
            stream = process.stdout
            try:
                if stream is None:
                    output.append(None)
                else:
                    length_bytes = stream.read(_LOGIN_RESULT_LENGTH_BYTES)
                    if len(length_bytes) != _LOGIN_RESULT_LENGTH_BYTES:
                        output.append(None)
                    else:
                        length = int.from_bytes(length_bytes, byteorder="big")
                        if not 0 < length <= MAX_LOGIN_RESULT_BYTES:
                            output.append(None)
                        else:
                            frame = stream.read(length)
                            output.append(frame if len(frame) == length else None)
            except OSError:
                output.append(None)
            finally:
                output_complete.set()

        reader = threading.Thread(target=read_fixed_frame, name="media-sync-login-frame", daemon=True)
        tree_closed = False
        disposition: MediaCrawlerLoginStatus | None = None
        remainder: bytes | None = None
        try:
            if cancellation is not None and cancellation.is_set():
                disposition = MediaCrawlerLoginStatus.CANCELLED
                _stop_child(process, windows_job)
                tree_closed = _close_process_tree(process, windows_job)
            elif not _write_login_start(process, payload):
                disposition = MediaCrawlerLoginStatus.START_FAILED
                _stop_child(process, windows_job)
                tree_closed = _close_process_tree(process, windows_job)
            payload = b""
            reader.start()
            started = time.monotonic()
            while disposition is None:
                if cancellation is not None and cancellation.is_set():
                    disposition = MediaCrawlerLoginStatus.CANCELLED
                    _stop_child(process, windows_job)
                    tree_closed = _close_process_tree(process, windows_job)
                    break
                if output_complete.is_set():
                    break
                if time.monotonic() - started >= request.timeout_seconds:
                    disposition = MediaCrawlerLoginStatus.TIMED_OUT
                    _stop_child(process, windows_job)
                    tree_closed = _close_process_tree(process, windows_job)
                    break
                if cancellation is None:
                    output_complete.wait(request.poll_seconds)
                else:
                    cancellation.wait(request.poll_seconds)
        finally:
            payload = b""
            # A complete bounded result frame hands the child to its guardian.
            # Closing control tells that guardian to close its descendant group
            # before this parent releases profile ownership.
            _close_control(process)
            if not tree_closed:
                tree_closed = _close_process_tree(process, windows_job)
            reader.join(timeout=5.0)
            if process.stdout is not None:
                try:
                    if not reader.is_alive():
                        remainder = process.stdout.read(MAX_LOGIN_RESULT_BYTES + 1)
                except OSError:
                    remainder = None
                finally:
                    with contextlib.suppress(OSError):
                        process.stdout.close()

        if not tree_closed or reader.is_alive() or remainder != b"":
            return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.RESULT_INVALID, upstream_sha)
        if disposition is not None:
            return MediaCrawlerLoginResult(disposition, upstream_sha)
        if not output or output[0] is None:
            return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.RESULT_INVALID, upstream_sha)
        try:
            child_status = _parse_child_frame(output[0])
        except ValueError:
            return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.RESULT_INVALID, upstream_sha)
        return MediaCrawlerLoginResult(child_status, upstream_sha)


def _profile_is_present(profile_root: Path) -> bool:
    try:
        opened = os.lstat(profile_root)
        return (
            stat.S_ISDIR(opened.st_mode)
            and not profile_root.is_symlink()
            and profile_root.resolve() == profile_root
            and next(profile_root.iterdir(), None) is not None
        )
    except OSError:
        return False


def _child_payload(
    request: MediaCrawlerLoginRequest,
    checkout: VerifiedCheckout,
    paths: RunPaths,
) -> bytes:
    payload = json.dumps(
        {
            "schema_version": LOGIN_RUNNER_SCHEMA_VERSION,
            "checkout_root": str(checkout.root),
            "integration_root": str(paths.integration_root),
            "account_id": str(request.account_id),
            "execution_id": paths.job_root.name,
            "platform": request.platform.value,
            "mode": request.mode.value,
        },
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    if len(payload) > MAX_LOGIN_REQUEST_BYTES:
        raise ValueError("MediaCrawler login request exceeds its fixed limit")
    return payload


def _login_request_frame(payload: bytes) -> bytes:
    """Encode one exact request without using EOF as its boundary."""

    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_LOGIN_REQUEST_BYTES:
        raise ValueError("MediaCrawler login request has an invalid size")
    return len(payload).to_bytes(_LOGIN_REQUEST_LENGTH_BYTES, byteorder="big") + payload


def _write_login_start(process: subprocess.Popen[bytes], payload: bytes) -> bool:
    """Send the bounded request and START while retaining parent ownership of stdin."""

    stream = process.stdin
    if stream is None or process.poll() is not None:
        return False
    try:
        frame = _login_request_frame(payload)
        if stream.write(frame) != len(frame) or stream.write(_CONTROL_START) != len(_CONTROL_START):
            return False
        stream.flush()
    except (BrokenPipeError, OSError, ValueError):
        return False
    return True


def _spawn_login_child(
    command: tuple[str, ...],
    cwd: Path,
    environment: dict[str, str],
    lock_descriptor: int,
) -> subprocess.Popen[bytes]:
    """Spawn with the account-lock handle inherited until the login child exits."""

    common: dict[str, Any] = {
        "cwd": cwd,
        "env": environment,
        "shell": False,
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name != "nt":
        return subprocess.Popen(command, start_new_session=True, pass_fds=(lock_descriptor,), **common)

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
            command,
            creationflags=(
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            ),
            startupinfo=startup_info,
            **common,
        )
    finally:
        set_handle_inheritable(lock_handle, False)


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _parse_child_frame(frame: bytes) -> MediaCrawlerLoginStatus:
    if not frame or len(frame) > MAX_LOGIN_RESULT_BYTES:
        raise ValueError("invalid child frame size")
    try:
        payload = json.loads(frame.decode("ascii"), object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid child frame") from exc
    if not isinstance(payload, Mapping) or set(payload) != {"schema_version", "status"}:
        raise ValueError("invalid child frame shape")
    if payload.get("schema_version") != LOGIN_RUNNER_SCHEMA_VERSION:
        raise ValueError("invalid child frame schema")
    status_value = payload.get("status")
    if not isinstance(status_value, str):
        raise ValueError("invalid child frame status")
    try:
        status = MediaCrawlerLoginStatus(status_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid child frame status") from exc
    if status not in _CHILD_STATUSES:
        raise ValueError("invalid child frame status")
    return status


class _ChildConfigurationError(RuntimeError):
    """The isolated child rejected paths, modules, or the pinned upstream shape."""


class _LoginAuthenticated(RuntimeError):
    """A client authentication probe or post-login cookie update succeeded."""


class SavedSessionQrFallbackBlocked(RuntimeError):
    """A saved profile would otherwise enter the upstream interactive QR path."""


@dataclass(frozen=True, slots=True)
class _ChildRequest:
    checkout_root: Path
    paths: RunPaths
    platform: Platform
    mode: MediaCrawlerLoginMode

    @classmethod
    def load(cls, payload: bytes) -> _ChildRequest:
        try:
            raw = json.loads(payload.decode("ascii"), object_pairs_hook=_strict_object)
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise _ChildConfigurationError from exc
        expected = {
            "schema_version",
            "checkout_root",
            "integration_root",
            "account_id",
            "execution_id",
            "platform",
            "mode",
        }
        if not isinstance(raw, Mapping) or set(raw) != expected or raw.get("schema_version") != 1:
            raise _ChildConfigurationError
        try:
            checkout_root = Path(_child_text(raw["checkout_root"], 32_767)).resolve()
            integration_root = Path(_child_text(raw["integration_root"], 32_767)).resolve()
            account_id = UUID(_child_text(raw["account_id"], 64))
            execution_id = UUID(_child_text(raw["execution_id"], 64))
            platform = Platform(raw["platform"])
            mode = MediaCrawlerLoginMode(raw["mode"])
            paths = build_run_paths(integration_root, platform, account_id, execution_id)
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise _ChildConfigurationError from exc
        if checkout_root != Path.cwd().resolve():
            raise _ChildConfigurationError
        return cls(checkout_root=checkout_root, paths=paths, platform=platform, mode=mode)


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
    paths = request.paths
    profile_parent = paths.profile_root.parent
    profile_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        profile_parent.chmod(0o700)
    profile_template = f"{str(profile_parent).replace('%', '%%')}{os.sep}%s_user_data_dir"
    calculated_profile = Path(
        os.path.join(request.checkout_root, "browser_data", profile_template % request.platform.value)
    ).resolve()
    if calculated_profile != paths.profile_root:
        raise _ChildConfigurationError

    config.PLATFORM = request.platform.value
    config.LOGIN_TYPE = "qrcode"
    config.CRAWLER_TYPE = LOGIN_ONLY_CRAWLER_TYPE
    config.COOKIES = ""
    config.SAVE_DATA_PATH = str(paths.output_root)
    config.USER_DATA_DIR = profile_template
    config.START_PAGE = 1
    config.KEYWORDS = ""
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
    config.HEADLESS = request.mode is MediaCrawlerLoginMode.SAVED_SESSION_PROBE
    config.CDP_HEADLESS = config.HEADLESS
    config.AUTO_CLOSE_BROWSER = True
    config.CREATOR_MODE = False
    config.XHS_INTERNATIONAL = False
    config.DISABLE_SSL_VERIFY = False
    for attribute in (*CREATOR_CONFIG_ATTRIBUTES.values(), *_CONTENT_CONFIG_ATTRIBUTES):
        setattr(config, attribute, [])


def _install_client_guard(crawler: Any, platform: Platform) -> None:
    factory_name = _CLIENT_FACTORY_NAMES[platform]
    original_factory = getattr(crawler, factory_name, None)
    if not callable(original_factory):
        raise _ChildConfigurationError

    async def guarded_factory(_instance: Any, *args: Any, **kwargs: Any) -> Any:
        client = await original_factory(*args, **kwargs)
        original_pong = getattr(client, "pong", None)
        original_update = getattr(client, "update_cookies", None)
        if not callable(original_pong) or not callable(original_update):
            raise _ChildConfigurationError

        async def guarded_pong(*pong_args: Any, **pong_kwargs: Any) -> Any:
            authenticated = await original_pong(*pong_args, **pong_kwargs)
            if authenticated is True:
                raise _LoginAuthenticated
            if authenticated is not False:
                raise _ChildConfigurationError
            return False

        async def guarded_update(*update_args: Any, **update_kwargs: Any) -> Any:
            await original_update(*update_args, **update_kwargs)
            raise _LoginAuthenticated

        client.pong = guarded_pong
        client.update_cookies = guarded_update
        return client

    setattr(crawler, factory_name, MethodType(guarded_factory, crawler))


@contextlib.contextmanager
def fence_saved_session_qr_fallback(platform: Platform) -> Iterator[None]:
    """Stop a pinned core before ``Login.begin`` can fall back to QR.

    Forward/detail children can reuse this context around ``crawler.start`` and
    map :class:`SavedSessionQrFallbackBlocked` to their fixed auth-expired state.
    """

    platform = Platform(platform)
    module_name, class_name = _LOGIN_CLASSES[platform]
    module = importlib.import_module(module_name)
    login_class = getattr(module, class_name, None)
    original_begin = getattr(login_class, "begin", None)
    if login_class is None or not callable(original_begin):
        raise _ChildConfigurationError

    async def reject_interactive_login(_instance: Any) -> None:
        raise SavedSessionQrFallbackBlocked

    login_class.begin = reject_interactive_login
    try:
        yield
    finally:
        login_class.begin = original_begin


@contextlib.contextmanager
def _disable_qr_export(checkout: Path, qr_relay: Path | None = None) -> Iterator[None]:
    """Keep the QR challenge out of the child terminal and optionally relay it.

    Without a relay destination the pinned ``show_qrcode`` helper becomes a
    no-op so the QR stays inside the headed browser. With a destination the
    exact image bytes are atomically mirrored to that path so a local web
    console can display the challenge while the browser runs on a container
    display. Failures to write never affect the login result.
    """

    utils: Any = importlib.import_module("tools.utils")
    if not _module_belongs_to_checkout(utils, checkout):
        raise _ChildConfigurationError
    original = getattr(utils, "show_qrcode", None)
    if not callable(original):
        raise _ChildConfigurationError

    def keep_qr_in_browser(_value: object) -> None:
        return None

    destination = qr_relay

    def relay_qr_to_file(value: object) -> None:
        if destination is None or not isinstance(value, (bytes, bytearray)) or not value:
            return
        if len(value) > _MAX_QR_IMAGE_BYTES:
            return
        try:
            temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0),
                0o600,
            )
            with os.fdopen(descriptor, "wb") as output:
                output.write(bytes(value))
            os.replace(temporary, destination)
        except OSError:
            return

    utils.show_qrcode = relay_qr_to_file if qr_relay is not None else keep_qr_in_browser
    try:
        yield
    finally:
        utils.show_qrcode = original


async def _run_upstream(request: _ChildRequest) -> MediaCrawlerLoginStatus:
    os.chdir(request.checkout_root)
    if str(request.checkout_root) not in sys.path:
        sys.path.insert(0, str(request.checkout_root))
    importlib.invalidate_caches()
    if "config" in sys.modules or "main" in sys.modules:
        raise _ChildConfigurationError
    sys.argv = ["mediacrawler"]
    config: Any = importlib.import_module("config")
    if not _module_belongs_to_checkout(config, request.checkout_root):
        raise _ChildConfigurationError
    _configure_upstream(config, request)
    upstream_main: Any = importlib.import_module("main")
    if not _module_belongs_to_checkout(upstream_main, request.checkout_root):
        raise _ChildConfigurationError
    crawler = upstream_main.CrawlerFactory.create_crawler(platform=request.platform.value)
    upstream_main.crawler = crawler
    _install_client_guard(crawler, request.platform)
    try:
        qr_fence = (
            fence_saved_session_qr_fallback(request.platform)
            if request.mode is MediaCrawlerLoginMode.SAVED_SESSION_PROBE
            else contextlib.nullcontext()
        )
        with _disable_qr_export(request.checkout_root, request.paths.account_root / LOGIN_QR_IMAGE_NAME), qr_fence:
            await crawler.start()
    except _LoginAuthenticated:
        return MediaCrawlerLoginStatus.AUTHENTICATED
    except SavedSessionQrFallbackBlocked:
        return MediaCrawlerLoginStatus.EXPIRED
    finally:
        config.__dict__["COOKIES"] = ""
        cleanup = getattr(upstream_main, "async_cleanup", None)
        if callable(cleanup):
            with contextlib.suppress(asyncio.TimeoutError, Exception):
                await asyncio.wait_for(cleanup(), timeout=5.0)
    raise _ChildConfigurationError


async def _execute_child(request: _ChildRequest) -> MediaCrawlerLoginStatus:
    return await _execute_controlled_child(request, None)


async def _execute_controlled_child(
    request: _ChildRequest,
    cancellation: threading.Event | None,
) -> MediaCrawlerLoginStatus:
    task: asyncio.Task[MediaCrawlerLoginStatus] | None = None

    async def guarded_upstream() -> MediaCrawlerLoginStatus:
        try:
            return await _run_upstream(request)
        except SystemExit:
            # Several pinned login implementations use ``sys.exit()`` (code
            # zero included) for a failed QR challenge. Keep it inside the
            # task so asyncio cannot promote it to process success.
            return MediaCrawlerLoginStatus.FAILED

    try:
        if cancellation is not None and cancellation.is_set():
            return MediaCrawlerLoginStatus.CANCELLED
        task = asyncio.create_task(guarded_upstream())
        while True:
            if cancellation is not None and cancellation.is_set():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
                return MediaCrawlerLoginStatus.CANCELLED
            done, _pending = await asyncio.wait(
                {task},
                timeout=_LOGIN_CONTROL_POLL_SECONDS,
            )
            if task in done:
                return await task
    except _ChildConfigurationError:
        return MediaCrawlerLoginStatus.CONFIGURATION_INVALID
    except BaseException:
        return MediaCrawlerLoginStatus.FAILED
    finally:
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


def _emit_child_frame(status: MediaCrawlerLoginStatus) -> None:
    payload = json.dumps(
        {"schema_version": LOGIN_RUNNER_SCHEMA_VERSION, "status": status.value},
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    frame = len(payload).to_bytes(_LOGIN_RESULT_LENGTH_BYTES, byteorder="big") + payload
    try:
        remaining = memoryview(frame)
        while remaining:
            written = os.write(1, remaining)
            if written <= 0:
                break
            remaining = remaining[written:]
    except OSError:
        pass
    finally:
        # The parent recognizes the length-delimited frame without waiting for
        # process exit.  Close stdout best-effort while this process deliberately
        # remains alive to retain the inherited account lock.
        with contextlib.suppress(OSError):
            os.close(1)


def _guard_completed_login_tree(
    cancellation: threading.Event,
    parent_lost: threading.Event,
    control_thread: threading.Thread,
    child_windows_job: _WindowsJob | None,
    result_complete: threading.Event,
) -> None:
    """Retain process-tree and lock ownership until the parent closes control."""

    while not parent_lost.is_set():
        control_thread.join()
        if parent_lost.is_set():
            break
        # An explicit CANCEL makes the one-shot watcher return.  Once cleanup
        # has produced its fixed result, synchronously resume watching so a
        # later parent death cannot strand descendants during parent teardown.
        _watch_parent_control(
            cancellation,
            parent_lost,
            child_windows_job,
            result_complete,
        )


def _read_exact_login_input(size: int) -> bytes:
    """Read framing and control through one unbuffered descriptor path."""

    if not 0 <= size <= MAX_LOGIN_REQUEST_BYTES:
        raise _ChildConfigurationError
    value = bytearray()
    while len(value) < size:
        chunk = _read_control_chunk(size - len(value))
        if chunk is None:
            raise _ChildConfigurationError
        value.extend(chunk)
    return bytes(value)


def _read_login_request() -> bytes:
    length_bytes = _read_exact_login_input(_LOGIN_REQUEST_LENGTH_BYTES)
    length = int.from_bytes(length_bytes, byteorder="big")
    if not 0 < length <= MAX_LOGIN_REQUEST_BYTES:
        raise _ChildConfigurationError
    return _read_exact_login_input(length)


def _child_entry() -> int:
    control_version = os.environ.pop(_CONTROL_ENV, None)
    payload = b""
    cancellation: threading.Event | None = None
    parent_lost: threading.Event | None = None
    control_thread: threading.Thread | None = None
    child_windows_job: _WindowsJob | None = None
    result_complete = threading.Event()
    previous_sigterm: Any | None = None
    try:
        if control_version != _CONTROL_VERSION:
            raise _ChildConfigurationError
        payload = _read_login_request()
        if _read_control_message() != _CONTROL_START:
            raise _ChildConfigurationError
        request = _ChildRequest.load(payload)
        payload = b""

        cancellation = threading.Event()
        parent_lost = threading.Event()
        if os.name == "nt":
            child_windows_job = _WindowsJob.attach_current_process()
            if child_windows_job is None:
                raise _ChildConfigurationError
        else:
            get_process_group = getattr(os, "getpgrp", None)
            if not callable(get_process_group) or int(get_process_group()) != os.getpid():
                raise _ChildConfigurationError
            previous_sigterm = signal.getsignal(signal.SIGTERM)

            def request_cancellation(_number: int, _frame: Any) -> None:
                assert cancellation is not None
                cancellation.set()

            signal.signal(signal.SIGTERM, request_cancellation)

        control_thread = threading.Thread(
            target=_watch_parent_control,
            args=(cancellation, parent_lost, child_windows_job, result_complete),
            name="media-sync-login-parent-control",
            daemon=True,
        )
        control_thread.start()
        with _silenced_upstream():
            status = asyncio.run(_execute_controlled_child(request, cancellation))
    except BaseException:
        status = MediaCrawlerLoginStatus.CONFIGURATION_INVALID
    finally:
        payload = b""
        if parent_lost is not None and parent_lost.is_set() and control_thread is not None:
            control_thread.join(timeout=_COOPERATIVE_STOP_SECONDS + 1.0)
    if control_thread is not None:
        # Publish guardian readiness before exposing the complete result frame.
        # A later control EOF (or hard parent death) must take the immediate
        # whole-group path rather than a cooperative child-only exit.
        result_complete.set()
    _emit_child_frame(status)
    if cancellation is not None and parent_lost is not None and control_thread is not None:
        _guard_completed_login_tree(
            cancellation,
            parent_lost,
            control_thread,
            child_windows_job,
            result_complete,
        )
    if previous_sigterm is not None:
        with contextlib.suppress(ValueError):
            signal.signal(signal.SIGTERM, previous_sigterm)
    return 0 if status is MediaCrawlerLoginStatus.AUTHENTICATED else 20


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "--child":
        raise SystemExit(20)
    raise SystemExit(_child_entry())


__all__ = [
    "LOGIN_ONLY_CRAWLER_TYPE",
    "LOGIN_QR_IMAGE_NAME",
    "LOGIN_RUNNER_SCHEMA_VERSION",
    "MediaCrawlerLoginProcessRunner",
    "SavedSessionQrFallbackBlocked",
    "fence_saved_session_qr_fallback",
]
