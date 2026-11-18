"""Closed, replayable Weibo creator-note pagination without disclosure.

The pinned upstream (``.upstream/MediaCrawler/media_platform/weibo/client.py:376-412``)
is the only source of the rules below:

* pagination is ``/api/container/getIndex`` keyed by ``containerid=107603<uid>``
  and a verbatim ``since_id`` cursor that starts empty and is echoed back in
  ``cardlistInfo.since_id``;
* the page size is **not** client-controlled: upstream advances an arithmetic
  counter by a hard-coded 10 per page and continues while
  ``cardlistInfo.total > counter`` (``client.py:411-412``);
* cards are filtered to ``card_type == 9`` *after* the page arrives, so the
  number of usable notes per page can be smaller than 10 — the arithmetic and
  the observed content therefore disagree by design;
* a falsy response is treated as a possible ban (``client.py:401-403``) and a
  missing ``cards`` key breaks the loop (``client.py:404-406``); neither is
  evidence of a source end.

Because the end signal is an *inference* over a declared total, this module never
lets an inferred end claim completeness: it keeps the declared total, the pages
consumed and the page witness so a later head reconciliation can confirm or
reject the boundary.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

WB_SCAN_CURSOR_PREFIX = "wb-work-v1:"
WB_SCAN_COVERAGE_FILENAME = "_media_sync_weibo_coverage.jsonl"
WB_SCAN_IDENTITY_FIELD = "__media_sync_weibo_note_identity"
WB_CREATOR_PAGE_SIZE = 10
WB_SCAN_STOP_REASONS = frozenset({"total_inferred_end", "empty_page_end", "access_restricted", "unit_cap_reached"})
WB_STALLED_UNIT_LIMIT = 3
WB_STALL_BLOCKED_CODE = "weibo_cursor_stalled"

_MAX_CURSOR_VALUE = 4_096
_MAX_CURSOR_PAYLOAD = 65_536
_MAX_COVERAGE_PAYLOAD = 131_072
_MAX_UNIT_ITEMS = 1_000
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_NOTE_ID = re.compile(r"[0-9]{10,20}\Z")
_OUTCOME_STATUSES = frozenset({"stored", "unchanged", "detail_unavailable", "access_restricted"})


def _invalid() -> ValueError:
    return ValueError("invalid Weibo creator-note scan contract")


def _integer(value: object, low: int = 0, high: int = 2**63 - 1) -> int:
    if type(value) is not int or not low <= value <= high:
        raise _invalid()
    return value


def _mapping(value: object, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise _invalid()
    return value


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def _json(value: str, maximum: int) -> object:
    if type(value) is not str or len(value) > maximum:
        raise _invalid()
    try:
        return json.loads(value, object_pairs_hook=_pairs, parse_constant=lambda _: (_ for _ in ()).throw(_invalid()))
    except (ValueError, RecursionError, TypeError) as error:
        raise _invalid() from error


def _dump(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise _invalid() from error


def _opaque_cursor(value: object) -> str:
    if type(value) is not str or len(value) > _MAX_CURSOR_VALUE:
        raise _invalid()
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise _invalid()
    return value


def _note_ids(value: object) -> tuple[str, ...]:
    if type(value) is not list or len(value) > _MAX_UNIT_ITEMS:
        raise _invalid()
    result = tuple(value)
    if any(type(item) is not str or _NOTE_ID.fullmatch(item) is None for item in result):
        raise _invalid()
    if len(set(result)) != len(result):
        raise _invalid()
    return result


@dataclass(frozen=True, slots=True)
class WeiboWorkIdentity:
    """One listed note reduced to the stable ``mblog.id`` and listing digest."""

    note_id: str
    listing_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.note_id) is not str
            or _NOTE_ID.fullmatch(self.note_id) is None
            or type(self.listing_sha256) is not str
            or _SHA256.fullmatch(self.listing_sha256) is None
        ):
            raise _invalid()

    def as_mapping(self) -> dict[str, str]:
        return {"note_id": self.note_id, "listing_sha256": self.listing_sha256}

    @classmethod
    def from_mapping(cls, value: object) -> WeiboWorkIdentity:
        return cls(**_mapping(value, {"note_id", "listing_sha256"}))


@dataclass(frozen=True, slots=True)
class WeiboPageWitness:
    """One page's exact continuation facts, persisted without any content."""

    input_since_id: str
    next_since_id: str
    declared_total: int | None
    identities: tuple[WeiboWorkIdentity, ...]

    def __post_init__(self) -> None:
        _opaque_cursor(self.input_since_id)
        _opaque_cursor(self.next_since_id)
        if self.declared_total is not None:
            _integer(self.declared_total)
        if type(self.identities) is not tuple or any(type(item) is not WeiboWorkIdentity for item in self.identities):
            raise _invalid()
        if len({item.note_id for item in self.identities}) != len(self.identities):
            raise _invalid()

    @property
    def note_ids(self) -> tuple[str, ...]:
        return tuple(item.note_id for item in self.identities)

    def as_mapping(self) -> dict[str, object]:
        return {
            "input_since_id": self.input_since_id,
            "next_since_id": self.next_since_id,
            "declared_total": self.declared_total,
            "identities": [item.as_mapping() for item in self.identities],
        }

    @classmethod
    def from_mapping(cls, value: object) -> WeiboPageWitness:
        item = _mapping(value, {"input_since_id", "next_since_id", "declared_total", "identities"})
        identities = item["identities"]
        if type(identities) is not list:
            raise _invalid()
        return cls(
            item["input_since_id"],
            item["next_since_id"],
            item["declared_total"],
            tuple(WeiboWorkIdentity.from_mapping(row) for row in identities),
        )


