import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, inspect, select, text
from typer.testing import CliRunner

import media_sync.interfaces.cli as cli_module
from media_sync import __version__
from media_sync.config import Settings, get_settings
from media_sync.domain import DomainError, Platform
from media_sync.infrastructure.db import Account, Database, LoginSession, Subscription
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
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002_checkpoint"
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
        "revision": "0002_checkpoint",
        "expected_revision": "0002_checkpoint",
        "revision_current": True,
        "required_table_count": 10,
        "present_table_count": 10,
        "missing_tables": [],
        "reason": None,
    }
    assert text_result.exit_code == 0
    assert "Database ready:" in text_result.output
    assert "revision=0002_checkpoint" in text_result.output
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
                "mediacrawler": {"creator_input": {"secret_ref": "env:MEDIA_SYNC_XHS_CREATOR_URL"}}
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
