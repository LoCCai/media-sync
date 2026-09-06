from __future__ import annotations

from pathlib import Path

import pytest
from _api_client import TEST_OPERATOR_CREDENTIAL, TEST_OPERATOR_ORIGIN, operator_test_settings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import media_sync.interfaces.api as api_module
from media_sync.config import Settings
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.security import OPERATOR_CSRF_HEADER_NAME


def _settings(tmp_path: Path, *, acknowledged: bool = False) -> Settings:
    settings = operator_test_settings(
        Settings(
            state_dir=tmp_path / "state",
            archive_dir=tmp_path / "archive",
            export_dir=tmp_path / "library",
            job_dir=tmp_path / "jobs",
            mediacrawler_runtime_dir=tmp_path / "mediacrawler",
            mediacrawler_python_executable=tmp_path / "mediacrawler-python",
            mediacrawler_license_acknowledged=acknowledged,
            _env_file=None,
        )
    )
    upgrade_database(settings.resolved_database_url)
    return settings


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/operator-auth/login",
        json={"credential": TEST_OPERATOR_CREDENTIAL},
        headers={"Origin": TEST_OPERATOR_ORIGIN},
    )
    assert response.status_code == 200
    return str(client.get("/api/v1/operator-auth/session").json()["csrf_token"])


def test_unacknowledged_deployment_never_constructs_or_starts_upstream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_factory(_settings: Settings) -> object:
        raise AssertionError("unacknowledged deployment must not import the upstream app")

    monkeypatch.setattr(api_module, "create_mediacrawler_webui_app", forbidden_factory)
    client = TestClient(api_module.create_api_app(_settings(tmp_path)), base_url=TEST_OPERATOR_ORIGIN)

    anonymous = client.get("/crawler/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert anonymous.status_code == 303
    csrf = _login(client)

    for path in ("/crawler", "/crawler/", "/crawler/api/env/check"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 503
        assert response.json() == {"detail": "license_acknowledgement_required"}
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["cross-origin-resource-policy"] == "same-origin"

    start = client.post(
        "/crawler/api/crawler/start",
        headers={"Origin": TEST_OPERATOR_ORIGIN, OPERATOR_CSRF_HEADER_NAME: csrf},
        json={"platform": "bili"},
    )
    assert start.status_code == 503
    assert start.json() == {"detail": "license_acknowledgement_required"}
    assert start.headers["cache-control"] == "no-store"
    assert start.headers["cross-origin-resource-policy"] == "same-origin"


def test_acknowledged_deployment_constructs_upstream_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Settings] = []
    shutdown_calls: list[str] = []

    def factory(settings: Settings) -> FastAPI:
        calls.append(settings)
        upstream = FastAPI()

        async def shutdown() -> None:
            shutdown_calls.append("called")

        upstream.state.media_sync_shutdown = shutdown
        return upstream

    monkeypatch.setattr(api_module, "create_mediacrawler_webui_app", factory)
    app = api_module.create_api_app(_settings(tmp_path, acknowledged=True))
    with TestClient(app, base_url=TEST_OPERATOR_ORIGIN):
        pass

    assert len(calls) == 1
    assert calls[0].mediacrawler_license_acknowledged is True
    assert shutdown_calls == ["called"]


@pytest.mark.parametrize("value", ["1", "yes", "TRUE", " true ", 1, None])
def test_license_acknowledgement_rejects_ambiguous_values(value: object) -> None:
    with pytest.raises(ValidationError, match="must be true or false"):
        Settings(mediacrawler_license_acknowledged=value, _env_file=None)  # type: ignore[arg-type]


def test_license_acknowledgement_environment_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_LICENSE_ACKNOWLEDGED", "true")
    assert Settings(_env_file=None).mediacrawler_license_acknowledged is True
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_LICENSE_ACKNOWLEDGED", "false")
    assert Settings(_env_file=None).mediacrawler_license_acknowledged is False
