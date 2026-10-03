"""Owned one-page Douyin creator loop composed with the pinned upstream runtime."""

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
from media_sync.integrations.mediacrawler.douyin_creator_work import (
    DOUYIN_CREATOR_PAGE_SIZE,
    DOUYIN_SCAN_COVERAGE_FILENAME,
    DOUYIN_SCAN_IDENTITY_FIELD,
    DouyinCreatorPage,
    DouyinScanUnit,
    DouyinWorkIdentity,
)
from media_sync.integrations.mediacrawler.normalizers import (
    NormalizationContext,
    RecordNormalizationError,
    normalize_record,
)

if TYPE_CHECKING:
    from media_sync.integrations.mediacrawler.bridge import RunnerManifest

_MARKER = "__media_sync_douyin_creator_capture_v1__"
_ACTIVE_IDENTITY: ContextVar[DouyinWorkIdentity | None] = ContextVar("douyin_work_identity", default=None)
_ACTIVE_CREATOR: ContextVar[str | None] = ContextVar("douyin_creator_reference_fingerprint", default=None)
_AWEME_ID = re.compile(r"[0-9]{10,20}\Z")
_SEC_USER_ID = re.compile(r"[A-Za-z0-9_\-]{20,80}\Z", re.ASCII)


class _DouyinWorkRejected(RuntimeError):
    pass


def _failure() -> RuntimeError:
    return RuntimeError("Douyin bounded creator-work contract failed")


def _checkout_module(name: str, root: Path) -> Any:
    module = importlib.import_module(name)
    source = getattr(module, "__file__", None)
    if type(source) is not str or not Path(source).resolve().is_relative_to(root.resolve()):
        raise _failure()
    return module


