"""TOCTOU and zero-write contracts for playback-evidence confirmation."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy.orm import Session

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
from media_sync.infrastructure.db import PlaybackEvidenceConflictError, PlaybackEvidenceResult
from media_sync.ports.media_server import MediaServerError

AUTHOR_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
JOB_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
EVIDENCE_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
PROFILE_FINGERPRINT = "1" * 64
PUBLICATION_FINGERPRINT = "2" * 64
SELECTOR_FINGERPRINT = "3" * 64
ITEM_FINGERPRINT = "4" * 64
OBSERVED_AT = datetime(2026, 9, 5, 8, tzinfo=UTC)
CONFIRMED_AT = OBSERVED_AT + timedelta(minutes=1)


def _target(**overrides: object) -> MediaServerPublicationTarget:
    values: dict[str, object] = {
        "provider_key": "media-sync-bili-creator",
        "provider_value": "private-provider-value",
        "server_path": "/srv/private-library/bili-author",
        "author_id": AUTHOR_ID,
        "publication_job_id": JOB_ID,
        "platform": "bili",
        "author_relative_directory": "bili-author",
        "server_path_style": "posix",
        "publication_fingerprint": PUBLICATION_FINGERPRINT,
        "selector_fingerprint": SELECTOR_FINGERPRINT,
        "managed_file_count": 3,
    }
    values.update(overrides)
    return MediaServerPublicationTarget(**values)  # type: ignore[arg-type]


def _observation_fingerprint(
    *,
    author_id: str = AUTHOR_ID,
    profile_fingerprint: str = PROFILE_FINGERPRINT,
    publication_fingerprint: str = PUBLICATION_FINGERPRINT,
    selector_fingerprint: str = SELECTOR_FINGERPRINT,
    item_fingerprint: str = ITEM_FINGERPRINT,
) -> str:
    return media_server_observation_fingerprint(
        author_id=author_id,
        profile_fingerprint=profile_fingerprint,
        publication_fingerprint=publication_fingerprint,
        selector_fingerprint=selector_fingerprint,
        item_fingerprint=item_fingerprint,
    )


def _lookup(
    *,
    target: MediaServerPublicationTarget | None = None,
    observation_fingerprint: str | None = None,
    observed_at: datetime = OBSERVED_AT,
) -> MediaServerAuthorLookupResult:
    selected = target or _target()
    return MediaServerAuthorLookupResult(
        schema_version=1,
        author_id=selected.author_id,
        provider="emby",
        library_id_digest="5" * 64,
        publication_fingerprint=selected.publication_fingerprint,
        selector_fingerprint=selected.selector_fingerprint,
        lookup_state="matched",
        match_count=1,
        item_fingerprint=ITEM_FINGERPRINT,
        observation_fingerprint=observation_fingerprint or _observation_fingerprint(),
        observed_at=observed_at.isoformat(),
        complete=True,
    )


def _not_found(target: MediaServerPublicationTarget | None = None) -> MediaServerAuthorLookupResult:
    selected = target or _target()
    return MediaServerAuthorLookupResult(
        schema_version=1,
        author_id=selected.author_id,
        provider="emby",
        library_id_digest="5" * 64,
        publication_fingerprint=selected.publication_fingerprint,
        selector_fingerprint=selected.selector_fingerprint,
        lookup_state="not_found",
        match_count=0,
        observed_at=OBSERVED_AT.isoformat(),
        complete=True,
    )


class _Observation:
    def __init__(
        self,
        events: list[str],
        *,
        targets: tuple[MediaServerPublicationTarget, ...] | None = None,
        lookup: MediaServerAuthorLookupResult | Exception | None = None,
        profile_fingerprint: str = PROFILE_FINGERPRINT,
    ) -> None:
        self.events = events
        self.targets = list(targets or (_target(), _target()))
        self.lookup = lookup or _lookup()
        self._profile_fingerprint = profile_fingerprint
        self.deadlines: list[float | None] = []

    @property
    def profile_fingerprint(self) -> str:
        self.events.append("profile")
        return self._profile_fingerprint

    def resolve_target(
        self,
        author_id: str,
        *,
        deadline: float | None = None,
    ) -> MediaServerPublicationTarget:
        assert author_id == AUTHOR_ID
        self.events.append("resolve")
        self.deadlines.append(deadline)
        return self.targets.pop(0)

    def lookup_author(
        self,
        target_or_author_id: MediaServerPublicationTarget,
        *,
        deadline: float | None = None,
    ) -> MediaServerAuthorLookupResult:
        assert target_or_author_id == _target()
        self.events.append("lookup")
        self.deadlines.append(deadline)
        if isinstance(self.lookup, Exception):
            raise self.lookup
        return self.lookup


class _Database:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    @contextmanager
    def session(self) -> Iterator[Session]:
        self.events.append("db_enter")
        try:
            yield cast(Session, object())
        finally:
            self.events.append("db_exit")


class _Repository:
    def __init__(
        self,
        events: list[str],
        result: PlaybackEvidenceResult | Exception,
        captured: dict[str, object],
    ) -> None:
        self.events = events
        self.result = result
        self.captured = captured

    def create_or_replay(self, **kwargs: object) -> PlaybackEvidenceResult:
        self.events.append("repository")
        self.captured.update(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _BlockingObservation(_Observation):
    """Hold the first lookup so a second confirmation contends for authority."""

    def __init__(self, events: list[str]) -> None:
        target = _target()
        super().__init__(events, targets=(target, target, target, target))
        self.first_lookup_entered = threading.Event()
        self.release_first_lookup = threading.Event()
        self._counts_lock = threading.Lock()
        self._resolve_count = 0
        self._lookup_count = 0

    @property
    def authority_counts(self) -> tuple[int, int]:
        with self._counts_lock:
            return self._resolve_count, self._lookup_count

    def resolve_target(
        self,
        author_id: str,
        *,
        deadline: float | None = None,
    ) -> MediaServerPublicationTarget:
        with self._counts_lock:
            self._resolve_count += 1
        return super().resolve_target(author_id, deadline=deadline)

    def lookup_author(
        self,
        target_or_author_id: MediaServerPublicationTarget,
        *,
        deadline: float | None = None,
    ) -> MediaServerAuthorLookupResult:
        result = super().lookup_author(target_or_author_id, deadline=deadline)
        with self._counts_lock:
            self._lookup_count += 1
            lookup_count = self._lookup_count
        if lookup_count == 1:
            self.first_lookup_entered.set()
            assert self.release_first_lookup.wait(5)
        return result


class _ObservedAuthorityLock:
    """Wrap a real lock and expose deterministic contender arrival to the test."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.contender_waiting = threading.Event()
        self.timeouts: list[float] = []

    def acquire(self, *, timeout: float) -> bool:
        self.timeouts.append(timeout)
        if self._lock.locked():
            self.contender_waiting.set()
        return self._lock.acquire(timeout=timeout)

    def release(self) -> None:
        self._lock.release()


