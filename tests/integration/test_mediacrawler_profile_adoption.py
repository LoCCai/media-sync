"""Deterministic filesystem and database acceptance for WebUI profile adoption."""

from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from media_sync.application.mediacrawler_profile_adoption import (
    MediaCrawlerProfileAdoptionError,
    MediaCrawlerProfileAdoptionRequest,
    MediaCrawlerWebUIProfileAdoptionService,
)
from media_sync.domain import AuthStatus, LoginMethod, Platform
from media_sync.infrastructure.db import (
    Account,
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    LoginSessionRepository,
    SubscriptionRepository,
)
from media_sync.infrastructure.db.models import Job
from media_sync.integrations.mediacrawler import (
    MediaCrawlerAccountLock,
    MediaCrawlerLoginMode,
    MediaCrawlerLoginRequest,
    MediaCrawlerLoginResult,
    MediaCrawlerLoginStatus,
)
from media_sync.integrations.mediacrawler.policies import build_run_paths
from media_sync.scheduler import SchedulerRepository

UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
NOW = datetime(2026, 9, 6, 8, 30, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'adoption.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


class _Runner:
    def __init__(
        self,
        runtime_root: Path,
        result: object,
        *,
        after_observation: Callable[[], None] | None = None,
    ) -> None:
        self.runtime_root = runtime_root
        self.result = result
        self.after_observation = after_observation
        self.requests: list[MediaCrawlerLoginRequest] = []
        self.observed_cookie: bytes | None = None

    def run(
        self,
        request: MediaCrawlerLoginRequest,
        *,
        cancellation: threading.Event | None = None,
    ) -> MediaCrawlerLoginResult:
        self.requests.append(request)
        assert request.mode is MediaCrawlerLoginMode.SAVED_SESSION_PROBE
        assert cancellation is None or not cancellation.is_set()
        profile = build_run_paths(
            self.runtime_root,
            request.platform,
            request.account_id,
            request.account_id,
        ).profile_root
        self.observed_cookie = (profile / "Default" / "Cookies").read_bytes()
        (profile / "probe-observation").write_text("authenticated", encoding="utf-8")
        if self.after_observation is not None:
            self.after_observation()
        if isinstance(self.result, BaseException):
            raise self.result
        return cast(MediaCrawlerLoginResult, self.result)


def _result(status: MediaCrawlerLoginStatus = MediaCrawlerLoginStatus.AUTHENTICATED) -> MediaCrawlerLoginResult:
    return MediaCrawlerLoginResult(status, UPSTREAM_SHA)


def _seed_account(
    database: Database,
    *,
    adapter: str = "mediacrawler",
    method: str = "qr",
    status: str = "required",
    credential_ref: str | None = None,
    profile_path: str | None = None,
) -> UUID:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter=adapter,
            display_name=f"adoption-{uuid4()}",
            login_method=method,
            auth_status=status,
            credential_ref=credential_ref,
            profile_path=profile_path,
        )
        return UUID(account.id)


def _source_profile(runtime_root: Path) -> Path:
    profile = runtime_root / "webui-profiles" / "bili_user_data_dir"
    (profile / "Default").mkdir(parents=True)
    (profile / "Default" / "Cookies").write_bytes(b"verified-cookie-db")
    return profile


def _target_profile(runtime_root: Path, account_id: UUID) -> Path:
    return build_run_paths(runtime_root, Platform.BILI, account_id, account_id).profile_root


def _seed_waiting_jobs(database: Database, account_id: UUID) -> tuple[str, str]:
    job_ids: list[str] = []
    with database.session() as session:
        repository = SchedulerRepository(session)
        for index, status in enumerate(("waiting_auth", "waiting_user")):
            author = AuthorRepository(session).upsert(
                AuthorUpsert(platform="bili", remote_id=f"creator-{index}", display_name=f"Creator {index}")
            )
            subscription = SubscriptionRepository(session).create(
                account_id=str(account_id),
                author_id=author.id,
                interval_seconds=3_600,
                policy={"handler": "mediacrawler"},
            )
            cycle = repository.materialize_one(
                subscription.id,
                expected_schedule_revision=0,
                now=NOW,
            )
            job = session.get(Job, cycle.job_id)
            assert job is not None
            job.status = status
            job.last_error_code = "auth_expired" if status == "waiting_auth" else "schema_invalid"
            job_ids.append(job.id)
    return job_ids[0], job_ids[1]


def _temporary_account_entries(runtime_root: Path, account_id: UUID) -> set[str]:
    account_parent = runtime_root / "accounts" / "bili"
    return {entry.name for entry in account_parent.iterdir()} - {str(account_id)}


