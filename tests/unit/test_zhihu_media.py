from __future__ import annotations

import asyncio
import types
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from media_sync.integrations.mediacrawler import zhihu_media
from media_sync.integrations.mediacrawler.zhihu_media import (
    ZHIHU_IMAGE_FIELD,
    install_zhihu_media_capture,
    is_zhihu_positive_id,
    validate_zhihu_answer_url,
    validate_zhihu_image_url,
)

IMAGE_URL = "https://picx.zhimg.com/v2-a1b2c3.jpg?source=answer&token=short"


@dataclass
class _FakeCheckout:
    root: Path
    extractor_class: type[Any]
    client_class: type[Any]
    store_class: type[Any]
    content_class: type[Any]
    rows: list[object]
    failing_ids: set[str]
    modules: dict[str, types.ModuleType]
    original_store_content: Any


def _answer(
    html: str,
    *,
    answer_id: object = 101,
    question_id: object = 202,
    content_type: str = "answer",
) -> dict[str, object]:
    return {
        "id": answer_id,
        "type": content_type,
        "content": html,
        "question": {"id": question_id},
    }


def _fake_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _FakeCheckout:
    root = tmp_path / "MediaCrawler"
    rows: list[object] = []
    failing_ids: set[str] = set()

    class Content:
        def __init__(self, content_id: str, question_id: str, content_type: str, content_url: str) -> None:
            self.content_id = content_id
            self.question_id = question_id
            self.content_type = content_type
            self.content_url = content_url

        def model_dump(self) -> dict[str, object]:
            return {
                "content_id": self.content_id,
                "question_id": self.question_id,
                "content_type": self.content_type,
                "content_url": self.content_url,
            }

    class Extractor:
        def _extract_answer_content(self, answer: Mapping[str, object]) -> Content:
            content_id = str(answer.get("id") or "")
            question = answer.get("question")
            question_id = str(question.get("id") or "") if isinstance(question, Mapping) else ""
            return Content(
                content_id,
                question_id,
                str(answer.get("type") or ""),
                f"https://www.zhihu.com/question/{question_id}/answer/{content_id}",
            )

        def extract_content_list_from_creator(self, data: list[Any]) -> list[Any]:
            return list(data)

    class JsonlStore:
        async def store_content(self, content_item: object) -> None:
            content_id = content_item.get("content_id") if isinstance(content_item, Mapping) else None
            if content_id in failing_ids:
                raise RuntimeError("injected store failure")
            rows.append(dict(content_item) if isinstance(content_item, Mapping) else content_item)

    original_store_content = JsonlStore.store_content

    async def update_zhihu_content(content_item: Content) -> None:
        await JsonlStore().store_content(content_item.model_dump())

    class Client:
        async def get_all_anwser_by_creator(
            self,
            url_token: str,
            crawl_interval: float = 1.0,
            callback: Any = None,
        ) -> list[str]:
            del url_token, crawl_interval, callback
            return ["unbounded-original"]

    package_names = ("media_platform", "media_platform.zhihu", "store")
    modules: dict[str, types.ModuleType] = {}
    for name in package_names:
        module = types.ModuleType(name)
        module.__file__ = str(root / Path(*name.split(".")) / "__init__.py")
        module.__path__ = []  # type: ignore[attr-defined]
        modules[name] = module

    help_module = types.ModuleType("media_platform.zhihu.help")
    help_module.__file__ = str(root / "media_platform" / "zhihu" / "help.py")
    help_module.ZhihuExtractor = Extractor
    modules[help_module.__name__] = help_module

    client_module = types.ModuleType("media_platform.zhihu.client")
    client_module.__file__ = str(root / "media_platform" / "zhihu" / "client.py")
    client_module.ZhiHuClient = Client
    modules[client_module.__name__] = client_module

    store_module = types.ModuleType("store.zhihu")
    store_module.__file__ = str(root / "store" / "zhihu" / "__init__.py")
    store_module.__path__ = []  # type: ignore[attr-defined]
    store_module.ZhihuJsonlStoreImplement = JsonlStore
    store_module.update_zhihu_content = update_zhihu_content
    modules[store_module.__name__] = store_module

    impl_module = types.ModuleType("store.zhihu._store_impl")
    impl_module.__file__ = str(root / "store" / "zhihu" / "_store_impl.py")
    impl_module.ZhihuJsonlStoreImplement = JsonlStore
    modules[impl_module.__name__] = impl_module

    for name, module in modules.items():
        monkeypatch.setitem(__import__("sys").modules, name, module)

    return _FakeCheckout(
        root=root,
        extractor_class=Extractor,
        client_class=Client,
        store_class=JsonlStore,
        content_class=Content,
        rows=rows,
        failing_ids=failing_ids,
        modules=modules,
        original_store_content=original_store_content,
    )


