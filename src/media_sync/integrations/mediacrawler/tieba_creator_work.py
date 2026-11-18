"""Closed, replayable Tieba creator-thread pagination without disclosure.

The pinned upstream (``.upstream/MediaCrawler/media_platform/tieba/client.py:772-830``)
is the only source of the rules below:

* pagination is the signed PC feed endpoint ``/c/u/feed/myThread`` with a 1-based
  ``pn`` and a client-chosen ``rn=20`` (``client.py:684-710``), so — unlike the
  other platforms — the page size *is* client-controlled;
* the loop continues while ``max_note_count == 0 or len(result) < max_note_count``
  and stops when a page yields no thread ids or when
  ``int(data.get("has_more") or 0)`` is falsy (``client.py:790-830``);
* a business ``error_code != 0`` or a malformed body makes upstream log and break
  (``client.py:806-810``); that is not a source end;
* the creator identity is the ``portrait`` extracted from the creator URL
  (``client.py:172-186``) and the thread identity is ``thread_info.tid`` or
  ``thread_info.id`` (``help.py:240-250``).

Because ``pn`` is an integer that always increments, a server that keeps serving
the same page cannot be detected from the cursor alone: the durable layer
compares page identities and counts a non-advancing page as a stall.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

TB_SCAN_CURSOR_PREFIX = "tb-work-v1:"
TB_SCAN_COVERAGE_FILENAME = "_media_sync_tieba_coverage.jsonl"
TB_SCAN_IDENTITY_FIELD = "__media_sync_tieba_thread_identity"
TB_CREATOR_PAGE_SIZE = 20
TB_SCAN_STOP_REASONS = frozenset({"has_more_false", "empty_page_end", "access_restricted", "unit_cap_reached"})
TB_STALLED_UNIT_LIMIT = 3
TB_STALL_BLOCKED_CODE = "tieba_page_stalled"

_MAX_CURSOR_PAYLOAD = 65_536
_MAX_COVERAGE_PAYLOAD = 131_072
_MAX_UNIT_ITEMS = 1_000
_MAX_PAGE_NUMBER = 1_000_000
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_THREAD_ID = re.compile(r"[0-9]{6,20}\Z")
_OUTCOME_STATUSES = frozenset({"stored", "unchanged", "detail_unavailable", "access_restricted"})


def _invalid() -> ValueError:
    return ValueError("invalid Tieba creator-thread scan contract")


def _integer(value: object, low: int = 0, high: int = 2**63 - 1) -> int:
    if type(value) is not int or not low <= value <= high:
        raise _invalid()
    return value


def _page_number(value: object) -> int:
    return _integer(value, 1, _MAX_PAGE_NUMBER)


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


def _thread_ids(value: object) -> tuple[str, ...]:
    if type(value) is not list or len(value) > _MAX_UNIT_ITEMS:
        raise _invalid()
    result = tuple(value)
    if any(type(item) is not str or _THREAD_ID.fullmatch(item) is None for item in result):
        raise _invalid()
    if len(set(result)) != len(result):
        raise _invalid()
    return result


@dataclass(frozen=True, slots=True)
class TiebaWorkIdentity:
    """One listed thread reduced to the stable ``thread_id`` and listing digest."""

    thread_id: str
    listing_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.thread_id) is not str
            or _THREAD_ID.fullmatch(self.thread_id) is None
            or type(self.listing_sha256) is not str
            or _SHA256.fullmatch(self.listing_sha256) is None
        ):
            raise _invalid()

    def as_mapping(self) -> dict[str, str]:
        return {"thread_id": self.thread_id, "listing_sha256": self.listing_sha256}

    @classmethod
    def from_mapping(cls, value: object) -> TiebaWorkIdentity:
        return cls(**_mapping(value, {"thread_id", "listing_sha256"}))


@dataclass(frozen=True, slots=True)
class TiebaPageWitness:
    """One page's exact continuation facts, persisted without any thread payload."""

    page: int
    has_more: bool
    identities: tuple[TiebaWorkIdentity, ...]

    def __post_init__(self) -> None:
        _page_number(self.page)
        if type(self.has_more) is not bool:
            raise _invalid()
        if type(self.identities) is not tuple or any(type(item) is not TiebaWorkIdentity for item in self.identities):
            raise _invalid()
        if len({item.thread_id for item in self.identities}) != len(self.identities):
            raise _invalid()

    @property
    def thread_ids(self) -> tuple[str, ...]:
        return tuple(item.thread_id for item in self.identities)

    def as_mapping(self) -> dict[str, object]:
        return {
            "page": self.page,
            "has_more": self.has_more,
            "identities": [item.as_mapping() for item in self.identities],
        }

    @classmethod
    def from_mapping(cls, value: object) -> TiebaPageWitness:
        item = _mapping(value, {"page", "has_more", "identities"})
        identities = item["identities"]
        if type(identities) is not list:
            raise _invalid()
        return cls(
            item["page"],
            item["has_more"],
            tuple(TiebaWorkIdentity.from_mapping(row) for row in identities),
        )


