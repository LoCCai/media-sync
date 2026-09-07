"""REST contract for execution 0075 paused subscription policy edits."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from _api_client import authenticated_test_client
from fastapi.testclient import TestClient

from media_sync.config import Settings
from media_sync.infrastructure.db import Database, Subscription
from media_sync.infrastructure.db.migration import upgrade_database

_PRIVATE_REFERENCE = "env:MEDIA_SYNC_PRIVATE_XHS_CREATOR"


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "library",
        job_dir=tmp_path / "jobs",
        mediacrawler_runtime_dir=tmp_path / "mediacrawler",
        _env_file=None,
    )
    upgrade_database(settings.resolved_database_url)
    return authenticated_test_client(settings)


def _subscription(client: TestClient) -> dict[str, object]:
    account = client.post(
        "/api/v1/accounts",
        json={"platform": "xhs", "display_name": "Policy account", "login_method": "qr"},
    ).json()
    created = client.post(
        "/api/v1/subscriptions",
        json={
            "account_id": account["id"],
            "platform": "xhs",
            "creator_remote_id": "5f1234567890abcdef123456",
            "display_name": "Policy creator",
            "creator_reference_ref": _PRIVATE_REFERENCE,
            "interval_seconds": 3_600,
            "max_items": 12,
            "request_delay_seconds": 5,
            "headless": True,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def _body(revision: int = 0) -> dict[str, object]:
    return {
        "interval_seconds": 7_200,
        "max_items": 18,
        "request_delay_seconds": 9.5,
        "headless": False,
        "expected_schedule_revision": revision,
    }


def test_policy_route_requires_paused_current_revision_and_returns_only_allowlisted_state(tmp_path: Path) -> None:
    client = _client(tmp_path)
    subscription = _subscription(client)
    identifier = subscription["id"]
    route = f"/api/v1/subscriptions/{identifier}/policy"

    enabled = client.put(route, json=_body())
    assert enabled.status_code == 409
    assert enabled.json() == {"detail": "subscription_policy_requires_paused"}
    assert client.post(f"/api/v1/subscriptions/{identifier}/pause").status_code == 200

    detail = client.get(f"/api/v1/subscriptions/{identifier}").json()
    revision = detail["schedule"]["schedule_revision"]
    response = client.put(route, json=_body(revision))

    assert response.status_code == 200
    assert response.json() == {
        "id": identifier,
        "platform": "xhs",
        "status": "paused",
        "enabled": False,
        "interval_seconds": 7_200,
        "max_items": 18,
        "schedule_revision": revision + 1,
        "checkpoint_revision": 0,
        "next_run_at": None,
        "policy_summary": {
            "adapter": "mediacrawler",
            "schema_version": 1,
            "allow_full_history": False,
            "request_delay_seconds": 9.5,
            "headless": False,
            "creator_reference_configured": True,
        },
        "changed": True,
        "checkpoint_preserved": True,
        "media_preserved": True,
    }
    assert _PRIVATE_REFERENCE not in response.text
    assert "creator_input" not in response.text

    current = client.get(f"/api/v1/subscriptions/{identifier}")
    assert current.status_code == 200
    assert current.json()["interval_seconds"] == 7_200
    assert current.json()["max_items"] == 18
    assert current.json()["schedule"]["schedule_revision"] == revision + 1
    assert current.json()["schedule"]["status"] == "paused"
    assert current.json()["policy_summary"] == response.json()["policy_summary"]
    assert _PRIVATE_REFERENCE not in current.text

    stale = client.put(route, json=_body(revision))
    assert stale.status_code == 409
    assert stale.json() == {"detail": "subscription_policy_revision_conflict"}


def test_policy_route_rejects_extra_invalid_foreign_removed_and_missing_requests(tmp_path: Path) -> None:
    client = _client(tmp_path)
    subscription = _subscription(client)
    identifier = subscription["id"]
    route = f"/api/v1/subscriptions/{identifier}/policy"
    assert client.post(f"/api/v1/subscriptions/{identifier}/pause").status_code == 200

    extra = client.put(route, json={**_body(), "credential_ref": "PRIVATE_SENTINEL"})
    invalid = client.put(route, json={**_body(), "interval_seconds": 59})
    coerced_delay = client.put(route, json={**_body(), "request_delay_seconds": "9.5"})
    foreign_scope = client.put(route, json={**_body(), "bili_scope": "uploads"})

    assert extra.status_code == invalid.status_code == coerced_delay.status_code == 422
    assert (
        extra.json()["detail"]
        == invalid.json()["detail"]
        == coerced_delay.json()["detail"]
        == "request_validation_failed"
    )
    assert extra.json()["errors"] == [{"code": "extra_forbidden", "location": ["body", "credential_ref"]}]
    assert invalid.json()["errors"] == [{"code": "greater_than_equal", "location": ["body", "interval_seconds"]}]
    assert coerced_delay.json()["errors"] == [{"code": "float_type", "location": ["body", "request_delay_seconds"]}]
    assert "PRIVATE_SENTINEL" not in extra.text
    assert foreign_scope.status_code == 400
    assert foreign_scope.json() == {"detail": "subscription_policy_options_invalid"}

    removed = client.delete(f"/api/v1/subscriptions/{identifier}")
    assert removed.status_code == 200
    tombstone = client.put(route, json=_body())
    assert tombstone.status_code == 409
    assert tombstone.json() == {"detail": "subscription_policy_removed"}

    missing = client.put(f"/api/v1/subscriptions/{uuid4()}/policy", json=_body())
    assert missing.status_code == 404
    assert missing.json() == {"detail": "subscription_policy_not_found"}


def test_policy_route_rejects_malformed_durable_policy_without_reflecting_it(tmp_path: Path) -> None:
    client = _client(tmp_path)
    subscription = _subscription(client)
    identifier = str(subscription["id"])
    assert client.post(f"/api/v1/subscriptions/{identifier}/pause").status_code == 200
    settings = client.app.state.settings  # type: ignore[attr-defined]
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            row = session.get(Subscription, identifier)
            assert row is not None
            row.policy = {"mediacrawler": {"private": "PRIVATE_DURABLE_SENTINEL"}}
        response = client.put(f"/api/v1/subscriptions/{identifier}/policy", json=_body())
        assert response.status_code == 409
        assert response.json() == {"detail": "subscription_policy_invalid"}
        assert "PRIVATE_DURABLE_SENTINEL" not in response.text
        with database.session() as session:
            row = session.get(Subscription, identifier)
            assert row is not None
            assert row.schedule_revision == 0
            assert json.dumps(row.policy).find("PRIVATE_DURABLE_SENTINEL") >= 0
    finally:
        database.dispose()
