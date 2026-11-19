"""Tieba bounded creator shim: page parsing privacy, restriction vs end, sealing."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import UUID

import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler.tieba_creator_capture import (
    install_tieba_creator_capture_shim,
    parse_tieba_creator_page,
)
from media_sync.integrations.mediacrawler.tieba_creator_work import (
    TB_SCAN_COVERAGE_FILENAME,
    TB_SCAN_IDENTITY_FIELD,
    TiebaScanCoverage,
    TiebaScanState,
)

ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000087")
PORTRAIT = "tb.1.abcdef0123456789abcdef0123456789"
CREATOR_URL = f"https://tieba.baidu.com/home/main?id={PORTRAIT}"
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"


class IPBlockError(RuntimeError):
    pass


class DataFetchError(RuntimeError):
    pass


class TiebaNote:
    def __init__(self, note_id: str) -> None:
        self.note_id = note_id
        self.note_url = f"https://tieba.baidu.com/p/{note_id}"
        self.title = f"thread-{note_id}"
        self.desc = f"body-{note_id}"
        self.publish_time = 1_788_235_200

    def model_dump(self) -> dict[str, object]:
        return {
            "note_id": self.note_id,
            "note_url": self.note_url,
            "title": self.title,
            "desc": self.desc,
            "publish_time": self.publish_time,
            "user_nickname": "creator",
        }


def _module(name: str, checkout: Path) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(checkout / (name.replace(".", "/") + ".py"))
    return module


def _thread_id(index: int) -> str:
    return f"{8100000000 + index}"


def _response(*indexes: int, has_more: bool = True, error_code: int = 0) -> dict[str, object]:
    return {
        "error_code": error_code,
        "data": {
            "has_more": 1 if has_more else 0,
            "list": [
                {"thread_info": {"tid": int(_thread_id(index)), "id": int(_thread_id(index))}} for index in indexes
            ],
        },
    }


def _install_modules(
    monkeypatch: pytest.MonkeyPatch,
    checkout: Path,
    output_root: Path,
    *,
    page: object,
) -> tuple[list[dict[str, object]], list[str]]:
    checkout.mkdir(parents=True, exist_ok=True)
    stored: list[dict[str, object]] = []
    detail_calls: list[str] = []

    class TieBaJsonlStoreImplement:
        async def store_content(self, content_item: dict[str, object]) -> None:
            stored.append(content_item)

    class BaiduTieBaClient:
        @staticmethod
        def _extract_creator_portrait(value: str) -> str:
            assert value == CREATOR_URL
            return PORTRAIT

        async def get_notes_by_creator_portrait(
            self, *, portrait: str, page_number: int, page_size: int = 20
        ) -> object:
            assert portrait == PORTRAIT
            assert page_number == 1
            assert page_size == 20
            if isinstance(page, BaseException):
                raise page
            return page

        async def get_note_by_id(self, note_id: str) -> TiebaNote:
            detail_calls.append(note_id)
            return TiebaNote(note_id)

        async def get_all_notes_by_creator_url(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("unbounded creator helper must be replaced")

    class TieBaCrawler:
        def __init__(self) -> None:
            self.tieba_client = BaiduTieBaClient()

        async def get_creators_and_notes(self) -> None:
            raise AssertionError("not used")

    core = _module("media_platform.tieba.core", checkout)
    core.TieBaCrawler = TieBaCrawler
    client = _module("media_platform.tieba.client", checkout)
    client.BaiduTieBaClient = BaiduTieBaClient
    logger = SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
        exception=lambda *_args, **_kwargs: None,
    )
    store = _module("store.tieba", checkout)
    store.utils = SimpleNamespace(logger=logger)
    client.utils = SimpleNamespace(logger=logger)

    async def update_tieba_note(note_item: object) -> None:
        payload = note_item.model_dump()
        await TieBaJsonlStoreImplement().store_content(payload)

    store.update_tieba_note = update_tieba_note
    store_impl = _module("store.tieba._store_impl", checkout)
    store_impl.TieBaJsonlStoreImplement = TieBaJsonlStoreImplement
    help_module = _module("media_platform.tieba.help", checkout)
    help_module.TieBaExtractor = type("TieBaExtractor", (), {})
    errors = _module("media_platform.tieba.exception", checkout)
    errors.IPBlockError = IPBlockError
    errors.DataFetchError = DataFetchError
    config = _module("config", checkout)
    config.TIEBA_CREATOR_URL_LIST = [CREATOR_URL]
    config.SAVE_DATA_OPTION = "jsonl"
    config.ENABLE_GET_COMMENTS = False
    config.ENABLE_IP_PROXY = False
    config.MAX_CONCURRENCY_NUM = 1
    modules = {
        "media_platform.tieba.core": core,
        "media_platform.tieba.client": client,
        "media_platform.tieba.help": help_module,
        "media_platform.tieba.exception": errors,
        "store.tieba": store,
        "store.tieba._store_impl": store_impl,
        "config": config,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return stored, detail_calls


def _manifest(output_root: Path) -> SimpleNamespace:
    author_sha = hashlib.sha256(PORTRAIT.encode()).hexdigest()
    creator_sha = hashlib.sha256(CREATOR_URL.encode()).hexdigest()
    state = TiebaScanState.initial(ACCOUNT_ID, author_sha, creator_sha, UPSTREAM_SHA)
    return SimpleNamespace(
        tieba_scan=state,
        platform=Platform.TIEBA,
        account_id=ACCOUNT_ID,
        author_remote_id_fingerprint_sha256=author_sha,
        creator_fingerprint_sha256=creator_sha,
        upstream_sha=UPSTREAM_SHA,
        max_items=20,
        request_delay_seconds=0.001,
        output_root=output_root,
    )


def test_page_parser_keeps_only_bounded_thread_identities() -> None:
    page = parse_tieba_creator_page(_response(1, 2, has_more=False), page=1)

    assert [identity.thread_id for identity in page.identities] == [_thread_id(1), _thread_id(2)]
    assert page.has_more is False
    serialized = json.dumps(page.as_mapping(), sort_keys=True)
    assert "thread-" not in serialized and "thread_info" not in serialized


@pytest.mark.parametrize(
    "payload",
    [
        {"error_code": 1, "data": {"has_more": 1, "list": []}},
        {"error_code": 0, "data": {"has_more": 2, "list": []}},
        {"error_code": 0, "data": {"has_more": 1, "list": "invalid"}},
        {"error_code": 0, "data": {"has_more": 1, "list": [{}]}},
        {"error_code": 0, "data": {"has_more": 1, "list": [{"thread_info": {"tid": 1, "id": 2}}]}},
        {
            "error_code": 0,
            "data": {
                "has_more": 1,
                "list": [{"thread_info": {"tid": 8100000001}}, {"thread_info": {"tid": 8100000001}}],
            },
        },
    ],
)
def test_page_parser_rejects_ambiguous_shapes(payload: object) -> None:
    with pytest.raises(RuntimeError, match="Tieba bounded"):
        parse_tieba_creator_page(payload, page=1)


def test_empty_page_is_a_page_not_a_drift() -> None:
    # An empty list is a valid page shape; the durable layer decides whether it
    # means an end, a stall or progress.
    page = parse_tieba_creator_page({"error_code": 0, "data": {"has_more": 1, "list": []}}, page=1)

    assert page.identities == ()
    assert page.has_more is True


def test_installed_shim_seals_coverage_and_reports_server_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    stored, detail_calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        page=_response(1, 2, has_more=False),
    )
    manifest = _manifest(output_root)
    previous = os.getcwd()
    os.chdir(tmp_path / "checkout")
    try:
        install_tieba_creator_capture_shim(manifest)  # type: ignore[arg-type]
        client_class = sys.modules["media_platform.tieba.client"].BaiduTieBaClient
        notes = asyncio.run(client_class().get_all_notes_by_creator_url(CREATOR_URL))
    finally:
        os.chdir(previous)

    assert [note.note_id for note in notes] == [_thread_id(1), _thread_id(2)]
    assert detail_calls == [_thread_id(1), _thread_id(2)]
    assert [item["note_id"] for item in stored] == [_thread_id(1), _thread_id(2)]
    assert all(TB_SCAN_IDENTITY_FIELD in item for item in stored)
    coverage = TiebaScanCoverage.from_json_line((output_root / TB_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8"))
    coverage.validate(
        manifest.tieba_scan,
        20,
        normalized_remote_ids=(_thread_id(1), _thread_id(2)),
    )
    assert coverage.stop_reason == "has_more_false"
    assert coverage.source_end_observed is True


def test_restricted_feed_is_not_source_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    _stored, _calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        page=DataFetchError("restricted"),
    )
    manifest = _manifest(output_root)
    previous = os.getcwd()
    os.chdir(tmp_path / "checkout")
    try:
        install_tieba_creator_capture_shim(manifest)  # type: ignore[arg-type]
        client_class = sys.modules["media_platform.tieba.client"].BaiduTieBaClient
        notes = asyncio.run(client_class().get_all_notes_by_creator_url(CREATOR_URL))
    finally:
        os.chdir(previous)

    assert notes == []
    coverage = TiebaScanCoverage.from_json_line((output_root / TB_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8"))
    assert coverage.stop_reason == "access_restricted"
    assert coverage.page is None
    assert coverage.source_end_observed is False
    assert coverage.next_state.head_boundary is None


def test_upstream_store_callback_does_not_double_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Upstream passes a store callback; the shim already stored those rows.

    `.upstream/MediaCrawler/media_platform/tieba/core.py:386-393` calls
    `get_all_notes_by_creator_url(..., callback=tieba_store.batch_update_tieba_notes)`
    and that callback is nothing but `for note in note_list: await
    update_tieba_note(note)` (`.upstream/.../store/tieba/__init__.py:51-63`).
    Invoking it would re-enter the guarded store with the identity ContextVar
    reset, aborting the unit before the coverage witness is sealed — so a run
    that reached the callback would persist rows and then fail with no receipt.
    """

    output_root = tmp_path / "output"
    output_root.mkdir()
    stored, detail_calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        page=_response(1, 2, has_more=False),
    )
    manifest = _manifest(output_root)
    replayed: list[str] = []

    async def upstream_callback(note_list: object) -> None:
        assert isinstance(note_list, list)
        for note in note_list:
            replayed.append(note.note_id)

    previous = os.getcwd()
    os.chdir(tmp_path / "checkout")
    try:
        install_tieba_creator_capture_shim(manifest)  # type: ignore[arg-type]
        client_class = sys.modules["media_platform.tieba.client"].BaiduTieBaClient
        notes = asyncio.run(client_class().get_all_notes_by_creator_url(CREATOR_URL, 0, upstream_callback, 20))
    finally:
        os.chdir(previous)

    assert [note.note_id for note in notes] == [_thread_id(1), _thread_id(2)]
    assert detail_calls == [_thread_id(1), _thread_id(2)]
    assert [item["note_id"] for item in stored] == [_thread_id(1), _thread_id(2)]
    assert replayed == []
    coverage = TiebaScanCoverage.from_json_line((output_root / TB_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8"))
    assert coverage.stop_reason == "has_more_false"
    coverage.validate(manifest.tieba_scan, 20)
