"""Validation for ephemeral Xiaohongshu CDN media locators."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_MAX_XHS_VIDEO_URL_CHARS = 4_096
_XHS_MEDIA_HOST = "xhscdn.com"
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z", re.ASCII)


def validate_xhs_video_url(value: str) -> str:
    """Return one bounded XHS CDN URL unchanged or raise ``ValueError``."""

    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or len(value) > _MAX_XHS_VIDEO_URL_CHARS
        or any(character.isspace() for character in value)
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise ValueError("invalid XHS video URL")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
        if hostname is None:
            raise ValueError("invalid XHS video URL")
        if hostname.endswith(".."):
            raise ValueError("invalid XHS video URL")
        normalized_host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError) as exc:
        raise ValueError("invalid XHS video URL") from exc

    scheme = parsed.scheme.lower()
    default_port = 80 if scheme == "http" else 443 if scheme == "https" else None
    if (
        default_port is None
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, default_port}
        or parsed.fragment
        or parsed.path in {"", "/"}
        or not _is_dns_hostname(normalized_host)
        or "%" in normalized_host
        or not (normalized_host == _XHS_MEDIA_HOST or normalized_host.endswith(f".{_XHS_MEDIA_HOST}"))
    ):
        raise ValueError("invalid XHS video URL")
    return value


def _is_dns_hostname(value: str) -> bool:
    labels = value.split(".")
    return len(value) <= 253 and all(_DNS_LABEL.fullmatch(label) is not None for label in labels)


__all__ = ["validate_xhs_video_url"]
