"""Task-local capture of live-photo streams discarded by pinned MediaCrawler.

The locked XHS store flattens ``image_list`` into a comma-join of image URLs
and does not retain the nested ``live_photo`` streams.  This shim wraps the
``update_xhs_note`` boundary: the frozen ``live_photo.stream.h264[0].master_url``
shape is validated while the store call is active, then copied into the
matching JSONL content record under one media-sync-owned private field.  A
ContextVar keeps concurrently scheduled upstream note tasks isolated.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any

from media_sync.integrations.mediacrawler.xhs_media import validate_xhs_video_url

XHS_LIVE_VIDEO_FIELD = "__media_sync_xhs_live_video_v1"

_INSTALL_MARKER = "__media_sync_xhs_live_capture_v1__"
_INSTALL_VERSION = "media-sync-xhs-live-v1"


@dataclass(frozen=True, slots=True)
class _CapturedLive:
    note_id: str
    live_url: str


_ACTIVE_LIVE: ContextVar[_CapturedLive | None] = ContextVar(
    "media_sync_xhs_live",
    default=None,
)


def _capture_live(note_item: object) -> _CapturedLive | None:
    if not isinstance(note_item, Mapping) or note_item.get("type") != "normal":
        return None
    note_id = note_item.get("note_id")
    if type(note_id) is not str or not note_id or note_id != note_id.strip():
        return None
    image_list = note_item.get("image_list")
    if not isinstance(image_list, list) or len(image_list) != 1:
        return None
    image = image_list[0]
    if not isinstance(image, Mapping):
        return None
    live_photo = image.get("live_photo")
    if not isinstance(live_photo, Mapping):
        return None
    stream = live_photo.get("stream")
    if not isinstance(stream, Mapping):
        return None
    h264 = stream.get("h264")
    if not isinstance(h264, list) or not h264 or any(not isinstance(entry, Mapping) for entry in h264):
        return None
    master_url = h264[0].get("master_url")
    try:
        live_url = validate_xhs_video_url(master_url)
    except ValueError:
        return None
    return _CapturedLive(note_id=note_id, live_url=live_url)


def install_xhs_live_capture(checkout_root: Path) -> None:
    """Install the pinned-store live-photo shim once in this child process."""

    store_module = importlib.import_module("store.xhs")
    store_impl_module = importlib.import_module("store.xhs._store_impl")
    for module, label in ((store_module, "XHS store"), (store_impl_module, "XHS JSONL store")):
        if not _module_belongs_to_checkout(module, checkout_root):
            raise RuntimeError(f"{label} did not load from the verified checkout")

    update_candidate = getattr(store_module, "update_xhs_note", None)
    jsonl_store_candidate = getattr(store_module, "XhsJsonlStoreImplement", None)
    impl_jsonl_store = getattr(store_impl_module, "XhsJsonlStoreImplement", None)
    store_content = getattr(jsonl_store_candidate, "store_content", None)
    if (
        not callable(update_candidate)
        or jsonl_store_candidate is None
        or jsonl_store_candidate is not impl_jsonl_store
        or not callable(store_content)
    ):
        raise RuntimeError("pinned XHS live media contract drifted")

    update_note = update_candidate
    jsonl_store: Any = jsonl_store_candidate
    update_marker = getattr(update_note, _INSTALL_MARKER, None)
    store_marker = getattr(store_content, _INSTALL_MARKER, None)
    if update_marker == _INSTALL_VERSION and store_marker == _INSTALL_VERSION:
        return
    if update_marker is not None or store_marker is not None:
        raise RuntimeError("partial XHS live media shim installation")

    @wraps(update_note)
    async def update_with_live(note_item: object) -> Any:
        token = _ACTIVE_LIVE.set(_capture_live(note_item))
        try:
            return await update_note(note_item)
        finally:
            _ACTIVE_LIVE.reset(token)

    @wraps(store_content)
    async def store_with_live(instance: object, content_item: object) -> Any:
        if not isinstance(content_item, Mapping):
            return await store_content(instance, content_item)
        if XHS_LIVE_VIDEO_FIELD in content_item:
            raise RuntimeError("private XHS live media field collision")
        captured = _ACTIVE_LIVE.get()
        if captured is None or content_item.get("note_id") != captured.note_id:
            return await store_content(instance, content_item)
        enriched = dict(content_item)
        enriched[XHS_LIVE_VIDEO_FIELD] = {"url": captured.live_url}
        return await store_content(instance, enriched)

    setattr(update_with_live, _INSTALL_MARKER, _INSTALL_VERSION)
    setattr(store_with_live, _INSTALL_MARKER, _INSTALL_VERSION)
    store_module.__dict__["update_xhs_note"] = update_with_live
    jsonl_store.store_content = store_with_live


def _module_belongs_to_checkout(module: object, checkout_root: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        return False
    try:
        return Path(module_file).resolve().is_relative_to(checkout_root.resolve())
    except OSError:
        return False


__all__ = [
    "XHS_LIVE_VIDEO_FIELD",
    "install_xhs_live_capture",
]