def _persisted(
    *,
    replayed: bool = False,
    observed_at: datetime = OBSERVED_AT,
    confirmed_at: datetime = CONFIRMED_AT,
) -> PlaybackEvidenceResult:
    return PlaybackEvidenceResult(
        id=EVIDENCE_ID,
        schema_version=1,
        author_id=AUTHOR_ID,
        publication_job_id=JOB_ID,
        profile_fingerprint=PROFILE_FINGERPRINT,
        publication_fingerprint=PUBLICATION_FINGERPRINT,
        selector_fingerprint=SELECTOR_FINGERPRINT,
        item_fingerprint=ITEM_FINGERPRINT,
        observation_fingerprint=_observation_fingerprint(),
        observed_at=observed_at,
        confirmed_at=confirmed_at,
        replayed=replayed,
    )


def _service(
    observation: _Observation,
    events: list[str],
    *,
    result: PlaybackEvidenceResult | Exception | None = None,
    clock: Callable[[], datetime] = lambda: CONFIRMED_AT,
    monotonic: Callable[[], float] = lambda: 10.0,
    audit_sink: Callable[[PlaybackEvidenceAuditCode], None] | None = None,
) -> tuple[PlaybackEvidenceService, dict[str, object]]:
    captured: dict[str, object] = {}

    def repository_factory(_session: Session) -> _Repository:
        return _Repository(events, result or _persisted(), captured)

    service = PlaybackEvidenceService(
        _Database(events),
        observation,
        clock=clock,
        monotonic=monotonic,
        audit_sink=audit_sink,
        repository_factory=repository_factory,  # type: ignore[arg-type]
    )
    return service, captured


