"""Tieba creator-thread scan state machine: page cursor, stop reasons, tails, stalls."""

from __future__ import annotations

import hashlib
from uuid import UUID

import pytest

from media_sync.integrations.mediacrawler.tieba_creator_work import (
    TB_CREATOR_PAGE_SIZE,
    TB_SCAN_COVERAGE_FILENAME,
    TB_SCAN_CURSOR_PREFIX,
    TB_STALL_BLOCKED_CODE,
    TB_STALLED_UNIT_LIMIT,
    TiebaCreatorPage,
    TiebaScanCoverage,
    TiebaScanState,
    TiebaScanUnit,
    TiebaWorkIdentity,
)

ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000086")
AUTHOR_FP = hashlib.sha256(b"tb.1.portrait").hexdigest()
CREATOR_FP = hashlib.sha256(b"https://tieba.baidu.com/home/main?id=tb.1.portrait").hexdigest()
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"


def _identity(thread_id: str, listing: str = "listing") -> TiebaWorkIdentity:
    return TiebaWorkIdentity(thread_id, hashlib.sha256(f"{thread_id}:{listing}".encode()).hexdigest())


def _page(
    number: int,
    threads: tuple[str, ...],
    *,
    has_more: bool = True,
    listing: str = "listing",
) -> TiebaCreatorPage:
    return TiebaCreatorPage(number, has_more, tuple(_identity(thread, listing) for thread in threads))


def _state() -> TiebaScanState:
    return TiebaScanState.initial(ACCOUNT_ID, AUTHOR_FP, CREATOR_FP, UPSTREAM_SHA)


def _drive(unit: TiebaScanUnit, page: TiebaCreatorPage, *, fail: tuple[str, ...] = ()) -> None:
    assert unit.next_action().kind == "list"
    unit.observe_page(page)
    while (action := unit.next_action()).kind == "detail":
        identity = action.identity
        assert identity is not None
        if identity.thread_id in fail:
            unit.fail(identity)
        else:
            unit.store(identity)


def test_cursor_round_trips_and_rejects_binding_changes() -> None:
    unit = TiebaScanUnit(_state(), 20)
    _drive(unit, _page(1, ("700000001", "700000002"), listing="private-listing-sentinel"))
    coverage = unit.coverage()
    cursor = coverage.next_state.to_cursor()

    assert cursor.startswith(TB_SCAN_CURSOR_PREFIX)
    assert coverage.next_state.page == 2
    assert "private-listing-sentinel" not in cursor
    restored = TiebaScanState.from_cursor(cursor)
    assert restored == coverage.next_state

    with pytest.raises(ValueError):
        TiebaScanState.for_cursor(
            cursor,
            account_id=ACCOUNT_ID,
            author_fingerprint_sha256=hashlib.sha256(b"other").hexdigest(),
            creator_fingerprint_sha256=CREATOR_FP,
            upstream_sha=UPSTREAM_SHA,
        )


def test_server_declared_end_is_a_source_end_candidate() -> None:
    unit = TiebaScanUnit(_state(), 20)
    _drive(unit, _page(1, ("700000010", "700000011"), has_more=False))

    coverage = unit.coverage()

    assert coverage.stop_reason == "has_more_false"
    assert coverage.source_end_observed is True
    assert coverage.summary.has_more is False
    assert coverage.next_state.head_boundary is not None
    assert coverage.next_state.page == 1


def test_empty_page_ends_with_its_own_code() -> None:
    unit = TiebaScanUnit(_state(), 20)
    _drive(unit, _page(1, (), has_more=False))

    coverage = unit.coverage()

    assert coverage.stop_reason == "empty_page_end"
    assert coverage.next_state.page == 1


def test_empty_page_that_promises_more_is_a_stall_not_an_end() -> None:
    """`has_more=1` with no threads contradicts itself.

    An anti-bot/rate-limit envelope still parses as `error_code=0` with
    `has_more=1` and an empty list. Treating that as `empty_page_end` publishes
    an empty head boundary, which then reconciles equal and moves the row into
    incremental — permanently skipping the creator's whole backlog. It must
    replay the same page and count the stall instead.
    """

    unit = TiebaScanUnit(_state(), 20)
    _drive(unit, _page(1, (), has_more=True))

    coverage = unit.coverage()

    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.source_end_observed is False
    assert coverage.next_state.page == 1
    assert coverage.next_state.head_boundary is None
    assert coverage.next_state.stalled_units == 1


def test_a_repeated_page_is_replayed_and_does_not_skip_threads() -> None:
    """A stalled `pn` must not advance: advancing drops that page's threads."""

    first = tuple(f"{9500000000 + index}" for index in range(20))
    unit = TiebaScanUnit(_state(), 20)
    _drive(unit, _page(1, first))
    state = unit.coverage().next_state
    assert state.page == 2

    unit = TiebaScanUnit(state, 20)
    _drive(unit, _page(2, first))
    coverage = unit.coverage()

    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.next_state.page == 2
    assert coverage.next_state.stalled_units == 1


