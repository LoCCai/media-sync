"""Stable Bilibili page identities retained across the pinned JSONL store.

MediaCrawler receives ``View.pages`` but its Bilibili store flattens an upload
without those identities.  This process-local shim captures only canonical
``page``/``cid`` pairs while ``update_bilibili_video`` is active and attaches
them to the matching JSONL row under a media-sync-owned private field.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any

BILIBILI_PAGES_FIELD = "__media_sync_bili_pages_v1"
BILIBILI_PROGRESSIVE_PAGE_FIELD = "__media_sync_bili_progressive_page_v2"
BILIBILI_PROGRESSIVE_BACKUPS_FIELD = "__media_sync_bili_progressive_backups_v1"
BILIBILI_PROGRESSIVE_FORMAT_FIELD = "__media_sync_bili_progressive_format_v1"
BILIBILI_DASH_PAGE_FIELD = "__media_sync_bili_dash_page_v1"
BILIBILI_MAX_PAGES = 64

_INSTALL_MARKER = "__media_sync_bilibili_media_capture_v1__"
_INSTALL_VERSION = "media-sync-bilibili-media-v1"
_MAX_ID = 2**63 - 1


@dataclass(frozen=True, slots=True)
class BilibiliPageIdentity:
    """One canonical, ordered page identity with no transient authority."""

    page: int
    cid: int

    def __post_init__(self) -> None:
        if type(self.page) is not int or self.page <= 0:
            raise ValueError("invalid Bilibili page number")
        if type(self.cid) is not int or not 1 <= self.cid <= _MAX_ID:
            raise ValueError("invalid Bilibili cid")

    def as_mapping(self) -> dict[str, int]:
        return {"page": self.page, "cid": self.cid}


@dataclass(frozen=True, slots=True)
class _CapturedPages:
    aid: str
    pages: tuple[BilibiliPageIdentity, ...]


_ACTIVE_PAGES: ContextVar[_CapturedPages | None] = ContextVar(
    "media_sync_bilibili_pages",
    default=None,
)


def is_bilibili_aid(value: object) -> bool:
    """Return whether *value* is one canonical positive decimal aid."""

    if type(value) is not str or not value.isascii() or not value.isdigit() or value.startswith("0"):
        return False
    try:
        return int(value) <= _MAX_ID
    except ValueError:
        return False


def _positive_id(value: object, *, label: str) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_ID:
        raise ValueError(f"invalid Bilibili {label}")
    return value


def parse_bilibili_view_pages(
    view: object,
    *,
    expected_aid: str | None = None,
) -> tuple[BilibiliPageIdentity, ...]:
    """Validate the bounded current page tuple from one ``View`` response."""

    if not isinstance(view, Mapping):
        raise ValueError("invalid Bilibili view")
    aid = _positive_id(view.get("aid"), label="aid")
    if expected_aid is not None and (not is_bilibili_aid(expected_aid) or str(aid) != expected_aid):
        raise ValueError("Bilibili aid mismatch")

    raw_pages = view.get("pages")
    if raw_pages in (None, []):
        return (BilibiliPageIdentity(page=1, cid=_positive_id(view.get("cid"), label="cid")),)
    if (
        not isinstance(raw_pages, Sequence)
        or isinstance(raw_pages, bytes | bytearray | str)
        or not 1 <= len(raw_pages) <= BILIBILI_MAX_PAGES
    ):
        raise ValueError("invalid Bilibili pages")

    pages: list[BilibiliPageIdentity] = []
    seen_cids: set[int] = set()
    for expected_page, item in enumerate(raw_pages, start=1):
        if not isinstance(item, Mapping):
            raise ValueError("invalid Bilibili page")
        page = _positive_id(item.get("page"), label="page")
        cid = _positive_id(item.get("cid"), label="cid")
        if page != expected_page or cid in seen_cids:
            raise ValueError("invalid Bilibili page order")
        seen_cids.add(cid)
        pages.append(BilibiliPageIdentity(page=page, cid=cid))
    return tuple(pages)


def parse_bilibili_page_payload(value: object) -> tuple[BilibiliPageIdentity, ...]:
    """Validate the exact private JSONL page payload after JSON freezing."""

    if (
        not isinstance(value, Sequence)
        or isinstance(value, bytes | bytearray | str)
        or not 1 <= len(value) <= BILIBILI_MAX_PAGES
    ):
        raise ValueError("invalid Bilibili page payload")
    pages: list[BilibiliPageIdentity] = []
    seen_cids: set[int] = set()
    for expected_page, item in enumerate(value, start=1):
        if not isinstance(item, Mapping) or set(item) != {"page", "cid"}:
            raise ValueError("invalid Bilibili page payload")
        identity = BilibiliPageIdentity(page=item["page"], cid=item["cid"])
        if identity.page != expected_page or identity.cid in seen_cids:
            raise ValueError("invalid Bilibili page payload")
        seen_cids.add(identity.cid)
        pages.append(identity)
    return tuple(pages)


def bilibili_video_remote_ids(aid: str, pages: Sequence[BilibiliPageIdentity]) -> tuple[str, ...]:
    """Return the compatible single-page or CID-bound multipart identities."""

    if not is_bilibili_aid(aid) or not 1 <= len(pages) <= BILIBILI_MAX_PAGES:
        raise ValueError("invalid Bilibili video identity")
    if len(pages) == 1:
        return (f"{aid}:video:0",)
    return tuple(f"{aid}:video:cid:{page.cid}" for page in pages)


def bilibili_video_cid(aid: str, remote_id: str) -> int | None:
    """Return a multipart CID, or ``None`` for the compatible single slot."""

    if not is_bilibili_aid(aid) or type(remote_id) is not str:
        raise ValueError("invalid Bilibili video identity")
    if remote_id == f"{aid}:video:0":
        return None
    prefix = f"{aid}:video:cid:"
    suffix = remote_id.removeprefix(prefix)
    if suffix == remote_id or not suffix.isascii() or not suffix.isdigit() or suffix.startswith("0"):
        raise ValueError("invalid Bilibili video identity")
    cid = int(suffix)
    if cid > _MAX_ID:
        raise ValueError("invalid Bilibili video identity")
    return cid


def _capture(video_item: object) -> _CapturedPages | None:
    if not isinstance(video_item, Mapping):
        return None
    view = video_item.get("View")
    if not isinstance(view, Mapping):
        return None
    raw_aid = view.get("aid")
    if type(raw_aid) is not int or not 1 <= raw_aid <= _MAX_ID:
        return None
    aid = str(raw_aid)
    try:
        pages = parse_bilibili_view_pages(view, expected_aid=aid)
    except ValueError:
        pages = ()
    return _CapturedPages(aid=aid, pages=pages)


def install_bilibili_media_capture(checkout_root: Path) -> None:
    """Install the pinned Bilibili store shim once in this child process."""

    store_module = importlib.import_module("store.bilibili")
    store_impl_module = importlib.import_module("store.bilibili._store_impl")
    for module, label in ((store_module, "Bilibili store"), (store_impl_module, "Bilibili JSONL store")):
        if not _module_belongs_to_checkout(module, checkout_root):
            raise RuntimeError(f"{label} did not load from the verified checkout")

    update_candidate = getattr(store_module, "update_bilibili_video", None)
    jsonl_store_candidate = getattr(store_module, "BiliJsonlStoreImplement", None)
    impl_jsonl_store = getattr(store_impl_module, "BiliJsonlStoreImplement", None)
    store_candidate = getattr(jsonl_store_candidate, "store_content", None)
    if (
        not callable(update_candidate)
        or jsonl_store_candidate is None
        or jsonl_store_candidate is not impl_jsonl_store
        or not callable(store_candidate)
    ):
        raise RuntimeError("pinned Bilibili media contract drifted")

    update_video = update_candidate
    jsonl_store: Any = jsonl_store_candidate
    store_content = store_candidate
    update_marker = getattr(update_video, _INSTALL_MARKER, None)
    store_marker = getattr(store_content, _INSTALL_MARKER, None)
    if update_marker == _INSTALL_VERSION and store_marker == _INSTALL_VERSION:
        return
    if update_marker is not None or store_marker is not None:
        raise RuntimeError("partial Bilibili media shim installation")

    @wraps(update_video)
    async def update_with_pages(video_item: object) -> Any:
        token = _ACTIVE_PAGES.set(_capture(video_item))
        try:
            return await update_video(video_item)
        finally:
            _ACTIVE_PAGES.reset(token)

    @wraps(store_content)
    async def store_with_pages(instance: object, content_item: object) -> Any:
        if not isinstance(content_item, Mapping):
            return await store_content(instance, content_item)
        if BILIBILI_PAGES_FIELD in content_item:
            raise RuntimeError("private Bilibili page field collision")
        capture = _ACTIVE_PAGES.get()
        if capture is None or content_item.get("video_id") != capture.aid:
            return await store_content(instance, content_item)
        enriched = dict(content_item)
        enriched[BILIBILI_PAGES_FIELD] = [page.as_mapping() for page in capture.pages]
        return await store_content(instance, enriched)

    setattr(update_with_pages, _INSTALL_MARKER, _INSTALL_VERSION)
    setattr(store_with_pages, _INSTALL_MARKER, _INSTALL_VERSION)
    store_module.__dict__["update_bilibili_video"] = update_with_pages
    jsonl_store.store_content = store_with_pages


def _module_belongs_to_checkout(module: object, checkout_root: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if type(module_file) is not str:
        return False
    try:
        return Path(module_file).resolve().is_relative_to(checkout_root.resolve())
    except OSError:
        return False


__all__ = [
    "BILIBILI_DASH_PAGE_FIELD",
    "BILIBILI_MAX_PAGES",
    "BILIBILI_PAGES_FIELD",
    "BILIBILI_PROGRESSIVE_BACKUPS_FIELD",
    "BILIBILI_PROGRESSIVE_FORMAT_FIELD",
    "BILIBILI_PROGRESSIVE_PAGE_FIELD",
    "BilibiliPageIdentity",
    "bilibili_video_cid",
    "bilibili_video_remote_ids",
    "install_bilibili_media_capture",
    "is_bilibili_aid",
    "parse_bilibili_page_payload",
    "parse_bilibili_view_pages",
]
