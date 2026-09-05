from __future__ import annotations

import io
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from _api_client import authenticated_test_client
from PIL import Image
from sqlalchemy import select

from media_sync.config import Settings
from media_sync.infrastructure.db import AccountRepository, Database
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.infrastructure.db.models import Account, Author, CreatorProfile, LoginSession, Operation
from media_sync.integrations.mediacrawler.creator_profile_runner import (
    MediaCrawlerCreatorProfile,
    MediaCrawlerCreatorProfileRequest,
    MediaCrawlerCreatorProfileResult,
    MediaCrawlerCreatorProfileStatus,
)


class Runner:
    def __init__(self) -> None:
        self.calls: list[MediaCrawlerCreatorProfileRequest] = []
        self.name = "平台上的准确昵称"
        self.status = MediaCrawlerCreatorProfileStatus.SUCCEEDED
        self.wrong_identity = False
        self.avatar: str | None = None
        self.hook: Any = None

    def run(self, request: MediaCrawlerCreatorProfileRequest, *, cancellation: threading.Event | None = None) -> Any:
        self.calls.append(request)
        if self.hook:
            self.hook(request, cancellation)
        return MediaCrawlerCreatorProfileResult(
            self.status,
            uuid4() if self.wrong_identity else request.account_id,
            request.platform,
            request.creator_remote_id,
            request.request_id,
            upstream_sha="a" * 40 if self.status.value == "succeeded" else None,
            profile=MediaCrawlerCreatorProfile(request.creator_remote_id, self.name, self.avatar)
            if self.status.value == "succeeded"
            else None,
        )


@pytest.fixture
def environment(tmp_path: Path) -> Any:
    settings = Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "library",
        job_dir=tmp_path / "jobs",
        _env_file=None,
    )
    upgrade_database(settings.resolved_database_url)
    database = Database(settings.resolved_database_url)
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            display_name="account",
            adapter="mediacrawler",
            login_method="saved_session",
            auth_status="authenticated",
        )
        account_id = account.id
    try:
        with authenticated_test_client(settings) as client:
            runner = Runner()
            client.app.state.creator_profile_service.runner = runner
            client.app.state.creator_profile_service.avatar_fetcher = lambda _: None
            yield client, database, account_id, runner
    finally:
        database.dispose()


def _body(**extra: object) -> dict[str, object]:
    return {
        "platform": "bili",
        "creator_remote_id": "252671524",
        "frontend_generation": str(uuid4()),
        "enable_mediacrawler": True,
        "accept_mediacrawler_license": True,
        **extra,
    }


