"""Zhihu creator-answer scan state machine: integer offset, window shift, stops."""

from __future__ import annotations

import hashlib
from uuid import UUID

import pytest

from media_sync.integrations.mediacrawler.zhihu_creator_work import (
    ZH_SCAN_COVERAGE_FILENAME,
    ZH_SCAN_CURSOR_PREFIX,
    ZH_STALL_BLOCKED_CODE,
    ZH_STALLED_UNIT_LIMIT,
    ZhihuCreatorPage,
    ZhihuScanCoverage,
    ZhihuScanState,
    ZhihuScanUnit,
    ZhihuWorkIdentity,
)

ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000088")
AUTHOR_FP = hashlib.sha256(b"zhihu-url-token").hexdigest()
CREATOR_FP = hashlib.sha256(b"https://www.zhihu.com/people/zhihu-url-token").hexdigest()
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"


def _identity(content_id: str, listing: str = "listing") -> ZhihuWorkIdentity:
    return ZhihuWorkIdentity(content_id, hashlib.sha256(f"{content_id}:{listing}".encode()).hexdigest())


def _page(
    offset: int,
    content_ids: tuple[str, ...],
    *,
    is_end: bool = False,
    listing: str = "listing",
    limit: int = 20,
) -> ZhihuCreatorPage:
    return ZhihuCreatorPage(offset, limit, is_end, tuple(_identity(value, listing) for value in content_ids))


def _state() -> ZhihuScanState:
    return ZhihuScanState.initial(ACCOUNT_ID, AUTHOR_FP, CREATOR_FP, UPSTREAM_SHA)


def _drive(unit: ZhihuScanUnit, page: ZhihuCreatorPage, *, fail: tuple[str, ...] = ()) -> None:
    assert unit.next_action().kind == "list"
    unit.observe_page(page)
    while (action := unit.next_action()).kind == "detail":
        identity = action.identity
        assert identity is not None
        if identity.content_id in fail:
            unit.fail(identity)
        else:
            unit.store(identity)


def _ids(start: int, count: int) -> tuple[str, ...]:
    return tuple(str(start + index) for index in range(count))


def test_cursor_round_trips_and_rejects_binding_changes() -> None:
    unit = ZhihuScanUnit(_state(), 20)
    _drive(unit, _page(0, _ids(1000, 20), listing="private-listing-sentinel"))
    coverage = unit.coverage()
    cursor = coverage.next_state.to_cursor()

    assert cursor.startswith(ZH_SCAN_CURSOR_PREFIX)
    assert coverage.next_state.offset == 20
    assert "private-listing-sentinel" not in cursor
    assert ZhihuScanState.from_cursor(cursor) == coverage.next_state

    with pytest.raises(ValueError):
        ZhihuScanState.for_cursor(
            cursor,
            account_id=ACCOUNT_ID,
            author_fingerprint_sha256=hashlib.sha256(b"other").hexdigest(),
            creator_fingerprint_sha256=CREATOR_FP,
            upstream_sha=UPSTREAM_SHA,
        )


def test_server_declared_end_is_a_source_end_candidate() -> None:
    unit = ZhihuScanUnit(_state(), 20)
    _drive(unit, _page(0, _ids(2000, 5), is_end=True))

    coverage = unit.coverage()

    assert coverage.stop_reason == "is_end"
    assert coverage.source_end_observed is True
    assert coverage.summary.is_end is True
    assert coverage.next_state.head_boundary is not None
    assert coverage.next_state.offset == 0


def test_empty_page_that_is_the_declared_end_keeps_its_own_code() -> None:
    unit = ZhihuScanUnit(_state(), 20)
    _drive(unit, _page(0, (), is_end=True))

    coverage = unit.coverage()

    assert coverage.stop_reason == "empty_page_end"
    assert coverage.source_end_observed is True


def test_empty_page_that_is_not_the_end_is_a_stall_not_an_end() -> None:
    """`data: []` with `is_end: false` contradicts itself.

    A rate-limited body parses this way; declaring an empty source end would
    publish an empty head boundary, which reconciles equal to anything and lets
    the row enter incremental while the whole backlog is still unfetched.
    """

    unit = ZhihuScanUnit(_state(), 20)
    _drive(unit, _page(0, (), is_end=False))

    coverage = unit.coverage()

    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.source_end_observed is False
    assert coverage.next_state.offset == 0
    assert coverage.next_state.stalled_units == 1
    assert coverage.next_state.head_boundary is None


def test_small_unit_cap_requests_and_consumes_its_own_limit() -> None:
    # Zhihu's page size is client-controlled (``limit``), so the durable layer
    # asks for exactly what the remaining cap allows and advances by that amount.
    ids = _ids(3000, 5)
    first = ZhihuScanUnit(_state(), max_items=5)
    assert first.next_action().limit == 5
    _drive(first, _page(0, ids, limit=5))
    coverage = first.coverage()

    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.summary.page_complete is True
    assert coverage.next_state.offset == 5
    assert [item.content_id for item in coverage.successful] == list(ids)

    second = ZhihuScanUnit(coverage.next_state, max_items=5)
    assert second.next_action().offset == 5


def test_failed_detail_keeps_the_offset_for_replay() -> None:
    ids = _ids(3500, 4)
    unit = ZhihuScanUnit(_state(), max_items=4)
    _drive(unit, _page(0, ids, limit=4), fail=(ids[1],))
    coverage = unit.coverage()

    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.summary.page_complete is False
    assert coverage.next_state.offset == 0
    assert coverage.next_state.witness is not None


