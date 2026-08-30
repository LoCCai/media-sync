import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import func, inspect, select, text
from typer.testing import CliRunner

import media_sync.interfaces.cli as cli_module
from media_sync import __version__
from media_sync.config import Settings, get_settings
from media_sync.domain import DomainError, Platform
from media_sync.infrastructure.db import (
    Account,
    Asset,
    Author,
    Content,
    Database,
    Job,
    LoginSession,
    Subscription,
    SyncRun,
)
from media_sync.integrations.mediacrawler.policies import normalize_creator_reference
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


def _create_fake_subscription(
    *,
    login_method: str = "cookie",
    creator_remote_id: str = "creator-001",
) -> tuple[str, str]:
    account_arguments = [
        "account",
        "add",
        "--platform",
        "bili",
        "--display-name",
        "Scheduler fixture account",
        "--login-method",
        login_method,
    ]
    account_arguments.extend(["--credential-ref", "env:MEDIA_SYNC_SCHEDULER_SENTINEL"])
    account_arguments.append("--json")
    account_result = runner.invoke(app, account_arguments)
    assert account_result.exit_code == 0, account_result.output
    account_id = json.loads(account_result.output)["id"]

    subscription_result = runner.invoke(
        app,
        [
            "subscription",
            "add",
            "--account-id",
            account_id,
            "--platform",
            "bili",
            "--creator-remote-id",
            creator_remote_id,
            "--display-name",
            "Scheduler fixture creator",
            "--json",
        ],
    )
    assert subscription_result.exit_code == 0, subscription_result.output
    return account_id, json.loads(subscription_result.output)["id"]


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
    assert report["requirements"]["asset_download"]["ffprobe_required_for"] == ["video", "audio"]
    assert list(tmp_path.iterdir()) == []


def test_doctor_and_asset_download_help_state_ffprobe_requirement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module.shutil, "which", lambda _name: None)

    doctor_result = runner.invoke(app, ["doctor"])
    help_result = runner.invoke(app, ["asset", "download", "--help"])

    assert doctor_result.exit_code == 0, doctor_result.output
    assert "video/audio asset download prerequisite: ffprobe is required (NOT READY)" in doctor_result.output
    assert help_result.exit_code == 0, help_result.output
    assert "ffprobe is required" in help_result.output


