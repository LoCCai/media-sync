"""Authenticated lifecycle API and matching CLI contracts."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from _api_client import authenticated_test_client
from typer.testing import CliRunner

import media_sync.interfaces.cli as cli_module
from media_sync.config import Settings
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.infrastructure.db.models import Job


def _settings(tmp_path: Path) -> Settings:
    settings = Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "library",
        job_dir=tmp_path / "jobs",
        _env_file=None,
    )
    upgrade_database(settings.resolved_database_url)
    return settings


def _create(client: object) -> tuple[dict[str, object], dict[str, object]]:
    account = client.post(
        "/api/v1/accounts", json={"platform": "bili", "display_name": "test-account", "login_method": "qr"}
    ).json()
    draft = {
        "account_id": account["id"],
        "platform": "bili",
        "creator_remote_id": "2",
        "display_name": "creator",
        "max_items": 5,
        "allow_full_history": True,
    }
    response = client.post("/api/v1/subscriptions", json=draft)
    assert response.status_code == 201
    return response.json(), draft


def test_delete_and_restore_same_subscription_paused_without_erasing_history(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with authenticated_test_client(settings) as client:
        subscription, draft = _create(client)
        subscription_id = subscription["id"]
        path = f"/api/v1/subscriptions/{subscription_id}"
        assert subscription["deleted_at"] is None
        client.post(f"{path}/run-now")
        tick = client.post("/api/v1/scheduler/tick", json={}).json()
        assert tick["materialized_count"] == 1
        job_id = tick["cycles"][0]["job_id"]
        removed = client.delete(path)
        assert removed.status_code == 200
        assert removed.json() == {
            "id": subscription_id,
            "status": "deleted",
            "changed": True,
            "cancelled_jobs": 1,
            "media_preserved": True,
        }
        assert client.delete(path).json()["changed"] is False
        assert client.get("/api/v1/subscriptions").json() == []
        deleted = client.get("/api/v1/subscriptions?deleted=true").json()
        assert len(deleted) == 1 and deleted[0]["deleted_at"]
        assert deleted[0]["enabled"] is False
        detail = client.get(path)
        assert detail.status_code == 200 and detail.json()["deleted_at"]
        assert client.get(f"/api/v1/scheduler/jobs/{job_id}").json()["status"] == "cancelled"
        for action in ("pause", "resume", "run-now"):
            response = client.post(f"{path}/{action}")
            assert response.status_code == 409
            assert response.json() == {"detail": "subscription_removed"}
        for endpoint in ("/api/v1/subscriptions", "/api/v1/subscriptions/preview"):
            conflict = client.post(endpoint, json=draft)
            assert conflict.status_code == 409
            assert conflict.json() == {"detail": "subscription_removed"}
        restored = client.post(f"{path}/restore")
        assert restored.status_code == 200
        assert restored.json() == {
            "id": subscription_id,
            "status": "paused",
            "changed": True,
            "cancelled_jobs": 0,
            "media_preserved": True,
        }
        assert client.post(f"{path}/restore").json()["changed"] is False
        assert client.get("/api/v1/subscriptions?deleted=true").json() == []
        current = client.get("/api/v1/subscriptions").json()[0]
        assert current["id"] == subscription_id and current["enabled"] is False
        assert client.get(f"/api/v1/scheduler/jobs/{job_id}").json()["status"] == "cancelled"
        assert client.post("/api/v1/scheduler/tick", json={}).json()["materialized_count"] == 0
        client.post(f"{path}/resume")
        assert client.post(f"{path}/restore").json() == {"detail": "subscription_not_removed"}


def test_busy_removal_has_no_partial_effect_and_missing_target_is_fixed(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with authenticated_test_client(settings) as client:
        subscription, _ = _create(client)
        path = f"/api/v1/subscriptions/{subscription['id']}"
        database = Database(settings.resolved_database_url)
        try:
            with database.session() as session:
                session.add(
                    Job(
                        job_type="sync.subscription",
                        natural_key=str(uuid4()),
                        subscription_id=subscription["id"],
                        account_id=subscription["account_id"],
                        platform="bili",
                        status="claimed",
                    )
                )
        finally:
            database.dispose()
        response = client.delete(path)
        assert response.status_code == 409
        assert response.json() == {"detail": "subscription_busy"}
        assert client.get(path).json()["deleted_at"] is None
        assert client.get(path).json()["enabled"] is True
        for method, suffix in ((client.delete, ""), (client.post, "/restore")):
            missing = method(f"/api/v1/subscriptions/{uuid4()}{suffix}")
            assert missing.status_code == 404
            assert missing.json() == {"detail": "subscription_not_found"}


def test_cli_delete_restore_and_removed_list_share_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    with authenticated_test_client(settings) as client:
        subscription, _ = _create(client)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    runner = CliRunner()
    for action, expected in (("delete", "deleted"), ("restore", "paused")):
        result = runner.invoke(
            cli_module.app, ["subscription", action, "--subscription-id", subscription["id"], "--json"]
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["status"] == expected
        listed = runner.invoke(cli_module.app, ["subscription", "list", "--deleted", "--json"])
        assert listed.exit_code == 0, listed.output
        assert len(json.loads(listed.output)) == (1 if action == "delete" else 0)
        if action == "delete":
            rejected = runner.invoke(
                cli_module.app, ["subscription", "resume", "--subscription-id", subscription["id"], "--json"]
            )
            assert rejected.exit_code != 0
            assert "subscription_removed" in rejected.output
