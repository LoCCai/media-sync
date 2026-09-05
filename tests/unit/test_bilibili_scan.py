from __future__ import annotations

import json
from dataclasses import replace
from uuid import UUID

import pytest

from media_sync.integrations.mediacrawler.bilibili_scan import (
    BILI_SCAN_CURSOR_PREFIX,
    BiliIdentity,
    BiliLane,
    BiliPage,
    BiliScanCoverage,
    BiliScanState,
    BiliScanUnit,
)

ACCOUNT = UUID("a45dd777-9633-4168-b432-677e6c7b97be")


def identity(number: int, timestamp: int | None = None) -> BiliIdentity:
    return BiliIdentity(str(number), f"BV{number:010d}", timestamp or 100_000 - number)


def initial() -> BiliScanState:
    return BiliScanState.initial(ACCOUNT, "a" * 64, "b" * 40)


def page(items: tuple[BiliIdentity, ...], number: int) -> BiliPage:
    return BiliPage(number, len(items), items[(number - 1) * 30 : number * 30])


def run(state: BiliScanState, items: tuple[BiliIdentity, ...], maximum: int = 1) -> BiliScanCoverage:
    unit = BiliScanUnit(state, maximum)
    actions = 0
    while (action := unit.next_action()).kind != "stop":
        actions += 1
        assert actions <= 32
        if action.kind == "list":
            assert action.page is not None
            unit.observe_page(page(items, action.page))
        else:
            assert action.identity is not None
            unit.consume(action.identity)
    result = unit.coverage()
    result.validate(state, maximum, tuple(row.aid for row in result.consumed))
    assert BiliScanCoverage.from_json_line(result.to_json_line()) == result
    assert BiliScanState.from_cursor(result.next_state.to_cursor()) == result.next_state
    return result


def test_initial_cursor_identity_and_legacy() -> None:
    state = initial()
    assert BiliScanState.from_cursor(state.to_cursor()) == state
    kwargs = dict(account_id=ACCOUNT, author_fingerprint_sha256="a" * 64, upstream_sha="b" * 40)
    assert BiliScanState.for_cursor(None, **kwargs) == state
    assert BiliScanState.for_cursor("legacy-cursor", **kwargs) == state
    assert BiliScanState.for_cursor(state.to_cursor(), **kwargs) == state
    for corrupt in ("bili-scan-v2:{}", "bili-scan-v1:[]", state.to_cursor() + " "):
        with pytest.raises(ValueError):
            BiliScanState.for_cursor(corrupt, **kwargs)
    with pytest.raises(ValueError):
        state.require_binding(**{**kwargs, "upstream_sha": "c" * 40})


@pytest.mark.parametrize("maximum", [1, 2, 7, 29, 30, 31, 100])
def test_more_than_thirty_is_reached_across_bounded_restarts(maximum: int) -> None:
    items = tuple(identity(number) for number in range(1, 68))
    state = initial()
    history_seen: set[str] = set()
    for iteration in range(180):
        result = run(state, items, maximum)
        assert result.lane == ("head" if iteration % 2 == 0 else "history")
        assert result.list_attempts <= 2
        assert result.detail_attempts <= min(maximum, 30)
        if result.lane == "history":
            history_seen.update(row.aid for row in result.consumed)
        state = result.next_state
        if history_seen == {row.aid for row in items} and state.head_boundary is not None:
            break
    assert history_seen == {row.aid for row in items}
    assert state.head_boundary == items[0].pubdate


def test_partial_pending_is_retained_without_requery() -> None:
    items = tuple(identity(number) for number in range(1, 36))
    first = run(initial(), items)
    assert first.next_state.head.index == 1
    assert first.next_state.head.witness == page(items, 1)
    history = run(first.next_state, items)
    resumed = run(history.next_state, items)
    assert resumed.list_attempts == 0
    assert resumed.consumed == (items[1],)


def test_detail_failure_cannot_produce_coverage_or_consume() -> None:
    unit = BiliScanUnit(initial(), 1)
    unit.observe_page(page((identity(1),), 1))
    assert unit.next_action().identity == identity(1)
    with pytest.raises(ValueError):
        unit.consume(identity(2))
    with pytest.raises(ValueError):
        unit.coverage()
    assert unit.current.index == 0
    assert unit.input_state == initial()


@pytest.mark.parametrize("mutation", ["insert", "delete", "same_second_reorder"])
def test_consumed_witness_drift_restarts_without_promoting_head(mutation: str) -> None:
    items = tuple(identity(number, 5000) for number in range(1, 32))
    state = replace(initial(), head=BiliLane(witness=page(items, 1), index=30), head_candidate=5000)
    changed = (
        (identity(99, 5000), *items)
        if mutation == "insert"
        else items[1:]
        if mutation == "delete"
        else (items[1], items[0], *items[2:])
    )
    result = run(state, changed, 30)
    assert result.stop_reason == "restarted"
    assert not result.consumed
    assert result.next_state.head == BiliLane()
    assert result.next_state.head_boundary is None
    assert result.next_state.head_candidate is None


