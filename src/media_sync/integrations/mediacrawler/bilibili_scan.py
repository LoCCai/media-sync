"""Closed, replayable bounded ordinary-upload scan state; no network authority."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

BILI_SCAN_CURSOR_PREFIX = "bili-scan-v1:"
BILI_SCAN_COVERAGE_FILENAME = "_media_sync_bili_coverage.jsonl"
BILI_SCAN_IDENTITY_FIELD = "__media_sync_bili_scan_identity"
BILI_SCAN_PAGE_SIZE = 30
_MAX_CURSOR = 24_576
_MAX_COVERAGE = 131_072
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_BVID = re.compile(r"BV[0-9A-Za-z]{10}\Z")
_REASONS = {"item_limit", "list_limit", "restarted", "source_end", "head_boundary"}


def _invalid() -> ValueError:
    return ValueError("invalid Bilibili bounded scan contract")


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
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True, slots=True)
class BiliIdentity:
    aid: str
    bvid: str
    pubdate: int

    def __post_init__(self) -> None:
        if type(self.aid) is not str or re.fullmatch(r"[1-9][0-9]{0,18}", self.aid) is None:
            raise _invalid()
        _integer(int(self.aid), 1)
        if type(self.bvid) is not str or _BVID.fullmatch(self.bvid) is None:
            raise _invalid()
        _integer(self.pubdate, 1, 253_402_300_799)

    def as_mapping(self) -> dict[str, object]:
        return {"aid": self.aid, "bvid": self.bvid, "pubdate": self.pubdate}

    @classmethod
    def from_mapping(cls, value: object) -> BiliIdentity:
        item = _mapping(value, {"aid", "bvid", "pubdate"})
        return cls(**item)


@dataclass(frozen=True, slots=True)
class BiliPage:
    page: int
    total: int
    identities: tuple[BiliIdentity, ...]

    def __post_init__(self) -> None:
        _integer(self.page, 1, 10_000_000)
        _integer(self.total, 0, 300_000_000)
        if type(self.identities) is not tuple or any(type(item) is not BiliIdentity for item in self.identities):
            raise _invalid()
        expected = min(BILI_SCAN_PAGE_SIZE, max(0, self.total - (self.page - 1) * BILI_SCAN_PAGE_SIZE))
        if len(self.identities) != expected:
            raise _invalid()
        if len({item.aid for item in self.identities}) != len(self.identities) or len(
            {item.bvid for item in self.identities}
        ) != len(self.identities):
            raise _invalid()
        if any(left.pubdate < right.pubdate for left, right in zip(self.identities, self.identities[1:], strict=False)):
            raise _invalid()

    @property
    def source_end(self) -> bool:
        return self.page * BILI_SCAN_PAGE_SIZE >= self.total

    def as_mapping(self) -> dict[str, object]:
        return {"page": self.page, "total": self.total, "identities": [item.as_mapping() for item in self.identities]}

    @classmethod
    def from_mapping(cls, value: object) -> BiliPage:
        item = _mapping(value, {"page", "total", "identities"})
        if type(item["identities"]) is not list or len(item["identities"]) > BILI_SCAN_PAGE_SIZE:
            raise _invalid()
        return cls(item["page"], item["total"], tuple(BiliIdentity.from_mapping(row) for row in item["identities"]))


@dataclass(frozen=True, slots=True)
class BiliLane:
    page: int = 1
    witness: BiliPage | None = None
    index: int = 0
    previous_pubdate: int | None = None

    def __post_init__(self) -> None:
        _integer(self.page, 1, 10_000_000)
        _integer(self.index, 0, BILI_SCAN_PAGE_SIZE)
        if self.witness is not None and (
            type(self.witness) is not BiliPage
            or self.witness.page != self.page
            or self.index > len(self.witness.identities)
        ):
            raise _invalid()
        if self.witness is None and self.index != 0:
            raise _invalid()
        if self.previous_pubdate is not None:
            _integer(self.previous_pubdate, 1, 253_402_300_799)
        if self.page == 1 and self.previous_pubdate is not None:
            raise _invalid()
        if self.page > 1 and self.previous_pubdate is None:
            raise _invalid()

    def as_mapping(self) -> dict[str, object]:
        return {
            "page": self.page,
            "witness": None if self.witness is None else self.witness.as_mapping(),
            "index": self.index,
            "previous_pubdate": self.previous_pubdate,
        }

    @classmethod
    def from_mapping(cls, value: object) -> BiliLane:
        item = _mapping(value, {"page", "witness", "index", "previous_pubdate"})
        return cls(
            item["page"],
            None if item["witness"] is None else BiliPage.from_mapping(item["witness"]),
            item["index"],
            item["previous_pubdate"],
        )


@dataclass(frozen=True, slots=True)
class BiliUnitSummary:
    lane: str
    stop_reason: str
    item_count: int
    list_attempts: int
    detail_attempts: int

    def __post_init__(self) -> None:
        if self.lane not in {"head", "history"} or self.stop_reason not in _REASONS:
            raise _invalid()
        _integer(self.item_count, 0, BILI_SCAN_PAGE_SIZE)
        _integer(self.list_attempts, 0, 2)
        if type(self.detail_attempts) is not int or self.detail_attempts != self.item_count:
            raise _invalid()

    def as_mapping(self) -> dict[str, object]:
        return {
            "lane": self.lane,
            "stop_reason": self.stop_reason,
            "item_count": self.item_count,
            "list_attempts": self.list_attempts,
            "detail_attempts": self.detail_attempts,
        }

    @classmethod
    def from_mapping(cls, value: object) -> BiliUnitSummary:
        return cls(**_mapping(value, {"lane", "stop_reason", "item_count", "list_attempts", "detail_attempts"}))


@dataclass(frozen=True, slots=True)
class BiliScanState:
    account_id: UUID
    author_fingerprint_sha256: str
    upstream_sha: str
    next_lane: str = "head"
    head: BiliLane = BiliLane()
    history: BiliLane = BiliLane()
    head_boundary: int | None = None
    head_candidate: int | None = None
    last_unit: BiliUnitSummary | None = None

    def __post_init__(self) -> None:
        if (
            type(self.account_id) is not UUID
            or type(self.author_fingerprint_sha256) is not str
            or _SHA256.fullmatch(self.author_fingerprint_sha256) is None
            or type(self.upstream_sha) is not str
            or _SHA1.fullmatch(self.upstream_sha) is None
        ):
            raise _invalid()
        if (
            self.next_lane not in {"head", "history"}
            or type(self.head) is not BiliLane
            or type(self.history) is not BiliLane
        ):
            raise _invalid()
        for timestamp in (self.head_boundary, self.head_candidate):
            if timestamp is not None:
                _integer(timestamp, 1, 253_402_300_799)
        if self.last_unit is not None and type(self.last_unit) is not BiliUnitSummary:
            raise _invalid()

    @classmethod
    def initial(cls, account_id: UUID, author_fingerprint_sha256: str, upstream_sha: str) -> BiliScanState:
        return cls(account_id, author_fingerprint_sha256, upstream_sha)

    def require_binding(self, *, account_id: UUID, author_fingerprint_sha256: str, upstream_sha: str) -> None:
        if (self.account_id, self.author_fingerprint_sha256, self.upstream_sha) != (
            account_id,
            author_fingerprint_sha256,
            upstream_sha,
        ):
            raise _invalid()

    def to_cursor(self) -> str:
        payload = {
            "schema_version": 1,
            "feed": "ordinary_uploads",
            "order": "pubdate",
            "page_size": BILI_SCAN_PAGE_SIZE,
            "account_id": str(self.account_id),
            "author_fingerprint_sha256": self.author_fingerprint_sha256,
            "upstream_sha": self.upstream_sha,
            "next_lane": self.next_lane,
            "head": self.head.as_mapping(),
            "history": self.history.as_mapping(),
            "head_boundary": self.head_boundary,
            "head_candidate": self.head_candidate,
            "last_unit": None if self.last_unit is None else self.last_unit.as_mapping(),
        }
        result = BILI_SCAN_CURSOR_PREFIX + _dump(payload)
        if len(result) > _MAX_CURSOR:
            raise _invalid()
        return result

    @classmethod
    def from_cursor(cls, value: str) -> BiliScanState:
        if type(value) is not str or not value.startswith(BILI_SCAN_CURSOR_PREFIX):
            raise _invalid()
        item = _mapping(
            _json(value[len(BILI_SCAN_CURSOR_PREFIX) :], _MAX_CURSOR),
            {
                "schema_version",
                "feed",
                "order",
                "page_size",
                "account_id",
                "author_fingerprint_sha256",
                "upstream_sha",
                "next_lane",
                "head",
                "history",
                "head_boundary",
                "head_candidate",
                "last_unit",
            },
        )
        if (
            type(item["schema_version"]) is not int
            or item["schema_version"] != 1
            or item["feed"] != "ordinary_uploads"
            or item["order"] != "pubdate"
            or type(item["page_size"]) is not int
            or item["page_size"] != BILI_SCAN_PAGE_SIZE
        ):
            raise _invalid()
        try:
            account_id = UUID(item["account_id"])
        except (ValueError, TypeError, AttributeError) as error:
            raise _invalid() from error
        if str(account_id) != item["account_id"]:
            raise _invalid()
        result = cls(
            account_id,
            item["author_fingerprint_sha256"],
            item["upstream_sha"],
            item["next_lane"],
            BiliLane.from_mapping(item["head"]),
            BiliLane.from_mapping(item["history"]),
            item["head_boundary"],
            item["head_candidate"],
            None if item["last_unit"] is None else BiliUnitSummary.from_mapping(item["last_unit"]),
        )
        if result.to_cursor() != value:
            raise _invalid()
        return result

    @classmethod
    def for_cursor(
        cls, value: str | None, *, account_id: UUID, author_fingerprint_sha256: str, upstream_sha: str
    ) -> BiliScanState:
        if value is not None and type(value) is not str:
            raise _invalid()
        if value is None or not value.startswith("bili-scan"):
            return cls.initial(account_id, author_fingerprint_sha256, upstream_sha)
        state = cls.from_cursor(value)
        state.require_binding(
            account_id=account_id, author_fingerprint_sha256=author_fingerprint_sha256, upstream_sha=upstream_sha
        )
        return state

    def public_summary(self) -> dict[str, object]:
        return {
            "version": 1,
            "next_lane": self.next_lane,
            "head_boundary_established": self.head_boundary is not None,
            "pending_count": sum(
                0 if lane.witness is None else len(lane.witness.identities) - lane.index
                for lane in (self.head, self.history)
            ),
            "history_active": True,
            "last_unit": None if self.last_unit is None else self.last_unit.as_mapping(),
            "next_action": f"continue_{self.next_lane}",
        }


@dataclass(frozen=True, slots=True)
class BiliScanAction:
    kind: str
    page: int | None = None
    identity: BiliIdentity | None = None


class BiliScanUnit:
    """One deterministic transaction proposal, replayable from page observations."""

    def __init__(self, state: BiliScanState, max_items: int):
        if type(state) is not BiliScanState:
            raise _invalid()
        self.limit = min(_integer(max_items, 1), BILI_SCAN_PAGE_SIZE)
        self.input_state = state
        self.state = state
        self.lane = state.next_lane
        self.pages: list[BiliPage] = []
        self.consumed: list[BiliIdentity] = []
        self.reason: str | None = None
        self._verified = False

    @property
    def current(self) -> BiliLane:
        return self.state.head if self.lane == "head" else self.state.history

    def _set_lane(self, lane: BiliLane) -> None:
        self.state = replace(self.state, head=lane) if self.lane == "head" else replace(self.state, history=lane)

    def _finish_sweep(self, reason: str) -> None:
        self._set_lane(BiliLane())
        if self.lane == "head":
            candidates = [value for value in (self.state.head_boundary, self.state.head_candidate) if value is not None]
            self.state = replace(self.state, head_boundary=max(candidates) if candidates else None, head_candidate=None)
        self.reason = reason

    def next_action(self) -> BiliScanAction:
        if self.reason is not None:
            return BiliScanAction("stop")
        current = self.current
        if len(self.consumed) == self.limit:
            self.reason = "item_limit"
            return BiliScanAction("stop")
        witness = current.witness
        if witness is not None and current.index < len(witness.identities):
            identity = witness.identities[current.index]
            if (
                self.lane == "head"
                and self.state.head_boundary is not None
                and identity.pubdate < self.state.head_boundary
            ):
                if not self._verified:
                    if len(self.pages) == 2:
                        self.reason = "list_limit"
                        return BiliScanAction("stop")
                    return BiliScanAction("list", page=current.page)
                self._finish_sweep("head_boundary")
                return BiliScanAction("stop")
            return BiliScanAction("detail", identity=identity)
        if witness is not None and self._verified:
            if witness.source_end:
                self._finish_sweep("source_end")
                return BiliScanAction("stop")
            if len(self.pages) == 2:
                self.reason = "list_limit"
                return BiliScanAction("stop")
            self._set_lane(BiliLane(current.page + 1, previous_pubdate=witness.identities[-1].pubdate))
            self._verified = False
            current = self.current
        if len(self.pages) == 2:
            self.reason = "list_limit"
            return BiliScanAction("stop")
        return BiliScanAction("list", page=current.page)

    def observe_page(self, page: BiliPage) -> None:
        action = self.next_action()
        if action.kind != "list" or type(page) is not BiliPage or action.page != page.page:
            raise _invalid()
        self.pages.append(page)
        current = self.current
        if current.witness is not None:
            if page != current.witness:
                self._set_lane(BiliLane())
                if self.lane == "head":
                    self.state = replace(self.state, head_candidate=None)
                self.reason = "restarted"
            else:
                self._verified = True
            return
        if (
            current.previous_pubdate is not None
            and page.identities
            and page.identities[0].pubdate > current.previous_pubdate
        ):
            self._set_lane(BiliLane())
            if self.lane == "head":
                self.state = replace(self.state, head_candidate=None)
            self.reason = "restarted"
            return
        self._set_lane(replace(current, witness=page))
        if self.lane == "head" and page.identities:
            self.state = replace(
                self.state, head_candidate=max(self.state.head_candidate or 0, page.identities[0].pubdate)
            )
        # An empty newly observed page is already a fresh source-end witness.
        self._verified = not page.identities

    def consume(self, identity: BiliIdentity) -> None:
        action = self.next_action()
        if action.kind != "detail" or identity != action.identity:
            raise _invalid()
        if identity.aid in {item.aid for item in self.consumed} or identity.bvid in {
            item.bvid for item in self.consumed
        }:
            raise _invalid()
        self.consumed.append(identity)
        self._set_lane(replace(self.current, index=self.current.index + 1))

    def coverage(self) -> BiliScanCoverage:
        if self.next_action().kind != "stop" or self.reason is None:
            raise _invalid()
        summary = BiliUnitSummary(self.lane, self.reason, len(self.consumed), len(self.pages), len(self.consumed))
        next_state = replace(self.state, next_lane="history" if self.lane == "head" else "head", last_unit=summary)
        return BiliScanCoverage(self.input_state, next_state, tuple(self.consumed), tuple(self.pages), summary)


@dataclass(frozen=True, slots=True)
class BiliScanCoverage:
    input_state: BiliScanState
    next_state: BiliScanState
    consumed: tuple[BiliIdentity, ...]
    pages: tuple[BiliPage, ...]
    summary: BiliUnitSummary

    @property
    def lane(self) -> str:
        return self.summary.lane

    @property
    def stop_reason(self) -> str:
        return self.summary.stop_reason

    @property
    def list_attempts(self) -> int:
        return self.summary.list_attempts

    @property
    def detail_attempts(self) -> int:
        return self.summary.detail_attempts

    def validate(
        self, input_state: BiliScanState, max_items: int, normalized_remote_ids: tuple[str, ...] | None = None
    ) -> None:
        if (
            self.input_state != input_state
            or len(self.pages) > 2
            or len(self.consumed) > min(max_items, BILI_SCAN_PAGE_SIZE)
        ):
            raise _invalid()
        unit = BiliScanUnit(input_state, max_items)
        page_index = consumed_index = 0
        while (action := unit.next_action()).kind != "stop":
            if action.kind == "list":
                if page_index >= len(self.pages):
                    raise _invalid()
                unit.observe_page(self.pages[page_index])
                page_index += 1
            else:
                if consumed_index >= len(self.consumed):
                    raise _invalid()
                unit.consume(self.consumed[consumed_index])
                consumed_index += 1
        if page_index != len(self.pages) or consumed_index != len(self.consumed) or unit.coverage() != self:
            raise _invalid()
        if normalized_remote_ids is not None and tuple(item.aid for item in self.consumed) != normalized_remote_ids:
            raise _invalid()

    def to_json_line(self) -> str:
        return (
            _dump(
                {
                    "schema_version": 1,
                    "input_cursor": self.input_state.to_cursor(),
                    "next_cursor": self.next_state.to_cursor(),
                    "consumed": [item.as_mapping() for item in self.consumed],
                    "pages": [page.as_mapping() for page in self.pages],
                    **self.summary.as_mapping(),
                }
            )
            + "\n"
        )

    @classmethod
    def from_json_line(cls, value: str) -> BiliScanCoverage:
        if type(value) is not str or not value.endswith("\n") or len(value.splitlines()) != 1:
            raise _invalid()
        item = _mapping(
            _json(value, _MAX_COVERAGE),
            {
                "schema_version",
                "input_cursor",
                "next_cursor",
                "consumed",
                "pages",
                "lane",
                "stop_reason",
                "item_count",
                "list_attempts",
                "detail_attempts",
            },
        )
        if (
            type(item["schema_version"]) is not int
            or item["schema_version"] != 1
            or type(item["consumed"]) is not list
            or len(item["consumed"]) > BILI_SCAN_PAGE_SIZE
            or type(item["pages"]) is not list
            or len(item["pages"]) > 2
        ):
            raise _invalid()
        return cls(
            BiliScanState.from_cursor(item["input_cursor"]),
            BiliScanState.from_cursor(item["next_cursor"]),
            tuple(BiliIdentity.from_mapping(row) for row in item["consumed"]),
            tuple(BiliPage.from_mapping(row) for row in item["pages"]),
            BiliUnitSummary.from_mapping(
                {key: item[key] for key in ("lane", "stop_reason", "item_count", "list_attempts", "detail_attempts")}
            ),
        )

    def public_summary(self) -> dict[str, object]:
        return {
            **self.summary.as_mapping(),
            "partial": True,
            "restarted": self.stop_reason == "restarted",
            "source_end_observed": self.stop_reason == "source_end",
            "head_boundary_observed": self.stop_reason == "head_boundary",
            "next_lane": self.next_state.next_lane,
            "next_action": f"continue_{self.next_state.next_lane}",
        }
