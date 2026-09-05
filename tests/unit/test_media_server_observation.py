from __future__ import annotations

import hashlib
import inspect
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from media_sync.application.media_server_observation import (
    MediaServerObservationLimits,
    MediaServerObservationService,
    media_server_item_fingerprint,
    media_server_observation_fingerprint,
)
from media_sync.application.media_server_publication import MediaServerPublicationTarget
from media_sync.application.operation_payloads import operation_request_fingerprint
from media_sync.application.operations import OperationCoordinator, OperationExecution, OperationOutcome
from media_sync.config import MediaServerSafeSummary
from media_sync.infrastructure.db import Database
from media_sync.ports.media_server import MediaServerError, MediaServerItemLookupResult, MediaServerScanResult

AUTHOR_ID = "00000000-0000-0000-0000-000000000001"
PUBLICATION_JOB_ID = "00000000-0000-0000-0000-000000000002"
PROFILE_FINGERPRINT = "a" * 64
LIBRARY_ID_DIGEST = "b" * 64
PUBLICATION_FINGERPRINT = "c" * 64
SELECTOR_FINGERPRINT = "d" * 64
SET_FINGERPRINT = "e" * 64
RAW_ITEM_ID = "private-remote-item-id-sentinel"


def _target(*, publication_fingerprint: str = PUBLICATION_FINGERPRINT) -> MediaServerPublicationTarget:
    return MediaServerPublicationTarget(
        author_id=AUTHOR_ID,
        publication_job_id=PUBLICATION_JOB_ID,
        platform="xhs",
        provider_key="media-sync-xhs-creator",
        provider_value="private-provider-value-sentinel",
        author_relative_directory="xhs-creator-author",
        server_path="/srv/media/xhs-creator-author",
        server_path_style="posix",
        publication_fingerprint=publication_fingerprint,
        selector_fingerprint=SELECTOR_FINGERPRINT,
        managed_file_count=3,
    )


def _lookup(
    state: str,
    *,
    item_id: str = RAW_ITEM_ID,
    set_fingerprint: str = SET_FINGERPRINT,
    items: int = 0,
    pages: int = 1,
    response_bytes: int = 2,
) -> MediaServerItemLookupResult:
    return MediaServerItemLookupResult(
        lookup_state=state,  # type: ignore[arg-type]
        inspected_item_count=items,
        page_count=pages,
        response_byte_count=response_bytes,
        item_id_set_fingerprint=set_fingerprint,
        item_id=item_id if state == "matched" else None,
    )


class _Resolver:
    def __init__(self, *targets: MediaServerPublicationTarget | MediaServerError) -> None:
        self.targets = list(targets) or [_target()]
        self.calls: list[str] = []
        self.deadlines: list[float | None] = []

    def resolve(
        self,
        author_id: str,
        *,
        deadline: float | None = None,
    ) -> MediaServerPublicationTarget:
        self.calls.append(author_id)
        self.deadlines.append(deadline)
        value = self.targets[min(len(self.calls) - 1, len(self.targets) - 1)]
        if isinstance(value, MediaServerError):
            raise value
        return value


class _TimelineEvent:
    def __init__(self) -> None:
        self.now = 0.0
        self.set_value = False
        self.waits: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def clock(self) -> datetime:
        return datetime(2026, 9, 5, tzinfo=UTC) + timedelta(seconds=self.now)

    def is_set(self) -> bool:
        return self.set_value

    def set(self) -> None:
        self.set_value = True

    def wait(self, timeout: float | None = None) -> bool:
        assert timeout is not None
        self.waits.append(timeout)
        if not self.set_value:
            self.now += timeout
        return self.set_value


@dataclass(frozen=True)
class _Snapshot:
    cancel_requested_at: datetime | None = None