@dataclass(frozen=True, slots=True)
class TiebaCreatorPage:
    """One exact list response reduced to bounded thread identities."""

    page: int
    has_more: bool
    identities: tuple[TiebaWorkIdentity, ...]

    def __post_init__(self) -> None:
        witness = self.witness
        if witness.thread_ids != tuple(item.thread_id for item in self.identities):
            raise _invalid()

    @property
    def witness(self) -> TiebaPageWitness:
        return TiebaPageWitness(self.page, self.has_more, self.identities)

    def as_mapping(self) -> dict[str, object]:
        return self.witness.as_mapping()

    @classmethod
    def from_mapping(cls, value: object) -> TiebaCreatorPage:
        item = _mapping(value, {"page", "has_more", "identities"})
        identities = item["identities"]
        if type(identities) is not list:
            raise _invalid()
        return cls(
            item["page"],
            item["has_more"],
            tuple(TiebaWorkIdentity.from_mapping(row) for row in identities),
        )


@dataclass(frozen=True, slots=True)
class TiebaWorkOutcome:
    identity: TiebaWorkIdentity
    status: str

    def __post_init__(self) -> None:
        if type(self.identity) is not TiebaWorkIdentity or self.status not in _OUTCOME_STATUSES:
            raise _invalid()

    def as_mapping(self) -> dict[str, object]:
        return {"identity": self.identity.as_mapping(), "status": self.status}

    @classmethod
    def from_mapping(cls, value: object) -> TiebaWorkOutcome:
        item = _mapping(value, {"identity", "status"})
        return cls(TiebaWorkIdentity.from_mapping(item["identity"]), item["status"])


@dataclass(frozen=True, slots=True)
class TiebaUnitSummary:
    lane: str
    stop_reason: str
    stored_count: int
    unchanged_count: int
    failed_count: int
    list_attempts: int
    detail_attempts: int
    page_complete: bool
    page_number: int
    has_more: bool | None

    def __post_init__(self) -> None:
        if self.lane not in {"history", "head"} or self.stop_reason not in TB_SCAN_STOP_REASONS:
            raise _invalid()
        _integer(self.stored_count, 0, _MAX_UNIT_ITEMS)
        _integer(self.unchanged_count, 0, _MAX_UNIT_ITEMS)
        _integer(self.failed_count, 0, _MAX_UNIT_ITEMS)
        _integer(self.list_attempts, 1, 1)
        _integer(self.detail_attempts, 0, _MAX_UNIT_ITEMS)
        _page_number(self.page_number)
        if self.has_more is not None and type(self.has_more) is not bool:
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
            "page_number": self.page_number,
            "has_more": self.has_more,
        }

    @classmethod
    def from_mapping(cls, value: object) -> TiebaUnitSummary:
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
                    "page_number",
                    "has_more",
                },
            )
        )


