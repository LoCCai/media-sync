"""SQLite integration coverage for the append-only playback-evidence repository."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from media_sync.infrastructure.db import (
    AuthorRepository,
    AuthorUpsert,
    Database,
    JobRepository,
    PlaybackEvidence,
    PlaybackEvidenceConflictError,
    PlaybackEvidenceRepository,
    PlaybackEvidenceResult,
    PlaybackEvidenceTransactionError,
)
from media_sync.infrastructure.db.database import SQLITE_IMMEDIATE_OPTION

NOW = datetime(2026, 9, 5, 9, tzinfo=UTC)
PROFILE = "a" * 64
PUBLICATION = "b" * 64
SELECTOR = "c" * 64
ITEM = "d" * 64
OBSERVATION = "e" * 64


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'playback-evidence.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_parents(database: Database, suffix: str = "primary") -> tuple[str, str]:
    with database.session() as session:
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="xhs", remote_id=f"evidence-author-{suffix}", display_name=f"Author {suffix}")
        )
        job = JobRepository(session).enqueue(
            job_type="export.emby",
            natural_key=f"evidence-publication-{suffix}",
            payload={"schema_version": 1},
            available_at=NOW,
        )
        return author.id, job.id


def _values(
    parent_author_id: str,
    parent_job_id: str,
    **overrides: object,
) -> dict[str, object]:
    values: dict[str, object] = {
        "author_id": parent_author_id,
        "publication_job_id": parent_job_id,
        "profile_fingerprint": PROFILE,
        "publication_fingerprint": PUBLICATION,
        "selector_fingerprint": SELECTOR,
        "item_fingerprint": ITEM,
        "observation_fingerprint": OBSERVATION,
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
        schema_version=values.get("schema_version", 1),  # type: ignore[arg-type]
    )


def test_create_reserves_sqlite_writer_uses_savepoint_and_flushes_without_commit(database: Database) -> None:
    author_id, job_id = _seed_parents(database)
    session = database.session_factory()
    statements: list[str] = []

    def capture_statement(_connection: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    event.listen(database.engine, "before_cursor_execute", capture_statement)
    try:
        with patch.object(session, "begin_nested", wraps=session.begin_nested) as begin_nested:
            result = _create(PlaybackEvidenceRepository(session), _values(author_id, job_id))

        assert result.replayed is False
        assert session.connection().get_execution_options()[SQLITE_IMMEDIATE_OPTION] is True
        assert statements[0] == "BEGIN IMMEDIATE"
        assert next(index for index, statement in enumerate(statements) if statement.startswith("SELECT")) > 0
        begin_nested.assert_called_once_with()
        assert session.scalar(select(func.count()).select_from(PlaybackEvidence)) == 1

        session.rollback()
        with database.session() as observer:
            assert observer.scalar(select(func.count()).select_from(PlaybackEvidence)) == 0
    finally:
        session.close()
        event.remove(database.engine, "before_cursor_execute", capture_statement)


def test_sqlite_existing_deferred_transaction_fails_closed_before_natural_key_read(database: Database) -> None:
    author_id, job_id = _seed_parents(database)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PlaybackEvidence)) == 0
        assert SQLITE_IMMEDIATE_OPTION not in session.connection().get_execution_options()

        with pytest.raises(PlaybackEvidenceTransactionError) as rejected:
            _create(PlaybackEvidenceRepository(session), _values(author_id, job_id))

        assert rejected.value.code == "playback_evidence_sqlite_writer_reservation_required"
        assert str(rejected.value) == "playback_evidence_sqlite_writer_reservation_required"
        assert session.scalar(select(func.count()).select_from(PlaybackEvidence)) == 0


def test_serial_replay_returns_first_row_and_ignores_new_request_timestamps(database: Database) -> None:
    author_id, job_id = _seed_parents(database)
    first_observed = NOW.astimezone(timezone(timedelta(hours=8)))
    first_confirmed = first_observed + timedelta(seconds=2)
    later_observed = NOW + timedelta(days=1)
    later_confirmed = later_observed + timedelta(seconds=30)

    with database.session() as session:
        repository = PlaybackEvidenceRepository(session)
        first = _create(
            repository,
            _values(author_id, job_id, observed_at=first_observed, confirmed_at=first_confirmed),
        )
        replay = _create(
            repository,
            _values(author_id, job_id, observed_at=later_observed, confirmed_at=later_confirmed),
        )

        assert first.replayed is False
        assert replay.replayed is True
        assert replay.id == first.id
        assert replay.observed_at == first.observed_at == NOW
        assert replay.confirmed_at == first.confirmed_at == NOW + timedelta(seconds=2)
        assert session.scalar(select(func.count()).select_from(PlaybackEvidence)) == 1


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("profile_fingerprint", "1" * 64),
        ("publication_fingerprint", "2" * 64),
        ("selector_fingerprint", "3" * 64),
        ("item_fingerprint", "4" * 64),
    ],
)
def test_replay_fails_closed_when_context_identity_conflicts(
    database: Database,
    field: str,
    replacement: str,
) -> None:
    author_id, job_id = _seed_parents(database)
    with database.session() as session:
        repository = PlaybackEvidenceRepository(session)
        first = _create(repository, _values(author_id, job_id))

        with pytest.raises(PlaybackEvidenceConflictError) as conflict:
            _create(repository, _values(author_id, job_id, **{field: replacement}))

        assert conflict.value.code == "playback_evidence_identity_conflict"
        assert conflict.value.evidence_id == first.id
        rendered = f"{conflict.value!s} {conflict.value!r}"
        assert rendered == (
            "playback_evidence_identity_conflict PlaybackEvidenceConflictError('playback_evidence_identity_conflict')"
        )
        assert OBSERVATION not in rendered


@pytest.mark.parametrize("identity", ["author", "job"])
def test_replay_fails_closed_when_parent_identity_conflicts(database: Database, identity: str) -> None:
    author_id, job_id = _seed_parents(database)
    other_author_id, other_job_id = _seed_parents(database, "other")
    with database.session() as session:
        repository = PlaybackEvidenceRepository(session)
        first = _create(repository, _values(author_id, job_id))
        conflicting_author = other_author_id if identity == "author" else author_id
        conflicting_job = other_job_id if identity == "job" else job_id

        with pytest.raises(PlaybackEvidenceConflictError) as conflict:
            _create(repository, _values(conflicting_author, conflicting_job))

        assert conflict.value.evidence_id == first.id


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("schema_version", True, "unsupported playback evidence schema_version"),
        ("schema_version", 2, "unsupported playback evidence schema_version"),
        ("author_id", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA", "author_id must be a canonical UUID"),
        ("publication_job_id", "not-a-uuid", "publication_job_id must be a canonical UUID"),
        ("profile_fingerprint", "A" * 64, "profile_fingerprint must be a lowercase SHA-256 digest"),
        ("publication_fingerprint", "b" * 63, "publication_fingerprint must be a lowercase SHA-256 digest"),
        ("selector_fingerprint", "g" * 64, "selector_fingerprint must be a lowercase SHA-256 digest"),
        ("item_fingerprint", 1, "item_fingerprint must be a lowercase SHA-256 digest"),
        ("observation_fingerprint", "e" * 65, "observation_fingerprint must be a lowercase SHA-256 digest"),
        ("observed_at", NOW.replace(tzinfo=None), "observed_at must be a timezone-aware timestamp"),
        ("confirmed_at", "2026-09-05T09:00:01Z", "confirmed_at must be a timezone-aware timestamp"),
        ("confirmed_at", NOW - timedelta(microseconds=1), "observed_at must not be after confirmed_at"),
    ],
)
def test_invalid_inputs_are_rejected_before_persistence(
    database: Database,
    field: str,
    replacement: object,
    message: str,
) -> None:
    author_id, job_id = _seed_parents(database)
    with database.session() as session:
        with pytest.raises(ValueError, match=message):
            _create(PlaybackEvidenceRepository(session), _values(author_id, job_id, **{field: replacement}))
        assert session.scalar(select(func.count()).select_from(PlaybackEvidence)) == 0


def test_foreign_key_integrity_error_is_not_collapsed_to_identity_conflict(database: Database) -> None:
    _author_id, job_id = _seed_parents(database)
    missing_author_id = "10000000-0000-4000-8000-000000000099"
    with database.session() as session:
        repository = PlaybackEvidenceRepository(session)
        with pytest.raises(IntegrityError):
            _create(repository, _values(missing_author_id, job_id))

        assert session.scalar(select(func.count()).select_from(PlaybackEvidence)) == 0


def test_sqlite_two_thread_replay_persists_one_winner_and_its_timestamps(database: Database) -> None:
    author_id, job_id = _seed_parents(database)
    ready = Barrier(2)

    def create(index: int) -> PlaybackEvidenceResult:
        worker_database = Database(database.url)
        try:
            requested_at = NOW + timedelta(minutes=index)
            ready.wait()
            with worker_database.session() as session:
                return _create(
                    PlaybackEvidenceRepository(session),
                    _values(
                        author_id,
                        job_id,
                        observed_at=requested_at,
                        confirmed_at=requested_at + timedelta(seconds=1),
                    ),
                )
        finally:
            worker_database.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, range(2)))

    assert len({result.id for result in results}) == 1
    assert sorted(result.replayed for result in results) == [False, True]
    assert len({result.observed_at for result in results}) == 1
    assert len({result.confirmed_at for result in results}) == 1
    assert results[0].observed_at in {NOW, NOW + timedelta(minutes=1)}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PlaybackEvidence)) == 1


def test_sqlite_two_thread_conflicting_identity_has_one_row_and_fixed_error(database: Database) -> None:
    author_id, job_id = _seed_parents(database)
    ready = Barrier(2)

    def create(index: int) -> tuple[str, str]:
        worker_database = Database(database.url)
        try:
            ready.wait()
            try:
                with worker_database.session() as session:
                    result = _create(
                        PlaybackEvidenceRepository(session),
                        _values(author_id, job_id, item_fingerprint=f"{index + 1:064x}"),
                    )
                return "created", result.id
            except PlaybackEvidenceConflictError as error:
                return error.code, error.evidence_id
        finally:
            worker_database.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, range(2)))

    assert sorted(status for status, _evidence_id in results) == [
        "created",
        "playback_evidence_identity_conflict",
    ]
    assert len({evidence_id for _status, evidence_id in results}) == 1
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PlaybackEvidence)) == 1
