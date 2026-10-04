"""Execution 0081: durable Kuaishou creator-work scan contracts."""

from __future__ import annotations

from uuid import UUID

import pytest

from media_sync.integrations.mediacrawler import kuaishou_creator_work as ks_module
from media_sync.integrations.mediacrawler.kuaishou_creator_work import (
    KUAISHOU_NO_MORE_SENTINEL,
    KUAISHOU_SCAN_CURSOR_PREFIX,
    KUAISHOU_STALL_BLOCKED_CODE,
    KUAISHOU_STALLED_UNIT_LIMIT,
    KuaishouCreatorPage,
    KuaishouScanState,
    KuaishouScanUnit,
    KuaishouWorkIdentity,
)

ACCOUNT = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
AUTHOR = "a" * 64
CREATOR = "b" * 64
UPSTREAM = "d" * 40


def _photo_id(index: int) -> str:
    return f"3x{index:013x}"


def _identity(photo_id: str, digest: str) -> KuaishouWorkIdentity:
    return KuaishouWorkIdentity(photo_id=photo_id, listing_sha256=digest)


def _page(input_cursor: str, next_cursor: str, works: list[tuple[str, str]]) -> KuaishouCreatorPage:
    return KuaishouCreatorPage(
        input_cursor,
        next_cursor,
        tuple(_identity(photo_id, digest) for photo_id, digest in works),
    )


def _state_for(cursor: str | None) -> KuaishouScanState:
    return KuaishouScanState.for_cursor(
        cursor,
        account_id=ACCOUNT,
        author_fingerprint_sha256=AUTHOR,
        creator_fingerprint_sha256=CREATOR,
        upstream_sha=UPSTREAM,
    )


def test_cursor_round_trip_is_canonical_and_opaque() -> None:
    state = KuaishouScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM)
    cursor = state.to_cursor()
    assert cursor.startswith(KUAISHOU_SCAN_CURSOR_PREFIX)
    restored = KuaishouScanState.from_cursor(cursor)
    assert restored == state
    assert restored.to_cursor() == cursor
    assert restored.public_summary()["lane"] == "history"


def test_three_opaque_cursor_steps_reach_only_real_source_end() -> None:
    digests = [f"{index:064x}" for index in range(1, 7)]
    cursor = None
    echo = ""
    for step in range(2):
        unit = KuaishouScanUnit(_state_for(cursor), 18)
        next_echo = f"echo-{step}"
        unit.observe_page(
            _page(
                echo,
                next_echo,
                [(_photo_id(step), digests[step * 2]), (_photo_id(step + 1), digests[step * 2 + 1])],
            )
        )
        assert unit.next_action().kind == "detail"
        unit.store(unit.next_action().identity)
        unit.store(unit.next_action().identity)
        coverage = unit.coverage()
        assert coverage.stop_reason == "unit_cap_reached"
        cursor = coverage.next_state.to_cursor()
        echo = next_echo
    # A server-echoed "no_more" sentinel is the primary source-end candidate.
    unit = KuaishouScanUnit(_state_for(cursor), 18)
    unit.observe_page(_page(echo, KUAISHOU_NO_MORE_SENTINEL, [(_photo_id(3), digests[4]), (_photo_id(4), digests[5])]))
    unit.store(unit.next_action().identity)
    unit.store(unit.next_action().identity)
    coverage = unit.coverage()
    assert coverage.stop_reason == "no_more_echoed"
    assert coverage.public_summary()["source_end_observed"] is True
    assert coverage.next_state.head_boundary is not None


def test_empty_page_without_echoed_sentinel_ends_via_client_inference() -> None:
    # Upstream Kuaishou terminates on an empty feeds array (client.py:436,
    # 440-442); the durable layer records the client-inferred end under its
    # own stop reason instead of merging it with the echoed one.
    unit = KuaishouScanUnit(KuaishouScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM), 18)
    unit.observe_page(_page("", "", []))
    coverage = unit.coverage()
    assert coverage.stop_reason == "empty_page_end"
    assert coverage.public_summary()["source_end_observed"] is True
    assert coverage.next_state.witness is None
    assert coverage.next_state.page_cursor == ""


def test_empty_page_with_echoed_sentinel_prefers_server_echo() -> None:
    # When an empty feeds page coincides with a server-echoed "no_more", the
    # server echo wins and the unit records no_more_echoed.
    unit = KuaishouScanUnit(KuaishouScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM), 18)
    unit.observe_page(_page("", KUAISHOU_NO_MORE_SENTINEL, []))
    coverage = unit.coverage()
    assert coverage.stop_reason == "no_more_echoed"
    assert coverage.next_state.page_cursor == KUAISHOU_NO_MORE_SENTINEL


def test_access_restriction_is_not_source_end() -> None:
    unit = KuaishouScanUnit(KuaishouScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM), 18)
    unit.observe_access_restricted()
    coverage = unit.coverage()
    assert coverage.stop_reason == "access_restricted"
    assert coverage.page is None
    assert coverage.public_summary()["source_end_observed"] is False


def test_unit_cap_is_recorded_before_finishing_a_page() -> None:
    unit = KuaishouScanUnit(KuaishouScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM), 1)
    unit.observe_page(_page("", "echo-0", [(_photo_id(1), f"{1:064x}"), (_photo_id(2), f"{2:064x}")]))
    unit.store(unit.next_action().identity)
    coverage = unit.coverage()
    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.next_state.witness is not None
    assert coverage.next_state.page_cursor == ""
    assert coverage.next_state.public_summary()["page_in_progress"] is True


