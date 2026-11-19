"""Zhihu bounded creator shim: page parsing privacy, restriction vs end, sealing."""

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
from media_sync.integrations.mediacrawler.zhihu_creator_capture import (
    install_zhihu_creator_capture_shim,
    parse_zhihu_creator_page,
)
from media_sync.integrations.mediacrawler.zhihu_creator_work import (
    ZH_SCAN_COVERAGE_FILENAME,
    ZH_SCAN_IDENTITY_FIELD,
    ZhihuScanCoverage,
    ZhihuScanState,
)

ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000089")
URL_TOKEN = "zhihu-url-token"
CREATOR_URL = f"https://www.zhihu.com/people/{URL_TOKEN}"
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"


class IPBlockError(RuntimeError):
    pass


class DataFetchError(RuntimeError):
    pass


class ZhihuContent:
    def __init__(self, content_id: str, content_type: str = "answer") -> None:
        self.content_id = content_id
        self.content_type = content_type
        self.content_text = f"body-{content_id}"
        self.content_url = f"https://www.zhihu.com/question/1/answer/{content_id}"

    def model_dump(self) -> dict[str, object]:
        return {
            "content_id": self.content_id,
            "content_type": self.content_type,
            "content_text": self.content_text,
            "content_url": self.content_url,
        }


def _module(name: str, checkout: Path) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(checkout / (name.replace(".", "/") + ".py"))
    return module


def _content_id(index: int) -> str:
    return str(8200000000 + index)


def _response(*indexes: int, is_end: bool = False) -> dict[str, object]:
    return {
        "data": [{"type": "answer", "id": int(_content_id(index))} for index in indexes],
        "paging": {"is_end": is_end},
    }


def _install_modules(
    monkeypatch: pytest.MonkeyPatch,
    checkout: Path,
    output_root: Path,
    *,
    page: object,
    unmappable: str | None = None,
) -> tuple[list[dict[str, object]], list[int]]:
    checkout.mkdir(parents=True, exist_ok=True)
    stored: list[dict[str, object]] = []
    list_calls: list[int] = []

    class ZhihuJsonlStoreImplement:
        async def store_content(self, content_item: dict[str, object]) -> None:
            stored.append(content_item)

    class _Extractor:
        @staticmethod
        def extract_content_list_from_creator(value: object) -> list[ZhihuContent]:
            assert type(value) is list
            rows = [ZhihuContent(str(item["id"])) for item in value if isinstance(item, dict)]
            for row in rows:
                if row.content_id == unmappable:
                    # A content type the pinned normalizer refuses makes the
                    # shim record `detail_unavailable` for exactly this answer.
                    row.content_type = "pin"
            return rows

    class ZhiHuClient:
        def __init__(self) -> None:
            self._extractor = _Extractor()

        async def get_creator_answers(self, url_token: str, offset: int = 0, limit: int = 20) -> object:
            assert url_token == URL_TOKEN
            list_calls.append(offset)
            if isinstance(page, BaseException):
                raise page
            return page

        async def get_all_anwser_by_creator(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("unbounded creator helper must be replaced")

    class ZhihuCrawler:
        def __init__(self) -> None:
            self.zhihu_client = ZhiHuClient()

    core = _module("media_platform.zhihu.core", checkout)
    core.ZhihuCrawler = ZhihuCrawler
    client = _module("media_platform.zhihu.client", checkout)
    client.ZhiHuClient = ZhiHuClient
    logger = SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
        exception=lambda *_args, **_kwargs: None,
    )
    store = _module("store.zhihu", checkout)
    store.utils = SimpleNamespace(logger=logger)
    client.utils = SimpleNamespace(logger=logger)

    async def update_zhihu_content(content_item: object) -> None:
        payload = content_item.model_dump()
        await ZhihuJsonlStoreImplement().store_content(payload)

    store.update_zhihu_content = update_zhihu_content
    store_impl = _module("store.zhihu._store_impl", checkout)
    store_impl.ZhihuJsonlStoreImplement = ZhihuJsonlStoreImplement
    errors = _module("media_platform.zhihu.exception", checkout)
    errors.IPBlockError = IPBlockError
    errors.DataFetchError = DataFetchError
    config = _module("config", checkout)
    config.ZHIHU_CREATOR_URL_LIST = [CREATOR_URL]
    config.SAVE_DATA_OPTION = "jsonl"
    config.ENABLE_GET_COMMENTS = False
    config.ENABLE_IP_PROXY = False
    config.MAX_CONCURRENCY_NUM = 1
    modules = {
        "media_platform.zhihu.core": core,
        "media_platform.zhihu.client": client,
        "media_platform.zhihu.exception": errors,
        "store.zhihu": store,
        "store.zhihu._store_impl": store_impl,
        "config": config,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return stored, list_calls


def _manifest(output_root: Path, *, state: ZhihuScanState | None = None) -> SimpleNamespace:
    author_sha = hashlib.sha256(URL_TOKEN.encode()).hexdigest()
    creator_sha = hashlib.sha256(CREATOR_URL.encode()).hexdigest()
    scan_state = state or ZhihuScanState.initial(ACCOUNT_ID, author_sha, creator_sha, UPSTREAM_SHA)
    return SimpleNamespace(
        zhihu_scan=scan_state,
        platform=Platform.ZHIHU,
        account_id=ACCOUNT_ID,
        author_remote_id_fingerprint_sha256=author_sha,
        creator_fingerprint_sha256=creator_sha,
        upstream_sha=UPSTREAM_SHA,
        max_items=20,
        request_delay_seconds=0.001,
        output_root=output_root,
    )


def test_page_parser_keeps_only_bounded_answer_identities() -> None:
    page = parse_zhihu_creator_page(_response(1, 2, is_end=True), offset=0, limit=20)

    assert [identity.content_id for identity in page.identities] == [_content_id(1), _content_id(2)]
    assert page.is_end is True
    serialized = json.dumps(page.as_mapping(), sort_keys=True)
    assert "body-" not in serialized and "content_text" not in serialized


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [], "paging": {"is_end": "yes"}},
        {"data": "invalid", "paging": {"is_end": True}},
        {"data": [{"id": 0}], "paging": {"is_end": True}},
        {"data": [{"id": 8200000001, "answer_id": 8200000002}], "paging": {"is_end": True}},
        {"data": [{"id": 8200000001}, {"id": 8200000001}], "paging": {"is_end": True}},
    ],
)
def test_page_parser_rejects_ambiguous_shapes(payload: object) -> None:
    with pytest.raises(RuntimeError, match="Zhihu bounded"):
        parse_zhihu_creator_page(payload, offset=0, limit=20)