def _wait(client: Any, operation_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/creator-lookups/{operation_id}")
        assert response.status_code == 200, response.text
        value = response.json()
        if value["state"] not in {"queued", "running"}:
            return value
        time.sleep(0.01)
    raise AssertionError("lookup did not terminate")


def _lookup(client: Any, account_id: str, **extra: object) -> dict[str, Any]:
    response = client.post(f"/api/v1/accounts/{account_id}/creator-lookups", json=_body(**extra))
    assert response.status_code == 202, response.text
    return _wait(client, response.json()["operation_id"])


def test_real_operation_service_receipt_creates_without_manual_name(environment: Any) -> None:
    client, database, account_id, runner = environment
    result = _lookup(client, account_id)
    assert result["state"] == "succeeded", result
    assert result["profile_source"] == "lookup_result"
    assert result["profile"]["nickname"] == runner.name
    assert result["profile"]["profile_url"] == "https://space.bilibili.com/252671524"
    assert result["lookup"]["result_profile_revision"] == result["profile"]["revision"] == 1
    assert len(runner.calls) == 1
    draft = {
        "account_id": account_id,
        "platform": "bili",
        "creator_remote_id": "252671524",
        "profile_lookup_id": result["operation_id"],
        "allow_full_history": True,
    }
    preview = client.post("/api/v1/subscriptions/preview", json=draft)
    assert preview.status_code == 200, preview.text
    assert preview.json()["creator_display_name"] == runner.name
    assert preview.json()["local_alias"] is None
    assert preview.json()["profile_lookup_id"] == result["operation_id"]
    created = client.post("/api/v1/subscriptions", json=draft)
    assert created.status_code == 201, created.text
    rows = client.get("/api/v1/subscriptions").json()
    assert rows[0]["creator_profile"] == result["profile"]
    assert rows[0]["local_alias"] is None
    with database.session() as session:
        assert session.scalar(select(LoginSession)) is None
        account = session.get(Account, account_id)
        assert account.auth_status == "authenticated" and account.auth_revision == 0
        operation = session.get(Operation, result["operation_id"])
        assert set(operation.result_summary) == {"profile_id", "generation", "revision"}
        assert runner.name not in str(operation.result_summary)


def test_alias_does_not_rename_shared_author_and_stale_receipt_rejected(environment: Any) -> None:
    client, database, account_id, runner = environment
    first = _lookup(client, account_id)
    draft = {
        "account_id": account_id,
        "platform": "bili",
        "creator_remote_id": "252671524",
        "profile_lookup_id": first["operation_id"],
        "local_alias": "我的本地备注",
        "allow_full_history": True,
    }
    assert client.post("/api/v1/subscriptions", json=draft).status_code == 201
    runner.name = "平台新昵称"
    second = _lookup(client, account_id)
    stale = client.post("/api/v1/subscriptions", json=draft)
    assert stale.status_code in {400, 409}
    draft["profile_lookup_id"] = second["operation_id"]
    draft["local_alias"] = "另一个备注"
    assert client.post("/api/v1/subscriptions", json=draft).status_code == 201
    with database.session() as session:
        assert session.scalar(select(Author)).display_name == "平台上的准确昵称"
    row = client.get("/api/v1/subscriptions").json()[0]
    assert row["local_alias"] == "另一个备注" and row["creator_profile"]["nickname"] == "平台新昵称"


@pytest.mark.parametrize("status", ["auth_expired", "account_busy", "result_invalid", "timed_out", "cleanup_failed"])
def test_failures_do_not_login_or_publish(environment: Any, status: str) -> None:
    client, database, account_id, runner = environment
    runner.status = MediaCrawlerCreatorProfileStatus(status)
    result = _lookup(client, account_id)
    assert result["state"] == "failed_terminal" and result["profile"] is None
    with database.session() as session:
        profile = session.scalar(select(CreatorProfile))
        assert profile.revision == 0 and profile.nickname is None
        assert session.scalar(select(LoginSession)) is None
        assert session.get(Account, account_id).auth_status == "authenticated"


def test_wrong_identity_and_auth_change_cannot_publish(environment: Any) -> None:
    client, database, account_id, runner = environment
    runner.wrong_identity = True
    assert _lookup(client, account_id)["error_code"] == "creator_profile_identity_mismatch"
    runner.wrong_identity = False

    def changed(*_: object) -> None:
        with database.session() as session:
            account = session.get(Account, account_id)
            account.auth_revision += 2  # Equal visible values with a real ABA generation change.

    runner.hook = changed
    assert _lookup(client, account_id)["error_code"] == "creator_profile_auth_changed"
    with database.session() as session:
        assert session.scalar(select(CreatorProfile)).revision == 0


def test_avatar_is_same_origin_exact_revision_and_failure_preserves_bytes(environment: Any) -> None:
    client, _, account_id, runner = environment
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
    png = buffer.getvalue()
    client.app.state.creator_profile_service.avatar_fetcher = lambda _: png
    first = _lookup(client, account_id)
    url = first["profile"]["avatar_url"]
    image = client.get(url)
    assert image.status_code == 200 and image.content == png
    assert image.headers["content-type"] == "image/png"
    assert image.headers["cross-origin-resource-policy"] == "same-origin"
    assert image.headers["cache-control"] == "private, no-store"
    assert client.get(url[:-1] + "2").status_code == 404
    runner.name = "new nickname"
    client.app.state.creator_profile_service.avatar_fetcher = lambda _: None
    second = _lookup(client, account_id)
    assert second["profile"]["avatar_state"] == "retained"
    assert second["profile"]["avatar_url"] == url
    assert client.get(url).content == png


@pytest.mark.parametrize(
    "extra,expected",
    [
        ({"platform": "dy"}, 400),
        ({"creator_remote_id": "https://space.bilibili.com/2"}, 422),
        ({"creator_remote_id": "0002"}, 400),
        ({"enable_mediacrawler": False}, 400),
        ({"accept_mediacrawler_license": False}, 400),
        ({"arbitrary_url": "http://127.0.0.1"}, 422),
    ],
)
def test_closed_request_before_runner(environment: Any, extra: dict[str, object], expected: int) -> None:
    client, _, account_id, runner = environment
    response = client.post(f"/api/v1/accounts/{account_id}/creator-lookups", json=_body(**extra))
    assert response.status_code == expected, response.text
    assert runner.calls == []


def test_idempotent_replay_and_wrong_scope_receipt(environment: Any) -> None:
    client, database, account_id, runner = environment
    body = _body()
    headers = {"Idempotency-Key": str(uuid4())}
    path = f"/api/v1/accounts/{account_id}/creator-lookups"
    first = client.post(path, json=body, headers=headers).json()
    _wait(client, first["operation_id"])
    again = client.post(path, json=body, headers=headers).json()
    assert again["operation_id"] == first["operation_id"] and again["replayed"] is True
    assert len(runner.calls) == 1
    with database.session() as session:
        other = AccountRepository(session).create(
            platform="bili",
            display_name="other",
            adapter="mediacrawler",
            login_method="saved_session",
            auth_status="authenticated",
        )
        other_id = other.id
    bad = client.post(
        "/api/v1/subscriptions",
        json={
            "account_id": other_id,
            "platform": "bili",
            "creator_remote_id": "252671524",
            "profile_lookup_id": first["operation_id"],
            "allow_full_history": True,
        },
    )
    assert bad.status_code in {400, 409}
    assert client.get("/api/v1/subscriptions").json() == []


def test_logout_protects_lookup_report_and_avatar(environment: Any) -> None:
    client, _, account_id, runner = environment
    client.cookies.clear()
    paths = [f"/api/v1/creator-lookups/{uuid4()}", f"/api/v1/creator-profiles/{uuid4()}/avatar/1"]
    for path in paths:
        assert client.get(path).status_code == 401
    assert client.post(f"/api/v1/accounts/{account_id}/creator-lookups", json=_body()).status_code == 401
    assert runner.calls == []


def test_cancel_during_runner_never_publishes(environment: Any) -> None:
    client, database, account_id, runner = environment
    entered = threading.Event()
    release = threading.Event()

    def blocked(_: object, cancellation: threading.Event) -> None:
        entered.set()
        assert release.wait(5)

    runner.hook = blocked
    response = client.post(f"/api/v1/accounts/{account_id}/creator-lookups", json=_body())
    assert response.status_code == 202
    operation_id = response.json()["operation_id"]
    try:
        assert entered.wait(5)
        cancelled = client.post(f"/api/v1/operations/{operation_id}/cancel")
        assert cancelled.status_code in {200, 202}, cancelled.text
    finally:
        release.set()
    result = _wait(client, operation_id)
    assert result["state"] == "cancelled" and result["profile"] is None
    with database.session() as session:
        assert session.scalar(select(CreatorProfile)).revision == 0


def test_lookup_error_projection_never_reflects_arbitrary_stored_error(environment: Any) -> None:
    client, database, account_id, runner = environment
    runner.status = MediaCrawlerCreatorProfileStatus.TEMPORARY
    result = _lookup(client, account_id)
    with database.session() as session:
        operation = session.get(Operation, result["operation_id"])
        operation.error_code = "private_cookie_sentinal_from_untrusted_error"
    response = client.get(f"/api/v1/creator-lookups/{result['operation_id']}")
    assert response.status_code == 200
    assert response.json()["error_code"] == "creator_profile_failed"
    assert "private_cookie" not in response.text


def _weibo_account(database: Database) -> str:
    with database.session() as session:
        return (
            AccountRepository(session)
            .create(
                platform="wb",
                display_name=f"Weibo {uuid4()}",
                adapter="mediacrawler",
                login_method="saved_session",
                auth_status="authenticated",
            )
            .id
        )


def test_weibo_profile_lookup_is_independent_of_capture_ack_and_preserves_author_path(environment: Any) -> None:
    client, database, bili_account_id, runner = environment
    wb_account_id = _weibo_account(database)
    bili = _lookup(client, bili_account_id)
    runner.name = "微博平台昵称"
    wb = _lookup(client, wb_account_id, platform="wb")
    assert wb["state"] == "succeeded", wb
    assert wb["profile"]["platform"] == "wb" and wb["profile"]["nickname"] == runner.name
    assert wb["profile"]["profile_url"] == "https://weibo.com/u/252671524"
    assert wb["profile"]["id"] != bili["profile"]["id"]
    # A lookup needs no full-history acknowledgement; actual capture policy does.
    draft = {
        "account_id": wb_account_id,
        "platform": "wb",
        "creator_remote_id": "252671524",
        "profile_lookup_id": wb["operation_id"],
    }
    assert client.post("/api/v1/subscriptions/preview", json=draft).status_code == 400
    draft["allow_full_history"] = True
    response = client.post("/api/v1/subscriptions", json=draft)
    assert response.status_code == 201, response.text
    assert response.json()["creator_display_name"] == "微博平台昵称"
    runner.name = "微博新昵称"
    newer = _lookup(client, wb_account_id, platform="wb")
    draft.update(profile_lookup_id=newer["operation_id"], local_alias="我的备注")
    assert client.post("/api/v1/subscriptions", json=draft).status_code == 201
    row = client.get("/api/v1/subscriptions").json()[0]
    assert row["creator_profile"]["nickname"] == "微博新昵称" and row["local_alias"] == "我的备注"
    with database.session() as session:
        assert session.scalar(select(Author)).display_name == "微博平台昵称"
        assert session.scalar(select(LoginSession)) is None
        account = session.get(Account, wb_account_id)
        assert account.auth_revision == 0 and account.auth_status == "authenticated"


def test_weibo_cannot_borrow_bili_or_other_account_receipt(environment: Any) -> None:
    client, database, bili_account_id, _ = environment
    bili = _lookup(client, bili_account_id)
    account = _weibo_account(database)
    wb = _lookup(client, account, platform="wb")
    other = _weibo_account(database)
    for account_id, receipt in ((account, bili["operation_id"]), (other, wb["operation_id"])):
        response = client.post(
            "/api/v1/subscriptions",
            json={
                "account_id": account_id,
                "platform": "wb",
                "creator_remote_id": "252671524",
                "allow_full_history": True,
                "profile_lookup_id": receipt,
            },
        )
        assert response.status_code in {400, 409}, response.text
    assert client.get("/api/v1/subscriptions").json() == []


@pytest.mark.parametrize("failure", ["auth_expired", "result_invalid", "timed_out", "auth_changed"])
def test_weibo_failed_refresh_preserves_previous_profile_and_avatar(environment: Any, failure: str) -> None:
    client, database, _, runner = environment
    account = _weibo_account(database)
    output = io.BytesIO()
    Image.new("RGB", (1, 1), "red").save(output, format="PNG")
    client.app.state.creator_profile_service.avatar_fetcher = lambda _: output.getvalue()
    first = _lookup(client, account, platform="wb")
    assert first["state"] == "succeeded", first
    if failure == "auth_changed":

        def change(*_: object) -> None:
            with database.session() as session:
                session.get(Account, account).auth_revision += 1

        runner.hook = change
    else:
        runner.status = MediaCrawlerCreatorProfileStatus(failure)
    second = _lookup(client, account, platform="wb")
    assert second["state"] == "failed_terminal", second
    with database.session() as session:
        profile = session.get(CreatorProfile, first["profile"]["id"])
        assert profile.nickname == runner.name and profile.revision == 1
        assert profile.avatar_revision == 1 and profile.avatar_png == output.getvalue()
        assert session.get(Account, account).auth_status == "authenticated"


@pytest.mark.parametrize("platform", ["bili", "wb"])
@pytest.mark.parametrize("wrong_platform", [False, True])
def test_avatar_network_scope_is_bound_to_profile_platform(
    environment: Any, platform: str, wrong_platform: bool
) -> None:
    client, database, bili_account_id, runner = environment
    account = bili_account_id if platform == "bili" else _weibo_account(database)
    urls = {
        "bili": "https://i1.hdslb.com/bfs/face/" + "a" * 40 + ".jpg",
        "wb": "https://tvax1.sinaimg.cn/crop.0.0.180.180.180/synthetic.jpg",
    }
    other = "wb" if platform == "bili" else "bili"
    runner.avatar = urls[other if wrong_platform else platform]
    received = []
    client.app.state.creator_profile_service.avatar_fetcher = lambda url: received.append(url)
    result = _lookup(client, account, platform=platform)
    assert result["state"] == "succeeded", result
    assert result["profile"]["nickname"] == runner.name
    assert received == ([] if wrong_platform else [urls[platform]])
