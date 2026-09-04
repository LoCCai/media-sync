"""Execution 0040 REST API smoke contract against a temporary SQLite store."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
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


def test_health_ready_settings_and_console(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    web_root = tmp_path / "console-v2"
    immutable_root = web_root / "_app" / "immutable"
    immutable_root.mkdir(parents=True)
    (web_root / "index.html").write_text("<!doctype html><title>media-sync Console v2</title>", encoding="utf-8")
    (immutable_root / "app.js").write_text("export {};", encoding="utf-8")
    monkeypatch.setattr("media_sync.interfaces.api._resolve_web_root", lambda: web_root)

    client = _client(tmp_path)

    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/ready").json()["status"] == "ready"
    settings = client.get("/api/v1/settings").json()
    assert settings["api_bind"] == "127.0.0.1:8632"
    console = client.get("/")
    assert console.status_code == 200
    assert "media-sync" in console.text
    assert console.headers["x-content-type-options"] == "nosniff"
    assert console.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in console.headers["content-security-policy"]

    nested_route = client.get("/accounts")
    assert nested_route.status_code == 200
    assert "media-sync" in nested_route.text

    immutable_asset = client.get("/_app/immutable/app.js")
    assert immutable_asset.status_code == 200
    assert immutable_asset.headers["cache-control"] == "public, max-age=31536000, immutable"

    legacy = client.get("/legacy")
    assert legacy.status_code == 200
    assert "media-sync 控制台" in legacy.text
    assert legacy.headers["cache-control"] == "no-cache"

    missing_api = client.get("/api/v1/not-a-route")
    assert missing_api.status_code == 404
    assert missing_api.headers["cache-control"] == "no-store"


def test_deep_readiness_reports_license_gate_without_exposing_paths(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.get("/api/v1/readiness/deep")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["code"] == "license_acknowledgement_required"
    assert body["mediacrawler"]["detail_code"] == "license_acknowledgement_required"
    assert body["mediacrawler"]["checks"]["license_acknowledgement"] == "fail"
    assert body["security"] == {
        "status": "pass",
        "code": None,
        "safe": True,
        "requires_operator_review": False,
        "api_host": "127.0.0.1",
        "api_port": 8632,
        "note": "loopback_only",
    }
    assert str(tmp_path) not in response.text


def test_login_qr_lifecycle_distinguishes_pending_and_gone(tmp_path: Path) -> None:
    from media_sync.infrastructure.db import LoginSessionRepository

    client = _client(tmp_path)
    account = client.post(
        "/api/v1/accounts",
        json={"platform": "bili", "display_name": "bili-main", "login_method": "qr"},
    ).json()
    settings = client.app.state.settings  # type: ignore[attr-defined]
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            login_session = LoginSessionRepository(session).create(
                account_id=account["id"],
                method="qr",
                challenge_kind="qr",
            )
            login_session.status = "waiting_user"
            login_session_id = login_session.id

        pending = client.get(f"/api/v1/accounts/{account['id']}/login-qr.png")
        assert pending.status_code == 202
        assert pending.json() == {"code": "login_qr_pending", "login_session_id": login_session_id}
        assert pending.headers["cache-control"] == "no-store"

        with database.session() as session:
            session_login = LoginSessionRepository(session).get(login_session_id)
            assert session_login is not None
            session_login.status = "expired"

        gone = client.get(f"/api/v1/accounts/{account['id']}/login-qr.png")
        assert gone.status_code == 410
        assert gone.json() == {"code": "login_qr_gone", "login_session_id": login_session_id}
    finally:
        database.dispose()


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

    missing = client.post(
        f"/api/v1/accounts/{uuid4()}/login",
        json={"enable_mediacrawler": True, "accept_mediacrawler_license": True},
    )
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
            "allow_full_history": True,
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

    contents = client.get("/api/v1/contents")
    assert contents.status_code == 200
    assert contents.json() == []

    library = client.get("/api/v1/library")
    assert library.status_code == 200
    assert library.json() == [
        {
            "author_id": subscription["author_id"],
            "platform": "bili",
            "display_name": "creator",
            "remote_id": "2",
            "content_count": 0,
            "asset_count": 0,
            "archived_count": 0,
            "exported_count": 0,
            "last_published_at": None,
            "archive_state": "empty",
        }
    ]


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


def test_subscription_detail_job_detail_and_asset_download(tmp_path: Path) -> None:
    client = _client(tmp_path)
    account = client.post(
        "/api/v1/accounts",
        json={"platform": "bili", "display_name": "bili-main", "login_method": "qr"},
    ).json()
    subscription = client.post(
        "/api/v1/subscriptions",
        json={
            "account_id": account["id"],
            "platform": "bili",
            "creator_remote_id": "2",
            "display_name": "creator",
            "max_items": 5,
            "allow_full_history": True,
        },
    ).json()
    subscription_id = UUID(subscription["id"])

    detail = client.get(f"/api/v1/subscriptions/{subscription_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == subscription["id"]
    assert body["schedule"]["status"] == "enabled"
    assert body["recent_runs"] == []
    assert isinstance(body["recent_jobs"], list)

    assert client.get("/api/v1/subscriptions/00000000-0000-0000-0000-000000000000").status_code == 404

    missing_job = client.get("/api/v1/scheduler/jobs/00000000-0000-0000-0000-000000000000")
    assert missing_job.status_code == 404

    ungated = client.post(f"/api/v1/assets/{uuid4()}/download", json={"accept_mediacrawler_license": True})
    assert ungated.status_code == 400
    assert ungated.json()["detail"] == "license_requires_enable_mediacrawler"

    missing_asset = client.post(
        f"/api/v1/assets/{uuid4()}/download",
        json={"enable_mediacrawler": False, "accept_mediacrawler_license": False},
    )
    assert missing_asset.status_code == 404


def _wait_operation(client: TestClient, operation_id: str, *, timeout: float = 10.0) -> dict[str, object]:
    import time as _time

    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        body = client.get(f"/api/v1/operations/{operation_id}").json()
        if body["state"] not in {"queued", "running"}:
            return body
        _time.sleep(0.02)
    raise AssertionError("operation did not leave the running state")


def test_asset_download_operation_lifecycle_on_a_real_asset(tmp_path: Path) -> None:
    """A real Asset drives blocked→failed and verified→succeeded operations."""

    import json
    from datetime import UTC, datetime

    from sqlalchemy import select

    from media_sync.domain import AuthStatus, Platform, RunStatus
    from media_sync.infrastructure.db import (
        AccountRepository,
        AuthorRepository,
        AuthorUpsert,
        IngestionMode,
        MediaCrawlerIngestionService,
        SubscriptionRepository,
        SyncRunRepository,
    )
    from media_sync.infrastructure.db.models import Asset
    from media_sync.integrations.mediacrawler.normalizers import (
        NormalizationContext,
        normalize_jsonl_bytes,
    )

    client = _client(tmp_path)
    settings = client.app.state.settings  # type: ignore[attr-defined]
    fixed_at = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            account = AccountRepository(session).create(
                platform=Platform.KS.value,
                adapter="mediacrawler",
                display_name="lifecycle-account",
                login_method="qr",
                auth_status=AuthStatus.AUTHENTICATED.value,
            )
            author = AuthorRepository(session).upsert(
                AuthorUpsert(platform=Platform.KS.value, remote_id="77", display_name="Lifecycle"),
                seen_at=fixed_at,
            )
            subscription = SubscriptionRepository(session).create(account_id=account.id, author_id=author.id, policy={})
            runs = SyncRunRepository(session)
            run = runs.create(subscription_id=subscription.id)
            for source, target in (
                (RunStatus.QUEUED, RunStatus.CLAIMED),
                (RunStatus.CLAIMED, RunStatus.RUNNING),
                (RunStatus.RUNNING, RunStatus.INGESTING),
            ):
                runs.set_status(run.id, target.value, expected_status=source.value)

        record = {
            "video_id": "life-video-001",
            "video_type": "video",
            "title": "lifecycle",
            "desc": "lifecycle",
            "video_url": "https://www.kuaishou.com/short-video/life-video-001",
            "video_cover_url": "",
            "video_play_url": "https://cdn.example.test/life.mp4",
        }
        normalized = normalize_jsonl_bytes(
            (json.dumps(record, separators=(",", ":")) + "\n").encode(),
            NormalizationContext(
                platform=Platform.KS,
                creator_remote_id="77",
                creator_display_name="Lifecycle",
                upstream_sha="d6f7c5bb906b6dac40ddf343ef9e26438a3de092",
                ingested_at=fixed_at,
            ),
        )
        assert not normalized.quarantined
        ingestion = MediaCrawlerIngestionService(database).ingest(
            normalized.records,
            subscription_id=subscription.id,
            run_id=run.id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )
        assert ingestion.asset_count == 1

        with database.session() as session:
            asset = session.scalars(select(Asset)).one()
            asset_id = UUID(asset.id)
            locator = asset.locator
            if isinstance(locator, str):
                import json as _json

                locator = _json.loads(locator)
            assert isinstance(locator, dict) and locator.get("type") == "adapter_refresh"

        # Blocked path: the mediacrawler gate is not satisfied → the background
        # operation must finish FAILED with the blocked error code, not green.
        started = client.post(
            f"/api/v1/assets/{asset_id}/download",
            json={"enable_mediacrawler": False, "accept_mediacrawler_license": False},
        )
        assert started.status_code == 202
        blocked = _wait_operation(client, started.json()["operation_id"])
        assert blocked["state"] == "failed_retryable"
        assert blocked["error_code"] == "locator_refresh_unsupported"
        assert blocked["result"]["ok"] is False
        assert blocked["result"]["status"] == "blocked"
        assert blocked["result"]["disposition"] == "not_started"

        # Verified-without-archive path: hand-marking an asset verified without
        # its immutable blob is a state inconsistency, and the recovery preflight
        # must surface it as a FAILED operation instead of a fake green success.
        with database.session() as session:
            verified = session.get(Asset, str(asset_id))
            assert verified is not None
            verified.status = "verified"
            verified.generation = 1
            verified.verified_at = fixed_at
        started = client.post(
            f"/api/v1/assets/{asset_id}/download",
            json={"enable_mediacrawler": False, "accept_mediacrawler_license": False},
        )
        assert started.status_code == 202
        inconsistent = _wait_operation(client, started.json()["operation_id"])
        assert inconsistent["state"] == "failed_terminal"
        assert inconsistent["error_code"] == "asset_download_state_invalid"
        assert inconsistent["result"]["ok"] is False
        assert inconsistent["result"]["status"] == "failed"
    finally:
        database.dispose()


def test_asset_download_operation_succeeded_wiring_uses_captured_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completing executor drives running→succeeded with app-captured settings."""

    import media_sync.interfaces.api as api_module

    client = _client(tmp_path)
    settings = client.app.state.settings  # type: ignore[attr-defined]
    captured: dict[str, object] = {}

    def fake_executor(**kwargs: object) -> tuple[dict[str, object], bool]:
        captured["settings_state_dir"] = str(kwargs["settings"].state_dir)  # type: ignore[attr-defined]
        return {
            "asset_id": str(kwargs["asset_id"]),
            "job_id": None,
            "status": "verified",
            "disposition": "downloaded",
            "generation": 1,
            "size_bytes": 42,
        }, True

    monkeypatch.setattr(api_module, "_execute_asset_download", fake_executor)
    asset_id = uuid4()

    # Insert a minimal content+asset row directly so the 404 preflight passes.
    from datetime import UTC, datetime

    from sqlalchemy import insert

    from media_sync.domain import AuthStatus, Platform
    from media_sync.infrastructure.db import AccountRepository, AuthorRepository, AuthorUpsert
    from media_sync.infrastructure.db.models import Asset, Content

    fixed_at = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            account = AccountRepository(session).create(
                platform=Platform.KS.value,
                adapter="mediacrawler",
                display_name="wiring-account",
                login_method="qr",
                auth_status=AuthStatus.AUTHENTICATED.value,
            )
            author = AuthorRepository(session).upsert(
                AuthorUpsert(platform=Platform.KS.value, remote_id="79", display_name="Wiring"),
                seen_at=fixed_at,
            )
            content_id = "wiring-content-001"
            session.execute(
                insert(Content).values(
                    id=content_id,
                    author_id=author.id,
                    platform="ks",
                    remote_type="content",
                    remote_id="wiring-001",
                    kind="video",
                    created_at=fixed_at,
                    updated_at=fixed_at,
                )
            )
            del account
            session.execute(
                insert(Asset).values(
                    id=str(asset_id),
                    platform="ks",
                    content_id=content_id,
                    remote_id="wiring-001:video:0",
                    kind="video",
                    position=0,
                    status="discovered",
                    locator={
                        "type": "adapter_refresh",
                        "adapter": "mediacrawler",
                        "asset_key": "wiring",
                        "version": 1,
                    },
                    semantic_fingerprint="0" * 64,
                    locator_fingerprint="1" * 64,
                    created_at=fixed_at,
                    updated_at=fixed_at,
                )
            )
    finally:
        database.dispose()

    started = client.post(
        f"/api/v1/assets/{asset_id}/download",
        json={"enable_mediacrawler": False, "accept_mediacrawler_license": False},
    )
    assert started.status_code == 202
    finished = _wait_operation(client, started.json()["operation_id"])
    assert finished["state"] == "succeeded"
    assert finished["error_code"] is None
    assert finished["result"]["ok"] is True
    assert finished["result"]["disposition"] == "downloaded"
    # The background thread used the settings captured by the app factory, not a
    # fresh global read, so its state_dir matches the app factory's.
    assert captured["settings_state_dir"] == str(settings.state_dir)
