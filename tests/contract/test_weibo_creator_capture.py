"""Weibo bounded creator shim: page parsing privacy, restriction vs end, sealing."""

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
from media_sync.integrations.mediacrawler.weibo_creator_capture import (
    install_weibo_creator_capture_shim,
    parse_weibo_creator_page,
)
from media_sync.integrations.mediacrawler.weibo_creator_work import (
    WB_SCAN_COVERAGE_FILENAME,
    WB_SCAN_IDENTITY_FIELD,
    WeiboScanCoverage,
    WeiboScanState,
)

ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000085")
CREATOR_ID = "5123456789012345"
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"


class IPBlockError(RuntimeError):
    pass


class DataFetchError(RuntimeError):
    pass


def _module(name: str, checkout: Path) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(checkout / (name.replace(".", "/") + ".py"))
    return module


def _note_id(index: int) -> str:
    return f"{5100000000000000 + index}"


def _page(
    *indexes: int,
    since_id: str = "page-2",
    total: int | None = 100,
    card_type: int = 9,
) -> dict[str, object]:
    return {
        "cardlistInfo": {"since_id": since_id, "total": total},
        "cards": [
            {
                "card_type": card_type,
                "mblog": {
                    "id": _note_id(index),
                    "text": f"note-{index}",
                    "user": {"id": CREATOR_ID},
                },
            }
            for index in indexes
        ],
    }


