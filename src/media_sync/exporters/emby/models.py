"""Immutable exporter inputs and results, deliberately independent of ORM models."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Self

from .errors import ExportError

_SHA256_LENGTH = 64
_ASSET_KINDS = frozenset({"image", "video", "audio", "subtitle", "cover", "avatar", "attachment"})


def _text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ExportError(f"invalid_{field_name}")
    return normalized


def _optional_text(value: str | None, field_name: str) -> str | None:
    return None if value is None else _text(value, field_name)


def _utc(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ExportError(f"invalid_{field_name}")
    return value.astimezone(UTC)


def _sha256(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != _SHA256_LENGTH or any(character not in "0123456789abcdef" for character in normalized):
        raise ExportError("invalid_asset_checksum")
    return normalized


def _published_sha256(value: str) -> str:
    if not isinstance(value, str):
        raise ExportError("invalid_published_identity")
    normalized = value.strip().lower()
    if len(normalized) != _SHA256_LENGTH or any(character not in "0123456789abcdef" for character in normalized):
        raise ExportError("invalid_published_identity")
    return normalized


@dataclass(frozen=True, slots=True)
class ExportAuthor:
    """One creator identity and display snapshot."""

    platform: str
    remote_id: str
    display_name: str
    handle: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "platform", _text(self.platform, "platform").lower())
        object.__setattr__(self, "remote_id", _text(self.remote_id, "author_remote_id"))
        object.__setattr__(self, "display_name", _text(self.display_name, "display_name"))
        object.__setattr__(self, "handle", _optional_text(self.handle, "handle"))


@dataclass(frozen=True, slots=True)
class VerifiedAsset:
    """Exact locally verified bytes eligible for export."""

    remote_id: str
    kind: str
    position: int
    local_path: Path
    checksum_sha256: str
    size_bytes: int
    mime_type: str
    generation: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "remote_id", _text(self.remote_id, "asset_remote_id"))
        kind = _text(self.kind, "asset_kind").lower()
        if kind not in _ASSET_KINDS:
            raise ExportError("invalid_asset_kind")
        object.__setattr__(self, "kind", kind)
        if self.position < 0:
            raise ExportError("invalid_asset_position")
        object.__setattr__(self, "local_path", Path(self.local_path))
        object.__setattr__(self, "checksum_sha256", _sha256(self.checksum_sha256))
        if self.size_bytes < 0:
            raise ExportError("invalid_asset_size")
        object.__setattr__(self, "mime_type", _text(self.mime_type, "asset_mime_type").lower())
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation < 1:
            raise ExportError("invalid_asset_generation")


@dataclass(frozen=True, slots=True)
class ExportContent:
    """One normalized content item plus only its verified local assets."""

    platform: str
    remote_type: str
    remote_id: str
    author_remote_id: str
    kind: str
    first_seen_at: datetime
    title: str | None = None
    body: str | None = field(default=None, repr=False)
    published_at: datetime | None = None
    assets: tuple[VerifiedAsset, ...] = ()

    def __init__(
        self,
        *,
        platform: str,
        remote_type: str,
        remote_id: str,
        author_remote_id: str,
        kind: str,
        first_seen_at: datetime,
        title: str | None = None,
        body: str | None = None,
        published_at: datetime | None = None,
        assets: Sequence[VerifiedAsset] = (),
    ) -> None:
        object.__setattr__(self, "platform", platform)
        object.__setattr__(self, "remote_type", remote_type)
        object.__setattr__(self, "remote_id", remote_id)
        object.__setattr__(self, "author_remote_id", author_remote_id)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "first_seen_at", first_seen_at)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "published_at", published_at)
        object.__setattr__(self, "assets", tuple(assets))
        self.__post_init__()

    def __post_init__(self) -> None:
        object.__setattr__(self, "platform", _text(self.platform, "platform").lower())
        object.__setattr__(self, "remote_type", _text(self.remote_type, "remote_type").lower())
        object.__setattr__(self, "remote_id", _text(self.remote_id, "content_remote_id"))
        object.__setattr__(self, "author_remote_id", _text(self.author_remote_id, "author_remote_id"))
        object.__setattr__(self, "kind", _text(self.kind, "content_kind").lower())
        first_seen = _utc(self.first_seen_at, "first_seen_at")
        if first_seen is None:  # pragma: no cover - statically non-optional
            raise ExportError("invalid_first_seen_at")
        object.__setattr__(self, "first_seen_at", first_seen)
        object.__setattr__(self, "published_at", _utc(self.published_at, "published_at"))
        object.__setattr__(self, "title", _optional_text(self.title, "title"))
        object.__setattr__(self, "body", self.body)
        object.__setattr__(self, "assets", tuple(self.assets))


@dataclass(frozen=True, slots=True)
class ManagedFile:
    """One final author-relative file and its exact bytes."""

    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ContentFingerprint:
    """Stable source identity used by per-content export orchestration."""

    platform: str
    remote_type: str
    remote_id: str
    sha256: str


@dataclass(frozen=True, slots=True)
class PublishedIdentity:
    """Trusted durable identity of one previously published author tree."""

    source_fingerprint: str
    tree_sha256: str
    manifest_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_fingerprint", _published_sha256(self.source_fingerprint))
        object.__setattr__(self, "tree_sha256", _published_sha256(self.tree_sha256))
        object.__setattr__(self, "manifest_sha256", _published_sha256(self.manifest_sha256))


@dataclass(frozen=True, slots=True)
class ManagedFileInspection:
    """One verified manifest-managed file, without a host filesystem path."""

    relative_path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.relative_path, str):
            raise ExportError("invalid_managed_file_inspection")
        relative = PurePosixPath(self.relative_path)
        if (
            not self.relative_path
            or "\\" in self.relative_path
            or relative.is_absolute()
            or relative.as_posix() != self.relative_path
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise ExportError("invalid_managed_file_inspection")
        object.__setattr__(self, "sha256", _published_sha256(self.sha256))
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise ExportError("invalid_managed_file_inspection")


@dataclass(frozen=True, slots=True)
class PublishedTreeInspection:
    """Bounded verification of one trusted published-manifest page."""

    layout_version: str
    source_fingerprint: str
    tree_sha256: str
    manifest_sha256: str
    managed_file_count: int
    start_index: int
    next_index: int
    files: tuple[ManagedFileInspection, ...]
    bytes_read: int
    complete: bool
    budget_exhausted: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "layout_version", _text(self.layout_version, "layout_version"))
        object.__setattr__(self, "source_fingerprint", _published_sha256(self.source_fingerprint))
        object.__setattr__(self, "tree_sha256", _published_sha256(self.tree_sha256))
        object.__setattr__(self, "manifest_sha256", _published_sha256(self.manifest_sha256))
        object.__setattr__(self, "files", tuple(self.files))
        integers = (self.managed_file_count, self.start_index, self.next_index, self.bytes_read)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in integers):
            raise ExportError("invalid_published_tree_inspection")
        if (
            self.start_index > self.next_index
            or self.next_index > self.managed_file_count
            or self.next_index - self.start_index != len(self.files)
            or sum(item.size_bytes for item in self.files) > self.bytes_read
            or not isinstance(self.complete, bool)
            or not isinstance(self.budget_exhausted, bool)
            or (self.complete and self.budget_exhausted)
            or (self.complete and (self.start_index != 0 or self.next_index != self.managed_file_count))
        ):
            raise ExportError("invalid_published_tree_inspection")


@dataclass(frozen=True, slots=True)
class RenderedExport:
    """A complete job-scoped staging tree ready for guarded publication."""

    layout_version: str
    job_id: str
    author: ExportAuthor
    author_segment: str
    staging_directory: Path
    predecessor_manifest_sha256: str | None
    source_fingerprint: str
    content_fingerprints: tuple[ContentFingerprint, ...]
    files: tuple[ManagedFile, ...]
    tree_sha256: str
    manifest_sha256: str


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Stable identity of a published author tree."""

    layout_version: str
    author_directory: Path
    manifest_path: Path
    source_fingerprint: str
    content_fingerprints: tuple[ContentFingerprint, ...]
    managed_files: tuple[ManagedFile, ...]
    tree_sha256: str
    manifest_sha256: str

    @classmethod
    def from_rendered(cls, rendered: RenderedExport, author_directory: Path, manifest_path: Path) -> Self:
        return cls(
            layout_version=rendered.layout_version,
            author_directory=author_directory,
            manifest_path=manifest_path,
            source_fingerprint=rendered.source_fingerprint,
            content_fingerprints=rendered.content_fingerprints,
            managed_files=rendered.files,
            tree_sha256=rendered.tree_sha256,
            manifest_sha256=rendered.manifest_sha256,
        )


__all__ = [
    "ContentFingerprint",
    "ExportAuthor",
    "ExportContent",
    "ExportResult",
    "ManagedFile",
    "ManagedFileInspection",
    "PublishedIdentity",
    "PublishedTreeInspection",
    "RenderedExport",
    "VerifiedAsset",
]
