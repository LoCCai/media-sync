from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from uuid import UUID

import pytest

from media_sync.integrations.mediacrawler.xhs_creator_notes import (
    XhsCreatorPage,
    XhsListingIdentity,
    XhsNoteIdentity,
    XhsScanCoverage,
    XhsScanState,
    XhsScanUnit,
)

ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000076")
AUTHOR_SHA = sha256(b"5f1234567890abcdef123456").hexdigest()
CREATOR_SHA = sha256(b"private-creator-url").hexdigest()
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"


def identity(index: int, *, token: str | None = None, listing: str | None = None) -> XhsNoteIdentity:
    return XhsNoteIdentity(
        f"{index:024x}",
        sha256((listing or f"listing-{index}").encode()).hexdigest(),
        sha256((token or f"token-{index}").encode()).hexdigest(),
        "pc_user",
    )


def page(cursor: str, next_cursor: str, indexes: range, *, has_more: bool) -> XhsCreatorPage:
    return XhsCreatorPage(cursor, next_cursor, has_more, tuple(identity(index) for index in indexes))


def initial() -> XhsScanState:
    return XhsScanState.initial(ACCOUNT_ID, AUTHOR_SHA, CREATOR_SHA, UPSTREAM_SHA)


def test_cursor_round_trip_is_canonical_and_public_summary_hides_cursors() -> None:
    # A generator is intentionally rejected rather than silently materialized.
    with pytest.raises(ValueError):
        replace(
            initial(),
            page_cursor="opaque.cursor/+==",
            head_boundary=(XhsListingIdentity(f"{index:024x}", "a" * 64) for index in range(3)),
        )

    state = replace(
        initial(),
        page_cursor="opaque.cursor/+==",
        head_boundary=tuple(XhsListingIdentity(f"{index:024x}", "a" * 64) for index in range(3)),
    )
    encoded = state.to_cursor()
    assert XhsScanState.from_cursor(encoded) == state
    assert (
        XhsScanState.for_cursor(
            encoded,
            account_id=ACCOUNT_ID,
            author_fingerprint_sha256=AUTHOR_SHA,
            creator_fingerprint_sha256=CREATOR_SHA,
            upstream_sha=UPSTREAM_SHA,
        )
        == state
    )
    public = state.public_summary()
    assert "opaque.cursor" not in repr(public)
    assert set(public) == {
        "version",
        "lane",
        "page_in_progress",
        "page_position",
        "head_boundary_established",
        "last_unit",
        "next_action",
    }


def test_small_item_cap_replays_same_page_then_advances_without_tail_loss() -> None:
    first_page = page("", "cursor-1", range(6), has_more=True)
    first = XhsScanUnit(initial(), 2)
    first.observe_page(first_page)
    first.store(first_page.identities[0])
    first.store(first_page.identities[1])
    first_coverage = first.coverage()
    assert first_coverage.stop_reason == "unit_cap_reached"
    assert first_coverage.next_state.page_cursor == ""
    assert first_coverage.next_state.index == 2
    assert first_coverage.next_state.witness == first_page.witness

    refreshed = XhsCreatorPage(
        "",
        "cursor-1",
        True,
        tuple(identity(index, token=f"fresh-{index}") for index in range(6)),
    )
    second = XhsScanUnit(first_coverage.next_state, 4)
    second.observe_page(refreshed)
    for item in refreshed.identities[2:]:
        second.store(item)
    second_coverage = second.coverage()
    assert second_coverage.next_state.page_cursor == "cursor-1"
    assert second_coverage.next_state.index == 0
    assert second_coverage.next_state.witness is None
    assert [item.note_id for item in first_coverage.successful + second_coverage.successful] == [
        f"{index:024x}" for index in range(6)
    ]


def test_three_opaque_cursor_steps_reach_only_real_source_end() -> None:
    state = initial()
    reasons: list[str] = []
    for source in (
        page("", "cursor-A", range(0, 2), has_more=True),
        page("cursor-A", "cursor-B", range(2, 4), has_more=True),
        page("cursor-B", "", range(4, 5), has_more=False),
    ):
        unit = XhsScanUnit(state, 30)
        unit.observe_page(source)
        for item in source.identities:
            unit.store(item)
        coverage = unit.coverage()
        coverage.validate(state, 30, tuple(item.note_id for item in source.identities))
        state = XhsScanCoverage.from_json_line(coverage.to_json_line()).next_state
        reasons.append(coverage.stop_reason)
    assert reasons == ["unit_cap_reached", "unit_cap_reached", "has_more_false"]
    assert state.head_boundary == tuple(identity(index).listing_identity for index in range(2))


