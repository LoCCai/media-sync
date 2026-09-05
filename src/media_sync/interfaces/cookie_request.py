"""Bounded credential request parsing without Pydantic input/error reflection."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from uuid import UUID

from starlette.requests import ClientDisconnect, Request

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler.cookie_login import parse_cookie_header
from media_sync.security.secrets import SecretError, SecretValue

MAX_COOKIE_LOGIN_BODY_BYTES = 32 * 1024
_FIELDS = frozenset(
    {
        "cookie",
        "platform",
        "expected_auth_revision",
        "frontend_generation",
        "enable_mediacrawler",
        "accept_mediacrawler_license",
    }
)
_JSON_CONTENT_TYPE = re.compile(r"application/json(?:\s*;\s*charset=utf-8)?\Z", re.IGNORECASE)


class CookieRequestError(ValueError):
    def __init__(self, code: str = "cookie_login_request_invalid", status: int = 400) -> None:
        self.code, self.status = code, status
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CookieLoginBody:
    cookie: SecretValue = field(repr=False)
    platform: Platform
    expected_auth_revision: int
    frontend_generation: UUID
    enable_mediacrawler: bool
    accept_mediacrawler_license: bool


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CookieRequestError()
        result[key] = value
    return result


def _constant(_value: str) -> object:
    raise CookieRequestError()


def _decode(raw: bytearray) -> CookieLoginBody:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
        if type(value) is not dict or set(value) != _FIELDS:
            raise CookieRequestError()
        if type(value["cookie"]) is not str or type(value["platform"]) is not str:
            raise CookieRequestError()
        revision = value["expected_auth_revision"]
        if type(revision) is not int or not 0 <= revision < 2**63 - 1:
            raise CookieRequestError()
        generation = value["frontend_generation"]
        if type(generation) is not str or str(UUID(generation)) != generation:
            raise CookieRequestError()
        if any(type(value[key]) is not bool for key in ("enable_mediacrawler", "accept_mediacrawler_license")):
            raise CookieRequestError()
        return CookieLoginBody(
            parse_cookie_header(value["cookie"]),
            Platform(value["platform"]),
            revision,
            UUID(generation),
            value["enable_mediacrawler"],
            value["accept_mediacrawler_license"],
        )
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError, SecretError):
        raise CookieRequestError() from None


async def read_cookie_login_body(request: Request) -> CookieLoginBody:
    headers = request.scope.get("headers", ())
    types = [value for key, value in headers if key.lower() == b"content-type"]
    if len(types) != 1 or len(types[0]) > 64:
        raise CookieRequestError("cookie_login_content_type_invalid", 415)
    try:
        if _JSON_CONTENT_TYPE.fullmatch(types[0].decode("ascii")) is None:
            raise CookieRequestError("cookie_login_content_type_invalid", 415)
    except UnicodeError:
        raise CookieRequestError("cookie_login_content_type_invalid", 415) from None
    encodings = [value for key, value in headers if key.lower() == b"content-encoding"]
    if encodings and encodings != [b"identity"]:
        raise CookieRequestError("cookie_login_content_type_invalid", 415)
    lengths = [value for key, value in headers if key.lower() == b"content-length"]
    if len(lengths) > 1:
        raise CookieRequestError()
    if lengths:
        try:
            length = int(lengths[0])
            if str(length).encode("ascii") != lengths[0] or length < 0:
                raise CookieRequestError()
            if length > MAX_COOKIE_LOGIN_BODY_BYTES:
                raise CookieRequestError("cookie_login_body_too_large", 413)
        except ValueError as error:
            if isinstance(error, CookieRequestError):
                raise
            raise CookieRequestError() from None
    raw = bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(raw) + len(chunk) > MAX_COOKIE_LOGIN_BODY_BYTES:
                    raise CookieRequestError("cookie_login_body_too_large", 413)
                raw.extend(chunk)
        if lengths and len(raw) != int(lengths[0]):
            raise CookieRequestError()
        return _decode(raw)
    except (TimeoutError, ClientDisconnect):
        raise CookieRequestError() from None
    finally:
        raw[:] = b"\x00" * len(raw)
        raw.clear()
