"""Closed, replayable Kuaishou creator-work pagination without disclosure.

Derived from the pinned MediaCrawler Kuaishou creator flow, not from the
Douyin or XHS shapes: the signed REST list endpoint ``/rest/v/profile/feed``
carries ``{user_id, pcursor, page: "profile"}`` with no client page size
(client.py:169-170), the opaque ``pcursor`` is echoed at the top level and
replayed verbatim (client.py:414, 434), the loop runs only while
``pcursor != "no_more"`` (client.py:416) and terminates client-side on an
empty ``feeds`` array (client.py:436-442).  The server alone decides each
page's size, so no fixed page-size bound exists here and the unit cap is
``max_items`` alone.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

KUAISHOU_SCAN_CURSOR_PREFIX = "ks-work-v1:"
KUAISHOU_SCAN_COVERAGE_FILENAME = "_media_sync_kuaishou_coverage.jsonl"
KUAISHOU_SCAN_IDENTITY_FIELD = "__media_sync_kuaishou_photo_identity"
KUAISHOU_SCAN_STOP_REASONS = frozenset({"no_more_echoed", "empty_page_end", "access_restricted", "unit_cap_reached"})
KUAISHOU_NO_MORE_SENTINEL = "no_more"
KUAISHOU_STALLED_UNIT_LIMIT = 3
KUAISHOU_STALL_BLOCKED_CODE = "kuaishou_cursor_stalled"

_MAX_CURSOR_VALUE = 4_096
_MAX_CURSOR_PAYLOAD = 65_536
_MAX_COVERAGE_PAYLOAD = 131_072
_MAX_UNIT_ITEMS = 1_000
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PHOTO_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_OUTCOME_STATUSES = frozenset({"stored", "unchanged", "detail_unavailable", "access_restricted"})


def _invalid() -> ValueError:
    return ValueError("invalid Kuaishou creator-work scan contract")


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


def _photo_ids(value: object) -> tuple[str, ...]:
    # No page-size bound: the server alone decides each page's size
    # (client.py:169 carries no count field), so lists are bounded only by
    # the cursor and coverage payload caps.
    if type(value) is not list:
        raise _invalid()
    result = tuple(value)
    if any(type(item) is not str or _PHOTO_ID.fullmatch(item) is None for item in result):
        raise _invalid()
    if len(result) != len(set(result)):
        raise _invalid()
    return result


@dataclass(frozen=True, slots=True)
class KuaishouWorkIdentity:
    """One page identity reduced to the stable ``photo.id`` and listing digest."""

    photo_id: str
    listing_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.photo_id) is not str
            or _PHOTO_ID.fullmatch(self.photo_id) is None
            or type(self.listing_sha256) is not str
            or _SHA256.fullmatch(self.listing_sha256) is None
        ):
            raise _invalid()

    def as_mapping(self) -> dict[str, str]:
        return {"photo_id": self.photo_id, "listing_sha256": self.listing_sha256}

    @classmethod
    def from_mapping(cls, value: object) -> KuaishouWorkIdentity:
        return cls(**_mapping(value, {"photo_id", "listing_sha256"}))


@dataclass(frozen=True, slots=True)
class KuaishouPageWitness:
    """Stable page shape persisted without any sign material or media URL.

    Unlike Douyin there is no ``has_more`` flag and no invariant forbidding
    ``next_cursor == input_cursor`` on a non-empty page: the echoed
    ``pcursor`` is the only continuation signal (client.py:434) and its
    non-advancement is the upstream-unchecked stall the durable layer must
    survive (client.py:416-448).
    """

    input_cursor: str
    next_cursor: str
    identities: tuple[KuaishouWorkIdentity, ...]

    def __post_init__(self) -> None:
        _opaque_cursor(self.input_cursor)
        _opaque_cursor(self.next_cursor)
        if type(self.identities) is not tuple:
            raise _invalid()
        if any(type(item) is not KuaishouWorkIdentity for item in self.identities):
            raise _invalid()
        if len({item.photo_id for item in self.identities}) != len(self.identities):
            raise _invalid()

    @property
    def photo_ids(self) -> tuple[str, ...]:
        return tuple(item.photo_id for item in self.identities)

    def as_mapping(self) -> dict[str, object]:
        return {
            "input_cursor": self.input_cursor,
            "next_cursor": self.next_cursor,
            "identities": [item.as_mapping() for item in self.identities],
        }

    @classmethod
    def from_mapping(cls, value: object) -> KuaishouPageWitness:
        item = _mapping(value, {"input_cursor", "next_cursor", "identities"})
        identities = item["identities"]
        if type(identities) is not list:
            raise _invalid()
        return cls(
            item["input_cursor"],
            item["next_cursor"],
            tuple(KuaishouWorkIdentity.from_mapping(row) for row in identities),
        )


@dataclass(frozen=True, slots=True)
class KuaishouCreatorPage:
    """One exact list response reduced to bounded work identities."""

    input_cursor: str
    next_cursor: str
    identities: tuple[KuaishouWorkIdentity, ...]

    def __post_init__(self) -> None:
        witness = self.witness
        if type(self.identities) is not tuple or any(
            type(item) is not KuaishouWorkIdentity for item in self.identities
        ):
            raise _invalid()
        if witness.photo_ids != tuple(item.photo_id for item in self.identities):
            raise _invalid()

    @property
    def witness(self) -> KuaishouPageWitness:
        return KuaishouPageWitness(self.input_cursor, self.next_cursor, self.identities)

    def as_mapping(self) -> dict[str, object]:
        return {
            "input_cursor": self.input_cursor,
            "next_cursor": self.next_cursor,
            "identities": [item.as_mapping() for item in self.identities],
        }

    @classmethod
    def from_mapping(cls, value: object) -> KuaishouCreatorPage:
        item = _mapping(value, {"input_cursor", "next_cursor", "identities"})
        identities = item["identities"]
        if type(identities) is not list:
            raise _invalid()
        return cls(
            item["input_cursor"],
            item["next_cursor"],
            tuple(KuaishouWorkIdentity.from_mapping(row) for row in identities),
        )


@dataclass(frozen=True, slots=True)
class KuaishouWorkOutcome:
    identity: KuaishouWorkIdentity
    status: str

    def __post_init__(self) -> None:
        if type(self.identity) is not KuaishouWorkIdentity or self.status not in _OUTCOME_STATUSES:
            raise _invalid()

    def as_mapping(self) -> dict[str, object]:
        return {"identity": self.identity.as_mapping(), "status": self.status}

    @classmethod
    def from_mapping(cls, value: object) -> KuaishouWorkOutcome:
        item = _mapping(value, {"identity", "status"})
        return cls(KuaishouWorkIdentity.from_mapping(item["identity"]), item["status"])


@dataclass(frozen=True, slots=True)
class KuaishouUnitSummary:
    lane: str
    stop_reason: str
    stored_count: int
    unchanged_count: int
    failed_count: int
    list_attempts: int
    detail_attempts: int
    page_complete: bool

    def __post_init__(self) -> None:
        if self.lane not in {"history", "head"} or self.stop_reason not in KUAISHOU_SCAN_STOP_REASONS:
            raise _invalid()
        _integer(self.stored_count, 0, _MAX_UNIT_ITEMS)
        _integer(self.unchanged_count, 0, _MAX_UNIT_ITEMS)
        _integer(self.failed_count, 0, _MAX_UNIT_ITEMS)
        _integer(self.list_attempts, 1, 1)
        _integer(self.detail_attempts, 0, _MAX_UNIT_ITEMS)
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
        }

    @classmethod
    def from_mapping(cls, value: object) -> KuaishouUnitSummary:
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
class KuaishouScanState:
    account_id: UUID
    author_fingerprint_sha256: str
    creator_fingerprint_sha256: str
    upstream_sha: str
    lane: str = "history"
    page_cursor: str = ""
    witness: KuaishouPageWitness | None = None
    index: int = 0
    completed_photo_ids: tuple[str, ...] = ()
    head_boundary: tuple[KuaishouWorkIdentity, ...] | None = None
    last_unit: KuaishouUnitSummary | None = None
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
        _opaque_cursor(self.page_cursor)
        _integer(self.index)
        _integer(self.stalled_units, 0, _MAX_UNIT_ITEMS)
        if type(self.completed_photo_ids) is not tuple:
            raise _invalid()
        _photo_ids(list(self.completed_photo_ids))
        if self.witness is not None and (
            type(self.witness) is not KuaishouPageWitness
            or self.witness.input_cursor != self.page_cursor
            or self.index > len(self.witness.photo_ids)
        ):
            raise _invalid()
        if self.witness is None and self.index:
            raise _invalid()
        if self.witness is None and self.completed_photo_ids:
            raise _invalid()
        if self.witness is not None and not set(self.completed_photo_ids).issubset(self.witness.photo_ids):
            raise _invalid()
        if self.head_boundary is not None:
            if type(self.head_boundary) is not tuple or any(
                type(item) is not KuaishouWorkIdentity for item in self.head_boundary
            ):
                raise _invalid()
            if len({item.photo_id for item in self.head_boundary}) != len(self.head_boundary):
                raise _invalid()
        if self.last_unit is not None and type(self.last_unit) is not KuaishouUnitSummary:
            raise _invalid()

    @classmethod
    def initial(
        cls,
        account_id: UUID,
        author_fingerprint_sha256: str,
        creator_fingerprint_sha256: str,
        upstream_sha: str,
    ) -> KuaishouScanState:
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

    def for_head(self) -> KuaishouScanState:
        if self.head_boundary is None:
            raise _invalid()
        return replace(
            self,
            lane="head",
            page_cursor="",
            witness=None,
            index=0,
            completed_photo_ids=(),
            last_unit=None,
            stalled_units=0,
        )

    def to_cursor(self) -> str:
        payload = {
            "schema_version": 1,
            "feed": "creator_works",
            "account_id": str(self.account_id),
            "author_fingerprint_sha256": self.author_fingerprint_sha256,
            "creator_fingerprint_sha256": self.creator_fingerprint_sha256,
            "upstream_sha": self.upstream_sha,
            "lane": self.lane,
            "page_cursor": self.page_cursor,
            "witness": None if self.witness is None else self.witness.as_mapping(),
            "index": self.index,
            "completed_photo_ids": list(self.completed_photo_ids),
            "head_boundary": (
                None if self.head_boundary is None else [item.as_mapping() for item in self.head_boundary]
            ),
            "stalled_units": self.stalled_units,
            "last_unit": None if self.last_unit is None else self.last_unit.as_mapping(),
        }
        result = KUAISHOU_SCAN_CURSOR_PREFIX + _dump(payload)
        if len(result) > _MAX_CURSOR_PAYLOAD:
            raise _invalid()
        return result

    @classmethod
    def from_cursor(cls, value: str) -> KuaishouScanState:
        if type(value) is not str or not value.startswith(KUAISHOU_SCAN_CURSOR_PREFIX):
            raise _invalid()
        item = _mapping(
            _json(value[len(KUAISHOU_SCAN_CURSOR_PREFIX) :], _MAX_CURSOR_PAYLOAD),
            {
                "schema_version",
                "feed",
                "account_id",
                "author_fingerprint_sha256",
                "creator_fingerprint_sha256",
                "upstream_sha",
                "lane",
                "page_cursor",
                "witness",
                "index",
                "completed_photo_ids",
                "head_boundary",
                "stalled_units",
                "last_unit",
            },
        )
        if item["schema_version"] != 1 or item["feed"] != "creator_works":
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
            None if item["witness"] is None else KuaishouPageWitness.from_mapping(item["witness"]),
            item["index"],
            _photo_ids(item["completed_photo_ids"]),
            (
                None
                if item["head_boundary"] is None
                else tuple(KuaishouWorkIdentity.from_mapping(row) for row in item["head_boundary"])
            ),
            None if item["last_unit"] is None else KuaishouUnitSummary.from_mapping(item["last_unit"]),
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
    ) -> KuaishouScanState:
        if value is not None and type(value) is not str:
            raise _invalid()
        if value is None:
            return cls.initial(account_id, author_fingerprint_sha256, creator_fingerprint_sha256, upstream_sha)
        if not value.startswith(KUAISHOU_SCAN_CURSOR_PREFIX):
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
            "stalled_units": self.stalled_units,
            "last_unit": None if self.last_unit is None else self.last_unit.as_mapping(),
            "next_action": f"continue_{self.lane}",
        }


@dataclass(frozen=True, slots=True)
class KuaishouScanAction:
    kind: str
    cursor: str | None = None
    identity: KuaishouWorkIdentity | None = None


class KuaishouScanUnit:
    """One page-bound proposal over the echoed ``pcursor`` chain."""

    def __init__(self, state: KuaishouScanState, max_items: int):
        if type(state) is not KuaishouScanState:
            raise _invalid()
        # No page-size clamp: the server alone decides each page's size, so
        # the unit cap is max_items alone (client.py:169 carries no count).
        self.limit = _integer(max_items, 1, _MAX_UNIT_ITEMS)
        self.input_state = state
        self.state = state
        self.page: KuaishouCreatorPage | None = None
        self.outcomes: list[KuaishouWorkOutcome] = []
        self.reason: str | None = None

    def next_action(self) -> KuaishouScanAction:
        if self.reason is not None:
            return KuaishouScanAction("stop")
        if self.page is None:
            return KuaishouScanAction("list", cursor=self.state.page_cursor)
        while (
            self.state.index < len(self.page.identities)
            and self.page.identities[self.state.index].photo_id in self.state.completed_photo_ids
        ):
            self.state = replace(self.state, index=self.state.index + 1)
        if self.state.index >= len(self.page.identities):
            self._finish_page()
            return KuaishouScanAction("stop")
        if len(self.outcomes) >= self.limit:
            self.reason = "unit_cap_reached"
            return KuaishouScanAction("stop")
        identity = self.page.identities[self.state.index]
        prior = {item.photo_id: item.listing_sha256 for item in self.state.head_boundary or ()}
        if self.state.lane == "head" and prior.get(identity.photo_id) == identity.listing_sha256:
            return KuaishouScanAction("unchanged", identity=identity)
        return KuaishouScanAction("detail", identity=identity)

    def observe_page(self, page: KuaishouCreatorPage) -> None:
        action = self.next_action()
        if action.kind != "list" or type(page) is not KuaishouCreatorPage or page.input_cursor != action.cursor:
            raise _invalid()
        if self.state.witness is not None:
            expected = self.state.witness
            observed = page.witness
            if (observed.input_cursor, observed.next_cursor, observed.photo_ids) != (
                expected.input_cursor,
                expected.next_cursor,
                expected.photo_ids,
            ):
                raise _invalid()
            prior_fingerprints = {item.photo_id: item.listing_sha256 for item in expected.identities}
            completed = tuple(
                item.photo_id
                for item in observed.identities
                if item.photo_id in self.state.completed_photo_ids
                and prior_fingerprints.get(item.photo_id) == item.listing_sha256
            )
            self.state = replace(self.state, witness=observed, index=0, completed_photo_ids=completed)
        self.page = page
        if self.state.witness is None:
            self.state = replace(self.state, witness=page.witness)
        if self.state.lane == "history" and self.state.page_cursor == "" and self.state.head_boundary is None:
            self.state = replace(self.state, head_boundary=page.witness.identities)

    def observe_access_restricted(self) -> None:
        if self.next_action().kind != "list":
            raise _invalid()
        self.reason = "access_restricted"

    def store(self, identity: KuaishouWorkIdentity) -> None:
        self._record(identity, "stored")

    def skip_unchanged(self, identity: KuaishouWorkIdentity) -> None:
        self._record(identity, "unchanged")

    def fail(self, identity: KuaishouWorkIdentity, *, access_restricted: bool = False) -> None:
        failed_index = self.state.index
        self._record(identity, "access_restricted" if access_restricted else "detail_unavailable")
        if access_restricted:
            self.state = replace(self.state, index=failed_index)
            self.reason = "access_restricted"

    def _record(self, identity: KuaishouWorkIdentity, status: str) -> None:
        action = self.next_action()
        expected_kind = "unchanged" if status == "unchanged" else "detail"
        if action.kind != expected_kind or identity != action.identity:
            raise _invalid()
        self.outcomes.append(KuaishouWorkOutcome(identity, status))
        completed = self.state.completed_photo_ids
        if status in {"stored", "unchanged"} and identity.photo_id not in completed:
            completed = (*completed, identity.photo_id)
        self.state = replace(self.state, index=self.state.index + 1, completed_photo_ids=completed)

    def _finish_page(self) -> None:
        page = self.page
        if page is None:
            raise _invalid()
        if self.state.lane == "history":
            if len(self.state.completed_photo_ids) != len(page.identities):
                # max_items (or a failed detail) stopped the unit before the
                # page tail: the input pcursor stays unchanged and the witness
                # is retained so the next unit re-issues the identical request
                # and skips already-delivered works by stable photo.id.
                self.reason = "unit_cap_reached"
                self.state = replace(self.state, index=0)
            elif not page.identities:
                # Empty feeds: upstream itself terminates here (client.py:436,
                # 440-442).  A server-echoed sentinel wins over the client
                # inference; otherwise the client-inferred end is recorded
                # under its own stop reason.
                if page.next_cursor == KUAISHOU_NO_MORE_SENTINEL:
                    self.reason = "no_more_echoed"
                else:
                    self.reason = "empty_page_end"
                self.state = replace(
                    self.state,
                    page_cursor=page.next_cursor,
                    witness=None,
                    index=0,
                    completed_photo_ids=(),
                    stalled_units=0,
                )
            elif page.next_cursor == KUAISHOU_NO_MORE_SENTINEL:
                # The server-echoed sentinel is the primary source-end
                # candidate (client.py:434, 416).
                self.reason = "no_more_echoed"
                self.state = replace(
                    self.state,
                    page_cursor=page.next_cursor,
                    witness=None,
                    index=0,
                    completed_photo_ids=(),
                    stalled_units=0,
                )
            elif page.next_cursor == page.input_cursor:
                # A non-empty page whose echoed pcursor equals its input
                # pcursor makes no progress (upstream never checks this,
                # client.py:416-448): retain the page for skip-on-replay and
                # count the stall toward the bounded blocked transition.
                self.reason = "unit_cap_reached"
                self.state = replace(self.state, index=0, stalled_units=self.state.stalled_units + 1)
            else:
                self.reason = "unit_cap_reached"
                self.state = replace(
                    self.state,
                    page_cursor=page.next_cursor,
                    witness=None,
                    index=0,
                    completed_photo_ids=(),
                    stalled_units=0,
                )
        else:
            if len(self.state.completed_photo_ids) != len(page.identities):
                self.reason = "unit_cap_reached"
                self.state = replace(self.state, index=0)
                return
            if page.next_cursor == KUAISHOU_NO_MORE_SENTINEL:
                self.reason = "no_more_echoed"
            elif not page.identities:
                self.reason = "empty_page_end"
            else:
                self.reason = "unit_cap_reached"
            self.state = replace(
                self.state,
                page_cursor="",
                witness=None,
                index=0,
                completed_photo_ids=(),
                stalled_units=0,
                head_boundary=page.witness.identities,
            )

    def coverage(self) -> KuaishouScanCoverage:
        if self.next_action().kind != "stop" or self.reason is None:
            raise _invalid()
        page_complete = self.page is not None and self.state.witness is None
        summary = KuaishouUnitSummary(
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
        return KuaishouScanCoverage(self.input_state, next_state, self.page, tuple(self.outcomes), summary)


@dataclass(frozen=True, slots=True)
class KuaishouScanCoverage:
    input_state: KuaishouScanState
    next_state: KuaishouScanState
    page: KuaishouCreatorPage | None
    outcomes: tuple[KuaishouWorkOutcome, ...]
    summary: KuaishouUnitSummary

    @property
    def successful(self) -> tuple[KuaishouWorkIdentity, ...]:
        return tuple(item.identity for item in self.outcomes if item.status == "stored")

    @property
    def failed(self) -> tuple[KuaishouWorkOutcome, ...]:
        return tuple(item for item in self.outcomes if item.status not in {"stored", "unchanged"})

    @property
    def stop_reason(self) -> str:
        return self.summary.stop_reason

    @property
    def lane(self) -> str:
        return self.summary.lane

    @property
    def blocked_code(self) -> str | None:
        """The fixed blocked code once consecutive stalled units exceed the bound."""

        if self.next_state.stalled_units >= KUAISHOU_STALLED_UNIT_LIMIT:
            return KUAISHOU_STALL_BLOCKED_CODE
        return None

    def validate(
        self,
        input_state: KuaishouScanState,
        max_items: int,
        normalized_remote_ids: tuple[str, ...] | None = None,
    ) -> None:
        if (
            type(input_state) is not KuaishouScanState
            or self.input_state != input_state
            or type(self.outcomes) is not tuple
            or len(self.outcomes) > max_items
        ):
            raise _invalid()
        unit = KuaishouScanUnit(input_state, max_items)
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
            and tuple(item.photo_id for item in self.successful) != normalized_remote_ids
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
    def from_json_line(cls, value: str) -> KuaishouScanCoverage:
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
            KuaishouScanState.from_cursor(item["input_cursor"]),
            KuaishouScanState.from_cursor(item["next_cursor"]),
            None if item["page"] is None else KuaishouCreatorPage.from_mapping(item["page"]),
            tuple(KuaishouWorkOutcome.from_mapping(row) for row in item["outcomes"]),
            KuaishouUnitSummary.from_mapping(
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
            "source_end_observed": self.stop_reason in {"no_more_echoed", "empty_page_end"},
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
    "KUAISHOU_NO_MORE_SENTINEL",
    "KUAISHOU_SCAN_COVERAGE_FILENAME",
    "KUAISHOU_SCAN_CURSOR_PREFIX",
    "KUAISHOU_SCAN_IDENTITY_FIELD",
    "KUAISHOU_SCAN_STOP_REASONS",
    "KUAISHOU_STALLED_UNIT_LIMIT",
    "KUAISHOU_STALL_BLOCKED_CODE",
    "KuaishouCreatorPage",
    "KuaishouPageWitness",
    "KuaishouScanAction",
    "KuaishouScanCoverage",
    "KuaishouScanState",
    "KuaishouScanUnit",
    "KuaishouUnitSummary",
    "KuaishouWorkIdentity",
    "KuaishouWorkOutcome",
]
