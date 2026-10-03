"""Douyin bounded creator-work shim: parse privacy, coverage sealing, restriction."""

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
from media_sync.integrations.mediacrawler.douyin_creator_capture import (
    install_douyin_creator_capture_shim,
    parse_douyin_creator_page,
)
from media_sync.integrations.mediacrawler.douyin_creator_work import (
    DOUYIN_SCAN_COVERAGE_FILENAME,
    DOUYIN_SCAN_IDENTITY_FIELD,
    DouyinScanCoverage,
    DouyinScanState,
)

ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000080")
SEC_USER_ID = "MS4wLjABAAAA0123456789abcdefghijklmnopqrstuv"
CREATOR_REFERENCE = f"https://www.douyin.com/user/{SEC_USER_ID}"
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"


class IPBlockError(RuntimeError):
    pass


class DataFetchError(RuntimeError):
    pass


def _module(name: str, checkout: Path) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(checkout / (name.replace(".", "/") + ".py"))
    return module


def _page(*indexes: int, cursor: str = "echo-next", has_more: bool = True) -> dict[str, object]:
    return {
        "max_cursor": cursor,
        "has_more": 1 if has_more else 0,
        "aweme_list": [{"aweme_id": f"{index:019d}", "desc": f"work-{index}"} for index in indexes],
    }


