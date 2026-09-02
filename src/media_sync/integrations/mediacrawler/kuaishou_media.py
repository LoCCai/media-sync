"""Task-local capture of atlas image locators discarded by pinned MediaCrawler.

The locked Kuaishou store flattens ``video_item.photo`` before writing JSONL
and does not retain ``ext_params``.  This shim wraps that exact store boundary:
the frozen ``atlas.pics[].cdn`` shape is validated while
``update_kuaishou_video`` is active, then copied into the matching JSONL
content record under one media-sync-owned private field.  A ContextVar keeps
concurrently scheduled upstream photo tasks isolated.
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

KS_GALLERY_FIELD = "__media_sync_ks_atlas_images_v1"

_INSTALL_MARKER = "__media_sync_ks_media_capture_v1__"
_INSTALL_VERSION = "media-sync-ks-media-v1"
KS_MAX_GALLERY_IMAGES = 64
_MAX_URL_CHARS = 4_096
_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z", re.ASCII)
_STATIC_IMAGE_EXTENSIONS = frozenset({".jpeg", ".jpg", ".png", ".webp"})


@dataclass(frozen=True, slots=True)
class _CapturedAtlas:
    video_id: str
    image_urls: tuple[str, ...]


_ACTIVE_ATLAS: ContextVar[_CapturedAtlas | None] = ContextVar(
    "media_sync_ks_atlas",
    default=None,
)


def _is_dns_hostname(value: str) -> bool:
    if not value.isascii() or len(value) > 253:
        return False
    labels = value.split(".")
    return all(_DNS_LABEL.fullmatch(label) is not None for label in labels)


def validate_ks_image_url(value: object) -> str:
    """Return one bounded Kuaishou atlas CDN image URL or raise ``ValueError``."""

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
        raise ValueError("invalid Kuaishou atlas image URL")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Kuaishou atlas image URL") from exc
    if (
        parsed.scheme.lower() != "https"
        or hostname is None
        or not _is_dns_hostname(hostname)
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.fragment
        or ("?" in value and not parsed.query)
        or parsed.path in {"", "/"}
    ):
        raise ValueError("invalid Kuaishou atlas image URL")
    filename = parsed.path.rsplit("/", 1)[-1]
    dot = filename.rfind(".")
    if dot <= 0 or filename[dot:].lower() not in _STATIC_IMAGE_EXTENSIONS:
        raise ValueError("invalid Kuaishou atlas image URL")
    return value


def _capture_atlas(video_item: object) -> _CapturedAtlas | None:
    if not isinstance(video_item, Mapping):
        return None
    photo = video_item.get("photo")
    if not isinstance(photo, Mapping):
        return None
    video_id = photo.get("id")
    if type(video_id) is not str or not video_id or video_id != video_id.strip():
        return None
    ext_params = photo.get("ext_params")
    if not isinstance(ext_params, Mapping):
        return None
    atlas = ext_params.get("atlas")
    if not isinstance(atlas, Mapping):
        return None
    pics = atlas.get("pics")
    if (
        not isinstance(pics, list)
        or not 1 <= len(pics) <= KS_MAX_GALLERY_IMAGES
        or any(not isinstance(pic, Mapping) for pic in pics)
    ):
        return None
    urls: list[str] = []
    for pic in pics:
        try:
            urls.append(validate_ks_image_url(pic.get("cdn")))
        except ValueError:
            return None
    if len(set(urls)) != len(urls):
        return None
    return _CapturedAtlas(video_id=video_id, image_urls=tuple(urls))


def install_kuaishou_media_capture(checkout_root: Path) -> None:
    """Install the pinned-store atlas shim once in the current child process."""

    store_module = importlib.import_module("store.kuaishou")
    store_impl_module = importlib.import_module("store.kuaishou._store_impl")
    for module, label in ((store_module, "Kuaishou store"), (store_impl_module, "Kuaishou JSONL store")):
        if not _module_belongs_to_checkout(module, checkout_root):
            raise RuntimeError(f"{label} did not load from the verified checkout")

    update_candidate = getattr(store_module, "update_kuaishou_video", None)
    jsonl_store_candidate = getattr(store_module, "KuaishouJsonlStoreImplement", None)
    impl_jsonl_store = getattr(store_impl_module, "KuaishouJsonlStoreImplement", None)
    store_content = getattr(jsonl_store_candidate, "store_content", None)
    if (
        not callable(update_candidate)
        or jsonl_store_candidate is None
        or jsonl_store_candidate is not impl_jsonl_store
        or not callable(store_content)
    ):
        raise RuntimeError("pinned Kuaishou media contract drifted")

    update_video = update_candidate
    jsonl_store: Any = jsonl_store_candidate
    update_marker = getattr(update_video, _INSTALL_MARKER, None)
    store_marker = getattr(store_content, _INSTALL_MARKER, None)
    if update_marker == _INSTALL_VERSION and store_marker == _INSTALL_VERSION:
        return
    if update_marker is not None or store_marker is not None:
        raise RuntimeError("partial Kuaishou media shim installation")

    @wraps(update_video)
    async def update_with_atlas(video_item: object) -> Any:
        token = _ACTIVE_ATLAS.set(_capture_atlas(video_item))
        try:
            return await update_video(video_item)
        finally:
            _ACTIVE_ATLAS.reset(token)

    @wraps(store_content)
    async def store_with_atlas(instance: object, content_item: object) -> Any:
        if not isinstance(content_item, Mapping):
            return await store_content(instance, content_item)
        if KS_GALLERY_FIELD in content_item:
            raise RuntimeError("private Kuaishou media field collision")
        captured = _ACTIVE_ATLAS.get()
        if captured is None or content_item.get("video_id") != captured.video_id:
            return await store_content(instance, content_item)
        enriched = dict(content_item)
        enriched[KS_GALLERY_FIELD] = list(captured.image_urls)
        return await store_content(instance, enriched)

    setattr(update_with_atlas, _INSTALL_MARKER, _INSTALL_VERSION)
    setattr(store_with_atlas, _INSTALL_MARKER, _INSTALL_VERSION)
    store_module.__dict__["update_kuaishou_video"] = update_with_atlas
    jsonl_store.store_content = store_with_atlas


def _module_belongs_to_checkout(module: object, checkout_root: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        return False
    try:
        return Path(module_file).resolve().is_relative_to(checkout_root.resolve())
    except OSError:
        return False


__all__ = [
    "KS_GALLERY_FIELD",
    "KS_MAX_GALLERY_IMAGES",
    "install_kuaishou_media_capture",
    "validate_ks_image_url",
]
