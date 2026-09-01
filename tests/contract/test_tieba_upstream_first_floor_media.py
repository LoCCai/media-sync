from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = PROJECT_ROOT / "upstreams.lock.json"
HELP_PATH = Path("media_platform") / "tieba" / "help.py"
CLIENT_PATH = Path("media_platform") / "tieba" / "client.py"
CORE_PATH = Path("media_platform") / "tieba" / "core.py"
MODEL_PATH = Path("model") / "m_baidu_tieba.py"
STORE_PATH = Path("store") / "tieba" / "__init__.py"
STORE_IMPL_PATH = Path("store") / "tieba" / "_store_impl.py"
RUNNER_PATH = PROJECT_ROOT / "src" / "media_sync" / "integrations" / "mediacrawler" / "runner.py"
DETAIL_RUNNER_PATH = PROJECT_ROOT / "src" / "media_sync" / "integrations" / "mediacrawler" / "detail_runner.py"
NOTE_ID = "10376710029"
IMAGE_ID = "489c9a3df8dcd1009420153b348b4710b8122fc3"
IMAGE_URL = f"https://tiebapic.baidu.com/forum/pic/item/{IMAGE_ID}.jpg?tbpicau=2026-09-02-17_contract"
SECOND_IMAGE_ID = "0123456789abcdef0123456789abcdef01234567"
SECOND_IMAGE_URL = (
    f"https://tiebapic.baidu.com/forum/pic/item/{SECOND_IMAGE_ID}.jpg?tbpicau=2026-09-02-17_contract_second"
)


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


def _image_item(*, identity: str = IMAGE_ID, image_url: str = IMAGE_URL) -> dict[str, object]:
    query = image_url.split("?", 1)[1]
    return {
        "type": 3,
        "origin_src": image_url,
        "cdn_src": f"https://tiebapic.baidu.com/forum/w%3D720/sign=a/{identity}.jpg?{query}",
        "big_cdn_src": f"https://tiebapic.baidu.com/forum/w%3D1920/sign=b/{identity}.jpg?{query}",
        "cdn_src_active": f"https://tiebapic.baidu.com/forum/w%3D720/sign=c/{identity}.jpg?{query}",
        "pic_id": 300_933_013_320,
        "bsize": "560,303",
        "origin_size": 65_144,
        "is_long_pic": 0,
        "show_original_btn": 1,
    }


def test_pinned_extractor_receives_current_structured_item_then_discards_every_locator() -> None:
    source_path, tree = _pinned_tree(HELP_PATH)
    extract_text = _one_class_method(tree, "TieBaExtractor", "_extract_api_content_text", ast.FunctionDef)
    extract_detail = _one_class_method(tree, "TieBaExtractor", "extract_note_detail_from_api", ast.FunctionDef)

    class Note:
        def __init__(self, **values: object) -> None:
            vars(self).update(values)

    extractor_class = ast.ClassDef(
        name="ContractExtractor",
        bases=[],
        keywords=[],
        body=[extract_text, extract_detail],
        decorator_list=[],
    )
    namespace: dict[str, Any] = {
        "Any": Any,
        "Dict": dict,
        "List": list,
        "TiebaNote": Note,
        "anonymize_user_id": lambda value: f"hash:{value}",
        "const": SimpleNamespace(TIEBA_URL="https://tieba.baidu.com"),
        "mask_nickname": lambda value: f"masked:{value}",
        "utils": SimpleNamespace(get_time_str_from_unix_time=lambda value: str(value)),
    }
    module = ast.fix_missing_locations(ast.Module(body=[extractor_class], type_ignores=[]))
    exec(compile(module, str(source_path), "exec"), namespace)
    extractor_type = namespace["ContractExtractor"]
    extractor_type._normalize_text = staticmethod(lambda value: str(value).strip())
    extractor_type._ensure_tieba_suffix = staticmethod(lambda value: f"{value}吧")
    extractor_type._api_user_map = staticmethod(lambda _value: {})
    extractor_type._api_user_link = staticmethod(lambda _value: "")
    extractor_type._tieba_link_from_name = staticmethod(lambda value: f"https://tieba.baidu.com/f?kw={value}")
    extractor_type._clean_title = staticmethod(lambda value, _tieba_name: value)
    extractor = extractor_type()
    response = {
        "thread": {"id": NOTE_ID, "title": "contract", "reply_num": 2},
        "first_floor": {
            "tid": NOTE_ID,
            "time": 1_725_000_000,
            "content": [
                {"type": 0, "text": "plain text"},
                _image_item(),
                _image_item(identity=SECOND_IMAGE_ID, image_url=SECOND_IMAGE_URL),
            ],
        },
        "forum": {"name": "测试"},
        "page": {"total_page": 1},
    }

    extracted = extractor.extract_note_detail_from_api(response)

    assert extracted.note_id == NOTE_ID
    assert extracted.note_url == f"https://tieba.baidu.com/p/{NOTE_ID}"
    assert extracted.desc == "plain text"
    assert IMAGE_URL not in vars(extracted).values()
    assert SECOND_IMAGE_URL not in vars(extracted).values()
    assert not any("image" in key or "media" in key or "src" in key for key in vars(extracted))


