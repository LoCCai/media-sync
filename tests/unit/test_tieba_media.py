from __future__ import annotations

import asyncio
import types
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from media_sync.integrations.mediacrawler import tieba_media
from media_sync.integrations.mediacrawler.tieba_media import (
    TIEBA_IMAGE_FIELD,
    install_tieba_media_capture,
    is_tieba_positive_id,
    tieba_image_source_hint,
    validate_tieba_image_source_hint,
    validate_tieba_image_url,
    validate_tieba_thread_url,
)

NOTE_ID = "10376710029"
IMAGE_ID = "489c9a3df8dcd1009420153b348b4710b8122fc3"
TOKEN = "2026-09-02-17_deadbeef"
IMAGE_URL = f"https://tiebapic.baidu.com/forum/pic/item/{IMAGE_ID}.jpg?tbpicau={TOKEN}"
IMAGE_HINT = f"https://tiebapic.baidu.com/forum/pic/item/{IMAGE_ID}.jpg"


@dataclass
class _FakeCheckout:
    root: Path
    extractor_class: type[Any]
    client_class: type[Any]
    store_class: type[Any]
    note_class: type[Any]
    rows: list[object]
    failing_ids: set[str]
    modules: dict[str, types.ModuleType]
    original_store_content: Any


def _image_item(*, image_url: str = IMAGE_URL) -> dict[str, object]:
    query = image_url.split("?", 1)[1]
    return {
        "type": 3,
        "origin_src": image_url,
        "cdn_src": (f"https://tiebapic.baidu.com/forum/w%3D720%3Bq%3D60/sign=a/{IMAGE_ID}.jpg?{query}"),
        "big_cdn_src": (f"https://tiebapic.baidu.com/forum/w%3D1920%3Bq%3D100/sign=b/{IMAGE_ID}.jpg?{query}"),
        "cdn_src_active": (f"https://tiebapic.baidu.com/forum/w%3D720%3Bq%3D60/sign=c/{IMAGE_ID}.jpg?{query}"),
        "pic_id": 300_933_013_320,
        "bsize": "560,303",
        "origin_size": 65_144,
        "is_long_pic": 0,
        "show_original_btn": 1,
    }


def _api_data(
    *,
    note_id: object = NOTE_ID,
    content: object | None = None,
) -> dict[str, object]:
    return {
        "thread": {"id": note_id, "title": "fixture"},
        "first_floor": {
            "tid": note_id,
            "content": [{"type": 0, "text": "fixture body"}, _image_item()] if content is None else content,
        },
    }