class _Context:
    def __init__(self, event: _TimelineEvent) -> None:
        self.cancellation = event
        self.phases: list[str] = []
        self.checkpoints: list[tuple[str, dict[str, object]]] = []
        self.progresses: list[tuple[str, int, int | None, str]] = []
        self.cancel_on_phase: str | None = None
        self.cancel_after_checkpoint: str | None = None
        self.on_phase: Callable[[str], None] | None = None

    @property
    def cancel_requested(self) -> bool:
        return self.cancellation.is_set()

    def phase(self, phase: str) -> _Snapshot:
        self.phases.append(phase)
        if self.on_phase is not None:
            self.on_phase(phase)
        if phase == self.cancel_on_phase:
            self.cancellation.set()
            return _Snapshot(datetime(2026, 9, 5, tzinfo=UTC))
        return _Snapshot()

    def checkpoint(self, *, phase: str, result_summary: Mapping[str, object]) -> _Snapshot:
        self.checkpoints.append((phase, dict(result_summary)))
        if phase == self.cancel_after_checkpoint:
            self.cancellation.set()
            return _Snapshot(datetime(2026, 9, 5, tzinfo=UTC))
        return _Snapshot()

    def progress(self, *, phase: str, current: int, unit: str, total: int | None = None) -> _Snapshot:
        self.progresses.append((phase, current, total, unit))
        return _Snapshot()


class _Server:
    def __init__(
        self,
        provider: str,
        lookups: list[MediaServerItemLookupResult | MediaServerError],
    ) -> None:
        self.profile_fingerprint = PROFILE_FINGERPRINT
        self.safe_summary = MediaServerSafeSummary(
            configured=True,
            provider=provider,  # type: ignore[arg-type]
            origin="http://127.0.0.1:8096",
            library_id_digest=LIBRARY_ID_DIGEST,
            profile_fingerprint=PROFILE_FINGERPRINT,
            verify_tls=False,
            timeout_seconds=10.0,
            operations_enabled=True,
            allowed_network_count=1,
            library_path_configured=True,
            api_key_configured=True,
        )
        self.lookups = lookups
        self.lookup_calls = 0
        self.lookup_deadlines: list[float | None] = []
        self.scan_calls = 0
        self.scan_deadlines: list[float | None] = []
        self.post_count = 0
        self.before_entry_calls = 0
        self.on_lookup: Callable[[int], None] | None = None

    def lookup_item(
        self,
        target: MediaServerPublicationTarget,
        *,
        deadline: float | None = None,
    ) -> MediaServerItemLookupResult:
        assert target.author_id == AUTHOR_ID
        value = self.lookups[self.lookup_calls]
        self.lookup_calls += 1
        self.lookup_deadlines.append(deadline)
        if self.on_lookup is not None:
            self.on_lookup(self.lookup_calls)
        if isinstance(value, MediaServerError):
            raise value
        return value

    def scan_observation(
        self,
        cancel_requested: Callable[[], bool],
        before_transport_entry: Callable[[], bool],
        *,
        deadline: float | None = None,
    ) -> MediaServerScanResult:
        self.scan_calls += 1
        self.scan_deadlines.append(deadline)
        self.before_entry_calls += 1
        if not before_transport_entry() or cancel_requested():
            raise MediaServerError("media_server_scan_cancelled")
        self.post_count += 1
        provider = self.safe_summary.provider
        assert provider is not None
        version = "4.9.5" if provider == "emby" else "10.10.7"
        return MediaServerScanResult(provider, version, LIBRARY_ID_DIGEST)


def _service(
    server: _Server,
    resolver: _Resolver,
    timeline: _TimelineEvent,
    *,
    limits: MediaServerObservationLimits | None = None,
) -> MediaServerObservationService:
    return MediaServerObservationService(
        resolver,
        server,
        limits=limits,
        monotonic=timeline.monotonic,
        clock=timeline.clock,
    )