def test_failed_detail_advances_without_storing() -> None:
    unit = KuaishouScanUnit(KuaishouScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM), 18)
    unit.observe_page(_page("", "echo-0", [(_photo_id(1), f"{1:064x}")]))
    identity = unit.next_action().identity
    unit.fail(identity)
    coverage = unit.coverage()
    # A failed detail keeps the page incomplete: the work stays inside the
    # retained witness for a later bounded retry and never claims delivery.
    assert coverage.stop_reason == "unit_cap_reached"
    assert len(coverage.failed) == 1
    assert coverage.successful == ()
    assert coverage.next_state.witness is not None
    assert coverage.public_summary()["partial"] is True


def test_head_drift_re_enters_reconciliation_with_boundary_witness() -> None:
    unit = KuaishouScanUnit(KuaishouScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM), 18)
    unit.observe_page(_page("", KUAISHOU_NO_MORE_SENTINEL, [(_photo_id(1), f"{1:064x}")]))
    unit.store(unit.next_action().identity)
    completed = unit.coverage().next_state
    assert completed.head_boundary is not None

    head_unit = KuaishouScanUnit(completed.for_head(), 18)
    # Drift: one inserted newer work ahead of the reconciled boundary.
    head_unit.observe_page(_page("", "echo-head", [(_photo_id(9), f"{9:064x}"), (_photo_id(1), f"{1:064x}")]))
    first = head_unit.next_action()
    assert first.kind == "detail" and first.identity.photo_id == _photo_id(9)
    head_unit.store(first.identity)
    second = head_unit.next_action()
    # The boundary work with an identical listing digest is unchanged.
    assert second.kind == "unchanged"
    head_unit.skip_unchanged(second.identity)
    head_coverage = head_unit.coverage()
    assert head_coverage.summary.lane == "head"
    assert head_coverage.next_state.head_boundary is not None


def test_cursor_binding_mutation_is_rejected() -> None:
    cursor = KuaishouScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM).to_cursor()
    restored = KuaishouScanState.from_cursor(cursor)
    with pytest.raises(ValueError):
        restored.require_binding(
            account_id=UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
            author_fingerprint_sha256=AUTHOR,
            creator_fingerprint_sha256=CREATOR,
            upstream_sha=UPSTREAM,
        )
    with pytest.raises(ValueError):
        KuaishouScanState.for_cursor(
            cursor,
            account_id=ACCOUNT,
            author_fingerprint_sha256=AUTHOR,
            creator_fingerprint_sha256=CREATOR,
            upstream_sha="e" * 40,
        )


def test_page_size_is_server_decided_not_a_client_contract() -> None:
    # client.py:169 carries no page-size field, so the module exposes no
    # fixed page size and accepts any server-decided page length.
    assert not any("PAGE_SIZE" in name for name in dir(ks_module))
    works = [(_photo_id(index), f"{index:064x}") for index in range(1, 26)]
    page = _page("", "echo", works)
    assert len(page.identities) == 25


def test_page_tail_replay_reissues_the_identical_request() -> None:
    digests = [f"{1:064x}", f"{2:064x}"]
    unit = KuaishouScanUnit(KuaishouScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM), 1)
    unit.observe_page(_page("", "echo-0", [(_photo_id(1), digests[0]), (_photo_id(2), digests[1])]))
    unit.store(unit.next_action().identity)
    coverage = unit.coverage()
    # Mid-page max_items stop: the input pcursor stays unchanged with the
    # page witness retained, and no stall is counted because the page made
    # delivery progress.
    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.next_state.page_cursor == ""
    assert coverage.next_state.witness is not None
    assert coverage.next_state.stalled_units == 0
    coverage.validate(KuaishouScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM), 1)

    replay = KuaishouScanUnit(_state_for(coverage.next_state.to_cursor()), 1)
    replay.observe_page(_page("", "echo-0", [(_photo_id(1), digests[0]), (_photo_id(2), digests[1])]))
    # The already-delivered work is skipped by stable photo.id.
    assert replay.next_action().identity.photo_id == _photo_id(2)
    replay.store(replay.next_action().identity)
    replay_coverage = replay.coverage()
    # Only the fully consumed page advances the feed to the echoed cursor.
    assert replay_coverage.stop_reason == "unit_cap_reached"
    assert replay_coverage.next_state.page_cursor == "echo-0"
    assert replay_coverage.next_state.witness is None
    assert replay_coverage.next_state.stalled_units == 0
    replay_coverage.validate(coverage.next_state, 1)


def test_cursor_non_advancement_stall_blocks_after_bounded_units() -> None:
    digests = [f"{1:064x}", f"{2:064x}"]
    works = [(_photo_id(1), digests[0]), (_photo_id(2), digests[1])]
    cursor = None
    for stalled in range(1, KUAISHOU_STALLED_UNIT_LIMIT + 1):
        unit = KuaishouScanUnit(_state_for(cursor), 18)
        unit.observe_page(_page("", "", works))
        while unit.next_action().kind == "detail":
            unit.store(unit.next_action().identity)
        coverage = unit.coverage()
        # The non-empty page's echo equals its input pcursor: no progress,
        # the identical request is re-issued until the bound trips.
        assert coverage.stop_reason == "unit_cap_reached"
        assert coverage.next_state.page_cursor == ""
        assert coverage.next_state.witness is not None
        assert coverage.next_state.stalled_units == stalled
        assert coverage.blocked_code == (
            KUAISHOU_STALL_BLOCKED_CODE if stalled >= KUAISHOU_STALLED_UNIT_LIMIT else None
        )
        coverage.validate(_state_for(cursor), 18)
        cursor = coverage.next_state.to_cursor()
    assert coverage.next_state.public_summary()["stalled_units"] == KUAISHOU_STALLED_UNIT_LIMIT