def _fake_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _FakeCheckout:
    root = tmp_path / "MediaCrawler"
    rows: list[object] = []
    failing_ids: set[str] = set()

    class Note:
        def __init__(self, note_id: str, note_url: str) -> None:
            self.note_id = note_id
            self.note_url = note_url
            self.title = "fixture"

        def model_dump(self) -> dict[str, object]:
            return {"note_id": self.note_id, "note_url": self.note_url, "title": self.title}

    class Extractor:
        def extract_note_detail_from_api(self, api_data: Mapping[str, object]) -> Note:
            thread = api_data.get("thread")
            first_floor = api_data.get("first_floor")
            thread_id = thread.get("id") if isinstance(thread, Mapping) else None
            floor_id = first_floor.get("tid") if isinstance(first_floor, Mapping) else None
            note_id = str(thread_id or floor_id or "")
            return Note(note_id, f"https://tieba.baidu.com/p/{note_id}")

    class JsonlStore:
        async def store_content(self, content_item: object) -> None:
            note_id = content_item.get("note_id") if isinstance(content_item, Mapping) else None
            if note_id in failing_ids:
                raise RuntimeError("injected store failure")
            rows.append(dict(content_item) if isinstance(content_item, Mapping) else content_item)

    original_store_content = JsonlStore.store_content

    async def update_tieba_note(note_item: Note) -> None:
        await JsonlStore().store_content(note_item.model_dump())

    class Client:
        @staticmethod
        def _extract_creator_portrait(creator_url: str) -> str:
            return creator_url

        async def get_all_notes_by_creator_url(
            self,
            creator_url: str,
            crawl_interval: float = 1.0,
            callback: Any = None,
            max_note_count: int = 0,
        ) -> list[str]:
            del creator_url, crawl_interval, callback, max_note_count
            return ["unbounded-original"]

    package_names = ("media_platform", "media_platform.tieba", "store")
    modules: dict[str, types.ModuleType] = {}
    for name in package_names:
        module = types.ModuleType(name)
        module.__file__ = str(root / Path(*name.split(".")) / "__init__.py")
        module.__path__ = []  # type: ignore[attr-defined]
        modules[name] = module

    help_module = types.ModuleType("media_platform.tieba.help")
    help_module.__file__ = str(root / "media_platform" / "tieba" / "help.py")
    help_module.TieBaExtractor = Extractor
    modules[help_module.__name__] = help_module

    client_module = types.ModuleType("media_platform.tieba.client")
    client_module.__file__ = str(root / "media_platform" / "tieba" / "client.py")
    client_module.BaiduTieBaClient = Client
    modules[client_module.__name__] = client_module

    store_module = types.ModuleType("store.tieba")
    store_module.__file__ = str(root / "store" / "tieba" / "__init__.py")
    store_module.__path__ = []  # type: ignore[attr-defined]
    store_module.TieBaJsonlStoreImplement = JsonlStore
    store_module.update_tieba_note = update_tieba_note
    modules[store_module.__name__] = store_module

    impl_module = types.ModuleType("store.tieba._store_impl")
    impl_module.__file__ = str(root / "store" / "tieba" / "_store_impl.py")
    impl_module.TieBaJsonlStoreImplement = JsonlStore
    modules[impl_module.__name__] = impl_module

    for name, module in modules.items():
        monkeypatch.setitem(__import__("sys").modules, name, module)

    return _FakeCheckout(
        root=root,
        extractor_class=Extractor,
        client_class=Client,
        store_class=JsonlStore,
        note_class=Note,
        rows=rows,
        failing_ids=failing_ids,
        modules=modules,
        original_store_content=original_store_content,
    )


@pytest.mark.parametrize("value", ["1", NOTE_ID, str(2**63 - 1)])
def test_positive_id_accepts_canonical_values(value: str) -> None:
    assert is_tieba_positive_id(value)


@pytest.mark.parametrize(
    "value",
    [None, True, 1, "", "0", "01", "+1", " 1", "1 ", "1.0", "\uff11\uff12", str(2**63)],
)
def test_positive_id_rejects_noncanonical_values(value: object) -> None:
    assert not is_tieba_positive_id(value)


def test_thread_url_is_strict_and_bound_to_note_id() -> None:
    value = f"https://tieba.baidu.com/p/{NOTE_ID}"
    assert validate_tieba_thread_url(value) == value
    assert validate_tieba_thread_url(value, note_id=NOTE_ID) == value


@pytest.mark.parametrize(
    "value",
    [
        f"http://tieba.baidu.com/p/{NOTE_ID}",
        f"https://www.tieba.baidu.com/p/{NOTE_ID}",
        f"https://TIEBA.BAIDU.COM/p/{NOTE_ID}",
        f"https://tieba.baidu.com:443/p/{NOTE_ID}",
        f"https://tieba.baidu.com/p/{NOTE_ID}/",
        "https://tieba.baidu.com/p/01",
        f"https://tieba.baidu.com/p/{NOTE_ID}?",
        f"https://tieba.baidu.com/p/{NOTE_ID}?pn=1",
        f"https://tieba.baidu.com/p/{NOTE_ID}#floor",
    ],
)
def test_thread_url_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(ValueError, match="invalid Tieba thread URL"):
        validate_tieba_thread_url(value)


def test_image_url_and_source_hint_have_separate_exact_contracts() -> None:
    assert validate_tieba_image_url(IMAGE_URL) == IMAGE_URL
    assert tieba_image_source_hint(IMAGE_URL) == IMAGE_HINT
    assert validate_tieba_image_source_hint(IMAGE_HINT) == IMAGE_HINT
    with pytest.raises(ValueError):
        validate_tieba_image_url(IMAGE_HINT)
    with pytest.raises(ValueError):
        validate_tieba_image_source_hint(IMAGE_URL)