@dataclass(frozen=True, slots=True)
class WeiboCreatorPage:
    """One exact list response reduced to bounded note identities."""

    input_since_id: str
    next_since_id: str
    declared_total: int | None
    identities: tuple[WeiboWorkIdentity, ...]

    def __post_init__(self) -> None:
        witness = self.witness
        if witness.note_ids != tuple(item.note_id for item in self.identities):
            raise _invalid()

    @property
    def witness(self) -> WeiboPageWitness:
        return WeiboPageWitness(self.input_since_id, self.next_since_id, self.declared_total, self.identities)

    def ends_after(self, pages_consumed: int) -> bool:
        """Mirror upstream's arithmetic for the page just consumed.

        Upstream advances ``crawler_total_count`` by a hard-coded 10 per page and
        keeps going while ``cardlistInfo.total > counter`` (client.py:411-412).
        A missing ``total`` is upstream's default zero, so the first page ends.
        """

        if type(pages_consumed) is not int or pages_consumed < 1:
            raise _invalid()
        total = 0 if self.declared_total is None else self.declared_total
        return not total > pages_consumed * WB_CREATOR_PAGE_SIZE

    def as_mapping(self) -> dict[str, object]:
        return self.witness.as_mapping()

    @classmethod
    def from_mapping(cls, value: object) -> WeiboCreatorPage:
        item = _mapping(value, {"input_since_id", "next_since_id", "declared_total", "identities"})
        identities = item["identities"]
        if type(identities) is not list:
            raise _invalid()
        return cls(
            item["input_since_id"],
            item["next_since_id"],
            item["declared_total"],
            tuple(WeiboWorkIdentity.from_mapping(row) for row in identities),
        )


@dataclass(frozen=True, slots=True)
class WeiboWorkOutcome:
    identity: WeiboWorkIdentity
    status: str

    def __post_init__(self) -> None:
        if type(self.identity) is not WeiboWorkIdentity or self.status not in _OUTCOME_STATUSES:
            raise _invalid()

    def as_mapping(self) -> dict[str, object]:
        return {"identity": self.identity.as_mapping(), "status": self.status}

    @classmethod
    def from_mapping(cls, value: object) -> WeiboWorkOutcome:
        item = _mapping(value, {"identity", "status"})
        return cls(WeiboWorkIdentity.from_mapping(item["identity"]), item["status"])


