"""Deterministic discovery fingerprints for durable asset generations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from media_sync.security.redaction import has_secret_url_path

ASSET_IDENTITY_VERSION = 1


@dataclass(frozen=True, slots=True)
class AssetFingerprints:
    """Semantic identity and exact persisted-locator fingerprints."""

    semantic: str
    locator: str


def _canonical_sha256(value: Mapping[str, Any], *, ensure_ascii: bool = False) -> str:
    payload = json.dumps(value, ensure_ascii=ensure_ascii, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def asset_source_hint(source_url: str | None) -> str | None:
    """Return a query-, fragment- and userinfo-free HTTP(S) origin/path hint."""

    if source_url is None:
        return None
    if source_url != source_url.strip() or len(source_url) > 4_096:
        return None
    if "\\" in source_url or any(ord(character) < 0x20 or ord(character) == 0x7F for character in source_url):
        return None
    try:
        parsed = urlsplit(source_url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if ("?" in source_url and not parsed.query) or ("#" in source_url and not parsed.fragment):
        return None
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or hostname is None:
        return None
    try:
        normalized_host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    if not normalized_host or "%" in normalized_host:
        return None
    if has_secret_url_path(parsed.path):
        return None
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    default_port = 80 if scheme == "http" else 443
    authority = normalized_host if port in {None, default_port} else f"{normalized_host}:{port}"
    return urlunsplit((scheme, authority, parsed.path or "/", "", ""))


def stable_asset_key(
    *,
    platform: str,
    content_remote_type: str,
    content_remote_id: str,
    kind: str,
    position: int,
    remote_id: str | None,
) -> str:
    """Build a non-secret adapter refresh key from stable remote identity."""

    return _canonical_sha256(
        {
            "version": ASSET_IDENTITY_VERSION,
            "platform": platform,
            "content_remote_type": content_remote_type,
            "content_remote_id": content_remote_id,
            "kind": kind,
            "position": position,
            "remote_id": remote_id,
        },
        ensure_ascii=True,
    )


def asset_fingerprints(
    *,
    platform: str,
    content_remote_type: str,
    content_remote_id: str,
    kind: str,
    position: int,
    remote_id: str | None,
    source_url: str | None,
    locator: Mapping[str, Any],
    width: int | None,
    height: int | None,
    duration_ms: int | None,
) -> AssetFingerprints:
    """Build v1 fingerprints while excluding query-only URL rotation semantically."""

    semantic_source = asset_source_hint(source_url)
    semantic: dict[str, Any] = {
        "version": ASSET_IDENTITY_VERSION,
        "platform": platform,
        "content_remote_type": content_remote_type,
        "content_remote_id": content_remote_id,
        "kind": kind,
        "position": position,
        "remote_id": remote_id,
        "source": semantic_source,
        "width": width,
        "height": height,
        "duration_ms": duration_ms,
    }
    # A refresh locator can be the only stable evidence for an asset without a
    # direct URL.  Such locators are closed, secret-free contracts; including
    # them prevents reuse when their stable media key changes.
    if semantic_source is None:
        semantic["locator"] = dict(locator)

    return AssetFingerprints(
        semantic=_canonical_sha256(semantic),
        locator=_canonical_sha256(dict(locator), ensure_ascii=True),
    )


__all__ = [
    "ASSET_IDENTITY_VERSION",
    "AssetFingerprints",
    "asset_fingerprints",
    "asset_source_hint",
    "stable_asset_key",
]
