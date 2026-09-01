from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from media_sync.integrations.mediacrawler.bilibili_media import (
    BILIBILI_MAX_PAGES,
    BILIBILI_PAGES_FIELD,
    BilibiliPageIdentity,
    bilibili_video_cid,
    bilibili_video_remote_ids,
    install_bilibili_media_capture,
    is_bilibili_aid,
    parse_bilibili_page_payload,
    parse_bilibili_view_pages,
)


def _view(cids: list[int]) -> dict[str, object]:
    return {
        "aid": 987654321,
        "cid": cids[0],
        "pages": [{"page": index, "cid": cid, "part": f"P{index}"} for index, cid in enumerate(cids, 1)],
    }


@pytest.mark.parametrize("value", ["1", "987654321", str(2**63 - 1)])
def test_aid_accepts_canonical_positive_decimal(value: str) -> None:
    assert is_bilibili_aid(value)


@pytest.mark.parametrize("value", [None, True, 1, "", "0", "01", "+1", " 1", "1 ", str(2**63)])
def test_aid_rejects_noncanonical_values(value: object) -> None:
    assert not is_bilibili_aid(value)


@pytest.mark.parametrize("count", [1, 2, 3, BILIBILI_MAX_PAGES])
def test_view_pages_preserve_exact_bounded_order(count: int) -> None:
    cids = list(range(10_001, 10_001 + count))
    pages = parse_bilibili_view_pages(_view(cids), expected_aid="987654321")

    assert pages == tuple(BilibiliPageIdentity(page=index, cid=cid) for index, cid in enumerate(cids, 1))
    assert parse_bilibili_page_payload([page.as_mapping() for page in pages]) == pages


def test_empty_page_list_uses_the_legacy_top_level_cid() -> None:
    pages = parse_bilibili_view_pages({"aid": 987654321, "cid": 24680, "pages": []})

    assert pages == (BilibiliPageIdentity(page=1, cid=24680),)
    assert bilibili_video_remote_ids("987654321", pages) == ("987654321:video:0",)
    assert bilibili_video_cid("987654321", "987654321:video:0") is None


def test_multipart_remote_ids_bind_each_distinct_cid() -> None:
    pages = parse_bilibili_view_pages(_view([24680, 97531, 86420]))
    remote_ids = bilibili_video_remote_ids("987654321", pages)

    assert remote_ids == (
        "987654321:video:cid:24680",
        "987654321:video:cid:97531",
        "987654321:video:cid:86420",
    )
    assert tuple(bilibili_video_cid("987654321", remote_id) for remote_id in remote_ids) == (
        24680,
        97531,
        86420,
    )


@pytest.mark.parametrize(
    "view",
    [
        {"aid": 987654321, "cid": 1, "pages": "not-a-list"},
        _view(list(range(1, BILIBILI_MAX_PAGES + 2))),
        {"aid": 987654321, "pages": [{"page": 1, "cid": 11}, {"page": 2, "cid": 11}]},
        {"aid": 987654321, "pages": [{"page": 2, "cid": 11}]},
        {"aid": 987654321, "pages": [{"page": True, "cid": 11}]},
        {"aid": 987654321, "pages": [{"page": 1, "cid": 0}]},
    ],
)
def test_view_pages_reject_overflow_duplicates_and_malformed_rows(view: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        parse_bilibili_view_pages(view)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        [{"page": 1, "cid": 11, "extra": 1}],
        [{"page": 1, "cid": 11}, {"page": 2, "cid": 11}],
        [{"page": 2, "cid": 11}],
    ],
)
def test_private_page_payload_is_closed_and_unique(payload: list[object]) -> None:
    with pytest.raises(ValueError):
        parse_bilibili_page_payload(payload)


def _install_fake_modules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, type[Any], types.ModuleType, list[object]]:
    root = tmp_path / "MediaCrawler"
    rows: list[object] = []

    class JsonlStore:
        async def store_content(self, content_item: object) -> None:
            rows.append(dict(content_item) if isinstance(content_item, Mapping) else content_item)

    async def update_bilibili_video(video_item: Mapping[str, object]) -> None:
        view = video_item["View"]
        assert isinstance(view, Mapping)
        await JsonlStore().store_content({"video_id": str(view["aid"]), "title": "fixture"})

    store_package = types.ModuleType("store")
    store_package.__file__ = str(root / "store" / "__init__.py")
    store_package.__path__ = []
    store_module = types.ModuleType("store.bilibili")
    store_module.__file__ = str(root / "store" / "bilibili" / "__init__.py")
    store_module.__path__ = []
    store_namespace: Any = store_module
    store_namespace.BiliJsonlStoreImplement = JsonlStore
    store_namespace.update_bilibili_video = update_bilibili_video
    impl_module = types.ModuleType("store.bilibili._store_impl")
    impl_module.__file__ = str(root / "store" / "bilibili" / "_store_impl.py")
    impl_namespace: Any = impl_module
    impl_namespace.BiliJsonlStoreImplement = JsonlStore
    for module in (store_package, store_module, impl_module):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    return root, JsonlStore, store_module, rows


def test_store_shim_carries_only_page_and_cid_to_the_matching_jsonl_row(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _store_class, store_module, rows = _install_fake_modules(monkeypatch, tmp_path)
    install_bilibili_media_capture(root)

    asyncio.run(store_module.update_bilibili_video({"View": _view([24680, 97531, 86420])}))

    assert rows == [
        {
            "video_id": "987654321",
            "title": "fixture",
            BILIBILI_PAGES_FIELD: [
                {"page": 1, "cid": 24680},
                {"page": 2, "cid": 97531},
                {"page": 3, "cid": 86420},
            ],
        }
    ]


def test_store_shim_emits_an_explicit_empty_claim_for_unsupported_page_shape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _store_class, store_module, rows = _install_fake_modules(monkeypatch, tmp_path)
    install_bilibili_media_capture(root)
    oversized = _view(list(range(1, BILIBILI_MAX_PAGES + 2)))

    asyncio.run(store_module.update_bilibili_video({"View": oversized}))

    assert isinstance(rows[0], Mapping)
    assert rows[0][BILIBILI_PAGES_FIELD] == []


def test_store_shim_is_idempotent_and_rejects_private_field_collisions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, store_class, store_module, _rows = _install_fake_modules(monkeypatch, tmp_path)
    install_bilibili_media_capture(root)
    installed = store_module.update_bilibili_video
    install_bilibili_media_capture(root)
    assert store_module.update_bilibili_video is installed

    with pytest.raises(RuntimeError, match="collision"):
        asyncio.run(
            store_class().store_content(
                {
                    "video_id": "987654321",
                    BILIBILI_PAGES_FIELD: [],
                }
            )
        )
