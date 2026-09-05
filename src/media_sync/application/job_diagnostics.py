"""Exact-Job, bounded support reports with no raw logs or credential material."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text

from media_sync import __version__
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.models import (
    JOB_STATUSES,
    OPERATION_KINDS,
    OPERATION_STATES,
    PLATFORMS,
    RUN_STATUSES,
    TERMINAL_JOB_STATUSES,
    TERMINAL_RUN_STATUSES,
    Job,
    Operation,
    OperationSubject,
    SyncRun,
)
from media_sync.scheduler.policy import classify_failure

MAX_REPORT_OPERATIONS = 5
MAX_REPORT_BYTES = 16_384
_ERROR_STATES = frozenset(
    {
        "failed_terminal",
        "failed_retryable",
        "retry_wait",
        "waiting_auth",
        "waiting_user",
        "awaiting_auth",
        "interrupted",
        "cancelled",
        "fenced",
    }
)
_CONTROL_ERRORS = frozenset(
    {
        "scheduler_lease_lost",
        "scheduler_cancelled",
        "operation_interrupted",
        "scheduler_operation_rejected",
        "scheduler_run_failed",
        "operation_execution_failed",
    }
)
_PHASES = frozenset(
    {
        "preparing",
        "running",
        "syncing",
        "ingesting",
        "finalizing",
        "reconciling",
        "completed",
        "claiming_jobs",
        "jobs_processed",
    }
)
_REVISIONS = frozenset(
    {
        "0001_core",
        "0002_checkpoint",
        "0003_media_download_emby",
        "0004_scheduler_control_plane",
        "0005_asset_refresh_sources",
        "0006_operations_observability",
        "0007_media_server_operations",
        "0008_playback_evidence",
        "0009_subscription_removal",
        "0010_creator_profiles",
        "0011_cookie_login",
    }
)


class JobDiagnosticError(RuntimeError):
    def __init__(self, code: str = "job_diagnostic_unavailable") -> None:
        self.code = "job_diagnostic_not_found" if code == "job_diagnostic_not_found" else "job_diagnostic_unavailable"
        super().__init__(self.code)


def _uuid(value: object) -> str | None:
    if type(value) is not str or len(value) != 36:
        return None
    try:
        return value if str(UUID(value)) == value else None
    except ValueError:
        return None


def _time(value: object) -> str | None:
    if isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None:
        return value.astimezone(UTC).isoformat()
    return None


def _count(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= 2**63 - 1 else None


def _code(value: object, allowed: frozenset[str]) -> str | None:
    return value if type(value) is str and value in allowed else None


def _error(status: object, value: object) -> dict[str, object]:
    if value is None:
        return {"code": None, "availability": "not_recorded"}
    if type(status) is not str or status not in _ERROR_STATES:
        return {"code": None, "availability": "ineligible_state"}
    if type(value) is str and (classify_failure(value).code == value or value in _CONTROL_ERRORS):
        return {"code": value, "availability": "recognized"}
    return {"code": None, "availability": "unrecognized"}


def _job(row: Mapping[str, Any]) -> dict[str, object]:
    return {
        "id": _uuid(row["id"]),
        "subscription_id": _uuid(row["subscription_id"]),
        "run_id": _uuid(row["run_id"]),
        "platform": _code(row["platform"], PLATFORMS),
        "status": _code(row["status"], JOB_STATUSES),
        "attempt": _count(row["attempts"]),
        "max_attempts": _count(row["max_attempts"]),
        "error": _error(row["status"], row["last_error_code"]),
        **{
            field: _time(row[field])
            for field in ("available_at", "created_at", "started_at", "finished_at", "updated_at")
        },
    }


class JobDiagnosticService:
    def __init__(
        self, database: Database, *, expected_revision: str, clock: Callable[[], datetime] | None = None
    ) -> None:
        if expected_revision not in _REVISIONS:
            raise JobDiagnosticError()
        self.database = database
        self.expected_revision = expected_revision
        self.clock = clock or (lambda: datetime.now(UTC))

    def build(self, job_id: str) -> dict[str, object]:
        if _uuid(job_id) is None:
            raise JobDiagnosticError("job_diagnostic_not_found")
        try:
            return self._build(job_id)
        except JobDiagnosticError:
            raise
        except Exception:
            raise JobDiagnosticError() from None

    def _build(self, job_id: str) -> dict[str, object]:
        generated_at = _time(self.clock())
        if generated_at is None:
            raise JobDiagnosticError()
        with self.database.session() as session:
            row = (
                session.execute(
                    select(
                        Job.id,
                        Job.subscription_id,
                        Job.run_id,
                        Job.platform,
                        Job.status,
                        Job.attempts,
                        Job.max_attempts,
                        Job.last_error_code,
                        Job.available_at,
                        Job.created_at,
                        Job.started_at,
                        Job.finished_at,
                        Job.updated_at,
                    ).where(Job.id == job_id, Job.job_type == "sync.subscription")
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise JobDiagnosticError("job_diagnostic_not_found")
            job = _job(dict(row))
            run_row = None
            if job["run_id"] is not None:
                run_row = (
                    session.execute(
                        select(
                            SyncRun.id,
                            SyncRun.subscription_id,
                            SyncRun.status,
                            SyncRun.error_code,
                            SyncRun.attempt,
                            SyncRun.discovered_count,
                            SyncRun.updated_count,
                            SyncRun.asset_count,
                            SyncRun.started_at,
                            SyncRun.finished_at,
                        ).where(SyncRun.id == job["run_id"])
                    )
                    .mappings()
                    .one_or_none()
                )
            run_matches = run_row is not None and run_row["subscription_id"] == job["subscription_id"]
            run: dict[str, object] | None = None
            if run_row is not None and run_matches:
                run = {
                    "id": _uuid(run_row["id"]),
                    "status": _code(run_row["status"], RUN_STATUSES),
                    "error": _error(run_row["status"], run_row["error_code"]),
                    **{
                        field: _count(run_row[field])
                        for field in ("attempt", "discovered_count", "updated_count", "asset_count")
                    },
                    **{field: _time(run_row[field]) for field in ("started_at", "finished_at")},
                }
            correlated = select(OperationSubject.operation_id).where(
                OperationSubject.subject_type == "job",
                OperationSubject.subject_id == job_id,
            )
            operation_rows = (
                session.execute(
                    select(
                        Operation.id,
                        Operation.kind,
                        Operation.state,
                        Operation.phase,
                        Operation.error_code,
                        Operation.correlation_id,
                        Operation.requested_at,
                        Operation.started_at,
                        Operation.finished_at,
                    )
                    .where(Operation.id.in_(correlated))
                    .order_by(Operation.requested_at.desc(), Operation.id.desc())
                    .limit(MAX_REPORT_OPERATIONS + 1)
                )
                .mappings()
                .all()
            )
            revisions = tuple(session.scalars(text("SELECT version_num FROM alembic_version LIMIT 2")))

        operations = [
            {
                "id": _uuid(item["id"]),
                "kind": _code(item["kind"], OPERATION_KINDS),
                "state": _code(item["state"], OPERATION_STATES),
                "phase": _code(item["phase"], _PHASES),
                "correlation_id": _uuid(item["correlation_id"]),
                "error": _error(item["state"], item["error_code"]),
                **{field: _time(item[field]) for field in ("requested_at", "started_at", "finished_at")},
            }
            for item in operation_rows[:MAX_REPORT_OPERATIONS]
        ]
        observations: list[str] = []
        if job["run_id"] is None:
            observations.append("no_attached_run")
        elif run_row is None:
            observations.append("attached_run_missing")
        elif not run_matches:
            observations.append("attached_run_scope_mismatch")
        if (
            run is not None
            and job["status"] in TERMINAL_JOB_STATUSES
            and run["status"] in RUN_STATUSES - TERMINAL_RUN_STATUSES
        ):
            observations.append("job_terminal_run_nonterminal")
        if job["status"] in {"failed_terminal", "failed_retryable"} and any(
            item["kind"] == "scheduler-run" and item["state"] == "succeeded" for item in operations
        ):
            observations.append("worker_completed_job_failed")
        if run is not None and run["status"] == "succeeded" and job["status"] != "succeeded":
            observations.append("run_succeeded_job_unreconciled")
        observed_revision = _code(revisions[0], _REVISIONS) if len(revisions) == 1 else None
        report: dict[str, object] = {
            "schema_version": 1,
            "application_version": __version__,
            "generated_at": generated_at,
            "database": {
                "expected_revision": self.expected_revision,
                "observed_revision": observed_revision,
                "revision_matches": observed_revision == self.expected_revision,
            },
            "job": job,
            "run_found": run_row is not None,
            "run_matches_subscription": run_matches,
            "run": run,
            "operations": operations,
            "operations_truncated": len(operation_rows) > MAX_REPORT_OPERATIONS,
            "observations": observations,
        }
        if len(json.dumps(report, ensure_ascii=True, allow_nan=False).encode("ascii")) > MAX_REPORT_BYTES:
            raise JobDiagnosticError()
        return report
