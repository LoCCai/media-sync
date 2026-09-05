"""Real, offline SQLite contention at the scheduler heartbeat boundary."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from threading import Event as ThreadEvent
from threading import get_ident
from time import perf_counter
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError

from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.database import SQLITE_BUSY_TIMEOUT_MS
from media_sync.infrastructure.db.models import Account, Content, Job, RunEvent, Subscription, SyncRun
from media_sync.scheduler.handlers import (
    SubscriptionHandlerRegistry,
    SubscriptionHandlerResult,
    SubscriptionJobContext,
)
from media_sync.scheduler.service import DurableSchedulerService, SubscriptionWorker

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
TEST_BUSY_TIMEOUT_MS = 100
PRIVATE_FILENAME = "SENTINEL-private-sqlite-location.sqlite3"


@pytest.fixture
def file_database(tmp_path: Path) -> Iterator[tuple[Database, Path]]:
    path = tmp_path / PRIVATE_FILENAME
    database = Database(f"sqlite+pysqlite:///{path.as_posix()}")

    @event.listens_for(database.engine, "connect")
    def shorten_only_this_test_connection_timeout(connection: Any, _record: Any) -> None:
        cursor = connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={TEST_BUSY_TIMEOUT_MS}")
        finally:
            cursor.close()

    database.create_schema()
    try:
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == TEST_BUSY_TIMEOUT_MS
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
            databases = connection.exec_driver_sql("PRAGMA database_list").all()
            assert [Path(row[2]).resolve() for row in databases if row[1] == "main"] == [path.resolve()]
        assert SQLITE_BUSY_TIMEOUT_MS == 5_000
        yield database, path
    finally:
        database.dispose()


def _seed(database: Database) -> tuple[str, str]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter="fake",
            display_name="Offline heartbeat contention account",
            login_method="saved_session",
            auth_status="authenticated",
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="bili", remote_id="offline-creator", display_name="Offline creator")
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            interval_seconds=60,
            max_items=1,
        )
        return account.id, subscription.id


class _WriterLockHandler:
    """Attach a running Run, then hold a genuinely independent SQLite writer."""

    def __init__(self, database: Database, path: Path) -> None:
        self.database = database
        self.path = path
        self.task: asyncio.Task[Any] | None = None
        self.run_id: str | None = None
        self.cancelled = False
        self.cleanup_complete = False
        self.lock_acquired_at = 0.0
        self.lock_released_at = 0.0

    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        self.task = asyncio.current_task()
        with self.database.session() as session:
            run = SyncRunRepository(session).create(
                subscription_id=str(context.subscription_id),
                status="running",
                attempt=context.attempt,
            )
            assert context.run_attacher is not None
            context.run_attacher(session, UUID(run.id), context.current_run_id)
            self.run_id = run.id

        # This is a second physical connection, not an injected OperationalError
        # or another Session that may share the same in-memory DB connection.
        writer = sqlite3.connect(self.path, isolation_level=None)
        try:
            writer.execute("BEGIN IMMEDIATE")
            self.lock_acquired_at = perf_counter()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        finally:
            writer.rollback()
            writer.close()
            self.lock_released_at = perf_counter()
            self.cleanup_complete = True
        raise AssertionError("the lock holder must be cancelled, not complete successfully")


async def test_real_file_sqlite_busy_heartbeat_joins_handler_before_failure_finalization(
    file_database: tuple[Database, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    database, path = file_database
    account_id, subscription_id = _seed(database)
    assert DurableSchedulerService(database, clock=lambda: NOW).tick(limit=1).materialized_count == 1
    handler = _WriterLockHandler(database, path)
    worker = SubscriptionWorker(database, SubscriptionHandlerRegistry({"fake": handler}), clock=lambda: NOW)
    original_heartbeat = worker._heartbeat
    original_finalize = worker._finalize
    heartbeat_finished = ThreadEvent()
    heartbeat_errors: list[OperationalError] = []
    heartbeat_threads: list[int] = []
    heartbeat_durations: list[float] = []
    finalization_observations: list[tuple[bool, bool, bool, bool]] = []
    event_loop_thread = get_ident()

    def observe_real_heartbeat(*args: Any, **kwargs: Any) -> None:
        heartbeat_threads.append(get_ident())
        started_at = perf_counter()
        try:
            original_heartbeat(*args, **kwargs)
        except OperationalError as error:
            heartbeat_errors.append(error)
            raise
        finally:
            heartbeat_durations.append(perf_counter() - started_at)
            heartbeat_finished.set()

    def observe_finalization(*args: Any, **kwargs: Any) -> Any:
        finalization_observations.append(
            (
                handler.cancelled,
                handler.cleanup_complete,
                handler.task is not None and handler.task.done(),
                heartbeat_finished.is_set(),
            )
        )
        return original_finalize(*args, **kwargs)

    # Observe and re-raise the real database exception unchanged; do not inject
    # a failure or replace the repository transaction/heartbeat implementation.
    monkeypatch.setattr(worker, "_heartbeat", observe_real_heartbeat)
    monkeypatch.setattr(worker, "_finalize", observe_finalization)
    result = await asyncio.wait_for(
        worker.run_once(worker_id="offline-worker", lease_seconds=60, heartbeat_interval_seconds=0.02),
        timeout=5,
    )

    assert len(heartbeat_errors) == 1
    actual_error = heartbeat_errors[0]
    assert isinstance(actual_error.orig, sqlite3.Error)
    assert type(actual_error.orig.sqlite_errorcode) is int
    assert actual_error.orig.sqlite_errorcode & 255 == sqlite3.SQLITE_BUSY
    assert heartbeat_threads and all(thread != event_loop_thread for thread in heartbeat_threads)
    assert heartbeat_durations[0] >= TEST_BUSY_TIMEOUT_MS / 1_000
    assert handler.lock_released_at - handler.lock_acquired_at > TEST_BUSY_TIMEOUT_MS / 1_000
    assert finalization_observations == [(True, True, True, True)]
    assert not any(task.get_coro().__qualname__ == "SubscriptionWorker._heartbeat_loop" for task in asyncio.all_tasks())
    assert result.status == "failed_terminal"
    assert result.error_code == "scheduler_heartbeat_storage_busy"
    assert result.run_id == handler.run_id

    with database.session() as session:
        job = session.get(Job, result.job_id)
        run = session.get(SyncRun, handler.run_id)
        account = session.get(Account, account_id)
        subscription = session.get(Subscription, subscription_id)
        assert job is not None and run is not None and account is not None and subscription is not None
        assert (job.status, job.last_error_code, job.run_id) == (
            "failed_terminal",
            "scheduler_heartbeat_storage_busy",
            run.id,
        )
        assert job.last_error_message is None
        assert job.lease_owner is None and job.lease_token is None and job.lease_expires_at is None
        assert job.attempts == 1 and job.finished_at == NOW
        assert (run.status, run.error_code, run.error_message, run.finished_at) == ("running", None, None, None)
        assert (run.discovered_count, run.updated_count, run.asset_count) == (0, 0, 0)
        assert (account.login_method, account.auth_status) == ("saved_session", "authenticated")
        assert subscription.checkpoint_revision == 0 and subscription.cursor is None
        assert subscription.consecutive_failures == 1 and subscription.last_success_at is None
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        events = session.scalars(select(RunEvent).where(RunEvent.run_id == run.id)).all()
        assert [(event.event_type, event.to_status) for event in events] == [("run_created", "running")]
        persisted_diagnostics = repr(
            (job.last_error_code, job.last_error_message, run.error_code, run.error_message)
        ) + repr([(event.message, event.payload) for event in events])

    captured = capsys.readouterr()
    outward = repr(asdict(result)) + persisted_diagnostics + captured.out + captured.err + caplog.text
    assert str(actual_error) not in outward
    assert "database is locked" not in outward
    assert "BEGIN IMMEDIATE" not in outward
    assert PRIVATE_FILENAME not in outward
    assert str(path) not in outward