@pytest.mark.parametrize("state", ["not_found", "matched"])
def test_safe_author_lookup_has_exact_complete_shape_and_no_raw_identity(state: str) -> None:
    timeline = _TimelineEvent()
    server = _Server("emby", [_lookup(state, items=1 if state == "matched" else 0)])
    resolver = _Resolver(_target())
    service = _service(server, resolver, timeline)

    result = service.lookup_author(AUTHOR_ID)
    payload = result.as_dict()
    item_fingerprint = media_server_item_fingerprint(
        profile_fingerprint=PROFILE_FINGERPRINT,
        publication_fingerprint=PUBLICATION_FINGERPRINT,
        selector_fingerprint=SELECTOR_FINGERPRINT,
        item_id=RAW_ITEM_ID,
    )
    observation_fingerprint = media_server_observation_fingerprint(
        author_id=AUTHOR_ID,
        profile_fingerprint=PROFILE_FINGERPRINT,
        publication_fingerprint=PUBLICATION_FINGERPRINT,
        selector_fingerprint=SELECTOR_FINGERPRINT,
        item_fingerprint=item_fingerprint,
    )

    assert payload == {
        "schema_version": 1,
        "author_id": AUTHOR_ID,
        "provider": "emby",
        "library_id_digest": LIBRARY_ID_DIGEST,
        "publication_fingerprint": PUBLICATION_FINGERPRINT,
        "selector_fingerprint": SELECTOR_FINGERPRINT,
        "lookup_state": state,
        "match_count": 1 if state == "matched" else 0,
        **(
            {
                "item_fingerprint": item_fingerprint,
                "observation_fingerprint": observation_fingerprint,
            }
            if state == "matched"
            else {}
        ),
        "observed_at": "2026-09-05T00:00:00+00:00",
        "complete": True,
    }
    assert RAW_ITEM_ID not in repr(result)
    assert RAW_ITEM_ID not in str(payload)
    assert "private-provider-value-sentinel" not in repr(result)
    assert "private-provider-value-sentinel" not in str(payload)
    assert "/srv/media/xhs-creator-author" not in repr(result)
    assert "/srv/media/xhs-creator-author" not in str(payload)
    assert item_fingerprint not in repr(result)
    assert observation_fingerprint not in repr(result)
    assert resolver.deadlines == [None]
    assert server.lookup_deadlines == [None]


def test_item_fingerprint_is_stable_and_binds_every_authority_context() -> None:
    baseline = media_server_item_fingerprint(
        profile_fingerprint=PROFILE_FINGERPRINT,
        publication_fingerprint=PUBLICATION_FINGERPRINT,
        selector_fingerprint=SELECTOR_FINGERPRINT,
        item_id=RAW_ITEM_ID,
    )

    assert baseline == "3d8c43c8a7cb8b65c840a9cf2fce863848d34720e1bc95c1fdfe37c9b74e6bfc"
    for change in (
        {"profile_fingerprint": "f" * 64},
        {"publication_fingerprint": "f" * 64},
        {"selector_fingerprint": "f" * 64},
        {"item_id": "another-item"},
    ):
        values = {
            "profile_fingerprint": PROFILE_FINGERPRINT,
            "publication_fingerprint": PUBLICATION_FINGERPRINT,
            "selector_fingerprint": SELECTOR_FINGERPRINT,
            "item_id": RAW_ITEM_ID,
            **change,
        }
        assert media_server_item_fingerprint(**values) != baseline


def test_observation_fingerprint_has_a_stable_domain_separated_digest_only_contract() -> None:
    item_fingerprint = media_server_item_fingerprint(
        profile_fingerprint=PROFILE_FINGERPRINT,
        publication_fingerprint=PUBLICATION_FINGERPRINT,
        selector_fingerprint=SELECTOR_FINGERPRINT,
        item_id=RAW_ITEM_ID,
    )
    values = {
        "author_id": AUTHOR_ID,
        "profile_fingerprint": PROFILE_FINGERPRINT,
        "publication_fingerprint": PUBLICATION_FINGERPRINT,
        "selector_fingerprint": SELECTOR_FINGERPRINT,
        "item_fingerprint": item_fingerprint,
    }

    baseline = media_server_observation_fingerprint(**values)

    assert baseline == "5712c66b1374d4cb1efde0164b139e5a794ac4f93219d2f70152555eff6a6f7f"
    assert media_server_observation_fingerprint(**values) == baseline
    assert tuple(inspect.signature(media_server_observation_fingerprint).parameters) == (
        "author_id",
        "profile_fingerprint",
        "publication_fingerprint",
        "selector_fingerprint",
        "item_fingerprint",
    )
    other_domain = hashlib.sha256(b"media-sync:media-server-observed-item:v1\0")
    for value in values.values():
        encoded = value.encode("ascii")
        other_domain.update(len(encoded).to_bytes(4, "big"))
        other_domain.update(encoded)
    assert other_domain.hexdigest() != baseline

    raw_capable_arguments = {**values, "provider_value": "private-provider-value-sentinel"}
    with pytest.raises(TypeError) as caught:
        media_server_observation_fingerprint(**raw_capable_arguments)  # type: ignore[arg-type]
    assert "private-provider-value-sentinel" not in str(caught.value)


