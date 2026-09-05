"""Bounded current/history reads for one author's durable playback attestations."""

from __future__ import annotations

import hmac
import math
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from media_sync.application.media_server_observation import (
    MediaServerAuthorLookupResult,
    media_server_observation_fingerprint,
)
from media_sync.application.media_server_publication import MediaServerPublicationTarget
from media_sync.application.playback_evidence import PlaybackEvidenceDatabasePort, PlaybackEvidenceObservationPort
from media_sync.infrastructure.db import PlaybackEvidenceRepository, PlaybackEvidenceResult
from media_sync.infrastructure.db.playback_evidence_repository import MAX_PLAYBACK_EVIDENCE_HISTORY

DEFAULT_EVIDENCE_HISTORY_LIMIT = 20
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
CurrentEvidenceState = Literal["matched", "not_found", "unavailable"]
HistoricalEvidenceState = Literal["current", "stale", "unknown"]


class PlaybackEvidenceQueryError(RuntimeError):
    """Fixed query errors that never reflect request or storage values."""

    def __init__(self, code: Literal["playback_evidence_request_invalid", "playback_evidence_store_unavailable"]):
        self.code = code
        super().__init__(code)


def validate_evidence_query(author_id: str, limit: int) -> None:
    try:
        valid_author = isinstance(author_id, str) and str(UUID(author_id)) == author_id
    except ValueError:
        valid_author = False
    if not valid_author or type(limit) is not int or not 1 <= limit <= MAX_PLAYBACK_EVIDENCE_HISTORY:
        raise PlaybackEvidenceQueryError("playback_evidence_request_invalid")


@dataclass(frozen=True, slots=True)
class PlaybackEvidenceView:
    """Only local identity, server timestamps and a freshly derived state."""

    id: str
    author_id: str
    observed_at: datetime
    confirmed_at: datetime
    state: HistoricalEvidenceState

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "id": self.id,
            "author_id": self.author_id,
            "observed_at": self.observed_at.astimezone(UTC).isoformat(),
            "confirmed_at": self.confirmed_at.astimezone(UTC).isoformat(),
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class PlaybackEvidenceProjection:
    author_id: str
    checked_at: datetime
    current_state: CurrentEvidenceState
    current: PlaybackEvidenceView | None
    history: tuple[PlaybackEvidenceView, ...]
    history_truncated: bool
    limit: int

    @property
    def human_status(self) -> Literal["PASS", "NOT_RUN"]:
        return "PASS" if self.current_state == "matched" and self.current is not None else "NOT_RUN"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "scope": "author",
            "author_id": self.author_id,
            "checked_at": self.checked_at.astimezone(UTC).isoformat(),
            "current_state": self.current_state,
            "human_status": self.human_status,
            "current": self.current.as_dict() if self.current is not None else None,
            "history": [row.as_dict() for row in self.history],
            "history_truncated": self.history_truncated,
            "limit": self.limit,
        }


def unrequested_playback_evidence() -> dict[str, object]:
    return {
        "schema_version": 1,
        "scope": "not_requested",
        "author_id": None,
        "checked_at": None,
        "current_state": "not_requested",
        "human_status": "NOT_RUN",
        "current": None,
        "history": [],
        "history_truncated": False,
        "limit": DEFAULT_EVIDENCE_HISTORY_LIMIT,
    }


@dataclass(frozen=True, slots=True)
class _CurrentAuthority:
    state: Literal["matched", "not_found"]
    target: MediaServerPublicationTarget = field(repr=False)
    profile: str = field(repr=False)
    item: str | None = field(repr=False)
    observation: str | None = field(repr=False)

    def matches(self, row: PlaybackEvidenceResult) -> bool:
        return (
            self.state == "matched"
            and row.schema_version == 1
            and row.author_id == self.target.author_id
            and row.publication_job_id == self.target.publication_job_id
            and row.profile_fingerprint == self.profile
            and row.publication_fingerprint == self.target.publication_fingerprint
            and row.selector_fingerprint == self.target.selector_fingerprint
            and row.item_fingerprint == self.item
            and row.observation_fingerprint == self.observation
        )


