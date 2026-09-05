"""Closed scheduler diagnostics shared by API and CLI, without new database reads."""

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from media_sync.interfaces.cli import _scheduler_job_payload, _scheduler_worker_payload
from media_sync.scheduler import SchedulerJobSummary, SchedulerWorkerResult

FIXED_CODES = (
    "rate_limited",
    "risk_controlled",
    "temporary_upstream",
    "upstream_timeout",
    "upstream_unavailable",
    "account_busy",
    "auth_expired",
    "credentials_unavailable",
    "captcha_required",
    "interactive_required",
    "license_acknowledgement_required",
    "qr_required",
    "configuration_invalid",
    "handler_unsupported",
    "output_security_failed",
    "schema_invalid",
    "content_ownership_conflict",
    "unexpected_handler_failure",
    "scheduler_heartbeat_failed",
    "scheduler_heartbeat_storage_busy",
    "scheduler_finalize_failed",
)
ELIGIBLE_STATUSES = (
    "failed_retryable",
    "failed_terminal",
    "retry_wait",
    "waiting_auth",
    "waiting_user",
    "fenced",
)
SENTINEL = "SECRET_SENTINEL cookie=value /private/database.sqlite3 SELECT hidden"


def _payloads(status: Any, code: Any) -> tuple[dict[str, object], dict[str, object]]:
    now = datetime(2026, 9, 5, tzinfo=UTC)
    job = SchedulerJobSummary(
        job_id="test-job",
        subscription_id="test-subscription",
        account_id="test-account",
        platform="bili",
        status=status,
        attempts=1,
        max_attempts=5,
        available_at=now,
        scheduled_for=now,
        run_id=None,
        last_error_code=code,
        created_at=now,
        updated_at=now,
        started_at=now,
        finished_at=None,
    )
    result = SchedulerWorkerResult(
        job_id=job.job_id,
        subscription_id=job.subscription_id,
        status=status,
        attempt=1,
        error_code=code,
    )
    return _scheduler_job_payload(job), _scheduler_worker_payload(result)


@pytest.mark.parametrize("code", FIXED_CODES)
@pytest.mark.parametrize("status", ELIGIBLE_STATUSES)
def test_scheduler_projection_exposes_only_exact_fixed_codes(status: str, code: str) -> None:
    job, worker = _payloads(status, code)
    assert job["last_error_code"] == worker["error_code"] == code


@pytest.mark.parametrize(
    "code",
    [
        None,
        "",
        SENTINEL,
        "unknown_fixed_code",
        "schema_invalid\n",
        "SCHEMA_INVALID",
        "content_ownership_conflict " + SENTINEL,
        "CONTENT_OWNERSHIP_CONFLICT",
        5,
        True,
        {},
        [],
    ],
)
def test_scheduler_projection_does_not_guess_or_reflect_unknown_diagnostic(code: Any) -> None:
    job, worker = _payloads("failed_terminal", code)
    assert job["last_error_code"] is worker["error_code"] is None
    assert SENTINEL not in json.dumps([job, worker])
    assert "unexpected_handler_failure" not in json.dumps([job, worker])


@pytest.mark.parametrize(
    "status", ["succeeded", "queued", "claimed", "running", "cancelled", "idle", "failed", "unknown"]
)
def test_scheduler_projection_suppresses_stale_diagnostics_outside_failure_states(status: str) -> None:
    job, worker = _payloads(status, "scheduler_heartbeat_failed")
    assert job["last_error_code"] is worker["error_code"] is None


def test_scheduler_projection_has_additive_closed_fields() -> None:
    job, worker = _payloads("failed_terminal", "schema_invalid")
    assert set(job) == {
        "job_id",
        "subscription_id",
        "account_id",
        "platform",
        "status",
        "attempt",
        "max_attempts",
        "available_at",
        "scheduled_for",
        "run_id",
        "last_error_code",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
    }
    assert set(worker) == {"job_id", "subscription_id", "status", "attempt", "run_id", "error_code"}


def test_scheduler_projection_does_not_coerce_untrusted_objects() -> None:
    class Untrusted:
        def __str__(self) -> str:
            raise AssertionError("must not coerce untrusted diagnostics")

    class StringSubclass(str):
        pass

    for code in (Untrusted(), StringSubclass("schema_invalid")):
        job, worker = _payloads("failed_terminal", code)
        assert job["last_error_code"] is worker["error_code"] is None
    for status in (None, [], Untrusted(), StringSubclass("failed_terminal")):
        job, worker = _payloads(status, "schema_invalid")
        assert job["last_error_code"] is worker["error_code"] is None
