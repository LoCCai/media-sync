"""Owned one-page Tieba creator loop composed with the pinned upstream runtime.

The pinned creator loop (``.upstream/MediaCrawler/media_platform/tieba/client.py:772-830``)
walks 1-based page numbers on the signed PC feed endpoint and breaks on a falsy
``has_more``, an empty thread list, or any business rejection.  This shim replaces
only ``get_all_notes_by_creator_url`` with one page-bound unit:

* the list call is ``get_notes_by_creator_portrait(portrait, pn, rn=20)`` with the
  portrait upstream extracts from the creator URL (``client.py:172-186``);
* thread identities are ``thread_info.tid``/``id`` (``help.py:240-250``);
* each listed thread is fetched by ``get_note_by_id`` and stored through the
  pinned ``update_tieba_note``, so the 0020-0022 first-floor media shim keeps
  producing the same frozen shapes;
* a non-zero ``error_code``, a malformed body, ``DataFetchError``/``IPBlockError``
  or any transport failure restricts the feed and is never a source end
  (``client.py:806-810``).
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
from media_sync.integrations.mediacrawler.tieba_creator_work import (
    TB_CREATOR_PAGE_SIZE,
    TB_SCAN_COVERAGE_FILENAME,
    TB_SCAN_IDENTITY_FIELD,
    TiebaCreatorPage,
    TiebaScanUnit,
    TiebaWorkIdentity,
)

if TYPE_CHECKING:
    from media_sync.integrations.mediacrawler.bridge import RunnerManifest

_MARKER = "__media_sync_tieba_creator_capture_v1__"
_ACTIVE_IDENTITY: ContextVar[TiebaWorkIdentity | None] = ContextVar("tieba_thread_identity", default=None)
_ACTIVE_CREATOR: ContextVar[str | None] = ContextVar("tieba_creator_reference_fingerprint", default=None)
_THREAD_ID = re.compile(r"[0-9]{6,20}\Z")


class _TiebaThreadRejected(RuntimeError):
    pass


def _failure() -> RuntimeError:
    return RuntimeError("Tieba bounded creator-thread contract failed")


def _checkout_module(name: str, root: Path) -> Any:
    module = importlib.import_module(name)
    source = getattr(module, "__file__", None)
    if type(source) is not str or not Path(source).resolve().is_relative_to(root.resolve()):
        raise _failure()
    return module


def _coerce_thread_id(value: object) -> str | None:
    if type(value) is int and value > 0:
        text = str(value)
    elif type(value) is str and value.isascii() and value.isdigit() and not value.startswith("0"):
        text = value
    else:
        return None
    return text if _THREAD_ID.fullmatch(text) is not None else None


def parse_tieba_creator_page(value: object, *, page: int) -> TiebaCreatorPage:
    """Reduce one ``/c/u/feed/myThread`` response to bounded thread identities."""

    if not isinstance(value, Mapping):
        raise _failure()
    error_code = value.get("error_code", 0)
    data = value.get("data")
    if type(error_code) is not int or error_code != 0 or not isinstance(data, Mapping):
        raise _failure()
    has_more_value = data.get("has_more")
    items = data.get("list")
    if type(has_more_value) is not int or has_more_value not in {0, 1} or type(items) is not list:
        raise _failure()
    if len(items) > TB_CREATOR_PAGE_SIZE:
        raise _failure()
    identities: list[TiebaWorkIdentity] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise _failure()
        info = item.get("thread_info")
        if not isinstance(info, Mapping):
            raise _failure()
        candidates = [_coerce_thread_id(info.get("tid")), _coerce_thread_id(info.get("id"))]
        normalized = [candidate for candidate in candidates if candidate is not None]
        if not normalized or len(set(normalized)) != 1:
            raise _failure()
        thread_id = normalized[0]
        if any(existing.thread_id == thread_id for existing in identities):
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
        identities.append(TiebaWorkIdentity(thread_id, hashlib.sha256(listing).hexdigest()))
    try:
        return TiebaCreatorPage(page, has_more_value == 1, tuple(identities))
    except ValueError as error:
        raise _failure() from error


def _validate_detail(value: object, *, identity: TiebaWorkIdentity) -> object:
    if getattr(value, "note_id", None) != identity.thread_id:
        raise _failure()
    note_url = getattr(value, "note_url", None)
    if type(note_url) is not str or not note_url.startswith("https://tieba.baidu.com/p/"):
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


def install_tieba_creator_capture_shim(manifest: RunnerManifest) -> None:
    """Replace only the Tieba creator loop with one replayable page-bound unit."""

    state = manifest.tieba_scan
    if state is None or manifest.platform.value != "tieba":
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
    client_module = _checkout_module("media_platform.tieba.client", root)
    store = _checkout_module("store.tieba", root)
    store_impl = _checkout_module("store.tieba._store_impl", root)
    exception_module = _checkout_module("media_platform.tieba.exception", root)
    help_module = _checkout_module("media_platform.tieba.help", root)
    config = _checkout_module("config", root)
    client_class = getattr(client_module, "BaiduTieBaClient", None)
    jsonl_class = getattr(store_impl, "TieBaJsonlStoreImplement", None)
    old_creator = getattr(client_class, "get_all_notes_by_creator_url", None)
    old_store = getattr(jsonl_class, "store_content", None)
    update_note = getattr(store, "update_tieba_note", None)
    extractor_class = getattr(help_module, "TieBaExtractor", None)
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
        or jsonl_class is None
        or extractor_class is None
        or len(restricted_errors) != 1
        or len(feed_errors) != 1
        or getattr(old_creator, _MARKER, False)
        or getattr(old_store, _MARKER, False)
        or not callable(getattr(client_class, "get_notes_by_creator_portrait", None))
        or not callable(getattr(client_class, "get_note_by_id", None))
        or not callable(getattr(client_class, "_extract_creator_portrait", None))
    ):
        raise _failure()

    active_portrait: str | None = None
    store_started = False

    async def store_with_identity(instance: object, content_item: object) -> Any:
        nonlocal store_started
        identity = _ACTIVE_IDENTITY.get()
        creator_fingerprint = _ACTIVE_CREATOR.get()
        if (
            identity is None
            or creator_fingerprint != state.creator_fingerprint_sha256
            or active_portrait is None
            or not isinstance(content_item, dict)
            or TB_SCAN_IDENTITY_FIELD in content_item
            or str(content_item.get("note_id")) != identity.thread_id
        ):
            raise _failure()
        try:
            normalize_record(
                content_item,
                NormalizationContext(
                    Platform.TIEBA,
                    active_portrait,
                    active_portrait,
                    state.upstream_sha,
                    datetime.now(UTC),
                ),
            )
        except RecordNormalizationError:
            raise _TiebaThreadRejected from None
        store_started = True
        return await old_store(
            instance,
            {
                **content_item,
                TB_SCAN_IDENTITY_FIELD: {
                    **identity.as_mapping(),
                    "creator_fingerprint_sha256": creator_fingerprint,
                },
            },
        )

    started = False

    async def bounded_creator(
        instance: Any,
        creator_url: str,
        crawl_interval: float = 1.0,
        callback: object = None,
        max_note_count: int = 0,
    ) -> list[Any]:
        nonlocal active_portrait, started, store_started
        references = getattr(config, "TIEBA_CREATOR_URL_LIST", None)
        if started or type(references) is not list or len(references) != 1 or type(references[0]) is not str:
            raise _failure()
        started = True
        reference = references[0]
        if reference != creator_url:
            raise _failure()
        if hashlib.sha256(creator_url.encode("utf-8")).hexdigest() != state.creator_fingerprint_sha256:
            raise _failure()
        portrait_method = instance._extract_creator_portrait
        try:
            portrait = portrait_method(creator_url)
        except Exception as error:
            raise _failure() from error
        if (
            type(portrait) is not str
            or not portrait
            or portrait != portrait.strip()
            or hashlib.sha256(portrait.encode("utf-8")).hexdigest() != state.author_fingerprint_sha256
        ):
            raise _failure()
        active_portrait = portrait
        if (
            config.SAVE_DATA_OPTION != "jsonl"
            or config.ENABLE_GET_COMMENTS is not False
            or config.ENABLE_IP_PROXY is not False
            or config.MAX_CONCURRENCY_NUM != 1
        ):
            raise _failure()

        unit = TiebaScanUnit(state, manifest.max_items)
        requested = False

        async def pace() -> None:
            nonlocal requested
            if requested:
                await asyncio.sleep(manifest.request_delay_seconds or 0)
            requested = True

        collected: list[Any] = []

        while (action := unit.next_action()).kind != "stop":
            if action.kind == "list":
                try:
                    await pace()
                    with _suppress_upstream_logging(client_module):
                        response = await instance.get_notes_by_creator_portrait(
                            portrait=portrait,
                            page_number=action.page or 1,
                            page_size=TB_CREATOR_PAGE_SIZE,
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
                page = parse_tieba_creator_page(response, page=action.page or 1)
                unit.observe_page(page)
                continue

            identity = action.identity
            if identity is None:
                raise _failure()
            if action.kind == "unchanged":
                unit.skip_unchanged(identity)
                continue
            note: object = None
            restricted = False
            try:
                await pace()
                with _suppress_upstream_logging(client_module):
                    note = await instance.get_note_by_id(identity.thread_id)
            except restricted_errors:
                restricted = True
            except Exception:
                note = None
            if restricted:
                unit.fail(identity, access_restricted=True)
                continue
            if note is None:
                unit.fail(identity)
                continue
            validated = _validate_detail(note, identity=identity)
            identity_token = _ACTIVE_IDENTITY.set(identity)
            creator_scope = _ACTIVE_CREATOR.set(state.creator_fingerprint_sha256)
            store_started = False
            try:
                with _suppress_upstream_logging(store):
                    await update_note(validated)
            except _TiebaThreadRejected:
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
            collected.append(validated)
            unit.store(identity)

        # Upstream passes a store callback (`batch_update_*`), whose whole
        # body re-runs the guarded store. Every collected row is already
        # persisted above with its durable identity, so the callback is
        # deliberately never invoked: that second write would run with the
        # identity ContextVar reset, abort the unit, and leave no witness.
        coverage = unit.coverage()
        coverage.validate(state, manifest.max_items)
        output = manifest.output_root / TB_SCAN_COVERAGE_FILENAME
        if manifest.output_root.is_symlink() or output.is_symlink():
            raise _failure()
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(coverage.to_json_line())
        return collected

    setattr(bounded_creator, _MARKER, True)
    setattr(store_with_identity, _MARKER, True)
    cast(Any, client_class).get_all_notes_by_creator_url = bounded_creator
    cast(Any, jsonl_class).store_content = store_with_identity


__all__ = ["install_tieba_creator_capture_shim", "parse_tieba_creator_page"]