def test_confirm_revalidates_before_the_short_insert_transaction() -> None:
    events: list[str] = []
    audits: list[PlaybackEvidenceAuditCode] = []
    observation = _Observation(events)
    service, captured = _service(observation, events, audit_sink=audits.append)

    result = service.confirm(AUTHOR_ID, _observation_fingerprint())

    assert events == ["resolve", "lookup", "resolve", "profile", "db_enter", "repository", "db_exit"]
    assert observation.deadlines == [130.0, 130.0, 130.0]
    assert captured == {
        "author_id": AUTHOR_ID,
        "publication_job_id": JOB_ID,
        "profile_fingerprint": PROFILE_FINGERPRINT,
        "publication_fingerprint": PUBLICATION_FINGERPRINT,
        "selector_fingerprint": SELECTOR_FINGERPRINT,
        "item_fingerprint": ITEM_FINGERPRINT,
        "observation_fingerprint": _observation_fingerprint(),
        "observed_at": OBSERVED_AT,
        "confirmed_at": CONFIRMED_AT,
    }
    assert result.as_dict() == {
        "schema_version": 1,
        "id": EVIDENCE_ID,
        "author_id": AUTHOR_ID,
        "observed_at": OBSERVED_AT.isoformat(),
        "confirmed_at": CONFIRMED_AT.isoformat(),
        "replayed": False,
    }
    assert audits == [PlaybackEvidenceAuditCode.CREATED]
    assert "fingerprint" not in repr(result)


def test_replay_returns_the_first_persisted_timestamps_and_fixed_audit_code() -> None:
    events: list[str] = []
    audits: list[PlaybackEvidenceAuditCode] = []
    first_observed = OBSERVED_AT - timedelta(hours=1)
    first_confirmed = OBSERVED_AT - timedelta(minutes=30)
    service, captured = _service(
        _Observation(events),
        events,
        result=_persisted(replayed=True, observed_at=first_observed, confirmed_at=first_confirmed),
        audit_sink=audits.append,
    )

    result = service.confirm(AUTHOR_ID, _observation_fingerprint())

    assert captured["observed_at"] == OBSERVED_AT
    assert captured["confirmed_at"] == CONFIRMED_AT
    assert result.observed_at == first_observed
    assert result.confirmed_at == first_confirmed
    assert result.replayed is True
    assert audits == [PlaybackEvidenceAuditCode.REPLAYED]


