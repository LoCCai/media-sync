from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from _api_client import TEST_OPERATOR_CREDENTIAL, TEST_OPERATOR_ORIGIN, operator_test_settings
from fastapi import FastAPI, Request
from fastapi import WebSocket as FastAPIWebSocket
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

import media_sync.interfaces.api as api_module
from media_sync.application.mediacrawler_profile_adoption import (
    MediaCrawlerProfileAdoptionError,
    MediaCrawlerProfileAdoptionResult,
)
from media_sync.config import Settings
from media_sync.domain import Platform
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.integrations.mediacrawler.webui import (
    MediaCrawlerWebUIBusyError,
    MediaCrawlerWebUIUnavailableError,
)
from media_sync.security import OPERATOR_CSRF_HEADER_NAME, OPERATOR_SESSION_COOKIE_NAME


def _settings(
    tmp_path: Path,
    *,
    acknowledged: bool = True,
    runtime_available: bool = True,
) -> Settings:
    settings = operator_test_settings(
        Settings(
            state_dir=tmp_path / "state",
            archive_dir=tmp_path / "archive",
            export_dir=tmp_path / "library",
            job_dir=tmp_path / "jobs",
            mediacrawler_runtime_dir=tmp_path / "mediacrawler",
            mediacrawler_python_executable=(tmp_path / "mediacrawler-python" if runtime_available else None),
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


class _AdoptionManager:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[tuple[UUID, int]] = []

    async def adopt_profile(self, account_id: UUID, expected_auth_revision: int) -> object:
        self.calls.append((account_id, expected_auth_revision))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def _adoption_upstream(
    manager: _AdoptionManager,
    captured: list[Any],
) -> Any:
    def factory(
        _settings: Settings,
        *,
        profile_adopter: Any = None,
    ) -> FastAPI:
        captured.append(profile_adopter)
        app = _upstream()
        app.state.media_sync_manager = manager
        return app

    return factory


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
    monkeypatch.setattr(
        api_module,
        "create_mediacrawler_webui_app",
        lambda _settings, *, profile_adopter=None: _upstream(),
    )
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


def test_crawler_profile_adoption_is_authenticated_csrf_protected_and_safely_projected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = uuid4()
    result = MediaCrawlerProfileAdoptionResult(
        account_id=account_id,
        platform=Platform.BILI,
        auth_revision=4,
        upstream_sha="a" * 40,
        profile_file_count=12,
        profile_byte_count=34_567,
        resumed_job_count=2,
    )
    manager = _AdoptionManager(result)
    captured: list[Any] = []
    monkeypatch.setattr(
        api_module,
        "create_mediacrawler_webui_app",
        _adoption_upstream(manager, captured),
    )
    client = TestClient(api_module.create_api_app(_settings(tmp_path)), base_url=TEST_OPERATOR_ORIGIN)
    path = f"/api/v1/accounts/{account_id}/crawler-profile"

    anonymous = client.post(
        path,
        json={"expected_auth_revision": 3},
        headers={"Origin": TEST_OPERATOR_ORIGIN},
    )
    assert anonymous.status_code == 401
    assert anonymous.json() == {"detail": "operator_auth_required"}

    csrf = _login(client)
    missing_csrf = client.post(
        path,
        json={"expected_auth_revision": 3},
        headers={"Origin": TEST_OPERATOR_ORIGIN},
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json() == {"detail": "operator_csrf_forbidden"}

    response = client.post(
        path,
        json={"expected_auth_revision": 3},
        headers={"Origin": TEST_OPERATOR_ORIGIN, OPERATOR_CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 200
    assert response.json() == {
        "account_id": str(account_id),
        "platform": "bili",
        "auth_revision": 4,
        "upstream_sha": "a" * 40,
        "profile_file_count": 12,
        "profile_byte_count": 34_567,
        "resumed_job_count": 2,
        "login_method": "saved_session",
        "auth_status": "authenticated",
    }
    assert manager.calls == [(account_id, 3)]
    assert len(captured) == 1 and callable(captured[0])


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"expected_auth_revision": "3"},
        {"expected_auth_revision": True},
        {"expected_auth_revision": -1},
        {"expected_auth_revision": 2**63 - 1},
        {"expected_auth_revision": 3, "profile_path": "PRIVATE-SENTINEL"},
    ],
)
def test_crawler_profile_adoption_rejects_every_other_client_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body: dict[str, object],
) -> None:
    manager = _AdoptionManager(object())
    monkeypatch.setattr(
        api_module,
        "create_mediacrawler_webui_app",
        _adoption_upstream(manager, []),
    )
    client = TestClient(api_module.create_api_app(_settings(tmp_path)), base_url=TEST_OPERATOR_ORIGIN)
    csrf = _login(client)
    response = client.post(
        f"/api/v1/accounts/{uuid4()}/crawler-profile",
        json=body,
        headers={"Origin": TEST_OPERATOR_ORIGIN, OPERATOR_CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "request_validation_failed"
    assert "PRIVATE-SENTINEL" not in response.text
    assert manager.calls == []


@pytest.mark.parametrize(
    ("outcome", "status", "detail"),
    [
        (
            MediaCrawlerProfileAdoptionError("profile_adoption_account_not_found"),
            404,
            "account_not_found",
        ),
        (
            MediaCrawlerProfileAdoptionError("profile_adoption_account_ineligible"),
            409,
            "account_platform_mismatch",
        ),
        (MediaCrawlerProfileAdoptionError("profile_adoption_busy"), 409, "account_busy"),
        (MediaCrawlerProfileAdoptionError("profile_adoption_conflict"), 409, "account_revision_conflict"),
        (
            MediaCrawlerProfileAdoptionError("profile_adoption_source_missing"),
            409,
            "crawler_profile_not_found",
        ),
        (
            MediaCrawlerProfileAdoptionError("profile_adoption_source_empty"),
            409,
            "crawler_profile_empty",
        ),
        (
            MediaCrawlerProfileAdoptionError("profile_adoption_source_invalid"),
            409,
            "crawler_profile_unsafe",
        ),
        (
            MediaCrawlerProfileAdoptionError("profile_adoption_copy_failed"),
            503,
            "crawler_profile_transfer_failed",
        ),
        (
            MediaCrawlerProfileAdoptionError("profile_adoption_probe_failed"),
            409,
            "crawler_profile_auth_failed",
        ),
        (
            MediaCrawlerProfileAdoptionError("profile_adoption_probe_unavailable"),
            503,
            "crawler_profile_probe_unavailable",
        ),
        (
            MediaCrawlerProfileAdoptionError("profile_adoption_result_invalid"),
            503,
            "crawler_profile_probe_unavailable",
        ),
        (
            MediaCrawlerProfileAdoptionError("profile_adoption_cancelled"),
            409,
            "crawler_profile_cancelled",
        ),
        (
            MediaCrawlerProfileAdoptionError("profile_adoption_filesystem_failed"),
            503,
            "crawler_profile_transfer_failed",
        ),
        (
            MediaCrawlerProfileAdoptionError("profile_adoption_rollback_failed"),
            503,
            "crawler_profile_cleanup_failed",
        ),
        (
            MediaCrawlerProfileAdoptionError("profile_adoption_cleanup_failed"),
            503,
            "crawler_profile_cleanup_failed",
        ),
        (MediaCrawlerWebUIBusyError(), 409, "crawler_busy"),
        (MediaCrawlerWebUIUnavailableError(), 503, "crawler_profile_probe_unavailable"),
        (RuntimeError("Cookie=PRIVATE-SENTINEL"), 503, "crawler_profile_transfer_failed"),
        (object(), 503, "crawler_profile_probe_unavailable"),
    ],
)
def test_crawler_profile_adoption_maps_only_fixed_safe_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: object,
    status: int,
    detail: str,
) -> None:
    manager = _AdoptionManager(outcome)
    monkeypatch.setattr(
        api_module,
        "create_mediacrawler_webui_app",
        _adoption_upstream(manager, []),
    )
    client = TestClient(api_module.create_api_app(_settings(tmp_path)), base_url=TEST_OPERATOR_ORIGIN)
    csrf = _login(client)
    response = client.post(
        f"/api/v1/accounts/{uuid4()}/crawler-profile",
        json={"expected_auth_revision": 0},
        headers={"Origin": TEST_OPERATOR_ORIGIN, OPERATOR_CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert "PRIVATE-SENTINEL" not in response.text


def test_crawler_profile_adoption_fails_closed_without_license_or_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_factory(_settings: Settings, **_kwargs: Any) -> FastAPI:
        raise AssertionError("the unacknowledged app must not construct MediaCrawler")

    monkeypatch.setattr(api_module, "create_mediacrawler_webui_app", forbidden_factory)
    unacknowledged = TestClient(
        api_module.create_api_app(_settings(tmp_path / "license", acknowledged=False)),
        base_url=TEST_OPERATOR_ORIGIN,
    )
    csrf = _login(unacknowledged)
    response = unacknowledged.post(
        f"/api/v1/accounts/{uuid4()}/crawler-profile",
        json={"expected_auth_revision": 0},
        headers={"Origin": TEST_OPERATOR_ORIGIN, OPERATOR_CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "license_acknowledgement_required"}

    manager = _AdoptionManager(object())
    monkeypatch.setattr(
        api_module,
        "create_mediacrawler_webui_app",
        _adoption_upstream(manager, []),
    )
    unavailable = TestClient(
        api_module.create_api_app(_settings(tmp_path / "runtime", runtime_available=False)),
        base_url=TEST_OPERATOR_ORIGIN,
    )
    csrf = _login(unavailable)
    response = unavailable.post(
        f"/api/v1/accounts/{uuid4()}/crawler-profile",
        json={"expected_auth_revision": 0},
        headers={"Origin": TEST_OPERATOR_ORIGIN, OPERATOR_CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "crawler_profile_probe_unavailable"}
    assert manager.calls == []
