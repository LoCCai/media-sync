"""Closed, secret-safe contracts for noninteractive Cookie authentication."""

from __future__ import annotations

import math
import re
import threading
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from media_sync.domain import Platform
from media_sync.security import SecretValue

MAX_COOKIE_HEADER_BYTES = 16 * 1024
MAX_COOKIE_PAIRS = 128
COOKIE_LOGIN_PLATFORMS = frozenset({Platform.BILI, Platform.WB, Platform.XHS, Platform.ZHIHU, Platform.TIEBA})
COOKIE_LOGIN_STATUSES = frozenset(
    {
        "authenticated",
        "rejected",
        "verification_unavailable",
        "timed_out",
        "cancelled",
        "configuration_invalid",
        "result_invalid",
        "cleanup_failed",
    }
)
_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+\Z")
_ATTRIBUTES = frozenset({"domain", "path", "expires", "max-age", "secure", "httponly", "samesite", "partitioned"})


def cookie_pairs(raw: str) -> dict[str, str]:
    """Parse a request Cookie header, never Set-Cookie or browser JSON.

    Reject ambiguity rather than silently dropping fields. Cookie values may
    contain any number of equals signs; nothing is URL-decoded or unquoted.
    """

    if type(raw) is not str or not 0 < len(raw) <= MAX_COOKIE_HEADER_BYTES:
        raise ValueError("cookie_header_invalid")
    if not raw.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise ValueError("cookie_header_invalid")
    pairs: dict[str, str] = {}
    parts = raw.split(";")
    # A single customary trailing semicolon does not introduce a cookie.
    if parts[-1].strip() == "":
        parts.pop()
    if not 1 <= len(parts) <= MAX_COOKIE_PAIRS:
        raise ValueError("cookie_header_invalid")
    for part in parts:
        candidate = part.strip()
        name, separator, value = candidate.partition("=")
        # RFC 6265 permits one outer quote pair. Keep it byte-for-byte because
        # e.g. Zhihu's d_c0 can be quoted and participates in signing.
        content = value[1:-1] if len(value) >= 2 and value.startswith('"') and value.endswith('"') else value
        if (
            not separator
            or _NAME.fullmatch(name) is None
            or name.startswith("$")
            or name.lower() in _ATTRIBUTES
            or name in pairs
            or any(ord(char) < 33 or char in '";,\\' for char in content)
        ):
            raise ValueError("cookie_header_invalid")
        pairs[name] = value
    return pairs


def parse_cookie_header(raw: str) -> SecretValue:
    pairs = cookie_pairs(raw)
    normalized = "; ".join(f"{name}={value}" for name, value in pairs.items())
    if len(normalized) > MAX_COOKIE_HEADER_BYTES:
        raise ValueError("cookie_header_invalid")
    return SecretValue(normalized)


@dataclass(frozen=True, slots=True)
class CookieLoginRequest:
    account_id: UUID
    platform: Platform
    operation_id: UUID
    cookie: SecretValue = field(repr=False)
    timeout_seconds: float = 45.0
    account_lock_fd: int | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, UUID) or not isinstance(self.operation_id, UUID):
            raise ValueError("cookie_login_identity_invalid")
        object.__setattr__(self, "platform", Platform(self.platform))
        if not isinstance(self.cookie, SecretValue):
            raise ValueError("cookie_header_invalid")
        object.__setattr__(self, "cookie", parse_cookie_header(self.cookie.reveal()))
        if self.account_lock_fd is not None and (type(self.account_lock_fd) is not int or self.account_lock_fd < 0):
            raise ValueError("cookie_login_lock_invalid")
        if (
            type(self.timeout_seconds) not in (int, float)
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 45
        ):
            raise ValueError("cookie_login_budget_invalid")


@dataclass(frozen=True, slots=True)
class CookieLoginResult:
    status: str
    account_id: UUID
    platform: Platform
    operation_id: UUID
    upstream_sha: str | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not str or self.status not in COOKIE_LOGIN_STATUSES:
            raise ValueError("cookie_login_result_invalid")
        if not isinstance(self.account_id, UUID) or not isinstance(self.operation_id, UUID):
            raise ValueError("cookie_login_identity_invalid")
        object.__setattr__(self, "platform", Platform(self.platform))
        if self.upstream_sha is not None and (
            type(self.upstream_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", self.upstream_sha) is None
        ):
            raise ValueError("cookie_login_result_invalid")
        if self.status == "authenticated" and (
            self.upstream_sha is None or self.platform not in COOKIE_LOGIN_PLATFORMS
        ):
            raise ValueError("cookie_login_result_invalid")


class CookieLoginRunner(Protocol):
    def run(
        self,
        request: CookieLoginRequest,
        *,
        cancellation: threading.Event | None = None,
    ) -> CookieLoginResult: ...


__all__ = [
    "COOKIE_LOGIN_PLATFORMS",
    "COOKIE_LOGIN_STATUSES",
    "CookieLoginRequest",
    "CookieLoginResult",
    "CookieLoginRunner",
    "parse_cookie_header",
]