def test_bounded_authority_lock_serializes_concurrent_confirmation_before_create_and_replay() -> None:
    events: list[str] = []
    audits: list[PlaybackEvidenceAuditCode] = []
    observation = _BlockingObservation(events)
    authority_lock = _ObservedAuthorityLock()
    repository_lock = threading.Lock()
    repository_calls = 0

    def repository_factory(_session: Session) -> _Repository:
        nonlocal repository_calls
        with repository_lock:
            replayed = repository_calls > 0
            repository_calls += 1
        return _Repository(events, _persisted(replayed=replayed), {})

    service = PlaybackEvidenceService(
        _Database(events),
        observation,
        monotonic=lambda: 10.0,
        clock=lambda: CONFIRMED_AT,
        audit_sink=audits.append,
        repository_factory=repository_factory,  # type: ignore[arg-type]
    )
    service._authority_lock = authority_lock  # type: ignore[assignment]

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service.confirm, AUTHOR_ID, _observation_fingerprint())
        assert observation.first_lookup_entered.wait(5)
        second = executor.submit(service.confirm, AUTHOR_ID, _observation_fingerprint())
        assert authority_lock.contender_waiting.wait(5)

        assert observation.authority_counts == (1, 1)
        assert events == ["resolve", "lookup"]
        assert second.done() is False

        observation.release_first_lookup.set()
        results = (first.result(timeout=5), second.result(timeout=5))

    assert observation.authority_counts == (4, 2)
    assert repository_calls == 2
    assert sorted(result.replayed for result in results) == [False, True]
    assert {result.id for result in results} == {EVIDENCE_ID}
    assert {result.observed_at for result in results} == {OBSERVED_AT}
    assert {result.confirmed_at for result in results} == {CONFIRMED_AT}
    assert authority_lock.timeouts == [120.0, 120.0]
    assert sorted(audit.value for audit in audits) == [
        "playback_evidence_created",
        "playback_evidence_replayed",
    ]


@pytest.mark.parametrize(
    ("author_id", "fingerprint"),
    [
        ("private-author-sentinel", _observation_fingerprint()),
        (AUTHOR_ID.upper(), _observation_fingerprint()),
        (AUTHOR_ID, "private-fingerprint-sentinel"),
        (AUTHOR_ID, "A" * 64),
    ],
)
def test_invalid_request_fails_before_authority_or_storage(author_id: str, fingerprint: str) -> None:
    events: list[str] = []
    service, _ = _service(_Observation(events), events)

    with pytest.raises(PlaybackEvidenceConfirmationError) as rejected:
        service.confirm(author_id, fingerprint)

    assert rejected.value.code == "playback_evidence_request_invalid"
    assert str(rejected.value) == "playback_evidence_request_invalid"
    assert events == []


def test_not_found_is_complete_but_has_no_attestation_authority_or_write() -> None:
    events: list[str] = []
    service, _ = _service(_Observation(events, lookup=_not_found()), events)

    with pytest.raises(PlaybackEvidenceConfirmationError) as rejected:
        service.confirm(AUTHOR_ID, _observation_fingerprint())

    assert rejected.value.code == "playback_evidence_not_confirmable"
    assert events == ["resolve", "lookup", "resolve"]


def test_publication_drift_after_lookup_fails_before_profile_or_storage() -> None:
    events: list[str] = []
    changed = _target(publication_fingerprint="6" * 64)
    service, _ = _service(_Observation(events, targets=(_target(), changed)), events)

    with pytest.raises(MediaServerError) as rejected:
        service.confirm(AUTHOR_ID, _observation_fingerprint())

    assert rejected.value.code == "media_server_publication_changed"
    assert events == ["resolve", "lookup", "resolve"]


@pytest.mark.parametrize(
    ("lookup", "profile_fingerprint", "code"),
    [
        (_lookup(observation_fingerprint="7" * 64), PROFILE_FINGERPRINT, "playback_evidence_not_confirmable"),
        (_lookup(), "8" * 64, "playback_evidence_not_confirmable"),
        (
            _lookup(target=_target(selector_fingerprint="9" * 64)),
            PROFILE_FINGERPRINT,
            "playback_evidence_not_confirmable",
        ),
    ],
)
def test_authority_context_mismatch_never_opens_storage(
    lookup: MediaServerAuthorLookupResult,
    profile_fingerprint: str,
    code: str,
) -> None:
    events: list[str] = []
    service, _ = _service(
        _Observation(events, lookup=lookup, profile_fingerprint=profile_fingerprint),
        events,
    )

    with pytest.raises(PlaybackEvidenceConfirmationError) as rejected:
        service.confirm(AUTHOR_ID, _observation_fingerprint())

    assert rejected.value.code == code
    assert "db_enter" not in events