def test_old_pending_head_boundary_is_revalidated_before_promotion() -> None:
    items = (identity(1, 1000), identity(2, 900))
    state = replace(initial(), head=BiliLane(witness=page(items, 1), index=1), head_boundary=950, head_candidate=1000)
    unit = BiliScanUnit(state, 30)
    assert unit.next_action().kind == "list"
    assert unit.state.head_boundary == 950
    unit.observe_page(page((identity(3, 1100), *items), 1))
    coverage = unit.coverage()
    assert coverage.stop_reason == "restarted"
    assert coverage.next_state.head_boundary == 950


def test_boundary_revalidation_keeps_same_second_items() -> None:
    items = (identity(1, 1000), identity(2, 1000), identity(3, 999))
    state = replace(initial(), head_boundary=1000)
    result = run(state, items, 30)
    assert result.consumed == items[:2]
    assert result.stop_reason == "head_boundary"
    assert result.list_attempts == 2
    assert result.next_state.head_boundary == 1000


def test_budget_exhaustion_keeps_final_consumed_page_witness() -> None:
    items = tuple(identity(number) for number in range(1, 32))
    state = replace(initial(), head=BiliLane(witness=page(items, 1), index=29), head_candidate=items[0].pubdate)
    result = run(state, items, 30)
    assert result.list_attempts == 2
    assert result.stop_reason == "list_limit"
    assert result.next_state.head.page == 2
    assert result.next_state.head.witness == page(items, 2)
    assert result.next_state.head.index == 1
    # No head boundary promotion until a later unit refreshes this witness.
    assert result.next_state.head_boundary is None


def test_history_never_applies_head_watermark_and_sweeps_again() -> None:
    state = replace(initial(), next_lane="history", head_boundary=999999)
    items = (identity(1),)
    first = run(state, items, 30)
    assert first.consumed == items
    assert first.stop_reason == "source_end"
    assert first.next_state.history == BiliLane()
    assert first.public_summary()["partial"] is True
    second = run(replace(first.next_state, next_lane="history"), items, 30)
    assert second.consumed == items


def test_pending_history_is_not_replaced_by_new_head_uploads() -> None:
    items = tuple(identity(number) for number in range(1, 35))
    state = run(run(initial(), items).next_state, items).next_state
    original_pending = state.history.witness
    for number in range(90, 95):
        items = (identity(number, 200000 + number), *items)
        state = run(state, items).next_state
        before = state.history.index
        state = run(state, items).next_state
        assert state.history.index == before + 1
        assert state.history.witness == original_pending


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("feed", "dynamics"),
        ("order", "click"),
        ("page_size", 1),
        ("next_lane", "other"),
        ("account_id", "bad"),
        ("head_boundary", True),
        ("upstream_sha", "x" * 40),
    ],
)
def test_cursor_closed_contract(field: str, value: object) -> None:
    item = json.loads(initial().to_cursor().removeprefix(BILI_SCAN_CURSOR_PREFIX))
    item[field] = value
    with pytest.raises(ValueError):
        BiliScanState.from_cursor(BILI_SCAN_CURSOR_PREFIX + json.dumps(item, sort_keys=True, separators=(",", ":")))


def test_duplicate_json_and_extra_sidecar_lines_rejected() -> None:
    with pytest.raises(ValueError):
        BiliScanState.from_cursor(BILI_SCAN_CURSOR_PREFIX + '{"x":1,"x":2}')
    result = run(initial(), (identity(1),))
    with pytest.raises(ValueError):
        BiliScanCoverage.from_json_line(result.to_json_line() + result.to_json_line())


@pytest.mark.parametrize("mutation", ["next_state", "counter", "lane", "reason", "consumed", "pages", "remote_ids"])
def test_coverage_replay_rejects_tamper(mutation: str) -> None:
    result = run(initial(), (identity(1),))
    changed = result
    remote_ids = ("1",)
    if mutation == "next_state":
        changed = replace(result, next_state=replace(result.next_state, head_boundary=999))
    elif mutation == "counter":
        changed = replace(result, summary=replace(result.summary, list_attempts=2))
    elif mutation == "lane":
        changed = replace(result, summary=replace(result.summary, lane="history"))
    elif mutation == "reason":
        changed = replace(result, summary=replace(result.summary, stop_reason="source_end"))
    elif mutation == "consumed":
        changed = replace(result, consumed=(identity(2),))
    elif mutation == "pages":
        changed = replace(result, pages=result.pages * 2)
    else:
        remote_ids = ("2",)
    with pytest.raises(ValueError):
        changed.validate(initial(), 1, remote_ids)


@pytest.mark.parametrize("value", [0, -1, True, 1.2])
def test_invalid_item_budget(value: int) -> None:
    with pytest.raises(ValueError):
        BiliScanUnit(initial(), value)


def test_zero_source_is_observation_not_complete() -> None:
    result = run(initial(), (), 30)
    assert result.stop_reason == "source_end"
    assert result.list_attempts == 1
    assert result.detail_attempts == 0
    assert result.next_state.head_boundary is None
    public = result.public_summary()
    assert public["source_end_observed"] is True
    assert "complete" not in public