@dataclass(frozen=True, slots=True)
class TiebaScanState:
    account_id: UUID
    author_fingerprint_sha256: str
    creator_fingerprint_sha256: str
    upstream_sha: str
    lane: str = "history"
    page: int = 1
    witness: TiebaPageWitness | None = None
    index: int = 0
    completed_thread_ids: tuple[str, ...] = ()
    previous_page_thread_ids: tuple[str, ...] = ()
    head_boundary: tuple[TiebaWorkIdentity, ...] | None = None
    last_unit: TiebaUnitSummary | None = None
    stalled_units: int = 0

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
        _page_number(self.page)
        _integer(self.index)
        _integer(self.stalled_units, 0, _MAX_UNIT_ITEMS)
        if type(self.completed_thread_ids) is not tuple:
            raise _invalid()
        _thread_ids(list(self.completed_thread_ids))
        if type(self.previous_page_thread_ids) is not tuple:
            raise _invalid()
        _thread_ids(list(self.previous_page_thread_ids))
        if self.witness is not None and (
            type(self.witness) is not TiebaPageWitness
            or self.witness.page != self.page
            or self.index > len(self.witness.thread_ids)
        ):
            raise _invalid()
        if self.witness is None and self.index:
            raise _invalid()
        if self.witness is None and self.completed_thread_ids:
            raise _invalid()
        if self.witness is not None and not set(self.completed_thread_ids).issubset(self.witness.thread_ids):
            raise _invalid()
        if self.head_boundary is not None:
            if type(self.head_boundary) is not tuple or any(
                type(item) is not TiebaWorkIdentity for item in self.head_boundary
            ):
                raise _invalid()
            if len({item.thread_id for item in self.head_boundary}) != len(self.head_boundary):
                raise _invalid()
        if self.last_unit is not None and type(self.last_unit) is not TiebaUnitSummary:
            raise _invalid()

    @classmethod
    def initial(
        cls,
        account_id: UUID,
        author_fingerprint_sha256: str,
        creator_fingerprint_sha256: str,
        upstream_sha: str,
    ) -> TiebaScanState:
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

    def for_head(self) -> TiebaScanState:
        if self.head_boundary is None:
            raise _invalid()
        return replace(
            self,
            lane="head",
            page=1,
            witness=None,
            index=0,
            completed_thread_ids=(),
            previous_page_thread_ids=(),
            last_unit=None,
            stalled_units=0,
        )

    def to_cursor(self) -> str:
        payload = {
            "schema_version": 1,
            "feed": "creator_threads",
            "account_id": str(self.account_id),
            "author_fingerprint_sha256": self.author_fingerprint_sha256,
            "creator_fingerprint_sha256": self.creator_fingerprint_sha256,
            "upstream_sha": self.upstream_sha,
            "lane": self.lane,
            "page": self.page,
            "witness": None if self.witness is None else self.witness.as_mapping(),
            "index": self.index,
            "completed_thread_ids": list(self.completed_thread_ids),
            "previous_page_thread_ids": list(self.previous_page_thread_ids),
            "head_boundary": None if self.head_boundary is None else [item.as_mapping() for item in self.head_boundary],
            "stalled_units": self.stalled_units,
            "last_unit": None if self.last_unit is None else self.last_unit.as_mapping(),
        }
        result = TB_SCAN_CURSOR_PREFIX + _dump(payload)
        if len(result) > _MAX_CURSOR_PAYLOAD:
            raise _invalid()
        return result

    @classmethod
    def from_cursor(cls, value: str) -> TiebaScanState:
        if type(value) is not str or not value.startswith(TB_SCAN_CURSOR_PREFIX):
            raise _invalid()
        item = _mapping(
            _json(value[len(TB_SCAN_CURSOR_PREFIX) :], _MAX_CURSOR_PAYLOAD),
            {
                "schema_version",
                "feed",
                "account_id",
                "author_fingerprint_sha256",
                "creator_fingerprint_sha256",
                "upstream_sha",
                "lane",
                "page",
                "witness",
                "index",
                "completed_thread_ids",
                "previous_page_thread_ids",
                "head_boundary",
                "stalled_units",
                "last_unit",
            },
        )
        if item["schema_version"] != 1 or item["feed"] != "creator_threads":
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
            item["page"],
            None if item["witness"] is None else TiebaPageWitness.from_mapping(item["witness"]),
            item["index"],
            _thread_ids(item["completed_thread_ids"]),
            _thread_ids(item["previous_page_thread_ids"]),
            (
                None
                if item["head_boundary"] is None
                else tuple(TiebaWorkIdentity.from_mapping(row) for row in item["head_boundary"])
            ),
            None if item["last_unit"] is None else TiebaUnitSummary.from_mapping(item["last_unit"]),
            item["stalled_units"],
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
    ) -> TiebaScanState:
        if value is not None and type(value) is not str:
            raise _invalid()
        if value is None:
            return cls.initial(account_id, author_fingerprint_sha256, creator_fingerprint_sha256, upstream_sha)
        if not value.startswith(TB_SCAN_CURSOR_PREFIX):
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
            "page": self.page,
            "page_in_progress": self.witness is not None,
            "page_position": self.index,
            "head_boundary_established": self.head_boundary is not None,
            "stalled_units": self.stalled_units,
            "last_unit": None if self.last_unit is None else self.last_unit.as_mapping(),
            "next_action": f"continue_{self.lane}",
        }


