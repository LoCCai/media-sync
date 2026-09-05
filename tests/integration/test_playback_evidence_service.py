"""SQLite composition of confirmation authority and append-only persistence."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from media_sync.application.media_server_observation import (
    MediaServerAuthorLookupResult,
    media_server_observation_fingerprint,
)
from media_sync.application.media_server_publication import MediaServerPublicationTarget
from media_sync.application.playback_evidence import (
    PlaybackEvidenceAuditCode,
    PlaybackEvidenceConfirmationError,
    PlaybackEvidenceService,
)
from media_sync.infrastructure.db import (
    AuthorRepository,
    AuthorUpsert,
    Database,
    JobRepository,
    PlaybackEvidence,
)

PROFILE = "1" * 64
PUBLICATION = "2" * 64
SELECTOR = "3" * 64
ITEM = "4" * 64
OBSERVED_AT = datetime(2026, 9, 5, 8, tzinfo=UTC)
CONFIRMED_AT = datetime(2026, 9, 5, 9, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'confirmation.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_parents(database: Database) -> tuple[str, str]:
    with database.session() as session:
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="bili", remote_id="confirmation-author", display_name="Confirmation Author")
        )
        job = JobRepository(session).enqueue(
            job_type="export.emby",
            natural_key="confirmation-publication",
            payload={"schema_version": 1},
            available_at=OBSERVED_AT,
        )
        return author.id, job.id


def _target(author_id: str, job_id: str) -> MediaServerPublicationTarget:
    return MediaServerPublicationTarget(
        provider_key="media-sync-bili-creator",
        provider_value="private-provider-value",
        server_path="/srv/private-library/bili-confirmation",
        author_id=author_id,
        publication_job_id=job_id,
        platform="bili",
        author_relative_directory="bili-confirmation",
        server_path_style="posix",
        publication_fingerprint=PUBLICATION,
        selector_fingerprint=SELECTOR,
        managed_file_count=1,
    )


class _Observation:
    profile_fingerprint = PROFILE

    def __init__(self, target: MediaServerPublicationTarget, fingerprint: str) -> None:
        self.target = target
        self.fingerprint = fingerprint
        self.resolve_calls = 0
        self.lookup_calls = 0

    def resolve_target(self, author_id: str, *, deadline: float | None = None) -> MediaServerPublicationTarget:
        assert author_id == self.target.author_id
        assert deadline == 120.0
        self.resolve_calls += 1
        return self.target

    def lookup_author(
        self,
        target_or_author_id: MediaServerPublicationTarget,
        *,
        deadline: float | None = None,
    ) -> MediaServerAuthorLookupResult:
        assert target_or_author_id == self.target
        assert deadline == 120.0
        self.lookup_calls += 1
        return MediaServerAuthorLookupResult(
            schema_version=1,
            author_id=self.target.author_id,
            provider="emby",
            library_id_digest="5" * 64,
            publication_fingerprint=PUBLICATION,
            selector_fingerprint=SELECTOR,
            lookup_state="matched",
            match_count=1,
            item_fingerprint=ITEM,
            observation_fingerprint=self.fingerprint,
            observed_at=OBSERVED_AT.isoformat(),
            complete=True,
        )


def _service(
    database: Database,
    author_id: str,
    job_id: str,
) -> tuple[PlaybackEvidenceService, _Observation, str, list[PlaybackEvidenceAuditCode]]:
    fingerprint = media_server_observation_fingerprint(
        author_id=author_id,
        profile_fingerprint=PROFILE,
        publication_fingerprint=PUBLICATION,
        selector_fingerprint=SELECTOR,
        item_fingerprint=ITEM,
    )
    observation = _Observation(_target(author_id, job_id), fingerprint)
    audits: list[PlaybackEvidenceAuditCode] = []
    service = PlaybackEvidenceService(
        database,
        observation,
        monotonic=lambda: 0.0,
        clock=lambda: CONFIRMED_AT,
        audit_sink=audits.append,
    )
    return service, observation, fingerprint, audits


def test_confirmation_commits_once_and_replays_the_first_row(database: Database) -> None:
    author_id, job_id = _seed_parents(database)
    service, observation, fingerprint, audits = _service(database, author_id, job_id)

    created = service.confirm(author_id, fingerprint)
    replayed = service.confirm(author_id, fingerprint)

    assert created.replayed is False
    assert replayed.replayed is True
    assert replayed.id == created.id
    assert replayed.observed_at == created.observed_at == OBSERVED_AT
    assert replayed.confirmed_at == created.confirmed_at == CONFIRMED_AT
    assert observation.resolve_calls == 4
    assert observation.lookup_calls == 2
    assert audits == [
        PlaybackEvidenceAuditCode.CREATED,
        PlaybackEvidenceAuditCode.REPLAYED,
    ]
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PlaybackEvidence)) == 1
        row = session.scalar(select(PlaybackEvidence))
        assert row is not None
        assert row.author_id == author_id
        assert row.publication_job_id == job_id


def test_nonmatching_fingerprint_leaves_the_real_ledger_empty(database: Database) -> None:
    author_id, job_id = _seed_parents(database)
    service, _observation, _fingerprint, _audits = _service(database, author_id, job_id)

    with pytest.raises(PlaybackEvidenceConfirmationError) as rejected:
        service.confirm(author_id, "f" * 64)

    assert rejected.value.code == "playback_evidence_not_confirmable"
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PlaybackEvidence)) == 0