@pytest.mark.parametrize(
    ("component", "replacement"),
    [
        ("author_id", "00000000-0000-0000-0000-000000000003"),
        ("profile_fingerprint", "f" * 64),
        ("publication_fingerprint", "1" * 64),
        ("selector_fingerprint", "2" * 64),
        ("item_fingerprint", "3" * 64),
    ],
)
def test_observation_fingerprint_binds_every_authority_component(
    component: str,
    replacement: str,
) -> None:
    item_fingerprint = media_server_item_fingerprint(
        profile_fingerprint=PROFILE_FINGERPRINT,
        publication_fingerprint=PUBLICATION_FINGERPRINT,
        selector_fingerprint=SELECTOR_FINGERPRINT,
        item_id=RAW_ITEM_ID,
    )
    values = {
        "author_id": AUTHOR_ID,
        "profile_fingerprint": PROFILE_FINGERPRINT,
        "publication_fingerprint": PUBLICATION_FINGERPRINT,
        "selector_fingerprint": SELECTOR_FINGERPRINT,
        "item_fingerprint": item_fingerprint,
    }
    baseline = media_server_observation_fingerprint(**values)

    assert media_server_observation_fingerprint(**{**values, component: replacement}) != baseline


@pytest.mark.parametrize(
    "author_id",
    [
        "00000000-0000-0000-0000-000000000001 ",
        "{00000000-0000-0000-0000-000000000001}",
        "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",
        "private-author-id-sentinel",
    ],
)
def test_observation_fingerprint_rejects_noncanonical_author_without_reflection(author_id: str) -> None:
    with pytest.raises(ValueError) as caught:
        media_server_observation_fingerprint(
            author_id=author_id,
            profile_fingerprint=PROFILE_FINGERPRINT,
            publication_fingerprint=PUBLICATION_FINGERPRINT,
            selector_fingerprint=SELECTOR_FINGERPRINT,
            item_fingerprint="f" * 64,
        )

    assert str(caught.value) == "observation fingerprint author is invalid"
    assert author_id not in str(caught.value)


@pytest.mark.parametrize(
    "component",
    [
        "profile_fingerprint",
        "publication_fingerprint",
        "selector_fingerprint",
        "item_fingerprint",
    ],
)
def test_observation_fingerprint_rejects_non_digest_context_without_reflection(component: str) -> None:
    values = {
        "author_id": AUTHOR_ID,
        "profile_fingerprint": PROFILE_FINGERPRINT,
        "publication_fingerprint": PUBLICATION_FINGERPRINT,
        "selector_fingerprint": SELECTOR_FINGERPRINT,
        "item_fingerprint": "f" * 64,
    }
    values[component] = "private-raw-context-sentinel"

    with pytest.raises(ValueError) as caught:
        media_server_observation_fingerprint(**values)

    assert str(caught.value) == "observation fingerprint context is invalid"
    assert "private-raw-context-sentinel" not in str(caught.value)


def test_repeated_matched_lookup_keeps_observation_identity_when_timestamp_changes() -> None:
    timeline = _TimelineEvent()
    server = _Server("emby", [_lookup("matched", items=1), _lookup("matched", items=1)])
    service = _service(server, _Resolver(_target()), timeline)

    first = service.lookup_author(AUTHOR_ID)
    timeline.now = 17.0
    second = service.lookup_author(AUTHOR_ID)

    assert first.observed_at != second.observed_at
    assert first.item_fingerprint == second.item_fingerprint
    assert first.observation_fingerprint == second.observation_fingerprint
    assert first.observation_fingerprint is not None


