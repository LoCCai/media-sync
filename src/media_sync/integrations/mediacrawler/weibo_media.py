"""Task-local capture of image and video locators discarded by pinned MediaCrawler.

The locked Weibo store flattens a raw ``mblog`` before writing JSONL and does
not retain ``pics`` or ``page_info``.  This shim wraps that exact store
boundary: raw media are validated while ``update_weibo_note`` is active, then
copied into the matching JSONL content record under one media-sync-owned
private field.  A ContextVar keeps concurrently scheduled upstream note tasks
isolated.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

WEIBO_IMAGES_FIELD = "__media_sync_weibo_images_v1"
WEIBO_VIDEO_FIELD = "__media_sync_weibo_video_v1"

_INSTALL_MARKER = "__media_sync_weibo_media_capture_v1__"
_MAX_NOTE_ID = 2**63 - 1
_PID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z", re.ASCII)
_HOST = re.compile(
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z",
    re.ASCII,
)
_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]{0,254}\Z", re.ASCII)
_STATIC_IMAGE_EXTENSIONS = frozenset({".jpeg", ".jpg", ".png", ".webp"})
_VIDEO_HOSTS = frozenset({"sinaimg.cn", "f.video.weibocdn.com"})


@dataclass(frozen=True, slots=True)
class _CapturedImages:
    note_id: str
    images: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _CapturedVideo:
    note_id: str
    url: str


_ACTIVE_IMAGES: ContextVar[_CapturedImages | None] = ContextVar(
    "media_sync_weibo_images",
    default=None,
)

_ACTIVE_VIDEO: ContextVar[_CapturedVideo | None] = ContextVar(
    "media_sync_weibo_video",
    default=None,
)


def is_weibo_numeric_note_id(value: object) -> bool:
    """Return whether *value* is one canonical positive Weibo numeric ID."""

    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        return False
    if value.startswith("0"):
        return False
    try:
        return int(value) <= _MAX_NOTE_ID
    except ValueError:
        return False


def _is_static_image_filename(value: str) -> bool:
    if _FILENAME.fullmatch(value) is None or value in {".", ".."}:
        return False
    dot = value.rfind(".")
    return dot > 0 and value[dot:].lower() in _STATIC_IMAGE_EXTENSIONS


def _is_weibo_image_host(value: str) -> bool:
    return _HOST.fullmatch(value) is not None and (value == "sinaimg.cn" or value.endswith(".sinaimg.cn"))


def is_weibo_proxy_image_url(value: object) -> bool:
    """Return whether *value* is one canonical query-free shim locator."""

    if not isinstance(value, str) or len(value) > 2_048:
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or parsed.netloc != "i1.wp.com"
        or parsed.hostname != "i1.wp.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
    ):
        return False
    segments = parsed.path.split("/")
    return (
        len(segments) == 4
        and not segments[0]
        and _is_weibo_image_host(segments[1])
        and segments[2] == "large"
        and _is_static_image_filename(segments[3])
    )


def _proxy_image_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 2_048:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or parsed.hostname is None
    ):
        return None
    host = parsed.hostname
    if parsed.netloc != host or not _is_weibo_image_host(host):
        return None
    segments = parsed.path.split("/")
    if len(segments) != 3 or segments[0] or not segments[1]:
        return None
    filename = segments[2]
    if not _is_static_image_filename(filename):
        return None
    return f"https://i1.wp.com/{host}/large/{filename}"


def _is_weibo_video_host(value: str) -> bool:
    if value == "f.video.weibocdn.com":
        return True
    return value == "sinaimg.cn" or value.endswith(".sinaimg.cn")


def validate_weibo_video_url(value: object) -> str:
    """Validate one canonical signed Weibo stream URL without rewriting it."""

    if not isinstance(value, str) or len(value) > 4_096 or value != value.strip():
        raise ValueError("invalid Weibo video URL")
    if "\\" in value or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError("invalid Weibo video URL")
    if any(character.isspace() for character in value):
        raise ValueError("invalid Weibo video URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        host = parsed.hostname
    except ValueError as exc:
        raise ValueError("invalid Weibo video URL") from exc
    if (
        parsed.scheme != "https"
        or host is None
        or not _is_weibo_video_host(host)
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.fragment
    ):
        raise ValueError("invalid Weibo video URL")
    segments = parsed.path.split("/")
    if len(segments) < 3 or any(not segment for segment in segments[1:]):
        raise ValueError("invalid Weibo video URL")
    filename = segments[-1]
    if _FILENAME.fullmatch(filename) is None or not filename.lower().endswith(".mp4"):
        raise ValueError("invalid Weibo video URL")
    return value


_WEIBO_PLAYBACK_QUALITY_ORDER = ("1080p", "720p", "540p", "480p", "360p")
_WEIBO_MAX_PLAYBACK_ENTRIES = 8


def _select_playback_list_url(media_info: Mapping[str, object]) -> str | None:
    playback_list = media_info.get("playback_list")
    if (
        not isinstance(playback_list, list)
        or not 1 <= len(playback_list) <= _WEIBO_MAX_PLAYBACK_ENTRIES
        or any(not isinstance(entry, Mapping) for entry in playback_list)
    ):
        return None
    best_rank: int | None = None
    best_url: str | None = None
    for entry in playback_list:
        play_info = entry.get("play_info")
        if not isinstance(play_info, Mapping):
            continue
        quality = play_info.get("quality")
        if type(quality) is not str or quality not in _WEIBO_PLAYBACK_QUALITY_ORDER:
            continue
        rank = _WEIBO_PLAYBACK_QUALITY_ORDER.index(quality)
        try:
            url = validate_weibo_video_url(play_info.get("url"))
        except ValueError:
            continue
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best_url = url
    return best_url


def _capture_video(note_item: object) -> _CapturedVideo | None:
    if not isinstance(note_item, Mapping):
        return None
    mblog = note_item.get("mblog")
    if not isinstance(mblog, Mapping):
        return None
    note_id = mblog.get("id")
    if not is_weibo_numeric_note_id(note_id):
        return None
    assert isinstance(note_id, str)
    if mblog.get("retweeted_status") is not None:
        return None
    page_info = mblog.get("page_info")
    if not isinstance(page_info, Mapping) or page_info.get("page_type") != "video":
        return None
    media_info = page_info.get("media_info")
    if not isinstance(media_info, Mapping):
        return None
    selected: str | None
    try:
        selected = validate_weibo_video_url(media_info.get("stream_url"))
    except ValueError:
        selected = _select_playback_list_url(media_info)
    if selected is None:
        return None
    return _CapturedVideo(note_id=note_id, url=selected)


def _capture_images(note_item: object) -> _CapturedImages | None:
    if not isinstance(note_item, Mapping):
        return None
    mblog = note_item.get("mblog")
    if not isinstance(mblog, Mapping):
        return None
    note_id = mblog.get("id")
    if not is_weibo_numeric_note_id(note_id):
        return None
    assert isinstance(note_id, str)
    if mblog.get("retweeted_status") is not None:
        return None
    page_info = mblog.get("page_info")
    if page_info not in (None, {}):
        return None
    pics = mblog.get("pics")
    if not isinstance(pics, list) or not pics:
        return None

    captured: list[tuple[str, str]] = []
    pids: set[str] = set()
    urls: set[str] = set()
    for pic in pics:
        if not isinstance(pic, Mapping):
            return None
        pid = pic.get("pid")
        url = _proxy_image_url(pic.get("url"))
        if not isinstance(pid, str) or _PID.fullmatch(pid) is None or url is None:
            return None
        if pid in pids or url in urls:
            return None
        pids.add(pid)
        urls.add(url)
        captured.append((pid, url))
    return _CapturedImages(note_id=note_id, images=tuple(captured))


def install_weibo_media_capture(checkout_root: Path) -> None:
    """Install the pinned-store shim once in the current child process."""

    weibo_store = importlib.import_module("store.weibo")
    module_file = getattr(weibo_store, "__file__", None)
    try:
        belongs_to_checkout = isinstance(module_file, str) and Path(module_file).resolve().is_relative_to(
            checkout_root.resolve()
        )
    except OSError:
        belongs_to_checkout = False
    if not belongs_to_checkout:
        raise RuntimeError("Weibo store did not load from the verified checkout")
    update_note = getattr(weibo_store, "update_weibo_note", None)
    jsonl_store = getattr(weibo_store, "WeiboJsonlStoreImplement", None)
    store_content = getattr(jsonl_store, "store_content", None)
    if not callable(update_note) or jsonl_store is None or not callable(store_content):
        raise RuntimeError("pinned Weibo store contract drifted")
    if getattr(update_note, _INSTALL_MARKER, False) and getattr(store_content, _INSTALL_MARKER, False):
        return
    if getattr(update_note, _INSTALL_MARKER, False) or getattr(store_content, _INSTALL_MARKER, False):
        raise RuntimeError("partial Weibo media shim installation")

    @wraps(update_note)
    async def update_with_images(note_item: object) -> Any:
        images_token = _ACTIVE_IMAGES.set(_capture_images(note_item))
        video_token = _ACTIVE_VIDEO.set(_capture_video(note_item))
        try:
            return await update_note(note_item)
        finally:
            _ACTIVE_VIDEO.reset(video_token)
            _ACTIVE_IMAGES.reset(images_token)

    @wraps(store_content)
    async def store_with_images(instance: object, content_item: object) -> Any:
        if not isinstance(content_item, Mapping):
            return await store_content(instance, content_item)
        if WEIBO_IMAGES_FIELD in content_item or WEIBO_VIDEO_FIELD in content_item:
            raise RuntimeError("private Weibo media field collision")
        enriched = dict(content_item)
        captured_images = _ACTIVE_IMAGES.get()
        if captured_images is not None and enriched.get("note_id") == captured_images.note_id:
            enriched[WEIBO_IMAGES_FIELD] = [{"pid": pid, "url": url} for pid, url in captured_images.images]
        captured_video = _ACTIVE_VIDEO.get()
        if captured_video is not None and enriched.get("note_id") == captured_video.note_id:
            enriched[WEIBO_VIDEO_FIELD] = {"url": captured_video.url}
        return await store_content(instance, enriched)

    setattr(update_with_images, _INSTALL_MARKER, True)
    setattr(store_with_images, _INSTALL_MARKER, True)
    weibo_store.__dict__["update_weibo_note"] = update_with_images
    jsonl_store.store_content = store_with_images


__all__ = [
    "WEIBO_IMAGES_FIELD",
    "WEIBO_VIDEO_FIELD",
    "install_weibo_media_capture",
    "is_weibo_numeric_note_id",
    "is_weibo_proxy_image_url",
    "validate_weibo_video_url",
]
