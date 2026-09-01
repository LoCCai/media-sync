from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = PROJECT_ROOT / "upstreams.lock.json"
CORE_PATH = Path("media_platform") / "bilibili" / "core.py"
CLIENT_PATH = Path("media_platform") / "bilibili" / "client.py"
STORE_PATH = Path("store") / "bilibili" / "__init__.py"
RUNNER_PATH = PROJECT_ROOT / "src" / "media_sync" / "integrations" / "mediacrawler" / "runner.py"


def _pinned_tree(relative_path: Path) -> tuple[Path, ast.Module]:
    checkout = verify_mediacrawler_checkout(LOCK_PATH, license_acknowledged=True)
    source_path = checkout.root / relative_path
    return source_path, ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))


def _one_method(tree: ast.Module, class_name: str, method_name: str) -> ast.AsyncFunctionDef:
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name]
    assert len(classes) == 1
    methods = [node for node in classes[0].body if isinstance(node, ast.AsyncFunctionDef) and node.name == method_name]
    assert len(methods) == 1
    return methods[0]


def _one_function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    functions = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == name]
    assert len(functions) == 1
    return functions[0]


def test_pinned_core_preserves_aid_cid_play_boundary_but_uses_only_the_top_level_cid() -> None:
    _source_path, tree = _pinned_tree(CORE_PATH)
    info = _one_method(tree, "BilibiliCrawler", "get_video_info_task")
    play = _one_method(tree, "BilibiliCrawler", "get_video_play_url_task")
    media = _one_method(tree, "BilibiliCrawler", "get_bilibili_video")

    info_calls = {
        node.func.attr for node in ast.walk(info) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    play_calls = {
        node.func.attr for node in ast.walk(play) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    media_keys = {
        node.args[0].value
        for node in ast.walk(media)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    assert "get_video_info" in info_calls
    assert "get_video_play_url" in play_calls
    assert {"View", "aid", "cid", "durl", "url"}.issubset(media_keys)
    assert "pages" not in media_keys


def test_pinned_client_play_request_is_progressive_fnval_one_and_accepts_aid_cid() -> None:
    _source_path, tree = _pinned_tree(CLIENT_PATH)
    play = _one_method(tree, "BilibiliClient", "get_video_play_url")
    argument_names = [argument.arg for argument in play.args.args]
    assert argument_names[:3] == ["self", "aid", "cid"]

    constants = [node.value for node in ast.walk(play) if isinstance(node, ast.Constant)]
    assert "/x/player/wbi/playurl" in constants
    dictionaries = [node for node in ast.walk(play) if isinstance(node, ast.Dict)]
    serialized = ast.dump(ast.Module(body=dictionaries, type_ignores=[]), include_attributes=False)
    assert "'avid'" in serialized and "'cid'" in serialized and "'fnval'" in serialized
    assert "Constant(value=1)" in serialized


async def test_pinned_store_flattens_view_without_retaining_pages_or_cid() -> None:
    source_path, tree = _pinned_tree(STORE_PATH)
    update = _one_function(tree, "update_bilibili_video")
    stored_rows: list[dict[str, object]] = []

    class CapturingStore:
        async def store_content(self, content_item: dict[str, object]) -> None:
            stored_rows.append(content_item)

    namespace: dict[str, Any] = {
        "Dict": dict,
        "BiliStoreFactory": SimpleNamespace(create_store=lambda: CapturingStore()),
        "anonymize_user_id": lambda value: f"hash:{value}",
        "mask_nickname": lambda value: f"masked:{value}",
        "source_keyword_var": SimpleNamespace(get=lambda: "contract"),
        "utils": SimpleNamespace(
            get_current_timestamp=lambda: 1_725_000_000,
            logger=SimpleNamespace(info=lambda _message: None),
        ),
    }
    module = ast.fix_missing_locations(ast.Module(body=[update], type_ignores=[]))
    exec(compile(module, str(source_path), "exec"), namespace)
    view = {
        "aid": 987654321,
        "cid": 24680,
        "pages": [
            {"page": 1, "cid": 24680, "part": "P1"},
            {"page": 2, "cid": 97531, "part": "P2"},
        ],
        "title": "contract",
        "desc": "contract",
        "pubdate": 1_725_000_000,
        "pic": "https://i.example.test/cover.jpg",
        "owner": {"mid": 42, "name": "creator"},
        "stat": {},
    }

    await namespace["update_bilibili_video"]({"View": view})

    assert len(stored_rows) == 1
    assert stored_rows[0]["video_id"] == "987654321"
    assert "pages" not in stored_rows[0]
    assert "cid" not in stored_rows[0]


def test_media_sync_forward_child_installs_the_bilibili_capture_without_modifying_upstream() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert 'manifest.platform.value == "bili"' in source
    assert "install_bilibili_media_capture(verified.root)" in source