def _install_modules(
    monkeypatch: pytest.MonkeyPatch,
    checkout: Path,
    output_root: Path,
    *,
    list_result: object,
    detail_failure: int | None = None,
    normalization_failure: int | None = None,
) -> tuple[type, list[dict[str, object]], list[str]]:
    checkout.mkdir(parents=True)
    stored: list[dict[str, object]] = []
    detail_calls: list[str] = []

    class DouyinJsonlStoreImplement:
        async def store_content(self, content_item: dict[str, object]) -> None:
            stored.append(content_item)

    class DouYinClient:
        async def get_user_aweme_posts(self, sec_user_id: str, max_cursor: str) -> object:
            assert sec_user_id == SEC_USER_ID
            assert max_cursor == ""
            if isinstance(list_result, BaseException):
                raise list_result
            return list_result

        async def get_video_by_id(self, aweme_id: str) -> dict[str, object]:
            detail_calls.append(aweme_id)
            if detail_failure is not None and aweme_id == f"{detail_failure:019d}":
                raise DataFetchError
            return {
                "aweme_id": aweme_id,
                "desc": f"work-{aweme_id}",
                "create_time": 1_788_235_200,
                "author": {"sec_uid": SEC_USER_ID},
            }

    class DouYinCrawler:
        def __init__(self) -> None:
            self.dy_client = DouYinClient()

        async def get_creators_and_videos(self) -> None:
            raise AssertionError("unbounded creator helper must be replaced")

    core = _module("media_platform.douyin.core", checkout)
    core.DouYinCrawler = DouYinCrawler
    client = _module("media_platform.douyin.client", checkout)
    client.DouYinClient = DouYinClient
    store = _module("store.douyin", checkout)
    logger = SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
        exception=lambda *_args, **_kwargs: None,
    )
    store.utils = SimpleNamespace(logger=logger)
    core.utils = SimpleNamespace(logger=logger)

    async def update_douyin_aweme(*, aweme_item: dict[str, object]) -> None:
        if normalization_failure is not None and aweme_item["aweme_id"] == f"{normalization_failure:019d}":
            raise ValueError("synthetic quarantine")
        await DouyinJsonlStoreImplement().store_content(
            {
                "aweme_id": aweme_item["aweme_id"],
                "desc": aweme_item["desc"],
                "create_time": aweme_item["create_time"],
                "video_download_url": "",
                "note_download_url": "",
                "music_download_url": "",
                "cover_url": "",
            }
        )

    store.update_douyin_aweme = update_douyin_aweme
    store_impl = _module("store.douyin._store_impl", checkout)
    store_impl.DouyinJsonlStoreImplement = DouyinJsonlStoreImplement
    helper = _module("media_platform.douyin.help", checkout)
    helper.parse_creator_info_from_url = lambda value: SimpleNamespace(sec_user_id=SEC_USER_ID)
    errors = _module("media_platform.douyin.exception", checkout)
    errors.IPBlockError = IPBlockError
    errors.DataFetchError = DataFetchError
    config = _module("config", checkout)
    config.DY_CREATOR_ID_LIST = [CREATOR_REFERENCE]
    config.SAVE_DATA_OPTION = "jsonl"
    config.ENABLE_GET_COMMENTS = False
    config.ENABLE_GET_MEIDAS = False
    config.ENABLE_IP_PROXY = False
    config.MAX_CONCURRENCY_NUM = 1
    modules = {
        "media_platform.douyin.core": core,
        "media_platform.douyin.client": client,
        "media_platform.douyin.help": helper,
        "media_platform.douyin.exception": errors,
        "store.douyin": store,
        "store.douyin._store_impl": store_impl,
        "config": config,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return DouYinCrawler, stored, detail_calls


def _manifest(output_root: Path) -> SimpleNamespace:
    author_sha = hashlib.sha256(SEC_USER_ID.encode()).hexdigest()
    creator_sha = hashlib.sha256(CREATOR_REFERENCE.encode()).hexdigest()
    state = DouyinScanState.initial(ACCOUNT_ID, author_sha, creator_sha, UPSTREAM_SHA)
    return SimpleNamespace(
        douyin_scan=state,
        platform=Platform.DY,
        account_id=ACCOUNT_ID,
        author_remote_id_fingerprint_sha256=author_sha,
        creator_fingerprint_sha256=creator_sha,
        upstream_sha=UPSTREAM_SHA,
        max_items=18,
        request_delay_seconds=0.001,
        output_root=output_root,
    )


def test_page_parser_reduces_listings_to_bounded_identities() -> None:
    page = parse_douyin_creator_page(_page(1, 2), input_cursor="")
    assert [identity.aweme_id for identity in page.identities] == [f"{index:019d}" for index in (1, 2)]
    serialized = json.dumps(page.as_mapping(), sort_keys=True)
    assert "desc" not in serialized and "work-" not in serialized
    assert page.has_more is True and page.next_cursor == "echo-next"


@pytest.mark.parametrize(
    "payload",
    [
        {"max_cursor": "next", "has_more": "1", "aweme_list": []},
        {"max_cursor": "next", "has_more": 2, "aweme_list": []},
        {"max_cursor": "next", "has_more": 1, "aweme_list": [{"aweme_id": "bad"}]},
        {"max_cursor": "next", "has_more": 1, "aweme_list": [{"aweme_id": f"{1:019d}"}, {"aweme_id": f"{1:019d}"}]},
    ],
)
def test_page_parser_rejects_ambiguous_progress(payload: object) -> None:
    with pytest.raises(RuntimeError, match="Douyin bounded"):
        parse_douyin_creator_page(payload, input_cursor="")


def test_installed_shim_seals_coverage_and_isolates_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    crawler_type, stored, detail_calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        list_result=_page(1, 2, 3, cursor="", has_more=False),
        detail_failure=2,
    )
    manifest = _manifest(output_root)
    previous = os.getcwd()
    os.chdir(tmp_path / "checkout")
    try:
        install_douyin_creator_capture_shim(manifest)  # type: ignore[arg-type]
    finally:
        os.chdir(previous)
    asyncio.run(crawler_type().get_creators_and_videos())

    assert [item["aweme_id"] for item in stored] == [f"{1:019d}", f"{3:019d}"]
    assert sorted(detail_calls) == sorted([f"{index:019d}" for index in (1, 2, 3)])
    assert all(DOUYIN_SCAN_IDENTITY_FIELD in item for item in stored)
    coverage_text = (output_root / DOUYIN_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8")
    coverage = DouyinScanCoverage.from_json_line(coverage_text)
    coverage.validate(
        manifest.douyin_scan,
        18,
        normalized_remote_ids=(f"{1:019d}", f"{3:019d}"),
    )
    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.summary.page_complete is False
    assert coverage.summary.failed_count == 1
    assert coverage.public_summary()["source_end_observed"] is False


def test_one_rejected_store_write_does_not_hide_unrelated_works(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    crawler_type, stored, _detail_calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        list_result=_page(1, 2, 3, cursor="", has_more=False),
        normalization_failure=2,
    )
    manifest = _manifest(output_root)
    previous = os.getcwd()
    os.chdir(tmp_path / "checkout")
    try:
        install_douyin_creator_capture_shim(manifest)  # type: ignore[arg-type]
    finally:
        os.chdir(previous)
    asyncio.run(crawler_type().get_creators_and_videos())

    assert [item["aweme_id"] for item in stored] == [f"{1:019d}", f"{3:019d}"]
    coverage = DouyinScanCoverage.from_json_line(
        (output_root / DOUYIN_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8")
    )
    coverage.validate(
        manifest.douyin_scan,
        18,
        normalized_remote_ids=(f"{1:019d}", f"{3:019d}"),
    )
    assert coverage.summary.failed_count == 1
    assert coverage.summary.page_complete is False


def test_list_access_restriction_is_not_source_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    crawler_type, _stored, _calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        list_result=IPBlockError("restricted"),
    )
    manifest = _manifest(output_root)
    previous = os.getcwd()
    os.chdir(tmp_path / "checkout")
    try:
        install_douyin_creator_capture_shim(manifest)  # type: ignore[arg-type]
    finally:
        os.chdir(previous)
    asyncio.run(crawler_type().get_creators_and_videos())

    coverage = DouyinScanCoverage.from_json_line(
        (output_root / DOUYIN_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8")
    )
    assert coverage.stop_reason == "access_restricted"
    assert coverage.page is None
    assert coverage.public_summary()["source_end_observed"] is False
    assert not (output_root / DOUYIN_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8").count("sec_uid")
