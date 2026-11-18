"""Owned one-page Weibo creator loop composed with the pinned upstream runtime.

The pinned creator loop (``.upstream/MediaCrawler/media_platform/weibo/core.py:308-334``)
delegates pagination to ``get_all_notes_by_creator_id`` (``client.py:372-412``),
which is unbounded and ends on an arithmetic inference.  This shim replaces only
``WeiboCrawler.get_creators_and_notes`` with one page-bound unit:

* the list call is ``get_notes_by_creator(creator_id, container_id, since_id)``
  with the container id upstream derives (``core.py:328``);
* the response is reduced to ``card_type == 9`` cards (``client.py:409``) plus
  the verbatim echoed ``since_id`` and ``cardlistInfo.total``;
* each listed note is stored through the pinned ``update_weibo_note`` so the
  0016/0031/0035/0036 media shim keeps producing the same frozen shapes, and the
  durable identity rides one media-sync-owned private field;
* a falsy body, a missing ``cards`` key, ``DataFetchError``/``IPBlockError`` or
  any transport failure restricts the feed and is never a source end
  (``client.py:401-406``).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib
import json
import re
from collections.abc import Iterator
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
from media_sync.integrations.mediacrawler.weibo_creator_work import (
    WB_SCAN_COVERAGE_FILENAME,
    WB_SCAN_IDENTITY_FIELD,
    WeiboCreatorPage,
    WeiboScanUnit,
    WeiboWorkIdentity,
)

if TYPE_CHECKING:
    from media_sync.integrations.mediacrawler.bridge import RunnerManifest

_MARKER = "__media_sync_weibo_creator_capture_v1__"
_ACTIVE_IDENTITY: ContextVar[WeiboWorkIdentity | None] = ContextVar("weibo_note_identity", default=None)
_ACTIVE_CREATOR: ContextVar[str | None] = ContextVar("weibo_creator_reference_fingerprint", default=None)
_NOTE_ID = re.compile(r"[0-9]{10,20}\Z")


class _WeiboNoteRejected(RuntimeError):
    pass


def _failure() -> RuntimeError:
    return RuntimeError("Weibo bounded creator-note contract failed")


def _checkout_module(name: str, root: Path) -> Any:
    module = importlib.import_module(name)
    source = getattr(module, "__file__", None)
    if type(source) is not str or not Path(source).resolve().is_relative_to(root.resolve()):
        raise _failure()
    return module


def _declared_total(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise _failure()
    return value


def parse_weibo_creator_page(value: object, *, input_since_id: str) -> WeiboCreatorPage:
    """Reduce one ``/api/container/getIndex`` response to bounded identities."""

    if not isinstance(value, dict):
        raise _failure()
    cards = value.get("cards")
    if type(cards) is not list:
        # A missing ``cards`` key breaks the upstream loop (client.py:404-406);
        # it is never a page and must not be reduced into progress.
        raise _failure()
    cardlist = value.get("cardlistInfo")
    if not isinstance(cardlist, dict):
        raise _failure()
    next_cursor = cardlist.get("since_id", "0")
    if type(next_cursor) is not str:
        raise _failure()
    total = _declared_total(cardlist.get("total"))
    identities: list[WeiboWorkIdentity] = []
    for card in cards:
        if not isinstance(card, dict):
            raise _failure()
        if card.get("card_type") != 9:
            continue
        mblog = card.get("mblog")
        if not isinstance(mblog, dict):
            raise _failure()
        note_id = mblog.get("id")
        if type(note_id) is not str or _NOTE_ID.fullmatch(note_id) is None:
            raise _failure()
        if any(item.note_id == note_id for item in identities):
            continue
        try:
            listing = json.dumps(
                card,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise _failure() from None
        identities.append(WeiboWorkIdentity(note_id, hashlib.sha256(listing).hexdigest()))
    try:
        return WeiboCreatorPage(input_since_id, next_cursor, total, tuple(identities))
    except ValueError as error:
        raise _failure() from error


def _validate_detail(value: object, *, identity: WeiboWorkIdentity, creator_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _failure()
    mblog = value.get("mblog")
    if not isinstance(mblog, dict) or str(mblog.get("id")) != identity.note_id:
        raise _failure()
    author = mblog.get("user")
    if not isinstance(author, dict) or str(author.get("id")) != creator_id:
        raise _failure()
    return value


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


def install_weibo_creator_capture_shim(manifest: RunnerManifest) -> None:
    """Replace only the Weibo creator method with one replayable page-bound unit.

    The child process has already validated the checkout and changed its working
    directory into it, so the shim anchors every filesystem access on the process
    working directory and never re-derives a root from manifest fields.
    """

    state = manifest.weibo_scan
    if state is None or manifest.platform.value != "wb":
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
    core = _checkout_module("media_platform.weibo.core", root)
    client_module = _checkout_module("media_platform.weibo.client", root)
    store = _checkout_module("store.weibo", root)
    store_impl = _checkout_module("store.weibo._store_impl", root)
    exception_module = _checkout_module("media_platform.weibo.exception", root)
    config = _checkout_module("config", root)
    crawler_class = getattr(core, "WeiboCrawler", None)
    client_class = getattr(client_module, "WeiboClient", None)
    jsonl_class = getattr(store_impl, "WeiboJsonlStoreImplement", None)
    old_creator = getattr(crawler_class, "get_creators_and_notes", None)
    old_store = getattr(jsonl_class, "store_content", None)
    update_note = getattr(store, "update_weibo_note", None)
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
        or not callable(update_note)
        or client_class is None
        or crawler_class is None
        or jsonl_class is None
        or len(restricted_errors) != 1
        or len(feed_errors) != 1
        or getattr(old_creator, _MARKER, False)
        or getattr(old_store, _MARKER, False)
        or not callable(getattr(client_class, "get_notes_by_creator", None))
        or not callable(getattr(client_class, "get_note_info_by_id", None))
    ):
        raise _failure()

    active_creator_id: str | None = None
    store_started = False

    async def store_with_identity(instance: object, content_item: object) -> Any:
        nonlocal store_started
        identity = _ACTIVE_IDENTITY.get()
        creator_fingerprint = _ACTIVE_CREATOR.get()
        if (
            identity is None
            or creator_fingerprint != state.creator_fingerprint_sha256
            or active_creator_id is None
            or not isinstance(content_item, dict)
            or WB_SCAN_IDENTITY_FIELD in content_item
            or content_item.get("note_id") != identity.note_id
        ):
            raise _failure()
        try:
            normalize_record(
                content_item,
                NormalizationContext(
                    Platform.WB,
                    active_creator_id,
                    active_creator_id,
                    state.upstream_sha,
                    datetime.now(UTC),
                ),
            )
        except RecordNormalizationError:
            raise _WeiboNoteRejected from None
        store_started = True
        return await old_store(
            instance,
            {
                **content_item,
                WB_SCAN_IDENTITY_FIELD: {
                    **identity.as_mapping(),
                    "creator_fingerprint_sha256": creator_fingerprint,
                },
            },
        )

    started = False

    async def bounded_creator(crawler: Any) -> None:
        nonlocal active_creator_id, started, store_started
        references = getattr(config, "WEIBO_CREATOR_ID_LIST", None)
        if started or type(references) is not list or len(references) != 1 or type(references[0]) is not str:
            raise _failure()
        started = True
        creator_reference = references[0]
        if hashlib.sha256(creator_reference.encode("utf-8")).hexdigest() != state.creator_fingerprint_sha256:
            raise _failure()
        if _NOTE_ID.fullmatch(creator_reference) is None:
            raise _failure()
        creator_id = creator_reference
        if hashlib.sha256(creator_id.encode("utf-8")).hexdigest() != state.author_fingerprint_sha256:
            raise _failure()
        active_creator_id = creator_id
        if (
            config.SAVE_DATA_OPTION != "jsonl"
            or config.ENABLE_GET_COMMENTS is not False
            or config.ENABLE_IP_PROXY is not False
            or config.MAX_CONCURRENCY_NUM != 1
        ):
            raise _failure()
        client = crawler.wb_client
        if not isinstance(client, client_class):
            raise _failure()

        unit = WeiboScanUnit(state, manifest.max_items)
        container_id = f"107603{creator_id}"
        requested = False

        async def pace() -> None:
            nonlocal requested
            if requested:
                await asyncio.sleep(manifest.request_delay_seconds or 0)
            requested = True

        while (action := unit.next_action()).kind != "stop":
            if action.kind == "list":
                try:
                    await pace()
                    with _suppress_upstream_logging(core):
                        response = await client.get_notes_by_creator(
                            creator_id,
                            container_id,
                            action.since_id or "",
                        )
                except (*restricted_errors, *feed_errors):
                    unit.observe_access_restricted()
                    continue
                except Exception:
                    # A transport-level failure aborts the exception-free
                    # upstream loop; the feed is restricted, never source end.
                    unit.observe_access_restricted()
                    continue
                if not isinstance(response, dict) or not response:
                    # A falsy body is upstream's "possibly banned" branch
                    # (client.py:401-403); it can never become progress.
                    unit.observe_access_restricted()
                    continue
                page = parse_weibo_creator_page(response, input_since_id=action.since_id or "")
                unit.observe_page(page)
                continue

            identity = action.identity
            if identity is None:
                raise _failure()
            if action.kind == "unchanged":
                unit.skip_unchanged(identity)
                continue
            detail: object = None
            restricted = False
            try:
                await pace()
                with _suppress_upstream_logging(core):
                    detail = await client.get_note_info_by_id(identity.note_id)
            except restricted_errors:
                restricted = True
            except Exception:
                detail = None
            if restricted:
                unit.fail(identity, access_restricted=True)
                continue
            if not detail:
                unit.fail(identity)
                continue
            note_item = _validate_detail(detail, identity=identity, creator_id=creator_id)
            identity_token = _ACTIVE_IDENTITY.set(identity)
            creator_scope = _ACTIVE_CREATOR.set(state.creator_fingerprint_sha256)
            store_started = False
            try:
                with _suppress_upstream_logging(store):
                    await update_note(note_item)
            except _WeiboNoteRejected:
                unit.fail(identity)
                continue
            except Exception:
                if not store_started:
                    unit.fail(identity)
                    continue
                raise
            finally:
                _ACTIVE_CREATOR.reset(creator_scope)
                _ACTIVE_IDENTITY.reset(identity_token)
            unit.store(identity)

        coverage = unit.coverage()
        coverage.validate(state, manifest.max_items)
        output = manifest.output_root / WB_SCAN_COVERAGE_FILENAME
        if manifest.output_root.is_symlink() or output.is_symlink():
            raise _failure()
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(coverage.to_json_line())

    setattr(bounded_creator, _MARKER, True)
    setattr(store_with_identity, _MARKER, True)
    cast(Any, crawler_class).get_creators_and_notes = bounded_creator
    cast(Any, jsonl_class).store_content = store_with_identity


__all__ = ["install_weibo_creator_capture_shim", "parse_weibo_creator_page"]
