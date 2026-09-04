"""Closed, redaction-safe payload contracts for durable API operations.

This module deliberately has no database or web-framework dependency.  It is
the single projection boundary used before operation results, lifecycle event
contexts, or request identities may reach persistence, logs, or SSE.

Only fixed fields with fixed scalar semantics are accepted.  Raw request
bodies, exception objects, URLs, paths, QR material, secret values, lease
tokens, and caller-provided worker identities have no representation here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Final, Literal, TypeAlias, cast
from uuid import UUID

OperationKind: TypeAlias = Literal[
    "account-login",
    "asset-download",
    "scheduler-run",
    "pipeline-run",
    "emby-export",
]
OperationEventCode: TypeAlias = Literal[
    "operation_requested",
    "operation_started",
    "operation_phase_changed",
    "operation_progressed",
    "operation_entity_linked",
    "operation_cancel_requested",
    "operation_cancel_observed",
    "operation_succeeded",
    "operation_failed",
    "operation_cancelled",
    "operation_interrupted",
    "operation_reconciled",
]

OPERATION_PAYLOAD_SCHEMA_VERSION: Final = 1
MAX_OPERATION_CODE_LENGTH: Final = 128
MAX_OPERATION_COUNT: Final = 9_223_372_036_854_775_807
MAX_OPERATION_ARRAY_ITEMS: Final = 1_000
MAX_OPERATION_MAPPING_ITEMS: Final = 32
MAX_OPERATION_PAYLOAD_DEPTH: Final = 4
MAX_OPERATION_RESULT_BYTES: Final = 4_096
MAX_OPERATION_EVENT_CONTEXT_BYTES: Final = 2_048
MAX_OPERATION_REQUEST_IDENTITY_BYTES: Final = 4_096
MIN_IDEMPOTENCY_KEY_LENGTH: Final = 16
MAX_IDEMPOTENCY_KEY_LENGTH: Final = 128

OPERATION_KINDS: Final = frozenset(
    {
        "account-login",
        "asset-download",
        "scheduler-run",
        "pipeline-run",
        "emby-export",
    }
)
OPERATION_EVENT_CODES: Final = frozenset(
    {
        "operation_requested",
        "operation_started",
        "operation_phase_changed",
        "operation_progressed",
        "operation_entity_linked",
        "operation_cancel_requested",
        "operation_cancel_observed",
        "operation_succeeded",
        "operation_failed",
        "operation_cancelled",
        "operation_interrupted",
        "operation_reconciled",
    }
)

_KIND_TARGET_TYPES: Final = MappingProxyType(
    {
        "account-login": "account",
        "asset-download": "asset",
        "scheduler-run": None,
        "pipeline-run": None,
        "emby-export": "author",
    }
)
_KIND_ROUTES: Final = MappingProxyType(
    {
        "account-login": "/api/v1/accounts/{account_id}/login",
        "asset-download": "/api/v1/assets/{asset_id}/download",
        "scheduler-run": "/api/v1/scheduler/run",
        "pipeline-run": "/api/v1/pipeline/run",
        "emby-export": "/api/v1/emby/export",
    }
)
_LOGIN_RUNNER_STATUSES: Final = frozenset(
    {
        "authenticated",
        "expired",
        "failed",
        "timed_out",
        "cancelled",
        "account_busy",
        "configuration_invalid",
        "start_failed",
        "result_invalid",
    }
)
_LOGIN_SESSION_STATUSES: Final = frozenset({"pending", "waiting_user", "succeeded", "expired", "failed", "cancelled"})
_AUTH_STATUSES: Final = frozenset({"unknown", "required", "authenticating", "authenticated", "expired", "failed"})
_ASSET_SUMMARY_STATUSES: Final = frozenset(
    {
        "blocked",
        "failed",
        "discovered",
        "queued",
        "downloading",
        "downloaded",
        "verified",
        "exported",
        "failed_retryable",
        "failed_terminal",
    }
)
_ASSET_DISPOSITIONS: Final = frozenset({"not_started", "downloaded", "already_verified"})
_BATCH_RESULT_STATUSES: Final = frozenset(
    {
        "idle",
        "fenced",
        "queued",
        "claimed",
        "running",
        "retry_wait",
        "waiting_auth",
        "waiting_user",
        "succeeded",
        "failed_retryable",
        "failed_terminal",
        "cancelled",
    }
)
_SUBJECT_TYPES: Final = frozenset(
    {
        "account",
        "asset",
        "author",
        "content",
        "export_record",
        "job",
        "login_session",
        "subscription",
        "sync_run",
    }
)
_SUBJECT_ROLES: Final = frozenset({"target", "execution", "result", "related"})
_PROGRESS_UNITS: Final = frozenset({"steps", "items", "jobs", "bytes"})
_RECONCILIATION_STATES: Final = (
    _BATCH_RESULT_STATUSES | _LOGIN_SESSION_STATUSES | frozenset({"missing", "incomplete", "lease_expired"})
)

_REQUEST_PARAMETER_FIELDS: Final = MappingProxyType(
    {
        "account-login": frozenset({"timeout_microseconds", "enable_mediacrawler", "accept_mediacrawler_license"}),
        "asset-download": frozenset(
            {
                "lease_seconds",
                "max_attempts",
                "enable_mediacrawler",
                "accept_mediacrawler_license",
                "xhs_detail_reference_digest",
            }
        ),
        "scheduler-run": frozenset(
            {
                "max_jobs",
                "global_capacity",
                "lease_seconds",
                "scan_limit",
                "enable_mediacrawler",
                "accept_mediacrawler_license",
            }
        ),
        "pipeline-run": frozenset(
            {
                "max_jobs",
                "lease_seconds",
                "scan_limit",
                "retry_delay_seconds",
                "enable_mediacrawler",
                "accept_mediacrawler_license",
                "xhs_detail_reference_digest",
            }
        ),
        "emby-export": frozenset({"lease_seconds", "max_attempts"}),
    }
)

_ERROR_MESSAGES: Final = {
    "operation_kind_invalid": "operation kind is outside the closed vocabulary",
    "operation_result_invalid": "operation result is outside the closed safe contract",
    "operation_event_code_invalid": "operation event code is outside the closed vocabulary",
    "operation_event_context_invalid": "operation event context is outside the closed safe contract",
    "operation_request_identity_invalid": "operation request identity is outside the closed safe contract",
    "operation_idempotency_key_invalid": "operation idempotency key is invalid",
}

_STABLE_CODE = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SENSITIVE_CODE_ATOMS: Final = frozenset(
    {"authorization", "cookie", "credential", "password", "secret", "token", "workerid"}
)
_SAFE_SENSITIVE_ERROR_CODES: Final = frozenset({"locator_secret_forbidden"})


class OperationPayloadError(ValueError):
    """A fixed-code validation error that never reflects the rejected value."""

    def __init__(self, code: str) -> None:
        try:
            message = _ERROR_MESSAGES[code]
        except KeyError as exc:  # pragma: no cover - programmer error
            raise ValueError("unknown operation payload error code") from exc
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _fail(code: str) -> OperationPayloadError:
    return OperationPayloadError(code)


def _kind(value: object) -> OperationKind:
    if not isinstance(value, str) or value not in OPERATION_KINDS:
        raise _fail("operation_kind_invalid")
    return cast(OperationKind, value)


def _event_code(value: object) -> OperationEventCode:
    if not isinstance(value, str) or value not in OPERATION_EVENT_CODES:
        raise _fail("operation_event_code_invalid")
    return cast(OperationEventCode, value)


def _mapping(value: object, *, error_code: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or len(value) > MAX_OPERATION_MAPPING_ITEMS:
        raise _fail(error_code)
    if any(not isinstance(key, str) for key in value):
        raise _fail(error_code)
    return value


def _exact_fields(
    value: Mapping[str, object],
    expected: set[str] | frozenset[str],
    *,
    error_code: str,
) -> None:
    if set(value) != set(expected):
        raise _fail(error_code)


def _uuid(value: object, *, error_code: str) -> str:
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str) or len(value) != 36:
        raise _fail(error_code)
    try:
        parsed = UUID(value)
    except ValueError:
        raise _fail(error_code) from None
    if str(parsed) != value:
        raise _fail(error_code)
    return value


def _optional_uuid(value: object, *, error_code: str) -> str | None:
    return None if value is None else _uuid(value, error_code=error_code)


def _bool(value: object, *, error_code: str) -> bool:
    if type(value) is not bool:
        raise _fail(error_code)
    return value


def _count(
    value: object,
    *,
    error_code: str,
    minimum: int = 0,
    maximum: int = MAX_OPERATION_COUNT,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _fail(error_code)
    return value


def _optional_count(value: object, *, error_code: str) -> int | None:
    return None if value is None else _count(value, error_code=error_code)


def _stable_code(
    value: object,
    *,
    error_code: str,
    allowed: frozenset[str] | None = None,
    maximum: int = MAX_OPERATION_CODE_LENGTH,
) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or _STABLE_CODE.fullmatch(value) is None
        or (allowed is not None and value not in allowed)
    ):
        raise _fail(error_code)
    return value


def _optional_stable_code(
    value: object,
    *,
    error_code: str,
    allowed: frozenset[str] | None = None,
    maximum: int = MAX_OPERATION_CODE_LENGTH,
) -> str | None:
    if value is None:
        return None
    return _stable_code(value, error_code=error_code, allowed=allowed, maximum=maximum)


def _safe_error_code(value: object, *, error_code: str) -> str:
    normalized = _stable_code(value, error_code=error_code)
    atoms = frozenset(re.split(r"[._-]+", normalized.replace("worker_id", "workerid")))
    if atoms & _SENSITIVE_CODE_ATOMS and normalized not in _SAFE_SENSITIVE_ERROR_CODES:
        raise _fail(error_code)
    return normalized


def _time(value: object, *, error_code: str) -> str:
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and 1 <= len(value) <= 40 and value == value.strip():
        candidate = f"{value[:-1]}+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            raise _fail(error_code) from None
    else:
        raise _fail(error_code)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _fail(error_code)
    return parsed.astimezone(UTC).isoformat()


def _optional_time(value: object, *, error_code: str) -> str | None:
    return None if value is None else _time(value, error_code=error_code)


def _sha256(value: object, *, error_code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise _fail(error_code)
    return value


def _optional_sha256(value: object, *, error_code: str) -> str | None:
    return None if value is None else _sha256(value, error_code=error_code)


def _assert_bounded_shape(value: object, *, maximum_bytes: int, error_code: str) -> None:
    def visit(item: object, depth: int) -> None:
        if depth > MAX_OPERATION_PAYLOAD_DEPTH:
            raise _fail(error_code)
        if item is None or type(item) in {bool, int}:
            return
        if isinstance(item, str):
            if len(item.encode("utf-8")) > 512:
                raise _fail(error_code)
            return
        if isinstance(item, Mapping):
            if len(item) > MAX_OPERATION_MAPPING_ITEMS:
                raise _fail(error_code)
            for key, child in item.items():
                if not isinstance(key, str) or len(key.encode("utf-8")) > 128:
                    raise _fail(error_code)
                visit(child, depth + 1)
            return
        if isinstance(item, Sequence) and not isinstance(item, bytes | bytearray | str):
            if len(item) > MAX_OPERATION_ARRAY_ITEMS:
                raise _fail(error_code)
            for child in item:
                visit(child, depth + 1)
            return
        raise _fail(error_code)

    visit(value, 0)
    try:
        encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        raise _fail(error_code) from None
    if len(encoded) > maximum_bytes:
        raise _fail(error_code)


def _account_login_summary(payload: Mapping[str, object]) -> dict[str, object]:
    error_code = "operation_result_invalid"
    _exact_fields(
        payload,
        {
            "account_id",
            "login_session_id",
            "runner_status",
            "login_session_status",
            "auth_status",
            "expires_at",
            "completed_at",
        },
        error_code=error_code,
    )
    return {
        "account_id": _uuid(payload["account_id"], error_code=error_code),
        "login_session_id": _uuid(payload["login_session_id"], error_code=error_code),
        "runner_status": _stable_code(payload["runner_status"], error_code=error_code, allowed=_LOGIN_RUNNER_STATUSES),
        "login_session_status": _stable_code(
            payload["login_session_status"], error_code=error_code, allowed=_LOGIN_SESSION_STATUSES
        ),
        "auth_status": _stable_code(payload["auth_status"], error_code=error_code, allowed=_AUTH_STATUSES),
        "expires_at": _optional_time(payload["expires_at"], error_code=error_code),
        "completed_at": _optional_time(payload["completed_at"], error_code=error_code),
    }


def _asset_download_summary(payload: Mapping[str, object]) -> dict[str, object]:
    error_code = "operation_result_invalid"
    _exact_fields(
        payload,
        {"asset_id", "job_id", "ok", "status", "disposition", "generation", "size_bytes"},
        error_code=error_code,
    )
    return {
        "asset_id": _uuid(payload["asset_id"], error_code=error_code),
        "job_id": _optional_uuid(payload["job_id"], error_code=error_code),
        "ok": _bool(payload["ok"], error_code=error_code),
        "status": _stable_code(payload["status"], error_code=error_code, allowed=_ASSET_SUMMARY_STATUSES),
        "disposition": _optional_stable_code(
            payload["disposition"], error_code=error_code, allowed=_ASSET_DISPOSITIONS
        ),
        "generation": _optional_count(payload["generation"], error_code=error_code),
        "size_bytes": _optional_count(payload["size_bytes"], error_code=error_code),
    }


def _batch_summary(payload: Mapping[str, object]) -> dict[str, object]:
    error_code = "operation_result_invalid"
    _exact_fields(payload, {"statuses"}, error_code=error_code)
    raw_statuses = payload["statuses"]
    if (
        not isinstance(raw_statuses, Sequence)
        or isinstance(raw_statuses, bytes | bytearray | str)
        or len(raw_statuses) > MAX_OPERATION_ARRAY_ITEMS
    ):
        raise _fail(error_code)
    counts: dict[str, int] = {}
    for value in raw_statuses:
        status = _stable_code(value, error_code=error_code, allowed=_BATCH_RESULT_STATUSES)
        counts[status] = counts.get(status, 0) + 1
    return {
        "processed_count": len(raw_statuses),
        "status_counts": {status: counts[status] for status in sorted(counts)},
    }


def _emby_export_summary(payload: Mapping[str, object]) -> dict[str, object]:
    error_code = "operation_result_invalid"
    _exact_fields(
        payload,
        {"author_id", "job_id", "already_exported", "managed_file_count"},
        error_code=error_code,
    )
    return {
        "author_id": _uuid(payload["author_id"], error_code=error_code),
        "job_id": _uuid(payload["job_id"], error_code=error_code),
        "already_exported": _bool(payload["already_exported"], error_code=error_code),
        "managed_file_count": _count(payload["managed_file_count"], error_code=error_code),
    }


def operation_result_summary(kind: object, payload: object) -> dict[str, object]:
    """Return the sole durable result shape for one of the five operation kinds."""

    normalized_kind = _kind(kind)
    normalized_payload = _mapping(payload, error_code="operation_result_invalid")
    if normalized_kind == "account-login":
        result = _account_login_summary(normalized_payload)
    elif normalized_kind == "asset-download":
        result = _asset_download_summary(normalized_payload)
    elif normalized_kind in {"scheduler-run", "pipeline-run"}:
        result = _batch_summary(normalized_payload)
    else:
        result = _emby_export_summary(normalized_payload)
    _assert_bounded_shape(
        result,
        maximum_bytes=MAX_OPERATION_RESULT_BYTES,
        error_code="operation_result_invalid",
    )
    return result


def _phase(value: object, *, error_code: str) -> str | None:
    return _optional_stable_code(value, error_code=error_code, maximum=64)


def operation_event_context(event_code: object, context: object) -> dict[str, object]:
    """Validate and copy the exact allowlisted context for a lifecycle event."""

    normalized_event = _event_code(event_code)
    payload = _mapping(context, error_code="operation_event_context_invalid")
    error_code = "operation_event_context_invalid"

    if normalized_event == "operation_requested":
        _exact_fields(payload, {"kind", "target_id"}, error_code=error_code)
        kind = _kind(payload["kind"])
        expected_target = _KIND_TARGET_TYPES[kind]
        raw_target = payload["target_id"]
        if expected_target is None:
            if raw_target is not None:
                raise _fail(error_code)
            result: dict[str, object] = {"kind": kind, "target_type": None, "target_id": None}
        else:
            result = {
                "kind": kind,
                "target_type": expected_target,
                "target_id": _uuid(raw_target, error_code=error_code),
            }
    elif normalized_event in {"operation_started", "operation_cancel_requested", "operation_succeeded"}:
        _exact_fields(payload, set(), error_code=error_code)
        result = {}
    elif normalized_event in {
        "operation_phase_changed",
        "operation_cancel_observed",
        "operation_cancelled",
    }:
        _exact_fields(payload, {"phase"}, error_code=error_code)
        result = {"phase": _phase(payload["phase"], error_code=error_code)}
    elif normalized_event == "operation_progressed":
        _exact_fields(
            payload,
            {"phase", "progress_current", "progress_total", "progress_unit"},
            error_code=error_code,
        )
        current = _count(payload["progress_current"], error_code=error_code)
        total = _optional_count(payload["progress_total"], error_code=error_code)
        if total is not None and current > total:
            raise _fail(error_code)
        result = {
            "phase": _phase(payload["phase"], error_code=error_code),
            "progress_current": current,
            "progress_total": total,
            "progress_unit": _stable_code(payload["progress_unit"], error_code=error_code, allowed=_PROGRESS_UNITS),
        }
    elif normalized_event == "operation_entity_linked":
        _exact_fields(payload, {"subject_type", "subject_id", "role"}, error_code=error_code)
        result = {
            "subject_type": _stable_code(payload["subject_type"], error_code=error_code, allowed=_SUBJECT_TYPES),
            "subject_id": _uuid(payload["subject_id"], error_code=error_code),
            "role": _stable_code(payload["role"], error_code=error_code, allowed=_SUBJECT_ROLES),
        }
    elif normalized_event in {"operation_failed", "operation_interrupted"}:
        _exact_fields(payload, {"error_code", "retryable"}, error_code=error_code)
        result = {
            "error_code": _safe_error_code(payload["error_code"], error_code=error_code),
            "retryable": _bool(payload["retryable"], error_code=error_code),
        }
    else:
        _exact_fields(payload, {"subject_type", "subject_state"}, error_code=error_code)
        result = {
            "subject_type": _stable_code(payload["subject_type"], error_code=error_code, allowed=_SUBJECT_TYPES),
            "subject_state": _stable_code(
                payload["subject_state"], error_code=error_code, allowed=_RECONCILIATION_STATES
            ),
        }

    _assert_bounded_shape(
        result,
        maximum_bytes=MAX_OPERATION_EVENT_CONTEXT_BYTES,
        error_code=error_code,
    )
    return result


def _request_parameters(kind: OperationKind, parameters: object) -> dict[str, object]:
    payload = _mapping(parameters, error_code="operation_request_identity_invalid")
    expected = _REQUEST_PARAMETER_FIELDS[kind]
    _exact_fields(payload, expected, error_code="operation_request_identity_invalid")
    error_code = "operation_request_identity_invalid"

    if kind == "account-login":
        return {
            "accept_mediacrawler_license": _bool(payload["accept_mediacrawler_license"], error_code=error_code),
            "enable_mediacrawler": _bool(payload["enable_mediacrawler"], error_code=error_code),
            "timeout_microseconds": _count(
                payload["timeout_microseconds"], error_code=error_code, minimum=1, maximum=3_600_000_000
            ),
        }
    if kind == "asset-download":
        return {
            "accept_mediacrawler_license": _bool(payload["accept_mediacrawler_license"], error_code=error_code),
            "enable_mediacrawler": _bool(payload["enable_mediacrawler"], error_code=error_code),
            "lease_seconds": _count(payload["lease_seconds"], error_code=error_code, minimum=1, maximum=86_400),
            "max_attempts": _count(payload["max_attempts"], error_code=error_code, minimum=1, maximum=100),
            "xhs_detail_reference_digest": _optional_sha256(
                payload["xhs_detail_reference_digest"], error_code=error_code
            ),
        }
    if kind == "scheduler-run":
        return {
            "accept_mediacrawler_license": _bool(payload["accept_mediacrawler_license"], error_code=error_code),
            "enable_mediacrawler": _bool(payload["enable_mediacrawler"], error_code=error_code),
            "global_capacity": _count(payload["global_capacity"], error_code=error_code, minimum=1, maximum=1_000),
            "lease_seconds": _count(payload["lease_seconds"], error_code=error_code, minimum=1, maximum=86_400),
            "max_jobs": _count(payload["max_jobs"], error_code=error_code, minimum=1, maximum=1_000),
            "scan_limit": _count(payload["scan_limit"], error_code=error_code, minimum=1, maximum=1_000),
        }
    if kind == "pipeline-run":
        return {
            "accept_mediacrawler_license": _bool(payload["accept_mediacrawler_license"], error_code=error_code),
            "enable_mediacrawler": _bool(payload["enable_mediacrawler"], error_code=error_code),
            "lease_seconds": _count(payload["lease_seconds"], error_code=error_code, minimum=1, maximum=86_400),
            "max_jobs": _count(payload["max_jobs"], error_code=error_code, minimum=1, maximum=1_000),
            "retry_delay_seconds": _count(
                payload["retry_delay_seconds"], error_code=error_code, minimum=1, maximum=86_400
            ),
            "scan_limit": _count(payload["scan_limit"], error_code=error_code, minimum=1, maximum=1_000),
            "xhs_detail_reference_digest": _optional_sha256(
                payload["xhs_detail_reference_digest"], error_code=error_code
            ),
        }
    return {
        "lease_seconds": _count(payload["lease_seconds"], error_code=error_code, minimum=1, maximum=86_400),
        "max_attempts": _count(payload["max_attempts"], error_code=error_code, minimum=1, maximum=100),
    }


def operation_request_fingerprint(
    kind: object,
    *,
    target_id: object,
    parameters: object,
) -> str:
    """Hash one normalized, safe request identity without accepting a raw body.

    Private references must be reduced by the caller to the explicitly named
    SHA-256 digest field.  ``worker_id`` is intentionally absent: API workers
    receive a server-owned identity derived from the durable Operation.
    """

    normalized_kind = _kind(kind)
    target_type = _KIND_TARGET_TYPES[normalized_kind]
    if target_type is None:
        if target_id is not None:
            raise _fail("operation_request_identity_invalid")
        normalized_target: str | None = None
    else:
        normalized_target = _uuid(target_id, error_code="operation_request_identity_invalid")
    normalized = {
        "schema_version": OPERATION_PAYLOAD_SCHEMA_VERSION,
        "method": "POST",
        "route": _KIND_ROUTES[normalized_kind],
        "kind": normalized_kind,
        "target_type": target_type,
        "target_id": normalized_target,
        "parameters": _request_parameters(normalized_kind, parameters),
    }
    _assert_bounded_shape(
        normalized,
        maximum_bytes=MAX_OPERATION_REQUEST_IDENTITY_BYTES,
        error_code="operation_request_identity_invalid",
    )
    encoded = json.dumps(normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b"media-sync:operation-request:v1\0" + encoded).hexdigest()


def operation_idempotency_key_digest(value: object) -> str:
    """Return a domain-separated digest without retaining or reflecting the key."""

    if (
        not isinstance(value, str)
        or not MIN_IDEMPOTENCY_KEY_LENGTH <= len(value) <= MAX_IDEMPOTENCY_KEY_LENGTH
        or _IDEMPOTENCY_KEY.fullmatch(value) is None
    ):
        raise _fail("operation_idempotency_key_invalid")
    return hashlib.sha256(b"media-sync:operation-idempotency:v1\0" + value.encode("ascii")).hexdigest()


__all__ = [
    "MAX_IDEMPOTENCY_KEY_LENGTH",
    "MAX_OPERATION_ARRAY_ITEMS",
    "MAX_OPERATION_CODE_LENGTH",
    "MAX_OPERATION_COUNT",
    "MAX_OPERATION_EVENT_CONTEXT_BYTES",
    "MAX_OPERATION_MAPPING_ITEMS",
    "MAX_OPERATION_PAYLOAD_DEPTH",
    "MAX_OPERATION_REQUEST_IDENTITY_BYTES",
    "MAX_OPERATION_RESULT_BYTES",
    "MIN_IDEMPOTENCY_KEY_LENGTH",
    "OPERATION_EVENT_CODES",
    "OPERATION_KINDS",
    "OPERATION_PAYLOAD_SCHEMA_VERSION",
    "OperationEventCode",
    "OperationKind",
    "OperationPayloadError",
    "operation_event_context",
    "operation_idempotency_key_digest",
    "operation_request_fingerprint",
    "operation_result_summary",
]
