"""Resolve one current, fully verified publication into an in-memory server target."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from media_sync.application.emby import _load_emby_publication_head, _PublicationAnchor, _snapshot_from_author
from media_sync.config import MediaServerProfile
from media_sync.domain import Platform
from media_sync.exporters.emby import (
    LAYOUT_VERSION,
    ExportAuthor,
    PublishedIdentity,
    PublishedTreeInspection,
    author_relative_directory,
)
from media_sync.infrastructure.db import Author, Content, Database
from media_sync.ports.media_server import MediaServerError, MediaServerLookupTarget

MediaServerPathStyle = Literal["posix", "windows"]

_INSPECTION_PAGE_FILES = 128
_DEFAULT_INSPECTION_MAX_BYTES = 1_073_741_824
_DEFAULT_INSPECTION_TIMEOUT_SECONDS = 10.0
_SHA256_LENGTH = 64


class MediaServerPublicationExporterPort(Protocol):
    """The existing-only, non-mutating exporter surface used by the resolver."""

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


@dataclass(frozen=True, slots=True, repr=False)
class MediaServerPublicationTarget(MediaServerLookupTarget):
    """Raw selectors kept in memory while ``repr`` exposes only safe identity."""

    author_id: str
    publication_job_id: str
    platform: str
    author_relative_directory: str = field(repr=False)
    server_path_style: MediaServerPathStyle
    publication_fingerprint: str
    selector_fingerprint: str
    managed_file_count: int

    def __post_init__(self) -> None:
        MediaServerLookupTarget.__post_init__(self)
        if not _is_canonical_uuid(self.author_id) or not _is_canonical_uuid(self.publication_job_id):
            raise ValueError("publication target IDs must be canonical UUIDs")
        if self.platform not in {platform.value for platform in Platform}:
            raise ValueError("publication target platform is unsupported")
        if self.provider_key != f"media-sync-{self.platform}-creator":
            raise ValueError("publication target provider key is inconsistent")
        relative = PurePosixPath(self.author_relative_directory)
        if (
            not self.author_relative_directory
            or "\\" in self.author_relative_directory
            or relative.is_absolute()
            or len(relative.parts) != 1
            or relative.parts[0] in {"", ".", ".."}
            or relative.as_posix() != self.author_relative_directory
        ):
            raise ValueError("publication target author directory is invalid")
        if self.server_path_style not in {"posix", "windows"}:
            raise ValueError("publication target server path is invalid")
        server_posix = PurePosixPath(self.server_path)
        server_windows = PureWindowsPath(self.server_path)
        if self.server_path_style == "posix":
            server_path_valid = (
                server_posix.is_absolute()
                and not server_windows.is_absolute()
                and "\\" not in self.server_path
                and server_posix.name == self.author_relative_directory
            )
        else:
            server_path_valid = (
                server_windows.is_absolute()
                and not server_posix.is_absolute()
                and "/" not in self.server_path
                and server_windows.name == self.author_relative_directory
            )
        if not server_path_valid:
            raise ValueError("publication target server path is inconsistent")
        if not _is_sha256(self.publication_fingerprint):
            raise ValueError("publication fingerprint must be a lowercase SHA-256 digest")
        if not _is_sha256(self.selector_fingerprint):
            raise ValueError("selector fingerprint must be a lowercase SHA-256 digest")
        if (
            isinstance(self.managed_file_count, bool)
            or not isinstance(self.managed_file_count, int)
            or self.managed_file_count < 0
        ):
            raise ValueError("managed file count must be a nonnegative integer")

    @property
    def remote_id(self) -> str:
        """Return the stored author remote ID used as the provider value."""

        return self.provider_value

    def __repr__(self) -> str:
        return (
            "MediaServerPublicationTarget("
            f"author_id={self.author_id!r}, publication_job_id={self.publication_job_id!r}, "
            f"platform={self.platform!r}, provider_key={self.provider_key!r}, "
            f"server_path_style={self.server_path_style!r}, "
            f"publication_fingerprint={self.publication_fingerprint!r}, "
            f"selector_fingerprint={self.selector_fingerprint!r}, "
            f"managed_file_count={self.managed_file_count!r})"
        )

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class _PublicationAuthority:
    author_id: str
    author: ExportAuthor
    source_fingerprint: str
    output_path: str
    head: _PublicationAnchor


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_canonical_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _normalized_author_id(value: object) -> str:
    if not _is_canonical_uuid(value):
        raise MediaServerError("media_server_publication_not_ready")
    assert isinstance(value, str)
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def media_server_publication_fingerprint(
    *,
    author_id: str,
    publication_scope: str,
    author: ExportAuthor,
    current_source_fingerprint: str,
    publication_job_id: str,
    predecessor_job_id: str | None,
    publication_identity: PublishedIdentity,
    managed_file_count: int,
) -> str:
    """Build the canonical DB/Job publication identity without I/O."""

    if (
        not _is_canonical_uuid(author_id)
        or not _is_canonical_uuid(publication_job_id)
        or (predecessor_job_id is not None and not _is_canonical_uuid(predecessor_job_id))
        or predecessor_job_id == publication_job_id
        or not _is_sha256(publication_scope)
        or not isinstance(author, ExportAuthor)
        or author.platform not in {platform.value for platform in Platform}
        or not _is_sha256(current_source_fingerprint)
        or not isinstance(publication_identity, PublishedIdentity)
        or publication_identity.source_fingerprint != current_source_fingerprint
        or isinstance(managed_file_count, bool)
        or not isinstance(managed_file_count, int)
        or managed_file_count < 0
    ):
        raise ValueError("media-server publication identity is invalid")
    output_path = author_relative_directory(author).as_posix()
    payload = {
        "author_id": author_id,
        "author_relative_directory": output_path,
        "layout_version": LAYOUT_VERSION,
        "managed_file_count": managed_file_count,
        "manifest_sha256": publication_identity.manifest_sha256,
        "platform": author.platform,
        "predecessor_job_id": predecessor_job_id,
        "publication_job_id": publication_job_id,
        "publication_scope": publication_scope,
        "remote_id": author.remote_id,
        "schema_version": 1,
        "source_fingerprint": publication_identity.source_fingerprint,
        "tree_sha256": publication_identity.tree_sha256,
        "type": "media_server_publication",
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _publication_fingerprint(scope: str, authority: _PublicationAuthority) -> str:
    head = authority.head
    return media_server_publication_fingerprint(
        author_id=authority.author_id,
        publication_scope=scope,
        author=authority.author,
        current_source_fingerprint=authority.source_fingerprint,
        publication_job_id=head.job_id,
        predecessor_job_id=head.predecessor_job_id,
        publication_identity=head.identity,
        managed_file_count=head.managed_file_count,
    )


def media_server_selector_fingerprint(
    *,
    profile_fingerprint: str,
    publication_fingerprint: str,
    target: MediaServerLookupTarget,
) -> str:
    """Bind raw selectors to high-entropy profile/publication context."""

    if (
        not _is_sha256(profile_fingerprint)
        or not _is_sha256(publication_fingerprint)
        or not isinstance(target, MediaServerLookupTarget)
    ):
        raise ValueError("media-server selector identity is invalid")
    payload = {
        "profile_fingerprint": profile_fingerprint,
        "provider_key": target.provider_key,
        "provider_value": target.provider_value,
        "publication_fingerprint": publication_fingerprint,
        "schema_version": 1,
        "server_path": target.server_path,
        "type": "media_server_selector",
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _join_server_path(server_root: str, author_directory: str) -> tuple[MediaServerPathStyle, str]:
    """Join using the server's explicit path syntax, rejecting mixed or ambiguous roots."""

    if not isinstance(server_root, str) or not server_root or not isinstance(author_directory, str):
        raise ValueError("invalid server path")
    relative = PurePosixPath(author_directory)
    if (
        not author_directory
        or "\\" in author_directory
        or relative.is_absolute()
        or len(relative.parts) != 1
        or relative.parts[0] in {"", ".", ".."}
        or relative.as_posix() != author_directory
    ):
        raise ValueError("invalid author directory")

    posix_root = PurePosixPath(server_root)
    windows_root = PureWindowsPath(server_root)
    posix_absolute = posix_root.is_absolute()
    windows_absolute = windows_root.is_absolute()
    if posix_absolute == windows_absolute or ("/" in server_root and "\\" in server_root):
        raise ValueError("ambiguous server path style")
    if posix_absolute:
        if "\\" in server_root:
            raise ValueError("mixed server path style")
        return "posix", (posix_root / relative).as_posix()
    return "windows", str(windows_root / PureWindowsPath(author_directory))