@pytest.mark.parametrize(
    "value",
    [
        "",
        f" {IMAGE_URL}",
        f"{IMAGE_URL} ",
        IMAGE_URL.replace("https://", "http://"),
        IMAGE_URL.replace("tiebapic.baidu.com", "evil.test"),
        IMAGE_URL.replace("tiebapic.baidu.com", "tiebapic.baidu.com.evil.test"),
        IMAGE_URL.replace("tiebapic.baidu.com", "user@tiebapic.baidu.com"),
        IMAGE_URL.replace("tiebapic.baidu.com", "tiebapic.baidu.com:443"),
        IMAGE_URL.replace("/forum/pic/item/", "/forum/pic/items/"),
        IMAGE_URL.replace(IMAGE_ID, "a" * 39),
        IMAGE_URL.replace(".jpg", ".gif"),
        IMAGE_URL.replace("?tbpicau=", "?token="),
        IMAGE_URL.replace(f"?tbpicau={TOKEN}", ""),
        f"{IMAGE_URL}&other=x",
        f"{IMAGE_URL}#fragment",
        IMAGE_URL.replace("/forum", "\\forum"),
    ],
)
def test_image_url_rejects_ambiguous_or_unsupported_values(value: str) -> None:
    with pytest.raises(ValueError, match="invalid Tieba image URL"):
        validate_tieba_image_url(value)


async def test_capture_injects_one_exact_type_three_origin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root)
    note = checkout.extractor_class().extract_note_detail_from_api(_api_data())

    await checkout.modules["store.tieba"].update_tieba_note(note)

    assert checkout.rows == [
        {
            "note_id": NOTE_ID,
            "note_url": f"https://tieba.baidu.com/p/{NOTE_ID}",
            "title": "fixture",
            TIEBA_IMAGE_FIELD: IMAGE_URL,
        }
    ]


@pytest.mark.parametrize(
    "content",
    [
        [{"type": 0, "text": "text"}],
        [{"type": 3, **{key: value for key, value in _image_item().items() if key != "type"}}],
        [{"type": 0, "text": "text"}, _image_item(), _image_item()],
        [{"type": 0, "text": "text"}, {**_image_item(), "type": True}],
        [{"type": 0, "text": "text"}, {**_image_item(), "extra": "drift"}],
        [{"type": 0, "text": "text"}, {key: value for key, value in _image_item().items() if key != "origin_src"}],
        [{"type": 2, "text": "emoji"}, _image_item()],
        [{"type": 0, "text": "text", "link": "drift"}, _image_item()],
        [{"type": 0, "text": ""}, _image_item()],
        "not-a-list",
    ],
)
async def test_capture_fails_closed_for_nonfrozen_first_floor_shapes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    content: object,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root)
    note = checkout.extractor_class().extract_note_detail_from_api(_api_data(content=content))
    await checkout.modules["store.tieba"].update_tieba_note(note)
    assert isinstance(checkout.rows[0], dict)
    assert TIEBA_IMAGE_FIELD not in checkout.rows[0]


async def test_capture_rejects_mismatched_response_ids(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root)
    response = _api_data()
    assert isinstance(response["first_floor"], dict)
    response["first_floor"]["tid"] = "10376710030"
    note = checkout.extractor_class().extract_note_detail_from_api(response)
    await checkout.modules["store.tieba"].update_tieba_note(note)
    assert isinstance(checkout.rows[0], dict)
    assert TIEBA_IMAGE_FIELD not in checkout.rows[0]


async def test_capture_binds_the_exact_returned_object(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root)
    captured = checkout.extractor_class().extract_note_detail_from_api(_api_data())
    clone = checkout.note_class(NOTE_ID, f"https://tieba.baidu.com/p/{NOTE_ID}")

    await checkout.modules["store.tieba"].update_tieba_note(clone)
    await checkout.modules["store.tieba"].update_tieba_note(captured)

    assert isinstance(checkout.rows[0], dict) and TIEBA_IMAGE_FIELD not in checkout.rows[0]
    assert isinstance(checkout.rows[1], dict) and checkout.rows[1][TIEBA_IMAGE_FIELD] == IMAGE_URL


