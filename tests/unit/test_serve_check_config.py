"""Configuration-only serve checks must not initialize application state."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import uvicorn
from pydantic_settings import SettingsError
from typer.testing import CliRunner

import media_sync.interfaces.api as api_module
import media_sync.interfaces.cli as cli_module
from media_sync.config import Settings

_SUCCESS = '{"service":"media-sync-api","configuration":"valid"}'
_AUTH_ERROR = '{"detail":"operator_auth_configuration_invalid"}'
_SETTINGS_ERROR = '{"detail":"service_configuration_invalid"}'
_REFERENCE = "CONFIG_CHECK_PRIVATE_REFERENCE"
_CREDENTIAL = "configuration-check-private-credential-0123456789"
runner = CliRunner()


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "exports",
        job_dir=tmp_path / "jobs",
        _env_file=None,
        **overrides,
    )


def _snapshot(root: Path) -> dict[str, tuple[bytes | None, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes() if path.is_file() else None, path.stat().st_mtime_ns)
        for path in root.rglob("*")
    }


@pytest.fixture
def forbid_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("configuration-only command attempted startup work")

    monkeypatch.setattr(Settings, "ensure_directories", forbidden)
    monkeypatch.setattr(api_module, "create_api_app", forbidden)
    monkeypatch.setattr(api_module, "Database", forbidden)
    monkeypatch.setattr(cli_module, "Database", forbidden)
    monkeypatch.setattr(cli_module, "create_engine", forbidden)
    monkeypatch.setattr(cli_module, "upgrade_database", forbidden)
    monkeypatch.setattr(uvicorn, "run", forbidden)


@pytest.mark.usefixtures("forbid_startup")
@pytest.mark.parametrize("existing_state", [False, True])
def test_check_config_leaves_fresh_and_existing_state_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing_state: bool
) -> None:
    settings = _settings(tmp_path, operator_credential_secret_ref=f"env:{_REFERENCE}")
    if existing_state:
        settings.state_dir.mkdir()
        with sqlite3.connect(settings.state_dir / "media-sync.sqlite3") as connection:
            connection.execute("CREATE TABLE retained (value TEXT)")
            connection.execute("INSERT INTO retained VALUES ('preflight-retained-state')")
    monkeypatch.setenv(_REFERENCE, _CREDENTIAL)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    before = _snapshot(tmp_path)

    result = runner.invoke(cli_module.app, ["serve", "--check-config"])

    assert result.exit_code == 0, result.output
    assert result.output.strip() == _SUCCESS
    assert _snapshot(tmp_path) == before


@pytest.mark.usefixtures("forbid_startup")
@pytest.mark.parametrize("value", [None, "short", "bad\ncredential-01234567890123456789"])
def test_check_config_resolves_and_validates_browser_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(_REFERENCE, raising=False)
    else:
        monkeypatch.setenv(_REFERENCE, value)
    settings = _settings(tmp_path, operator_credential_secret_ref=f"env:{_REFERENCE}")
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    result = runner.invoke(cli_module.app, ["serve", "--check-config"])

    assert result.exit_code == 2
    assert result.output.strip() == _AUTH_ERROR
    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("forbid_startup")
@pytest.mark.parametrize("file_state", ["missing", "unreadable", "invalid_utf8", "valid"])
@pytest.mark.parametrize("existing_state", [False, True])
def test_check_config_file_secret_read_is_safe_and_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, file_state: str, existing_state: bool
) -> None:
    secret_root = tmp_path / "secrets"
    secret_root.mkdir()
    secret_path = secret_root / "private-reference.txt"
    if file_state != "missing":
        secret_path.write_bytes(b"\xff" if file_state == "invalid_utf8" else _CREDENTIAL.encode())
    if file_state == "unreadable":
        original_read_text = Path.read_text

        def deny_secret(path: Path, *args: object, **kwargs: object) -> str:
            if path == secret_path:
                raise PermissionError("private-reference-and-credential-sentinel")
            return original_read_text(path, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "read_text", deny_secret)
    settings = _settings(
        tmp_path, secret_file_dir=secret_root, operator_credential_secret_ref="file:private-reference.txt"
    )
    if existing_state:
        settings.state_dir.mkdir()
        with sqlite3.connect(settings.state_dir / "media-sync.sqlite3") as connection:
            connection.execute("CREATE TABLE retained (value TEXT)")
            connection.execute("INSERT INTO retained VALUES ('preflight-retained-state')")
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    before = _snapshot(tmp_path)

    result = runner.invoke(cli_module.app, ["serve", "--check-config"])

    assert result.exit_code == (0 if file_state == "valid" else 2)
    assert result.output.strip() == (_SUCCESS if file_state == "valid" else _AUTH_ERROR)
    assert _snapshot(tmp_path) == before


@pytest.mark.usefixtures("forbid_startup")
@pytest.mark.parametrize("bearer_value", [None, "short", _CREDENTIAL, "distinct-api-token-01234567890123456789"])
def test_check_config_validates_optional_distinct_bearer_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bearer_value: str | None
) -> None:
    monkeypatch.setenv(_REFERENCE, _CREDENTIAL)
    monkeypatch.delenv("PRIVATE_CHECK_BEARER_REFERENCE", raising=False)
    if bearer_value is not None:
        monkeypatch.setenv("PRIVATE_CHECK_BEARER_REFERENCE", bearer_value)
    settings = _settings(
        tmp_path,
        operator_credential_secret_ref=f"env:{_REFERENCE}",
        operator_api_token_secret_ref="env:PRIVATE_CHECK_BEARER_REFERENCE",
    )
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    result = runner.invoke(cli_module.app, ["serve", "--check-config"])

    valid = bearer_value == "distinct-api-token-01234567890123456789"
    assert result.exit_code == (0 if valid else 2)
    assert result.output.strip() == (_SUCCESS if valid else _AUTH_ERROR)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("forbid_startup")
@pytest.mark.parametrize("failure", ["validation", "settings", "os", "unicode"])
def test_check_config_settings_failures_are_fixed_and_non_reflecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    def fail_settings() -> Settings:
        if failure == "validation":
            return _settings(tmp_path, operator_credential_secret_ref="private-invalid-reference")
        if failure == "settings":
            raise SettingsError("private-settings-sentinel")
        if failure == "os":
            raise PermissionError("private-filesystem-sentinel")
        raise UnicodeError("private-decoding-sentinel")

    monkeypatch.setattr(cli_module, "get_settings", fail_settings)

    result = runner.invoke(cli_module.app, ["serve", "--check-config"])

    assert result.exit_code == 2
    assert result.output.strip() == _SETTINGS_ERROR
    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("forbid_startup")
@pytest.mark.parametrize(
    ("origin", "expected_error"),
    [
        ("http://private.example", _AUTH_ERROR),
        ("https://user:private@console.example", _SETTINGS_ERROR),
        ("private-sentinel", _SETTINGS_ERROR),
    ],
)
def test_check_config_invalid_origin_settings_do_not_reflect_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, origin: str, expected_error: str
) -> None:
    def load_settings() -> Settings:
        return _settings(
            tmp_path,
            operator_credential_secret_ref=f"env:{_REFERENCE}",
            operator_allowed_origins=(origin,),
        )

    monkeypatch.setenv(_REFERENCE, _CREDENTIAL)
    monkeypatch.setattr(cli_module, "get_settings", load_settings)

    result = runner.invoke(cli_module.app, ["serve", "--check-config"])

    assert result.exit_code == 2
    assert result.output.strip() == expected_error
    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("forbid_startup")
@pytest.mark.parametrize("failure", [OSError, RuntimeError])
def test_check_config_confines_secret_root_resolution_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: type[Exception]
) -> None:
    settings = _settings(tmp_path, operator_credential_secret_ref=f"env:{_REFERENCE}")
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    def fail_resolver(*_args: object, **_kwargs: object) -> None:
        raise failure("private-secret-root-sentinel")

    monkeypatch.setattr(cli_module.SecretResolver, "local", fail_resolver)

    result = runner.invoke(cli_module.app, ["serve", "--check-config"])

    assert result.exit_code == 2
    assert result.output.strip() == _AUTH_ERROR
    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("forbid_startup")
def test_serve_help_does_not_even_resolve_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_settings() -> None:
        pytest.fail("help attempted configuration resolution")

    monkeypatch.setattr(cli_module, "get_settings", fail_settings)

    result = runner.invoke(cli_module.app, ["serve", "--help"])

    assert result.exit_code == 0
    assert "check-config" in result.output
    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("forbid_startup")
@pytest.mark.parametrize("host", ["", "bad host", "private@host", "https://private.example", "::1%private", "a..b"])
def test_check_config_rejects_invalid_bind_even_with_explicit_origins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    monkeypatch.setenv(_REFERENCE, _CREDENTIAL)
    settings = _settings(
        tmp_path,
        operator_credential_secret_ref=f"env:{_REFERENCE}",
        operator_allowed_origins=("http://127.0.0.1:8632",),
    )
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    result = runner.invoke(cli_module.app, ["serve", "--host", host, "--check-config"])

    assert result.exit_code == 2
    assert result.output.strip() == _SETTINGS_ERROR


@pytest.mark.usefixtures("forbid_startup")
@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "0.0.0.0"])
def test_check_config_uses_actual_bind_overrides_for_origin_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    monkeypatch.setenv(_REFERENCE, _CREDENTIAL)
    settings = _settings(tmp_path, operator_credential_secret_ref=f"env:{_REFERENCE}")
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    original = cli_module.derive_operator_origin_policy
    observed: list[tuple[str, int]] = []

    def derive(bind_host: str, bind_port: int, origins: tuple[str, ...] | None) -> object:
        observed.append((bind_host, bind_port))
        return original(bind_host, bind_port, origins)

    monkeypatch.setattr(cli_module, "derive_operator_origin_policy", derive)

    result = runner.invoke(cli_module.app, ["serve", "--host", host, "--port", "9017", "--check-config"])

    assert observed == [(host, 9017)]
    assert result.exit_code == (2 if host == "0.0.0.0" else 0)
    assert result.output.strip() == (_AUTH_ERROR if host == "0.0.0.0" else _SUCCESS)


@pytest.mark.parametrize("existing_state", [False, True])
@pytest.mark.parametrize("valid", [False, True])
@pytest.mark.parametrize("global_terminator", [False, True])
def test_real_check_config_process_preserves_state(
    tmp_path: Path, existing_state: bool, valid: bool, global_terminator: bool
) -> None:
    state_dir = tmp_path / "state"
    if existing_state:
        state_dir.mkdir()
        with sqlite3.connect(state_dir / "media-sync.sqlite3") as connection:
            connection.execute("CREATE TABLE retained (value TEXT)")
            connection.execute("INSERT INTO retained VALUES ('preflight-retained-state')")
    env = {key: value for key, value in os.environ.items() if not key.startswith("MEDIA_SYNC_")}
    env.update(
        {
            "MEDIA_SYNC_STATE_DIR": str(state_dir),
            "MEDIA_SYNC_ARCHIVE_DIR": str(tmp_path / "archive"),
            "MEDIA_SYNC_EXPORT_DIR": str(tmp_path / "exports"),
            "MEDIA_SYNC_JOB_DIR": str(tmp_path / "jobs"),
            "MEDIA_SYNC_OPERATOR_CREDENTIAL_SECRET_REF": f"env:{_REFERENCE}",
            _REFERENCE: _CREDENTIAL if valid else "short",
        }
    )
    before = _snapshot(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "media_sync.interfaces.cli",
            *(["--"] if global_terminator else []),
            "serve",
            "--check-config",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == (0 if valid else 2)
    assert (completed.stdout + completed.stderr).strip() == (_SUCCESS if valid else _AUTH_ERROR)
    assert _snapshot(tmp_path) == before