def _install_modules(
    monkeypatch: pytest.MonkeyPatch,
    checkout: Path,
    output_root: Path,
    *,
    list_result: object,
    detail_failure: int | None = None,
) -> tuple[type, list[dict[str, object]], list[str]]:
    checkout.mkdir(parents=True, exist_ok=True)
    stored: list[dict[str, object]] = []
    detail_calls: list[str] = []

    class WeiboJsonlStoreImplement:
        async def store_content(self, content_item: dict[str, object]) -> None:
            stored.append(content_item)

    class WeiboClient:
        async def get_notes_by_creator(self, creator_id: str, container_id: str, since_id: str = "0") -> object:
            assert creator_id == CREATOR_ID
            assert container_id == f"107603{CREATOR_ID}"
            assert since_id == ""
            if isinstance(list_result, BaseException):
                raise list_result
            return list_result

        async def get_note_info_by_id(self, note_id: str) -> dict[str, object]:
            detail_calls.append(note_id)
            if detail_failure is not None and note_id == _note_id(detail_failure):
                raise DataFetchError
            return {
                "mblog": {
                    "id": note_id,
                    "text": f"note-{note_id}",
                    "user": {"id": CREATOR_ID},
                }
            }

    class WeiboCrawler:
        def __init__(self) -> None:
            self.wb_client = WeiboClient()

        async def get_creators_and_notes(self) -> None:
            raise AssertionError("unbounded creator helper must be replaced")

    core = _module("media_platform.weibo.core", checkout)
    core.WeiboCrawler = WeiboCrawler
    client = _module("media_platform.weibo.client", checkout)
    client.WeiboClient = WeiboClient
    logger = SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
        exception=lambda *_args, **_kwargs: None,
    )
    store = _module("store.weibo", checkout)
    store.utils = SimpleNamespace(logger=logger)
    core.utils = SimpleNamespace(logger=logger)

    async def update_weibo_note(note_item: dict[str, object]) -> None:
        mblog = note_item["mblog"]
        assert isinstance(mblog, dict)
        await WeiboJsonlStoreImplement().store_content(
            {
                "note_id": mblog["id"],
                "content": mblog.get("text", ""),
                "create_time": 1_788_235_200,
                "creator_hash": "untrusted",
                "nickname": "untrusted",
                "liked_count": "0",
                "comments_count": "0",
                "shared_count": "0",
                "note_url": f"https://m.weibo.cn/detail/{mblog['id']}",
            }
        )

    store.update_weibo_note = update_weibo_note
    store_impl = _module("store.weibo._store_impl", checkout)
    store_impl.WeiboJsonlStoreImplement = WeiboJsonlStoreImplement
    errors = _module("media_platform.weibo.exception", checkout)
    errors.IPBlockError = IPBlockError
    errors.DataFetchError = DataFetchError
    config = _module("config", checkout)
    config.WEIBO_CREATOR_ID_LIST = [CREATOR_ID]
    config.SAVE_DATA_OPTION = "jsonl"
    config.ENABLE_GET_COMMENTS = False
    config.ENABLE_IP_PROXY = False
    config.MAX_CONCURRENCY_NUM = 1
    modules = {
        "media_platform.weibo.core": core,
        "media_platform.weibo.client": client,
        "media_platform.weibo.exception": errors,
        "store.weibo": store,
        "store.weibo._store_impl": store_impl,
        "config": config,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return WeiboCrawler, stored, detail_calls


def _manifest(output_root: Path) -> SimpleNamespace:
    author_sha = hashlib.sha256(CREATOR_ID.encode()).hexdigest()
    creator_sha = hashlib.sha256(CREATOR_ID.encode()).hexdigest()
    state = WeiboScanState.initial(ACCOUNT_ID, author_sha, creator_sha, UPSTREAM_SHA)
    return SimpleNamespace(
        weibo_scan=state,
        platform=Platform.WB,
        account_id=ACCOUNT_ID,
        author_remote_id_fingerprint_sha256=author_sha,
        creator_fingerprint_sha256=creator_sha,
        upstream_sha=UPSTREAM_SHA,
        max_items=10,
        request_delay_seconds=0.001,
        output_root=output_root,
    )


def test_page_parser_keeps_only_card_type_nine_identities() -> None:
    response = _page(1, 2, since_id="next", total=42)
    assert isinstance(response["cards"], list)
    response["cards"].append({"card_type": 5, "title": "not a note"})

    page = parse_weibo_creator_page(response, input_since_id="")

    assert [identity.note_id for identity in page.identities] == [_note_id(1), _note_id(2)]
    assert page.next_since_id == "next"
    assert page.declared_total == 42
    serialized = json.dumps(page.as_mapping(), sort_keys=True)
    assert "note-1" not in serialized and "mblog" not in serialized


@pytest.mark.parametrize(
    "payload",
    [
        {"cardlistInfo": {"since_id": "x", "total": 1}},
        {"cards": [], "cardlistInfo": "invalid"},
        {"cards": "invalid", "cardlistInfo": {"since_id": "x"}},
        {"cards": [{"card_type": 9, "mblog": {"id": "short"}}], "cardlistInfo": {"since_id": "x"}},
        {"cards": [{"card_type": 9}], "cardlistInfo": {"since_id": "x"}},
        {"cards": [], "cardlistInfo": {"since_id": "x", "total": -1}},
        {"cards": [], "cardlistInfo": {"since_id": 7}},
    ],
)
def test_page_parser_rejects_ambiguous_shapes(payload: object) -> None:
    with pytest.raises(RuntimeError, match="Weibo bounded"):
        parse_weibo_creator_page(payload, input_since_id="")


def test_installed_shim_seals_coverage_and_isolates_detail_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    crawler_type, stored, detail_calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        list_result=_page(1, 2, 3, since_id="next", total=10),
        detail_failure=2,
    )
    manifest = _manifest(output_root)
    previous = os.getcwd()
    os.chdir(tmp_path / "checkout")
    try:
        install_weibo_creator_capture_shim(manifest)  # type: ignore[arg-type]
    finally:
        os.chdir(previous)
    asyncio.run(crawler_type().get_creators_and_notes())

    assert [item["note_id"] for item in stored] == [_note_id(1), _note_id(3)]
    assert sorted(detail_calls) == sorted(_note_id(index) for index in (1, 2, 3))
    assert all(WB_SCAN_IDENTITY_FIELD in item for item in stored)
    coverage = WeiboScanCoverage.from_json_line((output_root / WB_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8"))
    coverage.validate(
        manifest.weibo_scan,
        10,
        normalized_remote_ids=(_note_id(1), _note_id(3)),
    )
    # A failed detail leaves the page tail unfinished, so the durable layer must
    # keep the cursor for replay instead of claiming the arithmetic end.
    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.summary.failed_count == 1
    assert coverage.summary.page_complete is False
    assert coverage.source_end_observed is False


def test_complete_page_reaches_the_arithmetic_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    crawler_type, stored, _calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        list_result=_page(1, 2, 3, since_id="next", total=10),
    )
    manifest = _manifest(output_root)
    previous = os.getcwd()
    os.chdir(tmp_path / "checkout")
    try:
        install_weibo_creator_capture_shim(manifest)  # type: ignore[arg-type]
    finally:
        os.chdir(previous)
    asyncio.run(crawler_type().get_creators_and_notes())

    assert len(stored) == 3
    coverage = WeiboScanCoverage.from_json_line((output_root / WB_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8"))
    assert coverage.stop_reason == "total_inferred_end"
    assert coverage.summary.declared_total == 10
    assert coverage.source_end_observed is True
    assert coverage.next_state.head_boundary is not None


def test_list_restriction_is_not_source_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    crawler_type, _stored, _calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        list_result=DataFetchError("restricted"),
    )
    manifest = _manifest(output_root)
    previous = os.getcwd()
    os.chdir(tmp_path / "checkout")
    try:
        install_weibo_creator_capture_shim(manifest)  # type: ignore[arg-type]
    finally:
        os.chdir(previous)
    asyncio.run(crawler_type().get_creators_and_notes())

    coverage = WeiboScanCoverage.from_json_line((output_root / WB_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8"))
    assert coverage.stop_reason == "access_restricted"
    assert coverage.page is None
    assert coverage.source_end_observed is False
    assert coverage.next_state.head_boundary is None
