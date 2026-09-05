"""Bounded SQLite evidence reads and author-scoped qualification composition."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, func, select

from media_sync.application.media_server_observation import media_server_observation_fingerprint
from media_sync.application.playback_evidence_query import PlaybackEvidenceQueryService
from media_sync.application.qualifications import QualificationService
from media_sync.infrastructure.db import Database, PlaybackEvidence, PlaybackEvidenceRepository
from tests.integration.test_playback_evidence_service import (
    CONFIRMED_AT,
    ITEM,
    OBSERVED_AT,
    PROFILE,
    PUBLICATION,
    SELECTOR,
    _seed_parents,
    _service,
)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'projection.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def test_current_row_outside_history_page_still_qualifies_with_bounded_read_only_sql(database: Database) -> None:
    author_id, job_id = _seed_parents(database)
    confirmation, observation, fingerprint, _audits = _service(database, author_id, job_id)
    first = confirmation.confirm(author_id, fingerprint)
    with database.session() as session:
        for index in range(1, 62):
            item = f"{index:064x}"
            assert item != ITEM
            session.add(
                PlaybackEvidence(
                    author_id=author_id,
                    publication_job_id=job_id,
                    profile_fingerprint=PROFILE,
                    publication_fingerprint=PUBLICATION,
                    selector_fingerprint=SELECTOR,
                    item_fingerprint=item,
                    observation_fingerprint=media_server_observation_fingerprint(
                        author_id=author_id,
                        profile_fingerprint=PROFILE,
                        publication_fingerprint=PUBLICATION,
                        selector_fingerprint=SELECTOR,
                        item_fingerprint=item,
                    ),
                    observed_at=OBSERVED_AT,
                    confirmed_at=CONFIRMED_AT + timedelta(seconds=index),
                )
            )

    statements: list[tuple[str, object]] = []

    def capture(
        _connection: object, _cursor: object, statement: str, parameters: object, _context: object, _many: bool
    ) -> None:
        statements.append((statement, parameters))

    event.listen(database.engine, "before_cursor_execute", capture)
    try:
        query = PlaybackEvidenceQueryService(database, observation, monotonic=lambda: 0.0, clock=lambda: CONFIRMED_AT)
        result = query.snapshot(author_id, limit=20)
    finally:
        event.remove(database.engine, "before_cursor_execute", capture)
    assert result.current is not None and result.current.id == first.id
    assert result.human_status == "PASS" and result.history_truncated is True
    assert len(result.history) == 20
    assert all(row.state == "stale" and row.id != first.id for row in result.history)
    assert [row.confirmed_at for row in result.history] == sorted(
        (row.confirmed_at for row in result.history), reverse=True
    )
    ledger_reads = [(sql, params) for sql, params in statements if "playback_evidence" in sql.lower()]
    assert len(ledger_reads) == 2
    assert all(
        sql.lstrip().upper().startswith("SELECT") and "LIMIT" in sql and "COUNT" not in sql.upper()
        for sql, _params in ledger_reads
    )
    assert ledger_reads[0][1][-2:] == (1, 0)
    assert ledger_reads[1][1][-2:] == (21, 0)
    assert not any(
        sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "BEGIN IMMEDIATE"))
        for sql, _params in statements
    )
    assert observation.lookup_calls == 2  # one confirmation, one projection
    assert observation.resolve_calls == 4
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PlaybackEvidence)) == 62


def test_qualification_calls_only_one_requested_author_and_keeps_unrequested_scope_idle(database: Database) -> None:
    author_id, job_id = _seed_parents(database)
    confirmation, observation, fingerprint, _audits = _service(database, author_id, job_id)
    confirmation.confirm(author_id, fingerprint)
    query = PlaybackEvidenceQueryService(database, observation, monotonic=lambda: 0.0)
    service = QualificationService(database, playback_evidence=query)

    unrequested = service.snapshot(media_server_configured=True)
    assert unrequested["schema_version"] == 3
    assert unrequested["media_server"]["playback_evidence"]["scope"] == "not_requested"
    assert observation.lookup_calls == 1
    requested = service.snapshot(media_server_configured=True, author_id=author_id)
    assert observation.lookup_calls == 2
    media = requested["media_server"]
    rows = {row["capability"]: row for row in media["human_qualification"]}
    assert rows["playback_evidence"] == {
        "capability": "playback_evidence",
        "implementation_status": "IMPLEMENTED",
        "human_status": "PASS",
        "scope": "author",
        "author_id": author_id,
    }
    assert media["playback_evidence"]["author_id"] == author_id
    assert rows["provider_task_completion"]["reason"] == "provider_api_unsupported"
    assert rows["automatic_post_export_scan"]["implementation_status"] == "NOT_IMPLEMENTED"
    assert all(row["human_status"] != "PASS" for name, row in rows.items() if name != "playback_evidence")
    assert all(
        row["human_status"] == "NOT_RUN"
        for platform in requested["platforms"]
        for row in platform["human_qualification"]
    )


def test_unconfigured_history_stays_unknown_and_repository_reads_validate_bounds(database: Database) -> None:
    author_id, job_id = _seed_parents(database)
    confirmation, _observation, fingerprint, _audits = _service(database, author_id, job_id)
    first = confirmation.confirm(author_id, fingerprint)
    result = PlaybackEvidenceQueryService(database, None).snapshot(author_id, limit=50)
    assert result.current is None and result.human_status == "NOT_RUN"
    assert result.current_state == "unavailable"
    assert [(row.id, row.state) for row in result.history] == [(first.id, "unknown")]
    assert result.history_truncated is False
    with database.session() as session:
        repository = PlaybackEvidenceRepository(session)
        for limit in (0, 51, True, 1.5):
            with pytest.raises(ValueError):
                repository.history_by_author(author_id, limit=limit)
        with pytest.raises(ValueError):
            repository.history_by_author("private-invalid-author")
        with pytest.raises(ValueError):
            repository.by_observation("private-invalid-fingerprint")
