"""Verified capture of one or two static first-floor images from pinned Tieba detail.

The pinned MediaCrawler detail API receives structured ``first_floor.content``
items and then reduces them to text before ``TiebaNote`` reaches JSONL.  This
integration-owned shim captures one narrowly frozen type-3 image or one exact
ordered pair, binds the capture to the exact returned model across the upstream
gather-child/parent-store boundary, and exposes it only to the matching nested
JSONL store call.
"""

from __future__ import annotations

import asyncio
import importlib
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

TIEBA_IMAGE_FIELD = "__media_sync_tieba_first_floor_image_v1"
TIEBA_IMAGES_FIELD = "__media_sync_tieba_first_floor_images_v2"

_INSTALL_MARKER = "__media_sync_tieba_media_capture_v1__"
_CREATOR_CAP_MARKER = "__media_sync_tieba_creator_cap_v1__"
_OBJECT_CAPTURE_FIELD = "__media_sync_tieba_first_floor_image_capture_v1__"
_INSTALL_VERSION = "media-sync-tieba-media-v1"
_MAX_ID = 2**63 - 1
_MAX_URL_CHARS = 4_096
_MAX_QUERY_VALUE_CHARS = 256
_MAX_FIRST_FLOOR_ITEMS = 512
_MAX_IMAGE_BYTES = 2**31 - 1
_MAX_DIMENSION = 100_000
_ORIGIN_PATH = re.compile(
    r"/forum/pic/item/(?P<identity>[0-9a-f]{40})\.(?P<extension>jpe?g|png|webp)\Z",
    re.ASCII,
)
_AUXILIARY_PATH = re.compile(
    r"/forum/.*/(?P<identity>[0-9a-f]{40})\.(?P<extension>jpe?g|png|webp)\Z",
    re.ASCII,
)
_QUERY_VALUE = re.compile(r"[A-Za-z0-9._~-]+\Z", re.ASCII)
_DIMENSIONS = re.compile(r"(?P<width>[1-9][0-9]{0,5}),(?P<height>[1-9][0-9]{0,5})\Z", re.ASCII)
_IMAGE_ITEM_KEYS = frozenset(
    {
        "type",
        "origin_src",
        "cdn_src",
        "big_cdn_src",
        "cdn_src_active",
        "pic_id",
        "bsize",
        "origin_size",
        "is_long_pic",
        "show_original_btn",
    }
)


@dataclass(frozen=True, slots=True)
class _RawCapture:
    note_id: str
    image_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _BoundCapture:
    content_object: object
    note_id: str
    canonical_url: str
    image_urls: tuple[str, ...]


_ACTIVE_CAPTURE: ContextVar[_BoundCapture | None] = ContextVar(
    "media_sync_tieba_active_first_floor_image",
    default=None,
)


def is_tieba_positive_id(value: object) -> bool:
    """Return whether *value* is one canonical positive Tieba numeric ID."""

    if type(value) is not str or not value.isascii() or not value.isdigit() or value.startswith("0"):
        return False
    try:
        return int(value) <= _MAX_ID
    except ValueError:
        return False


def validate_tieba_thread_url(value: str, *, note_id: str | None = None) -> str:
    """Return one exact canonical Tieba thread URL or raise ``ValueError``."""

    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_URL_CHARS
        or "\\" in value
        or "?" in value
        or "#" in value
        or any(character.isspace() for character in value)
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        or (note_id is not None and not is_tieba_positive_id(note_id))
    ):
        raise ValueError("invalid Tieba thread URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Tieba thread URL") from exc
    segments = parsed.path.split("/")
    if (
        parsed.scheme != "https"
        or parsed.netloc != "tieba.baidu.com"
        or parsed.hostname != "tieba.baidu.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or len(segments) != 3
        or segments[:2] != ["", "p"]
        or not is_tieba_positive_id(segments[2])
        or (note_id is not None and segments[2] != note_id)
    ):
        raise ValueError("invalid Tieba thread URL")
    return value


def validate_tieba_image_url(value: str) -> str:
    """Return one current signed Tieba origin-image locator unchanged."""

    parsed = _validated_image_base(value, require_query=True)
    if _ORIGIN_PATH.fullmatch(parsed.path) is None:
        raise ValueError("invalid Tieba image URL")
    return value


def validate_tieba_image_source_hint(value: str) -> str:
    """Return one canonical query-free Tieba origin-image identity."""

    parsed = _validated_image_base(value, require_query=False)
    if _ORIGIN_PATH.fullmatch(parsed.path) is None:
        raise ValueError("invalid Tieba image source hint")
    return value


