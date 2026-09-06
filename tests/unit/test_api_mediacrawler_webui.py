from __future__ import annotations

from pathlib import Path

import pytest
from _api_client import TEST_OPERATOR_CREDENTIAL, TEST_OPERATOR_ORIGIN, operator_test_settings
from fastapi import FastAPI, Request
from fastapi import WebSocket as FastAPIWebSocket
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

import media_sync.interfaces.api as api_module
from media_sync.config import Settings
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.security import OPERATOR_CSRF_HEADER_NAME, OPERATOR_SESSION_COOKIE_NAME


def _settings(tmp_path: Path) -> Settings:
    settings = operator_test_settings(
        Settings(
            state_dir=tmp_path / "state",
            archive_dir=tmp_path / "archive",
            export_dir=tmp_path / "library",
            job_dir=tmp_path / "jobs",
            mediacrawler_runtime_dir=tmp_path / "mediacrawler",
            mediacrawler_license_acknowledged=True,
            _env_file=None,
        )
    )
    upgrade_database(settings.resolved_database_url)
    return settings


def _upstream() -> FastAPI:
    app = FastAPI()

    @app.get("/")
    async def index() -> HTMLResponse:
        return HTMLResponse("<!doctype html><title>pinned MediaCrawler</title>")

    @app.post("/api/crawler/start")
    async def start(request: Request) -> dict[str, str]:
        return {"root_path": request.scope["root_path"], "status": "ok"}

    @app.get("/api/crawler/qrcode")
    async def qrcode() -> dict[str, str]:
        return {"status": "pending"}

    @app.websocket("/api/ws/logs")
    async def logs(websocket: FastAPIWebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"root_path": websocket.scope["root_path"], "status": "connected"})
        await websocket.close()

    return app


def test_mounted_console_uses_existing_operator_session_and_csrf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_module, "create_mediacrawler_webui_app", lambda _settings: _upstream())
    client = TestClient(api_module.create_api_app(_settings(tmp_path)), base_url=TEST_OPERATOR_ORIGIN)

    anonymous = client.get("/crawler/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert anonymous.status_code == 303
    assert anonymous.headers["location"] == "/?return_to=%2Fcrawler/"

    login = client.post(
        "/api/v1/operator-auth/login",
        json={"credential": TEST_OPERATOR_CREDENTIAL},
        headers={"Origin": TEST_OPERATOR_ORIGIN},
    )
    assert login.status_code == 200
    session = client.get("/api/v1/operator-auth/session").json()
    page = client.get("/crawler/")
    assert page.status_code == 200
    assert "pinned MediaCrawler" in page.text
    assert page.headers["cross-origin-resource-policy"] == "same-origin"

    missing_csrf = client.post("/crawler/api/crawler/start", headers={"Origin": TEST_OPERATOR_ORIGIN})
    assert missing_csrf.status_code == 403
    assert missing_csrf.json() == {"detail": "operator_csrf_forbidden"}
    assert client.app.state.log_store.flush()
    log_query = {"event_code": "request_finished", "module": "api", "level": "info"}
    before_events = client.get("/api/v1/logs", params=log_query).json()["events"]
    qr = client.get("/crawler/api/crawler/qrcode")
    assert qr.status_code == 200
    assert qr.headers["cache-control"] == "no-store"
    assert qr.headers["cross-origin-resource-policy"] == "same-origin"
    assert client.app.state.log_store.flush()
    after_qr_events = client.get("/api/v1/logs", params=log_query).json()["events"]
    assert after_qr_events == before_events
    started = client.post(
        "/crawler/api/crawler/start",
        headers={
            "Origin": TEST_OPERATOR_ORIGIN,
            OPERATOR_CSRF_HEADER_NAME: session["csrf_token"],
        },
    )
    assert started.status_code == 200
    assert started.json() == {"root_path": "/crawler", "status": "ok"}

    with client.websocket_connect(
        TEST_OPERATOR_ORIGIN.replace("http://", "ws://") + "/crawler/api/ws/logs",
        headers={
            "Origin": TEST_OPERATOR_ORIGIN,
            "Cookie": f"{OPERATOR_SESSION_COOKIE_NAME}={client.cookies[OPERATOR_SESSION_COOKIE_NAME]}",
        },
    ) as websocket:
        assert websocket.receive_json() == {"root_path": "/crawler", "status": "connected"}
    assert started.headers["cache-control"] == "no-store"
    assert started.headers["cross-origin-resource-policy"] == "same-origin"
    assert "content-security-policy" not in started.headers

    assert client.app.state.log_store.flush()
    after_events = client.get("/api/v1/logs", params=log_query).json()["events"]
    assert len(after_events) == len(before_events) + 1
    assert after_events[-1]["http_status"] == 200
