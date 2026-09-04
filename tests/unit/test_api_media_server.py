"""Safe API projections for media-server posture and qualifications."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import media_sync.interfaces.api as api_module
from media_sync.application.operation_payloads import operation_result_summary
from media_sync.config import Settings
from media_sync.infrastructure.db import Database, OperationRepository
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
    profile_fingerprint = "a" * 64

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