@dataclass(frozen=True, slots=True)
class WeiboUnitSummary:
    lane: str
    stop_reason: str
    stored_count: int
    unchanged_count: int
    failed_count: int
    list_attempts: int
    detail_attempts: int
    page_complete: bool
    declared_total: int | None
    pages_consumed: int

    def __post_init__(self) -> None:
        if self.lane not in {"history", "head"} or self.stop_reason not in WB_SCAN_STOP_REASONS:
            raise _invalid()
        _integer(self.stored_count, 0, _MAX_UNIT_ITEMS)
        _integer(self.unchanged_count, 0, _MAX_UNIT_ITEMS)
        _integer(self.failed_count, 0, _MAX_UNIT_ITEMS)
        _integer(self.list_attempts, 1, 1)
        _integer(self.detail_attempts, 0, _MAX_UNIT_ITEMS)
        _integer(self.pages_consumed, 0, _MAX_UNIT_ITEMS)
        if self.declared_total is not None:
            _integer(self.declared_total)
        if (
            self.detail_attempts != self.stored_count + self.failed_count
            or self.stored_count + self.unchanged_count + self.failed_count > _MAX_UNIT_ITEMS
            or type(self.page_complete) is not bool
        ):
            raise _invalid()

    def as_mapping(self) -> dict[str, object]:
        return {
            "lane": self.lane,
            "stop_reason": self.stop_reason,
            "stored_count": self.stored_count,
            "unchanged_count": self.unchanged_count,
            "failed_count": self.failed_count,
            "list_attempts": self.list_attempts,
            "detail_attempts": self.detail_attempts,
            "page_complete": self.page_complete,
            "declared_total": self.declared_total,
            "pages_consumed": self.pages_consumed,
        }

    @classmethod
    def from_mapping(cls, value: object) -> WeiboUnitSummary:
        return cls(
            **_mapping(
                value,
                {
                    "lane",
                    "stop_reason",
                    "stored_count",
                    "unchanged_count",
                    "failed_count",
                    "list_attempts",
                    "detail_attempts",
                    "page_complete",
                    "declared_total",
                    "pages_consumed",
                },
            )
        )