@dataclass(frozen=True, slots=True)
class TiebaScanAction:
    kind: str
    page: int | None = None
    identity: TiebaWorkIdentity | None = None


class TiebaScanUnit:
    """One page-bound proposal over the 1-based page-number chain."""

    def __init__(self, state: TiebaScanState, max_items: int):
        if type(state) is not TiebaScanState:
            raise _invalid()
        self.limit = _integer(max_items, 1, _MAX_UNIT_ITEMS)
        self.input_state = state
        self.state = state
        self.page: TiebaCreatorPage | None = None
        self.outcomes: list[TiebaWorkOutcome] = []
        self.reason: str | None = None

    def next_action(self) -> TiebaScanAction:
        if self.reason is not None:
            return TiebaScanAction("stop")
        if self.page is None:
            return TiebaScanAction("list", page=self.state.page)
        while (
            self.state.index < len(self.page.identities)
            and self.page.identities[self.state.index].thread_id in self.state.completed_thread_ids
        ):
            self.state = replace(self.state, index=self.state.index + 1)
        if self.state.index >= len(self.page.identities):
            self._finish_page()
            return TiebaScanAction("stop")
        if len(self.outcomes) >= self.limit:
            self.reason = "unit_cap_reached"
            return TiebaScanAction("stop")
        identity = self.page.identities[self.state.index]
        prior = {item.thread_id: item.listing_sha256 for item in self.state.head_boundary or ()}
        if self.state.lane == "head" and prior.get(identity.thread_id) == identity.listing_sha256:
            return TiebaScanAction("unchanged", identity=identity)
        return TiebaScanAction("detail", identity=identity)

    def observe_page(self, page: TiebaCreatorPage) -> None:
        action = self.next_action()
        if action.kind != "list" or type(page) is not TiebaCreatorPage or page.page != action.page:
            raise _invalid()
        if self.state.witness is not None:
            expected = self.state.witness
            observed = page.witness
            if (observed.page, observed.has_more, observed.thread_ids) != (
                expected.page,
                expected.has_more,
                expected.thread_ids,
            ):
                raise _invalid()
            prior_fingerprints = {item.thread_id: item.listing_sha256 for item in expected.identities}
            completed = tuple(
                item.thread_id
                for item in observed.identities
                if item.thread_id in self.state.completed_thread_ids
                and prior_fingerprints.get(item.thread_id) == item.listing_sha256
            )
            self.state = replace(self.state, witness=observed, index=0, completed_thread_ids=completed)
        self.page = page
        if self.state.witness is None:
            self.state = replace(self.state, witness=page.witness)
        if self.state.lane == "history" and self.state.page == 1 and self.state.head_boundary is None:
            self.state = replace(self.state, head_boundary=page.witness.identities)

    def observe_access_restricted(self) -> None:
        if self.next_action().kind != "list":
            raise _invalid()
        self.reason = "access_restricted"

    def store(self, identity: TiebaWorkIdentity) -> None:
        self._record(identity, "stored")

    def skip_unchanged(self, identity: TiebaWorkIdentity) -> None:
        self._record(identity, "unchanged")

    def fail(self, identity: TiebaWorkIdentity, *, access_restricted: bool = False) -> None:
        failed_index = self.state.index
        self._record(identity, "access_restricted" if access_restricted else "detail_unavailable")
        if access_restricted:
            self.state = replace(self.state, index=failed_index)
            self.reason = "access_restricted"

    def _record(self, identity: TiebaWorkIdentity, status: str) -> None:
        action = self.next_action()
        expected_kind = "unchanged" if status == "unchanged" else "detail"
        if action.kind != expected_kind or identity != action.identity:
            raise _invalid()
        self.outcomes.append(TiebaWorkOutcome(identity, status))
        completed = self.state.completed_thread_ids
        if status in {"stored", "unchanged"} and identity.thread_id not in completed:
            completed = (*completed, identity.thread_id)
        self.state = replace(self.state, index=self.state.index + 1, completed_thread_ids=completed)

    def _finish_page(self) -> None:
        page = self.page
        if page is None:
            raise _invalid()
        if len(self.state.completed_thread_ids) != len(page.identities):
            # max_items (or a failed detail) stopped the unit before the page
            # tail: keep the identical page number and witness so the next unit
            # re-issues the same request and skips already-delivered threads.
            self.reason = "unit_cap_reached"
            self.state = replace(self.state, index=0)
            return
        if self.state.lane == "head":
            self._finish_head(page)
            return
        page_ids = page.witness.thread_ids
        stalled = bool(page_ids) and page_ids == self.state.previous_page_thread_ids
        if not page.has_more:
            # The server declared the end; it is retained with the page witness
            # so reconciliation can confirm or reject the boundary.
            self.reason = "has_more_false"
            self.state = replace(
                self.state,
                page=1,
                witness=None,
                index=0,
                completed_thread_ids=(),
                previous_page_thread_ids=(),
                stalled_units=0,
            )
            return
        if not page_ids:
            self.reason = "empty_page_end"
            self.state = replace(
                self.state,
                page=1,
                witness=None,
                index=0,
                completed_thread_ids=(),
                previous_page_thread_ids=(),
                stalled_units=0,
            )
            return
        if stalled:
            # A server that keeps returning the same page cannot progress; the
            # cursor alone cannot detect this because ``pn`` always increments.
            self.reason = "unit_cap_reached"
            self.state = replace(
                self.state,
                page=self.state.page + 1,
                witness=None,
                index=0,
                completed_thread_ids=(),
                previous_page_thread_ids=page_ids,
                stalled_units=self.state.stalled_units + 1,
            )
            return
        self.reason = "unit_cap_reached"
        self.state = replace(
            self.state,
            page=self.state.page + 1,
            witness=None,
            index=0,
            completed_thread_ids=(),
            previous_page_thread_ids=page_ids,
            stalled_units=0,
        )

    def _finish_head(self, page: TiebaCreatorPage) -> None:
        if not page.has_more:
            self.reason = "has_more_false"
        elif not page.identities:
            self.reason = "empty_page_end"
        else:
            self.reason = "unit_cap_reached"
        self.state = replace(
            self.state,
            page=1,
            witness=None,
            index=0,
            completed_thread_ids=(),
            previous_page_thread_ids=(),
            stalled_units=0,
            head_boundary=page.witness.identities,
        )

    def coverage(self) -> TiebaScanCoverage:
        if self.next_action().kind != "stop" or self.reason is None:
            raise _invalid()
        page_complete = self.page is not None and self.state.witness is None
        summary = TiebaUnitSummary(
            self.input_state.lane,
            self.reason,
            sum(item.status == "stored" for item in self.outcomes),
            sum(item.status == "unchanged" for item in self.outcomes),
            sum(item.status not in {"stored", "unchanged"} for item in self.outcomes),
            1,
            sum(item.status != "unchanged" for item in self.outcomes),
            page_complete,
            self.input_state.page,
            None if self.page is None else self.page.has_more,
        )
        next_state = replace(self.state, last_unit=summary)
        return TiebaScanCoverage(self.input_state, next_state, self.page, tuple(self.outcomes), summary)


