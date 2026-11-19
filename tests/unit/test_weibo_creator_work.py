"""Weibo creator-note scan state machine: cursor, stop reasons, page tail, stalls."""

from __future__ import annotations

import hashlib
from uuid import UUID

import pytest

from media_sync.integrations.mediacrawler.weibo_creator_work import (
    WB_CREATOR_PAGE_SIZE,
    WB_SCAN_COVERAGE_FILENAME,
    WB_SCAN_CURSOR_PREFIX,
    WB_STALL_BLOCKED_CODE,
    WB_STALLED_UNIT_LIMIT,
    WeiboCreatorPage,
    WeiboPageWitness,
    WeiboScanCoverage,
    WeiboScanState,
    WeiboScanUnit,
    WeiboUnitSummary,
    WeiboWorkIdentity,
)

ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000084")
AUTHOR_FP = hashlib.sha256(b"5123456789012345").hexdigest()
CREATOR_FP = hashlib.sha256(b"https://m.weibo.cn/u/5123456789012345").hexdigest()
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"


def _identity(note_id: str, listing: str = "listing") -> WeiboWorkIdentity:
    return WeiboWorkIdentity(note_id, hashlib.sha256(f"{note_id}:{listing}".encode()).hexdigest())


def _page(
    since_in: str,
    since_out: str,
    notes: tuple[str, ...],
    *,
    total: int | None = 100,
    listing: str = "listing",
) -> WeiboCreatorPage:
    return WeiboCreatorPage(since_in, since_out, total, tuple(_identity(note, listing) for note in notes))


def _state() -> WeiboScanState:
    return WeiboScanState.initial(ACCOUNT_ID, AUTHOR_FP, CREATOR_FP, UPSTREAM_SHA)


def _unit(state: WeiboScanState, max_items: int = 10) -> WeiboScanUnit:
    return WeiboScanUnit(state, max_items)


def _drive(unit: WeiboScanUnit, page: WeiboCreatorPage, *, fail: tuple[str, ...] = ()) -> None:
    assert unit.next_action().kind == "list"
    unit.observe_page(page)
    while (action := unit.next_action()).kind == "detail":
        identity = action.identity
        assert identity is not None
        if identity.note_id in fail:
            unit.fail(identity)
        else:
            unit.store(identity)


def test_cursor_round_trips_byte_exactly() -> None:
    state = _state()
    unit = _unit(state)
    _drive(unit, _page("", "next-since", ("1111111111", "2222222222"), listing="private-listing-sentinel"))
    coverage = unit.coverage()
    assert coverage.next_state.to_cursor().startswith(WB_SCAN_CURSOR_PREFIX)

    restored = WeiboScanState.from_cursor(coverage.next_state.to_cursor())

    assert restored == coverage.next_state
    assert restored.since_id == "next-since"
    assert restored.pages_consumed == 1
    # The listing digest is retained; the listing itself never is.
    assert "private-listing-sentinel" not in restored.to_cursor()


def test_cursor_rejects_a_binding_change() -> None:
    state = _state()
    unit = _unit(state)
    _drive(unit, _page("", "next-since", ("1111111111",)))
    cursor = unit.coverage().next_state.to_cursor()

    with pytest.raises(ValueError):
        WeiboScanState.for_cursor(
            cursor,
            account_id=ACCOUNT_ID,
            author_fingerprint_sha256=hashlib.sha256(b"other").hexdigest(),
            creator_fingerprint_sha256=CREATOR_FP,
            upstream_sha=UPSTREAM_SHA,
        )


def test_total_inferred_end_is_a_candidate_not_a_completeness_claim() -> None:
    state = _state()
    unit = _unit(state)
    # total == 10 with one page consumed: upstream's arithmetic stops here.
    _drive(unit, _page("", "next-since", tuple(f"{1000000000 + index}" for index in range(10)), total=10))

    coverage = unit.coverage()

    assert coverage.stop_reason == "total_inferred_end"
    assert coverage.source_end_observed is True
    assert coverage.summary.declared_total == 10
    assert coverage.summary.pages_consumed == 0
    assert coverage.next_state.head_boundary is not None
    # The inferred end keeps its evidence visible to an operator instead of
    # being flattened into a completeness flag.
    assert coverage.public_summary()["declared_total"] == 10
    assert coverage.public_summary()["page_complete"] is True


def test_missing_total_ends_the_first_page_under_its_own_code() -> None:
    unit = _unit(_state())
    _drive(unit, _page("", "", (), total=None))

    coverage = unit.coverage()

    assert coverage.stop_reason == "empty_page_end"
    assert coverage.summary.declared_total is None
    # An empty first page must not establish a head boundary: an empty boundary
    # reconciles equal to anything, which would let a rate-limited response read
    # as a complete history.
    assert coverage.next_state.head_boundary is None


def test_page_tail_is_replayed_by_the_identical_since_id() -> None:
    state = _state()
    notes = tuple(f"{2000000000 + index}" for index in range(WB_CREATOR_PAGE_SIZE))
    first = _unit(state, max_items=3)
    _drive(first, _page("", "page-2", notes))
    coverage = first.coverage()

    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.summary.page_complete is False
    assert coverage.next_state.since_id == ""
    assert coverage.next_state.witness is not None
    assert [item.note_id for item in coverage.successful] == list(notes[:3])

    # The next unit reissues the same request and skips delivered notes.
    second = _unit(coverage.next_state, max_items=3)
    assert second.next_action().since_id == ""
    second.observe_page(_page("", "page-2", notes))
    delivered: list[str] = []
    while (action := second.next_action()).kind == "detail":
        identity = action.identity
        assert identity is not None
        delivered.append(identity.note_id)
        second.store(identity)
    assert delivered == list(notes[3:6])


