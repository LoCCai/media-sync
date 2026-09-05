"""TOCTOU-safe confirmation of one current media-server playback observation."""

from __future__ import annotations

import hmac
import logging
import math
import re
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from media_sync.application.media_server_observation import (
    MediaServerAuthorLookupResult,
    media_server_observation_fingerprint,
)
from media_sync.application.media_server_publication import MediaServerPublicationTarget
from media_sync.infrastructure.db import (
    PlaybackEvidenceConflictError,
    PlaybackEvidenceRepository,
    PlaybackEvidenceResult,
)
from media_sync.ports.media_server import MediaServerError

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MAX_CONFIRMATION_TIMEOUT_SECONDS = 120.0
_LOGGER = logging.getLogger(__name__)


class PlaybackEvidenceDatabasePort(Protocol):
    """The sole short transaction opened after all external validation."""

    def session(self) -> AbstractContextManager[Session]: ...


class PlaybackEvidenceObservationPort(Protocol):
    """Current publication and one bounded complete item lookup."""

    @property
    def profile_fingerprint(self) -> str: ...

    def resolve_target(
        self,
        author_id: str,
        *,
        deadline: float | None = None,
    ) -> MediaServerPublicationTarget: ...

    def lookup_author(
        self,
        target_or_author_id: MediaServerPublicationTarget,
        *,
        deadline: float | None = None,
    ) -> MediaServerAuthorLookupResult: ...


class PlaybackEvidenceAuditCode(StrEnum):
    """Fixed success-only audit events with no request-derived context."""

    CREATED = "playback_evidence_created"
    REPLAYED = "playback_evidence_replayed"