async def test_capture_crosses_gather_child_to_parent_store_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root)

    async def extract(note_id: str, image_id: str) -> object:
        await asyncio.sleep(0)
        image_url = f"https://tiebapic.baidu.com/forum/pic/item/{image_id}.jpg?tbpicau={TOKEN}"
        item = _image_item(image_url=image_url)
        for key in ("cdn_src", "big_cdn_src", "cdn_src_active"):
            item[key] = str(item[key]).replace(IMAGE_ID, image_id)
        return checkout.extractor_class().extract_note_detail_from_api(
            _api_data(note_id=note_id, content=[{"type": 0, "text": "text"}, item])
        )

    second_id = "0123456789abcdef0123456789abcdef01234567"
    notes = await asyncio.gather(extract(NOTE_ID, IMAGE_ID), extract("10376710030", second_id))
    for note in notes:
        await checkout.modules["store.tieba"].update_tieba_note(note)

    by_id = {row["note_id"]: row for row in checkout.rows if isinstance(row, dict)}
    assert by_id[NOTE_ID][TIEBA_IMAGE_FIELD] == IMAGE_URL
    assert second_id in by_id["10376710030"][TIEBA_IMAGE_FIELD]


async def test_store_exception_consumes_capture_and_clears_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root)
    note = checkout.extractor_class().extract_note_detail_from_api(_api_data())
    checkout.failing_ids.add(NOTE_ID)
    with pytest.raises(RuntimeError, match="injected store failure"):
        await checkout.modules["store.tieba"].update_tieba_note(note)
    checkout.failing_ids.clear()

    await checkout.modules["store.tieba"].update_tieba_note(note)

    assert isinstance(checkout.rows[0], dict)
    assert TIEBA_IMAGE_FIELD not in checkout.rows[0]


async def test_private_field_collision_is_rejected_recursively(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root)
    with pytest.raises(RuntimeError, match="private Tieba media field collision"):
        await checkout.store_class().store_content({"nested": [{TIEBA_IMAGE_FIELD: IMAGE_URL}]})


def test_install_is_idempotent_for_the_same_creator_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root, creator_max_items=23)
    installed = checkout.client_class.get_all_notes_by_creator_url
    install_tieba_media_capture(checkout.root, creator_max_items=23)
    assert checkout.client_class.get_all_notes_by_creator_url is installed


def test_install_rejects_partial_installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root)
    checkout.store_class.store_content = checkout.original_store_content
    with pytest.raises(RuntimeError, match="partial Tieba media shim installation"):
        install_tieba_media_capture(checkout.root)


def test_install_rejects_modules_outside_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    checkout.modules["media_platform.tieba.help"].__file__ = str(tmp_path / "foreign" / "help.py")
    with pytest.raises(RuntimeError, match="did not load from the verified checkout"):
        install_tieba_media_capture(checkout.root)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "23", 1_001])
def test_install_rejects_invalid_creator_caps(value: object, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="creator_max_items"):
        install_tieba_media_capture(tmp_path, creator_max_items=value)  # type: ignore[arg-type]


