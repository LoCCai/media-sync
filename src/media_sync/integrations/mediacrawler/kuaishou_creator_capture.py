"""Owned one-page Kuaishou creator loop composed with the pinned upstream runtime.

The signed list channel is the only signed surface: the shim names
``get_video_by_creater_v2`` (client.py:161-170, served by
``request_rest_v2_signed`` client.py:117-159) and passes the verbatim
``pcursor``; the ``__NS_hxfalcon`` signature is captured from the live page
realm inside the client, regenerated per attempt (client.py:130), and never
enters this module — offline construction or caching of a signature is an
explicit non-goal.  Details ride the unsigned GraphQL channel
(``get_video_info`` client.py:243-254 over ``post()``/``request()``
client.py:88-92, 68-78) and must never carry or require signature material.
List-level failures mirror the exception-free upstream loop
(client.py:416-448): a falsy body, a business ``result != 1``, a
``DataFetchError``/``IPBlockError`` or any transport-level failure records
``access_restricted`` and is never source end, while a failed detail isolates
that one work only.
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
from media_sync.integrations.mediacrawler.kuaishou_creator_work import (
    KUAISHOU_SCAN_COVERAGE_FILENAME,
    KUAISHOU_SCAN_IDENTITY_FIELD,
    KuaishouCreatorPage,
    KuaishouScanUnit,
    KuaishouWorkIdentity,
)
from media_sync.integrations.mediacrawler.normalizers import (
    NormalizationContext,
    RecordNormalizationError,
    normalize_record,
)

if TYPE_CHECKING:
    from media_sync.integrations.mediacrawler.bridge import RunnerManifest

_MARKER = "__media_sync_kuaishou_creator_capture_v1__"
_ACTIVE_IDENTITY: ContextVar[KuaishouWorkIdentity | None] = ContextVar("kuaishou_work_identity", default=None)
_ACTIVE_CREATOR: ContextVar[str | None] = ContextVar("kuaishou_creator_reference_fingerprint", default=None)
_USER_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z", re.ASCII)


class _KuaishouWorkRejected(RuntimeError):
    pass


def _failure() -> RuntimeError:
    return RuntimeError("Kuaishou bounded creator-work contract failed")


def _checkout_module(name: str, root: Path) -> Any:
    module = importlib.import_module(name)
    source = getattr(module, "__file__", None)
    if type(source) is not str or not Path(source).resolve().is_relative_to(root.resolve()):
        raise _failure()
    return module


def parse_kuaishou_creator_page(value: object, *, input_cursor: str) -> KuaishouCreatorPage:
    """Reduce one upstream ``/rest/v/profile/feed`` list response to bounded identities."""

    if not isinstance(value, dict):
        raise _failure()
    result = value.get("result")
    next_cursor = value.get("pcursor")
    works = value.get("feeds")
    if type(result) is not int or result != 1:
        # A business rejection (client.py:426-432) is not a page and must
        # never be reduced into pagination progress.
        raise _failure()
    if type(next_cursor) is not str or type(works) is not list:
        raise _failure()
    identities: list[KuaishouWorkIdentity] = []
    for work in works:
        if not isinstance(work, dict):
            raise _failure()
        photo = work.get("photo")
        if not isinstance(photo, dict):
            raise _failure()
        photo_id = photo.get("id")
        if type(photo_id) is not str or _USER_ID.fullmatch(photo_id) is None:
            raise _failure()
        if any(item.photo_id == photo_id for item in identities):
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
        identities.append(KuaishouWorkIdentity(photo_id, hashlib.sha256(listing).hexdigest()))
    try:
        return KuaishouCreatorPage(input_cursor, next_cursor, tuple(identities))
    except ValueError as error:
        raise _failure() from error


def _validate_detail(value: object, *, identity: KuaishouWorkIdentity, user_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _failure()
    detail = value.get("visionVideoDetail")
    if not isinstance(detail, dict):
        raise _failure()
    photo = detail.get("photo")
    if not isinstance(photo, dict) or photo.get("id") != identity.photo_id:
        raise _failure()
    author = detail.get("author")
    if not isinstance(author, dict) or author.get("id") != user_id:
        raise _failure()
    return detail


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


def install_kuaishou_creator_capture_shim(manifest: RunnerManifest) -> None:
    """Replace only the Kuaishou creator method with one replayable page-bound unit.

    The child process has already validated the checkout and changed its
    working directory into it, so the shim anchors every filesystem access
    on the process working directory and never re-derives a root from
    manifest fields.  Authority details (creator reference, cookies, the
    page signing realm) stay in this subprocess's memory only.
    """

    state = manifest.kuaishou_scan
    if state is None or manifest.platform.value != "ks":
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
    core = _checkout_module("media_platform.kuaishou.core", root)
    client_module = _checkout_module("media_platform.kuaishou.client", root)
    store = _checkout_module("store.kuaishou", root)
    store_impl = _checkout_module("store.kuaishou._store_impl", root)
    help_module = _checkout_module("media_platform.kuaishou.help", root)
    exception_module = _checkout_module("media_platform.kuaishou.exception", root)
    config = _checkout_module("config", root)
    crawler_class = getattr(core, "KuaishouCrawler", None)
    client_class = getattr(client_module, "KuaiShouClient", None)
    jsonl_class = getattr(store_impl, "KuaishouJsonlStoreImplement", None)
    old_creator = getattr(crawler_class, "get_creators_and_videos", None)
    old_store = getattr(jsonl_class, "store_content", None)
    parse_creator = getattr(help_module, "parse_creator_info_from_url", None)
    update_work = getattr(store, "update_kuaishou_video", None)
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
        or not callable(getattr(client_class, "get_video_by_creater_v2", None))
        or not callable(getattr(client_class, "get_video_info", None))
    ):
        raise _failure()

    active_user_id: str | None = None
    store_started = False

    async def store_with_identity(instance: object, content_item: object) -> Any:
        nonlocal store_started
        identity = _ACTIVE_IDENTITY.get()
        creator_fingerprint = _ACTIVE_CREATOR.get()
        if (
            identity is None
            or creator_fingerprint != state.creator_fingerprint_sha256
            or active_user_id is None
            or not isinstance(content_item, dict)
            or KUAISHOU_SCAN_IDENTITY_FIELD in content_item
            or content_item.get("video_id") != identity.photo_id
        ):
            raise _failure()
        try:
            normalize_record(
                content_item,
                NormalizationContext(
                    Platform.KS,
                    active_user_id,
                    active_user_id,
                    state.upstream_sha,
                    datetime.now(UTC),
                ),
            )
        except RecordNormalizationError:
            raise _KuaishouWorkRejected from None
        store_started = True
        return await old_store(
            instance,
            {
                **content_item,
                KUAISHOU_SCAN_IDENTITY_FIELD: {
                    **identity.as_mapping(),
                    "creator_fingerprint_sha256": creator_fingerprint,
                },
            },
        )

    started = False

    async def bounded_creator(crawler: Any) -> None:
        nonlocal active_user_id, started, store_started
        references = getattr(config, "KS_CREATOR_ID_LIST", None)
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
        user_id = getattr(creator_info, "user_id", None)
        if (
            type(user_id) is not str
            or _USER_ID.fullmatch(user_id) is None
            or hashlib.sha256(user_id.encode("utf-8")).hexdigest() != state.author_fingerprint_sha256
        ):
            raise _failure()
        active_user_id = user_id
        if (
            config.SAVE_DATA_OPTION != "jsonl"
            or config.ENABLE_GET_COMMENTS is not False
            or config.ENABLE_GET_MEIDAS is not False
            or config.ENABLE_IP_PROXY is not False
            or config.MAX_CONCURRENCY_NUM != 1
        ):
            raise _failure()
        client = crawler.ks_client
        if not isinstance(client, client_class):
            raise _failure()

        unit = KuaishouScanUnit(state, manifest.max_items)
        requested = False

        async def pace() -> None:
            nonlocal requested
            if requested:
                await asyncio.sleep(manifest.request_delay_seconds or 0)
            requested = True

        while (action := unit.next_action()).kind != "stop":
            if action.kind == "list":
                # Only list requests are signed, and the signature is
                # captured from the live page realm inside the client
                # (client.py:117-159); it never reaches this module.
                try:
                    await pace()
                    with _suppress_upstream_logging(core):
                        response = await client.get_video_by_creater_v2(user_id, action.cursor or "")
                except (*restricted_errors, *feed_errors):
                    unit.observe_access_restricted()
                    continue
                except Exception:
                    # Any transport-level failure (httpx error, unparseable
                    # JSON body, proxy-refresh error) aborts the
                    # exception-free upstream loop (client.py:416-448): the
                    # feed is restricted and never source end.
                    unit.observe_access_restricted()
                    continue
                if not isinstance(response, dict) or response.get("result") != 1:
                    # A banned falsy body or a business rejection
                    # (client.py:418-422, 426-432) restricts the feed; it can
                    # never be reduced into pagination progress.
                    unit.observe_access_restricted()
                    continue
                page = parse_kuaishou_creator_page(response, input_cursor=action.cursor or "")
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
                    # Detail requests ride the unsigned GraphQL channel and
                    # carry no __NS_hxfalcon material (client.py:243-254,
                    # 88-92).
                    detail = await client.get_video_info(identity.photo_id)
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
            detail_item = _validate_detail(detail, identity=identity, user_id=user_id)
            identity_token = _ACTIVE_IDENTITY.set(identity)
            creator_scope = _ACTIVE_CREATOR.set(state.creator_fingerprint_sha256)
            store_started = False
            try:
                with _suppress_upstream_logging(store):
                    await update_work(video_item=detail_item)
            except _KuaishouWorkRejected:
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
        output = manifest.output_root / KUAISHOU_SCAN_COVERAGE_FILENAME
        if manifest.output_root.is_symlink() or output.is_symlink():
            raise _failure()
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(coverage.to_json_line())

    setattr(bounded_creator, _MARKER, True)
    setattr(store_with_identity, _MARKER, True)
    cast(Any, crawler_class).get_creators_and_videos = bounded_creator
    cast(Any, jsonl_class).store_content = store_with_identity


__all__ = ["install_kuaishou_creator_capture_shim", "parse_kuaishou_creator_page"]
