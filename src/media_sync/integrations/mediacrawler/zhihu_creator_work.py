"""Closed, replayable Zhihu creator-answer pagination without disclosure.

The pinned upstream (``.upstream/MediaCrawler/media_platform/zhihu/client.py:399-419``,
``:462-490``) is the only source of the rules below:

* pagination is an integer ``offset`` on ``/api/v4/members/<url_token>/answers``
  with a client-chosen ``limit=20`` and ``order_by=created``;
* the loop runs while ``not is_end`` and advances ``offset += limit``; the end is
  the server-declared ``paging.is_end`` boolean (``client.py:481-490``);
* a falsy body breaks the loop before any paging is read (``client.py:483-484``),
  which is not a source end;
* because ``offset`` is a page*limit product rather than an opaque cursor, an
  insertion or deletion between two requests shifts the whole window.  A durable
  layer therefore cannot trust the offset alone: it compares the identity tuple of
  each page with the previous page's and refuses to advance on an unexpected
  overlap, which is the only available signal that the window moved.

Creator identity is the ``url_token`` from ``/people/<url_token>`` and content
identity is ``content_id`` (answer id) as extracted by the pinned help module.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

ZH_SCAN_CURSOR_PREFIX = "zh-work-v1:"
ZH_SCAN_COVERAGE_FILENAME = "_media_sync_zhihu_coverage.jsonl"
ZH_SCAN_IDENTITY_FIELD = "__media_sync_zhihu_answer_identity"
ZH_CREATOR_PAGE_SIZE = 20
ZH_SCAN_STOP_REASONS = frozenset({"is_end", "empty_page_end", "access_restricted", "unit_cap_reached"})
ZH_STALLED_UNIT_LIMIT = 3
ZH_STALL_BLOCKED_CODE = "zhihu_offset_stalled"
ZH_SHIFT_BLOCKED_CODE = "zhihu_window_shifted"

_MAX_CURSOR_PAYLOAD = 65_536
_MAX_COVERAGE_PAYLOAD = 131_072
_MAX_UNIT_ITEMS = 1_000
_MAX_OFFSET = 2_000_000
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CONTENT_ID = re.compile(r"[0-9]{1,20}\Z")
_OUTCOME_STATUSES = frozenset({"stored", "unchanged", "detail_unavailable", "access_restricted"})


def _invalid() -> ValueError:
    return ValueError("invalid Zhihu creator-answer scan contract")


def _integer(value: object, low: int = 0, high: int = 2**63 - 1) -> int:
    if type(value) is not int or not low <= value <= high:
        raise _invalid()
    return value


def _offset(value: object) -> int:
    return _integer(value, 0, _MAX_OFFSET)


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


def _content_ids(value: object) -> tuple[str, ...]:
    if type(value) is not list or len(value) > _MAX_UNIT_ITEMS:
        raise _invalid()
    result = tuple(value)
    if any(type(item) is not str or _CONTENT_ID.fullmatch(item) is None for item in result):
        raise _invalid()
    if len(set(result)) != len(result):
        raise _invalid()
    return result


@dataclass(frozen=True, slots=True)
class ZhihuWorkIdentity:
    """One listed answer reduced to the stable ``content_id`` and listing digest."""

    content_id: str
    listing_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.content_id) is not str
            or _CONTENT_ID.fullmatch(self.content_id) is None
            or type(self.listing_sha256) is not str
            or _SHA256.fullmatch(self.listing_sha256) is None
        ):
            raise _invalid()

    def as_mapping(self) -> dict[str, str]:
        return {"content_id": self.content_id, "listing_sha256": self.listing_sha256}

    @classmethod
    def from_mapping(cls, value: object) -> ZhihuWorkIdentity:
        return cls(**_mapping(value, {"content_id", "listing_sha256"}))


@dataclass(frozen=True, slots=True)
class ZhihuPageWitness:
    """One page's exact continuation facts, persisted without any answer payload."""

    offset: int
    limit: int
    is_end: bool
    identities: tuple[ZhihuWorkIdentity, ...]

    def __post_init__(self) -> None:
        _offset(self.offset)
        _integer(self.limit, 1, ZH_CREATOR_PAGE_SIZE)
        if type(self.is_end) is not bool:
            raise _invalid()
        if type(self.identities) is not tuple or any(type(item) is not ZhihuWorkIdentity for item in self.identities):
            raise _invalid()
        if len({item.content_id for item in self.identities}) != len(self.identities):
            raise _invalid()
        if len(self.identities) > self.limit:
            raise _invalid()

    @property
    def content_ids(self) -> tuple[str, ...]:
        return tuple(item.content_id for item in self.identities)

    def as_mapping(self) -> dict[str, object]:
        return {
            "offset": self.offset,
            "limit": self.limit,
            "is_end": self.is_end,
            "identities": [item.as_mapping() for item in self.identities],
        }

    @classmethod
    def from_mapping(cls, value: object) -> ZhihuPageWitness:
        item = _mapping(value, {"offset", "limit", "is_end", "identities"})
        identities = item["identities"]
        if type(identities) is not list:
            raise _invalid()
        return cls(
            item["offset"],
            item["limit"],
            item["is_end"],
            tuple(ZhihuWorkIdentity.from_mapping(row) for row in identities),
        )


