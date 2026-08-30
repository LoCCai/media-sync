"""Pure deterministic planning for Emby/Jellyfin layout v1."""

from __future__ import annotations

import hashlib
import json
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

from .errors import ExportConflictError, ExportError
from .models import ContentFingerprint, ExportAuthor, ExportContent, VerifiedAsset

LAYOUT_VERSION = "emby-jellyfin-v1"
MANIFEST_NAME = ".media-sync-managed-v1.json"
MAX_SEGMENT_BYTES = 180
_IDENTITY_HASH_CHARS = 16
_MAX_EPISODE = 2_147_483_647
_WINDOWS_ILLEGAL = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul", "clock$"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)
_KIND_ORDER = {
    "video": 0,
    "audio": 1,
    "cover": 2,
    "image": 3,
    "subtitle": 4,
    "attachment": 5,
    "avatar": 6,
}
_MIME_EXTENSIONS = {
    "application/epub+zip": ".epub",
    "application/json": ".json",
    "application/octet-stream": ".bin",
    "application/pdf": ".pdf",
    "application/x-subrip": ".srt",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "image/avif": ".avif",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "text/plain": ".txt",
    "text/vtt": ".vtt",
    "video/mp4": ".mp4",
    "video/ogg": ".ogv",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
}


@dataclass(frozen=True, slots=True)
class PlannedFile:
    """One author-relative output, backed by bytes or a verified asset."""

    relative_path: PurePosixPath
    payload: bytes | None = None
    asset: VerifiedAsset | None = None

    def __post_init__(self) -> None:
        if (self.payload is None) == (self.asset is None):
            raise TypeError("planned files require exactly one byte source")


