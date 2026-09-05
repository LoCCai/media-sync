"""Secret-safe process and manifest construction for the MediaCrawler runner."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import math
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from media_sync.domain import LoginMethod, Platform
from media_sync.integrations.mediacrawler.browser_environment import browser_child_environment
from media_sync.security import SecretValue, redact_text, secret_url_components

from .checkout import (
    MEDIACRAWLER_LICENSE,
    MEDIACRAWLER_LICENSE_SHA256,
    VerifiedCheckout,
    VerifiedPython,
    normalize_python_executable,
    verify_mediacrawler_checkout,
    verify_mediacrawler_python,
)
from .policies import (
    MAX_PRIVATE_INPUT_BYTES,
    PRIVATE_INPUT_ENV,
    MediaCrawlerPolicyError,
    RunPaths,
    WatchdogLimits,
    build_run_paths,
    normalize_creator_reference,
    require_confined,
    require_full_history_acknowledgement,
    upstream_login_type,
)
from .subscription_policy import MAX_REQUEST_DELAY_SECONDS

LEGACY_MANIFEST_SCHEMA_VERSION = 2
MANIFEST_SCHEMA_VERSION = 3
PRIVATE_INPUT_SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 1_048_576
RUNNER_SCRIPT = Path(__file__).with_name("runner.py").resolve()

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _strict_manifest_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BridgeConfigurationError("runner manifest contains duplicate fields")
        result[key] = value
    return result


def _reject_manifest_constant(value: str) -> None:
    del value
    raise BridgeConfigurationError("runner manifest contains a non-standard number")


class BridgeConfigurationError(MediaCrawlerPolicyError):
    """A bridge request or runner manifest is malformed."""


class SavedSessionUnavailableError(BridgeConfigurationError):
    """The derived account profile required by saved-session mode is absent."""


class MediaCrawlerRunMode(StrEnum):
    """Checkpoint namespace that a prepared crawl is allowed to advance."""

    FORWARD = "forward"
    BACKFILL = "backfill"


@dataclass(frozen=True, slots=True)
class BridgeRequest:
    """One creator crawl request before any upstream process is started."""

    lock_path: Path
    integration_root: Path
    python_executable: Path
    account_id: UUID
    subscription_id: UUID
    job_id: UUID
    checkpoint_revision_before: int
    intended_mode: MediaCrawlerRunMode
    platform: Platform
    login_method: LoginMethod
    author_remote_id: str = field(repr=False)
    creator_reference: str | SecretValue = field(repr=False)
    license_acknowledged: bool = False
    allow_full_history: bool = False
    cookie: SecretValue | None = field(default=None, repr=False)
    headless: bool = False
    max_items: int = 30
    watchdogs: WatchdogLimits = field(default_factory=WatchdogLimits)
    scheduler_job_id: UUID | None = None
    schedule_revision: int = 0
    attempt: int = 1
    execution_id: UUID | None = None
    sync_run_id: UUID | None = None
    request_delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        try:
            intended_mode = MediaCrawlerRunMode(self.intended_mode)
        except (TypeError, ValueError) as error:
            raise BridgeConfigurationError("intended_mode must be forward or backfill") from error
        object.__setattr__(self, "intended_mode", intended_mode)
        normalized_author_remote_id = self.author_remote_id.strip()
        if not normalized_author_remote_id or len(normalized_author_remote_id) > 255:
            raise BridgeConfigurationError("author_remote_id must contain between 1 and 255 characters")
        if any(not character.isprintable() for character in normalized_author_remote_id):
            raise BridgeConfigurationError("author_remote_id contains control characters")
        object.__setattr__(self, "author_remote_id", normalized_author_remote_id)
        if type(self.checkpoint_revision_before) is not int or self.checkpoint_revision_before < 0:
            raise BridgeConfigurationError("checkpoint_revision_before must be nonnegative")
        if isinstance(self.max_items, bool) or not 1 <= self.max_items <= 1_000:
            raise BridgeConfigurationError("max_items must be between 1 and 1000")
        if not isinstance(self.headless, bool):
            raise BridgeConfigurationError("headless must be boolean")
        scheduler_job_id = self.scheduler_job_id or self.job_id
        if not isinstance(scheduler_job_id, UUID) or scheduler_job_id != self.job_id:
            raise BridgeConfigurationError("scheduler_job_id must match the durable job_id")
        execution_id = self.execution_id or self.job_id
        sync_run_id = self.sync_run_id or self.job_id
        if not isinstance(execution_id, UUID):
            raise BridgeConfigurationError("execution_id must be a UUID")
        if not isinstance(sync_run_id, UUID):
            raise BridgeConfigurationError("sync_run_id must be a UUID")
        if type(self.schedule_revision) is not int or self.schedule_revision < 0:
            raise BridgeConfigurationError("schedule_revision must be nonnegative")
        if type(self.attempt) is not int or self.attempt < 1:
            raise BridgeConfigurationError("attempt must be positive")
        if (
            isinstance(self.request_delay_seconds, bool)
            or not isinstance(self.request_delay_seconds, int | float)
            or not math.isfinite(self.request_delay_seconds)
            or not 0 < self.request_delay_seconds <= MAX_REQUEST_DELAY_SECONDS
        ):
            raise BridgeConfigurationError(
                f"request_delay_seconds must be greater than zero and at most {MAX_REQUEST_DELAY_SECONDS:g}"
            )
        object.__setattr__(self, "scheduler_job_id", scheduler_job_id)
        object.__setattr__(self, "execution_id", execution_id)
        object.__setattr__(self, "sync_run_id", sync_run_id)
        object.__setattr__(self, "request_delay_seconds", float(self.request_delay_seconds))


@dataclass(frozen=True, slots=True)
class RunnerManifest:
    """Private, bounded child input; creator references never enter argv."""

    checkout_root: Path
    lock_path: Path
    python_executable: Path
    integration_root: Path
    account_id: UUID
    subscription_id: UUID
    job_id: UUID
    checkpoint_revision_before: int
    intended_mode: MediaCrawlerRunMode
    account_root: Path
    profile_root: Path
    job_root: Path
    output_root: Path
    upstream_sha: str
    platform: Platform
    login_method: LoginMethod
    author_remote_id_fingerprint_sha256: str
    creator_fingerprint_sha256: str
    license_acknowledged: bool = True
    allow_full_history: bool = False
    headless: bool = False
    max_items: int = 30
    watchdogs: WatchdogLimits = field(default_factory=WatchdogLimits)
    schema_version: int = MANIFEST_SCHEMA_VERSION
    schedule_revision: int | None = 0
    attempt: int | None = 1
    execution_id: UUID | None = None
    sync_run_id: UUID | None = None
    request_delay_seconds: float | None = 2.0
    license_name: str | None = MEDIACRAWLER_LICENSE
    license_sha256: str | None = MEDIACRAWLER_LICENSE_SHA256

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version not in {
            LEGACY_MANIFEST_SCHEMA_VERSION,
            MANIFEST_SCHEMA_VERSION,
        }:
            raise BridgeConfigurationError("unsupported runner manifest schema")
        if self.schema_version == LEGACY_MANIFEST_SCHEMA_VERSION:
            if any(
                value is not None
                for value in (
                    self.schedule_revision,
                    self.attempt,
                    self.execution_id,
                    self.sync_run_id,
                    self.request_delay_seconds,
                    self.license_name,
                    self.license_sha256,
                )
            ):
                raise BridgeConfigurationError("legacy runner manifests cannot acquire v3 identity")
            return

        execution_id = self.execution_id or self.job_id
        sync_run_id = self.sync_run_id or self.job_id
        if type(self.schedule_revision) is not int or self.schedule_revision < 0:
            raise BridgeConfigurationError("runner manifest schedule revision is invalid")
        if type(self.attempt) is not int or self.attempt < 1:
            raise BridgeConfigurationError("runner manifest attempt is invalid")
        if not isinstance(execution_id, UUID) or not isinstance(sync_run_id, UUID):
            raise BridgeConfigurationError("runner manifest execution identity is invalid")
        if (
            isinstance(self.request_delay_seconds, bool)
            or not isinstance(self.request_delay_seconds, int | float)
            or not math.isfinite(self.request_delay_seconds)
            or not 0 < self.request_delay_seconds <= MAX_REQUEST_DELAY_SECONDS
        ):
            raise BridgeConfigurationError("runner manifest request delay is invalid")
        if self.license_name != MEDIACRAWLER_LICENSE or self.license_sha256 != MEDIACRAWLER_LICENSE_SHA256:
            raise BridgeConfigurationError("runner manifest license identity is invalid")
        object.__setattr__(self, "execution_id", execution_id)
        object.__setattr__(self, "sync_run_id", sync_run_id)
        object.__setattr__(self, "request_delay_seconds", float(self.request_delay_seconds))

    @property
    def scheduler_job_id(self) -> UUID:
        """Return the durable scheduler identity (called ``job_id`` in v2)."""

        return self.job_id

    def as_payload(self) -> dict[str, object]:
        if self.schema_version == LEGACY_MANIFEST_SCHEMA_VERSION:
            return {
                "schema_version": LEGACY_MANIFEST_SCHEMA_VERSION,
                "checkout_root": str(self.checkout_root),
                "lock_path": str(self.lock_path),
                "python_executable": str(self.python_executable),
                "integration_root": str(self.integration_root),
                "account_id": str(self.account_id),
                "subscription_id": str(self.subscription_id),
                "job_id": str(self.job_id),
                "checkpoint_revision_before": self.checkpoint_revision_before,
                "intended_mode": self.intended_mode.value,
                "account_root": str(self.account_root),
                "profile_root": str(self.profile_root),
                "job_root": str(self.job_root),
                "output_root": str(self.output_root),
                "upstream_sha": self.upstream_sha,
                "platform": self.platform.value,
                "login_method": self.login_method.value,
                "author_remote_id_fingerprint_sha256": self.author_remote_id_fingerprint_sha256,
                "creator_fingerprint_sha256": self.creator_fingerprint_sha256,
                "license_acknowledged": self.license_acknowledged,
                "allow_full_history": self.allow_full_history,
                "headless": self.headless,
                "max_items": self.max_items,
                "watchdogs": {
                    "max_seconds": self.watchdogs.max_seconds,
                    "max_output_bytes": self.watchdogs.max_output_bytes,
                    "max_output_items": self.watchdogs.max_output_items,
                    "max_output_files": self.watchdogs.max_output_files,
                    "max_line_bytes": self.watchdogs.max_line_bytes,
                    "poll_seconds": self.watchdogs.poll_seconds,
                },
            }
        if (
            self.schedule_revision is None
            or self.attempt is None
            or self.execution_id is None
            or self.sync_run_id is None
            or self.request_delay_seconds is None
            or self.license_name is None
            or self.license_sha256 is None
        ):  # pragma: no cover - construction validates this invariant
            raise BridgeConfigurationError("runner manifest v3 identity is incomplete")
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "checkout_root": str(self.checkout_root),
            "lock_path": str(self.lock_path),
            "python_executable": str(self.python_executable),
            "integration_root": str(self.integration_root),
            "account_id": str(self.account_id),
            "subscription_id": str(self.subscription_id),
            "scheduler_job_id": str(self.scheduler_job_id),
            "schedule_revision": self.schedule_revision,
            "attempt": self.attempt,
            "execution_id": str(self.execution_id),
            "sync_run_id": str(self.sync_run_id),
            "checkpoint_revision_before": self.checkpoint_revision_before,
            "intended_mode": self.intended_mode.value,
            "account_root": str(self.account_root),
            "profile_root": str(self.profile_root),
            "job_root": str(self.job_root),
            "output_root": str(self.output_root),
            "upstream_sha": self.upstream_sha,
            "license_name": self.license_name,
            "license_sha256": self.license_sha256,
            "platform": self.platform.value,
            "login_method": self.login_method.value,
            "author_remote_id_fingerprint_sha256": self.author_remote_id_fingerprint_sha256,
            "creator_fingerprint_sha256": self.creator_fingerprint_sha256,
            "license_acknowledged": self.license_acknowledged,
            "allow_full_history": self.allow_full_history,
            "headless": self.headless,
            "max_items": self.max_items,
            "request_delay_seconds": self.request_delay_seconds,
            "watchdogs": {
                "max_seconds": self.watchdogs.max_seconds,
                "max_output_bytes": self.watchdogs.max_output_bytes,
                "max_output_items": self.watchdogs.max_output_items,
                "max_output_files": self.watchdogs.max_output_files,
                "max_line_bytes": self.watchdogs.max_line_bytes,
                "poll_seconds": self.watchdogs.poll_seconds,
            },
        }

    @classmethod
    def load(cls, manifest_path: Path) -> RunnerManifest:
        """Load and structurally validate one private runner manifest."""

        resolved_manifest = manifest_path.expanduser().resolve()
        try:
            if not resolved_manifest.is_file() or resolved_manifest.stat().st_size > MAX_MANIFEST_BYTES:
                raise BridgeConfigurationError("runner manifest is missing or exceeds the size limit")
            raw = json.loads(
                resolved_manifest.read_text(encoding="utf-8"),
                object_pairs_hook=_strict_manifest_object,
                parse_constant=_reject_manifest_constant,
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise BridgeConfigurationError("runner manifest could not be read safely") from error
        if (
            not isinstance(raw, Mapping)
            or type(raw.get("schema_version")) is not int
            or raw.get("schema_version") not in {LEGACY_MANIFEST_SCHEMA_VERSION, MANIFEST_SCHEMA_VERSION}
        ):
            raise BridgeConfigurationError("unsupported runner manifest schema")
        schema_version = raw["schema_version"]
        common_keys = {
            "schema_version",
            "checkout_root",
            "lock_path",
            "python_executable",
            "integration_root",
            "account_id",
            "subscription_id",
            "checkpoint_revision_before",
            "intended_mode",
            "account_root",
            "profile_root",
            "job_root",
            "output_root",
            "upstream_sha",
            "platform",
            "login_method",
            "author_remote_id_fingerprint_sha256",
            "creator_fingerprint_sha256",
            "license_acknowledged",
            "allow_full_history",
            "headless",
            "max_items",
            "watchdogs",
        }
        legacy_keys = common_keys | {"job_id"}
        v3_keys = common_keys | {
            "scheduler_job_id",
            "schedule_revision",
            "attempt",
            "execution_id",
            "sync_run_id",
            "license_name",
            "license_sha256",
            "request_delay_seconds",
        }
        expected_keys = legacy_keys if schema_version == LEGACY_MANIFEST_SCHEMA_VERSION else v3_keys
        if set(raw) != expected_keys:
            raise BridgeConfigurationError("runner manifest contains unsupported fields")

        def text_value(name: str) -> str:
            value = raw.get(name)
            if not isinstance(value, str) or not value.strip():
                raise BridgeConfigurationError(f"runner manifest {name} must be a non-empty string")
            return value.strip()

        def boolean_value(name: str) -> bool:
            value = raw.get(name)
            if not isinstance(value, bool):
                raise BridgeConfigurationError(f"runner manifest {name} must be boolean")
            return value

        def uuid_value(name: str) -> UUID:
            value = text_value(name)
            try:
                parsed = UUID(value)
            except ValueError as error:
                raise BridgeConfigurationError("runner manifest contains an invalid UUID") from error
            if str(parsed) != value:
                raise BridgeConfigurationError("runner manifest UUIDs must use canonical lowercase form")
            return parsed

        try:
            account_id = UUID(text_value("account_id"))
            subscription_id = UUID(text_value("subscription_id"))
            intended_mode = MediaCrawlerRunMode(text_value("intended_mode"))
            platform = Platform(text_value("platform"))
            login_method = LoginMethod(text_value("login_method"))
        except ValueError as error:
            raise BridgeConfigurationError("runner manifest contains an unsupported identifier or enum") from error
        if str(account_id) != text_value("account_id") or str(subscription_id) != text_value("subscription_id"):
            raise BridgeConfigurationError("runner manifest UUIDs must use canonical lowercase form")

        if schema_version == LEGACY_MANIFEST_SCHEMA_VERSION:
            job_id = uuid_value("job_id")
            schedule_revision: int | None = None
            attempt: int | None = None
            execution_id: UUID | None = None
            sync_run_id: UUID | None = None
            request_delay_seconds: float | None = None
            license_name: str | None = None
            license_sha256: str | None = None
        else:
            job_id = uuid_value("scheduler_job_id")
            execution_id = uuid_value("execution_id")
            sync_run_id = uuid_value("sync_run_id")
            schedule_revision = raw.get("schedule_revision")
            attempt = raw.get("attempt")
            request_delay_seconds = raw.get("request_delay_seconds")
            if type(schedule_revision) is not int or schedule_revision < 0:
                raise BridgeConfigurationError("runner manifest schedule revision is invalid")
            if type(attempt) is not int or attempt < 1:
                raise BridgeConfigurationError("runner manifest attempt is invalid")
            if (
                isinstance(request_delay_seconds, bool)
                or not isinstance(request_delay_seconds, int | float)
                or not math.isfinite(request_delay_seconds)
                or not 0 < request_delay_seconds <= MAX_REQUEST_DELAY_SECONDS
            ):
                raise BridgeConfigurationError("runner manifest request delay is invalid")
            license_name = text_value("license_name")
            license_sha256 = text_value("license_sha256").lower()
            if license_name != MEDIACRAWLER_LICENSE or license_sha256 != MEDIACRAWLER_LICENSE_SHA256:
                raise BridgeConfigurationError("runner manifest license identity is invalid")

        raw_watchdogs = raw.get("watchdogs")
        if not isinstance(raw_watchdogs, Mapping) or set(raw_watchdogs) != {
            "max_seconds",
            "max_output_bytes",
            "max_output_items",
            "max_output_files",
            "max_line_bytes",
            "poll_seconds",
        }:
            raise BridgeConfigurationError("runner manifest watchdogs must be an object")
        max_items = raw.get("max_items")
        if type(max_items) is not int:
            raise BridgeConfigurationError("runner manifest max_items must be an integer")
        checkpoint_revision_before = raw.get("checkpoint_revision_before")
        if type(checkpoint_revision_before) is not int or checkpoint_revision_before < 0:
            raise BridgeConfigurationError("runner manifest checkpoint revision is invalid")

        def finite_number(name: str) -> int | float:
            value = raw_watchdogs.get(name)
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise BridgeConfigurationError("runner manifest watchdog limits are invalid")
            converted = float(value)
            if not (converted > 0 and converted < float("inf")):
                raise BridgeConfigurationError("runner manifest watchdog limits are invalid")
            return value

        def positive_integer(name: str) -> int:
            value = raw_watchdogs.get(name)
            if type(value) is not int or value < 1:
                raise BridgeConfigurationError("runner manifest watchdog limits are invalid")
            return value

        try:
            watchdogs = WatchdogLimits(
                max_seconds=finite_number("max_seconds"),
                max_output_bytes=positive_integer("max_output_bytes"),
                max_output_items=positive_integer("max_output_items"),
                max_output_files=positive_integer("max_output_files"),
                max_line_bytes=positive_integer("max_line_bytes"),
                poll_seconds=finite_number("poll_seconds"),
            )
        except (TypeError, ValueError) as error:
            raise BridgeConfigurationError("runner manifest watchdog limits are invalid") from error

        integration_root = Path(text_value("integration_root")).expanduser().resolve()
        path_identity = execution_id if execution_id is not None else job_id
        expected_paths = build_run_paths(integration_root, platform, account_id, path_identity)
        supplied_paths = {
            "account_root": Path(text_value("account_root")).expanduser().resolve(),
            "profile_root": Path(text_value("profile_root")).expanduser().resolve(),
            "job_root": Path(text_value("job_root")).expanduser().resolve(),
            "output_root": Path(text_value("output_root")).expanduser().resolve(),
        }
        for name, supplied in supplied_paths.items():
            try:
                require_confined(integration_root, supplied)
            except MediaCrawlerPolicyError as error:
                raise BridgeConfigurationError("runner manifest path layout is not confined") from error
            if supplied != getattr(expected_paths, name):
                raise BridgeConfigurationError("runner manifest path layout is not canonical")
        if resolved_manifest != expected_paths.manifest_path:
            raise BridgeConfigurationError("runner manifest path is not canonical")

        license_acknowledged = boolean_value("license_acknowledged")
        allow_full_history = boolean_value("allow_full_history")
        headless = boolean_value("headless")
        if not 1 <= max_items <= 1_000:
            raise BridgeConfigurationError("runner manifest max_items is outside the allowed range")
        require_full_history_acknowledgement(platform, allow_full_history)
        upstream_login_type(login_method)
        author_remote_id_fingerprint = text_value("author_remote_id_fingerprint_sha256").lower()
        creator_fingerprint = text_value("creator_fingerprint_sha256").lower()
        if _SHA256.fullmatch(author_remote_id_fingerprint) is None or _SHA256.fullmatch(creator_fingerprint) is None:
            raise BridgeConfigurationError("runner manifest creator fingerprint is invalid")
        upstream_sha = text_value("upstream_sha").lower()
        if re.fullmatch(r"[0-9a-f]{40}", upstream_sha) is None:
            raise BridgeConfigurationError("runner manifest upstream SHA is invalid")

        return cls(
            checkout_root=Path(text_value("checkout_root")).expanduser().resolve(),
            lock_path=Path(text_value("lock_path")).expanduser().resolve(),
            python_executable=normalize_python_executable(Path(text_value("python_executable"))),
            integration_root=integration_root,
            account_id=account_id,
            subscription_id=subscription_id,
            job_id=job_id,
            checkpoint_revision_before=checkpoint_revision_before,
            intended_mode=intended_mode,
            account_root=supplied_paths["account_root"],
            profile_root=supplied_paths["profile_root"],
            job_root=supplied_paths["job_root"],
            output_root=supplied_paths["output_root"],
            upstream_sha=upstream_sha,
            platform=platform,
            login_method=login_method,
            author_remote_id_fingerprint_sha256=author_remote_id_fingerprint,
            creator_fingerprint_sha256=creator_fingerprint,
            license_acknowledged=license_acknowledged,
            allow_full_history=allow_full_history,
            headless=headless,
            max_items=max_items,
            watchdogs=watchdogs,
            schema_version=schema_version,
            schedule_revision=schedule_revision,
            attempt=attempt,
            execution_id=execution_id,
            sync_run_id=sync_run_id,
            request_delay_seconds=request_delay_seconds,
            license_name=license_name,
            license_sha256=license_sha256,
        )


@dataclass(frozen=True, slots=True)
class PrivateRunnerInputs:
    """Ephemeral child inputs removed from the environment before manifest loading."""

    creator_reference: str = field(repr=False)
    cookie: str | None = field(default=None, repr=False)

    @classmethod
    def load(cls, payload: str | None, manifest: RunnerManifest) -> PrivateRunnerInputs:
        if payload is None or len(payload.encode("utf-8")) > MAX_PRIVATE_INPUT_BYTES:
            raise BridgeConfigurationError("private runner input is missing or exceeds the size limit")
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as error:
            raise BridgeConfigurationError("private runner input is malformed") from error
        if (
            not isinstance(raw, Mapping)
            or set(raw) != {"schema_version", "creator_reference", "cookie"}
            or type(raw.get("schema_version")) is not int
            or raw.get("schema_version") != PRIVATE_INPUT_SCHEMA_VERSION
        ):
            raise BridgeConfigurationError("private runner input schema is unsupported")
        raw_creator = raw.get("creator_reference")
        raw_cookie = raw.get("cookie")
        if not isinstance(raw_creator, str) or not raw_creator:
            raise BridgeConfigurationError("private runner creator input is invalid")
        if raw_cookie is not None and not isinstance(raw_cookie, str):
            raise BridgeConfigurationError("private runner Cookie input is invalid")
        if isinstance(raw_cookie, str) and (
            not raw_cookie or "\0" in raw_cookie or len(raw_cookie.encode("utf-8")) > 65_536
        ):
            raise BridgeConfigurationError("private runner Cookie input is invalid")

        creator_reference = normalize_creator_reference(manifest.platform, raw_creator)
        fingerprint = hashlib.sha256(creator_reference.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(fingerprint, manifest.creator_fingerprint_sha256):
            raise BridgeConfigurationError("private runner creator input does not match the manifest")
        if manifest.login_method is LoginMethod.COOKIE and raw_cookie is None:
            raise BridgeConfigurationError("private runner Cookie input is required")
        if manifest.login_method is not LoginMethod.COOKIE and raw_cookie is not None:
            raise BridgeConfigurationError("private runner Cookie input is not allowed")
        return cls(creator_reference=creator_reference, cookie=raw_cookie)


@dataclass(frozen=True, slots=True)
class MediaCrawlerRunSpec:
    """A shell-free child-process specification suitable for dry-run review."""

    command: tuple[str, ...]
    cwd: Path
    paths: RunPaths
    manifest: RunnerManifest = field(repr=False)
    environment: Mapping[str, str] = field(repr=False)
    known_secrets: tuple[str | SecretValue, ...] = field(default=(), repr=False)


def _plain_tieba_query_is_canonical(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        port = parsed.port
        query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    return (
        parsed.scheme.lower() in {"http", "https"}
        and parsed.hostname == "tieba.baidu.com"
        and parsed.username is None
        and parsed.password is None
        and port is None
        and parsed.path == "/home/main"
        and not parsed.fragment
        and len(query) == 1
        and query[0][0] == "id"
        and bool(query[0][1])
    )


def _plain_creator_reference_requires_secret(platform: Platform, value: str) -> bool:
    """Fail closed for URL material whose confidentiality is ambiguous."""

    if redact_text(value) != value:
        return True
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "://" in value or "?" in value or "#" in value
    if parsed.fragment:
        return True
    if not parsed.query:
        return False
    return platform is not Platform.TIEBA or not _plain_tieba_query_is_canonical(value)


def _normalize_creator_input(
    platform: Platform,
    value: str | SecretValue,
) -> tuple[str, tuple[str | SecretValue, ...]]:
    """Normalize one creator input while retaining its confidentiality source."""

    if isinstance(value, SecretValue):
        original = value.reveal()
        normalized = normalize_creator_reference(platform, original)
        known_secrets: list[str | SecretValue] = [value]
        seen = {original}
        if normalized not in seen:
            known_secrets.append(normalized)
            seen.add(normalized)
        for candidate in (original, normalized):
            for component in secret_url_components(candidate):
                if component not in seen:
                    known_secrets.append(component)
                    seen.add(component)
        return normalized, tuple(known_secrets)

    if not isinstance(value, str):
        raise BridgeConfigurationError("creator reference must be text or a resolved SecretValue")
    if _plain_creator_reference_requires_secret(platform, value):
        raise BridgeConfigurationError("sensitive creator URL material must be supplied as a resolved SecretValue")
    return normalize_creator_reference(platform, value), ()


def _child_environment(
    creator_reference: str,
    cookie: SecretValue | None,
    *,
    creator_known_secrets: tuple[str | SecretValue, ...] = (),
) -> tuple[Mapping[str, str], tuple[str | SecretValue, ...]]:
    environment = browser_child_environment()
    environment.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PYTHONUNBUFFERED": "1",
        }
    )
    cookie_value = cookie.reveal() if cookie is not None else None
    private_payload = json.dumps(
        {
            "schema_version": PRIVATE_INPUT_SCHEMA_VERSION,
            "creator_reference": creator_reference,
            "cookie": cookie_value,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(private_payload.encode("utf-8")) > MAX_PRIVATE_INPUT_BYTES:
        raise BridgeConfigurationError("private runner input exceeds the size limit")
    environment[PRIVATE_INPUT_ENV] = private_payload
    known_secrets: tuple[str | SecretValue, ...] = ((cookie,) if cookie is not None else ()) + creator_known_secrets
    return MappingProxyType(environment), known_secrets


def _secure_write_manifest(path: Path, manifest: RunnerManifest) -> None:
    payload = json.dumps(manifest.as_payload(), ensure_ascii=False, separators=(",", ":"))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    except BaseException:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)
        raise


class MediaCrawlerBridge:
    """Validate and prepare one isolated external process without executing it."""

    def __init__(
        self,
        python_verifier: Callable[[Path], VerifiedPython] = verify_mediacrawler_python,
    ) -> None:
        self._python_verifier = python_verifier

    def prepare(self, request: BridgeRequest) -> MediaCrawlerRunSpec:
        checkout = verify_mediacrawler_checkout(
            request.lock_path,
            license_acknowledged=request.license_acknowledged,
        )
        python_runtime = self._python_verifier(request.python_executable)
        if not RUNNER_SCRIPT.is_file():
            raise BridgeConfigurationError("isolated MediaCrawler runner script is unavailable")
        require_full_history_acknowledgement(request.platform, request.allow_full_history)
        upstream_login_type(request.login_method)
        creator_reference, creator_known_secrets = _normalize_creator_input(
            request.platform,
            request.creator_reference,
        )

        if request.login_method is LoginMethod.COOKIE and request.cookie is None:
            raise BridgeConfigurationError("Cookie login requires one resolved SecretValue")
        if request.login_method is not LoginMethod.COOKIE and request.cookie is not None:
            raise BridgeConfigurationError("resolved Cookie secret is only valid for Cookie login")

        scheduler_job_id = request.scheduler_job_id
        execution_id = request.execution_id
        sync_run_id = request.sync_run_id
        if scheduler_job_id is None or execution_id is None or sync_run_id is None:  # pragma: no cover
            raise BridgeConfigurationError("bridge request identity is incomplete")

        paths = build_run_paths(
            request.integration_root,
            request.platform,
            request.account_id,
            execution_id,
        )
        if request.login_method is LoginMethod.SAVED_SESSION and (
            not paths.profile_root.is_dir() or not any(paths.profile_root.iterdir())
        ):
            raise SavedSessionUnavailableError("saved-session login requires an existing account profile")

        paths.integration_root.mkdir(parents=True, exist_ok=True)
        paths.account_root.mkdir(parents=True, exist_ok=True)
        try:
            paths.job_root.mkdir(parents=True, exist_ok=False)
        except FileExistsError as error:
            raise BridgeConfigurationError("job path already exists; every run requires a unique job_id") from error
        paths.output_root.mkdir(parents=False, exist_ok=False)
        if any(paths.output_root.iterdir()):  # pragma: no cover - exclusive creation guarantees this
            raise BridgeConfigurationError("MediaCrawler output root must start empty")
        for candidate in (paths.account_root, paths.job_root, paths.output_root):
            require_confined(paths.integration_root, candidate)
            with contextlib.suppress(OSError):
                candidate.chmod(0o700)

        manifest = RunnerManifest(
            checkout_root=checkout.root,
            lock_path=checkout.lock_path,
            python_executable=python_runtime.executable,
            integration_root=paths.integration_root,
            account_id=request.account_id,
            subscription_id=request.subscription_id,
            job_id=scheduler_job_id,
            checkpoint_revision_before=request.checkpoint_revision_before,
            intended_mode=request.intended_mode,
            account_root=paths.account_root,
            profile_root=paths.profile_root,
            job_root=paths.job_root,
            output_root=paths.output_root,
            upstream_sha=checkout.commit,
            license_name=checkout.license_name,
            license_sha256=MEDIACRAWLER_LICENSE_SHA256,
            platform=request.platform,
            login_method=request.login_method,
            author_remote_id_fingerprint_sha256=hashlib.sha256(request.author_remote_id.encode("utf-8")).hexdigest(),
            creator_fingerprint_sha256=hashlib.sha256(creator_reference.encode("utf-8")).hexdigest(),
            license_acknowledged=True,
            allow_full_history=request.allow_full_history,
            headless=request.headless,
            max_items=request.max_items,
            watchdogs=request.watchdogs,
            schema_version=MANIFEST_SCHEMA_VERSION,
            schedule_revision=request.schedule_revision,
            attempt=request.attempt,
            execution_id=execution_id,
            sync_run_id=sync_run_id,
            request_delay_seconds=request.request_delay_seconds,
        )
        environment, known_secrets = _child_environment(
            creator_reference,
            request.cookie,
            creator_known_secrets=creator_known_secrets,
        )
        _secure_write_manifest(paths.manifest_path, manifest)
        command = (
            str(python_runtime.executable),
            "-I",
            "-u",
            "-B",
            str(RUNNER_SCRIPT),
            "--manifest",
            str(paths.manifest_path),
        )
        return MediaCrawlerRunSpec(
            command=command,
            cwd=checkout.root,
            paths=paths,
            manifest=manifest,
            environment=environment,
            known_secrets=known_secrets,
        )


def verify_manifest_checkout(manifest: RunnerManifest) -> VerifiedCheckout:
    """Re-verify the checkout in the child immediately before any import."""

    verified = verify_mediacrawler_checkout(
        manifest.lock_path,
        license_acknowledged=manifest.license_acknowledged,
    )
    if verified.root != manifest.checkout_root or verified.commit != manifest.upstream_sha:
        raise BridgeConfigurationError("runner manifest checkout does not match the verified lock")
    return verified


__all__ = [
    "LEGACY_MANIFEST_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "MAX_MANIFEST_BYTES",
    "PRIVATE_INPUT_SCHEMA_VERSION",
    "RUNNER_SCRIPT",
    "BridgeConfigurationError",
    "BridgeRequest",
    "MediaCrawlerBridge",
    "MediaCrawlerRunMode",
    "MediaCrawlerRunSpec",
    "PrivateRunnerInputs",
    "RunnerManifest",
    "SavedSessionUnavailableError",
    "verify_manifest_checkout",
]
