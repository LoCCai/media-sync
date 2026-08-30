"""Closed asset locator schema v1."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeAlias
from urllib.parse import urlsplit, urlunsplit

from media_sync.media.errors import MediaDownloadError
from media_sync.security.redaction import has_secret_url_path

_STABLE_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_STABLE_KEY = re.compile(r"[A-Za-z0-9._:/-]{1,255}\Z")
_HEX_PAIR = re.compile(r"%[0-9A-Fa-f]{2}")
_SECRET_WORDS = frozenset(
    {
        "auth",
        "authorization",
        "cookie",
        "credential",
        "key",
        "password",
        "secret",
        "signature",
        "token",
    }
)


def _fail(code: str = "locator_invalid") -> MediaDownloadError:
    return MediaDownloadError(code)


def _plain_text(value: object, *, name: bool = False) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise _fail()
    pattern = _STABLE_NAME if name else _STABLE_KEY
    if pattern.fullmatch(value) is None:
        raise _fail()
    lowered_parts = frozenset(re.split(r"[._:/-]+", value.lower()))
    if lowered_parts & _SECRET_WORDS:
        raise _fail("locator_secret_forbidden")
    return value


def _canonical_direct_url(raw: object) -> str:
    if not isinstance(raw, str) or raw != raw.strip() or len(raw) > 4096:
        raise _fail()
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in raw):
        raise _fail()
    if "?" in raw or "#" in raw or "\\" in raw:
        raise _fail("locator_secret_forbidden")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError as exc:
        raise _fail() from exc
    if parsed.scheme.lower() not in {"http", "https"} or hostname is None:
        raise _fail()
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise _fail("locator_secret_forbidden")
    if port is not None and not 1 <= port <= 65535:
        raise _fail()
    try:
        canonical_host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise _fail() from exc
    if not canonical_host or "%" in canonical_host:
        raise _fail()
    path = parsed.path or "/"
    if has_secret_url_path(path):
        raise _fail("locator_secret_forbidden")
    offset = 0
    while True:
        marker = path.find("%", offset)
        if marker < 0:
            break
        if _HEX_PAIR.fullmatch(path[marker : marker + 3]) is None:
            raise _fail()
        offset = marker + 3
    default_port = 80 if parsed.scheme.lower() == "http" else 443
    bracketed_host = f"[{canonical_host}]" if ":" in canonical_host else canonical_host
    authority = bracketed_host if port in {None, default_port} else f"{bracketed_host}:{port}"
    return urlunsplit((parsed.scheme.lower(), authority, path, "", ""))


@dataclass(frozen=True, slots=True)
class DirectLocator:
    """A persistable query-free HTTP(S) locator."""

    url: str
    version: Literal[1] = 1
    type: Literal["direct"] = "direct"

    def __post_init__(self) -> None:
        object.__setattr__(self, "url", _canonical_direct_url(self.url))

    def as_dict(self) -> dict[str, object]:
        return {"type": self.type, "url": self.url, "version": self.version}


@dataclass(frozen=True, slots=True)
class AdapterRefreshLocator:
    """Stable, non-secret keys used by a future adapter refresh implementation."""

    adapter: str
    asset_key: str
    version: Literal[1] = 1
    type: Literal["adapter_refresh"] = "adapter_refresh"

    def __post_init__(self) -> None:
        object.__setattr__(self, "adapter", _plain_text(self.adapter, name=True))
        object.__setattr__(self, "asset_key", _plain_text(self.asset_key))

    def as_dict(self) -> dict[str, object]:
        return {
            "adapter": self.adapter,
            "asset_key": self.asset_key,
            "type": self.type,
            "version": self.version,
        }


AssetLocator: TypeAlias = DirectLocator | AdapterRefreshLocator


@dataclass(frozen=True, slots=True)
class ResolvedLocator:
    """Ephemeral runtime locator that may contain a signed query."""

    url: str = field(repr=False)

    def __post_init__(self) -> None:
        raw = self.url
        if not isinstance(raw, str) or raw != raw.strip() or len(raw) > 4096:
            raise _fail()
        if any(character.isspace() or ord(character) == 0x7F for character in raw) or "\\" in raw:
            raise _fail()
        try:
            parsed = urlsplit(raw)
            port = parsed.port
            hostname = parsed.hostname
        except ValueError as exc:
            raise _fail() from exc
        if parsed.scheme.lower() not in {"http", "https"} or hostname is None:
            raise _fail()
        if parsed.username is not None or parsed.password is not None or parsed.fragment or "#" in raw:
            raise _fail("locator_secret_forbidden")
        if port is not None and not 1 <= port <= 65535:
            raise _fail()
        try:
            canonical_host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise _fail() from exc
        if not canonical_host or "%" in canonical_host:
            raise _fail()
        default_port = 80 if parsed.scheme.lower() == "http" else 443
        bracketed = f"[{canonical_host}]" if ":" in canonical_host else canonical_host
        authority = bracketed if port in {None, default_port} else f"{bracketed}:{port}"
        object.__setattr__(
            self,
            "url",
            urlunsplit((parsed.scheme.lower(), authority, parsed.path or "/", parsed.query, "")),
        )


def parse_locator(value: Mapping[str, object] | str) -> AssetLocator:
    """Parse exactly one known v1 locator form and reject all extensions."""

    if isinstance(value, str):
        try:
            decoded = json.loads(value, object_pairs_hook=_reject_duplicate_keys)
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise _fail() from exc
        if not isinstance(decoded, dict):
            raise _fail()
        raw: Mapping[str, object] = decoded
    elif isinstance(value, Mapping):
        raw = value
    else:
        raise _fail()
    if type(raw.get("version")) is not int or raw.get("version") != 1 or not isinstance(raw.get("type"), str):
        raise _fail()
    locator_type = raw["type"]
    if locator_type == "direct":
        if set(raw) != {"version", "type", "url"}:
            raise _fail()
        return DirectLocator(url=raw["url"] if isinstance(raw["url"], str) else "")
    if locator_type == "adapter_refresh":
        if set(raw) != {"version", "type", "adapter", "asset_key"}:
            raise _fail()
        adapter = raw["adapter"] if isinstance(raw["adapter"], str) else ""
        asset_key = raw["asset_key"] if isinstance(raw["asset_key"], str) else ""
        return AdapterRefreshLocator(adapter=adapter, asset_key=asset_key)
    raise _fail()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            raise _fail()
        result[key] = item
    return result


def canonical_locator_json(locator: AssetLocator) -> str:
    """Return the only canonical serialized locator representation."""

    return json.dumps(locator.as_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def locator_fingerprint(locator: AssetLocator) -> str:
    """Hash the canonical locator without exposing it in logs or paths."""

    return hashlib.sha256(canonical_locator_json(locator).encode("ascii")).hexdigest()


class LocatorRefreshPort(Protocol):
    """Resolve a stable refresh locator to an ephemeral direct target."""

    def resolve(self, locator: AdapterRefreshLocator) -> ResolvedLocator:
        """Return a validated direct locator without persisting it."""
        ...


def resolve_locator(locator: AssetLocator, refresher: LocatorRefreshPort | None = None) -> ResolvedLocator:
    """Resolve a locator, failing with a fixed code when refresh is unavailable."""

    if isinstance(locator, DirectLocator):
        return ResolvedLocator(locator.url)
    if refresher is None:
        raise MediaDownloadError("locator_refresh_unsupported")
    resolved = refresher.resolve(locator)
    if not isinstance(resolved, ResolvedLocator):
        raise MediaDownloadError("locator_invalid")
    return resolved


__all__ = [
    "AdapterRefreshLocator",
    "AssetLocator",
    "DirectLocator",
    "LocatorRefreshPort",
    "ResolvedLocator",
    "canonical_locator_json",
    "locator_fingerprint",
    "parse_locator",
    "resolve_locator",
]