def test_pinned_tieba_note_carries_private_capture_without_serializing_it() -> None:
    source_path, tree = _pinned_tree(MODEL_PATH)
    model_imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    model_classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "TiebaNote"]
    assert len(model_classes) == 1
    namespace: dict[str, Any] = {}
    module = ast.fix_missing_locations(ast.Module(body=[*model_imports, model_classes[0]], type_ignores=[]))
    exec(compile(module, str(source_path), "exec"), namespace)
    note = namespace["TiebaNote"](
        note_id=NOTE_ID,
        title="contract",
        note_url=f"https://tieba.baidu.com/p/{NOTE_ID}",
        tieba_name="测试吧",
        tieba_link="https://tieba.baidu.com/f?kw=test",
    )
    private_field = "__media_sync_tieba_first_floor_image_capture_v1__"
    private_marker = "private-tieba-capture-must-not-serialize"

    class Capture:
        def __repr__(self) -> str:
            return private_marker

    capture = Capture()
    object.__setattr__(note, private_field, capture)

    assert getattr(note, private_field) is capture
    assert private_field not in note.model_dump()
    for rendered in (note.model_dump_json(), repr(note)):
        assert private_field not in rendered
        assert private_marker not in rendered

    object.__delattr__(note, private_field)
    assert not hasattr(note, private_field)