def test_advanced_offset_is_replayed_verbatim() -> None:
    unit = ZhihuScanUnit(_state(), max_items=20)
    _drive(unit, _page(0, _ids(4000, 20)))
    coverage = unit.coverage()

    assert coverage.next_state.offset == 20
    follow = ZhihuScanUnit(coverage.next_state, max_items=20)
    assert follow.next_action().offset == 20


def test_a_partially_shifted_window_advances_instead_of_blocking() -> None:
    """One insertion legitimately repeats the previous page's tail.

    Zhihu paginates by an integer ``offset`` product, so publishing one answer
    moves the window by one and the next page starts with the previous page's
    last id. Treating that partial intersection as a stall would wedge the
    subscription on the first new answer forever, so the page must be consumed
    normally. Re-storing an already delivered answer is idempotent.
    """

    first = ZhihuScanUnit(_state(), 20)
    _drive(first, _page(0, _ids(5000, 20)))
    state = first.coverage().next_state
    assert state.offset == 20

    drifted = (_ids(5000, 20)[-1], *_ids(6000, 19))
    unit = ZhihuScanUnit(state, 20)
    _drive(unit, _page(20, drifted))
    coverage = unit.coverage()

    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.source_end_observed is False
    assert coverage.next_state.offset == 40
    assert coverage.next_state.stalled_units == 0
    assert coverage.blocked_code is None


def test_an_identical_page_stalls_and_blocks_with_its_own_code() -> None:
    """A page that repeats verbatim means the window is not moving at all."""

    first = ZhihuScanUnit(_state(), 20)
    _drive(first, _page(0, _ids(7000, 20)))
    state = first.coverage().next_state

    repeated = _ids(7000, 20)
    for _ in range(ZH_STALLED_UNIT_LIMIT):
        unit = ZhihuScanUnit(state, 20)
        _drive(unit, _page(state.offset, repeated))
        coverage = unit.coverage()
        assert coverage.stop_reason == "unit_cap_reached"
        assert coverage.source_end_observed is False
        state = coverage.next_state

    assert state.offset == 20
    assert state.stalled_units == ZH_STALLED_UNIT_LIMIT
    unit = ZhihuScanUnit(state, 20)
    _drive(unit, _page(state.offset, repeated))
    assert unit.coverage().blocked_code == ZH_STALL_BLOCKED_CODE


def test_access_restriction_is_never_an_end() -> None:
    unit = ZhihuScanUnit(_state(), 20)
    unit.observe_access_restricted()
    coverage = unit.coverage()

    assert coverage.stop_reason == "access_restricted"
    assert coverage.source_end_observed is False
    assert coverage.public_summary()["blocked_code"] is None


def test_head_lane_reproduces_the_boundary_and_skips_unchanged_answers() -> None:
    ids = _ids(6000, 3)
    first = ZhihuScanUnit(_state(), 20)
    _drive(first, _page(0, ids, is_end=True))
    base = first.coverage().next_state

    head = ZhihuScanUnit(base.for_head(), 20)
    head.observe_page(_page(0, ids, is_end=True))
    while (action := head.next_action()).kind == "unchanged":
        identity = action.identity
        assert identity is not None
        head.skip_unchanged(identity)

    coverage = head.coverage()
    assert coverage.stop_reason == "is_end"
    assert coverage.public_summary()["head_boundary_matches"] is True


def test_coverage_round_trips_through_its_json_line() -> None:
    unit = ZhihuScanUnit(_state(), max_items=2)
    _drive(
        unit,
        _page(0, ("7000001", "7000002"), listing="coverage-listing-sentinel", limit=2),
        fail=("7000001",),
    )
    coverage = unit.coverage()

    line = coverage.to_json_line()

    assert line.endswith("\n")
    assert ZH_SCAN_COVERAGE_FILENAME.endswith(".jsonl")
    assert "coverage-listing-sentinel" not in line
    restored = ZhihuScanCoverage.from_json_line(line)
    assert restored == coverage
    assert restored.summary.failed_count == 1


def test_failed_detail_does_not_hide_unrelated_answers() -> None:
    unit = ZhihuScanUnit(_state(), max_items=5)
    _drive(unit, _page(0, ("8000001", "8000002", "8000003"), limit=5), fail=("8000002",))

    coverage = unit.coverage()

    assert [item.content_id for item in coverage.successful] == ["8000001", "8000003"]
    assert [item.identity.content_id for item in coverage.failed] == ["8000002"]
    assert coverage.stop_reason == "unit_cap_reached"


def test_page_rejects_a_mismatched_offset_or_limit() -> None:
    unit = ZhihuScanUnit(_state(), 20)
    assert unit.next_action().kind == "list"
    with pytest.raises(ValueError):
        unit.observe_page(_page(20, ("9000001",)))


def test_offset_and_content_shape_are_bounded() -> None:
    with pytest.raises(ValueError):
        ZhihuCreatorPage(-1, 20, False, ())
    with pytest.raises(ValueError):
        ZhihuCreatorPage(0, 0, False, ())
    with pytest.raises(ValueError):
        ZhihuCreatorPage(0, 20, False, (_identity("not-an-id"),))
    with pytest.raises(ValueError):
        ZhihuCreatorPage(0, 20, False, (_identity("9000001"), _identity("9000001")))
    with pytest.raises(ValueError):
        ZhihuCreatorPage(0, 2, False, (_identity("9000001"), _identity("9000002"), _identity("9000003")))
