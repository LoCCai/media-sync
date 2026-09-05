"""Exact-Job report scope, contradiction preservation and redaction contracts."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from _api_client import authenticated_test_client
from sqlalchemy import event, text

from media_sync.application.job_diagnostics import JobDiagnosticError, JobDiagnosticService, _error
from media_sync.config import Settings
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.infrastructure.db.models import Account, Author, Job, Operation, OperationSubject, Subscription, SyncRun
from media_sync.interfaces.cli import _EXPECTED_DATABASE_REVISION

NOW = datetime(2026, 9, 5, tzinfo=UTC)
PRIVATE = "PRIVATE_SENTINEL cookie=value /private/db.sqlite SELECT hidden"


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    url = f"sqlite+pysqlite:///{(tmp_path / 'diagnostics.sqlite3').as_posix()}"
    upgrade_database(url)
    instance = Database(url)
    try:
        yield instance
    finally:
        instance.dispose()


def _seed(
    database: Database, *, run_status: str | None = "running", code: str | None = "schema_invalid"
) -> tuple[str, str]:
    with database.session() as session:
        account = Account(
            platform="bili", display_name=f"{PRIVATE}-{uuid4()}", login_method="qr", credential_ref=PRIVATE
        )
        author = Author(platform="bili", remote_id=str(uuid4()), display_name=PRIVATE, raw={"cookie": PRIVATE})
        session.add_all([account, author])
        session.flush()
        subscription = Subscription(account_id=account.id, author_id=author.id, policy={"private": PRIVATE})
        session.add(subscription)
        session.flush()
        run = (
            SyncRun(
                subscription_id=subscription.id,
                status=run_status,
                manifest={"private": PRIVATE},
                error_message=PRIVATE,
                started_at=NOW,
            )
            if run_status
            else None
        )
        if run:
            session.add(run)
            session.flush()
        job = Job(
            job_type="sync.subscription",
            natural_key=str(uuid4()),
            subscription_id=subscription.id,
            account_id=account.id,
            platform="bili",
            run_id=run.id if run else None,
            status="failed_terminal",
            last_error_code=code,
            last_error_message=PRIVATE,
            payload={"private": PRIVATE},
            created_at=NOW,
        )
        session.add(job)
        session.flush()
        return job.id, subscription.id


def _service(database: Database) -> JobDiagnosticService:
    return JobDiagnosticService(database, expected_revision=_EXPECTED_DATABASE_REVISION, clock=lambda: NOW)


def _operation(database: Database, job_id: str, *, state: str = "succeeded") -> str:
    with database.session() as session:
        operation = Operation(
            kind="scheduler-run",
            state=state,
            request_fingerprint="a" * 64,
            phase="completed",
            requested_at=NOW,
            finished_at=NOW,
            result_summary={"private": PRIVATE},
            error_code=PRIVATE if state == "failed_terminal" else None,
        )
        session.add(operation)
        session.flush()
        session.add(OperationSubject(operation_id=operation.id, subject_type="job", subject_id=job_id, role="result"))
        return operation.id


def test_exact_report_preserves_terminal_job_nonterminal_run_without_writes(database: Database) -> None:
    job_id, _ = _seed(database)
    operation_id = _operation(database, job_id)
    queries: list[str] = []

    def before_cursor_execute(
        _conn: object, _cursor: object, statement: str, _parameters: object, _context: object, _many: object
    ) -> None:
        queries.append(statement)

    event.listen(database.engine, "before_cursor_execute", before_cursor_execute)
    try:
        report = _service(database).build(job_id)
    finally:
        event.remove(database.engine, "before_cursor_execute", before_cursor_execute)
    assert report["observations"] == ["job_terminal_run_nonterminal", "worker_completed_job_failed"]
    assert report["job"]["error"] == {"code": "schema_invalid", "availability": "recognized"}
    assert report["run"]["status"] == "running"
    assert report["run"]["error"] == {"code": None, "availability": "not_recorded"}
    assert report["operations"][0]["id"] == operation_id
    assert report["database"]["revision_matches"] is True
    assert all(query.lstrip().upper().startswith(("SELECT", "BEGIN")) for query in queries)
    assert all(
        private_column not in " ".join(queries).lower()
        for private_column in ("payload", "manifest", "last_error_message", "credential_ref", "result_summary")
    )
    assert PRIVATE not in json.dumps(report)
    assert len(json.dumps(report).encode()) < 16_384


@pytest.mark.parametrize(
    "status,code,availability",
    [
        ("failed_terminal", None, "not_recorded"),
        ("failed_terminal", "looks_like_a_secret", "unrecognized"),
        ("failed_terminal", PRIVATE, "unrecognized"),
        ("succeeded", "schema_invalid", "ineligible_state"),
        ("failed_terminal", "schema_invalid\n", "unrecognized"),
    ],
)
def test_error_availability_never_guesses_or_echoes(status: str, code: str | None, availability: str) -> None:
    assert _error(status, code) == {"code": None, "availability": availability}


def test_no_run_and_missing_run_are_distinct(database: Database) -> None:
    job_id, _ = _seed(database, run_status=None)
    assert _service(database).build(job_id)["observations"] == ["no_attached_run"]
    # Deliberately model a damaged historical FK using a private test connection.
    connection = database.engine.raw_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("UPDATE jobs SET run_id=? WHERE id=?", (str(uuid4()), job_id))
        connection.commit()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    finally:
        connection.close()
    report = _service(database).build(job_id)
    assert report["run_found"] is False
    assert report["observations"] == ["attached_run_missing"]


def test_foreign_subscription_run_is_not_projected(database: Database) -> None:
    first, _ = _seed(database)
    second, _ = _seed(database)
    with database.session() as session:
        session.get(Job, first).run_id = session.get(Job, second).run_id
    report = _service(database).build(first)
    assert report["run_found"] is True
    assert report["run_matches_subscription"] is False
    assert report["run"] is None
    assert report["observations"] == ["attached_run_scope_mismatch"]


def test_report_is_bounded_and_uses_only_exact_job_subject(database: Database) -> None:
    first, _ = _seed(database)
    second, _ = _seed(database)
    foreign_operation = _operation(database, second)
    for _ in range(6):
        _operation(database, first, state="failed_terminal")
    report = _service(database).build(first)
    assert len(report["operations"]) == 5
    assert report["operations_truncated"] is True
    assert foreign_operation not in json.dumps(report)
    assert PRIVATE not in json.dumps(report)
    assert all(op["error"] == {"code": None, "availability": "unrecognized"} for op in report["operations"])


def test_successful_run_is_not_rewritten_to_match_failed_job(database: Database) -> None:
    job_id, _ = _seed(database, run_status="succeeded")
    report = _service(database).build(job_id)
    assert report["observations"] == ["run_succeeded_job_unreconciled"]
    assert report["run"]["status"] == "succeeded"


@pytest.mark.parametrize("identifier", ["not-a-uuid", str(uuid4())])
def test_missing_job_has_fixed_error(database: Database, identifier: str) -> None:
    with pytest.raises(JobDiagnosticError, match=r"^job_diagnostic_not_found$"):
        _service(database).build(identifier)


def test_storage_failure_is_fixed_and_unknown_revision_is_not_reflected(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id, _ = _seed(database)
    with database.session() as session:
        session.execute(
            text("UPDATE alembic_version SET version_num=:revision"), {"revision": "private_schema_sentinel"}
        )
    report = _service(database).build(job_id)
    assert report["database"]["observed_revision"] is None
    assert report["database"]["revision_matches"] is False

    def fail() -> None:
        raise RuntimeError(PRIVATE)

    monkeypatch.setattr(database, "session", fail)
    with pytest.raises(JobDiagnosticError, match=r"^job_diagnostic_unavailable$"):
        _service(database).build(job_id)


def test_authenticated_api_exact_job_report(tmp_path: Path, database: Database) -> None:
    job_id, _ = _seed(database)
    settings = Settings(database_url=str(database.engine.url), state_dir=tmp_path / "state", _env_file=None)
    with authenticated_test_client(settings) as client:
        response = client.get(f"/api/v1/scheduler/jobs/{job_id}/diagnostics")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["job"]["id"] == job_id
        assert PRIVATE not in response.text
        assert client.get(f"/api/v1/scheduler/jobs/{uuid4()}/diagnostics").status_code == 404


@pytest.mark.parametrize("revision", ["0001_core", "0002_checkpoint"])
def test_known_old_revision_is_retained_without_claiming_current(database: Database, revision: str) -> None:
    job_id, _ = _seed(database)
    with database.session() as session:
        session.execute(text("UPDATE alembic_version SET version_num=:revision"), {"revision": revision})
    report = _service(database).build(job_id)
    assert report["database"]["observed_revision"] == revision
    assert report["database"]["revision_matches"] is False


@pytest.mark.parametrize("phase", ["claiming_jobs", "jobs_processed"])
def test_actual_scheduler_operation_phase_and_failure_code_are_recognized(database: Database, phase: str) -> None:
    job_id, _ = _seed(database)
    operation_id = _operation(database, job_id, state="failed_terminal")
    with database.session() as session:
        operation = session.get(Operation, operation_id)
        operation.phase = phase
        operation.error_code = "scheduler_run_failed"
    report = _service(database).build(job_id)
    assert report["operations"][0]["phase"] == phase
    assert report["operations"][0]["error"] == {"code": "scheduler_run_failed", "availability": "recognized"}