@dataclass(frozen=True, slots=True)
class ZhihuCreatorPage:
    """One exact list response reduced to bounded answer identities."""

    offset: int
    limit: int
    is_end: bool
    identities: tuple[ZhihuWorkIdentity, ...]

    def __post_init__(self) -> None:
        witness = self.witness
        if witness.content_ids != tuple(item.content_id for item in self.identities):
            raise _invalid()

    @property
    def witness(self) -> ZhihuPageWitness:
        return ZhihuPageWitness(self.offset, self.limit, self.is_end, self.identities)

    def as_mapping(self) -> dict[str, object]:
        return self.witness.as_mapping()

    @classmethod
    def from_mapping(cls, value: object) -> ZhihuCreatorPage:
        item = _mapping(value, {"offset", "limit", "is_end", "identities"})
        identities = item["identities"]
        if type(identities) is not list:
            raise _invalid()
        return cls(
            item["offset"],
            item["limit"],
            item["is_end"],
            tuple(ZhihuWorkIdentity.from_mapping(row) for row in identities),
        )


@dataclass(frozen=True, slots=True)
class ZhihuWorkOutcome:
    identity: ZhihuWorkIdentity
    status: str

    def __post_init__(self) -> None:
        if type(self.identity) is not ZhihuWorkIdentity or self.status not in _OUTCOME_STATUSES:
            raise _invalid()

    def as_mapping(self) -> dict[str, object]:
        return {"identity": self.identity.as_mapping(), "status": self.status}

    @classmethod
    def from_mapping(cls, value: object) -> ZhihuWorkOutcome:
        item = _mapping(value, {"identity", "status"})
        return cls(ZhihuWorkIdentity.from_mapping(item["identity"]), item["status"])


@dataclass(frozen=True, slots=True)
class ZhihuUnitSummary:
    lane: str
    stop_reason: str
    stored_count: int
    unchanged_count: int
    failed_count: int
    list_attempts: int
    detail_attempts: int
    page_complete: bool
    offset: int
    is_end: bool | None

    def __post_init__(self) -> None:
        if self.lane not in {"history", "head"} or self.stop_reason not in ZH_SCAN_STOP_REASONS:
            raise _invalid()
        _integer(self.stored_count, 0, _MAX_UNIT_ITEMS)
        _integer(self.unchanged_count, 0, _MAX_UNIT_ITEMS)
        _integer(self.failed_count, 0, _MAX_UNIT_ITEMS)
        _integer(self.list_attempts, 1, 1)
        _integer(self.detail_attempts, 0, _MAX_UNIT_ITEMS)
        _offset(self.offset)
        if self.is_end is not None and type(self.is_end) is not bool:
            raise _invalid()
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
            "offset": self.offset,
            "is_end": self.is_end,
        }

    @classmethod
    def from_mapping(cls, value: object) -> ZhihuUnitSummary:
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
                    "offset",
                    "is_end",
                },
            )
        )


