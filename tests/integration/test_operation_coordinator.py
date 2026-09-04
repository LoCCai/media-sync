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

from media_sync.application.operation_payloads import operation_request_fingerprint
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
    OperationStateConflictError,
    OperationSubjectInput,
)

NOW = datetime(2026, 9, 4, 8, tzinfo=UTC)
AUTHOR_ID = "55555555-5555-4555-8555-555555555555"
PUBLICATION_JOB_ID = "66666666-6666-4666-8666-666666666666"
OTHER_AUTHOR_ID = "77777777-7777-4777-8777-777777777777"


def _observation_payload(*, observed: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 2,
        "mode": "post_refresh_item_observation",
        "provider": "emby",
        "server_version": "4.9.5",
        "profile_fingerprint": "c" * 64,
        "library_id_digest": "d" * 64,
        "scan_state": "accepted",
        "publication_fingerprint": "e" * 64,
        "selector_fingerprint": "f" * 64,
        "baseline_state": "not_found",
        "observation_state": "observed" if observed else "pending",
        "match_count": 1 if observed else 0,
        "verification_count": 2 if observed else 0,
        "accepted_at": NOW.isoformat(),
    }
    if observed:
        payload.update(
            item_fingerprint="1" * 64,
            observed_at=(NOW + timedelta(seconds=2)).isoformat(),
        )
    return payload


def _author_scan_fingerprint() -> str:
    return operation_request_fingerprint(
        "media-server-scan",
        target_id=AUTHOR_ID,
        parameters={
            "profile_fingerprint": "c" * 64,
            "mode": "post_refresh_item_observation",
            "publication_fingerprint": "e" * 64,
        },
    )


def _succeeded_publication_job(database: Database, *, natural_key: str) -> str:
    with database.session() as session:
        jobs = JobRepository(session)
        publication = jobs.enqueue(
            job_type="export.emby",
            natural_key=natural_key,
            payload={"author_id": AUTHOR_ID},
            available_at=NOW,
        )
        claimed = jobs.claim(publication.id, worker_id="publisher", lease_seconds=60, now=NOW)
        assert claimed is not None and claimed.lease_token is not None
        running = jobs.start(
            publication.id,
            worker_id="publisher",
            lease_token=claimed.lease_token,
            now=NOW,
        )
        assert running.lease_token is not None
        jobs.complete(
            publication.id,
            worker_id="publisher",
            lease_token=running.lease_token,
            now=NOW,
        )
        return publication.id


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


def test_media_server_scan_cancel_before_success_cas_becomes_acceptance_unknown(
    database: Database,
) -> None:
    finalization_entered = threading.Event()
    finalization_release = threading.Event()

    def execute(_context: OperationExecutionContext) -> OperationOutcome:
        return OperationOutcome.success(
            {
                "provider": "emby",
                "server_version": "4.9.0",
                "library_id_digest": "d" * 64,
                "scan_state": "accepted",
            }
        )

    owner = OperationCoordinator(
        Database(database.url),
        lease_seconds=120,
        heartbeat_interval_seconds=60,
    )
    canceller = OperationCoordinator(
        Database(database.url),
        lease_seconds=120,
        heartbeat_interval_seconds=60,
    )
    original_run_write = owner._run_write

    def gated_run_write(action: object) -> object:
        if getattr(action, "__name__", "") == "finish":
            finalization_entered.set()
            assert finalization_release.wait(5)
        assert callable(action)
        return original_run_write(action)

    owner._run_write = gated_run_write  # type: ignore[method-assign]
    try:
        submission = owner.submit(
            OperationExecution(
                kind="media-server-scan",
                request_fingerprint=f"{33:064x}",
                exclusive_key=f"media-server:{33:064x}",
                execute=execute,
            )
        )
        assert finalization_entered.wait(5)

        requested = canceller.request_cancel(submission.operation_id)
        assert requested.state == "running"
        assert requested.cancel_requested_at is not None

        finalization_release.set()
        terminal = _wait_terminal(owner, submission.operation_id)
        assert terminal.state == "failed_terminal"
        assert terminal.error_code == "media_server_scan_acceptance_unknown"
        assert owner.get(submission.operation_id).retryable is False
        assert terminal.result_summary == {}
        assert terminal.cancel_requested_at == requested.cancel_requested_at

        events = owner.events_for_operation(submission.operation_id)
        assert [event.event_code for event in events[-2:]] == [
            "operation_cancel_requested",
            "operation_failed",
        ]
        assert events[-1].safe_context == {
            "error_code": "media_server_scan_acceptance_unknown",
            "retryable": False,
        }
    finally:
        finalization_release.set()
        owner.shutdown()
        canceller.shutdown()
        owner._database.dispose()
        canceller._database.dispose()


