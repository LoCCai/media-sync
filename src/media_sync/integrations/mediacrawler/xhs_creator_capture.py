"""Owned one-page XHS creator loop composed with the pinned upstream runtime."""

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
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler.normalizers import (
    NormalizationContext,
    RecordNormalizationError,
    normalize_record,
)
from media_sync.integrations.mediacrawler.xhs_creator_notes import (
    XHS_CREATOR_PAGE_SIZE,
    XHS_SCAN_COVERAGE_FILENAME,
    XHS_SCAN_IDENTITY_FIELD,
    XhsCreatorPage,
    XhsNoteIdentity,
    XhsScanUnit,
)

if TYPE_CHECKING:
    from media_sync.integrations.mediacrawler.bridge import RunnerManifest

_MARKER = "__media_sync_xhs_creator_capture_v1__"
_ACTIVE_IDENTITY: ContextVar[XhsNoteIdentity | None] = ContextVar("xhs_creator_note_identity", default=None)
_ACTIVE_CREATOR: ContextVar[str | None] = ContextVar("xhs_creator_reference_fingerprint", default=None)
_TOKEN = re.compile(r"[^\x00-\x20\x7f]{1,2048}\Z")
_SOURCE = re.compile(r"[A-Za-z0-9_]{1,64}\Z", re.ASCII)
_XHS_ID = re.compile(r"[0-9a-f]{24}\Z")


class _XhsNoteRejected(RuntimeError):
    pass


def _failure() -> RuntimeError:
    return RuntimeError("XHS bounded creator-note contract failed")


def _checkout_module(name: str, root: Path) -> Any:
    module = importlib.import_module(name)
    source = getattr(module, "__file__", None)
    if type(source) is not str or not Path(source).resolve().is_relative_to(root.resolve()):
        raise _failure()
    return module


def _bounded_token(value: object) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise _failure()
    return value


def _bounded_source(value: object) -> str:
    if type(value) is not str or _SOURCE.fullmatch(value) is None:
        raise _failure()
    return value


def parse_xhs_creator_page(value: object, *, input_cursor: str) -> tuple[XhsCreatorPage, dict[str, str]]:
    """Reduce one upstream list response while returning tokens only in memory."""

    if not isinstance(value, dict):
        raise _failure()
    has_more = value.get("has_more")
    next_cursor = value.get("cursor")
    notes = value.get("notes")
    if type(has_more) is not bool or type(next_cursor) is not str or type(notes) is not list:
        raise _failure()
    if len(notes) > XHS_CREATOR_PAGE_SIZE:
        raise _failure()
    identities: list[XhsNoteIdentity] = []
    tokens: dict[str, str] = {}
    for note in notes:
        if not isinstance(note, dict):
            raise _failure()
        note_id = note.get("note_id")
        if type(note_id) is not str or _XHS_ID.fullmatch(note_id) is None or note_id in tokens:
            raise _failure()
        token = _bounded_token(note.get("xsec_token"))
        source = _bounded_source(note.get("xsec_source"))
        try:
            listing = json.dumps(
                {key: item for key, item in note.items() if key not in {"xsec_token", "xsec_source"}},
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise _failure() from None
        tokens[note_id] = token
        identities.append(
            XhsNoteIdentity(
                note_id,
                hashlib.sha256(listing).hexdigest(),
                hashlib.sha256(token.encode("utf-8")).hexdigest(),
                source,
            )
        )
    try:
        return XhsCreatorPage(input_cursor, next_cursor, has_more, tuple(identities)), tokens
    except ValueError as error:
        raise _failure() from error


def _validate_detail(value: object, *, identity: XhsNoteIdentity, creator_id: str) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or value.get("note_id") != identity.note_id
        or value.get("type")
        not in {
            "normal",
            "video",
        }
    ):
        raise _failure()
    user = value.get("user")
    if not isinstance(user, dict) or user.get("user_id") != creator_id:
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