def test_emby_observation_persists_accepted_then_same_item_twice_and_succeeds() -> None:
    target = _target()
    timeline = _TimelineEvent()
    resolver = _Resolver(target, target, target)
    server = _Server("emby", [_lookup("not_found"), _lookup("matched", items=1), _lookup("matched", items=1)])
    context = _Context(timeline)

    outcome = _service(server, resolver, timeline).observe_author(target, context)

    assert outcome.state == "succeeded"
    assert outcome.error_code is None
    assert outcome.payload is not None
    assert outcome.payload["observation_state"] == "observed"
    assert outcome.payload["match_count"] == 1
    assert outcome.payload["verification_count"] == 2
    assert outcome.payload["observed_at"] == "2026-09-05T00:00:04+00:00"
    assert RAW_ITEM_ID not in str(outcome.payload)
    assert server.scan_calls == server.post_count == server.before_entry_calls == 1
    assert server.lookup_calls == 3
    assert resolver.calls == [AUTHOR_ID, AUTHOR_ID, AUTHOR_ID]
    assert resolver.deadlines == [120.0, 120.0, 120.0]
    assert server.lookup_deadlines == [120.0, 120.0, 120.0]
    assert server.scan_deadlines == [120.0]
    assert context.phases == ["baselining", "dispatching"]
    assert [phase for phase, _payload in context.checkpoints] == ["accepted", "observed"]
    accepted = context.checkpoints[0][1]
    assert accepted == {
        "schema_version": 2,
        "mode": "post_refresh_item_observation",
        "provider": "emby",
        "server_version": "4.9.5",
        "profile_fingerprint": PROFILE_FINGERPRINT,
        "library_id_digest": LIBRARY_ID_DIGEST,
        "scan_state": "accepted",
        "publication_fingerprint": PUBLICATION_FINGERPRINT,
        "selector_fingerprint": SELECTOR_FINGERPRINT,
        "baseline_state": "not_found",
        "observation_state": "pending",
        "match_count": 0,
        "verification_count": 0,
        "accepted_at": "2026-09-05T00:00:00+00:00",
    }
    assert context.progresses == [
        ("polling", 0, None, "steps"),
        ("polling", 1, None, "steps"),
        ("polling", 2, None, "steps"),
    ]
    assert timeline.waits == [2.0, 2.0]


def test_jellyfin_requires_two_stable_absent_baselines_and_exactly_two_positive_polls() -> None:
    target = _target()
    timeline = _TimelineEvent()
    server = _Server(
        "jellyfin",
        [
            _lookup("not_found", items=12, pages=2),
            _lookup("not_found", items=12, pages=2),
            _lookup("matched", items=13, pages=2),
            _lookup("matched", items=13, pages=2),
        ],
    )

    outcome = _service(server, _Resolver(target, target, target), timeline).observe_author(
        target,
        _Context(timeline),
    )

    assert outcome.state == "succeeded"
    assert server.lookup_calls == 4
    assert server.post_count == 1
    assert timeline.waits == [2.0, 2.0]


def test_unstable_jellyfin_absent_baseline_is_incomplete_and_sends_no_post() -> None:
    target = _target()
    timeline = _TimelineEvent()
    server = _Server(
        "jellyfin",
        [
            _lookup("not_found", set_fingerprint="1" * 64, items=10),
            _lookup("not_found", set_fingerprint="2" * 64, items=10),
        ],
    )

    outcome = _service(server, _Resolver(target), timeline).observe_author(target, _Context(timeline))

    assert outcome.state == "failed_terminal"
    assert outcome.error_code == "media_server_item_lookup_incomplete"
    assert server.scan_calls == server.post_count == 0


@pytest.mark.parametrize("provider", ["emby", "jellyfin"])
def test_matched_baseline_is_terminal_precondition_failure_without_post(provider: str) -> None:
    target = _target()
    timeline = _TimelineEvent()
    server = _Server(provider, [_lookup("matched", items=1)])

    outcome = _service(server, _Resolver(target), timeline).observe_author(target, _Context(timeline))

    assert outcome.state == "failed_terminal"
    assert outcome.error_code == "media_server_scan_observation_precondition_failed"
    assert outcome.payload is None
    assert server.scan_calls == server.post_count == 0


def test_publication_drift_in_transport_hook_rejects_entry_and_post() -> None:
    target = _target()
    changed = _target(publication_fingerprint="f" * 64)
    timeline = _TimelineEvent()
    server = _Server("emby", [_lookup("not_found")])
    resolver = _Resolver(target, target)
    context = _Context(timeline)

    def drift_during_phase(phase: str) -> None:
        if phase == "dispatching":
            resolver.targets[1] = changed

    context.on_phase = drift_during_phase

    outcome = _service(server, resolver, timeline).observe_author(target, context)

    assert outcome.state == "failed_terminal"
    assert outcome.error_code == "media_server_publication_changed"
    assert server.scan_calls == 1
    assert server.before_entry_calls == 1
    assert server.post_count == 0
    assert context.phases == ["baselining", "dispatching", "baselining"]
    assert resolver.deadlines == [120.0, 120.0]


