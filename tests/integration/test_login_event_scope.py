"""Bind diagnostic identities only after the durable login subject commits."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from media_sync.application.authentication import AccountLoginError, AccountLoginRequest, MediaCrawlerQrLoginService
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.models import LoginSession
from media_sync.infrastructure.observability.events import validate_event as validate_store_event
from media_sync.infrastructure.observability.store import LogStore
from media_sync.integrations.mediacrawler import login_runner
from media_sync.integrations.mediacrawler.login import (
    MediaCrawlerLoginRequest,
    MediaCrawlerLoginResult,
    MediaCrawlerLoginStatus,
)
from media_sync.integrations.mediacrawler.login_events import DiagnosticHook, event
from tests.contract.test_mediacrawler_login import _runner, _write_fake_checkout
from tests.integration.test_mediacrawler_login_application import (
    STARTED_AT,
    UPSTREAM_SHA,
    _Clock,
    _seed_account,
    _session_count,
)
from tests.integration.test_mediacrawler_login_application import (
    database as database,
)


class DiagnosticRunner:
    def run(
        self,
        request: MediaCrawlerLoginRequest,
        *,
        on_account_locked: Callable[[], None] | None = None,
        diagnostic_hook: DiagnosticHook | None = None,
        **_kwargs: Any,
    ) -> MediaCrawlerLoginResult:
        assert diagnostic_hook is not None and on_account_locked is not None
        diagnostic_hook(event("preflight", "prepare", "started"))
        # A malicious injected identity must reject the whole child frame.
        bad = event("session_probe", "probe", "started")
        bad["login_session_id"] = str(uuid4())
        diagnostic_hook(bad)
        on_account_locked()
        diagnostic_hook(event("session_probe", "probe", "succeeded", elapsed_ms=12))
        return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.AUTHENTICATED, UPSTREAM_SHA)


def test_service_scopes_only_after_exact_durable_subject_commit(database: Database) -> None:
    account_id = _seed_account(database)
    recorded: list[Mapping[str, object]] = []
    subjects: list[str] = []

    def subject_hook(session: Any, subject: Any) -> None:
        subjects.append(subject.subject_id)
        assert session.get(LoginSession, subject.subject_id) is not None

    def diagnostic_hook(value: Mapping[str, object]) -> None:
        validate_store_event(value)
        if "login_session_id" in value:
            with database.session() as session:
                assert session.get(LoginSession, str(value["login_session_id"])) is not None
        recorded.append(value)

    result = MediaCrawlerQrLoginService(
        database,
        DiagnosticRunner(),
        clock=_Clock(STARTED_AT, STARTED_AT + timedelta(seconds=1)),
    ).run(AccountLoginRequest(account_id), subject_hook=subject_hook, diagnostic_hook=diagnostic_hook)
    assert len(recorded) == 2
    assert all(value["account_id"] == str(account_id) and value["platform"] == "bili" for value in recorded)
    assert "login_session_id" not in recorded[0]
    assert recorded[1]["login_session_id"] == str(result.login_session_id) == subjects[0]
    assert recorded[1]["duration_ms"] == 12
    assert "elapsed_ms" not in recorded[1] and "schema_version" not in recorded[1]
    assert "operation_id" not in recorded[1]


def test_failed_subject_commit_never_publishes_session_in_diagnostics(database: Database) -> None:
    account_id = _seed_account(database)
    recorded: list[Any] = []

    def failed_subject(_session: Any, _subject: Any) -> None:
        raise RuntimeError("PRIVATE-COMMIT-FAILURE")

    with pytest.raises(AccountLoginError):
        MediaCrawlerQrLoginService(database, DiagnosticRunner(), clock=lambda: STARTED_AT).run(
            AccountLoginRequest(account_id),
            subject_hook=failed_subject,
            diagnostic_hook=recorded.append,
        )
    assert len(recorded) == 1
    assert "login_session_id" not in recorded[0]
    assert _session_count(database) == 0


@pytest.mark.parametrize("mode", ["success", "browser_timeout"])
def test_real_isolated_child_through_real_service_to_persisted_log_segment(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    account_id = _seed_account(database)
    checkout = _write_fake_checkout(tmp_path / "checkout")
    (checkout / "mode.txt").write_text(mode, encoding="utf-8")
    frames: list[dict[str, object]] = []
    original_parser = login_runner._parse_child_frame

    def parse_frame(raw: bytes) -> MediaCrawlerLoginStatus:
        frames.append(json.loads(raw))
        return original_parser(raw)

    monkeypatch.setattr(login_runner, "_parse_child_frame", parse_frame)
    store = LogStore(tmp_path / "state" / "logs")
    accepted: list[bool] = []

    def sink(value: Mapping[str, object]) -> None:
        accepted.append(store.emit(value))

    try:
        outcome = MediaCrawlerQrLoginService(
            database,
            _runner(checkout, tmp_path / "runtime"),
            clock=_Clock(STARTED_AT, STARTED_AT + timedelta(seconds=1)),
        ).run(AccountLoginRequest(account_id, timeout_seconds=10), diagnostic_hook=sink)
        assert store.flush(timeout=5)
    finally:
        store.close()

    expected = "authenticated" if mode == "success" else "upstream_browser_timeout"
    assert outcome.runner_status.value == expected
    assert frames == [{"schema_version": 1, "status": expected}]
    assert accepted and all(accepted)
    status = store.status()
    assert status["invalid"] == status["dropped"] == 0
    assert status["written"] == len(accepted)
    assert status["sealed_segments"] >= 1
    result = store.query(login_session_id=str(outcome.login_session_id), limit=200)
    records = result["events"]
    assert records and all(record["login_session_id"] == str(outcome.login_session_id) for record in records)
    assert all(record["account_id"] == str(account_id) and record["platform"] == "bili" for record in records)
    assert any(record["phase"] == "session_probe" and record["event_code"] == "login_stage" for record in records)
    assert all("operation_id" not in record for record in records)
    assert all(record["writer_id"] == store.writer_id and record["schema_version"] == 1 for record in records)
    if mode == "browser_timeout":
        assert any(
            record["event_code"] == "login_terminal" and record["error_type"] == "playwright_timeout"
            for record in records
        )
    with database.session() as session:
        saved = session.get(LoginSession, str(outcome.login_session_id))
        assert saved is not None and saved.account_id == str(account_id)
        assert saved.status == ("succeeded" if mode == "success" else "failed")
    disk_bytes = b"".join(path.read_bytes() for path in (tmp_path / "state" / "logs").glob("*.jsonl"))
    assert b"PRIVATE" not in disk_bytes and b"https://" not in disk_bytes and b"Cookie" not in disk_bytes