@dataclass(frozen=True, slots=True)
class LayoutPlan:
    """Pure output plan with stable source fingerprints."""

    author_segment: str
    source_fingerprint: str
    content_fingerprints: tuple[ContentFingerprint, ...]
    files: tuple[PlannedFile, ...]


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _iso8601(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    shortened = encoded[:max_bytes]
    while shortened:
        try:
            return shortened.decode("utf-8")
        except UnicodeDecodeError:
            shortened = shortened[:-1]
    return "_"


def _sanitize_segment(value: str, *, max_bytes: int) -> str:
    normalized = unicodedata.normalize("NFC", value)
    sanitized = "".join(
        "_" if character in _WINDOWS_ILLEGAL or ord(character) < 32 or ord(character) == 127 else character
        for character in normalized
    )
    sanitized = sanitized.rstrip(" .")
    if not sanitized:
        sanitized = "_"
    first_component = sanitized.split(".", maxsplit=1)[0].casefold()
    if first_component in _WINDOWS_RESERVED:
        sanitized = f"_{sanitized}"
    shortened = _truncate_utf8(sanitized, max_bytes).rstrip(" .")
    return shortened or "_"


def _identity_digest(*parts: str) -> str:
    hasher = hashlib.sha256()
    for part in parts:
        encoded = unicodedata.normalize("NFC", part).encode("utf-8")
        hasher.update(len(encoded).to_bytes(8, "big"))
        hasher.update(encoded)
    return hasher.hexdigest()


def _stable_segment(readable: str, identity: tuple[str, ...], *, max_bytes: int = MAX_SEGMENT_BYTES) -> str:
    suffix = f"-{_identity_digest(*identity)[:_IDENTITY_HASH_CHARS]}"
    budget = max_bytes - len(suffix.encode("ascii"))
    if budget < 1:
        raise ValueError("max_bytes cannot hold an identity suffix")
    return f"{_sanitize_segment(readable, max_bytes=budget)}{suffix}"


def author_relative_directory(author: ExportAuthor) -> PurePosixPath:
    """Return the stable, title-independent relative directory for an author."""

    segment = _stable_segment(
        f"{author.platform}-creator-{author.remote_id}",
        (LAYOUT_VERSION, "creator", author.platform, author.remote_id),
        max_bytes=120,
    )
    return PurePosixPath(segment)


def stable_episode_number(platform: str, remote_type: str, remote_id: str) -> int:
    """Map a content identity to a stable positive signed-32-bit episode number."""

    digest = _identity_digest(LAYOUT_VERSION, "episode", platform.lower(), remote_type.lower(), remote_id)
    return int(digest[:16], 16) % _MAX_EPISODE + 1


def _asset_source_payload(asset: VerifiedAsset) -> dict[str, object]:
    return {
        "checksum_sha256": asset.checksum_sha256,
        "generation": asset.generation,
        "kind": asset.kind,
        "mime_type": asset.mime_type,
        "position": asset.position,
        "remote_id": asset.remote_id,
        "size_bytes": asset.size_bytes,
    }


def _sorted_assets(content: ExportContent) -> tuple[VerifiedAsset, ...]:
    assets = tuple(
        sorted(
            content.assets,
            key=lambda item: (_KIND_ORDER.get(item.kind, 99), item.position, item.remote_id, item.checksum_sha256),
        )
    )
    seen: set[tuple[str, int, str]] = set()
    for asset in assets:
        identity = (asset.kind, asset.position, asset.remote_id)
        if identity in seen:
            raise ExportError("duplicate_asset_identity")
        seen.add(identity)
    return assets


def _content_source_payload(content: ExportContent) -> dict[str, object]:
    return {
        "assets": [_asset_source_payload(asset) for asset in _sorted_assets(content)],
        "author_remote_id": content.author_remote_id,
        "body": content.body,
        "content_kind": content.kind,
        "first_seen_at": _iso8601(content.first_seen_at),
        "platform": content.platform,
        "published_at": _iso8601(content.published_at),
        "remote_id": content.remote_id,
        "remote_type": content.remote_type,
        "schema_version": 1,
        "title": content.title,
    }


def content_source_fingerprint(content: ExportContent) -> str:
    """Fingerprint every allowlisted input that can affect one rendered item."""

    return _fingerprint(_content_source_payload(content))


def _content_fingerprint(content: ExportContent) -> ContentFingerprint:
    return ContentFingerprint(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        sha256=content_source_fingerprint(content),
    )


def export_source_fingerprint(author: ExportAuthor, contents: Sequence[ExportContent]) -> str:
    """Fingerprint one complete author render independently of input order."""

    content_rows = [
        {
            "platform": item.platform,
            "remote_id": item.remote_id,
            "remote_type": item.remote_type,
            "sha256": content_source_fingerprint(item),
        }
        for item in contents
    ]
    content_rows.sort(key=lambda item: (str(item["platform"]), str(item["remote_type"]), str(item["remote_id"])))
    return _fingerprint(
        {
            "author": {
                "display_name": author.display_name,
                "handle": author.handle,
                "platform": author.platform,
                "remote_id": author.remote_id,
            },
            "contents": content_rows,
            "layout_version": LAYOUT_VERSION,
        }
    )


def _xml_text(value: str) -> str:
    return "".join(
        character
        for character in value
        if ord(character) in {0x9, 0xA, 0xD}
        or 0x20 <= ord(character) <= 0xD7FF
        or 0xE000 <= ord(character) <= 0xFFFD
        or 0x10000 <= ord(character) <= 0x10FFFF
    )


def _child(parent: ET.Element, tag: str, text: str | int, attributes: dict[str, str] | None = None) -> ET.Element:
    element = ET.SubElement(parent, tag, attributes or {})
    element.text = _xml_text(str(text))
    return element


def _xml_bytes(root: ET.Element) -> bytes:
    ET.indent(root, space="  ")
    return bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=True)) + b"\n"


def _tvshow_nfo(author: ExportAuthor) -> bytes:
    root = ET.Element("tvshow")
    _child(root, "title", author.display_name)
    if author.handle is not None:
        _child(root, "sorttitle", author.handle)
    _child(
        root,
        "uniqueid",
        author.remote_id,
        {"type": f"media-sync-{author.platform}-creator", "default": "true"},
    )
    _child(root, "studio", author.platform)
    return _xml_bytes(root)