@pytest.mark.parametrize("value", ["1", "9", "101", str(2**63 - 1)])
def test_positive_id_accepts_canonical_values(value: str) -> None:
    assert is_zhihu_positive_id(value)


@pytest.mark.parametrize(
    "value",
    [None, True, 1, "", "0", "01", "+1", " 1", "1 ", "1.0", "\uff11\uff12", str(2**63)],
)
def test_positive_id_rejects_noncanonical_values(value: object) -> None:
    assert not is_zhihu_positive_id(value)


@pytest.mark.parametrize(
    "value",
    [
        "https://zhimg.com/root.jpg",
        "https://picx.zhimg.com/v2-a1b2c3.jpg?source=answer&token=short",
        "https://pic1.zhimg.com/80/v2-deadbeef.jpeg",
        "https://cdn-a.zhimg.com/path/image.png?token=short",
        "https://PIC2.ZHIMG.COM:443/v2-feed.WEBP",
    ],
)
def test_image_url_accepts_apex_subdomains_query_case_and_default_port(value: str) -> None:
    assert validate_zhihu_image_url(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        " https://picx.zhimg.com/x.jpg",
        "https://picx.zhimg.com/x.jpg ",
        "http://picx.zhimg.com/x.jpg",
        "https://example.com/x.jpg",
        "https://zhimg.com.evil.test/x.jpg",
        "https://-bad.zhimg.com/x.jpg",
        "https://user@picx.zhimg.com/x.jpg",
        "https://picx.zhimg.com:/x.jpg",
        "https://picx.zhimg.com:0443/x.jpg",
        "https://picx.zhimg.com:444/x.jpg",
        "https://picx.zhimg.com/",
        "https://picx.zhimg.com/x.gif",
        "https://picx.zhimg.com/x.svg",
        "https://picx.zhimg.com/x.jpg?",
        "https://picx.zhimg.com/x.jpg#",
        "https://picx.zhimg.com/x.jpg#fragment",
        "https://picx.zhimg.com/x.jpg\n",
        "https://picx.zhimg.com\\evil.test/x.jpg",
        "https://picx.zhimg.com./x.jpg",
        "https://例子.zhimg.com/x.jpg",
    ],
)
def test_image_url_rejects_ambiguous_or_unsupported_values(value: str) -> None:
    with pytest.raises(ValueError, match="invalid Zhihu image URL"):
        validate_zhihu_image_url(value)


