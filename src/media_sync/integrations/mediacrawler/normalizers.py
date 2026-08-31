"""Normalize the pinned MediaCrawler JSONL schemas without importing upstream code."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from media_sync.domain import (
    AssetKind,
    AssetSnapshot,
    AuthorSnapshot,
    ContentKind,
    ContentSnapshot,
    DomainError,
    Platform,
)

from .envelope import MediaCrawlerEnvelope
from .jsonl import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_LINE_BYTES,
    DEFAULT_MAX_PATH_CHARS,
    DEFAULT_MAX_RECORDS,
    JsonlReadResult,
    QuarantinedRecord,
    QuarantineReason,
    read_jsonl,
    read_jsonl_bytes,
)
from .weibo_media import (
    WEIBO_IMAGES_FIELD,
    is_weibo_numeric_note_id,
    is_weibo_proxy_image_url,
)

_GIT_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
_CHINA_TZ = timezone(timedelta(hours=8))
_BILI_PROGRESSIVE_FIELD = "__media_sync_bili_progressive_url"
_PRIVATE_MEDIA_FIELDS = frozenset({_BILI_PROGRESSIVE_FIELD, WEIBO_IMAGES_FIELD})
_DY_EPHEMERAL_MEDIA_URL_FIELDS = frozenset({"video_download_url", "cover_url", "music_download_url"})
_DY_NOTE_MEDIA_URL_FIELD = "note_download_url"
_KS_EPHEMERAL_MEDIA_URL_FIELDS = frozenset({"video_play_url", "video_cover_url"})
_WEIBO_PID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class NormalizationContext:
    """Trusted subscription identity and provenance supplied outside upstream output."""

    platform: Platform
    creator_remote_id: str
    creator_display_name: str
    upstream_sha: str
    ingested_at: datetime
    allow_bili_progressive_detail: bool = False

    def __post_init__(self) -> None:
        creator_remote_id = self.creator_remote_id.strip()
        creator_display_name = self.creator_display_name.strip()
        upstream_sha = self.upstream_sha.strip().lower()
        if not creator_remote_id:
            raise ValueError("creator_remote_id must not be blank")
        if not creator_display_name:
            raise ValueError("creator_display_name must not be blank")
        if _GIT_SHA.fullmatch(upstream_sha) is None:
            raise ValueError("upstream_sha must be a full 40-character Git commit")
        if self.ingested_at.tzinfo is None or self.ingested_at.utcoffset() is None:
            raise ValueError("ingested_at must be timezone-aware")
        object.__setattr__(self, "creator_remote_id", creator_remote_id)
        object.__setattr__(self, "creator_display_name", creator_display_name)
        object.__setattr__(self, "upstream_sha", upstream_sha)
        object.__setattr__(self, "ingested_at", self.ingested_at.astimezone(UTC))


class RecordNormalizationError(ValueError):
    """Safe record rejection that never includes an upstream field or value."""

    def __init__(self, reason: QuarantineReason) -> None:
        self.reason = reason
        super().__init__(f"MediaCrawler record rejected: {reason.value}")


@dataclass(frozen=True, slots=True)
class NormalizedMediaRecord:
    """One author/content/assets aggregate ready for the normalized repository port."""

    author: AuthorSnapshot
    content: ContentSnapshot
    assets: tuple[AssetSnapshot, ...]


@dataclass(frozen=True, slots=True)
class NormalizationBatch:
    """Bounded normalized records plus safe quarantine evidence."""

    records: tuple[NormalizedMediaRecord, ...]
    quarantined: tuple[QuarantinedRecord, ...]
    bytes_read: int
    records_seen: int
    truncated_tail: bool


@dataclass(frozen=True, slots=True)
class _ContentParts:
    remote_id: str
    kind: ContentKind
    title: str | None
    body: str | None
    canonical_url: str | None
    published_at: datetime | None
    metrics: Mapping[str, int | float]
    asset_groups: tuple[tuple[AssetKind, tuple[str | None, ...]], ...] = ()
    remote_type: str = "content"


def _text(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        normalized = value.strip()
    elif isinstance(value, int | float):
        normalized = str(value).strip()
    else:
        return None
    if not normalized or normalized.lower() in {"none", "null"}:
        return None
    return normalized


def _required_id(record: Mapping[str, object], key: str) -> str:
    value = _text(record.get(key))
    if value is None:
        raise RecordNormalizationError(QuarantineReason.MISSING_REQUIRED_FIELD)
    return value


def _safe_url(value: object) -> str | None:
    normalized = _text(value)
    if normalized is None:
        return None
    if normalized.startswith("//"):
        normalized = f"https:{normalized}"
    parsed = urlsplit(normalized)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return normalized


def _url_list(value: object) -> tuple[str, ...]:
    candidates: list[object]
    if isinstance(value, str):
        candidates = list(value.split(","))
    elif isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        candidates = list(value)
    else:
        candidates = []
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        url = _safe_url(candidate)
        if url is not None and url not in seen:
            result.append(url)
            seen.add(url)
    return tuple(result)


def _dy_url_list(value: object, *, allow_scalar_commas: bool) -> tuple[str, ...]:
    """Parse one Douyin media field while rejecting ambiguous sequence drift."""

    if isinstance(value, str):
        if "," in value and not allow_scalar_commas:
            return ()
        candidates: Sequence[object] = value.split(",") if allow_scalar_commas else (value,)
    elif isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        candidates = value
    else:
        return ()
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        # A comma inside an already-sequenced item can smuggle a second URL into
        # the first URL's path.  It is schema drift, not another list boundary.
        if not isinstance(candidate, str) or "," in candidate:
            continue
        url = _safe_url(candidate)
        if url is not None and url not in seen:
            result.append(url)
            seen.add(url)
    return tuple(result)


def _strip_private_media_fields(value: object) -> object:
    """Copy JSON-shaped input while recursively removing shim-only media fields."""

    if isinstance(value, Mapping):
        return {
            key: _strip_private_media_fields(item) for key, item in value.items() if key not in _PRIVATE_MEDIA_FIELDS
        }
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return [_strip_private_media_fields(item) for item in value]
    return value


def _weibo_image_urls(value: object) -> tuple[str, ...]:
    """Parse one all-or-nothing ordered Weibo image capture payload."""

    # The JSON reader freezes a JSON list to a tuple before normalization.
    if not isinstance(value, Sequence) or isinstance(value, bytes | bytearray | str) or not value:
        return ()
    urls: list[str] = []
    seen_pids: set[str] = set()
    seen_urls: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"pid", "url"}:
            return ()
        pid = item.get("pid")
        if not isinstance(pid, str) or not pid or pid != pid.strip() or _WEIBO_PID.fullmatch(pid) is None:
            return ()
        url = item.get("url")
        if not isinstance(url, str) or not is_weibo_proxy_image_url(url) or pid in seen_pids or url in seen_urls:
            return ()
        seen_pids.add(pid)
        seen_urls.add(url)
        urls.append(url)
    return tuple(urls)


def _query_free_media_url(value: object) -> object:
    """Retain only a canonical HTTP(S) origin/path in durable raw metadata."""

    if isinstance(value, str):
        normalized = _safe_url(value)
        if normalized is None:
            return None
        parsed = urlsplit(normalized)
        try:
            hostname = parsed.hostname
            port = parsed.port
            if hostname is None:
                return None
            normalized_host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
        except (UnicodeError, ValueError):
            return None
        if not normalized_host or "%" in normalized_host:
            return None
        if ":" in normalized_host:
            normalized_host = f"[{normalized_host}]"
        scheme = parsed.scheme.lower()
        default_port = 80 if scheme == "http" else 443
        authority = normalized_host if port in {None, default_port} else f"{normalized_host}:{port}"
        return urlunsplit((scheme, authority, parsed.path or "/", "", ""))
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return [_query_free_media_url(item) for item in value]
    # The upstream fields are strings (or, defensively, string sequences).
    # Any other shape is schema drift and must not preserve opaque nested
    # values that could contain a future signed URL or credential.
    return None


def _strip_ks_media_url_ephemera(record: Mapping[str, object]) -> Mapping[str, object]:
    """Keep Kuaishou media queries in Asset source URLs, never retained raw."""

    return {
        key: _query_free_media_url(value) if key in _KS_EPHEMERAL_MEDIA_URL_FIELDS else value
        for key, value in record.items()
    }


def _query_free_flat_media_urls(value: object, *, allow_scalar_commas: bool) -> object:
    """Sanitize one URL or a flat URL sequence without retaining opaque children."""

    if isinstance(value, str):
        if "," in value:
            if not allow_scalar_commas:
                return None
            candidates: Sequence[object] = value.split(",")
        else:
            return _query_free_media_url(value)
    elif isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        candidates = value
    else:
        return None
    return [_query_free_media_url(item) if isinstance(item, str) and "," not in item else None for item in candidates]


def _strip_dy_media_url_ephemera(record: Mapping[str, object]) -> Mapping[str, object]:
    """Keep Douyin signed media URLs transient while retaining auditable raw shape."""

    sanitized: dict[str, object] = {}
    for key, value in record.items():
        if key == _DY_NOTE_MEDIA_URL_FIELD:
            sanitized[key] = _query_free_flat_media_urls(value, allow_scalar_commas=True)
        elif key in _DY_EPHEMERAL_MEDIA_URL_FIELDS:
            sanitized[key] = _query_free_flat_media_urls(value, allow_scalar_commas=False)
        else:
            sanitized[key] = value
    return sanitized


def _number(value: object) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace(",", "")
    if not normalized or normalized.lower() in {"none", "null"}:
        return None
    try:
        numeric = float(normalized)
    except ValueError:
        return None
    if not math.isfinite(numeric):
        return None
    return int(numeric) if numeric.is_integer() else numeric


def _metrics(record: Mapping[str, object], fields: Mapping[str, str]) -> Mapping[str, int | float]:
    result: dict[str, int | float] = {}
    for upstream_name, normalized_name in fields.items():
        value = _number(record.get(upstream_name))
        if value is not None:
            result[normalized_name] = value
    return result


def _published_at(value: object) -> datetime | None:
    numeric = _number(value)
    if numeric is not None:
        seconds = float(numeric)
        if seconds <= 0:
            return None
        if seconds >= 1_000_000_000_000:
            seconds /= 1_000
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None

    text = _text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        # MediaCrawler's Tieba helper persists a host-local string. Its intended
        # deployment timezone is China Standard Time, while the raw value stays
        # available in the envelope for future reprocessing.
        parsed = parsed.replace(tzinfo=_CHINA_TZ)
    return parsed.astimezone(UTC)


def _summary(value: str | None, *, limit: int = 120) -> str | None:
    if value is None:
        return None
    return value if len(value) <= limit else value[:limit]


def _normalize_xhs(record: Mapping[str, object]) -> _ContentParts:
    remote_id = _required_id(record, "note_id")
    images = _url_list(record.get("image_list"))
    videos = _url_list(record.get("video_url"))
    if images and videos:
        kind = ContentKind.MIXED
    elif videos:
        kind = ContentKind.VIDEO
    elif len(images) > 1:
        kind = ContentKind.GALLERY
    elif images:
        kind = ContentKind.IMAGE
    else:
        kind = ContentKind.TEXT
    body = _text(record.get("desc"))
    title = _text(record.get("title")) or _summary(body)
    return _ContentParts(
        remote_id=remote_id,
        kind=kind,
        title=title,
        body=body,
        canonical_url=f"https://www.xiaohongshu.com/explore/{remote_id}",
        published_at=_published_at(record.get("time")),
        metrics=_metrics(
            record,
            {
                "liked_count": "likes",
                "collected_count": "collections",
                "comment_count": "comments",
                "share_count": "shares",
            },
        ),
        asset_groups=((AssetKind.IMAGE, images), (AssetKind.VIDEO, videos)),
    )


def _normalize_dy(record: Mapping[str, object]) -> _ContentParts:
    remote_id = _required_id(record, "aweme_id")
    images = _dy_url_list(record.get("note_download_url"), allow_scalar_commas=True)
    video = _dy_url_list(record.get("video_download_url"), allow_scalar_commas=False)
    audio = _dy_url_list(record.get("music_download_url"), allow_scalar_commas=False)
    cover = _dy_url_list(record.get("cover_url"), allow_scalar_commas=False)
    # The pinned crawler deliberately chooses image downloads whenever
    # note_download_url is populated; its video URL can then be an audio stream.
    if len(images) > 1:
        kind = ContentKind.GALLERY
        videos: tuple[str, ...] = ()
    elif images:
        kind = ContentKind.IMAGE
        videos = ()
    elif video:
        kind = ContentKind.VIDEO
        videos = video
    elif audio:
        kind = ContentKind.AUDIO
        videos = ()
    else:
        kind = ContentKind.TEXT
        videos = ()
    body = _text(record.get("desc"))
    title = _text(record.get("title")) or _summary(body)
    canonical_url = _safe_url(record.get("aweme_url")) or f"https://www.douyin.com/video/{remote_id}"
    return _ContentParts(
        remote_id=remote_id,
        kind=kind,
        title=title,
        body=body,
        canonical_url=canonical_url,
        published_at=_published_at(record.get("create_time")),
        metrics=_metrics(
            record,
            {
                "liked_count": "likes",
                "collected_count": "collections",
                "comment_count": "comments",
                "share_count": "shares",
            },
        ),
        asset_groups=(
            (AssetKind.IMAGE, images),
            (AssetKind.VIDEO, videos),
            (AssetKind.AUDIO, audio),
            (AssetKind.COVER, cover),
        ),
    )


def _normalize_ks(record: Mapping[str, object]) -> _ContentParts:
    remote_id = _required_id(record, "video_id")
    body = _text(record.get("desc"))
    return _ContentParts(
        remote_id=remote_id,
        kind=ContentKind.VIDEO,
        title=_text(record.get("title")) or _summary(body),
        body=body,
        canonical_url=_safe_url(record.get("video_url")) or f"https://www.kuaishou.com/short-video/{remote_id}",
        published_at=_published_at(record.get("create_time")),
        metrics=_metrics(record, {"liked_count": "likes", "viewd_count": "views"}),
        asset_groups=(
            (AssetKind.VIDEO, _url_list(record.get("video_play_url"))),
            (AssetKind.COVER, _url_list(record.get("video_cover_url"))),
        ),
    )


def _normalize_bili(record: Mapping[str, object], *, allow_progressive_detail: bool = False) -> _ContentParts:
    if _text(record.get("dynamic_id")) is not None:
        remote_id = _required_id(record, "dynamic_id")
        body = _text(record.get("text"))
        return _ContentParts(
            remote_id=remote_id,
            kind=ContentKind.DYNAMIC,
            title=_summary(body),
            body=body,
            canonical_url=f"https://t.bilibili.com/{remote_id}",
            published_at=_published_at(record.get("pub_ts")),
            metrics=_metrics(
                record,
                {
                    "total_comments": "comments",
                    "total_forwards": "forwards",
                    "total_liked": "likes",
                },
            ),
            remote_type="dynamic",
        )

    remote_id = _required_id(record, "video_id")
    body = _text(record.get("desc"))
    return _ContentParts(
        remote_id=remote_id,
        kind=ContentKind.VIDEO,
        title=_text(record.get("title")) or _summary(body),
        body=body,
        canonical_url=_safe_url(record.get("video_url")) or f"https://www.bilibili.com/video/av{remote_id}",
        published_at=_published_at(record.get("create_time")),
        metrics=_metrics(
            record,
            {
                "liked_count": "likes",
                "disliked_count": "dislikes",
                "video_play_count": "views",
                "video_favorite_count": "favorites",
                "video_share_count": "shares",
                "video_coin_count": "coins",
                "video_danmaku": "danmaku",
                "video_comment": "comments",
            },
        ),
        # Every ordinary Bilibili video owns a stable video slot. The optional
        # private detail field is only trusted by an explicitly gated detail
        # flow; otherwise the slot remains locator-only for a later refresh.
        asset_groups=(
            (
                AssetKind.VIDEO,
                (_safe_url(record.get(_BILI_PROGRESSIVE_FIELD)) if allow_progressive_detail else None,),
            ),
            (AssetKind.COVER, _url_list(record.get("video_cover_url"))),
        ),
    )


def _normalize_wb(record: Mapping[str, object]) -> _ContentParts:
    remote_id = _required_id(record, "note_id")
    body = _text(record.get("content"))
    page_info = record.get("page_info")
    eligible_image_post = (
        is_weibo_numeric_note_id(remote_id) and record.get("retweeted_status") is None and page_info in (None, {})
    )
    images = _weibo_image_urls(record.get(WEIBO_IMAGES_FIELD)) if eligible_image_post else ()
    if len(images) > 1:
        kind = ContentKind.GALLERY
    elif images:
        kind = ContentKind.IMAGE
    else:
        kind = ContentKind.TEXT
    return _ContentParts(
        remote_id=remote_id,
        kind=kind,
        title=_summary(body),
        body=body,
        canonical_url=_safe_url(record.get("note_url")) or f"https://m.weibo.cn/detail/{remote_id}",
        published_at=_published_at(record.get("create_time")),
        metrics=_metrics(
            record,
            {"liked_count": "likes", "comments_count": "comments", "shared_count": "shares"},
        ),
        asset_groups=((AssetKind.IMAGE, images),),
    )


def _normalize_tieba(record: Mapping[str, object]) -> _ContentParts:
    remote_id = _required_id(record, "note_id")
    return _ContentParts(
        remote_id=remote_id,
        kind=ContentKind.ARTICLE,
        title=_text(record.get("title")),
        body=_text(record.get("desc")),
        canonical_url=_safe_url(record.get("note_url")) or f"https://tieba.baidu.com/p/{remote_id}",
        published_at=_published_at(record.get("publish_time")),
        metrics=_metrics(record, {"total_replay_num": "replies"}),
    )


def _normalize_zhihu(record: Mapping[str, object]) -> _ContentParts:
    remote_id = _required_id(record, "content_id")
    content_type = (_text(record.get("content_type")) or "").lower()
    if content_type in {"answer", "article"}:
        kind = ContentKind.ARTICLE
    elif content_type in {"video", "zvideo"}:
        kind = ContentKind.VIDEO
    elif content_type == "audio":
        kind = ContentKind.AUDIO
    else:
        raise RecordNormalizationError(QuarantineReason.UNKNOWN_RECORD)
    return _ContentParts(
        remote_id=remote_id,
        kind=kind,
        title=_text(record.get("title")),
        body=_text(record.get("content_text")) or _text(record.get("desc")),
        canonical_url=_safe_url(record.get("content_url")),
        published_at=_published_at(record.get("created_time")),
        metrics=_metrics(record, {"voteup_count": "upvotes", "comment_count": "comments"}),
    )


_NORMALIZERS = {
    Platform.XHS: _normalize_xhs,
    Platform.DY: _normalize_dy,
    Platform.KS: _normalize_ks,
    Platform.BILI: _normalize_bili,
    Platform.WB: _normalize_wb,
    Platform.TIEBA: _normalize_tieba,
    Platform.ZHIHU: _normalize_zhihu,
}


def _mime_type(kind: AssetKind, source_url: str | None) -> str | None:
    if source_url is None:
        return None
    suffix = Path(urlsplit(source_url).path).suffix.lower()
    known = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
    }
    guessed = known.get(suffix)
    if guessed is not None:
        return guessed
    if kind is AssetKind.COVER:
        return None
    return None


def _build_assets(
    platform: Platform,
    content_remote_id: str,
    groups: Sequence[tuple[AssetKind, Sequence[str | None]]],
    raw: Mapping[str, object],
) -> tuple[AssetSnapshot, ...]:
    assets: list[AssetSnapshot] = []
    for kind, urls in groups:
        seen: set[str | None] = set()
        position = 0
        for source_url in urls:
            if source_url in seen:
                continue
            seen.add(source_url)
            assets.append(
                AssetSnapshot(
                    platform=platform,
                    remote_id=f"{content_remote_id}:{kind.value}:{position}",
                    content_remote_id=content_remote_id,
                    kind=kind,
                    source_url=source_url,
                    position=position,
                    mime_type=_mime_type(kind, source_url),
                    raw=raw,
                )
            )
            position += 1
    return tuple(assets)


def normalize_record(record: Mapping[str, object], context: NormalizationContext) -> NormalizedMediaRecord:
    """Normalize one actual MediaCrawler content/dynamic output dictionary."""

    if "comment_id" in record:
        raise RecordNormalizationError(QuarantineReason.UNKNOWN_RECORD)
    try:
        if context.platform is Platform.BILI:
            parts = _normalize_bili(record, allow_progressive_detail=context.allow_bili_progressive_detail)
        else:
            parts = _NORMALIZERS[context.platform](record)
        sanitized_record = _strip_private_media_fields(record)
        if not isinstance(sanitized_record, Mapping):  # pragma: no cover - record is already a mapping
            raise RecordNormalizationError(QuarantineReason.INVALID_RECORD)
        if context.platform is Platform.DY:
            sanitized_record = _strip_dy_media_url_ephemera(sanitized_record)
        elif context.platform is Platform.KS:
            sanitized_record = _strip_ks_media_url_ephemera(sanitized_record)
        envelope = MediaCrawlerEnvelope(
            platform=context.platform,
            upstream_sha=context.upstream_sha,
            ingested_at=context.ingested_at,
            record=sanitized_record,
        )
        raw = envelope.as_mapping()
        author = AuthorSnapshot(
            platform=context.platform,
            remote_id=context.creator_remote_id,
            display_name=context.creator_display_name,
            raw=raw,
        )
        content = ContentSnapshot(
            platform=context.platform,
            remote_id=parts.remote_id,
            author_remote_id=context.creator_remote_id,
            kind=parts.kind,
            remote_type=parts.remote_type,
            title=parts.title,
            body=parts.body,
            canonical_url=parts.canonical_url,
            published_at=parts.published_at,
            metrics=parts.metrics,
            raw=raw,
        )
        assets = _build_assets(context.platform, parts.remote_id, parts.asset_groups, raw)
    except RecordNormalizationError:
        raise
    except (DomainError, TypeError, ValueError):
        raise RecordNormalizationError(QuarantineReason.INVALID_RECORD) from None
    return NormalizedMediaRecord(author=author, content=content, assets=assets)


def normalize_jsonl(
    path: str | Path,
    context: NormalizationContext,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
    max_path_chars: int = DEFAULT_MAX_PATH_CHARS,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> NormalizationBatch:
    """Stream, quarantine and normalize one bounded upstream JSONL file."""

    read_result: JsonlReadResult = read_jsonl(
        path,
        max_bytes=max_bytes,
        max_line_bytes=max_line_bytes,
        max_path_chars=max_path_chars,
        max_records=max_records,
    )
    return _normalize_read_result(read_result, context)


def normalize_jsonl_bytes(
    payload: bytes,
    context: NormalizationContext,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> NormalizationBatch:
    """Normalize one receipt-verified immutable JSONL payload."""

    read_result = read_jsonl_bytes(
        payload,
        max_bytes=max_bytes,
        max_line_bytes=max_line_bytes,
        max_records=max_records,
    )
    return _normalize_read_result(read_result, context)


def _normalize_read_result(
    read_result: JsonlReadResult,
    context: NormalizationContext,
) -> NormalizationBatch:
    normalized: list[NormalizedMediaRecord] = []
    quarantined = list(read_result.quarantined)
    for source_record in read_result.records:
        try:
            normalized.append(normalize_record(source_record.value, context))
        except RecordNormalizationError as error:
            quarantined.append(
                QuarantinedRecord(
                    line_number=source_record.line_number,
                    byte_count=source_record.byte_count,
                    fingerprint_sha256=source_record.fingerprint_sha256,
                    reason=error.reason,
                )
            )
    return NormalizationBatch(
        records=tuple(normalized),
        quarantined=tuple(quarantined),
        bytes_read=read_result.bytes_read,
        records_seen=read_result.records_seen,
        truncated_tail=read_result.truncated_tail,
    )


__all__ = [
    "NormalizationBatch",
    "NormalizationContext",
    "NormalizedMediaRecord",
    "RecordNormalizationError",
    "normalize_jsonl",
    "normalize_jsonl_bytes",
    "normalize_record",
]
