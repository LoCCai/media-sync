"""Versioned Bili feed proposals and private, immutable dynamic page snapshots.

The state machine has no network authority. Only exact detail confirmation may
consume a snapshot identity; snapshot discovery itself is a durable zero-record
unit. Original upload cursors and inactive feed state remain unchanged.
"""

from __future__ import annotations

import contextlib
import ctypes
import errno
import hashlib
import os
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import UUID

from media_sync.security.paths import (
    PathSecurityError,
    assert_existing_regular_file,
    assert_existing_secure_root,
    create_regular_file,
    ensure_secure_directory,
    read_regular_file_bytes,
    safe_unlink,
)

from .bilibili_dynamic import BiliDynamicIdentity, parse_dynamic_identity
from .bilibili_scan import (
    BiliIdentity,
    BiliScanCoverage,
    BiliScanState,
    _dump,
    _integer,
    _json,
    _mapping,
)

BILI_MULTIFEED_CURSOR_PREFIX = "bili-multifeed-v2:"
BILI_DYNAMIC_PAGE_SIZE = 30
BILI_DYNAMIC_SNAPSHOT_MAX_BYTES = 2 * 1024 * 1024
_MAX_CURSOR = 65_536
_MAX_COVERAGE = 262_144
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_OFFSET = re.compile(r"[A-Za-z0-9_-]{0,256}\Z")
_SCOPES = {"uploads", "dynamics", "both"}
_REASONS = {"snapshot_saved", "item_limit", "page_end", "source_end", "restarted"}


def _invalid() -> ValueError:
    return ValueError("invalid Bilibili multifeed contract")


def _scope(value: object) -> str:
    if type(value) is not str or value not in _SCOPES:
        raise _invalid()
    return value


def _offset(value: object) -> str:
    if type(value) is not str or _OFFSET.fullmatch(value) is None:
        raise _invalid()
    return value


def _digest(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise _invalid()
    return value


def _offset_digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class BiliDynamicSnapshotRef:
    digest: str
    offset: str
    next_offset: str
    source_end: bool
    count: int

    def __post_init__(self) -> None:
        _digest(self.digest)
        _offset(self.offset)
        _offset(self.next_offset)
        _integer(self.count, 0, BILI_DYNAMIC_PAGE_SIZE)
        if type(self.source_end) is not bool or (not self.source_end and not self.next_offset):
            raise _invalid()

    def as_mapping(self) -> dict[str, object]:
        return {
            "digest": self.digest,
            "offset": self.offset,
            "next_offset": self.next_offset,
            "source_end": self.source_end,
            "count": self.count,
        }

    @classmethod
    def from_mapping(cls, value: object) -> BiliDynamicSnapshotRef:
        return cls(**_mapping(value, {"digest", "offset", "next_offset", "source_end", "count"}))


@dataclass(frozen=True, slots=True)
class BiliDynamicPage:
    ref: BiliDynamicSnapshotRef
    identities: tuple[BiliDynamicIdentity, ...]

    def __post_init__(self) -> None:
        if type(self.ref) is not BiliDynamicSnapshotRef or type(self.identities) is not tuple:
            raise _invalid()
        if len(self.identities) != self.ref.count or any(
            type(item) is not BiliDynamicIdentity for item in self.identities
        ):
            raise _invalid()
        if len({item.did for item in self.identities}) != len(self.identities):
            raise _invalid()

    def as_mapping(self) -> dict[str, object]:
        return {"ref": self.ref.as_mapping(), "identities": [item.as_mapping() for item in self.identities]}

    @classmethod
    def from_mapping(cls, value: object) -> BiliDynamicPage:
        item = _mapping(value, {"ref", "identities"})
        if type(item["identities"]) is not list or len(item["identities"]) > BILI_DYNAMIC_PAGE_SIZE:
            raise _invalid()
        return cls(
            BiliDynamicSnapshotRef.from_mapping(item["ref"]),
            tuple(BiliDynamicIdentity.from_mapping(row) for row in item["identities"]),
        )


def _rename_snapshot_no_replace(source: Path, destination: Path) -> None:
    """Publish one complete inode atomically, never replacing an existing blob.

    A link/unlink sequence is insufficient: process death between those calls
    leaves a two-link final blob that the private regular-file reader rejects.
    These are the same native no-replace primitives used by the Emby publisher.
    Unsupported filesystems fail closed instead of using a clobbering rename.
    """
    if os.name == "nt":
        os.rename(source, destination)
        return
    library = ctypes.CDLL(None, use_errno=True)
    source_bytes, destination_bytes = os.fsencode(source), os.fsencode(destination)
    result = -1
    if sys.platform.startswith("linux"):
        rename = getattr(library, "renameat2", None)
        if rename is None:
            raise OSError(errno.ENOTSUP, "atomic snapshot publication is unavailable")
        result = rename(
            ctypes.c_int(-100),
            ctypes.c_char_p(source_bytes),
            ctypes.c_int(-100),
            ctypes.c_char_p(destination_bytes),
            ctypes.c_uint(1),
        )
    elif sys.platform == "darwin":
        rename = getattr(library, "renamex_np", None)
        if rename is None:
            raise OSError(errno.ENOTSUP, "atomic snapshot publication is unavailable")
        result = rename(ctypes.c_char_p(source_bytes), ctypes.c_char_p(destination_bytes), ctypes.c_uint(4))
    else:
        raise OSError(errno.ENOTSUP, "atomic snapshot publication is unavailable")
    if result == 0:
        return
    error = ctypes.get_errno()
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error, "snapshot destination already exists")
    raise OSError(error, "atomic snapshot publication failed")