def test_image_url_rejects_non_string_and_excessive_length() -> None:
    with pytest.raises(ValueError):
        validate_zhihu_image_url(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        validate_zhihu_image_url(f"https://picx.zhimg.com/{'a' * 4_096}.jpg")


def test_answer_url_is_strictly_canonical_and_can_be_bound_to_ids() -> None:
    value = "https://www.zhihu.com/question/202/answer/101"
    assert validate_zhihu_answer_url(value) == value
    assert validate_zhihu_answer_url(value, answer_id="101", question_id="202") == value


@pytest.mark.parametrize(
    "value",
    [
        "http://www.zhihu.com/question/202/answer/101",
        "https://zhihu.com/question/202/answer/101",
        "https://WWW.ZHIHU.COM/question/202/answer/101",
        "https://www.zhihu.com:443/question/202/answer/101",
        "https://www.zhihu.com/question/202/answer/101/",
        "https://www.zhihu.com/question/0202/answer/101",
        "https://www.zhihu.com/question/202/answer/0",
        "https://www.zhihu.com/question/202/answer/101?",
        "https://www.zhihu.com/question/202/answer/101?token=secret",
        "https://www.zhihu.com/question/202/answer/101#",
        "https://www.zhihu.com/question/202/answer/101#fragment",
    ],
)
def test_answer_url_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(ValueError, match="invalid Zhihu answer URL"):
        validate_zhihu_answer_url(value)


def test_answer_url_rejects_expected_id_mismatch() -> None:
    value = "https://www.zhihu.com/question/202/answer/101"
    with pytest.raises(ValueError):
        validate_zhihu_answer_url(value, answer_id="102")
    with pytest.raises(ValueError):
        validate_zhihu_answer_url(value, question_id="203")
    with pytest.raises(ValueError, match="invalid Zhihu answer ID"):
        validate_zhihu_answer_url(value, answer_id="01")


@pytest.mark.parametrize("attribute", ["data-original", "data-actualsrc", "src"])
async def test_capture_injects_one_valid_managed_image_attribute(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    attribute: str,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root)
    content = checkout.extractor_class()._extract_answer_content(
        _answer(f'<p>text<img {attribute}="{IMAGE_URL.replace("&", "&amp;")}"></p>')
    )

    await checkout.modules["store.zhihu"].update_zhihu_content(content)

    assert checkout.rows == [
        {
            "content_id": "101",
            "question_id": "202",
            "content_type": "answer",
            "content_url": "https://www.zhihu.com/question/202/answer/101",
            ZHIHU_IMAGE_FIELD: IMAGE_URL,
        }
    ]


@pytest.mark.parametrize(
    "html",
    [
        "plain text",
        f'<img src="{IMAGE_URL}"><img src="https://picx.zhimg.com/second.png">',
        f'<img src="{IMAGE_URL}" src="{IMAGE_URL}">',
        f'<img data-original="" src="{IMAGE_URL}">',
        f'<img data-original src="{IMAGE_URL}">',
        f'<img src="{IMAGE_URL}" srcset="https://picx.zhimg.com/second.png 2x">',
        f'<img src="{IMAGE_URL}" data-src="https://picx.zhimg.com/second.png">',
        f'<img src="{IMAGE_URL}" data-lazy-srcset="https://picx.zhimg.com/second.png 2x">',
        '<img src="https://picx.zhimg.com/animated.gif">',
        '<img src="https://picx.zhimg.com/vector.svg">',
        '<img src="https://example.test/foreign.jpg">',
        f'<video></video><img src="{IMAGE_URL}">',
        f'<picture><img src="{IMAGE_URL}"></picture>',
        f'<source src="movie.mp4"><img src="{IMAGE_URL}">',
        f'<audio></audio><img src="{IMAGE_URL}">',
        f'<iframe></iframe><img src="{IMAGE_URL}">',
        f'<object></object><img src="{IMAGE_URL}">',
        f'<svg></svg><img src="{IMAGE_URL}">',
        f'<div data-video-id="player"><img src="{IMAGE_URL}"></div>',
        f'<div data-player="video"><img src="{IMAGE_URL}"></div>',
    ],
)
async def test_capture_fails_closed_for_ambiguous_or_nonstatic_html(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    html: str,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root)
    content = checkout.extractor_class()._extract_answer_content(_answer(html))

    await checkout.modules["store.zhihu"].update_zhihu_content(content)

    assert isinstance(checkout.rows[0], dict)
    assert ZHIHU_IMAGE_FIELD not in checkout.rows[0]


async def test_capture_uses_frozen_managed_attribute_priority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root)
    preferred = "https://pic1.zhimg.com/preferred.webp?token=preferred"
    fallback = "https://pic2.zhimg.com/fallback.jpg?token=fallback"
    content = checkout.extractor_class()._extract_answer_content(
        _answer(f'<img src="{fallback}" data-original="{preferred}">')
    )

    await checkout.modules["store.zhihu"].update_zhihu_content(content)

    assert isinstance(checkout.rows[0], dict)
    assert checkout.rows[0][ZHIHU_IMAGE_FIELD] == preferred


@pytest.mark.parametrize(
    "answer",
    [
        _answer(f'<img src="{IMAGE_URL}">', content_type="article"),
        _answer(f'<img src="{IMAGE_URL}">', answer_id="01"),
        _answer(f'<img src="{IMAGE_URL}">', question_id=0),
    ],
)
async def test_capture_requires_an_ordinary_answer_with_positive_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    answer: dict[str, object],
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root)
    content = checkout.extractor_class()._extract_answer_content(answer)
    await checkout.modules["store.zhihu"].update_zhihu_content(content)
    assert isinstance(checkout.rows[0], dict)
    assert ZHIHU_IMAGE_FIELD not in checkout.rows[0]


async def test_capture_rejects_html_over_one_mib(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root)
    html = f'<img src="{IMAGE_URL}">' + ("x" * 1_048_576)
    content = checkout.extractor_class()._extract_answer_content(_answer(html))
    await checkout.modules["store.zhihu"].update_zhihu_content(content)
    assert isinstance(checkout.rows[0], dict)
    assert ZHIHU_IMAGE_FIELD not in checkout.rows[0]


