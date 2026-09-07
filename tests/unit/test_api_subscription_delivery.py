"""Exact subscription delivery API ownership and receipt contracts."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from _api_client import authenticated_test_client
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import media_sync.interfaces.api as api_module
from media_sync.application.operations import OperationExecutionContext
from media_sync.config import Settings
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.infrastructure.db.models import Job, Subscription
from media_sync.scheduler import PipelineDeliveryReceipt, PipelineWorkerResult, SchedulerWorkerResult
from media_sync.scheduler.repository import SchedulerRepository as DurableSchedulerRepository


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
    return authenticated_test_client(settings, app_factory=api_module.create_api_app)


def _subscription(client: TestClient) -> dict[str, object]:
    account = client.post(
        "/api/v1/accounts",
        json={"platform": "bili", "display_name": "delivery", "login_method": "qr"},
    )
    assert account.status_code == 201
    response = client.post(
        "/api/v1/subscriptions",
        json={
            "account_id": account.json()["id"],
            "platform": "bili",
            "creator_remote_id": "252671524",
            "display_name": "delivery-author",
            "allow_full_history": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def _wait_terminal(client: TestClient, operation_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/operations/{operation_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["state"] not in {"queued", "running"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("subscription delivery operation did not finish")


def _request(revision: int = 0) -> dict[str, object]:
    return {
        "expected_schedule_revision": revision,
        "global_capacity": 1,
        "lease_seconds": 60,
        "retry_delay_seconds": 30,
        "enable_mediacrawler": True,
        "accept_mediacrawler_license": True,
    }


def test_subscription_detail_exposes_closed_uninitialized_bili_delivery_projection(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with _client(settings) as client:
        subscription_id = str(_subscription(client)["id"])
        response = client.get(f"/api/v1/subscriptions/{subscription_id}")

    assert response.status_code == 200
    progress = response.json()["bili_delivery"]
    assert progress == {
        "schema_version": 1,
        "initialized": False,
        "phase": "backfill",
        "baseline_snapshot_complete": False,
        "generation_id": None,
        "batch_count": 0,
        "content_observation_count": 0,
        "backfill_batch_count": 0,
        "reconciliation_batch_count": 0,
        "incremental_batch_count": 0,
        "partial_batch_count": 0,
        "failed_content_count": 0,
        "last_lane": None,
        "last_stop_reason": None,
        "last_delivery_at": None,
        "source_end_observed_at": None,
        "source_end_run_id": None,
        "reconciled_at": None,
        "reconciliation_run_id": None,
        "baseline_snapshot_at": None,
        "next_eligible_at": None,
        "blocked_code": None,
    }


def test_subscription_detail_fails_closed_when_upstream_lock_is_invalid(tmp_path: Path) -> None:
    lock_path = tmp_path / "invalid-upstreams.lock.json"
    lock_path.write_text("{}", encoding="utf-8")
    settings = Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "library",
        job_dir=tmp_path / "jobs",
        mediacrawler_runtime_dir=tmp_path / "mediacrawler",
        mediacrawler_lock_path=lock_path,
    )
    with _client(settings) as client:
        subscription_id = str(_subscription(client)["id"])
        response = client.get(f"/api/v1/subscriptions/{subscription_id}")

    assert response.status_code == 200
    assert "bili_delivery" not in response.json()


def _install_success_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    target_subscription_id: str,
    entered: threading.Event | None = None,
    release: threading.Event | None = None,
    pipeline_idle: bool = False,
    discovery_observations: tuple[str, ...] = (),
    pipeline_observations: tuple[str, ...] = (),
    discovery_attempts: tuple[str, ...] = (),
    pipeline_attempts: tuple[str, ...] = (),
    strict_observations: bool = False,
    retry_entered: threading.Event | None = None,
    retry_release: threading.Event | None = None,
) -> dict[str, object]:
    sync_job_id = str(uuid4())
    run_id = str(uuid4())
    pipeline_job_id = str(uuid4())
    account_id = str(uuid4())
    author_id = str(uuid4())
    export_job_id = str(uuid4())
    calls: dict[str, object] = {"materialize_count": 0}

    class FakeScheduler:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def materialize_one(self, subscription_id: str, **kwargs: object) -> SimpleNamespace:
            assert subscription_id == target_subscription_id
            assert kwargs["expected_schedule_revision"] == 0
            calls["materialize_count"] = int(calls["materialize_count"]) + 1
            return SimpleNamespace(job_id=sync_job_id)

        def get_job(self, identifier: str) -> SimpleNamespace:
            assert identifier == sync_job_id
            assert discovery_observations
            index = int(calls.get("discovery_observation_count", 0))
            if strict_observations and index >= len(discovery_observations):
                raise AssertionError("active discovery lease was polled instead of retried exactly")
            calls["discovery_observation_count"] = index + 1
            status = discovery_observations[min(index, len(discovery_observations) - 1)]
            return SimpleNamespace(
                job_id=identifier,
                subscription_id=target_subscription_id,
                status=status,
                run_id=run_id if status == "succeeded" else None,
            )

    class FakeDiscoveryWorker:
        async def run_exact(self, job_id: str, **kwargs: object) -> SchedulerWorkerResult:
            assert job_id == sync_job_id
            assert kwargs["expected_subscription_id"] == target_subscription_id
            assert kwargs["global_capacity"] == 1
            assert kwargs["lease_seconds"] == 60
            assert callable(kwargs["subject_hook"])
            calls["discovery_worker_id"] = kwargs["worker_id"]
            if entered is not None and release is not None:
                entered.set()
                await asyncio.to_thread(release.wait, 5)
            if discovery_attempts:
                index = int(calls.get("discovery_attempt_count", 0))
                calls["discovery_attempt_count"] = index + 1
                status = discovery_attempts[min(index, len(discovery_attempts) - 1)]
                if status == "idle":
                    return SchedulerWorkerResult.idle()
                return SchedulerWorkerResult(
                    sync_job_id,
                    target_subscription_id,
                    status,
                    index + 1,
                    run_id if status == "succeeded" else None,
                )
            if discovery_observations:
                return SchedulerWorkerResult.idle()
            return SchedulerWorkerResult(sync_job_id, target_subscription_id, "succeeded", 1, run_id)

    class FakePipelineRepository:
        def __init__(self, _session: object) -> None:
            pass

        def get_for_succeeded_sync(self, source_id: str, **kwargs: object) -> SimpleNamespace:
            assert source_id == sync_job_id
            assert kwargs == {
                "run_id": run_id,
                "expected_subscription_id": target_subscription_id,
            }
            return SimpleNamespace(job_id=pipeline_job_id)

        def get(self, identifier: str) -> SimpleNamespace:
            assert identifier == pipeline_job_id
            if pipeline_observations:
                index = int(calls.get("pipeline_observation_count", 0))
                if strict_observations and index >= len(pipeline_observations):
                    raise AssertionError("active pipeline lease was polled instead of retried exactly")
                calls["pipeline_observation_count"] = index + 1
                status = pipeline_observations[min(index, len(pipeline_observations) - 1)]
                return SimpleNamespace(
                    job_id=identifier,
                    subscription_id=target_subscription_id,
                    status=status,
                    receipt=receipt if status == "succeeded" else None,
                )
            return SimpleNamespace(
                job_id=identifier, subscription_id=target_subscription_id, status="succeeded", receipt=receipt
            )

    receipt = PipelineDeliveryReceipt(
        subscription_id=target_subscription_id,
        account_id=account_id,
        author_id=author_id,
        platform="bili",
        export_job_id=export_job_id,
        selected_asset_count=2,
        verified_asset_count=2,
        downloaded_count=1,
        already_verified_count=1,
        publication_disposition="published",
        managed_file_count=7,
        directory_verified=True,
    )

    class FakePipelineWorker:
        async def run_exact(self, job_id: str, **kwargs: object) -> PipelineWorkerResult:
            assert job_id == pipeline_job_id
            assert kwargs["expected_subscription_id"] == target_subscription_id
            assert kwargs["expected_sync_job_id"] == sync_job_id
            assert kwargs["expected_run_id"] == run_id
            assert kwargs["lease_seconds"] == 60
            assert callable(kwargs["subject_hook"])
            calls["pipeline_worker_id"] = kwargs["worker_id"]
            if pipeline_attempts:
                index = int(calls.get("pipeline_attempt_count", 0))
                calls["pipeline_attempt_count"] = index + 1
                if index > 0 and retry_entered is not None and retry_release is not None:
                    retry_entered.set()
                    await asyncio.to_thread(retry_release.wait, 5)
                status = pipeline_attempts[min(index, len(pipeline_attempts) - 1)]
                if status == "idle":
                    return PipelineWorkerResult.idle()
                return PipelineWorkerResult(
                    pipeline_job_id,
                    target_subscription_id,
                    status,
                    index + 1,
                    receipt=receipt if status == "succeeded" else None,
                )
            if pipeline_idle or pipeline_observations:
                return PipelineWorkerResult.idle()
            return PipelineWorkerResult(
                pipeline_job_id,
                target_subscription_id,
                "succeeded",
                1,
                receipt=receipt,
            )

    result = {
        "subscription_id": target_subscription_id,
        "account_id": account_id,
        "author_id": author_id,
        "platform": "bili",
        "sync_job_id": sync_job_id,
        "run_id": run_id,
        "pipeline_job_id": pipeline_job_id,
        "export_job_id": export_job_id,
        "discovery_count": 2,
        "asset_identity_count": 2,
        "updated_count": None,
        "discovery_count_semantics": "created_rows",
        "selection_scope": "author_active_snapshot",
        "selected_asset_count": 2,
        "verified_asset_count": 2,
        "downloaded_count": 1,
        "already_verified_count": 1,
        "publication_disposition": "published",
        "managed_file_count": 7,
        "directory_verified": True,
    }

    def build_result(_database: object, **kwargs: object) -> dict[str, object]:
        assert kwargs == {
            "subscription_id": target_subscription_id,
            "sync_job_id": sync_job_id,
            "run_id": run_id,
            "pipeline_job_id": pipeline_job_id,
            "pipeline_receipt": receipt,
        }
        return result

    monkeypatch.setattr(api_module, "SchedulerRepository", FakeScheduler)
    monkeypatch.setattr(api_module, "PipelineJobRepository", FakePipelineRepository)
    monkeypatch.setattr(
        api_module,
        "_build_subscription_worker",
        lambda *_args, **_kwargs: FakeDiscoveryWorker(),
    )
    monkeypatch.setattr(
        api_module,
        "_build_pipeline_worker",
        lambda *_args, **_kwargs: FakePipelineWorker(),
    )
    monkeypatch.setattr(api_module, "build_subscription_delivery_result", build_result)
    calls["result"] = result
    return calls


def test_exact_delivery_tracks_one_operation_and_safe_durable_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    with _client(settings) as client:
        subscription = _subscription(client)
        subscription_id = str(subscription["id"])
        calls = _install_success_fakes(
            monkeypatch,
            target_subscription_id=subscription_id,
        )
        headers = {"Idempotency-Key": "subscription-delivery-0001"}
        started = client.post(
            f"/api/v1/subscriptions/{subscription_id}/execute",
            json=_request(),
            headers=headers,
        )
        assert started.status_code == 202
        terminal = _wait_terminal(client, started.json()["operation_id"])
        assert terminal["state"] == "succeeded"
        assert terminal["kind"] == "subscription-delivery"
        assert terminal["result"] == calls["result"]
        assert str(calls["discovery_worker_id"]).startswith("operation-")
        assert calls["pipeline_worker_id"] == calls["discovery_worker_id"]

        subjects = {(item["type"], item["role"]) for item in terminal["subjects"]}
        assert subjects == {
            ("subscription", "target"),
            ("job", "execution"),
            ("sync_run", "result"),
            ("job", "result"),
        }
        replay = client.post(
            f"/api/v1/subscriptions/{subscription_id}/execute",
            json=_request(),
            headers=headers,
        )
        assert replay.status_code == 202
        assert replay.json()["operation_id"] == terminal["id"]
        assert replay.json()["replayed"] is True
        assert calls["materialize_count"] == 1


def test_exact_delivery_rejects_parallel_operation_for_same_subscription(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    with _client(settings) as client:
        subscription_id = str(_subscription(client)["id"])
        _install_success_fakes(
            monkeypatch,
            target_subscription_id=subscription_id,
            entered=entered,
            release=release,
        )
        first = client.post(
            f"/api/v1/subscriptions/{subscription_id}/execute",
            json=_request(),
            headers={"Idempotency-Key": "subscription-delivery-0002"},
        )
        assert first.status_code == 202
        assert entered.wait(2)
        second = client.post(
            f"/api/v1/subscriptions/{subscription_id}/execute",
            json=_request(),
            headers={"Idempotency-Key": "subscription-delivery-0003"},
        )
        assert second.status_code == 409
        assert second.json() == {"detail": "operation_already_running"}
        release.set()
        assert _wait_terminal(client, first.json()["operation_id"])["state"] == "succeeded"


def test_supervisor_completed_pipeline_is_reobserved_from_durable_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _client(_settings(tmp_path)) as client:
        identifier = str(_subscription(client)["id"])
        calls = _install_success_fakes(monkeypatch, target_subscription_id=identifier, pipeline_idle=True)
        response = client.post(f"/api/v1/subscriptions/{identifier}/execute", json=_request())
        result = _wait_terminal(client, response.json()["operation_id"])
        assert result["state"] == "succeeded" and result["result"] == calls["result"]


@pytest.mark.parametrize("supervisor_stage", ["discovery", "pipeline"])
def test_supervisor_owned_exact_job_is_observed_through_retry_until_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    supervisor_stage: str,
) -> None:
    monkeypatch.setattr(api_module, "_SUBSCRIPTION_DELIVERY_OBSERVE_SECONDS", 0.001)
    with _client(_settings(tmp_path)) as client:
        identifier = str(_subscription(client)["id"])
        observations = ("running", "retry_wait", "succeeded")
        calls = _install_success_fakes(
            monkeypatch,
            target_subscription_id=identifier,
            discovery_observations=observations if supervisor_stage == "discovery" else (),
            pipeline_observations=observations if supervisor_stage == "pipeline" else (),
        )
        response = client.post(f"/api/v1/subscriptions/{identifier}/execute", json=_request())
        terminal = _wait_terminal(client, response.json()["operation_id"])
        assert terminal["state"] == "succeeded"
        assert terminal["result"] == calls["result"]
        assert calls[f"{supervisor_stage}_observation_count"] == len(observations)


@pytest.mark.parametrize("supervisor_stage", ["discovery", "pipeline"])
@pytest.mark.parametrize("active_status", ["claimed", "running"])
def test_supervisor_owned_active_lease_is_retried_exactly_until_reclaimed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    supervisor_stage: str,
    active_status: str,
) -> None:
    """The observer must call run_exact; polling alone cannot reclaim an expired lease."""

    monkeypatch.setattr(api_module, "_SUBSCRIPTION_DELIVERY_OBSERVE_SECONDS", 0.001)
    with _client(_settings(tmp_path)) as client:
        identifier = str(_subscription(client)["id"])
        calls = _install_success_fakes(
            monkeypatch,
            target_subscription_id=identifier,
            discovery_observations=(active_status,) if supervisor_stage == "discovery" else (),
            pipeline_observations=(active_status,) if supervisor_stage == "pipeline" else (),
            discovery_attempts=("idle", "succeeded") if supervisor_stage == "discovery" else (),
            pipeline_attempts=("idle", "succeeded") if supervisor_stage == "pipeline" else (),
            strict_observations=True,
        )
        response = client.post(f"/api/v1/subscriptions/{identifier}/execute", json=_request())
        terminal = _wait_terminal(client, response.json()["operation_id"])

        assert terminal["state"] == "succeeded"
        assert terminal["result"] == calls["result"]
        assert calls[f"{supervisor_stage}_attempt_count"] == 2
        assert calls[f"{supervisor_stage}_observation_count"] == 1
        assert calls["materialize_count"] == 1


def test_retryable_exact_pipeline_keeps_operation_and_due_cycle_fenced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    retry_entered = threading.Event()
    retry_release = threading.Event()
    monkeypatch.setattr(api_module, "_SUBSCRIPTION_DELIVERY_OBSERVE_SECONDS", 0.001)
    with _client(settings) as client:
        identifier = str(_subscription(client)["id"])
        database = Database(settings.resolved_database_url)
        try:
            with database.session() as session:
                subscription = session.get(Subscription, identifier)
                assert subscription is not None
                subscription.next_run_at = None
            calls = _install_success_fakes(
                monkeypatch,
                target_subscription_id=identifier,
                pipeline_attempts=("retry_wait", "succeeded"),
                retry_entered=retry_entered,
                retry_release=retry_release,
            )
            response = client.post(f"/api/v1/subscriptions/{identifier}/execute", json=_request())
            operation_id = response.json()["operation_id"]
            assert retry_entered.wait(2)
            assert client.get(f"/api/v1/operations/{operation_id}").json()["state"] == "running"

            conflicting = client.post(f"/api/v1/subscriptions/{identifier}/execute", json=_request())
            assert conflicting.status_code == 409
            assert conflicting.json() == {"detail": "operation_already_running"}
            with database.session() as session:
                assert (
                    DurableSchedulerRepository(session).materialize_due(
                        limit=1,
                        now=datetime.now(UTC),
                    )
                    == []
                )
                subscription = session.get(Subscription, identifier)
                assert subscription is not None and subscription.schedule_revision == 0
                assert list(session.scalars(select(Job))) == []
        finally:
            retry_release.set()
            database.dispose()

        terminal = _wait_terminal(client, operation_id)
        assert terminal["state"] == "succeeded"
        assert terminal["result"] == calls["result"]
        assert calls["pipeline_attempt_count"] == 2


def test_exact_delivery_idle_queued_job_is_observed_until_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    sync_job_id = str(uuid4())
    observation_count = 0

    class FakeScheduler:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def materialize_one(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(job_id=sync_job_id)

    class IdleWorker:
        async def run_exact(self, *_args: object, **_kwargs: object) -> SchedulerWorkerResult:
            return SchedulerWorkerResult.idle()

    class QueuedRepository:
        def __init__(self, _session: object) -> None:
            pass

        def materialize_one(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(job_id=sync_job_id)

        def get_job(self, job_id: str) -> SimpleNamespace:
            nonlocal observation_count
            assert job_id == sync_job_id
            status = "queued" if observation_count == 0 else "failed_terminal"
            observation_count += 1
            return SimpleNamespace(
                job_id=sync_job_id,
                subscription_id=subscription_id,
                status=status,
                run_id=None,
            )

    monkeypatch.setattr(api_module, "DurableSchedulerService", FakeScheduler)
    monkeypatch.setattr(api_module, "SchedulerRepository", QueuedRepository)
    monkeypatch.setattr(api_module, "_build_subscription_worker", lambda *_args, **_kwargs: IdleWorker())
    monkeypatch.setattr(api_module, "_SUBSCRIPTION_DELIVERY_OBSERVE_SECONDS", 0.001)
    with _client(settings) as client:
        subscription_id = str(_subscription(client)["id"])
        started = client.post(
            f"/api/v1/subscriptions/{subscription_id}/execute",
            json=_request(),
        )
        assert started.status_code == 202
        terminal = _wait_terminal(client, started.json()["operation_id"])
        assert terminal["state"] == "failed_terminal"
        assert terminal["error_code"] == "subscription_delivery_discovery_failed"
        assert observation_count == 2


def test_exact_delivery_rejects_license_without_runtime_enablement(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    with _client(settings) as client:
        subscription_id = str(_subscription(client)["id"])
        request = _request()
        request["enable_mediacrawler"] = False
        response = client.post(
            f"/api/v1/subscriptions/{subscription_id}/execute",
            json=request,
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "license_requires_enable_mediacrawler"}


@pytest.mark.parametrize(
    ("enabled", "error"),
    [
        (False, "subscription_delivery_mediacrawler_not_enabled"),
        (True, "subscription_delivery_license_required"),
    ],
)
def test_mediacrawler_preflight_failure_never_materializes_or_changes_revision(
    tmp_path: Path, enabled: bool, error: str
) -> None:
    settings = _settings(tmp_path)
    with _client(settings) as client:
        identifier = str(_subscription(client)["id"])
        response = client.post(
            f"/api/v1/subscriptions/{identifier}/execute",
            json={
                **_request(),
                "enable_mediacrawler": enabled,
                "accept_mediacrawler_license": False,
            },
        )
        terminal = _wait_terminal(client, response.json()["operation_id"])
        assert terminal["state"] == "failed_terminal" and terminal["error_code"] == error
        database = Database(settings.resolved_database_url)
        try:
            with database.session() as session:
                assert session.scalar(select(func.count()).select_from(Job)) == 0
                assert session.get(Subscription, identifier).schedule_revision == 0
        finally:
            database.dispose()


def test_non_cancellable_delivery_survives_cancel_request_and_graceful_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    entered, release = threading.Event(), threading.Event()
    with _client(settings) as client:
        identifier = str(_subscription(client)["id"])
        _install_success_fakes(monkeypatch, target_subscription_id=identifier, entered=entered, release=release)
        response = client.post(f"/api/v1/subscriptions/{identifier}/execute", json=_request())
        operation_id = response.json()["operation_id"]
        assert entered.wait(2)
        assert client.get(f"/api/v1/operations/{operation_id}").json()["allowed_actions"] == []
        cancelled = client.post(f"/api/v1/operations/{operation_id}/cancel")
        assert cancelled.status_code == 409
        assert cancelled.json() == {"detail": "subscription_delivery_cancel_unsupported"}
        client.app.state.operations.shutdown(timeout_seconds=0)
        observed = client.get(f"/api/v1/operations/{operation_id}").json()
        assert observed["state"] == "running" and observed["cancel_requested_at"] is None
        release.set()
        assert _wait_terminal(client, operation_id)["state"] == "succeeded"


@pytest.mark.parametrize("failure", ["subject", "fence"])
def test_materialization_and_subject_are_rolled_back_with_operation_fence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    settings = _settings(tmp_path)
    with _client(settings) as client:
        identifier = str(_subscription(client)["id"])
        if failure == "subject":

            def reject(_self: object) -> object:
                def hook(*_args: object) -> None:
                    raise RuntimeError("synthetic subject unavailable")

                return hook

            monkeypatch.setattr(OperationExecutionContext, "subject_hook", property(reject))
        else:
            original = OperationExecutionContext.commit_effect

            def lose_fence(context: OperationExecutionContext, action: object) -> object:
                def effect(session: object) -> object:
                    result = action(session)
                    context.cancellation.set()
                    return result

                return original(context, effect)

            monkeypatch.setattr(OperationExecutionContext, "commit_effect", lose_fence)
        response = client.post(f"/api/v1/subscriptions/{identifier}/execute", json=_request())
        terminal = _wait_terminal(client, response.json()["operation_id"])
        assert terminal["state"] not in {"succeeded", "cancelled"}
        assert not any(subject["type"] == "job" for subject in terminal["subjects"])
        database = Database(settings.resolved_database_url)
        try:
            with database.session() as session:
                assert session.scalar(select(func.count()).select_from(Job)) == 0
                assert session.get(Subscription, identifier).schedule_revision == 0
        finally:
            database.dispose()
