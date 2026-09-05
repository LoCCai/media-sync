"""Current authority, unknown history and transaction ordering for evidence reads."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import cast

import pytest
from sqlalchemy.orm import Session
from test_playback_evidence_service import (
    AUTHOR_ID,
    CONFIRMED_AT,
    PROFILE_FINGERPRINT,
    _lookup,
    _not_found,
    _Observation,
    _observation_fingerprint,
    _persisted,
    _target,
)

from media_sync.application.playback_evidence_query import PlaybackEvidenceQueryError, PlaybackEvidenceQueryService
from media_sync.infrastructure.db import PlaybackEvidenceResult
from media_sync.ports.media_server import MediaServerError


class _ReadRepository:
    def __init__(self, events: list[str], candidate: PlaybackEvidenceResult | None) -> None:
        self.events = events
        self.candidate = candidate
        self.history = (replace(_persisted(), id="dddddddd-dddd-4ddd-8ddd-dddddddddddd"),)
        self.query: tuple[str, int, str | None] | None = None

    def by_observation(self, _fingerprint: str) -> PlaybackEvidenceResult | None:
        self.events.append("exact")
        return self.candidate

    def history_by_author(
        self, author_id: str, *, limit: int, exclude_id: str | None
    ) -> tuple[PlaybackEvidenceResult, ...]:
        self.events.append("history")
        self.query = author_id, limit, exclude_id
        return self.history


class _ReadDatabase:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.service: PlaybackEvidenceQueryService | None = None

    @contextmanager
    def session(self) -> Iterator[Session]:
        assert self.service is not None
        assert not self.service._authority_lock.locked()
        self.events.append("db_enter")
        yield cast(Session, object())
        self.events.append("db_exit")


def _query(
    observation: _Observation | None,
    events: list[str],
    candidate: PlaybackEvidenceResult | None,
) -> tuple[PlaybackEvidenceQueryService, _ReadRepository]:
    repository = _ReadRepository(events, candidate)
    database = _ReadDatabase(events)
    service = PlaybackEvidenceQueryService(
        database,
        observation,
        monotonic=lambda: 10.0,
        clock=lambda: CONFIRMED_AT,
        repository_factory=lambda _session: repository,  # type: ignore[arg-type,return-value]
    )
    database.service = service
    return service, repository


def test_current_authority_finishes_before_read_transaction_and_safe_projection() -> None:
    events: list[str] = []
    observation = _Observation(events)
    service, repository = _query(observation, events, _persisted())
    result = service.snapshot(AUTHOR_ID, limit=1)

    assert result.human_status == "PASS"
    assert result.current is not None and result.current.id == _persisted().id
    assert result.history[0].state == "stale"
    assert events == ["resolve", "profile", "lookup", "resolve", "profile", "db_enter", "exact", "history", "db_exit"]
    assert repository.query == (AUTHOR_ID, 1, _persisted().id)
    assert observation.deadlines == [130.0, 130.0, 130.0]
    payload = result.as_dict()
    assert set(payload) == {
        "schema_version",
        "scope",
        "author_id",
        "checked_at",
        "current_state",
        "human_status",
        "current",
        "history",
        "history_truncated",
        "limit",
    }
    assert set(payload["current"]) == {"schema_version", "id", "author_id", "observed_at", "confirmed_at", "state"}
    serialized = json.dumps(payload)
    for forbidden in ("fingerprint", "publication_job", "provider", "path", "private-", PROFILE_FINGERPRINT):
        assert forbidden not in serialized


@pytest.mark.parametrize("candidate", [None, _persisted()])
def test_complete_absence_makes_history_stale_without_reading_current_candidate(
    candidate: PlaybackEvidenceResult | None,
) -> None:
    events: list[str] = []
    service, _repository = _query(_Observation(events, lookup=_not_found()), events, candidate)
    result = service.snapshot(AUTHOR_ID)
    assert result.current_state == "not_found"
    assert result.current is None and result.human_status == "NOT_RUN"
    assert all(row.state == "stale" for row in result.history)
    assert "exact" not in events


def test_matched_without_durable_attestation_does_not_promote_playback() -> None:
    events: list[str] = []
    service, _repository = _query(_Observation(events), events, None)
    result = service.snapshot(AUTHOR_ID)
    assert result.current_state == "matched"
    assert result.human_status == "NOT_RUN" and result.current is None


@pytest.mark.parametrize(
    "failure", ["timeout", "ambiguous", "incomplete", "publication", "profile", "forged", "unconfigured"]
)
def test_uncertain_authority_preserves_unknown_history_and_never_passes(failure: str) -> None:
    events: list[str] = []
    observation: _Observation | None = _Observation(events)
    if failure == "timeout":
        observation.lookup = MediaServerError("media_server_timeout", retryable=True)
    elif failure == "ambiguous":
        observation.lookup = MediaServerError("media_server_item_lookup_ambiguous")
    elif failure == "incomplete":
        # Corrupt adapter response bypasses DTO construction, proving the consumer fence.
        lookup = _lookup()
        object.__setattr__(lookup, "complete", False)
        observation.lookup = lookup
    elif failure == "publication":
        observation.targets[-1] = replace(_target(), publication_fingerprint="f" * 64)
    elif failure == "profile":

        class DriftingProfile(_Observation):
            @property
            def profile_fingerprint(self) -> str:
                self.events.append("profile")
                return PROFILE_FINGERPRINT if self.events.count("profile") == 1 else "f" * 64

        observation = DriftingProfile(events)
    elif failure == "forged":
        observation.lookup = _lookup(observation_fingerprint="f" * 64)
    else:
        observation = None
    service, _repository = _query(observation, events, _persisted())
    result = service.snapshot(AUTHOR_ID)
    assert result.current_state == "unavailable"
    assert result.current is None and result.human_status == "NOT_RUN"
    assert all(row.state == "unknown" for row in result.history)
    assert "exact" not in events


@pytest.mark.parametrize(
    "field",
    [
        "author_id",
        "publication_job_id",
        "profile_fingerprint",
        "publication_fingerprint",
        "selector_fingerprint",
        "item_fingerprint",
    ],
)
def test_current_candidate_requires_every_immutable_context_field(field: str) -> None:
    events: list[str] = []
    candidate = replace(_persisted(), **{field: "f" * 64})
    service, repository = _query(_Observation(events), events, candidate)
    result = service.snapshot(AUTHOR_ID)
    assert result.current_state == "unavailable"
    assert result.human_status == "NOT_RUN" and result.current is None
    assert result.history[0].state == "unknown"
    assert repository.query == (AUTHOR_ID, 20, None)


@pytest.mark.parametrize(
    "author_id,limit",
    [
        ("private-input", 20),
        (AUTHOR_ID.upper(), 20),
        (AUTHOR_ID, 0),
        (AUTHOR_ID, 51),
        (AUTHOR_ID, True),
        (AUTHOR_ID, 1.1),
    ],
)
def test_invalid_read_parameters_fail_before_external_or_database_work(author_id: str, limit: int) -> None:
    events: list[str] = []
    service, _repository = _query(_Observation(events), events, _persisted())
    with pytest.raises(PlaybackEvidenceQueryError, match=r"^playback_evidence_request_invalid$"):
        service.snapshot(author_id, limit=limit)
    assert events == []


def test_expired_deadline_and_storage_failure_are_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    service, repository = _query(_Observation(events), events, _persisted())
    ticks = iter([10.0, 130.0])
    service._monotonic = lambda: next(ticks)
    result = service.snapshot(AUTHOR_ID)
    assert result.current_state == "unavailable" and result.human_status == "NOT_RUN"
    assert events == ["db_enter", "history", "db_exit"]

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("private-storage-sentinel")

    monkeypatch.setattr(repository, "history_by_author", broken)
    with pytest.raises(PlaybackEvidenceQueryError, match=r"^playback_evidence_store_unavailable$"):
        service.snapshot(AUTHOR_ID)


def test_changed_remote_item_is_known_stale_only_after_complete_matching_identity() -> None:
    events: list[str] = []
    new_item = "f" * 64
    observation = _Observation(
        events,
        lookup=replace(
            _lookup(),
            item_fingerprint=new_item,
            observation_fingerprint=_observation_fingerprint(item_fingerprint=new_item),
        ),
    )
    service, _repository = _query(observation, events, None)
    result = service.snapshot(AUTHOR_ID)
    assert result.current_state == "matched"
    assert result.current is None and result.human_status == "NOT_RUN"
    assert all(row.state == "stale" for row in result.history)
    assert events.count("lookup") == 1 and events.count("resolve") == 2


def test_deadline_expiring_inside_lookup_never_reaches_a_current_read() -> None:
    events: list[str] = []
    service, _repository = _query(_Observation(events), events, _persisted())
    service._monotonic = lambda: 130.0 if "lookup" in events else 10.0
    result = service.snapshot(AUTHOR_ID)
    assert result.current_state == "unavailable"
    assert result.history[0].state == "unknown"
    assert events.count("resolve") == 1 and "exact" not in events


def test_contending_authority_lock_is_bounded_and_unknown() -> None:
    events: list[str] = []
    service, repository = _query(_Observation(events), events, _persisted())
    # Hold the authority lock from a concurrent owner. Database uses a separate
    # scope because it must remain readable even when authority is unavailable.
    service._timeout_seconds = 0.001
    with service._authority_lock:
        assert service._current_authority(AUTHOR_ID) is None
    assert events == [] and repository.query is None


@pytest.mark.parametrize("timeout", [0, 121, True, float("nan"), float("inf")])
def test_authority_timeout_configuration_is_bounded(timeout: float) -> None:
    with pytest.raises(ValueError):
        PlaybackEvidenceQueryService(_ReadDatabase([]), None, timeout_seconds=timeout)
