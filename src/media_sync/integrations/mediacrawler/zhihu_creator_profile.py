"""Exact nickname-only Zhihu observation; no crawler, content or avatar access."""

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
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast

from media_sync.domain import Platform
from media_sync.security.secrets import SecretValue

from .cookie_login import cookie_pairs, parse_cookie_header
from .cookie_login_runner import _authenticated, _VerificationFailure
from .creator_profile_runner import (
    MAX_PROFILE_API_BYTES,
    MediaCrawlerCreatorProfile,
    MediaCrawlerCreatorProfileStatus,
    _LookupFailure,
    _origin,
    _strict_object,
    _text,
)

_ORIGIN = "https://www.zhihu.com"
_SELF_PATH = "/api/v4/me"
_TOKEN = re.compile(r"[A-Za-z0-9._-]{1,255}\Z")
MAX_PROFILE_HTML_BYTES = 4 * 1024 * 1024
_BASE_HEADERS = {
    "user-agent",
    "cookie",
    "origin",
    "referer",
    "content-type",
    "x-api-version",
    "x-app-za",
    "x-requested-with",
    "x-zse-93",
}
_SIGN_HEADERS = {"x-zst-81", "x-zse-96"}


def _invalid() -> _LookupFailure:
    return _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)


def _token(value: object) -> str:
    if type(value) is not str or value in {".", ".."} or _TOKEN.fullmatch(value) is None:
        raise _invalid()
    return value


def _json(payload: bytes, maximum: int) -> dict[str, Any]:
    def constant(value: str) -> Any:
        raise _invalid()

    try:
        if not payload or len(payload) > maximum:
            raise _invalid()
        result = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object, parse_constant=constant)
        if type(result) is not dict:
            raise _invalid()
        return result
    except (ValueError, RecursionError) as error:
        raise _invalid() from error


class _InitialDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.count = 0
        self.active = False
        self.closed = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        ids = [value for name, value in attrs if name == "id"]
        if "js-initialData" in ids:
            if len(ids) != 1 or self.count:
                raise _invalid()
            self.count += 1
            self.active = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and any(name == "id" and value == "js-initialData" for name, value in attrs):
            raise _invalid()

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.active:
            self.active = False
            self.closed = True

    def handle_data(self, data: str) -> None:
        if self.active:
            self.parts.append(data)


def parse_zhihu_profile_html(html: str, token: str) -> MediaCrawlerCreatorProfile:
    """Only the exact response row's own urlToken can authorize its raw name."""
    _token(token)
    try:
        if type(html) is not str or not html or len(html.encode("utf-8")) > MAX_PROFILE_HTML_BYTES:
            raise _invalid()
        parser = _InitialDataParser()
        parser.feed(html)
        parser.close()
        if parser.count != 1 or parser.active or not parser.closed:
            raise _invalid()
        data: Any = _json("".join(parser.parts).encode("utf-8"), MAX_PROFILE_HTML_BYTES)
        for key in ("initialState", "entities", "users"):
            data = data.get(key)
            if type(data) is not dict:
                raise _invalid()
        row = data.get(token)
        if type(row) is not dict or type(row.get("urlToken")) is not str or row["urlToken"] != token:
            raise _invalid()
        # avatarUrl is a protocol field, not evidence for a safe CDN shape.
        # Never turn it or incidental page entities into output/storage.
        return MediaCrawlerCreatorProfile(token, _text(row.get("name"), 512), None)
    except (ValueError, TypeError, RecursionError, UnicodeError) as error:
        raise _invalid() from error


