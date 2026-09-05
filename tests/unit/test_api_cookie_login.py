from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from _api_client import authenticated_test_client
from sqlalchemy import select

from media_sync.config import Settings
from media_sync.infrastructure.db import AccountRepository, Database
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.infrastructure.db.models import Account, LoginSession, Operation
from media_sync.integrations.mediacrawler.cookie_login import CookieLoginRequest, CookieLoginResult
from media_sync.integrations.mediacrawler.creator_profile_runner import (
    MediaCrawlerCreatorProfile,
    MediaCrawlerCreatorProfileResult,
    MediaCrawlerCreatorProfileStatus,
)
from media_sync.security.secrets import SecretResolver

SENTINEL = "SESSDATA=synthetic-private-cookie-sentinel==; DedeUserID=123"


class Runner:
    def __init__(self) -> None:
        self.calls: list[CookieLoginRequest] = []
        self.status = "authenticated"
        self.wrong_identity = False
        self.hook: Any = None

    def run(self, request: CookieLoginRequest, *, cancellation: threading.Event | None = None) -> CookieLoginResult:
        self.calls.append(request)
        if self.hook:
            self.hook(request, cancellation)
        return CookieLoginResult(
            self.status,
            uuid4() if self.wrong_identity else request.account_id,
            request.platform,
            request.operation_id,
            "a" * 40 if self.status == "authenticated" else None,
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
            display_name="unchanged account",
            adapter="mediacrawler",
            login_method="saved_session",
            auth_status="authenticated",
        )
        account_id = account.id
    try:
        with authenticated_test_client(settings) as client:
            runner = Runner()
            client.app.state.cookie_login_service.runner = runner
            yield client, database, account_id, runner, settings
    finally:
        database.dispose()


def body(**changes: object) -> dict[str, object]:
    return {
        "cookie": SENTINEL,
        "platform": "bili",
        "expected_auth_revision": 0,
        "frontend_generation": str(uuid4()),
        "enable_mediacrawler": True,
        "accept_mediacrawler_license": True,
        **changes,
    }


