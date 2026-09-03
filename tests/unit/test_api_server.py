"""Execution 0040 REST API smoke contract against a temporary SQLite store."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from media_sync.config import Settings
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.interfaces.api import create_api_app


def _client(tmp_path: Path) -> TestClient:
    state = tmp_path / "state"
    settings = Settings(
        state_dir=state,
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "library",
        job_dir=tmp_path / "jobs",
        mediacrawler_runtime_dir=tmp_path / "mediacrawler",
    )
    upgrade_database(settings.resolved_database_url)
    return TestClient(create_api_app(settings))


def test_health_ready_settings_and_console(tmp_path: Path) -> None:
    client = _client(tmp_path)

    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/ready").json()["status"] == "ready"
    settings = client.get("/api/v1/settings").json()
    assert settings["api_bind"] == "127.0.0.1:8632"
    console = client.get("/")
    assert console.status_code == 200
    assert "media-sync" in console.text


def test_account_lifecycle_and_login_gates(tmp_path: Path) -> None:
    client = _client(tmp_path)

    created = client.post(
        "/api/v1/accounts",
        json={"platform": "bili", "display_name": "bili-main", "login_method": "qr"},
    )
    assert created.status_code == 201
    account = created.json()
    assert account["created"] is True
    account_id = UUID(account["id"])

    repeat = client.post(
        "/api/v1/accounts",
        json={"platform": "bili", "display_name": "bili-main", "login_method": "qr"},
    )
    assert repeat.status_code == 201
    assert repeat.json()["created"] is False

    conflict = client.post(
        "/api/v1/accounts",
        json={"platform": "bili", "display_name": "bili-main", "login_method": "cookie", "credential_ref": "k1"},
    )
    assert conflict.status_code == 400

    assert [item["id"] for item in client.get("/api/v1/accounts").json()] == [account["id"]]

    status = client.get(f"/api/v1/accounts/{account_id}/login-status")
    assert status.status_code == 200
    assert status.json()["auth_status"] == "unknown"

    ungated = client.post(f"/api/v1/accounts/{account_id}/login", json={})
    assert ungated.status_code == 400
    assert ungated.json()["detail"] == "mediacrawler_not_enabled"

    half_gated = client.post(
        f"/api/v1/accounts/{account_id}/login",
        json={"enable_mediacrawler": True},
    )
    assert half_gated.status_code == 400
    assert half_gated.json()["detail"] == "license_acknowledgement_required"

    missing = client.post(f"/api/v1/accounts/{uuid4()}/login", json={"enable_mediacrawler": True})
    assert missing.status_code == 404

    qr = client.get(f"/api/v1/accounts/{account_id}/login-qr.png")
    assert qr.status_code == 404


def test_subscription_and_scheduler_surface(tmp_path: Path) -> None:
    client = _client(tmp_path)
    account = client.post(
        "/api/v1/accounts",
        json={"platform": "bili", "display_name": "bili-main", "login_method": "qr"},
    ).json()
    account_id = UUID(account["id"])

    created = client.post(
        "/api/v1/subscriptions",
        json={
            "account_id": str(account_id),
            "platform": "bili",
            "creator_remote_id": "2",
            "display_name": "creator",
            "max_items": 5,
        },
    )
    assert created.status_code == 201
    subscription = created.json()
    assert subscription["created"] is True
    subscription_id = UUID(subscription["id"])

    platform_conflict = client.post(
        "/api/v1/subscriptions",
        json={
            "account_id": str(account_id),
            "platform": "xhs",
            "creator_remote_id": "abc",
            "display_name": "creator",
        },
    )
    assert platform_conflict.status_code == 400

    run_now = client.post(f"/api/v1/subscriptions/{subscription_id}/run-now")
    assert run_now.status_code == 200
    assert run_now.json()["status"] == "enabled"

    pause = client.post(f"/api/v1/subscriptions/{subscription_id}/pause")
    assert pause.json()["status"] == "paused"
    resume = client.post(f"/api/v1/subscriptions/{subscription_id}/resume")
    assert resume.json()["status"] == "enabled"

    assert client.post(f"/api/v1/subscriptions/{uuid4()}/pause").status_code == 404

    tick = client.post("/api/v1/scheduler/tick", json={})
    assert tick.status_code == 200
    assert tick.json()["materialized_count"] >= 0

    jobs = client.get("/api/v1/scheduler/jobs")
    assert jobs.status_code == 200
    assert all(job["subscription_id"] == str(subscription_id) for job in jobs.json())

    assets = client.get("/api/v1/assets")
    assert assets.status_code == 200
    assert assets.json() == []


def test_background_operation_gates(tmp_path: Path) -> None:
    client = _client(tmp_path)

    ungated = client.post("/api/v1/scheduler/run", json={"accept_mediacrawler_license": True})
    assert ungated.status_code == 400
    assert ungated.json()["detail"] == "license_requires_enable_mediacrawler"

    ungated_pipeline = client.post("/api/v1/pipeline/run", json={"accept_mediacrawler_license": True})
    assert ungated_pipeline.status_code == 400

    fake_run = client.post(
        "/api/v1/scheduler/run",
        json={"enable_mediacrawler": False, "accept_mediacrawler_license": False},
    )
    assert fake_run.status_code == 202
    operation_id = fake_run.json()["operation_id"]

    operations = client.get("/api/v1/operations").json()
    assert any(item["id"] == operation_id for item in operations)
    detail = client.get(f"/api/v1/operations/{operation_id}")
    assert detail.status_code == 200
    assert detail.json()["kind"] == "scheduler-run"
    assert client.get("/api/v1/operations/not-a-uuid").status_code == 404

    database = Database(Settings(state_dir=tmp_path / "state").resolved_database_url)
    database.dispose()