class MediaServerPublicationResolver:
    """Fence DB publication identity around complete hardened filesystem inspection."""

    def __init__(
        self,
        database: Database,
        exporter: MediaServerPublicationExporterPort,
        profile: MediaServerProfile,
        *,
        inspection_max_bytes: int = _DEFAULT_INSPECTION_MAX_BYTES,
        inspection_timeout_seconds: float = _DEFAULT_INSPECTION_TIMEOUT_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(profile, MediaServerProfile):
            raise TypeError("profile must be a MediaServerProfile")
        try:
            scope = exporter.coordination_scope
        except Exception:
            raise ValueError("exporter coordination scope is unavailable") from None
        if not _is_sha256(scope):
            raise ValueError("exporter coordination scope must be a lowercase SHA-256 digest")
        if (
            isinstance(inspection_max_bytes, bool)
            or not isinstance(inspection_max_bytes, int)
            or inspection_max_bytes < 1
        ):
            raise ValueError("inspection_max_bytes must be a positive integer")
        if (
            isinstance(inspection_timeout_seconds, bool)
            or not isinstance(inspection_timeout_seconds, int | float)
            or not math.isfinite(inspection_timeout_seconds)
            or inspection_timeout_seconds <= 0
        ):
            raise ValueError("inspection_timeout_seconds must be positive and finite")
        if not callable(monotonic):
            raise TypeError("monotonic must be callable")
        self._database = database
        self._exporter = exporter
        self._profile = profile
        self._publication_scope = scope
        self._inspection_max_bytes = inspection_max_bytes
        self._inspection_timeout_seconds = float(inspection_timeout_seconds)
        self._monotonic = monotonic

    def resolve(
        self,
        author_id: str,
        *,
        deadline: float | None = None,
    ) -> MediaServerPublicationTarget:
        """Resolve only a local author UUID; no caller-controlled remote selector is accepted."""

        normalized_author_id = _normalized_author_id(author_id)
        inspection_deadline = self._deadline(deadline)
        initial = self._load_authority(normalized_author_id, changed=False)
        if self._time() >= inspection_deadline:
            raise MediaServerError("media_server_publication_not_ready")
        try:
            path_style, server_path = _join_server_path(self._profile.library_path, initial.output_path)
            lookup_target = MediaServerLookupTarget(
                provider_key=f"media-sync-{initial.author.platform}-creator",
                provider_value=initial.author.remote_id,
                server_path=server_path,
            )
            publication_fingerprint = _publication_fingerprint(self._publication_scope, initial)
            selector_fingerprint = media_server_selector_fingerprint(
                profile_fingerprint=self._profile.profile_fingerprint,
                publication_fingerprint=publication_fingerprint,
                target=lookup_target,
            )
            target = MediaServerPublicationTarget(
                provider_key=lookup_target.provider_key,
                provider_value=lookup_target.provider_value,
                server_path=lookup_target.server_path,
                author_id=normalized_author_id,
                publication_job_id=initial.head.job_id,
                platform=initial.author.platform,
                author_relative_directory=initial.output_path,
                server_path_style=path_style,
                publication_fingerprint=publication_fingerprint,
                selector_fingerprint=selector_fingerprint,
                managed_file_count=initial.head.managed_file_count,
            )
        except (TypeError, ValueError):
            raise MediaServerError("media_server_publication_not_ready") from None

        self._inspect_complete(initial, inspection_deadline)
        final = self._load_authority(normalized_author_id, changed=True)
        if self._time() >= inspection_deadline:
            raise MediaServerError("media_server_publication_not_ready")
        if final != initial:
            raise MediaServerError("media_server_publication_changed")

        return target

    def _deadline(self, caller_deadline: float | None) -> float:
        try:
            started = self._monotonic()
            local_deadline = started + self._inspection_timeout_seconds
        except (TypeError, ValueError, OverflowError):
            raise MediaServerError("media_server_publication_not_ready") from None
        if (
            isinstance(started, bool)
            or not isinstance(started, int | float)
            or not math.isfinite(started)
            or not math.isfinite(local_deadline)
        ):
            raise MediaServerError("media_server_publication_not_ready")
        if caller_deadline is None:
            return local_deadline
        if (
            isinstance(caller_deadline, bool)
            or not isinstance(caller_deadline, int | float)
            or not math.isfinite(caller_deadline)
        ):
            raise ValueError("deadline must be finite monotonic time")
        return min(local_deadline, float(caller_deadline))

    def _load_authority(self, author_id: str, *, changed: bool) -> _PublicationAuthority:
        code = "media_server_publication_changed" if changed else "media_server_publication_not_ready"
        try:
            with self._database.session() as session:
                stored = session.scalar(
                    select(Author)
                    .where(Author.id == author_id)
                    .options(selectinload(Author.contents).selectinload(Content.assets))
                )
                if stored is None:
                    raise MediaServerError(code)
                snapshot = _snapshot_from_author(stored)
                head = _load_emby_publication_head(
                    session,
                    author_id=author_id,
                    publication_scope=self._publication_scope,
                    output_path=snapshot.output_path,
                )
                if head is None or head.source_fingerprint != snapshot.source_fingerprint:
                    raise MediaServerError(code)
                return _PublicationAuthority(
                    author_id=author_id,
                    author=snapshot.author,
                    source_fingerprint=snapshot.source_fingerprint,
                    output_path=snapshot.output_path,
                    head=head,
                )
        except MediaServerError:
            raise
        except Exception:
            raise MediaServerError(code) from None

    def _inspect_complete(self, authority: _PublicationAuthority, deadline: float) -> None:
        head = authority.head
        next_index = 0
        remaining_bytes = self._inspection_max_bytes
        while True:
            if self._time() >= deadline:
                raise MediaServerError("media_server_publication_not_ready")
            try:
                inspected = self._exporter.inspect_published(
                    authority.author,
                    head.identity,
                    start_index=next_index,
                    limit=_INSPECTION_PAGE_FILES,
                    max_bytes=remaining_bytes,
                    deadline=deadline,
                    monotonic=self._monotonic,
                )
            except Exception:
                raise MediaServerError("media_server_publication_not_ready") from None
            if not self._inspection_matches(inspected, head, next_index, remaining_bytes):
                raise MediaServerError("media_server_publication_not_ready")
            remaining_bytes -= inspected.bytes_read
            if inspected.budget_exhausted:
                raise MediaServerError("media_server_publication_not_ready")
            expected_complete = next_index == 0 and inspected.next_index == head.managed_file_count
            if inspected.complete != expected_complete:
                raise MediaServerError("media_server_publication_not_ready")
            if inspected.next_index == head.managed_file_count:
                return
            if inspected.next_index <= next_index:
                raise MediaServerError("media_server_publication_not_ready")
            next_index = inspected.next_index

    def _time(self) -> float:
        try:
            value = self._monotonic()
        except (TypeError, ValueError, OverflowError):
            raise MediaServerError("media_server_publication_not_ready") from None
        if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
            raise MediaServerError("media_server_publication_not_ready")
        return float(value)

    @staticmethod
    def _inspection_matches(
        inspected: object,
        head: _PublicationAnchor,
        start_index: int,
        remaining_bytes: int,
    ) -> bool:
        return (
            isinstance(inspected, PublishedTreeInspection)
            and inspected.layout_version == LAYOUT_VERSION
            and inspected.source_fingerprint == head.source_fingerprint
            and inspected.tree_sha256 == head.tree_sha256
            and inspected.manifest_sha256 == head.manifest_sha256
            and inspected.managed_file_count == head.managed_file_count
            and inspected.start_index == start_index
            and inspected.next_index == min(head.managed_file_count, start_index + _INSPECTION_PAGE_FILES)
            and inspected.bytes_read <= remaining_bytes
        )


__all__ = [
    "MediaServerPathStyle",
    "MediaServerPublicationExporterPort",
    "MediaServerPublicationResolver",
    "MediaServerPublicationTarget",
    "media_server_publication_fingerprint",
    "media_server_selector_fingerprint",
]
