"""Task-local capture of one static image from a pinned Zhihu answer.

Pinned MediaCrawler turns answer HTML into plain text before its JSONL store
sees the record.  This integration-owned shim captures one narrowly supported
``img`` locator at that extractor boundary, binds it to the exact extracted
object, and injects it only while the matching record is being stored.  The
capture travels on that exact object across upstream ``asyncio.gather`` task
boundaries; a ``ContextVar`` then isolates only the nested store call.
"""

from __future__ import annotations

import asyncio
import importlib
import re
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

ZHIHU_IMAGE_FIELD = "__media_sync_zhihu_answer_image_v1"
ZHIHU_IMAGES_FIELD = "__media_sync_zhihu_answer_images_v2"

_INSTALL_MARKER = "__media_sync_zhihu_media_capture_v1__"
_CREATOR_CAP_MARKER = "__media_sync_zhihu_creator_cap_v1__"
_OBJECT_CAPTURE_FIELD = "__media_sync_zhihu_answer_image_capture_v1__"
_INSTALL_VERSION = "media-sync-zhihu-media-v1"
_MAX_ID = 2**63 - 1
_MAX_ANSWER_HTML_CHARS = 1_048_576
_MAX_URL_CHARS = 4_096
ZHIHU_MAX_GALLERY_IMAGES = 64
_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z", re.ASCII)
_STATIC_IMAGE_EXTENSIONS = frozenset({".jpeg", ".jpg", ".png", ".webp"})
_IMAGE_ATTRIBUTE_PRIORITY = ("data-original", "data-actualsrc", "src")
_IMAGE_ATTRIBUTES = frozenset(_IMAGE_ATTRIBUTE_PRIORITY)
_FORBIDDEN_MEDIA_TAGS = frozenset(
    {
        "audio",
        "iframe",
        "object",
        "picture",
        "source",
        "svg",
        "video",
    }
)


@dataclass(frozen=True, slots=True)
class _RawCapture:
    answer_id: str
    question_id: str
    image_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _BoundCapture:
    content_object: object
    answer_id: str
    question_id: str
    canonical_url: str
    image_urls: tuple[str, ...]


_ACTIVE_CAPTURE: ContextVar[_BoundCapture | None] = ContextVar(
    "media_sync_zhihu_active_answer_image",
    default=None,
)


class _AnswerImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.image_candidates: list[tuple[tuple[str, str | None], ...]] = []
        self.has_forbidden_media = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _FORBIDDEN_MEDIA_TAGS:
            self.has_forbidden_media = True
        if any(_is_forbidden_media_attribute(name) for name, _value in attrs):
            self.has_forbidden_media = True
        if normalized_tag != "img":
            return
        candidates = tuple((name.lower(), value) for name, value in attrs if name.lower() in _IMAGE_ATTRIBUTES)
        self.image_candidates.append(candidates)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def is_zhihu_positive_id(value: object) -> bool:
    """Return whether *value* is one canonical positive Zhihu numeric ID."""

    if type(value) is not str or not value.isascii() or not value.isdigit():
        return False
    if value.startswith("0"):
        return False
    try:
        return int(value) <= _MAX_ID
    except ValueError:
        return False


def validate_zhihu_image_url(value: str) -> str:
    """Return one bounded Zhihu static-image URL unchanged or raise ``ValueError``."""

    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or len(value) > _MAX_URL_CHARS
        or "\\" in value
        or "#" in value
        or value.endswith("?")
        or any(character.isspace() for character in value)
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise ValueError("invalid Zhihu image URL")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Zhihu image URL") from exc

    if (
        parsed.scheme.lower() != "https"
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or ("?" in value and not parsed.query)
        or parsed.fragment
        or parsed.path in {"", "/"}
        or not _is_canonical_image_authority(parsed.netloc, hostname, port)
        or not _is_zhimg_hostname(hostname)
        or not _has_static_image_extension(parsed.path)
    ):
        raise ValueError("invalid Zhihu image URL")
    return value


