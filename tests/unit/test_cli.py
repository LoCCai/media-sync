import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select, text
from typer.testing import CliRunner

import media_sync.interfaces.cli as cli_module
from media_sync import __version__
from media_sync.config import Settings, get_settings
from media_sync.domain import DomainError
from media_sync.infrastructure.db import Account, Database, LoginSession
from media_sync.interfaces.cli import app, collect_doctor_report

runner = CliRunner()


@pytest.fixture
def initialized_cli_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[str]:
    database_path = tmp_path / "state" / "cli.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MEDIA_SYNC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MEDIA_SYNC_ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setenv("MEDIA_SYNC_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("MEDIA_SYNC_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", database_url)
    get_settings.cache_clear()

    initialized = runner.invoke(app, ["db", "init"])
    assert initialized.exit_code == 0, initialized.output
    try:
        yield database_url
    finally:
        get_settings.cache_clear()


def _row_count(database_url: str, model: type[Account] | type[LoginSession]) -> int:
    database = Database(database_url)
    try:
        with database.session() as session:
            count = session.scalar(select(func.count()).select_from(model))
            assert count is not None
            return count
    finally:
        database.dispose()


def test_version_option() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"media-sync {__version__}"


def test_doctor_json_does_not_expose_database_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIA_SYNC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", "sqlite+pysqlite:///sentinel-secret.sqlite3")
    get_settings.cache_clear()

    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["database_driver"] == "sqlite+pysqlite"
    assert "sentinel-secret" not in result.stdout
    get_settings.cache_clear()


def test_doctor_report_is_read_only(tmp_path: Path) -> None:
    settings = Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "exports",
        job_dir=tmp_path / "jobs",
        _env_file=None,
    )

    report = collect_doctor_report(settings)

    assert report["ok"] is True
    assert report["path_exists"] == {"state": False, "archive": False, "export": False, "jobs": False}
    assert list(tmp_path.iterdir()) == []