@dataclass(frozen=True, slots=True)
class ZhihuScanState:
    account_id: UUID
    author_fingerprint_sha256: str
    creator_fingerprint_sha256: str
    upstream_sha: str
    lane: str = "history"
    offset: int = 0
    witness: ZhihuPageWitness | None = None
    index: int = 0
    completed_content_ids: tuple[str, ...] = ()
    previous_page_content_ids: tuple[str, ...] = ()
    head_boundary: tuple[ZhihuWorkIdentity, ...] | None = None
    last_unit: ZhihuUnitSummary | None = None
    stalled_units: int = 0
    shifted_units: int = 0

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
        _offset(self.offset)
        _integer(self.index)
        _integer(self.stalled_units, 0, _MAX_UNIT_ITEMS)
        _integer(self.shifted_units, 0, _MAX_UNIT_ITEMS)
        if type(self.completed_content_ids) is not tuple:
            raise _invalid()
        _content_ids(list(self.completed_content_ids))
        if type(self.previous_page_content_ids) is not tuple:
            raise _invalid()
        _content_ids(list(self.previous_page_content_ids))
        if self.witness is not None and (
            type(self.witness) is not ZhihuPageWitness
            or self.witness.offset != self.offset
            or self.index > len(self.witness.content_ids)
        ):
            raise _invalid()
        if self.witness is None and self.index:
            raise _invalid()
        if self.witness is None and self.completed_content_ids:
            raise _invalid()
        if self.witness is not None and not set(self.completed_content_ids).issubset(self.witness.content_ids):
            raise _invalid()
        if self.head_boundary is not None:
            if type(self.head_boundary) is not tuple or any(
                type(item) is not ZhihuWorkIdentity for item in self.head_boundary
            ):
                raise _invalid()
            if len({item.content_id for item in self.head_boundary}) != len(self.head_boundary):
                raise _invalid()
        if self.last_unit is not None and type(self.last_unit) is not ZhihuUnitSummary:
            raise _invalid()

    @classmethod
    def initial(
        cls,
        account_id: UUID,
        author_fingerprint_sha256: str,
        creator_fingerprint_sha256: str,
        upstream_sha: str,
    ) -> ZhihuScanState:
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

    def for_head(self) -> ZhihuScanState:
        if self.head_boundary is None:
            raise _invalid()
        return replace(
            self,
            lane="head",
            offset=0,
            witness=None,
            index=0,
            completed_content_ids=(),
            previous_page_content_ids=(),
            last_unit=None,
            stalled_units=0,
            shifted_units=0,
        )

    def to_cursor(self) -> str:
        payload = {
            "schema_version": 1,
            "feed": "creator_answers",
            "account_id": str(self.account_id),
            "author_fingerprint_sha256": self.author_fingerprint_sha256,
            "creator_fingerprint_sha256": self.creator_fingerprint_sha256,
            "upstream_sha": self.upstream_sha,
            "lane": self.lane,
            "offset": self.offset,
            "witness": None if self.witness is None else self.witness.as_mapping(),
            "index": self.index,
            "completed_content_ids": list(self.completed_content_ids),
            "previous_page_content_ids": list(self.previous_page_content_ids),
            "head_boundary": None if self.head_boundary is None else [item.as_mapping() for item in self.head_boundary],
            "stalled_units": self.stalled_units,
            "shifted_units": self.shifted_units,
            "last_unit": None if self.last_unit is None else self.last_unit.as_mapping(),
        }
        result = ZH_SCAN_CURSOR_PREFIX + _dump(payload)
        if len(result) > _MAX_CURSOR_PAYLOAD:
            raise _invalid()
        return result

    @classmethod
    def from_cursor(cls, value: str) -> ZhihuScanState:
        if type(value) is not str or not value.startswith(ZH_SCAN_CURSOR_PREFIX):
            raise _invalid()
        item = _mapping(
            _json(value[len(ZH_SCAN_CURSOR_PREFIX) :], _MAX_CURSOR_PAYLOAD),
            {
                "schema_version",
                "feed",
                "account_id",
                "author_fingerprint_sha256",
                "creator_fingerprint_sha256",
                "upstream_sha",
                "lane",
                "offset",
                "witness",
                "index",
                "completed_content_ids",
                "previous_page_content_ids",
                "head_boundary",
                "stalled_units",
                "shifted_units",
                "last_unit",
            },
        )
        if item["schema_version"] != 1 or item["feed"] != "creator_answers":
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
            item["offset"],
            None if item["witness"] is None else ZhihuPageWitness.from_mapping(item["witness"]),
            item["index"],
            _content_ids(item["completed_content_ids"]),
            _content_ids(item["previous_page_content_ids"]),
            (
                None
                if item["head_boundary"] is None
                else tuple(ZhihuWorkIdentity.from_mapping(row) for row in item["head_boundary"])
            ),
            None if item["last_unit"] is None else ZhihuUnitSummary.from_mapping(item["last_unit"]),
            item["stalled_units"],
            item["shifted_units"],
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
    ) -> ZhihuScanState:
        if value is not None and type(value) is not str:
            raise _invalid()
        if value is None:
            return cls.initial(account_id, author_fingerprint_sha256, creator_fingerprint_sha256, upstream_sha)
        if not value.startswith(ZH_SCAN_CURSOR_PREFIX):
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
            "offset": self.offset,
            "page_in_progress": self.witness is not None,
            "page_position": self.index,
            "head_boundary_established": self.head_boundary is not None,
            "stalled_units": self.stalled_units,
            "shifted_units": self.shifted_units,
            "last_unit": None if self.last_unit is None else self.last_unit.as_mapping(),
            "next_action": f"continue_{self.lane}",
        }