def wait(client: Any, operation_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/operations/{operation_id}")
        assert response.status_code == 200
        result = response.json()
        if result["state"] not in {"queued", "running"}:
            return result
        time.sleep(0.01)
    raise AssertionError("cookie operation did not terminate")


def submit(environment: Any, payload: dict[str, object] | None = None) -> dict[str, Any]:
    client, _, account_id, _, _ = environment
    response = client.post(f"/api/v1/accounts/{account_id}/cookie-login", json=payload or body())
    assert response.status_code == 202, response.text
    return wait(client, response.json()["operation_id"])


def original(database: Database, account_id: str) -> tuple[object, ...]:
    with database.session() as session:
        row = session.get(Account, account_id)
        assert row is not None
        return (
            row.login_method,
            row.auth_status,
            row.credential_ref,
            row.auth_revision,
            row.auth_updated_at,
            row.profile_path,
        )


def test_remote_success_publishes_exact_cookie_without_changing_qr_or_exposing_secret(environment: Any) -> None:
    client, database, account_id, runner, settings = environment
    result = submit(environment)
    assert result["state"] == "succeeded", result
    assert result["result"] == {
        "account_id": account_id,
        "auth_status": "authenticated",
        "login_method": "cookie",
        "auth_revision": 1,
    }
    assert len(runner.calls) == 1 and runner.calls[0].cookie.reveal() == SENTINEL
    assert SENTINEL not in repr(runner.calls)
    with database.session() as session:
        account = session.get(Account, account_id)
        assert account is not None and account.auth_revision == 1 and account.login_method == "cookie"
        assert account.display_name == "unchanged account" and account.profile_path is None
        reference = account.credential_ref
        assert reference is not None and reference.startswith("managed:")
        assert session.scalar(select(LoginSession)) is None
        operation = session.get(Operation, result["id"])
        assert operation.state == "succeeded" and operation.result_summary == result["result"]
    resolver = SecretResolver.local(
        file_root=settings.resolved_secret_file_dir, managed_root=settings.state_dir / "credentials"
    )
    assert resolver.resolve(reference).reveal() == SENTINEL
    # A real new interpreter resolves the persisted version, without placing
    # the value in argv, the child environment, or stdout.
    script = (
        "import hashlib,sys;from pathlib import Path;from media_sync.security.secrets import SecretResolver;"
        "resolver=SecretResolver.local(file_root=Path(sys.argv[1]),managed_root=Path(sys.argv[2]));"
        "print(hashlib.sha256(resolver.resolve(sys.argv[3]).reveal().encode()).hexdigest())"
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(settings.resolved_secret_file_dir),
            str(settings.state_dir / "credentials"),
            reference,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert probe.returncode == 0
    assert probe.stdout.strip() == hashlib.sha256(SENTINEL.encode()).hexdigest()
    assert SENTINEL not in probe.stderr
    public = (
        json.dumps(result)
        + client.get("/api/v1/accounts").text
        + client.get(f"/api/v1/accounts/{account_id}/login-status").text
    )
    public += client.get(f"/api/v1/operations/{result['id']}/events").text
    assert SENTINEL not in public and reference not in public
    assert client.get("/api/v1/accounts").json()[0]["auth_revision"] == 1
    for file in settings.state_dir.glob("*.sqlite3*"):
        assert SENTINEL.encode() not in file.read_bytes()


@pytest.mark.parametrize(
    "status",
    ["rejected", "verification_unavailable", "timed_out", "configuration_invalid", "result_invalid", "cancelled"],
)
def test_candidate_failure_preserves_complete_original_auth(environment: Any, status: str) -> None:
    _, database, account_id, runner, settings = environment
    before = original(database, account_id)
    runner.status = status
    result = submit(environment)
    assert result["state"] == ("cancelled" if status == "cancelled" else "failed_terminal")
    assert original(database, account_id) == before
    assert not (settings.state_dir / "credentials").exists()


def test_wrong_identity_never_publishes(environment: Any) -> None:
    _, database, account_id, runner, settings = environment
    before = original(database, account_id)
    runner.wrong_identity = True
    result = submit(environment)
    assert result["state"] == "failed_terminal" and result["error_code"] == "cookie_login_result_invalid"
    assert original(database, account_id) == before
    assert not (settings.state_dir / "credentials").exists()


def test_auth_revision_change_during_validation_rejects_publication(environment: Any) -> None:
    _, database, account_id, runner, settings = environment

    def change(_request: Any, _cancellation: Any) -> None:
        with database.session() as session:
            session.get(Account, account_id).auth_revision += 1

    runner.hook = change
    result = submit(environment)
    assert result["state"] == "failed_terminal" and result["error_code"] == "cookie_login_conflict"
    after = original(database, account_id)
    assert after[:3] == ("saved_session", "authenticated", None) and after[3] == 1
    # A validated immutable orphan may remain after a rejected DB commit; it
    # is not referenced and is never substituted for the prior credential.
    assert (settings.state_dir / "credentials").is_dir()


def test_cancelled_remote_completion_does_not_save(environment: Any) -> None:
    _, database, account_id, runner, settings = environment
    before = original(database, account_id)
    runner.hook = lambda _request, cancellation: cancellation.set()
    result = submit(environment)
    assert result["state"] == "cancelled" and original(database, account_id) == before
    assert not (settings.state_dir / "credentials").exists()


@pytest.mark.parametrize("field", ["target_id", "target_type"])
def test_operation_target_drift_cannot_publish_original_account(environment: Any, field: str) -> None:
    _, database, account_id, runner, _ = environment
    before = original(database, account_id)

    def drift(request: Any, _cancellation: Any) -> None:
        with database.session() as session:
            operation = session.get(Operation, str(request.operation_id))
            setattr(operation, field, str(uuid4()) if field == "target_id" else "author")

    runner.hook = drift
    result = submit(environment)
    assert result["state"] == "failed_terminal" and result["error_code"] == "cookie_login_conflict"
    assert original(database, account_id) == before


def test_candidate_does_not_run_without_current_csrf(environment: Any) -> None:
    client, database, account_id, runner, _ = environment
    before = original(database, account_id)
    response = client.post(
        f"/api/v1/accounts/{account_id}/cookie-login", json=body(), headers={"X-Media-Sync-CSRF": "invalid"}
    )
    assert response.status_code == 403 and SENTINEL not in response.text
    assert not runner.calls and original(database, account_id) == before


def test_idempotency_replay_is_safe_and_changed_candidate_conflicts(environment: Any) -> None:
    client, _, account_id, runner, _ = environment
    payload = body()
    headers = {"Idempotency-Key": str(uuid4())}
    route = f"/api/v1/accounts/{account_id}/cookie-login"
    first = client.post(route, json=payload, headers=headers)
    assert first.status_code == 202
    assert wait(client, first.json()["operation_id"])["state"] == "succeeded"
    replay = client.post(route, json=payload, headers=headers)
    assert replay.status_code == 202 and replay.json()["operation_id"] == first.json()["operation_id"]
    rejected = client.post(route, json={**payload, "cookie": "SESSDATA=different=="}, headers=headers)
    assert rejected.status_code == 409 and len(runner.calls) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"cookie": "a=x\r\nb=y"},
        {"cookie": "a=x; a=y"},
        {"cookie": "[]"},
        {"cookie": "a=x; Domain=example.test"},
        {"cookie": 123},
        {"cookie": "a=" + "x" * 16384},
        {"expected_auth_revision": True},
        {"expected_auth_revision": -1},
        {"expected_auth_revision": 2**63},
        {"platform": "invalid"},
        {"frontend_generation": "INVALID"},
        {"enable_mediacrawler": 1},
        {"accept_mediacrawler_license": "true"},
        {SENTINEL: "unexpected"},
    ],
)
def test_invalid_requests_never_reflect_values_or_dynamic_field_names(
    environment: Any, changes: dict[str, object]
) -> None:
    client, database, account_id, runner, _ = environment
    response = client.post(f"/api/v1/accounts/{account_id}/cookie-login", json=body(**changes))
    assert response.status_code == 400 and response.json() == {"detail": "cookie_login_request_invalid"}
    assert SENTINEL not in response.text and not runner.calls
    assert original(database, account_id)[:4] == ("saved_session", "authenticated", None, 0)


