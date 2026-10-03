"""Closed, replayable Douyin creator-work pagination without disclosure."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

DOUYIN_SCAN_CURSOR_PREFIX = "dy-work-v1:"
DOUYIN_SCAN_COVERAGE_FILENAME = "_media_sync_douyin_coverage.jsonl"
DOUYIN_SCAN_IDENTITY_FIELD = "__media_sync_douyin_aweme_identity"
DOUYIN_CREATOR_PAGE_SIZE = 18
DOUYIN_SCAN_STOP_REASONS = frozenset({"has_more_false", "empty_page_stalled", "access_restricted", "unit_cap_reached"})

_MAX_CURSOR_VALUE = 4_096
_MAX_CURSOR_PAYLOAD = 65_536
_MAX_COVERAGE_PAYLOAD = 131_072
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_AWEME_ID = re.compile(r"[0-9]{10,20}\Z")
_OUTCOME_STATUSES = frozenset({"stored", "unchanged", "detail_unavailable", "access_restricted"})


def _invalid() -> ValueError:
    return ValueError("invalid Douyin creator-work scan contract")


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


def _aweme_ids(value: object) -> tuple[str, ...]:
    if type(value) is not list or len(value) > DOUYIN_CREATOR_PAGE_SIZE:
        raise _invalid()
    result = tuple(value)
    if any(type(item) is not str or _AWEME_ID.fullmatch(item) is None for item in result):
        raise _invalid()
    if len(result) != len(set(result)):
        raise _invalid()
    return result


@dataclass(frozen=True, slots=True)
class DouyinWorkIdentity:
    """One page identity reduced to the stable work id and listing digest."""

    aweme_id: str
    listing_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.aweme_id) is not str
            or _AWEME_ID.fullmatch(self.aweme_id) is None
            or type(self.listing_sha256) is not str
            or _SHA256.fullmatch(self.listing_sha256) is None
        ):
            raise _invalid()

    def as_mapping(self) -> dict[str, str]:
        return {"aweme_id": self.aweme_id, "listing_sha256": self.listing_sha256}

    @classmethod
    def from_mapping(cls, value: object) -> DouyinWorkIdentity:
        return cls(**_mapping(value, {"aweme_id", "listing_sha256"}))


@dataclass(frozen=True, slots=True)
class DouyinPageWitness:
    """Stable page shape persisted without any sign material or media URL."""

    input_cursor: str
    next_cursor: str
    has_more: bool
    identities: tuple[DouyinWorkIdentity, ...]

    def __post_init__(self) -> None:
        _opaque_cursor(self.input_cursor)
        _opaque_cursor(self.next_cursor)
        if type(self.has_more) is not bool or type(self.identities) is not tuple:
            raise _invalid()
        if any(type(item) is not DouyinWorkIdentity for item in self.identities):
            raise _invalid()
        if len(self.identities) > DOUYIN_CREATOR_PAGE_SIZE or len({item.aweme_id for item in self.identities}) != len(
            self.identities
        ):
            raise _invalid()
        if self.has_more and self.identities and self.next_cursor == self.input_cursor:
            raise _invalid()

    @property
    def aweme_ids(self) -> tuple[str, ...]:
        return tuple(item.aweme_id for item in self.identities)

    def as_mapping(self) -> dict[str, object]:
        return {
            "input_cursor": self.input_cursor,
            "next_cursor": self.next_cursor,
            "has_more": self.has_more,
            "identities": [item.as_mapping() for item in self.identities],
        }

    @classmethod
    def from_mapping(cls, value: object) -> DouyinPageWitness:
        item = _mapping(value, {"input_cursor", "next_cursor", "has_more", "identities"})
        identities = item["identities"]
        if type(identities) is not list:
            raise _invalid()
        return cls(
            item["input_cursor"],
            item["next_cursor"],
            item["has_more"],
            tuple(DouyinWorkIdentity.from_mapping(row) for row in identities),
        )


@dataclass(frozen=True, slots=True)
class DouyinCreatorPage:
    """One exact list response reduced to bounded work identities."""

    input_cursor: str
    next_cursor: str
    has_more: bool
    identities: tuple[DouyinWorkIdentity, ...]

    def __post_init__(self) -> None:
        witness = self.witness
        if type(self.identities) is not tuple or any(type(item) is not DouyinWorkIdentity for item in self.identities):
            raise _invalid()
        if witness.aweme_ids != tuple(item.aweme_id for item in self.identities):
            raise _invalid()

    @property
    def witness(self) -> DouyinPageWitness:
        return DouyinPageWitness(self.input_cursor, self.next_cursor, self.has_more, self.identities)

    def as_mapping(self) -> dict[str, object]:
        return {
            "input_cursor": self.input_cursor,
            "next_cursor": self.next_cursor,
            "has_more": self.has_more,
            "identities": [item.as_mapping() for item in self.identities],
        }

    @classmethod
    def from_mapping(cls, value: object) -> DouyinCreatorPage:
        item = _mapping(value, {"input_cursor", "next_cursor", "has_more", "identities"})
        identities = item["identities"]
        if type(identities) is not list or len(identities) > DOUYIN_CREATOR_PAGE_SIZE:
            raise _invalid()
        return cls(
            item["input_cursor"],
            item["next_cursor"],
            item["has_more"],
            tuple(DouyinWorkIdentity.from_mapping(row) for row in identities),
        )


@dataclass(frozen=True, slots=True)
class DouyinWorkOutcome:
    identity: DouyinWorkIdentity
    status: str

    def __post_init__(self) -> None:
        if type(self.identity) is not DouyinWorkIdentity or self.status not in _OUTCOME_STATUSES:
            raise _invalid()

    def as_mapping(self) -> dict[str, object]:
        return {"identity": self.identity.as_mapping(), "status": self.status}

    @classmethod
    def from_mapping(cls, value: object) -> DouyinWorkOutcome:
        item = _mapping(value, {"identity", "status"})
        return cls(DouyinWorkIdentity.from_mapping(item["identity"]), item["status"])


@dataclass(frozen=True, slots=True)
class DouyinUnitSummary:
    lane: str
    stop_reason: str
    stored_count: int
    unchanged_count: int
    failed_count: int
    list_attempts: int
    detail_attempts: int
    page_complete: bool

    def __post_init__(self) -> None:
        if self.lane not in {"history", "head"} or self.stop_reason not in DOUYIN_SCAN_STOP_REASONS:
            raise _invalid()
        _integer(self.stored_count, 0, DOUYIN_CREATOR_PAGE_SIZE)
        _integer(self.unchanged_count, 0, DOUYIN_CREATOR_PAGE_SIZE)
        _integer(self.failed_count, 0, DOUYIN_CREATOR_PAGE_SIZE)
        _integer(self.list_attempts, 1, 1)
        _integer(self.detail_attempts, 0, DOUYIN_CREATOR_PAGE_SIZE)
        if (
            self.detail_attempts != self.stored_count + self.failed_count
            or self.stored_count + self.unchanged_count + self.failed_count > DOUYIN_CREATOR_PAGE_SIZE
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
        }

    @classmethod
    def from_mapping(cls, value: object) -> DouyinUnitSummary:
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
                },
            )
        )


@dataclass(frozen=True, slots=True)
class DouyinScanState:
    account_id: UUID
    author_fingerprint_sha256: str
    creator_fingerprint_sha256: str
    upstream_sha: str
    lane: str = "history"
    page_cursor: str = ""
    witness: DouyinPageWitness | None = None
    index: int = 0
    completed_aweme_ids: tuple[str, ...] = ()
    head_boundary: tuple[DouyinWorkIdentity, ...] | None = None
    last_unit: DouyinUnitSummary | None = None

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
        _opaque_cursor(self.page_cursor)
        _integer(self.index, 0, DOUYIN_CREATOR_PAGE_SIZE)
        if type(self.completed_aweme_ids) is not tuple:
            raise _invalid()
        _aweme_ids(list(self.completed_aweme_ids))
        if self.witness is not None and (
            type(self.witness) is not DouyinPageWitness
            or self.witness.input_cursor != self.page_cursor
            or self.index > len(self.witness.aweme_ids)
        ):
            raise _invalid()
        if self.witness is None and self.index:
            raise _invalid()
        if self.witness is None and self.completed_aweme_ids:
            raise _invalid()
        if self.witness is not None and not set(self.completed_aweme_ids).issubset(self.witness.aweme_ids):
            raise _invalid()
        if self.head_boundary is not None:
            if type(self.head_boundary) is not tuple or any(
                type(item) is not DouyinWorkIdentity for item in self.head_boundary
            ):
                raise _invalid()
            if len(self.head_boundary) > DOUYIN_CREATOR_PAGE_SIZE or len(
                {item.aweme_id for item in self.head_boundary}
            ) != len(self.head_boundary):
                raise _invalid()
        if self.last_unit is not None and type(self.last_unit) is not DouyinUnitSummary:
            raise _invalid()

    @classmethod
    def initial(
        cls,
        account_id: UUID,
        author_fingerprint_sha256: str,
        creator_fingerprint_sha256: str,
        upstream_sha: str,
    ) -> DouyinScanState:
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

    def for_head(self) -> DouyinScanState:
        if self.head_boundary is None:
            raise _invalid()
        return replace(
            self,
            lane="head",
            page_cursor="",
            witness=None,
            index=0,
            completed_aweme_ids=(),
            last_unit=None,
        )

    def to_cursor(self) -> str:
        payload = {
            "schema_version": 1,
            "feed": "creator_works",
            "page_size": DOUYIN_CREATOR_PAGE_SIZE,
            "account_id": str(self.account_id),
            "author_fingerprint_sha256": self.author_fingerprint_sha256,
            "creator_fingerprint_sha256": self.creator_fingerprint_sha256,
            "upstream_sha": self.upstream_sha,
            "lane": self.lane,
            "page_cursor": self.page_cursor,
            "witness": None if self.witness is None else self.witness.as_mapping(),
            "index": self.index,
            "completed_aweme_ids": list(self.completed_aweme_ids),
            "head_boundary": (
                None if self.head_boundary is None else [item.as_mapping() for item in self.head_boundary]
            ),
            "last_unit": None if self.last_unit is None else self.last_unit.as_mapping(),
        }
        result = DOUYIN_SCAN_CURSOR_PREFIX + _dump(payload)
        if len(result) > _MAX_CURSOR_PAYLOAD:
            raise _invalid()
        return result

    @classmethod
    def from_cursor(cls, value: str) -> DouyinScanState:
        if type(value) is not str or not value.startswith(DOUYIN_SCAN_CURSOR_PREFIX):
            raise _invalid()
        item = _mapping(
            _json(value[len(DOUYIN_SCAN_CURSOR_PREFIX) :], _MAX_CURSOR_PAYLOAD),
            {
                "schema_version",
                "feed",
                "page_size",
                "account_id",
                "author_fingerprint_sha256",
                "creator_fingerprint_sha256",
                "upstream_sha",
                "lane",
                "page_cursor",
                "witness",
                "index",
                "completed_aweme_ids",
                "head_boundary",
                "last_unit",
            },
        )
        if item["schema_version"] != 1 or item["feed"] != "creator_works" or item["page_size"] != 18:
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
            item["page_cursor"],
            None if item["witness"] is None else DouyinPageWitness.from_mapping(item["witness"]),
            item["index"],
            _aweme_ids(item["completed_aweme_ids"]),
            (
                None
                if item["head_boundary"] is None
                else tuple(DouyinWorkIdentity.from_mapping(row) for row in item["head_boundary"])
            ),
            None if item["last_unit"] is None else DouyinUnitSummary.from_mapping(item["last_unit"]),
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
    ) -> DouyinScanState:
        if value is not None and type(value) is not str:
            raise _invalid()
        if value is None:
            return cls.initial(account_id, author_fingerprint_sha256, creator_fingerprint_sha256, upstream_sha)
        if not value.startswith(DOUYIN_SCAN_CURSOR_PREFIX):
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
            "head_boundary_established": self.head_boundary is not None,
            "last_unit": None if self.last_unit is None else self.last_unit.as_mapping(),
            "next_action": f"continue_{self.lane}",
        }


@dataclass(frozen=True, slots=True)
class DouyinScanAction:
    kind: str
    cursor: str | None = None
    identity: DouyinWorkIdentity | None = None


class DouyinScanUnit:
    """One page-bound proposal over the echoed ``max_cursor`` chain."""

    def __init__(self, state: DouyinScanState, max_items: int):
        if type(state) is not DouyinScanState:
            raise _invalid()
        self.limit = min(_integer(max_items, 1, 1_000), DOUYIN_CREATOR_PAGE_SIZE)
        self.input_state = state
        self.state = state
        self.page: DouyinCreatorPage | None = None
        self.outcomes: list[DouyinWorkOutcome] = []
        self.reason: str | None = None

    def next_action(self) -> DouyinScanAction:
        if self.reason is not None:
            return DouyinScanAction("stop")
        if self.page is None:
            return DouyinScanAction("list", cursor=self.state.page_cursor)
        while (
            self.state.index < len(self.page.identities)
            and self.page.identities[self.state.index].aweme_id in self.state.completed_aweme_ids
        ):
            self.state = replace(self.state, index=self.state.index + 1)
        if self.state.index >= len(self.page.identities):
            self._finish_page()
            return DouyinScanAction("stop")
        if len(self.outcomes) >= self.limit:
            self.reason = "unit_cap_reached"
            return DouyinScanAction("stop")
        identity = self.page.identities[self.state.index]
        prior = {item.aweme_id: item.listing_sha256 for item in self.state.head_boundary or ()}
        if self.state.lane == "head" and prior.get(identity.aweme_id) == identity.listing_sha256:
            return DouyinScanAction("unchanged", identity=identity)
        return DouyinScanAction("detail", identity=identity)

    def observe_page(self, page: DouyinCreatorPage) -> None:
        action = self.next_action()
        if action.kind != "list" or type(page) is not DouyinCreatorPage or page.input_cursor != action.cursor:
            raise _invalid()
        if self.state.witness is not None:
            expected = self.state.witness
            observed = page.witness
            if (
                observed.input_cursor,
                observed.next_cursor,
                observed.has_more,
                observed.aweme_ids,
            ) != (expected.input_cursor, expected.next_cursor, expected.has_more, expected.aweme_ids):
                raise _invalid()
            prior_fingerprints = {item.aweme_id: item.listing_sha256 for item in expected.identities}
            completed = tuple(
                item.aweme_id
                for item in observed.identities
                if item.aweme_id in self.state.completed_aweme_ids
                and prior_fingerprints.get(item.aweme_id) == item.listing_sha256
            )
            self.state = replace(self.state, witness=observed, index=0, completed_aweme_ids=completed)
        self.page = page
        if self.state.witness is None:
            self.state = replace(self.state, witness=page.witness)
        if self.state.lane == "history" and self.state.page_cursor == "" and self.state.head_boundary is None:
            self.state = replace(self.state, head_boundary=page.witness.identities)

    def observe_access_restricted(self) -> None:
        if self.next_action().kind != "list":
            raise _invalid()
        self.reason = "access_restricted"

    def store(self, identity: DouyinWorkIdentity) -> None:
        self._record(identity, "stored")

    def skip_unchanged(self, identity: DouyinWorkIdentity) -> None:
        self._record(identity, "unchanged")

    def fail(self, identity: DouyinWorkIdentity, *, access_restricted: bool = False) -> None:
        failed_index = self.state.index
        self._record(identity, "access_restricted" if access_restricted else "detail_unavailable")
        if access_restricted:
            self.state = replace(self.state, index=failed_index)
            self.reason = "access_restricted"

    def _record(self, identity: DouyinWorkIdentity, status: str) -> None:
        action = self.next_action()
        expected_kind = "unchanged" if status == "unchanged" else "detail"
        if action.kind != expected_kind or identity != action.identity:
            raise _invalid()
        self.outcomes.append(DouyinWorkOutcome(identity, status))
        completed = self.state.completed_aweme_ids
        if status in {"stored", "unchanged"} and identity.aweme_id not in completed:
            completed = (*completed, identity.aweme_id)
        self.state = replace(self.state, index=self.state.index + 1, completed_aweme_ids=completed)

    def _finish_page(self) -> None:
        page = self.page
        if page is None:
            raise _invalid()
        if self.state.lane == "history":
            if len(self.state.completed_aweme_ids) != len(page.identities):
                self.reason = "unit_cap_reached"
                self.state = replace(self.state, index=0)
            elif not page.has_more:
                self.reason = "has_more_false"
                self.state = replace(
                    self.state,
                    page_cursor=page.next_cursor,
                    witness=None,
                    index=0,
                    completed_aweme_ids=(),
                )
            elif not page.identities and page.next_cursor == page.input_cursor:
                self.reason = "empty_page_stalled"
            else:
                self.reason = "unit_cap_reached"
                self.state = replace(
                    self.state,
                    page_cursor=page.next_cursor,
                    witness=None,
                    index=0,
                    completed_aweme_ids=(),
                )
        else:
            if len(self.state.completed_aweme_ids) != len(page.identities):
                self.reason = "unit_cap_reached"
                self.state = replace(self.state, index=0)
                return
            self.reason = "has_more_false" if not page.has_more else "unit_cap_reached"
            self.state = replace(
                self.state,
                page_cursor="",
                witness=None,
                index=0,
                completed_aweme_ids=(),
                head_boundary=page.witness.identities,
            )

    def coverage(self) -> DouyinScanCoverage:
        if self.next_action().kind != "stop" or self.reason is None:
            raise _invalid()
        page_complete = self.page is not None and self.state.witness is None
        summary = DouyinUnitSummary(
            self.input_state.lane,
            self.reason,
            sum(item.status == "stored" for item in self.outcomes),
            sum(item.status == "unchanged" for item in self.outcomes),
            sum(item.status not in {"stored", "unchanged"} for item in self.outcomes),
            1,
            sum(item.status != "unchanged" for item in self.outcomes),
            page_complete,
        )
        next_state = replace(self.state, last_unit=summary)
        return DouyinScanCoverage(self.input_state, next_state, self.page, tuple(self.outcomes), summary)


@dataclass(frozen=True, slots=True)
class DouyinScanCoverage:
    input_state: DouyinScanState
    next_state: DouyinScanState
    page: DouyinCreatorPage | None
    outcomes: tuple[DouyinWorkOutcome, ...]
    summary: DouyinUnitSummary

    @property
    def successful(self) -> tuple[DouyinWorkIdentity, ...]:
        return tuple(item.identity for item in self.outcomes if item.status == "stored")

    @property
    def failed(self) -> tuple[DouyinWorkOutcome, ...]:
        return tuple(item for item in self.outcomes if item.status not in {"stored", "unchanged"})

    @property
    def stop_reason(self) -> str:
        return self.summary.stop_reason

    @property
    def lane(self) -> str:
        return self.summary.lane

    def validate(
        self,
        input_state: DouyinScanState,
        max_items: int,
        normalized_remote_ids: tuple[str, ...] | None = None,
    ) -> None:
        if (
            type(input_state) is not DouyinScanState
            or self.input_state != input_state
            or type(self.outcomes) is not tuple
            or len(self.outcomes) > min(max_items, DOUYIN_CREATOR_PAGE_SIZE)
        ):
            raise _invalid()
        unit = DouyinScanUnit(input_state, max_items)
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
            and tuple(item.aweme_id for item in self.successful) != normalized_remote_ids
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
    def from_json_line(cls, value: str) -> DouyinScanCoverage:
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
            },
        )
        if item["schema_version"] != 1 or type(item["outcomes"]) is not list:
            raise _invalid()
        result = cls(
            DouyinScanState.from_cursor(item["input_cursor"]),
            DouyinScanState.from_cursor(item["next_cursor"]),
            None if item["page"] is None else DouyinCreatorPage.from_mapping(item["page"]),
            tuple(DouyinWorkOutcome.from_mapping(row) for row in item["outcomes"]),
            DouyinUnitSummary.from_mapping(
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
            "source_end_observed": self.stop_reason == "has_more_false",
            "head_boundary_matches": (
                None
                if self.page is None or self.input_state.lane != "head"
                else self.input_state.head_boundary == self.page.witness.identities
            ),
            "next_action": f"continue_{self.next_state.lane}",
        }


__all__ = [
    "DOUYIN_CREATOR_PAGE_SIZE",
    "DOUYIN_SCAN_COVERAGE_FILENAME",
    "DOUYIN_SCAN_CURSOR_PREFIX",
    "DOUYIN_SCAN_IDENTITY_FIELD",
    "DOUYIN_SCAN_STOP_REASONS",
    "DouyinCreatorPage",
    "DouyinPageWitness",
    "DouyinScanAction",
    "DouyinScanCoverage",
    "DouyinScanState",
    "DouyinScanUnit",
    "DouyinUnitSummary",
    "DouyinWorkIdentity",
    "DouyinWorkOutcome",
]
