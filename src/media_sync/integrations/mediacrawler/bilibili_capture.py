"""Owned bounded Bili creator loop composed with the verified upstream runtime."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qs, urlsplit

from media_sync.integrations.mediacrawler.bilibili_media import parse_bilibili_view_pages
from media_sync.integrations.mediacrawler.bilibili_multifeed import BiliMultiFeedState, wrap_upload_coverage
from media_sync.integrations.mediacrawler.bilibili_scan import (
    BILI_SCAN_COVERAGE_FILENAME,
    BILI_SCAN_IDENTITY_FIELD,
    BILI_SCAN_PAGE_SIZE,
    BiliIdentity,
    BiliPage,
    BiliScanUnit,
)

if TYPE_CHECKING:
    from media_sync.integrations.mediacrawler.bridge import RunnerManifest

_MARKER = "__media_sync_bili_bounded_capture_v1__"
_ACTIVE_IDENTITY: ContextVar[BiliIdentity | None] = ContextVar("bili_bounded_identity", default=None)
_ACTIVE_AUTHOR: ContextVar[str | None] = ContextVar("bili_bounded_author_fingerprint", default=None)


def _failure() -> RuntimeError:
    return RuntimeError("Bilibili bounded capture contract failed")


def parse_bili_upload_page(value: object, *, page: int, creator_id: int) -> BiliPage:
    """Reduce a verified author-list response to a closed identity witness."""
    if not isinstance(value, dict):
        raise _failure()
    metadata = value.get("page")
    listing = value.get("list")
    if not isinstance(metadata, dict) or not isinstance(listing, dict):
        raise _failure()
    if (
        type(metadata.get("pn")) is not int
        or metadata["pn"] != page
        or type(metadata.get("ps")) is not int
        or metadata["ps"] != BILI_SCAN_PAGE_SIZE
    ):
        raise _failure()
    rows = listing.get("vlist")
    if type(rows) is not list or len(rows) > BILI_SCAN_PAGE_SIZE:
        raise _failure()
    identities: list[BiliIdentity] = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or type(row.get("mid")) is not int
            or row["mid"] != creator_id
            or type(row.get("aid")) is not int
        ):
            raise _failure()
        try:
            identities.append(BiliIdentity(str(row["aid"]), row.get("bvid", ""), row.get("created", 0)))
        except ValueError as error:
            raise _failure() from error
    try:
        return BiliPage(page, metadata.get("count", -1), tuple(identities))
    except ValueError as error:
        raise _failure() from error


def validate_bili_upload_detail(value: object, *, identity: BiliIdentity, creator_id: int) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("View"), dict):
        raise _failure()
    view = value["View"]
    owner = view.get("owner")
    if (
        type(view.get("aid")) is not int
        or str(view["aid"]) != identity.aid
        or view.get("bvid") != identity.bvid
        or type(view.get("pubdate")) is not int
        or view["pubdate"] != identity.pubdate
        or not isinstance(owner, dict)
        or type(owner.get("mid")) is not int
        or owner["mid"] != creator_id
        or not isinstance(view.get("stat"), dict)
    ):
        raise _failure()
    try:
        parse_bilibili_view_pages(view, expected_aid=identity.aid)
    except ValueError as error:
        raise _failure() from error


def _checkout_module(name: str, root: Path) -> Any:
    module = importlib.import_module(name)
    source = getattr(module, "__file__", None)
    if type(source) is not str or not Path(source).resolve().is_relative_to(root.resolve()):
        raise _failure()
    return module


def install_bilibili_capture_shim(manifest: RunnerManifest) -> None:
    """Install once after the page-identity shim, before upstream ``main.start``."""
    state = manifest.bili_scan
    if state is None or manifest.platform.value != "bili":
        raise _failure()
    state.require_binding(
        account_id=manifest.account_id,
        author_fingerprint_sha256=manifest.author_remote_id_fingerprint_sha256,
        upstream_sha=manifest.upstream_sha,
    )
    root = manifest.checkout_root
    core = _checkout_module("media_platform.bilibili.core", root)
    client_module = _checkout_module("media_platform.bilibili.client", root)
    store = _checkout_module("store.bilibili", root)
    store_impl = _checkout_module("store.bilibili._store_impl", root)
    config = _checkout_module("config", root)
    crawler_class = getattr(core, "BilibiliCrawler", None)
    client_class = getattr(client_module, "BilibiliClient", None)
    jsonl_class = getattr(store, "BiliJsonlStoreImplement", None)
    old_creator = getattr(crawler_class, "get_creator_videos", None)
    old_store = getattr(jsonl_class, "store_content", None)
    if (
        not callable(old_creator)
        or not callable(old_store)
        or client_class is None
        or jsonl_class is not getattr(store_impl, "BiliJsonlStoreImplement", None)
        or getattr(old_creator, _MARKER, False)
        or getattr(old_store, _MARKER, False)
    ):
        raise _failure()
    if (
        not callable(getattr(store, "update_bilibili_video", None))
        or not callable(getattr(client_class, "get_creator_videos", None))
        or not callable(getattr(client_class, "get_video_info", None))
    ):
        raise _failure()

    async def store_with_scan_identity(instance: object, content_item: object) -> Any:
        identity = _ACTIVE_IDENTITY.get()
        author_fingerprint = _ACTIVE_AUTHOR.get()
        if (
            identity is None
            or author_fingerprint != state.author_fingerprint_sha256
            or not isinstance(content_item, dict)
            or BILI_SCAN_IDENTITY_FIELD in content_item
            or content_item.get("video_id") != identity.aid
            or content_item.get("create_time") != identity.pubdate
        ):
            raise _failure()
        return await old_store(
            instance,
            {
                **content_item,
                BILI_SCAN_IDENTITY_FIELD: {**identity.as_mapping(), "author_fingerprint_sha256": author_fingerprint},
            },
        )

    started = False

    async def bounded_creator(crawler: Any, creator_id: int) -> None:
        nonlocal started
        if (
            started
            or type(creator_id) is not int
            or not 0 < creator_id <= 2**63 - 1
            or hashlib.sha256(str(creator_id).encode("utf-8")).hexdigest() != state.author_fingerprint_sha256
        ):
            raise _failure()
        started = True
        if (
            config.SAVE_DATA_OPTION != "jsonl"
            or config.CREATOR_MODE is not True
            or config.ENABLE_GET_COMMENTS is not False
            or config.ENABLE_GET_SUB_COMMENTS is not False
            or config.ENABLE_GET_MEIDAS is not False
            or config.ENABLE_GET_MEDIAS is not False
            or config.ENABLE_IP_PROXY is not False
        ):
            raise _failure()
        client = crawler.bili_client
        if not isinstance(client, client_class):
            raise _failure()
        if isinstance(state, BiliMultiFeedState) and state.next_feed == "dynamics":
            from media_sync.integrations.mediacrawler.bilibili_dynamic_capture import capture_dynamic_unit

            async def store_video(detail: Any, identity: BiliIdentity) -> None:
                token = _ACTIVE_IDENTITY.set(identity)
                author_token = _ACTIVE_AUTHOR.set(state.author_fingerprint_sha256)
                try:
                    await store.update_bilibili_video(detail)
                finally:
                    _ACTIVE_AUTHOR.reset(author_token)
                    _ACTIVE_IDENTITY.reset(token)

            dynamic_coverage = await capture_dynamic_unit(manifest, client, creator_id, store_video)
            output = manifest.output_root / BILI_SCAN_COVERAGE_FILENAME
            if manifest.output_root.is_symlink() or output.is_symlink():
                raise _failure()
            with output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(dynamic_coverage.to_json_line())
            return
        upload_state = state.uploads if isinstance(state, BiliMultiFeedState) else state
        unit = BiliScanUnit(upload_state, manifest.max_items)
        original_request = client.request
        list_attempts = detail_attempts = 0
        nav_attempts = 0
        nav_in_list = False
        requested = False
        expected_kind: str | None = None
        expected_page: int | None = None
        expected_identity: BiliIdentity | None = None

        async def guarded_request(method: str, url: str, **kwargs: Any) -> Any:
            nonlocal list_attempts, detail_attempts, nav_attempts, nav_in_list, requested
            parsed = urlsplit(url)
            if method != "GET" or parsed.scheme != "https" or parsed.netloc != "api.bilibili.com" or parsed.fragment:
                raise _failure()
            query = parse_qs(parsed.query, keep_blank_values=True)
            if any(len(values) != 1 for values in query.values()):
                raise _failure()
            if parsed.path == "/x/space/wbi/arc/search":
                if (
                    expected_kind != "list"
                    or list_attempts >= 2
                    or query.get("mid") != [str(creator_id)]
                    or query.get("pn") != [str(expected_page)]
                    or query.get("ps") != [str(BILI_SCAN_PAGE_SIZE)]
                    or query.get("order") != ["pubdate"]
                    or set(query) != {"mid", "pn", "ps", "order", "wts", "w_rid"}
                ):
                    raise _failure()
                list_attempts += 1
            elif parsed.path == "/x/web-interface/view/detail":
                if (
                    expected_kind != "detail"
                    or expected_identity is None
                    or detail_attempts >= min(manifest.max_items, BILI_SCAN_PAGE_SIZE)
                    or query != {"bvid": [expected_identity.bvid]}
                ):
                    raise _failure()
                detail_attempts += 1
            elif parsed.path != "/x/web-interface/nav" or query or expected_kind != "list":
                # The locked WBI signer may refresh its key. No other API is permitted.
                raise _failure()
            else:
                if nav_in_list or nav_attempts >= 2:
                    raise _failure()
                nav_in_list = True
                nav_attempts += 1
            if requested:
                await asyncio.sleep(manifest.request_delay_seconds or 0)
            requested = True
            return await original_request(method=method, url=url, **kwargs)

        client.request = guarded_request
        try:
            while (action := unit.next_action()).kind != "stop":
                expected_kind = action.kind
                expected_page = action.page
                expected_identity = action.identity
                if action.kind == "list":
                    nav_in_list = False
                    response = await client.get_creator_videos(
                        str(creator_id), action.page, BILI_SCAN_PAGE_SIZE, order_mode="pubdate"
                    )
                    if action.page is None:
                        raise _failure()
                    unit.observe_page(parse_bili_upload_page(response, page=action.page, creator_id=creator_id))
                else:
                    identity = action.identity
                    if identity is None:
                        raise _failure()
                    detail = await client.get_video_info(bvid=identity.bvid)
                    validate_bili_upload_detail(detail, identity=identity, creator_id=creator_id)
                    token = _ACTIVE_IDENTITY.set(identity)
                    author_token = _ACTIVE_AUTHOR.set(
                        hashlib.sha256(str(detail["View"]["owner"]["mid"]).encode("utf-8")).hexdigest()
                    )
                    try:
                        await store.update_bilibili_video(detail)
                    finally:
                        _ACTIVE_AUTHOR.reset(author_token)
                        _ACTIVE_IDENTITY.reset(token)
                    unit.consume(identity)
            coverage = unit.coverage()
            if (list_attempts, detail_attempts) != (coverage.list_attempts, coverage.detail_attempts):
                raise _failure()
            coverage.validate(upload_state, manifest.max_items)
            output = manifest.output_root / BILI_SCAN_COVERAGE_FILENAME
            if manifest.output_root.is_symlink() or output.is_symlink():
                raise _failure()
            with output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(
                    wrap_upload_coverage(state, coverage).to_json_line()
                    if isinstance(state, BiliMultiFeedState)
                    else coverage.to_json_line()
                )
        finally:
            client.request = original_request

    setattr(bounded_creator, _MARKER, True)
    setattr(store_with_scan_identity, _MARKER, True)
    cast(Any, crawler_class).get_creator_videos = bounded_creator
    cast(Any, jsonl_class).store_content = store_with_scan_identity