def install_xhs_creator_capture_shim(manifest: RunnerManifest, checkout_root: Path) -> None:
    """Replace only the XHS creator method with one replayable page-bound unit."""

    state = manifest.xhs_scan
    if state is None or manifest.platform.value != "xhs":
        raise _failure()
    state.require_binding(
        account_id=manifest.account_id,
        author_fingerprint_sha256=manifest.author_remote_id_fingerprint_sha256,
        creator_fingerprint_sha256=manifest.creator_fingerprint_sha256,
        upstream_sha=manifest.upstream_sha,
    )
    root = Path(checkout_root)
    core = _checkout_module("media_platform.xhs.core", root)
    client_module = _checkout_module("media_platform.xhs.client", root)
    store = _checkout_module("store.xhs", root)
    store_impl = _checkout_module("store.xhs._store_impl", root)
    help_module = _checkout_module("media_platform.xhs.help", root)
    exception_module = _checkout_module("media_platform.xhs.exception", root)
    config = _checkout_module("config", root)

    crawler_class = getattr(core, "XiaoHongShuCrawler", None)
    client_class = getattr(client_module, "XiaoHongShuClient", None)
    jsonl_class = getattr(store, "XhsJsonlStoreImplement", None)
    old_creator = getattr(crawler_class, "get_creators_and_notes", None)
    old_store = getattr(jsonl_class, "store_content", None)
    parse_creator = getattr(help_module, "parse_creator_info_from_url", None)
    restricted_errors = tuple(
        error
        for name in ("IPBlockError", "PlatformAccessError")
        for error in (getattr(exception_module, name, None),)
        if isinstance(error, type) and issubclass(error, BaseException)
    )
    ordinary_errors = tuple(
        error
        for name in ("DataFetchError", "NoteNotFoundError")
        for error in (getattr(exception_module, name, None),)
        if isinstance(error, type) and issubclass(error, BaseException)
    )
    if (
        not callable(old_creator)
        or not callable(old_store)
        or not callable(parse_creator)
        or client_class is None
        or jsonl_class is not getattr(store_impl, "XhsJsonlStoreImplement", None)
        or len(restricted_errors) != 2
        or len(ordinary_errors) != 2
        or getattr(old_creator, _MARKER, False)
        or getattr(old_store, _MARKER, False)
        or not callable(getattr(client_class, "get_notes_by_creator", None))
        or not callable(getattr(client_class, "get_note_by_id", None))
        or not callable(getattr(client_class, "get_note_by_id_from_html", None))
        or not callable(getattr(store, "update_xhs_note", None))
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
            or XHS_SCAN_IDENTITY_FIELD in content_item
            or content_item.get("note_id") != identity.note_id
            or type(content_item.get("xsec_token")) is not str
            or hashlib.sha256(content_item["xsec_token"].encode("utf-8")).hexdigest() != identity.token_sha256
        ):
            raise _failure()
        try:
            normalize_record(
                content_item,
                NormalizationContext(
                    Platform.XHS,
                    active_creator_id,
                    active_creator_id,
                    state.upstream_sha,
                    datetime.now(UTC),
                ),
            )
        except RecordNormalizationError:
            raise _XhsNoteRejected from None
        store_started = True
        return await old_store(
            instance,
            {
                **content_item,
                XHS_SCAN_IDENTITY_FIELD: {
                    **identity.as_mapping(),
                    "creator_fingerprint_sha256": creator_fingerprint,
                },
            },
        )

    started = False

    async def bounded_creator(crawler: Any) -> None:
        nonlocal active_creator_id, started, store_started
        references = getattr(config, "XHS_CREATOR_URL_LIST", None)
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
        creator_id = getattr(creator_info, "user_id", None)
        creator_token = getattr(creator_info, "xsec_token", None)
        creator_source = getattr(creator_info, "xsec_source", None)
        if (
            type(creator_id) is not str
            or _XHS_ID.fullmatch(creator_id) is None
            or hashlib.sha256(creator_id.encode("utf-8")).hexdigest() != state.author_fingerprint_sha256
        ):
            raise _failure()
        active_creator_id = creator_id
        creator_token = _bounded_token(creator_token)
        creator_source = _bounded_source(creator_source)
        if (
            config.SAVE_DATA_OPTION != "jsonl"
            or config.CREATOR_MODE is not True
            or config.ENABLE_GET_COMMENTS is not False
            or config.ENABLE_GET_SUB_COMMENTS is not False
            or config.ENABLE_GET_MEIDAS is not False
            or config.ENABLE_GET_MEDIAS is not False
            or config.ENABLE_IP_PROXY is not False
            or config.MAX_CONCURRENCY_NUM != 1
        ):
            raise _failure()
        client = crawler.xhs_client
        if not isinstance(client, client_class):
            raise _failure()

        unit = XhsScanUnit(state, manifest.max_items)
        tokens: dict[str, str] = {}
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
                            action.cursor,
                            page_size=XHS_CREATOR_PAGE_SIZE,
                            xsec_token=creator_token,
                            xsec_source=creator_source,
                        )
                except restricted_errors:
                    unit.observe_access_restricted()
                    continue
                except Exception as error:
                    raise _failure() from error
                page, tokens = parse_xhs_creator_page(response, input_cursor=action.cursor or "")
                unit.observe_page(page)
                continue

            identity = action.identity
            if identity is None:
                raise _failure()
            if action.kind == "unchanged":
                unit.skip_unchanged(identity)
                continue
            token = tokens.get(identity.note_id)
            if token is None or hashlib.sha256(token.encode("utf-8")).hexdigest() != identity.token_sha256:
                raise _failure()
            detail: object = None
            restricted = False
            try:
                await pace()
                with _suppress_upstream_logging(core):
                    detail = await client.get_note_by_id(identity.note_id, identity.xsec_source, token)
            except restricted_errors:
                restricted = True
            except ordinary_errors:
                detail = None
            except Exception:
                detail = None
            if not restricted and not detail:
                try:
                    await pace()
                    with _suppress_upstream_logging(core):
                        detail = await client.get_note_by_id_from_html(
                            identity.note_id,
                            identity.xsec_source,
                            token,
                            enable_cookie=True,
                        )
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
            detail_item = _validate_detail(detail, identity=identity, creator_id=creator_id)
            detail_item.update({"xsec_token": token, "xsec_source": identity.xsec_source})
            identity_token = _ACTIVE_IDENTITY.set(identity)
            creator_scope = _ACTIVE_CREATOR.set(state.creator_fingerprint_sha256)
            store_started = False
            try:
                with _suppress_upstream_logging(store):
                    await store.update_xhs_note(detail_item)
            except _XhsNoteRejected:
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
        output = manifest.output_root / XHS_SCAN_COVERAGE_FILENAME
        if manifest.output_root.is_symlink() or output.is_symlink():
            raise _failure()
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(coverage.to_json_line())

    setattr(bounded_creator, _MARKER, True)
    setattr(store_with_identity, _MARKER, True)
    cast(Any, crawler_class).get_creators_and_notes = bounded_creator
    cast(Any, jsonl_class).store_content = store_with_identity


__all__ = ["install_xhs_creator_capture_shim", "parse_xhs_creator_page"]