def test_mediacrawler_doctor_requires_explicit_license_without_writes(tmp_path: Path) -> None:
    settings = Settings(
        state_dir=tmp_path / "state",
        mediacrawler_lock_path=tmp_path / "missing-lock.json",
        _env_file=None,
    )

    report = cli_module.collect_mediacrawler_doctor_report(
        settings,
        license_acknowledged=False,
    )

    assert report["ok"] is False
    assert report["code"] == "license_acknowledgement_required"
    assert report["live_qualification"] == "NOT_RUN"
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_mediacrawler_doctor_ready_report_is_fixed_and_path_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_path = tmp_path / "sentinel-private" / "python.exe"
    settings = Settings(
        mediacrawler_lock_path=tmp_path / "sentinel-lock.json",
        mediacrawler_python_executable=sentinel_path,
        _env_file=None,
    )
    monkeypatch.setattr(
        cli_module,
        "verify_mediacrawler_checkout",
        lambda lock_path, *, license_acknowledged: SimpleNamespace(commit="a" * 40),
    )
    monkeypatch.setattr(
        cli_module,
        "verify_mediacrawler_python",
        lambda python_executable: SimpleNamespace(executable=python_executable),
    )
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    result = runner.invoke(app, ["mediacrawler", "doctor", "--accept-license", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["code"] == "ready"
    assert payload["upstream_sha"] == "a" * 40
    assert payload["runtime_ready"] is True
    assert payload["live_qualification"] == "NOT_RUN"
    assert "sentinel-private" not in result.output
    assert "sentinel-lock" not in result.output


@pytest.mark.parametrize("platform", ["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"])
def test_mediacrawler_dry_run_wires_all_platforms_without_spawn_or_secret_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
) -> None:
    settings = Settings(
        mediacrawler_lock_path=tmp_path / "lock.json",
        mediacrawler_python_executable=tmp_path / "python.exe",
        _env_file=None,
    )
    captured: list[object] = []
    temporary_roots: list[Path] = []

    class _FakeBridge:
        def prepare(self, request: object) -> object:
            captured.append(request)
            temporary_roots.append(request.integration_root)  # type: ignore[attr-defined]
            return SimpleNamespace(manifest=SimpleNamespace(upstream_sha="b" * 40))

    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    monkeypatch.setattr(cli_module, "MediaCrawlerBridge", _FakeBridge)

    result = runner.invoke(
        app,
        [
            "mediacrawler",
            "dry-run",
            "--platform",
            platform,
            "--creator-id",
            f"stable-{platform}-creator",
            "--accept-license",
            "--allow-full-history",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["platform"] == platform
    assert payload["spawned"] is False
    assert payload["command_shape"] == [
        "<verified-python>",
        "-I",
        "-u",
        "-B",
        "<isolated-runner>",
        "--manifest",
        "<unique-job-manifest>",
    ]
    assert payload["live_qualification"] == "NOT_RUN"
    assert captured
    assert all(not root.exists() for root in temporary_roots)
    assert f"stable-{platform}-creator" not in result.output


def test_mediacrawler_dry_run_rejects_signed_creator_url_without_echoing_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "sentinel-xsec-token"
    settings = Settings(
        mediacrawler_python_executable=tmp_path / "python.exe",
        _env_file=None,
    )
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    result = runner.invoke(
        app,
        [
            "mediacrawler",
            "dry-run",
            "--platform",
            "xhs",
            "--creator-id",
            f"https://example.test/creator?xsec_token={sentinel}",
        ],
    )

    assert result.exit_code == 2
    assert "stable non-secret ID" in result.output
    assert sentinel not in result.output


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
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version")) == "0005_asset_refresh_sources"
                )
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
        "revision": "0005_asset_refresh_sources",
        "expected_revision": "0005_asset_refresh_sources",
        "revision_current": True,
        "required_table_count": 12,
        "present_table_count": 12,
        "missing_tables": [],
        "reason": None,
    }
    assert text_result.exit_code == 0
    assert "Database ready:" in text_result.output
    assert "revision=0005_asset_refresh_sources" in text_result.output
    assert "tables=12/12" in text_result.output
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
        assert len(payload["missing_tables"]) == payload["required_table_count"] == 12
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
    assert payload["present_table_count"] == 11
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
    ("login_method", "credential_arguments"),
    [
        ("qr", []),
        ("saved_session", []),
        ("cookie", ["--credential-ref", "env:MEDIA_SYNC_TEST_COOKIE"]),
    ],
)
def test_account_add_accepts_only_qualified_mediacrawler_login_configuration(
    initialized_cli_database: str,
    login_method: str,
    credential_arguments: list[str],
) -> None:
    result = runner.invoke(
        app,
        [
            "account",
            "add",
            "--platform",
            "xhs",
            "--display-name",
            f"MediaCrawler {login_method}",
            "--adapter",
            "mediacrawler",
            "--login-method",
            login_method,
            *credential_arguments,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["adapter"] == "mediacrawler"
    assert "MEDIA_SYNC_TEST_COOKIE" not in result.output


@pytest.mark.parametrize(
    ("login_method", "credential_arguments", "message"),
    [
        ("phone", [], "support only QR"),
        ("cookie", [], "requires credential_ref"),
        ("qr", ["--credential-ref", "env:MEDIA_SYNC_TEST_COOKIE"], "allowed only"),
    ],
)
def test_account_add_rejects_unsafe_mediacrawler_login_configuration_before_insert(
    initialized_cli_database: str,
    login_method: str,
    credential_arguments: list[str],
    message: str,
) -> None:
    result = runner.invoke(
        app,
        [
            "account",
            "add",
            "--platform",
            "xhs",
            "--display-name",
            "Rejected MediaCrawler",
            "--adapter",
            "mediacrawler",
            "--login-method",
            login_method,
            *credential_arguments,
        ],
    )

    assert result.exit_code == 2
    assert message in result.output
    assert "MEDIA_SYNC_TEST_COOKIE" not in result.output
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


def test_mediacrawler_subscription_stores_only_secret_creator_reference_locator(
    initialized_cli_database: str,
) -> None:
    account_result = runner.invoke(
        app,
        [
            "account",
            "add",
            "--platform",
            "xhs",
            "--display-name",
            "MediaCrawler subscription account",
            "--adapter",
            "mediacrawler",
            "--login-method",
            "qr",
            "--json",
        ],
    )
    assert account_result.exit_code == 0, account_result.output
    account_id = json.loads(account_result.output)["id"]

    subscription_result = runner.invoke(
        app,
        [
            "subscription",
            "add",
            "--account-id",
            account_id,
            "--platform",
            "xhs",
            "--creator-remote-id",
            "stable-author-001",
            "--display-name",
            "Fixture Author",
            "--creator-reference-ref",
            "env:MEDIA_SYNC_XHS_CREATOR_URL",
            "--json",
        ],
    )

    assert subscription_result.exit_code == 0, subscription_result.output
    assert "MEDIA_SYNC_XHS_CREATOR_URL" not in subscription_result.output
    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            subscription = session.scalar(select(Subscription))
            assert subscription is not None
            assert subscription.policy == {
                "mediacrawler": {
                    "schema_version": 1,
                    "allow_full_history": False,
                    "request_delay_seconds": 5.0,
                    "headless": True,
                    "creator_input": {"secret_ref": "env:MEDIA_SYNC_XHS_CREATOR_URL"},
                }
            }
    finally:
        database.dispose()


@pytest.mark.parametrize(
    ("platform", "remote_id"),
    [
        (Platform.BILI, "stable-author-001"),
        (Platform.TIEBA, "stable-tieba-author"),
        (Platform.ZHIHU, "stable-zhihu-author"),
    ],
)
def test_mediacrawler_creator_fingerprint_is_derived_from_stable_author_id(
    tmp_path: Path,
    platform: Platform,
    remote_id: str,
) -> None:
    settings = Settings(secret_file_dir=tmp_path / "secrets", _env_file=None)

    fingerprint = cli_module._expected_mediacrawler_creator_fingerprint(
        settings,
        platform=platform,
        creator_remote_id=remote_id,
        policy={},
    )

    expected_reference = normalize_creator_reference(platform, remote_id)
    assert fingerprint == hashlib.sha256(expected_reference.encode("utf-8")).hexdigest()


def test_mediacrawler_creator_fingerprint_resolves_secret_reference_only_in_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_reference = "https://www.xiaohongshu.com/user/profile/author?xsec_token=sentinel-secret"
    monkeypatch.setenv("MEDIA_SYNC_TEST_CREATOR_REFERENCE", secret_reference)
    settings = Settings(secret_file_dir=tmp_path / "secrets", _env_file=None)

    fingerprint = cli_module._expected_mediacrawler_creator_fingerprint(
        settings,
        platform=Platform.XHS,
        creator_remote_id="stable-author-001",
        policy={
            "mediacrawler": {
                "creator_input": {"secret_ref": "env:MEDIA_SYNC_TEST_CREATOR_REFERENCE"},
            }
        },
    )

    assert fingerprint == hashlib.sha256(secret_reference.encode("utf-8")).hexdigest()


def test_mediacrawler_subscription_rejects_signed_url_as_persisted_creator_id(
    initialized_cli_database: str,
) -> None:
    account_result = runner.invoke(
        app,
        [
            "account",
            "add",
            "--platform",
            "xhs",
            "--display-name",
            "Signed URL rejection account",
            "--adapter",
            "mediacrawler",
            "--login-method",
            "qr",
            "--json",
        ],
    )
    account_id = json.loads(account_result.output)["id"]
    sentinel = "sentinel-xsec-token"

    result = runner.invoke(
        app,
        [
            "subscription",
            "add",
            "--account-id",
            account_id,
            "--platform",
            "xhs",
            "--creator-remote-id",
            f"https://www.xiaohongshu.com/user/profile/author?xsec_token={sentinel}",
            "--display-name",
            "Rejected",
        ],
    )

    assert result.exit_code == 2
    assert "must be a stable ID" in result.output
    assert sentinel not in result.output
    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            assert session.scalar(select(Subscription)) is None
    finally:
        database.dispose()


def test_scheduler_controls_are_bounded_and_redact_every_output_sink(
    initialized_cli_database: str,
) -> None:
    raw_error_sentinel = "sentinel-raw-scheduler-error"
    payload_sentinel = "sentinel-private-job-payload"
    creator_sentinel = "sentinel-private-creator"
    account_id, subscription_id = _create_fake_subscription(
        login_method="qr",
        creator_remote_id=creator_sentinel,
    )
    outputs: list[str] = []

    paused = runner.invoke(
        app,
        ["subscription", "pause", "--subscription-id", subscription_id, "--json"],
    )
    assert paused.exit_code == 0, paused.output
    outputs.append(paused.output)
    paused_payload = json.loads(paused.output)
    assert paused_payload["status"] == "paused"
    assert set(paused_payload) == {
        "subscription_id",
        "status",
        "interval_seconds",
        "next_run_at",
        "last_run_at",
        "last_success_at",
        "schedule_revision",
        "consecutive_failures",
    }
    paused_text = runner.invoke(app, ["subscription", "pause", "--subscription-id", subscription_id])
    assert paused_text.exit_code == 0, paused_text.output
    outputs.append(paused_text.output)

    run_now = runner.invoke(
        app,
        ["subscription", "run-now", "--subscription-id", subscription_id, "--json"],
    )
    assert run_now.exit_code == 0, run_now.output
    outputs.append(run_now.output)
    assert json.loads(run_now.output)["status"] == "paused"
    paused_tick = runner.invoke(app, ["scheduler", "tick", "--limit", "5", "--json"])
    assert paused_tick.exit_code == 0, paused_tick.output
    outputs.append(paused_tick.output)
    assert json.loads(paused_tick.output) == {"materialized_count": 0, "cycles": []}
    paused_tick_text = runner.invoke(app, ["scheduler", "tick", "--limit", "5"])
    assert paused_tick_text.exit_code == 0, paused_tick_text.output
    outputs.append(paused_tick_text.output)

    resumed = runner.invoke(
        app,
        ["subscription", "resume", "--subscription-id", subscription_id, "--json"],
    )
    assert resumed.exit_code == 0, resumed.output
    outputs.append(resumed.output)
    assert json.loads(resumed.output)["status"] == "enabled"

    tick = runner.invoke(app, ["scheduler", "tick", "--limit", "5", "--json"])
    assert tick.exit_code == 0, tick.output
    outputs.append(tick.output)
    tick_payload = json.loads(tick.output)
    assert tick_payload["materialized_count"] == 1
    assert set(tick_payload["cycles"][0]) == {
        "job_id",
        "subscription_id",
        "schedule_revision",
        "scheduled_for",
    }
    job_id = tick_payload["cycles"][0]["job_id"]

    worker = runner.invoke(
        app,
        [
            "scheduler",
            "run",
            "--max-jobs",
            "5",
            "--global-capacity",
            "2",
            "--lease-seconds",
            "30",
            "--scan-limit",
            "10",
            "--json",
        ],
    )
    assert worker.exit_code == 0, worker.output
    outputs.append(worker.output)
    worker_payload = json.loads(worker.output)
    assert len(worker_payload) == 1
    assert worker_payload[0]["status"] == "waiting_user"
    assert set(worker_payload[0]) == {"job_id", "subscription_id", "status", "attempt", "run_id"}
    idle_text = runner.invoke(app, ["scheduler", "run", "--max-jobs", "1"])
    assert idle_text.exit_code == 0, idle_text.output
    outputs.append(idle_text.output)

    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            job = session.get(Job, job_id)
            assert job is not None
            job.last_error_message = raw_error_sentinel
            job.payload = {**job.payload, "private": payload_sentinel}
    finally:
        database.dispose()

    listed = runner.invoke(
        app,
        ["scheduler", "job", "list", "--subscription-id", subscription_id, "--json"],
    )
    listed_text = runner.invoke(app, ["scheduler", "job", "list", "--status", "waiting_user"])
    assert listed.exit_code == listed_text.exit_code == 0
    outputs.extend([listed.output, listed_text.output])
    jobs = json.loads(listed.output)
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == job_id
    assert jobs[0]["account_id"] == account_id
    assert set(jobs[0]) == {
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
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
    }

    resumed_job = runner.invoke(app, ["scheduler", "job", "resume", "--job-id", job_id, "--json"])
    cancelled_job = runner.invoke(app, ["scheduler", "job", "cancel", "--job-id", job_id, "--json"])
    assert resumed_job.exit_code == cancelled_job.exit_code == 0
    outputs.extend([resumed_job.output, cancelled_job.output])
    assert json.loads(resumed_job.output)["status"] == "queued"
    assert json.loads(cancelled_job.output)["status"] == "cancelled"

    retained_output = "\n".join(outputs)
    for sentinel in (
        raw_error_sentinel,
        payload_sentinel,
        creator_sentinel,
        "MEDIA_SYNC_SCHEDULER_SENTINEL",
        "lease_token",
        "lease_owner",
        "credential_ref",
        "creator_reference",
        "cursor",
        "locator",
    ):
        assert sentinel not in retained_output
    assert initialized_cli_database not in retained_output
    assert "cli.sqlite3" not in retained_output


def test_scheduler_mediacrawler_enablement_and_license_are_explicit(
    initialized_cli_database: str,
) -> None:
    acknowledgement_without_enablement = runner.invoke(
        app,
        ["scheduler", "run", "--accept-mediacrawler-license"],
    )
    assert acknowledgement_without_enablement.exit_code == 2
    assert "--enable-mediacrawler" in acknowledgement_without_enablement.output

    account = runner.invoke(
        app,
        [
            "account",
            "add",
            "--platform",
            "xhs",
            "--adapter",
            "mediacrawler",
            "--display-name",
            "Default-off MediaCrawler account",
            "--login-method",
            "saved_session",
            "--json",
        ],
    )
    assert account.exit_code == 0, account.output
    account_id = json.loads(account.output)["id"]
    subscription = runner.invoke(
        app,
        [
            "subscription",
            "add",
            "--account-id",
            account_id,
            "--platform",
            "xhs",
            "--creator-remote-id",
            "creator-default-off",
            "--display-name",
            "Default-off creator",
            "--json",
        ],
    )
    assert subscription.exit_code == 0, subscription.output
    tick = runner.invoke(app, ["scheduler", "tick", "--json"])
    assert tick.exit_code == 0, tick.output
    assert json.loads(tick.output)["materialized_count"] == 1

    runtime_root = get_settings().resolved_mediacrawler_runtime_dir
    assert not runtime_root.exists()
    default_off = runner.invoke(app, ["scheduler", "run", "--json"])
    assert default_off.exit_code == 0, default_off.output
    assert json.loads(default_off.output) == []
    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            untouched = session.scalar(select(Job))
            untouched_subscription = session.scalar(select(Subscription))
            assert untouched is not None and (untouched.status, untouched.attempts) == ("queued", 0)
            assert untouched_subscription is not None and untouched_subscription.consecutive_failures == 0
    finally:
        database.dispose()

    worker = runner.invoke(
        app,
        ["scheduler", "run", "--enable-mediacrawler", "--json"],
    )
    assert worker.exit_code == 0, worker.output
    result = json.loads(worker.output)
    assert len(result) == 1
    assert result[0]["status"] == "waiting_user"
    assert result[0]["run_id"] is None
    assert "license_acknowledgement_required" not in worker.output
    assert not runtime_root.exists()

    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            job = session.scalar(select(Job))
            assert job is not None
            assert job.last_error_code == "license_acknowledgement_required"
            assert session.scalar(select(func.count()).select_from(SyncRun)) == 0
    finally:
        database.dispose()


def test_scheduler_lane_controls_enforce_policy_bounds_and_revision_cas(
    initialized_cli_database: str,
) -> None:
    account_id, _subscription_id = _create_fake_subscription()
    create = runner.invoke(
        app,
        [
            "scheduler",
            "lane",
            "set",
            "--scope",
            "platform",
            "--platform",
            "bili",
            "--max-concurrency",
            "2",
            "--min-start-interval-seconds",
            "0",
            "--failure-threshold",
            "4",
            "--cooldown-seconds",
            "60",
            "--expected-revision",
            "0",
            "--json",
        ],
    )
    assert create.exit_code == 0, create.output
    created = json.loads(create.output)
    assert created["scope"] == "platform"
    assert created["revision"] == 1
    assert created["max_concurrency"] == 2
    assert "MEDIA_SYNC_SCHEDULER_SENTINEL" not in create.output

    stale = runner.invoke(
        app,
        [
            "scheduler",
            "lane",
            "set",
            "--scope",
            "platform",
            "--platform",
            "bili",
            "--expected-revision",
            "0",
        ],
    )
    assert stale.exit_code == 2
    assert "revision conflict" in stale.output
    assert "Traceback" not in stale.output

    account_lane = runner.invoke(
        app,
        [
            "scheduler",
            "lane",
            "set",
            "--scope",
            "account",
            "--platform",
            "bili",
            "--account-id",
            account_id,
            "--json",
        ],
    )
    assert account_lane.exit_code == 0, account_lane.output
    assert json.loads(account_lane.output)["account_id"] == account_id

    listed = runner.invoke(
        app,
        ["scheduler", "lane", "list", "--scope", "platform", "--platform", "bili", "--json"],
    )
    assert listed.exit_code == 0, listed.output
    lanes = json.loads(listed.output)
    assert len(lanes) == 1
    assert set(lanes[0]) == {
        "lane_id",
        "scope",
        "platform",
        "account_id",
        "max_concurrency",
        "min_start_interval_seconds",
        "failure_threshold",
        "cooldown_seconds",
        "next_start_at",
        "consecutive_failures",
        "circuit_state",
        "circuit_open_until",
        "half_open_job_id",
        "revision",
        "created_at",
        "updated_at",
    }
    listed_text = runner.invoke(app, ["scheduler", "lane", "list", "--platform", "bili"])
    assert listed_text.exit_code == 0, listed_text.output
    assert "MEDIA_SYNC_SCHEDULER_SENTINEL" not in listed_text.output
    assert "cli.sqlite3" not in listed_text.output

    reset = runner.invoke(
        app,
        [
            "scheduler",
            "lane",
            "reset",
            "--scope",
            "platform",
            "--platform",
            "bili",
            "--expected-revision",
            "1",
            "--json",
        ],
    )
    assert reset.exit_code == 0, reset.output
    assert json.loads(reset.output)["revision"] == 2
    assert json.loads(reset.output)["circuit_state"] == "closed"

    missing_account = runner.invoke(
        app,
        ["scheduler", "lane", "set", "--scope", "account", "--platform", "bili"],
    )
    invalid_bound = runner.invoke(
        app,
        [
            "scheduler",
            "lane",
            "set",
            "--scope",
            "platform",
            "--platform",
            "bili",
            "--max-concurrency",
            "0",
        ],
    )
    assert missing_account.exit_code == invalid_bound.exit_code == 2
    assert "Traceback" not in missing_account.output
    assert "Traceback" not in invalid_bound.output


@pytest.mark.parametrize(
    "arguments",
    [
        ["scheduler", "tick", "--limit", "0"],
        ["scheduler", "tick", "--limit", "1001"],
        ["scheduler", "run", "--max-jobs", "0"],
        ["scheduler", "run", "--global-capacity", "1001"],
        ["scheduler", "run", "--lease-seconds", "86401"],
        ["scheduler", "run", "--scan-limit", "0"],
        ["scheduler", "lane", "set", "--scope", "platform", "--platform", "bili", "--max-concurrency", "0"],
        [
            "scheduler",
            "lane",
            "set",
            "--scope",
            "platform",
            "--platform",
            "bili",
            "--min-start-interval-seconds",
            "604801",
        ],
        [
            "scheduler",
            "lane",
            "set",
            "--scope",
            "platform",
            "--platform",
            "bili",
            "--failure-threshold",
            "0",
        ],
        ["scheduler", "lane", "set", "--scope", "platform", "--platform", "bili", "--cooldown-seconds", "0"],
    ],
)
def test_scheduler_cli_rejects_out_of_bounds_controls(arguments: list[str]) -> None:
    result = runner.invoke(app, arguments)

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert "Traceback" not in result.output


def test_asset_list_filters_by_author_and_status_with_stable_redacted_output(
    initialized_cli_database: str,
) -> None:
    sentinel = "sentinel-signed-source-token"
    first_author_id = "00000000-0000-0000-0000-000000000001"
    second_author_id = "00000000-0000-0000-0000-000000000002"
    first_content_id = "00000000-0000-0000-0000-000000000011"
    second_content_id = "00000000-0000-0000-0000-000000000012"
    video_asset_id = "00000000-0000-0000-0000-000000000021"
    cover_asset_id = "00000000-0000-0000-0000-000000000022"
    other_asset_id = "00000000-0000-0000-0000-000000000023"
    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            session.add_all(
                [
                    Author(
                        id=first_author_id,
                        platform="bili",
                        remote_id="author-one",
                        display_name="Author One",
                    ),
                    Author(
                        id=second_author_id,
                        platform="bili",
                        remote_id="author-two",
                        display_name="Author Two",
                    ),
                    Content(
                        id=first_content_id,
                        author_id=first_author_id,
                        platform="bili",
                        remote_type="video",
                        remote_id="content-one",
                        kind="video",
                    ),
                    Content(
                        id=second_content_id,
                        author_id=second_author_id,
                        platform="bili",
                        remote_type="video",
                        remote_id="content-two",
                        kind="video",
                    ),
                    Asset(
                        id=video_asset_id,
                        content_id=first_content_id,
                        platform="bili",
                        kind="video",
                        position=0,
                        source_url=f"https://media.invalid/video?token={sentinel}",
                        locator={"type": "direct", "url": f"https://media.invalid/video?token={sentinel}"},
                        semantic_fingerprint="1" * 64,
                        locator_fingerprint="2" * 64,
                        status="discovered",
                        raw={"credential": sentinel},
                        last_error_message=sentinel,
                    ),
                    Asset(
                        id=cover_asset_id,
                        content_id=first_content_id,
                        platform="bili",
                        kind="cover",
                        position=0,
                        source_url=f"https://media.invalid/cover?token={sentinel}",
                        locator={"type": "direct", "url": f"https://media.invalid/cover?token={sentinel}"},
                        semantic_fingerprint="3" * 64,
                        locator_fingerprint="4" * 64,
                        status="verified",
                        mime_type="image/jpeg",
                        size_bytes=42,
                        checksum_sha256="5" * 64,
                        local_path=f"C:/private/{sentinel}/cover.jpg",
                        verified_at=datetime(2026, 1, 1, tzinfo=UTC),
                    ),
                    Asset(
                        id=other_asset_id,
                        content_id=second_content_id,
                        platform="bili",
                        kind="video",
                        position=0,
                        source_url=f"https://media.invalid/other?token={sentinel}",
                        locator={"type": "direct", "url": f"https://media.invalid/other?token={sentinel}"},
                        semantic_fingerprint="6" * 64,
                        locator_fingerprint="7" * 64,
                        status="discovered",
                    ),
                ]
            )
    finally:
        database.dispose()

    filtered = runner.invoke(
        app,
        [
            "asset",
            "list",
            "--author-id",
            first_author_id,
            "--status",
            "discovered",
            "--json",
        ],
    )
    unfiltered = runner.invoke(app, ["asset", "list", "--json"])

    assert filtered.exit_code == 0, filtered.output
    assert json.loads(filtered.output) == [
        {
            "id": video_asset_id,
            "author_id": first_author_id,
            "content_id": first_content_id,
            "platform": "bili",
            "kind": "video",
            "position": 0,
            "generation": 1,
            "status": "discovered",
            "mime_type": None,
            "size_bytes": None,
            "verified_at": None,
        }
    ]
    assert unfiltered.exit_code == 0, unfiltered.output
    assert [record["id"] for record in json.loads(unfiltered.output)] == [
        cover_asset_id,
        video_asset_id,
        other_asset_id,
    ]
    for output in (filtered.output, unfiltered.output):
        assert sentinel not in output
        assert "source_url" not in output
        assert "locator" not in output
        assert "local_path" not in output
        assert "last_error_message" not in output


def test_asset_download_without_ffprobe_fails_before_database_or_job_work(
    initialized_cli_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_id = UUID("00000000-0000-0000-0000-000000000031")
    author_id = "00000000-0000-0000-0000-000000000032"
    content_id = "00000000-0000-0000-0000-000000000033"
    service_calls: list[object] = []
    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            session.add_all(
                [
                    Author(
                        id=author_id,
                        platform="bili",
                        remote_id="probe-author",
                        display_name="Probe Author",
                    ),
                    Content(
                        id=content_id,
                        author_id=author_id,
                        platform="bili",
                        remote_type="video",
                        remote_id="probe-content",
                        kind="video",
                    ),
                    Asset(
                        id=str(asset_id),
                        content_id=content_id,
                        platform="bili",
                        kind="video",
                        position=0,
                        locator={"type": "direct", "url": "https://media.invalid/video"},
                        semantic_fingerprint="8" * 64,
                        locator_fingerprint="9" * 64,
                        status="discovered",
                    ),
                ]
            )
    finally:
        database.dispose()

    def unexpected_service(*args: object, **kwargs: object) -> None:
        service_calls.append((args, kwargs))
        raise AssertionError("download service must not start without the required probe")

    monkeypatch.setattr(cli_module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(cli_module, "AssetDownloadService", unexpected_service)

    result = runner.invoke(app, ["asset", "download", "--asset-id", str(asset_id), "--json"])

    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "asset_id": str(asset_id),
        "status": "blocked",
        "disposition": "not_started",
        "persisted_status": "discovered",
        "error_code": "media_probe_unavailable",
        "retryable": True,
    }
    assert service_calls == []
    assert "Traceback" not in result.output
    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            asset = session.get(Asset, str(asset_id))
            assert asset is not None
            assert asset.status == "discovered"
            assert session.scalar(select(func.count()).select_from(Job)) == 0
    finally:
        database.dispose()


def test_asset_download_without_ffprobe_allows_image_magic_validation(
    initialized_cli_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_id = UUID("00000000-0000-0000-0000-000000000034")
    author_id = "00000000-0000-0000-0000-000000000035"
    content_id = "00000000-0000-0000-0000-000000000036"
    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            session.add_all(
                [
                    Author(
                        id=author_id,
                        platform="bili",
                        remote_id="image-author",
                        display_name="Image Author",
                    ),
                    Content(
                        id=content_id,
                        author_id=author_id,
                        platform="bili",
                        remote_type="dynamic",
                        remote_id="image-content",
                        kind="image",
                    ),
                    Asset(
                        id=str(asset_id),
                        content_id=content_id,
                        platform="bili",
                        kind="image",
                        position=0,
                        locator={"type": "direct", "url": "https://media.invalid/image"},
                        semantic_fingerprint="a" * 64,
                        locator_fingerprint="b" * 64,
                        status="discovered",
                    ),
                ]
            )
    finally:
        database.dispose()

    captured: dict[str, object] = {}

    class _FakeDownloader:
        def __init__(self, client: object, *, probe: object, limits: object) -> None:
            captured.update(client=client, probe=probe, limits=limits)

    class _FakeService:
        def __init__(self, database: object, downloader: object) -> None:
            captured.update(database=database, downloader=downloader)

        def run(self, request: object) -> object:
            captured["request"] = request
            return SimpleNamespace(
                asset_id=asset_id,
                generation=1,
                job_id=None,
                status=cli_module.AssetStatus.VERIFIED,
                disposition="downloaded",
                archive_path=Path("archive/image.jpg"),
                checksum_sha256="c" * 64,
                size_bytes=42,
                mime_type="image/jpeg",
            )

    monkeypatch.setattr(cli_module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(cli_module, "SecureMediaDownloader", _FakeDownloader)
    monkeypatch.setattr(cli_module, "AssetDownloadService", _FakeService)

    result = runner.invoke(app, ["asset", "download", "--asset-id", str(asset_id), "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "verified"
    assert captured["probe"] is None


def test_asset_download_adapter_refresh_preflight_has_zero_sqlite_state_change(
    initialized_cli_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_id = UUID("00000000-0000-0000-0000-000000000037")
    author_id = "00000000-0000-0000-0000-000000000038"
    content_id = "00000000-0000-0000-0000-000000000039"
    sentinel = "sentinel-private-refresh-key"
    service_calls: list[object] = []
    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            session.add_all(
                [
                    Author(
                        id=author_id,
                        platform="xhs",
                        remote_id="refresh-author",
                        display_name="Refresh Author",
                    ),
                    Content(
                        id=content_id,
                        author_id=author_id,
                        platform="xhs",
                        remote_type="note",
                        remote_id="refresh-content",
                        kind="image",
                    ),
                    Asset(
                        id=str(asset_id),
                        content_id=content_id,
                        platform="xhs",
                        kind="image",
                        position=0,
                        locator={
                            "version": 1,
                            "type": "adapter_refresh",
                            "adapter": "mediacrawler",
                            "asset_key": sentinel,
                        },
                        semantic_fingerprint="d" * 64,
                        locator_fingerprint="e" * 64,
                        status="discovered",
                    ),
                ]
            )
        with database.session() as session:
            before = session.execute(
                select(
                    Asset.status,
                    Asset.generation,
                    Asset.download_job_id,
                    Asset.queued_at,
                    Asset.download_started_at,
                    Asset.last_error_code,
                ).where(Asset.id == str(asset_id))
            ).one()
    finally:
        database.dispose()

    def unexpected_service(*args: object, **kwargs: object) -> None:
        service_calls.append((args, kwargs))
        raise AssertionError("unsupported refresh locator must not enter download orchestration")

    monkeypatch.setattr(cli_module, "AssetDownloadService", unexpected_service)

    result = runner.invoke(app, ["asset", "download", "--asset-id", str(asset_id), "--json"])

    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "asset_id": str(asset_id),
        "status": "blocked",
        "disposition": "not_started",
        "persisted_status": "discovered",
        "error_code": "locator_refresh_unsupported",
        "retryable": True,
    }
    assert sentinel not in result.output
    assert service_calls == []
    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            after = session.execute(
                select(
                    Asset.status,
                    Asset.generation,
                    Asset.download_job_id,
                    Asset.queued_at,
                    Asset.download_started_at,
                    Asset.last_error_code,
                ).where(Asset.id == str(asset_id))
            ).one()
            assert session.scalar(select(func.count()).select_from(Job)) == 0
    finally:
        database.dispose()
    assert after == before
    assert "Traceback" not in result.output

    license_result = runner.invoke(
        app,
        [
            "asset",
            "download",
            "--asset-id",
            str(asset_id),
            "--enable-mediacrawler",
            "--json",
        ],
    )
    assert license_result.exit_code == 1
    assert json.loads(license_result.output)["error_code"] == "license_acknowledgement_required"
    assert service_calls == []


def test_asset_download_explicitly_wires_lazy_mediacrawler_refresh(
    initialized_cli_database: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_id = UUID("00000000-0000-0000-0000-000000000071")
    author_id = "00000000-0000-0000-0000-000000000072"
    content_id = "00000000-0000-0000-0000-000000000073"
    subscription_id = UUID("00000000-0000-0000-0000-000000000074")
    database = Database(initialized_cli_database)
    try:
        with database.session() as session:
            session.add_all(
                [
                    Author(
                        id=author_id,
                        platform="dy",
                        remote_id="refresh-author",
                        display_name="Refresh Author",
                    ),
                    Content(
                        id=content_id,
                        author_id=author_id,
                        platform="dy",
                        remote_type="content",
                        remote_id="refresh-content",
                        kind="image",
                    ),
                    Asset(
                        id=str(asset_id),
                        content_id=content_id,
                        platform="dy",
                        kind="image",
                        position=0,
                        locator={
                            "version": 1,
                            "type": "adapter_refresh",
                            "adapter": "mediacrawler",
                            "asset_key": "stable-refresh-key",
                        },
                        semantic_fingerprint="1" * 64,
                        locator_fingerprint="2" * 64,
                        status="discovered",
                    ),
                ]
            )
    finally:
        database.dispose()

    captured: dict[str, object] = {}

    class _FakeRefresher:
        def __init__(self, database: object, **kwargs: object) -> None:
            captured["refresh_database"] = database
            captured["refresh_kwargs"] = kwargs

    class _FakeDownloader:
        def __init__(
            self,
            client: object,
            *,
            refresher: object,
            probe: object,
            limits: object,
        ) -> None:
            captured.update(client=client, refresher=refresher, probe=probe, limits=limits)

    class _FakeService:
        def __init__(self, database: object, downloader: object) -> None:
            captured.update(database=database, downloader=downloader)

        def run(self, request: object) -> object:
            captured["request"] = request
            return SimpleNamespace(
                asset_id=asset_id,
                generation=1,
                job_id=None,
                status=cli_module.AssetStatus.VERIFIED,
                disposition="downloaded",
                archive_path=Path("archive/image.jpg"),
                checksum_sha256="3" * 64,
                size_bytes=42,
                mime_type="image/jpeg",
            )

    python_executable = tmp_path / "mediacrawler-python"
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_PYTHON_EXECUTABLE", str(python_executable))
    get_settings.cache_clear()
    monkeypatch.setattr(cli_module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(cli_module, "LazyMediaCrawlerLocatorRefresher", _FakeRefresher)
    monkeypatch.setattr(cli_module, "SecureMediaDownloader", _FakeDownloader)
    monkeypatch.setattr(cli_module, "AssetDownloadService", _FakeService)

    result = runner.invoke(
        app,
        [
            "asset",
            "download",
            "--asset-id",
            str(asset_id),
            "--subscription-id",
            str(subscription_id),
            "--enable-mediacrawler",
            "--accept-mediacrawler-license",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "verified"
    assert isinstance(captured["refresher"], _FakeRefresher)
    refresh_kwargs = captured["refresh_kwargs"]
    assert isinstance(refresh_kwargs, dict)
    assert refresh_kwargs["asset_id"] == asset_id
    assert refresh_kwargs["subscription_id"] == subscription_id
    assert refresh_kwargs["python_executable"] == python_executable
    assert refresh_kwargs["license_acknowledged"] is True


@pytest.mark.parametrize(
    ("already_exported", "expected_disposition", "managed_file_count"),
    [
        (False, "exported", 4),
        (True, "already_exported", 0),
    ],
)
def test_emby_export_reports_success_and_idempotent_outcomes(
    initialized_cli_database: str,
    monkeypatch: pytest.MonkeyPatch,
    already_exported: bool,
    expected_disposition: str,
    managed_file_count: int,
) -> None:
    del initialized_cli_database
    author_id = UUID("00000000-0000-0000-0000-000000000041")
    captured: dict[str, object] = {}

    class _FakeExporter:
        def __init__(self, export_root: Path, *, staging_root: Path) -> None:
            captured["export_root"] = export_root
            captured["staging_root"] = staging_root

    class _FakeService:
        def __init__(self, database: object, exporter: object) -> None:
            captured["database"] = database
            captured["exporter"] = exporter

        def export_author(self, request: object) -> object:
            captured["request"] = request
            return SimpleNamespace(
                job_id="00000000-0000-0000-0000-000000000042",
                source_fingerprint="a" * 64,
                output_path="bili/author-safe",
                rendered_fingerprint="b" * 64,
                managed_file_count=managed_file_count,
                already_exported=already_exported,
            )

    monkeypatch.setattr(cli_module, "EmbyExporter", _FakeExporter)
    monkeypatch.setattr(cli_module, "EmbyExportService", _FakeService)

    result = runner.invoke(
        app,
        [
            "emby",
            "export",
            "--author-id",
            str(author_id),
            "--worker-id",
            "fixture-worker",
            "--lease-seconds",
            "120",
            "--max-attempts",
            "3",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {
        "author_id": str(author_id),
        "job_id": "00000000-0000-0000-0000-000000000042",
        "status": "succeeded",
        "disposition": expected_disposition,
        "output_path": "bili/author-safe",
        "source_fingerprint": "a" * 64,
        "rendered_fingerprint": "b" * 64,
        "managed_file_count": managed_file_count,
    }
    request = captured["request"]
    assert request.author_id == str(author_id)  # type: ignore[attr-defined]
    assert request.worker_id == "fixture-worker"  # type: ignore[attr-defined]
    assert request.lease_seconds == 120  # type: ignore[attr-defined]
    assert request.max_attempts == 3  # type: ignore[attr-defined]


def test_emby_export_failure_uses_fixed_code_and_redacts_exception_chain(
    initialized_cli_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del initialized_cli_database
    author_id = UUID("00000000-0000-0000-0000-000000000051")
    sentinel = "sentinel-private-export-detail"

    class _FakeExporter:
        def __init__(self, export_root: Path, *, staging_root: Path) -> None:
            del export_root, staging_root

    class _FailingService:
        def __init__(self, database: object, exporter: object) -> None:
            del database, exporter

        def export_author(self, request: object) -> object:
            del request
            try:
                raise RuntimeError(sentinel)
            except RuntimeError as error:
                raise cli_module.ExportError("publish_failed") from error

    monkeypatch.setattr(cli_module, "EmbyExporter", _FakeExporter)
    monkeypatch.setattr(cli_module, "EmbyExportService", _FailingService)

    result = runner.invoke(
        app,
        ["emby", "export", "--author-id", str(author_id), "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "author_id": str(author_id),
        "status": "failed",
        "error_code": "publish_failed",
        "retryable": True,
    }
    assert sentinel not in result.output
    assert "Traceback" not in result.output


def test_emby_export_database_failure_has_fixed_redacted_code(
    initialized_cli_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del initialized_cli_database
    author_id = UUID("00000000-0000-0000-0000-000000000061")
    sentinel = "sentinel-private-database-detail"

    class _FakeExporter:
        def __init__(self, export_root: Path, *, staging_root: Path) -> None:
            del export_root, staging_root

    class _FailingService:
        def __init__(self, database: object, exporter: object) -> None:
            del database, exporter

        def export_author(self, request: object) -> object:
            del request
            raise cli_module.SQLAlchemyError(sentinel)

    monkeypatch.setattr(cli_module, "EmbyExporter", _FakeExporter)
    monkeypatch.setattr(cli_module, "EmbyExportService", _FailingService)

    result = runner.invoke(
        app,
        ["emby", "export", "--author-id", str(author_id), "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "author_id": str(author_id),
        "status": "failed",
        "error_code": "export_database_failed",
        "retryable": True,
    }
    assert sentinel not in result.output
    assert "Traceback" not in result.output