async def test_capture_binds_exact_object_ids_and_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root)
    captured = checkout.extractor_class()._extract_answer_content(_answer(f'<img src="{IMAGE_URL}">'))
    clone = checkout.content_class("101", "202", "answer", "https://www.zhihu.com/question/202/answer/101")

    await checkout.modules["store.zhihu"].update_zhihu_content(clone)
    await checkout.modules["store.zhihu"].update_zhihu_content(captured)

    assert isinstance(checkout.rows[0], dict) and ZHIHU_IMAGE_FIELD not in checkout.rows[0]
    assert isinstance(checkout.rows[1], dict) and checkout.rows[1][ZHIHU_IMAGE_FIELD] == IMAGE_URL


async def test_mutated_binding_is_consumed_without_later_replay(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root)
    content = checkout.extractor_class()._extract_answer_content(_answer(f'<img src="{IMAGE_URL}">'))
    canonical = content.content_url
    content.content_url = "https://www.zhihu.com/question/202/answer/999"
    await checkout.modules["store.zhihu"].update_zhihu_content(content)
    content.content_url = canonical
    await checkout.modules["store.zhihu"].update_zhihu_content(content)
    assert all(isinstance(row, dict) and ZHIHU_IMAGE_FIELD not in row for row in checkout.rows)


async def test_context_is_isolated_across_concurrent_answer_tasks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root)

    async def run_one(answer_id: int, image_url: str) -> None:
        content = checkout.extractor_class()._extract_answer_content(
            _answer(f'<img src="{image_url}">', answer_id=answer_id)
        )
        await asyncio.sleep(0)
        await checkout.modules["store.zhihu"].update_zhihu_content(content)

    first = "https://pic1.zhimg.com/first.jpg"
    second = "https://pic2.zhimg.com/second.webp?token=two"
    await asyncio.gather(run_one(101, first), run_one(102, second))

    by_id = {row["content_id"]: row for row in checkout.rows if isinstance(row, dict)}
    assert by_id["101"][ZHIHU_IMAGE_FIELD] == first
    assert by_id["102"][ZHIHU_IMAGE_FIELD] == second


async def test_capture_crosses_gather_child_to_parent_store_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root)

    async def extract_in_child(answer_id: int, image_url: str) -> object:
        await asyncio.sleep(0)
        return checkout.extractor_class()._extract_answer_content(
            _answer(f'<img src="{image_url}">', answer_id=answer_id)
        )

    first = "https://pic1.zhimg.com/gather-first.jpg"
    second = "https://pic2.zhimg.com/gather-second.webp?token=two"
    contents = await asyncio.gather(extract_in_child(101, first), extract_in_child(102, second))
    for content in contents:
        await checkout.modules["store.zhihu"].update_zhihu_content(content)

    by_id = {row["content_id"]: row for row in checkout.rows if isinstance(row, dict)}
    assert by_id["101"][ZHIHU_IMAGE_FIELD] == first
    assert by_id["102"][ZHIHU_IMAGE_FIELD] == second


async def test_store_exception_clears_active_and_object_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root)
    content = checkout.extractor_class()._extract_answer_content(_answer(f'<img src="{IMAGE_URL}">'))
    checkout.failing_ids.add("101")
    with pytest.raises(RuntimeError, match="injected store failure"):
        await checkout.modules["store.zhihu"].update_zhihu_content(content)
    checkout.failing_ids.clear()

    await checkout.modules["store.zhihu"].update_zhihu_content(content)

    assert isinstance(checkout.rows[0], dict)
    assert ZHIHU_IMAGE_FIELD not in checkout.rows[0]


async def test_private_field_collision_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root)
    with pytest.raises(RuntimeError, match="private Zhihu media field collision"):
        await checkout.store_class().store_content({ZHIHU_IMAGE_FIELD: IMAGE_URL})


def test_install_is_idempotent_for_the_same_creator_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root, creator_max_items=3)
    installed = checkout.client_class.get_all_anwser_by_creator
    install_zhihu_media_capture(checkout.root, creator_max_items=3)
    assert checkout.client_class.get_all_anwser_by_creator is installed


def test_install_rejects_partial_installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root)
    checkout.store_class.store_content = checkout.original_store_content
    with pytest.raises(RuntimeError, match="partial Zhihu media shim installation"):
        install_zhihu_media_capture(checkout.root)


def test_install_rejects_modules_outside_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    checkout.modules["media_platform.zhihu.help"].__file__ = str(tmp_path / "foreign" / "help.py")
    with pytest.raises(RuntimeError, match="did not load from the verified checkout"):
        install_zhihu_media_capture(checkout.root)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "3"])
def test_install_rejects_invalid_creator_caps(value: object, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="creator_max_items"):
        install_zhihu_media_capture(tmp_path, creator_max_items=value)  # type: ignore[arg-type]


