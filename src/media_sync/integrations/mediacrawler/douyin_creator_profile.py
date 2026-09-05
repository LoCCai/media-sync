"""One signed Douyin author observation; never proof of the current login.

The locked client and JavaScript build the request. Only its transport is
replaced, retaining the exact signed query (including an absent xmst as None).
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import os
import re
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from media_sync.integrations.mediacrawler.cookie_login import cookie_pairs, parse_cookie_header
from media_sync.integrations.mediacrawler.creator_profile_runner import (
    MAX_PROFILE_API_BYTES,
    MediaCrawlerCreatorProfile,
    MediaCrawlerCreatorProfileStatus,
    _json,
    _LookupFailure,
    _origin,
    _text,
)
from media_sync.security.secrets import SecretValue

_ORIGIN = "https://www.douyin.com"
_PATH = "/aweme/v1/web/user/profile/other/"
_ENDPOINT = _ORIGIN + _PATH
_ID = re.compile(r"[A-Za-z0-9_-]{1,255}\Z", re.ASCII)
_HEADER_NAMES = {"User-Agent", "Cookie", "Host", "Origin", "Referer", "Content-Type"}
_MAX_QUERY_BYTES = 16384
_COMMON: dict[str, str | int] = {
    "publish_video_strategy_type": 2,
    "personal_center_strategy": 1,
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "version_code": "190600",
    "version_name": "19.6.0",
    "update_version_code": "170400",
    "pc_client_type": "1",
    "cookie_enabled": "true",
    "browser_language": "zh-CN",
    "browser_platform": "MacIntel",
    "browser_name": "Chrome",
    "browser_version": "125.0.0.0",
    "browser_online": "true",
    "engine_name": "Blink",
    "os_name": "Mac OS",
    "os_version": "10.15.7",
    "cpu_core_num": "8",
    "device_memory": "8",
    "engine_version": "109.0",
    "platform": "PC",
    "screen_width": "2560",
    "screen_height": "1440",
    "effective_type": "4g",
    "round_trip_time": "50",
}


def _invalid() -> _LookupFailure:
    return _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)


def _identity(value: object) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise _invalid()
    return value


def _ascii(value: object, maximum: int) -> bool:
    return type(value) is str and 0 < len(value) <= maximum and all(32 <= ord(c) < 127 for c in value)


def _unsigned_query(params: object, remote_id: str) -> str:
    if type(params) is not dict or set(params) != set(_COMMON) | {"sec_user_id", "webid", "msToken", "a_bogus"}:
        raise _invalid()
    for key, value in {"sec_user_id": remote_id, **_COMMON}.items():
        if type(params[key]) is not type(value) or params[key] != value:
            raise _invalid()
    if type(params["webid"]) is not str or re.fullmatch(r"[0-9]{19}", params["webid"], re.ASCII) is None:
        raise _invalid()
    if params["msToken"] is not None and not _ascii(params["msToken"], 2048):
        raise _invalid()
    if not _ascii(params["a_bogus"], 2048):
        raise _invalid()
    return urlencode({key: value for key, value in params.items() if key != "a_bogus"})


def _fetch_profile_json(query: str, headers: Mapping[str, str], deadline: float) -> dict[str, Any]:
    """Single fixed-origin, DNS-pinned GET, with bounded uncompressed JSON."""
    import httpx

    from media_sync.media.network import PinnedHTTPTransport, SocketAddressResolver, validate_target

    if deadline <= time.monotonic():
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
    if (
        not _ascii(query, _MAX_QUERY_BYTES)
        or "#" in query
        or set(headers) != _HEADER_NAMES
        or any(not _ascii(value, 65536) for value in headers.values())
        or headers["Host"] != "www.douyin.com"
        or headers["Origin"] != _ORIGIN + "/"
        or headers["Referer"] != _ORIGIN + "/"
        or headers["Content-Type"] != "application/json;charset=UTF-8"
    ):
        raise _invalid()
    target = validate_target(_ENDPOINT + "?" + query, SocketAddressResolver(), max_url_chars=_MAX_QUERY_BYTES + 256)
    remaining = min(10.0, deadline - time.monotonic())
    if remaining <= 0:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
    outgoing = dict(headers)
    outgoing.update({"Host": target.host_header, "Accept": "application/json", "Accept-Encoding": "identity"})
    with (
        httpx.Client(
            transport=PinnedHTTPTransport(target), trust_env=False, follow_redirects=False, timeout=remaining
        ) as client,
        client.stream("GET", target.url, headers=outgoing) as response,
    ):
        if response.status_code != 200:
            # Public-target failures, even 401/403, do not establish Cookie expiry.
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TEMPORARY)
        if (
            response.headers.get("content-encoding", "identity").lower() != "identity"
            or response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json"
        ):
            raise _invalid()
        length = response.headers.get("content-length")
        if length is not None and (
            not length.isascii() or not length.isdecimal() or len(length) > 10 or int(length) > MAX_PROFILE_API_BYTES
        ):
            raise _invalid()
        payload = bytearray()
        for chunk in response.iter_raw(chunk_size=8192):
            if time.monotonic() >= deadline:
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
            if len(payload) + len(chunk) > MAX_PROFILE_API_BYTES:
                raise _invalid()
            payload.extend(chunk)
    return _json(bytes(payload), MAX_PROFILE_API_BYTES)


async def _query_douyin_client(
    client: Any, remote_id: str, deadline: float, *, signing_module: Any
) -> MediaCrawlerCreatorProfile:
    _identity(remote_id)
    original_request, original_sign = client.request, signing_module.get_a_bogus
    original_headers = dict(client.headers)
    signed_query: str | None = None
    signature: str | None = None
    calls = 0
    captured: dict[str, Any] | None = None

    async def sign(uri: str, query: str, post: dict[str, Any], agent: str, page: Any) -> str:
        nonlocal signed_query, signature
        if (
            uri != _PATH
            or signed_query is not None
            or calls != 0
            or not _ascii(query, _MAX_QUERY_BYTES)
            or type(post) is not dict
            or post != {}
            or agent != original_headers["User-Agent"]
            or page is not client.playwright_page
        ):
            raise _invalid()
        if deadline <= time.monotonic():
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
        signed_query = query
        value = await original_sign(uri, query, post, agent, page)
        if not _ascii(value, 2048):
            raise _invalid()
        signature = value
        return str(value)

    async def request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls, captured
        if (
            method != "GET"
            or url != _ENDPOINT
            or calls != 0
            or set(kwargs) != {"params", "headers"}
            or not isinstance(kwargs["headers"], Mapping)
            or dict(kwargs["headers"]) != original_headers
        ):
            raise _invalid()
        params = kwargs["params"]
        query = _unsigned_query(params, remote_id)
        if signed_query is None or signature is None or query != signed_query or params["a_bogus"] != signature:
            raise _invalid()
        # Do not let HTTPX re-encode None as an empty value: send precisely what
        # the real locked signer saw, then append its actual a_bogus value.
        outgoing_query = query + "&" + urlencode({"a_bogus": signature})
        calls += 1
        captured = await asyncio.to_thread(_fetch_profile_json, outgoing_query, original_headers, deadline)
        return captured

    client.request, signing_module.get_a_bogus = request, sign
    try:
        value = await client.get_user_info(remote_id)
        if calls != 1 or captured is None or value is not captured:
            raise _invalid()
        # Integer zero is our conservative success subset, not a claim that
        # every public profile response necessarily supplies this envelope.
        if type(value.get("status_code")) is not int or value["status_code"] != 0:
            raise _invalid()
        user = value.get("user")
        if type(user) is not dict or type(user.get("sec_uid")) is not str or user["sec_uid"] != remote_id:
            raise _invalid()
        # avatar_larger.url_list exists, but no fixed CDN URL shape is qualified.
        return MediaCrawlerCreatorProfile(remote_id, _text(user.get("nickname"), 512), None)
    finally:
        client.request, signing_module.get_a_bogus = original_request, original_sign


async def lookup_douyin(
    checkout: Path, profile: Path, remote_id: str, deadline: float, *, cookie: SecretValue | None = None
) -> MediaCrawlerCreatorProfile:
    """Use exactly the account's credential mode, without browser platform I/O."""
    _identity(remote_id)
    if deadline <= time.monotonic():
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
    if cookie is not None:
        cookie = parse_cookie_header(cookie.reveal())
    os.chdir(checkout)
    sys.path.insert(0, str(checkout))
    if any(name in sys.modules for name in ("config", "media_platform.douyin.client", "media_platform.douyin.help")):
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
    config: Any = importlib.import_module("config")
    _origin(config, checkout / "config/__init__.py")
    config.PLATFORM, config.COOKIES = "dy", ""
    config.ENABLE_IP_PROXY, config.STATIC_PROXY_URL = False, ""
    execjs: Any = importlib.import_module("execjs")
    original_compile = execjs.compile
    try:
        # help.py compiles at import time. Node uses stdin rather than a
        # secret-bearing temporary JavaScript file on the filesystem.
        execjs.compile = execjs.get("Node").compile
        client_module: Any = importlib.import_module("media_platform.douyin.client")
        helper: Any = importlib.import_module("media_platform.douyin.help")
    except Exception:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID) from None
    finally:
        execjs.compile = original_compile
    utils: Any = importlib.import_module("tools.utils")
    _origin(client_module, checkout / "media_platform/douyin/client.py")
    _origin(helper, checkout / "media_platform/douyin/help.py")
    _origin(utils, checkout / "tools/utils.py")
    if getattr(client_module.DouYinClient, "__module__", None) != client_module.__name__:
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
                        {"name": name, "value": value, "domain": ".douyin.com", "path": "/", "secure": True}
                        for name, value in cookie_pairs(cookie.reveal()).items()
                    ]
                )
        except Exception:
            if browser is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(browser.close(), timeout=2)
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.BROWSER_LAUNCH_FAILED) from None
        try:

            async def route_browser(route: Any) -> None:
                if route.request.is_navigation_request() and route.request.url == _ORIGIN + "/":
                    await route.fulfill(status=200, content_type="text/html", body="<!doctype html><title></title>")
                else:
                    await route.abort()

            await context.route("**/*", route_browser)
            page = await context.new_page()
            await page.goto(
                _ORIGIN + "/",
                wait_until="domcontentloaded",
                timeout=max(1, int(min(10, deadline - time.monotonic()) * 1000)),
            )
            if cookie is None:
                header, _unused = await utils.convert_browser_context_cookies(context, urls=[_ORIGIN])
                if not header:
                    raise _invalid()
                header = parse_cookie_header(header).reveal()
            else:
                header = cookie.reveal()
            agent = await page.evaluate("() => navigator.userAgent")
            if not _ascii(agent, 2048):
                raise _invalid()
            client = client_module.DouYinClient(
                proxy=None,
                headers={
                    "User-Agent": agent,
                    "Cookie": header,
                    "Host": "www.douyin.com",
                    "Origin": _ORIGIN + "/",
                    "Referer": _ORIGIN + "/",
                    "Content-Type": "application/json;charset=UTF-8",
                },
                playwright_page=page,
                cookie_dict=cookie_pairs(header),
            )
            if type(client) is not client_module.DouYinClient:
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
            return await _query_douyin_client(client, remote_id, deadline, signing_module=client_module)
        finally:
            config.COOKIES = ""
            with contextlib.suppress(Exception):
                await asyncio.wait_for(context.close(), timeout=max(0.01, min(2, deadline - time.monotonic())))
            if browser is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(browser.close(), timeout=max(0.01, min(2, deadline - time.monotonic())))


__all__ = ["lookup_douyin"]