def test_success_replaces_old_profile_publishes_cas_and_resumes_only_waiting_auth(
    database: Database,
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    source = _source_profile(runtime_root)
    account_id = _seed_account(
        database,
        method="cookie",
        status="failed",
        credential_ref="env:OLD_PROFILE_COOKIE",
        profile_path="legacy-profile-override",
    )
    waiting_auth_id, waiting_user_id = _seed_waiting_jobs(database, account_id)
    target = _target_profile(runtime_root, account_id)
    target.mkdir(parents=True)
    (target / "old-state").write_text("must disappear", encoding="utf-8")
    outside = tmp_path / "outside-secret"
    outside.write_text("must not be copied", encoding="utf-8")
    # Symlink creation can require an explicit Windows developer setting; the
    # same no-follow branch is exercised on Linux CI.
    with contextlib.suppress(OSError):
        os.symlink(outside, source / "SingletonLock")
    runner = _Runner(runtime_root, _result())
    service = MediaCrawlerWebUIProfileAdoptionService(
        database,
        runner,
        integration_root=runtime_root,
        clock=lambda: NOW,
    )

    outcome = service.adopt_account(account_id, 0)

    assert outcome.account_id == account_id and outcome.platform is Platform.BILI
    assert outcome.login_method is LoginMethod.SAVED_SESSION
    assert outcome.auth_status is AuthStatus.AUTHENTICATED
    assert (outcome.auth_revision, outcome.resumed_job_count) == (1, 1)
    assert outcome.profile_file_count == 1 and outcome.profile_byte_count == len(b"verified-cookie-db")
    assert outcome.upstream_sha == UPSTREAM_SHA and runner.observed_cookie == b"verified-cookie-db"
    assert outcome.to_payload()["resumed_job_count"] == 1
    assert (source / "Default" / "Cookies").read_bytes() == b"verified-cookie-db"
    assert (target / "Default" / "Cookies").read_bytes() == b"verified-cookie-db"
    assert (target / "probe-observation").read_text(encoding="utf-8") == "authenticated"
    assert not (target / "old-state").exists() and not (target / "SingletonLock").exists()
    assert _temporary_account_entries(runtime_root, account_id) == set()
    assert not any(target.parent.glob(".profile-adoption-backup-*"))
    with database.session() as session:
        account = session.get(Account, str(account_id))
        waiting_auth = session.get(Job, waiting_auth_id)
        waiting_user = session.get(Job, waiting_user_id)
        assert account is not None
        assert (
            account.login_method,
            account.auth_status,
            account.credential_ref,
            account.profile_path,
            account.auth_revision,
            account.auth_updated_at,
        ) == ("saved_session", "authenticated", None, None, 1, NOW)
        assert waiting_auth is not None and (waiting_auth.status, waiting_auth.last_error_code) == ("queued", None)
        assert waiting_user is not None and (waiting_user.status, waiting_user.last_error_code) == (
            "waiting_user",
            "schema_invalid",
        )


def test_auth_revision_drift_after_probe_restores_old_profile_and_does_not_publish(
    database: Database,
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    _source_profile(runtime_root)
    account_id = _seed_account(database)
    target = _target_profile(runtime_root, account_id)
    target.mkdir(parents=True)
    (target / "old-state").write_text("original", encoding="utf-8")

    def drift() -> None:
        with database.session() as session:
            AccountRepository(session).set_auth_status(
                str(account_id),
                "failed",
                expected_status="required",
                at=NOW,
            )

    runner = _Runner(runtime_root, _result(), after_observation=drift)
    service = MediaCrawlerWebUIProfileAdoptionService(
        database,
        runner,
        integration_root=runtime_root,
        clock=lambda: NOW,
    )

    with pytest.raises(MediaCrawlerProfileAdoptionError) as captured:
        service.adopt(MediaCrawlerProfileAdoptionRequest(account_id, 0))

    assert captured.value.code == "profile_adoption_conflict"
    assert (target / "old-state").read_text(encoding="utf-8") == "original"
    assert not (target / "Default").exists() and not any(target.parent.glob(".profile-adoption-backup-*"))
    assert _temporary_account_entries(runtime_root, account_id) == set()
    with database.session() as session:
        account = session.get(Account, str(account_id))
        assert account is not None
        assert (account.login_method, account.auth_status, account.auth_revision) == ("qr", "failed", 1)


@pytest.mark.parametrize(
    ("runner_result", "expected_code"),
    [
        (_result(MediaCrawlerLoginStatus.EXPIRED), "profile_adoption_probe_failed"),
        (_result(MediaCrawlerLoginStatus.CONFIGURATION_INVALID), "profile_adoption_probe_unavailable"),
        (object(), "profile_adoption_result_invalid"),
        (RuntimeError("Cookie=PRIVATE-SENTINEL"), "profile_adoption_probe_unavailable"),
    ],
)
def test_failed_probe_never_changes_account_or_existing_profile(
    database: Database,
    tmp_path: Path,
    runner_result: object,
    expected_code: str,
) -> None:
    runtime_root = tmp_path / "runtime"
    _source_profile(runtime_root)
    account_id = _seed_account(database)
    target = _target_profile(runtime_root, account_id)
    target.mkdir(parents=True)
    (target / "old-state").write_text("original", encoding="utf-8")
    service = MediaCrawlerWebUIProfileAdoptionService(
        database,
        _Runner(runtime_root, runner_result),
        integration_root=runtime_root,
    )

    with pytest.raises(MediaCrawlerProfileAdoptionError) as captured:
        service.adopt_account(account_id, 0)

    assert captured.value.code == expected_code
    assert "PRIVATE-SENTINEL" not in str(captured.value)
    assert (target / "old-state").read_text(encoding="utf-8") == "original"
    assert _temporary_account_entries(runtime_root, account_id) == set()
    with database.session() as session:
        account = session.get(Account, str(account_id))
        assert account is not None
        assert (account.login_method, account.auth_status, account.auth_revision) == ("qr", "required", 0)


def test_empty_or_missing_source_fails_before_runner_and_leaves_no_temporary_account(
    database: Database,
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    account_id = _seed_account(database)
    runner = _Runner(runtime_root, _result())
    service = MediaCrawlerWebUIProfileAdoptionService(database, runner, integration_root=runtime_root)

    with pytest.raises(MediaCrawlerProfileAdoptionError) as missing:
        service.adopt_account(account_id, 0)
    assert missing.value.code == "profile_adoption_source_missing"
    empty = runtime_root / "webui-profiles" / "bili_user_data_dir"
    empty.mkdir(parents=True)
    with pytest.raises(MediaCrawlerProfileAdoptionError) as blank:
        service.adopt_account(account_id, 0)
    assert blank.value.code == "profile_adoption_source_empty"

    assert runner.requests == []
    assert _temporary_account_entries(runtime_root, account_id) == set()


def test_real_account_lock_blocks_replacement_after_probe(database: Database, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    _source_profile(runtime_root)
    account_id = _seed_account(database)
    target = _target_profile(runtime_root, account_id)
    target.mkdir(parents=True)
    (target / "old-state").write_text("original", encoding="utf-8")
    held = MediaCrawlerAccountLock(runtime_root, Platform.BILI, account_id)
    assert held.acquire()
    try:
        service = MediaCrawlerWebUIProfileAdoptionService(
            database,
            _Runner(runtime_root, _result()),
            integration_root=runtime_root,
        )
        with pytest.raises(MediaCrawlerProfileAdoptionError) as captured:
            service.adopt_account(account_id, 0)
    finally:
        held.release()

    assert captured.value.code == "profile_adoption_busy"
    assert (target / "old-state").read_text(encoding="utf-8") == "original"
    assert _temporary_account_entries(runtime_root, account_id) == set()


def test_active_qr_and_wrong_adapter_are_rejected_before_source_or_probe(database: Database, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    account_id = _seed_account(database)
    with database.session() as session:
        login = LoginSessionRepository(session).create(account_id=str(account_id), method="qr")
        login.status = "waiting_user"
    runner = _Runner(runtime_root, _result())
    service = MediaCrawlerWebUIProfileAdoptionService(database, runner, integration_root=runtime_root)

    with pytest.raises(MediaCrawlerProfileAdoptionError) as busy:
        service.adopt_account(account_id, 0)
    assert busy.value.code == "profile_adoption_busy"

    native_id = _seed_account(database, adapter="native")
    with pytest.raises(MediaCrawlerProfileAdoptionError) as ineligible:
        service.adopt_account(native_id, 0)
    assert ineligible.value.code == "profile_adoption_account_ineligible"
    assert runner.requests == []


def test_pre_cancelled_request_does_not_read_database_or_source(database: Database, tmp_path: Path) -> None:
    cancellation = threading.Event()
    cancellation.set()
    service = MediaCrawlerWebUIProfileAdoptionService(
        database,
        _Runner(tmp_path / "runtime", _result()),
        integration_root=tmp_path / "runtime",
    )

    with pytest.raises(MediaCrawlerProfileAdoptionError) as captured:
        service.adopt_account(uuid4(), 0, cancellation=cancellation)

    assert captured.value.code == "profile_adoption_cancelled"
    assert not (tmp_path / "runtime").exists()
