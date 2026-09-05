"""One signed, identity-bound Tieba creator observation; never self authentication."""

from __future__ import annotations

import ast
import asyncio
import contextlib
import importlib
import inspect
import json
import os
import re
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit

from media_sync.security.secrets import SecretValue

from .cookie_login import cookie_pairs, parse_cookie_header
from .creator_profile_runner import (
    MAX_PROFILE_API_BYTES,
    MediaCrawlerCreatorProfile,
    MediaCrawlerCreatorProfileStatus,
    _LookupFailure,
    _origin,
    _strict_object,
    _text,
)

_ORIGIN = "https://tieba.baidu.com"
_PATH = "/c/u/pc/homeSidebarRight"
_PORTRAIT = re.compile(r"tb\.1\.[A-Za-z0-9._-]{28,31}\Z", re.ASCII)
_TIMESTAMP = re.compile(r"[0-9]{10}\Z", re.ASCII)
_SIGNATURE = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_AVATAR = "https://gss0.bdstatic.com/6LZ1dD3d1sgCo2Kml5_Y_D3/sys/portrait/item/"
_HEADER_NAMES = {"User-Agent", "Cookie", "Origin", "Referer"}


def _invalid() -> _LookupFailure:
    return _LookupFailure(MediaCrawlerCreatorProfileStatus.RESULT_INVALID)


def _identity(value: object) -> str:
    if type(value) is not str or _PORTRAIT.fullmatch(value) is None or ".." in value or value.endswith("."):
        raise _invalid()
    return value


def _returned_portrait(value: object, remote_id: str) -> str:
    _identity(remote_id)
    if type(value) is not str:
        raise _invalid()
    bare, separator, stamp = value.partition("?t=")
    if bare != remote_id or (separator and _TIMESTAMP.fullmatch(stamp) is None):
        raise _invalid()
    return value


def _json(payload: bytes) -> dict[str, Any]:
    def constant(value: str) -> Any:
        raise _invalid()

    try:
        if type(payload) is not bytes or not 0 < len(payload) <= MAX_PROFILE_API_BYTES:
            raise _invalid()
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object, parse_constant=constant)
        if (
            type(data) is not dict
            or type(data.get("error_code")) is not int
            or data["error_code"] != 0
            or ("no" in data and (type(data["no"]) is not int or data["no"] != 0))
        ):
            raise _invalid()
        return data
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise _invalid() from None


def _avatar(user: dict[str, Any], portrait: str) -> str | None:
    value: Any = user
    for key in ("user_show_info", "feed_head", "image_data", "img_url"):
        if type(value) is not dict:
            return None
        value = value.get(key)
        if value in (None, ""):
            # The historical creator helper explicitly used this fixed fallback.
            return _AVATAR + portrait
    # Unknown or differently bound optional imagery is not a nickname failure.
    return value if type(value) is str and value == _AVATAR + portrait else None


def parse_tieba_profile_json(raw: dict[str, Any], remote_id: str) -> MediaCrawlerCreatorProfile:
    _identity(remote_id)
    if (
        type(raw) is not dict
        or type(raw.get("error_code")) is not int
        or raw["error_code"] != 0
        or ("no" in raw and (type(raw["no"]) is not int or raw["no"] != 0))
    ):
        raise _invalid()
    data = raw.get("data")
    user = data.get("user") if type(data) is dict else None
    if type(user) is not dict:
        raise _invalid()
    portrait = _returned_portrait(user.get("portrait"), remote_id)
    name = user.get("name_show")
    if name is None or name == "":
        name = user.get("name")
    try:
        return MediaCrawlerCreatorProfile(remote_id, _text(name, 512), _avatar(user, portrait))
    except (ValueError, TypeError, UnicodeError):
        raise _invalid() from None


def _params(remote_id: str) -> dict[str, str]:
    return {"portrait": _identity(remote_id), "un": "", "subapp_type": "pc", "_client_type": "20"}


def _request_url(remote_id: str, signature: str) -> str:
    if type(signature) is not str or _SIGNATURE.fullmatch(signature) is None:
        raise _invalid()
    return _ORIGIN + _PATH + "?" + urlencode({**_params(remote_id), "sign": signature})