@dataclass(frozen=True, slots=True)
class ZhihuScanAction:
    kind: str
    offset: int | None = None
    limit: int | None = None
    identity: ZhihuWorkIdentity | None = None


class ZhihuScanUnit:
    """One page-bound proposal over the integer ``offset`` chain."""

    def __init__(self, state: ZhihuScanState, max_items: int):
        if type(state) is not ZhihuScanState:
            raise _invalid()
        self.max_items = _integer(max_items, 1, _MAX_UNIT_ITEMS)
        self.input_state = state
        self.state = state
        self.page: ZhihuCreatorPage | None = None
        self.outcomes: list[ZhihuWorkOutcome] = []
        self.reason: str | None = None

    def _limit(self) -> int:
        remaining = self.max_items - len(self.outcomes)
        return max(1, min(ZH_CREATOR_PAGE_SIZE, remaining))

    def next_action(self) -> ZhihuScanAction:
        if self.reason is not None:
            return ZhihuScanAction("stop")
        if self.page is None:
            return ZhihuScanAction("list", offset=self.state.offset, limit=self._limit())
        while (
            self.state.index < len(self.page.identities)
            and self.page.identities[self.state.index].content_id in self.state.completed_content_ids
        ):
            self.state = replace(self.state, index=self.state.index + 1)
        if self.state.index >= len(self.page.identities):
            self._finish_page()
            return ZhihuScanAction("stop")
        if len(self.outcomes) >= self.max_items:
            self.reason = "unit_cap_reached"
            return ZhihuScanAction("stop")
        identity = self.page.identities[self.state.index]
        prior = {item.content_id: item.listing_sha256 for item in self.state.head_boundary or ()}
        if self.state.lane == "head" and prior.get(identity.content_id) == identity.listing_sha256:
            return ZhihuScanAction("unchanged", identity=identity)
        return ZhihuScanAction("detail", identity=identity)

    def observe_page(self, page: ZhihuCreatorPage) -> None:
        action = self.next_action()
        if (
            action.kind != "list"
            or type(page) is not ZhihuCreatorPage
            or page.offset != action.offset
            or page.limit != action.limit
        ):
            raise _invalid()
        if self.state.witness is not None:
            expected = self.state.witness
            observed = page.witness
            if (observed.offset, observed.limit, observed.is_end, observed.content_ids) != (
                expected.offset,
                expected.limit,
                expected.is_end,
                expected.content_ids,
            ):
                raise _invalid()
            prior_fingerprints = {item.content_id: item.listing_sha256 for item in expected.identities}
            completed = tuple(
                item.content_id
                for item in observed.identities
                if item.content_id in self.state.completed_content_ids
                and prior_fingerprints.get(item.content_id) == item.listing_sha256
            )
            self.state = replace(self.state, witness=observed, index=0, completed_content_ids=completed)
        self.page = page
        if self.state.witness is None:
            self.state = replace(self.state, witness=page.witness)
        if (
            self.state.lane == "history"
            and self.state.offset == 0
            and self.state.head_boundary is None
            and page.witness.identities
        ):
            # Only a page that listed answers establishes the head boundary. An
            # empty boundary reconciles equal to anything, so recording one here
            # would let a contradictory or rate-limited response look complete.
            self.state = replace(self.state, head_boundary=page.witness.identities)

    def observe_access_restricted(self) -> None:
        if self.next_action().kind != "list":
            raise _invalid()
        self.reason = "access_restricted"

    def store(self, identity: ZhihuWorkIdentity) -> None:
        self._record(identity, "stored")

    def skip_unchanged(self, identity: ZhihuWorkIdentity) -> None:
        self._record(identity, "unchanged")

    def fail(self, identity: ZhihuWorkIdentity, *, access_restricted: bool = False) -> None:
        failed_index = self.state.index
        self._record(identity, "access_restricted" if access_restricted else "detail_unavailable")
        if access_restricted:
            self.state = replace(self.state, index=failed_index)
            self.reason = "access_restricted"

    def _record(self, identity: ZhihuWorkIdentity, status: str) -> None:
        action = self.next_action()
        expected_kind = "unchanged" if status == "unchanged" else "detail"
        if action.kind != expected_kind or identity != action.identity:
            raise _invalid()
        self.outcomes.append(ZhihuWorkOutcome(identity, status))
        completed = self.state.completed_content_ids
        if status in {"stored", "unchanged"} and identity.content_id not in completed:
            completed = (*completed, identity.content_id)
        self.state = replace(self.state, index=self.state.index + 1, completed_content_ids=completed)

    def _finish_page(self) -> None:
        page = self.page
        if page is None:
            raise _invalid()
        if len(self.state.completed_content_ids) != len(page.identities):
            # max_items (or a failed detail) stopped the unit before the page
            # tail: keep the identical offset and witness so the next unit
            # re-issues the same request and skips already-delivered answers.
            self.reason = "unit_cap_reached"
            self.state = replace(self.state, index=0, shifted_units=0)
            return
        if self.state.lane == "head":
            self._finish_head(page)
            return
        page_ids = page.witness.content_ids
        # The offset is a page*limit product, so ONE insertion or deletion
        # shifts the window by one and the next page legitimately repeats the
        # previous page's tail. A partial intersection is therefore normal
        # drift, not a stall: the repeated answers are already delivered and
        # re-storing them is idempotent, so the page is consumed normally.
        # Only a page that is IDENTICAL to the previous one shows that the
        # window is not moving at all, which is the sole blocking condition.
        stalled = bool(page_ids) and page_ids == self.state.previous_page_content_ids
        if not page_ids and not page.is_end:
            # "No answers here, but this is not the end" contradicts itself. A
            # rate-limited body parses this way, so replay the same offset and
            # count the stall instead of declaring an empty source end.
            self.reason = "unit_cap_reached"
            self.state = replace(
                self.state,
                witness=None,
                index=0,
                completed_content_ids=(),
                previous_page_content_ids=(),
                stalled_units=self.state.stalled_units + 1,
            )
            return
        if not page_ids:
            self.reason = "empty_page_end"
            self.state = replace(
                self.state,
                offset=0,
                witness=None,
                index=0,
                completed_content_ids=(),
                previous_page_content_ids=(),
                stalled_units=0,
                shifted_units=0,
            )
            return
        if page.is_end:
            # The server declared the end; it is retained with the page witness
            # so reconciliation can confirm or reject the boundary.
            self.reason = "is_end"
            self.state = replace(
                self.state,
                offset=0,
                witness=None,
                index=0,
                completed_content_ids=(),
                previous_page_content_ids=(),
                stalled_units=0,
                shifted_units=0,
            )
            return
        if stalled:
            # The identical page came back twice: the window is not advancing.
            # Keep the offset so the request is replayed, and count the stall
            # toward the bounded blocked transition.
            self.reason = "unit_cap_reached"
            self.state = replace(
                self.state,
                witness=None,
                index=0,
                completed_content_ids=(),
                previous_page_content_ids=page_ids,
                stalled_units=self.state.stalled_units + 1,
                shifted_units=0,
            )
            return
        self.reason = "unit_cap_reached"
        self.state = replace(
            self.state,
            offset=self.state.offset + page.limit,
            witness=None,
            index=0,
            completed_content_ids=(),
            previous_page_content_ids=page_ids,
            stalled_units=0,
            shifted_units=0,
        )

    def _finish_head(self, page: ZhihuCreatorPage) -> None:
        if page.is_end:
            self.reason = "is_end"
        elif not page.identities:
            self.reason = "empty_page_end"
        else:
            self.reason = "unit_cap_reached"
        self.state = replace(
            self.state,
            offset=0,
            witness=None,
            index=0,
            completed_content_ids=(),
            previous_page_content_ids=(),
            stalled_units=0,
            shifted_units=0,
            head_boundary=page.witness.identities,
        )

    def coverage(self) -> ZhihuScanCoverage:
        if self.next_action().kind != "stop" or self.reason is None:
            raise _invalid()
        page_complete = self.page is not None and self.state.witness is None
        summary = ZhihuUnitSummary(
            self.input_state.lane,
            self.reason,
            sum(item.status == "stored" for item in self.outcomes),
            sum(item.status == "unchanged" for item in self.outcomes),
            sum(item.status not in {"stored", "unchanged"} for item in self.outcomes),
            1,
            sum(item.status != "unchanged" for item in self.outcomes),
            page_complete,
            self.input_state.offset,
            None if self.page is None else self.page.is_end,
        )
        next_state = replace(self.state, last_unit=summary)
        return ZhihuScanCoverage(self.input_state, next_state, self.page, tuple(self.outcomes), summary)


