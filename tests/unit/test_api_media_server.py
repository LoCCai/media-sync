"""Safe API projections for media-server posture and qualifications."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import media_sync.interfaces.api as api_module
from media_sync.application.media_server_observation import MediaServerAuthorLookupResult
from media_sync.application.media_server_publication import MediaServerPublicationTarget
from media_sync.application.operation_payloads import operation_request_fingerprint, operation_result_summary
from media_sync.application.operations import OperationOutcome
from media_sync.config import Settings
from media_sync.infrastructure.db import Database, JobRepository, Operation, OperationRepository
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.interfaces.api import create_api_app
from media_sync.ports.media_server import MediaServerError, MediaServerProbeResult, MediaServerScanResult


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "exports",
        job_dir=tmp_path / "jobs",
        mediacrawler_runtime_dir=tmp_path / "mediacrawler",
        **overrides,
    )


def _client_for_settings(settings: Settings) -> TestClient:
    upgrade_database(settings.resolved_database_url)
    return TestClient(create_api_app(settings))


def _client(tmp_path: Path, **overrides: object) -> TestClient:
    return _client_for_settings(_settings(tmp_path, **overrides))


def _seed_media_server_operation(
    settings: Settings,
    *,
    kind: str,
    profile_fingerprint: str,
    at: datetime,
    succeeded: bool,
) -> str:
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            repository = OperationRepository(session)
            started = repository.create_or_replay(
                kind=kind,
                request_fingerprint=profile_fingerprint,
                exclusive_key=f"media-server:{profile_fingerprint}",
                phase="preparing",
                at=at,
            )
            if not succeeded:
                return started.operation_id
            lease = repository.claim(
                started.operation_id,
                expected_revision=started.revision,
                lease_owner=f"test-{kind}",
                lease_seconds=30,
                at=at,
            )
            if kind == "media-server-probe":
                result = {
                    "provider": "emby",
                    "server_version": "4.9.0",
                    "library_id_digest": "d" * 64,
                    "library_present": True,
                }
            else:
                assert kind == "media-server-scan"
                result = {
                    "provider": "emby",
                    "server_version": "4.9.0",
                    "library_id_digest": "d" * 64,
                    "scan_state": "accepted",
                }
            repository.finish_succeeded(
                started.operation_id,
                expected_revision=lease.revision,
                lease_owner=lease.lease_owner,
                lease_token=lease.lease_token,
                result_summary=operation_result_summary(kind, result),
                at=at + timedelta(microseconds=1),
            )
            return started.operation_id
    finally:
        database.dispose()


def _wait_terminal(client: TestClient, operation_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/operations/{operation_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["state"] not in {"queued", "running"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("media-server operation did not finish")


class _FakeMediaServerService:
    configured = True
    operations_enabled = True
    profile_fingerprint = "b" * 64

    def __init__(self) -> None:
        self.probe_calls = 0
        self.scan_calls = 0
        self.probe_error: MediaServerError | None = None
        self.scan_error: MediaServerError | None = None
        self.scan_entered = threading.Event()
        self.scan_release = threading.Event()
        self.block_scan = False

    def probe(self) -> MediaServerProbeResult:
        self.probe_calls += 1
        if self.probe_error is not None:
            raise self.probe_error
        return MediaServerProbeResult("emby", "4.9.0", "b" * 64)

    def scan(self, cancel_requested: Any) -> MediaServerScanResult:
        self.scan_calls += 1
        self.scan_entered.set()
        if self.block_scan:
            assert self.scan_release.wait(5)
        if cancel_requested():
            raise MediaServerError("media_server_scan_cancelled")
        if self.scan_error is not None:
            raise self.scan_error
        return MediaServerScanResult("emby", "4.9.0", "b" * 64)


class _FakeMediaServerObservationService:
    def __init__(self, targets: dict[str, MediaServerPublicationTarget]) -> None:
        self.targets = targets
        self.resolve_calls: list[str] = []
        self.lookup_calls: list[str] = []
        self.observe_calls: list[tuple[MediaServerPublicationTarget, object]] = []
        self.lookup_result: MediaServerAuthorLookupResult | MediaServerError | None = None
        self.observe_result = OperationOutcome.failed(
            "media_server_scan_observation_precondition_failed",
            retryable=False,
        )
        self.before_observe: Any = None

    def resolve_target(self, author_id: str) -> MediaServerPublicationTarget:
        self.resolve_calls.append(author_id)
        try:
            return self.targets[author_id]
        except KeyError:
            raise MediaServerError("media_server_publication_not_ready") from None

    def lookup_author(self, author_id: str) -> MediaServerAuthorLookupResult:
        self.lookup_calls.append(author_id)
        if isinstance(self.lookup_result, MediaServerError):
            raise self.lookup_result
        if self.lookup_result is None:
            raise AssertionError("lookup_result must be configured by the test")
        return self.lookup_result

    def observe_author(self, target: MediaServerPublicationTarget, context: Any) -> OperationOutcome:
        self.observe_calls.append((target, context))
        if self.before_observe is not None:
            self.before_observe(context)
        payload = self.observe_result.payload
        if (
            self.observe_result.state == "succeeded"
            and payload is not None
            and payload.get("observation_state") == "observed"
        ):
            accepted = dict(payload)
            accepted.update(observation_state="pending", match_count=0, verification_count=0)
            accepted.pop("item_fingerprint", None)
            accepted.pop("observed_at", None)
            context.checkpoint(phase="accepted", result_summary=accepted)
            context.checkpoint(phase="observed", result_summary=payload)
        return self.observe_result


def _publication_target(
    author_id: str,
    *,
    publication_job_id: str | None = None,
    publication_fingerprint: str = "c" * 64,
    selector_fingerprint: str = "d" * 64,
) -> MediaServerPublicationTarget:
    author_directory = f"bili-{author_id[:8]}"
    return MediaServerPublicationTarget(
        provider_key="media-sync-bili-creator",
        provider_value="private-provider-value",
        server_path=f"/srv/private-library/{author_directory}",
        author_id=author_id,
        publication_job_id=publication_job_id or str(uuid4()),
        platform="bili",
        author_relative_directory=author_directory,
        server_path_style="posix",
        publication_fingerprint=publication_fingerprint,
        selector_fingerprint=selector_fingerprint,
        managed_file_count=3,
    )


def _configured_media_server_settings(tmp_path: Path) -> Settings:
    return _settings(
        tmp_path,
        media_server_provider="emby",
        media_server_base_url="http://127.0.0.1:8096",
        media_server_library_id="private-library",
        media_server_api_key_secret_ref="env:MEDIA_SERVER_API_KEY",
        media_server_library_path="/srv/private-library",
        media_server_allowed_cidrs=("127.0.0.1/32",),
        media_server_operations_enabled=True,
    )


def _seed_succeeded_publication_job(settings: Settings, author_id: str) -> str:
    database = Database(settings.resolved_database_url)
    now = datetime(2026, 9, 5, 7, tzinfo=UTC)
    try:
        with database.session() as session:
            jobs = JobRepository(session)
            job = jobs.enqueue(
                job_type="export.emby",
                natural_key=f"api-test-publication:{author_id}",
                payload={"author_id": author_id},
                available_at=now,
            )
            claimed = jobs.claim(job.id, worker_id="api-test-publisher", lease_seconds=60, now=now)
            assert claimed is not None and claimed.lease_token is not None
            running = jobs.start(
                job.id,
                worker_id="api-test-publisher",
                lease_token=claimed.lease_token,
                now=now,
            )
            assert running.lease_token is not None
            jobs.complete(
                job.id,
                worker_id="api-test-publisher",
                lease_token=running.lease_token,
                now=now,
            )
            return job.id
    finally:
        database.dispose()


def _observation_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    server: _FakeMediaServerService,
    observation: _FakeMediaServerObservationService,
) -> tuple[TestClient, Settings]:
    settings = _configured_media_server_settings(tmp_path)
    profile_fingerprint = settings.media_server_profile_fingerprint
    assert profile_fingerprint is not None
    server.profile_fingerprint = profile_fingerprint
    monkeypatch.setattr(
        api_module.MediaServerService,
        "from_settings",
        classmethod(lambda _cls, _settings, _secret_resolver: server),
    )
    monkeypatch.setattr(
        api_module,
        "MediaServerObservationService",
        lambda _resolver, wired_server: observation if wired_server is server else None,
    )
    return _client_for_settings(settings), settings


def _fake_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    service: _FakeMediaServerService,
) -> TestClient:
    monkeypatch.setattr(
        api_module.MediaServerService,
        "from_settings",
        classmethod(lambda _cls, _settings, _secret_resolver: service),
    )
    return _client(tmp_path)


def test_unconfigured_media_server_and_qualifications_are_explicit(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    upgrade_database(settings.resolved_database_url)
    historical_profile = "f" * 64
    _seed_media_server_operation(
        settings,
        kind="media-server-probe",
        profile_fingerprint=historical_profile,
        at=datetime(2026, 9, 5, 1, tzinfo=UTC),
        succeeded=True,
    )
    _seed_media_server_operation(
        settings,
        kind="media-server-scan",
        profile_fingerprint=historical_profile,
        at=datetime(2026, 9, 5, 2, tzinfo=UTC),
        succeeded=False,
    )
    client = _client_for_settings(settings)

    status = client.get("/api/v1/media-server")
    assert status.status_code == 200
    assert status.json() == {
        "schema_version": 1,
        "configuration": {
            "configured": False,
            "provider": None,
            "origin": None,
            "library_id_digest": None,
            "profile_fingerprint": None,
            "verify_tls": True,
            "timeout_seconds": 10.0,
            "operations_enabled": False,
            "allowed_network_count": 0,
            "library_path_configured": False,
            "api_key_configured": False,
        },
        "latest_probe": None,
        "latest_scan": None,
        "allowed_actions": [],
    }

    lookup = client.get("/api/v1/media-server/items/by-author/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    assert lookup.status_code == 409
    assert lookup.headers["cache-control"] == "no-store"
    assert lookup.json() == {"detail": "media_server_not_configured"}

    qualifications = client.get("/api/v1/qualifications")
    assert qualifications.status_code == 200
    body = qualifications.json()
    assert body["schema_version"] == 1
    assert body["policy"]["automated_evidence_confers_human_pass"] is False
    assert [row["platform"] for row in body["platforms"]] == [
        "xhs",
        "dy",
        "ks",
        "bili",
        "wb",
        "tieba",
        "zhihu",
    ]
    media_capabilities = {row["capability"]: row for row in body["media_server"]["human_qualification"]}
    assert media_capabilities["connection_probe"]["human_status"] == "NOT_RUN"
    assert media_capabilities["scan_completion"] == {
        "capability": "scan_completion",
        "implementation_status": "NOT_IMPLEMENTED",
        "human_status": None,
    }
    assert body["media_server"]["automated_evidence"] == {
        "latest_probe": None,
        "latest_targeted_scan": None,
    }


def test_status_and_qualifications_only_use_current_profile_operations(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        media_server_provider="emby",
        media_server_base_url="http://127.0.0.1:8096",
        media_server_library_id="current-library",
        media_server_api_key_secret_ref="env:MEDIA_SERVER_API_KEY",
        media_server_library_path="/srv/current",
        media_server_allowed_cidrs=("127.0.0.1/32",),
        media_server_operations_enabled=True,
    )
    upgrade_database(settings.resolved_database_url)
    current_profile = settings.media_server_profile_fingerprint
    assert current_profile is not None
    other_profile = "e" * 64
    base_time = datetime(2026, 9, 5, 1, tzinfo=UTC)
    current_probe_id = _seed_media_server_operation(
        settings,
        kind="media-server-probe",
        profile_fingerprint=current_profile,
        at=base_time,
        succeeded=True,
    )
    other_probe_id = _seed_media_server_operation(
        settings,
        kind="media-server-probe",
        profile_fingerprint=other_profile,
        at=base_time + timedelta(minutes=1),
        succeeded=True,
    )
    other_scan_id = _seed_media_server_operation(
        settings,
        kind="media-server-scan",
        profile_fingerprint=other_profile,
        at=base_time + timedelta(minutes=2),
        succeeded=False,
    )
    client = _client_for_settings(settings)

    status = client.get("/api/v1/media-server")
    assert status.status_code == 200
    status_body = status.json()
    assert status_body["latest_probe"]["id"] == current_probe_id
    assert status_body["latest_scan"] is None
    assert status_body["allowed_actions"] == ["probe", "scan"]

    qualifications = client.get("/api/v1/qualifications")
    assert qualifications.status_code == 200
    evidence = qualifications.json()["media_server"]["automated_evidence"]
    assert evidence["latest_probe"]["operation_id"] == current_probe_id
    assert evidence["latest_targeted_scan"] is None
    serialized = json.dumps({"status": status_body, "evidence": evidence})
    assert other_probe_id not in serialized
    assert other_scan_id not in serialized


def test_configured_media_server_projection_omits_private_selectors(tmp_path: Path) -> None:
    secret_reference = "MEDIA_SERVER_API_KEY_SENTINEL"
    library_id = "private-library-id"
    server_path = r"D:\private-library-path"
    allowed_network = "127.0.0.0/8"
    client = _client(
        tmp_path,
        media_server_provider="emby",
        media_server_base_url="http://127.0.0.1:8096",
        media_server_library_id=library_id,
        media_server_api_key_secret_ref=f"env:{secret_reference}",
        media_server_library_path=server_path,
        media_server_allowed_cidrs=(allowed_network,),
        media_server_operations_enabled=True,
    )

    status = client.get("/api/v1/media-server")
    assert status.status_code == 200
    body = status.json()
    assert body["configuration"]["configured"] is True
    assert body["configuration"]["provider"] == "emby"
    assert body["configuration"]["origin"] == "http://127.0.0.1:8096"
    assert body["configuration"]["allowed_network_count"] == 1
    assert body["configuration"]["library_path_configured"] is True
    assert body["configuration"]["api_key_configured"] is True
    assert body["allowed_actions"] == ["probe", "scan"]

    settings = client.get("/api/v1/settings")
    assert settings.status_code == 200
    assert settings.json()["media_server"] == body["configuration"]

    serialized = json.dumps({"status": body, "settings_media_server": settings.json()["media_server"]})
    for forbidden in (secret_reference, library_id, server_path, allowed_network):
        assert forbidden not in serialized


def test_probe_and_scan_are_targetless_durable_idempotent_operations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _FakeMediaServerService()
    client = _fake_client(tmp_path, monkeypatch, service)

    probe = client.post(
        "/api/v1/media-server/probe",
        json={},
        headers={"Idempotency-Key": "probe-idempotency-key"},
    )
    assert probe.status_code == 202
    probe_terminal = _wait_terminal(client, probe.json()["operation_id"])
    assert probe_terminal["kind"] == "media-server-probe"
    assert probe_terminal["target"] is None
    assert probe_terminal["state"] == "succeeded"
    assert probe_terminal["result"] == {
        "provider": "emby",
        "server_version": "4.9.0",
        "library_id_digest": "b" * 64,
        "library_present": True,
    }

    replay = client.post(
        "/api/v1/media-server/probe",
        json={},
        headers={"Idempotency-Key": "probe-idempotency-key"},
    )
    assert replay.status_code == 202
    assert replay.json()["operation_id"] == probe.json()["operation_id"]
    assert replay.json()["replayed"] is True
    assert service.probe_calls == 1

    scan = client.post("/api/v1/media-server/scan", json={})
    assert scan.status_code == 202
    scan_terminal = _wait_terminal(client, scan.json()["operation_id"])
    assert scan_terminal["kind"] == "media-server-scan"
    assert scan_terminal["target"] is None
    assert scan_terminal["state"] == "succeeded"
    assert scan_terminal["result"] == {
        "provider": "emby",
        "server_version": "4.9.0",
        "library_id_digest": "b" * 64,
        "scan_state": "accepted",
    }
    assert "library_present" not in scan_terminal["result"]
    database = Database(_settings(tmp_path).resolved_database_url)
    try:
        with database.session() as session:
            stored = session.get(Operation, scan.json()["operation_id"])
            assert stored is not None
            assert stored.request_fingerprint == ("38940fd2eab5c1af56d1f6ab715f268227d8c65be6c60bb330fb7131e2d8930d")
    finally:
        database.dispose()


def test_media_server_operation_gate_rejects_overrides_and_disabled_state(tmp_path: Path) -> None:
    client = _client(tmp_path)

    assert client.post("/api/v1/media-server/probe", json={}).json()["detail"] == ("media_server_not_configured")
    override = client.post(
        "/api/v1/media-server/scan",
        json={"base_url": "http://private-sentinel", "api_key": "secret-sentinel"},
    )
    assert override.status_code == 422
    assert override.json()["detail"] == "request_validation_failed"
    assert "private-sentinel" not in override.text
    assert "secret-sentinel" not in override.text

    disabled = _client(
        tmp_path / "disabled",
        media_server_provider="jellyfin",
        media_server_base_url="https://media.example.test",
        media_server_library_id="library",
        media_server_api_key_secret_ref="env:MEDIA_SERVER_API_KEY",
        media_server_library_path="/srv/media",
        media_server_allowed_cidrs=("203.0.113.0/24",),
    )
    denied = disabled.post("/api/v1/media-server/probe", json={})
    assert denied.status_code == 403
    assert denied.json() == {"detail": "media_server_operations_disabled"}


def test_media_server_failure_retryability_and_pre_dispatch_cancel_are_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _FakeMediaServerService()
    service.probe_error = MediaServerError("media_server_timeout", retryable=True)
    client = _fake_client(tmp_path, monkeypatch, service)

    probe = client.post("/api/v1/media-server/probe", json={})
    terminal = _wait_terminal(client, probe.json()["operation_id"])
    assert terminal["state"] == "failed_retryable"
    assert terminal["retryable"] is True
    assert terminal["error_code"] == "media_server_timeout"

    service.block_scan = True
    scan = client.post("/api/v1/media-server/scan", json={})
    scan_id = scan.json()["operation_id"]
    assert service.scan_entered.wait(2)
    cancelled = client.post(f"/api/v1/operations/{scan_id}/cancel")
    assert cancelled.status_code == 200
    service.scan_release.set()
    scan_terminal = _wait_terminal(client, scan_id)
    assert scan_terminal["state"] == "cancelled"
    assert scan_terminal["error_code"] is None


def test_scan_acceptance_unknown_is_terminal_and_not_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _FakeMediaServerService()
    service.scan_error = MediaServerError("media_server_scan_acceptance_unknown", retryable=False)
    client = _fake_client(tmp_path, monkeypatch, service)

    started = client.post("/api/v1/media-server/scan", json={})
    terminal = _wait_terminal(client, started.json()["operation_id"])

    assert terminal["state"] == "failed_terminal"
    assert terminal["retryable"] is False
    assert terminal["error_code"] == "media_server_scan_acceptance_unknown"


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {"author_id": None},
        {"author_id": 7},
        {"author_id": "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"},
        {"author_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "path": "private-path-sentinel"},
        {"provider_value": "private-provider-sentinel"},
    ],
)
def test_author_scan_body_is_an_exact_strict_union_without_input_reflection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body: object,
) -> None:
    author_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    observation = _FakeMediaServerObservationService({author_id: _publication_target(author_id)})
    server = _FakeMediaServerService()
    client, _settings_value = _observation_client(tmp_path, monkeypatch, server, observation)

    response = client.post("/api/v1/media-server/scan", json=body)

    assert response.status_code == 422
    assert response.json()["detail"] == "request_validation_failed"
    assert "private-path-sentinel" not in response.text
    assert "private-provider-sentinel" not in response.text
    assert "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA" not in response.text
    assert observation.resolve_calls == []
    assert server.scan_calls == 0


def test_author_scan_resolver_failure_is_fixed_and_creates_no_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    observation = _FakeMediaServerObservationService({})
    client, _settings_value = _observation_client(
        tmp_path,
        monkeypatch,
        _FakeMediaServerService(),
        observation,
    )

    response = client.post("/api/v1/media-server/scan", json={"author_id": author_id})

    assert response.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "media_server_publication_not_ready"}
    assert author_id not in response.text
    assert observation.resolve_calls == [author_id]
    assert observation.observe_calls == []


@pytest.mark.parametrize("lookup_state", ["not_found", "matched"])
def test_author_lookup_returns_only_complete_safe_evidence_with_no_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lookup_state: str,
) -> None:
    author_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    target = _publication_target(author_id)
    observation = _FakeMediaServerObservationService({author_id: target})
    result = MediaServerAuthorLookupResult(
        schema_version=1,
        author_id=author_id,
        provider="emby",
        library_id_digest="b" * 64,
        publication_fingerprint=target.publication_fingerprint,
        selector_fingerprint=target.selector_fingerprint,
        lookup_state=lookup_state,  # type: ignore[arg-type]
        match_count=1 if lookup_state == "matched" else 0,
        item_fingerprint="e" * 64 if lookup_state == "matched" else None,
        observed_at="2026-09-05T08:00:00+00:00",
        complete=True,
    )
    observation.lookup_result = result
    client, _settings_value = _observation_client(
        tmp_path,
        monkeypatch,
        _FakeMediaServerService(),
        observation,
    )

    response = client.get(f"/api/v1/media-server/items/by-author/{author_id}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == result.as_dict()
    assert observation.lookup_calls == [author_id]
    serialized = response.text
    assert "private-provider-value" not in serialized
    assert "/srv/private-library" not in serialized
    assert "provider_value" not in serialized
    assert "server_path" not in serialized
    assert "item_id" not in serialized


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        ("media_server_address_forbidden", 503),
        ("media_server_authentication_failed", 503),
        ("media_server_body_limit", 503),
        ("media_server_dns_failed", 503),
        ("media_server_header_limit", 503),
        ("media_server_http_retryable", 503),
        ("media_server_http_terminal", 503),
        ("media_server_item_lookup_ambiguous", 409),
        ("media_server_item_lookup_incomplete", 503),
        ("media_server_library_ambiguous", 503),
        ("media_server_library_not_found", 503),
        ("media_server_library_path_mismatch", 503),
        ("media_server_not_configured", 409),
        ("media_server_operations_disabled", 403),
        ("media_server_provider_mismatch", 409),
        ("media_server_publication_changed", 409),
        ("media_server_publication_not_ready", 409),
        ("media_server_redirect_forbidden", 503),
        ("media_server_response_invalid", 503),
        ("media_server_scan_acceptance_unknown", 503),
        ("media_server_scan_cancelled", 503),
        ("media_server_scan_rejected", 503),
        ("media_server_schema_invalid", 503),
        ("media_server_secret_unavailable", 503),
        ("media_server_targeted_scan_unsupported", 503),
        ("media_server_timeout", 503),
        ("media_server_transport", 503),
    ],
)
def test_author_lookup_maps_only_fixed_errors_without_reflecting_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    status_code: int,
) -> None:
    author_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    observation = _FakeMediaServerObservationService({author_id: _publication_target(author_id)})
    observation.lookup_result = MediaServerError(code)
    client, _settings_value = _observation_client(
        tmp_path,
        monkeypatch,
        _FakeMediaServerService(),
        observation,
    )

    response = client.get(f"/api/v1/media-server/items/by-author/{author_id}")

    assert response.status_code == status_code
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": code}
    assert "private-provider-value" not in response.text
    assert "/srv/private-library" not in response.text


def test_author_lookup_rejects_noncanonical_uuid_and_disabled_gate_before_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    observation = _FakeMediaServerObservationService({author_id: _publication_target(author_id)})
    server = _FakeMediaServerService()
    client, _settings_value = _observation_client(tmp_path, monkeypatch, server, observation)

    invalid = client.get("/api/v1/media-server/items/by-author/private-author-sentinel")
    assert invalid.status_code == 409
    assert invalid.headers["cache-control"] == "no-store"
    assert invalid.json() == {"detail": "media_server_publication_not_ready"}
    assert "private-author-sentinel" not in invalid.text

    server.operations_enabled = False
    disabled = client.get(f"/api/v1/media-server/items/by-author/{author_id}")
    assert disabled.status_code == 403
    assert disabled.headers["cache-control"] == "no-store"
    assert disabled.json() == {"detail": "media_server_operations_disabled"}
    assert observation.lookup_calls == []


def test_author_scan_persists_identity_subjects_and_safe_observed_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    settings = _configured_media_server_settings(tmp_path)
    upgrade_database(settings.resolved_database_url)
    publication_job_id = _seed_succeeded_publication_job(settings, author_id)
    target = _publication_target(author_id, publication_job_id=publication_job_id)
    observation = _FakeMediaServerObservationService({author_id: target})
    server = _FakeMediaServerService()
    client, settings = _observation_client(tmp_path, monkeypatch, server, observation)
    profile_fingerprint = settings.media_server_profile_fingerprint
    assert profile_fingerprint is not None
    observed_result = {
        "schema_version": 2,
        "mode": "post_refresh_item_observation",
        "provider": "emby",
        "server_version": "4.9.5",
        "profile_fingerprint": profile_fingerprint,
        "library_id_digest": "b" * 64,
        "scan_state": "accepted",
        "publication_fingerprint": target.publication_fingerprint,
        "selector_fingerprint": target.selector_fingerprint,
        "baseline_state": "not_found",
        "observation_state": "observed",
        "match_count": 1,
        "verification_count": 2,
        "accepted_at": "2026-09-05T08:00:00+00:00",
        "item_fingerprint": "e" * 64,
        "observed_at": "2026-09-05T08:00:02+00:00",
    }
    observation.observe_result = OperationOutcome.success(observed_result)
    subjects_at_worker_start: list[tuple[str, str, str]] = []

    def inspect_subjects(context: Any) -> None:
        api_app: Any = client.app
        subjects_at_worker_start.extend(
            (subject.subject_type, subject.subject_id, subject.role)
            for subject in api_app.state.operations.list_subjects(context.operation_id)
        )

    observation.before_observe = inspect_subjects
    started = client.post(
        "/api/v1/media-server/scan",
        json={"author_id": author_id},
        headers={"Idempotency-Key": "author-observation-key"},
    )
    terminal = _wait_terminal(client, started.json()["operation_id"])

    assert started.status_code == 202
    assert terminal["state"] == "succeeded"
    assert terminal["target"] == {"type": "author", "id": author_id}
    assert terminal["result"] == observed_result
    assert [(row["type"], row["id"], row["role"]) for row in terminal["subjects"]] == [
        ("author", author_id, "target"),
        ("job", target.publication_job_id, "related"),
    ]
    assert subjects_at_worker_start == [
        ("author", author_id, "target"),
        ("job", target.publication_job_id, "related"),
    ]
    assert observation.resolve_calls == [author_id]
    assert len(observation.observe_calls) == 1
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            stored = session.get(Operation, started.json()["operation_id"])
            assert stored is not None
            assert stored.request_fingerprint == operation_request_fingerprint(
                "media-server-scan",
                target_id=author_id,
                parameters={
                    "profile_fingerprint": profile_fingerprint,
                    "mode": "post_refresh_item_observation",
                    "publication_fingerprint": target.publication_fingerprint,
                },
            )
    finally:
        database.dispose()


def test_author_scan_idempotency_binds_mode_author_profile_and_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    other_author_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    target = _publication_target(author_id)
    other_target = _publication_target(other_author_id)
    observation = _FakeMediaServerObservationService({author_id: target, other_author_id: other_target})
    server = _FakeMediaServerService()
    client, _settings_value = _observation_client(tmp_path, monkeypatch, server, observation)

    first = client.post(
        "/api/v1/media-server/scan",
        json={"author_id": author_id},
        headers={"Idempotency-Key": "same-author-key-01"},
    )
    assert first.status_code == 202
    _wait_terminal(client, first.json()["operation_id"])
    replay = client.post(
        "/api/v1/media-server/scan",
        json={"author_id": author_id},
        headers={"Idempotency-Key": "same-author-key-01"},
    )
    assert replay.status_code == 202
    assert replay.json()["operation_id"] == first.json()["operation_id"]
    assert replay.json()["replayed"] is True
    assert len(observation.observe_calls) == 1

    changed_author = client.post(
        "/api/v1/media-server/scan",
        json={"author_id": other_author_id},
        headers={"Idempotency-Key": "same-author-key-01"},
    )
    changed_mode = client.post(
        "/api/v1/media-server/scan",
        json={},
        headers={"Idempotency-Key": "same-author-key-01"},
    )
    assert changed_author.status_code == 409
    assert changed_author.json() == {"detail": "idempotency_key_reused"}
    assert changed_mode.status_code == 409
    assert changed_mode.json() == {"detail": "idempotency_key_reused"}

    publication_first = client.post(
        "/api/v1/media-server/scan",
        json={"author_id": author_id},
        headers={"Idempotency-Key": "publication-change-key"},
    )
    assert publication_first.status_code == 202
    _wait_terminal(client, publication_first.json()["operation_id"])
    observation.targets[author_id] = _publication_target(
        author_id,
        publication_fingerprint="f" * 64,
        selector_fingerprint="1" * 64,
    )
    changed_publication = client.post(
        "/api/v1/media-server/scan",
        json={"author_id": author_id},
        headers={"Idempotency-Key": "publication-change-key"},
    )
    assert changed_publication.status_code == 409
    assert changed_publication.json() == {"detail": "idempotency_key_reused"}

    profile_first = client.post(
        "/api/v1/media-server/scan",
        json={"author_id": author_id},
        headers={"Idempotency-Key": "profile-change-key"},
    )
    assert profile_first.status_code == 202
    _wait_terminal(client, profile_first.json()["operation_id"])
    server.profile_fingerprint = "9" * 64
    changed_profile = client.post(
        "/api/v1/media-server/scan",
        json={"author_id": author_id},
        headers={"Idempotency-Key": "profile-change-key"},
    )
    assert changed_profile.status_code == 409
    assert changed_profile.json() == {"detail": "idempotency_key_reused"}
