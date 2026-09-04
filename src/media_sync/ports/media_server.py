"""Provider-neutral contracts for bounded media-server operations."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

MediaServerProvider = Literal["emby", "jellyfin"]

_SAFE_CODE = re.compile(r"media_server_[a-z0-9_]+\Z")
_SERVER_VERSION = re.compile(r"(?=.{1,64}\Z)[0-9]+(?:\.[0-9]+){0,7}\Z")
_PROVIDER_KEY = re.compile(r"media-sync-[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?-creator\Z")
_ERROR_MESSAGES: dict[str, str] = {
    "media_server_not_configured": "media server is not configured",
    "media_server_operations_disabled": "media-server operations are disabled",
    "media_server_scan_cancelled": "media-server scan was cancelled before dispatch",
    "media_server_secret_unavailable": "media-server credentials are unavailable",
    "media_server_dns_failed": "media-server address resolution failed",
    "media_server_address_forbidden": "media-server address is outside the configured policy",
    "media_server_transport": "media-server transport failed",
    "media_server_timeout": "media-server request deadline was exceeded",
    "media_server_redirect_forbidden": "media-server redirect was rejected",
    "media_server_authentication_failed": "media-server authentication failed",
    "media_server_http_retryable": "media server is temporarily unavailable",
    "media_server_http_terminal": "media server rejected the request",
    "media_server_header_limit": "media-server response headers exceeded a limit",
    "media_server_body_limit": "media-server response body exceeded a limit",
    "media_server_response_invalid": "media-server response is invalid",
    "media_server_schema_invalid": "media-server response schema is unsupported",
    "media_server_provider_mismatch": "configured media-server provider does not match the server",
    "media_server_library_not_found": "configured media-server library was not found",
    "media_server_library_ambiguous": "configured media-server library is ambiguous",
    "media_server_library_path_mismatch": "configured media-server library path does not match",
    "media_server_targeted_scan_unsupported": "media server does not support targeted library refresh",
    "media_server_scan_rejected": "media server rejected the targeted library refresh",
    "media_server_scan_acceptance_unknown": "targeted library refresh acceptance is unknown",
    "media_server_item_lookup_ambiguous": "media-server item lookup found multiple exact matches",
    "media_server_item_lookup_incomplete": "media-server item lookup could not prove a complete result",
    "media_server_publication_not_ready": "current media-server publication is not ready",
    "media_server_publication_changed": "media-server publication changed during validation",
}


class MediaServerError(RuntimeError):
    """A fixed-code failure that never includes remote or credential material."""

    def __init__(self, code: str, retryable: bool = False) -> None:
        if not isinstance(code, str) or _SAFE_CODE.fullmatch(code) is None or code not in _ERROR_MESSAGES:
            raise ValueError("unknown media-server error code")
        if not isinstance(retryable, bool):
            raise TypeError("retryable must be a bool")
        self.code = code
        self.retryable = retryable
        self.message = _ERROR_MESSAGES[code]
        super().__init__(f"{code}: {self.message}")

    def __repr__(self) -> str:
        return f"MediaServerError(code={self.code!r}, retryable={self.retryable!r})"


def _validated_provider(value: object) -> MediaServerProvider:
    if value not in {"emby", "jellyfin"}:
        raise ValueError("provider must be emby or jellyfin")
    return value  # type: ignore[return-value]


def validate_media_server_version(value: object) -> str:
    """Return one bounded numeric-dotted server version or fail closed."""

    if not isinstance(value, str) or _SERVER_VERSION.fullmatch(value) is None:
        raise ValueError("server_version must use the closed conservative version format")
    return value


def _validated_digest(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("library_id_digest must be a lowercase SHA-256 digest")
    return value


def _validated_bounded_text(value: object, *, name: str, max_chars: int) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= max_chars
        or any(
            ord(character) < 0x20 or ord(character) == 0x7F or 0xD800 <= ord(character) <= 0xDFFF for character in value
        )
    ):
        raise ValueError(f"{name} must be bounded non-control text")
    return value


@dataclass(frozen=True, slots=True)
class MediaServerLookupTarget:
    """In-memory exact selector derived from one validated publication."""

    provider_key: str
    provider_value: str = field(repr=False)
    server_path: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.provider_key, str) or _PROVIDER_KEY.fullmatch(self.provider_key) is None:
            raise ValueError("provider_key must use the managed creator-provider format")
        object.__setattr__(
            self,
            "provider_value",
            _validated_bounded_text(self.provider_value, name="provider_value", max_chars=4_096),
        )
        object.__setattr__(
            self,
            "server_path",
            _validated_bounded_text(self.server_path, name="server_path", max_chars=1_024),
        )


@dataclass(frozen=True, slots=True)
class MediaServerItemLookupResult:
    """Complete lookup evidence with remote item material retained in memory only."""

    lookup_state: Literal["not_found", "matched"]
    inspected_item_count: int
    page_count: int
    response_byte_count: int
    item_id_set_fingerprint: str = field(repr=False)
    item_id: str | None = field(default=None, repr=False)
    etag: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.lookup_state not in {"not_found", "matched"}:
            raise ValueError("lookup_state must be not_found or matched")
        for name, value in (
            ("inspected_item_count", self.inspected_item_count),
            ("page_count", self.page_count),
            ("response_byte_count", self.response_byte_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.page_count < 1:
            raise ValueError("page_count must be positive")
        object.__setattr__(self, "item_id_set_fingerprint", _validated_digest(self.item_id_set_fingerprint))
        if self.lookup_state == "matched":
            object.__setattr__(
                self,
                "item_id",
                _validated_bounded_text(self.item_id, name="item_id", max_chars=128),
            )
            if self.etag is not None:
                object.__setattr__(
                    self,
                    "etag",
                    _validated_bounded_text(self.etag, name="etag", max_chars=4_096),
                )
        elif self.item_id is not None or self.etag is not None:
            raise ValueError("not_found lookup results cannot retain an item identity")


@dataclass(frozen=True, slots=True)
class MediaServerProbeResult:
    """Allowlisted evidence from server identity and exact library discovery."""

    provider: MediaServerProvider
    server_version: str
    library_id_digest: str
    library_present: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _validated_provider(self.provider))
        object.__setattr__(self, "server_version", validate_media_server_version(self.server_version))
        object.__setattr__(self, "library_id_digest", _validated_digest(self.library_id_digest))
        if not isinstance(self.library_present, bool):
            raise TypeError("library_present must be a bool")


@dataclass(frozen=True, slots=True)
class MediaServerScanResult:
    """Allowlisted evidence that the one targeted refresh was accepted."""

    provider: MediaServerProvider
    server_version: str
    library_id_digest: str
    library_present: bool = True
    scan_state: Literal["accepted"] = "accepted"

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _validated_provider(self.provider))
        object.__setattr__(self, "server_version", validate_media_server_version(self.server_version))
        object.__setattr__(self, "library_id_digest", _validated_digest(self.library_id_digest))
        if not isinstance(self.library_present, bool):
            raise TypeError("library_present must be a bool")
        if self.scan_state != "accepted":
            raise ValueError("scan_state must be accepted")


@runtime_checkable
class MediaServerLookupPort(Protocol):
    """Optional read-only exact item lookup boundary."""

    def lookup_item(self, target: MediaServerLookupTarget) -> MediaServerItemLookupResult:
        """Return only a complete absence or complete unique exact match."""
        ...


@runtime_checkable
class MediaServerPort(Protocol):
    """0054-A connection boundary retained for compatibility."""

    @property
    def profile_fingerprint(self) -> str:
        """Return the non-reversible configured-profile identity."""
        ...

    def probe(self) -> MediaServerProbeResult:
        """Read server identity and verify the exact configured library."""
        ...

    def scan(self, cancel_requested: Callable[[], bool]) -> MediaServerScanResult:
        """Submit the exact targeted refresh once, honoring cancellation before dispatch."""
        ...


__all__ = [
    "MediaServerError",
    "MediaServerItemLookupResult",
    "MediaServerLookupPort",
    "MediaServerLookupTarget",
    "MediaServerPort",
    "MediaServerProbeResult",
    "MediaServerProvider",
    "MediaServerScanResult",
    "validate_media_server_version",
]
