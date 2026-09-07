"""One source-backed current-user GraphQL check with the private candidate only."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from media_sync.domain import Platform

from .cookie_login import CookieLoginRequest, cookie_pairs, parse_cookie_header
from .cookie_login_runner import MAX_API_BYTES, _origin, _VerificationFailure
from .creator_profile_runner import _strict_object

_ORIGIN = "https://www.kuaishou.com"
_ENDPOINT = _ORIGIN + "/graphql"
_CP_COOKIE = "kuaishou.web.cp.api_ph"
_QUERY = (
    "query userInfoQuery {\n  userInfo {\n    id\n    name\n    avatar\n    eid\n    userId\n    __typename\n  }\n}\n"
)
_HEADERS = {"User-Agent", "Cookie", "Origin", "Referer", "Content-Type"}
_MAX_JSON_DEPTH = 64


def _invalid() -> _VerificationFailure:
    return _VerificationFailure("result_invalid")


def _body(candidate: str) -> dict[str, Any]:
    try:
        value = cookie_pairs(candidate).get(_CP_COOKIE)
    except (ValueError, TypeError):
        raise _invalid() from None
    # A literal presence marker is never proof. Preserve nonempty quoted values
    # exactly; no URL decoding, unquoting or substitution from another key.
    if value is None or value in {"", '""'}:
        raise _invalid()
    return {"operationName": "userInfoQuery", "variables": {}, "query": _QUERY, _CP_COOKIE: value}


def _encode_body(candidate: str) -> str:
    return json.dumps(_body(candidate), separators=(",", ":"), ensure_ascii=False)


def _bounded_json_depth(payload: bytes) -> bool:
    """Reject hostile nesting independently of interpreter recursion behavior."""

    depth = 0
    in_string = False
    escaped = False
    for value in payload:
        if in_string:
            if escaped:
                escaped = False
            elif value == 0x5C:  # backslash
                escaped = True
            elif value == 0x22:  # quote
                in_string = False
            continue
        if value == 0x22:
            in_string = True
        elif value in {0x5B, 0x7B}:  # [ {
            depth += 1
            if depth > _MAX_JSON_DEPTH:
                return False
        elif value in {0x5D, 0x7D}:  # ] }
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_string and not escaped


def _json(payload: bytes) -> dict[str, Any]:
    def constant(value: str) -> Any:
        raise _invalid()

    try:
        if type(payload) is not bytes or not 0 < len(payload) <= MAX_API_BYTES or not _bounded_json_depth(payload):
            raise _invalid()
        raw = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object, parse_constant=constant)
        if type(raw) is not dict:
            raise _invalid()
        return raw
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise _invalid() from None


def _authenticated(raw: dict[str, Any]) -> None:
    """Validate self identity, not a target profile or local credential marker."""
    if type(raw) is not dict or raw.get("errors") not in (None, []):
        raise _invalid()
    data = raw.get("data")
    user = data.get("userInfo") if type(data) is dict and set(data) == {"userInfo"} else None
    if type(data) is not dict or type(user) is not dict:
        raise _invalid()
    uid, name = user.get("userId"), user.get("name")
    if (
        type(uid) is not int
        or not 0 < uid <= 2**64 - 1
        or type(name) is not str
        or not 0 < len(name) <= 512
        or not name.strip()
        or not name.isprintable()
    ):
        raise _invalid()
    for value in (raw, data, user):
        # These are conservative contradiction fences, not invented remote
        # error-code semantics. Unknown/ambiguous values cannot authenticate.
        if (
            any(value[key] is not False for key in ("guest", "isGuest", "is_guest") if key in value)
            or any(value[key] is not True for key in ("isLogin", "is_login", "loggedIn") if key in value)
            or any(key in value for key in ("error", "error_code", "errorCode"))
        ):
            raise _invalid()


def _fetch(url: str, body: bytes, headers: Mapping[str, str], deadline: float) -> dict[str, Any]:
    """Bounded POST: fixed origin/query/body, no retries, redirects or proxies."""
    import httpx

    from media_sync.media.network import PinnedHTTPTransport, SocketAddressResolver, validate_target

    if url != _ENDPOINT or type(body) is not bytes or not 0 < len(body) <= 32 * 1024:
        raise _invalid()
    if (
        set(headers) != _HEADERS
        or any(
            type(value) is not str
            or len(value) > (16384 if key == "Cookie" else 8192)
            or not value.isascii()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            for key, value in headers.items()
        )
        or headers["Origin"] != _ORIGIN
        or headers["Referer"] != _ORIGIN + "/"
        or headers["Content-Type"] != "application/json"
        or body != _encode_body(headers["Cookie"]).encode("utf-8")
    ):
        raise _invalid()
    if deadline <= time.monotonic():
        raise _VerificationFailure("timed_out")
    try:
        target = validate_target(url, SocketAddressResolver(), max_url_chars=256)
        if target.url != _ENDPOINT:
            raise _invalid()
        remaining = min(10.0, deadline - time.monotonic())
        if remaining <= 0:
            raise _VerificationFailure("timed_out")
        outgoing = dict(headers)
        outgoing.update({"Host": target.host_header, "Accept": "application/json", "Accept-Encoding": "identity"})
        with (
            httpx.Client(
                transport=PinnedHTTPTransport(target), trust_env=False, follow_redirects=False, timeout=remaining
            ) as client,
            client.stream("POST", target.url, content=body, headers=outgoing) as response,
        ):
            if response.status_code == 401:
                raise _VerificationFailure("rejected")
            if response.status_code != 200:
                raise _invalid()
            if (
                response.headers.get("content-encoding", "identity").strip().lower() != "identity"
                or response.headers.get("content-type", "").partition(";")[0].strip().lower() != "application/json"
            ):
                raise _invalid()
            length = response.headers.get("content-length")
            if length is not None and (
                not length.isascii() or not length.isdecimal() or len(length) > 10 or int(length) > MAX_API_BYTES
            ):
                raise _invalid()
            payload = bytearray()
            for chunk in response.iter_raw(chunk_size=8192):
                if time.monotonic() >= deadline:
                    raise _VerificationFailure("timed_out")
                if len(payload) + len(chunk) > MAX_API_BYTES:
                    raise _invalid()
                payload.extend(chunk)
        return _json(bytes(payload))
    except httpx.TimeoutException:
        raise _VerificationFailure("timed_out") from None
    except httpx.HTTPError:
        raise _VerificationFailure("verification_unavailable") from None
    except _VerificationFailure:
        raise
    except Exception:
        raise _invalid() from None


async def query_kuaishou_cookie_client(client: Any, candidate: str, deadline: float) -> None:
    expected = _encode_body(candidate)
    original_request = client.request
    original_headers = dict(client.headers)
    calls = 0
    observed: dict[str, Any] | None = None
    observed_copy: dict[str, Any] | None = None

    async def request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls, observed, observed_copy
        if (
            calls != 0
            or method != "POST"
            or url != _ENDPOINT
            or set(kwargs) != {"headers", "data"}
            or not isinstance(kwargs["headers"], Mapping)
            or dict(kwargs["headers"]) != original_headers
            or original_headers.get("Cookie") != candidate
            or type(kwargs["data"]) is not str
            or kwargs["data"] != expected
        ):
            raise _invalid()
        calls += 1
        raw = await asyncio.to_thread(_fetch, url, expected.encode("utf-8"), original_headers, deadline)
        _authenticated(raw)
        data = raw["data"]
        if type(data) is not dict:
            raise _invalid()
        observed = data
        # Isolate the verified identity from a mutable object returned upstream.
        observed_copy = json.loads(json.dumps(observed, ensure_ascii=True, allow_nan=False))
        return data

    client.request = request
    try:
        result = await client.post("", _body(candidate))
        if calls != 1 or observed is None or result is not observed or result != observed_copy:
            raise _invalid()
        if time.monotonic() >= deadline:
            raise _VerificationFailure("timed_out")
    finally:
        client.request = original_request


async def verify_kuaishou_cookie(checkout: Path, request: CookieLoginRequest, deadline: float) -> None:
    """No browser, saved session, account mutation or public-profile fallback."""
    if request.platform is not Platform.KS:
        raise _invalid()
    if deadline <= time.monotonic():
        raise _VerificationFailure("timed_out")
    candidate = parse_cookie_header(request.cookie.reveal()).reveal()
    _body(candidate)
    os.chdir(checkout)
    sys.path.insert(0, str(checkout))
    if "config" in sys.modules or "media_platform.kuaishou.client" in sys.modules:
        raise _VerificationFailure("configuration_invalid")
    config: Any = importlib.import_module("config")
    _origin(config, checkout / "config/__init__.py")
    config.PLATFORM, config.COOKIES = "ks", ""
    config.ENABLE_IP_PROXY, config.STATIC_PROXY_URL = False, ""
    try:
        module: Any = importlib.import_module("media_platform.kuaishou.client")
        utils: Any = importlib.import_module("tools.utils")
        _origin(module, checkout / "media_platform/kuaishou/client.py")
        _origin(utils, checkout / "tools/utils.py")
        if getattr(module.KuaiShouClient, "__module__", None) != module.__name__:
            raise _VerificationFailure("configuration_invalid")
        client = module.KuaiShouClient(
            headers={
                "User-Agent": utils.get_user_agent(),
                "Cookie": candidate,
                "Origin": _ORIGIN,
                "Referer": _ORIGIN + "/",
                "Content-Type": "application/json",
            },
            playwright_page=None,
            cookie_dict=cookie_pairs(candidate),
            proxy=None,
        )
        if type(client) is not module.KuaiShouClient:
            raise _VerificationFailure("configuration_invalid")
        await query_kuaishou_cookie_client(client, candidate, deadline)
    finally:
        config.COOKIES = ""


__all__ = ["verify_kuaishou_cookie"]
