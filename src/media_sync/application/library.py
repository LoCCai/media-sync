"""Read-only, publication-anchored inspection of managed media-library trees."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from media_sync.exporters.emby import (
    LAYOUT_VERSION,
    ExportAuthor,
    ExportError,
    ManagedFileInspection,
    PublishedIdentity,
    PublishedTreeInspection,
    author_relative_directory,
)
from media_sync.infrastructure.db import Author, Content, Database

from .emby import _load_emby_publication_head, _PublicationAnchor, _snapshot_from_author

LibraryFreshness = Literal["not_published", "current", "outdated", "blocked"]
LibraryIntegrity = Literal[
    "not_available",
    "unchecked",
    "page_verified",
    "complete",
    "budget_exhausted",
    "drifted",
    "inconsistent",
]

_CURSOR_SCHEMA_VERSION = 1
_MAX_CURSOR_BYTES = 4_096
_MAX_PAGE_FILES = 128
_SHA256_LENGTH = 64
_INSPECTION_GATE = threading.Lock()
_BLOCKED_SNAPSHOT_CODES = frozenset(
    {
        "asset_not_verified",
        "export_output_path_invalid",
        "export_snapshot_invalid",
        "verified_asset_incomplete",
    }
)


class LibraryInspectionError(RuntimeError):
    """A fixed, redaction-safe application failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Library inspection failed: {code}")


class LibraryExporterPort(Protocol):
    """Only the non-mutating exporter surface used by this read service."""

    @property
    def coordination_scope(self) -> str: ...

    def inspect_published(
        self,
        author: ExportAuthor,
        expected_identity: PublishedIdentity,
        *,
        start_index: int,
        limit: int,
        max_bytes: int,
        deadline: float,
        monotonic: Callable[[], float],
    ) -> PublishedTreeInspection: ...


@dataclass(frozen=True, slots=True)
class LibraryPublication:
    """Allowlisted identity of the database-authorized publication head."""

    layout_version: str
    publication_scope: str
    job_id: str
    source_fingerprint: str
    tree_sha256: str
    manifest_sha256: str
    managed_file_count: int


@dataclass(frozen=True, slots=True)
class LibraryInspectionPage:
    """Exact scope and resource usage of one inspection response."""

    start_index: int
    next_index: int
    limit: int
    returned_count: int
    bytes_read: int
    complete: bool
    budget_exhausted: bool
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class LibraryInspection:
    """Safe application projection for an author library detail endpoint."""

    author_id: str
    publication: LibraryPublication | None
    freshness: LibraryFreshness
    freshness_reason_code: str | None
    integrity: LibraryIntegrity
    integrity_reason_code: str | None
    user_changes_protected: bool
    files: tuple[ManagedFileInspection, ...]
    page: LibraryInspectionPage
    allowed_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Cursor:
    author_id: str
    publication_scope: str
    job_id: str
    source_fingerprint: str
    tree_sha256: str
    manifest_sha256: str
    managed_file_count: int
    next_index: int


@dataclass(frozen=True, slots=True)
class _LibraryState:
    author: ExportAuthor
    current_source_fingerprint: str | None
    snapshot_blocked: bool
    head: _PublicationAnchor | None


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate cursor field")
        result[key] = value
    return result


def _publication(scope: str, head: _PublicationAnchor) -> LibraryPublication:
    return LibraryPublication(
        layout_version=LAYOUT_VERSION,
        publication_scope=scope,
        job_id=head.job_id,
        source_fingerprint=head.source_fingerprint,
        tree_sha256=head.tree_sha256,
        manifest_sha256=head.manifest_sha256,
        managed_file_count=head.managed_file_count,
    )


def _freshness(state: _LibraryState) -> tuple[LibraryFreshness, str | None]:
    if state.snapshot_blocked:
        return "blocked", "library_snapshot_blocked"
    if state.head is None:
        return "not_published", "library_not_published"
    if state.current_source_fingerprint == state.head.source_fingerprint:
        return "current", None
    return "outdated", "library_source_outdated"


