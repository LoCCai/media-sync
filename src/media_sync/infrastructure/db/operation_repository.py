"""Durable, fenced operations and their globally replayable event stream."""

from __future__ import annotations

import builtins
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from media_sync.security import redact_text

from .base import new_uuid, utc_now
from .models import (
    ACTIVE_OPERATION_STATES,
    OPERATION_EVENT_CODES,
    OPERATION_EVENT_LEVELS,
    OPERATION_FAILURE_STATES,
    OPERATION_KINDS,
    OPERATION_STATES,
    OPERATION_SUBJECT_ROLES,
    OPERATION_SUBJECT_TYPES,
    TERMINAL_OPERATION_STATES,
    Operation,
    OperationEvent,
    OperationEventStreamState,
    OperationSubject,
)
from .repositories import NotFoundError, RepositoryError

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_CODE = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_JSON_KEY = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_WINDOWS_DRIVE = re.compile(r"[A-Za-z]:[\\/]")
_SECRET_KEY_PARTS = frozenset(
    {
        "authorization",
        "cookie",
        "credential",
        "exception",
        "password",
        "path",
        "payload",
        "qr",
        "secret",
        "session",
        "token",
        "traceback",
        "url",
    }
)
_SAFE_SENSITIVE_KEYS = frozenset(
    {
        "account_id",
        "asset_id",
        "author_id",
        "content_id",
        "export_record_id",
        "job_id",
        "login_session_id",
        "login_session_status",
        "operation_id",
        "subject_id",
        "subscription_id",
        "sync_run_id",
        "target_id",
    }
)
_MAX_SUBJECTS = 1_024
_MAX_CONTEXT_BYTES = 4 * 1024
_MAX_RESULT_BYTES = 16 * 1024
_MAX_JSON_DEPTH = 4
_MAX_JSON_ITEMS = 256
_MAX_JSON_SEQUENCE = 128
_MAX_JSON_STRING = 512
_MAX_EVENT_SEQUENCE = 9_223_372_036_854_775_807
_OWNED_PROGRESS_EVENT_CODES = frozenset(
    {
        "operation_cancel_observed",
        "operation_phase_changed",
        "operation_progressed",
    }
)
_RECONCILIATION_SUBJECT_STATES = frozenset(
    {
        "cancelled",
        "claimed",
        "expired",
        "failed",
        "failed_retryable",
        "failed_terminal",
        "fenced",
        "idle",
        "incomplete",
        "lease_expired",
        "missing",
        "pending",
        "queued",
        "retry_wait",
        "running",
        "succeeded",
        "waiting_auth",
        "waiting_user",
    }
)


class OperationError(RepositoryError):
    """Base class carrying a stable operation error code."""

    def __init__(self, code: str, operation_id: str | None = None) -> None:
        self.code = code
        self.operation_id = operation_id
        super().__init__(code)


class OperationConflictError(OperationError):
    """Idempotency or active-exclusion rejected a new request."""


class OperationStateConflictError(OperationError):
    """The operation no longer has the exact lifecycle generation observed."""


class OperationLeaseLostError(OperationError):
    """A stale owner attempted to mutate an active Operation."""


class OperationPayloadError(OperationError, ValueError):
    """An operation summary or event context crossed the safe JSON boundary."""


class OperationEventCursorError(OperationError, ValueError):
    """A resumable event cursor is invalid or no longer retained."""


@dataclass(frozen=True, slots=True)
class OperationSubjectInput:
    subject_type: str
    subject_id: str
    role: str = "related"

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_type", _choice(self.subject_type, OPERATION_SUBJECT_TYPES, "subject_type"))
        object.__setattr__(self, "subject_id", _canonical_uuid(self.subject_id, "subject_id"))
        object.__setattr__(self, "role", _choice(self.role, OPERATION_SUBJECT_ROLES, "subject_role"))


@dataclass(frozen=True, slots=True)
class OperationStartResult:
    operation_id: str
    state: str
    revision: int
    correlation_id: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class OperationLease:
    operation_id: str
    lease_owner: str
    lease_token: str = field(repr=False)
    lease_expires_at: datetime
    revision: int
    cancel_requested_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OperationSnapshot:
    id: str
    kind: str
    state: str
    phase: str | None
    progress_current: int | None
    progress_total: int | None
    progress_unit: str | None
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    requested_by: str
    target_type: str | None
    target_id: str | None
    correlation_id: str
    cancel_requested_at: datetime | None
    error_code: str | None
    result_summary: Mapping[str, Any] = field(repr=False)
    event_sequence: int = 0
    revision: int = 0

    @property
    def retryable(self) -> bool:
        return self.state in {"failed_retryable", "interrupted"}

    @property
    def allowed_actions(self) -> tuple[str, ...]:
        if self.state in ACTIVE_OPERATION_STATES and self.cancel_requested_at is None:
            return ("cancel",)
        return ()


@dataclass(frozen=True, slots=True)
class OperationEventSnapshot:
    stream_sequence: int
    operation_id: str
    operation_sequence: int
    at: datetime
    level: str
    event_code: str
    from_state: str | None
    to_state: str | None
    phase: str | None
    message_key: str | None
    subject_type: str | None
    subject_id: str | None
    safe_context: Mapping[str, Any] = field(repr=False)


@dataclass(frozen=True, slots=True)
class OperationSubjectSnapshot:
    operation_id: str
    subject_type: str
    subject_id: str
    role: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OperationRecoveryCandidate:
    operation_id: str
    kind: str
    state: str
    revision: int
    lease_owner: str
    lease_token: str = field(repr=False)
    lease_expires_at: datetime
    cancel_requested_at: datetime | None
    target_type: str | None
    target_id: str | None


def _aware_utc(value: datetime | None = None) -> datetime:
    result = value or utc_now()
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return result.astimezone(UTC)