def _headers(headers: Mapping[str, str]) -> dict[str, str]:
    outgoing: dict[str, str] = {}
    for name, value in headers.items():
        if (
            type(name) is not str
            or name.lower() not in _BASE_HEADERS | _SIGN_HEADERS
            or name.lower() in outgoing
            or type(value) is not str
            or len(value) > (16384 if name.lower() == "cookie" else 8192)
            or not value.isascii()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise _invalid()
        outgoing[name.lower()] = value
    if (
        set(outgoing) != _BASE_HEADERS | _SIGN_HEADERS
        or not all(outgoing[key] for key in ("cookie", *_SIGN_HEADERS))
        or outgoing["origin"] != _ORIGIN
        or outgoing["referer"] != _ORIGIN + "/"
    ):
        raise _invalid()
    return outgoing


def _fetch(url: str, headers: Mapping[str, str], deadline: float, *, token: str, html: bool) -> bytes:
    """One exact signed URL, bounded raw bytes, no proxies/redirects/retries."""
    import httpx

    from media_sync.media.network import PinnedHTTPTransport, SocketAddressResolver, validate_target

    _token(token)
    if type(html) is not bool or url != _ORIGIN + ("/people/" + token if html else _SELF_PATH):
        raise _invalid()
    remaining = min(10.0, deadline - time.monotonic())
    if remaining <= 0:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
    outgoing = _headers(headers)
    maximum = MAX_PROFILE_HTML_BYTES if html else MAX_PROFILE_API_BYTES
    try:
        target = validate_target(url, SocketAddressResolver(), max_url_chars=4096)
        if target.url != url:
            raise _invalid()
        outgoing.update(
            {
                "host": target.host_header,
                "accept": "text/html" if html else "application/json",
                "accept-encoding": "identity",
            }
        )
        with (
            httpx.Client(
                transport=PinnedHTTPTransport(target), trust_env=False, follow_redirects=False, timeout=remaining
            ) as client,
            client.stream("GET", target.url, headers=outgoing) as response,
        ):
            if response.status_code == 401:
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.AUTH_EXPIRED)
            if response.status_code != 200:
                raise _invalid()
            media_type = response.headers.get("content-type", "").partition(";")[0].strip().lower()
            if response.headers.get("content-encoding", "identity").strip().lower() != "identity" or media_type != (
                "text/html" if html else "application/json"
            ):
                raise _invalid()
            length = response.headers.get("content-length")
            if length is not None and (
                not length.isascii() or not length.isdecimal() or len(length) > 10 or int(length) > maximum
            ):
                raise _invalid()
            body = bytearray()
            for chunk in response.iter_raw(chunk_size=8192):
                if time.monotonic() >= deadline:
                    raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
                if len(body) + len(chunk) > maximum:
                    raise _invalid()
                body.extend(chunk)
        return bytes(body)
    except httpx.HTTPError:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TEMPORARY) from None
    except _LookupFailure:
        raise
    except Exception:
        raise _invalid() from None


async def query_zhihu_client(client: Any, token: str, deadline: float) -> MediaCrawlerCreatorProfile:
    """Execute real locked get/get_creator_info under one two-request guard."""
    _token(token)
    originals = client.request, client._extractor.extract_creator
    original_headers = dict(client.default_headers)
    expected = (_ORIGIN + _SELF_PATH, _ORIGIN + "/people/" + token)
    calls = 0
    auth_confirmed = False
    response_html: str | None = None
    captured: MediaCrawlerCreatorProfile | None = None

    async def request(method: str, url: str, **kwargs: Any) -> Any:
        nonlocal calls, auth_confirmed, response_html
        html = calls == 1
        if (
            method != "GET"
            or calls >= 2
            or url != expected[calls]
            or set(kwargs) != ({"headers", "return_response"} if html else {"headers"})
            or (html and (kwargs.get("return_response") is not True or not auth_confirmed))
            or not isinstance(kwargs.get("headers"), Mapping)
        ):
            raise _invalid()
        signed = kwargs["headers"]
        if set(signed) != set(original_headers) | _SIGN_HEADERS or any(
            signed.get(key) != value for key, value in original_headers.items()
        ):
            raise _invalid()
        _headers(signed)
        calls += 1
        payload = await asyncio.to_thread(_fetch, url, signed, deadline, token=token, html=html)
        if html:
            try:
                response_html = payload.decode("utf-8")
            except UnicodeError:
                raise _invalid() from None
            return response_html
        data = _json(payload, MAX_PROFILE_API_BYTES)
        try:
            _authenticated(Platform.ZHIHU, data)
        except _VerificationFailure as error:
            raise _LookupFailure(
                MediaCrawlerCreatorProfileStatus.AUTH_EXPIRED
                if error.status == "rejected"
                else MediaCrawlerCreatorProfileStatus.RESULT_INVALID
            ) from None
        auth_confirmed = True
        return data

    def extract(actual_token: str, html_content: str) -> MediaCrawlerCreatorProfile:
        nonlocal captured
        if (
            calls != 2
            or not auth_confirmed
            or actual_token != token
            or response_html is None
            or html_content is not response_html
            or captured is not None
        ):
            raise _invalid()
        captured = parse_zhihu_profile_html(html_content, token)
        return captured

    client.request, client._extractor.extract_creator = request, extract
    try:
        await client.get(_SELF_PATH)
        if calls != 1 or not auth_confirmed:
            raise _invalid()
        result = await client.get_creator_info(token)
        if calls != 2 or captured is None or result is not captured:
            raise _invalid()
        return cast(MediaCrawlerCreatorProfile, captured)
    finally:
        client.request, client._extractor.extract_creator = originals