@dataclass(frozen=True, slots=True)
class WeiboScanState:
    account_id: UUID
    author_fingerprint_sha256: str
    creator_fingerprint_sha256: str
    upstream_sha: str
    lane: str = "history"
    since_id: str = ""
    witness: WeiboPageWitness | None = None
    index: int = 0
    completed_note_ids: tuple[str, ...] = ()
    head_boundary: tuple[WeiboWorkIdentity, ...] | None = None
    last_unit: WeiboUnitSummary | None = None
    stalled_units: int = 0
    pages_consumed: int = 0

    def __post_init__(self) -> None:
        if (
            type(self.account_id) is not UUID
            or type(self.author_fingerprint_sha256) is not str
            or _SHA256.fullmatch(self.author_fingerprint_sha256) is None
            or type(self.creator_fingerprint_sha256) is not str
            or _SHA256.fullmatch(self.creator_fingerprint_sha256) is None
            or type(self.upstream_sha) is not str
            or _SHA1.fullmatch(self.upstream_sha) is None
            or self.lane not in {"history", "head"}
        ):
            raise _invalid()
        _opaque_cursor(self.since_id)
        _integer(self.index)
        _integer(self.stalled_units, 0, _MAX_UNIT_ITEMS)
        _integer(self.pages_consumed, 0, _MAX_UNIT_ITEMS)
        if type(self.completed_note_ids) is not tuple:
            raise _invalid()
        _note_ids(list(self.completed_note_ids))
        if self.witness is not None and (
            type(self.witness) is not WeiboPageWitness
            or self.witness.input_since_id != self.since_id
            or self.index > len(self.witness.note_ids)
        ):
            raise _invalid()
        if self.witness is None and self.index:
            raise _invalid()
        if self.witness is None and self.completed_note_ids:
            raise _invalid()
        if self.witness is not None and not set(self.completed_note_ids).issubset(self.witness.note_ids):
            raise _invalid()
        if self.head_boundary is not None:
            if type(self.head_boundary) is not tuple or any(
                type(item) is not WeiboWorkIdentity for item in self.head_boundary
            ):
                raise _invalid()
            if len({item.note_id for item in self.head_boundary}) != len(self.head_boundary):
                raise _invalid()
        if self.last_unit is not None and type(self.last_unit) is not WeiboUnitSummary:
            raise _invalid()

    @classmethod
    def initial(
        cls,
        account_id: UUID,
        author_fingerprint_sha256: str,
        creator_fingerprint_sha256: str,
        upstream_sha: str,
    ) -> WeiboScanState:
        return cls(account_id, author_fingerprint_sha256, creator_fingerprint_sha256, upstream_sha)

    def require_binding(
        self,
        *,
        account_id: UUID,
        author_fingerprint_sha256: str,
        creator_fingerprint_sha256: str,
        upstream_sha: str,
    ) -> None:
        if (
            self.account_id,
            self.author_fingerprint_sha256,
            self.creator_fingerprint_sha256,
            self.upstream_sha,
        ) != (account_id, author_fingerprint_sha256, creator_fingerprint_sha256, upstream_sha):
            raise _invalid()

    def record_scan(self) -> int:
        """Return the bounded history position used for the arithmetic mirror."""

        return self.pages_consumed

    def for_head(self) -> WeiboScanState:
        if self.head_boundary is None:
            raise _invalid()
        return replace(
            self,
            lane="head",
            since_id="",
            witness=None,
            index=0,
            completed_note_ids=(),
            last_unit=None,
            stalled_units=0,
        )

    def to_cursor(self) -> str:
        payload = {
            "schema_version": 1,
            "feed": "creator_notes",
            "account_id": str(self.account_id),
            "author_fingerprint_sha256": self.author_fingerprint_sha256,
            "creator_fingerprint_sha256": self.creator_fingerprint_sha256,
            "upstream_sha": self.upstream_sha,
            "lane": self.lane,
            "since_id": self.since_id,
            "witness": None if self.witness is None else self.witness.as_mapping(),
            "index": self.index,
            "completed_note_ids": list(self.completed_note_ids),
            "head_boundary": None if self.head_boundary is None else [item.as_mapping() for item in self.head_boundary],
            "stalled_units": self.stalled_units,
            "pages_consumed": self.pages_consumed,
            "last_unit": None if self.last_unit is None else self.last_unit.as_mapping(),
        }
        result = WB_SCAN_CURSOR_PREFIX + _dump(payload)
        if len(result) > _MAX_CURSOR_PAYLOAD:
            raise _invalid()
        return result

    @classmethod
    def from_cursor(cls, value: str) -> WeiboScanState:
        if type(value) is not str or not value.startswith(WB_SCAN_CURSOR_PREFIX):
            raise _invalid()
        item = _mapping(
            _json(value[len(WB_SCAN_CURSOR_PREFIX) :], _MAX_CURSOR_PAYLOAD),
            {
                "schema_version",
                "feed",
                "account_id",
                "author_fingerprint_sha256",
                "creator_fingerprint_sha256",
                "upstream_sha",
                "lane",
                "since_id",
                "witness",
                "index",
                "completed_note_ids",
                "head_boundary",
                "stalled_units",
                "pages_consumed",
                "last_unit",
            },
        )
        if item["schema_version"] != 1 or item["feed"] != "creator_notes":
            raise _invalid()
        try:
            account_id = UUID(item["account_id"])
        except (AttributeError, TypeError, ValueError) as error:
            raise _invalid() from error
        if str(account_id) != item["account_id"]:
            raise _invalid()
        result = cls(
            account_id,
            item["author_fingerprint_sha256"],
            item["creator_fingerprint_sha256"],
            item["upstream_sha"],
            item["lane"],
            item["since_id"],
            None if item["witness"] is None else WeiboPageWitness.from_mapping(item["witness"]),
            item["index"],
            _note_ids(item["completed_note_ids"]),
            (
                None
                if item["head_boundary"] is None
                else tuple(WeiboWorkIdentity.from_mapping(row) for row in item["head_boundary"])
            ),
            None if item["last_unit"] is None else WeiboUnitSummary.from_mapping(item["last_unit"]),
            item["stalled_units"],
            item["pages_consumed"],
        )
        if result.to_cursor() != value:
            raise _invalid()
        return result

    @classmethod
    def for_cursor(
        cls,
        value: str | None,
        *,
        account_id: UUID,
        author_fingerprint_sha256: str,
        creator_fingerprint_sha256: str,
        upstream_sha: str,
    ) -> WeiboScanState:
        if value is not None and type(value) is not str:
            raise _invalid()
        if value is None:
            return cls.initial(account_id, author_fingerprint_sha256, creator_fingerprint_sha256, upstream_sha)
        if not value.startswith(WB_SCAN_CURSOR_PREFIX):
            raise _invalid()
        state = cls.from_cursor(value)
        state.require_binding(
            account_id=account_id,
            author_fingerprint_sha256=author_fingerprint_sha256,
            creator_fingerprint_sha256=creator_fingerprint_sha256,
            upstream_sha=upstream_sha,
        )
        return state

    def public_summary(self) -> dict[str, object]:
        return {
            "version": 1,
            "lane": self.lane,
            "page_in_progress": self.witness is not None,
            "page_position": self.index,
            "pages_consumed": self.pages_consumed,
            "head_boundary_established": self.head_boundary is not None,
            "stalled_units": self.stalled_units,
            "last_unit": None if self.last_unit is None else self.last_unit.as_mapping(),
            "next_action": f"continue_{self.lane}",
        }


