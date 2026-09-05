"""CLI contracts for explicit, host-assisted MediaCrawler QR login."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

import media_sync.interfaces.cli as cli_module
from media_sync.config import get_settings
from media_sync.infrastructure.db import Account, Database, LoginSession
from media_sync.integrations.mediacrawler import (
    MediaCrawlerLoginMode,
    MediaCrawlerLoginResult,
    MediaCrawlerLoginStatus,
)
from media_sync.interfaces.cli import app

runner = CliRunner()
_ACCOUNT_ID = UUID("10000000-0000-4000-8000-000000000011")


@pytest.fixture
def login_cli_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    database_path = tmp_path / "state" / "login-cli.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MEDIA_SYNC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MEDIA_SYNC_ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setenv("MEDIA_SYNC_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("MEDIA_SYNC_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", database_url)
    monkeypatch.setenv(
        "MEDIA_SYNC_MEDIACRAWLER_PYTHON_EXECUTABLE",
        str(tmp_path / "private-runtime" / "python.exe"),
    )
    get_settings.cache_clear()

    initialized = runner.invoke(app, ["db", "init"])
    assert initialized.exit_code == 0, initialized.output
    try:
        yield database_url
    finally:
        get_settings.cache_clear()


def _add_account(*, adapter: str = "mediacrawler", login_method: str = "qr") -> str:
    arguments = [
        "account",
        "add",
        "--platform",
        "bili",
        "--display-name",
        f"login-{adapter}-{login_method}",
        "--adapter",
        adapter,
        "--login-method",
        login_method,
    ]
    if login_method == "cookie":
        arguments.extend(["--credential-ref", "env:MEDIA_SYNC_LOGIN_CLI_SENTINEL"])
    arguments.append("--json")
    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.output
    return str(json.loads(result.output)["id"])


@pytest.mark.parametrize(
    ("arguments", "expected_code"),
    [
        ([], "mediacrawler_not_enabled"),
        (["--accept-mediacrawler-license"], "mediacrawler_not_enabled"),
        (["--enable-mediacrawler"], "license_acknowledgement_required"),
    ],
)
def test_account_login_double_gate_precedes_settings_and_database(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    expected_code: str,
) -> None:
    def unexpected_settings() -> None:
        raise AssertionError("gated invocation must not read settings or open the database")

    monkeypatch.setattr(cli_module, "get_settings", unexpected_settings)

    result = runner.invoke(
        app,
        ["account", "login", "--account-id", str(_ACCOUNT_ID), *arguments, "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "account_id": str(_ACCOUNT_ID),
        "status": "failed",
        "error_code": expected_code,
        "retryable": False,
    }
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("adapter", "login_method"),
    [
        ("fake", "qr"),
        ("mediacrawler", "cookie"),
        ("mediacrawler", "saved_session"),
    ],
)
def test_account_login_rejects_foreign_and_non_qr_accounts_before_integration(
    login_cli_database: str,
    monkeypatch: pytest.MonkeyPatch,
    adapter: str,
    login_method: str,
) -> None:
    account_id = _add_account(adapter=adapter, login_method=login_method)

    def unexpected_process_runner(**_kwargs: object) -> None:
        raise AssertionError("ineligible account must not construct or run the process integration")

    monkeypatch.setattr(cli_module, "MediaCrawlerLoginProcessRunner", unexpected_process_runner)

    result = runner.invoke(
        app,
        [
            "account",
            "login",
            "--account-id",
            account_id,
            "--enable-mediacrawler",
            "--accept-mediacrawler-license",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.output)["error_code"] == "account_login_ineligible"
    database = Database(login_cli_database)
    try:
        with database.session() as session:
            account = session.get(Account, account_id)
            assert account is not None
            assert account.auth_status == "unknown"
            assert session.scalar(select(func.count()).select_from(LoginSession)) == 0
    finally:
        database.dispose()


@pytest.mark.parametrize(
    ("initial_login_method", "initial_auth_status"),
    [("qr", "unknown"), ("saved_session", "expired")],
)
def test_account_login_success_and_status_are_fixed_and_redacted(
    login_cli_database: str,
    monkeypatch: pytest.MonkeyPatch,
    initial_login_method: str,
    initial_auth_status: str,
) -> None:
    account_id = _add_account(login_method=initial_login_method)
    if initial_auth_status != "unknown":
        database = Database(login_cli_database)
        try:
            with database.session() as session:
                account = session.get(Account, account_id)
                assert account is not None
                account.auth_status = initial_auth_status
        finally:
            database.dispose()
    captured: dict[str, Any] = {}

    class _AuthenticatedProcessRunner:
        def __init__(self, **kwargs: object) -> None:
            captured["kwargs"] = kwargs

        def run(self, request: object, **kwargs: object) -> MediaCrawlerLoginResult:
            captured["request"] = request
            on_account_locked = kwargs["on_account_locked"]
            assert callable(on_account_locked)
            on_account_locked()
            return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.AUTHENTICATED, "a" * 40)

    monkeypatch.setattr(cli_module, "MediaCrawlerLoginProcessRunner", _AuthenticatedProcessRunner)

    result = runner.invoke(
        app,
        [
            "account",
            "login",
            "--account-id",
            account_id,
            "--enable-mediacrawler",
            "--accept-mediacrawler-license",
            "--timeout-seconds",
            "12",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["account_id"] == account_id
    assert payload["runner_status"] == "authenticated"
    assert payload["login_session_status"] == "succeeded"
    assert payload["auth_status"] == "authenticated"
    assert payload["completed_at"] is not None
    assert set(payload) == {
        "account_id",
        "login_session_id",
        "runner_status",
        "login_session_status",
        "auth_status",
        "expires_at",
        "completed_at",
        "created_at",
        "updated_at",
    }
    request = captured["request"]
    assert request.account_id == UUID(account_id)
    assert request.mode is MediaCrawlerLoginMode.INTERACTIVE_QR
    assert request.timeout_seconds == 12.0
    process_kwargs = captured["kwargs"]
    assert process_kwargs["enabled"] is True
    assert process_kwargs["license_acknowledged"] is True

    status = runner.invoke(app, ["account", "login-status", "--account-id", account_id, "--json"])
    assert status.exit_code == 0, status.output
    status_payload = json.loads(status.output)
    assert status_payload["account_id"] == account_id
    assert status_payload["auth_status"] == "authenticated"
    assert status_payload["login_session_id"] == payload["login_session_id"]
    assert status_payload["login_session_status"] == "succeeded"
    combined_output = result.output + status.output
    for forbidden in ("private-runtime", "profile_path", "public_payload", "upstream_sha", "cookie", "qr_token"):
        assert forbidden not in combined_output.lower()

    database = Database(login_cli_database)
    try:
        with database.session() as session:
            account = session.get(Account, account_id)
            assert account is not None
            assert (account.login_method, account.auth_status) == ("saved_session", "authenticated")
            assert session.scalar(select(func.count()).select_from(LoginSession)) == 1
    finally:
        database.dispose()


def test_account_login_timeout_persists_recoverable_state_and_exits_nonzero(
    login_cli_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = _add_account()

    class _TimedOutProcessRunner:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def run(self, _request: object, **kwargs: object) -> MediaCrawlerLoginResult:
            on_account_locked = kwargs["on_account_locked"]
            assert callable(on_account_locked)
            on_account_locked()
            return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.TIMED_OUT, "b" * 40)

    monkeypatch.setattr(cli_module, "MediaCrawlerLoginProcessRunner", _TimedOutProcessRunner)

    result = runner.invoke(
        app,
        [
            "account",
            "login",
            "--account-id",
            account_id,
            "--enable-mediacrawler",
            "--accept-mediacrawler-license",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert (payload["runner_status"], payload["login_session_status"], payload["auth_status"]) == (
        "timed_out",
        "expired",
        "required",
    )
    database = Database(login_cli_database)
    try:
        with database.session() as session:
            account = session.get(Account, account_id)
            login_session = session.scalar(select(LoginSession))
            assert account is not None
            assert login_session is not None
            assert (account.login_method, account.auth_status, login_session.status) == ("qr", "required", "expired")
    finally:
        database.dispose()


def test_account_login_redacts_unexpected_runner_failure(
    login_cli_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = _add_account()
    sentinel = "sentinel-private-child-output-and-profile"

    class _FailingProcessRunner:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def run(self, _request: object, **kwargs: object) -> MediaCrawlerLoginResult:
            on_account_locked = kwargs["on_account_locked"]
            assert callable(on_account_locked)
            on_account_locked()
            raise RuntimeError(sentinel)

    monkeypatch.setattr(cli_module, "MediaCrawlerLoginProcessRunner", _FailingProcessRunner)

    result = runner.invoke(
        app,
        [
            "account",
            "login",
            "--account-id",
            account_id,
            "--enable-mediacrawler",
            "--accept-mediacrawler-license",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "account_id": account_id,
        "status": "failed",
        "error_code": "account_login_unexpected",
        "retryable": True,
    }
    assert sentinel not in result.output
    assert "Traceback" not in result.output
    database = Database(login_cli_database)
    try:
        with database.session() as session:
            account = session.get(Account, account_id)
            login_session = session.scalar(select(LoginSession))
            assert account is not None
            assert login_session is not None
            assert (account.auth_status, login_session.status) == ("failed", "failed")
    finally:
        database.dispose()


def test_account_login_status_missing_account_is_structured_and_nonzero(
    login_cli_database: str,
) -> None:
    del login_cli_database

    result = runner.invoke(
        app,
        ["account", "login-status", "--account-id", str(_ACCOUNT_ID), "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "account_id": str(_ACCOUNT_ID),
        "status": "failed",
        "error_code": "account_login_not_found",
        "retryable": False,
    }


def test_account_login_status_without_session_omits_account_secrets_and_paths(
    login_cli_database: str,
) -> None:
    account_id = _add_account(login_method="cookie")
    profile_sentinel = "C:/private/sentinel-profile-root"
    database = Database(login_cli_database)
    try:
        with database.session() as session:
            account = session.get(Account, account_id)
            assert account is not None
            account.profile_path = profile_sentinel
    finally:
        database.dispose()

    result = runner.invoke(
        app,
        ["account", "login-status", "--account-id", account_id, "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "account_id": account_id,
        "auth_status": "unknown",
        "auth_updated_at": None,
        "login_session_id": None,
        "login_session_status": None,
        "expires_at": None,
        "completed_at": None,
        "created_at": None,
        "updated_at": None,
        "diagnostic": None,
    }
    lowered = result.output.lower()
    for forbidden in (
        profile_sentinel.lower(),
        "media_sync_login_cli_sentinel",
        "credential_ref",
        "profile_path",
    ):
        assert forbidden not in lowered
