"""Provider-neutral contracts for bounded media-server operations."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

MediaServerProvider = Literal["emby", "jellyfin"]

_SAFE_CODE = re.compile(r"media_server_[a-z0-9_]+\Z")
_SERVER_VERSION = re.compile(r"(?=.{1,64}\Z)[0-9]+(?:\.[0-9]+){0,7}\Z")
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
class MediaServerPort(Protocol):
    """Connection boundary consumed by the application service."""

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
    "MediaServerPort",
    "MediaServerProbeResult",
    "MediaServerProvider",
    "MediaServerScanResult",
    "validate_media_server_version",
]