@dataclass(frozen=True, slots=True)
class WeiboScanAction:
    kind: str
    since_id: str | None = None
    identity: WeiboWorkIdentity | None = None


class WeiboScanUnit:
    """One page-bound proposal over the ``since_id`` chain."""

    def __init__(self, state: WeiboScanState, max_items: int):
        if type(state) is not WeiboScanState:
            raise _invalid()
        # Upstream's page size is a hard-coded arithmetic constant, not a
        # request parameter, so the durable cap is max_items alone.
        self.limit = _integer(max_items, 1, _MAX_UNIT_ITEMS)
        self.input_state = state
        self.state = state
        self.page: WeiboCreatorPage | None = None
        self.outcomes: list[WeiboWorkOutcome] = []
        self.reason: str | None = None

    def next_action(self) -> WeiboScanAction:
        if self.reason is not None:
            return WeiboScanAction("stop")
        if self.page is None:
            return WeiboScanAction("list", since_id=self.state.since_id)
        while (
            self.state.index < len(self.page.identities)
            and self.page.identities[self.state.index].note_id in self.state.completed_note_ids
        ):
            self.state = replace(self.state, index=self.state.index + 1)
        if self.state.index >= len(self.page.identities):
            self._finish_page()
            return WeiboScanAction("stop")
        if len(self.outcomes) >= self.limit:
            self.reason = "unit_cap_reached"
            return WeiboScanAction("stop")
        identity = self.page.identities[self.state.index]
        prior = {item.note_id: item.listing_sha256 for item in self.state.head_boundary or ()}
        if self.state.lane == "head" and prior.get(identity.note_id) == identity.listing_sha256:
            return WeiboScanAction("unchanged", identity=identity)
        return WeiboScanAction("detail", identity=identity)

    def observe_page(self, page: WeiboCreatorPage) -> None:
        action = self.next_action()
        if action.kind != "list" or type(page) is not WeiboCreatorPage or page.input_since_id != action.since_id:
            raise _invalid()
        if self.state.witness is not None:
            expected = self.state.witness
            observed = page.witness
            if (observed.input_since_id, observed.next_since_id, observed.note_ids) != (
                expected.input_since_id,
                expected.next_since_id,
                expected.note_ids,
            ):
                raise _invalid()
            prior_fingerprints = {item.note_id: item.listing_sha256 for item in expected.identities}
            completed = tuple(
                item.note_id
                for item in observed.identities
                if item.note_id in self.state.completed_note_ids
                and prior_fingerprints.get(item.note_id) == item.listing_sha256
            )
            self.state = replace(self.state, witness=observed, index=0, completed_note_ids=completed)
        self.page = page
        if self.state.witness is None:
            self.state = replace(self.state, witness=page.witness)
        if self.state.lane == "history" and self.state.since_id == "" and self.state.head_boundary is None:
            self.state = replace(self.state, head_boundary=page.witness.identities)

    def observe_access_restricted(self) -> None:
        if self.next_action().kind != "list":
            raise _invalid()
        self.reason = "access_restricted"

    def store(self, identity: WeiboWorkIdentity) -> None:
        self._record(identity, "stored")

    def skip_unchanged(self, identity: WeiboWorkIdentity) -> None:
        self._record(identity, "unchanged")

    def fail(self, identity: WeiboWorkIdentity, *, access_restricted: bool = False) -> None:
        failed_index = self.state.index
        self._record(identity, "access_restricted" if access_restricted else "detail_unavailable")
        if access_restricted:
            self.state = replace(self.state, index=failed_index)
            self.reason = "access_restricted"

    def _record(self, identity: WeiboWorkIdentity, status: str) -> None:
        action = self.next_action()
        expected_kind = "unchanged" if status == "unchanged" else "detail"
        if action.kind != expected_kind or identity != action.identity:
            raise _invalid()
        self.outcomes.append(WeiboWorkOutcome(identity, status))
        completed = self.state.completed_note_ids
        if status in {"stored", "unchanged"} and identity.note_id not in completed:
            completed = (*completed, identity.note_id)
        self.state = replace(self.state, index=self.state.index + 1, completed_note_ids=completed)

    def _finish_page(self) -> None:
        page = self.page
        if page is None:
            raise _invalid()
        if len(self.state.completed_note_ids) != len(page.identities):
            # max_items (or a failed detail) stopped the unit before the page
            # tail: retain the identical since_id and witness so the next unit
            # re-issues the same request and skips already-delivered notes.
            self.reason = "unit_cap_reached"
            self.state = replace(self.state, index=0)
            return
        if self.state.lane == "head":
            self._finish_head(page)
            return
        pages_consumed = self.state.pages_consumed + 1
        stalled = page.next_since_id == page.input_since_id
        if page.declared_total is None and not page.identities:
            # Nothing listed and no total to infer from: upstream's default
            # zero ends the loop, but the evidence is weaker than a declared
            # total, so it keeps its own code.
            self.reason = "empty_page_end"
            self.state = replace(
                self.state,
                since_id="",
                witness=None,
                index=0,
                completed_note_ids=(),
                stalled_units=0,
                pages_consumed=0,
            )
        elif page.ends_after(pages_consumed):
            # Arithmetic inference over cardlistInfo.total: a time-bounded end
            # candidate, never a completeness proof.
            self.reason = "total_inferred_end"
            self.state = replace(
                self.state,
                since_id="",
                witness=None,
                index=0,
                completed_note_ids=(),
                stalled_units=0,
                pages_consumed=0,
            )
        elif stalled:
            # The echoed cursor repeats its input, so the next unit would issue
            # the identical request forever; upstream never checks this
            # (client.py:411-412).  Retain the page for skip-on-replay and count
            # the stall toward the bounded blocked transition.
            self.reason = "unit_cap_reached"
            self.state = replace(
                self.state,
                index=0,
                pages_consumed=pages_consumed,
                stalled_units=self.state.stalled_units + 1,
            )
        else:
            self.reason = "unit_cap_reached"
            self.state = replace(
                self.state,
                since_id=page.next_since_id,
                witness=None,
                index=0,
                completed_note_ids=(),
                stalled_units=0,
                pages_consumed=pages_consumed,
            )

    def _finish_head(self, page: WeiboCreatorPage) -> None:
        if page.ends_after(1):
            self.reason = "total_inferred_end"
        else:
            self.reason = "unit_cap_reached"
        self.state = replace(
            self.state,
            since_id="",
            witness=None,
            index=0,
            completed_note_ids=(),
            stalled_units=0,
            pages_consumed=0,
            head_boundary=page.witness.identities,
        )

    def coverage(self) -> WeiboScanCoverage:
        if self.next_action().kind != "stop" or self.reason is None:
            raise _invalid()
        page_complete = self.page is not None and self.state.witness is None
        summary = WeiboUnitSummary(
            self.input_state.lane,
            self.reason,
            sum(item.status == "stored" for item in self.outcomes),
            sum(item.status == "unchanged" for item in self.outcomes),
            sum(item.status not in {"stored", "unchanged"} for item in self.outcomes),
            1,
            sum(item.status != "unchanged" for item in self.outcomes),
            page_complete,
            None if self.page is None else self.page.declared_total,
            self.state.pages_consumed,
        )
        next_state = replace(self.state, last_unit=summary)
        return WeiboScanCoverage(self.input_state, next_state, self.page, tuple(self.outcomes), summary)


