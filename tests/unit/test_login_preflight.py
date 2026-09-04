"""Execution 0051 account-scoped login-preflight contracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from media_sync.application.login_preflight import collect_account_login_preflight
from media_sync.config import Settings
from media_sync.infrastructure.db import AccountRepository, Database, LoginSessionRepository
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.integrations.mediacrawler.checkout import CheckoutValidationError


def _settings(tmp_path: Path) -> Settings:
    state = tmp_path / "state"
    state.mkdir()
    settings = Settings(
        state_dir=state,
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "library",
        job_dir=tmp_path / "jobs",
        mediacrawler_runtime_dir=state / "mediacrawler",
        mediacrawler_python_executable=tmp_path / "mediacrawler-python",
        mediacrawler_lock_path=tmp_path / "upstreams.lock.json",
    )
    upgrade_database(settings.resolved_database_url)
    return settings


def _account(settings: Settings, *, login_method: str = "qr", auth_status: str = "unknown") -> UUID:
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            account = AccountRepository(session).create(
                platform="bili",
                adapter="mediacrawler",
                display_name=f"account-{login_method}-{auth_status}",
                login_method=login_method,
                auth_status=auth_status,
            )
            return UUID(account.id)
    finally:
        database.dispose()


def _pass_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "media_sync.application.login_preflight.verify_mediacrawler_checkout", lambda *args, **kwargs: object()
    )
    monkeypatch.setattr(
        "media_sync.application.login_preflight.verify_mediacrawler_python", lambda *args, **kwargs: object()
    )
    monkeypatch.setattr(
        "media_sync.application.login_preflight.verify_mediacrawler_browser", lambda *args, **kwargs: "151.0"
    )


def test_login_preflight_is_ready_without_download_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    account_id = _account(settings)
    _pass_runtime(monkeypatch)

    report = collect_account_login_preflight(settings, account_id, license_acknowledged=True)

    assert report.ok is True
    assert report.code == "ready"
    assert report.platform is not None and report.platform.value == "bili"
    assert [check.name for check in report.checks] == [
        "database",
        "account",
        "account_eligible",
        "license_acknowledgement",
        "checkout",
        "runtime",
        "browser",
        "profile",
        "account_lock",
    ]
    assert all(check.status == "pass" for check in report.checks)
    payload = json.dumps(report.to_payload(), sort_keys=True)
    assert str(tmp_path) not in payload
    assert "ffmpeg" not in payload
    assert "ffprobe" not in payload


def test_login_preflight_stops_at_license_without_runtime_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    account_id = _account(settings)

    def unexpected(*args: object, **kwargs: object) -> object:
        raise AssertionError("runtime verifier must not run")

    monkeypatch.setattr("media_sync.application.login_preflight.verify_mediacrawler_checkout", unexpected)
    monkeypatch.setattr("media_sync.application.login_preflight.verify_mediacrawler_python", unexpected)
    monkeypatch.setattr("media_sync.application.login_preflight.verify_mediacrawler_browser", unexpected)

    report = collect_account_login_preflight(settings, account_id, license_acknowledged=False)

    assert report.ok is False
    assert report.code == "license_acknowledgement_required"
    assert report.retryable is False
    assert next(check for check in report.checks if check.name == "license_acknowledgement").status == "fail"
    assert next(check for check in report.checks if check.name == "checkout").status == "not_run"


def test_login_preflight_reports_exact_runtime_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    account_id = _account(settings)
    monkeypatch.setattr(
        "media_sync.application.login_preflight.verify_mediacrawler_checkout", lambda *args, **kwargs: object()
    )

    def reject_runtime(*args: object, **kwargs: object) -> object:
        raise CheckoutValidationError("sentinel path must not escape", "runtime_imports_missing")

    monkeypatch.setattr("media_sync.application.login_preflight.verify_mediacrawler_python", reject_runtime)

    report = collect_account_login_preflight(settings, account_id, license_acknowledged=True)

    assert report.ok is False
    assert report.code == "runtime_imports_missing"
    assert report.to_payload()["checks"][5] == {
        "name": "runtime",
        "status": "fail",
        "required": True,
        "detail_code": "runtime_imports_missing",
    }
    assert "sentinel" not in json.dumps(report.to_payload())


def test_login_preflight_rejects_ineligible_cookie_account_before_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            account = AccountRepository(session).create(
                platform="bili",
                adapter="mediacrawler",
                display_name="cookie-account",
                login_method="cookie",
                credential_ref="env:SECRET_SENTINEL",
            )
            account_id = UUID(account.id)
    finally:
        database.dispose()

    monkeypatch.setattr(
        "media_sync.application.login_preflight.verify_mediacrawler_checkout",
        lambda *args, **kwargs: pytest.fail("checkout must not run"),
    )

    report = collect_account_login_preflight(settings, account_id, license_acknowledged=True)

    assert report.code == "account_login_ineligible"
    assert "SECRET_SENTINEL" not in json.dumps(report.to_payload())


def test_login_preflight_reports_active_session_as_busy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    account_id = _account(settings)
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            LoginSessionRepository(session).create(account_id=str(account_id), method="qr")
    finally:
        database.dispose()
    _pass_runtime(monkeypatch)

    report = collect_account_login_preflight(settings, account_id, license_acknowledged=True)

    assert report.code == "account_login_busy"
    assert report.retryable is True
    assert next(check for check in report.checks if check.name == "account_lock").status == "fail"
    assert next(check for check in report.checks if check.name == "checkout").status == "not_run"


def test_login_preflight_recovers_an_expired_abandoned_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    account_id = _account(settings)
    started_at = datetime.now(UTC) - timedelta(minutes=10)
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            repository = LoginSessionRepository(session)
            started = repository.start_mediacrawler_qr(
                str(account_id),
                expires_at=started_at + timedelta(minutes=5),
                at=started_at,
            )
            repository.mark_waiting_user(started.id, at=started_at)
            login_session_id = started.id
        account_root = settings.resolved_mediacrawler_runtime_dir / "accounts" / "bili" / str(account_id)
        account_root.mkdir(parents=True)
        _pass_runtime(monkeypatch)

        report = collect_account_login_preflight(settings, account_id, license_acknowledged=True)

        assert report.ok is True
        with database.session() as session:
            recovered = LoginSessionRepository(session).get(login_session_id)
            account = AccountRepository(session).get(str(account_id))
            assert recovered is not None and recovered.status == "expired"
            assert account is not None and account.auth_status == "required"
    finally:
        database.dispose()


def test_login_preflight_missing_account_and_database_are_closed(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    missing = collect_account_login_preflight(settings, UUID(int=0), license_acknowledged=True)
    assert missing.code == "account_login_not_found"

    broken = Settings(
        state_dir=tmp_path / "uninitialized",
        mediacrawler_runtime_dir=tmp_path / "runtime",
    )
    unavailable = collect_account_login_preflight(broken, UUID(int=0), license_acknowledged=True)
    assert unavailable.code == "database_not_ready"
    assert unavailable.retryable is True