async def lookup_zhihu(
    checkout: Path, profile: Path, remote_id: str, deadline: float, *, cookie: SecretValue | None = None
) -> MediaCrawlerCreatorProfile:
    """Read exact scoped cookies without browser network; query a locked client."""
    _token(remote_id)
    if time.monotonic() >= deadline:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
    os.chdir(checkout)
    sys.path.insert(0, str(checkout))
    if "config" in sys.modules or "media_platform.zhihu.client" in sys.modules:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
    config: Any = importlib.import_module("config")
    _origin(config, checkout / "config/__init__.py")
    config.PLATFORM, config.COOKIES = "zhihu", ""
    config.ENABLE_IP_PROXY, config.STATIC_PROXY_URL = False, ""
    module: Any = importlib.import_module("media_platform.zhihu.client")
    helper: Any = importlib.import_module("media_platform.zhihu.help")
    utils: Any = importlib.import_module("tools.utils")
    _origin(module, checkout / "media_platform/zhihu/client.py")
    _origin(helper, checkout / "media_platform/zhihu/help.py")
    _origin(utils, checkout / "tools/utils.py")
    if getattr(module.ZhiHuClient, "__module__", None) != module.__name__:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
    original_compile = helper.execjs.compile
    try:
        helper.execjs.compile = helper.execjs.get("Node").compile
    except Exception:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID) from None
    try:
        playwright_api = importlib.import_module("playwright.async_api")
        async with playwright_api.async_playwright() as playwright:
            browser = context = None
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
                            {"name": name, "value": value, "domain": ".zhihu.com", "path": "/", "secure": True}
                            for name, value in cookie_pairs(cookie.reveal()).items()
                        ]
                    )
            except Exception:
                if browser is not None:
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(browser.close(), timeout=2)
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.BROWSER_LAUNCH_FAILED) from None
            try:

                async def abort(route: Any) -> None:
                    await route.abort()

                await context.route("**/*", abort)
                if cookie is None:
                    header, _unused = await utils.convert_browser_context_cookies(context, urls=[_ORIGIN])
                    if not header:
                        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.AUTH_EXPIRED)
                    header = parse_cookie_header(header).reveal()
                else:
                    header = cookie.reveal()
                pairs = cookie_pairs(header)
                if not pairs.get("d_c0"):
                    raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
                client = module.ZhiHuClient(
                    headers={
                        "User-Agent": utils.get_user_agent(),
                        "cookie": header,
                        "Origin": _ORIGIN,
                        "Referer": _ORIGIN + "/",
                        "Content-Type": "application/json;charset=UTF-8",
                        "x-api-version": "3.0.91",
                        "x-app-za": "OS=Web",
                        "x-requested-with": "fetch",
                        "x-zse-93": "101_3_3.0",
                    },
                    playwright_page=None,
                    cookie_dict=pairs,
                    proxy=None,
                )
                if type(client) is not module.ZhiHuClient:
                    raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
                return await query_zhihu_client(client, remote_id, deadline)
            finally:
                config.COOKIES = ""
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(context.close(), timeout=max(0.01, min(2.0, deadline - time.monotonic())))
                if browser is not None:
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(
                            browser.close(), timeout=max(0.01, min(2.0, deadline - time.monotonic()))
                        )
    finally:
        helper.execjs.compile = original_compile


__all__ = ["lookup_zhihu"]
