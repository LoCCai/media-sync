"""Integration coverage for durable operations, fencing, and event cursors."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from media_sync.application.operation_payloads import operation_result_summary
from media_sync.infrastructure.db import (
    Database,
    Operation,
    OperationConflictError,
    OperationEvent,
    OperationEventCursorError,
    OperationEventStreamState,
    OperationLease,
    OperationLeaseLostError,
    OperationPayloadError,
    OperationRepository,
    OperationStateConflictError,
    OperationSubject,
    OperationSubjectInput,
)
from media_sync.infrastructure.db.database import SQLITE_IMMEDIATE_OPTION

NOW = datetime(2026, 9, 4, 1, tzinfo=UTC)
FINGERPRINT = "a" * 64
OTHER_FINGERPRINT = "b" * 64
IDEMPOTENCY_HASH = "c" * 64


def _uuid(value: int) -> str:
    return str(UUID(int=value))


AUTHOR_ID = _uuid(500)


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


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'operations.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _create_claimed(
    database: Database,
    *,
    suffix: int = 1,
    kind: str = "pipeline-run",
    lease_seconds: int = 30,
    at: datetime = NOW,
) -> tuple[str, OperationLease]:
    with database.session() as session:
        repository = OperationRepository(session)
        started = repository.create_or_replay(
            kind=kind,
            request_fingerprint=f"{suffix:064x}",
            exclusive_key=f"{kind}:{_uuid(suffix)}",
            at=at,
        )
        lease = repository.claim(
            started.operation_id,
            expected_revision=started.revision,
            lease_owner=f"worker-{suffix}",
            lease_seconds=lease_seconds,
            at=at,
        )
    return started.operation_id, lease


def test_locked_authoritative_read_reserves_sqlite_writer_and_postgresql_row_lock(
    database: Database,
) -> None:
    operation_id, _lease = _create_claimed(database, suffix=90, kind="media-server-scan")

    with database.session() as session:
        with patch.object(session, "scalar", wraps=session.scalar) as scalar:
            snapshot = OperationRepository(session).require_for_update(operation_id)

        statement = scalar.call_args.args[0]
        postgresql_sql = str(statement.compile(dialect=postgresql.dialect()))
        assert postgresql_sql.rstrip().endswith("FOR UPDATE")
        assert session.connection().get_execution_options()[SQLITE_IMMEDIATE_OPTION] is True
        assert snapshot.id == operation_id


def test_create_replay_fingerprint_conflict_and_active_exclusion(database: Database) -> None:
    target_id = _uuid(10)
    with database.session() as session:
        repository = OperationRepository(session)
        first = repository.create_or_replay(
            kind="account-login",
            request_fingerprint=FINGERPRINT,
            idempotency_key_hash=IDEMPOTENCY_HASH,
            exclusive_key=f"account-login:{target_id}",
            target_type="account",
            target_id=target_id,
            at=NOW,
        )
        replay = repository.create_or_replay(
            kind="account-login",
            request_fingerprint=FINGERPRINT,
            idempotency_key_hash=IDEMPOTENCY_HASH,
            exclusive_key=f"account-login:{target_id}",
            target_type="account",
            target_id=target_id,
            at=NOW,
        )
        assert replay.operation_id == first.operation_id
        assert replay.replayed is True

        with pytest.raises(OperationConflictError) as reused:
            repository.create_or_replay(
                kind="account-login",
                request_fingerprint=OTHER_FINGERPRINT,
                idempotency_key_hash=IDEMPOTENCY_HASH,
                exclusive_key=f"account-login:{target_id}",
                target_type="account",
                target_id=target_id,
                at=NOW,
            )
        assert reused.value.code == "idempotency_key_reused"
        assert reused.value.operation_id == first.operation_id

        with pytest.raises(OperationConflictError) as active:
            repository.create_or_replay(
                kind="account-login",
                request_fingerprint=OTHER_FINGERPRINT,
                exclusive_key=f"account-login:{target_id}",
                target_type="account",
                target_id=target_id,
                at=NOW,
            )
        assert active.value.code == "operation_already_running"
        assert active.value.operation_id == first.operation_id

        other_kind = repository.create_or_replay(
            kind="asset-download",
            request_fingerprint=FINGERPRINT,
            idempotency_key_hash=IDEMPOTENCY_HASH,
            at=NOW,
        )
        assert other_kind.operation_id != first.operation_id
        requested_event = repository.events_for_operation(first.operation_id)[0]
        assert requested_event.safe_context == {
            "kind": "account-login",
            "target_type": "account",
            "target_id": target_id,
        }


def test_terminal_operation_releases_exclusive_scope_but_idempotency_still_replays(database: Database) -> None:
    exclusive_key = f"emby-export:{_uuid(20)}"
    with database.session() as session:
        repository = OperationRepository(session)
        started = repository.create_or_replay(
            kind="emby-export",
            request_fingerprint=FINGERPRINT,
            idempotency_key_hash=IDEMPOTENCY_HASH,
            exclusive_key=exclusive_key,
            at=NOW,
        )
        lease = repository.claim(
            started.operation_id,
            expected_revision=started.revision,
            lease_owner="worker-export",
            lease_seconds=30,
            at=NOW,
        )
        terminal = repository.finish_succeeded(
            started.operation_id,
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            result_summary={"status": "published"},
            at=NOW,
        )
        assert terminal.state == "succeeded"

        replay = repository.create_or_replay(
            kind="emby-export",
            request_fingerprint=FINGERPRINT,
            idempotency_key_hash=IDEMPOTENCY_HASH,
            exclusive_key=exclusive_key,
            at=NOW,
        )
        replacement = repository.create_or_replay(
            kind="emby-export",
            request_fingerprint=OTHER_FINGERPRINT,
            exclusive_key=exclusive_key,
            at=NOW,
        )
        assert replay.operation_id == started.operation_id and replay.replayed
        assert replacement.operation_id != started.operation_id


def test_media_server_probe_and_scan_share_one_active_profile_exclusion(database: Database) -> None:
    exclusive_key = f"media-server:{FINGERPRINT}"
    with database.session() as session:
        repository = OperationRepository(session)
        probe = repository.create_or_replay(
            kind="media-server-probe",
            request_fingerprint=FINGERPRINT,
            exclusive_key=exclusive_key,
            at=NOW,
        )

        with pytest.raises(OperationConflictError) as conflict:
            repository.create_or_replay(
                kind="media-server-scan",
                request_fingerprint=OTHER_FINGERPRINT,
                exclusive_key=exclusive_key,
                at=NOW,
            )

        assert conflict.value.code == "operation_already_running"
        assert conflict.value.operation_id == probe.operation_id


def test_list_filters_exact_exclusive_scope_and_preserves_other_filters(database: Database) -> None:
    current_scope = f"media-server:{FINGERPRINT}"
    other_scope = f"media-server:{OTHER_FINGERPRINT}"
    with database.session() as session:
        repository = OperationRepository(session)
        current_probe = repository.create_or_replay(
            kind="media-server-probe",
            request_fingerprint=FINGERPRINT,
            exclusive_key=current_scope,
            at=NOW,
        )
        lease = repository.claim(
            current_probe.operation_id,
            expected_revision=current_probe.revision,
            lease_owner="current-profile-probe",
            lease_seconds=30,
            at=NOW,
        )
        repository.finish_succeeded(
            current_probe.operation_id,
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            result_summary=operation_result_summary(
                "media-server-probe",
                {
                    "provider": "emby",
                    "server_version": "4.9.0",
                    "library_id_digest": "d" * 64,
                    "library_present": True,
                },
            ),
            at=NOW + timedelta(microseconds=1),
        )
        other_probe = repository.create_or_replay(
            kind="media-server-probe",
            request_fingerprint=OTHER_FINGERPRINT,
            exclusive_key=other_scope,
            at=NOW + timedelta(minutes=1),
        )
        current_scan = repository.create_or_replay(
            kind="media-server-scan",
            request_fingerprint=IDEMPOTENCY_HASH,
            exclusive_key=current_scope,
            at=NOW + timedelta(minutes=2),
        )

        assert [item.id for item in repository.list(exclusive_key=current_scope)] == [
            current_scan.operation_id,
            current_probe.operation_id,
        ]
        assert [
            item.id
            for item in repository.list(
                kind="media-server-probe",
                exclusive_key=current_scope,
            )
        ] == [current_probe.operation_id]
        assert [
            item.id
            for item in repository.list(
                exclusive_key=current_scope,
                before=(NOW + timedelta(minutes=2), current_scan.operation_id),
            )
        ] == [current_probe.operation_id]
        assert other_probe.operation_id not in {item.id for item in repository.list(exclusive_key=current_scope)}
        with pytest.raises(ValueError, match="exclusive_key is invalid"):
            repository.list(exclusive_key="")


def test_sqlite_concurrent_idempotency_replays_one_identity(database: Database) -> None:
    ready = Barrier(2)

    def create() -> tuple[str, bool]:
        worker_database = Database(database.url)
        try:
            ready.wait()
            with worker_database.session() as session:
                result = OperationRepository(session).create_or_replay(
                    kind="scheduler-run",
                    request_fingerprint=FINGERPRINT,
                    idempotency_key_hash=IDEMPOTENCY_HASH,
                    exclusive_key="scheduler-run:global",
                    at=NOW,
                )
            return result.operation_id, result.replayed
        finally:
            worker_database.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: create(), range(2)))

    assert len({operation_id for operation_id, _replayed in results}) == 1
    assert sorted(replayed for _operation_id, replayed in results) == [False, True]
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Operation)) == 1
        assert session.scalar(select(func.count()).select_from(OperationEvent)) == 1


def test_sqlite_concurrent_exclusive_scope_rejects_second_request(database: Database) -> None:
    ready = Barrier(2)

    def create(index: int) -> tuple[str, str]:
        worker_database = Database(database.url)
        try:
            ready.wait()
            try:
                with worker_database.session() as session:
                    result = OperationRepository(session).create_or_replay(
                        kind="pipeline-run",
                        request_fingerprint=f"{index + 1:064x}",
                        idempotency_key_hash=f"{index + 10:064x}",
                        exclusive_key="pipeline-run:global",
                        at=NOW,
                    )
                return "created", result.operation_id
            except OperationConflictError as error:
                return error.code, error.operation_id or ""
        finally:
            worker_database.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, range(2)))

    assert sorted(result[0] for result in results) == ["created", "operation_already_running"]
    assert len({operation_id for _status, operation_id in results}) == 1


def test_claim_heartbeat_token_fencing_and_terminal_immutability(database: Database) -> None:
    operation_id, lease = _create_claimed(database)
    assert lease.lease_token not in repr(lease)

    with database.session() as session:
        repository = OperationRepository(session)
        with pytest.raises(OperationLeaseLostError) as wrong_owner:
            repository.heartbeat(
                operation_id,
                expected_revision=lease.revision,
                lease_owner="other-worker",
                lease_token=lease.lease_token,
                lease_seconds=60,
                at=NOW + timedelta(seconds=1),
            )
        assert wrong_owner.value.code == "operation_lease_lost"

        renewed = repository.heartbeat(
            operation_id,
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            lease_seconds=60,
            at=NOW + timedelta(seconds=1),
        )
        assert renewed.lease_token == lease.lease_token
        assert renewed.revision == lease.revision + 1
        assert renewed.cancel_requested_at is None

        progressed = repository.progress(
            operation_id,
            expected_revision=lease.revision,
            lease_owner=renewed.lease_owner,
            lease_token=renewed.lease_token,
            phase="downloading",
            current=1,
            total=2,
            unit="items",
            at=NOW + timedelta(seconds=2),
        )
        with pytest.raises(OperationLeaseLostError):
            repository.progress(
                operation_id,
                expected_revision=progressed.revision + 1,
                lease_owner=lease.lease_owner,
                lease_token=lease.lease_token,
                phase="future",
                current=2,
                total=2,
                unit="items",
                at=NOW + timedelta(seconds=2),
            )
        terminal = repository.finish_succeeded(
            operation_id,
            expected_revision=progressed.revision,
            lease_owner=renewed.lease_owner,
            lease_token=renewed.lease_token,
            at=NOW + timedelta(seconds=3),
        )
        assert terminal.state == "succeeded"
        assert terminal.allowed_actions == ()
        events = repository.events_for_operation(operation_id)
        assert events[-2].safe_context == {
            "phase": "downloading",
            "progress_current": 1,
            "progress_total": 2,
            "progress_unit": "items",
        }
        assert events[-1].safe_context == {}

        with pytest.raises(OperationLeaseLostError):
            repository.finish_cancelled(
                operation_id,
                expected_revision=terminal.revision,
                lease_owner=renewed.lease_owner,
                lease_token=renewed.lease_token,
                at=NOW + timedelta(seconds=4),
            )


def test_cross_session_cancel_is_observed_by_stale_revision_heartbeat(database: Database) -> None:
    operation_id, lease = _create_claimed(database, suffix=2)
    cancel_at = NOW + timedelta(seconds=1)
    with Database(database.url).session() as session:
        cancelled = OperationRepository(session).request_cancel(
            operation_id,
            expected_revision=lease.revision,
            at=cancel_at,
        )
        assert cancelled.state == "running"
        assert cancelled.cancel_requested_at == cancel_at

    with database.session() as session:
        repository = OperationRepository(session)
        renewed = repository.heartbeat(
            operation_id,
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            lease_seconds=60,
            at=NOW + timedelta(seconds=2),
        )
        assert renewed.revision == lease.revision + 2
        assert renewed.cancel_requested_at == cancel_at
        terminal = repository.finish_cancelled(
            operation_id,
            expected_revision=renewed.revision,
            lease_owner=renewed.lease_owner,
            lease_token=renewed.lease_token,
            result_summary={"status": "cancelled_at_boundary"},
            at=NOW + timedelta(seconds=3),
        )
        assert terminal.state == "cancelled"


def test_running_checkpoint_preserves_accepted_fact_and_rejects_cancelled_observation(
    database: Database,
) -> None:
    with database.session() as session:
        repository = OperationRepository(session)
        started = repository.create_or_replay(
            kind="media-server-scan",
            request_fingerprint="9" * 64,
            target_type="author",
            target_id=AUTHOR_ID,
            phase="dispatching",
            at=NOW,
        )
        lease = repository.claim(
            started.operation_id,
            expected_revision=started.revision,
            lease_owner="observation-owner",
            lease_seconds=60,
            at=NOW,
        )

    with Database(database.url).session() as session:
        cancelled = OperationRepository(session).request_cancel(
            started.operation_id,
            expected_revision=lease.revision,
            at=NOW + timedelta(seconds=1),
        )
        assert cancelled.cancel_requested_at is not None

    with database.session() as session:
        repository = OperationRepository(session)
        accepted = repository.checkpoint(
            started.operation_id,
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            phase="accepted",
            result_summary=_observation_summary(),
            at=NOW + timedelta(seconds=2),
        )
        assert accepted.state == "running"
        assert accepted.phase == "accepted"
        assert accepted.cancel_requested_at is not None
        assert accepted.result_summary == _observation_summary()

        with pytest.raises(OperationStateConflictError) as raised:
            repository.checkpoint(
                started.operation_id,
                expected_revision=accepted.revision,
                lease_owner=lease.lease_owner,
                lease_token=lease.lease_token,
                phase="observed",
                result_summary=_observation_summary(observed=True),
                at=NOW + timedelta(seconds=3),
            )
        assert raised.value.code == "operation_cancel_precedes_checkpoint"
        current = repository.require(started.operation_id)
        assert current.phase == "accepted"
        assert current.result_summary == _observation_summary()
        assert [event.event_code for event in repository.events_for_operation(started.operation_id)][-2:] == [
            "operation_cancel_requested",
            "operation_phase_changed",
        ]


@pytest.mark.parametrize(
    ("phase", "observed"),
    [("observed", False), ("accepted", True), ("polling", False), ("polling", True)],
)
def test_author_observation_checkpoint_rejects_phase_evidence_mismatch(
    database: Database,
    phase: str,
    observed: bool,
) -> None:
    with database.session() as session:
        repository = OperationRepository(session)
        started = repository.create_or_replay(
            kind="media-server-scan",
            request_fingerprint="8" * 64,
            target_type="author",
            target_id=AUTHOR_ID,
            phase="dispatching",
            at=NOW,
        )
        lease = repository.claim(
            started.operation_id,
            expected_revision=started.revision,
            lease_owner="mismatched-checkpoint-owner",
            lease_seconds=60,
            at=NOW,
        )

        with pytest.raises(OperationPayloadError) as raised:
            repository.checkpoint(
                started.operation_id,
                expected_revision=lease.revision,
                lease_owner=lease.lease_owner,
                lease_token=lease.lease_token,
                phase=phase,
                result_summary=_observation_summary(observed=observed),
                at=NOW + timedelta(seconds=1),
            )

        assert raised.value.code == "operation_checkpoint_invalid"
        current = repository.require(started.operation_id)
        assert current.phase == "dispatching"
        assert current.result_summary == {}


@pytest.mark.parametrize(
    ("outcome", "expected_state"),
    [
        ("succeeded", "succeeded"),
        ("failed", "failed_retryable"),
        ("cancelled", "cancelled"),
    ],
)
def test_cancel_revision_does_not_reject_truthful_owner_finish(
    database: Database,
    outcome: str,
    expected_state: str,
) -> None:
    operation_id, lease = _create_claimed(database, suffix={"succeeded": 3, "failed": 4, "cancelled": 5}[outcome])
    with Database(database.url).session() as session:
        OperationRepository(session).request_cancel(
            operation_id,
            expected_revision=lease.revision,
            at=NOW + timedelta(seconds=1),
        )

    with database.session() as session:
        repository = OperationRepository(session)
        common: dict[str, object] = {
            "expected_revision": lease.revision,
            "lease_owner": lease.lease_owner,
            "lease_token": lease.lease_token,
            "at": NOW + timedelta(seconds=2),
        }
        if outcome == "succeeded":
            terminal = repository.finish_succeeded(operation_id, **common)  # type: ignore[arg-type]
        elif outcome == "failed":
            terminal = repository.finish_failed(
                operation_id,
                retryable=True,
                error_code="upstream_unavailable",
                **common,  # type: ignore[arg-type]
            )
        else:
            terminal = repository.finish_cancelled(operation_id, **common)  # type: ignore[arg-type]

        assert terminal.state == expected_state
        assert terminal.cancel_requested_at == NOW + timedelta(seconds=1)
        assert terminal.finished_at == NOW + timedelta(seconds=2)
        event = repository.events_for_operation(operation_id)[-1]
        expected_context = {
            "succeeded": {},
            "failed": {"error_code": "upstream_unavailable", "retryable": True},
            "cancelled": {"phase": None},
        }[outcome]
        assert event.safe_context == expected_context


def test_queued_cancel_is_idempotent_and_terminal(database: Database) -> None:
    with database.session() as session:
        repository = OperationRepository(session)
        started = repository.create_or_replay(
            kind="asset-download",
            request_fingerprint=FINGERPRINT,
            at=NOW,
        )
        first = repository.request_cancel(
            started.operation_id,
            expected_revision=started.revision,
            at=NOW + timedelta(seconds=1),
        )
        repeated = repository.request_cancel(
            started.operation_id,
            expected_revision=started.revision,
            at=NOW + timedelta(seconds=2),
        )
        assert first.state == repeated.state == "cancelled"
        assert first.revision == repeated.revision
        assert [event.event_code for event in repository.events_for_operation(started.operation_id)] == [
            "operation_requested",
            "operation_cancelled",
        ]
        assert repository.events_for_operation(started.operation_id)[-1].safe_context == {"phase": None}
        with pytest.raises(OperationStateConflictError):
            repository.claim(
                started.operation_id,
                expected_revision=repeated.revision,
                lease_owner="late-worker",
                lease_seconds=30,
                at=NOW + timedelta(seconds=3),
            )


def test_subject_bounds_reverse_lookup_and_fenced_link(database: Database) -> None:
    target_id = _uuid(100)
    related_id = _uuid(101)
    with database.session() as session:
        repository = OperationRepository(session)
        started = repository.create_or_replay(
            kind="account-login",
            request_fingerprint=FINGERPRINT,
            target_type="account",
            target_id=target_id,
            at=NOW,
        )
        lease = repository.claim(
            started.operation_id,
            expected_revision=started.revision,
            lease_owner="login-worker",
            lease_seconds=30,
            at=NOW,
        )
        linked = repository.link_subject(
            started.operation_id,
            OperationSubjectInput("login_session", related_id, "execution"),
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            context={
                "subject_type": "login_session",
                "subject_id": related_id,
                "role": "execution",
            },
            at=NOW + timedelta(seconds=1),
        )
        subjects = repository.list_subjects(started.operation_id)
        assert [(item.subject_type, item.subject_id, item.role) for item in subjects] == [
            ("account", target_id, "target"),
            ("login_session", related_id, "execution"),
        ]
        assert all(item.created_at.tzinfo is UTC for item in subjects)
        assert [item.id for item in repository.list(target_type="login_session", target_id=related_id)] == [
            started.operation_id
        ]
        assert repository.events_for_operation(started.operation_id)[-1].event_code == "operation_entity_linked"

        repeated = repository.link_subject(
            started.operation_id,
            OperationSubjectInput("login_session", related_id, "execution"),
            expected_revision=linked.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            at=NOW + timedelta(seconds=2),
        )
        assert repeated.revision == linked.revision
        absorbed = repository.link_subject(
            started.operation_id,
            OperationSubjectInput("job", _uuid(102), "execution"),
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            at=NOW + timedelta(seconds=2),
        )
        assert absorbed.revision == linked.revision + 1
        with pytest.raises(OperationLeaseLostError):
            repository.link_subject(
                started.operation_id,
                OperationSubjectInput("job", _uuid(103), "execution"),
                expected_revision=absorbed.revision,
                lease_owner=lease.lease_owner,
                lease_token=_uuid(999),
                at=NOW + timedelta(seconds=2),
            )

    subjects = tuple(OperationSubjectInput("job", _uuid(1_000 + index), "related") for index in range(1_024))
    with database.session() as session:
        repository = OperationRepository(session)
        bounded = repository.create_or_replay(
            kind="scheduler-run",
            request_fingerprint=OTHER_FINGERPRINT,
            subjects=subjects,
            at=NOW,
        )
        bounded_lease = repository.claim(
            bounded.operation_id,
            expected_revision=bounded.revision,
            lease_owner="scheduler-worker",
            lease_seconds=30,
            at=NOW,
        )
        with pytest.raises(OperationPayloadError) as too_many:
            repository.link_subject(
                bounded.operation_id,
                OperationSubjectInput("job", _uuid(3_000), "related"),
                expected_revision=bounded_lease.revision,
                lease_owner=bounded_lease.lease_owner,
                lease_token=bounded_lease.lease_token,
                at=NOW,
            )
        assert too_many.value.code == "operation_subject_limit"

        with pytest.raises(OperationPayloadError):
            repository.create_or_replay(
                kind="scheduler-run",
                request_fingerprint="d" * 64,
                subjects=(*subjects, OperationSubjectInput("job", _uuid(3_001))),
                at=NOW,
            )


def test_owned_revision_lower_bound_absorbs_committed_subject_hook(database: Database) -> None:
    heartbeat_id, heartbeat_lease = _create_claimed(database, suffix=110)
    finish_id, finish_lease = _create_claimed(database, suffix=111)

    for operation_id, lease, subject_id in (
        (heartbeat_id, heartbeat_lease, _uuid(4_000)),
        (finish_id, finish_lease, _uuid(4_001)),
    ):
        hook_database = Database(database.url)
        try:
            with hook_database.session() as session:
                linked = OperationRepository(session).link_subject(
                    operation_id,
                    OperationSubjectInput("job", subject_id, "execution"),
                    expected_revision=lease.revision,
                    lease_owner=lease.lease_owner,
                    lease_token=lease.lease_token,
                    at=NOW + timedelta(seconds=1),
                )
                assert linked.revision == lease.revision + 1
        finally:
            hook_database.dispose()

    with database.session() as session:
        repository = OperationRepository(session)
        renewed = repository.heartbeat(
            heartbeat_id,
            expected_revision=heartbeat_lease.revision,
            lease_owner=heartbeat_lease.lease_owner,
            lease_token=heartbeat_lease.lease_token,
            lease_seconds=60,
            at=NOW + timedelta(seconds=2),
        )
        assert renewed.revision == heartbeat_lease.revision + 2

        terminal = repository.finish_succeeded(
            finish_id,
            expected_revision=finish_lease.revision,
            lease_owner=finish_lease.lease_owner,
            lease_token=finish_lease.lease_token,
            at=NOW + timedelta(seconds=2),
        )
        assert terminal.state == "succeeded"
        assert terminal.revision == finish_lease.revision + 2


def test_rolled_back_subject_hook_does_not_advance_durable_revision(database: Database) -> None:
    operation_id, lease = _create_claimed(database, suffix=112)
    hook_database = Database(database.url)
    try:
        with pytest.raises(RuntimeError, match="rollback hook"), hook_database.session() as session:
            linked = OperationRepository(session).link_subject(
                operation_id,
                OperationSubjectInput("job", _uuid(4_002), "execution"),
                expected_revision=lease.revision,
                lease_owner=lease.lease_owner,
                lease_token=lease.lease_token,
                at=NOW + timedelta(seconds=1),
            )
            assert linked.revision == lease.revision + 1
            raise RuntimeError("rollback hook")
    finally:
        hook_database.dispose()

    with database.session() as session:
        repository = OperationRepository(session)
        unchanged = repository.require(operation_id)
        assert unchanged.revision == lease.revision
        assert len(repository.list_subjects(operation_id)) == 0
        terminal = repository.finish_succeeded(
            operation_id,
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            at=NOW + timedelta(seconds=2),
        )
        assert terminal.state == "succeeded"
        assert [event.event_code for event in repository.events_for_operation(operation_id)] == [
            "operation_requested",
            "operation_started",
            "operation_succeeded",
        ]


def test_sqlite_concurrent_subject_links_are_revision_fenced(database: Database) -> None:
    operation_id, lease = _create_claimed(database, suffix=113)
    ready = Barrier(2)

    def link(index: int) -> str:
        worker_database = Database(database.url)
        try:
            ready.wait()
            try:
                with worker_database.session() as session:
                    OperationRepository(session).link_subject(
                        operation_id,
                        OperationSubjectInput("job", _uuid(4_100 + index), "execution"),
                        expected_revision=lease.revision,
                        lease_owner=lease.lease_owner,
                        lease_token=lease.lease_token,
                        at=NOW + timedelta(seconds=1),
                    )
                return "linked"
            except OperationLeaseLostError as error:
                return error.code
        finally:
            worker_database.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(link, range(2)))

    # The first link advances the revision. The second call uses the same
    # valid lease generation and may absorb it; both links remain bounded and
    # are serialized by SQLite's BEGIN IMMEDIATE writer reservation.
    assert results == ["linked", "linked"]
    with database.session() as session:
        repository = OperationRepository(session)
        assert len(repository.list_subjects(operation_id)) == 2
        assert [event.event_code for event in repository.events_for_operation(operation_id)].count(
            "operation_entity_linked"
        ) == 2


@pytest.mark.parametrize(
    "unsafe_context",
    [
        {"password": "sentinel"},
        {"value": "https://example.invalid/media?token=sentinel"},
        {"value": "C:\\Users\\sentinel\\private.txt"},
        {"value": "/srv/private/media.bin"},
        {"value": "relative/private.txt"},
        {"value": "data:image/png;base64,c2VudGluZWw="},
        {"value": b"qr-image-bytes"},
        {"value": "Authorization: Bearer sentinel"},
        {"session": "opaque-browser-state"},
        {"session_token": "opaque-session-token"},
        {"payload": {"status": "succeeded"}},
    ],
)
def test_safe_payload_boundary_rejects_secrets_urls_paths_and_bytes(
    database: Database,
    unsafe_context: Mapping[str, object],
) -> None:
    operation_id, lease = _create_claimed(database, suffix=30)
    with database.session() as session:
        repository = OperationRepository(session)
        with pytest.raises(OperationPayloadError):
            repository.progress(
                operation_id,
                expected_revision=lease.revision,
                lease_owner=lease.lease_owner,
                lease_token=lease.lease_token,
                phase="downloading",
                current=0,
                total=1,
                unit="items",
                context=unsafe_context,
                at=NOW + timedelta(seconds=1),
            )
        unchanged = repository.require(operation_id)
        assert unchanged.revision == lease.revision
        assert unchanged.event_sequence == 2


@pytest.mark.parametrize(
    ("suffix", "kind", "payload"),
    [
        (
            60,
            "account-login",
            {
                "account_id": _uuid(5_000),
                "login_session_id": _uuid(5_001),
                "runner_status": "authenticated",
                "login_session_status": "succeeded",
                "auth_status": "authenticated",
                "expires_at": None,
                "completed_at": NOW,
            },
        ),
        (
            61,
            "asset-download",
            {
                "asset_id": _uuid(5_002),
                "job_id": _uuid(5_003),
                "ok": True,
                "status": "verified",
                "disposition": "downloaded",
                "generation": 1,
                "size_bytes": 1_024,
            },
        ),
        (62, "scheduler-run", {"statuses": ["succeeded", "failed_retryable"]}),
        (63, "pipeline-run", {"statuses": ["succeeded", "cancelled"]}),
        (
            64,
            "emby-export",
            {
                "author_id": _uuid(5_004),
                "job_id": _uuid(5_005),
                "already_exported": False,
                "managed_file_count": 3,
            },
        ),
        (
            65,
            "media-server-probe",
            {
                "provider": "emby",
                "server_version": "4.8.11.0",
                "library_id_digest": "d" * 64,
                "library_present": True,
            },
        ),
        (
            66,
            "media-server-scan",
            {
                "provider": "jellyfin",
                "server_version": "10.10.7",
                "library_id_digest": "e" * 64,
                "scan_state": "accepted",
            },
        ),
    ],
)
def test_seven_kind_projected_results_compose_with_repository_safety_boundary(
    database: Database,
    suffix: int,
    kind: str,
    payload: Mapping[str, object],
) -> None:
    summary = operation_result_summary(kind, payload)
    operation_id, lease = _create_claimed(database, suffix=suffix, kind=kind)
    with database.session() as session:
        terminal = OperationRepository(session).finish_succeeded(
            operation_id,
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            result_summary=summary,
            at=NOW + timedelta(seconds=1),
        )
        assert terminal.state == "succeeded"
        assert dict(terminal.result_summary) == summary


def test_event_codes_are_closed_before_database_mutation(database: Database) -> None:
    operation_id, lease = _create_claimed(database, suffix=31)
    with database.session() as session:
        repository = OperationRepository(session)
        with pytest.raises(ValueError, match="unsupported owned progress event code"):
            repository.progress(
                operation_id,
                expected_revision=lease.revision,
                lease_owner=lease.lease_owner,
                lease_token=lease.lease_token,
                phase="downloading",
                event_code="operator_supplied_event",
                at=NOW + timedelta(seconds=1),
            )
        assert repository.require(operation_id).revision == lease.revision

    with pytest.raises(IntegrityError), database.session() as session:
        operation = session.get(Operation, operation_id)
        assert operation is not None
        session.add(
            OperationEvent(
                stream_sequence=3,
                operation_id=operation_id,
                operation_sequence=3,
                event_code="operator_supplied_event",
            )
        )


def test_owned_event_contexts_are_exact_and_derived_when_omitted(database: Database) -> None:
    operation_id, lease = _create_claimed(database, suffix=32)
    with database.session() as session:
        repository = OperationRepository(session)
        with pytest.raises(OperationPayloadError) as mismatch:
            repository.progress(
                operation_id,
                expected_revision=lease.revision,
                lease_owner=lease.lease_owner,
                lease_token=lease.lease_token,
                phase="fetching",
                current=1,
                total=2,
                unit="items",
                context={
                    "phase": "fetching",
                    "progress_current": 1,
                    "progress_total": 2,
                    "progress_unit": "items",
                    "extra": "not_allowed",
                },
                at=NOW + timedelta(seconds=1),
            )
        assert mismatch.value.code == "operation_event_context_mismatch"

        initial_progress = repository.progress(
            operation_id,
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            phase="fetching",
            current=1,
            total=2,
            unit="items",
            at=NOW + timedelta(seconds=1),
        )
        phase_changed = repository.progress(
            operation_id,
            expected_revision=initial_progress.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            phase="processing",
            event_code="operation_phase_changed",
            at=NOW + timedelta(seconds=2),
        )
        assert (phase_changed.progress_current, phase_changed.progress_total, phase_changed.progress_unit) == (
            1,
            2,
            "items",
        )
        cancel_requested = repository.request_cancel(
            operation_id,
            expected_revision=phase_changed.revision,
            at=NOW + timedelta(seconds=3),
        )
        observed = repository.progress(
            operation_id,
            expected_revision=phase_changed.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            phase="safe_boundary",
            event_code="operation_cancel_observed",
            at=NOW + timedelta(seconds=4),
        )
        assert observed.revision == cancel_requested.revision + 1
        assert (observed.progress_current, observed.progress_total, observed.progress_unit) == (1, 2, "items")
        events = repository.events_for_operation(operation_id)
        assert [(event.event_code, event.safe_context) for event in events[-3:]] == [
            ("operation_phase_changed", {"phase": "processing"}),
            ("operation_cancel_requested", {}),
            ("operation_cancel_observed", {"phase": "safe_boundary"}),
        ]


def test_local_and_global_event_sequences_are_dense_across_writers(database: Database) -> None:
    ready = Barrier(2)

    def create(index: int) -> str:
        worker_database = Database(database.url)
        try:
            ready.wait()
            with worker_database.session() as session:
                result = OperationRepository(session).create_or_replay(
                    kind="asset-download",
                    request_fingerprint=f"{100 + index:064x}",
                    exclusive_key=f"asset-download:{_uuid(100 + index)}",
                    at=NOW + timedelta(microseconds=index),
                )
            return result.operation_id
        finally:
            worker_database.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        operation_ids = list(executor.map(create, range(2)))

    with database.session() as session:
        repository = OperationRepository(session)
        events = repository.events_after(0, limit=10)
        assert [event.stream_sequence for event in events] == [1, 2]
        assert {event.operation_id for event in events} == set(operation_ids)
        assert all(event.operation_sequence == 1 for event in events)
        assert repository.stream_bounds() == (0, 2)


def test_event_cursor_validation_expiry_and_operation_filter(database: Database) -> None:
    first_id, first_lease = _create_claimed(database, suffix=40)
    second_id, _second_lease = _create_claimed(database, suffix=41)
    with database.session() as session:
        repository = OperationRepository(session)
        progressed = repository.progress(
            first_id,
            expected_revision=first_lease.revision,
            lease_owner=first_lease.lease_owner,
            lease_token=first_lease.lease_token,
            phase="fetching",
            current=1,
            total=1,
            unit="items",
            at=NOW + timedelta(seconds=1),
        )
        assert progressed.event_sequence == 3
        _pruned, last = repository.stream_bounds()
        filtered = repository.events_after(0, operation_id=second_id, limit=10)
        assert filtered and {event.operation_id for event in filtered} == {second_id}

        for invalid in (-1, True, last + 1, 2**63):
            with pytest.raises(OperationEventCursorError) as error:
                repository.events_after(invalid)  # type: ignore[arg-type]
            assert error.value.code == "operation_event_cursor_invalid"

        with pytest.raises(OperationEventCursorError) as oversized:
            repository.events_for_operation(first_id, after_operation_sequence=2**63)
        assert oversized.value.code == "operation_event_cursor_invalid"

        stream_state = session.get(OperationEventStreamState, 1)
        assert stream_state is not None
        stream_state.pruned_through_sequence = 2
        session.flush()
        with pytest.raises(OperationEventCursorError) as expired:
            repository.events_after(1)
        assert expired.value.code == "operation_event_cursor_expired"
        assert repository.events_after(2)


def test_ten_thousand_event_keyset_pagination(database: Database) -> None:
    total = 10_000
    with database.session() as session:
        repository = OperationRepository(session)
        started = repository.create_or_replay(
            kind="pipeline-run",
            request_fingerprint=FINGERPRINT,
            at=NOW,
        )
        session.execute(
            insert(OperationEvent),
            [
                {
                    "stream_sequence": sequence,
                    "operation_id": started.operation_id,
                    "operation_sequence": sequence,
                    "event_code": "operation_progressed",
                }
                for sequence in range(2, total + 1)
            ],
        )
        session.execute(
            update(Operation).where(Operation.id == started.operation_id).values(event_sequence=total, revision=total)
        )
        session.execute(
            update(OperationEventStreamState).where(OperationEventStreamState.id == 1).values(last_sequence=total)
        )

    with database.session() as session:
        repository = OperationRepository(session)
        cursor = 0
        observed: list[int] = []
        while True:
            page = repository.events_after(cursor, limit=1_000)
            if not page:
                break
            assert page[0].stream_sequence == cursor + 1
            observed.extend(event.stream_sequence for event in page)
            cursor = page[-1].stream_sequence
        assert observed == list(range(1, total + 1))
        assert (
            repository.events_for_operation(
                started.operation_id,
                after_operation_sequence=total - 10,
                limit=10,
            )[-1].operation_sequence
            == total
        )


def test_expired_reconciliation_is_fenced_and_preserves_live_foreign_lease(database: Database) -> None:
    expired_id, _expired_lease = _create_claimed(database, suffix=50, lease_seconds=1)
    live_id, _live_lease = _create_claimed(database, suffix=51, lease_seconds=30)
    refreshed_id, refreshed_lease = _create_claimed(database, suffix=52, lease_seconds=1)
    observed_at = NOW + timedelta(seconds=2)

    with database.session() as session:
        repository = OperationRepository(session)
        candidates = repository.list_expired_candidates(at=observed_at)
        assert {candidate.operation_id for candidate in candidates} == {expired_id, refreshed_id}
        stale_candidate = next(candidate for candidate in candidates if candidate.operation_id == refreshed_id)
        assert live_id not in {candidate.operation_id for candidate in candidates}

    with Database(database.url).session() as session:
        renewed = OperationRepository(session).heartbeat(
            refreshed_id,
            expected_revision=refreshed_lease.revision,
            lease_owner=refreshed_lease.lease_owner,
            lease_token=refreshed_lease.lease_token,
            lease_seconds=30,
            at=observed_at,
        )
        assert renewed.lease_expires_at > observed_at

    with database.session() as session:
        repository = OperationRepository(session)
        refreshed = repository.require(refreshed_id)
        with pytest.raises(OperationStateConflictError):
            repository.reconcile(
                stale_candidate,
                state="interrupted",
                error_code="lease_expired",
                context={"subject_type": "job", "subject_state": "lease_expired"},
                at=observed_at,
            )
        assert repository.require(refreshed_id) == refreshed

        candidate = next(
            item for item in repository.list_expired_candidates(at=observed_at) if item.operation_id == expired_id
        )
        terminal = repository.reconcile(
            candidate,
            state="interrupted",
            error_code="lease_expired",
            context={"subject_type": "job", "subject_state": "lease_expired"},
            result_summary={"status": "interrupted"},
            at=observed_at,
        )
        assert terminal.state == "interrupted"
        assert terminal.error_code == "lease_expired"
        assert terminal.retryable is True
        assert terminal.allowed_actions == ()
        assert repository.events_for_operation(expired_id)[-1].safe_context == {
            "subject_type": "job",
            "subject_state": "lease_expired",
        }
        assert repository.require(live_id).state == "running"


def test_metadata_create_all_seeds_exactly_one_stream_state_and_cascades(database: Database) -> None:
    database.create_schema()
    database.create_schema()
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(OperationEventStreamState)) == 1
        started = OperationRepository(session).create_or_replay(
            kind="account-login",
            request_fingerprint=FINGERPRINT,
            target_type="account",
            target_id=_uuid(90),
            at=NOW,
        )
        operation = session.get(Operation, started.operation_id)
        assert operation is not None
        session.delete(operation)

    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(OperationEvent)) == 0
        assert session.scalar(select(func.count()).select_from(OperationSubject)) == 0
