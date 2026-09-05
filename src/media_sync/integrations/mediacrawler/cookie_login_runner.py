"""Supervised remote self checks; never start a crawler or touch a browser profile."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import math
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler.browser_environment import browser_child_environment
from media_sync.integrations.mediacrawler.checkout import (
    normalize_python_executable,
    verify_mediacrawler_checkout,
    verify_mediacrawler_python,
)
from media_sync.integrations.mediacrawler.cookie_login import (
    COOKIE_LOGIN_PLATFORMS,
    CookieLoginRequest,
    CookieLoginResult,
    cookie_pairs,
    parse_cookie_header,
)
from media_sync.integrations.mediacrawler.creator_profile_runner import (
    _emit,
    _encode,
    _json,
    _read_control_frame,
    _read_stream_frame,
)
from media_sync.integrations.mediacrawler.login_runner import (
    _guard_completed_login_tree,
    _silenced_upstream,
    _spawn_login_child,
)
from media_sync.integrations.mediacrawler.runner import (
    _CONTROL_ENV,
    _CONTROL_START,
    _CONTROL_VERSION,
    _close_process_tree,
    _read_control_message,
    _watch_parent_control,
    _WindowsJob,
)

SCHEMA_VERSION = 1
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESULT_BYTES = 4096
MAX_API_BYTES = 128 * 1024
MAX_CLEANUP_SECONDS = 15.0
_SELF_ENDPOINTS = {
    Platform.BILI: ("bilibili", "BilibiliClient", "https://api.bilibili.com", "/x/web-interface/nav"),
    Platform.WB: ("weibo", "WeiboClient", "https://m.weibo.cn", "/api/config"),
    Platform.XHS: ("xhs", "XiaoHongShuClient", "https://edith.xiaohongshu.com", "/api/sns/web/v1/user/selfinfo"),
    Platform.ZHIHU: ("zhihu", "ZhiHuClient", "https://www.zhihu.com", "/api/v4/me"),
    Platform.TIEBA: ("tieba", "BaiduTieBaClient", "https://tieba.baidu.com", "/mo/q/newmoindex"),
}
_PAGE_ORIGINS = {
    Platform.BILI: "https://www.bilibili.com",
    Platform.WB: "https://m.weibo.cn",
    Platform.XHS: "https://www.xiaohongshu.com",
    Platform.ZHIHU: "https://www.zhihu.com",
    Platform.TIEBA: "https://tieba.baidu.com",
}


def _self_url(platform: Platform) -> str:
    _module, _class, host, path = _SELF_ENDPOINTS[platform]
    return host + path + ("?need_user=1" if platform is Platform.TIEBA else "")


def _result(request: CookieLoginRequest, status: str, sha: str | None = None) -> CookieLoginResult:
    return CookieLoginResult(status, request.account_id, request.platform, request.operation_id, sha)


def _request_payload(request: CookieLoginRequest) -> dict[str, object]:
    return {
        "account_id": str(request.account_id),
        "platform": request.platform.value,
        "operation_id": str(request.operation_id),
        "cookie": request.cookie.reveal(),
    }


def _load_request(raw: Any) -> CookieLoginRequest:
    if type(raw) is not dict or set(raw) != {"account_id", "platform", "operation_id", "cookie"}:
        raise ValueError("cookie_login_frame_invalid")
    for key in ("account_id", "operation_id"):
        if type(raw[key]) is not str or str(UUID(raw[key])) != raw[key]:
            raise ValueError("cookie_login_identity_invalid")
    return CookieLoginRequest(
        UUID(raw["account_id"]),
        Platform(raw["platform"]),
        UUID(raw["operation_id"]),
        parse_cookie_header(raw["cookie"]),
    )


def _result_frame(result: CookieLoginResult) -> bytes:
    return _encode(
        {
            "schema_version": SCHEMA_VERSION,
            "status": result.status,
            "account_id": str(result.account_id),
            "platform": result.platform.value,
            "operation_id": str(result.operation_id),
            "upstream_sha": result.upstream_sha,
        },
        MAX_RESULT_BYTES,
    )


def _parse_result(payload: bytes, request: CookieLoginRequest) -> CookieLoginResult:
    raw = _json(payload, MAX_RESULT_BYTES)
    if (
        set(raw) != {"schema_version", "status", "account_id", "platform", "operation_id", "upstream_sha"}
        or type(raw["schema_version"]) is not int
        or raw["schema_version"] != SCHEMA_VERSION
        or (raw["account_id"], raw["platform"], raw["operation_id"])
        != (str(request.account_id), request.platform.value, str(request.operation_id))
    ):
        raise ValueError("cookie_login_frame_invalid")
    return _result(request, raw["status"], raw["upstream_sha"])


def _deadline(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, float | int) or not math.isfinite(value):
        raise ValueError("cookie_login_budget_invalid")
    if not 0 < value - time.monotonic() <= 45:
        raise ValueError("cookie_login_budget_invalid")
    return float(value)


def _command(mode: str, executable: Path) -> tuple[str, ...]:
    return str(executable), "-I", "-u", "-B", str(Path(__file__).resolve()), mode


class CookieLoginProcessRunner:
    """The service owns the account lock across validation and publication.

    This runner never acquires a second lock and never accesses credentials on
    disk or a browser profile. The held descriptor is inherited by the guardian,
    never serialized to a worker. cleanup_failed must keep the caller's lock held.
    """

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
            raise ValueError("cookie_login_configuration_invalid")
        self._lock_path = lock_path.expanduser().resolve()
        self._integration_root = integration_root.expanduser().resolve()
        self._python_executable = normalize_python_executable(python_executable)
        self._enabled = enabled
        self._license_acknowledged = license_acknowledged

    def run(
        self,
        request: CookieLoginRequest,
        *,
        cancellation: threading.Event | None = None,
    ) -> CookieLoginResult:
        if not isinstance(request, CookieLoginRequest):
            raise TypeError("cookie_login_request_invalid")
        if cancellation is not None and not isinstance(cancellation, threading.Event):
            raise TypeError("cookie_login_cancellation_invalid")
        if not self._enabled or not self._license_acknowledged:
            return _result(request, "configuration_invalid")
        if request.platform not in COOKIE_LOGIN_PLATFORMS:
            return _result(request, "verification_unavailable")
        if cancellation is not None and cancellation.is_set():
            return _result(request, "cancelled")
        deadline = time.monotonic() + request.timeout_seconds
        payload = _encode(
            {
                "schema_version": SCHEMA_VERSION,
                "request": _request_payload(request),
                "deadline": deadline,
                "lock_path": str(self._lock_path),
                "python_executable": str(self._python_executable),
            },
            MAX_REQUEST_BYTES,
        )
        return self._execute(payload, request, deadline, cancellation)

    @staticmethod
    def _execute(
        payload: bytes,
        request: CookieLoginRequest,
        deadline: float,
        cancellation: threading.Event | None,
    ) -> CookieLoginResult:
        environment = browser_child_environment()
        environment.update({_CONTROL_ENV: _CONTROL_VERSION, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
        if request.account_lock_fd is None:
            return _result(request, "configuration_invalid")
        try:
            os.fstat(request.account_lock_fd)
            process = _spawn_login_child(
                _command("--guardian", Path(sys.executable)),
                Path.cwd(),
                environment,
                request.account_lock_fd,
            )
        except OSError:
            return _result(request, "configuration_invalid")
        windows_job = _WindowsJob.attach(process)
        result = _result(request, "result_invalid")
        output: list[bytes | None] = []
        completed, write_failed = threading.Event(), threading.Event()

        def read() -> None:
            try:
                output.append(_read_stream_frame(process.stdout, MAX_RESULT_BYTES))
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

        reader = threading.Thread(target=read, name="media-sync-cookie-frame", daemon=True)
        writer = threading.Thread(target=write, name="media-sync-cookie-input", daemon=True)
        reader_started = writer_started = False
        try:
            reader.start()
            reader_started = True
            if os.name == "nt" and windows_job is None:
                result = _result(request, "configuration_invalid")
            else:
                writer.start()
                writer_started = True
                while not completed.is_set():
                    if cancellation is not None and cancellation.is_set():
                        result = _result(request, "cancelled")
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        result = _result(request, "timed_out")
                        break
                    completed.wait(min(0.05, remaining))
                else:
                    if cancellation is not None and cancellation.is_set():
                        result = _result(request, "cancelled")
                    elif time.monotonic() >= deadline:
                        result = _result(request, "timed_out")
                    elif not write_failed.is_set() and output and output[0] is not None:
                        result = _parse_result(output[0], request)
        except (OSError, ValueError, TypeError, RuntimeError):
            result = _result(request, "result_invalid")
        finally:
            payload = b""
            cleanup_deadline = time.monotonic() + MAX_CLEANUP_SECONDS
            # Kill/join before touching buffered streams: the writer might be
            # blocked in a pipe while holding the stream's internal lock.
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
                result = _result(request, "cleanup_failed")
            elif remainder != b"":
                result = _result(request, "result_invalid")
            elif result.status == "authenticated" and cancellation is not None and cancellation.is_set():
                result = _result(request, "cancelled")
        return result


@dataclass(frozen=True, slots=True)
class _Envelope:
    request: CookieLoginRequest = field(repr=False)
    deadline: float
    lock_path: Path
    python_executable: Path

    @classmethod
    def load(cls, payload: bytes) -> _Envelope:
        raw = _json(payload, MAX_REQUEST_BYTES)
        if (
            set(raw) != {"schema_version", "request", "deadline", "lock_path", "python_executable"}
            or type(raw["schema_version"]) is not int
            or raw["schema_version"] != SCHEMA_VERSION
        ):
            raise ValueError("cookie_login_frame_invalid")
        for key in ("lock_path", "python_executable"):
            if type(raw[key]) is not str or not 0 < len(raw[key]) <= 32767 or "\0" in raw[key]:
                raise ValueError("cookie_login_configuration_invalid")
        return cls(
            _load_request(raw["request"]),
            _deadline(raw["deadline"]),
            Path(raw["lock_path"]),
            Path(raw["python_executable"]),
        )


def _run_guardian(envelope: _Envelope) -> CookieLoginResult:
    request = envelope.request
    try:
        checkout = verify_mediacrawler_checkout(envelope.lock_path, license_acknowledged=True)
        runtime = verify_mediacrawler_python(envelope.python_executable)
        if time.monotonic() >= envelope.deadline:
            return _result(request, "timed_out")
        payload = _encode(
            {
                "schema_version": SCHEMA_VERSION,
                "request": _request_payload(request),
                "deadline": envelope.deadline,
                "checkout_root": str(checkout.root),
                "upstream_sha": checkout.commit,
            },
            MAX_REQUEST_BYTES,
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
        # Worker and any offline signer inherit this guardian's process group/Job.
        if process.stdin is None or process.stdout is None:
            raise ValueError
        process.stdin.write(payload)
        process.stdin.close()
        payload = b""
        frame = _read_stream_frame(process.stdout, MAX_RESULT_BYTES)
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
        return _result(request, "timed_out")
    except Exception:
        return _result(request, "configuration_invalid")


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
        get_group = getattr(os, "getpgrp", None)
        if not callable(get_group) or get_group() != os.getpid():
            return 20
        signal.signal(signal.SIGTERM, lambda *_: cancellation.set())
    watcher = threading.Thread(
        target=_watch_parent_control,
        args=(cancellation, parent_lost, child_job, result_complete),
        daemon=True,
    )
    watcher.start()
    with _silenced_upstream():
        result = _run_guardian(envelope)
    result_complete.set()
    _emit(_result_frame(result))
    _guard_completed_login_tree(cancellation, parent_lost, watcher, child_job, result_complete)
    return 0


class _VerificationFailure(RuntimeError):
    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(status)


def _fetch_json(url: str, headers: Mapping[str, str], deadline: float) -> dict[str, Any]:
    import httpx

    from media_sync.media.network import PinnedHTTPTransport, SocketAddressResolver, validate_target

    if url not in {_self_url(platform) for platform in _SELF_ENDPOINTS}:
        raise _VerificationFailure("result_invalid")
    remaining = min(10.0, deadline - time.monotonic())
    if remaining <= 0:
        raise _VerificationFailure("timed_out")
    target = validate_target(url, SocketAddressResolver(), max_url_chars=4096)
    allowed = {
        "user-agent",
        "cookie",
        "origin",
        "referer",
        "content-type",
        "x-s",
        "x-t",
        "x-s-common",
        "x-b3-traceid",
        "x-zst-81",
        "x-zse-96",
        "x-zse-93",
        "x-api-version",
        "x-app-za",
        "x-requested-with",
    }
    outgoing: dict[str, str] = {}
    for name, value in headers.items():
        if type(name) is not str or name.lower() not in allowed:
            continue
        lowered = name.lower()
        if (
            lowered in outgoing
            or type(value) is not str
            or len(value) > (16384 if lowered == "cookie" else 8192)
            or not value.isascii()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise _VerificationFailure("result_invalid")
        outgoing[lowered] = value
    outgoing.update({"host": target.host_header, "accept": "application/json", "accept-encoding": "identity"})
    with (
        httpx.Client(
            transport=PinnedHTTPTransport(target), trust_env=False, follow_redirects=False, timeout=remaining
        ) as client,
        client.stream("GET", target.url, headers=outgoing) as response,
    ):
        if response.status_code == 401:
            raise _VerificationFailure("rejected")
        if response.status_code != 200:
            raise _VerificationFailure("result_invalid")
        encoding = response.headers.get("content-encoding", "identity").strip().lower()
        content_type = response.headers.get("content-type", "")
        media_type = content_type.partition(";")[0].strip().lower()
        length = response.headers.get("content-length")
        if (
            encoding != "identity"
            or len(content_type) > 128
            or (
                media_type != "application/json"
                and not (media_type.startswith("application/") and media_type.endswith("+json"))
            )
            or (
                length is not None
                and (not length.isascii() or not length.isdigit() or len(length) > 10 or int(length) > MAX_API_BYTES)
            )
        ):
            raise _VerificationFailure("result_invalid")
        payload = bytearray()
        for chunk in response.iter_raw(chunk_size=8192):
            if time.monotonic() >= deadline:
                raise _VerificationFailure("timed_out")
            if len(payload) + len(chunk) > MAX_API_BYTES:
                raise _VerificationFailure("result_invalid")
            payload.extend(chunk)
    return _json(bytes(payload), MAX_API_BYTES)


def _authenticated(platform: Platform, raw: dict[str, Any]) -> None:
    if platform is Platform.BILI:
        if type(raw.get("code")) is int and raw["code"] == -101:
            raise _VerificationFailure("rejected")
        if type(raw.get("code")) is not int or raw["code"] != 0 or type(raw.get("data")) is not dict:
            raise _VerificationFailure("result_invalid")
        flag = raw["data"].get("isLogin")
    elif platform is Platform.WB:
        if type(raw.get("ok")) is not int or raw["ok"] != 1 or type(raw.get("data")) is not dict:
            raise _VerificationFailure("result_invalid")
        flag = raw["data"].get("login")
    elif platform is Platform.XHS:
        if raw.get("success") is False:
            raise _VerificationFailure("rejected")
        if "code" in raw and (type(raw["code"]) is not int or raw["code"] != 0):
            raise _VerificationFailure("rejected")
        data = raw.get("data")
        if not isinstance(data, dict):
            raise _VerificationFailure("result_invalid")
        result = data.get("result")
        if type(result) is not dict:
            raise _VerificationFailure("result_invalid")
        flag = result.get("success")
        if any(data.get(key) is True for key in ("guest", "isGuest", "is_guest")):
            raise _VerificationFailure("rejected")
    elif platform is Platform.ZHIHU:
        if raw.get("error"):
            raise _VerificationFailure("rejected")
        uid, name = raw.get("uid"), raw.get("name")
        valid_uid = (type(uid) is str and 0 < len(uid) <= 128 and uid.isascii() and uid.isalnum()) or (
            type(uid) is int and 0 < uid <= 2**64 - 1
        )
        if not valid_uid or type(name) is not str or not 0 < len(name) <= 512 or not name.isprintable():
            raise _VerificationFailure("result_invalid")
        return
    elif platform is Platform.TIEBA:
        # The immutable current-user ID is supplied by the exact moindex self
        # endpoint, never a caller-selected public profile or local Cookie flag.
        # Unknown remote codes are not evidence that a credential has expired.
        data = raw.get("data")
        if (
            type(raw.get("no")) is not int
            or raw["no"] != 0
            or type(data) is not dict
            or raw.get("error") not in (None, "")
        ):
            raise _VerificationFailure("result_invalid")
        uid, portrait = data.get("id"), data.get("portrait")
        if (
            type(uid) is not int
            or not 0 < uid <= 2**64 - 1
            or type(portrait) is not str
            or re.fullmatch(r"tb\.1\.[A-Za-z0-9._-]{28,31}", portrait, flags=re.ASCII) is None
            or ".." in portrait
            or portrait.endswith(".")
            or any(
                value.get(key) is not False
                for value in (raw, data)
                for key in ("guest", "isGuest", "is_guest")
                if key in value
            )
        ):
            raise _VerificationFailure("result_invalid")
        return
    else:
        raise _VerificationFailure("verification_unavailable")
    if flag is False:
        raise _VerificationFailure("rejected")
    if flag is not True:
        raise _VerificationFailure("result_invalid")


def _origin(module: Any, expected: Path) -> None:
    path = getattr(module, "__file__", None)
    if type(path) is not str or Path(path).resolve() != expected.resolve() or expected.is_symlink():
        raise _VerificationFailure("configuration_invalid")


async def _verify_remote(checkout: Path, request: CookieLoginRequest, deadline: float) -> None:
    module_name, class_name, _host, uri = _SELF_ENDPOINTS[request.platform]
    expected_url = _self_url(request.platform)
    candidate_pairs = cookie_pairs(request.cookie.reveal())
    if request.platform is Platform.TIEBA and not candidate_pairs.get("BDUSS", "").strip('"'):
        raise _VerificationFailure("result_invalid")
    os.chdir(checkout)
    sys.path.insert(0, str(checkout))
    if "config" in sys.modules or f"media_platform.{module_name}.client" in sys.modules:
        raise _VerificationFailure("configuration_invalid")
    config: Any = importlib.import_module("config")
    _origin(config, checkout / "config/__init__.py")
    config.XHS_INTERNATIONAL = False
    config.ENABLE_IP_PROXY = False
    config.COOKIES = ""
    module: Any = importlib.import_module(f"media_platform.{module_name}.client")
    _origin(module, checkout / f"media_platform/{module_name}/client.py")
    utils: Any = importlib.import_module("tools.utils")
    _origin(utils, checkout / "tools/utils.py")
    client_type = getattr(module, class_name, None)
    if not isinstance(client_type, type) or client_type.__module__ != module.__name__:
        raise _VerificationFailure("configuration_invalid")
    if request.platform in {Platform.XHS, Platform.ZHIHU}:
        helper_name = "playwright_sign" if request.platform is Platform.XHS else "help"
        helper: Any = importlib.import_module(f"media_platform.{module_name}.{helper_name}")
        _origin(helper, checkout / f"media_platform/{module_name}/{helper_name}.py")
        if request.platform is Platform.ZHIHU:
            # Node's pipe-based engine keeps the Cookie out of temporary JS
            # files. Never let PyExecJS fall back to Windows JScript or another
            # runtime. The locked help.sign still loads/calls its own script.
            try:
                helper.execjs.compile = helper.execjs.get("Node").compile
            except Exception:
                raise _VerificationFailure("configuration_invalid") from None
    cookie_name = "cookie" if request.platform is Platform.ZHIHU else "Cookie"
    page_origin = _PAGE_ORIGINS[request.platform]
    headers = {
        "User-Agent": utils.get_mobile_user_agent() if request.platform is Platform.WB else utils.get_user_agent(),
        cookie_name: request.cookie.reveal(),
        "Origin": page_origin,
        "Referer": page_origin + "/",
        "Content-Type": "application/json;charset=UTF-8",
    }
    if request.platform is Platform.ZHIHU:
        headers.update(
            {"x-api-version": "3.0.91", "x-app-za": "OS=Web", "x-requested-with": "fetch", "x-zse-93": "101_3_3.0"}
        )
    if request.platform is Platform.TIEBA:
        # This locked client has a distinct constructor and its get() forwards
        # return_ori_content. Do not invoke its retried requests/browser path.
        client = client_type(headers=headers, playwright_page=None, ip_pool=None, default_ip_proxy=None)
    else:
        client = client_type(headers=headers, playwright_page=None, cookie_dict=candidate_pairs, proxy=None)
    calls = 0

    async def remote(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        expected_kwargs = {"headers", "return_ori_content"} if request.platform is Platform.TIEBA else {"headers"}
        if (
            method != "GET"
            or url != expected_url
            or set(kwargs) != expected_kwargs
            or (request.platform is Platform.TIEBA and kwargs["return_ori_content"] is not False)
            or calls != 0
        ):
            raise _VerificationFailure("result_invalid")
        calls += 1
        outgoing = kwargs["headers"]
        if not isinstance(outgoing, Mapping) or outgoing.get(cookie_name) != request.cookie.reveal():
            raise _VerificationFailure("result_invalid")
        raw = await asyncio.to_thread(_fetch_json, url, outgoing, deadline)
        _authenticated(request.platform, raw)
        return raw if request.platform in {Platform.XHS, Platform.ZHIHU, Platform.TIEBA} else raw["data"]

    client.request = remote
    if request.platform is Platform.XHS:
        # query_self bypasses client.request in this exact pinned version. Give
        # its HTTP factory a closed one-call transport, retaining its real
        # endpoint selection and pure-algorithm signature implementation.
        class Response:
            status_code = 200

            def __init__(self, data: dict[str, Any]) -> None:
                self.data = data

            def json(self) -> dict[str, Any]:
                return self.data

        class BoundedClient:
            async def __aenter__(self) -> BoundedClient:
                return self

            async def __aexit__(self, *_args: Any) -> None:
                pass

            async def get(self, url: str, **kwargs: Any) -> Response:
                return Response(await remote("GET", url, **kwargs))

        original = module.make_async_client
        module.make_async_client = lambda **_kwargs: BoundedClient()
        try:
            await client.query_self()
        finally:
            module.make_async_client = original
    elif request.platform is Platform.BILI:
        await client.get(uri, enable_params_sign=False)
    elif request.platform is Platform.TIEBA:
        await client.get(uri, params={"need_user": 1}, headers=headers)
    else:
        # The locked Zhihu get_current_user_info adds email/phone fields. Keep
        # its same self path and real signing/get method without those fields.
        await client.get(uri)
    if calls != 1:
        raise _VerificationFailure("result_invalid")
    if time.monotonic() >= deadline:
        raise _VerificationFailure("timed_out")


def _worker_entry() -> int:
    try:
        raw = _json(_read_control_frame(), MAX_REQUEST_BYTES)
        if (
            set(raw) != {"schema_version", "request", "deadline", "checkout_root", "upstream_sha"}
            or type(raw["schema_version"]) is not int
            or raw["schema_version"] != SCHEMA_VERSION
        ):
            return 20
        request = _load_request(raw["request"])
        checkout, sha, deadline = Path(raw["checkout_root"]), raw["upstream_sha"], _deadline(raw["deadline"])
        if (
            request.platform not in COOKIE_LOGIN_PLATFORMS
            or type(sha) is not str
            or re.fullmatch(r"[0-9a-f]{40}", sha) is None
            or checkout.resolve() != Path.cwd().resolve()
        ):
            return 20
    except (ValueError, TypeError, KeyError, OSError):
        return 20
    try:
        with _silenced_upstream():
            asyncio.run(_verify_remote(checkout, request, deadline))
        result = _result(request, "authenticated", sha)
    except _VerificationFailure as error:
        result = _result(request, error.status, sha)
    except (TimeoutError, subprocess.TimeoutExpired):
        result = _result(request, "timed_out", sha)
    except BaseException:
        result = _result(request, "result_invalid", sha)
    _emit(_result_frame(result))
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--guardian"]:
        raise SystemExit(_guardian_entry())
    if sys.argv[1:] == ["--worker"]:
        raise SystemExit(_worker_entry())
    raise SystemExit(20)
