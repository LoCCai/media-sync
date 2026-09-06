"""Closed event vocabulary: no log messages, exception text or remote data."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

EVENT_SCHEMA_VERSION = 1
MAX_EVENT_BYTES = 4096
MAX_NUMBER = 9_007_199_254_740_991
EVENT_CODES = frozenset(
    {
        "application_log_redacted",
        "request_finished",
        "command_started",
        "command_finished",
        "service_started",
        "service_stopped",
        "operation_started",
        "operation_phase_changed",
        "operation_finished",
        "job_started",
        "job_finished",
        "supervisor_started",
        "supervisor_stopped",
        "supervisor_failed",
        "login_stage",
        "login_terminal",
        "login_diagnostics_degraded",
        "output_policy_saved",
        "log_store_degraded",
    }
)
MODULES = frozenset(
    {
        "api",
        "cli",
        "login",
        "cookie_login",
        "crawler",
        "download",
        "scheduler",
        "pipeline",
        "exporter",
        "library",
        "media_server",
        "supervisor",
        "output_directories",
        "log_store",
        "application",
        "creator_profile",
        "archive",
    }
)
LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})
PHASES = frozenset(
    {
        "starting",
        "preparing",
        "running",
        "probing",
        "discovering",
        "authenticating",
        "downloading",
        "claiming_jobs",
        "jobs_processed",
        "exporting",
        "syncing",
        "ingesting",
        "finalizing",
        "reconciling",
        "completed",
        "stopping",
        "preflight",
        "account_lock",
        "browser_launch",
        "platform_navigation",
        "session_probe",
        "login_dialog",
        "qr_locate",
        "qr_image_fetch",
        "qr_relay",
        "waiting_scan",
        "login_confirmation",
        "profile_finalize",
        "cleanup",
        "upstream_execution",
        "unknown",
        "verifying_cookie",
        "saving_cookie",
        "looking_up_creator",
        "fetching_creator_avatar",
        "baselining",
        "dispatching",
        "accepted",
        "polling",
        "observed",
    }
)
ACTIONS = frozenset(
    {
        "start",
        "finish",
        "phase_change",
        "tick",
        "stop",
        "save",
        "drop",
        "prepare",
        "acquire",
        "launch",
        "navigate",
        "click",
        "wait_selector",
        "wait_load",
        "probe",
        "fetch",
        "relay_write",
        "confirm",
        "finalize",
        "cleanup",
        "execute",
        "read_image",
        "account-cookie-login",
        "creator-profile",
        "account-login",
        "asset-download",
        "scheduler-run",
        "pipeline-run",
        "emby-export",
        "media-server-probe",
        "media-server-scan",
    }
)
OUTCOMES = frozenset(
    {
        "started",
        "succeeded",
        "failed",
        "cancelled",
        "interrupted",
        "queued",
        "claimed",
        "running",
        "retry_wait",
        "failed_retryable",
        "failed_terminal",
        "waiting_auth",
        "waiting_user",
        "awaiting_auth",
        "skipped",
        "rejected",
        "completed",
        "timed_out",
        "expired",
        "fenced",
        "stopped",
        "unknown",
    }
)
ERROR_TYPES = frozenset(
    {
        "none",
        "playwright_timeout",
        "timeout",
        "os_error",
        "cancelled",
        "system_exit",
        "configuration",
        "confirmation_rejected",
        "browser_launch_failed",
        "unknown",
    }
)
PLATFORMS = frozenset({"bili", "dy", "ks", "tieba", "wb", "xhs", "zhihu"})
UUID_FIELDS = frozenset(
    {
        "operation_id",
        "correlation_id",
        "account_id",
        "login_session_id",
        "job_id",
        "run_id",
        "subscription_id",
        "author_id",
        "asset_id",
    }
)
NUMBER_FIELDS = frozenset({"duration_ms", "attempt", "count", "bytes", "http_status"})
SOURCE_FRAMES = frozenset(
    {
        "parent",
        "runner",
        "client",
        "login",
        "qr_helper",
        "qr_relay",
        "httpx_get",
        "browser_type",
        "browser_context",
        "page",
        "frame",
        "locator",
        "element_handle",
        "cleanup",
    }
)
ENUM_FIELDS = {
    "event_code": EVENT_CODES,
    "module": MODULES,
    "level": LEVELS,
    "phase": PHASES,
    "action": ACTIONS,
    "outcome": OUTCOMES,
    "error_type": ERROR_TYPES,
    "platform": PLATFORMS,
    "source_frame": SOURCE_FRAMES,
}
_REQUIRED = frozenset({"event_code", "module", "level"})
_INPUT_FIELDS = frozenset(ENUM_FIELDS) | UUID_FIELDS | NUMBER_FIELDS
_MINTED_FIELDS = frozenset({"schema_version", "timestamp", "writer_id", "sequence"})


class EventValidationError(ValueError):
    """No rejected value is retained in the error."""

    def __init__(self) -> None:
        super().__init__("log_event_invalid")


def canonical_uuid(value: object) -> str:
    if type(value) is not str or len(value) != 36:
        raise EventValidationError
    try:
        if str(UUID(value)) == value:
            return value
    except (ValueError, AttributeError):
        pass
    raise EventValidationError


def canonical_time(value: object) -> str:
    if type(value) is not str or len(value) != 27 or not value.endswith("Z"):
        raise EventValidationError
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
        if format_time(parsed) == value:
            return value
    except ValueError:
        pass
    raise EventValidationError


def format_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EventValidationError
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def validate_event(event: Mapping[str, object]) -> dict[str, object]:
    """Copy only a complete valid event; do not sanitize arbitrary strings."""

    if not isinstance(event, Mapping) or not event.keys() >= _REQUIRED or not event.keys() <= _INPUT_FIELDS:
        raise EventValidationError
    result: dict[str, object] = {}
    for key, value in event.items():
        if key in ENUM_FIELDS:
            if type(value) is not str or value not in ENUM_FIELDS[key]:
                raise EventValidationError
        elif key in UUID_FIELDS:
            canonical_uuid(value)
        elif key in NUMBER_FIELDS:
            if type(value) is not int or not 0 <= value <= MAX_NUMBER:
                raise EventValidationError
            if key == "http_status" and not 100 <= value <= 599:
                raise EventValidationError
        result[key] = value
    if (
        result["event_code"] in {"login_stage", "login_terminal"}
        and not {"phase", "action", "outcome", "error_type", "duration_ms"} <= result.keys()
    ):
        raise EventValidationError
    return result


def validate_record(record: Mapping[str, object]) -> dict[str, object]:
    """Validate the stored parent-minted frame before returning any content."""

    if not isinstance(record, Mapping) or not record.keys() >= _MINTED_FIELDS:
        raise EventValidationError
    if type(record["schema_version"]) is not int or record["schema_version"] != EVENT_SCHEMA_VERSION:
        raise EventValidationError
    canonical_time(record["timestamp"])
    canonical_uuid(record["writer_id"])
    sequence = record["sequence"]
    if type(sequence) is not int or not 1 <= sequence <= MAX_NUMBER:
        raise EventValidationError
    event = validate_event({key: value for key, value in record.items() if key not in _MINTED_FIELDS})
    return {**event, **{key: record[key] for key in _MINTED_FIELDS}}


__all__ = [
    "ACTIONS",
    "ENUM_FIELDS",
    "ERROR_TYPES",
    "EVENT_CODES",
    "EVENT_SCHEMA_VERSION",
    "LEVELS",
    "MAX_EVENT_BYTES",
    "MAX_NUMBER",
    "MODULES",
    "NUMBER_FIELDS",
    "OUTCOMES",
    "PHASES",
    "PLATFORMS",
    "SOURCE_FRAMES",
    "UUID_FIELDS",
    "EventValidationError",
    "canonical_time",
    "canonical_uuid",
    "format_time",
    "validate_event",
    "validate_record",
]