def test_page_tail_is_replayed_by_the_identical_page_number() -> None:
    threads = tuple(f"{700000100 + index}" for index in range(TB_CREATOR_PAGE_SIZE))
    first = TiebaScanUnit(_state(), max_items=5)
    _drive(first, _page(1, threads))
    coverage = first.coverage()

    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.summary.page_complete is False
    assert coverage.next_state.page == 1
    assert coverage.next_state.witness is not None
    assert [item.thread_id for item in coverage.successful] == list(threads[:5])

    second = TiebaScanUnit(coverage.next_state, max_items=5)
    assert second.next_action().page == 1
    second.observe_page(_page(1, threads))
    delivered: list[str] = []
    while (action := second.next_action()).kind == "detail":
        identity = action.identity
        assert identity is not None
        delivered.append(identity.thread_id)
        second.store(identity)
    assert delivered == list(threads[5:10])


def test_advanced_page_is_replayed_verbatim() -> None:
    unit = TiebaScanUnit(_state(), max_items=1)
    _drive(unit, _page(1, ("700000200", "700000201")))
    coverage = unit.coverage()

    follow = TiebaScanUnit(coverage.next_state, max_items=20)
    assert follow.next_action().page == 1

    complete = TiebaScanUnit(coverage.next_state, max_items=20)
    _drive(complete, _page(1, ("700000200", "700000201")))
    assert complete.coverage().next_state.page == 2


def test_repeated_page_identity_blocks_after_a_bounded_number_of_units() -> None:
    threads = ("700000300", "700000301")
    unit = TiebaScanUnit(_state(), 20)
    _drive(unit, _page(1, threads))
    state = unit.coverage().next_state
    assert state.previous_page_thread_ids == threads

    for _ in range(TB_STALLED_UNIT_LIMIT + 1):
        unit = TiebaScanUnit(state, 20)
        _drive(unit, _page(state.page, threads))
        coverage = unit.coverage()
        state = coverage.next_state

    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.source_end_observed is False
    assert coverage.blocked_code == TB_STALL_BLOCKED_CODE


def test_access_restriction_is_never_an_end() -> None:
    unit = TiebaScanUnit(_state(), 20)
    unit.observe_access_restricted()
    coverage = unit.coverage()

    assert coverage.stop_reason == "access_restricted"
    assert coverage.source_end_observed is False
    assert coverage.public_summary()["blocked_code"] is None


def test_head_lane_reproduces_the_boundary_and_skips_unchanged_threads() -> None:
    threads = ("700000400", "700000401")
    first = TiebaScanUnit(_state(), 20)
    _drive(first, _page(1, threads, has_more=False))
    base = first.coverage().next_state

    head = TiebaScanUnit(base.for_head(), 20)
    head.observe_page(_page(1, threads, has_more=False))
    while (action := head.next_action()).kind == "unchanged":
        identity = action.identity
        assert identity is not None
        head.skip_unchanged(identity)

    coverage = head.coverage()
    assert coverage.stop_reason == "has_more_false"
    assert coverage.public_summary()["head_boundary_matches"] is True


def test_coverage_round_trips_through_its_json_line() -> None:
    unit = TiebaScanUnit(_state(), max_items=2)
    _drive(
        unit,
        _page(1, ("700000500", "700000501", "700000502"), listing="coverage-listing-sentinel"),
        fail=("700000501",),
    )
    coverage = unit.coverage()

    line = coverage.to_json_line()

    assert line.endswith("\n")
    assert TB_SCAN_COVERAGE_FILENAME.endswith(".jsonl")
    assert "coverage-listing-sentinel" not in line
    restored = TiebaScanCoverage.from_json_line(line)
    assert restored == coverage
    assert restored.summary.failed_count == 1


def test_failed_detail_does_not_hide_unrelated_threads() -> None:
    unit = TiebaScanUnit(_state(), max_items=5)
    _drive(unit, _page(1, ("700000600", "700000601", "700000602")), fail=("700000601",))

    coverage = unit.coverage()

    assert [item.thread_id for item in coverage.successful] == ["700000600", "700000602"]
    assert [item.identity.thread_id for item in coverage.failed] == ["700000601"]
    assert coverage.stop_reason == "unit_cap_reached"


def test_page_rejects_a_mismatched_number() -> None:
    unit = TiebaScanUnit(_state(), 20)
    assert unit.next_action().kind == "list"
    with pytest.raises(ValueError):
        unit.observe_page(_page(2, ("700000700",)))


def test_page_number_and_thread_shape_are_bounded() -> None:
    with pytest.raises(ValueError):
        TiebaCreatorPage(0, True, ())
    with pytest.raises(ValueError):
        TiebaCreatorPage(1, True, (_identity("not-a-thread"),))
    with pytest.raises(ValueError):
        TiebaCreatorPage(1, True, (_identity("700000001"), _identity("700000001")))