def _fetch(url: str, headers: Mapping[str, str], deadline: float, *, remote_id: str) -> bytes:
    """One exact signed GET; bounded pinned DNS/HTTP with no browser or proxies."""
    import httpx

    from media_sync.media.network import PinnedHTTPTransport, SocketAddressResolver, validate_target

    _identity(remote_id)
    query = parse_qsl(urlsplit(url).query, keep_blank_values=True)
    if len(query) != 5 or url != _request_url(remote_id, dict(query).get("sign", "")):
        raise _invalid()
    if (
        set(headers) != _HEADER_NAMES
        or any(
            type(value) is not str
            or len(value) > (16384 if key == "Cookie" else 8192)
            or not value.isascii()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            for key, value in headers.items()
        )
        or not headers["Cookie"]
        or headers["Origin"] != _ORIGIN
        or headers["Referer"] != _ORIGIN + "/"
    ):
        raise _invalid()
    remaining = min(10.0, deadline - time.monotonic())
    if remaining <= 0:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
    try:
        target = validate_target(url, SocketAddressResolver(), max_url_chars=2048)
        if target.url != url:
            raise _invalid()
        outgoing = dict(headers)
        outgoing.update({"Host": target.host_header, "Accept": "application/json", "Accept-Encoding": "identity"})
        with (
            httpx.Client(
                transport=PinnedHTTPTransport(target), trust_env=False, follow_redirects=False, timeout=remaining
            ) as client,
            client.stream("GET", target.url, headers=outgoing) as response,
        ):
            if response.status_code >= 500:
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TEMPORARY)
            if response.status_code != 200:
                raise _invalid()
            if (
                response.headers.get("content-encoding", "identity").strip().lower() != "identity"
                or response.headers.get("content-type", "").partition(";")[0].strip().lower() != "application/json"
            ):
                raise _invalid()
            length = response.headers.get("content-length")
            if length is not None and (
                not length.isascii()
                or not length.isdecimal()
                or len(length) > 10
                or int(length) > MAX_PROFILE_API_BYTES
            ):
                raise _invalid()
            body = bytearray()
            for chunk in response.iter_raw(chunk_size=8192):
                if time.monotonic() >= deadline:
                    raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
                if len(body) + len(chunk) > MAX_PROFILE_API_BYTES:
                    raise _invalid()
                body.extend(chunk)
        return bytes(body)
    except httpx.HTTPError:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TEMPORARY) from None
    except _LookupFailure:
        raise
    except Exception:
        raise _invalid() from None


def _evaluate_script(method: Any) -> str:
    """Read the locked method's literal without copying or executing page JS."""
    try:
        # Keep indentation inside the multiline JS literal byte-for-byte. A
        # source dedent would silently change that literal's runtime value.
        tree = ast.parse("if True:\n" + inspect.getsource(method))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "evaluate"
        ]
        if len(calls) != 1 or len(calls[0].args) != 2:
            raise ValueError
        literal = calls[0].args[0]
        if not isinstance(literal, ast.Constant) or type(literal.value) is not str:
            raise ValueError
        return literal.value
    except (OSError, TypeError, ValueError, SyntaxError):
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID) from None


