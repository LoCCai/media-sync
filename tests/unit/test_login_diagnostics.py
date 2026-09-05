"""Exact-session diagnostic identity, legacy compatibility and safe projections."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from _api_client import authenticated_test_client
from sqlalchemy import event, select, text
from typer.testing import CliRunner

import media_sync.interfaces.api as api_module
import media_sync.interfaces.cli as cli_module
from media_sync.application.authentication import AccountLoginOutcome
from media_sync.application.login_diagnostics import latest_session_login_diagnostic, login_operation_error_code
from media_sync.application.operation_payloads import operation_result_summary
from media_sync.application.operations import OperationCoordinator
from media_sync.config import Settings
from media_sync.domain import AuthStatus, Platform
from media_sync.infrastructure.db import (
    AccountRepository,
    Database,
    LoginSession,
    LoginSessionRepository,
    LoginSessionState,
    Operation,
    OperationRepository,
    OperationSubject,
    OperationSubjectInput,
    upgrade_database,
)
from media_sync.integrations.mediacrawler.login import MediaCrawlerLoginStatus

_NOW = datetime(2026, 9, 5, 8, tzinfo=UTC)
_PRIVATE = "raw-private-browser-url-cookie-sentinel"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    result = Settings(
        database_url=f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}",
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "export",
        job_dir=tmp_path / "jobs",
        mediacrawler_runtime_dir=tmp_path / "runtime",
        secret_file_dir=tmp_path / "secrets",
        _env_file=None,
    )
    upgrade_database(result.resolved_database_url)
    return result


@pytest.fixture
def database(settings: Settings) -> Iterator[Database]:
    value = Database(settings.resolved_database_url)
    try:
        yield value
    finally:
        value.dispose()


def _seed(database: Database, *, runner_status: str = "browser_launch_failed") -> tuple[str, LoginSessionState, str]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili", adapter="mediacrawler", display_name="diagnostic", login_method="qr", auth_status="failed"
        )
        login = LoginSession(
            account_id=account.id,
            method="qr",
            challenge_kind="qr",
            status="failed",
            expires_at=_NOW + timedelta(minutes=1),
            completed_at=_NOW,
            created_at=_NOW,
            updated_at=_NOW,
            public_payload={"untrusted": _PRIVATE},
        )
        session.add(login)
        session.flush()
        summary = {
            "account_id": account.id,
            "login_session_id": login.id,
            "runner_status": runner_status,
            "login_session_status": "failed",
            "auth_status": "failed",
            "expires_at": login.expires_at.isoformat(),
            "completed_at": _NOW.isoformat(),
        }
        operation = Operation(
            kind="account-login",
            state="failed_terminal",
            target_type="account",
            target_id=account.id,
            request_fingerprint="1" * 64,
            result_summary=summary,
            error_code=login_operation_error_code(runner_status),
            requested_at=_NOW,
            started_at=_NOW,
            finished_at=_NOW,
        )
        session.add(operation)
        session.flush()
        session.add(
            OperationSubject(
                operation_id=operation.id, subject_type="login_session", subject_id=login.id, role="execution"
            )
        )
        session.flush()
        return account.id, LoginSessionRepository(session).list_for_account(account.id)[0], operation.id


def test_projection_is_exact_bounded_and_read_only(database: Database) -> None:
    account_id, latest, operation_id = _seed(database)
    statements: list[tuple[str, object]] = []

    def capture(_connection: object, _cursor: object, statement: str, parameters: object, *_args: object) -> None:
        statements.append((statement, parameters))

    event.listen(database.engine, "before_cursor_execute", capture)
    try:
        with database.session() as session:
            diagnostic = latest_session_login_diagnostic(session, account_id, latest)
            assert not session.dirty and not session.new and not session.deleted
    finally:
        event.remove(database.engine, "before_cursor_execute", capture)

    assert diagnostic == {
        "operation_id": operation_id,
        "operation_state": "failed_terminal",
        "runner_status": "browser_launch_failed",
        "error_code": "operation_login_browser_launch_failed",
    }
    queries = [(query, parameters) for query, parameters in statements if query.startswith("SELECT")]
    assert len(queries) == 2
    assert all("LIMIT ? OFFSET ?" in query and parameters[-2:] == (2, 0) for query, parameters in queries)
    assert _PRIVATE not in json.dumps(diagnostic)


@pytest.mark.parametrize("state", ["pending", "waiting_user"])
def test_active_session_never_borrows_previous_diagnostic(database: Database, state: str) -> None:
    account_id, latest, _operation_id = _seed(database)
    with database.session() as session:
        assert latest_session_login_diagnostic(session, account_id, replace(latest, status=state)) is None


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_operation",
        "wrong_kind",
        "wrong_target",
        "wrong_target_type",
        "wrong_role",
        "other_execution",
        "duplicate_candidate",
        "running",
        "unknown_error",
        "unknown_runner",
        "extra_field",
        "missing_field",
        "wrong_result_account",
        "wrong_result_session",
        "wrong_result_state",
        "non_mapping",
        "invalid_json",
        "success_with_failure",
        "failure_with_authenticated",
        "other_execution_type",
        "contradictory_error",
    ],
)
def test_missing_ambiguous_or_malformed_diagnostic_fails_closed(database: Database, corruption: str) -> None:
    account_id, latest, operation_id = _seed(database)
    with database.session() as session:
        operation = session.get(Operation, operation_id)
        assert operation is not None
        if corruption == "missing_operation":
            session.delete(operation)
        elif corruption == "wrong_kind":
            operation.kind = "asset-download"
        elif corruption == "wrong_target":
            operation.target_id = str(uuid4())
        elif corruption == "wrong_target_type":
            operation.target_type = "asset"
        elif corruption == "wrong_role":
            subject = session.scalar(select(OperationSubject).where(OperationSubject.operation_id == operation_id))
            assert subject is not None
            subject.role = "related"
        elif corruption in {"other_execution", "other_execution_type"}:
            session.add(
                OperationSubject(
                    operation_id=operation_id,
                    subject_type="login_session" if corruption == "other_execution" else "asset",
                    subject_id=str(uuid4()),
                    role="execution",
                )
            )
        elif corruption == "duplicate_candidate":
            duplicate = Operation(
                kind="account-login",
                state="failed_terminal",
                target_type="account",
                target_id=account_id,
                request_fingerprint="2" * 64,
                result_summary=operation.result_summary,
                error_code=operation.error_code,
                requested_at=_NOW - timedelta(days=1),
                finished_at=_NOW,
            )
            session.add(duplicate)
            session.flush()
            session.add(
                OperationSubject(
                    operation_id=duplicate.id, subject_type="login_session", subject_id=latest.id, role="execution"
                )
            )
        elif corruption == "running":
            operation.state = "running"
            operation.finished_at = None
            operation.error_code = None
            operation.lease_owner = "in-progress"
            operation.lease_token = str(uuid4())
            operation.lease_expires_at = _NOW + timedelta(seconds=30)
        elif corruption == "unknown_error":
            operation.error_code = "well_formed_but_unapproved_private_reason"
        elif corruption == "non_mapping":
            operation.result_summary = [_PRIVATE]  # type: ignore[assignment]
        elif corruption == "invalid_json":
            session.execute(
                text("UPDATE operations SET result_summary=:raw WHERE id=:identity"),
                {"raw": "{" + _PRIVATE, "identity": operation_id},
            )
        elif corruption == "success_with_failure":
            operation.state = "succeeded"
            operation.error_code = None
        elif corruption == "contradictory_error":
            operation.error_code = "operation_login_expired"
        else:
            summary = dict(operation.result_summary)
            if corruption == "unknown_runner":
                summary["runner_status"] = _PRIVATE
            elif corruption == "extra_field":
                summary["raw_log"] = _PRIVATE
            elif corruption == "missing_field":
                del summary["runner_status"]
            elif corruption == "wrong_result_account":
                summary["account_id"] = str(uuid4())
            elif corruption == "wrong_result_session":
                summary["login_session_id"] = str(uuid4())
            elif corruption == "wrong_result_state":
                summary["login_session_status"] = "expired"
            elif corruption == "failure_with_authenticated":
                summary["runner_status"] = "authenticated"
            operation.result_summary = summary
    with database.session() as session:
        assert latest_session_login_diagnostic(session, account_id, latest) is None


def test_newer_session_without_operation_has_no_old_failure(database: Database) -> None:
    account_id, _latest, _operation_id = _seed(database)
    with database.session() as session:
        newer = LoginSession(
            account_id=account_id, method="qr", status="failed", created_at=_NOW + timedelta(seconds=1)
        )
        session.add(newer)
        session.flush()
        latest = LoginSessionRepository(session).list_for_account(account_id)[0]
        assert latest.id == newer.id
        assert latest_session_login_diagnostic(session, account_id, latest) is None


@pytest.mark.parametrize("status", ["failed", "configuration_invalid", "start_failed", "result_invalid"])
def test_old_runner_statuses_remain_generic(database: Database, status: str) -> None:
    account_id, latest, _operation_id = _seed(database, runner_status=status)
    with database.session() as session:
        diagnostic = latest_session_login_diagnostic(session, account_id, latest)
    assert diagnostic is not None
    assert diagnostic["runner_status"] == status
    assert diagnostic["error_code"] == "operation_login_failed"


@pytest.mark.parametrize(
    ("runner_status", "session_status", "auth_status", "operation_state", "error_code"),
    [
        ("authenticated", "succeeded", "authenticated", "succeeded", None),
        ("cancelled", "cancelled", "required", "cancelled", None),
        ("expired", "expired", "required", "failed_terminal", "operation_login_expired"),
        ("timed_out", "expired", "required", "failed_terminal", "operation_login_expired"),
    ],
)
def test_other_truthful_terminal_outcomes_remain_visible(
    database: Database,
    runner_status: str,
    session_status: str,
    auth_status: str,
    operation_state: str,
    error_code: str | None,
) -> None:
    account_id, latest, operation_id = _seed(database)
    with database.session() as session:
        login = session.get(LoginSession, latest.id)
        operation = session.get(Operation, operation_id)
        assert login is not None and operation is not None
        login.status = session_status
        operation.state = operation_state
        operation.error_code = error_code
        operation.result_summary = {
            **operation.result_summary,
            "runner_status": runner_status,
            "login_session_status": session_status,
            "auth_status": auth_status,
        }
    with database.session() as session:
        diagnostic = latest_session_login_diagnostic(session, account_id, replace(latest, status=session_status))
    assert diagnostic == {
        "operation_id": operation_id,
        "operation_state": operation_state,
        "runner_status": runner_status,
        "error_code": error_code,
    }


def test_api_and_cli_project_the_same_latest_exact_diagnostic(
    database: Database, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    account_id, latest, operation_id = _seed(database)
    client = authenticated_test_client(settings)
    response = client.get(f"/api/v1/accounts/{account_id}/login-status")
    assert response.status_code == 200
    assert response.json()["login_session_id"] == latest.id
    assert response.json()["diagnostic"]["operation_id"] == operation_id
    assert _PRIVATE not in response.text
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    result = CliRunner().invoke(cli_module.app, ["account", "login-status", "--account-id", account_id, "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == response.json()
    with database.session() as session:
        session.add(
            LoginSession(account_id=account_id, method="qr", status="failed", created_at=_NOW + timedelta(seconds=1))
        )
    refreshed = client.get(f"/api/v1/accounts/{account_id}/login-status")
    cli_refreshed = CliRunner().invoke(
        cli_module.app, ["account", "login-status", "--account-id", account_id, "--json"]
    )
    assert refreshed.json()["diagnostic"] is None
    assert json.loads(cli_refreshed.output)["diagnostic"] is None


def test_restart_recovery_cannot_reconstruct_browser_launch_reason(database: Database) -> None:
    account_id, latest, old_operation_id = _seed(database)
    with database.session() as session:
        operation = session.get(Operation, old_operation_id)
        assert operation is not None
        session.delete(operation)
        session.flush()
        repository = OperationRepository(session)
        started = repository.create_or_replay(
            kind="account-login", request_fingerprint="3" * 64, target_type="account", target_id=account_id, at=_NOW
        )
        lease = repository.claim(
            started.operation_id,
            expected_revision=started.revision,
            lease_owner="abandoned-login",
            lease_seconds=1,
            at=_NOW,
        )
        repository.link_subject(
            started.operation_id,
            OperationSubjectInput("login_session", latest.id, "execution"),
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            at=_NOW,
        )
    coordinator = OperationCoordinator(database)
    try:
        coordinator.reconcile_expired(at=_NOW + timedelta(seconds=2))
        with database.session() as session:
            diagnostic = latest_session_login_diagnostic(session, account_id, latest)
        assert diagnostic is not None
        assert diagnostic["runner_status"] == "failed"
        assert diagnostic["error_code"] == "operation_login_failed"
    finally:
        coordinator.shutdown()


def test_api_maps_launch_failure_without_changing_result_fields(
    database: Database, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    account_id, latest, _old_operation_id = _seed(database)

    class FakeLoginService:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def run(self, *args: object, **kwargs: object) -> AccountLoginOutcome:
            return AccountLoginOutcome(
                account_id=UUID(account_id),
                login_session_id=UUID(latest.id),
                platform=Platform.BILI,
                runner_status=MediaCrawlerLoginStatus("browser_launch_failed"),
                session_status="failed",
                auth_status=AuthStatus.FAILED,
                expires_at=latest.expires_at,
                completed_at=latest.completed_at,
                created_at=latest.created_at,
                updated_at=latest.updated_at,
            )

    monkeypatch.setattr(api_module, "MediaCrawlerQrLoginService", FakeLoginService)
    monkeypatch.setattr(api_module, "collect_account_login_preflight", lambda *args, **kwargs: SimpleNamespace(ok=True))
    with authenticated_test_client(settings) as client:
        started = client.post(
            f"/api/v1/accounts/{account_id}/login",
            json={"enable_mediacrawler": True, "accept_mediacrawler_license": True},
        )
        assert started.status_code == 202
        operation_id = started.json()["operation_id"]
        deadline = time.monotonic() + 5
        terminal: dict[str, object] = {}
        while time.monotonic() < deadline:
            terminal = client.get(f"/api/v1/operations/{operation_id}").json()
            if terminal["state"] not in {"queued", "running"}:
                break
            time.sleep(0.01)
        assert terminal["error_code"] == "operation_login_browser_launch_failed"
        assert terminal["state"] == "failed_terminal"
        result = terminal["result"]
        assert isinstance(result, dict) and result["runner_status"] == "browser_launch_failed"
        assert operation_result_summary("account-login", result) == result