def validate_zhihu_answer_url(
    value: str,
    *,
    answer_id: str | None = None,
    question_id: str | None = None,
) -> str:
    """Return one canonical Zhihu answer URL or raise ``ValueError``.

    Optional IDs constrain the corresponding path components and are useful
    when checking a persisted record against its source object.
    """

    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or len(value) > _MAX_URL_CHARS
        or "\\" in value
        or "?" in value
        or "#" in value
        or any(character.isspace() for character in value)
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise ValueError("invalid Zhihu answer URL")
    if answer_id is not None and not is_zhihu_positive_id(answer_id):
        raise ValueError("invalid Zhihu answer ID")
    if question_id is not None and not is_zhihu_positive_id(question_id):
        raise ValueError("invalid Zhihu question ID")

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Zhihu answer URL") from exc
    segments = parsed.path.split("/")
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.zhihu.com"
        or parsed.hostname != "www.zhihu.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or len(segments) != 5
        or segments[0] != ""
        or segments[1] != "question"
        or segments[3] != "answer"
        or not is_zhihu_positive_id(segments[2])
        or not is_zhihu_positive_id(segments[4])
        or (question_id is not None and segments[2] != question_id)
        or (answer_id is not None and segments[4] != answer_id)
    ):
        raise ValueError("invalid Zhihu answer URL")
    return value


