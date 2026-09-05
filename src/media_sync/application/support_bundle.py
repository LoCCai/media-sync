"""Bounded, redaction-safe diagnostics for local support requests.

The bundle is deliberately an aggregate-only projection.  It never reads
request payloads, operation identifiers, timestamps, paths, exception text,
or any credential-bearing domain fields.  The encoded bytes are scanned a
second time before they can cross the application boundary.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy.orm import Session

from media_sync.application.operation_payloads import OperationPayloadError, operation_event_context
from media_sync.infrastructure.db.database import Database
from media_sync.infrastructure.db.models import (
    OPERATION_KINDS,
    OPERATION_STATES,
    Account,
    Asset,
    Author,
    Content,
    Job,
    Operation,
    Subscription,
)

SUPPORT_BUNDLE_SCHEMA_VERSION: Final = 1
MAX_RECENT_OPERATIONS: Final = 200
MAX_RECENT_ERROR_CODES: Final = 32
MAX_SUPPORT_BUNDLE_BYTES: Final = 16_384

_PROJECT_NAME: Final = "media-sync"
_MAX_COUNT: Final = 9_223_372_036_854_775_807
_VERSION_PATTERN: Final = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,63}\Z")
_REVISION_PATTERN: Final = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]{0,127}\Z")
_URL_PATTERN: Final = re.compile(r"(?i)(?:https?|ftp|file)://")
_QUERY_PATTERN: Final = re.compile(r"(?:\?|&)[A-Za-z0-9_.~-]{1,64}=")
_WINDOWS_PATH_PATTERN: Final = re.compile(r"(?i)(?:^|[\"'\s])(?:[a-z]:\\|\\\\)")
_QR_PATTERN: Final = re.compile(r"(?i)(?:^|[^a-z0-9])(?:qr|qrcode|qr_code)(?:[^a-z0-9]|$)|data:image/")
_SENSITIVE_PATTERN: Final = re.compile(r"(?i)(?:authorization|bearer|cookie|credential|password|secret|session|token)")
_EXCEPTION_PATTERN: Final = re.compile(r"(?i)(?:exception|stack[ _-]?trace|traceback)")
_SENTINEL_PATTERN: Final = re.compile(r"(?i)sentinel")
_SAFE_SENSITIVE_REVISIONS: Final = frozenset({"0011_cookie_login"})
_SAFE_SENSITIVE_ERROR_CODES: Final = frozenset(
    {
        "locator_secret_forbidden",
        "cookie_login_account_not_found",
        "cookie_login_conflict",
        "cookie_login_busy",
        "cookie_login_unavailable",
        "cookie_login_rejected",
        "cookie_login_verification_unavailable",
        "cookie_login_timed_out",
        "cookie_login_cancelled",
        "cookie_login_result_invalid",
        "cookie_login_cleanup_failed",
        "cookie_login_save_failed",
    }
)
_SAFE_SENSITIVE_FIELDS: Final = {
    "error_code": _SAFE_SENSITIVE_ERROR_CODES,
    "kind": frozenset({"account-cookie-login"}),
    "schema_revision": _SAFE_SENSITIVE_REVISIONS,
    "expected_schema_revision": _SAFE_SENSITIVE_REVISIONS,
}

_ERROR_MESSAGES: Final = {
    "support_bundle_configuration_invalid": "support bundle configuration is invalid",
    "support_bundle_clock_invalid": "support bundle clock did not return an aware datetime",
    "support_bundle_database_failed": "support bundle database inspection failed",
    "support_bundle_content_unsafe": "support bundle content failed the safety boundary",
    "support_bundle_too_large": "support bundle exceeds the encoded size limit",
}


class SupportBundleError(RuntimeError):
    """A stable service error that never reflects the rejected value."""

    def __init__(self, code: str) -> None:
        try:
            message = _ERROR_MESSAGES[code]
        except KeyError as exc:  # pragma: no cover - programmer error
            raise ValueError("unknown support bundle error code") from exc
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _fail(code: str) -> SupportBundleError:
    return SupportBundleError(code)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _configuration_value(value: object, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or value != value.strip() or pattern.fullmatch(value) is None:
        raise _fail("support_bundle_configuration_invalid")
    return value


def _count(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_COUNT:
        raise _fail("support_bundle_database_failed")
    return value


def _row_count(
    session: Session,
    model: type[Any],
    criterion: ColumnElement[bool] | None = None,
) -> int:
    statement = select(func.count()).select_from(model)
    if criterion is not None:
        statement = statement.where(criterion)
    return _count(session.scalar(statement))


def _schema_revision(session: Session) -> str:
    revisions = tuple(session.scalars(text("SELECT version_num FROM alembic_version")))
    if len(revisions) != 1:
        raise _fail("support_bundle_database_failed")
    revision = revisions[0]
    if (
        not isinstance(revision, str)
        or _REVISION_PATTERN.fullmatch(revision) is None
        or _QR_PATTERN.search(revision)
        or (_SENSITIVE_PATTERN.search(revision) and revision not in _SAFE_SENSITIVE_REVISIONS)
        or _EXCEPTION_PATTERN.search(revision)
        or _SENTINEL_PATTERN.search(revision)
    ):
        raise _fail("support_bundle_database_failed")
    return revision


def _operation_counts(
    session: Session,
    *,
    total_operations: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    state_pairs = [
        (state, _row_count(session, Operation, Operation.state == state)) for state in sorted(OPERATION_STATES)
    ]
    kind_pairs = [(kind, _row_count(session, Operation, Operation.kind == kind)) for kind in sorted(OPERATION_KINDS)]
    if sum(count for _, count in state_pairs) != total_operations:
        raise _fail("support_bundle_database_failed")
    if sum(count for _, count in kind_pairs) != total_operations:
        raise _fail("support_bundle_database_failed")
    state_counts: list[dict[str, object]] = [{"state": state, "count": count} for state, count in state_pairs]
    kind_counts: list[dict[str, object]] = [{"kind": kind, "count": count} for kind, count in kind_pairs]
    return state_counts, kind_counts


def _recent_error_counts(session: Session) -> list[dict[str, object]]:
    recent_codes = session.scalars(
        select(Operation.error_code)
        .where(Operation.error_code.is_not(None))
        .order_by(Operation.requested_at.desc(), Operation.id.desc())
        .limit(MAX_RECENT_OPERATIONS)
    ).all()
    counts: Counter[str] = Counter()
    for raw_code in recent_codes:
        try:
            projected = operation_event_context(
                "operation_failed",
                {"error_code": raw_code, "retryable": False},
            )
        except OperationPayloadError:
            raise _fail("support_bundle_content_unsafe") from None
        safe_code = projected.get("error_code")
        if not isinstance(safe_code, str):  # pragma: no cover - protected by the payload contract
            raise _fail("support_bundle_content_unsafe")
        counts[safe_code] += 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:MAX_RECENT_ERROR_CODES]
    return [{"error_code": error_code, "count": count} for error_code, count in ranked]


def _generated_at(clock: Callable[[], datetime]) -> str:
    try:
        value = clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise _fail("support_bundle_clock_invalid")
        return value.astimezone(UTC).isoformat()
    except SupportBundleError:
        raise
    except Exception:
        raise _fail("support_bundle_clock_invalid") from None


def _assert_closed_document(document: dict[str, object]) -> None:
    try:
        if set(document) != {
            "schema_version",
            "generated_at",
            "project",
            "build",
            "database",
            "entity_counts",
            "operations",
        }:
            raise ValueError
        project = document["project"]
        build = document["build"]
        database = document["database"]
        entity_counts = document["entity_counts"]
        operations = document["operations"]
        if not isinstance(project, dict) or set(project) != {"name", "version"}:
            raise ValueError
        if not isinstance(build, dict) or set(build) != {"expected_schema_revision"}:
            raise ValueError
        if not isinstance(database, dict) or set(database) != {
            "reachable",
            "ready",
            "schema_revision",
            "revision_matches",
        }:
            raise ValueError
        if not isinstance(entity_counts, dict) or set(entity_counts) != {
            "accounts",
            "subscriptions",
            "authors",
            "contents",
            "assets",
            "jobs",
            "operations",
        }:
            raise ValueError
        if not isinstance(operations, dict) or set(operations) != {
            "state_counts",
            "kind_counts",
            "recent_error_counts",
        }:
            raise ValueError
        for item in operations["state_counts"]:
            if not isinstance(item, dict) or set(item) != {"state", "count"}:
                raise ValueError
        for item in operations["kind_counts"]:
            if not isinstance(item, dict) or set(item) != {"kind", "count"}:
                raise ValueError
        for item in operations["recent_error_counts"]:
            if not isinstance(item, dict) or set(item) != {"error_code", "count"}:
                raise ValueError
    except (KeyError, TypeError, ValueError):
        raise _fail("support_bundle_content_unsafe") from None


def _assert_encoded_safe(encoded: bytes) -> None:
    try:
        material = encoded.decode("ascii").replace("\\\\", "\\").replace("\\/", "/")
    except UnicodeDecodeError:
        raise _fail("support_bundle_content_unsafe") from None

    # These exact field/value pairs describe fixed schema and operation
    # vocabulary, never user material. Do not exempt prefixes, substrings, or
    # the same values in another field (for example the application version).
    scanned = material
    for field, values in _SAFE_SENSITIVE_FIELDS.items():
        for value in values:
            scanned = scanned.replace(f'"{field}":"{value}"', f'"{field}":""')
    if (
        _URL_PATTERN.search(scanned)
        or _QUERY_PATTERN.search(scanned)
        or _WINDOWS_PATH_PATTERN.search(scanned)
        or ':"/' in scanned
        or ':"~/' in scanned
        or _QR_PATTERN.search(scanned)
        or _SENSITIVE_PATTERN.search(scanned)
        or _EXCEPTION_PATTERN.search(scanned)
        or _SENTINEL_PATTERN.search(scanned)
    ):
        raise _fail("support_bundle_content_unsafe")


def _encode_document(document: dict[str, object]) -> bytes:
    _assert_closed_document(document)
    try:
        encoded = json.dumps(
            document,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise _fail("support_bundle_content_unsafe") from None
    _assert_encoded_safe(encoded)
    if len(encoded) > MAX_SUPPORT_BUNDLE_BYTES:
        raise _fail("support_bundle_too_large")
    return encoded


class SupportBundleService:
    """Build a bounded JSON support bundle without exporting sensitive rows."""

    def __init__(
        self,
        database: Database,
        *,
        application_version: str,
        expected_revision: str,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._database = database
        self._application_version = _configuration_value(application_version, _VERSION_PATTERN)
        self._expected_revision = _configuration_value(expected_revision, _REVISION_PATTERN)
        self._clock = clock

    def build(self) -> bytes:
        generated_at = _generated_at(self._clock)
        try:
            with self._database.session() as session:
                current_revision = _schema_revision(session)
                entity_counts = {
                    "accounts": _row_count(session, Account),
                    "subscriptions": _row_count(session, Subscription),
                    "authors": _row_count(session, Author),
                    "contents": _row_count(session, Content),
                    "assets": _row_count(session, Asset),
                    "jobs": _row_count(session, Job),
                    "operations": _row_count(session, Operation),
                }
                state_counts, kind_counts = _operation_counts(
                    session,
                    total_operations=entity_counts["operations"],
                )
                recent_error_counts = _recent_error_counts(session)
        except SupportBundleError:
            raise
        except Exception:
            raise _fail("support_bundle_database_failed") from None

        revision_matches = current_revision == self._expected_revision
        document: dict[str, object] = {
            "schema_version": SUPPORT_BUNDLE_SCHEMA_VERSION,
            "generated_at": generated_at,
            "project": {"name": _PROJECT_NAME, "version": self._application_version},
            "build": {"expected_schema_revision": self._expected_revision},
            "database": {
                "reachable": True,
                "ready": revision_matches,
                "schema_revision": current_revision,
                "revision_matches": revision_matches,
            },
            "entity_counts": entity_counts,
            "operations": {
                "state_counts": state_counts,
                "kind_counts": kind_counts,
                "recent_error_counts": recent_error_counts,
            },
        }
        return _encode_document(document)


__all__ = [
    "MAX_RECENT_ERROR_CODES",
    "MAX_RECENT_OPERATIONS",
    "MAX_SUPPORT_BUNDLE_BYTES",
    "SUPPORT_BUNDLE_SCHEMA_VERSION",
    "SupportBundleError",
    "SupportBundleService",
]