class PlaybackEvidenceConfirmationError(RuntimeError):
    """A fixed, redaction-safe confirmation rejection."""

    _CODES = frozenset(
        {
            "playback_evidence_confirmation_unavailable",
            "playback_evidence_identity_conflict",
            "playback_evidence_not_confirmable",
            "playback_evidence_request_invalid",
            "playback_evidence_store_unavailable",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._CODES:
            raise ValueError("unknown playback-evidence confirmation code")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PlaybackEvidenceConfirmation:
    """Safe projection of the first durable row for one observation."""

    id: str
    author_id: str
    observed_at: datetime
    confirmed_at: datetime
    replayed: bool
    schema_version: int = 1

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "author_id": self.author_id,
            "observed_at": self.observed_at.astimezone(UTC).isoformat(),
            "confirmed_at": self.confirmed_at.astimezone(UTC).isoformat(),
            "replayed": self.replayed,
        }


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _canonical_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise PlaybackEvidenceConfirmationError("playback_evidence_request_invalid")
    try:
        canonical = str(UUID(value))
    except ValueError:
        raise PlaybackEvidenceConfirmationError("playback_evidence_request_invalid") from None
    if canonical != value:
        raise PlaybackEvidenceConfirmationError("playback_evidence_request_invalid")
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise PlaybackEvidenceConfirmationError("playback_evidence_request_invalid")
    return value


class PlaybackEvidenceService:
    """Revalidate current authority, then persist one human attestation."""

    def __init__(
        self,
        database: PlaybackEvidenceDatabasePort,
        observation: PlaybackEvidenceObservationPort,
        *,
        timeout_seconds: float = _MAX_CONFIRMATION_TIMEOUT_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        clock: Callable[[], datetime] = _utc_now,
        audit_sink: Callable[[PlaybackEvidenceAuditCode], None] | None = None,
        repository_factory: Callable[[Session], PlaybackEvidenceRepository] = PlaybackEvidenceRepository,
    ) -> None:
        if not hasattr(database, "session"):
            raise TypeError("database must expose session")
        if not all(hasattr(observation, name) for name in ("resolve_target", "lookup_author")):
            raise TypeError("observation must expose resolve_target and lookup_author")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int | float)
            or not math.isfinite(timeout_seconds)
            or not 0 < float(timeout_seconds) <= _MAX_CONFIRMATION_TIMEOUT_SECONDS
        ):
            raise ValueError("timeout_seconds must be finite and at most 120 seconds")
        if not callable(monotonic) or not callable(clock) or not callable(repository_factory):
            raise TypeError("clock and repository seams must be callable")
        if audit_sink is not None and not callable(audit_sink):
            raise TypeError("audit_sink must be callable")
        self._database = database
        self._observation = observation
        self._timeout_seconds = float(timeout_seconds)
        self._monotonic = monotonic
        self._clock = clock
        self._audit_sink = audit_sink or self._default_audit_sink
        self._repository_factory = repository_factory
        self._authority_lock = threading.Lock()

    def confirm(self, author_id: str, observation_fingerprint: str) -> PlaybackEvidenceConfirmation:
        """Confirm only the exact item identity observed again at request time."""

        normalized_author_id = _canonical_uuid(author_id)
        submitted_fingerprint = _digest(observation_fingerprint)
        deadline = self._deadline()

        self._acquire_authority(deadline)
        try:
            self._require_time(deadline)
            target_a = self._observation.resolve_target(normalized_author_id, deadline=deadline)
            self._require_time(deadline)
            lookup = self._observation.lookup_author(target_a, deadline=deadline)
            self._require_time(deadline)
            target_b = self._observation.resolve_target(normalized_author_id, deadline=deadline)
            self._require_time(deadline)
            if not isinstance(target_a, MediaServerPublicationTarget) or not isinstance(
                target_b,
                MediaServerPublicationTarget,
            ):
                raise PlaybackEvidenceConfirmationError("playback_evidence_not_confirmable")
            if target_a != target_b:
                raise MediaServerError("media_server_publication_changed")
            if not isinstance(lookup, MediaServerAuthorLookupResult):
                raise PlaybackEvidenceConfirmationError("playback_evidence_not_confirmable")
            if lookup.lookup_state != "matched" or lookup.match_count != 1:
                raise PlaybackEvidenceConfirmationError("playback_evidence_not_confirmable")
            if (
                lookup.author_id != normalized_author_id
                or lookup.publication_fingerprint != target_a.publication_fingerprint
                or lookup.selector_fingerprint != target_a.selector_fingerprint
                or lookup.item_fingerprint is None
                or lookup.observation_fingerprint is None
            ):
                raise PlaybackEvidenceConfirmationError("playback_evidence_not_confirmable")

            profile_fingerprint = self._profile_fingerprint()
            try:
                recomputed_fingerprint = media_server_observation_fingerprint(
                    author_id=normalized_author_id,
                    profile_fingerprint=profile_fingerprint,
                    publication_fingerprint=target_a.publication_fingerprint,
                    selector_fingerprint=target_a.selector_fingerprint,
                    item_fingerprint=lookup.item_fingerprint,
                )
            except ValueError:
                raise PlaybackEvidenceConfirmationError("playback_evidence_not_confirmable") from None
            lookup_matches = hmac.compare_digest(lookup.observation_fingerprint, recomputed_fingerprint)
            submitted_matches = hmac.compare_digest(submitted_fingerprint, recomputed_fingerprint)
            if not lookup_matches or not submitted_matches:
                raise PlaybackEvidenceConfirmationError("playback_evidence_not_confirmable")

            observed_at = self._observed_at(lookup.observed_at)
            confirmed_at = self._now()
            if observed_at > confirmed_at:
                raise PlaybackEvidenceConfirmationError("playback_evidence_confirmation_unavailable")
            self._require_time(deadline)
        finally:
            self._authority_lock.release()

        try:
            with self._database.session() as session:
                persisted = self._repository_factory(session).create_or_replay(
                    author_id=normalized_author_id,
                    publication_job_id=target_a.publication_job_id,
                    profile_fingerprint=profile_fingerprint,
                    publication_fingerprint=target_a.publication_fingerprint,
                    selector_fingerprint=target_a.selector_fingerprint,
                    item_fingerprint=lookup.item_fingerprint,
                    observation_fingerprint=recomputed_fingerprint,
                    observed_at=observed_at,
                    confirmed_at=confirmed_at,
                )
                if not isinstance(persisted, PlaybackEvidenceResult):
                    raise PlaybackEvidenceConfirmationError("playback_evidence_confirmation_unavailable")
        except PlaybackEvidenceConflictError:
            raise PlaybackEvidenceConfirmationError("playback_evidence_identity_conflict") from None
        except PlaybackEvidenceConfirmationError:
            raise
        except Exception:
            raise PlaybackEvidenceConfirmationError("playback_evidence_store_unavailable") from None

        result = PlaybackEvidenceConfirmation(
            id=persisted.id,
            author_id=persisted.author_id,
            observed_at=persisted.observed_at,
            confirmed_at=persisted.confirmed_at,
            replayed=persisted.replayed,
            schema_version=persisted.schema_version,
        )
        self._emit(PlaybackEvidenceAuditCode.REPLAYED if result.replayed else PlaybackEvidenceAuditCode.CREATED)
        return result

    def _profile_fingerprint(self) -> str:
        try:
            value = self._observation.profile_fingerprint
        except MediaServerError:
            raise
        except Exception:
            raise PlaybackEvidenceConfirmationError("playback_evidence_not_confirmable") from None
        if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
            raise PlaybackEvidenceConfirmationError("playback_evidence_not_confirmable")
        return value

    def _acquire_authority(self, deadline: float) -> None:
        remaining = deadline - self._time()
        if remaining <= 0 or not self._authority_lock.acquire(timeout=remaining):
            raise MediaServerError("media_server_timeout", retryable=True)

    def _require_time(self, deadline: float) -> None:
        if self._time() >= deadline:
            raise MediaServerError("media_server_timeout", retryable=True)

    def _deadline(self) -> float:
        started = self._time()
        deadline = started + self._timeout_seconds
        if not math.isfinite(deadline):
            raise PlaybackEvidenceConfirmationError("playback_evidence_confirmation_unavailable")
        return deadline

    def _time(self) -> float:
        try:
            value = self._monotonic()
        except (TypeError, ValueError, OverflowError):
            raise PlaybackEvidenceConfirmationError("playback_evidence_confirmation_unavailable") from None
        if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
            raise PlaybackEvidenceConfirmationError("playback_evidence_confirmation_unavailable")
        return float(value)

    def _now(self) -> datetime:
        try:
            value = self._clock()
        except (TypeError, ValueError, OverflowError):
            raise PlaybackEvidenceConfirmationError("playback_evidence_confirmation_unavailable") from None
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise PlaybackEvidenceConfirmationError("playback_evidence_confirmation_unavailable")
        return value.astimezone(UTC)

    @staticmethod
    def _observed_at(value: object) -> datetime:
        if not isinstance(value, str):
            raise PlaybackEvidenceConfirmationError("playback_evidence_not_confirmable")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise PlaybackEvidenceConfirmationError("playback_evidence_not_confirmable") from None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise PlaybackEvidenceConfirmationError("playback_evidence_not_confirmable")
        return parsed.astimezone(UTC)

    @staticmethod
    def _default_audit_sink(code: PlaybackEvidenceAuditCode) -> None:
        _LOGGER.info("%s", code.value)

    def _emit(self, code: PlaybackEvidenceAuditCode) -> None:
        try:
            self._audit_sink(code)
        except Exception:  # pragma: no cover - logging must not change durable truth
            _LOGGER.error("playback_evidence_audit_sink_failed")


__all__ = [
    "PlaybackEvidenceAuditCode",
    "PlaybackEvidenceConfirmation",
    "PlaybackEvidenceConfirmationError",
    "PlaybackEvidenceDatabasePort",
    "PlaybackEvidenceObservationPort",
    "PlaybackEvidenceService",
]