def test_pinned_client_and_core_keep_the_exact_detail_gather_parent_store_boundary() -> None:
    _client_path, client_tree = _pinned_tree(CLIENT_PATH)
    page = _one_class_method(client_tree, "BaiduTieBaClient", "_get_pc_page_data", ast.AsyncFunctionDef)
    detail = _one_class_method(client_tree, "BaiduTieBaClient", "get_note_by_id", ast.AsyncFunctionDef)
    creator = _one_class_method(
        client_tree,
        "BaiduTieBaClient",
        "get_all_notes_by_creator_url",
        ast.AsyncFunctionDef,
    )
    page_constants = {
        node.value for node in ast.walk(page) if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "/c/f/pb/page_pc" in page_constants
    assert {"kz", "tbs", "pn"}.issubset(
        {
            key.value
            for node in ast.walk(page)
            if isinstance(node, ast.Dict)
            for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
    )
    detail_calls = {
        node.func.attr
        for node in ast.walk(detail)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "_get_pc_page_data" in detail_calls
    assert "extract_note_detail_from_api" in detail_calls
    creator_calls = {
        node.func.attr
        for node in ast.walk(creator)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "get_notes_by_creator_portrait" in creator_calls
    assert "extract_creator_thread_id_list_from_api" in creator_calls
    assert "gather" in creator_calls
    assert "get_note_by_id" in creator_calls

    _core_path, core_tree = _pinned_tree(CORE_PATH)
    specified = _one_class_method(core_tree, "TieBaCrawler", "get_specified_notes", ast.AsyncFunctionDef)
    calls = [
        node.func.attr
        for node in ast.walk(specified)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert calls.count("gather") == 1
    assert calls.count("update_tieba_note") == 1
    gather_line = next(
        node.lineno
        for node in ast.walk(specified)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "gather"
    )
    update_line = next(
        node.lineno
        for node in ast.walk(specified)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "update_tieba_note"
    )
    assert gather_line < update_line


async def test_pinned_update_flattens_model_before_calling_store() -> None:
    source_path, tree = _pinned_tree(STORE_PATH)
    update = _one_top_level_function(tree, "update_tieba_note", ast.AsyncFunctionDef)
    stored_rows: list[dict[str, object]] = []

    class CapturingStore:
        async def store_content(self, row: dict[str, object]) -> None:
            stored_rows.append(row)

    namespace: dict[str, Any] = {
        "TiebaNote": object,
        "source_keyword_var": SimpleNamespace(get=lambda: "contract-keyword"),
        "TieBaStoreFactory": SimpleNamespace(create_store=lambda: CapturingStore()),
        "utils": SimpleNamespace(
            get_current_timestamp=lambda: 1_725_000_000,
            logger=SimpleNamespace(info=lambda _message: None),
        ),
    }
    module = ast.fix_missing_locations(ast.Module(body=[update], type_ignores=[]))
    exec(compile(module, str(source_path), "exec"), namespace)

    class Note:
        source_keyword = ""

        def model_dump(self) -> dict[str, object]:
            return {
                "note_id": NOTE_ID,
                "note_url": f"https://tieba.baidu.com/p/{NOTE_ID}",
                "desc": "plain text only",
            }

    await namespace["update_tieba_note"](Note())

    assert stored_rows == [
        {
            "note_id": NOTE_ID,
            "note_url": f"https://tieba.baidu.com/p/{NOTE_ID}",
            "desc": "plain text only",
            "last_modify_ts": 1_725_000_000,
        }
    ]


async def test_pinned_jsonl_store_passes_content_mapping_to_writer_unchanged() -> None:
    source_path, tree = _pinned_tree(STORE_IMPL_PATH)
    method = _one_class_method(tree, "TieBaJsonlStoreImplement", "store_content", ast.AsyncFunctionDef)
    writes: list[tuple[str, dict[str, object]]] = []

    class Writer:
        async def write_to_jsonl(self, *, item_type: str, item: dict[str, object]) -> None:
            writes.append((item_type, item))

    namespace: dict[str, Any] = {"Dict": dict}
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    exec(compile(module, str(source_path), "exec"), namespace)
    row = {"note_id": NOTE_ID, "note_url": f"https://tieba.baidu.com/p/{NOTE_ID}"}

    await namespace["store_content"](SimpleNamespace(writer=Writer()), row)

    assert writes == [("contents", row)]
    assert writes[0][1] is row


def _install_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "install_tieba_media_capture"
    ]


def test_scheduled_and_detail_children_install_tieba_capture_at_the_verified_boundary() -> None:
    scheduled_calls = _install_calls(RUNNER_PATH)
    detail_calls = _install_calls(DETAIL_RUNNER_PATH)
    assert len(scheduled_calls) == len(detail_calls) == 1

    scheduled = scheduled_calls[0]
    assert len(scheduled.args) == 1
    keywords = {keyword.arg: keyword.value for keyword in scheduled.keywords}
    assert set(keywords) == {"creator_max_items"}
    assert ast.dump(keywords["creator_max_items"], include_attributes=False) == ast.dump(
        ast.Attribute(value=ast.Name(id="manifest", ctx=ast.Load()), attr="max_items", ctx=ast.Load()),
        include_attributes=False,
    )

    detail = detail_calls[0]
    assert len(detail.args) == 1
    assert detail.keywords == []
    assert ast.dump(detail.args[0], include_attributes=False) == ast.dump(
        ast.Attribute(value=ast.Name(id="request", ctx=ast.Load()), attr="checkout_root", ctx=ast.Load()),
        include_attributes=False,
    )

    runner_tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"), filename=str(RUNNER_PATH))
    main_import = next(
        node
        for node in ast.walk(runner_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "import_module"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "main"
    )
    watch = next(
        node
        for node in ast.walk(runner_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_watch_upstream"
    )
    assert main_import.lineno < scheduled.lineno < watch.lineno
