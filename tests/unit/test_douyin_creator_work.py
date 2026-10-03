"""Execution 0080: durable Douyin creator-work scan contracts."""

from __future__ import annotations

from uuid import UUID

import pytest

from media_sync.integrations.mediacrawler.douyin_creator_work import (
    DOUYIN_CREATOR_PAGE_SIZE,
    DOUYIN_SCAN_CURSOR_PREFIX,
    DouyinCreatorPage,
    DouyinScanState,
    DouyinScanUnit,
    DouyinWorkIdentity,
)

ACCOUNT = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
AUTHOR = "a" * 64
CREATOR = "b" * 64
UPSTREAM = "d" * 40


def _identity(aweme_id: str, digest: str) -> DouyinWorkIdentity:
    return DouyinWorkIdentity(aweme_id=aweme_id, listing_sha256=digest)


def _page(
    input_cursor: str,
    next_cursor: str,
    *,
    has_more: bool,
    works: list[tuple[str, str]],
) -> DouyinCreatorPage:
    return DouyinCreatorPage(
        input_cursor,
        next_cursor,
        has_more,
        tuple(_identity(aweme_id, digest) for aweme_id, digest in works),
    )


def _state_for(cursor: str | None) -> DouyinScanState:
    return DouyinScanState.for_cursor(
        cursor,
        account_id=ACCOUNT,
        author_fingerprint_sha256=AUTHOR,
        creator_fingerprint_sha256=CREATOR,
        upstream_sha=UPSTREAM,
    )


def test_cursor_round_trip_is_canonical_and_opaque() -> None:
    state = DouyinScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM)
    cursor = state.to_cursor()
    assert cursor.startswith(DOUYIN_SCAN_CURSOR_PREFIX)
    restored = DouyinScanState.from_cursor(cursor)
    assert restored == state
    assert restored.to_cursor() == cursor
    assert restored.public_summary()["lane"] == "history"


def test_three_opaque_cursor_steps_reach_only_real_source_end() -> None:
    digests = [f"{index:064x}" for index in range(1, 7)]
    cursor = None
    echo = ""
    for step in range(2):
        unit = DouyinScanUnit(_state_for(cursor), 18)
        next_echo = f"echo-{step}"
        unit.observe_page(
            _page(
                echo,
                next_echo,
                has_more=True,
                works=[(f"{step:019d}", digests[step * 2]), (f"{step + 1:019d}", digests[step * 2 + 1])],
            )
        )
        assert unit.next_action().kind == "detail"
        unit.store(unit.next_action().identity)
        unit.store(unit.next_action().identity)
        coverage = unit.coverage()
        assert coverage.stop_reason == "unit_cap_reached"
        cursor = coverage.next_state.to_cursor()
        echo = next_echo
    # A final page with has_more != 1 is the only source-end candidate.
    unit = DouyinScanUnit(_state_for(cursor), 18)
    unit.observe_page(
        _page(
            echo,
            "echo-2",
            has_more=False,
            works=[("3000000000000000001", digests[4]), ("3000000000000000002", digests[5])],
        )
    )
    unit.store(unit.next_action().identity)
    unit.store(unit.next_action().identity)
    coverage = unit.coverage()
    assert coverage.stop_reason == "has_more_false"
    assert coverage.public_summary()["source_end_observed"] is True
    assert coverage.next_state.head_boundary is not None


def test_empty_page_with_has_more_one_stalls_and_never_ends_the_feed() -> None:
    unit = DouyinScanUnit(DouyinScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM), 18)
    unit.observe_page(_page("", "", has_more=True, works=[]))
    coverage = unit.coverage()
    assert coverage.stop_reason == "empty_page_stalled"
    assert coverage.public_summary()["source_end_observed"] is False


def test_access_restriction_is_not_source_end() -> None:
    unit = DouyinScanUnit(DouyinScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM), 18)
    unit.observe_access_restricted()
    coverage = unit.coverage()
    assert coverage.stop_reason == "access_restricted"
    assert coverage.page is None
    assert coverage.public_summary()["source_end_observed"] is False


def test_unit_cap_is_recorded_before_finishing_a_page() -> None:
    unit = DouyinScanUnit(DouyinScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM), 1)
    unit.observe_page(
        _page(
            "",
            "echo-0",
            has_more=True,
            works=[("1000000000000000001", f"{1:064x}"), ("1000000000000000002", f"{2:064x}")],
        )
    )
    unit.store(unit.next_action().identity)
    coverage = unit.coverage()
    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.next_state.witness is not None
    assert coverage.next_state.public_summary()["page_in_progress"] is True


def test_failed_detail_advances_without_storing() -> None:
    unit = DouyinScanUnit(DouyinScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM), 18)
    unit.observe_page(_page("", "echo-0", has_more=False, works=[("1000000000000000001", f"{1:064x}")]))
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
    unit = DouyinScanUnit(DouyinScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM), 18)
    unit.observe_page(_page("", "echo-0", has_more=False, works=[("1000000000000000001", f"{1:064x}")]))
    unit.store(unit.next_action().identity)
    completed = unit.coverage().next_state
    assert completed.head_boundary is not None

    head_unit = DouyinScanUnit(completed.for_head(), 18)
    # Drift: one inserted newer work ahead of the reconciled boundary.
    head_unit.observe_page(
        _page(
            "",
            "echo-head",
            has_more=True,
            works=[("1000000000000000009", f"{9:064x}"), ("1000000000000000001", f"{1:064x}")],
        )
    )
    first = head_unit.next_action()
    assert first.kind == "detail" and first.identity.aweme_id == "1000000000000000009"
    head_unit.store(first.identity)
    second = head_unit.next_action()
    # The boundary work with an identical listing digest is unchanged.
    assert second.kind == "unchanged"
    head_unit.skip_unchanged(second.identity)
    head_coverage = head_unit.coverage()
    assert head_coverage.summary.lane == "head"
    assert head_coverage.next_state.head_boundary is not None


def test_cursor_binding_mutation_is_rejected() -> None:
    cursor = DouyinScanState.initial(ACCOUNT, AUTHOR, CREATOR, UPSTREAM).to_cursor()
    restored = DouyinScanState.from_cursor(cursor)
    with pytest.raises(ValueError):
        restored.require_binding(
            account_id=UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
            author_fingerprint_sha256=AUTHOR,
            creator_fingerprint_sha256=CREATOR,
            upstream_sha=UPSTREAM,
        )
    with pytest.raises(ValueError):
        DouyinScanState.for_cursor(
            cursor,
            account_id=ACCOUNT,
            author_fingerprint_sha256=AUTHOR,
            creator_fingerprint_sha256=CREATOR,
            upstream_sha="e" * 40,
        )


def test_page_size_is_the_upstream_eighteen() -> None:
    assert DOUYIN_CREATOR_PAGE_SIZE == 18
    with pytest.raises(ValueError):
        _page("", "echo", has_more=True, works=[(f"{index:019d}", f"{index:064x}") for index in range(19)])