@dataclass(frozen=True, slots=True)
class WeiboScanCoverage:
    input_state: WeiboScanState
    next_state: WeiboScanState
    page: WeiboCreatorPage | None
    outcomes: tuple[WeiboWorkOutcome, ...]
    summary: WeiboUnitSummary

    @property
    def successful(self) -> tuple[WeiboWorkIdentity, ...]:
        return tuple(item.identity for item in self.outcomes if item.status == "stored")

    @property
    def failed(self) -> tuple[WeiboWorkOutcome, ...]:
        return tuple(item for item in self.outcomes if item.status not in {"stored", "unchanged"})

    @property
    def stop_reason(self) -> str:
        return self.summary.stop_reason

    @property
    def lane(self) -> str:
        return self.summary.lane

    @property
    def source_end_observed(self) -> bool:
        """Only the arithmetic candidate; never a completeness claim."""

        return self.summary.stop_reason in {"total_inferred_end", "empty_page_end"}

    @property
    def blocked_code(self) -> str | None:
        if self.next_state.stalled_units >= WB_STALLED_UNIT_LIMIT:
            return WB_STALL_BLOCKED_CODE
        return None

    def validate(
        self,
        input_state: WeiboScanState,
        max_items: int,
        normalized_remote_ids: tuple[str, ...] | None = None,
    ) -> None:
        if (
            type(input_state) is not WeiboScanState
            or self.input_state != input_state
            or type(self.outcomes) is not tuple
            or len(self.outcomes) > max_items
        ):
            raise _invalid()
        unit = WeiboScanUnit(input_state, max_items)
        if self.page is None:
            unit.observe_access_restricted()
        else:
            unit.observe_page(self.page)
            for outcome in self.outcomes:
                if outcome.status == "stored":
                    unit.store(outcome.identity)
                elif outcome.status == "unchanged":
                    unit.skip_unchanged(outcome.identity)
                else:
                    unit.fail(outcome.identity, access_restricted=outcome.status == "access_restricted")
        if unit.coverage() != self:
            raise _invalid()
        if (
            normalized_remote_ids is not None
            and tuple(item.note_id for item in self.successful) != normalized_remote_ids
        ):
            raise _invalid()

    def to_json_line(self) -> str:
        payload = _dump(
            {
                "schema_version": 1,
                "input_cursor": self.input_state.to_cursor(),
                "next_cursor": self.next_state.to_cursor(),
                "page": None if self.page is None else self.page.as_mapping(),
                "outcomes": [item.as_mapping() for item in self.outcomes],
                **self.summary.as_mapping(),
            }
        )
        if len(payload) > _MAX_COVERAGE_PAYLOAD:
            raise _invalid()
        return payload + "\n"

    @classmethod
    def from_json_line(cls, value: str) -> WeiboScanCoverage:
        if type(value) is not str or not value.endswith("\n") or len(value.splitlines()) != 1:
            raise _invalid()
        item = _mapping(
            _json(value, _MAX_COVERAGE_PAYLOAD),
            {
                "schema_version",
                "input_cursor",
                "next_cursor",
                "page",
                "outcomes",
                "lane",
                "stop_reason",
                "stored_count",
                "unchanged_count",
                "failed_count",
                "list_attempts",
                "detail_attempts",
                "page_complete",
                "declared_total",
                "pages_consumed",
            },
        )
        if item["schema_version"] != 1 or type(item["outcomes"]) is not list:
            raise _invalid()
        result = cls(
            WeiboScanState.from_cursor(item["input_cursor"]),
            WeiboScanState.from_cursor(item["next_cursor"]),
            None if item["page"] is None else WeiboCreatorPage.from_mapping(item["page"]),
            tuple(WeiboWorkOutcome.from_mapping(row) for row in item["outcomes"]),
            WeiboUnitSummary.from_mapping(
                {
                    key: item[key]
                    for key in (
                        "lane",
                        "stop_reason",
                        "stored_count",
                        "unchanged_count",
                        "failed_count",
                        "list_attempts",
                        "detail_attempts",
                        "page_complete",
                        "declared_total",
                        "pages_consumed",
                    )
                }
            ),
        )
        if result.to_json_line() != value:
            raise _invalid()
        return result

    def public_summary(self) -> dict[str, object]:
        return {
            **self.summary.as_mapping(),
            "partial": bool(self.failed),
            "source_end_observed": self.source_end_observed,
            "head_boundary_matches": (
                None
                if self.page is None or self.input_state.lane != "head"
                else self.input_state.head_boundary == self.page.witness.identities
            ),
            "stalled_units": self.next_state.stalled_units,
            "blocked_code": self.blocked_code,
            "next_action": f"continue_{self.next_state.lane}",
        }


__all__ = [
    "WB_CREATOR_PAGE_SIZE",
    "WB_SCAN_COVERAGE_FILENAME",
    "WB_SCAN_CURSOR_PREFIX",
    "WB_SCAN_IDENTITY_FIELD",
    "WB_SCAN_STOP_REASONS",
    "WB_STALLED_UNIT_LIMIT",
    "WB_STALL_BLOCKED_CODE",
    "WeiboCreatorPage",
    "WeiboPageWitness",
    "WeiboScanAction",
    "WeiboScanCoverage",
    "WeiboScanState",
    "WeiboScanUnit",
    "WeiboUnitSummary",
    "WeiboWorkIdentity",
    "WeiboWorkOutcome",
]
