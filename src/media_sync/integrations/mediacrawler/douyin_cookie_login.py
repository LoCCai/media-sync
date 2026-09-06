"""One remote Douyin current-account check, using original protocol plumbing.

This fixed creator-center self endpoint is not a MediaCrawler client method.
No author ID, browser, local login flag, signing or discovery request is used.
Only a closed success subset authenticates; no returned identity leaves here.
"""

from __future__ import annotations

import asyncio
import math
import re
import time
from typing import Any

import httpx

from media_sync.integrations.mediacrawler.cookie_login import cookie_pairs
from media_sync.integrations.mediacrawler.cookie_login_runner import MAX_API_BYTES, _VerificationFailure
from media_sync.integrations.mediacrawler.creator_profile_runner import _json, _text
from media_sync.security.secrets import SecretValue

_ENDPOINT = "https://creator.douyin.com/web/api/media/user/info/"
_REFERER = "https://creator.douyin.com/creator-micro/home"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_SEC_UID = re.compile(r"[A-Za-z0-9_-]{1,255}\Z", re.ASCII)
_UID = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)
_GUEST_FLAGS = ("guest", "isGuest", "is_guest")
_LOGIN_FLAGS = ("isLogin", "is_login", "loggedIn")


def _invalid() -> _VerificationFailure:
    return _VerificationFailure("result_invalid")


def _check_deadline(deadline: object) -> None:
    if isinstance(deadline, bool) or not isinstance(deadline, int | float) or not math.isfinite(deadline):
        raise _invalid()
    if deadline <= time.monotonic():
        raise _VerificationFailure("timed_out")


def _authenticated(raw: object) -> None:
    """Explicitly stricter than the public sources' truthy/alternate wrappers."""
    if type(raw) is not dict or type(raw.get("status_code")) is not int or raw["status_code"] != 0:
        raise _invalid()
    # We qualify only the documented user wrapper. A second nonempty identity
    # wrapper is ambiguous, even if the other implementation might prefer it.
    if (
        raw.get("user_info") not in (None, {})
        or raw.get("error") not in (None, "")
        or raw.get("errors") not in (None, [])
    ):
        raise _invalid()
    user = raw.get("user")
    if type(user) is not dict:
        raise _invalid()
    if any(value[key] is not False for value in (raw, user) for key in _GUEST_FLAGS if key in value) or any(
        value[key] is not True for value in (raw, user) for key in _LOGIN_FLAGS if key in value
    ):
        raise _invalid()
    uid = user.get("uid")
    valid_uid = (type(uid) is int and 0 < uid <= 2**64 - 1) or (
        type(uid) is str and _UID.fullmatch(uid) is not None and int(uid) <= 2**64 - 1
    )
    sec_uid = user.get("sec_uid")
    if not valid_uid or type(sec_uid) is not str or _SEC_UID.fullmatch(sec_uid) is None:
        raise _invalid()
    try:
        _text(user.get("nickname"), 512)
    except ValueError:
        raise _invalid() from None


def _fetch_self(cookie: str, deadline: float) -> dict[str, Any]:
    """One fixed HTTPS GET, public-address pinned, with no ambient HTTP state."""
    from media_sync.media.network import PinnedHTTPTransport, SocketAddressResolver, validate_target

    _check_deadline(deadline)
    # Validation must not normalize, drop, merge or replace candidate fields.
    cookie_pairs(cookie)
    target = validate_target(_ENDPOINT, SocketAddressResolver(), max_url_chars=256)
    _check_deadline(deadline)
    headers = {
        "Host": target.host_header,
        "User-Agent": _USER_AGENT,
        "Cookie": cookie,
        "Referer": _REFERER,
        "Accept": "application/json",
        "Accept-Encoding": "identity",
    }
    with (
        httpx.Client(
            transport=PinnedHTTPTransport(target),
            trust_env=False,
            follow_redirects=False,
            timeout=min(10.0, deadline - time.monotonic()),
        ) as client,
        client.stream("GET", target.url, headers=headers) as response,
    ):
        if response.status_code == 401:
            raise _VerificationFailure("rejected")
        if response.status_code != 200:
            raise _invalid()
        content_type = response.headers.get("content-type", "")
        length = response.headers.get("content-length")
        if (
            response.headers.get("content-encoding", "identity").strip().lower() != "identity"
            or len(content_type) > 128
            or content_type.partition(";")[0].strip().lower() != "application/json"
            or (
                length is not None
                and (not length.isascii() or not length.isdecimal() or len(length) > 10 or int(length) > MAX_API_BYTES)
            )
        ):
            raise _invalid()
        payload = bytearray()
        for chunk in response.iter_raw(chunk_size=8192):
            _check_deadline(deadline)
            if len(payload) + len(chunk) > MAX_API_BYTES:
                raise _invalid()
            payload.extend(chunk)
    _check_deadline(deadline)
    return _json(bytes(payload), MAX_API_BYTES)


async def verify_douyin_cookie(cookie: SecretValue, deadline: float) -> None:
    """Authenticate only the exact supplied candidate; return no private data."""
    try:
        _check_deadline(deadline)
        if not isinstance(cookie, SecretValue):
            raise _invalid()
        raw = await asyncio.to_thread(_fetch_self, cookie.reveal(), deadline)
        _authenticated(raw)
        _check_deadline(deadline)
    except _VerificationFailure:
        raise
    except (TimeoutError, httpx.TimeoutException):
        raise _VerificationFailure("timed_out") from None
    except httpx.HTTPError:
        raise _VerificationFailure("verification_unavailable") from None
    except Exception:
        # HTTP/browser-independent implementation errors may mention the
        # candidate or private response. Only closed classifications escape.
        raise _invalid() from None


__all__ = ["verify_douyin_cookie"]