def install_zhihu_media_capture(
    checkout_root: Path,
    *,
    creator_max_items: int | None = None,
) -> None:
    """Install the pinned Zhihu capture shim once in the current child process."""

    _validate_creator_cap(creator_max_items)
    extractor_module = importlib.import_module("media_platform.zhihu.help")
    client_module = importlib.import_module("media_platform.zhihu.client")
    store_module = importlib.import_module("store.zhihu")
    store_impl_module = importlib.import_module("store.zhihu._store_impl")
    for module, label in (
        (extractor_module, "Zhihu extractor"),
        (client_module, "Zhihu client"),
        (store_module, "Zhihu store"),
        (store_impl_module, "Zhihu JSONL store"),
    ):
        if not _module_belongs_to_checkout(module, checkout_root):
            raise RuntimeError(f"{label} did not load from the verified checkout")

    extractor_class_candidate = getattr(extractor_module, "ZhihuExtractor", None)
    client_class_candidate = getattr(client_module, "ZhiHuClient", None)
    jsonl_store_candidate = getattr(store_module, "ZhihuJsonlStoreImplement", None)
    impl_jsonl_store = getattr(store_impl_module, "ZhihuJsonlStoreImplement", None)
    if jsonl_store_candidate is None or jsonl_store_candidate is not impl_jsonl_store:
        raise RuntimeError("pinned Zhihu JSONL store export drifted")
    extract_answer_candidate = getattr(extractor_class_candidate, "_extract_answer_content", None)
    get_all_answers_candidate = getattr(client_class_candidate, "get_all_anwser_by_creator", None)
    update_content_candidate = getattr(store_module, "update_zhihu_content", None)
    store_content_candidate = getattr(jsonl_store_candidate, "store_content", None)
    if not all(
        callable(target)
        for target in (
            extract_answer_candidate,
            get_all_answers_candidate,
            update_content_candidate,
            store_content_candidate,
        )
    ):
        raise RuntimeError("pinned Zhihu media contract drifted")
    extractor_class: Any = extractor_class_candidate
    client_class: Any = client_class_candidate
    jsonl_store: Any = jsonl_store_candidate
    extract_answer = cast(Callable[..., Any], extract_answer_candidate)
    get_all_answers = cast(Callable[..., Any], get_all_answers_candidate)
    update_content = cast(Callable[..., Any], update_content_candidate)
    store_content = cast(Callable[..., Any], store_content_candidate)

    targets = (extract_answer, update_content, store_content)
    markers = tuple(getattr(target, _INSTALL_MARKER, None) for target in targets)
    client_marker = getattr(get_all_answers, _INSTALL_MARKER, None)
    if any(marker is not None and marker != _INSTALL_VERSION for marker in (*markers, client_marker)):
        raise RuntimeError("Zhihu media shim marker collision")
    if any(marker == _INSTALL_VERSION for marker in markers):
        if not all(marker == _INSTALL_VERSION for marker in markers):
            raise RuntimeError("partial Zhihu media shim installation")
        if creator_max_items is not None:
            if client_marker != _INSTALL_VERSION:
                raise RuntimeError("partial Zhihu creator cap installation")
            if getattr(get_all_answers, _CREATOR_CAP_MARKER, None) != creator_max_items:
                raise RuntimeError("Zhihu creator cap collision")
        return
    if client_marker == _INSTALL_VERSION:
        raise RuntimeError("partial Zhihu media shim installation")

    @wraps(extract_answer)
    def extract_with_image(instance: object, answer: object) -> Any:
        result = extract_answer(instance, answer)
        raw_capture = _capture_answer(answer)
        if raw_capture is None:
            return result
        canonical_url = getattr(result, "content_url", None)
        if not isinstance(canonical_url, str) or not _matches_extracted_result(result, raw_capture, canonical_url):
            return result
        capture = _BoundCapture(
            content_object=result,
            answer_id=raw_capture.answer_id,
            question_id=raw_capture.question_id,
            canonical_url=canonical_url,
            image_urls=raw_capture.image_urls,
        )
        sentinel = object()
        if getattr(result, _OBJECT_CAPTURE_FIELD, sentinel) is not sentinel:
            raise RuntimeError("private Zhihu object capture collision")
        try:
            object.__setattr__(result, _OBJECT_CAPTURE_FIELD, capture)
        except (AttributeError, TypeError) as exc:
            raise RuntimeError("pinned Zhihu content object cannot carry media capture") from exc
        return result

    @wraps(update_content)
    async def update_with_image(content_item: object) -> Any:
        attached = getattr(content_item, _OBJECT_CAPTURE_FIELD, None)
        capture: _BoundCapture | None = None
        if attached is not None:
            if not isinstance(attached, _BoundCapture) or attached.content_object is not content_item:
                raise RuntimeError("private Zhihu object capture collision")
            try:
                object.__delattr__(content_item, _OBJECT_CAPTURE_FIELD)
            except (AttributeError, TypeError) as exc:
                raise RuntimeError("private Zhihu object capture could not be consumed") from exc
            if _matches_bound_object(attached, content_item):
                capture = attached
        token = _ACTIVE_CAPTURE.set(capture)
        try:
            return await update_content(content_item)
        finally:
            _ACTIVE_CAPTURE.reset(token)

    @wraps(store_content)
    async def store_with_image(instance: object, content_item: object) -> Any:
        if not isinstance(content_item, Mapping):
            return await store_content(instance, content_item)
        if ZHIHU_IMAGE_FIELD in content_item or ZHIHU_IMAGES_FIELD in content_item:
            raise RuntimeError("private Zhihu media field collision")
        capture = _ACTIVE_CAPTURE.get()
        if capture is None or not _matches_stored_row(capture, content_item):
            return await store_content(instance, content_item)
        enriched = dict(content_item)
        if len(capture.image_urls) == 1:
            enriched[ZHIHU_IMAGE_FIELD] = capture.image_urls[0]
        else:
            enriched[ZHIHU_IMAGES_FIELD] = list(capture.image_urls)
        return await store_content(instance, enriched)

    setattr(extract_with_image, _INSTALL_MARKER, _INSTALL_VERSION)
    setattr(update_with_image, _INSTALL_MARKER, _INSTALL_VERSION)
    setattr(store_with_image, _INSTALL_MARKER, _INSTALL_VERSION)

    bounded_get_all: Any = None
    if creator_max_items is not None:

        @wraps(get_all_answers)
        async def get_bounded_answers(
            instance: object,
            url_token: str,
            crawl_interval: float = 1.0,
            callback: Any = None,
        ) -> list[Any]:
            all_contents: list[Any] = []
            seen_content_ids: set[str] = set()
            offset = 0
            while len(all_contents) < creator_max_items:
                remaining = creator_max_items - len(all_contents)
                limit = min(20, remaining)
                response = await instance.get_creator_answers(url_token, offset, limit)  # type: ignore[attr-defined]
                data, is_end = _validate_creator_page(response, limit=limit)
                contents = instance._extractor.extract_content_list_from_creator(data)  # type: ignore[attr-defined]
                if type(contents) is not list or len(contents) != len(data) or len(contents) > remaining:
                    raise RuntimeError("pinned Zhihu creator extractor contract drifted")
                page_content_ids: list[str] = []
                for content in contents:
                    content_id = getattr(content, "content_id", None)
                    if (
                        type(content_id) is not str
                        or not is_zhihu_positive_id(content_id)
                        or content_id in seen_content_ids
                        or content_id in page_content_ids
                    ):
                        raise RuntimeError("invalid Zhihu creator pagination")
                    page_content_ids.append(content_id)
                if not is_end and len(data) != limit:
                    raise RuntimeError("invalid Zhihu creator pagination")
                if callback:
                    await callback(contents)
                all_contents.extend(contents)
                seen_content_ids.update(page_content_ids)
                if is_end or len(all_contents) >= creator_max_items:
                    break
                offset += limit
                await asyncio.sleep(crawl_interval)
            return all_contents

        setattr(get_bounded_answers, _INSTALL_MARKER, _INSTALL_VERSION)
        setattr(get_bounded_answers, _CREATOR_CAP_MARKER, creator_max_items)
        bounded_get_all = get_bounded_answers

    assigned: list[tuple[object, str, Any]] = []
    try:
        assigned.append((extractor_class, "_extract_answer_content", extract_answer))
        extractor_class._extract_answer_content = extract_with_image
        assigned.append((store_module, "update_zhihu_content", update_content))
        store_module.__dict__["update_zhihu_content"] = update_with_image
        assigned.append((jsonl_store, "store_content", store_content))
        jsonl_store.store_content = store_with_image
        if bounded_get_all is not None:
            assigned.append((client_class, "get_all_anwser_by_creator", get_all_answers))
            client_class.get_all_anwser_by_creator = bounded_get_all
    except Exception:
        for owner, attribute, original in reversed(assigned):
            setattr(owner, attribute, original)
        raise