def test_forged_or_stale_fingerprint_uses_one_fixed_mismatch_and_writes_nothing() -> None:
    events: list[str] = []
    service, _ = _service(_Observation(events), events)

    with pytest.raises(PlaybackEvidenceConfirmationError) as rejected:
        service.confirm(AUTHOR_ID, "f" * 64)

    assert rejected.value.code == "playback_evidence_not_confirmable"
    assert "f" * 64 not in str(rejected.value)
    assert "db_enter" not in events


def test_lookup_failure_propagates_fixed_media_error_without_second_resolve_or_write() -> None:
    events: list[str] = []
    service, _ = _service(
        _Observation(events, lookup=MediaServerError("media_server_item_lookup_ambiguous")),
        events,
    )

    with pytest.raises(MediaServerError) as rejected:
        service.confirm(AUTHOR_ID, _observation_fingerprint())

    assert rejected.value.code == "media_server_item_lookup_ambiguous"
    assert events == ["resolve", "lookup"]


def test_deadline_and_future_wall_clock_fail_before_storage() -> None:
    events: list[str] = []
    times = iter((0.0, 121.0))
    service, _ = _service(_Observation(events), events, monotonic=lambda: next(times))

    with pytest.raises(MediaServerError) as timeout:
        service.confirm(AUTHOR_ID, _observation_fingerprint())
    assert timeout.value.code == "media_server_timeout"
    assert "db_enter" not in events

    events.clear()
    future_lookup = _lookup(observed_at=CONFIRMED_AT + timedelta(seconds=1))
    service, _ = _service(_Observation(events, lookup=future_lookup), events)
    with pytest.raises(PlaybackEvidenceConfirmationError) as clock_failure:
        service.confirm(AUTHOR_ID, _observation_fingerprint())
    assert clock_failure.value.code == "playback_evidence_confirmation_unavailable"
    assert "db_enter" not in events


def test_repository_identity_conflict_maps_to_fixed_code_without_reflection_or_success_audit() -> None:
    events: list[str] = []
    audits: list[PlaybackEvidenceAuditCode] = []
    private_evidence_id = "private-evidence-id-sentinel"
    service, _ = _service(
        _Observation(events),
        events,
        result=PlaybackEvidenceConflictError(private_evidence_id),
        audit_sink=audits.append,
    )

    with pytest.raises(PlaybackEvidenceConfirmationError) as rejected:
        service.confirm(AUTHOR_ID, _observation_fingerprint())

    assert rejected.value.code == "playback_evidence_identity_conflict"
    rendered = f"{rejected.value!s} {rejected.value!r}"
    assert private_evidence_id not in rendered
    assert events[-3:] == ["db_enter", "repository", "db_exit"]
    assert audits == []


def test_arbitrary_repository_failure_maps_to_store_unavailable_without_reflection_or_success_audit() -> None:
    events: list[str] = []
    audits: list[PlaybackEvidenceAuditCode] = []
    failure = RuntimeError("private-storage-sentinel")
    service, _ = _service(
        _Observation(events),
        events,
        result=failure,
        audit_sink=audits.append,
    )

    with pytest.raises(PlaybackEvidenceConfirmationError) as rejected:
        service.confirm(AUTHOR_ID, _observation_fingerprint())

    assert rejected.value.code == "playback_evidence_store_unavailable"
    rendered = f"{rejected.value!s} {rejected.value!r}"
    assert "private-storage-sentinel" not in rendered
    assert events[-3:] == ["db_enter", "repository", "db_exit"]
    assert audits == []


def test_audit_sink_failure_does_not_change_committed_result(caplog: pytest.LogCaptureFixture) -> None:
    events: list[str] = []

    def failed_audit(_code: PlaybackEvidenceAuditCode) -> None:
        raise RuntimeError("private-audit-sentinel")

    service, _ = _service(_Observation(events), events, audit_sink=failed_audit)

    result = service.confirm(AUTHOR_ID, _observation_fingerprint())

    assert result.id == EVIDENCE_ID
    assert "playback_evidence_audit_sink_failed" in caplog.text
    assert "private-audit-sentinel" not in caplog.text
