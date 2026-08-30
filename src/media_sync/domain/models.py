"""Immutable entities and value objects shared across application boundaries."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Generic, TypeVar
from urllib.parse import urlparse
from uuid import UUID

from media_sync.domain.enums import (
    AssetKind,
    AuthStatus,
    ContentKind,
    CreatorReferenceKind,
    LoginMethod,
    Platform,
)
from media_sync.domain.errors import DomainValidationError

T = TypeVar("T")


def _required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise DomainValidationError(f"{field_name} must not be blank", field=field_name)
    return normalized


def _optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _utc_datetime(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{field_name} must be timezone-aware", field=field_name)
    return value.astimezone(UTC)


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze(item) for item in value)
    return value


def freeze_mapping(value: Mapping[str, object] | None = None) -> Mapping[str, object]:
    """Return a deeply read-only copy suitable for a frozen snapshot."""

    frozen = _freeze(value or {})
    if not isinstance(frozen, Mapping):  # pragma: no cover - defensive type narrowing
        raise TypeError("freeze_mapping must produce a mapping")
    return frozen


def _validate_http_url(value: str | None, field_name: str) -> str | None:
    normalized = _optional_text(value, field_name)
    if normalized is None:
        return None
    parsed = urlparse(normalized)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise DomainValidationError(f"{field_name} must be an absolute HTTP(S) URL", field=field_name)
    return normalized


@dataclass(frozen=True, slots=True)
class AccountRef:
    """Non-secret account identity passed to platform ports."""

    account_id: UUID
    platform: Platform
    login_method: LoginMethod
    adapter: str = "fake"
    credential_ref: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "adapter", _required_text(self.adapter, "adapter"))
        object.__setattr__(self, "credential_ref", _optional_text(self.credential_ref, "credential_ref"))


@dataclass(frozen=True, slots=True)
class AuthChallenge:
    """Redaction-safe interaction request emitted by an authentication port."""

    method: LoginMethod
    prompt: str
    payload: Mapping[str, object] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "prompt", _required_text(self.prompt, "prompt"))
        object.__setattr__(self, "payload", freeze_mapping(self.payload))


@dataclass(frozen=True, slots=True)
class AuthResult:
    """Authentication outcome containing only opaque, non-secret references."""

    status: AuthStatus
    session_ref: str | None = field(default=None, repr=False)
    expires_at: datetime | None = None
    message: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_ref", _optional_text(self.session_ref, "session_ref"))
        object.__setattr__(self, "expires_at", _utc_datetime(self.expires_at, "expires_at"))
        object.__setattr__(self, "message", _optional_text(self.message, "message"))
        if self.status is AuthStatus.AUTHENTICATED and self.session_ref is None:
            raise DomainValidationError(
                "authenticated results require an opaque session_ref",
                field="session_ref",
            )


@dataclass(frozen=True, slots=True)
class CapabilitySet:
    """Precisely qualified behavior exposed by one platform adapter."""

    platform: Platform
    login_methods: frozenset[LoginMethod]
    creator_reference_kinds: frozenset[CreatorReferenceKind]
    content_kinds: frozenset[ContentKind]
    asset_kinds: frozenset[AssetKind]
    interactive_login_methods: frozenset[LoginMethod] = frozenset()
    supports_incremental_cursor: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "login_methods", frozenset(self.login_methods))
        object.__setattr__(self, "creator_reference_kinds", frozenset(self.creator_reference_kinds))
        object.__setattr__(self, "content_kinds", frozenset(self.content_kinds))
        object.__setattr__(self, "asset_kinds", frozenset(self.asset_kinds))
        object.__setattr__(self, "interactive_login_methods", frozenset(self.interactive_login_methods))
        unsupported_interactive = self.interactive_login_methods - self.login_methods
        if unsupported_interactive:
            values = sorted(method.value for method in unsupported_interactive)
            raise DomainValidationError(
                f"interactive login methods must be supported login methods: {values}",
                field="interactive_login_methods",
            )
        if not self.creator_reference_kinds:
            raise DomainValidationError(
                "at least one creator reference kind is required",
                field="creator_reference_kinds",
            )

    def supports_login(self, method: LoginMethod) -> bool:
        return method in self.login_methods

    def requires_interaction(self, method: LoginMethod) -> bool:
        return method in self.interactive_login_methods


@dataclass(frozen=True, slots=True)
class Cursor:
    """Opaque adapter-owned pagination token."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _required_text(self.value, "cursor"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    """One immutable page with an explicit continuation contract."""

    items: tuple[T, ...]
    next_cursor: Cursor | None
    has_more: bool

    def __init__(
        self,
        items: Iterable[T],
        *,
        next_cursor: Cursor | None = None,
        has_more: bool = False,
    ) -> None:
        object.__setattr__(self, "items", tuple(items))
        object.__setattr__(self, "next_cursor", next_cursor)
        object.__setattr__(self, "has_more", has_more)
        self.__post_init__()

    def __post_init__(self) -> None:
        if self.has_more and self.next_cursor is None:
            raise DomainValidationError(
                "a page with has_more=True requires next_cursor",
                field="next_cursor",
            )
        if not self.has_more and self.next_cursor is not None:
            raise DomainValidationError(
                "a terminal page must not expose next_cursor",
                field="next_cursor",
            )


@dataclass(frozen=True, slots=True)
class AuthorSnapshot:
    """Normalized immutable creator metadata returned by an adapter."""

    platform: Platform
    remote_id: str
    display_name: str
    handle: str | None = None
    profile_url: str | None = field(default=None, repr=False)
    avatar_url: str | None = field(default=None, repr=False)
    raw: Mapping[str, object] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "remote_id", _required_text(self.remote_id, "remote_id"))
        object.__setattr__(self, "display_name", _required_text(self.display_name, "display_name"))
        object.__setattr__(self, "handle", _optional_text(self.handle, "handle"))
        object.__setattr__(self, "profile_url", _validate_http_url(self.profile_url, "profile_url"))
        object.__setattr__(self, "avatar_url", _validate_http_url(self.avatar_url, "avatar_url"))
        object.__setattr__(self, "raw", freeze_mapping(self.raw))


@dataclass(frozen=True, slots=True)
class ContentSnapshot:
    """Normalized immutable creator-content metadata returned by an adapter."""

    platform: Platform
    remote_id: str
    author_remote_id: str
    kind: ContentKind
    remote_type: str = "content"
    title: str | None = None
    body: str | None = field(default=None, repr=False)
    canonical_url: str | None = field(default=None, repr=False)
    published_at: datetime | None = None
    metrics: Mapping[str, int | float] = field(default_factory=dict)
    raw: Mapping[str, object] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "remote_id", _required_text(self.remote_id, "remote_id"))
        object.__setattr__(
            self,
            "author_remote_id",
            _required_text(self.author_remote_id, "author_remote_id"),
        )
        object.__setattr__(self, "remote_type", _required_text(self.remote_type, "remote_type"))
        object.__setattr__(self, "title", _optional_text(self.title, "title"))
        object.__setattr__(self, "body", _optional_text(self.body, "body"))
        object.__setattr__(self, "canonical_url", _validate_http_url(self.canonical_url, "canonical_url"))
        object.__setattr__(self, "published_at", _utc_datetime(self.published_at, "published_at"))
        normalized_metrics: dict[str, int | float] = {}
        for key, value in self.metrics.items():
            metric_name = _required_text(str(key), "metric_name")
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise DomainValidationError(
                    f"metric {metric_name!r} must be numeric",
                    field="metrics",
                )
            normalized_metrics[metric_name] = value
        object.__setattr__(self, "metrics", MappingProxyType(normalized_metrics))
        object.__setattr__(self, "raw", freeze_mapping(self.raw))


@dataclass(frozen=True, slots=True)
class AssetSnapshot:
    """Normalized immutable remote asset metadata returned by an adapter."""

    platform: Platform
    remote_id: str
    content_remote_id: str
    kind: AssetKind
    source_url: str | None = field(default=None, repr=False)
    position: int = 0
    mime_type: str | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    raw: Mapping[str, object] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "remote_id", _required_text(self.remote_id, "remote_id"))
        object.__setattr__(
            self,
            "content_remote_id",
            _required_text(self.content_remote_id, "content_remote_id"),
        )
        object.__setattr__(self, "source_url", _validate_http_url(self.source_url, "source_url"))
        if self.position < 0:
            raise DomainValidationError("position must be non-negative", field="position")
        object.__setattr__(self, "mime_type", _optional_text(self.mime_type, "mime_type"))
        if self.size_bytes is not None and self.size_bytes < 0:
            raise DomainValidationError("size_bytes must be non-negative", field="size_bytes")
        checksum = _optional_text(self.checksum_sha256, "checksum_sha256")
        if checksum is not None:
            checksum = checksum.lower()
            if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
                raise DomainValidationError(
                    "checksum_sha256 must contain exactly 64 hexadecimal characters",
                    field="checksum_sha256",
                )
        object.__setattr__(self, "checksum_sha256", checksum)
        object.__setattr__(self, "raw", freeze_mapping(self.raw))


__all__ = [
    "AccountRef",
    "AssetSnapshot",
    "AuthChallenge",
    "AuthResult",
    "AuthorSnapshot",
    "CapabilitySet",
    "ContentSnapshot",
    "Cursor",
    "Page",
    "freeze_mapping",
]