def _capture_answer(answer: object) -> _RawCapture | None:
    if not isinstance(answer, Mapping) or answer.get("type") != "answer":
        return None
    answer_id = _coerce_upstream_id(answer.get("id"))
    question = answer.get("question")
    question_id = _coerce_upstream_id(question.get("id")) if isinstance(question, Mapping) else None
    html = answer.get("content")
    if answer_id is None or question_id is None or type(html) is not str or len(html) > _MAX_ANSWER_HTML_CHARS:
        return None

    parser = _AnswerImageParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return None
    if parser.has_forbidden_media or not 1 <= len(parser.image_candidates) <= ZHIHU_MAX_GALLERY_IMAGES:
        return None
    selected_urls: list[str] = []
    for candidates in parser.image_candidates:
        candidate_names = [name for name, _value in candidates]
        if not candidates or len(candidate_names) != len(set(candidate_names)):
            return None
        selected: str | None = None
        for attribute in _IMAGE_ATTRIBUTE_PRIORITY:
            values = [value for name, value in candidates if name == attribute]
            if values:
                value = values[0]
                if type(value) is not str or not value:
                    return None
                selected = value
                break
        if selected is None:  # pragma: no cover - candidates contain only managed names
            return None
        try:
            selected_urls.append(validate_zhihu_image_url(selected))
        except ValueError:
            return None
    if len(set(selected_urls)) != len(selected_urls):
        return None
    return _RawCapture(answer_id=answer_id, question_id=question_id, image_urls=tuple(selected_urls))


