"""One exact Kuaishou creator observation, never a self-login validator.

The locked client's GraphQL/post methods are reused behind a single-request
transport fence. Its get_creator_info wrapper has an extra-unwrapping defect,
and relationship-list pong is not evidence of the current account identity.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import os
import re
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

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
from media_sync.security.paths import read_regular_file_bytes
from media_sync.security.secrets import SecretValue

_ORIGIN = "https://www.kuaishou.com"
_ENDPOINT = _ORIGIN + "/graphql"
_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_HEADER_NAMES = {"User-Agent", "Cookie", "Origin", "Referer", "Content-Type"}
_MAX_QUERY_BYTES = 8192


def _identity(value: object) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
    return value


def _fetch_profile_json(body: bytes, headers: Mapping[str, str], deadline: float) -> dict[str, Any]:
    """Bounded fixed-origin POST; credentials never enter a browser request."""
    import httpx

    from media_sync.media.network import PinnedHTTPTransport, SocketAddressResolver, validate_target

    if deadline <= time.monotonic():
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
    if (
        type(body) is not bytes
        or not 0 < len(body) <= 2 * _MAX_QUERY_BYTES
        or set(headers) != _HEADER_NAMES
        or any(
            type(value) is not str or len(value) > 65536 or "\r" in value or "\n" in value for value in headers.values()
        )
        or headers["Origin"] != _ORIGIN
        or headers["Referer"] != _ORIGIN + "/"
        or headers["Content-Type"] != "application/json;charset=UTF-8"
    ):
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
    target = validate_target(_ENDPOINT, SocketAddressResolver(), max_url_chars=256)
    remaining = min(10.0, deadline - time.monotonic())
    if remaining <= 0:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
    outgoing = dict(headers)
    outgoing.update({"Host": target.host_header, "Accept": "application/json", "Accept-Encoding": "identity"})
    with (
        httpx.Client(
            transport=PinnedHTTPTransport(target),
            trust_env=False,
            follow_redirects=False,
            timeout=remaining,
        ) as client,
        client.stream("POST", target.url, headers=outgoing, content=body) as response,
    ):
        if response.status_code != 200:
            # A public creator request does not establish self-auth semantics,
            # including for 401/403. Do not mutate account authentication.
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
        payload = bytearray()
        for chunk in response.iter_raw(chunk_size=8192):
            if time.monotonic() >= deadline:
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
            if len(payload) + len(chunk) > MAX_PROFILE_API_BYTES:
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
            payload.extend(chunk)
    return _json(bytes(payload), MAX_PROFILE_API_BYTES)


async def _query_kuaishou_client(
    client: Any,
    remote_id: str,
    deadline: float,
    *,
    expected_query: str,
) -> MediaCrawlerCreatorProfile:
    _identity(remote_id)
    if type(expected_query) is not str or not 0 < len(expected_query.encode("utf-8")) <= _MAX_QUERY_BYTES:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
    expected_body = json.dumps(
        {"operationName": "visionProfile", "variables": {"userId": remote_id}, "query": expected_query},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    original_headers = dict(client.headers)
    calls = 0

    async def bounded_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        if (
            method != "POST"
            or url != _ENDPOINT
            or calls != 0
            or set(kwargs) != {"headers", "data"}
            or not isinstance(kwargs["headers"], Mapping)
            or dict(kwargs["headers"]) != original_headers
            or type(kwargs["data"]) is not str
            or kwargs["data"] != expected_body
        ):
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
        calls += 1
        raw = await asyncio.to_thread(_fetch_profile_json, expected_body.encode("utf-8"), original_headers, deadline)
        if raw.get("errors") not in (None, []):
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
        data = raw.get("data")
        if type(data) is not dict or set(data) != {"visionProfile"}:
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
        return data

    client.request = bounded_request
    # Calling get_creator_info would incorrectly skip the visionProfile layer.
    data = await client.get_creator_profile(remote_id)
    value = data.get("visionProfile") if type(data) is dict else None
    if calls != 1 or type(value) is not dict:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
    if type(value.get("result")) is not int or value["result"] != 1:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
    user_profile = value.get("userProfile")
    profile = user_profile.get("profile") if type(user_profile) is dict else None
    if type(profile) is not dict or type(profile.get("user_id")) is not str or profile["user_id"] != remote_id:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
    # headurl is declared in the source, but no trustworthy fixed avatar-CDN
    # shape is established. Neither arbitrary URLs nor incidental fields leave
    # this boundary; optional imagery can be qualified independently later.
    return MediaCrawlerCreatorProfile(remote_id, _text(profile.get("user_name"), 512), None)


async def lookup_kuaishou(
    checkout: Path,
    profile: Path,
    remote_id: str,
    deadline: float,
    *,
    cookie: SecretValue | None = None,
) -> MediaCrawlerCreatorProfile:
    """Observe one exact profile using the eligible account's credential mode."""
    _identity(remote_id)
    if deadline <= time.monotonic():
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
    if cookie is not None:
        cookie = parse_cookie_header(cookie.reveal())
    os.chdir(checkout)
    sys.path.insert(0, str(checkout))
    if "config" in sys.modules or "media_platform.kuaishou.client" in sys.modules:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
    config: Any = importlib.import_module("config")
    _origin(config, checkout / "config/__init__.py")
    config.PLATFORM = "ks"
    config.COOKIES = ""
    config.ENABLE_IP_PROXY = False
    config.STATIC_PROXY_URL = ""
    client_module = importlib.import_module("media_platform.kuaishou.client")
    utils = importlib.import_module("tools.utils")
    _origin(client_module, checkout / "media_platform/kuaishou/client.py")
    _origin(utils, checkout / "tools/utils.py")
    if getattr(client_module.KuaiShouClient, "__module__", None) != client_module.__name__:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
    expected_query = (
        read_regular_file_bytes(
            checkout / "media_platform/kuaishou/graphql/vision_profile.graphql",
            root=checkout,
            max_bytes=_MAX_QUERY_BYTES,
        )
        .decode("utf-8")
        .replace("\r\n", "\n")
    )
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
                        {"name": name, "value": value, "domain": ".kuaishou.com", "path": "/", "secure": True}
                        for name, value in cookie_pairs(cookie.reveal()).items()
                    ]
                )
        except Exception:
            if browser is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(browser.close(), timeout=2.0)
            raise _LookupFailure(MediaCrawlerCreatorProfileStatus.BROWSER_LAUNCH_FAILED) from None
        try:

            async def route_browser(route: Any) -> None:
                if route.request.is_navigation_request() and route.request.url == _ORIGIN + "/":
                    await route.fulfill(status=200, content_type="text/html", body="<!doctype html><title></title>")
                else:
                    await route.abort()

            await context.route("**/*", route_browser)
            page = await context.new_page()
            await page.goto(_ORIGIN + "/", wait_until="domcontentloaded")
            if cookie is None:
                header, _unused = await utils.convert_browser_context_cookies(context, urls=[_ORIGIN])
                if not header:
                    raise _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
                header = parse_cookie_header(header).reveal()
            else:
                header = cookie.reveal()
            client = client_module.KuaiShouClient(
                proxy=None,
                headers={
                    "User-Agent": utils.get_user_agent(),
                    "Cookie": header,
                    "Origin": _ORIGIN,
                    "Referer": _ORIGIN + "/",
                    "Content-Type": "application/json;charset=UTF-8",
                },
                playwright_page=page,
                cookie_dict=cookie_pairs(header),
            )
            if type(client) is not client_module.KuaiShouClient:
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
            return await _query_kuaishou_client(client, remote_id, deadline, expected_query=expected_query)
        finally:
            config.COOKIES = ""
            with contextlib.suppress(Exception):
                await asyncio.wait_for(context.close(), timeout=max(0.01, min(2.0, deadline - time.monotonic())))
            if browser is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(browser.close(), timeout=max(0.01, min(2.0, deadline - time.monotonic())))


__all__ = ["lookup_kuaishou"]
