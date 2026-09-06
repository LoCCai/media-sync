"""Closed event vocabulary with bounded, policy-checked process diagnostics."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from media_sync.security.redaction import redact_text

EVENT_SCHEMA_VERSION = 1
MAX_EVENT_BYTES = 4096
MAX_NUMBER = 9_007_199_254_740_991
EVENT_CODES = frozenset(
    {
        "application_log_redacted",
        "process_output",
        "process_output_summary",
        "process_output_dropped",
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
        "subscription_delivery",
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
        "subscription-delivery",
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
        "invalid_encoding",
        "line_too_large",
        "capture_budget_exhausted",
        "log_sink_rejected",
        "policy_filtered",
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
STREAMS = frozenset({"stdout_protocol", "upstream"})
TEXT_FIELDS = frozenset({"message"})
MAX_MESSAGE_BYTES = 2048
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
    "stream": STREAMS,
}
_REQUIRED = frozenset({"event_code", "module", "level"})
_INPUT_FIELDS = frozenset(ENUM_FIELDS) | UUID_FIELDS | NUMBER_FIELDS | TEXT_FIELDS
_MINTED_FIELDS = frozenset({"schema_version", "timestamp", "writer_id", "sequence"})
_SENSITIVE_MESSAGE = re.compile(
    r"(?ix)(?:data:image/(?:png|jpeg|webp);base64,|"
    r"\b(?:qr|qr[_-]?code|qrcode)\b\s*[:=]\s*(?!\[REDACTED\])\S+|"
    r"\bset-cookie\s*:|"
    r"\bauthorization\s*(?:(?::|=)\s*|\s+bearer\s+)(?!\[REDACTED\])|"
    r"\bstorage[_-]?state\b|"
    r"\bcookies?\s*[:=]\s*(?!\[REDACTED\])(?:\[|\{|\()|"
    r"['\"]name['\"]\s*:\s*['\"](?:sessdata|bili_jct|sid|session|token)|"
    r"\b(?:ac_time_value|a1|bili_jct|csrf|ms_?token|sessdata|sid|webid|xsec_?token)\b"
    r"\s*[:=]\s*(?!\[REDACTED\])|"
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b|"
    r"https?://[^\s<>\"']*[?#][^\s<>\"']*|"
    r"(?:^|[\s\"'=])(?:[a-z]:[\\/]|\\\\[^\\/\s]+[\\/]|/(?!/)(?:[^/\s]+/)+)[^\s\"']*"
    r")"
)
_MEDIACRAWLER_LOG_PREFIX = re.compile(
    r"^(?P<timestamp>[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) "
    r"MediaCrawler (?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL) "
    r"\((?P<filename>[A-Za-z0-9_.-]{1,251}\.py):(?P<lineno>[1-9][0-9]{0,6})\) - "
)
_PROCESS_OUTPUT_SHAPE = re.compile(
    r"(?ix)^\s*(?:"
    r"\[(?:trace|debug|info|notice|warn(?:ing)?|error|critical|fatal)\]\s*|"
    r"(?:\d{4}[-/]\d{2}[-/]\d{2}[T\s][0-9:.+Z-]+\s+)?"
    r"(?:\[[^\]\r\n]{1,80}\]\s*){0,2}"
    r"(?:trace|debug|info|notice|warn(?:ing)?|error|critical|fatal)\b(?:\s*[:|>-]\s*|\s+)|"
    r"traceback\b|caused\s+by\s*:|unhandled\s+(?:error|exception|rejection)\b|"
    r"playwright(?:\s+[a-z_][\w.-]*){0,4}\s+(?:error|exception)\b|"
    r"(?:[a-z_][\w.]*\.)*[a-z_][\w]*(?:error|exception|failure)\s*:|"
    r"(?:timeout|cancelled|canceled)\s*:|at\s+\S+|file\s+['\"]"
    r")"
)
_FORBIDDEN_PROCESS_CONTENT = re.compile(
    r"(?is)(?:"
    r"<!doctype\s+html|<html\b|<(?:body|button|div|form|iframe|img|input|script|span|svg)\b[^>]*>|"
    r"[{[]\s*['\"]?[A-Za-z0-9_-]+['\"]?\s*:|"
    r"(?:^|\W)(?:aweme|body|caption|content|creator[_-]?content|desc(?:ription)?|note|post|title)\s*[:=]"
    r")"
)


def normalize_process_output_message(value: str) -> str:
    """Remove only the exact pinned MediaCrawler formatter prefix."""

    matched = _MEDIACRAWLER_LOG_PREFIX.match(value)
    if matched is None:
        return value
    payload = value[matched.end() :].lstrip()
    return f"{matched.group('level')} {payload}".rstrip()


def process_output_message_has_explicit_shape(value: str) -> bool:
    return _PROCESS_OUTPUT_SHAPE.search(normalize_process_output_message(value)) is not None


def process_output_message_has_forbidden_content(value: str) -> bool:
    normalized = normalize_process_output_message(value)
    payload = _PROCESS_OUTPUT_SHAPE.sub("", normalized, count=1).lstrip()
    return _FORBIDDEN_PROCESS_CONTENT.search(payload) is not None or (
        payload[:1] in {"{", "["} and payload[-1:] in {"}", "]"}
    )


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
        elif key in TEXT_FIELDS and (
            type(value) is not str
            or not value
            or "\x00" in value
            or any(character in value for character in ("\r", "\n"))
            or len(json.dumps(value, ensure_ascii=True).encode("ascii")) > MAX_MESSAGE_BYTES
            or redact_text(value, max_length=MAX_MESSAGE_BYTES) != value
            or _SENSITIVE_MESSAGE.search(value) is not None
        ):
            raise EventValidationError
        result[key] = value
    if (
        result["event_code"] in {"login_stage", "login_terminal"}
        and not {"phase", "action", "outcome", "error_type", "duration_ms"} <= result.keys()
    ):
        raise EventValidationError
    if result["event_code"] == "process_output" and not {"stream", "message"} <= result.keys():
        raise EventValidationError
    if result["event_code"] == "process_output":
        message = result["message"]
        if not isinstance(message, str) or (
            message != "[REDACTED]"
            and (
                normalize_process_output_message(message) != message
                or not process_output_message_has_explicit_shape(message)
                or process_output_message_has_forbidden_content(message)
            )
        ):
            raise EventValidationError
    if "message" in result and result["event_code"] != "process_output":
        raise EventValidationError
    if "stream" in result and result["event_code"] not in {
        "process_output",
        "process_output_summary",
        "process_output_dropped",
    }:
        raise EventValidationError
    if (
        result["event_code"] == "process_output_summary"
        and not {
            "stream",
            "action",
            "outcome",
            "count",
            "bytes",
        }
        <= result.keys()
    ):
        raise EventValidationError
    if (
        result["event_code"] == "process_output_dropped"
        and not {
            "stream",
            "action",
            "outcome",
            "error_type",
            "count",
        }
        <= result.keys()
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
    "MAX_MESSAGE_BYTES",
    "MAX_NUMBER",
    "MODULES",
    "NUMBER_FIELDS",
    "OUTCOMES",
    "PHASES",
    "PLATFORMS",
    "SOURCE_FRAMES",
    "STREAMS",
    "TEXT_FIELDS",
    "UUID_FIELDS",
    "EventValidationError",
    "canonical_time",
    "canonical_uuid",
    "format_time",
    "normalize_process_output_message",
    "process_output_message_has_explicit_shape",
    "process_output_message_has_forbidden_content",
    "validate_event",
    "validate_record",
]