@pytest.mark.parametrize("mode", ["duplicate", "too_large", "non_json", "constant", "nested", "encoding"])
def test_wire_shape_rejection_is_fixed_and_bounded(environment: Any, mode: str) -> None:
    client, _, account_id, runner, _ = environment
    raw = json.dumps(body())
    content_type = "application/json"
    headers = {}
    if mode == "duplicate":
        raw = raw[:-1] + ',"cookie":"private-duplicate"}'
    if mode == "too_large":
        raw = " " * 32769
    if mode == "non_json":
        content_type = "text/plain"
    if mode == "constant":
        raw = raw.replace('"expected_auth_revision": 0', '"expected_auth_revision": NaN')
    if mode == "nested":
        raw = "[" * 2000 + "]" * 2000
    if mode == "encoding":
        headers["Content-Encoding"] = "gzip"
    response = client.post(
        f"/api/v1/accounts/{account_id}/cookie-login", content=raw, headers={"Content-Type": content_type, **headers}
    )
    assert response.status_code in {400, 413, 415}
    assert set(response.json()) == {"detail"} and SENTINEL not in response.text and not runner.calls


@pytest.mark.parametrize(
    "change,code",
    [
        ({"enable_mediacrawler": False}, "mediacrawler_not_enabled"),
        ({"accept_mediacrawler_license": False}, "license_acknowledgement_required"),
        ({"expected_auth_revision": 1}, "cookie_login_conflict"),
        ({"platform": "wb"}, "cookie_login_conflict"),
    ],
)
def test_gates_do_not_call_runner(environment: Any, change: dict[str, object], code: str) -> None:
    client, _, account_id, runner, _ = environment
    response = client.post(f"/api/v1/accounts/{account_id}/cookie-login", json=body(**change))
    assert response.status_code in {400, 409} and response.json() == {"detail": code}
    assert not runner.calls