def _canonical_uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a canonical UUID")
    try:
        parsed = str(UUID(value))
    except ValueError as error:
        raise ValueError(f"{name} must be a canonical UUID") from error
    if parsed != value:
        raise ValueError(f"{name} must be a canonical UUID")
    return value


def _digest_value(value: object, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _choice(value: object, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"unsupported {name}")
    return value


def _code(value: object, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or _CODE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a stable code")
    return value


def _label(value: object, name: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(not character.isprintable() for character in value)
    ):
        raise ValueError(f"{name} is invalid")
    if _unsafe_string(value):
        raise ValueError(f"{name} is unsafe")
    return value


def _phase(value: object | None) -> str | None:
    if value is None:
        return None
    parsed = _code(value, "phase")
    assert parsed is not None
    if len(parsed) > 64:
        raise ValueError("phase is too long")
    return parsed


def _positive_limit(value: object, *, maximum: int = 1_000) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"limit must be between 1 and {maximum}")
    return value


def _revision(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("expected_revision must be a nonnegative integer")
    return value


def _lease_seconds(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 86_400:
        raise ValueError("lease_seconds must be between 1 and 86400")
    return value


def _unsafe_key(value: str) -> bool:
    lowered = value.lower()
    if lowered in _SAFE_SENSITIVE_KEYS:
        return False
    parts = frozenset(re.split(r"[_-]+", lowered))
    return bool(parts & _SECRET_KEY_PARTS) or "lease" in parts or lowered == "idempotency_key"


def _unsafe_string(value: str) -> bool:
    stripped = value.strip()
    try:
        parsed = urlsplit(stripped)
    except ValueError:
        return True
    if parsed.scheme.lower() in {"data", "file", "ftp", "http", "https", "s3", "ws", "wss"} or "://" in stripped:
        return True
    if (
        PurePosixPath(stripped).is_absolute()
        or PureWindowsPath(stripped).is_absolute()
        or stripped.startswith(("\\\\", "//"))
        or _WINDOWS_DRIVE.match(stripped) is not None
        or "/" in stripped
        or "\\" in stripped
        or "?" in stripped
    ):
        return True
    return redact_text(stripped, max_length=_MAX_JSON_STRING) != stripped


def _safe_json_object(value: Mapping[str, Any] | None, *, maximum_bytes: int) -> dict[str, Any]:
    seen = 0

    def normalize(item: object, *, depth: int) -> Any:
        nonlocal seen
        seen += 1
        if seen > _MAX_JSON_ITEMS or depth > _MAX_JSON_DEPTH:
            raise OperationPayloadError("operation_payload_too_large")
        if item is None or isinstance(item, bool):
            return item
        if type(item) is int:
            if not -(2**63) <= item < 2**63:
                raise OperationPayloadError("operation_payload_invalid")
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise OperationPayloadError("operation_payload_invalid")
            return item
        if isinstance(item, UUID):
            return str(item)
        if isinstance(item, datetime):
            return _aware_utc(item).isoformat()
        if isinstance(item, str):
            if not len(item) <= _MAX_JSON_STRING or any(not character.isprintable() for character in item):
                raise OperationPayloadError("operation_payload_invalid")
            if _unsafe_string(item):
                raise OperationPayloadError("operation_payload_unsafe")
            return item
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            for key, nested in item.items():
                if not isinstance(key, str) or _JSON_KEY.fullmatch(key) is None or _unsafe_key(key):
                    raise OperationPayloadError("operation_payload_unsafe")
                result[key] = normalize(nested, depth=depth + 1)
            return result
        if isinstance(item, Sequence) and not isinstance(item, bytes | bytearray | memoryview | str):
            if len(item) > _MAX_JSON_SEQUENCE:
                raise OperationPayloadError("operation_payload_too_large")
            return [normalize(nested, depth=depth + 1) for nested in item]
        raise OperationPayloadError("operation_payload_invalid")

    normalized = normalize(value or {}, depth=0)
    if not isinstance(normalized, dict):  # pragma: no cover - the root input is a Mapping
        raise OperationPayloadError("operation_payload_invalid")
    encoded = json.dumps(normalized, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > maximum_bytes:
        raise OperationPayloadError("operation_payload_too_large")
    return normalized


def _exact_event_context(
    supplied: Mapping[str, Any] | None,
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_expected = _safe_json_object(expected, maximum_bytes=_MAX_CONTEXT_BYTES)
    if supplied is None:
        return normalized_expected
    normalized_supplied = _safe_json_object(supplied, maximum_bytes=_MAX_CONTEXT_BYTES)
    if normalized_supplied != normalized_expected:
        raise OperationPayloadError("operation_event_context_mismatch")
    return normalized_supplied


def _reconciliation_context(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _safe_json_object(value, maximum_bytes=_MAX_CONTEXT_BYTES)
    if set(normalized) != {"subject_type", "subject_state"}:
        raise OperationPayloadError("operation_event_context_mismatch")
    return {
        "subject_type": _choice(normalized["subject_type"], OPERATION_SUBJECT_TYPES, "subject_type"),
        "subject_state": _choice(
            normalized["subject_state"],
            _RECONCILIATION_SUBJECT_STATES,
            "reconciliation subject state",
        ),
    }


def _reserve_sqlite_writer(session: Session) -> None:
    bind = session.get_bind()
    if bind.dialect.name == "sqlite" and not session.in_transaction():
        session.connection(execution_options={"media_sync_sqlite_begin_immediate": True})


def _owned_revision_condition(expected_revision: int) -> Any:
    """Treat revision as a lower bound inside one fenced lease generation.

    Cancellation and same-transaction subject hooks can advance the durable
    revision before an in-memory coordinator can safely update its copy.  The
    unguessable lease token is the ABA fence; a future revision is still
    rejected while an older revision from that same lease may be absorbed.
    """

    return Operation.revision >= expected_revision


class OperationRepository:
    """Transactional lifecycle, ownership, subjects, and event replay."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_or_replay(
        self,
        *,
        kind: str,
        request_fingerprint: str,
        idempotency_key_hash: str | None = None,
        exclusive_key: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        requested_by: str = "local-api",
        correlation_id: str | None = None,
        phase: str | None = None,
        subjects: Sequence[OperationSubjectInput] = (),
        at: datetime | None = None,
    ) -> OperationStartResult:
        normalized_kind = _choice(kind, OPERATION_KINDS, "operation kind")
        fingerprint = _digest_value(request_fingerprint, "request_fingerprint")
        assert fingerprint is not None
        idempotency_hash = _digest_value(idempotency_key_hash, "idempotency_key_hash", optional=True)
        normalized_exclusive = _label(exclusive_key, "exclusive_key", 512) if exclusive_key is not None else None
        normalized_requester = _label(requested_by, "requested_by", 128)
        normalized_phase = _phase(phase)
        correlation = _canonical_uuid(correlation_id, "correlation_id") if correlation_id else new_uuid()
        if (target_type is None) != (target_id is None):
            raise ValueError("target_type and target_id must be supplied together")
        normalized_target_type = (
            _choice(target_type, OPERATION_SUBJECT_TYPES, "target_type") if target_type is not None else None
        )
        normalized_target_id = _canonical_uuid(target_id, "target_id") if target_id is not None else None
        normalized_subjects = self._subjects(
            subjects,
            target_type=normalized_target_type,
            target_id=normalized_target_id,
        )
        current = _aware_utc(at)

        _reserve_sqlite_writer(self.session)
        replay = self._idempotent(normalized_kind, idempotency_hash)
        if replay is not None:
            return self._replay(replay, fingerprint)
        conflict = self._active_exclusive(normalized_exclusive)
        if conflict is not None:
            raise OperationConflictError("operation_already_running", conflict.id)

        operation = Operation(
            kind=normalized_kind,
            state="queued",
            phase=normalized_phase,
            requested_at=current,
            requested_by=normalized_requester,
            idempotency_key_hash=idempotency_hash,
            request_fingerprint=fingerprint,
            exclusive_key=normalized_exclusive,
            target_type=normalized_target_type,
            target_id=normalized_target_id,
            correlation_id=correlation,
            result_summary={},
            event_sequence=0,
            revision=0,
            updated_at=current,
        )
        try:
            with self.session.begin_nested():
                self.session.add(operation)
                self.session.flush()
                for subject in normalized_subjects:
                    self.session.add(
                        OperationSubject(
                            operation_id=operation.id,
                            subject_type=subject.subject_type,
                            subject_id=subject.subject_id,
                            role=subject.role,
                            created_at=current,
                        )
                    )
                operation.event_sequence = 1
                operation.revision = 1
                operation.updated_at = current
                self.session.flush()
                self._insert_event(
                    operation,
                    event_code="operation_requested",
                    from_state=None,
                    to_state="queued",
                    phase=normalized_phase,
                    message_key="operation.requested",
                    subject=(normalized_target_type, normalized_target_id),
                    safe_context={
                        "kind": normalized_kind,
                        "target_type": normalized_target_type,
                        "target_id": normalized_target_id,
                    },
                    at=current,
                )
                self.session.flush()
        except IntegrityError:
            self.session.expire_all()
            replay = self._idempotent(normalized_kind, idempotency_hash)
            if replay is not None:
                return self._replay(replay, fingerprint)
            conflict = self._active_exclusive(normalized_exclusive)
            if conflict is not None:
                raise OperationConflictError("operation_already_running", conflict.id) from None
            raise OperationConflictError("operation_create_conflict") from None
        return OperationStartResult(operation.id, operation.state, operation.revision, operation.correlation_id, False)

    def claim(
        self,
        operation_id: str,
        *,
        expected_revision: int,
        lease_owner: str,
        lease_seconds: int,
        at: datetime | None = None,
    ) -> OperationLease:
        normalized_id = _canonical_uuid(operation_id, "operation_id")
        revision = _revision(expected_revision)
        owner = _label(lease_owner, "lease_owner", 255)
        duration = _lease_seconds(lease_seconds)
        current = _aware_utc(at)
        token = new_uuid()
        expiry = current + timedelta(seconds=duration)
        operation = self._mutate_with_event(
            normalized_id,
            conditions=(Operation.state == "queued", Operation.revision == revision),
            values={
                "state": "running",
                "started_at": current,
                "lease_owner": owner,
                "lease_token": token,
                "lease_expires_at": expiry,
            },
            event_code="operation_started",
            from_state="queued",
            to_state="running",
            level="info",
            message_key="operation.started",
            safe_context={},
            at=current,
        )
        return OperationLease(
            operation_id=operation.id,
            lease_owner=owner,
            lease_token=token,
            lease_expires_at=expiry,
            revision=operation.revision,
            cancel_requested_at=operation.cancel_requested_at,
        )

    def heartbeat(
        self,
        operation_id: str,
        *,
        expected_revision: int,
        lease_owner: str,
        lease_token: str,
        lease_seconds: int,
        at: datetime | None = None,
    ) -> OperationLease:
        normalized_id = _canonical_uuid(operation_id, "operation_id")
        revision = _revision(expected_revision)
        owner = _label(lease_owner, "lease_owner", 255)
        token = _canonical_uuid(lease_token, "lease_token")
        duration = _lease_seconds(lease_seconds)
        current = _aware_utc(at)
        expiry = current + timedelta(seconds=duration)
        operation = self.session.execute(
            update(Operation)
            .where(
                Operation.id == normalized_id,
                Operation.state == "running",
                _owned_revision_condition(revision),
                Operation.lease_owner == owner,
                Operation.lease_token == token,
            )
            .values(
                lease_expires_at=expiry,
                revision=Operation.revision + 1,
                updated_at=current,
            )
            .returning(Operation)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        ).scalar_one_or_none()
        if operation is None:
            self._raise_lease_conflict(normalized_id)
        assert operation is not None
        return OperationLease(
            operation_id=operation.id,
            lease_owner=owner,
            lease_token=token,
            lease_expires_at=expiry,
            revision=operation.revision,
            cancel_requested_at=operation.cancel_requested_at,
        )

    def get(self, operation_id: str) -> OperationSnapshot | None:
        operation = self.session.get(Operation, _canonical_uuid(operation_id, "operation_id"))
        return self._snapshot(operation) if operation is not None else None

    def require(self, operation_id: str) -> OperationSnapshot:
        operation = self.get(operation_id)
        if operation is None:
            raise NotFoundError("operation not found")
        return operation

    def list(
        self,
        *,
        kind: str | None = None,
        state: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        correlation_id: str | None = None,
        before: tuple[datetime, str] | None = None,
        limit: int = 100,
    ) -> builtins.list[OperationSnapshot]:
        bounded_limit = _positive_limit(limit)
        statement = select(Operation)
        if kind is not None:
            statement = statement.where(Operation.kind == _choice(kind, OPERATION_KINDS, "operation kind"))
        if state is not None:
            statement = statement.where(Operation.state == _choice(state, OPERATION_STATES, "operation state"))
        if (target_type is None) != (target_id is None):
            raise ValueError("target_type and target_id must be supplied together")
        if target_type is not None and target_id is not None:
            normalized_subject_type = _choice(target_type, OPERATION_SUBJECT_TYPES, "target_type")
            normalized_subject_id = _canonical_uuid(target_id, "target_id")
            statement = statement.where(
                Operation.subjects.any(
                    and_(
                        OperationSubject.subject_type == normalized_subject_type,
                        OperationSubject.subject_id == normalized_subject_id,
                    )
                )
            )
        if correlation_id is not None:
            statement = statement.where(Operation.correlation_id == _canonical_uuid(correlation_id, "correlation_id"))
        if before is not None:
            if not isinstance(before, tuple) or len(before) != 2:
                raise ValueError("operation cursor must be a (requested_at, id) tuple")
            before_at = _aware_utc(before[0])
            before_id = _canonical_uuid(before[1], "operation cursor id")
            statement = statement.where(
                or_(
                    Operation.requested_at < before_at,
                    and_(Operation.requested_at == before_at, Operation.id < before_id),
                )
            )
        rows = self.session.scalars(
            statement.order_by(Operation.requested_at.desc(), Operation.id.desc()).limit(bounded_limit)
        ).all()
        return [self._snapshot(row) for row in rows]

    def request_cancel(
        self,
        operation_id: str,
        *,
        expected_revision: int,
        at: datetime | None = None,
    ) -> OperationSnapshot:
        normalized_id = _canonical_uuid(operation_id, "operation_id")
        revision = _revision(expected_revision)
        current = _aware_utc(at)
        _reserve_sqlite_writer(self.session)
        observed = self.session.get(Operation, normalized_id)
        if observed is None:
            raise NotFoundError("operation not found")
        if observed.state in TERMINAL_OPERATION_STATES or observed.cancel_requested_at is not None:
            return self._snapshot(observed)
        if observed.revision != revision:
            raise OperationStateConflictError("operation_revision_conflict", normalized_id)
        if observed.state == "queued":
            operation = self._mutate_with_event(
                normalized_id,
                conditions=(Operation.state == "queued", Operation.revision == revision),
                values={
                    "state": "cancelled",
                    "cancel_requested_at": current,
                    "finished_at": current,
                },
                event_code="operation_cancelled",
                from_state="queued",
                to_state="cancelled",
                level="info",
                message_key="operation.cancelled",
                safe_context={"phase": observed.phase},
                at=current,
            )
            return self._snapshot(operation)
        if observed.state != "running":  # pragma: no cover - database CHECK closes this vocabulary
            raise OperationStateConflictError("operation_state_conflict", normalized_id)
        operation = self._mutate_with_event(
            normalized_id,
            conditions=(
                Operation.state == "running",
                Operation.revision == revision,
                Operation.cancel_requested_at.is_(None),
            ),
            values={"cancel_requested_at": current},
            event_code="operation_cancel_requested",
            from_state="running",
            to_state="running",
            level="warning",
            message_key="operation.cancel_requested",
            safe_context={},
            at=current,
        )
        return self._snapshot(operation)

    def progress(
        self,
        operation_id: str,
        *,
        expected_revision: int,
        lease_owner: str,
        lease_token: str,
        phase: str | None,
        current: int | None = None,
        total: int | None = None,
        unit: str | None = None,
        event_code: str = "operation_progressed",
        context: Mapping[str, Any] | None = None,
        at: datetime | None = None,
    ) -> OperationSnapshot:
        normalized_current, normalized_total, normalized_unit = self._progress(current, total, unit)
        normalized_phase = _phase(phase)
        normalized_event_code = _choice(event_code, _OWNED_PROGRESS_EVENT_CODES, "owned progress event code")
        if normalized_event_code == "operation_progressed":
            if normalized_current is None or normalized_unit is None:
                raise ValueError("operation progress event requires current and unit")
            expected_context: Mapping[str, Any] = {
                "phase": normalized_phase,
                "progress_current": normalized_current,
                "progress_total": normalized_total,
                "progress_unit": normalized_unit,
            }
            values: Mapping[str, Any] = {
                "phase": normalized_phase,
                "progress_current": normalized_current,
                "progress_total": normalized_total,
                "progress_unit": normalized_unit,
            }
        else:
            if normalized_current is not None or normalized_total is not None or normalized_unit is not None:
                raise ValueError("phase and cancellation observation events cannot change progress")
            expected_context = {"phase": normalized_phase}
            values = {"phase": normalized_phase}
        normalized_context = _exact_event_context(context, expected_context)
        operation = self._owned_event(
            operation_id,
            expected_revision=expected_revision,
            lease_owner=lease_owner,
            lease_token=lease_token,
            values=values,
            event_code=normalized_event_code,
            level="info",
            message_key={
                "operation_cancel_observed": "operation.cancel_observed",
                "operation_phase_changed": "operation.phase_changed",
                "operation_progressed": "operation.progressed",
            }[normalized_event_code],
            safe_context=normalized_context,
            at=at,
        )
        return self._snapshot(operation)

    def link_subject(
        self,
        operation_id: str,
        subject: OperationSubjectInput,
        *,
        expected_revision: int,
        lease_owner: str,
        lease_token: str,
        context: Mapping[str, Any] | None = None,
        at: datetime | None = None,
    ) -> OperationSnapshot:
        normalized_id = _canonical_uuid(operation_id, "operation_id")
        if not isinstance(subject, OperationSubjectInput):
            raise TypeError("subject must be an OperationSubjectInput")
        revision = _revision(expected_revision)
        owner = _label(lease_owner, "lease_owner", 255)
        token = _canonical_uuid(lease_token, "lease_token")
        _reserve_sqlite_writer(self.session)
        owned = self.session.scalar(
            select(Operation)
            .where(
                Operation.id == normalized_id,
                Operation.state == "running",
                _owned_revision_condition(revision),
                Operation.lease_owner == owner,
                Operation.lease_token == token,
            )
            .with_for_update()
        )
        if owned is None:
            self._raise_lease_conflict(normalized_id)
        existing = self.session.get(
            OperationSubject,
            (normalized_id, subject.subject_type, subject.subject_id, subject.role),
        )
        if existing is not None:
            assert owned is not None
            return self._snapshot(owned)
        subject_count = self.session.scalar(
            select(func.count()).select_from(OperationSubject).where(OperationSubject.operation_id == normalized_id)
        )
        if subject_count is not None and subject_count >= _MAX_SUBJECTS:
            raise OperationPayloadError("operation_subject_limit", normalized_id)
        current = _aware_utc(at)
        normalized_context = _exact_event_context(
            context,
            {
                "subject_type": subject.subject_type,
                "subject_id": subject.subject_id,
                "role": subject.role,
            },
        )
        with self.session.begin_nested():
            self.session.add(
                OperationSubject(
                    operation_id=normalized_id,
                    subject_type=subject.subject_type,
                    subject_id=subject.subject_id,
                    role=subject.role,
                    created_at=current,
                )
            )
            operation = self._owned_event(
                normalized_id,
                expected_revision=revision,
                lease_owner=owner,
                lease_token=token,
                values={},
                event_code="operation_entity_linked",
                level="info",
                message_key="operation.subject_linked",
                safe_context=normalized_context,
                subject=subject,
                at=current,
            )
            self.session.flush()
        return self._snapshot(operation)

    def finish_succeeded(
        self,
        operation_id: str,
        *,
        expected_revision: int,
        lease_owner: str,
        lease_token: str,
        result_summary: Mapping[str, Any] | None = None,
        at: datetime | None = None,
    ) -> OperationSnapshot:
        return self._finish(
            operation_id,
            expected_revision=expected_revision,
            lease_owner=lease_owner,
            lease_token=lease_token,
            state="succeeded",
            error_code=None,
            result_summary=result_summary,
            at=at,
        )

    def finish_failed(
        self,
        operation_id: str,
        *,
        expected_revision: int,
        lease_owner: str,
        lease_token: str,
        retryable: bool,
        error_code: str,
        result_summary: Mapping[str, Any] | None = None,
        at: datetime | None = None,
    ) -> OperationSnapshot:
        if not isinstance(retryable, bool):
            raise TypeError("retryable must be a boolean")
        return self._finish(
            operation_id,
            expected_revision=expected_revision,
            lease_owner=lease_owner,
            lease_token=lease_token,
            state="failed_retryable" if retryable else "failed_terminal",
            error_code=error_code,
            result_summary=result_summary,
            at=at,
        )

    def finish_cancelled(
        self,
        operation_id: str,
        *,
        expected_revision: int,
        lease_owner: str,
        lease_token: str,
        result_summary: Mapping[str, Any] | None = None,
        at: datetime | None = None,
    ) -> OperationSnapshot:
        return self._finish(
            operation_id,
            expected_revision=expected_revision,
            lease_owner=lease_owner,
            lease_token=lease_token,
            state="cancelled",
            error_code=None,
            result_summary=result_summary,
            at=at,
        )

    def list_expired_candidates(
        self,
        *,
        at: datetime | None = None,
        limit: int = 100,
        after: tuple[datetime, str] | None = None,
    ) -> builtins.list[OperationRecoveryCandidate]:
        current = _aware_utc(at)
        bounded_limit = _positive_limit(limit)
        statement = select(Operation).where(
            Operation.state == "running",
            Operation.lease_expires_at.is_not(None),
            Operation.lease_expires_at <= current,
        )
        if after is not None:
            if not isinstance(after, tuple) or len(after) != 2:
                raise ValueError("recovery cursor must be a (lease_expires_at, id) tuple")
            after_at = _aware_utc(after[0])
            after_id = _canonical_uuid(after[1], "recovery cursor id")
            statement = statement.where(
                or_(
                    Operation.lease_expires_at > after_at,
                    and_(Operation.lease_expires_at == after_at, Operation.id > after_id),
                )
            )
        rows = self.session.scalars(
            statement.order_by(Operation.lease_expires_at, Operation.id).limit(bounded_limit)
        ).all()
        return [self._recovery_candidate(row) for row in rows]

    def reconcile(
        self,
        candidate: OperationRecoveryCandidate,
        *,
        state: str,
        error_code: str | None,
        context: Mapping[str, Any],
        result_summary: Mapping[str, Any] | None = None,
        at: datetime | None = None,
    ) -> OperationSnapshot:
        if not isinstance(candidate, OperationRecoveryCandidate):
            raise TypeError("candidate must be an OperationRecoveryCandidate")
        target = _choice(state, TERMINAL_OPERATION_STATES, "reconciled operation state")
        normalized_error = self._terminal_error(target, error_code)
        summary = _safe_json_object(result_summary, maximum_bytes=_MAX_RESULT_BYTES)
        normalized_context = _reconciliation_context(context)
        current = _aware_utc(at)
        if candidate.lease_expires_at > current:
            raise ValueError("operation lease has not expired")
        operation = self._mutate_with_event(
            candidate.operation_id,
            conditions=(
                Operation.state == candidate.state,
                Operation.revision == candidate.revision,
                Operation.lease_owner == candidate.lease_owner,
                Operation.lease_token == candidate.lease_token,
                Operation.lease_expires_at == candidate.lease_expires_at,
                Operation.lease_expires_at <= current,
            ),
            values={
                "state": target,
                "finished_at": current,
                "lease_owner": None,
                "lease_token": None,
                "lease_expires_at": None,
                "error_code": normalized_error,
                "result_summary": summary,
            },
            event_code="operation_reconciled",
            from_state=candidate.state,
            to_state=target,
            level="info" if target == "succeeded" else "warning",
            message_key="operation.reconciled",
            safe_context=normalized_context,
            at=current,
        )
        return self._snapshot(operation)

    def events_after(
        self,
        after_stream_sequence: int,
        *,
        operation_id: str | None = None,
        limit: int = 100,
    ) -> builtins.list[OperationEventSnapshot]:
        if (
            type(after_stream_sequence) is not int
            or after_stream_sequence < 0
            or after_stream_sequence > _MAX_EVENT_SEQUENCE
        ):
            raise OperationEventCursorError("operation_event_cursor_invalid")
        bounded_limit = _positive_limit(limit, maximum=1_000)
        pruned_through, last = self.stream_bounds()
        if after_stream_sequence < pruned_through:
            raise OperationEventCursorError("operation_event_cursor_expired")
        if after_stream_sequence > last:
            raise OperationEventCursorError("operation_event_cursor_invalid")
        statement = select(OperationEvent).where(OperationEvent.stream_sequence > after_stream_sequence)
        if operation_id is not None:
            statement = statement.where(OperationEvent.operation_id == _canonical_uuid(operation_id, "operation_id"))
        rows = self.session.scalars(statement.order_by(OperationEvent.stream_sequence).limit(bounded_limit)).all()
        return [self._event_snapshot(row) for row in rows]

    def events_for_operation(
        self,
        operation_id: str,
        *,
        after_operation_sequence: int = 0,
        limit: int = 100,
    ) -> builtins.list[OperationEventSnapshot]:
        normalized_id = _canonical_uuid(operation_id, "operation_id")
        if (
            type(after_operation_sequence) is not int
            or after_operation_sequence < 0
            or after_operation_sequence > _MAX_EVENT_SEQUENCE
        ):
            raise OperationEventCursorError("operation_event_cursor_invalid", normalized_id)
        bounded_limit = _positive_limit(limit, maximum=1_000)
        if self.session.scalar(select(Operation.id).where(Operation.id == normalized_id)) is None:
            raise NotFoundError("operation not found")
        rows = self.session.scalars(
            select(OperationEvent)
            .where(
                OperationEvent.operation_id == normalized_id,
                OperationEvent.operation_sequence > after_operation_sequence,
            )
            .order_by(OperationEvent.operation_sequence)
            .limit(bounded_limit)
        ).all()
        return [self._event_snapshot(row) for row in rows]

    def list_subjects(self, operation_id: str) -> builtins.list[OperationSubjectSnapshot]:
        normalized_id = _canonical_uuid(operation_id, "operation_id")
        if self.session.scalar(select(Operation.id).where(Operation.id == normalized_id)) is None:
            raise NotFoundError("operation not found")
        rows = self.session.scalars(
            select(OperationSubject)
            .where(OperationSubject.operation_id == normalized_id)
            .order_by(OperationSubject.created_at, OperationSubject.subject_type, OperationSubject.subject_id)
        ).all()
        return [
            OperationSubjectSnapshot(
                operation_id=row.operation_id,
                subject_type=row.subject_type,
                subject_id=row.subject_id,
                role=row.role,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def stream_bounds(self) -> tuple[int, int]:
        state = self.session.get(OperationEventStreamState, 1)
        if state is None:
            raise RepositoryError("operation event stream state is unavailable")
        return state.pruned_through_sequence, state.last_sequence

    def _finish(
        self,
        operation_id: str,
        *,
        expected_revision: int,
        lease_owner: str,
        lease_token: str,
        state: str,
        error_code: str | None,
        result_summary: Mapping[str, Any] | None,
        at: datetime | None,
    ) -> OperationSnapshot:
        target = _choice(state, TERMINAL_OPERATION_STATES, "terminal operation state")
        normalized_error = self._terminal_error(target, error_code)
        summary = _safe_json_object(result_summary, maximum_bytes=_MAX_RESULT_BYTES)
        current = _aware_utc(at)
        event_code = {
            "succeeded": "operation_succeeded",
            "failed_retryable": "operation_failed",
            "failed_terminal": "operation_failed",
            "cancelled": "operation_cancelled",
            "interrupted": "operation_interrupted",
        }[target]
        if target in OPERATION_FAILURE_STATES:
            event_context: Mapping[str, Any] = {
                "error_code": normalized_error,
                "retryable": target in {"failed_retryable", "interrupted"},
            }
        else:
            event_context = {}
        operation = self._owned_event(
            operation_id,
            expected_revision=expected_revision,
            lease_owner=lease_owner,
            lease_token=lease_token,
            values={
                "state": target,
                "finished_at": current,
                "lease_owner": None,
                "lease_token": None,
                "lease_expires_at": None,
                "error_code": normalized_error,
                "result_summary": summary,
            },
            event_code=event_code,
            level="info" if target in {"succeeded", "cancelled"} else "error",
            message_key=f"operation.{target}",
            safe_context=event_context,
            to_state=target,
            context_from_phase=target == "cancelled",
            at=current,
        )
        return self._snapshot(operation)

    def _owned_event(
        self,
        operation_id: str,
        *,
        expected_revision: int,
        lease_owner: str,
        lease_token: str,
        values: Mapping[str, Any],
        event_code: str,
        level: str,
        message_key: str,
        safe_context: Mapping[str, Any] | None,
        to_state: str = "running",
        subject: OperationSubjectInput | None = None,
        context_from_phase: bool = False,
        at: datetime | None,
    ) -> Operation:
        normalized_id = _canonical_uuid(operation_id, "operation_id")
        revision = _revision(expected_revision)
        owner = _label(lease_owner, "lease_owner", 255)
        token = _canonical_uuid(lease_token, "lease_token")
        current = _aware_utc(at)
        return self._mutate_with_event(
            normalized_id,
            conditions=(
                Operation.state == "running",
                _owned_revision_condition(revision),
                Operation.lease_owner == owner,
                Operation.lease_token == token,
            ),
            values=dict(values),
            event_code=event_code,
            from_state="running",
            to_state=to_state,
            level=level,
            message_key=message_key,
            safe_context=safe_context,
            subject=(subject.subject_type, subject.subject_id) if subject is not None else None,
            at=current,
            lease_conflict=True,
            context_from_phase=context_from_phase,
        )

    def _mutate_with_event(
        self,
        operation_id: str,
        *,
        conditions: Sequence[Any],
        values: Mapping[str, Any],
        event_code: str,
        from_state: str | None,
        to_state: str | None,
        level: str,
        message_key: str | None,
        safe_context: Mapping[str, Any] | None,
        at: datetime,
        subject: tuple[str | None, str | None] | None = None,
        lease_conflict: bool = False,
        context_from_phase: bool = False,
    ) -> Operation:
        normalized_context = _safe_json_object(safe_context, maximum_bytes=_MAX_CONTEXT_BYTES)
        normalized_event_code = _choice(event_code, OPERATION_EVENT_CODES, "operation event code")
        normalized_level = _choice(level, OPERATION_EVENT_LEVELS, "event level")
        normalized_message = _code(message_key, "message_key", optional=True)
        normalized_from = _choice(from_state, OPERATION_STATES, "from_state") if from_state is not None else None
        normalized_to = _choice(to_state, OPERATION_STATES, "to_state") if to_state is not None else None
        statement_values = dict(values)
        statement_values.update(
            event_sequence=Operation.event_sequence + 1,
            revision=Operation.revision + 1,
            updated_at=at,
        )
        operation = self.session.execute(
            update(Operation)
            .where(Operation.id == operation_id, *conditions)
            .values(**statement_values)
            .returning(Operation)
            .execution_options(synchronize_session="fetch", populate_existing=True)
        ).scalar_one_or_none()
        if operation is None:
            if lease_conflict:
                self._raise_lease_conflict(operation_id)
            self._raise_state_conflict(operation_id)
        assert operation is not None
        if context_from_phase:
            normalized_context = {"phase": operation.phase}
        self._insert_event(
            operation,
            event_code=normalized_event_code,
            from_state=normalized_from,
            to_state=normalized_to,
            phase=operation.phase,
            message_key=normalized_message,
            subject=subject,
            safe_context=normalized_context,
            level=normalized_level,
            at=at,
        )
        self.session.flush()
        return operation

    def _insert_event(
        self,
        operation: Operation,
        *,
        event_code: str,
        from_state: str | None,
        to_state: str | None,
        phase: str | None,
        message_key: str | None,
        subject: tuple[str | None, str | None] | None,
        safe_context: Mapping[str, Any],
        at: datetime,
        level: str = "info",
    ) -> None:
        stream_sequence = self.session.scalar(
            update(OperationEventStreamState)
            .where(OperationEventStreamState.id == 1)
            .values(
                last_sequence=OperationEventStreamState.last_sequence + 1,
                updated_at=at,
            )
            .returning(OperationEventStreamState.last_sequence)
        )
        if stream_sequence is None:
            raise RepositoryError("operation event stream state is unavailable")
        subject_type, subject_id = subject or (None, None)
        self.session.add(
            OperationEvent(
                stream_sequence=stream_sequence,
                operation_id=operation.id,
                operation_sequence=operation.event_sequence,
                at=at,
                level=level,
                event_code=event_code,
                from_state=from_state,
                to_state=to_state,
                phase=phase,
                message_key=message_key,
                subject_type=subject_type,
                subject_id=subject_id,
                safe_context=dict(safe_context),
            )
        )

    def _idempotent(self, kind: str, idempotency_hash: str | None) -> Operation | None:
        if idempotency_hash is None:
            return None
        return self.session.scalar(
            select(Operation).where(
                Operation.kind == kind,
                Operation.idempotency_key_hash == idempotency_hash,
            )
        )

    def _active_exclusive(self, exclusive_key: str | None) -> Operation | None:
        if exclusive_key is None:
            return None
        return self.session.scalar(
            select(Operation)
            .where(Operation.exclusive_key == exclusive_key, Operation.state.in_(tuple(ACTIVE_OPERATION_STATES)))
            .order_by(Operation.requested_at, Operation.id)
            .limit(1)
        )

    @staticmethod
    def _replay(operation: Operation, request_fingerprint: str) -> OperationStartResult:
        if operation.request_fingerprint != request_fingerprint:
            raise OperationConflictError("idempotency_key_reused", operation.id)
        return OperationStartResult(
            operation.id,
            operation.state,
            operation.revision,
            operation.correlation_id,
            True,
        )

    @staticmethod
    def _subjects(
        subjects: Sequence[OperationSubjectInput],
        *,
        target_type: str | None,
        target_id: str | None,
    ) -> tuple[OperationSubjectInput, ...]:
        if isinstance(subjects, str) or len(subjects) > _MAX_SUBJECTS:
            raise OperationPayloadError("operation_subject_limit")
        values: list[OperationSubjectInput] = []
        if target_type is not None and target_id is not None:
            values.append(OperationSubjectInput(target_type, target_id, "target"))
        for subject in subjects:
            if not isinstance(subject, OperationSubjectInput):
                raise TypeError("subjects must contain OperationSubjectInput values")
            if subject not in values:
                values.append(subject)
        if len(values) > _MAX_SUBJECTS:
            raise OperationPayloadError("operation_subject_limit")
        return tuple(values)

    @staticmethod
    def _progress(
        current: int | None,
        total: int | None,
        unit: str | None,
    ) -> tuple[int | None, int | None, str | None]:
        for name, value in (("current", current), ("total", total)):
            if value is not None and (type(value) is not int or not 0 <= value < 2**63):
                raise ValueError(f"progress {name} must be a nonnegative integer")
        if current is not None and total is not None and current > total:
            raise ValueError("progress current cannot exceed total")
        normalized_unit = _code(unit, "progress unit", optional=True)
        if normalized_unit is not None and len(normalized_unit) > 32:
            raise ValueError("progress unit is too long")
        if normalized_unit is not None and current is None and total is None:
            raise ValueError("progress unit requires a value")
        return current, total, normalized_unit

    @staticmethod
    def _terminal_error(state: str, error_code: str | None) -> str | None:
        if state in OPERATION_FAILURE_STATES:
            parsed = _code(error_code, "error_code")
            assert parsed is not None
            return parsed
        if error_code is not None:
            raise ValueError("non-failure operation cannot retain an error code")
        return None

    def _raise_state_conflict(self, operation_id: str) -> None:
        if self.session.scalar(select(Operation.id).where(Operation.id == operation_id)) is None:
            raise NotFoundError("operation not found")
        raise OperationStateConflictError("operation_state_conflict", operation_id)

    def _raise_lease_conflict(self, operation_id: str) -> None:
        if self.session.scalar(select(Operation.id).where(Operation.id == operation_id)) is None:
            raise NotFoundError("operation not found")
        raise OperationLeaseLostError("operation_lease_lost", operation_id)

    @staticmethod
    def _snapshot(operation: Operation) -> OperationSnapshot:
        return OperationSnapshot(
            id=operation.id,
            kind=operation.kind,
            state=operation.state,
            phase=operation.phase,
            progress_current=operation.progress_current,
            progress_total=operation.progress_total,
            progress_unit=operation.progress_unit,
            requested_at=operation.requested_at,
            started_at=operation.started_at,
            finished_at=operation.finished_at,
            requested_by=operation.requested_by,
            target_type=operation.target_type,
            target_id=operation.target_id,
            correlation_id=operation.correlation_id,
            cancel_requested_at=operation.cancel_requested_at,
            error_code=operation.error_code,
            result_summary=dict(operation.result_summary),
            event_sequence=operation.event_sequence,
            revision=operation.revision,
        )

    @staticmethod
    def _event_snapshot(event: OperationEvent) -> OperationEventSnapshot:
        return OperationEventSnapshot(
            stream_sequence=event.stream_sequence,
            operation_id=event.operation_id,
            operation_sequence=event.operation_sequence,
            at=event.at,
            level=event.level,
            event_code=event.event_code,
            from_state=event.from_state,
            to_state=event.to_state,
            phase=event.phase,
            message_key=event.message_key,
            subject_type=event.subject_type,
            subject_id=event.subject_id,
            safe_context=dict(event.safe_context),
        )

    @staticmethod
    def _recovery_candidate(operation: Operation) -> OperationRecoveryCandidate:
        if operation.lease_owner is None or operation.lease_token is None or operation.lease_expires_at is None:
            raise RepositoryError("running operation has incomplete lease state")
        return OperationRecoveryCandidate(
            operation_id=operation.id,
            kind=operation.kind,
            state=operation.state,
            revision=operation.revision,
            lease_owner=operation.lease_owner,
            lease_token=operation.lease_token,
            lease_expires_at=operation.lease_expires_at,
            cancel_requested_at=operation.cancel_requested_at,
            target_type=operation.target_type,
            target_id=operation.target_id,
        )


__all__ = [
    "OperationConflictError",
    "OperationError",
    "OperationEventCursorError",
    "OperationEventSnapshot",
    "OperationLease",
    "OperationLeaseLostError",
    "OperationPayloadError",
    "OperationRecoveryCandidate",
    "OperationRepository",
    "OperationSnapshot",
    "OperationStartResult",
    "OperationStateConflictError",
    "OperationSubjectInput",
    "OperationSubjectSnapshot",
]