def tieba_image_source_hint(value: str) -> str:
    """Derive the only durable scheme/authority/path identity from a signed URL."""

    validated = validate_tieba_image_url(value)
    parsed = urlsplit(validated)
    return validate_tieba_image_source_hint(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")))


def install_tieba_media_capture(
    checkout_root: Path,
    *,
    creator_max_items: int | None = None,
) -> None:
    """Install the pinned Tieba capture and optional creator cap once."""

    _validate_creator_cap(creator_max_items)
    extractor_module = importlib.import_module("media_platform.tieba.help")
    client_module = importlib.import_module("media_platform.tieba.client")
    store_module = importlib.import_module("store.tieba")
    store_impl_module = importlib.import_module("store.tieba._store_impl")
    for module, label in (
        (extractor_module, "Tieba extractor"),
        (client_module, "Tieba client"),
        (store_module, "Tieba store"),
        (store_impl_module, "Tieba JSONL store"),
    ):
        if not _module_belongs_to_checkout(module, checkout_root):
            raise RuntimeError(f"{label} did not load from the verified checkout")

    extractor_class_candidate = getattr(extractor_module, "TieBaExtractor", None)
    client_class_candidate = getattr(client_module, "BaiduTieBaClient", None)
    jsonl_store_candidate = getattr(store_module, "TieBaJsonlStoreImplement", None)
    impl_jsonl_store = getattr(store_impl_module, "TieBaJsonlStoreImplement", None)
    if jsonl_store_candidate is None or jsonl_store_candidate is not impl_jsonl_store:
        raise RuntimeError("pinned Tieba JSONL store export drifted")
    extract_candidate = getattr(extractor_class_candidate, "extract_note_detail_from_api", None)
    get_creator_candidate = getattr(client_class_candidate, "get_all_notes_by_creator_url", None)
    update_candidate = getattr(store_module, "update_tieba_note", None)
    store_candidate = getattr(jsonl_store_candidate, "store_content", None)
    if not all(
        callable(target) for target in (extract_candidate, get_creator_candidate, update_candidate, store_candidate)
    ):
        raise RuntimeError("pinned Tieba media contract drifted")

    extractor_class: Any = extractor_class_candidate
    client_class: Any = client_class_candidate
    jsonl_store: Any = jsonl_store_candidate
    extract_detail = cast(Callable[..., Any], extract_candidate)
    get_creator_notes = cast(Callable[..., Any], get_creator_candidate)
    update_note = cast(Callable[..., Any], update_candidate)
    store_content = cast(Callable[..., Any], store_candidate)

    capture_targets = (extract_detail, update_note, store_content)
    capture_markers = tuple(getattr(target, _INSTALL_MARKER, None) for target in capture_targets)
    creator_marker = getattr(get_creator_notes, _INSTALL_MARKER, None)
    if any(marker is not None and marker != _INSTALL_VERSION for marker in (*capture_markers, creator_marker)):
        raise RuntimeError("Tieba media shim marker collision")
    if any(marker == _INSTALL_VERSION for marker in capture_markers):
        if not all(marker == _INSTALL_VERSION for marker in capture_markers):
            raise RuntimeError("partial Tieba media shim installation")
        if creator_max_items is not None:
            if creator_marker != _INSTALL_VERSION:
                raise RuntimeError("partial Tieba creator cap installation")
            if getattr(get_creator_notes, _CREATOR_CAP_MARKER, None) != creator_max_items:
                raise RuntimeError("Tieba creator cap collision")
        return
    if creator_marker == _INSTALL_VERSION:
        raise RuntimeError("partial Tieba media shim installation")

    @wraps(extract_detail)
    def extract_with_image(instance: object, api_data: object) -> Any:
        result = extract_detail(instance, api_data)
        raw_capture = _capture_first_floor(api_data)
        if raw_capture is None or not _matches_extracted_result(result, raw_capture):
            return result
        canonical_url = getattr(result, "note_url", None)
        assert isinstance(canonical_url, str)
        capture = _BoundCapture(
            content_object=result,
            note_id=raw_capture.note_id,
            canonical_url=canonical_url,
            image_urls=raw_capture.image_urls,
        )
        sentinel = object()
        if getattr(result, _OBJECT_CAPTURE_FIELD, sentinel) is not sentinel:
            raise RuntimeError("private Tieba object capture collision")
        try:
            object.__setattr__(result, _OBJECT_CAPTURE_FIELD, capture)
        except (AttributeError, TypeError) as exc:
            raise RuntimeError("pinned Tieba note object cannot carry media capture") from exc
        return result

    @wraps(update_note)
    async def update_with_image(note_item: object) -> Any:
        attached = getattr(note_item, _OBJECT_CAPTURE_FIELD, None)
        capture: _BoundCapture | None = None
        if attached is not None:
            if not isinstance(attached, _BoundCapture) or attached.content_object is not note_item:
                raise RuntimeError("private Tieba object capture collision")
            try:
                object.__delattr__(note_item, _OBJECT_CAPTURE_FIELD)
            except (AttributeError, TypeError) as exc:
                raise RuntimeError("private Tieba object capture could not be consumed") from exc
            if _matches_bound_object(attached, note_item):
                capture = attached
        token = _ACTIVE_CAPTURE.set(capture)
        try:
            return await update_note(note_item)
        finally:
            _ACTIVE_CAPTURE.reset(token)

    @wraps(store_content)
    async def store_with_image(instance: object, content_item: object) -> Any:
        if not isinstance(content_item, Mapping):
            return await store_content(instance, content_item)
        if _contains_private_field(content_item):
            raise RuntimeError("private Tieba media field collision")
        capture = _ACTIVE_CAPTURE.get()
        if capture is None or not _matches_stored_row(capture, content_item):
            return await store_content(instance, content_item)
        enriched = dict(content_item)
        if len(capture.image_urls) == 1:
            enriched[TIEBA_IMAGE_FIELD] = capture.image_urls[0]
        else:
            enriched[TIEBA_IMAGES_FIELD] = list(capture.image_urls)
        return await store_content(instance, enriched)

    setattr(extract_with_image, _INSTALL_MARKER, _INSTALL_VERSION)
    setattr(update_with_image, _INSTALL_MARKER, _INSTALL_VERSION)
    setattr(store_with_image, _INSTALL_MARKER, _INSTALL_VERSION)

    bounded_creator: Any = None
    if creator_max_items is not None:

        @wraps(get_creator_notes)
        async def get_bounded_creator_notes(
            instance: object,
            creator_url: str,
            crawl_interval: float = 1.0,
            callback: Any = None,
            max_note_count: int = 0,
        ) -> list[Any]:
            if type(max_note_count) is not int or max_note_count != creator_max_items:
                raise RuntimeError("Tieba creator cap mismatch")
            portrait_method = getattr(instance, "_extract_creator_portrait", None)
            if not callable(portrait_method):
                raise RuntimeError("pinned Tieba creator portrait contract drifted")
            portrait = portrait_method(creator_url)
            if type(portrait) is not str or not portrait or portrait != portrait.strip():
                raise RuntimeError("invalid Tieba creator authority")

            result: list[Any] = []
            seen_thread_ids: set[str] = set()
            page_number = 1
            page_size = 20
            while len(result) < creator_max_items:
                response = await instance.get_notes_by_creator_portrait(  # type: ignore[attr-defined]
                    portrait=portrait,
                    page_number=page_number,
                    page_size=page_size,
                )
                thread_ids, has_more = _validate_creator_page(
                    response,
                    page_size=page_size,
                    seen_thread_ids=seen_thread_ids,
                )
                remaining = creator_max_items - len(result)
                selected_ids = thread_ids[:remaining]
                detail_method = getattr(instance, "get_note_by_id", None)
                if not callable(detail_method):
                    raise RuntimeError("pinned Tieba creator detail contract drifted")
                get_note_by_id = cast(Callable[[str], Awaitable[Any]], detail_method)
                notes = await asyncio.gather(*(get_note_by_id(thread_id) for thread_id in selected_ids))
                if len(notes) != len(selected_ids) or any(
                    not _matches_creator_note(note, thread_id)
                    for note, thread_id in zip(notes, selected_ids, strict=True)
                ):
                    raise RuntimeError("pinned Tieba creator detail contract drifted")
                if callback is not None and notes:
                    await callback(notes)
                result.extend(notes)
                seen_thread_ids.update(thread_ids)
                if len(result) >= creator_max_items or not has_more:
                    break
                await asyncio.sleep(crawl_interval)
                page_number += 1
            return result

        setattr(get_bounded_creator_notes, _INSTALL_MARKER, _INSTALL_VERSION)
        setattr(get_bounded_creator_notes, _CREATOR_CAP_MARKER, creator_max_items)
        bounded_creator = get_bounded_creator_notes

    assigned: list[tuple[object, str, Any]] = []
    try:
        assigned.append((extractor_class, "extract_note_detail_from_api", extract_detail))
        extractor_class.extract_note_detail_from_api = extract_with_image
        assigned.append((store_module, "update_tieba_note", update_note))
        store_module.__dict__["update_tieba_note"] = update_with_image
        assigned.append((jsonl_store, "store_content", store_content))
        jsonl_store.store_content = store_with_image
        if bounded_creator is not None:
            assigned.append((client_class, "get_all_notes_by_creator_url", get_creator_notes))
            client_class.get_all_notes_by_creator_url = bounded_creator
    except Exception:
        for owner, attribute, original in reversed(assigned):
            setattr(owner, attribute, original)
        raise


def _validated_image_base(value: str, *, require_query: bool) -> Any:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_URL_CHARS
        or "\\" in value
        or "#" in value
        or any(character.isspace() for character in value)
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise ValueError("invalid Tieba image URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Tieba image URL") from exc
    if (
        parsed.scheme != "https"
        or parsed.netloc != "tiebapic.baidu.com"
        or parsed.hostname != "tiebapic.baidu.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path in {"", "/"}
        or parsed.fragment
    ):
        raise ValueError("invalid Tieba image URL")
    if require_query:
        if parsed.query.count("=") != 1 or "&" in parsed.query or ";" in parsed.query:
            raise ValueError("invalid Tieba image URL")
        name, value_part = parsed.query.split("=", 1)
        if (
            name != "tbpicau"
            or not 1 <= len(value_part) <= _MAX_QUERY_VALUE_CHARS
            or _QUERY_VALUE.fullmatch(value_part) is None
        ):
            raise ValueError("invalid Tieba image URL")
    elif "?" in value or parsed.query:
        raise ValueError("invalid Tieba image source hint")
    return parsed


def _capture_first_floor(api_data: object) -> _RawCapture | None:
    if not isinstance(api_data, Mapping):
        return None
    note_id = _consistent_note_id(api_data)
    first_floor = api_data.get("first_floor")
    content = first_floor.get("content") if isinstance(first_floor, Mapping) else None
    if note_id is None or type(content) is not list or not 1 <= len(content) <= _MAX_FIRST_FLOOR_ITEMS:
        return None

    image_items: list[Mapping[str, object]] = []
    text_count = 0
    for item in content:
        if not isinstance(item, Mapping) or type(item.get("type")) is not int:
            return None
        item_type = item.get("type")
        if item_type == 0:
            if not _valid_text_item(item):
                return None
            text_count += 1
        elif item_type == 3:
            if len(image_items) == 2:
                return None
            image_items.append(cast(Mapping[str, object], item))
        else:
            return None
    if text_count == 0 or not image_items:
        return None
    try:
        image_urls = tuple(_validate_image_item(item) for item in image_items)
        source_hints = tuple(tieba_image_source_hint(url) for url in image_urls)
    except ValueError:
        return None
    if len(set(source_hints)) != len(source_hints):
        return None
    return _RawCapture(note_id=note_id, image_urls=image_urls)


def _consistent_note_id(api_data: Mapping[object, object]) -> str | None:
    thread = api_data.get("thread")
    first_floor = api_data.get("first_floor")
    if not isinstance(thread, Mapping) or not isinstance(first_floor, Mapping):
        return None
    candidates = [thread.get("id"), thread.get("tid"), first_floor.get("tid")]
    normalized = [_coerce_upstream_id(value) for value in candidates if value is not None]
    if not normalized or any(value is None for value in normalized) or len(set(normalized)) != 1:
        return None
    return normalized[0]


def _coerce_upstream_id(value: object) -> str | None:
    if type(value) is int:
        value = str(value)
    return value if type(value) is str and is_tieba_positive_id(value) else None


def _valid_text_item(item: Mapping[object, object]) -> bool:
    keys = set(item)
    if keys not in ({"type", "text"}, {"type", "c"}):
        return False
    value = item.get("text") if "text" in item else item.get("c")
    return type(value) is str and bool(value) and len(value) <= 1_048_576


def _validate_image_item(item: Mapping[str, object]) -> str:
    if set(item) != _IMAGE_ITEM_KEYS or type(item.get("type")) is not int or item.get("type") != 3:
        raise ValueError("invalid Tieba image item")
    for key in ("pic_id", "origin_size"):
        value = item.get(key)
        maximum = _MAX_ID if key == "pic_id" else _MAX_IMAGE_BYTES
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError("invalid Tieba image item")
    for key in ("is_long_pic", "show_original_btn"):
        value = item.get(key)
        if type(value) is not int or value not in {0, 1}:
            raise ValueError("invalid Tieba image item")
    dimensions = item.get("bsize")
    if type(dimensions) is not str or (match := _DIMENSIONS.fullmatch(dimensions)) is None:
        raise ValueError("invalid Tieba image item")
    if int(match.group("width")) > _MAX_DIMENSION or int(match.group("height")) > _MAX_DIMENSION:
        raise ValueError("invalid Tieba image item")

    origin = item.get("origin_src")
    if type(origin) is not str:
        raise ValueError("invalid Tieba image item")
    validate_tieba_image_url(origin)
    origin_match = _ORIGIN_PATH.fullmatch(urlsplit(origin).path)
    assert origin_match is not None
    identity = origin_match.group("identity")
    extension = origin_match.group("extension")
    for key in ("cdn_src", "big_cdn_src", "cdn_src_active"):
        candidate = item.get(key)
        if type(candidate) is not str:
            raise ValueError("invalid Tieba image item")
        parsed = _validated_image_base(candidate, require_query=True)
        candidate_match = _AUXILIARY_PATH.fullmatch(parsed.path)
        if (
            candidate_match is None
            or candidate_match.group("identity") != identity
            or candidate_match.group("extension") != extension
        ):
            raise ValueError("invalid Tieba image item")
    return origin


def _matches_extracted_result(result: object, capture: _RawCapture) -> bool:
    canonical_url = getattr(result, "note_url", None)
    if type(canonical_url) is not str:
        return False
    try:
        validate_tieba_thread_url(canonical_url, note_id=capture.note_id)
    except ValueError:
        return False
    return getattr(result, "note_id", None) == capture.note_id


def _matches_bound_object(capture: _BoundCapture, content_item: object) -> bool:
    return (
        capture.content_object is content_item
        and getattr(content_item, "note_id", None) == capture.note_id
        and getattr(content_item, "note_url", None) == capture.canonical_url
    )


def _matches_stored_row(capture: _BoundCapture, content_item: Mapping[object, object]) -> bool:
    return content_item.get("note_id") == capture.note_id and content_item.get("note_url") == capture.canonical_url


def _contains_private_field(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            key in {TIEBA_IMAGE_FIELD, TIEBA_IMAGES_FIELD} or _contains_private_field(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return any(_contains_private_field(item) for item in value)
    return False


def _validate_creator_page(
    response: object,
    *,
    page_size: int,
    seen_thread_ids: set[str],
) -> tuple[list[str], bool]:
    if not isinstance(response, Mapping):
        raise RuntimeError("invalid Tieba creator pagination")
    error_code = response.get("error_code", 0)
    data = response.get("data")
    if type(error_code) is not int or error_code != 0 or not isinstance(data, Mapping):
        raise RuntimeError("invalid Tieba creator pagination")
    has_more_value = data.get("has_more")
    items = data.get("list")
    if type(has_more_value) is not int or has_more_value not in {0, 1} or type(items) is not list:
        raise RuntimeError("invalid Tieba creator pagination")
    if not items or len(items) > page_size or (has_more_value == 1 and len(items) != page_size):
        raise RuntimeError("invalid Tieba creator pagination")
    thread_ids: list[str] = []
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("thread_info"), Mapping):
            raise RuntimeError("invalid Tieba creator pagination")
        info = item["thread_info"]
        candidates = [info.get("tid"), info.get("id")]
        normalized = [_coerce_upstream_id(value) for value in candidates if value is not None]
        if not normalized or any(value is None for value in normalized) or len(set(normalized)) != 1:
            raise RuntimeError("invalid Tieba creator pagination")
        thread_id = normalized[0]
        if thread_id is None or thread_id in seen_thread_ids or thread_id in thread_ids:
            raise RuntimeError("invalid Tieba creator pagination")
        thread_ids.append(thread_id)
    return thread_ids, bool(has_more_value)


def _matches_creator_note(note: object, thread_id: str) -> bool:
    if getattr(note, "note_id", None) != thread_id:
        return False
    note_url = getattr(note, "note_url", None)
    if type(note_url) is not str:
        return False
    try:
        return validate_tieba_thread_url(note_url, note_id=thread_id) == note_url
    except ValueError:
        return False


def _validate_creator_cap(value: int | None) -> None:
    if value is not None and (type(value) is not int or not 1 <= value <= 1_000):
        raise ValueError("creator_max_items must be between 1 and 1000")


def _module_belongs_to_checkout(module: object, checkout_root: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if type(module_file) is not str:
        return False
    try:
        return Path(module_file).resolve().is_relative_to(checkout_root.resolve())
    except OSError:
        return False


__all__ = [
    "TIEBA_IMAGES_FIELD",
    "TIEBA_IMAGE_FIELD",
    "install_tieba_media_capture",
    "is_tieba_positive_id",
    "tieba_image_source_hint",
    "validate_tieba_image_source_hint",
    "validate_tieba_image_url",
    "validate_tieba_thread_url",
]
