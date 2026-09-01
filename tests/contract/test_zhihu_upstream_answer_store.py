from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = PROJECT_ROOT / "upstreams.lock.json"
HELP_PATH = Path("media_platform") / "zhihu" / "help.py"
CLIENT_PATH = Path("media_platform") / "zhihu" / "client.py"
CORE_PATH = Path("media_platform") / "zhihu" / "core.py"
CRAWLER_UTIL_PATH = Path("tools") / "crawler_util.py"
MODEL_PATH = Path("model") / "m_zhihu.py"
STORE_PATH = Path("store") / "zhihu" / "__init__.py"
STORE_IMPL_PATH = Path("store") / "zhihu" / "_store_impl.py"
RUNNER_PATH = PROJECT_ROOT / "src" / "media_sync" / "integrations" / "mediacrawler" / "runner.py"


def _pinned_tree(relative_path: Path) -> tuple[Path, ast.Module]:
    checkout = verify_mediacrawler_checkout(LOCK_PATH, license_acknowledged=True)
    source_path = checkout.root / relative_path
    return source_path, ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))


def _one_top_level_function(
    tree: ast.Module,
    name: str,
    expected_type: type[ast.FunctionDef] | type[ast.AsyncFunctionDef],
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    matches = [
        node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(matches) == 1, f"expected exactly one pinned upstream {name} definition"
    assert isinstance(matches[0], expected_type), f"pinned upstream {name} changed function kind"
    return matches[0]


def _one_class_method(
    tree: ast.Module,
    class_name: str,
    method_name: str,
    expected_type: type[ast.FunctionDef] | type[ast.AsyncFunctionDef],
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name]
    assert len(classes) == 1, f"expected exactly one pinned upstream {class_name} definition"
    matches = [
        node
        for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name
    ]
    assert len(matches) == 1, f"expected exactly one pinned upstream {class_name}.{method_name} definition"
    assert isinstance(matches[0], expected_type), f"pinned upstream {method_name} changed function kind"
    return matches[0]


def test_pinned_answer_extractor_receives_raw_html_then_discards_its_image_locator() -> None:
    source_path, tree = _pinned_tree(HELP_PATH)
    method = _one_class_method(tree, "ZhihuExtractor", "_extract_answer_content", ast.FunctionDef)
    util_source_path, util_tree = _pinned_tree(CRAWLER_UTIL_PATH)
    extract_text = _one_top_level_function(util_tree, "extract_text_from_html", ast.FunctionDef)

    class Content:
        pass

    namespace: dict[str, Any] = {
        "Dict": dict,
        "ZhihuContent": Content,
        "re": re,
        "zhihu_constant": SimpleNamespace(ZHIHU_URL="https://www.zhihu.com"),
    }
    module = ast.fix_missing_locations(ast.Module(body=[extract_text, method], type_ignores=[]))
    exec(compile(module, f"{util_source_path};{source_path}", "exec"), namespace)
    extractor = SimpleNamespace(
        _extract_content_or_comment_author=lambda _author: SimpleNamespace(
            creator_hash="hash:creator",
            user_nickname="masked:creator",
        )
    )
    image_url = "https://picx.zhimg.com/v2-contract.jpg?source=answer"
    answer = {
        "id": 101,
        "type": "answer",
        "content": f'<p>contract<img src="{image_url}"></p>',
        "question": {"id": 202},
        "author": {"id": "creator"},
    }

    extracted = namespace["_extract_answer_content"](extractor, answer)

    assert extracted.content_id == "101"
    assert extracted.question_id == "202"
    assert extracted.content_url == "https://www.zhihu.com/question/202/answer/101"
    assert extracted.content_text == "contract"
    assert image_url not in extracted.content_text
    assert image_url not in vars(extracted).values()
    assert not any("image" in key or "media" in key for key in vars(extracted))


def test_pinned_zhihu_content_carries_private_capture_without_serializing_it() -> None:
    source_path, tree = _pinned_tree(MODEL_PATH)
    model_imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    model_classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ZhihuContent"]
    assert len(model_classes) == 1, "expected exactly one pinned upstream ZhihuContent definition"

    namespace: dict[str, Any] = {}
    module = ast.fix_missing_locations(ast.Module(body=[*model_imports, model_classes[0]], type_ignores=[]))
    exec(compile(module, str(source_path), "exec"), namespace)
    content = namespace["ZhihuContent"](
        content_id="101",
        content_type="answer",
        content_text="contract",
        content_url="https://www.zhihu.com/question/202/answer/101",
        question_id="202",
    )

    private_field = "__media_sync_zhihu_answer_image_capture_v1__"
    private_marker = "private-capture-must-not-serialize"

    class Capture:
        def __repr__(self) -> str:
            return private_marker

    capture = Capture()
    object.__setattr__(content, private_field, capture)

    assert getattr(content, private_field) is capture
    assert private_field not in content.model_dump()
    for rendered in (content.model_dump_json(), repr(content)):
        assert private_field not in rendered
        assert private_marker not in rendered

    object.__delattr__(content, private_field)
    assert not hasattr(content, private_field)


def test_pinned_creator_source_requests_answer_html_but_ignores_the_configured_cap() -> None:
    _client_path, client_tree = _pinned_tree(CLIENT_PATH)
    get_page = _one_class_method(client_tree, "ZhiHuClient", "get_creator_answers", ast.AsyncFunctionDef)
    get_all = _one_class_method(client_tree, "ZhiHuClient", "get_all_anwser_by_creator", ast.AsyncFunctionDef)

    page_constants = {
        node.value for node in ast.walk(get_page) if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "/api/v4/members/" in page_constants
    assert "/answers" in page_constants
    includes = [value for value in page_constants if "data[*]." in value]
    assert len(includes) == 1
    assert "content" in includes[0]

    all_calls = [
        node.func.attr
        for node in ast.walk(get_all)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert all_calls.count("get_creator_answers") == 1
    assert "extract_content_list_from_creator" in all_calls
    assert any(isinstance(node, ast.While) for node in ast.walk(get_all))
    assert any(
        isinstance(node, ast.AugAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "offset"
        and isinstance(node.op, ast.Add)
        for node in ast.walk(get_all)
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "CRAWLER_MAX_NOTES_COUNT" for node in ast.walk(get_all)
    )


def test_pinned_creator_dispatch_calls_answers_only() -> None:
    _source_path, tree = _pinned_tree(CORE_PATH)
    method = _one_class_method(tree, "ZhihuCrawler", "get_creators_and_notes", ast.AsyncFunctionDef)
    calls = {
        node.func.attr
        for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "get_all_anwser_by_creator" in calls
    assert "get_all_articles_by_creator" not in calls
    assert "get_all_videos_by_creator" not in calls


async def test_pinned_update_flattens_model_before_calling_store() -> None:
    source_path, tree = _pinned_tree(STORE_PATH)
    update = _one_top_level_function(tree, "update_zhihu_content", ast.AsyncFunctionDef)
    stored_rows: list[dict[str, object]] = []

    class CapturingStore:
        async def store_content(self, row: dict[str, object]) -> None:
            stored_rows.append(row)

    namespace: dict[str, Any] = {
        "ZhihuContent": object,
        "source_keyword_var": SimpleNamespace(get=lambda: "contract-keyword"),
        "ZhihuStoreFactory": SimpleNamespace(create_store=lambda: CapturingStore()),
        "utils": SimpleNamespace(
            get_current_timestamp=lambda: 1_725_000_000,
            logger=SimpleNamespace(info=lambda _message: None),
        ),
    }
    module = ast.fix_missing_locations(ast.Module(body=[update], type_ignores=[]))
    exec(compile(module, str(source_path), "exec"), namespace)

    class Content:
        source_keyword = ""

        def model_dump(self) -> dict[str, object]:
            return {
                "content_id": "101",
                "question_id": "202",
                "content_type": "answer",
                "content_url": "https://www.zhihu.com/question/202/answer/101",
                "content_text": "plain text only",
            }

    await namespace["update_zhihu_content"](Content())

    assert stored_rows == [
        {
            "content_id": "101",
            "question_id": "202",
            "content_type": "answer",
            "content_url": "https://www.zhihu.com/question/202/answer/101",
            "content_text": "plain text only",
            "last_modify_ts": 1_725_000_000,
        }
    ]


async def test_pinned_jsonl_store_passes_content_mapping_to_writer_unchanged() -> None:
    source_path, tree = _pinned_tree(STORE_IMPL_PATH)
    method = _one_class_method(tree, "ZhihuJsonlStoreImplement", "store_content", ast.AsyncFunctionDef)
    writes: list[tuple[str, dict[str, object]]] = []

    class Writer:
        async def write_to_jsonl(self, *, item_type: str, item: dict[str, object]) -> None:
            writes.append((item_type, item))

    namespace: dict[str, Any] = {"Dict": dict}
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    exec(compile(module, str(source_path), "exec"), namespace)
    row = {
        "content_id": "101",
        "content_url": "https://www.zhihu.com/question/202/answer/101",
    }

    await namespace["store_content"](SimpleNamespace(writer=Writer()), row)

    assert writes == [("contents", row)]
    assert writes[0][1] is row


def test_scheduled_child_installs_zhihu_shim_with_manifest_max_items_after_main_import() -> None:
    tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"), filename=str(RUNNER_PATH))
    install_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "install_zhihu_media_capture"
    ]
    assert len(install_calls) == 1
    install = install_calls[0]
    assert len(install.args) == 1
    assert ast.dump(install.args[0], include_attributes=False) == ast.dump(
        ast.Attribute(value=ast.Name(id="verified", ctx=ast.Load()), attr="root", ctx=ast.Load()),
        include_attributes=False,
    )
    keywords = {keyword.arg: keyword.value for keyword in install.keywords}
    assert set(keywords) == {"creator_max_items"}
    assert ast.dump(keywords["creator_max_items"], include_attributes=False) == ast.dump(
        ast.Attribute(value=ast.Name(id="manifest", ctx=ast.Load()), attr="max_items", ctx=ast.Load()),
        include_attributes=False,
    )

    main_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "importlib"
        and node.func.attr == "import_module"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "main"
    ]
    watch_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_watch_upstream"
    ]
    assert len(main_imports) == len(watch_calls) == 1
    assert main_imports[0].lineno < install.lineno < watch_calls[0].lineno
