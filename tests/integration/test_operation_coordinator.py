"""Integration coverage for durable process-local operation coordination."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from media_sync.application.operations import (
    DurableSubjectRef,
    OperationCoordinator,
    OperationExecution,
    OperationExecutionContext,
    OperationOutcome,
)
from media_sync.infrastructure.db import (
    AccountRepository,
    Database,
    Job,
    JobRepository,
    LoginSessionRepository,
    Operation,
    OperationEvent,
    OperationRepository,
    OperationSubjectInput,
)

NOW = datetime(2026, 9, 4, 8, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'coordinator.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _execution(
    execute: object,
    *,
    suffix: int = 1,
    idempotent: bool = True,
) -> OperationExecution:
    assert callable(execute)
    return OperationExecution(
        kind="scheduler-run",
        request_fingerprint=f"{suffix:064x}",
        idempotency_key_hash=f"{suffix + 100:064x}" if idempotent else None,
        exclusive_key="scheduler-run:global",
        execute=execute,
    )


def _wait_terminal(
    coordinator: OperationCoordinator,
    operation_id: str,
    *,
    timeout: float = 5,
) -> Operation:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with coordinator._database.session() as session:
            operation = session.get(Operation, operation_id)
            assert operation is not None
            if operation.state not in {"queued", "running"}:
                return operation
        time.sleep(0.01)
    raise AssertionError("operation did not reach a terminal state")


def test_submit_commits_claim_before_callable_and_replay_never_executes(database: Database) -> None:
    entered = threading.Event()
    release = threading.Event()
    observed_states: list[str] = []
    calls = 0

    def execute(_context: object) -> OperationOutcome:
        nonlocal calls
        calls += 1
        with Database(database.url).session() as session:
            operation = session.scalar(select(Operation))
            assert operation is not None
            observed_states.append(operation.state)
        entered.set()
        assert release.wait(5)
        return OperationOutcome.success({"statuses": ["succeeded"]})

    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    first = coordinator.submit(_execution(execute))
    assert entered.wait(5)
    replay = coordinator.submit(_execution(execute))

    assert replay.replayed is True
    assert replay.operation_id == first.operation_id
    assert observed_states == ["running"]
    assert calls == 1

    release.set()
    terminal = _wait_terminal(coordinator, first.operation_id)
    assert terminal.state == "succeeded"
    assert terminal.result_summary == {"processed_count": 1, "status_counts": {"succeeded": 1}}
    coordinator.shutdown()


def test_two_coordinators_concurrently_replay_one_identity_and_one_callable(database: Database) -> None:
    barrier = threading.Barrier(2)
    release = threading.Event()
    calls_lock = threading.Lock()
    calls = 0

    def execute(_context: object) -> OperationOutcome:
        nonlocal calls
        with calls_lock:
            calls += 1
        assert release.wait(5)
        return OperationOutcome.success({"statuses": []})

    coordinators = (
        OperationCoordinator(Database(database.url), heartbeat_interval_seconds=0.05),
        OperationCoordinator(Database(database.url), heartbeat_interval_seconds=0.05),
    )

    def submit(index: int) -> tuple[str, bool]:
        barrier.wait(timeout=5)
        result = coordinators[index].submit(_execution(execute, suffix=2))
        return result.operation_id, result.replayed

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        assert len({operation_id for operation_id, _replayed in results}) == 1
        assert sorted(replayed for _operation_id, replayed in results) == [False, True]
        assert calls == 1
        release.set()
        _wait_terminal(coordinators[0], results[0][0])
    finally:
        release.set()
        for coordinator in coordinators:
            coordinator.shutdown()
            coordinator._database.dispose()


def test_cancel_observed_once_and_domain_success_wins_race(database: Database) -> None:
    entered = threading.Event()

    def execute(context: object) -> OperationOutcome:
        cancellation = context.cancellation
        entered.set()
        assert cancellation.wait(5)
        return OperationOutcome.success({"statuses": ["succeeded"]})

    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    submission = coordinator.submit(_execution(execute, suffix=3))
    assert entered.wait(5)
    requested = coordinator.request_cancel(submission.operation_id)
    assert requested.cancel_requested_at is not None

    terminal = _wait_terminal(coordinator, submission.operation_id)
    assert terminal.state == "succeeded"
    assert terminal.cancel_requested_at is not None
    events = coordinator.events_for_operation(submission.operation_id)
    assert [event.event_code for event in events].count("operation_cancel_observed") == 1
    observed = next(event for event in events if event.event_code == "operation_cancel_observed")
    assert observed.safe_context == {"phase": "starting"}
    coordinator.shutdown()


def test_central_monitor_heartbeats_one_blocked_execution(database: Database) -> None:
    entered = threading.Event()
    release = threading.Event()

    def execute(_context: object) -> OperationOutcome:
        entered.set()
        assert release.wait(5)
        return OperationOutcome.success({"statuses": []})

    coordinator = OperationCoordinator(
        database,
        lease_seconds=2,
        heartbeat_interval_seconds=0.05,
    )
    submission = coordinator.submit(_execution(execute, suffix=4))
    assert entered.wait(5)
    initial_revision = submission.operation.revision
    deadline = time.monotonic() + 3
    observed_revision = initial_revision
    while time.monotonic() < deadline and observed_revision == initial_revision:
        observed_revision = coordinator.get(submission.operation_id).revision
        time.sleep(0.02)
    assert observed_revision > initial_revision

    release.set()
    assert _wait_terminal(coordinator, submission.operation_id).state == "succeeded"
    coordinator.shutdown()


def test_terminal_intent_survives_all_inline_write_retries_and_monitor_finishes(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_finish = OperationRepository.finish_succeeded
    finish_calls = 0

    def fail_inline_retries(
        repository: OperationRepository,
        *args: object,
        **kwargs: object,
    ) -> object:
        nonlocal finish_calls
        finish_calls += 1
        if finish_calls <= 4:
            raise RuntimeError("transient terminal write failure")
        return original_finish(repository, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(OperationRepository, "finish_succeeded", fail_inline_retries)
    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.01)
    submission = coordinator.submit(_execution(lambda _context: OperationOutcome.success({"statuses": []}), suffix=40))

    terminal = _wait_terminal(coordinator, submission.operation_id)

    assert terminal.state == "succeeded"
    assert finish_calls >= 5
    coordinator.shutdown()


def test_progress_and_cancel_retry_from_fresh_authoritative_transactions(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_progress = OperationRepository.progress
    original_cancel = OperationRepository.request_cancel
    progress_calls = 0
    cancel_calls = 0
    entered = threading.Event()

    def flaky_progress(
        repository: OperationRepository,
        *args: object,
        **kwargs: object,
    ) -> object:
        nonlocal progress_calls
        if kwargs.get("event_code", "operation_progressed") == "operation_progressed":
            progress_calls += 1
            if progress_calls == 1:
                raise RuntimeError("transient progress write failure")
        return original_progress(repository, *args, **kwargs)  # type: ignore[arg-type]

    def flaky_cancel(
        repository: OperationRepository,
        *args: object,
        **kwargs: object,
    ) -> object:
        nonlocal cancel_calls
        cancel_calls += 1
        if cancel_calls == 1:
            raise RuntimeError("transient cancel write failure")
        return original_cancel(repository, *args, **kwargs)  # type: ignore[arg-type]

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        context.progress(phase="working", current=1, total=1, unit="items")
        entered.set()
        assert context.cancellation.wait(5)
        return OperationOutcome.success({"statuses": ["succeeded"]})

    monkeypatch.setattr(OperationRepository, "progress", flaky_progress)
    monkeypatch.setattr(OperationRepository, "request_cancel", flaky_cancel)
    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    submission = coordinator.submit(_execution(execute, suffix=41))
    assert entered.wait(5)

    coordinator.request_cancel(submission.operation_id)
    terminal = _wait_terminal(coordinator, submission.operation_id)

    assert terminal.state == "succeeded"
    assert progress_calls == 2
    assert cancel_calls == 2
    events = coordinator.events_for_operation(submission.operation_id)
    assert [event.event_code for event in events].count("operation_progressed") == 1
    assert [event.event_code for event in events].count("operation_cancel_requested") == 1
    coordinator.shutdown()


def test_heartbeat_transient_failure_retries_without_false_cancellation(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_heartbeat = OperationRepository.heartbeat
    heartbeat_calls = 0
    heartbeat_retried = threading.Event()
    release = threading.Event()
    cancellation_seen: list[bool] = []

    def flaky_heartbeat(
        repository: OperationRepository,
        *args: object,
        **kwargs: object,
    ) -> object:
        nonlocal heartbeat_calls
        heartbeat_calls += 1
        if heartbeat_calls == 1:
            raise RuntimeError("transient heartbeat write failure")
        heartbeat_retried.set()
        return original_heartbeat(repository, *args, **kwargs)  # type: ignore[arg-type]

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        assert release.wait(5)
        cancellation_seen.append(context.cancellation.is_set())
        return OperationOutcome.success({"statuses": []})

    monkeypatch.setattr(OperationRepository, "heartbeat", flaky_heartbeat)
    coordinator = OperationCoordinator(database, lease_seconds=2, heartbeat_interval_seconds=0.01)
    submission = coordinator.submit(_execution(execute, suffix=42))
    assert heartbeat_retried.wait(5)
    release.set()

    assert _wait_terminal(coordinator, submission.operation_id).state == "succeeded"
    assert heartbeat_calls >= 2
    assert cancellation_seen == [False]
    coordinator.shutdown()


def test_fast_heartbeat_finish_race_stress_never_leaves_running(database: Database) -> None:
    coordinator = OperationCoordinator(database, lease_seconds=2, heartbeat_interval_seconds=0.001)
    try:
        for index in range(30):
            entered = threading.Event()
            release = threading.Event()

            def execute(
                _context: OperationExecutionContext,
                ready: threading.Event = entered,
                gate: threading.Event = release,
            ) -> OperationOutcome:
                ready.set()
                assert gate.wait(5)
                return OperationOutcome.success({"statuses": ["succeeded"]})

            submission = coordinator.submit(_execution(execute, suffix=100 + index))
            assert entered.wait(5)
            deadline = time.monotonic() + 2
            while coordinator.get(submission.operation_id).revision == submission.operation.revision:
                if time.monotonic() >= deadline:
                    raise AssertionError("monitor did not race the terminal write")
                time.sleep(0.001)
            release.set()
            terminal = _wait_terminal(coordinator, submission.operation_id, timeout=2)
            assert terminal.state == "succeeded"
    finally:
        coordinator.shutdown()


def test_shutdown_requests_cancel_then_bounded_joins(database: Database) -> None:
    entered = threading.Event()

    def execute(context: object) -> OperationOutcome:
        entered.set()
        assert context.cancellation.wait(5)
        return OperationOutcome.cancelled()

    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    submission = coordinator.submit(_execution(execute, suffix=5))
    assert entered.wait(5)

    summary = coordinator.shutdown(timeout_seconds=3)

    assert summary.requested == summary.joined == 1
    assert summary.still_running == 0
    terminal = coordinator.get(submission.operation_id)
    assert terminal.state == "cancelled"
    assert terminal.cancel_requested_at is not None
    assert coordinator._monitor is not None
    assert coordinator._monitor.is_alive() is False


def test_shutdown_stops_monitor_when_terminal_persistence_keeps_failing(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_terminal_persistence(
        _repository: OperationRepository,
        *_args: object,
        **_kwargs: object,
    ) -> object:
        raise RuntimeError("persistent terminal write failure")

    monkeypatch.setattr(OperationRepository, "finish_succeeded", fail_terminal_persistence)
    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.01)
    submission = coordinator.submit(_execution(lambda _context: OperationOutcome.success({"statuses": []}), suffix=43))
    deadline = time.monotonic() + 5
    while submission.operation_id not in coordinator._pending_terminals:
        if time.monotonic() >= deadline:
            raise AssertionError("terminal intent was not deferred")
        time.sleep(0.01)

    summary = coordinator.shutdown(timeout_seconds=1)

    assert summary.requested == summary.joined == 1
    assert summary.still_running == 0
    assert coordinator._monitor is not None
    assert coordinator._monitor.is_alive() is False
    assert coordinator.get(submission.operation_id).state == "running"


def test_thread_start_failure_converges_without_calling_execution(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original_start = threading.Thread.start

    def fail_worker_start(thread: threading.Thread) -> None:
        if thread.name.startswith("media-sync-operation-") and "monitor" not in thread.name:
            raise RuntimeError("raw thread sentinel")
        original_start(thread)

    def execute(_context: object) -> OperationOutcome:
        nonlocal calls
        calls += 1
        return OperationOutcome.success({"statuses": []})

    monkeypatch.setattr(threading.Thread, "start", fail_worker_start)
    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    submission = coordinator.submit(_execution(execute, suffix=6))

    terminal = coordinator.get(submission.operation_id)
    assert terminal.state == "failed_retryable"
    assert terminal.error_code == "operation_thread_start_failed"
    assert calls == 0
    coordinator.shutdown()


def test_subject_hook_failure_rolls_back_domain_write(database: Database) -> None:
    attempted_job_id: list[str] = []

    def execute(context: object) -> OperationOutcome:
        with database.session() as session:
            job = JobRepository(session).enqueue(
                job_type="asset_download",
                natural_key="hook-rollback",
                payload={},
                available_at=datetime.now(UTC),
            )
            attempted_job_id.append(job.id)
            context.subject_hook(session, DurableSubjectRef("job", job.id))
        return OperationOutcome.success({"statuses": []})

    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)

    def fail_link(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("raw hook sentinel")

    coordinator._link_subject = fail_link  # type: ignore[method-assign]
    submission = coordinator.submit(_execution(execute, suffix=7))
    terminal = _wait_terminal(coordinator, submission.operation_id)

    assert terminal.state == "failed_retryable"
    assert terminal.error_code == "operation_execution_failed"
    assert len(attempted_job_id) == 1
    with database.session() as session:
        assert session.get(Job, attempted_job_id[0]) is None
        assert session.scalar(select(func.count()).select_from(Job)) == 0
    coordinator.shutdown()


def test_restart_reconciliation_uses_exact_login_truth_and_interrupts_batches(database: Database) -> None:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter="mediacrawler",
            display_name="reconcile-login",
            login_method="qr",
            auth_status="unknown",
        )
        logins = LoginSessionRepository(session)
        started_login = logins.start_mediacrawler_qr(
            account.id,
            expires_at=NOW + timedelta(minutes=1),
            at=NOW,
        )
        waiting = logins.mark_waiting_user(started_login.id, at=NOW)
        finished_login = logins.succeed_mediacrawler_qr(waiting.id, at=NOW)

        repository = OperationRepository(session)
        started = repository.create_or_replay(
            kind="account-login",
            request_fingerprint="8" * 64,
            target_type="account",
            target_id=account.id,
            phase="waiting_user",
            at=NOW,
        )
        lease = repository.claim(
            started.operation_id,
            expected_revision=started.revision,
            lease_owner="expired-login-owner",
            lease_seconds=1,
            at=NOW,
        )
        repository.link_subject(
            started.operation_id,
            OperationSubjectInput("login_session", finished_login.id, "execution"),
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            at=NOW,
        )

        batch = repository.create_or_replay(
            kind="pipeline-run",
            request_fingerprint="9" * 64,
            phase="running",
            at=NOW,
        )
        repository.claim(
            batch.operation_id,
            expected_revision=batch.revision,
            lease_owner="expired-batch-owner",
            lease_seconds=1,
            at=NOW,
        )

    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    summary = coordinator.reconcile_expired(at=NOW + timedelta(seconds=2))

    assert summary.scanned == 2
    assert summary.succeeded == 1
    assert summary.interrupted == 1
    login_operation = coordinator.get(started.operation_id)
    assert login_operation.state == "succeeded"
    assert login_operation.result_summary["login_session_id"] == finished_login.id
    assert coordinator.get(batch.operation_id).state == "interrupted"
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(OperationEvent)) == 7
    coordinator.shutdown()


def test_restart_reconciliation_preserves_unexpired_foreign_lease(database: Database) -> None:
    with database.session() as session:
        repository = OperationRepository(session)
        started = repository.create_or_replay(
            kind="scheduler-run",
            request_fingerprint="a" * 64,
            at=NOW,
        )
        repository.claim(
            started.operation_id,
            expected_revision=started.revision,
            lease_owner="foreign-owner",
            lease_seconds=60,
            at=NOW,
        )

    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    summary = coordinator.reconcile_expired(at=NOW + timedelta(seconds=30))

    assert summary.scanned == 0
    assert coordinator.get(started.operation_id).state == "running"
    coordinator.shutdown()


def test_reconciliation_never_invokes_process_callable(database: Database) -> None:
    called = False
    with database.session() as session:
        repository = OperationRepository(session)
        started = repository.create_or_replay(
            kind="scheduler-run",
            request_fingerprint="b" * 64,
            at=NOW,
        )
        repository.claim(
            started.operation_id,
            expected_revision=started.revision,
            lease_owner="dead-process",
            lease_seconds=1,
            at=NOW,
        )

    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    coordinator.reconcile_expired(at=NOW + timedelta(seconds=2))

    assert called is False
    assert coordinator.get(started.operation_id).state == "interrupted"
    coordinator.shutdown()