def test_real_coordinator_preserves_only_clean_hook_rejection_as_pre_dispatch(
    tmp_path: Path,
) -> None:
    target = _target()
    changed = _target(publication_fingerprint="f" * 64)
    timeline = _TimelineEvent()
    server = _Server("emby", [_lookup("not_found")])
    service = _service(server, _Resolver(target, changed), timeline)
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'observation-operation.sqlite3').as_posix()}")
    database.create_schema()
    coordinator = OperationCoordinator(database, heartbeat_interval_seconds=0.05)
    fingerprint = operation_request_fingerprint(
        "media-server-scan",
        target_id=AUTHOR_ID,
        parameters={
            "profile_fingerprint": PROFILE_FINGERPRINT,
            "mode": "post_refresh_item_observation",
            "publication_fingerprint": PUBLICATION_FINGERPRINT,
        },
    )
    try:
        submission = coordinator.submit(
            OperationExecution(
                kind="media-server-scan",
                request_fingerprint=fingerprint,
                exclusive_key=f"media-server:{PROFILE_FINGERPRINT}",
                target_type="author",
                target_id=AUTHOR_ID,
                phase="preparing",
                execute=lambda context: service.observe_author(target, context),
            )
        )
        wait_deadline = time.monotonic() + 5
        terminal = coordinator.get(submission.operation_id)
        while terminal.state in {"queued", "running"} and time.monotonic() < wait_deadline:
            time.sleep(0.01)
            terminal = coordinator.get(submission.operation_id)

        assert terminal.state == "failed_terminal"
        assert terminal.phase == "baselining"
        assert terminal.error_code == "media_server_publication_changed"
        assert server.scan_calls == 1
        assert server.post_count == 0

        def fail_after_unproven_dispatch(context: object) -> OperationOutcome:
            assert hasattr(context, "phase")
            context.phase("dispatching")
            return OperationOutcome.failed("media_server_publication_changed", retryable=False)

        generic = coordinator.submit(
            OperationExecution(
                kind="media-server-scan",
                request_fingerprint="9" * 64,
                exclusive_key="media-server:generic-dispatch-failure",
                target_type="author",
                target_id=AUTHOR_ID,
                phase="preparing",
                execute=fail_after_unproven_dispatch,
            )
        )
        wait_deadline = time.monotonic() + 5
        generic_terminal = coordinator.get(generic.operation_id)
        while generic_terminal.state in {"queued", "running"} and time.monotonic() < wait_deadline:
            time.sleep(0.01)
            generic_terminal = coordinator.get(generic.operation_id)

        assert generic_terminal.state == "failed_terminal"
        assert generic_terminal.phase == "dispatching"
        assert generic_terminal.error_code == "media_server_scan_acceptance_unknown"
    finally:
        coordinator.shutdown()
        database.dispose()


@pytest.mark.parametrize("phase", ["baselining", "dispatching"])
def test_cancellation_before_transport_entry_is_cancelled_and_sends_no_post(phase: str) -> None:
    target = _target()
    timeline = _TimelineEvent()
    context = _Context(timeline)
    context.cancel_on_phase = phase
    server = _Server("emby", [_lookup("not_found")])

    outcome = _service(server, _Resolver(target, target), timeline).observe_author(target, context)

    assert outcome.state == "cancelled"
    assert server.post_count == 0
    assert server.lookup_calls == (0 if phase == "baselining" else 1)


def test_cancellation_after_accepted_checkpoint_is_completion_unknown_with_checkpoint() -> None:
    target = _target()
    timeline = _TimelineEvent()
    context = _Context(timeline)
    context.cancel_after_checkpoint = "accepted"
    server = _Server("emby", [_lookup("not_found")])

    outcome = _service(server, _Resolver(target, target), timeline).observe_author(target, context)

    assert outcome.state == "failed_terminal"
    assert outcome.error_code == "media_server_scan_completion_unknown"
    assert outcome.payload == context.checkpoints[0][1]
    assert outcome.payload is not None and outcome.payload["observation_state"] == "pending"
    assert server.post_count == 1
    assert server.lookup_calls == 1
    assert timeline.waits == []


def test_accepted_lookup_failure_is_completion_unknown_and_post_is_never_retried() -> None:
    target = _target()
    timeline = _TimelineEvent()
    server = _Server(
        "emby",
        [_lookup("not_found"), MediaServerError("media_server_item_lookup_incomplete")],
    )
    context = _Context(timeline)

    outcome = _service(server, _Resolver(target, target), timeline).observe_author(target, context)

    assert outcome.state == "failed_terminal"
    assert outcome.error_code == "media_server_scan_completion_unknown"
    assert outcome.payload == context.checkpoints[0][1]
    assert server.scan_calls == server.post_count == 1
    assert server.lookup_calls == 2