def _episode_nfo(
    author: ExportAuthor,
    content: ExportContent,
    *,
    season: int,
    episode: int,
    poster_name: str | None,
    backdrop_name: str | None,
) -> bytes:
    root = ET.Element("episodedetails")
    _child(root, "title", content.title or f"{content.remote_type}:{content.remote_id}")
    _child(root, "showtitle", author.display_name)
    _child(root, "season", season)
    _child(root, "episode", episode)
    if content.published_at is not None:
        _child(root, "aired", content.published_at.date().isoformat())
    _child(root, "dateadded", _iso8601(content.first_seen_at) or "")
    if content.body is not None:
        _child(root, "plot", content.body)
    _child(
        root,
        "uniqueid",
        content.remote_id,
        {"type": f"media-sync-{content.platform}-{content.remote_type}", "default": "true"},
    )
    _child(root, "studio", content.platform)
    if poster_name is not None:
        _child(root, "thumb", poster_name, {"aspect": "poster"})
    if backdrop_name is not None:
        fanart = ET.SubElement(root, "fanart")
        _child(fanart, "thumb", backdrop_name)
    return _xml_bytes(root)


def _extension(asset: VerifiedAsset) -> str:
    return _MIME_EXTENSIONS.get(asset.mime_type, ".bin")


def _content_base(content: ExportContent, season: int, episode: int) -> str:
    readable = f"S{season:04d}E{episode:010d}-{content.platform}-{content.remote_type}-{content.remote_id}"
    return _stable_segment(
        readable,
        (LAYOUT_VERSION, "content", content.platform, content.remote_type, content.remote_id),
        max_bytes=145,
    )


def _asset_filename(prefix: str, index: int, asset: VerifiedAsset) -> str:
    return _stable_segment(
        f"{prefix}-{index:03d}-{asset.remote_id}",
        (LAYOUT_VERSION, "asset", asset.kind, str(asset.position), asset.remote_id, asset.checksum_sha256),
        max_bytes=150 - len(_extension(asset).encode("ascii")),
    ) + _extension(asset)


def _creator_source_json(author: ExportAuthor) -> bytes:
    return _canonical_json_bytes(
        {
            "display_name": author.display_name,
            "entity": "creator",
            "handle": author.handle,
            "layout_version": LAYOUT_VERSION,
            "platform": author.platform,
            "remote_id": author.remote_id,
            "schema_version": 1,
        }
    )


def _content_source_json(content: ExportContent, fingerprint: str) -> bytes:
    payload = _content_source_payload(content)
    # Text lives in body.txt and NFO; source.json stays a small provenance allowlist.
    payload.pop("body")
    payload.pop("title")
    payload["entity"] = "content"
    payload["layout_version"] = LAYOUT_VERSION
    payload["source_fingerprint"] = fingerprint
    return _canonical_json_bytes(payload)