def _coerce_upstream_id(value: object) -> str | None:
    if type(value) is int:
        value = str(value)
    return value if type(value) is str and is_zhihu_positive_id(value) else None


def _matches_extracted_result(result: object, capture: _RawCapture, canonical_url: str) -> bool:
    try:
        validate_zhihu_answer_url(
            canonical_url,
            answer_id=capture.answer_id,
            question_id=capture.question_id,
        )
    except ValueError:
        return False
    return (
        getattr(result, "content_type", None) == "answer"
        and getattr(result, "content_id", None) == capture.answer_id
        and getattr(result, "question_id", None) == capture.question_id
    )


def _matches_bound_object(capture: _BoundCapture, content_item: object) -> bool:
    return (
        capture.content_object is content_item
        and getattr(content_item, "content_type", None) == "answer"
        and getattr(content_item, "content_id", None) == capture.answer_id
        and getattr(content_item, "question_id", None) == capture.question_id
        and getattr(content_item, "content_url", None) == capture.canonical_url
    )


def _matches_stored_row(capture: _BoundCapture, content_item: Mapping[object, object]) -> bool:
    return (
        content_item.get("content_type") == "answer"
        and content_item.get("content_id") == capture.answer_id
        and content_item.get("question_id") == capture.question_id
        and content_item.get("content_url") == capture.canonical_url
    )


def _validate_creator_page(response: object, *, limit: int) -> tuple[list[Any], bool]:
    if not isinstance(response, Mapping):
        raise RuntimeError("invalid Zhihu creator page")
    data = response.get("data")
    paging = response.get("paging")
    if type(data) is not list or not isinstance(paging, Mapping):
        raise RuntimeError("invalid Zhihu creator page")
    is_end = paging.get("is_end")
    if type(is_end) is not bool or len(data) > limit or (not data and not is_end):
        raise RuntimeError("invalid Zhihu creator pagination")
    return data, is_end


def _validate_creator_cap(value: int | None) -> None:
    if value is not None and (type(value) is not int or value <= 0):
        raise ValueError("creator_max_items must be a positive integer or None")


def _module_belongs_to_checkout(module: object, checkout_root: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        return False
    try:
        return Path(module_file).resolve().is_relative_to(checkout_root.resolve())
    except OSError:
        return False


def _is_dns_hostname(value: str) -> bool:
    if not value.isascii() or len(value) > 253:
        return False
    labels = value.split(".")
    return all(_DNS_LABEL.fullmatch(label) is not None for label in labels)


def _is_canonical_image_authority(netloc: str, hostname: str, port: int | None) -> bool:
    authority_host = netloc
    if port is None:
        if ":" in authority_host:
            return False
    else:
        if not authority_host.endswith(":443"):
            return False
        authority_host = authority_host[:-4]
    return authority_host.lower() == hostname.lower() and _is_dns_hostname(authority_host)


def _is_zhimg_hostname(value: str) -> bool:
    normalized = value.lower()
    return normalized == "zhimg.com" or normalized.endswith(".zhimg.com")


def _is_forbidden_media_attribute(value: str) -> bool:
    normalized = value.lower()
    return normalized in {
        "data-lazy-src",
        "data-lazy-srcset",
        "data-player",
        "data-src",
        "data-srcset",
        "data-video",
        "srcset",
    } or normalized.startswith(("data-player-", "data-video-"))


def _has_static_image_extension(path: str) -> bool:
    filename = path.rsplit("/", 1)[-1]
    dot = filename.rfind(".")
    return dot > 0 and filename[dot:].lower() in _STATIC_IMAGE_EXTENSIONS


__all__ = [
    "ZHIHU_IMAGES_FIELD",
    "ZHIHU_IMAGE_FIELD",
    "ZHIHU_MAX_GALLERY_IMAGES",
    "install_zhihu_media_capture",
    "is_zhihu_positive_id",
    "validate_zhihu_answer_url",
    "validate_zhihu_image_url",
]