@dataclass(frozen=True, slots=True)
class TiebaScanCoverage:
    input_state: TiebaScanState
    next_state: TiebaScanState
    page: TiebaCreatorPage | None
    outcomes: tuple[TiebaWorkOutcome, ...]
    summary: TiebaUnitSummary

    @property
    def successful(self) -> tuple[TiebaWorkIdentity, ...]:
        return tuple(item.identity for item in self.outcomes if item.status == "stored")

    @property
    def failed(self) -> tuple[TiebaWorkOutcome, ...]:
        return tuple(item for item in self.outcomes if item.status not in {"stored", "unchanged"})

    @property
    def stop_reason(self) -> str:
        return self.summary.stop_reason

    @property
    def lane(self) -> str:
        return self.summary.lane

    @property
    def source_end_observed(self) -> bool:
        return self.summary.stop_reason in {"has_more_false", "empty_page_end"}

    @property
    def blocked_code(self) -> str | None:
        if self.next_state.stalled_units >= TB_STALLED_UNIT_LIMIT:
            return TB_STALL_BLOCKED_CODE
        return None

    def validate(
        self,
        input_state: TiebaScanState,
        max_items: int,
        normalized_remote_ids: tuple[str, ...] | None = None,
    ) -> None:
        if (
            type(input_state) is not TiebaScanState
            or self.input_state != input_state
            or type(self.outcomes) is not tuple
            or len(self.outcomes) > max_items
        ):
            raise _invalid()
        unit = TiebaScanUnit(input_state, max_items)
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
            and tuple(item.thread_id for item in self.successful) != normalized_remote_ids
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
    def from_json_line(cls, value: str) -> TiebaScanCoverage:
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
                "page_number",
                "has_more",
            },
        )
        if item["schema_version"] != 1 or type(item["outcomes"]) is not list:
            raise _invalid()
        result = cls(
            TiebaScanState.from_cursor(item["input_cursor"]),
            TiebaScanState.from_cursor(item["next_cursor"]),
            None if item["page"] is None else TiebaCreatorPage.from_mapping(item["page"]),
            tuple(TiebaWorkOutcome.from_mapping(row) for row in item["outcomes"]),
            TiebaUnitSummary.from_mapping(
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
                        "page_number",
                        "has_more",
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
    "TB_CREATOR_PAGE_SIZE",
    "TB_SCAN_COVERAGE_FILENAME",
    "TB_SCAN_CURSOR_PREFIX",
    "TB_SCAN_IDENTITY_FIELD",
    "TB_SCAN_STOP_REASONS",
    "TB_STALLED_UNIT_LIMIT",
    "TB_STALL_BLOCKED_CODE",
    "TiebaCreatorPage",
    "TiebaPageWitness",
    "TiebaScanAction",
    "TiebaScanCoverage",
    "TiebaScanState",
    "TiebaScanUnit",
    "TiebaUnitSummary",
    "TiebaWorkIdentity",
    "TiebaWorkOutcome",
]