def _content_files(author: ExportAuthor, content: ExportContent, season: int, episode: int) -> tuple[PlannedFile, ...]:
    base = _content_base(content, season, episode)
    season_directory = PurePosixPath(f"Season {season:04d}")
    asset_directory = season_directory / f"{base}.assets"
    assets = _sorted_assets(content)
    planned: list[PlannedFile] = []

    playable = tuple(asset for asset in assets if asset.kind in {"video", "audio"})
    for index, asset in enumerate(playable, start=1):
        filename = f"{base}{_extension(asset)}" if index == 1 else _asset_filename(f"{base}-part", index, asset)
        planned.append(PlannedFile(season_directory / filename, asset=asset))

    images = tuple(asset for asset in assets if asset.kind == "image")
    covers = tuple(asset for asset in assets if asset.kind == "cover")
    poster = covers[0] if covers else (images[0] if images else None)
    backdrop = images[1] if len(images) > 1 else (images[0] if images else (covers[0] if covers else None))
    poster_name: str | None = None
    backdrop_name: str | None = None
    if poster is not None:
        poster_name = f"{base}-poster{_extension(poster)}"
        planned.append(PlannedFile(season_directory / poster_name, asset=poster))
    if backdrop is not None:
        backdrop_name = f"{base}-backdrop{_extension(backdrop)}"
        planned.append(PlannedFile(season_directory / backdrop_name, asset=backdrop))

    for index, asset in enumerate(images, start=1):
        planned.append(PlannedFile(asset_directory / _asset_filename("gallery", index, asset), asset=asset))
    preserved = tuple(asset for asset in assets if asset.kind in {"subtitle", "attachment", "cover", "avatar"})
    for index, asset in enumerate(preserved, start=1):
        planned.append(PlannedFile(asset_directory / _asset_filename(asset.kind, index, asset), asset=asset))
    if content.body is not None:
        planned.append(PlannedFile(asset_directory / "body.txt", payload=content.body.encode("utf-8")))

    fingerprint = content_source_fingerprint(content)
    planned.append(PlannedFile(asset_directory / "source.json", payload=_content_source_json(content, fingerprint)))
    planned.append(
        PlannedFile(
            season_directory / f"{base}.nfo",
            payload=_episode_nfo(
                author,
                content,
                season=season,
                episode=episode,
                poster_name=poster_name,
                backdrop_name=backdrop_name,
            ),
        )
    )
    return tuple(planned)


def _validate_unique_paths(files: tuple[PlannedFile, ...]) -> None:
    paths: dict[str, str] = {}
    for item in files:
        value = item.relative_path.as_posix()
        folded = unicodedata.normalize("NFC", value).casefold()
        if folded in paths and paths[folded] != value:
            raise ExportConflictError("layout_path_collision")
        if folded in paths:
            raise ExportConflictError("layout_path_collision")
        paths[folded] = value


def build_layout_plan(author: ExportAuthor, contents: tuple[ExportContent, ...]) -> LayoutPlan:
    """Validate and plan a complete deterministic author tree."""

    ordered = tuple(sorted(contents, key=lambda item: (item.platform, item.remote_type, item.remote_id)))
    identities: set[tuple[str, str, str]] = set()
    episodes: dict[tuple[int, int], tuple[str, str, str]] = {}
    content_fingerprints: list[ContentFingerprint] = []
    files: list[PlannedFile] = [
        PlannedFile(PurePosixPath("source.json"), payload=_creator_source_json(author)),
        PlannedFile(PurePosixPath("tvshow.nfo"), payload=_tvshow_nfo(author)),
    ]
    for content in ordered:
        if content.platform != author.platform or content.author_remote_id != author.remote_id:
            raise ExportError("content_author_mismatch")
        identity = (content.platform, content.remote_type, content.remote_id)
        if identity in identities:
            raise ExportError("duplicate_content_identity")
        identities.add(identity)
        season = (content.published_at or content.first_seen_at).year
        episode = stable_episode_number(*identity)
        episode_key = (season, episode)
        previous = episodes.get(episode_key)
        if previous is not None and previous != identity:
            raise ExportConflictError("episode_number_collision")
        episodes[episode_key] = identity
        content_fingerprints.append(_content_fingerprint(content))
        files.extend(_content_files(author, content, season, episode))

    frozen_files = tuple(
        sorted(files, key=lambda item: (item.relative_path.as_posix().casefold(), item.relative_path.as_posix()))
    )
    _validate_unique_paths(frozen_files)
    return LayoutPlan(
        author_segment=author_relative_directory(author).as_posix(),
        source_fingerprint=export_source_fingerprint(author, ordered),
        content_fingerprints=tuple(content_fingerprints),
        files=frozen_files,
    )


__all__ = [
    "LAYOUT_VERSION",
    "MANIFEST_NAME",
    "LayoutPlan",
    "PlannedFile",
    "author_relative_directory",
    "build_layout_plan",
    "content_source_fingerprint",
    "export_source_fingerprint",
    "stable_episode_number",
]