def test_different_second_item_cannot_prove_observation() -> None:
    target = _target()
    timeline = _TimelineEvent()
    server = _Server(
        "emby",
        [
            _lookup("not_found"),
            _lookup("matched", item_id="first", items=1),
            _lookup("matched", item_id="second", items=1),
        ],
    )

    outcome = _service(server, _Resolver(target, target), timeline).observe_author(target, _Context(timeline))

    assert outcome.state == "failed_terminal"
    assert outcome.error_code == "media_server_scan_completion_unknown"
    assert server.lookup_calls == 3
    assert server.post_count == 1


def test_observed_publication_drift_preserves_only_accepted_checkpoint() -> None:
    target = _target()
    changed = _target(publication_fingerprint="f" * 64)
    timeline = _TimelineEvent()
    server = _Server(
        "emby",
        [_lookup("not_found"), _lookup("matched", items=1), _lookup("matched", items=1)],
    )
    context = _Context(timeline)

    outcome = _service(server, _Resolver(target, target, changed), timeline).observe_author(target, context)

    assert outcome.state == "failed_terminal"
    assert outcome.error_code == "media_server_scan_completion_unknown"
    assert [phase for phase, _payload in context.checkpoints] == ["accepted"]
    assert outcome.payload == context.checkpoints[0][1]


def test_jellyfin_aggregate_reservation_limits_operation_to_four_passes() -> None:
    target = _target()
    timeline = _TimelineEvent()
    server = _Server("jellyfin", [_lookup("not_found") for _index in range(5)])

    outcome = _service(server, _Resolver(target, target), timeline).observe_author(target, _Context(timeline))

    assert outcome.state == "failed_terminal"
    assert outcome.error_code == "media_server_scan_completion_unknown"
    assert server.lookup_calls == 4
    assert server.post_count == 1
    assert timeline.waits == [2.0, 2.0, 2.0]


def test_provider_pass_hard_limit_is_checked_before_mutation() -> None:
    target = _target()
    timeline = _TimelineEvent()
    server = _Server("emby", [_lookup("not_found", pages=2)])

    outcome = _service(server, _Resolver(target), timeline).observe_author(target, _Context(timeline))

    assert outcome.state == "failed_terminal"
    assert outcome.error_code == "media_server_item_lookup_incomplete"
    assert server.scan_calls == server.post_count == 0


def test_absolute_deadline_and_minimum_interval_bound_polling() -> None:
    target = _target()
    timeline = _TimelineEvent()
    server = _Server("emby", [_lookup("not_found"), _lookup("not_found"), _lookup("matched", items=1)])
    limits = MediaServerObservationLimits(timeout_seconds=4, poll_interval_seconds=2)

    outcome = _service(server, _Resolver(target, target), timeline, limits=limits).observe_author(
        target,
        _Context(timeline),
    )

    assert outcome.state == "failed_terminal"
    assert outcome.error_code == "media_server_scan_completion_unknown"
    assert timeline.now == 4.0
    assert timeline.waits == [2.0, 2.0]
    assert server.lookup_calls == 2
    assert server.post_count == 1


def test_lookup_returning_at_outer_deadline_cannot_advance_or_start_another_pass() -> None:
    target = _target()
    timeline = _TimelineEvent()
    resolver = _Resolver(target, target)
    server = _Server("emby", [_lookup("not_found"), _lookup("matched", items=1), _lookup("matched", items=1)])

    def block_at_tail(call: int) -> None:
        if call == 2:
            timeline.now = 120.0

    server.on_lookup = block_at_tail
    context = _Context(timeline)

    outcome = _service(server, resolver, timeline).observe_author(target, context)

    assert outcome.state == "failed_terminal"
    assert outcome.error_code == "media_server_scan_completion_unknown"
    assert server.lookup_calls == 2
    assert server.lookup_deadlines == [120.0, 120.0]
    assert server.scan_deadlines == [120.0]
    assert resolver.deadlines == [120.0, 120.0]
    assert context.progresses == [("polling", 0, None, "steps")]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_seconds": 120.000001},
        {"poll_interval_seconds": 1.999999},
        {"max_pages": 129},
        {"max_rows": 16_385},
        {"max_response_bytes": 32 * 1024 * 1024 + 1},
    ],
)
def test_limits_cannot_raise_frozen_operation_boundary(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        MediaServerObservationLimits(**kwargs)  # type: ignore[arg-type]
