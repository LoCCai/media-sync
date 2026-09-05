"""Optional real-PostgreSQL races for the playback-evidence natural identity."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.schema import CreateIndex, CreateSchema, CreateTable, DropSchema

from media_sync.infrastructure.db import (
    Author,
    AuthorRepository,
    AuthorUpsert,
    Database,
    Job,
    JobRepository,
    PlaybackEvidence,
    PlaybackEvidenceConflictError,
    PlaybackEvidenceRepository,
    PlaybackEvidenceResult,
)

POSTGRESQL_URL_ENV = "MEDIA_SYNC_TEST_POSTGRESQL_URL"
NOW = datetime(2026, 9, 5, 10, tzinfo=UTC)


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
        pytest.skip(f"{POSTGRESQL_URL_ENV} is not set; playback-evidence PostgreSQL races were not run")

    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail(f"{POSTGRESQL_URL_ENV} must identify a PostgreSQL database")
    url = url.set(drivername="postgresql+psycopg")
    admin_database = Database(url.render_as_string(hide_password=False))
    schema = f"media_sync_playback_evidence_{uuid4().hex}"
    test_database: Database | None = None
    schema_created = False
    try:
        with admin_database.engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        schema_created = True
        options = f"-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=10000"
        scoped_url = url.update_query_dict({"options": options}, append=False)
        test_database = Database(scoped_url.render_as_string(hide_password=False))
        with test_database.engine.begin() as connection:
            # Job has unrelated application foreign keys.  Omitting those
            # constraints lets this fixture stay an honest three-table slice;
            # PlaybackEvidence's two production RESTRICT FKs remain intact.
            connection.execute(CreateTable(Author.__table__))
            connection.execute(CreateTable(Job.__table__, include_foreign_key_constraints=[]))
            connection.execute(CreateTable(PlaybackEvidence.__table__))
            for table in (Author.__table__, Job.__table__, PlaybackEvidence.__table__):
                for index in sorted(table.indexes, key=lambda candidate: candidate.name or ""):
                    connection.execute(CreateIndex(index))
        yield test_database
    finally:
        if test_database is not None:
            test_database.dispose()
        if schema_created:
            with admin_database.engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        admin_database.dispose()


def _seed_parents(database: Database, label: str) -> tuple[str, str]:
    unique = uuid4().hex
    with database.session() as session:
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform="xhs",
                remote_id=f"postgresql-evidence-author-{label}-{unique}",
                display_name=f"Author {label}",
            )
        )
        job = JobRepository(session).enqueue(
            job_type="export.emby",
            natural_key=f"postgresql-evidence-publication-{label}-{unique}",
            payload={"schema_version": 1},
            available_at=NOW,
        )
        return author.id, job.id


def _values(
    author_id: str,
    job_id: str,
    seed: int,
    **overrides: object,
) -> dict[str, object]:
    values: dict[str, object] = {
        "author_id": author_id,
        "publication_job_id": job_id,
        "profile_fingerprint": "a" * 64,
        "publication_fingerprint": "b" * 64,
        "selector_fingerprint": "c" * 64,
        "item_fingerprint": "d" * 64,
        "observation_fingerprint": f"{seed:064x}",
        "observed_at": NOW,
        "confirmed_at": NOW + timedelta(seconds=1),
    }
    values.update(overrides)
    return values


def _create(repository: PlaybackEvidenceRepository, values: dict[str, object]) -> PlaybackEvidenceResult:
    return repository.create_or_replay(
        author_id=values["author_id"],  # type: ignore[arg-type]
        publication_job_id=values["publication_job_id"],  # type: ignore[arg-type]
        profile_fingerprint=values["profile_fingerprint"],  # type: ignore[arg-type]
        publication_fingerprint=values["publication_fingerprint"],  # type: ignore[arg-type]
        selector_fingerprint=values["selector_fingerprint"],  # type: ignore[arg-type]
        item_fingerprint=values["item_fingerprint"],  # type: ignore[arg-type]
        observation_fingerprint=values["observation_fingerprint"],  # type: ignore[arg-type]
        observed_at=values["observed_at"],  # type: ignore[arg-type]
        confirmed_at=values["confirmed_at"],  # type: ignore[arg-type]
    )


def _repository_write(database_url: str, call: _ThreadCall, values: dict[str, object]) -> PlaybackEvidenceResult:
    database = Database(database_url)
    try:
        with database.session() as session:
            backend_pid = session.scalar(text("SELECT pg_backend_pid()"))
            assert isinstance(backend_pid, int)
            call.backend_pid = backend_pid
            call.backend_ready.set()
            return _create(PlaybackEvidenceRepository(session), values)
    finally:
        database.dispose()


def _delete_author(database_url: str, call: _ThreadCall, author_id: str) -> int:
    database = Database(database_url)
    try:
        with database.session() as session:
            backend_pid = session.scalar(text("SELECT pg_backend_pid()"))
            assert isinstance(backend_pid, int)
            call.backend_pid = backend_pid
            call.backend_ready.set()
            result = session.execute(delete(Author).where(Author.id == author_id))
            return int(result.rowcount or 0)  # type: ignore[attr-defined]
    finally:
        database.dispose()


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


def _short_lock_timeout_url(database_url: str, milliseconds: int) -> str:
    url = make_url(database_url)
    existing = url.query.get("options", "")
    assert isinstance(existing, str)
    scoped = url.update_query_dict({"options": f"{existing} -clock_timeout={milliseconds}"}, append=False)
    return scoped.render_as_string(hide_password=False)


def test_postgresql_fixture_is_limited_to_three_metadata_tables(postgresql_database: Database) -> None:
    inspector = inspect(postgresql_database.engine)
    assert set(inspector.get_table_names()) == {"authors", "jobs", "playback_evidence"}
    assert {
        (tuple(item["constrained_columns"]), item["referred_table"], item["options"].get("ondelete"))
        for item in inspector.get_foreign_keys("playback_evidence")
    } == {
        (("author_id",), "authors", "RESTRICT"),
        (("publication_job_id",), "jobs", "RESTRICT"),
    }


def test_postgresql_unique_wait_then_replays_committed_winner(postgresql_database: Database) -> None:
    author_id, job_id = _seed_parents(postgresql_database, "unique-commit")
    first_values = _values(author_id, job_id, 101)
    second_values = _values(
        author_id,
        job_id,
        101,
        observed_at=NOW + timedelta(hours=1),
        confirmed_at=NOW + timedelta(hours=1, seconds=2),
    )
    winner_session = postgresql_database.session_factory()
    try:
        winner = _create(PlaybackEvidenceRepository(winner_session), first_values)
        contender = _start_call(lambda call: _repository_write(postgresql_database.url, call, second_values))
        _assert_waiting_on_postgresql_lock(postgresql_database.url, contender)
        winner_session.commit()
    finally:
        winner_session.close()
    _await_call(contender)

    assert contender.errors == []
    replay = contender.values[0]
    assert isinstance(replay, PlaybackEvidenceResult)
    assert replay.replayed is True
    assert replay.id == winner.id
    assert replay.observed_at == winner.observed_at == NOW
    assert replay.confirmed_at == winner.confirmed_at == NOW + timedelta(seconds=1)


def test_postgresql_unique_wait_then_creates_after_winner_rollback(postgresql_database: Database) -> None:
    author_id, job_id = _seed_parents(postgresql_database, "unique-rollback")
    first_values = _values(author_id, job_id, 102)
    second_observed = NOW + timedelta(hours=2)
    second_values = _values(
        author_id,
        job_id,
        102,
        observed_at=second_observed,
        confirmed_at=second_observed + timedelta(seconds=2),
    )
    winner_session = postgresql_database.session_factory()
    try:
        rolled_back = _create(PlaybackEvidenceRepository(winner_session), first_values)
        contender = _start_call(lambda call: _repository_write(postgresql_database.url, call, second_values))
        _assert_waiting_on_postgresql_lock(postgresql_database.url, contender)
        winner_session.rollback()
    finally:
        winner_session.close()
    _await_call(contender)

    assert contender.errors == []
    created = contender.values[0]
    assert isinstance(created, PlaybackEvidenceResult)
    assert created.replayed is False
    assert created.id != rolled_back.id
    assert created.observed_at == second_observed


def test_postgresql_unique_wait_fails_closed_on_conflicting_identity(postgresql_database: Database) -> None:
    author_id, job_id = _seed_parents(postgresql_database, "unique-conflict")
    winner_session = postgresql_database.session_factory()
    try:
        winner = _create(PlaybackEvidenceRepository(winner_session), _values(author_id, job_id, 103))
        contender = _start_call(
            lambda call: _repository_write(
                postgresql_database.url,
                call,
                _values(author_id, job_id, 103, item_fingerprint="1" * 64),
            )
        )
        _assert_waiting_on_postgresql_lock(postgresql_database.url, contender)
        winner_session.commit()
    finally:
        winner_session.close()
    _await_call(contender)

    assert contender.values == []
    assert len(contender.errors) == 1
    conflict = contender.errors[0]
    assert isinstance(conflict, PlaybackEvidenceConflictError)
    assert conflict.code == "playback_evidence_identity_conflict"
    assert conflict.evidence_id == winner.id


def test_postgresql_different_observations_create_independently(postgresql_database: Database) -> None:
    author_id, job_id = _seed_parents(postgresql_database, "different")
    ready = Barrier(2)

    def create(seed: int) -> PlaybackEvidenceResult:
        worker = Database(postgresql_database.url)
        try:
            ready.wait()
            with worker.session() as session:
                return _create(PlaybackEvidenceRepository(session), _values(author_id, job_id, seed))
        finally:
            worker.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, (104, 105)))

    assert all(result.replayed is False for result in results)
    assert len({result.id for result in results}) == 2


def test_postgresql_committed_evidence_prevents_concurrent_parent_delete(postgresql_database: Database) -> None:
    author_id, job_id = _seed_parents(postgresql_database, "insert-before-delete")
    winner_session = postgresql_database.session_factory()
    try:
        winner = _create(PlaybackEvidenceRepository(winner_session), _values(author_id, job_id, 106))
        deletion = _start_call(lambda call: _delete_author(postgresql_database.url, call, author_id))
        _assert_waiting_on_postgresql_lock(postgresql_database.url, deletion)
        winner_session.commit()
    finally:
        winner_session.close()
    _await_call(deletion)

    assert deletion.values == []
    assert len(deletion.errors) == 1
    assert isinstance(deletion.errors[0], IntegrityError)
    with postgresql_database.session() as session:
        assert session.get(Author, author_id) is not None
        assert session.get(PlaybackEvidence, winner.id) is not None


def test_postgresql_committed_parent_delete_prevents_concurrent_evidence_insert(
    postgresql_database: Database,
) -> None:
    author_id, job_id = _seed_parents(postgresql_database, "delete-before-insert")
    deleting_session = postgresql_database.session_factory()
    try:
        deleted = deleting_session.execute(delete(Author).where(Author.id == author_id))
        assert deleted.rowcount == 1  # type: ignore[attr-defined]
        insertion = _start_call(
            lambda call: _repository_write(
                postgresql_database.url,
                call,
                _values(author_id, job_id, 107),
            )
        )
        _assert_waiting_on_postgresql_lock(postgresql_database.url, insertion)
        deleting_session.commit()
    finally:
        deleting_session.close()
    _await_call(insertion)

    assert insertion.values == []
    assert len(insertion.errors) == 1
    assert isinstance(insertion.errors[0], IntegrityError)
    with postgresql_database.session() as session:
        assert session.get(Author, author_id) is None
        assert (
            session.scalar(
                select(func.count()).select_from(PlaybackEvidence).where(PlaybackEvidence.author_id == author_id)
            )
            == 0
        )


def test_postgresql_lock_timeout_leaves_retryable_natural_replay(postgresql_database: Database) -> None:
    author_id, job_id = _seed_parents(postgresql_database, "timeout")
    values = _values(author_id, job_id, 108)
    winner_session = postgresql_database.session_factory()
    try:
        winner = _create(PlaybackEvidenceRepository(winner_session), values)
        timeout_url = _short_lock_timeout_url(postgresql_database.url, 200)
        contender = _start_call(lambda call: _repository_write(timeout_url, call, values))
        _await_call(contender)
        assert contender.values == []
        assert len(contender.errors) == 1
        assert isinstance(contender.errors[0], OperationalError)
        winner_session.commit()
    finally:
        winner_session.close()

    with postgresql_database.session() as session:
        replay = _create(PlaybackEvidenceRepository(session), values)
        assert replay.replayed is True
        assert replay.id == winner.id
        assert (
            session.scalar(
                select(func.count())
                .select_from(PlaybackEvidence)
                .where(PlaybackEvidence.observation_fingerprint == values["observation_fingerprint"])
            )
            == 1
        )
