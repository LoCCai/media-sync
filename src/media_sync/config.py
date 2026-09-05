"""Application configuration with safe local defaults."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from media_sync.security.secrets import SecretError, SecretReference

MediaServerProvider = Literal["emby", "jellyfin"]
MediaServerNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

_MEDIA_SERVER_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_MAX_OPERATOR_ORIGINS = 8


def _canonical_media_server_origin(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("media_server_base_url must be an HTTP(S) origin")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 2048
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized)
        or "\\" in normalized
    ):
        raise ValueError("media_server_base_url must be an HTTP(S) origin")
    try:
        parsed = urlsplit(normalized)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("media_server_base_url must be an HTTP(S) origin") from exc
    scheme = parsed.scheme.lower()
    if (
        scheme not in {"http", "https"}
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.netloc.endswith(":")
    ):
        raise ValueError("media_server_base_url must be an HTTP(S) origin")
    hostname = hostname.rstrip(".")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            canonical_host = hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("media_server_base_url hostname is invalid") from exc
        if (
            not canonical_host
            or len(canonical_host) > 253
            or "%" in canonical_host
            or any(
                not label
                or len(label) > 63
                or label.startswith("-")
                or label.endswith("-")
                or re.fullmatch(r"[a-z0-9-]+", label) is None
                for label in canonical_host.split(".")
            )
        ):
            raise ValueError("media_server_base_url hostname is invalid") from None
    else:
        canonical_host = address.compressed.lower()
    effective_port = port if port is not None else (80 if scheme == "http" else 443)
    if not 1 <= effective_port <= 65535:  # pragma: no cover - urlsplit validates this
        raise ValueError("media_server_base_url port is invalid")
    bracketed = f"[{canonical_host}]" if ":" in canonical_host else canonical_host
    default_port = 80 if scheme == "http" else 443
    authority = bracketed if effective_port == default_port else f"{bracketed}:{effective_port}"
    return urlunsplit((scheme, authority, "", "", ""))


def _canonical_media_server_library_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("media_server_library_id is invalid")
    normalized = value.strip()
    if _MEDIA_SERVER_ID.fullmatch(normalized) is None:
        raise ValueError("media_server_library_id must be 1-128 URL-safe characters")
    return normalized


def _canonical_media_server_library_path(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("media_server_library_path is invalid")
    normalized = value.strip()
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(normalized)
    if (
        not 1 <= len(normalized) <= 1024
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized)
        or not (posix.is_absolute() or windows.is_absolute())
        or ".." in posix.parts
        or ".." in windows.parts
    ):
        raise ValueError("media_server_library_path must be a bounded absolute server path")
    return normalized


def _parse_media_server_cidrs(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    raw_items: object = value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("media_server_allowed_cidrs must not be empty")
        if stripped.startswith("["):
            try:
                raw_items = json.loads(stripped)
            except (TypeError, ValueError) as exc:
                raise ValueError("media_server_allowed_cidrs must be a JSON array or comma-separated list") from exc
        else:
            raw_items = stripped.split(",")
    if not isinstance(raw_items, list | tuple | set | frozenset):
        raise ValueError("media_server_allowed_cidrs must be a sequence")
    networks: dict[tuple[int, int, int], str] = {}
    for item in raw_items:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("media_server_allowed_cidrs contains an invalid network")
        try:
            network = ipaddress.ip_network(item.strip(), strict=False)
        except ValueError as exc:
            raise ValueError("media_server_allowed_cidrs contains an invalid network") from exc
        networks[(network.version, int(network.network_address), network.prefixlen)] = network.with_prefixlen
    if not networks:
        raise ValueError("media_server_allowed_cidrs must contain at least one network")
    return tuple(networks[key] for key in sorted(networks))


def _canonical_operator_origin(value: str) -> str:
    """Return one exact browser origin without retaining ambiguous URL forms."""

    if not isinstance(value, str):
        raise ValueError("operator origin must be an HTTP(S) origin")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 2048
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized)
        or "\\" in normalized
        or "*" in normalized
    ):
        raise ValueError("operator origin must be an HTTP(S) origin")
    try:
        parsed = urlsplit(normalized)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("operator origin must be an HTTP(S) origin") from exc
    scheme = parsed.scheme.lower()
    if (
        scheme not in {"http", "https"}
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.netloc.endswith(":")
    ):
        raise ValueError("operator origin must be an HTTP(S) origin")
    hostname = hostname.rstrip(".")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            canonical_host = hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("operator origin hostname is invalid") from exc
        if (
            not canonical_host
            or len(canonical_host) > 253
            or "%" in canonical_host
            or any(
                not label
                or len(label) > 63
                or label.startswith("-")
                or label.endswith("-")
                or re.fullmatch(r"[a-z0-9-]+", label) is None
                for label in canonical_host.split(".")
            )
        ):
            raise ValueError("operator origin hostname is invalid") from None
    else:
        canonical_host = address.compressed.lower()
    effective_port = port if port is not None else (80 if scheme == "http" else 443)
    if not 1 <= effective_port <= 65535:  # pragma: no cover - urlsplit rejects values above the range
        raise ValueError("operator origin port is invalid")
    bracketed = f"[{canonical_host}]" if ":" in canonical_host else canonical_host
    default_port = 80 if scheme == "http" else 443
    authority = bracketed if effective_port == default_port else f"{bracketed}:{effective_port}"
    return urlunsplit((scheme, authority, "", "", ""))


def _parse_operator_origins(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    raw_items: object = value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("operator_allowed_origins must not be empty")
        if stripped.startswith("["):
            try:
                raw_items = json.loads(stripped)
            except (TypeError, ValueError) as exc:
                raise ValueError("operator_allowed_origins must be a JSON array or comma-separated list") from exc
        else:
            raw_items = stripped.split(",")
    if not isinstance(raw_items, list | tuple):
        raise ValueError("operator_allowed_origins must be a sequence")
    if not 1 <= len(raw_items) <= _MAX_OPERATOR_ORIGINS:
        raise ValueError(f"operator_allowed_origins must contain between 1 and {_MAX_OPERATOR_ORIGINS} origins")
    origins = tuple(_canonical_operator_origin(item) for item in raw_items)
    if len(set(origins)) != len(origins):
        raise ValueError("operator_allowed_origins must not contain duplicates")
    return origins


def _media_server_networks(values: tuple[str, ...]) -> tuple[MediaServerNetwork, ...]:
    return tuple(ipaddress.ip_network(value, strict=True) for value in values)


@dataclass(frozen=True, slots=True)
class MediaServerSafeSummary:
    """Explicit API-safe connection posture with sensitive selectors omitted."""

    configured: bool
    provider: MediaServerProvider | None
    origin: str | None
    library_id_digest: str | None
    profile_fingerprint: str | None
    verify_tls: bool
    timeout_seconds: float
    operations_enabled: bool
    allowed_network_count: int
    library_path_configured: bool
    api_key_configured: bool

    def as_dict(self) -> dict[str, object]:
        """Return a hand-built projection suitable for JSON serialization."""

        return {
            "configured": self.configured,
            "provider": self.provider,
            "origin": self.origin,
            "library_id_digest": self.library_id_digest,
            "profile_fingerprint": self.profile_fingerprint,
            "verify_tls": self.verify_tls,
            "timeout_seconds": self.timeout_seconds,
            "operations_enabled": self.operations_enabled,
            "allowed_network_count": self.allowed_network_count,
            "library_path_configured": self.library_path_configured,
            "api_key_configured": self.api_key_configured,
        }


@dataclass(frozen=True, slots=True, repr=False)
class MediaServerProfile:
    """One canonical, immutable, environment-owned media-server profile."""

    provider: MediaServerProvider
    origin: str
    library_id: str = field(repr=False)
    api_key_secret_reference: SecretReference = field(repr=False)
    library_path: str = field(repr=False)
    allowed_networks: tuple[MediaServerNetwork, ...] = field(repr=False)
    verify_tls: bool = True
    timeout_seconds: float = 10.0
    operations_enabled: bool = False

    def __post_init__(self) -> None:
        provider = self.provider.strip().lower() if isinstance(self.provider, str) else self.provider
        if provider not in {"emby", "jellyfin"}:
            raise ValueError("media-server provider must be emby or jellyfin")
        origin = _canonical_media_server_origin(self.origin)
        library_id = _canonical_media_server_library_id(self.library_id)
        library_path = _canonical_media_server_library_path(self.library_path)
        reference = self.api_key_secret_reference
        if isinstance(reference, str):
            reference = SecretReference.parse(reference)
        if not isinstance(reference, SecretReference):
            raise ValueError("media-server API key must use a typed secret reference")
        if not isinstance(self.allowed_networks, tuple | list) or not self.allowed_networks:
            raise ValueError("media-server profile requires at least one allowed network")
        raw_networks = tuple(str(value) for value in self.allowed_networks)
        canonical_networks = _media_server_networks(_parse_media_server_cidrs(raw_networks) or ())
        timeout = self.timeout_seconds
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not math.isfinite(timeout)
            or not 0.1 <= float(timeout) <= 60.0
        ):
            raise ValueError("media-server timeout must be finite and between 0.1 and 60 seconds")
        if not isinstance(self.verify_tls, bool) or not isinstance(self.operations_enabled, bool):
            raise TypeError("media-server TLS and operation gate values must be bools")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "library_id", library_id)
        object.__setattr__(self, "api_key_secret_reference", reference)
        object.__setattr__(self, "library_path", library_path)
        object.__setattr__(self, "allowed_networks", canonical_networks)
        object.__setattr__(self, "timeout_seconds", float(timeout))

    @property
    def base_url(self) -> str:
        """Compatibility name for the canonical origin."""

        return self.origin

    @property
    def api_key_secret_ref(self) -> SecretReference:
        """Return the internal typed reference, never its resolved value."""

        return self.api_key_secret_reference

    @property
    def allowed_cidrs(self) -> tuple[str, ...]:
        """Return canonical internal network policy entries."""

        return tuple(network.with_prefixlen for network in self.allowed_networks)

    @property
    def library_id_digest(self) -> str:
        payload = f"{self.provider}\0{self.library_id}".encode()
        return hashlib.sha256(payload).hexdigest()

    @property
    def profile_fingerprint(self) -> str:
        payload = {
            "allowed_networks": self.allowed_cidrs,
            "api_key_secret_reference": self.api_key_secret_reference.serialize(),
            "library_id": self.library_id,
            "library_path": self.library_path,
            "origin": self.origin,
            "provider": self.provider,
            "timeout_seconds": self.timeout_seconds,
            "verify_tls": self.verify_tls,
        }
        encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def safe_summary(self) -> MediaServerSafeSummary:
        return MediaServerSafeSummary(
            configured=True,
            provider=self.provider,
            origin=self.origin,
            library_id_digest=self.library_id_digest,
            profile_fingerprint=self.profile_fingerprint,
            verify_tls=self.verify_tls,
            timeout_seconds=self.timeout_seconds,
            operations_enabled=self.operations_enabled,
            allowed_network_count=len(self.allowed_networks),
            library_path_configured=True,
            api_key_configured=True,
        )

    def address_is_allowed(self, value: str) -> bool:
        """Return whether one parsed IP is inside the explicit policy."""

        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return False
        return any(address.version == network.version and address in network for network in self.allowed_networks)

    def __repr__(self) -> str:
        summary = self.safe_summary
        return (
            "MediaServerProfile("
            f"provider={summary.provider!r}, origin={summary.origin!r}, "
            f"library_id_digest={summary.library_id_digest!r}, "
            f"profile_fingerprint={summary.profile_fingerprint!r}, "
            f"verify_tls={summary.verify_tls!r}, timeout_seconds={summary.timeout_seconds!r}, "
            f"operations_enabled={summary.operations_enabled!r}, "
            f"allowed_network_count={summary.allowed_network_count!r})"
        )

    __str__ = __repr__


class Settings(BaseSettings):
    """Runtime settings loaded from ``MEDIA_SYNC_*`` environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="MEDIA_SYNC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    state_dir: Path = Path(".media-sync")
    archive_dir: Path = Path("archive")
    export_dir: Path = Path("exports")
    job_dir: Path = Path("jobs")
    secret_file_dir: Path | None = None
    mediacrawler_lock_path: Path = Path("upstreams.lock.json")
    mediacrawler_python_executable: Path | None = None
    mediacrawler_runtime_dir: Path | None = None
    database_url: str | None = None
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8632, ge=1, le=65535)
    log_level: str = "INFO"
    operator_credential_secret_ref: str | None = Field(default=None, repr=False)
    operator_api_token_secret_ref: str | None = Field(default=None, repr=False)
    operator_allowed_origins: Annotated[tuple[str, ...] | None, NoDecode] = None
    operator_session_ttl_seconds: int = Field(default=28_800, ge=60, le=28_800)
    default_sync_interval_seconds: int = Field(default=21_600, ge=60)
    default_max_items: int = Field(default=30, ge=1, le=1_000)
    max_crawl_seconds: int = Field(default=1_800, ge=30, le=86_400)
    media_server_provider: MediaServerProvider | None = None
    media_server_base_url: str | None = None
    media_server_library_id: str | None = Field(default=None, repr=False)
    media_server_api_key_secret_ref: str | None = Field(default=None, repr=False)
    media_server_library_path: str | None = Field(default=None, repr=False)
    media_server_allowed_cidrs: Annotated[tuple[str, ...] | None, NoDecode] = Field(default=None, repr=False)
    media_server_verify_tls: bool = True
    media_server_timeout_seconds: float = Field(default=10.0, ge=0.1, le=60.0, allow_inf_nan=False)
    media_server_operations_enabled: bool = False
    library_inspection_max_bytes: int = Field(default=1_073_741_824, ge=1, le=1_099_511_627_776)
    library_inspection_deadline_seconds: float = Field(default=10.0, ge=0.01, le=300.0, allow_inf_nan=False)

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper().strip()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalized not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return normalized

    @field_validator("operator_credential_secret_ref", "operator_api_token_secret_ref")
    @classmethod
    def normalize_operator_secret_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return SecretReference.parse(value).serialize()
        except SecretError as exc:
            raise ValueError("operator credentials must use typed secret references") from exc

    @field_validator("operator_allowed_origins", mode="before")
    @classmethod
    def normalize_operator_allowed_origins(cls, value: object) -> tuple[str, ...] | None:
        return _parse_operator_origins(value)

    @field_validator("media_server_provider", mode="before")
    @classmethod
    def normalize_media_server_provider(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("media_server_provider must be emby or jellyfin")
        normalized = value.strip().lower()
        if normalized not in {"emby", "jellyfin"}:
            raise ValueError("media_server_provider must be emby or jellyfin")
        return normalized

    @field_validator("media_server_base_url")
    @classmethod
    def normalize_media_server_base_url(cls, value: str | None) -> str | None:
        return None if value is None else _canonical_media_server_origin(value)

    @field_validator("media_server_library_id")
    @classmethod
    def normalize_media_server_library_id(cls, value: str | None) -> str | None:
        return None if value is None else _canonical_media_server_library_id(value)

    @field_validator("media_server_api_key_secret_ref")
    @classmethod
    def normalize_media_server_secret_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return SecretReference.parse(value).serialize()
        except SecretError as exc:
            raise ValueError("media_server_api_key_secret_ref must be a typed secret reference") from exc

    @field_validator("media_server_library_path")
    @classmethod
    def normalize_media_server_library_path(cls, value: str | None) -> str | None:
        return None if value is None else _canonical_media_server_library_path(value)

    @field_validator("media_server_allowed_cidrs", mode="before")
    @classmethod
    def normalize_media_server_allowed_cidrs(cls, value: object) -> tuple[str, ...] | None:
        return _parse_media_server_cidrs(value)

    @model_validator(mode="after")
    def validate_media_server_profile(self) -> Self:
        if (
            self.operator_credential_secret_ref is not None
            and self.operator_api_token_secret_ref == self.operator_credential_secret_ref
        ):
            raise ValueError("operator browser and API credentials must use distinct secret references")
        values: tuple[object | None, ...] = (
            self.media_server_provider,
            self.media_server_base_url,
            self.media_server_library_id,
            self.media_server_api_key_secret_ref,
            self.media_server_library_path,
            self.media_server_allowed_cidrs,
        )
        configured = [value is not None for value in values]
        if any(configured) and not all(configured):
            raise ValueError("media-server profile fields must be configured all-or-none")
        if self.media_server_operations_enabled and not all(configured):
            raise ValueError("media-server operations cannot be enabled without a complete profile")
        return self

    @property
    def operator_credential_secret_reference(self) -> SecretReference | None:
        value = self.operator_credential_secret_ref
        return SecretReference.parse(value) if value is not None else None

    @property
    def operator_api_token_secret_reference(self) -> SecretReference | None:
        value = self.operator_api_token_secret_ref
        return SecretReference.parse(value) if value is not None else None

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        database_path = (self.state_dir / "media-sync.sqlite3").resolve()
        return f"sqlite+pysqlite:///{database_path.as_posix()}"

    @property
    def resolved_secret_file_dir(self) -> Path:
        """Return the root allowed for relative ``file:`` secret references."""

        return (self.secret_file_dir or self.state_dir / "secrets").expanduser().resolve()

    @property
    def resolved_mediacrawler_runtime_dir(self) -> Path:
        """Return the root for isolated bridge profiles, manifests, and output."""

        return (self.mediacrawler_runtime_dir or self.state_dir / "mediacrawler").expanduser().resolve()

    @property
    def media_server_profile(self) -> MediaServerProfile | None:
        """Return the canonical profile, resolving no secret and doing no I/O."""

        if self.media_server_provider is None:
            return None
        # The all-or-none validator proves these values are populated.
        assert self.media_server_base_url is not None
        assert self.media_server_library_id is not None
        assert self.media_server_api_key_secret_ref is not None
        assert self.media_server_library_path is not None
        assert self.media_server_allowed_cidrs is not None
        return MediaServerProfile(
            provider=self.media_server_provider,
            origin=self.media_server_base_url,
            library_id=self.media_server_library_id,
            api_key_secret_reference=SecretReference.parse(self.media_server_api_key_secret_ref),
            library_path=self.media_server_library_path,
            allowed_networks=_media_server_networks(self.media_server_allowed_cidrs),
            verify_tls=self.media_server_verify_tls,
            timeout_seconds=self.media_server_timeout_seconds,
            operations_enabled=self.media_server_operations_enabled,
        )

    @property
    def media_server_profile_fingerprint(self) -> str | None:
        profile = self.media_server_profile
        return profile.profile_fingerprint if profile is not None else None

    @property
    def media_server_safe_summary(self) -> MediaServerSafeSummary:
        profile = self.media_server_profile
        if profile is not None:
            return profile.safe_summary
        return MediaServerSafeSummary(
            configured=False,
            provider=None,
            origin=None,
            library_id_digest=None,
            profile_fingerprint=None,
            verify_tls=self.media_server_verify_tls,
            timeout_seconds=self.media_server_timeout_seconds,
            operations_enabled=False,
            allowed_network_count=0,
            library_path_configured=False,
            api_key_configured=False,
        )

    @property
    def library_inspection_byte_budget(self) -> int:
        """Compatibility name for the configured per-request byte budget."""

        return self.library_inspection_max_bytes

    @property
    def library_inspection_timeout_seconds(self) -> float:
        """Compatibility name for the configured inspection deadline."""

        return self.library_inspection_deadline_seconds

    def ensure_directories(self) -> None:
        """Create runtime roots without creating or exposing credential files."""

        for path in (self.state_dir, self.archive_dir, self.export_dir, self.job_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide immutable settings snapshot."""

    return Settings()


__all__ = [
    "MediaServerNetwork",
    "MediaServerProfile",
    "MediaServerProvider",
    "MediaServerSafeSummary",
    "Settings",
    "get_settings",
]
