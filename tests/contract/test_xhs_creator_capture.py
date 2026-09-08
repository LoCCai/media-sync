from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import UUID

import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler.xhs_creator_capture import (
    install_xhs_creator_capture_shim,
    parse_xhs_creator_page,
)
from media_sync.integrations.mediacrawler.xhs_creator_notes import (
    XHS_SCAN_COVERAGE_FILENAME,
    XHS_SCAN_IDENTITY_FIELD,
    XhsScanCoverage,
    XhsScanState,
)

ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000076")
CREATOR_ID = "5f1234567890abcdef123456"
CREATOR_TOKEN = "creator-token-private"
CREATOR_REFERENCE = (
    f"https://www.xiaohongshu.com/user/profile/{CREATOR_ID}?xsec_token={CREATOR_TOKEN}&xsec_source=pc_user"
)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"


class IPBlockError(RuntimeError):
    pass


class PlatformAccessError(RuntimeError):
    pass


class DataFetchError(RuntimeError):
    pass


class NoteNotFoundError(RuntimeError):
    pass


def _module(name: str, checkout: Path) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(checkout / (name.replace(".", "/") + ".py"))
    return module


def _page(*indexes: int, cursor: str = "cursor-next", has_more: bool = True) -> dict[str, object]:
    return {
        "cursor": cursor,
        "has_more": has_more,
        "notes": [
            {
                "note_id": f"{index:024x}",
                "xsec_token": f"note-token-{index}",
                "xsec_source": "pc_user",
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
    normalization_failure: int | None = None,
) -> tuple[type, list[dict[str, object]], list[tuple[str, str, str]]]:
    checkout.mkdir(parents=True)
    stored: list[dict[str, object]] = []
    detail_calls: list[tuple[str, str, str]] = []

    class XhsJsonlStoreImplement:
        async def store_content(self, content_item: dict[str, object]) -> None:
            stored.append(content_item)

    class XiaoHongShuClient:
        async def get_notes_by_creator(self, creator: str, cursor: str, **kwargs: object) -> object:
            assert creator == CREATOR_ID
            assert cursor == ""
            assert kwargs == {
                "page_size": 30,
                "xsec_token": CREATOR_TOKEN,
                "xsec_source": "pc_user",
            }
            if isinstance(list_result, BaseException):
                raise list_result
            return list_result

        async def get_note_by_id(self, note_id: str, source: str, token: str) -> dict[str, object]:
            detail_calls.append((note_id, source, token))
            if detail_failure is not None and note_id == f"{detail_failure:024x}":
                raise DataFetchError
            return {
                "note_id": note_id,
                "type": "normal",
                "title": note_id,
                "desc": "fixture",
                "user": {"user_id": CREATOR_ID},
                "interact_info": {},
                "image_list": [],
                "tag_list": [],
            }

        async def get_note_by_id_from_html(
            self,
            note_id: str,
            source: str,
            token: str,
            *,
            enable_cookie: bool,
        ) -> None:
            assert enable_cookie is True
            detail_calls.append((note_id, source, token))
            return None

    class XiaoHongShuCrawler:
        def __init__(self) -> None:
            self.xhs_client = XiaoHongShuClient()

        async def get_creators_and_notes(self) -> None:
            raise AssertionError("unbounded creator helper must be replaced")

    core = _module("media_platform.xhs.core", checkout)
    core.XiaoHongShuCrawler = XiaoHongShuCrawler
    client = _module("media_platform.xhs.client", checkout)
    client.XiaoHongShuClient = XiaoHongShuClient
    store = _module("store.xhs", checkout)
    store.XhsJsonlStoreImplement = XhsJsonlStoreImplement
    logger = SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
        exception=lambda *_args, **_kwargs: None,
    )
    store.utils = SimpleNamespace(logger=logger)
    core.utils = SimpleNamespace(logger=logger)

    async def update_xhs_note(note: dict[str, object]) -> None:
        invalid_video_urls = ",".join(f"https://cdn.example.test/{index}.mp4" for index in range(17))
        await XhsJsonlStoreImplement().store_content(
            {
                "note_id": note["note_id"],
                "type": note["type"],
                "title": note["title"],
                "desc": note["desc"],
                "time": 1_788_235_200_000,
                "video_url": (
                    invalid_video_urls
                    if normalization_failure is not None and note["note_id"] == f"{normalization_failure:024x}"
                    else ""
                ),
                "image_list": "",
                "xsec_token": note["xsec_token"],
            }
        )

    store.update_xhs_note = update_xhs_note
    store_impl = _module("store.xhs._store_impl", checkout)
    store_impl.XhsJsonlStoreImplement = XhsJsonlStoreImplement
    helper = _module("media_platform.xhs.help", checkout)
    helper.parse_creator_info_from_url = lambda value: SimpleNamespace(
        user_id=CREATOR_ID,
        xsec_token=CREATOR_TOKEN,
        xsec_source="pc_user",
    )
    errors = _module("media_platform.xhs.exception", checkout)
    errors.IPBlockError = IPBlockError
    errors.PlatformAccessError = PlatformAccessError
    errors.DataFetchError = DataFetchError
    errors.NoteNotFoundError = NoteNotFoundError
    config = _module("config", checkout)
    config.XHS_CREATOR_URL_LIST = [CREATOR_REFERENCE]
    config.SAVE_DATA_OPTION = "jsonl"
    config.CREATOR_MODE = True
    config.ENABLE_GET_COMMENTS = False
    config.ENABLE_GET_SUB_COMMENTS = False
    config.ENABLE_GET_MEIDAS = False
    config.ENABLE_GET_MEDIAS = False
    config.ENABLE_IP_PROXY = False
    config.MAX_CONCURRENCY_NUM = 1
    modules = {
        "media_platform.xhs.core": core,
        "media_platform.xhs.client": client,
        "media_platform.xhs.help": helper,
        "media_platform.xhs.exception": errors,
        "store.xhs": store,
        "store.xhs._store_impl": store_impl,
        "config": config,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return XiaoHongShuCrawler, stored, detail_calls


def _manifest(output_root: Path) -> SimpleNamespace:
    author_sha = hashlib.sha256(CREATOR_ID.encode()).hexdigest()
    creator_sha = hashlib.sha256(CREATOR_REFERENCE.encode()).hexdigest()
    state = XhsScanState.initial(ACCOUNT_ID, author_sha, creator_sha, UPSTREAM_SHA)
    return SimpleNamespace(
        xhs_scan=state,
        platform=Platform.XHS,
        account_id=ACCOUNT_ID,
        author_remote_id_fingerprint_sha256=author_sha,
        creator_fingerprint_sha256=creator_sha,
        upstream_sha=UPSTREAM_SHA,
        max_items=30,
        request_delay_seconds=0.001,
        output_root=output_root,
    )


def test_page_parser_keeps_tokens_only_in_private_return() -> None:
    raw = _page(1, 2)
    page, tokens = parse_xhs_creator_page(raw, input_cursor="")
    assert tokens == {f"{index:024x}": f"note-token-{index}" for index in (1, 2)}
    serialized = json.dumps(page.as_mapping(), sort_keys=True)
    assert "note-token" not in serialized
    assert all(identity.token_sha256 in serialized for identity in page.identities)


@pytest.mark.parametrize(
    "payload",
    [
        {"cursor": "next", "has_more": "true", "notes": []},
        {"cursor": "next", "has_more": True, "notes": [{"note_id": "bad"}]},
        {
            "cursor": "",
            "has_more": True,
            "notes": [{"note_id": f"{1:024x}", "xsec_token": "x", "xsec_source": "pc_user"}],
        },
    ],
)
def test_page_parser_rejects_ambiguous_progress(payload: object) -> None:
    with pytest.raises(RuntimeError, match="XHS bounded"):
        parse_xhs_creator_page(payload, input_cursor="")


def test_installed_shim_uses_page_tokens_and_seals_coverage(
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
    install_xhs_creator_capture_shim(manifest, tmp_path / "checkout")  # type: ignore[arg-type]
    asyncio.run(crawler_type().get_creators_and_notes())

    assert [item["note_id"] for item in stored] == [f"{1:024x}", f"{3:024x}"]
    assert len(detail_calls) == 4
    assert all(XHS_SCAN_IDENTITY_FIELD in item for item in stored)
    coverage_text = (output_root / XHS_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8")
    coverage = XhsScanCoverage.from_json_line(coverage_text)
    coverage.validate(
        manifest.xhs_scan,
        30,
        normalized_remote_ids=(f"{1:024x}", f"{3:024x}"),
    )
    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.summary.page_complete is False
    assert coverage.summary.failed_count == 1
    assert CREATOR_TOKEN not in coverage_text
    assert all(f"note-token-{index}" not in coverage_text for index in (1, 2, 3))


def test_one_unsupported_normalized_note_does_not_hide_unrelated_notes(
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
    install_xhs_creator_capture_shim(manifest, tmp_path / "checkout")  # type: ignore[arg-type]
    asyncio.run(crawler_type().get_creators_and_notes())

    assert [item["note_id"] for item in stored] == [f"{1:024x}", f"{3:024x}"]
    coverage = XhsScanCoverage.from_json_line((output_root / XHS_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8"))
    coverage.validate(
        manifest.xhs_scan,
        30,
        normalized_remote_ids=(f"{1:024x}", f"{3:024x}"),
    )
    assert coverage.summary.failed_count == 1
    assert coverage.summary.page_complete is False


def test_list_access_restriction_is_not_source_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    crawler_type, stored, _calls = _install_modules(
        monkeypatch,
        tmp_path / "checkout",
        output_root,
        list_result=IPBlockError(),
    )
    manifest = _manifest(output_root)
    install_xhs_creator_capture_shim(manifest, tmp_path / "checkout")  # type: ignore[arg-type]
    asyncio.run(crawler_type().get_creators_and_notes())
    coverage = XhsScanCoverage.from_json_line((output_root / XHS_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8"))
    assert stored == []
    assert coverage.stop_reason == "access_restricted"
    assert coverage.public_summary()["source_end_observed"] is False
