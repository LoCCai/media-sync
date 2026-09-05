"""Append-only persistence for authenticated playback attestations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import SQLITE_IMMEDIATE_OPTION
from .models import PlaybackEvidence
from .repositories import RepositoryError

PLAYBACK_EVIDENCE_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class PlaybackEvidenceConflictError(RepositoryError):
    """One natural observation identity was reused for different evidence."""

    code = "playback_evidence_identity_conflict"

    def __init__(self, evidence_id: str) -> None:
        self.evidence_id = evidence_id
        super().__init__(self.code)


class PlaybackEvidenceTransactionError(RepositoryError):
    """The caller began an unsafe SQLite transaction before repository entry."""

    code = "playback_evidence_sqlite_writer_reservation_required"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class PlaybackEvidenceResult:
    """The first durable row for one observation and whether this call replayed it."""

    id: str
    schema_version: int
    author_id: str
    publication_job_id: str
    profile_fingerprint: str = field(repr=False)
    publication_fingerprint: str = field(repr=False)
    selector_fingerprint: str = field(repr=False)
    item_fingerprint: str = field(repr=False)
    observation_fingerprint: str = field(repr=False)
    observed_at: datetime = field(repr=False)
    confirmed_at: datetime = field(repr=False)
    replayed: bool = False


def _canonical_uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a canonical UUID")
    try:
        canonical = str(UUID(value))
    except ValueError as error:
        raise ValueError(f"{name} must be a canonical UUID") from error
    if canonical != value:
        raise ValueError(f"{name} must be a canonical UUID")
    return value


def _sha256(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _aware_utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware timestamp")
    return value.astimezone(UTC)


def _reserve_sqlite_writer(session: Session) -> None:
    """Make the initial natural-key read linearizable on SQLite."""

    bind = session.get_bind()
    if bind.dialect.name != "sqlite":
        return
    if not session.in_transaction():
        execution_options: Mapping[str, Any] = {SQLITE_IMMEDIATE_OPTION: True}
        session.connection(execution_options=execution_options)
        return
    if not session.connection().get_execution_options().get(SQLITE_IMMEDIATE_OPTION):
        raise PlaybackEvidenceTransactionError()


class PlaybackEvidenceRepository:
    """Create or replay immutable evidence without owning the outer commit."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_or_replay(
        self,
        *,
        author_id: str,
        publication_job_id: str,
        profile_fingerprint: str,
        publication_fingerprint: str,
        selector_fingerprint: str,
        item_fingerprint: str,
        observation_fingerprint: str,
        observed_at: datetime,
        confirmed_at: datetime,
        schema_version: int = PLAYBACK_EVIDENCE_SCHEMA_VERSION,
    ) -> PlaybackEvidenceResult:
        if type(schema_version) is not int or schema_version != PLAYBACK_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported playback evidence schema_version")
        normalized_author_id = _canonical_uuid(author_id, "author_id")
        normalized_job_id = _canonical_uuid(publication_job_id, "publication_job_id")
        normalized_profile = _sha256(profile_fingerprint, "profile_fingerprint")
        normalized_publication = _sha256(publication_fingerprint, "publication_fingerprint")
        normalized_selector = _sha256(selector_fingerprint, "selector_fingerprint")
        normalized_item = _sha256(item_fingerprint, "item_fingerprint")
        normalized_observation = _sha256(observation_fingerprint, "observation_fingerprint")
        normalized_observed_at = _aware_utc(observed_at, "observed_at")
        normalized_confirmed_at = _aware_utc(confirmed_at, "confirmed_at")
        if normalized_observed_at > normalized_confirmed_at:
            raise ValueError("observed_at must not be after confirmed_at")

        identity = (
            schema_version,
            normalized_author_id,
            normalized_job_id,
            normalized_profile,
            normalized_publication,
            normalized_selector,
            normalized_item,
            normalized_observation,
        )
        _reserve_sqlite_writer(self.session)
        existing = self._by_observation_fingerprint(normalized_observation)
        if existing is not None:
            return self._replay(existing, identity)

        evidence = PlaybackEvidence(
            schema_version=schema_version,
            author_id=normalized_author_id,
            publication_job_id=normalized_job_id,
            profile_fingerprint=normalized_profile,
            publication_fingerprint=normalized_publication,
            selector_fingerprint=normalized_selector,
            item_fingerprint=normalized_item,
            observation_fingerprint=normalized_observation,
            observed_at=normalized_observed_at,
            confirmed_at=normalized_confirmed_at,
        )
        try:
            with self.session.begin_nested():
                self.session.add(evidence)
                self.session.flush()
        except IntegrityError:
            # The savepoint keeps the caller's transaction usable.  A unique
            # contender may now be visible under PostgreSQL READ COMMITTED.
            self.session.expire_all()
            existing = self._by_observation_fingerprint(normalized_observation)
            if existing is not None:
                return self._replay(existing, identity)
            # Preserve ordinary FK/check failures and their database semantics.
            raise
        return self._result(evidence, replayed=False)

    def _by_observation_fingerprint(self, fingerprint: str) -> PlaybackEvidence | None:
        return self.session.scalar(
            select(PlaybackEvidence).where(PlaybackEvidence.observation_fingerprint == fingerprint).limit(1)
        )

    @staticmethod
    def _replay(
        evidence: PlaybackEvidence,
        identity: tuple[int, str, str, str, str, str, str, str],
    ) -> PlaybackEvidenceResult:
        persisted_identity = (
            evidence.schema_version,
            evidence.author_id,
            evidence.publication_job_id,
            evidence.profile_fingerprint,
            evidence.publication_fingerprint,
            evidence.selector_fingerprint,
            evidence.item_fingerprint,
            evidence.observation_fingerprint,
        )
        if persisted_identity != identity:
            raise PlaybackEvidenceConflictError(evidence.id)
        return PlaybackEvidenceRepository._result(evidence, replayed=True)

    @staticmethod
    def _result(evidence: PlaybackEvidence, *, replayed: bool) -> PlaybackEvidenceResult:
        return PlaybackEvidenceResult(
            id=evidence.id,
            schema_version=evidence.schema_version,
            author_id=evidence.author_id,
            publication_job_id=evidence.publication_job_id,
            profile_fingerprint=evidence.profile_fingerprint,
            publication_fingerprint=evidence.publication_fingerprint,
            selector_fingerprint=evidence.selector_fingerprint,
            item_fingerprint=evidence.item_fingerprint,
            observation_fingerprint=evidence.observation_fingerprint,
            observed_at=evidence.observed_at,
            confirmed_at=evidence.confirmed_at,
            replayed=replayed,
        )


__all__ = [
    "PLAYBACK_EVIDENCE_SCHEMA_VERSION",
    "PlaybackEvidenceConflictError",
    "PlaybackEvidenceRepository",
    "PlaybackEvidenceResult",
    "PlaybackEvidenceTransactionError",
]
