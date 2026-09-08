"""Closed, replayable XHS creator-note pagination without token disclosure."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

XHS_SCAN_CURSOR_PREFIX = "xhs-notes-v1:"
XHS_SCAN_COVERAGE_FILENAME = "_media_sync_xhs_coverage.jsonl"
XHS_SCAN_IDENTITY_FIELD = "__media_sync_xhs_note_identity"
XHS_CREATOR_PAGE_SIZE = 30
XHS_SCAN_STOP_REASONS = frozenset({"has_more_false", "empty_page_stalled", "access_restricted", "unit_cap_reached"})

_MAX_CURSOR_VALUE = 4_096
_MAX_CURSOR_PAYLOAD = 65_536
_MAX_COVERAGE_PAYLOAD = 131_072
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_XHS_ID = re.compile(r"[0-9a-f]{24}\Z")
_XSEC_SOURCE = re.compile(r"[A-Za-z0-9_]{1,64}\Z", re.ASCII)
_OUTCOME_STATUSES = frozenset({"stored", "unchanged", "detail_unavailable", "access_restricted"})


def _invalid() -> ValueError:
    return ValueError("invalid XHS creator-note scan contract")


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
    if type(value) is not list or len(value) > XHS_CREATOR_PAGE_SIZE:
        raise _invalid()
    result = tuple(value)
    if any(type(item) is not str or _XHS_ID.fullmatch(item) is None for item in result):
        raise _invalid()
    if len(result) != len(set(result)):
        raise _invalid()
    return result


@dataclass(frozen=True, slots=True)
class XhsListingIdentity:
    note_id: str
    listing_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.note_id) is not str
            or _XHS_ID.fullmatch(self.note_id) is None
            or type(self.listing_sha256) is not str
            or _SHA256.fullmatch(self.listing_sha256) is None
        ):
            raise _invalid()

    def as_mapping(self) -> dict[str, str]:
        return {"note_id": self.note_id, "listing_sha256": self.listing_sha256}

    @classmethod
    def from_mapping(cls, value: object) -> XhsListingIdentity:
        return cls(**_mapping(value, {"note_id", "listing_sha256"}))


@dataclass(frozen=True, slots=True)
class XhsNoteIdentity:
    """One page identity with only the digest of its short-lived token."""

    note_id: str
    listing_sha256: str
    token_sha256: str
    xsec_source: str

    def __post_init__(self) -> None:
        if (
            type(self.note_id) is not str
            or _XHS_ID.fullmatch(self.note_id) is None
            or type(self.listing_sha256) is not str
            or _SHA256.fullmatch(self.listing_sha256) is None
            or type(self.token_sha256) is not str
            or _SHA256.fullmatch(self.token_sha256) is None
            or type(self.xsec_source) is not str
            or _XSEC_SOURCE.fullmatch(self.xsec_source) is None
        ):
            raise _invalid()

    def as_mapping(self) -> dict[str, str]:
        return {
            "note_id": self.note_id,
            "listing_sha256": self.listing_sha256,
            "token_sha256": self.token_sha256,
            "xsec_source": self.xsec_source,
        }

    @classmethod
    def from_mapping(cls, value: object) -> XhsNoteIdentity:
        return cls(**_mapping(value, {"note_id", "listing_sha256", "token_sha256", "xsec_source"}))

    @property
    def listing_identity(self) -> XhsListingIdentity:
        return XhsListingIdentity(self.note_id, self.listing_sha256)


@dataclass(frozen=True, slots=True)
class XhsPageWitness:
    """Stable page shape persisted without any usable xsec token."""

    input_cursor: str
    next_cursor: str
    has_more: bool
    identities: tuple[XhsListingIdentity, ...]

    def __post_init__(self) -> None:
        _opaque_cursor(self.input_cursor)
        _opaque_cursor(self.next_cursor)
        if type(self.has_more) is not bool or type(self.identities) is not tuple:
            raise _invalid()
        if any(type(item) is not XhsListingIdentity for item in self.identities):
            raise _invalid()
        if len(self.identities) > XHS_CREATOR_PAGE_SIZE or len({item.note_id for item in self.identities}) != len(
            self.identities
        ):
            raise _invalid()
        if self.has_more and self.identities and self.next_cursor == self.input_cursor:
            raise _invalid()

    @property
    def note_ids(self) -> tuple[str, ...]:
        return tuple(item.note_id for item in self.identities)

    def as_mapping(self) -> dict[str, object]:
        return {
            "input_cursor": self.input_cursor,
            "next_cursor": self.next_cursor,
            "has_more": self.has_more,
            "identities": [item.as_mapping() for item in self.identities],
        }

    @classmethod
    def from_mapping(cls, value: object) -> XhsPageWitness:
        item = _mapping(value, {"input_cursor", "next_cursor", "has_more", "identities"})
        identities = item["identities"]
        if type(identities) is not list:
            raise _invalid()
        return cls(
            item["input_cursor"],
            item["next_cursor"],
            item["has_more"],
            tuple(XhsListingIdentity.from_mapping(row) for row in identities),
        )


@dataclass(frozen=True, slots=True)
class XhsCreatorPage:
    """One exact list response reduced to bounded identities and token digests."""

    input_cursor: str
    next_cursor: str
    has_more: bool
    identities: tuple[XhsNoteIdentity, ...]

    def __post_init__(self) -> None:
        witness = self.witness
        if type(self.identities) is not tuple or any(type(item) is not XhsNoteIdentity for item in self.identities):
            raise _invalid()
        if witness.note_ids != tuple(item.note_id for item in self.identities):
            raise _invalid()

    @property
    def witness(self) -> XhsPageWitness:
        return XhsPageWitness(
            self.input_cursor,
            self.next_cursor,
            self.has_more,
            tuple(item.listing_identity for item in self.identities),
        )

    def as_mapping(self) -> dict[str, object]:
        return {
            "input_cursor": self.input_cursor,
            "next_cursor": self.next_cursor,
            "has_more": self.has_more,
            "identities": [item.as_mapping() for item in self.identities],
        }

    @classmethod
    def from_mapping(cls, value: object) -> XhsCreatorPage:
        item = _mapping(value, {"input_cursor", "next_cursor", "has_more", "identities"})
        identities = item["identities"]
        if type(identities) is not list or len(identities) > XHS_CREATOR_PAGE_SIZE:
            raise _invalid()
        return cls(
            item["input_cursor"],
            item["next_cursor"],
            item["has_more"],
            tuple(XhsNoteIdentity.from_mapping(row) for row in identities),
        )


@dataclass(frozen=True, slots=True)
class XhsNoteOutcome:
    identity: XhsNoteIdentity
    status: str

    def __post_init__(self) -> None:
        if type(self.identity) is not XhsNoteIdentity or self.status not in _OUTCOME_STATUSES:
            raise _invalid()

    def as_mapping(self) -> dict[str, object]:
        return {"identity": self.identity.as_mapping(), "status": self.status}

    @classmethod
    def from_mapping(cls, value: object) -> XhsNoteOutcome:
        item = _mapping(value, {"identity", "status"})
        return cls(XhsNoteIdentity.from_mapping(item["identity"]), item["status"])


@dataclass(frozen=True, slots=True)
class XhsUnitSummary:
    lane: str
    stop_reason: str
    stored_count: int
    unchanged_count: int
    failed_count: int
    list_attempts: int
    detail_attempts: int
    page_complete: bool

    def __post_init__(self) -> None:
        if self.lane not in {"history", "head"} or self.stop_reason not in XHS_SCAN_STOP_REASONS:
            raise _invalid()
        _integer(self.stored_count, 0, XHS_CREATOR_PAGE_SIZE)
        _integer(self.unchanged_count, 0, XHS_CREATOR_PAGE_SIZE)
        _integer(self.failed_count, 0, XHS_CREATOR_PAGE_SIZE)
        _integer(self.list_attempts, 1, 1)
        _integer(self.detail_attempts, 0, XHS_CREATOR_PAGE_SIZE)
        if (
            self.detail_attempts != self.stored_count + self.failed_count
            or self.stored_count + self.unchanged_count + self.failed_count > XHS_CREATOR_PAGE_SIZE
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
    def from_mapping(cls, value: object) -> XhsUnitSummary:
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
class XhsScanState:
    account_id: UUID
    author_fingerprint_sha256: str
    creator_fingerprint_sha256: str
    upstream_sha: str
    lane: str = "history"
    page_cursor: str = ""
    witness: XhsPageWitness | None = None
    index: int = 0
    completed_note_ids: tuple[str, ...] = ()
    head_boundary: tuple[XhsListingIdentity, ...] | None = None
    last_unit: XhsUnitSummary | None = None

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
        _integer(self.index, 0, XHS_CREATOR_PAGE_SIZE)
        if type(self.completed_note_ids) is not tuple:
            raise _invalid()
        _note_ids(list(self.completed_note_ids))
        if self.witness is not None and (
            type(self.witness) is not XhsPageWitness
            or self.witness.input_cursor != self.page_cursor
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
                type(item) is not XhsListingIdentity for item in self.head_boundary
            ):
                raise _invalid()
            if len(self.head_boundary) > XHS_CREATOR_PAGE_SIZE or len(
                {item.note_id for item in self.head_boundary}
            ) != len(self.head_boundary):
                raise _invalid()
        if self.last_unit is not None and type(self.last_unit) is not XhsUnitSummary:
            raise _invalid()

    @classmethod
    def initial(
        cls,
        account_id: UUID,
        author_fingerprint_sha256: str,
        creator_fingerprint_sha256: str,
        upstream_sha: str,
    ) -> XhsScanState:
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

    def for_head(self) -> XhsScanState:
        if self.head_boundary is None:
            raise _invalid()
        return replace(
            self,
            lane="head",
            page_cursor="",
            witness=None,
            index=0,
            completed_note_ids=(),
            last_unit=None,
        )

    def to_cursor(self) -> str:
        payload = {
            "schema_version": 1,
            "feed": "creator_notes",
            "page_size": XHS_CREATOR_PAGE_SIZE,
            "account_id": str(self.account_id),
            "author_fingerprint_sha256": self.author_fingerprint_sha256,
            "creator_fingerprint_sha256": self.creator_fingerprint_sha256,
            "upstream_sha": self.upstream_sha,
            "lane": self.lane,
            "page_cursor": self.page_cursor,
            "witness": None if self.witness is None else self.witness.as_mapping(),
            "index": self.index,
            "completed_note_ids": list(self.completed_note_ids),
            "head_boundary": (
                None if self.head_boundary is None else [item.as_mapping() for item in self.head_boundary]
            ),
            "last_unit": None if self.last_unit is None else self.last_unit.as_mapping(),
        }
        result = XHS_SCAN_CURSOR_PREFIX + _dump(payload)
        if len(result) > _MAX_CURSOR_PAYLOAD:
            raise _invalid()
        return result

    @classmethod
    def from_cursor(cls, value: str) -> XhsScanState:
        if type(value) is not str or not value.startswith(XHS_SCAN_CURSOR_PREFIX):
            raise _invalid()
        item = _mapping(
            _json(value[len(XHS_SCAN_CURSOR_PREFIX) :], _MAX_CURSOR_PAYLOAD),
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
                "completed_note_ids",
                "head_boundary",
                "last_unit",
            },
        )
        if item["schema_version"] != 1 or item["feed"] != "creator_notes" or item["page_size"] != 30:
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
            None if item["witness"] is None else XhsPageWitness.from_mapping(item["witness"]),
            item["index"],
            _note_ids(item["completed_note_ids"]),
            (
                None
                if item["head_boundary"] is None
                else tuple(XhsListingIdentity.from_mapping(row) for row in item["head_boundary"])
            ),
            None if item["last_unit"] is None else XhsUnitSummary.from_mapping(item["last_unit"]),
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
    ) -> XhsScanState:
        if value is not None and type(value) is not str:
            raise _invalid()
        if value is None:
            return cls.initial(account_id, author_fingerprint_sha256, creator_fingerprint_sha256, upstream_sha)
        if not value.startswith(XHS_SCAN_CURSOR_PREFIX):
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
class XhsScanAction:
    kind: str
    cursor: str | None = None
    identity: XhsNoteIdentity | None = None


class XhsScanUnit:
    """One page-bound proposal that re-lists before using fresh note tokens."""

    def __init__(self, state: XhsScanState, max_items: int):
        if type(state) is not XhsScanState:
            raise _invalid()
        self.limit = min(_integer(max_items, 1, 1_000), XHS_CREATOR_PAGE_SIZE)
        self.input_state = state
        self.state = state
        self.page: XhsCreatorPage | None = None
        self.outcomes: list[XhsNoteOutcome] = []
        self.reason: str | None = None

    def next_action(self) -> XhsScanAction:
        if self.reason is not None:
            return XhsScanAction("stop")
        if self.page is None:
            return XhsScanAction("list", cursor=self.state.page_cursor)
        while (
            self.state.index < len(self.page.identities)
            and self.page.identities[self.state.index].note_id in self.state.completed_note_ids
        ):
            self.state = replace(self.state, index=self.state.index + 1)
        if self.state.index >= len(self.page.identities):
            self._finish_page()
            return XhsScanAction("stop")
        if len(self.outcomes) >= self.limit:
            self.reason = "unit_cap_reached"
            return XhsScanAction("stop")
        identity = self.page.identities[self.state.index]
        prior = {item.note_id: item.listing_sha256 for item in self.state.head_boundary or ()}
        if self.state.lane == "head" and prior.get(identity.note_id) == identity.listing_sha256:
            return XhsScanAction("unchanged", identity=identity)
        return XhsScanAction("detail", identity=identity)

    def observe_page(self, page: XhsCreatorPage) -> None:
        action = self.next_action()
        if action.kind != "list" or type(page) is not XhsCreatorPage or page.input_cursor != action.cursor:
            raise _invalid()
        if self.state.witness is not None:
            expected = self.state.witness
            observed = page.witness
            if (
                observed.input_cursor,
                observed.next_cursor,
                observed.has_more,
                observed.note_ids,
            ) != (expected.input_cursor, expected.next_cursor, expected.has_more, expected.note_ids):
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
        if self.state.lane == "history" and self.state.page_cursor == "" and self.state.head_boundary is None:
            self.state = replace(self.state, head_boundary=page.witness.identities)

    def observe_access_restricted(self) -> None:
        if self.next_action().kind != "list":
            raise _invalid()
        self.reason = "access_restricted"

    def store(self, identity: XhsNoteIdentity) -> None:
        self._record(identity, "stored")

    def skip_unchanged(self, identity: XhsNoteIdentity) -> None:
        self._record(identity, "unchanged")

    def fail(self, identity: XhsNoteIdentity, *, access_restricted: bool = False) -> None:
        failed_index = self.state.index
        self._record(identity, "access_restricted" if access_restricted else "detail_unavailable")
        if access_restricted:
            self.state = replace(self.state, index=failed_index)
            self.reason = "access_restricted"

    def _record(self, identity: XhsNoteIdentity, status: str) -> None:
        action = self.next_action()
        expected_kind = "unchanged" if status == "unchanged" else "detail"
        if action.kind != expected_kind or identity != action.identity:
            raise _invalid()
        self.outcomes.append(XhsNoteOutcome(identity, status))
        completed = self.state.completed_note_ids
        if status in {"stored", "unchanged"} and identity.note_id not in completed:
            completed = (*completed, identity.note_id)
        self.state = replace(self.state, index=self.state.index + 1, completed_note_ids=completed)

    def _finish_page(self) -> None:
        page = self.page
        if page is None:
            raise _invalid()
        if self.state.lane == "history":
            if len(self.state.completed_note_ids) != len(page.identities):
                self.reason = "unit_cap_reached"
                self.state = replace(self.state, index=0)
            elif not page.has_more:
                self.reason = "has_more_false"
                self.state = replace(
                    self.state,
                    page_cursor=page.next_cursor,
                    witness=None,
                    index=0,
                    completed_note_ids=(),
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
                    completed_note_ids=(),
                )
        else:
            if len(self.state.completed_note_ids) != len(page.identities):
                self.reason = "unit_cap_reached"
                self.state = replace(self.state, index=0)
                return
            self.reason = "has_more_false" if not page.has_more else "unit_cap_reached"
            self.state = replace(
                self.state,
                page_cursor="",
                witness=None,
                index=0,
                completed_note_ids=(),
                head_boundary=page.witness.identities,
            )

    def coverage(self) -> XhsScanCoverage:
        if self.next_action().kind != "stop" or self.reason is None:
            raise _invalid()
        page_complete = self.page is not None and self.state.witness is None
        summary = XhsUnitSummary(
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
        return XhsScanCoverage(self.input_state, next_state, self.page, tuple(self.outcomes), summary)


@dataclass(frozen=True, slots=True)
class XhsScanCoverage:
    input_state: XhsScanState
    next_state: XhsScanState
    page: XhsCreatorPage | None
    outcomes: tuple[XhsNoteOutcome, ...]
    summary: XhsUnitSummary

    @property
    def successful(self) -> tuple[XhsNoteIdentity, ...]:
        return tuple(item.identity for item in self.outcomes if item.status == "stored")

    @property
    def failed(self) -> tuple[XhsNoteOutcome, ...]:
        return tuple(item for item in self.outcomes if item.status not in {"stored", "unchanged"})

    @property
    def stop_reason(self) -> str:
        return self.summary.stop_reason

    @property
    def lane(self) -> str:
        return self.summary.lane

    def validate(
        self,
        input_state: XhsScanState,
        max_items: int,
        normalized_remote_ids: tuple[str, ...] | None = None,
    ) -> None:
        if (
            type(input_state) is not XhsScanState
            or self.input_state != input_state
            or type(self.outcomes) is not tuple
            or len(self.outcomes) > min(max_items, XHS_CREATOR_PAGE_SIZE)
        ):
            raise _invalid()
        unit = XhsScanUnit(input_state, max_items)
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
    def from_json_line(cls, value: str) -> XhsScanCoverage:
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
            XhsScanState.from_cursor(item["input_cursor"]),
            XhsScanState.from_cursor(item["next_cursor"]),
            None if item["page"] is None else XhsCreatorPage.from_mapping(item["page"]),
            tuple(XhsNoteOutcome.from_mapping(row) for row in item["outcomes"]),
            XhsUnitSummary.from_mapping(
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
    "XHS_CREATOR_PAGE_SIZE",
    "XHS_SCAN_COVERAGE_FILENAME",
    "XHS_SCAN_CURSOR_PREFIX",
    "XHS_SCAN_IDENTITY_FIELD",
    "XHS_SCAN_STOP_REASONS",
    "XhsCreatorPage",
    "XhsListingIdentity",
    "XhsNoteIdentity",
    "XhsNoteOutcome",
    "XhsPageWitness",
    "XhsScanAction",
    "XhsScanCoverage",
    "XhsScanState",
    "XhsScanUnit",
    "XhsUnitSummary",
]
