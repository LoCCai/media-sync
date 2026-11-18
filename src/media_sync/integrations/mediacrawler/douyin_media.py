"""Closed Douyin media selection from the pinned upstream detail response.

The pinned store flattens ``video.play_addr_h264`` / ``play_addr_256`` /
``play_addr`` to one URL (``.upstream/MediaCrawler/store/douyin/__init__.py:132-140``)
and drops the richer ``video.bit_rate[]`` array.  This module reads only the
documented response fields, ranks the declared streams and returns one decision
without ever guessing: any drift raises a fixed ``ValueError`` subclass so a
direct caller never publishes a wrong byte stream.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

DOUYIN_MAX_BIT_RATE_ENTRIES = 8
DOUYIN_MEDIA_RANK_FIELD = "__media_sync_dy_media_rank_v1"
DOUYIN_MEDIA_FIELD = "__media_sync_dy_media_v1"

_MAX_URL_CHARS = 4_096
_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z", re.ASCII)
# Closed suffix list of hosts the pinned detail response is known to hand out for
# media bytes.  A drifted host is refused rather than fetched.
_MEDIA_HOST_SUFFIXES = (
    "douyinvod.com",
    "douyinpic.com",
    "douyinstatic.com",
    "byteimg.com",
    "snssdk.com",
    "iesdouyin.com",
)


class DouyinMediaSelectionError(ValueError):
    """Closed rejection of one drifted Douyin media declaration."""


class DouyinMediaRank(StrEnum):
    """Which declared source produced the selected URL."""

    BIT_RATE = "bit_rate"
    PLAY_ADDR_H264 = "play_addr_h264"
    PLAY_ADDR_256 = "play_addr_256"
    PLAY_ADDR = "play_addr"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class DouyinMediaSelection:
    """One bounded media decision for a single Douyin work."""

    rank: DouyinMediaRank
    video_url: str | None = field(default=None, repr=False)
    cover_url: str | None = field(default=None, repr=False)
    width: int | None = None
    height: int | None = None
    fidelity: int | None = None

    @property
    def has_video(self) -> bool:
        return self.video_url is not None

    def summary(self) -> dict[str, object]:
        """Return the only facts allowed to reach persisted or public state."""

        payload: dict[str, object] = {"rank": self.rank.value}
        if self.width is not None:
            payload["width"] = self.width
        if self.height is not None:
            payload["height"] = self.height
        return payload

    def __post_init__(self) -> None:
        if not isinstance(self.rank, DouyinMediaRank):
            raise DouyinMediaSelectionError("douyin_media_rank_invalid")
        if self.rank is DouyinMediaRank.NONE:
            if self.video_url is not None:
                raise DouyinMediaSelectionError("douyin_media_rank_invalid")
        elif self.video_url is None:
            raise DouyinMediaSelectionError("douyin_media_rank_invalid")
        if self.video_url is not None:
            validate_douyin_media_url(self.video_url)
        if self.cover_url is not None:
            validate_douyin_media_url(self.cover_url)
        for name in ("width", "height", "fidelity"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise DouyinMediaSelectionError("douyin_media_rank_invalid")


def _is_dns_hostname(value: str) -> bool:
    if not value.isascii() or len(value) > 253:
        return False
    return all(_DNS_LABEL.fullmatch(label) is not None for label in value.split("."))


def validate_douyin_media_url(value: object) -> str:
    """Return one bounded HTTPS Douyin media URL or raise ``ValueError``."""

    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or len(value) > _MAX_URL_CHARS
        or "\\" in value
        or "#" in value
        or any(character.isspace() for character in value)
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise DouyinMediaSelectionError("douyin_media_url_invalid")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise DouyinMediaSelectionError("douyin_media_url_invalid") from exc
    if (
        parsed.scheme.lower() != "https"
        or hostname is None
        or not _is_dns_hostname(hostname)
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.fragment
        or parsed.path in {"", "/"}
    ):
        raise DouyinMediaSelectionError("douyin_media_url_invalid")
    lowered = hostname.lower()
    if not any(lowered == suffix or lowered.endswith(f".{suffix}") for suffix in _MEDIA_HOST_SUFFIXES):
        raise DouyinMediaSelectionError("douyin_media_host_invalid")
    return value


def _integer(value: object) -> int:
    if type(value) is int and value >= 0:
        return value
    if type(value) is str:
        text = value.strip()
        if text.isdigit() and len(text) <= 18:
            return int(text)
    raise DouyinMediaSelectionError("douyin_media_field_invalid")


def _optional_integer(value: object) -> int | None:
    if value is None:
        return None
    return _integer(value)


def _urls(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        raise DouyinMediaSelectionError("douyin_media_field_invalid")
    raw = value.get("url_list")
    if not isinstance(raw, Sequence) or isinstance(raw, bytes | bytearray | str) or not raw:
        raise DouyinMediaSelectionError("douyin_media_field_invalid")
    urls: list[str] = []
    for item in raw:
        urls.append(validate_douyin_media_url(item))
    del label
    if len(set(urls)) != len(urls):
        raise DouyinMediaSelectionError("douyin_media_field_invalid")
    return tuple(urls)


def _preferred(urls: Sequence[str]) -> str:
    # The pinned store takes the last entry; keep that exact candidate while
    # still refusing a list whose members are not all valid media URLs.
    return urls[-1]


def _cover_url(video: Mapping[str, object]) -> str | None:
    for key in ("raw_cover", "origin_cover"):
        candidate = video.get(key)
        if not isinstance(candidate, Mapping):
            continue
        raw = candidate.get("url_list")
        if not isinstance(raw, Sequence) or isinstance(raw, bytes | bytearray | str) or len(raw) < 2:
            continue
        url = validate_douyin_media_url(raw[1])
        return url
    return None


def _bit_rate_entries(video: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = video.get("bit_rate")
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, bytes | bytearray | str):
        raise DouyinMediaSelectionError("douyin_media_field_invalid")
    if not 1 <= len(raw) <= DOUYIN_MAX_BIT_RATE_ENTRIES:
        raise DouyinMediaSelectionError("douyin_media_field_invalid")
    entries: list[Mapping[str, object]] = []
    for item in raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("play_addr"), Mapping):
            raise DouyinMediaSelectionError("douyin_media_field_invalid")
        entries.append(item)
    return tuple(entries)


def select_douyin_media(aweme_detail: object) -> DouyinMediaSelection:
    """Reduce one pinned ``aweme_detail`` to a bounded media decision."""

    if not isinstance(aweme_detail, Mapping):
        raise DouyinMediaSelectionError("douyin_media_field_invalid")
    video = aweme_detail.get("video")
    if not isinstance(video, Mapping):
        return DouyinMediaSelection(video_url=None, cover_url=None, rank=DouyinMediaRank.NONE)
    cover = _cover_url(video)
    entries = _bit_rate_entries(video)
    if entries:
        ranked: list[tuple[tuple[int, int, int, int], str, Mapping[str, object]]] = []
        for declaration, entry in enumerate(entries):
            address = entry.get("play_addr")
            if not isinstance(address, Mapping):
                raise DouyinMediaSelectionError("douyin_media_field_invalid")
            urls = _urls(address, label="bit_rate")
            width = _optional_integer(entry.get("width")) or _optional_integer(address.get("width")) or 0
            height = _optional_integer(entry.get("height")) or _optional_integer(address.get("height")) or 0
            fidelity = _optional_integer(entry.get("bit_rate")) or _optional_integer(address.get("bit_rate")) or 0
            size = _optional_integer(entry.get("data_size")) or _optional_integer(address.get("data_size")) or 0
            ranked.append(((max(width, height), fidelity, size, -declaration), _preferred(urls), entry))
        ranked.sort(key=lambda item: item[0], reverse=True)
        _, url, entry = ranked[0]
        return DouyinMediaSelection(
            rank=DouyinMediaRank.BIT_RATE,
            video_url=url,
            cover_url=cover,
            width=_optional_integer(entry.get("width")),
            height=_optional_integer(entry.get("height")),
            fidelity=_optional_integer(entry.get("bit_rate")),
        )
    for rank, key in (
        (DouyinMediaRank.PLAY_ADDR_H264, "play_addr_h264"),
        (DouyinMediaRank.PLAY_ADDR_256, "play_addr_256"),
        (DouyinMediaRank.PLAY_ADDR, "play_addr"),
    ):
        candidate = video.get(key)
        if candidate is None:
            continue
        urls = _urls(candidate, label=key)
        return DouyinMediaSelection(
            rank=rank,
            video_url=_preferred(urls),
            cover_url=cover,
            width=_optional_integer(candidate.get("width")) if isinstance(candidate, Mapping) else None,
            height=_optional_integer(candidate.get("height")) if isinstance(candidate, Mapping) else None,
        )
    return DouyinMediaSelection(video_url=None, cover_url=cover, rank=DouyinMediaRank.NONE)


def apply_douyin_media_selection(
    content_item: Mapping[str, object],
    selection: DouyinMediaSelection,
) -> Mapping[str, object]:
    """Return the flattened record with a strictly better declared stream.

    Only the ``bit_rate`` rank rewrites the persisted field: the fallback ranks
    mirror the pinned flattening rule, so leaving them untouched keeps every
    already-deliverable work byte-identical.
    """

    if selection.rank is not DouyinMediaRank.BIT_RATE or selection.video_url is None:
        return content_item
    return {**content_item, "video_download_url": selection.video_url}


@dataclass(frozen=True, slots=True)
class _PendingSelection:
    aweme_id: str
    selection: DouyinMediaSelection


_PENDING: ContextVar[_PendingSelection | None] = ContextVar("douyin_pending_media", default=None)
_INSTALL_MARKER = "__media_sync_dy_media_capture_v1__"
_INSTALL_VERSION = "media-sync-dy-media-v1"


def _module_belongs_to_checkout(module: object, checkout_root: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        return False
    try:
        return Path(module_file).resolve().is_relative_to(checkout_root.resolve())
    except OSError:
        return False


def install_douyin_media_capture(checkout_root: Path) -> None:
    """Install the pinned-store stream-selection shim once in this child process."""

    store_module = importlib.import_module("store.douyin")
    store_impl_module = importlib.import_module("store.douyin._store_impl")
    for module, label in ((store_module, "Douyin store"), (store_impl_module, "Douyin JSONL store")):
        if not _module_belongs_to_checkout(module, checkout_root):
            raise RuntimeError(f"{label} did not load from the verified checkout")

    update_aweme = getattr(store_module, "update_douyin_aweme", None)
    jsonl_class = getattr(store_impl_module, "DouyinJsonlStoreImplement", None)
    store_content = getattr(jsonl_class, "store_content", None)
    if not callable(update_aweme) or jsonl_class is None or not callable(store_content):
        raise RuntimeError("pinned Douyin media contract drifted")
    update_marker = getattr(update_aweme, _INSTALL_MARKER, None)
    store_marker = getattr(store_content, _INSTALL_MARKER, None)
    if update_marker == _INSTALL_VERSION and store_marker == _INSTALL_VERSION:
        return
    if update_marker is not None or store_marker is not None:
        raise RuntimeError("partial Douyin media shim installation")

    @wraps(update_aweme)
    async def update_with_selection(aweme_item: object) -> Any:
        pending: _PendingSelection | None = None
        if isinstance(aweme_item, Mapping):
            aweme_id = aweme_item.get("aweme_id")
            try:
                selection = select_douyin_media(aweme_item)
            except DouyinMediaSelectionError:
                selection = None
            if type(aweme_id) is str and aweme_id and selection is not None:
                pending = _PendingSelection(aweme_id, selection)
        token = _PENDING.set(pending)
        try:
            return await update_aweme(aweme_item)
        finally:
            _PENDING.reset(token)

    @wraps(store_content)
    async def store_with_selection(instance: object, content_item: object) -> Any:
        if not isinstance(content_item, Mapping):
            return await store_content(instance, content_item)
        if DOUYIN_MEDIA_RANK_FIELD in content_item:
            raise RuntimeError("private Douyin media field collision")
        pending = _PENDING.get()
        if pending is None or content_item.get("aweme_id") != pending.aweme_id:
            return await store_content(instance, content_item)
        selected = apply_douyin_media_selection(content_item, pending.selection)
        enriched = dict(selected)
        if pending.selection.has_video:
            enriched[DOUYIN_MEDIA_RANK_FIELD] = pending.selection.summary()
        return await store_content(instance, enriched)

    setattr(update_with_selection, _INSTALL_MARKER, _INSTALL_VERSION)
    setattr(store_with_selection, _INSTALL_MARKER, _INSTALL_VERSION)
    store_module.__dict__["update_douyin_aweme"] = update_with_selection
    jsonl_class.store_content = store_with_selection


__all__ = [
    "DOUYIN_MAX_BIT_RATE_ENTRIES",
    "DOUYIN_MEDIA_RANK_FIELD",
    "DouyinMediaRank",
    "DouyinMediaSelection",
    "DouyinMediaSelectionError",
    "apply_douyin_media_selection",
    "install_douyin_media_capture",
    "select_douyin_media",
    "validate_douyin_media_url",
]
