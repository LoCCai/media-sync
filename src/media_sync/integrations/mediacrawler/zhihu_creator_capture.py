"""Owned one-page Zhihu creator loop composed with the pinned upstream runtime.

The pinned creator loop (``.upstream/MediaCrawler/media_platform/zhihu/core.py:256-300``)
delegates pagination to ``get_all_anwser_by_creator``
(``client.py:462-490``), which walks an integer ``offset`` in steps of a
client-chosen ``limit=20`` until ``paging.is_end`` is true.  This shim replaces
only ``get_all_anwser_by_creator`` with one page-bound unit:

* the list call is ``get_creator_answers(url_token, offset, limit)`` with the
  ``url_token`` upstream derives from the creator URL (``core.py:265``);
* answer identities are the extractor's ``content_id`` values, which the pinned
  help module derives from the answer and question ids;
* each listed answer is stored through the pinned ``update_zhihu_content`` so the
  0033 gallery shim keeps producing the same frozen shape;
* a falsy body, a malformed body or ``DataFetchError``/``IPBlockError`` restricts
  the feed and is never a source end (``client.py:483-484``).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib
import json
import re
from collections.abc import Iterator, Mapping
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, cast

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler.normalizers import (
    NormalizationContext,
    RecordNormalizationError,
    normalize_record,
)
from media_sync.integrations.mediacrawler.zhihu_creator_work import (
    ZH_SCAN_COVERAGE_FILENAME,
    ZH_SCAN_IDENTITY_FIELD,
    ZhihuCreatorPage,
    ZhihuScanUnit,
    ZhihuWorkIdentity,
)

if TYPE_CHECKING:
    from media_sync.integrations.mediacrawler.bridge import RunnerManifest

_MARKER = "__media_sync_zhihu_creator_capture_v1__"
_ACTIVE_IDENTITY: ContextVar[ZhihuWorkIdentity | None] = ContextVar("zhihu_answer_identity", default=None)
_ACTIVE_CREATOR: ContextVar[str | None] = ContextVar("zhihu_creator_reference_fingerprint", default=None)
_URL_TOKEN = re.compile(r"[A-Za-z0-9._-]{1,255}\Z", re.ASCII)


class _ZhihuAnswerRejected(RuntimeError):
    pass


def _failure() -> RuntimeError:
    return RuntimeError("Zhihu bounded creator-answer contract failed")


def _checkout_module(name: str, root: Path) -> Any:
    module = importlib.import_module(name)
    source = getattr(module, "__file__", None)
    if type(source) is not str or not Path(source).resolve().is_relative_to(root.resolve()):
        raise _failure()
    return module


def parse_zhihu_creator_page(value: object, *, offset: int, limit: int) -> ZhihuCreatorPage:
    """Reduce one ``/api/v4/members/<token>/answers`` response to identities."""

    if not isinstance(value, Mapping):
        raise _failure()
    data = value.get("data")
    paging = value.get("paging")
    if type(data) is not list or not isinstance(paging, Mapping):
        raise _failure()
    is_end = paging.get("is_end")
    # An EMPTY page is a valid shape: `is_end` decides whether it is the
    # declared end or a contradictory response, and the unit classifies that.
    # Raising here would turn a rate-limited body into a hard upstream fault
    # with no bounded witness, unlike the Weibo/Tieba shims.
    if type(is_end) is not bool or len(data) > limit:
        raise _failure()
    identities: list[ZhihuWorkIdentity] = []
    for item in data:
        if not isinstance(item, Mapping):
            raise _failure()
        tokens: list[str] = []
        for key in ("id", "answer_id"):
            candidate = item.get(key)
            if type(candidate) is int and candidate > 0:
                tokens.append(str(candidate))
            elif (
                type(candidate) is str and candidate.isascii() and candidate.isdigit() and not candidate.startswith("0")
            ):
                tokens.append(candidate)
        if not tokens or len(set(tokens)) != 1:
            raise _failure()
        content_id = tokens[0]
        if any(existing.content_id == content_id for existing in identities):
            raise _failure()
        try:
            listing = json.dumps(
                item,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise _failure() from None
        identities.append(ZhihuWorkIdentity(content_id, hashlib.sha256(listing).hexdigest()))
    try:
        return ZhihuCreatorPage(offset, limit, is_end, tuple(identities))
    except ValueError as error:
        raise _failure() from error


@contextlib.contextmanager
def _suppress_upstream_logging(module: Any) -> Iterator[None]:
    """Prevent short-lived list/detail authority from reaching dependency logs."""

    logger = getattr(getattr(module, "utils", None), "logger", None)
    names = ("debug", "info", "warning", "error", "exception")
    originals = {name: getattr(logger, name, None) for name in names}
    if logger is None or any(not callable(value) for value in originals.values()):
        raise _failure()
    try:
        for name in names:
            setattr(logger, name, lambda *_args, **_kwargs: None)
        yield
    finally:
        for name, value in originals.items():
            setattr(logger, name, value)


def install_zhihu_creator_capture_shim(manifest: RunnerManifest) -> None:
    """Replace only the Zhihu creator-answer loop with one page-bound unit."""

    state = manifest.zhihu_scan
    if state is None or manifest.platform.value != "zhihu":
        raise _failure()
    if ".." in PurePath(manifest.output_root).parts:
        raise _failure()
    state.require_binding(
        account_id=manifest.account_id,
        author_fingerprint_sha256=manifest.author_remote_id_fingerprint_sha256,
        creator_fingerprint_sha256=manifest.creator_fingerprint_sha256,
        upstream_sha=manifest.upstream_sha,
    )
    root = Path.cwd()
    core = _checkout_module("media_platform.zhihu.core", root)
    client_module = _checkout_module("media_platform.zhihu.client", root)
    store = _checkout_module("store.zhihu", root)
    store_impl = _checkout_module("store.zhihu._store_impl", root)
    exception_module = _checkout_module("media_platform.zhihu.exception", root)
    config = _checkout_module("config", root)
    crawler_class = getattr(core, "ZhihuCrawler", None)
    client_class = getattr(client_module, "ZhiHuClient", None)
    jsonl_class = getattr(store_impl, "ZhihuJsonlStoreImplement", None)
    old_creator = getattr(client_class, "get_all_anwser_by_creator", None)
    old_store = getattr(jsonl_class, "store_content", None)
    update_content = getattr(store, "update_zhihu_content", None)
    restricted_errors = tuple(
        error
        for name in ("IPBlockError",)
        for error in (getattr(exception_module, name, None),)
        if isinstance(error, type) and issubclass(error, BaseException)
    )
    feed_errors = tuple(
        error
        for name in ("DataFetchError",)
        for error in (getattr(exception_module, name, None),)
        if isinstance(error, type) and issubclass(error, BaseException)
    )
    if (
        not callable(old_creator)
        or not callable(old_store)
        or not callable(update_content)
        or client_class is None
        or crawler_class is None
        or jsonl_class is None
        or len(restricted_errors) != 1
        or len(feed_errors) != 1
        or getattr(old_creator, _MARKER, False)
        or getattr(old_store, _MARKER, False)
        or not callable(getattr(client_class, "get_creator_answers", None))
    ):
        raise _failure()

    active_url_token: str | None = None
    store_started = False

    async def store_with_identity(instance: object, content_item: object) -> Any:
        nonlocal store_started
        identity = _ACTIVE_IDENTITY.get()
        creator_fingerprint = _ACTIVE_CREATOR.get()
        if (
            identity is None
            or creator_fingerprint != state.creator_fingerprint_sha256
            or active_url_token is None
            or not isinstance(content_item, dict)
            or ZH_SCAN_IDENTITY_FIELD in content_item
            or str(content_item.get("content_id")) != identity.content_id
        ):
            raise _failure()
        try:
            normalize_record(
                content_item,
                NormalizationContext(
                    Platform.ZHIHU,
                    active_url_token,
                    active_url_token,
                    state.upstream_sha,
                    datetime.now(UTC),
                ),
            )
        except RecordNormalizationError:
            raise _ZhihuAnswerRejected from None
        store_started = True
        return await old_store(
            instance,
            {
                **content_item,
                ZH_SCAN_IDENTITY_FIELD: {
                    **identity.as_mapping(),
                    "creator_fingerprint_sha256": creator_fingerprint,
                },
            },
        )

    started = False

    async def bounded_creator(
        instance: Any,
        url_token: str,
        crawl_interval: float = 1.0,
        callback: Any = None,
    ) -> list[Any]:
        nonlocal active_url_token, started, store_started
        references = getattr(config, "ZHIHU_CREATOR_URL_LIST", None)
        if started or type(references) is not list or len(references) != 1 or type(references[0]) is not str:
            raise _failure()
        started = True
        reference = references[0]
        if reference.split("/")[-1] != url_token or _URL_TOKEN.fullmatch(url_token) is None:
            raise _failure()
        if hashlib.sha256(reference.encode("utf-8")).hexdigest() != state.creator_fingerprint_sha256:
            raise _failure()
        if hashlib.sha256(url_token.encode("utf-8")).hexdigest() != state.author_fingerprint_sha256:
            raise _failure()
        active_url_token = url_token
        if (
            config.SAVE_DATA_OPTION != "jsonl"
            or config.ENABLE_GET_COMMENTS is not False
            or config.ENABLE_IP_PROXY is not False
            or config.MAX_CONCURRENCY_NUM != 1
        ):
            raise _failure()
        extractor = getattr(instance, "_extractor", None)
        if extractor is None or not callable(getattr(extractor, "extract_content_list_from_creator", None)):
            raise _failure()

        unit = ZhihuScanUnit(state, manifest.max_items)
        requested = False
        collected: list[Any] = []

        async def pace() -> None:
            nonlocal requested
            if requested:
                await asyncio.sleep(manifest.request_delay_seconds or 0)
            requested = True

        while (action := unit.next_action()).kind != "stop":
            if action.kind == "list":
                try:
                    await pace()
                    with _suppress_upstream_logging(client_module):
                        response = await instance.get_creator_answers(
                            url_token,
                            action.offset or 0,
                            action.limit or 20,
                        )
                except (*restricted_errors, *feed_errors):
                    unit.observe_access_restricted()
                    continue
                except Exception:
                    unit.observe_access_restricted()
                    continue
                if not isinstance(response, Mapping) or not response:
                    unit.observe_access_restricted()
                    continue
                page = parse_zhihu_creator_page(response, offset=action.offset or 0, limit=action.limit or 20)
                # The extractor turns each raw answer into the pinned content
                # model; its content_id is the durable identity, so a mismatch
                # between the raw ids and the extracted ones is drift.
                contents = extractor.extract_content_list_from_creator(response.get("data"))
                if (
                    type(contents) is not list
                    or len(contents) != len(page.identities)
                    or [str(getattr(item, "content_id", "")) for item in contents]
                    != [identity.content_id for identity in page.identities]
                ):
                    raise _failure()
                by_content_id = {str(item.content_id): item for item in contents}
                unit.observe_page(page)
                # Drive the unit's own cursor rather than walking `contents`
                # positionally: a unit that stopped mid-page keeps the identical
                # offset and witness, so on replay the first listed answers are
                # already completed. `next_action()` skips those; a positional
                # walk would offer them again and be rejected as contract drift.
                while (pending := unit.next_action()).kind in {"detail", "unchanged"}:
                    pending_identity = pending.identity
                    if pending_identity is None:
                        raise _failure()
                    content = by_content_id.get(pending_identity.content_id)
                    if content is None:
                        raise _failure()
                    if pending.kind == "unchanged":
                        collected.append(content)
                        unit.skip_unchanged(pending_identity)
                        continue
                    identity_token = _ACTIVE_IDENTITY.set(pending_identity)
                    creator_scope = _ACTIVE_CREATOR.set(state.creator_fingerprint_sha256)
                    store_started = False
                    try:
                        with _suppress_upstream_logging(store):
                            await update_content(content)
                    except _ZhihuAnswerRejected:
                        unit.fail(pending_identity)
                        continue
                    except Exception:
                        if not store_started:
                            unit.fail(pending_identity)
                            continue
                        raise
                    finally:
                        _ACTIVE_CREATOR.reset(creator_scope)
                        _ACTIVE_IDENTITY.reset(identity_token)
                    collected.append(content)
                    unit.store(pending_identity)
                continue

            pending_identity = action.identity
            if pending_identity is None:
                raise _failure()
            unit.skip_unchanged(pending_identity)

        # Upstream passes a store callback (`batch_update_*`), whose whole
        # body re-runs the guarded store. Every collected row is already
        # persisted above with its durable identity, so the callback is
        # deliberately never invoked: that second write would run with the
        # identity ContextVar reset, abort the unit, and leave no witness.
        coverage = unit.coverage()
        coverage.validate(state, manifest.max_items)
        output = manifest.output_root / ZH_SCAN_COVERAGE_FILENAME
        if manifest.output_root.is_symlink() or output.is_symlink():
            raise _failure()
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(coverage.to_json_line())
        return collected

    setattr(bounded_creator, _MARKER, True)
    setattr(store_with_identity, _MARKER, True)
    cast(Any, client_class).get_all_anwser_by_creator = bounded_creator
    cast(Any, jsonl_class).store_content = store_with_identity


__all__ = ["install_zhihu_creator_capture_shim", "parse_zhihu_creator_page"]
