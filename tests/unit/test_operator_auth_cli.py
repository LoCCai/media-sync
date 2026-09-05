"""Fail-before-bind contracts for ``media-sync serve`` operator auth."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from typer.testing import CliRunner

import media_sync.interfaces.api as api_module
import media_sync.interfaces.cli as cli_module
from media_sync.config import Settings

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


def test_serve_rejects_missing_operator_credential_before_app_or_bind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_calls: list[object] = []
    bind_calls: list[object] = []
    monkeypatch.setattr(cli_module, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(api_module, "create_api_app", lambda *_args, **_kwargs: app_calls.append(object()))
    monkeypatch.setattr(uvicorn, "run", lambda *_args, **_kwargs: bind_calls.append(object()))

    result = runner.invoke(cli_module.app, ["serve"])

    assert result.exit_code == 2
    assert result.output.strip() == '{"detail":"operator_auth_configuration_invalid"}'
    assert app_calls == []
    assert bind_calls == []
    assert "Traceback" not in result.output


@pytest.mark.parametrize("secret_value", [None, "short"])
def test_serve_collapses_unresolved_and_weak_secret_failures_without_echo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    secret_value: str | None,
) -> None:
    locator = "PRIVATE_OPERATOR_REFERENCE_SENTINEL"
    if secret_value is None:
        monkeypatch.delenv(locator, raising=False)
    else:
        monkeypatch.setenv(locator, secret_value)
    settings = _settings(tmp_path, operator_credential_secret_ref=f"env:{locator}")
    bind_calls: list[object] = []
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    monkeypatch.setattr(uvicorn, "run", lambda *_args, **_kwargs: bind_calls.append(object()))

    result = runner.invoke(cli_module.app, ["serve"])

    assert result.exit_code == 2
    assert result.output.strip() == '{"detail":"operator_auth_configuration_invalid"}'
    assert locator not in result.output
    if secret_value is not None:
        assert secret_value not in result.output
    assert bind_calls == []


def test_serve_collapses_settings_validation_without_echo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def invalid_settings() -> Settings:
        return _settings(tmp_path, operator_credential_secret_ref="inline-private-sentinel")

    monkeypatch.setattr(cli_module, "get_settings", invalid_settings)

    result = runner.invoke(cli_module.app, ["serve"])

    assert result.exit_code == 2
    assert result.output.strip() == '{"detail":"service_configuration_invalid"}'
    assert "inline-private-sentinel" not in result.output
    assert "Traceback" not in result.output


def test_serve_passes_one_resolved_boundary_and_disables_proxy_and_access_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locator = "MEDIA_SYNC_OPERATOR_CLI_TEST"
    credential = "cli-test-operator-credential-0123456789"
    monkeypatch.setenv(locator, credential)
    settings = _settings(tmp_path, operator_credential_secret_ref=f"env:{locator}")
    calls: list[tuple[object, dict[str, Any]]] = []
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    monkeypatch.setattr(uvicorn, "run", lambda application, **kwargs: calls.append((application, kwargs)))

    result = runner.invoke(cli_module.app, ["serve"])

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    application, kwargs = calls[0]
    assert application.state.operator_auth_runtime.bearer_enabled is False  # type: ignore[attr-defined]
    log_config = kwargs.pop("log_config")
    assert kwargs == {
        "host": "127.0.0.1",
        "port": 8632,
        "log_level": "info",
        "proxy_headers": False,
        "access_log": False,
    }
    assert log_config["handlers"]["media_sync"] == {
        "class": "logging.StreamHandler",
        "formatter": "default",
        "stream": "ext://sys.stderr",
    }
    assert log_config["loggers"]["media_sync"] == {
        "handlers": ["media_sync"],
        "level": "INFO",
        "propagate": False,
    }
    for name in ("default", "access"):
        assert log_config["handlers"][name] == uvicorn.config.LOGGING_CONFIG["handlers"][name]
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        assert log_config["loggers"][name] == uvicorn.config.LOGGING_CONFIG["loggers"][name]
    assert "media_sync" not in uvicorn.config.LOGGING_CONFIG["handlers"]
    assert "media_sync" not in uvicorn.config.LOGGING_CONFIG["loggers"]
    payload = json.loads(result.output)
    assert payload == {
        "service": "media-sync-api",
        "bind": "127.0.0.1:8632",
        "console": "http://127.0.0.1:8632/",
        "authentication": "single-operator-session",
        "bearer_automation_enabled": False,
    }
    assert credential not in result.output
    assert locator not in result.output


def test_serve_log_config_emits_only_fixed_application_audits_without_binding() -> None:
    private_sentinel = "private-runtime-audit-sentinel"
    script = """
import sys

import uvicorn

from media_sync.application.playback_evidence import PlaybackEvidenceAuditCode, PlaybackEvidenceService
from media_sync.interfaces.cli import _uvicorn_log_config
from media_sync.security import operator_auth as operator_auth_module
from media_sync.security.operator_auth import OperatorAuditCode

configuration = uvicorn.Config(
    "media_sync.interfaces.api:create_api_app",
    log_config=_uvicorn_log_config("INFO"),
    log_level="info",
    access_log=False,
)
configuration.configure_logging()
PlaybackEvidenceService._default_audit_sink(PlaybackEvidenceAuditCode.CREATED)
operator_auth_module._default_audit_sink(OperatorAuditCode.LOGIN_SUCCEEDED)
if sys.argv[1] in "playback_evidence_created operator_login_succeeded":
    raise AssertionError("private sentinel unexpectedly matched a fixed audit code")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, private_sentinel],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    audit_lines = [line for line in completed.stderr.splitlines() if line]
    assert len(audit_lines) == 2
    assert audit_lines[0].endswith("playback_evidence_created")
    assert audit_lines[1].endswith("operator_login_succeeded")
    assert private_sentinel not in completed.stdout + completed.stderr


def test_serve_non_loopback_override_requires_an_explicit_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locator = "MEDIA_SYNC_OPERATOR_NON_LOOPBACK_TEST"
    monkeypatch.setenv(locator, "non-loopback-operator-credential-012345")
    settings = _settings(tmp_path, operator_credential_secret_ref=f"env:{locator}")
    bind_calls: list[object] = []
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    monkeypatch.setattr(uvicorn, "run", lambda *_args, **_kwargs: bind_calls.append(object()))

    result = runner.invoke(cli_module.app, ["serve", "--host", "0.0.0.0"])

    assert result.exit_code == 2
    assert result.output.strip() == '{"detail":"operator_auth_configuration_invalid"}'
    assert bind_calls == []


def test_serve_allows_container_wildcard_bind_with_explicit_loopback_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locator = "MEDIA_SYNC_OPERATOR_CONTAINER_TEST"
    monkeypatch.setenv(locator, "container-operator-credential-0123456789")
    settings = _settings(
        tmp_path,
        api_host="0.0.0.0",
        operator_credential_secret_ref=f"env:{locator}",
        operator_allowed_origins=("http://127.0.0.1:8632",),
    )
    calls: list[tuple[object, dict[str, Any]]] = []
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    monkeypatch.setattr(uvicorn, "run", lambda application, **kwargs: calls.append((application, kwargs)))

    result = runner.invoke(cli_module.app, ["serve"])

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    application, kwargs = calls[0]
    assert application.state.operator_origin_policy.origins == ("http://127.0.0.1:8632",)  # type: ignore[attr-defined]
    assert application.state.operator_origin_policy.secure_cookie is False  # type: ignore[attr-defined]
    assert kwargs["host"] == "0.0.0.0"
    assert json.loads(result.output)["console"] == "http://127.0.0.1:8632/"