def test_advanced_cursor_is_replayed_verbatim() -> None:
    unit = _unit(_state(), max_items=1)
    _drive(unit, _page("", "opaque/echo+value=1", ("3333333333", "4444444444")))
    coverage = unit.coverage()

    assert coverage.next_state.since_id == ""
    assert coverage.next_state.witness is not None

    follow = _unit(coverage.next_state, max_items=10)
    assert follow.next_action().since_id == ""


def test_stalled_echo_blocks_after_a_bounded_number_of_units() -> None:
    notes = tuple(f"{3000000000 + index}" for index in range(10))
    # The first page advances the cursor; every later page then echoes the same
    # value, which upstream would re-request forever (client.py:411-412).
    unit = _unit(_state(), max_items=10)
    _drive(unit, _page("", "pinned", notes))
    state = unit.coverage().next_state
    assert state.since_id == "pinned" and state.stalled_units == 0

    for _ in range(WB_STALLED_UNIT_LIMIT):
        unit = _unit(state, max_items=10)
        _drive(unit, _page("pinned", "pinned", notes))
        coverage = unit.coverage()
        assert coverage.stop_reason == "unit_cap_reached"
        assert coverage.source_end_observed is False
        state = coverage.next_state

    assert state.stalled_units == WB_STALLED_UNIT_LIMIT
    unit = _unit(state, max_items=10)
    _drive(unit, _page("pinned", "pinned", notes))
    assert unit.coverage().blocked_code == WB_STALL_BLOCKED_CODE


def test_access_restriction_is_never_an_end() -> None:
    unit = _unit(_state())
    unit.observe_access_restricted()
    coverage = unit.coverage()

    assert coverage.stop_reason == "access_restricted"
    assert coverage.source_end_observed is False
    assert coverage.public_summary()["blocked_code"] is None
    assert coverage.next_state.head_boundary is None


def test_head_lane_reproduces_the_boundary_and_skips_unchanged_notes() -> None:
    state = _state()
    notes = ("4000000000", "4000000001")
    first = _unit(state)
    _drive(first, _page("", "next", notes, total=2))
    base = first.coverage().next_state

    head = _unit(base.for_head(), max_items=10)
    head.observe_page(_page("", "next", notes, total=2))
    action = head.next_action()

    assert action.kind == "unchanged"
    while (action := head.next_action()).kind == "unchanged":
        identity = action.identity
        assert identity is not None
        head.skip_unchanged(identity)
    coverage = head.coverage()
    assert coverage.stop_reason == "total_inferred_end"
    assert coverage.public_summary()["head_boundary_matches"] is True


def test_coverage_round_trips_through_its_json_line() -> None:
    unit = _unit(_state(), max_items=2)
    _drive(
        unit,
        _page("", "next", ("5000000000", "5000000001", "5000000002"), listing="coverage-listing-sentinel"),
        fail=("5000000001",),
    )
    coverage = unit.coverage()

    line = coverage.to_json_line()

    assert line.endswith("\n")
    assert WB_SCAN_COVERAGE_FILENAME.endswith(".jsonl")
    restored = WeiboScanCoverage.from_json_line(line)
    assert restored == coverage
    assert restored.summary.failed_count == 1
    assert "coverage-listing-sentinel" not in line


def test_failed_detail_does_not_hide_unrelated_notes() -> None:
    unit = _unit(_state(), max_items=5)
    _drive(unit, _page("", "next", ("6000000000", "6000000001", "6000000002")), fail=("6000000001",))

    coverage = unit.coverage()

    assert [item.note_id for item in coverage.successful] == ["6000000000", "6000000002"]
    assert [item.identity.note_id for item in coverage.failed] == ["6000000001"]
    assert coverage.stop_reason == "unit_cap_reached"


def test_page_rejects_a_mismatched_cursor() -> None:
    unit = _unit(_state())
    assert unit.next_action().kind == "list"
    with pytest.raises(ValueError):
        unit.observe_page(_page("different", "next", ("7000000000",)))


def test_inferred_end_ignores_the_observed_page_size() -> None:
    # A filtered page can carry fewer than WB_CREATOR_PAGE_SIZE notes while the
    # declared total still says more exists: upstream keeps going.
    unit = _unit(_state(), max_items=10)
    _drive(unit, _page("", "next", ("8000000000", "8000000001"), total=25))

    coverage = unit.coverage()
    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.next_state.since_id == "next"
    assert coverage.source_end_observed is False


def test_empty_filtered_page_with_advanced_cursor_advances() -> None:
    # A filtered page can be empty while the declared total still says more
    # exists; upstream keeps going, so the cursor must advance.
    unit = _unit(_state(), max_items=10)
    _drive(unit, _page("", "next", (), total=25))

    coverage = unit.coverage()

    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.next_state.since_id == "next"
    assert coverage.next_state.stalled_units == 0
    assert coverage.source_end_observed is False


def test_declared_total_beyond_the_durable_bound_is_rejected() -> None:
    """`cardlistInfo.total` is an unvalidated server integer.

    The durable column only accepts 2**53-1, so the scan layer must refuse
    anything larger instead of letting the progress-row flush fail inside the
    pipeline transaction and turn a completed unit into an endless retry.
    """

    identity = _identity("8100000001")
    with pytest.raises(ValueError):
        WeiboPageWitness("0", "1", 2**53, (identity,))
    with pytest.raises(ValueError):
        WeiboUnitSummary("history", "unit_cap_reached", 1, 0, 0, 1, 1, True, 2**53, 1)
    assert WeiboPageWitness("0", "1", 2**53 - 1, (identity,)).declared_total == 2**53 - 1
