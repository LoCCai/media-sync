"""Real PostgreSQL coverage for operation checkpoint/cancel/final races."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from media_sync.application.operation_payloads import operation_request_fingerprint
from media_sync.application.operations import (
    OperationCoordinator,
    OperationExecution,
    OperationExecutionContext,
    OperationOutcome,
)
from media_sync.infrastructure.db import (
    Database,
    Operation,
    OperationEvent,
    OperationEventStreamState,
    OperationLease,
    OperationLeaseLostError,
    OperationRepository,
    OperationStateConflictError,
    OperationSubject,
)

POSTGRESQL_URL_ENV = "MEDIA_SYNC_TEST_POSTGRESQL_URL"
NOW = datetime(2026, 9, 5, 1, tzinfo=UTC)
AUTHOR_ID = "55555555-5555-4555-8555-555555555555"
TERMINAL_STATES = frozenset({"succeeded", "failed_retryable", "failed_terminal", "cancelled", "interrupted"})


@dataclass(frozen=True, slots=True)
class _ClaimedOperation:
    operation_id: str
    lease: OperationLease


@dataclass(slots=True)
class _ThreadCall:
    backend_ready: threading.Event = field(default_factory=threading.Event)
    finished: threading.Event = field(default_factory=threading.Event)
    backend_pid: int | None = None
    values: list[object] = field(default_factory=list)
    errors: list[BaseException] = field(default_factory=list)
    thread: threading.Thread | None = None


@pytest.fixture(scope="module")
def postgresql_database() -> Iterator[Database]:
    raw_url = os.environ.get(POSTGRESQL_URL_ENV)
    if not raw_url:
        pytest.skip(f"{POSTGRESQL_URL_ENV} is not set; real PostgreSQL race tests were not run")

    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail(f"{POSTGRESQL_URL_ENV} must identify a PostgreSQL database")
    url = url.set(drivername="postgresql+psycopg")
    admin_database = Database(url.render_as_string(hide_password=False))
    schema = f"media_sync_races_{uuid4().hex}"
    test_database: Database | None = None
    schema_created = False
    try:
        with admin_database.engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        schema_created = True
        options = f"-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=10000"
        scoped_url = url.update_query_dict({"options": options}, append=False)
        test_database = Database(scoped_url.render_as_string(hide_password=False))
        Operation.metadata.create_all(
            test_database.engine,
            tables=[
                OperationEventStreamState.__table__,
                Operation.__table__,
                OperationSubject.__table__,
                OperationEvent.__table__,
            ],
        )
        yield test_database
    finally:
        if test_database is not None:
            test_database.dispose()
        if schema_created:
            with admin_database.engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        admin_database.dispose()


def _observation_summary(*, observed: bool = False) -> dict[str, object]:
    summary: dict[str, object] = {
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
        summary.update(
            item_fingerprint="1" * 64,
            observed_at=(NOW + timedelta(seconds=2)).isoformat(),
        )
    return summary


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


def _create_claimed(
    database: Database,
    *,
    suffix: int,
    author_scan: bool = True,
    lease_seconds: int = 120,
) -> _ClaimedOperation:
    with database.session() as session:
        repository = OperationRepository(session)
        started = repository.create_or_replay(
            kind="media-server-scan" if author_scan else "scheduler-run",
            request_fingerprint=_author_scan_fingerprint() if author_scan else f"{suffix:064x}",
            exclusive_key=f"postgresql-race:{suffix}",
            target_type="author" if author_scan else None,
            target_id=AUTHOR_ID if author_scan else None,
            phase="dispatching" if author_scan else "working",
            at=NOW,
        )
        lease = repository.claim(
            started.operation_id,
            expected_revision=started.revision,
            lease_owner=f"postgresql-worker-{suffix}",
            lease_seconds=lease_seconds,
            at=NOW,
        )
    return _ClaimedOperation(started.operation_id, lease)


def _checkpoint(
    repository: OperationRepository,
    claimed: _ClaimedOperation,
    *,
    observed: bool,
    at: datetime,
) -> object:
    return repository.checkpoint(
        claimed.operation_id,
        expected_revision=claimed.lease.revision,
        lease_owner=claimed.lease.lease_owner,
        lease_token=claimed.lease.lease_token,
        phase="observed" if observed else "accepted",
        result_summary=_observation_summary(observed=observed),
        at=at,
    )


def _independent_write(
    database_url: str,
    call: _ThreadCall,
    action: Callable[[OperationRepository], object],
) -> object:
    database = Database(database_url)
    try:
        with database.session() as session:
            backend_pid = session.scalar(text("SELECT pg_backend_pid()"))
            assert isinstance(backend_pid, int)
            call.backend_pid = backend_pid
            call.backend_ready.set()
            return action(OperationRepository(session))
    finally:
        database.dispose()


def _capture_next_backend(database: Database, call: _ThreadCall) -> None:
    def capture(connection: object, *_args: object) -> None:
        driver_connection = connection.connection.driver_connection  # type: ignore[attr-defined]
        backend_pid = driver_connection.info.backend_pid
        assert isinstance(backend_pid, int)
        call.backend_pid = backend_pid
        call.backend_ready.set()

    event.listen(database.engine, "before_cursor_execute", capture, once=True)


def _cancel_from_coordinator(
    database_url: str,
    operation_id: str,
    call: _ThreadCall,
    *,
    at: datetime,
) -> object:
    database = Database(database_url)
    coordinator = OperationCoordinator(
        database,
        lease_seconds=120,
        heartbeat_interval_seconds=60,
        clock=lambda: at,
    )
    try:
        _capture_next_backend(database, call)
        return coordinator.request_cancel(operation_id)
    finally:
        coordinator.shutdown()
        database.dispose()


def _shutdown_with_backend_capture(
    coordinator: OperationCoordinator,
    database: Database,
    call: _ThreadCall,
) -> object:
    _capture_next_backend(database, call)
    return coordinator.shutdown(timeout_seconds=5)


def _start_call(action: Callable[[_ThreadCall], object]) -> _ThreadCall:
    call = _ThreadCall()

    def run() -> None:
        try:
            call.values.append(action(call))
        except BaseException as error:  # pragma: no cover - asserted by the controlling thread
            call.errors.append(error)
        finally:
            call.finished.set()

    call.thread = threading.Thread(target=run, daemon=True)
    call.thread.start()
    assert call.backend_ready.wait(5)
    return call


def _assert_waiting_on_postgresql_lock(database_url: str, call: _ThreadCall) -> None:
    assert call.backend_pid is not None
    observer = Database(database_url)
    deadline = time.monotonic() + 5
    try:
        with observer.session() as session:
            while time.monotonic() < deadline:
                wait_event_type = session.scalar(
                    text("SELECT wait_event_type FROM pg_catalog.pg_stat_activity WHERE pid = :pid"),
                    {"pid": call.backend_pid},
                )
                if wait_event_type == "Lock":
                    assert call.finished.is_set() is False
                    return
                if call.finished.is_set():
                    raise AssertionError("competing PostgreSQL backend completed before entering a lock wait")
                time.sleep(0.01)
    finally:
        observer.dispose()
    raise AssertionError("competing PostgreSQL backend did not enter a lock wait")


def _await_call(call: _ThreadCall) -> None:
    assert call.finished.wait(5)
    assert call.thread is not None
    call.thread.join(1)
    assert call.thread.is_alive() is False


def _terminal_event_count(repository: OperationRepository, operation_id: str) -> int:
    return sum(event.to_state in TERMINAL_STATES for event in repository.events_for_operation(operation_id))


def _wait_terminal(
    coordinator: OperationCoordinator,
    operation_id: str,
    *,
    timeout: float = 5,
) -> object:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = coordinator.get(operation_id)
        if snapshot.state not in {"queued", "running"}:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("operation did not reach a terminal state")


@pytest.mark.parametrize("first", ["accepted", "cancel"])
def test_postgresql_accepted_checkpoint_and_cancel_preserve_acceptance_in_both_orders(
    postgresql_database: Database,
    first: str,
) -> None:
    claimed = _create_claimed(postgresql_database, suffix=10 if first == "accepted" else 11)

    if first == "accepted":
        with postgresql_database.session() as session:
            accepted = _checkpoint(
                OperationRepository(session),
                claimed,
                observed=False,
                at=NOW + timedelta(seconds=1),
            )
            assert accepted.result_summary == _observation_summary()
            call = _start_call(
                lambda current_call: _cancel_from_coordinator(
                    postgresql_database.url,
                    claimed.operation_id,
                    current_call,
                    at=NOW + timedelta(seconds=2),
                )
            )
            _assert_waiting_on_postgresql_lock(postgresql_database.url, call)
        _await_call(call)
        assert call.errors == []
    else:
        with postgresql_database.session() as session:
            cancelled = OperationRepository(session).request_cancel(
                claimed.operation_id,
                expected_revision=claimed.lease.revision,
                at=NOW + timedelta(seconds=1),
            )
            assert cancelled.cancel_requested_at is not None
            call = _start_call(
                lambda current_call: _independent_write(
                    postgresql_database.url,
                    current_call,
                    lambda repository: _checkpoint(
                        repository,
                        claimed,
                        observed=False,
                        at=NOW + timedelta(seconds=2),
                    ),
                )
            )
            _assert_waiting_on_postgresql_lock(postgresql_database.url, call)
        _await_call(call)
        assert call.errors == []

    with postgresql_database.session() as session:
        repository = OperationRepository(session)
        current = repository.require(claimed.operation_id)
        assert current.state == "running"
        assert current.phase == "accepted"
        assert current.cancel_requested_at is not None
        assert current.result_summary == _observation_summary()
        expected_tail = (
            ["operation_phase_changed", "operation_cancel_requested"]
            if first == "accepted"
            else ["operation_cancel_requested", "operation_phase_changed"]
        )
        assert [event.event_code for event in repository.events_for_operation(claimed.operation_id)][
            -2:
        ] == expected_tail


@pytest.mark.parametrize("first", ["observed", "cancel"])
def test_postgresql_observed_checkpoint_and_cancel_honor_locked_order(
    postgresql_database: Database,
    first: str,
) -> None:
    claimed = _create_claimed(postgresql_database, suffix=20 if first == "observed" else 21)
    with postgresql_database.session() as session:
        _checkpoint(
            OperationRepository(session),
            claimed,
            observed=False,
            at=NOW + timedelta(seconds=1),
        )

    if first == "observed":
        with postgresql_database.session() as session:
            observed = _checkpoint(
                OperationRepository(session),
                claimed,
                observed=True,
                at=NOW + timedelta(seconds=2),
            )
            assert observed.result_summary == _observation_summary(observed=True)
            call = _start_call(
                lambda current_call: _cancel_from_coordinator(
                    postgresql_database.url,
                    claimed.operation_id,
                    current_call,
                    at=NOW + timedelta(seconds=3),
                )
            )
            _assert_waiting_on_postgresql_lock(postgresql_database.url, call)
        _await_call(call)
        assert call.errors == []
        with postgresql_database.session() as session:
            repository = OperationRepository(session)
            current = repository.require(claimed.operation_id)
            terminal = repository.finish_succeeded(
                claimed.operation_id,
                expected_revision=current.revision,
                lease_owner=claimed.lease.lease_owner,
                lease_token=claimed.lease.lease_token,
                result_summary=_observation_summary(observed=True),
                at=NOW + timedelta(seconds=4),
            )
        assert terminal.state == "succeeded"
        assert terminal.cancel_requested_at is not None
        assert terminal.result_summary == _observation_summary(observed=True)
    else:
        with postgresql_database.session() as session:
            cancelled = OperationRepository(session).request_cancel(
                claimed.operation_id,
                expected_revision=claimed.lease.revision + 1,
                at=NOW + timedelta(seconds=2),
            )
            assert cancelled.cancel_requested_at is not None
            call = _start_call(
                lambda current_call: _independent_write(
                    postgresql_database.url,
                    current_call,
                    lambda repository: _checkpoint(
                        repository,
                        claimed,
                        observed=True,
                        at=NOW + timedelta(seconds=3),
                    ),
                )
            )
            _assert_waiting_on_postgresql_lock(postgresql_database.url, call)
        _await_call(call)
        assert len(call.errors) == 1
        assert isinstance(call.errors[0], OperationStateConflictError)
        assert call.errors[0].code == "operation_cancel_precedes_checkpoint"
        with postgresql_database.session() as session:
            repository = OperationRepository(session)
            current = repository.require(claimed.operation_id)
            terminal = repository.finish_failed(
                claimed.operation_id,
                expected_revision=current.revision,
                lease_owner=claimed.lease.lease_owner,
                lease_token=claimed.lease.lease_token,
                retryable=False,
                error_code="media_server_scan_completion_unknown",
                result_summary=_observation_summary(),
                at=NOW + timedelta(seconds=4),
            )
        assert terminal.state == "failed_terminal"
        assert terminal.result_summary == _observation_summary()

    with postgresql_database.session() as session:
        repository = OperationRepository(session)
        assert _terminal_event_count(repository, claimed.operation_id) == 1


@pytest.mark.parametrize("first", ["final", "cancel"])
def test_postgresql_final_and_cancel_produce_one_truthful_terminal_event(
    postgresql_database: Database,
    first: str,
) -> None:
    claimed = _create_claimed(
        postgresql_database,
        suffix=30 if first == "final" else 31,
        author_scan=False,
    )

    if first == "final":
        with postgresql_database.session() as session:
            terminal = OperationRepository(session).finish_succeeded(
                claimed.operation_id,
                expected_revision=claimed.lease.revision,
                lease_owner=claimed.lease.lease_owner,
                lease_token=claimed.lease.lease_token,
                result_summary={"status": "finished"},
                at=NOW + timedelta(seconds=1),
            )
            assert terminal.state == "succeeded"
            call = _start_call(
                lambda current_call: _cancel_from_coordinator(
                    postgresql_database.url,
                    claimed.operation_id,
                    current_call,
                    at=NOW + timedelta(seconds=2),
                )
            )
            _assert_waiting_on_postgresql_lock(postgresql_database.url, call)
        _await_call(call)
        assert call.errors == []
    else:
        with postgresql_database.session() as session:
            cancelled = OperationRepository(session).request_cancel(
                claimed.operation_id,
                expected_revision=claimed.lease.revision,
                at=NOW + timedelta(seconds=1),
            )
            assert cancelled.cancel_requested_at is not None
            call = _start_call(
                lambda current_call: _independent_write(
                    postgresql_database.url,
                    current_call,
                    lambda repository: repository.finish_succeeded(
                        claimed.operation_id,
                        expected_revision=claimed.lease.revision,
                        lease_owner=claimed.lease.lease_owner,
                        lease_token=claimed.lease.lease_token,
                        result_summary={"status": "finished"},
                        at=NOW + timedelta(seconds=2),
                    ),
                )
            )
            _assert_waiting_on_postgresql_lock(postgresql_database.url, call)
        _await_call(call)
        assert call.errors == []

    with postgresql_database.session() as session:
        repository = OperationRepository(session)
        current = repository.require(claimed.operation_id)
        assert current.state == "succeeded"
        assert current.result_summary == {"status": "finished"}
        assert (current.cancel_requested_at is not None) is (first == "cancel")
        assert _terminal_event_count(repository, claimed.operation_id) == 1


@pytest.mark.parametrize("fallback", ["exception", "cancelled_outcome"])
def test_postgresql_coordinator_fallback_preserves_accepted_checkpoint(
    postgresql_database: Database,
    fallback: str,
) -> None:
    accepted = _observation_summary()

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        checkpoint = context.checkpoint(phase="accepted", result_summary=accepted)
        assert checkpoint.result_summary == accepted
        if fallback == "exception":
            raise RuntimeError("post-acceptance failure")
        return OperationOutcome.cancelled()

    coordinator = OperationCoordinator(
        postgresql_database,
        lease_seconds=120,
        heartbeat_interval_seconds=60,
        clock=lambda: NOW + timedelta(seconds=40 if fallback == "exception" else 41),
    )
    try:
        submission = coordinator.submit(
            OperationExecution(
                kind="media-server-scan",
                request_fingerprint=_author_scan_fingerprint(),
                exclusive_key=f"postgresql-race:coordinator-{fallback}",
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
        events = coordinator.events_for_operation(submission.operation_id)
        assert [event.event_code for event in events][-2:] == ["operation_phase_changed", "operation_failed"]
        assert sum(event.to_state in TERMINAL_STATES for event in events) == 1
    finally:
        coordinator.shutdown()


def test_postgresql_shutdown_waits_for_accepted_checkpoint_then_persists_cancel(
    postgresql_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint_locked = threading.Event()
    release_checkpoint = threading.Event()
    accepted = _observation_summary()
    original_checkpoint = OperationRepository.checkpoint

    def checkpoint_then_hold_lock(
        repository: OperationRepository,
        *args: object,
        **kwargs: object,
    ) -> object:
        snapshot = original_checkpoint(repository, *args, **kwargs)  # type: ignore[arg-type]
        if kwargs.get("phase") == "accepted":
            checkpoint_locked.set()
            assert release_checkpoint.wait(5)
        return snapshot

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        context.checkpoint(phase="accepted", result_summary=accepted)
        assert context.cancellation.wait(5)
        return OperationOutcome.cancelled()

    monkeypatch.setattr(OperationRepository, "checkpoint", checkpoint_then_hold_lock)
    coordinator = OperationCoordinator(
        postgresql_database,
        lease_seconds=120,
        heartbeat_interval_seconds=60,
        clock=lambda: NOW + timedelta(seconds=50),
    )
    call: _ThreadCall | None = None
    try:
        submission = coordinator.submit(
            OperationExecution(
                kind="media-server-scan",
                request_fingerprint=_author_scan_fingerprint(),
                exclusive_key="postgresql-race:shutdown",
                target_type="author",
                target_id=AUTHOR_ID,
                phase="dispatching",
                execute=execute,
            )
        )
        assert checkpoint_locked.wait(5)
        call = _start_call(
            lambda current_call: _shutdown_with_backend_capture(
                coordinator,
                postgresql_database,
                current_call,
            )
        )
        _assert_waiting_on_postgresql_lock(postgresql_database.url, call)
        release_checkpoint.set()
        _await_call(call)
        assert call.errors == []

        with postgresql_database.session() as session:
            repository = OperationRepository(session)
            current = repository.require(submission.operation_id)
            events = repository.events_for_operation(submission.operation_id)
        assert current.state == "failed_terminal"
        assert current.error_code == "media_server_scan_completion_unknown"
        assert current.cancel_requested_at is not None
        assert current.result_summary == accepted
        assert [event.event_code for event in events].count("operation_cancel_requested") == 1
        assert [event.event_code for event in events].count("operation_cancel_observed") == 1
        assert sum(event.to_state in TERMINAL_STATES for event in events) == 1
    finally:
        release_checkpoint.set()
        if call is not None:
            _await_call(call)
        coordinator.shutdown(timeout_seconds=1)


def test_postgresql_lost_lease_cannot_append_a_second_terminal_event(
    postgresql_database: Database,
) -> None:
    claimed = _create_claimed(
        postgresql_database,
        suffix=50,
        author_scan=False,
        lease_seconds=1,
    )
    with postgresql_database.session() as session:
        candidates = OperationRepository(session).list_expired_candidates(at=NOW + timedelta(seconds=2))
    candidate = next(item for item in candidates if item.operation_id == claimed.operation_id)

    with postgresql_database.session() as session:
        reconciled = OperationRepository(session).reconcile(
            candidate,
            state="interrupted",
            error_code="operation_interrupted",
            context={"subject_type": "job", "subject_state": "incomplete"},
            at=NOW + timedelta(seconds=2),
        )
        assert reconciled.state == "interrupted"
        call = _start_call(
            lambda current_call: _independent_write(
                postgresql_database.url,
                current_call,
                lambda repository: repository.finish_succeeded(
                    claimed.operation_id,
                    expected_revision=claimed.lease.revision,
                    lease_owner=claimed.lease.lease_owner,
                    lease_token=claimed.lease.lease_token,
                    result_summary={"status": "stale"},
                    at=NOW + timedelta(seconds=3),
                ),
            )
        )
        _assert_waiting_on_postgresql_lock(postgresql_database.url, call)
    _await_call(call)

    assert len(call.errors) == 1
    assert isinstance(call.errors[0], OperationLeaseLostError)
    with postgresql_database.session() as session:
        repository = OperationRepository(session)
        assert repository.require(claimed.operation_id).state == "interrupted"
        assert _terminal_event_count(repository, claimed.operation_id) == 1


def test_postgresql_duplicate_final_race_has_one_winner_and_one_terminal_event(
    postgresql_database: Database,
) -> None:
    claimed = _create_claimed(postgresql_database, suffix=60, author_scan=False)
    with postgresql_database.session() as session:
        winner = OperationRepository(session).finish_succeeded(
            claimed.operation_id,
            expected_revision=claimed.lease.revision,
            lease_owner=claimed.lease.lease_owner,
            lease_token=claimed.lease.lease_token,
            result_summary={"winner": 0},
            at=NOW + timedelta(seconds=1),
        )
        assert winner.state == "succeeded"
        call = _start_call(
            lambda current_call: _independent_write(
                postgresql_database.url,
                current_call,
                lambda repository: repository.finish_succeeded(
                    claimed.operation_id,
                    expected_revision=claimed.lease.revision,
                    lease_owner=claimed.lease.lease_owner,
                    lease_token=claimed.lease.lease_token,
                    result_summary={"winner": 1},
                    at=NOW + timedelta(seconds=2),
                ),
            )
        )
        _assert_waiting_on_postgresql_lock(postgresql_database.url, call)
    _await_call(call)

    assert len(call.errors) == 1
    assert isinstance(call.errors[0], OperationLeaseLostError)
    with postgresql_database.session() as session:
        repository = OperationRepository(session)
        assert repository.require(claimed.operation_id).state == "succeeded"
        assert _terminal_event_count(repository, claimed.operation_id) == 1
