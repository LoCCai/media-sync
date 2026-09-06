"""Authenticated retained traces, closed diagnostic projection and configuration."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from _api_client import authenticated_test_client
from pydantic import ValidationError

from media_sync.application.log_center import LogCenterError, LogCenterService, _upstream_versions
from media_sync.config import Settings
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.infrastructure.db.models import Operation, OperationEvent, OperationSubject
from media_sync.infrastructure.observability.store import LogStore

PRIVATE = "PRIVATE-cookie-token-url-traceback-sentinel"


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


def _seed(settings: Settings, *, controls: int = 1, subjects: int = 1) -> tuple[str, str, str]:
    operation_id, account_id, session_id = (str(uuid4()) for _ in range(3))
    database = Database(settings.resolved_database_url)
    now = datetime.now(UTC)
    try:
        with database.session() as session:
            session.add(
                Operation(
                    id=operation_id,
                    kind="account-login",
                    state="failed_retryable",
                    phase=PRIVATE,
                    requested_at=now,
                    finished_at=now,
                    request_fingerprint="a" * 64,
                    target_type="account",
                    target_id=account_id,
                    error_code=PRIVATE,
                    requested_by=PRIVATE,
                    result_summary={"runner_status": "upstream_browser_timeout", "raw": PRIVATE},
                )
            )
            session.flush()
            for index in range(controls):
                session.add(
                    OperationEvent(
                        operation_id=operation_id,
                        stream_sequence=index + 1,
                        operation_sequence=index + 1,
                        event_code="operation_failed",
                        level="error",
                        phase=PRIVATE,
                        safe_context={"raw": PRIVATE},
                        message_key=PRIVATE,
                        to_state="failed_retryable",
                    )
                )
            for index in range(subjects):
                session.add(
                    OperationSubject(
                        operation_id=operation_id,
                        subject_type="login_session",
                        subject_id=session_id if index == 0 else str(uuid4()),
                        role="execution",
                    )
                )
    finally:
        database.dispose()
    return operation_id, account_id, session_id


def _stage(operation_id: str, account_id: str, session_id: str) -> dict[str, object]:
    return {
        "event_code": "login_stage",
        "module": "login",
        "level": "warning",
        "operation_id": operation_id,
        "account_id": account_id,
        "login_session_id": session_id,
        "platform": "wb",
        "phase": "qr_locate",
        "action": "wait_selector",
        "outcome": "failed",
        "error_type": "playwright_timeout",
        "source_frame": "locator",
        "duration_ms": 30_000,
    }


def test_retained_stage_api_diagnostic_and_restart_do_not_leak_free_database_values(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    operation_id, account_id, session_id = _seed(settings)
    with authenticated_test_client(settings) as client:
        store = client.app.state.log_store
        assert store.emit(_stage(operation_id, account_id, session_id))
        assert not store.emit({**_stage(operation_id, account_id, session_id), "message": PRIVATE})
        assert store.flush()
        response = client.get("/api/v1/logs", params={"operation_id": operation_id})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["events"][0]["login_session_id"] == session_id
        trace = client.get(f"/api/v1/logs/operations/{operation_id}")
        assert trace.status_code == 200
        data = trace.json()
        assert data["operation"]["state"] == "failed_retryable"
        assert data["operation"]["phase"] == "unknown"
        assert data["operation"]["runner_status"] == "upstream_browser_timeout"
        assert data["login_stage_evidence"] == "available_in_page"
        assert data["subjects"] == [{"type": "login_session", "id": session_id, "role": "execution"}]
        assert data["authentication_authority"] == "durable_account_state_only"
        diagnostic = client.get(f"/api/v1/logs/operations/{operation_id}/diagnostic")
        assert diagnostic.status_code == 200
        assert diagnostic.headers["content-type"] == "application/json"
        assert diagnostic.headers["content-disposition"].endswith(f'{operation_id}.json"')
        assert len(diagnostic.content) < 1_048_576
        assert diagnostic.json()["trace"]["operation"]["id"] == operation_id
        assert diagnostic.json()["upstreams"]["MediaCrawler"] == "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
        assert PRIVATE not in response.text + trace.text + diagnostic.text
        assert str(settings.state_dir) not in diagnostic.text
        assert client.get("/api/v1/logs/status").json()["invalid"] == 1
    with authenticated_test_client(settings) as restarted:
        response = restarted.get("/api/v1/logs", params={"login_session_id": session_id})
        assert response.status_code == 200
        assert len(response.json()["events"]) == 1
        assert response.json()["events"][0]["operation_id"] == operation_id
    for path in (settings.state_dir / "logs").iterdir():
        if path.is_file():
            assert PRIVATE.encode() not in path.read_bytes()


@pytest.mark.parametrize(
    "query",
    [
        "file=/etc/passwd",
        "module=login&module=api",
        "operation_id=not-a-uuid",
        "platform=unknown",
        "level=trace",
        "module=private",
        "event_code=raw",
        "since=not-a-date",
        "since=2026-09-07T00:00:00.000000Z&until=2026-09-06T00:00:00.000000Z",
        "cursor=%%%",
        "cursor=" + "x" * 3000,
    ],
)
def test_query_rejects_unsupported_or_ambiguous_values(tmp_path: Path, query: str) -> None:
    with authenticated_test_client(_settings(tmp_path)) as client:
        response = client.get("/api/v1/logs?" + query)
        assert response.status_code == 400
        assert response.json()["detail"] in {"log_query_invalid", "log_cursor_invalid"}


@pytest.mark.parametrize("limit", ["0", "201", "true", PRIVATE])
def test_query_limit_is_bounded_and_does_not_echo_input(tmp_path: Path, limit: str) -> None:
    with authenticated_test_client(_settings(tmp_path)) as client:
        response = client.get("/api/v1/logs", params={"limit": limit})
        assert response.status_code == 422
        assert PRIVATE not in response.text


def test_cursor_pages_and_restart_staleness(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    operation_id = str(uuid4())
    with authenticated_test_client(settings) as client:
        store = client.app.state.log_store
        for _ in range(3):
            assert store.emit(
                {"event_code": "operation_started", "module": "login", "level": "info", "operation_id": operation_id}
            )
        assert store.flush()
        params = {"operation_id": operation_id, "limit": 1}
        first = client.get("/api/v1/logs", params=params).json()
        assert len(first["events"]) == 1 and first["next_cursor"]
        second = client.get("/api/v1/logs", params={**params, "cursor": first["next_cursor"]}).json()
        assert first["events"][0]["sequence"] != second["events"][0]["sequence"]
    with authenticated_test_client(settings) as restarted:
        response = restarted.get("/api/v1/logs", params={**params, "cursor": first["next_cursor"]})
        assert response.status_code == 409
        assert response.json() == {"detail": "log_cursor_stale"}


def test_old_operation_has_explicit_missing_stage_evidence_and_bounded_controls(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    operation_id, _, _ = _seed(settings, controls=201, subjects=65)
    with authenticated_test_client(settings) as client:
        data = client.get(f"/api/v1/logs/operations/{operation_id}").json()
        assert data["login_stage_evidence"] == "not_recorded_or_not_in_retained_page"
        assert len(data["control_events"]) == 200 and data["control_events_truncated"] is True
        assert len(data["subjects"]) == 64 and data["subjects_truncated"] is True
        for suffix in ("", "/diagnostic"):
            assert client.get(f"/api/v1/logs/operations/{uuid4()}{suffix}").status_code == 404
            assert client.get(f"/api/v1/logs/operations/invalid{suffix}").status_code == 400


def test_api_safe_handler_never_formats_message_and_does_not_log_log_polling(tmp_path: Path) -> None:
    class Unformattable:
        def __str__(self) -> str:
            raise AssertionError("private log args must not be formatted")

    with authenticated_test_client(_settings(tmp_path)) as client:
        store = client.app.state.log_store
        logger = logging.getLogger("media_sync.diagnostic_fixture")
        propagate = logger.propagate
        logger.propagate = False
        try:
            record = logging.LogRecord(logger.name, logging.ERROR, PRIVATE, 1, Unformattable(), (), None)
            # Exercise installed handler without pytest's separate raw log capture.
            handlers = logging.getLogger("media_sync").handlers
            for handler in handlers:
                handler.handle(record)
        finally:
            logger.propagate = propagate
        assert store.flush()
        before = store.status()["accepted"]
        data = client.get("/api/v1/logs", params={"event_code": "application_log_redacted"}).json()
        assert len(data["events"]) == 1
        assert PRIVATE not in json.dumps(data)
        assert client.get("/api/v1/logs/status").status_code == 200
        assert store.status()["accepted"] == before


def test_diagnostic_encoded_cap_and_lock_projection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    operation_id, _, _ = _seed(settings)
    database = Database(settings.resolved_database_url)
    store = LogStore(settings.state_dir / "logs")
    try:
        service = LogCenterService(database, store, settings)
        monkeypatch.setattr("media_sync.application.log_center.MAX_DIAGNOSTIC_BYTES", 64)
        with pytest.raises(LogCenterError, match=r"^log_diagnostic_too_large$"):
            service.diagnostic_bytes(operation_id)
    finally:
        store.close()
        database.dispose()
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"upstreams": [{"name": "MediaCrawler", "commit": PRIVATE}]}))
    assert _upstream_versions(lock) == {"MediaCrawler": None, "bili-sync-up": None}
    lock.write_text("x" * 65_537)
    assert _upstream_versions(lock) == {"MediaCrawler": None, "bili-sync-up": None}


@pytest.mark.parametrize(
    "field,value",
    [
        ("log_segment_max_bytes", True),
        ("log_segment_max_bytes", 1.5),
        ("log_segment_max_bytes", "1.5"),
        ("log_segment_max_bytes", 16383),
        ("log_total_max_bytes", 1_048_575),
        ("log_total_max_bytes", 10_737_418_241),
        ("log_retention_days", 0),
        ("log_retention_days", 91),
        ("log_retention_days", False),
    ],
)
def test_log_limits_reject_coercion_and_unbounded_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)


def test_log_defaults_environment_and_two_segment_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None)
    assert (settings.log_segment_max_bytes, settings.log_total_max_bytes, settings.log_retention_days) == (
        16_777_216,
        1_073_741_824,
        7,
    )
    monkeypatch.setenv("MEDIA_SYNC_LOG_RETENTION_DAYS", "14")
    assert Settings(_env_file=None).log_retention_days == 14
    with pytest.raises(ValidationError):
        Settings(log_segment_max_bytes=1_048_576, log_total_max_bytes=1_048_576, _env_file=None)