@dataclass(frozen=True, slots=True)
class ZhihuScanCoverage:
    input_state: ZhihuScanState
    next_state: ZhihuScanState
    page: ZhihuCreatorPage | None
    outcomes: tuple[ZhihuWorkOutcome, ...]
    summary: ZhihuUnitSummary

    @property
    def successful(self) -> tuple[ZhihuWorkIdentity, ...]:
        return tuple(item.identity for item in self.outcomes if item.status == "stored")

    @property
    def failed(self) -> tuple[ZhihuWorkOutcome, ...]:
        return tuple(item for item in self.outcomes if item.status not in {"stored", "unchanged"})

    @property
    def stop_reason(self) -> str:
        return self.summary.stop_reason

    @property
    def lane(self) -> str:
        return self.summary.lane

    @property
    def source_end_observed(self) -> bool:
        return self.summary.stop_reason in {"is_end", "empty_page_end"}

    @property
    def blocked_code(self) -> str | None:
        if self.next_state.shifted_units >= ZH_STALLED_UNIT_LIMIT:
            return ZH_SHIFT_BLOCKED_CODE
        if self.next_state.stalled_units >= ZH_STALLED_UNIT_LIMIT:
            return ZH_STALL_BLOCKED_CODE
        return None

    def validate(
        self,
        input_state: ZhihuScanState,
        max_items: int,
        normalized_remote_ids: tuple[str, ...] | None = None,
    ) -> None:
        if (
            type(input_state) is not ZhihuScanState
            or self.input_state != input_state
            or type(self.outcomes) is not tuple
            or len(self.outcomes) > max_items
        ):
            raise _invalid()
        unit = ZhihuScanUnit(input_state, max_items)
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
            and tuple(item.content_id for item in self.successful) != normalized_remote_ids
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
    def from_json_line(cls, value: str) -> ZhihuScanCoverage:
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
                "offset",
                "is_end",
            },
        )
        if item["schema_version"] != 1 or type(item["outcomes"]) is not list:
            raise _invalid()
        result = cls(
            ZhihuScanState.from_cursor(item["input_cursor"]),
            ZhihuScanState.from_cursor(item["next_cursor"]),
            None if item["page"] is None else ZhihuCreatorPage.from_mapping(item["page"]),
            tuple(ZhihuWorkOutcome.from_mapping(row) for row in item["outcomes"]),
            ZhihuUnitSummary.from_mapping(
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
                        "offset",
                        "is_end",
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
            "shifted_units": self.next_state.shifted_units,
            "blocked_code": self.blocked_code,
            "next_action": f"continue_{self.next_state.lane}",
        }


__all__ = [
    "ZH_CREATOR_PAGE_SIZE",
    "ZH_SCAN_COVERAGE_FILENAME",
    "ZH_SCAN_CURSOR_PREFIX",
    "ZH_SCAN_IDENTITY_FIELD",
    "ZH_SCAN_STOP_REASONS",
    "ZH_SHIFT_BLOCKED_CODE",
    "ZH_STALLED_UNIT_LIMIT",
    "ZH_STALL_BLOCKED_CODE",
    "ZhihuCreatorPage",
    "ZhihuPageWitness",
    "ZhihuScanAction",
    "ZhihuScanCoverage",
    "ZhihuScanState",
    "ZhihuScanUnit",
    "ZhihuUnitSummary",
    "ZhihuWorkIdentity",
    "ZhihuWorkOutcome",
]