def test_db_init_runs_packaged_migrations_idempotently(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "state" / "cli.sqlite3"
    monkeypatch.setenv("MEDIA_SYNC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MEDIA_SYNC_ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setenv("MEDIA_SYNC_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("MEDIA_SYNC_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", f"sqlite+pysqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    try:
        first = runner.invoke(app, ["db", "init"])
        second = runner.invoke(app, ["db", "init"])

        assert first.exit_code == 0
        assert second.exit_code == 0
        assert "Database schema upgraded" in first.stdout
        database = Database(f"sqlite+pysqlite:///{database_path.as_posix()}")
        try:
            assert "alembic_version" in inspect(database.engine).get_table_names()
            with database.engine.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001_core"
        finally:
            database.dispose()
    finally:
        get_settings.cache_clear()


def test_db_init_output_redacts_url_user_password_and_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_url = (
        "postgresql+psycopg://sentinel-user:sentinel-password@example.invalid:5544/catalog"
        "?sslmode=require&token=sentinel-query"
    )
    called_with: list[str] = []
    monkeypatch.setenv("MEDIA_SYNC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MEDIA_SYNC_ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setenv("MEDIA_SYNC_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("MEDIA_SYNC_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", secret_url)
    monkeypatch.setattr(cli_module, "upgrade_database", called_with.append)
    get_settings.cache_clear()

    try:
        result = runner.invoke(app, ["db", "init"])

        assert result.exit_code == 0
        assert called_with == [secret_url]
        assert "driver=postgresql+psycopg" in result.stdout
        assert "host=example.invalid:5544" in result.stdout
        for secret in ("sentinel-user", "sentinel-password", "sentinel-query", "catalog"):
            assert secret not in result.stdout
    finally:
        get_settings.cache_clear()


def test_db_status_reports_current_complete_schema_without_exposing_target(
    initialized_cli_database: str,
) -> None:
    json_result = runner.invoke(app, ["db", "status", "--json"])
    text_result = runner.invoke(app, ["db", "status"])

    assert json_result.exit_code == 0, json_result.output
    payload = json.loads(json_result.output)
    assert payload == {
        "ok": True,
        "database_driver": "sqlite+pysqlite",
        "reachable": True,
        "revision": "0001_core",
        "expected_revision": "0001_core",
        "revision_current": True,
        "required_table_count": 10,
        "present_table_count": 10,
        "missing_tables": [],
        "reason": None,
    }
    assert text_result.exit_code == 0
    assert "Database ready:" in text_result.output
    assert "revision=0001_core" in text_result.output
    assert "tables=10/10" in text_result.output
    for output in (json_result.output, text_result.output):
        assert initialized_cli_database not in output
        assert "cli.sqlite3" not in output
        assert "Traceback" not in output


def test_db_status_uninitialized_is_nonzero_read_only_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "sentinel-secret.sqlite3"
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", f"sqlite+pysqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    try:
        result = runner.invoke(app, ["db", "status", "--json"])
        text_result = runner.invoke(app, ["db", "status"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert payload["reachable"] is False
        assert payload["revision"] is None
        assert payload["revision_current"] is False
        assert payload["present_table_count"] == 0
        assert len(payload["missing_tables"]) == payload["required_table_count"] == 10
        assert payload["reason"] == "database file does not exist"
        assert "sentinel-secret" not in result.output
        assert "Traceback" not in result.output
        assert text_result.exit_code == 1
        assert "Database not ready: database file does not exist" in text_result.output
        assert "run `media-sync db init`" in text_result.output
        assert "sentinel-secret" not in text_result.output
        assert "Traceback" not in text_result.output
        assert not database_path.exists()
    finally:
        get_settings.cache_clear()


def test_db_status_rejects_non_current_revision_without_echoing_it(
    initialized_cli_database: str,
) -> None:
    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            session.execute(text("UPDATE alembic_version SET version_num = 'sentinel-secret-revision'"))
    finally:
        database.dispose()

    result = runner.invoke(app, ["db", "status", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["reachable"] is True
    assert payload["revision"] is None
    assert payload["revision_current"] is False
    assert payload["reason"] == "database schema revision is not current"
    assert "sentinel-secret" not in result.output
    assert "Traceback" not in result.output


def test_db_status_rejects_incomplete_required_table_set(
    initialized_cli_database: str,
) -> None:
    database = Database(initialized_cli_database)
    try:
        with database.engine.begin() as connection:
            connection.execute(text("DROP TABLE export_records"))
    finally:
        database.dispose()

    result = runner.invoke(app, ["db", "status", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["reachable"] is True
    assert payload["revision_current"] is True
    assert payload["present_table_count"] == 9
    assert payload["missing_tables"] == ["export_records"]
    assert payload["reason"] == "database schema is incomplete"
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("platform", "login_method"),
    [
        ("not-a-platform", "cookie"),
        ("bili", "not-a-login-method"),
    ],
)
def test_account_add_rejects_invalid_enum_without_traceback(
    platform: str,
    login_method: str,
) -> None:
    result = runner.invoke(
        app,
        [
            "account",
            "add",
            "--platform",
            platform,
            "--display-name",
            "Invalid Enum Account",
            "--login-method",
            login_method,
        ],
    )

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert "Traceback" not in result.output


def test_account_add_rejects_login_method_not_supported_by_fake_adapter(
    initialized_cli_database: str,
) -> None:
    result = runner.invoke(
        app,
        [
            "account",
            "add",
            "--platform",
            "bili",
            "--display-name",
            "Unsupported Login Account",
            "--login-method",
            "phone",
        ],
    )

    assert result.exit_code == 2
    assert "selected login method is not supported by the fake adapter" in result.output
    assert "Traceback" not in result.output
    assert _row_count(initialized_cli_database, Account) == 0


@pytest.mark.parametrize(
    "credential_ref",
    [
        "env:MEDIA_SYNC_COOKIE",
        "keyring:media-sync/test",
        "file:credentials/bili-cookie",
    ],
)
def test_account_add_accepts_opaque_credential_references(
    initialized_cli_database: str,
    credential_ref: str,
) -> None:
    result = runner.invoke(
        app,
        [
            "account",
            "add",
            "--platform",
            "bili",
            "--display-name",
            "Opaque Credential Account",
            "--credential-ref",
            credential_ref,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert credential_ref not in result.output
    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            account = session.scalar(select(Account))
            assert account is not None
            assert account.credential_ref == credential_ref
    finally:
        database.dispose()


def test_account_add_rejects_inline_credential_without_printing_or_persisting_it(
    initialized_cli_database: str,
) -> None:
    result = runner.invoke(
        app,
        [
            "account",
            "add",
            "--platform",
            "bili",
            "--display-name",
            "Rejected Credential Account",
            "--credential-ref",
            "sessionid=sentinel-secret",
        ],
    )

    assert result.exit_code == 2
    assert "credential_ref must not contain inline credential data" in result.output
    assert "sentinel-secret" not in result.output
    assert "Traceback" not in result.output
    assert _row_count(initialized_cli_database, Account) == 0
    assert _row_count(initialized_cli_database, LoginSession) == 0


def test_account_add_redacts_domain_error_message(
    initialized_cli_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_create(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise DomainError("fixture_rejected", "sentinel-secret domain detail")

    monkeypatch.setattr(cli_module.AccountRepository, "create", reject_create)
    result = runner.invoke(
        app,
        [
            "account",
            "add",
            "--platform",
            "bili",
            "--display-name",
            "Rejected Domain Account",
        ],
    )

    assert result.exit_code == 2
    assert "fixture_rejected: domain operation rejected" in result.output
    assert "sentinel-secret" not in result.output
    assert "Traceback" not in result.output
    assert _row_count(initialized_cli_database, Account) == 0