def test_installed_shim_seals_coverage_and_reports_server_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    stored, list_calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        page=_response(1, 2, is_end=True),
    )
    manifest = _manifest(output_root)
    previous = os.getcwd()
    os.chdir(tmp_path / "checkout")
    try:
        install_zhihu_creator_capture_shim(manifest)  # type: ignore[arg-type]
        client_class = sys.modules["media_platform.zhihu.client"].ZhiHuClient
        contents = asyncio.run(client_class().get_all_anwser_by_creator(URL_TOKEN))
    finally:
        os.chdir(previous)

    assert [item.content_id for item in contents] == [_content_id(1), _content_id(2)]
    assert list_calls == [0]
    assert [item["content_id"] for item in stored] == [_content_id(1), _content_id(2)]
    assert all(ZH_SCAN_IDENTITY_FIELD in item for item in stored)
    coverage = ZhihuScanCoverage.from_json_line((output_root / ZH_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8"))
    coverage.validate(
        manifest.zhihu_scan,
        20,
        normalized_remote_ids=(_content_id(1), _content_id(2)),
    )
    assert coverage.stop_reason == "is_end"
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
        install_zhihu_creator_capture_shim(manifest)  # type: ignore[arg-type]
        client_class = sys.modules["media_platform.zhihu.client"].ZhiHuClient
        contents = asyncio.run(client_class().get_all_anwser_by_creator(URL_TOKEN))
    finally:
        os.chdir(previous)

    assert contents == []
    coverage = ZhihuScanCoverage.from_json_line((output_root / ZH_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8"))
    assert coverage.stop_reason == "access_restricted"
    assert coverage.page is None
    assert coverage.source_end_observed is False
    assert coverage.next_state.head_boundary is None


def test_partial_page_replays_only_the_missing_answer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A unit that stopped mid-page must resume from the same offset.

    The first run delivers every listed answer except one the pinned normalizer
    refuses; the unit therefore keeps the identical offset and witness. The
    replay must re-fetch that offset and offer ONLY the still-missing answer.
    A positional walk over the extracted list would re-offer an already
    delivered answer and be rejected as contract drift, so this pins the
    state-machine-driven loop shape.
    """

    output_root = tmp_path / "output"
    output_root.mkdir()
    missing = _content_id(2)
    stored, list_calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        page=_response(1, 2, 3, is_end=False),
        unmappable=missing,
    )
    manifest = _manifest(output_root)
    previous = os.getcwd()
    os.chdir(tmp_path / "checkout")
    try:
        install_zhihu_creator_capture_shim(manifest)  # type: ignore[arg-type]
        client_class = sys.modules["media_platform.zhihu.client"].ZhiHuClient
        first = asyncio.run(client_class().get_all_anwser_by_creator(URL_TOKEN))
    finally:
        os.chdir(previous)

    assert [item.content_id for item in first] == [_content_id(1), _content_id(3)]
    coverage = ZhihuScanCoverage.from_json_line((output_root / ZH_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8"))
    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.summary.page_complete is False
    assert coverage.summary.failed_count == 1
    assert [item.identity.content_id for item in coverage.failed] == [missing]
    assert coverage.next_state.offset == 0
    assert coverage.next_state.witness is not None

    first_calls = list(list_calls)
    (output_root / ZH_SCAN_COVERAGE_FILENAME).unlink()
    # A resumed unit runs in a fresh child process, so re-register the pinned
    # modules: the capture shim installs exactly once per process.
    stored, list_calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        page=_response(1, 2, 3, is_end=False),
    )
    replay_manifest = _manifest(output_root, state=coverage.next_state)
    previous = os.getcwd()
    os.chdir(tmp_path / "checkout")
    try:
        install_zhihu_creator_capture_shim(replay_manifest)  # type: ignore[arg-type]
        client_class = sys.modules["media_platform.zhihu.client"].ZhiHuClient
        second = asyncio.run(client_class().get_all_anwser_by_creator(URL_TOKEN))
    finally:
        os.chdir(previous)

    assert [item.content_id for item in second] == [missing]
    assert [item["content_id"] for item in stored] == [missing]
    # Both runs re-requested the identical offset instead of advancing it.
    assert first_calls == [0]
    assert list_calls == [0]


def test_upstream_store_callback_does_not_double_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Upstream passes a store callback; the shim already stored those rows.

    `.upstream/MediaCrawler/media_platform/zhihu/core.py:283-287` calls
    `get_all_anwser_by_creator(..., callback=zhihu_store.batch_update_zhihu_contents)`
    and that callback is nothing but `for content in contents: await
    update_zhihu_content(content)` (`.upstream/.../store/zhihu/__init__.py:57-70`).
    Invoking it would re-enter the guarded store with the identity ContextVar
    reset, aborting the unit before the coverage witness is sealed.
    """

    output_root = tmp_path / "output"
    output_root.mkdir()
    stored, list_calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        page=_response(1, 2, is_end=True),
    )
    manifest = _manifest(output_root)
    replayed: list[str] = []

    async def upstream_callback(contents: object) -> None:
        assert isinstance(contents, list)
        for content in contents:
            replayed.append(content.content_id)

    previous = os.getcwd()
    os.chdir(tmp_path / "checkout")
    try:
        install_zhihu_creator_capture_shim(manifest)  # type: ignore[arg-type]
        client_class = sys.modules["media_platform.zhihu.client"].ZhiHuClient
        contents = asyncio.run(client_class().get_all_anwser_by_creator(URL_TOKEN, 0, upstream_callback))
    finally:
        os.chdir(previous)

    assert [item.content_id for item in contents] == [_content_id(1), _content_id(2)]
    assert list_calls == [0]
    assert [item["content_id"] for item in stored] == [_content_id(1), _content_id(2)]
    assert replayed == []
    coverage = ZhihuScanCoverage.from_json_line((output_root / ZH_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8"))
    assert coverage.stop_reason == "is_end"
    coverage.validate(manifest.zhihu_scan, 20)


def test_empty_body_that_is_not_the_end_is_a_page_not_a_drift() -> None:
    """A rate-limited body parses as `data: []` with `is_end: false`.

    That is a valid page shape, and classifying it belongs to the unit (which
    replays and counts a stall) — raising here would surface it as a hard
    upstream fault with no bounded witness, unlike the Weibo/Tieba shims.
    """

    page = parse_zhihu_creator_page({"data": [], "paging": {"is_end": False}}, offset=20, limit=20)

    assert page.identities == ()
    assert page.is_end is False