def test_capabilities_distinguish_supported_remote_proofs(environment: Any) -> None:
    client, _, _, _, _ = environment
    rows = client.get("/api/v1/platform-capabilities").json()["platforms"]
    assert {row["platform"] for row in rows if row["pasted_cookie_login"]} == {"bili", "xhs", "wb", "zhihu", "tieba"}
    assert len(rows) == 7


@pytest.mark.parametrize("platform", ["bili", "wb", "zhihu"])
def test_saved_cookie_feeds_profile_receipt_and_subscription(environment: Any, platform: str) -> None:
    client, database, account_id, _, _ = environment
    with database.session() as session:
        session.get(Account, account_id).platform = platform
    assert submit(environment, body(platform=platform))["state"] == "succeeded"
    calls = []

    class ProfileRunner:
        def run(self, request: Any, **kwargs: Any) -> MediaCrawlerCreatorProfileResult:
            assert request.cookie.reveal() == SENTINEL
            calls.append(request)
            return MediaCrawlerCreatorProfileResult(
                MediaCrawlerCreatorProfileStatus.SUCCEEDED,
                request.account_id,
                request.platform,
                request.creator_remote_id,
                request.request_id,
                "a" * 40,
                MediaCrawlerCreatorProfile(request.creator_remote_id, "Remote nickname", None),
            )

    client.app.state.creator_profile_service.runner = ProfileRunner()
    client.app.state.creator_profile_service.avatar_fetcher = lambda _: None
    response = client.post(
        f"/api/v1/accounts/{account_id}/creator-lookups",
        json={
            "platform": platform,
            "creator_remote_id": "123",
            "frontend_generation": str(uuid4()),
            "enable_mediacrawler": True,
            "accept_mediacrawler_license": True,
        },
    )
    assert response.status_code == 202, response.text
    operation_id = response.json()["operation_id"]
    assert wait(client, operation_id)["state"] == "succeeded"
    created = client.post(
        "/api/v1/subscriptions",
        json={
            "account_id": account_id,
            "platform": platform,
            "creator_remote_id": "123",
            "profile_lookup_id": operation_id,
            "allow_full_history": True,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["creator_display_name"] == "Remote nickname" and len(calls) == 1
    assert original(database, account_id)[3] == 1


@pytest.mark.parametrize("failure", ["rejected", "result_invalid", "verification_unavailable", "cancelled"])
def test_tieba_saved_cookie_is_private_and_failed_replacement_retains_exact_auth(
    environment: Any, failure: str
) -> None:
    client, database, account_id, runner, settings = environment
    candidate = "BDUSS=" + "S" * 192 + "; STOKEN=synthetic=="
    with database.session() as session:
        session.get(Account, account_id).platform = "tieba"
    first = submit(environment, body(platform="tieba", cookie=candidate))
    assert first["state"] == "succeeded", first
    before = original(database, account_id)
    reference = before[2]
    assert isinstance(reference, str) and reference.startswith("managed:")
    resolver = SecretResolver.local(
        file_root=settings.resolved_secret_file_dir, managed_root=settings.state_dir / "credentials"
    )
    assert resolver.resolve(reference).reveal() == candidate
    runner.status = failure
    second = submit(environment, body(platform="tieba", cookie="BDUSS=" + "F" * 192, expected_auth_revision=1))
    assert second["state"] in {"failed_terminal", "cancelled"}, second
    assert original(database, account_id) == before
    assert resolver.resolve(reference).reveal() == candidate
    public = json.dumps(first) + json.dumps(second) + client.get("/api/v1/accounts").text
    public += client.get(f"/api/v1/operations/{first['id']}/events").text
    assert candidate not in public and reference not in public
    with database.session() as session:
        assert session.scalar(select(LoginSession)) is None
    for path in settings.state_dir.glob("*.sqlite3*"):
        assert candidate.encode() not in path.read_bytes()
