"""Execution 0052 durable operation API, cancellation and SSE contracts."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select

import media_sync.interfaces.api as api_module
from media_sync.application import DurableSubjectRef, OperationExecutionContext
from media_sync.application.authentication import AccountLoginOutcome
from media_sync.config import Settings
from media_sync.domain import AuthStatus, Platform
from media_sync.infrastructure.db import Database, Operation, OperationEventStreamState, OperationRepository
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.infrastructure.db.models import Asset, Content
from media_sync.integrations.mediacrawler import MediaCrawlerLoginStatus
from media_sync.scheduler import PipelineWorkerResult, SchedulerWorkerResult

_FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "exclusive_key",
        "idempotency_key",
        "idempotency_key_hash",
        "lease_expires_at",
        "lease_owner",
        "lease_token",
        "request_fingerprint",
        "requested_by",
        "revision",
        "worker_id",
    }
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "library",
        job_dir=tmp_path / "jobs",
        mediacrawler_runtime_dir=tmp_path / "mediacrawler",
    )


def _client(settings: Settings) -> TestClient:
    upgrade_database(settings.resolved_database_url)
    return TestClient(api_module.create_api_app(settings))


def _wait_terminal(client: TestClient, operation_id: str, *, timeout: float = 5.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/operations/{operation_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["state"] not in {"queued", "running"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("operation did not reach a terminal state")


def _assert_safe_public_payload(value: object, *sentinels: str) -> None:
    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            assert not (_FORBIDDEN_PUBLIC_KEYS & set(item))
            for child in item.values():
                visit(child)
        elif isinstance(item, list | tuple):
            for child in item:
                visit(child)

    visit(value)
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True)
    for sentinel in sentinels:
        assert sentinel not in encoded


def _assert_cancel_event_chain(client: TestClient, operation_id: str) -> None:
    response = client.get(f"/api/v1/operations/{operation_id}/events", params={"limit": 200})
    assert response.status_code == 200
    cancel_codes = [
        event["event_code"] for event in response.json() if event["event_code"].startswith("operation_cancel")
    ]
    assert cancel_codes == [
        "operation_cancel_requested",
        "operation_cancel_observed",
        "operation_cancelled",
    ]


def _create_account_subscription_asset(client: TestClient, settings: Settings) -> tuple[str, str, str]:
    account = client.post(
        "/api/v1/accounts",
        json={"platform": "bili", "display_name": "operations", "login_method": "qr"},
    ).json()
    subscription = client.post(
        "/api/v1/subscriptions",
        json={
            "account_id": account["id"],
            "platform": "bili",
            "creator_remote_id": "24680",
            "display_name": "operation-author",
            "allow_full_history": True,
        },
    ).json()
    asset_id = str(uuid4())
    content_id = "operation-api-content"
    at = datetime(2026, 9, 4, 12, tzinfo=UTC)
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            session.execute(
                insert(Content).values(
                    id=content_id,
                    author_id=subscription["author_id"],
                    platform="bili",
                    remote_type="video",
                    remote_id="BV1operation",
                    kind="video",
                    created_at=at,
                    updated_at=at,
                )
            )
            session.execute(
                insert(Asset).values(
                    id=asset_id,
                    platform="bili",
                    content_id=content_id,
                    remote_id="24680:video:0",
                    kind="video",
                    position=0,
                    status="discovered",
                    locator={"type": "direct", "url_hint": "opaque"},
                    semantic_fingerprint="0" * 64,
                    locator_fingerprint="1" * 64,
                    created_at=at,
                    updated_at=at,
                )
            )
    finally:
        database.dispose()
    return str(account["id"]), str(subscription["author_id"]), asset_id


def test_operation_reconciliation_trigger_is_non_blocking_single_flight_and_closable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = threading.Event()
    release = threading.Event()
    first_done = threading.Event()
    failure_seen = threading.Event()
    third_done = threading.Event()
    lock = threading.Lock()
    calls = 0
    active = 0
    max_active = 0

    class FakeCoordinator:
        def reconcile_expired(self, *, limit: int) -> None:
            nonlocal calls, active, max_active
            assert limit == 7
            with lock:
                calls += 1
                call = calls
                active += 1
                max_active = max(max_active, active)
            try:
                if call == 1:
                    entered.set()
                    release.wait(5)
                    first_done.set()
                elif call == 2:
                    failure_seen.set()
                    raise RuntimeError("private reconciliation detail")
                else:
                    third_done.set()
            finally:
                with lock:
                    active -= 1

    monkeypatch.setattr(api_module, "_OPERATION_RECONCILE_MIN_INTERVAL_SECONDS", 0.0)
    trigger = api_module._OperationReconciliationTrigger(FakeCoordinator(), limit=7)  # type: ignore[arg-type]

    started = time.monotonic()
    assert trigger.trigger() is True
    assert time.monotonic() - started < 0.5
    assert entered.wait(2)
    assert trigger.trigger() is False
    assert calls == 1
    release.set()
    assert first_done.wait(2)

    deadline = time.monotonic() + 2
    while not trigger.trigger():
        if time.monotonic() >= deadline:
            raise AssertionError("failed reconciliation did not release the single-flight gate")
        time.sleep(0.001)
    assert failure_seen.wait(2)
    deadline = time.monotonic() + 2
    while not trigger.trigger():
        if time.monotonic() >= deadline:
            raise AssertionError("reconciliation exception left the trigger stuck")
        time.sleep(0.001)
    assert third_done.wait(2)

    trigger.close(timeout_seconds=1)
    assert trigger.trigger() is False
    assert calls == 3
    assert max_active == 1


def test_idempotency_projection_filters_and_keyset_pagination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    raw_key = "operation-idempotency-0001"
    monkeypatch.setattr(api_module, "_OPERATION_STREAM_MAX_SECONDS", 0.04)
    monkeypatch.setattr(api_module, "_OPERATION_STREAM_POLL_SECONDS", 0.005)
    with _client(settings) as client:
        first = client.post(
            "/api/v1/scheduler/run",
            headers={"Idempotency-Key": raw_key},
            json={"max_jobs": 1},
        )
        assert first.status_code == 202
        operation_id = first.json()["operation_id"]
        terminal = _wait_terminal(client, operation_id)
        replay = client.post(
            "/api/v1/scheduler/run",
            headers={"Idempotency-Key": raw_key},
            json={"max_jobs": 1},
        )
        conflict = client.post(
            "/api/v1/scheduler/run",
            headers={"Idempotency-Key": raw_key},
            json={"max_jobs": 2},
        )

        assert replay.status_code == 202
        assert replay.json()["operation_id"] == operation_id
        assert replay.json()["replayed"] is True
        assert conflict.status_code == 409
        assert conflict.json() == {"detail": "idempotency_key_reused"}
        assert terminal["state"] == "succeeded"
        assert terminal["result"] == {"processed_count": 0, "status_counts": {}}

        for suffix in range(3):
            response = client.post("/api/v1/scheduler/run", json={"max_jobs": suffix + 1})
            assert response.status_code == 202
            _wait_terminal(client, response.json()["operation_id"])

        first_page = client.get("/api/v1/operations", params={"kind": "scheduler-run", "limit": 2})
        assert first_page.status_code == 200
        page = first_page.json()
        assert len(page) == 2
        second_page = client.get(
            "/api/v1/operations",
            params={
                "kind": "scheduler-run",
                "limit": 2,
                "before_requested_at": page[-1]["requested_at"],
                "before_id": page[-1]["id"],
            },
        )
        assert second_page.status_code == 200
        assert {item["id"] for item in page}.isdisjoint({item["id"] for item in second_page.json()})

        detail = client.get(f"/api/v1/operations/{operation_id}")
        events = client.get(f"/api/v1/operations/{operation_id}/events", params={"after": 0, "limit": 200})
        assert detail.status_code == 200
        assert events.status_code == 200
        assert [event["operation_sequence"] for event in events.json()] == list(range(1, len(events.json()) + 1))
        _assert_safe_public_payload(first.json(), raw_key, str(tmp_path), "http://", "https://")
        _assert_safe_public_payload(detail.json(), raw_key, str(tmp_path), "http://", "https://")
        _assert_safe_public_payload(events.json(), raw_key, str(tmp_path), "http://", "https://")
        stream = client.get("/api/v1/operations/events", headers={"Last-Event-ID": "0"})
        assert stream.status_code == 200
        assert raw_key not in stream.text
        assert str(tmp_path) not in stream.text
        for forbidden in _FORBIDDEN_PUBLIC_KEYS:
            assert forbidden not in stream.text

        database = Database(settings.resolved_database_url)
        try:
            with database.session() as session:
                row = session.get(Operation, operation_id)
                assert row is not None
                assert row.idempotency_key_hash is not None
                assert len(row.idempotency_key_hash) == 64
                assert row.idempotency_key_hash != raw_key
                assert session.scalar(select(func.count()).select_from(Operation)) == 4
        finally:
            database.dispose()

    for candidate in (settings.state_dir / "media-sync.sqlite3", settings.state_dir / "media-sync.sqlite3-wal"):
        if candidate.exists():
            assert raw_key.encode() not in candidate.read_bytes()


def test_all_five_post_routes_use_safe_durable_results_and_server_owned_workers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    captured_workers: list[str] = []

    class FakeLoginService:
        def __init__(self, database: Database, *_args: object, **_kwargs: object) -> None:
            self.database = database

        def run(self, request: object, **kwargs: object) -> AccountLoginOutcome:
            del request
            login_id = str(uuid4())
            hook = kwargs["subject_hook"]
            assert callable(hook)
            with self.database.session() as session:
                hook(session, DurableSubjectRef("login_session", login_id))
            now = datetime.now(UTC)
            return AccountLoginOutcome(
                account_id=UUID(account_id),
                login_session_id=UUID(login_id),
                platform=Platform.BILI,
                runner_status=MediaCrawlerLoginStatus.AUTHENTICATED,
                session_status="succeeded",
                auth_status=AuthStatus.AUTHENTICATED,
                expires_at=now + timedelta(minutes=5),
                completed_at=now,
                created_at=now,
                updated_at=now,
            )

    class FakeSchedulerWorker:
        def __init__(self, database: Database) -> None:
            self.database = database

        async def run_bounded(self, **kwargs: object) -> tuple[SchedulerWorkerResult, ...]:
            worker_id = kwargs["worker_id"]
            assert isinstance(worker_id, str)
            captured_workers.append(worker_id)
            job_id = str(uuid4())
            hook = kwargs["subject_hook"]
            assert callable(hook)
            with self.database.session() as session:
                hook(session, DurableSubjectRef("job", job_id))
            return (SchedulerWorkerResult(job_id, None, "succeeded", 1, None),)

    class FakePipelineWorker:
        def __init__(self, database: Database) -> None:
            self.database = database

        async def run_bounded(self, **kwargs: object) -> tuple[PipelineWorkerResult, ...]:
            worker_id = kwargs["worker_id"]
            assert isinstance(worker_id, str)
            captured_workers.append(worker_id)
            job_id = str(uuid4())
            hook = kwargs["subject_hook"]
            assert callable(hook)
            with self.database.session() as session:
                hook(session, DurableSubjectRef("job", job_id))
            return (PipelineWorkerResult(job_id, None, "succeeded", 1, None),)

    def fake_asset_download(**kwargs: object) -> tuple[dict[str, object], bool]:
        worker_id = kwargs["worker_id"]
        assert isinstance(worker_id, str)
        captured_workers.append(worker_id)
        job_id = str(uuid4())
        hook = kwargs["subject_hook"]
        database = kwargs["database"]
        assert callable(hook) and isinstance(database, Database)
        with database.session() as session:
            hook(session, DurableSubjectRef("job", job_id))
        return {
            "asset_id": kwargs["asset_id"],
            "job_id": job_id,
            "status": "verified",
            "disposition": "downloaded",
            "generation": 1,
            "size_bytes": 42,
        }, True

    class FakeEmbyService:
        def __init__(self, database: Database, *_args: object, **_kwargs: object) -> None:
            self.database = database

        def export_author(self, request: object, **kwargs: object) -> SimpleNamespace:
            worker_id = request.worker_id  # type: ignore[attr-defined]
            captured_workers.append(worker_id)
            job_id = str(uuid4())
            hook = kwargs["subject_hook"]
            assert callable(hook)
            with self.database.session() as session:
                hook(session, DurableSubjectRef("job", job_id))
            return SimpleNamespace(job_id=job_id, already_exported=False, managed_file_count=3)

    monkeypatch.setattr(
        api_module,
        "collect_account_login_preflight",
        lambda *_args, **_kwargs: SimpleNamespace(ok=True, code="ready"),
    )
    monkeypatch.setattr(api_module, "MediaCrawlerQrLoginService", FakeLoginService)
    monkeypatch.setattr(
        api_module,
        "_build_subscription_worker",
        lambda database, *_args, **_kwargs: FakeSchedulerWorker(database),
    )
    monkeypatch.setattr(
        api_module,
        "_build_pipeline_worker",
        lambda database, *_args, **_kwargs: FakePipelineWorker(database),
    )
    monkeypatch.setattr(api_module, "_execute_asset_download", fake_asset_download)
    monkeypatch.setattr(api_module, "EmbyExportService", FakeEmbyService)

    with _client(settings) as client:
        account_id, author_id, asset_id = _create_account_subscription_asset(client, settings)
        caller_worker = "caller-worker-must-not-persist"
        starts = []
        terminal = []
        requests = (
            (
                f"/api/v1/accounts/{account_id}/login",
                {"enable_mediacrawler": True, "accept_mediacrawler_license": True},
            ),
            (
                f"/api/v1/assets/{asset_id}/download",
                {"worker_id": caller_worker},
            ),
            ("/api/v1/scheduler/run", {"max_jobs": 1}),
            ("/api/v1/pipeline/run", {"max_jobs": 1, "worker_id": caller_worker}),
            (
                "/api/v1/emby/export",
                {"author_id": author_id, "worker_id": caller_worker},
            ),
        )
        for route, body in requests:
            response = client.post(route, json=body)
            assert response.status_code == 202
            starts.append(response)
            terminal.append(_wait_terminal(client, response.json()["operation_id"]))
        assert {item["kind"] for item in terminal} == {
            "account-login",
            "asset-download",
            "scheduler-run",
            "pipeline-run",
            "emby-export",
        }
        assert all(item["state"] == "succeeded" for item in terminal), [
            (item["kind"], item["state"], item["error_code"]) for item in terminal
        ]
        assert len(captured_workers) == 4
        assert all(worker.startswith("operation-") for worker in captured_workers)
        assert caller_worker not in captured_workers

        snapshot = client.get("/api/v1/operations", params={"limit": 200})
        assert snapshot.status_code == 200
        assert len(snapshot.json()) == 5
        _assert_safe_public_payload(snapshot.json(), caller_worker, str(tmp_path), "http://", "https://")
        for started, completed in zip(starts, terminal, strict=True):
            detail = client.get(f"/api/v1/operations/{completed['id']}")
            events = client.get(f"/api/v1/operations/{completed['id']}/events", params={"limit": 200})
            assert detail.status_code == 200
            assert events.status_code == 200
            assert detail.json()["subjects"]
            _assert_safe_public_payload(started.json(), caller_worker, str(tmp_path), "http://", "https://")
            _assert_safe_public_payload(detail.json(), caller_worker, str(tmp_path), "http://", "https://")
            _assert_safe_public_payload(events.json(), caller_worker, str(tmp_path), "http://", "https://")


def test_asset_and_emby_cancel_before_domain_call_stop_at_safe_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    domain_calls: list[str] = []
    gates = {
        "downloading": (threading.Event(), threading.Event()),
        "exporting": (threading.Event(), threading.Event()),
    }
    original_phase = OperationExecutionContext.phase

    def gated_phase(context: OperationExecutionContext, phase: str) -> object:
        snapshot = original_phase(context, phase)
        gate = gates.get(phase)
        if gate is not None:
            entered, release = gate
            entered.set()
            release.wait(5)
        return snapshot

    def unexpected_download(**_kwargs: object) -> tuple[dict[str, object], bool]:
        domain_calls.append("asset-download")
        return {}, False

    class UnexpectedEmbyService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def export_author(self, *_args: object, **_kwargs: object) -> object:
            domain_calls.append("emby-export")
            return object()

    monkeypatch.setattr(OperationExecutionContext, "phase", gated_phase)
    monkeypatch.setattr(api_module, "_execute_asset_download", unexpected_download)
    monkeypatch.setattr(api_module, "EmbyExportService", UnexpectedEmbyService)

    with _client(settings) as client:
        _account_id, author_id, asset_id = _create_account_subscription_asset(client, settings)
        cases = (
            (f"/api/v1/assets/{asset_id}/download", {}, "downloading"),
            ("/api/v1/emby/export", {"author_id": author_id}, "exporting"),
        )
        for route, body, phase in cases:
            started = client.post(route, json=body)
            assert started.status_code == 202
            operation_id = started.json()["operation_id"]
            entered, release = gates[phase]
            assert entered.wait(2)
            cancelled = client.post(f"/api/v1/operations/{operation_id}/cancel")
            assert cancelled.status_code == 200
            release.set()
            terminal = _wait_terminal(client, operation_id)
            assert terminal["state"] == "cancelled"
            event_codes = [
                event["event_code"] for event in client.get(f"/api/v1/operations/{operation_id}/events").json()
            ]
            assert event_codes.count("operation_cancel_requested") == 1
            assert event_codes.count("operation_cancel_observed") == 1
            assert event_codes.count("operation_cancelled") == 1

    assert domain_calls == []


def test_durable_cancel_snapshot_stops_asset_when_local_signal_lags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    phase_entered = threading.Event()
    phase_release = threading.Event()
    domain_called = threading.Event()
    original_phase = OperationExecutionContext.phase

    def gated_phase(context: OperationExecutionContext, phase: str) -> object:
        if phase == "downloading":
            phase_entered.set()
            phase_release.wait(5)
        return original_phase(context, phase)

    def persist_cancel_without_local_signal(
        coordinator: object,
        operation_id: str,
        *,
        expected_revision: int | None = None,
    ) -> object:
        database = coordinator._database  # type: ignore[attr-defined]
        with database.session() as session:
            repository = OperationRepository(session)
            observed = repository.require(operation_id)
            revision = observed.revision if expected_revision is None else expected_revision
            requested = repository.request_cancel(operation_id, expected_revision=revision)
        return requested

    def unexpected_download(**_kwargs: object) -> tuple[dict[str, object], bool]:
        domain_called.set()
        return {}, False

    monkeypatch.setattr(OperationExecutionContext, "phase", gated_phase)
    monkeypatch.setattr(api_module.OperationCoordinator, "request_cancel", persist_cancel_without_local_signal)
    monkeypatch.setattr(api_module, "_execute_asset_download", unexpected_download)

    with _client(settings) as client:
        _account_id, _author_id, asset_id = _create_account_subscription_asset(client, settings)
        started = client.post(f"/api/v1/assets/{asset_id}/download", json={})
        assert started.status_code == 202
        operation_id = started.json()["operation_id"]
        assert phase_entered.wait(2)
        cancelled = client.post(f"/api/v1/operations/{operation_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["cancel_requested_at"] is not None
        phase_release.set()
        terminal = _wait_terminal(client, operation_id)

    assert terminal["state"] == "cancelled"
    assert terminal["cancel_requested_at"] is not None
    assert not domain_called.is_set()


def test_cross_coordinator_cancel_stops_login_before_runner_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    phase_entered = threading.Event()
    phase_release = threading.Event()
    owner_contexts: list[OperationExecutionContext] = []
    domain_calls: list[str] = []
    original_phase = OperationExecutionContext.phase

    def gated_phase(context: OperationExecutionContext, phase: str) -> object:
        if phase == "authenticating":
            owner_contexts.append(context)
            phase_entered.set()
            phase_release.wait(5)
        return original_phase(context, phase)

    def unexpected_component(*_args: object, **_kwargs: object) -> object:
        domain_calls.append("login")
        raise AssertionError("login runner/service must not be constructed after durable cancellation")

    monkeypatch.setattr(OperationExecutionContext, "phase", gated_phase)
    monkeypatch.setattr(
        api_module,
        "collect_account_login_preflight",
        lambda *_args, **_kwargs: SimpleNamespace(ok=True, code="ready"),
    )
    monkeypatch.setattr(api_module, "_UnavailableMediaCrawlerLoginRunner", unexpected_component)
    monkeypatch.setattr(api_module, "MediaCrawlerLoginProcessRunner", unexpected_component)
    monkeypatch.setattr(api_module, "MediaCrawlerQrLoginService", unexpected_component)

    owner_client = _client(settings)
    cancelling_client = _client(settings)
    assert owner_client.app.state.operations.instance_id != cancelling_client.app.state.operations.instance_id
    with owner_client as owner, cancelling_client as canceller:
        account = owner.post(
            "/api/v1/accounts",
            json={"platform": "bili", "display_name": "cross-process-login", "login_method": "qr"},
        )
        assert account.status_code == 201
        started = owner.post(
            f"/api/v1/accounts/{account.json()['id']}/login",
            json={"enable_mediacrawler": True, "accept_mediacrawler_license": True},
        )
        assert started.status_code == 202
        operation_id = started.json()["operation_id"]
        assert phase_entered.wait(2)

        cancelled = canceller.post(f"/api/v1/operations/{operation_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["cancel_requested_at"] is not None
        assert len(owner_contexts) == 1
        assert owner_contexts[0].cancel_requested is False

        phase_release.set()
        terminal = _wait_terminal(owner, operation_id)
        assert terminal["state"] == "cancelled"
        _assert_cancel_event_chain(owner, operation_id)

    assert domain_calls == []


@pytest.mark.parametrize(
    ("route", "body", "builder_name"),
    (
        ("/api/v1/scheduler/run", {"max_jobs": 1}, "_build_subscription_worker"),
        ("/api/v1/pipeline/run", {"max_jobs": 1}, "_build_pipeline_worker"),
    ),
)
def test_cross_coordinator_cancel_stops_workers_before_claiming_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    body: dict[str, object],
    builder_name: str,
) -> None:
    settings = _settings(tmp_path)
    phase_entered = threading.Event()
    phase_release = threading.Event()
    owner_contexts: list[OperationExecutionContext] = []
    worker_calls: list[str] = []
    original_phase = OperationExecutionContext.phase

    def gated_phase(context: OperationExecutionContext, phase: str) -> object:
        if phase == "claiming_jobs":
            owner_contexts.append(context)
            phase_entered.set()
            phase_release.wait(5)
        return original_phase(context, phase)

    class UnexpectedWorker:
        async def run_bounded(self, **_kwargs: object) -> tuple[object, ...]:
            worker_calls.append("run_bounded")
            return ()

    monkeypatch.setattr(OperationExecutionContext, "phase", gated_phase)
    monkeypatch.setattr(
        api_module,
        builder_name,
        lambda *_args, **_kwargs: UnexpectedWorker(),
    )

    owner_client = _client(settings)
    cancelling_client = _client(settings)
    assert owner_client.app.state.operations.instance_id != cancelling_client.app.state.operations.instance_id
    with owner_client as owner, cancelling_client as canceller:
        started = owner.post(route, json=body)
        assert started.status_code == 202
        operation_id = started.json()["operation_id"]
        assert phase_entered.wait(2)

        cancelled = canceller.post(f"/api/v1/operations/{operation_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["cancel_requested_at"] is not None
        assert len(owner_contexts) == 1
        assert owner_contexts[0].cancel_requested is False

        phase_release.set()
        terminal = _wait_terminal(owner, operation_id)
        assert terminal["state"] == "cancelled"
        _assert_cancel_event_chain(owner, operation_id)

    assert worker_calls == []


def test_asset_and_emby_domain_success_wins_cancel_during_non_interruptible_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    gates = {
        "asset-download": (threading.Event(), threading.Event()),
        "emby-export": (threading.Event(), threading.Event()),
    }

    def successful_download(**kwargs: object) -> tuple[dict[str, object], bool]:
        entered, release = gates["asset-download"]
        entered.set()
        release.wait(5)
        return {
            "asset_id": kwargs["asset_id"],
            "job_id": str(uuid4()),
            "status": "verified",
            "disposition": "downloaded",
            "generation": 1,
            "size_bytes": 42,
        }, True

    class SuccessfulEmbyService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def export_author(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
            entered, release = gates["emby-export"]
            entered.set()
            release.wait(5)
            return SimpleNamespace(job_id=str(uuid4()), already_exported=False, managed_file_count=3)

    monkeypatch.setattr(api_module, "_execute_asset_download", successful_download)
    monkeypatch.setattr(api_module, "EmbyExportService", SuccessfulEmbyService)

    with _client(settings) as client:
        _account_id, author_id, asset_id = _create_account_subscription_asset(client, settings)
        cases = (
            (f"/api/v1/assets/{asset_id}/download", {}, "asset-download"),
            ("/api/v1/emby/export", {"author_id": author_id}, "emby-export"),
        )
        for route, body, kind in cases:
            started = client.post(route, json=body)
            assert started.status_code == 202
            operation_id = started.json()["operation_id"]
            entered, release = gates[kind]
            assert entered.wait(2)
            cancelled = client.post(f"/api/v1/operations/{operation_id}/cancel")
            assert cancelled.status_code == 200
            release.set()
            terminal = _wait_terminal(client, operation_id)
            assert terminal["state"] == "succeeded"
            assert terminal["cancel_requested_at"] is not None
            event_codes = [
                event["event_code"] for event in client.get(f"/api/v1/operations/{operation_id}/events").json()
            ]
            assert event_codes.count("operation_succeeded") == 1
            assert "operation_cancelled" not in event_codes


def test_cooperative_cancel_and_sse_ready_replay_are_bounded_and_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    entered = threading.Event()

    class BlockingWorker:
        async def run_bounded(self, **kwargs: object) -> tuple[SchedulerWorkerResult, ...]:
            cancellation = kwargs["cancellation"]
            assert isinstance(cancellation, threading.Event)
            entered.set()
            while not cancellation.is_set():
                await asyncio.sleep(0.005)
            return ()

    monkeypatch.setattr(
        api_module,
        "_build_subscription_worker",
        lambda *_args, **_kwargs: BlockingWorker(),
    )
    monkeypatch.setattr(api_module, "_OPERATION_STREAM_MAX_SECONDS", 0.08)
    monkeypatch.setattr(api_module, "_OPERATION_STREAM_POLL_SECONDS", 0.005)
    monkeypatch.setattr(api_module, "_OPERATION_STREAM_KEEPALIVE_SECONDS", 0.02)

    with _client(settings) as client:
        started = client.post("/api/v1/scheduler/run", json={"max_jobs": 1})
        assert started.status_code == 202
        operation_id = started.json()["operation_id"]
        assert entered.wait(2)
        cancelled = client.post(f"/api/v1/operations/{operation_id}/cancel")
        assert cancelled.status_code == 200
        terminal = _wait_terminal(client, operation_id)
        assert terminal["state"] == "cancelled"
        assert terminal["cancel_requested_at"] is not None
        repeated = client.post(f"/api/v1/operations/{operation_id}/cancel")
        assert repeated.status_code == 200
        assert repeated.json()["state"] == "cancelled"

        fresh = client.get("/api/v1/operations/events")
        replay = client.get("/api/v1/operations/events", headers={"Last-Event-ID": "0"})
        assert fresh.status_code == 200
        assert replay.status_code == 200
        assert fresh.headers["content-type"].startswith("text/event-stream")
        assert "event: ready" in fresh.text
        assert "event: operation" not in fresh.text
        assert "event: ready" in replay.text
        assert "event: operation" in replay.text
        event_ids = [int(line.removeprefix("id: ")) for line in replay.text.splitlines() if line.startswith("id: ")]
        assert event_ids == sorted(event_ids)
        assert len(event_ids) == len(set(event_ids))

        event_payloads = client.get(f"/api/v1/operations/{operation_id}/events").json()
        event_codes = [event["event_code"] for event in event_payloads]
        assert event_codes.count("operation_cancel_requested") == 1
        assert event_codes.count("operation_cancel_observed") == 1
        assert event_codes.count("operation_cancelled") == 1
        _assert_safe_public_payload(cancelled.json(), str(tmp_path), "http://", "https://")
        _assert_safe_public_payload(event_payloads, str(tmp_path), "http://", "https://")
        for forbidden in _FORBIDDEN_PUBLIC_KEYS:
            assert forbidden not in replay.text
        assert str(tmp_path) not in replay.text
        assert "http://" not in replay.text
        assert "https://" not in replay.text

        malformed = "1?credential=SSE-SECRET-SENTINEL"
        invalid = client.get("/api/v1/operations/events", headers={"Last-Event-ID": malformed})
        assert invalid.status_code == 400
        assert invalid.json() == {"detail": "operation_event_cursor_invalid"}
        assert "SSE-SECRET-SENTINEL" not in invalid.text
        assert client.get("/api/v1/operations/not-a-uuid").status_code == 404
        assert client.get(f"/api/v1/operations/{operation_id}/events", params={"after": -1}).status_code == 400
        oversized = client.get(
            f"/api/v1/operations/{operation_id}/events",
            params={"after": 2**63},
        )
        assert oversized.status_code == 400
        assert oversized.json() == {"detail": "operation_event_cursor_invalid"}
        future_cursor = max(event["stream_sequence"] for event in event_payloads) + 1
        future = client.get(
            "/api/v1/operations/events",
            headers={"Last-Event-ID": str(future_cursor)},
        )
        assert future.status_code == 400
        assert future.json() == {"detail": "operation_event_cursor_invalid"}

        database = Database(settings.resolved_database_url)
        try:
            with database.session() as session:
                stream_state = session.get(OperationEventStreamState, 1)
                assert stream_state is not None
                stream_state.pruned_through_sequence = 1
        finally:
            database.dispose()
        expired = client.get(
            "/api/v1/operations/events",
            headers={"Last-Event-ID": "0"},
        )
        assert expired.status_code == 410
        assert expired.json() == {"detail": "operation_event_cursor_expired"}


def test_sse_initial_database_reads_do_not_block_the_asgi_event_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    upgrade_database(settings.resolved_database_url)
    app = api_module.create_api_app(settings)
    original_stream_bounds = app.state.operations.stream_bounds
    entered = threading.Event()
    release = threading.Event()
    responses: list[object] = []

    def blocking_stream_bounds() -> tuple[int, int]:
        entered.set()
        release.wait(5)
        return original_stream_bounds()

    monkeypatch.setattr(app.state.operations, "stream_bounds", blocking_stream_bounds)
    monkeypatch.setattr(api_module, "_OPERATION_STREAM_MAX_SECONDS", 0.02)
    monkeypatch.setattr(api_module, "_OPERATION_STREAM_POLL_SECONDS", 0.005)

    with TestClient(app) as client:
        stream_request = threading.Thread(
            target=lambda: responses.append(client.get("/api/v1/operations/events")),
            daemon=True,
        )
        stream_request.start()
        assert entered.wait(2)
        delayed_release = threading.Timer(2, release.set)
        delayed_release.start()
        started = time.monotonic()
        health = client.get("/api/v1/health")
        elapsed = time.monotonic() - started
        release.set()
        delayed_release.cancel()
        stream_request.join(2)

    assert health.status_code == 200
    assert elapsed < 1
    assert not stream_request.is_alive()
    assert len(responses) == 1
    assert getattr(responses[0], "status_code", None) == 200


def test_sse_idle_fresh_cursor_replays_events_created_between_connections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(api_module, "_OPERATION_STREAM_MAX_SECONDS", 0.03)
    monkeypatch.setattr(api_module, "_OPERATION_STREAM_POLL_SECONDS", 0.005)

    with _client(settings) as client:
        first = client.get("/api/v1/operations/events")
        assert first.status_code == 200
        first_ids = [int(line.removeprefix("id: ")) for line in first.text.splitlines() if line.startswith("id: ")]
        assert first_ids == [0]

        started = client.post("/api/v1/scheduler/run", json={"max_jobs": 1})
        assert started.status_code == 202
        operation_id = started.json()["operation_id"]
        _wait_terminal(client, operation_id)
        committed = client.get(f"/api/v1/operations/{operation_id}/events").json()
        committed_ids = [event["stream_sequence"] for event in committed]
        assert committed_ids

        replay = client.get(
            "/api/v1/operations/events",
            headers={"Last-Event-ID": str(first_ids[0])},
        )
        replay_ids = [int(line.removeprefix("id: ")) for line in replay.text.splitlines() if line.startswith("id: ")]
        assert replay_ids == [first_ids[0], *committed_ids]
        assert replay.text.count("event: operation") == len(committed_ids)


def test_invalid_or_duplicate_idempotency_headers_fail_without_echo(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    sentinel = "SECRET?HEADER-MUST-NOT-ECHO"
    with _client(settings) as client:
        invalid = client.post(
            "/api/v1/scheduler/run",
            headers={"Idempotency-Key": sentinel},
            json={},
        )
        duplicate = client.post(
            "/api/v1/scheduler/run",
            headers=[
                ("Idempotency-Key", "operation-key-00000001"),
                ("Idempotency-Key", "operation-key-00000002"),
            ],
            json={},
        )
        assert invalid.status_code == 400
        assert duplicate.status_code == 400
        assert invalid.json() == {"detail": "operation_idempotency_key_invalid"}
        assert duplicate.json() == {"detail": "operation_idempotency_key_invalid"}
        assert sentinel not in invalid.text
        database = Database(settings.resolved_database_url)
        try:
            with database.session() as session:
                assert session.scalar(select(func.count()).select_from(Operation)) == 0
        finally:
            database.dispose()