def parse_douyin_creator_page(value: object, *, input_cursor: str) -> DouyinCreatorPage:
    """Reduce one upstream ``aweme/post`` list response to bounded identities."""

    if not isinstance(value, dict):
        raise _failure()
    has_more_raw = value.get("has_more")
    next_cursor = value.get("max_cursor")
    works = value.get("aweme_list")
    if type(has_more_raw) is not int or has_more_raw not in (0, 1):
        raise _failure()
    if type(next_cursor) is not str or type(works) is not list:
        raise _failure()
    if len(works) > DOUYIN_CREATOR_PAGE_SIZE:
        raise _failure()
    identities: list[DouyinWorkIdentity] = []
    for work in works:
        if not isinstance(work, dict):
            raise _failure()
        aweme_id = work.get("aweme_id")
        if type(aweme_id) is not str or _AWEME_ID.fullmatch(aweme_id) is None:
            raise _failure()
        if any(item.aweme_id == aweme_id for item in identities):
            raise _failure()
        try:
            listing = json.dumps(
                work,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise _failure() from None
        identities.append(DouyinWorkIdentity(aweme_id, hashlib.sha256(listing).hexdigest()))
    try:
        return DouyinCreatorPage(input_cursor, next_cursor, has_more_raw == 1, tuple(identities))
    except ValueError as error:
        raise _failure() from error


def _validate_detail(value: object, *, identity: DouyinWorkIdentity, sec_user_id: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("aweme_id") != identity.aweme_id:
        raise _failure()
    author = value.get("author")
    if not isinstance(author, dict) or author.get("sec_uid") != sec_user_id:
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


def install_douyin_creator_capture_shim(manifest: RunnerManifest) -> None:
    """Replace only the Douyin creator method with one replayable page-bound unit.

    The child process has already validated the checkout and changed its
    working directory into it, so the shim anchors every filesystem access
    on the process working directory and never re-derives a root from
    manifest fields.
    """

    state = manifest.douyin_scan
    if state is None or manifest.platform.value != "dy":
        raise _failure()
    # Manifest-borne workspace paths must not carry traversal segments; the
    # shim only ever touches files under the working directory and the
    # output root.
    if ".." in PurePath(manifest.output_root).parts:
        raise _failure()
    state.require_binding(
        account_id=manifest.account_id,
        author_fingerprint_sha256=manifest.author_remote_id_fingerprint_sha256,
        creator_fingerprint_sha256=manifest.creator_fingerprint_sha256,
        upstream_sha=manifest.upstream_sha,
    )
    root = Path.cwd()
    core = _checkout_module("media_platform.douyin.core", root)
    client_module = _checkout_module("media_platform.douyin.client", root)
    store = _checkout_module("store.douyin", root)
    store_impl = _checkout_module("store.douyin._store_impl", root)
    help_module = _checkout_module("media_platform.douyin.help", root)
    exception_module = _checkout_module("media_platform.douyin.exception", root)
    config = _checkout_module("config", root)
    crawler_class = getattr(core, "DouYinCrawler", None)
    client_class = getattr(client_module, "DouYinClient", None)
    jsonl_class = getattr(store_impl, "DouyinJsonlStoreImplement", None)
    old_creator = getattr(crawler_class, "get_creators_and_videos", None)
    old_store = getattr(jsonl_class, "store_content", None)
    parse_creator = getattr(help_module, "parse_creator_info_from_url", None)
    update_work = getattr(store, "update_douyin_aweme", None)
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
        or not callable(parse_creator)
        or not callable(update_work)
        or client_class is None
        or jsonl_class is None
        or len(restricted_errors) != 1
        or len(feed_errors) != 1
        or getattr(old_creator, _MARKER, False)
        or getattr(old_store, _MARKER, False)
        or not callable(getattr(client_class, "get_user_aweme_posts", None))
        or not callable(getattr(client_class, "get_video_by_id", None))
    ):
        raise _failure()

    active_sec_user_id: str | None = None
    store_started = False

    async def store_with_identity(instance: object, content_item: object) -> Any:
        nonlocal store_started
        identity = _ACTIVE_IDENTITY.get()
        creator_fingerprint = _ACTIVE_CREATOR.get()
        if (
            identity is None
            or creator_fingerprint != state.creator_fingerprint_sha256
            or active_sec_user_id is None
            or not isinstance(content_item, dict)
            or DOUYIN_SCAN_IDENTITY_FIELD in content_item
            or content_item.get("aweme_id") != identity.aweme_id
        ):
            raise _failure()
        try:
            normalize_record(
                content_item,
                NormalizationContext(
                    Platform.DY,
                    active_sec_user_id,
                    active_sec_user_id,
                    state.upstream_sha,
                    datetime.now(UTC),
                ),
            )
        except RecordNormalizationError:
            raise _DouyinWorkRejected from None
        store_started = True
        return await old_store(
            instance,
            {
                **content_item,
                DOUYIN_SCAN_IDENTITY_FIELD: {
                    **identity.as_mapping(),
                    "creator_fingerprint_sha256": creator_fingerprint,
                },
            },
        )

    started = False

    async def bounded_creator(crawler: Any) -> None:
        nonlocal active_sec_user_id, started, store_started
        references = getattr(config, "DY_CREATOR_ID_LIST", None)
        if started or type(references) is not list or len(references) != 1 or type(references[0]) is not str:
            raise _failure()
        started = True
        creator_reference = references[0]
        if hashlib.sha256(creator_reference.encode("utf-8")).hexdigest() != state.creator_fingerprint_sha256:
            raise _failure()
        try:
            creator_info = parse_creator(creator_reference)
        except Exception as error:
            raise _failure() from error
        sec_user_id = getattr(creator_info, "sec_user_id", None)
        if (
            type(sec_user_id) is not str
            or _SEC_USER_ID.fullmatch(sec_user_id) is None
            or hashlib.sha256(sec_user_id.encode("utf-8")).hexdigest() != state.author_fingerprint_sha256
        ):
            raise _failure()
        active_sec_user_id = sec_user_id
        if (
            config.SAVE_DATA_OPTION != "jsonl"
            or config.ENABLE_GET_COMMENTS is not False
            or config.ENABLE_GET_MEIDAS is not False
            or config.ENABLE_IP_PROXY is not False
            or config.MAX_CONCURRENCY_NUM != 1
        ):
            raise _failure()
        client = crawler.dy_client
        if not isinstance(client, client_class):
            raise _failure()

        unit = DouyinScanUnit(state, manifest.max_items)
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
                        response = await client.get_user_aweme_posts(sec_user_id, action.cursor or "")
                except (*restricted_errors, *feed_errors):
                    # Any list-level fetch failure restricts the whole feed:
                    # a blocked body cannot be distinguished from a transient
                    # one, and neither may ever count as source end.
                    unit.observe_access_restricted()
                    continue
                except Exception as error:
                    raise _failure() from error
                page = parse_douyin_creator_page(response, input_cursor=action.cursor or "")
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
                    detail = await client.get_video_by_id(identity.aweme_id)
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
            detail_item = _validate_detail(detail, identity=identity, sec_user_id=sec_user_id)
            identity_token = _ACTIVE_IDENTITY.set(identity)
            creator_scope = _ACTIVE_CREATOR.set(state.creator_fingerprint_sha256)
            store_started = False
            try:
                with _suppress_upstream_logging(store):
                    await update_work(aweme_item=detail_item)
            except _DouyinWorkRejected:
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
        output = manifest.output_root / DOUYIN_SCAN_COVERAGE_FILENAME
        if manifest.output_root.is_symlink() or output.is_symlink():
            raise _failure()
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(coverage.to_json_line())

    setattr(bounded_creator, _MARKER, True)
    setattr(store_with_identity, _MARKER, True)
    cast(Any, crawler_class).get_creators_and_videos = bounded_creator
    cast(Any, jsonl_class).store_content = store_with_identity


__all__ = ["install_douyin_creator_capture_shim", "parse_douyin_creator_page"]