class PlaybackEvidenceQueryService:
    """Read one author without making a remote call under a database transaction."""

    def __init__(
        self,
        database: PlaybackEvidenceDatabasePort,
        observation: PlaybackEvidenceObservationPort | None,
        *,
        timeout_seconds: float = 120.0,
        monotonic: Callable[[], float] = time.monotonic,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        repository_factory: Callable[[Session], PlaybackEvidenceRepository] = PlaybackEvidenceRepository,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int | float)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 120
        ):
            raise ValueError("evidence query timeout must be finite and at most 120 seconds")
        self._database = database
        self._observation = observation
        self._timeout_seconds = timeout_seconds
        self._monotonic = monotonic
        self._clock = clock
        self._repository_factory = repository_factory
        self._authority_lock = threading.Lock()

    def snapshot(self, author_id: str, *, limit: int = DEFAULT_EVIDENCE_HISTORY_LIMIT) -> PlaybackEvidenceProjection:
        validate_evidence_query(author_id, limit)
        authority = self._current_authority(author_id)
        current: PlaybackEvidenceResult | None = None
        try:
            with self._database.session() as session:
                repository = self._repository_factory(session)
                if authority is not None and authority.observation is not None:
                    candidate = repository.by_observation(authority.observation)
                    if candidate is not None:
                        if authority.matches(candidate):
                            current = candidate
                        else:
                            # A digest collision/corrupt context cannot promote a row or
                            # establish staleness for any historical evidence.
                            authority = None
                rows = repository.history_by_author(
                    author_id, limit=limit, exclude_id=current.id if current is not None else None
                )
        except Exception:
            raise PlaybackEvidenceQueryError("playback_evidence_store_unavailable") from None
        state: CurrentEvidenceState = authority.state if authority is not None else "unavailable"
        history_state: HistoricalEvidenceState = "unknown" if authority is None else "stale"
        return PlaybackEvidenceProjection(
            author_id=author_id,
            checked_at=self._clock(),
            current_state=state,
            current=self._view(current, "current") if current is not None else None,
            history=tuple(self._view(row, history_state) for row in rows[:limit]),
            history_truncated=len(rows) > limit,
            limit=limit,
        )

    def _current_authority(self, author_id: str) -> _CurrentAuthority | None:
        if self._observation is None:
            return None
        try:
            started = self._time()
            deadline = started + self._timeout_seconds
            self._require_time(deadline)
            remaining = deadline - self._time()
            if remaining <= 0 or not self._authority_lock.acquire(timeout=remaining):
                return None
            try:
                return self._resolve(author_id, deadline)
            finally:
                self._authority_lock.release()
        except Exception:
            # Remote exceptions and selectors cannot cross the safe read boundary.
            return None

    def _resolve(self, author_id: str, deadline: float) -> _CurrentAuthority:
        observation = self._observation
        assert observation is not None
        self._require_time(deadline)
        target_a = observation.resolve_target(author_id, deadline=deadline)
        self._require_time(deadline)
        profile_a = observation.profile_fingerprint
        self._require_time(deadline)
        if not isinstance(target_a, MediaServerPublicationTarget) or target_a.author_id != author_id:
            raise ValueError("evidence authority unavailable")
        if not isinstance(profile_a, str) or not _DIGEST.fullmatch(profile_a):
            raise ValueError("evidence authority unavailable")
        lookup = observation.lookup_author(target_a, deadline=deadline)
        self._require_time(deadline)
        target_b = observation.resolve_target(author_id, deadline=deadline)
        self._require_time(deadline)
        profile_b = observation.profile_fingerprint
        self._require_time(deadline)
        if target_a != target_b or profile_a != profile_b:
            raise ValueError("evidence authority unavailable")
        if (
            not isinstance(lookup, MediaServerAuthorLookupResult)
            or lookup.complete is not True
            or lookup.author_id != author_id
            or lookup.publication_fingerprint != target_a.publication_fingerprint
            or lookup.selector_fingerprint != target_a.selector_fingerprint
        ):
            raise ValueError("evidence authority unavailable")
        if lookup.lookup_state == "not_found":
            if (
                lookup.match_count != 0
                or lookup.item_fingerprint is not None
                or lookup.observation_fingerprint is not None
            ):
                raise ValueError("evidence authority unavailable")
            return _CurrentAuthority("not_found", target_a, profile_a, None, None)
        if lookup.lookup_state != "matched" or lookup.match_count != 1 or lookup.item_fingerprint is None:
            raise ValueError("evidence authority unavailable")
        fingerprint = media_server_observation_fingerprint(
            author_id=author_id,
            profile_fingerprint=profile_a,
            publication_fingerprint=target_a.publication_fingerprint,
            selector_fingerprint=target_a.selector_fingerprint,
            item_fingerprint=lookup.item_fingerprint,
        )
        if lookup.observation_fingerprint is None or not hmac.compare_digest(
            lookup.observation_fingerprint, fingerprint
        ):
            raise ValueError("evidence authority unavailable")
        self._require_time(deadline)
        return _CurrentAuthority("matched", target_a, profile_a, lookup.item_fingerprint, fingerprint)

    def _time(self) -> float:
        value = self._monotonic()
        if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
            raise ValueError("evidence query clock unavailable")
        return float(value)

    def _require_time(self, deadline: float) -> None:
        if not math.isfinite(deadline) or self._time() >= deadline:
            raise ValueError("evidence query deadline exceeded")

    @staticmethod
    def _view(row: PlaybackEvidenceResult, state: HistoricalEvidenceState) -> PlaybackEvidenceView:
        return PlaybackEvidenceView(row.id, row.author_id, row.observed_at, row.confirmed_at, state)