def _fsync_snapshot_directory(directory: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


class BiliDynamicSnapshotStore:
    """Append-only bounded page blobs confined to one account/creator/SHA scope."""

    def __init__(
        self,
        account_root: Path,
        *,
        account_id: UUID,
        author_fingerprint_sha256: str,
        upstream_sha: str,
        creator_id: int,
    ) -> None:
        self.binding = BiliScanState.initial(account_id, author_fingerprint_sha256, upstream_sha)
        self.creator_id = _integer(creator_id, 1)
        self.account_root = assert_existing_secure_root(account_root)
        if self.account_root.resolve() != self.account_root:
            raise _invalid()
        self.relative = Path("dynamic-snapshots") / str(account_id) / author_fingerprint_sha256 / upstream_sha

    def _binding_mapping(self) -> dict[str, object]:
        return {
            "account_id": str(self.binding.account_id),
            "author_fingerprint_sha256": self.binding.author_fingerprint_sha256,
            "upstream_sha": self.binding.upstream_sha,
            "creator_id": self.creator_id,
        }

    def _page(self, payload: bytes) -> BiliDynamicPage:
        if len(payload) > BILI_DYNAMIC_SNAPSHOT_MAX_BYTES:
            raise _invalid()
        try:
            item = _mapping(
                _json(payload.decode("utf-8"), BILI_DYNAMIC_SNAPSHOT_MAX_BYTES),
                {"schema_version", "binding", "offset", "data"},
            )
        except UnicodeDecodeError as error:
            raise _invalid() from error
        if (
            type(item["schema_version"]) is not int
            or item["schema_version"] != 1
            or item["binding"] != self._binding_mapping()
        ):
            raise _invalid()
        data = item["data"]
        if type(data) is not dict or type(data.get("items")) is not list:
            raise _invalid()
        if len(data["items"]) > BILI_DYNAMIC_PAGE_SIZE:
            raise _invalid()
        has_more = data.get("has_more")
        if type(has_more) not in {bool, int} or has_more not in {0, 1}:
            raise _invalid()
        next_offset = _offset(data.get("offset", ""))
        identities = tuple(parse_dynamic_identity(row, self.creator_id) for row in data["items"])
        return BiliDynamicPage(
            BiliDynamicSnapshotRef(
                hashlib.sha256(payload).hexdigest(),
                _offset(item["offset"]),
                next_offset,
                not bool(has_more),
                len(identities),
            ),
            identities,
        )

    def persist(self, offset: str, data: dict[str, Any]) -> BiliDynamicPage:
        """Return a reference only after the canonical private page has been fsynced."""

        _offset(offset)
        payload = _dump(
            {"schema_version": 1, "binding": self._binding_mapping(), "offset": offset, "data": data}
        ).encode("utf-8")
        page = self._page(payload)
        directory = self.account_root
        for component in self.relative.parts:
            parent = directory
            directory = ensure_secure_directory(directory, component)
            if os.name != "nt":
                os.chmod(directory, 0o700)
            # Persist each newly created directory entry before publishing a
            # cursor that depends on the complete account/creator/SHA chain.
            _fsync_snapshot_directory(parent)
        path = directory / f"{page.ref.digest}.json"
        if path.exists() or path.is_symlink():
            if (
                read_regular_file_bytes(path, root=self.account_root, max_bytes=BILI_DYNAMIC_SNAPSHOT_MAX_BYTES)
                != payload
            ):
                raise _invalid()
        else:
            temporary = path.with_name(f".{page.ref.digest}.{os.urandom(12).hex()}.tmp")
            created_identity: tuple[int, int] | None = None
            try:
                with create_regular_file(temporary, root=self.account_root) as handle:
                    created = os.fstat(handle.fileno())
                    created_identity = created.st_dev, created.st_ino
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                if (
                    read_regular_file_bytes(
                        temporary, root=self.account_root, max_bytes=BILI_DYNAMIC_SNAPSHOT_MAX_BYTES
                    )
                    != payload
                ):
                    raise _invalid()
                try:
                    _rename_snapshot_no_replace(temporary, path)
                except FileExistsError:
                    # Another complete publisher may win. Its bytes must match;
                    # an existing malformed/tampered blob is never replaced.
                    if (
                        read_regular_file_bytes(path, root=self.account_root, max_bytes=BILI_DYNAMIC_SNAPSHOT_MAX_BYTES)
                        != payload
                    ):
                        raise _invalid() from None
            finally:
                # Remove only this invocation's temporary inode. A killed
                # process may leave an unreferenced .tmp; loading a cursor can
                # only address the final digest.json name and never adopts it.
                if created_identity is not None:
                    with contextlib.suppress(OSError, PathSecurityError):
                        current = assert_existing_regular_file(temporary, root=self.account_root)
                        if (current.st_dev, current.st_ino) == created_identity:
                            safe_unlink(temporary, root=self.account_root)
        # Include the existing-file path: a preceding process may have died
        # after atomic rename but before its directory flush acknowledged.
        _fsync_snapshot_directory(directory)
        if self.load(page.ref) != page:
            raise _invalid()
        return page

    def load(self, ref: BiliDynamicSnapshotRef) -> BiliDynamicPage:
        if type(ref) is not BiliDynamicSnapshotRef:
            raise _invalid()
        path = self.account_root / self.relative / f"{ref.digest}.json"
        payload = read_regular_file_bytes(path, root=self.account_root, max_bytes=BILI_DYNAMIC_SNAPSHOT_MAX_BYTES)
        if hashlib.sha256(payload).hexdigest() != ref.digest:
            raise _invalid()
        page = self._page(payload)
        if page.ref != ref:
            raise _invalid()
        return page


@dataclass(frozen=True, slots=True)
class BiliDynamicLane:
    offset: str = ""
    snapshot: BiliDynamicSnapshotRef | None = None
    index: int = 0
    seen_offsets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _offset(self.offset)
        _integer(self.index, 0, BILI_DYNAMIC_PAGE_SIZE)
        if self.snapshot is None:
            if self.index:
                raise _invalid()
        elif (
            type(self.snapshot) is not BiliDynamicSnapshotRef
            or self.snapshot.offset != self.offset
            or self.index > self.snapshot.count
        ):
            raise _invalid()
        if type(self.seen_offsets) is not tuple or len(self.seen_offsets) > 64:
            raise _invalid()
        for value in self.seen_offsets:
            _digest(value)
        if len(set(self.seen_offsets)) != len(self.seen_offsets):
            raise _invalid()

    def as_mapping(self) -> dict[str, object]:
        return {
            "offset": self.offset,
            "snapshot": None if self.snapshot is None else self.snapshot.as_mapping(),
            "index": self.index,
            "seen_offsets": list(self.seen_offsets),
        }

    @classmethod
    def from_mapping(cls, value: object) -> BiliDynamicLane:
        item = _mapping(value, {"offset", "snapshot", "index", "seen_offsets"})
        if type(item["seen_offsets"]) is not list:
            raise _invalid()
        return cls(
            item["offset"],
            None if item["snapshot"] is None else BiliDynamicSnapshotRef.from_mapping(item["snapshot"]),
            item["index"],
            tuple(item["seen_offsets"]),
        )


@dataclass(frozen=True, slots=True)
class BiliDynamicState:
    next_lane: str = "head"
    head: BiliDynamicLane = BiliDynamicLane()
    history: BiliDynamicLane = BiliDynamicLane()

    def __post_init__(self) -> None:
        if (
            type(self.next_lane) is not str
            or self.next_lane not in {"head", "history"}
            or type(self.head) is not BiliDynamicLane
            or type(self.history) is not BiliDynamicLane
        ):
            raise _invalid()

    def as_mapping(self) -> dict[str, object]:
        return {"next_lane": self.next_lane, "head": self.head.as_mapping(), "history": self.history.as_mapping()}

    @classmethod
    def from_mapping(cls, value: object) -> BiliDynamicState:
        item = _mapping(value, {"next_lane", "head", "history"})
        return cls(
            item["next_lane"], BiliDynamicLane.from_mapping(item["head"]), BiliDynamicLane.from_mapping(item["history"])
        )

    def public_summary(self) -> dict[str, object]:
        head_pending = 0 if self.head.snapshot is None else self.head.snapshot.count - self.head.index
        history_pending = 0 if self.history.snapshot is None else self.history.snapshot.count - self.history.index
        return {
            "next_lane": self.next_lane,
            "pending_count": head_pending + history_pending,
            "head_pending_count": head_pending,
            "history_pending_count": history_pending,
            "head_has_offset": bool(self.head.offset),
            "history_has_offset": bool(self.history.offset),
            "head_active": True,
            "history_active": True,
        }


@dataclass(frozen=True, slots=True)
class BiliMultiFeedState:
    uploads: BiliScanState
    scope: str
    next_feed: str = "uploads"
    dynamics: BiliDynamicState = BiliDynamicState()

    def __post_init__(self) -> None:
        _scope(self.scope)
        if type(self.uploads) is not BiliScanState or type(self.dynamics) is not BiliDynamicState:
            raise _invalid()
        if (
            type(self.next_feed) is not str
            or self.next_feed not in {"uploads", "dynamics"}
            or (self.scope != "both" and self.next_feed != self.scope)
        ):
            raise _invalid()

    @property
    def account_id(self) -> UUID:
        return self.uploads.account_id

    @property
    def author_fingerprint_sha256(self) -> str:
        return self.uploads.author_fingerprint_sha256

    @property
    def upstream_sha(self) -> str:
        return self.uploads.upstream_sha

    def require_binding(self, *, account_id: UUID, author_fingerprint_sha256: str, upstream_sha: str) -> None:
        self.uploads.require_binding(
            account_id=account_id, author_fingerprint_sha256=author_fingerprint_sha256, upstream_sha=upstream_sha
        )

    def with_scope(self, scope: str) -> BiliMultiFeedState:
        return replace(self, scope=_scope(scope), next_feed=self.next_feed if scope == "both" else scope)

    def to_cursor(self) -> str:
        value = BILI_MULTIFEED_CURSOR_PREFIX + _dump(
            {
                "schema_version": 2,
                "scope": self.scope,
                "next_feed": self.next_feed,
                "uploads_cursor": self.uploads.to_cursor(),
                "dynamics": self.dynamics.as_mapping(),
            }
        )
        if len(value) > _MAX_CURSOR:
            raise _invalid()
        return value

    @classmethod
    def from_cursor(cls, cursor: str) -> BiliMultiFeedState:
        if type(cursor) is not str or not cursor.startswith(BILI_MULTIFEED_CURSOR_PREFIX):
            raise _invalid()
        item = _mapping(
            _json(cursor[len(BILI_MULTIFEED_CURSOR_PREFIX) :], _MAX_CURSOR),
            {"schema_version", "scope", "next_feed", "uploads_cursor", "dynamics"},
        )
        if type(item["schema_version"]) is not int or item["schema_version"] != 2:
            raise _invalid()
        result = cls(
            BiliScanState.from_cursor(item["uploads_cursor"]),
            item["scope"],
            item["next_feed"],
            BiliDynamicState.from_mapping(item["dynamics"]),
        )
        if result.to_cursor() != cursor:
            raise _invalid()
        return result

    def public_summary(self) -> dict[str, object]:
        return {
            "version": 2,
            "scope": self.scope,
            "next_feed": self.next_feed,
            "uploads": {**self.uploads.public_summary(), "active": self.scope != "dynamics"},
            "dynamics": {**self.dynamics.public_summary(), "active": self.scope != "uploads"},
            "next_action": f"continue_{self.next_feed}",
        }


def state_from_cursor(cursor: str) -> BiliScanState | BiliMultiFeedState:
    if type(cursor) is str and cursor.startswith(BILI_MULTIFEED_CURSOR_PREFIX):
        return BiliMultiFeedState.from_cursor(cursor)
    return BiliScanState.from_cursor(cursor)


def state_for_cursor(
    cursor: str | None,
    *,
    account_id: UUID,
    author_fingerprint_sha256: str,
    upstream_sha: str,
    scope: str | None = None,
) -> BiliScanState | BiliMultiFeedState:
    if cursor is not None and type(cursor) is not str:
        raise _invalid()
    if scope is not None:
        _scope(scope)
    if cursor is not None and cursor.startswith("bili-multifeed"):
        composite = BiliMultiFeedState.from_cursor(cursor)
        composite.require_binding(
            account_id=account_id, author_fingerprint_sha256=author_fingerprint_sha256, upstream_sha=upstream_sha
        )
        return composite.with_scope(scope or "uploads")
    uploads = BiliScanState.for_cursor(
        cursor, account_id=account_id, author_fingerprint_sha256=author_fingerprint_sha256, upstream_sha=upstream_sha
    )
    return (
        uploads
        if scope is None
        else BiliMultiFeedState(uploads, scope, "dynamics" if scope == "dynamics" else "uploads")
    )


@dataclass(frozen=True, slots=True)
class BiliDynamicConsumption:
    identity: BiliDynamicIdentity
    video_identity: BiliIdentity | None = None

    def __post_init__(self) -> None:
        if type(self.identity) is not BiliDynamicIdentity:
            raise _invalid()
        if (self.identity.dynamic_type == "DYNAMIC_TYPE_AV") != (self.video_identity is not None):
            raise _invalid()
        if self.video_identity is not None and type(self.video_identity) is not BiliIdentity:
            raise _invalid()
        if self.identity.dynamic_type not in {"DYNAMIC_TYPE_WORD", "DYNAMIC_TYPE_DRAW", "DYNAMIC_TYPE_AV"}:
            raise _invalid()

    @property
    def cost(self) -> int:
        return 2 if self.video_identity is not None else 1

    def as_mapping(self) -> dict[str, object]:
        return {
            "identity": self.identity.as_mapping(),
            "video_identity": None if self.video_identity is None else self.video_identity.as_mapping(),
        }

    @classmethod
    def from_mapping(cls, value: object) -> BiliDynamicConsumption:
        item = _mapping(value, {"identity", "video_identity"})
        return cls(
            BiliDynamicIdentity.from_mapping(item["identity"]),
            None if item["video_identity"] is None else BiliIdentity.from_mapping(item["video_identity"]),
        )


@dataclass(frozen=True, slots=True)
class BiliDynamicAction:
    kind: str
    offset: str | None = None
    snapshot: BiliDynamicSnapshotRef | None = None
    identity: BiliDynamicIdentity | None = None


class BiliDynamicUnit:
    """One fair dynamic-lane page proposal; failed detail leaves its index intact."""

    def __init__(self, state: BiliMultiFeedState, max_items: int):
        if type(state) is not BiliMultiFeedState or state.next_feed != "dynamics":
            raise _invalid()
        self.limit = min(_integer(max_items, 2, 1_000), BILI_DYNAMIC_PAGE_SIZE)
        self.input_state = self.state = state
        self.lane = state.dynamics.next_lane
        self.page: BiliDynamicPage | None = None
        self.observation: str | None = None
        self.consumed: list[BiliDynamicConsumption] = []
        self.reason: str | None = None

    @property
    def current(self) -> BiliDynamicLane:
        return self.state.dynamics.head if self.lane == "head" else self.state.dynamics.history

    def _set_lane(self, lane: BiliDynamicLane) -> None:
        dynamic = (
            replace(self.state.dynamics, head=lane)
            if self.lane == "head"
            else replace(self.state.dynamics, history=lane)
        )
        self.state = replace(self.state, dynamics=dynamic)

    def next_action(self) -> BiliDynamicAction:
        if self.reason is not None:
            return BiliDynamicAction("stop")
        current = self.current
        if current.snapshot is None:
            return BiliDynamicAction("list", offset=current.offset)
        if self.page is None:
            return BiliDynamicAction("load", snapshot=current.snapshot)
        if current.index == len(self.page.identities):
            ref = self.page.ref
            if ref.source_end:
                self._set_lane(BiliDynamicLane())
                self.reason = "source_end"
            elif ref.next_offset == current.offset or _offset_digest(ref.next_offset) in current.seen_offsets:
                self._set_lane(BiliDynamicLane())
                self.reason = "restarted"
            else:
                seen = (*current.seen_offsets, _offset_digest(current.offset))[-64:]
                self._set_lane(BiliDynamicLane(offset=ref.next_offset, seen_offsets=seen))
                self.reason = "page_end"
            return BiliDynamicAction("stop")
        identity = self.page.identities[current.index]
        cost = 2 if identity.dynamic_type == "DYNAMIC_TYPE_AV" else 1
        if sum(item.cost for item in self.consumed) + cost > self.limit:
            self.reason = "item_limit"
            return BiliDynamicAction("stop")
        return BiliDynamicAction("detail", identity=identity)

    def observe_page(self, page: BiliDynamicPage) -> None:
        action = self.next_action()
        if type(page) is not BiliDynamicPage or action.kind not in {"list", "load"}:
            raise _invalid()
        if action.kind == "list":
            if page.ref.offset != action.offset:
                raise _invalid()
            self._set_lane(replace(self.current, snapshot=page.ref))
            self.reason = "snapshot_saved"
        elif page.ref != action.snapshot:
            raise _invalid()
        self.page = page
        self.observation = action.kind

    def consume(self, identity: BiliDynamicIdentity, video_identity: BiliIdentity | None = None) -> None:
        action = self.next_action()
        if action.kind != "detail" or action.identity != identity:
            raise _invalid()
        consumed = BiliDynamicConsumption(identity, video_identity)
        for previous in self.consumed:
            if previous.identity.did == identity.did:
                raise _invalid()
            if (
                previous.video_identity is not None
                and video_identity is not None
                and (
                    previous.video_identity.aid == video_identity.aid
                    or previous.video_identity.bvid == video_identity.bvid
                )
                and previous.video_identity != video_identity
            ):
                raise _invalid()
        self.consumed.append(consumed)
        self._set_lane(replace(self.current, index=self.current.index + 1))

    def coverage(self) -> BiliMultiFeedCoverage:
        if self.next_action().kind != "stop" or self.reason is None or self.page is None or self.observation is None:
            raise _invalid()
        dynamic = replace(self.state.dynamics, next_lane="history" if self.lane == "head" else "head")
        next_state = replace(
            self.state, dynamics=dynamic, next_feed="uploads" if self.state.scope == "both" else "dynamics"
        )
        return BiliMultiFeedCoverage(
            self.input_state,
            next_state,
            "dynamics",
            None,
            self.page,
            self.observation,
            tuple(self.consumed),
            self.reason,
        )


@dataclass(frozen=True, slots=True)
class BiliMultiFeedCoverage:
    input_state: BiliMultiFeedState
    next_state: BiliMultiFeedState
    feed: str
    uploads: BiliScanCoverage | None = None
    page: BiliDynamicPage | None = None
    observation: str | None = None
    dynamic_consumed: tuple[BiliDynamicConsumption, ...] = ()
    reason: str | None = None

    @property
    def upload_coverage(self) -> BiliScanCoverage | None:
        return self.uploads

    @property
    def consumed(self) -> tuple[BiliIdentity, ...] | tuple[BiliDynamicConsumption, ...]:
        return self.uploads.consumed if self.uploads is not None else self.dynamic_consumed

    @property
    def lane(self) -> str:
        return self.uploads.lane if self.uploads is not None else self.input_state.dynamics.next_lane

    @property
    def stop_reason(self) -> str:
        return self.uploads.stop_reason if self.uploads is not None else str(self.reason)

    @property
    def list_attempts(self) -> int:
        return self.uploads.list_attempts if self.uploads is not None else int(self.observation == "list")

    @property
    def detail_attempts(self) -> int:
        return self.uploads.detail_attempts if self.uploads is not None else len(self.dynamic_consumed)

    @property
    def record_keys(self) -> tuple[tuple[str, str], ...]:
        if self.uploads is not None:
            return tuple(("content", row.aid) for row in self.uploads.consumed)
        records: dict[tuple[str, str], None] = {}
        for row in self.dynamic_consumed:
            records["dynamic", row.identity.did] = None
            if row.video_identity is not None:
                records["content", row.video_identity.aid] = None
        return tuple(records)

    def validate(
        self,
        input_state: BiliMultiFeedState,
        max_items: int,
        normalized_remote_ids: tuple[str, ...] | None = None,
        *,
        normalized_records: tuple[tuple[str, str], ...] | None = None,
    ) -> None:
        if (
            type(input_state) is not BiliMultiFeedState
            or self.input_state != input_state
            or self.feed != input_state.next_feed
        ):
            raise _invalid()
        _integer(max_items, 1 if input_state.scope == "uploads" else 2, 1_000)
        if self.feed == "uploads":
            if (
                self.uploads is None
                or self.page is not None
                or self.observation is not None
                or self.dynamic_consumed
                or self.reason is not None
            ):
                raise _invalid()
            self.uploads.validate(input_state.uploads, max_items, normalized_remote_ids)
            if wrap_upload_coverage(input_state, self.uploads) != self:
                raise _invalid()
        else:
            if (
                self.uploads is not None
                or self.page is None
                or type(self.observation) is not str
                or self.observation not in {"list", "load"}
                or type(self.reason) is not str
                or self.reason not in _REASONS
            ):
                raise _invalid()
            if normalized_remote_ids is not None:
                # AID and DID occupy distinct namespaces; raw numeric IDs cannot
                # prove a dynamic unit's normalized output identity.
                raise _invalid()
            unit = BiliDynamicUnit(input_state, max_items)
            unit.observe_page(self.page)
            for row in self.dynamic_consumed:
                unit.consume(row.identity, row.video_identity)
            if unit.coverage() != self:
                raise _invalid()
        if normalized_records is not None and (
            len(normalized_records) != len(self.record_keys) or set(normalized_records) != set(self.record_keys)
        ):
            raise _invalid()

    def to_json_line(self) -> str:
        result = (
            _dump(
                {
                    "schema_version": 2,
                    "feed": self.feed,
                    "input_cursor": self.input_state.to_cursor(),
                    "next_cursor": self.next_state.to_cursor(),
                    "uploads": None if self.uploads is None else self.uploads.to_json_line(),
                    "page": None if self.page is None else self.page.as_mapping(),
                    "observation": self.observation,
                    "dynamic_consumed": [row.as_mapping() for row in self.dynamic_consumed],
                    "reason": self.reason,
                }
            )
            + "\n"
        )
        if len(result) > _MAX_COVERAGE:
            raise _invalid()
        return result

    @classmethod
    def from_json_line(cls, line: str) -> BiliMultiFeedCoverage:
        if type(line) is not str or not line.endswith("\n") or len(line.splitlines()) != 1:
            raise _invalid()
        item = _mapping(
            _json(line, _MAX_COVERAGE),
            {
                "schema_version",
                "feed",
                "input_cursor",
                "next_cursor",
                "uploads",
                "page",
                "observation",
                "dynamic_consumed",
                "reason",
            },
        )
        if (
            type(item["schema_version"]) is not int
            or item["schema_version"] != 2
            or type(item["dynamic_consumed"]) is not list
            or len(item["dynamic_consumed"]) > BILI_DYNAMIC_PAGE_SIZE
        ):
            raise _invalid()
        return cls(
            BiliMultiFeedState.from_cursor(item["input_cursor"]),
            BiliMultiFeedState.from_cursor(item["next_cursor"]),
            item["feed"],
            None if item["uploads"] is None else BiliScanCoverage.from_json_line(item["uploads"]),
            None if item["page"] is None else BiliDynamicPage.from_mapping(item["page"]),
            item["observation"],
            tuple(BiliDynamicConsumption.from_mapping(row) for row in item["dynamic_consumed"]),
            item["reason"],
        )

    def public_summary(self) -> dict[str, object]:
        return {
            "version": 2,
            "feed": self.feed,
            "lane": self.lane,
            "stop_reason": self.stop_reason,
            "item_count": len(self.record_keys),
            "list_attempts": self.list_attempts,
            "detail_attempts": self.detail_attempts,
            "partial": True,
            "restarted": self.stop_reason == "restarted",
            "source_end_observed": self.stop_reason == "source_end",
            "next_feed": self.next_state.next_feed,
            "next_action": f"continue_{self.next_state.next_feed}",
        }


def wrap_upload_coverage(input_state: BiliMultiFeedState, coverage: BiliScanCoverage) -> BiliMultiFeedCoverage:
    if (
        type(input_state) is not BiliMultiFeedState
        or input_state.next_feed != "uploads"
        or coverage.input_state != input_state.uploads
    ):
        raise _invalid()
    next_state = replace(
        input_state, uploads=coverage.next_state, next_feed="dynamics" if input_state.scope == "both" else "uploads"
    )
    return BiliMultiFeedCoverage(input_state, next_state, "uploads", coverage)


def coverage_from_json_line(line: str) -> BiliScanCoverage | BiliMultiFeedCoverage:
    item = _json(line, _MAX_COVERAGE)
    if type(item) is dict and type(item.get("schema_version")) is int and item["schema_version"] == 2:
        return BiliMultiFeedCoverage.from_json_line(line)
    return BiliScanCoverage.from_json_line(line)
