"""Read only the exact latest session's uniquely linked safe login diagnostic."""

from __future__ import annotations

import json
from typing import TypedDict
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from media_sync.application.operation_payloads import OperationPayloadError, operation_result_summary
from media_sync.infrastructure.db import LoginSessionState, Operation, OperationSubject

_TERMINAL_SESSION_STATES = frozenset({"succeeded", "expired", "failed", "cancelled"})
_TERMINAL_OPERATION_STATES = frozenset({"succeeded", "failed_retryable", "failed_terminal", "cancelled", "interrupted"})
_LOGIN_DIAGNOSTIC_ERROR_CODES = frozenset(
    {
        "operation_login_failed",
        "operation_login_expired",
        "operation_login_browser_launch_failed",
        "operation_interrupted",
        "account_login_busy",
        "account_login_configuration_invalid",
        "account_login_start_failed",
        "account_login_result_invalid",
        "account_login_conflict",
        "account_login_unexpected",
    }
)


class LoginDiagnostic(TypedDict):
    """A fixed projection, never a generic view of an Operation or its result."""

    operation_id: str
    operation_state: str
    runner_status: str
    error_code: str | None


def login_operation_error_code(runner_status: str) -> str:
    """Preserve ordinary failure/expiry semantics and identify exact launch failures."""

    if runner_status == "browser_launch_failed":
        return "operation_login_browser_launch_failed"
    if runner_status in {"expired", "timed_out"}:
        return "operation_login_expired"
    return "operation_login_failed"


def _canonical_uuid(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def latest_session_login_diagnostic(
    session: Session,
    account_id: str,
    latest: LoginSessionState | None,
) -> LoginDiagnostic | None:
    """Fail closed instead of borrowing another attempt's historical failure.

    Call alongside the Account/latest-Session read in the same transaction.
    A missing Operation (including CLI attempts), pending completion, ambiguous
    link, or malformed persisted summary has no recoverable detailed reason.
    """

    if (
        latest is None
        or latest.status not in _TERMINAL_SESSION_STATES
        or latest.account_id != account_id
        or not _canonical_uuid(account_id)
        or not _canonical_uuid(latest.id)
    ):
        return None
    candidate_query = (
        select(
            Operation.id,
            Operation.state,
            Operation.target_type,
            Operation.target_id,
            Operation.error_code,
            Operation.result_summary,
        )
        .where(
            Operation.kind == "account-login",
            Operation.subjects.any(
                and_(
                    OperationSubject.subject_type == "login_session",
                    OperationSubject.subject_id == latest.id,
                )
            ),
        )
        .limit(2)
    )
    try:
        candidates = session.execute(candidate_query).all()
    except json.JSONDecodeError:
        # Imported/corrupt JSON is not a diagnostic; other database failures
        # still propagate to the existing fixed-safe API/CLI error boundary.
        return None
    if len(candidates) != 1:
        return None
    operation = candidates[0]
    if (
        not _canonical_uuid(operation.id)
        or operation.state not in _TERMINAL_OPERATION_STATES
        or operation.target_type != "account"
        or operation.target_id != account_id
    ):
        return None
    execution_subjects = session.execute(
        select(OperationSubject.subject_type, OperationSubject.subject_id)
        .where(
            OperationSubject.operation_id == operation.id,
            OperationSubject.role == "execution",
        )
        .limit(2)
    ).all()
    if len(execution_subjects) != 1 or tuple(execution_subjects[0]) != ("login_session", latest.id):
        return None
    error_code = operation.error_code
    if error_code is not None and (type(error_code) is not str or error_code not in _LOGIN_DIAGNOSTIC_ERROR_CODES):
        return None
    if (operation.state in {"succeeded", "cancelled"}) != (error_code is None):
        return None
    try:
        summary = operation_result_summary("account-login", operation.result_summary)
    except OperationPayloadError:
        return None
    if (
        summary["account_id"] != account_id
        or summary["login_session_id"] != latest.id
        or summary["login_session_status"] != latest.status
    ):
        return None
    runner_status = summary["runner_status"]
    if not isinstance(runner_status, str):  # The closed summary validator already guarantees this.
        return None
    if runner_status == "authenticated":
        consistent = (
            operation.state == "succeeded"
            and latest.status == "succeeded"
            and summary["auth_status"] == "authenticated"
            and error_code is None
        )
    elif runner_status == "cancelled":
        consistent = (
            operation.state == "cancelled"
            and latest.status == "cancelled"
            and summary["auth_status"] == "required"
            and error_code is None
        )
    else:
        expired = runner_status in {"expired", "timed_out"}
        consistent = (
            operation.state == "failed_terminal"
            and latest.status == ("expired" if expired else "failed")
            and summary["auth_status"] == ("required" if expired else "failed")
            and error_code == login_operation_error_code(runner_status)
        )
    if not consistent:
        return None
    return {
        "operation_id": operation.id,
        "operation_state": operation.state,
        "runner_status": runner_status,
        "error_code": error_code,
    }


__all__ = ["LoginDiagnostic", "latest_session_login_diagnostic", "login_operation_error_code"]
