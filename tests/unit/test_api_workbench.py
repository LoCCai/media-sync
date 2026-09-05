"""Execution 0051 REST workbench and login-session security contracts."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from _api_client import authenticated_test_client
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from media_sync.config import Settings
from media_sync.infrastructure.db import Database, LoginSessionRepository
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.infrastructure.db.models import Author, Subscription
from media_sync.integrations.mediacrawler.bilibili_scan import (
    BiliIdentity,
    BiliLane,
    BiliPage,
    BiliScanState,
    BiliUnitSummary,
)
from media_sync.integrations.mediacrawler.checkout import load_mediacrawler_lock


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "library",
        job_dir=tmp_path / "jobs",
        mediacrawler_runtime_dir=tmp_path / "mediacrawler",
    )
    upgrade_database(settings.resolved_database_url)
    return authenticated_test_client(settings)


def _account(client: TestClient, platform: str, name: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/accounts",
        json={"platform": platform, "display_name": name, "login_method": "qr"},
    )
    assert response.status_code == 201
    return response.json()


def _row_counts(client: TestClient) -> tuple[int, int]:
    settings = client.app.state.settings  # type: ignore[attr-defined]
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            authors = session.scalar(select(func.count()).select_from(Author))
            subscriptions = session.scalar(select(func.count()).select_from(Subscription))
            return int(authors or 0), int(subscriptions or 0)
    finally:
        database.dispose()


def test_bili_dynamic_scope_preview_and_paused_revision_update(tmp_path: Path) -> None:
    client = _client(tmp_path)
    account = _account(client, "bili", "scope-fixture")
    draft = {
        "account_id": account["id"],
        "platform": "bili",
        "creator_remote_id": "42",
        "display_name": "Fixture",
        "bili_scope": "dynamics",
        "max_items": 2,
    }
    preview = client.post("/api/v1/subscriptions/preview", json=draft)
    assert preview.status_code == 200
    assert preview.json()["policy_summary"]["bili_scope"] == "dynamics"
    assert client.post("/api/v1/subscriptions/preview", json={**draft, "max_items": 1}).status_code == 400
    created = client.post("/api/v1/subscriptions", json=draft)
    assert created.status_code == 201
    identifier = created.json()["id"]
    detail = client.get(f"/api/v1/subscriptions/{identifier}").json()
    revision = detail["schedule"]["schedule_revision"]
    update = {"scope": "both", "max_items": 2, "expected_schedule_revision": revision}
    assert client.post(f"/api/v1/subscriptions/{identifier}/bili-scope", json=update).status_code == 409
    assert client.post(f"/api/v1/subscriptions/{identifier}/pause").status_code == 200
    response = client.post(f"/api/v1/subscriptions/{identifier}/bili-scope", json=update)
    assert response.status_code == 200 and response.json()["checkpoint_preserved"] is True
    assert response.json()["enabled"] is False
    assert client.post(f"/api/v1/subscriptions/{identifier}/bili-scope", json=update).status_code == 409
    assert _row_counts(client) == (1, 1)


def test_platform_capabilities_are_complete_versioned_and_path_free(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.get("/api/v1/platform-capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert [item["platform"] for item in body["platforms"]] == [
        "xhs",
        "dy",
        "ks",
        "bili",
        "wb",
        "tieba",
        "zhihu",
    ]
    assert all(item["live_qualification"] == "NOT_RUN" for item in body["platforms"])
    assert str(tmp_path) not in response.text
    assert "credential_ref" not in response.text
    assert "creator_secret_ref" not in response.text


def test_request_validation_never_echoes_rejected_secret_or_creator_input(tmp_path: Path) -> None:
    client = _client(tmp_path)
    account = _account(client, "xhs", "xhs-main")
    credential_sentinel = "SENTINEL_INLINE_COOKIE_MUST_NOT_ECHO"
    creator_sentinel = "SENTINEL_SIGNED_CREATOR_URL_MUST_NOT_ECHO"

    bad_account = client.post(
        "/api/v1/accounts",
        json={
            "platform": "xhs",
            "display_name": "bad-cookie",
            "login_method": "cookie",
            "credential_ref": {"cookie": credential_sentinel},
        },
    )
    bad_subscription = client.post(
        "/api/v1/subscriptions/preview",
        json={
            "account_id": account["id"],
            "platform": "xhs",
            "creator_remote_id": creator_sentinel * 20,
            "display_name": "creator",
        },
    )

    assert bad_account.status_code == 422
    assert bad_subscription.status_code == 422
    assert bad_account.json()["detail"] == "request_validation_failed"
    assert bad_subscription.json()["detail"] == "request_validation_failed"
    assert credential_sentinel not in bad_account.text
    assert creator_sentinel not in bad_subscription.text


def test_unacknowledged_or_unstable_subscription_drafts_write_no_rows(tmp_path: Path) -> None:
    client = _client(tmp_path)
    account = _account(client, "wb", "weibo-main")
    draft = {
        "account_id": account["id"],
        "platform": "wb",
        "creator_remote_id": "123456",
        "display_name": "creator",
    }

    preview = client.post("/api/v1/subscriptions/preview", json=draft)
    create = client.post("/api/v1/subscriptions", json=draft)
    unstable = client.post(
        "/api/v1/subscriptions",
        json={**draft, "creator_remote_id": "https://space.bilibili.com/123456", "allow_full_history": True},
    )

    assert preview.status_code == 400
    assert preview.json()["detail"] == "full_history_acknowledgement_required"
    assert create.status_code == 400
    assert create.json()["detail"] == "full_history_acknowledgement_required"
    assert unstable.status_code == 400
    assert unstable.json()["detail"] == "creator_remote_id_must_be_stable_id"
    assert _row_counts(client) == (0, 0)


def test_new_bili_subscription_needs_no_unbounded_history_acknowledgement(tmp_path: Path) -> None:
    client = _client(tmp_path)
    account = _account(client, "bili", "bili-main")
    draft = {
        "account_id": account["id"],
        "platform": "bili",
        "creator_remote_id": "123456",
        "display_name": "creator",
        "max_items": 1000,
    }
    preview = client.post("/api/v1/subscriptions/preview", json=draft)
    assert preview.status_code == 200
    assert preview.json()["policy_summary"]["allow_full_history"] is False
    assert _row_counts(client) == (0, 0)
    created = client.post("/api/v1/subscriptions", json=draft)
    assert created.status_code == 201
    detail = client.get(f"/api/v1/subscriptions/{created.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["checkpoint_summary"]["bili_scan"] == {
        "version": 1,
        "status": "not_started",
        "feed": "ordinary_uploads",
        "unit_item_limit": 30,
        "max_list_attempts": 2,
        "history_complete": False,
        "state": None,
    }


@pytest.mark.parametrize(
    "mode",
    ["bound", "source_end", "restarted", "account", "author", "sha", "legacy", "malformed", "extra", "version"],
)
def test_bili_api_projects_only_verified_bound_scan_state(tmp_path: Path, mode: str) -> None:
    client = _client(tmp_path)
    account = _account(client, "bili", "bili-main")
    created = client.post(
        "/api/v1/subscriptions",
        json={
            "account_id": account["id"],
            "platform": "bili",
            "creator_remote_id": "123456",
            "display_name": "creator",
            "max_items": 1,
        },
    )
    assert created.status_code == 201
    settings = client.app.state.settings  # type: ignore[attr-defined]
    sha = load_mediacrawler_lock(settings.mediacrawler_lock_path).commit
    state = BiliScanState.initial(
        UUID(str(account["id"])),
        hashlib.sha256(b"123456").hexdigest(),
        sha,
    )
    page = BiliPage(1, 30, tuple(BiliIdentity(str(i), f"BV{i:010}", 1_700_000_000) for i in range(1, 31)))
    state = replace(
        state,
        next_lane="history",
        head=BiliLane(witness=page, index=1),
        last_unit=BiliUnitSummary("head", "item_limit", 1, 1, 1),
    )
    if mode in {"source_end", "restarted"}:
        state = replace(state, head=BiliLane(), last_unit=BiliUnitSummary("head", mode, 0, 1, 0))
    if mode == "account":
        state = replace(state, account_id=uuid4())
    elif mode == "author":
        state = replace(state, author_fingerprint_sha256="a" * 64)
    elif mode == "sha":
        state = replace(state, upstream_sha="a" * 40)
    cursor = {"value": state.to_cursor()}
    if mode == "legacy":
        cursor = {"value": "LEGACY_PRIVATE_SENTINEL"}
    elif mode == "malformed":
        cursor = {"value": 'bili-scan-v1:{"cookie":"PRIVATE_SENTINEL"}'}
    elif mode == "extra":
        cursor["private"] = "PRIVATE_SENTINEL"
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            subscription = session.get(Subscription, created.json()["id"])
            assert subscription is not None
            subscription.cursor = cursor
            subscription.cursor_version = 2 if mode == "version" else 1
            subscription.watermarked_at = datetime(2025, 1, 1, tzinfo=UTC)
            subscription.watermark_remote_ids = ["PRIVATE_WATERMARK_ID"]
            session.commit()
        response = client.get(f"/api/v1/subscriptions/{created.json()['id']}")
        assert response.status_code == 200
        projection = response.json()["checkpoint_summary"]["bili_scan"]
        assert projection["unit_item_limit"] == 1 and projection["history_complete"] is False
        if mode in {"bound", "source_end", "restarted"}:
            assert projection["status"] == "verified"
            assert projection["state"] == state.public_summary()
            assert projection["state"]["head_boundary_established"] is False
        else:
            assert projection["status"] == "unverified" and projection["state"] is None
        public = json.dumps(projection)
        assert set(projection) == {
            "version",
            "status",
            "feed",
            "unit_item_limit",
            "max_list_attempts",
            "history_complete",
            "state",
        }
        for private in (
            "PRIVATE",
            "BV0000000001",
            "author_fingerprint",
            sha,
            "head_candidate",
            "witness",
            "account_id",
            str(tmp_path),
        ):
            assert private not in public
    finally:
        database.dispose()


def test_concurrent_same_draft_creates_converge_idempotently(tmp_path: Path) -> None:
    client = _client(tmp_path)
    account_draft = {
        "platform": "bili",
        "display_name": "concurrent-account",
        "login_method": "qr",
    }

    with ThreadPoolExecutor(max_workers=8) as pool:
        account_responses = list(pool.map(lambda _: client.post("/api/v1/accounts", json=account_draft), range(8)))

    assert all(response.status_code == 201 for response in account_responses)
    accounts = [response.json() for response in account_responses]
    assert len({account["id"] for account in accounts}) == 1
    assert sum(account["created"] is True for account in accounts) == 1

    subscription_draft = {
        "account_id": accounts[0]["id"],
        "platform": "bili",
        "creator_remote_id": "123456",
        "display_name": "concurrent-creator",
        "allow_full_history": True,
    }
    with ThreadPoolExecutor(max_workers=8) as pool:
        subscription_responses = list(
            pool.map(lambda _: client.post("/api/v1/subscriptions", json=subscription_draft), range(8))
        )

    assert all(response.status_code == 201 for response in subscription_responses)
    subscriptions = [response.json() for response in subscription_responses]
    assert len({subscription["id"] for subscription in subscriptions}) == 1
    assert sum(subscription["created"] is True for subscription in subscriptions) == 1
    assert _row_counts(client) == (1, 1)


def test_preview_create_and_detail_return_only_safe_subscription_summaries(tmp_path: Path) -> None:
    client = _client(tmp_path)
    account = _account(client, "xhs", "xhs-main")
    reference = "env:MEDIA_SYNC_XHS_CREATOR"
    draft = {
        "account_id": account["id"],
        "platform": "xhs",
        "creator_remote_id": "5f1234567890abcdef123456",
        "display_name": "creator",
        "creator_reference_ref": reference,
        "interval_seconds": 3600,
        "max_items": 12,
        "request_delay_seconds": 8.5,
        "headless": False,
    }

    preview = client.post("/api/v1/subscriptions/preview", json=draft)

    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["exists"] is False
    assert preview_body["creator_remote_id"] == draft["creator_remote_id"]
    assert preview_body["policy_summary"] == {
        "adapter": "mediacrawler",
        "schema_version": 1,
        "allow_full_history": False,
        "request_delay_seconds": 8.5,
        "headless": False,
        "creator_reference_configured": True,
    }
    assert reference not in preview.text
    assert _row_counts(client) == (0, 0)

    created = client.post("/api/v1/subscriptions", json=draft)

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["created"] is True
    assert reference not in created.text
    listed = client.get("/api/v1/subscriptions")
    detail = client.get(f"/api/v1/subscriptions/{created_body['id']}")
    assert listed.status_code == 200
    assert detail.status_code == 200
    assert listed.json()[0]["policy_summary"] == preview_body["policy_summary"]
    assert detail.json()["policy_summary"] == preview_body["policy_summary"]
    assert set(detail.json()["checkpoint_summary"]) == {
        "has_checkpoint",
        "has_forward_cursor",
        "has_backfill_cursor",
        "revision",
        "cursor_version",
        "watermarked_at",
        "watermark_count",
        "last_success_at",
    }
    for response in (listed, detail):
        assert reference not in response.text
        assert "creator_input" not in response.text
        assert '"cursor"' not in response.text
        assert str(tmp_path) not in response.text


def test_qr_image_is_bound_to_the_exact_login_session(tmp_path: Path) -> None:
    client = _client(tmp_path)
    account = _account(client, "bili", "bili-main")
    settings = client.app.state.settings  # type: ignore[attr-defined]
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            first = LoginSessionRepository(session).create(
                account_id=str(account["id"]),
                method="qr",
                challenge_kind="qr",
            )
            first.status = "waiting_user"
            first_id = first.id

        qr_bytes = b"\x89PNG\r\n\x1a\nexact-session"
        qr_path = settings.resolved_mediacrawler_runtime_dir / "accounts" / "bili" / str(account["id"]) / "login-qr.png"
        qr_path.parent.mkdir(parents=True)
        qr_path.write_bytes(qr_bytes)

        exact = client.get(f"/api/v1/login-sessions/{first_id}/qr.png")
        compatible = client.get(f"/api/v1/accounts/{account['id']}/login-qr.png")
        unknown = client.get(f"/api/v1/login-sessions/{uuid4()}/qr.png")

        assert exact.status_code == 200
        assert exact.content == qr_bytes
        assert exact.headers["x-login-session-id"] == first_id
        assert compatible.status_code == 200
        assert compatible.headers["x-login-session-id"] == first_id
        assert unknown.status_code == 404

        with database.session() as session:
            stored = LoginSessionRepository(session).get(first_id)
            assert stored is not None
            stored.status = "expired"

        gone = client.get(f"/api/v1/login-sessions/{first_id}/qr.png")
        assert gone.status_code == 410
        assert gone.json() == {"code": "login_qr_gone", "login_session_id": first_id}
    finally:
        database.dispose()


def test_non_qr_session_cannot_claim_an_account_qr_file(tmp_path: Path) -> None:
    client = _client(tmp_path)
    account = _account(client, "xhs", "xhs-main")
    settings = client.app.state.settings  # type: ignore[attr-defined]
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            cookie_session = LoginSessionRepository(session).create(
                account_id=str(account["id"]),
                method="cookie",
            )
            cookie_session_id = cookie_session.id
        qr_path = settings.resolved_mediacrawler_runtime_dir / "accounts" / "xhs" / str(account["id"]) / "login-qr.png"
        qr_path.parent.mkdir(parents=True)
        qr_path.write_bytes(b"not-owned-by-cookie-session")

        exact = client.get(f"/api/v1/login-sessions/{cookie_session_id}/qr.png")
        compatible = client.get(f"/api/v1/accounts/{account['id']}/login-qr.png")

        assert exact.status_code == 404
        assert compatible.status_code == 404
        assert b"not-owned-by-cookie-session" not in exact.content
        assert b"not-owned-by-cookie-session" not in compatible.content
    finally:
        database.dispose()


def test_qr_route_revalidates_session_after_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path)
    account = _account(client, "bili", "bili-main")
    settings = client.app.state.settings  # type: ignore[attr-defined]
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            login_session = LoginSessionRepository(session).create(
                account_id=str(account["id"]),
                method="qr",
                challenge_kind="qr",
            )
            login_session.status = "waiting_user"
            login_session_id = login_session.id
        qr_path = settings.resolved_mediacrawler_runtime_dir / "accounts" / "bili" / str(account["id"]) / "login-qr.png"
        qr_path.parent.mkdir(parents=True)
        qr_path.write_bytes(b"qr-that-expires-during-read")
        original_open = Path.open
        transitioned = False

        def transition_then_open(path: Path, *args: object, **kwargs: object) -> object:
            nonlocal transitioned
            if path == qr_path and not transitioned:
                transitioned = True
                with database.session() as session:
                    stored = LoginSessionRepository(session).get(login_session_id)
                    assert stored is not None
                    stored.status = "expired"
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", transition_then_open)

        response = client.get(f"/api/v1/login-sessions/{login_session_id}/qr.png")

        assert transitioned is True
        assert response.status_code == 410
        assert b"qr-that-expires-during-read" not in response.content
    finally:
        database.dispose()


def test_qr_route_reconciles_an_expired_abandoned_session_before_serving(tmp_path: Path) -> None:
    client = _client(tmp_path)
    account = _account(client, "bili", "bili-main")
    settings = client.app.state.settings  # type: ignore[attr-defined]
    database = Database(settings.resolved_database_url)
    started_at = datetime.now(UTC) - timedelta(minutes=10)
    try:
        with database.session() as session:
            repository = LoginSessionRepository(session)
            started = repository.start_mediacrawler_qr(
                str(account["id"]),
                expires_at=started_at + timedelta(minutes=5),
                at=started_at,
            )
            repository.mark_waiting_user(started.id, at=started_at)
            login_session_id = started.id
        qr_path = settings.resolved_mediacrawler_runtime_dir / "accounts" / "bili" / str(account["id"]) / "login-qr.png"
        qr_path.parent.mkdir(parents=True)
        qr_path.write_bytes(b"expired-qr-must-not-be-served")

        exact = client.get(f"/api/v1/login-sessions/{login_session_id}/qr.png")
        compatible = client.get(f"/api/v1/accounts/{account['id']}/login-qr.png")

        assert exact.status_code == 410
        assert compatible.status_code == 410
        assert b"expired-qr-must-not-be-served" not in exact.content
        assert b"expired-qr-must-not-be-served" not in compatible.content
        with database.session() as session:
            recovered = LoginSessionRepository(session).get(login_session_id)
            assert recovered is not None and recovered.status == "expired"
    finally:
        database.dispose()


def test_failed_login_preflight_allocates_no_operation_or_child(tmp_path: Path) -> None:
    client = _client(tmp_path)
    account = _account(client, "bili", "bili-main")
    settings = client.app.state.settings  # type: ignore[attr-defined]
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            LoginSessionRepository(session).create(account_id=str(account["id"]), method="qr")
    finally:
        database.dispose()

    preflight = client.get(
        f"/api/v1/accounts/{account['id']}/login-preflight",
        params={"accept_mediacrawler_license": True},
    )
    started = client.post(
        f"/api/v1/accounts/{account['id']}/login",
        json={"enable_mediacrawler": True, "accept_mediacrawler_license": True},
    )

    assert preflight.status_code == 200
    assert preflight.json()["code"] == "account_login_busy"
    assert str(tmp_path) not in preflight.text
    assert started.status_code == 409
    assert started.json()["detail"] == "account_login_busy"
    assert client.get("/api/v1/operations").json() == []