def _allowed_actions(freshness: LibraryFreshness, integrity: LibraryIntegrity) -> tuple[str, ...]:
    actions: list[str] = []
    if freshness in {"not_published", "outdated"} and integrity not in {"drifted", "inconsistent"}:
        actions.append("export_author")
    if freshness == "current" and integrity == "complete":
        actions.append("refresh_and_verify")
    return tuple(actions)


class LibraryInspectionService:
    """Resolve DB authority, then inspect one bounded page outside its transaction."""

    def __init__(
        self,
        database: Database,
        exporter: LibraryExporterPort,
        *,
        cursor_key: bytes | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        scope = exporter.coordination_scope
        key = secrets.token_bytes(32) if cursor_key is None else cursor_key
        if not _is_sha256(scope) or not isinstance(key, bytes) or len(key) < 32 or not callable(monotonic):
            raise LibraryInspectionError("library_inspection_invalid")
        self._database = database
        self._exporter = exporter
        self._publication_scope = scope
        self._cursor_key = key
        self._monotonic = monotonic

    def inspect(
        self,
        author_id: str,
        *,
        cursor: str | None = None,
        limit: int = _MAX_PAGE_FILES,
        max_bytes: int,
        deadline_seconds: float,
        monotonic: Callable[[], float] | None = None,
    ) -> LibraryInspection:
        """Inspect one author by UUID without accepting any filesystem locator."""

        normalized_author_id = self._author_id(author_id)
        self._validate_budget(limit, max_bytes, deadline_seconds)
        decoded_cursor = None if cursor is None else self._decode_cursor(cursor)
        request_clock = self._monotonic if monotonic is None else monotonic
        if not callable(request_clock):
            raise LibraryInspectionError("library_inspection_invalid")
        try:
            started_at = request_clock()
            deadline = started_at + float(deadline_seconds)
        except (TypeError, ValueError, OverflowError):
            raise LibraryInspectionError("library_inspection_invalid") from None
        if (
            isinstance(started_at, bool)
            or not isinstance(started_at, (int, float))
            or not math.isfinite(started_at)
            or not math.isfinite(deadline)
        ):
            raise LibraryInspectionError("library_inspection_invalid")

        if not _INSPECTION_GATE.acquire(blocking=False):
            raise LibraryInspectionError("library_inspection_busy")
        try:
            state = self._load_state(normalized_author_id)
            freshness, freshness_reason = _freshness(state)
            head = state.head
            if decoded_cursor is not None:
                self._check_cursor(decoded_cursor, normalized_author_id, head)
            if head is None:
                return LibraryInspection(
                    author_id=normalized_author_id,
                    publication=None,
                    freshness=freshness,
                    freshness_reason_code=freshness_reason,
                    integrity="not_available",
                    integrity_reason_code="library_not_published",
                    user_changes_protected=True,
                    files=(),
                    page=LibraryInspectionPage(0, 0, limit, 0, 0, False, False, None),
                    allowed_actions=_allowed_actions(freshness, "not_available"),
                )

            start_index = 0 if decoded_cursor is None else decoded_cursor.next_index
            publication = _publication(self._publication_scope, head)
            if request_clock() >= deadline:
                return self._budget_result(
                    normalized_author_id,
                    publication,
                    freshness,
                    freshness_reason,
                    start_index,
                    limit,
                    reason_code="library_inspection_deadline_exceeded",
                )

            try:
                inspected = self._exporter.inspect_published(
                    state.author,
                    head.identity,
                    start_index=start_index,
                    limit=limit,
                    max_bytes=max_bytes,
                    deadline=deadline,
                    monotonic=request_clock,
                )
            except ExportError as error:
                if error.code == "published_inspection_busy":
                    raise LibraryInspectionError("library_inspection_busy") from None
                if error.code == "published_inspection_deadline":
                    return self._budget_result(
                        normalized_author_id,
                        publication,
                        freshness,
                        freshness_reason,
                        start_index,
                        limit,
                        reason_code="library_inspection_deadline_exceeded",
                    )
                return self._failed_result(
                    normalized_author_id,
                    publication,
                    freshness,
                    freshness_reason,
                    start_index,
                    limit,
                    integrity="drifted",
                    reason_code="library_tree_drifted",
                )

            if not self._inspection_matches(inspected, head, start_index, limit, max_bytes):
                return self._failed_result(
                    normalized_author_id,
                    publication,
                    freshness,
                    freshness_reason,
                    start_index,
                    limit,
                    integrity="inconsistent",
                    reason_code="library_publication_inconsistent",
                )

            reached_end = inspected.next_index == head.managed_file_count and not inspected.budget_exhausted
            whole_tree_complete = inspected.complete
            if inspected.budget_exhausted:
                integrity: LibraryIntegrity = "budget_exhausted"
                integrity_reason = (
                    "library_inspection_deadline_exceeded"
                    if request_clock() >= deadline
                    else "library_inspection_byte_budget_exhausted"
                )
            elif whole_tree_complete:
                integrity = "complete"
                integrity_reason = None
            else:
                integrity = "page_verified"
                integrity_reason = None
            next_cursor = None
            if not reached_end:
                next_cursor = self._encode_cursor(normalized_author_id, head, inspected.next_index)
            page = LibraryInspectionPage(
                start_index=inspected.start_index,
                next_index=inspected.next_index,
                limit=limit,
                returned_count=len(inspected.files),
                bytes_read=inspected.bytes_read,
                complete=whole_tree_complete,
                budget_exhausted=inspected.budget_exhausted,
                next_cursor=next_cursor,
            )
            return LibraryInspection(
                author_id=normalized_author_id,
                publication=publication,
                freshness=freshness,
                freshness_reason_code=freshness_reason,
                integrity=integrity,
                integrity_reason_code=integrity_reason,
                user_changes_protected=True,
                files=inspected.files,
                page=page,
                allowed_actions=_allowed_actions(freshness, integrity),
            )
        finally:
            _INSPECTION_GATE.release()

    @staticmethod
    def _author_id(author_id: str) -> str:
        try:
            return str(UUID(author_id.strip()))
        except (AttributeError, TypeError, ValueError):
            raise LibraryInspectionError("library_author_invalid") from None

    @staticmethod
    def _validate_budget(limit: int, max_bytes: int, deadline_seconds: float) -> None:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= _MAX_PAGE_FILES
            or isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or max_bytes < 0
            or isinstance(deadline_seconds, bool)
            or not isinstance(deadline_seconds, (int, float))
            or not math.isfinite(deadline_seconds)
            or deadline_seconds < 0
        ):
            raise LibraryInspectionError("library_inspection_invalid")

    def _load_state(self, author_id: str) -> _LibraryState:
        try:
            with self._database.session() as session:
                author = session.scalar(
                    select(Author)
                    .where(Author.id == author_id)
                    .options(selectinload(Author.contents).selectinload(Content.assets))
                )
                if author is None:
                    raise LibraryInspectionError("library_author_not_found")
                try:
                    export_author = ExportAuthor(
                        platform=author.platform,
                        remote_id=author.remote_id,
                        display_name=author.display_name,
                        handle=author.handle,
                    )
                    output_path = author_relative_directory(export_author).as_posix()
                    relative_output = PurePosixPath(output_path)
                    if relative_output.is_absolute() or ".." in relative_output.parts:
                        raise ExportError("export_output_path_invalid")
                except ExportError:
                    raise LibraryInspectionError("library_publication_inconsistent") from None

                snapshot_blocked = False
                current_source_fingerprint: str | None
                try:
                    snapshot = _snapshot_from_author(author)
                    current_source_fingerprint = snapshot.source_fingerprint
                except ExportError as error:
                    if error.code not in _BLOCKED_SNAPSHOT_CODES:
                        raise LibraryInspectionError("library_publication_inconsistent") from None
                    snapshot_blocked = True
                    current_source_fingerprint = None
                try:
                    head = _load_emby_publication_head(
                        session,
                        author_id=author_id,
                        publication_scope=self._publication_scope,
                        output_path=output_path,
                    )
                except ExportError:
                    raise LibraryInspectionError("library_publication_inconsistent") from None
                return _LibraryState(export_author, current_source_fingerprint, snapshot_blocked, head)
        except LibraryInspectionError:
            raise
        except Exception:
            raise LibraryInspectionError("library_inspection_failed") from None

    def _encode_cursor(self, author_id: str, head: _PublicationAnchor, next_index: int) -> str:
        payload: dict[str, object] = {
            "author_id": author_id,
            "job_id": head.job_id,
            "managed_file_count": head.managed_file_count,
            "manifest_sha256": head.manifest_sha256,
            "next_index": next_index,
            "publication_scope": self._publication_scope,
            "schema_version": _CURSOR_SCHEMA_VERSION,
            "source_fingerprint": head.source_fingerprint,
            "tree_sha256": head.tree_sha256,
        }
        signature = hmac.new(self._cursor_key, _canonical_json(payload), hashlib.sha256).hexdigest()
        raw = _canonical_json({"payload": payload, "signature": signature})
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    def _decode_cursor(self, cursor: str) -> _Cursor:
        try:
            if (
                not isinstance(cursor, str)
                or not cursor
                or len(cursor) > _MAX_CURSOR_BYTES
                or not cursor.isascii()
                or any(character.isspace() for character in cursor)
                or any(not (character.isalnum() or character in "-_") for character in cursor)
            ):
                raise ValueError("invalid cursor envelope")
            encoded = cursor.encode("ascii")
            raw = base64.b64decode(
                encoded + b"=" * ((4 - len(encoded) % 4) % 4),
                altchars=b"-_",
                validate=True,
            )
            if len(raw) > _MAX_CURSOR_BYTES:
                raise ValueError("oversized cursor")
            envelope = json.loads(
                raw.decode("ascii"),
                object_pairs_hook=_strict_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("invalid cursor number")),
            )
            if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"}:
                raise ValueError("invalid cursor envelope")
            if raw != _canonical_json(envelope):
                raise ValueError("non-canonical cursor")
            payload = envelope["payload"]
            signature = envelope["signature"]
            if not isinstance(payload, dict) or set(payload) != {
                "author_id",
                "job_id",
                "managed_file_count",
                "manifest_sha256",
                "next_index",
                "publication_scope",
                "schema_version",
                "source_fingerprint",
                "tree_sha256",
            }:
                raise ValueError("invalid cursor payload")
            if not isinstance(signature, str) or not _is_sha256(signature):
                raise ValueError("invalid cursor signature")
            expected_signature = hmac.new(self._cursor_key, _canonical_json(payload), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected_signature):
                raise ValueError("invalid cursor signature")
            author_id = payload["author_id"]
            job_id = payload["job_id"]
            scope = payload["publication_scope"]
            source = payload["source_fingerprint"]
            tree = payload["tree_sha256"]
            manifest = payload["manifest_sha256"]
            managed_count = payload["managed_file_count"]
            next_index = payload["next_index"]
            if (
                payload["schema_version"] != _CURSOR_SCHEMA_VERSION
                or not _is_uuid(author_id)
                or not _is_uuid(job_id)
                or not _is_sha256(scope)
                or not _is_sha256(source)
                or not _is_sha256(tree)
                or not _is_sha256(manifest)
                or isinstance(managed_count, bool)
                or not isinstance(managed_count, int)
                or managed_count < 0
                or isinstance(next_index, bool)
                or not isinstance(next_index, int)
                or not 0 <= next_index <= managed_count
            ):
                raise ValueError("invalid cursor values")
            assert all(isinstance(value, str) for value in (author_id, job_id, scope, source, tree, manifest))
            return _Cursor(author_id, scope, job_id, source, tree, manifest, managed_count, next_index)
        except (UnicodeError, binascii.Error, json.JSONDecodeError, TypeError, ValueError):
            raise LibraryInspectionError("library_cursor_invalid") from None

    def _check_cursor(
        self,
        cursor: _Cursor,
        author_id: str,
        head: _PublicationAnchor | None,
    ) -> None:
        if (
            head is None
            or cursor.author_id != author_id
            or cursor.publication_scope != self._publication_scope
            or cursor.job_id != head.job_id
            or cursor.source_fingerprint != head.source_fingerprint
            or cursor.tree_sha256 != head.tree_sha256
            or cursor.manifest_sha256 != head.manifest_sha256
            or cursor.managed_file_count != head.managed_file_count
        ):
            raise LibraryInspectionError("library_cursor_stale")

    @staticmethod
    def _inspection_matches(
        inspected: PublishedTreeInspection,
        head: _PublicationAnchor,
        start_index: int,
        limit: int,
        max_bytes: int,
    ) -> bool:
        return (
            isinstance(inspected, PublishedTreeInspection)
            and inspected.layout_version == LAYOUT_VERSION
            and inspected.source_fingerprint == head.source_fingerprint
            and inspected.tree_sha256 == head.tree_sha256
            and inspected.manifest_sha256 == head.manifest_sha256
            and inspected.managed_file_count == head.managed_file_count
            and inspected.start_index == start_index
            and inspected.next_index <= min(head.managed_file_count, start_index + limit)
            and inspected.bytes_read <= max_bytes
        )

    def _budget_result(
        self,
        author_id: str,
        publication: LibraryPublication,
        freshness: LibraryFreshness,
        freshness_reason: str | None,
        start_index: int,
        limit: int,
        *,
        reason_code: str,
    ) -> LibraryInspection:
        head = _PublicationAnchor(
            publication.job_id,
            None,
            publication.source_fingerprint,
            publication.tree_sha256,
            publication.manifest_sha256,
            publication.managed_file_count,
        )
        return LibraryInspection(
            author_id=author_id,
            publication=publication,
            freshness=freshness,
            freshness_reason_code=freshness_reason,
            integrity="budget_exhausted",
            integrity_reason_code=reason_code,
            user_changes_protected=True,
            files=(),
            page=LibraryInspectionPage(
                start_index,
                start_index,
                limit,
                0,
                0,
                False,
                True,
                self._encode_cursor(author_id, head, start_index),
            ),
            allowed_actions=_allowed_actions(freshness, "budget_exhausted"),
        )

    @staticmethod
    def _failed_result(
        author_id: str,
        publication: LibraryPublication,
        freshness: LibraryFreshness,
        freshness_reason: str | None,
        start_index: int,
        limit: int,
        *,
        integrity: Literal["drifted", "inconsistent"],
        reason_code: str,
    ) -> LibraryInspection:
        return LibraryInspection(
            author_id=author_id,
            publication=publication,
            freshness=freshness,
            freshness_reason_code=freshness_reason,
            integrity=integrity,
            integrity_reason_code=reason_code,
            user_changes_protected=True,
            files=(),
            page=LibraryInspectionPage(start_index, start_index, limit, 0, 0, False, False, None),
            allowed_actions=_allowed_actions(freshness, integrity),
        )


__all__ = [
    "LibraryExporterPort",
    "LibraryFreshness",
    "LibraryInspection",
    "LibraryInspectionError",
    "LibraryInspectionPage",
    "LibraryInspectionService",
    "LibraryIntegrity",
    "LibraryPublication",
]