async def test_creator_cap_limits_every_request_and_stops_without_extra_page_or_sleep(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root, creator_max_items=23)
    client = checkout.client_class()
    client._extractor = SimpleNamespace(
        extract_content_list_from_creator=lambda data: [
            SimpleNamespace(content_id=str(item), value=item) for item in data
        ]
    )
    pages = [
        {"data": list(range(1, 21)), "paging": {"is_end": False}},
        {"data": list(range(21, 24)), "paging": {"is_end": False}},
    ]
    calls: list[tuple[str, int, int]] = []
    callbacks: list[list[int]] = []
    sleeps: list[float] = []

    async def get_page(_self: object, token: str, offset: int, limit: int) -> dict[str, object]:
        calls.append((token, offset, limit))
        return pages.pop(0)

    async def callback(items: list[object]) -> None:
        callbacks.append([item.value for item in items])

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    client.get_creator_answers = types.MethodType(get_page, client)
    monkeypatch.setattr(zhihu_media.asyncio, "sleep", sleep)
    result = await client.get_all_anwser_by_creator("creator-token", crawl_interval=0.25, callback=callback)

    assert [item.value for item in result] == list(range(1, 24))
    assert calls == [("creator-token", 0, 20), ("creator-token", 20, 3)]
    assert callbacks == [list(range(1, 21)), list(range(21, 24))]
    assert sleeps == [0.25]
    assert pages == []


@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        {"data": {}, "paging": {"is_end": True}},
        {"data": [], "paging": []},
        {"data": [], "paging": {"is_end": 1}},
        {"data": [], "paging": {"is_end": False}},
        {"data": [1, 2], "paging": {"is_end": True}},
    ],
)
async def test_creator_cap_rejects_malformed_or_oversized_pages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response: object,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root, creator_max_items=1)
    client = checkout.client_class()
    client._extractor = SimpleNamespace(extract_content_list_from_creator=lambda data: list(data))

    async def get_page(_self: object, _token: str, _offset: int, _limit: int) -> object:
        return response

    client.get_creator_answers = types.MethodType(get_page, client)
    with pytest.raises(RuntimeError, match="invalid Zhihu creator"):
        await client.get_all_anwser_by_creator("creator-token")


async def test_creator_cap_rejects_extractor_cardinality_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root, creator_max_items=2)
    client = checkout.client_class()
    client._extractor = SimpleNamespace(extract_content_list_from_creator=lambda _data: [])

    async def get_page(_self: object, _token: str, _offset: int, _limit: int) -> object:
        return {"data": [1], "paging": {"is_end": True}}

    client.get_creator_answers = types.MethodType(get_page, client)
    with pytest.raises(RuntimeError, match="extractor contract drifted"):
        await client.get_all_anwser_by_creator("creator-token")


async def test_creator_cap_rejects_repeated_content_across_progressing_pages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root, creator_max_items=21)
    client = checkout.client_class()
    client._extractor = SimpleNamespace(
        extract_content_list_from_creator=lambda data: [SimpleNamespace(content_id=str(item)) for item in data]
    )
    pages = [
        {"data": list(range(101, 121)), "paging": {"is_end": False}},
        {"data": [120], "paging": {"is_end": False}},
    ]

    async def get_page(_self: object, _token: str, _offset: int, _limit: int) -> object:
        return pages.pop(0)

    client.get_creator_answers = types.MethodType(get_page, client)
    with pytest.raises(RuntimeError, match="invalid Zhihu creator pagination"):
        await client.get_all_anwser_by_creator("creator-token")


async def test_creator_cap_rejects_short_nonterminal_page(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    install_zhihu_media_capture(checkout.root, creator_max_items=20)
    client = checkout.client_class()
    client._extractor = SimpleNamespace(
        extract_content_list_from_creator=lambda data: [SimpleNamespace(content_id=str(item)) for item in data]
    )

    async def get_page(_self: object, _token: str, _offset: int, _limit: int) -> object:
        return {"data": list(range(101, 120)), "paging": {"is_end": False}}

    client.get_creator_answers = types.MethodType(get_page, client)
    with pytest.raises(RuntimeError, match="invalid Zhihu creator pagination"):
        await client.get_all_anwser_by_creator("creator-token")


async def test_no_creator_cap_preserves_original_unbounded_method(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = _fake_checkout(monkeypatch, tmp_path)
    original = checkout.client_class.get_all_anwser_by_creator
    install_zhihu_media_capture(checkout.root)
    assert checkout.client_class.get_all_anwser_by_creator is original
    assert await checkout.client_class().get_all_anwser_by_creator("creator-token") == ["unbounded-original"]