def test_empty_has_more_page_and_access_restriction_never_claim_source_end() -> None:
    stalled = XhsScanUnit(initial(), 30)
    stalled.observe_page(page("", "", range(0), has_more=True))
    stalled_coverage = stalled.coverage()
    assert stalled_coverage.stop_reason == "empty_page_stalled"
    assert stalled_coverage.public_summary()["source_end_observed"] is False
    assert stalled_coverage.next_state.page_cursor == ""

    restricted = XhsScanUnit(initial(), 30)
    restricted.observe_access_restricted()
    restricted_coverage = restricted.coverage()
    restricted_coverage.validate(initial(), 30, ())
    assert restricted_coverage.stop_reason == "access_restricted"
    assert restricted_coverage.page is None
    assert restricted_coverage.public_summary()["source_end_observed"] is False


def test_failed_detail_advances_within_page_without_blocking_later_notes() -> None:
    source = page("", "", range(3), has_more=False)
    unit = XhsScanUnit(initial(), 30)
    unit.observe_page(source)
    unit.store(source.identities[0])
    unit.fail(source.identities[1])
    unit.store(source.identities[2])
    coverage = unit.coverage()
    coverage.validate(initial(), 30, (source.identities[0].note_id, source.identities[2].note_id))
    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.summary.page_complete is False
    assert coverage.summary.failed_count == 1
    assert [item.note_id for item in coverage.successful] == [
        source.identities[0].note_id,
        source.identities[2].note_id,
    ]

    retry_page = XhsCreatorPage(
        "",
        "",
        False,
        tuple(identity(index, token=f"retry-{index}") for index in range(3)),
    )
    retry = XhsScanUnit(coverage.next_state, 30)
    retry.observe_page(retry_page)
    action = retry.next_action()
    assert action.kind == "detail" and action.identity == retry_page.identities[1]
    retry.store(retry_page.identities[1])
    completed = retry.coverage()
    completed.validate(coverage.next_state, 30, (retry_page.identities[1].note_id,))
    assert completed.stop_reason == "has_more_false" and completed.summary.page_complete is True


def test_head_drift_is_visible_without_disclosing_token_or_cursor() -> None:
    source = page("", "next", range(2), has_more=True)
    history = XhsScanUnit(initial(), 30)
    history.observe_page(source)
    for item in source.identities:
        history.store(item)
    head_state = history.coverage().next_state.for_head()

    drifted = XhsCreatorPage(
        "",
        "different-next",
        True,
        (identity(99), *tuple(identity(index, token=f"new-{index}") for index in range(2))),
    )
    head = XhsScanUnit(head_state, 30)
    head.observe_page(drifted)
    while (action := head.next_action()).kind != "stop":
        assert action.identity is not None
        if action.kind == "unchanged":
            head.skip_unchanged(action.identity)
        else:
            head.store(action.identity)
    coverage = head.coverage()
    assert coverage.public_summary()["head_boundary_matches"] is False
    assert coverage.next_state.head_boundary == tuple(item.listing_identity for item in drifted.identities)
    visible = repr(coverage.public_summary())
    assert "different-next" not in visible
    assert all(item.token_sha256 not in visible for item in drifted.identities)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.replace("xhs-notes-v1:", "xhs-notes-v2:", 1),
        lambda value: value.replace(UPSTREAM_SHA, "f" * 40),
        lambda value: value[:-1],
    ],
)
def test_cursor_rejects_noncanonical_or_changed_binding(mutator) -> None:
    encoded = initial().to_cursor()
    changed = mutator(encoded)
    with pytest.raises(ValueError):
        if changed.startswith("xhs-notes-v1:") and changed.endswith("}"):
            XhsScanState.for_cursor(
                changed,
                account_id=ACCOUNT_ID,
                author_fingerprint_sha256=AUTHOR_SHA,
                creator_fingerprint_sha256=CREATOR_SHA,
                upstream_sha=UPSTREAM_SHA,
            )
        else:
            XhsScanState.from_cursor(changed)