async def query_tieba_client(client: Any, remote_id: str, deadline: float) -> MediaCrawlerCreatorProfile:
    """Run the locked creator/fetch/sign methods behind one private Page adapter."""
    _identity(remote_id)
    original_fetch = client._fetch_json_by_browser
    original_sign = client._sign_pc_params
    original_extract = client._page_extractor.extract_creator_info_from_api
    original_page = client.playwright_page
    original_headers = dict(client.headers)
    script = _evaluate_script(original_fetch)
    fetches = signatures = evaluations = 0
    expected_url: str | None = None
    observed_json: dict[str, Any] | None = None
    actual_response: dict[str, Any] | None = None
    captured: MediaCrawlerCreatorProfile | None = None

    class Page:
        url = _ORIGIN

        async def goto(self, *args: Any, **kwargs: Any) -> None:
            raise _invalid()

        async def evaluate(self, expression: str, arguments: Any) -> dict[str, Any]:
            nonlocal evaluations, observed_json
            if (
                fetches != 1
                or signatures != 1
                or evaluations != 0
                or expected_url is None
                or expression != script
                or type(arguments) is not dict
                or arguments != {"url": expected_url, "method": "GET", "body": ""}
                or dict(client.headers) != original_headers
            ):
                raise _invalid()
            evaluations += 1
            payload = await asyncio.to_thread(_fetch, expected_url, original_headers, deadline, remote_id=remote_id)
            observed_json = _json(payload)
            return {"status": 200, "text": payload.decode("utf-8")}

    def sign(params: Any) -> str:
        nonlocal signatures, expected_url
        if signatures != 0 or fetches != 1 or type(params) is not dict or params != _params(remote_id):
            raise _invalid()
        signatures += 1
        value = original_sign(params)
        expected_url = _request_url(remote_id, value)
        return cast(str, value)

    async def fetch(uri: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal fetches, actual_response
        if (
            fetches != 0
            or uri != _PATH
            or set(kwargs) != {"params", "use_sign"}
            or kwargs["use_sign"] is not True
            or type(kwargs["params"]) is not dict
            or kwargs["params"] != _params(remote_id)
        ):
            raise _invalid()
        fetches += 1
        result = await original_fetch(uri, **kwargs)
        if evaluations != 1 or observed_json is None or type(result) is not dict or result != observed_json:
            raise _invalid()
        actual_response = result
        return result

    def extract(value: Any) -> MediaCrawlerCreatorProfile:
        nonlocal captured
        if (
            fetches != 1
            or evaluations != 1
            or actual_response is None
            or value is not actual_response
            or value != observed_json
            or captured
        ):
            raise _invalid()
        captured = parse_tieba_profile_json(value, remote_id)
        return captured

    client.playwright_page = Page()
    client._fetch_json_by_browser, client._sign_pc_params = fetch, sign
    client._page_extractor.extract_creator_info_from_api = extract
    try:
        result = await client.get_creator_info_by_url(_ORIGIN + "/home/main?id=" + remote_id)
        if fetches != 1 or signatures != 1 or evaluations != 1 or captured is None or result is not captured:
            raise _invalid()
        return cast(MediaCrawlerCreatorProfile, captured)
    finally:
        client.playwright_page = original_page
        client._fetch_json_by_browser, client._sign_pc_params = original_fetch, original_sign
        client._page_extractor.extract_creator_info_from_api = original_extract


async def lookup_tieba(
    checkout: Path, profile: Path, remote_id: str, deadline: float, *, cookie: SecretValue | None = None
) -> MediaCrawlerCreatorProfile:
    """Read only the eligible account's exact cookie context, without navigation."""
    _identity(remote_id)
    if deadline <= time.monotonic():
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.TIMED_OUT)
    if cookie is not None:
        cookie = parse_cookie_header(cookie.reveal())
    os.chdir(checkout)
    sys.path.insert(0, str(checkout))
    if "config" in sys.modules or "media_platform.tieba.client" in sys.modules:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
    config: Any = importlib.import_module("config")
    _origin(config, checkout / "config/__init__.py")
    config.PLATFORM, config.COOKIES = "tieba", ""
    config.ENABLE_IP_PROXY, config.STATIC_PROXY_URL = False, ""
    module: Any = importlib.import_module("media_platform.tieba.client")
    helper: Any = importlib.import_module("media_platform.tieba.help")
    utils: Any = importlib.import_module("tools.utils")
    _origin(module, checkout / "media_platform/tieba/client.py")
    _origin(helper, checkout / "media_platform/tieba/help.py")
    _origin(utils, checkout / "tools/utils.py")
    if getattr(module.BaiduTieBaClient, "__module__", None) != module.__name__:
        raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
    playwright_api = importlib.import_module("playwright.async_api")
    async with playwright_api.async_playwright() as playwright:
        browser = context = None
        try:
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
                            {"name": name, "value": value, "domain": ".tieba.baidu.com", "path": "/", "secure": True}
                            for name, value in cookie_pairs(cookie.reveal()).items()
                        ]
                    )
            except Exception:
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.BROWSER_LAUNCH_FAILED) from None

            async def abort(route: Any) -> None:
                await route.abort()

            await context.route("**/*", abort)
            if cookie is None:
                header, _unused = await utils.convert_browser_context_cookies(context, urls=[_ORIGIN])
                if not header:
                    raise _invalid()
                header = parse_cookie_header(header).reveal()
            else:
                header = cookie.reveal()
            client = module.BaiduTieBaClient(
                headers={
                    "User-Agent": utils.get_user_agent(),
                    "Cookie": header,
                    "Origin": _ORIGIN,
                    "Referer": _ORIGIN + "/",
                },
                playwright_page=None,
                ip_pool=None,
                default_ip_proxy=None,
            )
            if type(client) is not module.BaiduTieBaClient:
                raise _LookupFailure(MediaCrawlerCreatorProfileStatus.CONFIGURATION_INVALID)
            return await query_tieba_client(client, remote_id, deadline)
        finally:
            config.COOKIES = ""
            for resource in (context, browser):
                if resource is not None:
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(
                            resource.close(), timeout=max(0.01, min(2.0, deadline - time.monotonic()))
                        )


__all__ = ["lookup_tieba"]