def test_media_server_scan_final_lock_before_cancel_preserves_success(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final_lock_entered = threading.Event()
    final_lock_release = threading.Event()
    cancel_write_entered = threading.Event()
    cancel_finished = threading.Event()
    cancel_results: list[tuple[str, datetime | None]] = []
    cancel_errors: list[BaseException] = []

    def execute(_context: OperationExecutionContext) -> OperationOutcome:
        return OperationOutcome.success(
            {
                "provider": "emby",
                "server_version": "4.9.0",
                "library_id_digest": "e" * 64,
                "scan_state": "accepted",
            }
        )

    original_require_for_update = OperationRepository.require_for_update

    def gated_require_for_update(
        repository: OperationRepository,
        operation_id: str,
    ) -> object:
        snapshot = original_require_for_update(repository, operation_id)
        if snapshot.kind == "media-server-scan":
            final_lock_entered.set()
            assert final_lock_release.wait(5)
        return snapshot

    monkeypatch.setattr(OperationRepository, "require_for_update", gated_require_for_update)
    owner = OperationCoordinator(
        Database(database.url),
        lease_seconds=120,
        heartbeat_interval_seconds=60,
    )
    canceller = OperationCoordinator(
        Database(database.url),
        lease_seconds=120,
        heartbeat_interval_seconds=60,
    )
    original_cancel_run_write = canceller._run_write

    def tracked_cancel_run_write(action: object) -> object:
        cancel_write_entered.set()
        assert callable(action)
        return original_cancel_run_write(action)

    canceller._run_write = tracked_cancel_run_write  # type: ignore[method-assign]
    cancellation_thread: threading.Thread | None = None
    try:
        submission = owner.submit(
            OperationExecution(
                kind="media-server-scan",
                request_fingerprint=f"{34:064x}",
                exclusive_key=f"media-server:{34:064x}",
                execute=execute,
            )
        )
        assert final_lock_entered.wait(5)

        def request_cancel() -> None:
            try:
                snapshot = canceller.request_cancel(submission.operation_id)
                cancel_results.append((snapshot.state, snapshot.cancel_requested_at))
            except BaseException as error:  # pragma: no cover - asserted below
                cancel_errors.append(error)
            finally:
                cancel_finished.set()

        cancellation_thread = threading.Thread(target=request_cancel, daemon=True)
        cancellation_thread.start()
        assert cancel_write_entered.wait(5)
        assert cancel_finished.is_set() is False

        final_lock_release.set()
        terminal = _wait_terminal(owner, submission.operation_id)
        assert cancel_finished.wait(5)
        cancellation_thread.join(5)

        assert cancel_errors == []
        assert cancel_results == [("succeeded", None)]
        assert terminal.state == "succeeded"
        assert terminal.cancel_requested_at is None
        assert terminal.error_code is None
        assert terminal.result_summary == {
            "provider": "emby",
            "server_version": "4.9.0",
            "library_id_digest": "e" * 64,
            "scan_state": "accepted",
        }
        assert [event.event_code for event in owner.events_for_operation(submission.operation_id)] == [
            "operation_requested",
            "operation_started",
            "operation_succeeded",
        ]
    finally:
        final_lock_release.set()
        if cancellation_thread is not None:
            cancellation_thread.join(5)
        owner.shutdown()
        canceller.shutdown()
        owner._database.dispose()
        canceller._database.dispose()


def test_author_scan_persists_target_and_related_publication_before_callable(database: Database) -> None:
    observed_subjects: list[tuple[str, str, str]] = []
    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        observed_subjects.extend(
            (subject.subject_type, subject.subject_id, subject.role)
            for subject in coordinator.list_subjects(context.operation_id)
        )
        return OperationOutcome.failed(
            "media_server_scan_observation_precondition_failed",
            retryable=False,
        )

    submission = coordinator.submit(
        OperationExecution(
            kind="media-server-scan",
            request_fingerprint="2" * 64,
            exclusive_key="media-server:author-observation",
            target_type="author",
            target_id=AUTHOR_ID,
            subjects=(OperationSubjectInput("job", PUBLICATION_JOB_ID, "related"),),
            phase="preparing",
            execute=execute,
        )
    )
    terminal = _wait_terminal(coordinator, submission.operation_id)

    assert terminal.target_type == "author"
    assert terminal.target_id == AUTHOR_ID
    assert terminal.state == "failed_terminal"
    assert terminal.error_code == "media_server_scan_observation_precondition_failed"
    assert observed_subjects == [
        ("author", AUTHOR_ID, "target"),
        ("job", PUBLICATION_JOB_ID, "related"),
    ]
    coordinator.shutdown()


def test_author_scan_exception_after_accepted_checkpoint_is_completion_unknown(database: Database) -> None:
    accepted = _observation_payload()

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        checkpoint = context.checkpoint(phase="accepted", result_summary=accepted)
        assert checkpoint.result_summary == accepted
        raise RuntimeError("private post-acceptance sentinel")

    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    submission = coordinator.submit(
        OperationExecution(
            kind="media-server-scan",
            request_fingerprint=_author_scan_fingerprint(),
            exclusive_key="media-server:accepted-exception",
            target_type="author",
            target_id=AUTHOR_ID,
            phase="dispatching",
            execute=execute,
        )
    )
    terminal = _wait_terminal(coordinator, submission.operation_id)

    assert terminal.state == "failed_terminal"
    assert terminal.error_code == "media_server_scan_completion_unknown"
    assert terminal.result_summary == accepted
    assert [event.event_code for event in coordinator.events_for_operation(submission.operation_id)][-2:] == [
        "operation_phase_changed",
        "operation_failed",
    ]
    coordinator.shutdown()


def test_author_scan_observed_checkpoint_wins_later_cancel(database: Database) -> None:
    observed_written = threading.Event()
    release = threading.Event()
    observed = _observation_payload(observed=True)
    publication_job_id = _succeeded_publication_job(database, natural_key="online-observed-publication")

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        context.checkpoint(phase="accepted", result_summary=_observation_payload())
        context.checkpoint(
            phase="observed",
            result_summary=observed,
        )
        observed_written.set()
        assert release.wait(5)
        return OperationOutcome.success(observed)

    owner = OperationCoordinator(Database(database.url), lease_seconds=120, heartbeat_interval_seconds=60)
    canceller = OperationCoordinator(Database(database.url), lease_seconds=120, heartbeat_interval_seconds=60)
    try:
        submission = owner.submit(
            OperationExecution(
                kind="media-server-scan",
                request_fingerprint=_author_scan_fingerprint(),
                exclusive_key="media-server:observed-wins",
                target_type="author",
                target_id=AUTHOR_ID,
                subjects=(OperationSubjectInput("job", publication_job_id, "related"),),
                phase="dispatching",
                execute=execute,
            )
        )
        assert observed_written.wait(5)
        cancelled = canceller.request_cancel(submission.operation_id)
        assert cancelled.cancel_requested_at is not None
        release.set()
        terminal = _wait_terminal(owner, submission.operation_id)

        assert terminal.state == "succeeded"
        assert terminal.error_code is None
        assert terminal.cancel_requested_at is not None
        assert terminal.result_summary == observed
    finally:
        release.set()
        owner.shutdown()
        canceller.shutdown()
        owner._database.dispose()
        canceller._database.dispose()


def test_author_scan_observed_checkpoint_requires_bound_request_identity(database: Database) -> None:
    observed = _observation_payload(observed=True)
    publication_job_id = _succeeded_publication_job(database, natural_key="online-unbound-publication")

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        context.checkpoint(phase="accepted", result_summary=_observation_payload())
        context.checkpoint(phase="observed", result_summary=observed)
        return OperationOutcome.success(observed)

    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    submission = coordinator.submit(
        OperationExecution(
            kind="media-server-scan",
            request_fingerprint="9" * 64,
            exclusive_key="media-server:unbound-observation",
            target_type="author",
            target_id=AUTHOR_ID,
            subjects=(OperationSubjectInput("job", publication_job_id, "related"),),
            phase="dispatching",
            execute=execute,
        )
    )
    terminal = _wait_terminal(coordinator, submission.operation_id)

    assert terminal.state == "failed_terminal"
    assert terminal.error_code == "media_server_scan_completion_unknown"
    assert terminal.result_summary == {}
    coordinator.shutdown()


def test_author_scan_cancel_before_observed_checkpoint_retains_acceptance(database: Database) -> None:
    accepted_written = threading.Event()
    checkpoint_rejected = threading.Event()

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        context.checkpoint(phase="accepted", result_summary=_observation_payload())
        accepted_written.set()
        assert context.cancellation.wait(5)
        try:
            context.checkpoint(
                phase="observed",
                result_summary=_observation_payload(observed=True),
            )
        except OperationStateConflictError as error:
            assert error.code == "operation_cancel_precedes_checkpoint"
            checkpoint_rejected.set()
        return OperationOutcome.cancelled()

    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    submission = coordinator.submit(
        OperationExecution(
            kind="media-server-scan",
            request_fingerprint=_author_scan_fingerprint(),
            exclusive_key="media-server:cancel-first",
            target_type="author",
            target_id=AUTHOR_ID,
            phase="dispatching",
            execute=execute,
        )
    )
    assert accepted_written.wait(5)
    coordinator.request_cancel(submission.operation_id)
    terminal = _wait_terminal(coordinator, submission.operation_id)

    assert checkpoint_rejected.is_set()
    assert terminal.state == "failed_terminal"
    assert terminal.error_code == "media_server_scan_completion_unknown"
    assert terminal.result_summary == _observation_payload()
    coordinator.shutdown()


def test_phase_waits_for_existing_cancel_observer_before_terminal(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute_entered = threading.Event()
    allow_phase = threading.Event()
    second_observer_entered = threading.Event()
    phase_returned = threading.Event()
    observer_write_entered = threading.Event()
    observer_write_release = threading.Event()
    existing_observer_wait_entered = threading.Event()

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        execute_entered.set()
        assert allow_phase.wait(5)
        snapshot = context.phase("safe_boundary")
        phase_returned.set()
        assert snapshot.cancel_requested_at is not None
        assert context.cancel_requested is True
        return OperationOutcome.cancelled()

    owner = OperationCoordinator(
        Database(database.url),
        lease_seconds=120,
        heartbeat_interval_seconds=60,
    )
    canceller = OperationCoordinator(
        Database(database.url),
        lease_seconds=120,
        heartbeat_interval_seconds=60,
    )
    observer: threading.Thread | None = None
    try:
        submission = owner.submit(_execution(execute, suffix=31))
        assert execute_entered.wait(5)
        requested = canceller.request_cancel(submission.operation_id)
        assert requested.cancel_requested_at is not None

        handle = owner._local_handle(submission.operation_id)
        assert handle is not None
        original_run_write = owner._run_write
        original_observe_cancel = owner._observe_cancel
        original_cancel_wait = handle.cancellation.wait
        observe_calls = 0
        observe_calls_lock = threading.Lock()

        def tracked_cancel_wait(timeout: float | None = None) -> bool:
            existing_observer_wait_entered.set()
            return original_cancel_wait(timeout)

        def gated_run_write(action: object) -> object:
            if getattr(action, "__name__", "") == "observe":
                observer_write_entered.set()
                assert observer_write_release.wait(5)
            assert callable(action)
            return original_run_write(action)

        def tracked_observe_cancel(operation_id: str, current_handle: object) -> None:
            nonlocal observe_calls
            with observe_calls_lock:
                observe_calls += 1
                if observe_calls == 2:
                    second_observer_entered.set()
            original_observe_cancel(operation_id, current_handle)  # type: ignore[arg-type]

        owner._run_write = gated_run_write  # type: ignore[method-assign]
        owner._observe_cancel = tracked_observe_cancel  # type: ignore[method-assign]
        monkeypatch.setattr(handle.cancellation, "wait", tracked_cancel_wait)
        observer = threading.Thread(
            target=owner._observe_cancel,
            args=(submission.operation_id, handle),
            daemon=True,
        )
        observer.start()
        assert observer_write_entered.wait(5)

        allow_phase.set()
        assert second_observer_entered.wait(5)
        assert existing_observer_wait_entered.wait(5)
        assert phase_returned.is_set() is False
        assert owner.get(submission.operation_id).state == "running"

        observer_write_release.set()
        observer.join(5)
        assert observer.is_alive() is False
        terminal = _wait_terminal(owner, submission.operation_id)
        assert terminal.state == "cancelled"

        cancel_codes = [
            event.event_code
            for event in owner.events_for_operation(submission.operation_id)
            if event.event_code.startswith("operation_cancel")
        ]
        assert cancel_codes == [
            "operation_cancel_requested",
            "operation_cancel_observed",
            "operation_cancelled",
        ]
    finally:
        allow_phase.set()
        observer_write_release.set()
        if observer is not None:
            observer.join(5)
        owner.shutdown()
        canceller.shutdown()
        owner._database.dispose()
        canceller._database.dispose()


def test_shutdown_timeout_bounds_existing_cancel_observer_wait(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute_entered = threading.Event()
    execute_release = threading.Event()
    observer_write_entered = threading.Event()
    observer_write_release = threading.Event()

    def execute(_context: OperationExecutionContext) -> OperationOutcome:
        execute_entered.set()
        assert execute_release.wait(5)
        return OperationOutcome.success({"statuses": []})

    owner = OperationCoordinator(
        Database(database.url),
        lease_seconds=120,
        heartbeat_interval_seconds=60,
    )
    canceller = OperationCoordinator(
        Database(database.url),
        lease_seconds=120,
        heartbeat_interval_seconds=60,
    )
    observer: threading.Thread | None = None
    try:
        submission = owner.submit(_execution(execute, suffix=32))
        assert execute_entered.wait(5)
        requested = canceller.request_cancel(submission.operation_id)
        assert requested.cancel_requested_at is not None

        handle = owner._local_handle(submission.operation_id)
        assert handle is not None
        original_run_write = owner._run_write
        observed_wait_timeouts: list[float | None] = []

        def gated_run_write(action: object) -> object:
            if getattr(action, "__name__", "") == "observe":
                observer_write_entered.set()
                assert observer_write_release.wait(5)
            assert callable(action)
            return original_run_write(action)

        def nonblocking_wait(timeout: float | None = None) -> bool:
            observed_wait_timeouts.append(timeout)
            return False

        owner._run_write = gated_run_write  # type: ignore[method-assign]
        monkeypatch.setattr(handle.cancellation, "wait", nonblocking_wait)
        observer = threading.Thread(
            target=owner._observe_cancel,
            args=(submission.operation_id, handle),
            daemon=True,
        )
        observer.start()
        assert observer_write_entered.wait(5)

        summary = owner.shutdown(timeout_seconds=0)

        assert summary.requested == 1
        assert summary.joined == 0
        assert summary.still_running == 1
        assert observed_wait_timeouts == [0.0]
    finally:
        observer_write_release.set()
        execute_release.set()
        if observer is not None:
            observer.join(5)
        owner.shutdown()
        canceller.shutdown()
        owner._database.dispose()
        canceller._database.dispose()


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
    interrupted_batch = coordinator.get(batch.operation_id)
    assert interrupted_batch.state == "interrupted"
    assert interrupted_batch.retryable is True
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


def test_restart_reconciliation_interrupts_media_server_work_without_remote_subject(
    database: Database,
) -> None:
    operation_ids: dict[str, str] = {}
    with database.session() as session:
        repository = OperationRepository(session)
        for index, kind in enumerate(("media-server-probe", "media-server-scan"), start=12):
            started = repository.create_or_replay(
                kind=kind,
                request_fingerprint=f"{index:064x}",
                phase="remote_request",
                at=NOW,
            )
            repository.claim(
                started.operation_id,
                expected_revision=started.revision,
                lease_owner=f"expired-media-server-{index}",
                lease_seconds=1,
                at=NOW,
            )
            operation_ids[kind] = started.operation_id

    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    summary = coordinator.reconcile_expired(at=NOW + timedelta(seconds=2))

    assert summary.scanned == 2
    assert summary.interrupted == 2
    for kind, operation_id in operation_ids.items():
        operation = coordinator.get(operation_id)
        assert operation.state == "interrupted"
        assert operation.retryable is (kind == "media-server-probe")
        assert operation.error_code == "operation_interrupted"
        assert operation.result_summary == {}
        assert coordinator.list_subjects(operation_id) == []
        event = coordinator.events_for_operation(operation_id)[-1]
        assert event.event_code == "operation_reconciled"
        assert event.safe_context == {"subject_type": "job", "subject_state": "missing"}
    coordinator.shutdown()


def test_restart_reconciliation_classifies_author_scan_phases_and_checkpoints(
    database: Database,
) -> None:
    operation_ids: dict[str, str] = {}
    with database.session() as session:
        jobs = JobRepository(session)
        publication_jobs = {
            "valid": jobs.enqueue(
                job_type="export.emby",
                natural_key="phase-b-recovery-publication",
                payload={"author_id": AUTHOR_ID},
                available_at=NOW,
            ),
            "wrong_job_type": jobs.enqueue(
                job_type="asset_download",
                natural_key="phase-b-recovery-wrong-job-type",
                payload={"author_id": AUTHOR_ID},
                available_at=NOW,
            ),
            "wrong_job_author": jobs.enqueue(
                job_type="export.emby",
                natural_key="phase-b-recovery-wrong-job-author",
                payload={"author_id": OTHER_AUTHOR_ID},
                available_at=NOW,
            ),
        }
        for job in publication_jobs.values():
            claimed_job = jobs.claim(job.id, worker_id="publisher", lease_seconds=60, now=NOW)
            assert claimed_job is not None and claimed_job.lease_token is not None
            running_job = jobs.start(
                job.id,
                worker_id="publisher",
                lease_token=claimed_job.lease_token,
                now=NOW,
            )
            assert running_job.lease_token is not None
            jobs.complete(
                job.id,
                worker_id="publisher",
                lease_token=running_job.lease_token,
                now=NOW,
            )

        repository = OperationRepository(session)
        for phase in ("preparing", "baselining", "dispatching", "accepted", "polling", "observed"):
            subjects = (
                (OperationSubjectInput("job", publication_jobs["valid"].id, "related"),) if phase == "observed" else ()
            )
            initial_phase = "accepted" if phase == "polling" else phase
            started = repository.create_or_replay(
                kind="media-server-scan",
                request_fingerprint=_author_scan_fingerprint(),
                target_type="author",
                target_id=AUTHOR_ID,
                phase=initial_phase,
                subjects=subjects,
                at=NOW,
            )
            lease = repository.claim(
                started.operation_id,
                expected_revision=started.revision,
                lease_owner=f"expired-observation-{phase}",
                lease_seconds=1,
                at=NOW,
            )
            if phase in {"accepted", "polling", "observed"}:
                checkpoint = repository.checkpoint(
                    started.operation_id,
                    expected_revision=lease.revision,
                    lease_owner=lease.lease_owner,
                    lease_token=lease.lease_token,
                    phase="observed" if phase == "observed" else "accepted",
                    result_summary=_observation_payload(observed=phase == "observed"),
                    at=NOW,
                )
                if phase == "polling":
                    repository.progress(
                        started.operation_id,
                        expected_revision=checkpoint.revision,
                        lease_owner=lease.lease_owner,
                        lease_token=lease.lease_token,
                        phase="polling",
                        event_code="operation_phase_changed",
                        at=NOW,
                    )
            operation_ids[phase] = started.operation_id

        invalid_observations = {
            "fingerprint_mismatch": ("7" * 64, publication_jobs["valid"].id),
            "wrong_job_type": (_author_scan_fingerprint(), publication_jobs["wrong_job_type"].id),
            "wrong_job_author": (_author_scan_fingerprint(), publication_jobs["wrong_job_author"].id),
        }
        for case, (request_fingerprint, publication_job_id) in invalid_observations.items():
            started = repository.create_or_replay(
                kind="media-server-scan",
                request_fingerprint=request_fingerprint,
                target_type="author",
                target_id=AUTHOR_ID,
                phase="observed",
                subjects=(OperationSubjectInput("job", publication_job_id, "related"),),
                at=NOW,
            )
            lease = repository.claim(
                started.operation_id,
                expected_revision=started.revision,
                lease_owner=f"expired-observation-{case}",
                lease_seconds=1,
                at=NOW,
            )
            repository.checkpoint(
                started.operation_id,
                expected_revision=lease.revision,
                lease_owner=lease.lease_owner,
                lease_token=lease.lease_token,
                phase="observed",
                result_summary=_observation_payload(observed=True),
                at=NOW,
            )
            operation_ids[case] = started.operation_id

    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    summary = coordinator.reconcile_expired(at=NOW + timedelta(seconds=2))

    assert summary.scanned == 9
    assert summary.interrupted == 2
    assert summary.failed_terminal == 6
    assert summary.succeeded == 1
    preparing = coordinator.get(operation_ids["preparing"])
    baselining = coordinator.get(operation_ids["baselining"])
    dispatching = coordinator.get(operation_ids["dispatching"])
    accepted = coordinator.get(operation_ids["accepted"])
    polling = coordinator.get(operation_ids["polling"])
    observed = coordinator.get(operation_ids["observed"])
    assert (preparing.state, preparing.error_code) == ("interrupted", "operation_interrupted")
    assert (baselining.state, baselining.error_code) == ("interrupted", "operation_interrupted")
    assert (dispatching.state, dispatching.error_code) == (
        "failed_terminal",
        "media_server_scan_acceptance_unknown",
    )
    assert (accepted.state, accepted.error_code, accepted.result_summary) == (
        "failed_terminal",
        "media_server_scan_completion_unknown",
        _observation_payload(),
    )
    assert (polling.state, polling.error_code, polling.result_summary) == (
        "failed_terminal",
        "media_server_scan_completion_unknown",
        _observation_payload(),
    )
    assert (observed.state, observed.error_code, observed.result_summary) == (
        "succeeded",
        None,
        _observation_payload(observed=True),
    )
    fingerprint_mismatch = coordinator.get(operation_ids["fingerprint_mismatch"])
    assert (
        fingerprint_mismatch.state,
        fingerprint_mismatch.error_code,
        fingerprint_mismatch.result_summary,
    ) == ("failed_terminal", "media_server_scan_completion_unknown", {})
    for case in ("wrong_job_type", "wrong_job_author"):
        invalid_publication = coordinator.get(operation_ids[case])
        assert (
            invalid_publication.state,
            invalid_publication.error_code,
            invalid_publication.result_summary,
        ) == (
            "failed_terminal",
            "media_server_scan_completion_unknown",
            _observation_payload(observed=True),
        )
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