async def test_creator_cap_requests_and_callbacks_twenty_plus_three_without_post_cap_sleep(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root, creator_max_items=23)
    client = checkout.client_class()
    pages = [list(range(1, 21)), list(range(21, 41))]
    page_calls: list[tuple[str, int, int]] = []
    detail_calls: list[str] = []
    callbacks: list[list[str]] = []
    sleeps: list[float] = []

    async def get_page(*, portrait: str, page_number: int, page_size: int) -> dict[str, object]:
        page_calls.append((portrait, page_number, page_size))
        values = pages.pop(0)
        return {
            "error_code": 0,
            "data": {
                "has_more": 1,
                "list": [{"thread_info": {"id": value, "tid": value}} for value in values],
            },
        }

    async def get_note(note_id: str) -> object:
        detail_calls.append(note_id)
        return checkout.note_class(note_id, f"https://tieba.baidu.com/p/{note_id}")

    async def callback(notes: list[object]) -> None:
        callbacks.append([note.note_id for note in notes])

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    client.get_notes_by_creator_portrait = get_page
    client.get_note_by_id = get_note
    monkeypatch.setattr(tieba_media.asyncio, "sleep", sleep)
    result = await client.get_all_notes_by_creator_url(
        "creator-portrait",
        crawl_interval=0.25,
        callback=callback,
        max_note_count=23,
    )

    assert [note.note_id for note in result] == [str(value) for value in range(1, 24)]
    assert page_calls == [("creator-portrait", 1, 20), ("creator-portrait", 2, 20)]
    assert detail_calls == [str(value) for value in range(1, 24)]
    assert callbacks == [[str(value) for value in range(1, 21)], ["21", "22", "23"]]
    assert sleeps == [0.25]
    assert pages == []


async def test_creator_cap_rejects_repeated_page_before_second_detail_batch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root, creator_max_items=21)
    client = checkout.client_class()
    pages = [list(range(1, 21)), list(range(1, 21))]
    details: list[str] = []

    async def get_page(*, portrait: str, page_number: int, page_size: int) -> dict[str, object]:
        del portrait, page_number, page_size
        values = pages.pop(0)
        return {
            "error_code": 0,
            "data": {"has_more": 1, "list": [{"thread_info": {"id": value}} for value in values]},
        }

    async def get_note(note_id: str) -> object:
        details.append(note_id)
        return checkout.note_class(note_id, f"https://tieba.baidu.com/p/{note_id}")

    client.get_notes_by_creator_portrait = get_page
    client.get_note_by_id = get_note
    with pytest.raises(RuntimeError, match="invalid Tieba creator pagination"):
        await client.get_all_notes_by_creator_url("creator-portrait", max_note_count=21)
    assert details == [str(value) for value in range(1, 21)]


async def test_creator_cap_rejects_short_nonterminal_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root, creator_max_items=21)
    client = checkout.client_class()

    async def get_page(*, portrait: str, page_number: int, page_size: int) -> dict[str, object]:
        del portrait, page_number, page_size
        return {
            "error_code": 0,
            "data": {"has_more": 1, "list": [{"thread_info": {"id": 1}}]},
        }

    client.get_notes_by_creator_portrait = get_page
    with pytest.raises(RuntimeError, match="invalid Tieba creator pagination"):
        await client.get_all_notes_by_creator_url("creator-portrait", max_note_count=21)


async def test_creator_cap_rejects_detail_identity_drift(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root, creator_max_items=1)
    client = checkout.client_class()

    async def get_page(*, portrait: str, page_number: int, page_size: int) -> dict[str, object]:
        del portrait, page_number, page_size
        return {
            "error_code": 0,
            "data": {"has_more": 0, "list": [{"thread_info": {"id": 1}}]},
        }

    async def get_note(_note_id: str) -> object:
        return checkout.note_class("2", "https://tieba.baidu.com/p/2")

    client.get_notes_by_creator_portrait = get_page
    client.get_note_by_id = get_note
    with pytest.raises(RuntimeError, match="detail contract drifted"):
        await client.get_all_notes_by_creator_url("creator-portrait", max_note_count=1)


async def test_creator_cap_rejects_caller_cap_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_tieba_media_capture(checkout.root, creator_max_items=3)
    with pytest.raises(RuntimeError, match="creator cap mismatch"):
        await checkout.client_class().get_all_notes_by_creator_url("creator-portrait", max_note_count=2)


async def test_no_creator_cap_preserves_original_method(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    original = checkout.client_class.get_all_notes_by_creator_url
    install_tieba_media_capture(checkout.root)
    assert checkout.client_class.get_all_notes_by_creator_url is original
    assert await checkout.client_class().get_all_notes_by_creator_url("creator") == ["unbounded-original"]
