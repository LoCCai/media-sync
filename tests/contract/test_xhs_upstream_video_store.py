from __future__ import annotations

import ast
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = PROJECT_ROOT / "upstreams.lock.json"
XHS_STORE_PATH = Path("store") / "xhs" / "__init__.py"
XHS_VIDEO_HOST = "http://sns-video-bd.xhscdn.com"


class _ExtractedXhsStore:
    def __init__(
        self,
        *,
        get_video_url_arr: Callable[[dict[str, Any]], list[str]],
        update_xhs_note: Callable[[dict[str, Any]], Awaitable[None]],
        stored_rows: list[dict[str, Any]],
    ) -> None:
        self.get_video_url_arr = get_video_url_arr
        self.update_xhs_note = update_xhs_note
        self.stored_rows = stored_rows


def _extract_xhs_store_contract() -> _ExtractedXhsStore:
    checkout = verify_mediacrawler_checkout(LOCK_PATH, license_acknowledged=True)
    source_path = checkout.root / XHS_STORE_PATH
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))

    expected_nodes: tuple[tuple[str, type[ast.FunctionDef] | type[ast.AsyncFunctionDef]], ...] = (
        ("get_video_url_arr", ast.FunctionDef),
        ("update_xhs_note", ast.AsyncFunctionDef),
    )
    extracted_nodes: list[ast.stmt] = []
    for name, expected_type in expected_nodes:
        matches = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ]
        assert len(matches) == 1, f"expected exactly one pinned upstream {name} definition"
        assert isinstance(matches[0], expected_type), f"pinned upstream {name} changed function kind"
        extracted_nodes.append(matches[0])

    stored_rows: list[dict[str, Any]] = []

    class CapturingStore:
        async def store_content(self, row: dict[str, Any]) -> None:
            stored_rows.append(row)

    store = CapturingStore()
    namespace: dict[str, Any] = {
        "Dict": dict,
        "List": list,
        "XhsStoreFactory": SimpleNamespace(create_store=lambda: store),
        "anonymize_user_id": lambda user_id: f"hash:{user_id}",
        "mask_nickname": lambda nickname: f"masked:{nickname}",
        "source_keyword_var": SimpleNamespace(get=lambda: "contract-keyword"),
        "utils": SimpleNamespace(
            get_current_timestamp=lambda: 1_725_000_000,
            logger=SimpleNamespace(info=lambda _message: None),
        ),
    }
    extracted_module = ast.fix_missing_locations(ast.Module(body=extracted_nodes, type_ignores=[]))
    exec(compile(extracted_module, str(source_path), "exec"), namespace)

    return _ExtractedXhsStore(
        get_video_url_arr=namespace["get_video_url_arr"],
        update_xhs_note=namespace["update_xhs_note"],
        stored_rows=stored_rows,
    )


@pytest.fixture(scope="module")
def xhs_store() -> _ExtractedXhsStore:
    return _extract_xhs_store_contract()


@pytest.mark.parametrize(
    ("video", "expected_urls"),
    [
        (
            {
                "consumer": {
                    "origin_video_key": "snake-case.mp4",
                    "originVideoKey": "ignored-camel-case.mp4",
                },
                "media": {"stream": {"h264": [{"master_url": "https://ignored.example/video.mp4"}]}},
            },
            [f"{XHS_VIDEO_HOST}/snake-case.mp4"],
        ),
        (
            {"consumer": {"origin_video_key": "", "originVideoKey": "camel-case.mp4"}},
            [f"{XHS_VIDEO_HOST}/camel-case.mp4"],
        ),
        (
            {
                "consumer": {},
                "media": {
                    "stream": {
                        "h264": [
                            {"master_url": "https://video.example.test/first.mp4"},
                            {"master_url": "https://video.example.test/second.mp4"},
                        ]
                    }
                },
            },
            [
                "https://video.example.test/first.mp4",
                "https://video.example.test/second.mp4",
            ],
        ),
    ],
    ids=["origin-video-key", "originVideoKey", "h264-master-url-fallback"],
)
def test_pinned_get_video_url_arr_branches(
    xhs_store: _ExtractedXhsStore,
    video: dict[str, Any],
    expected_urls: list[str],
) -> None:
    assert xhs_store.get_video_url_arr({"type": "video", "video": video}) == expected_urls


async def test_pinned_update_xhs_note_emits_comma_delimited_video_and_cover_scalars(
    xhs_store: _ExtractedXhsStore,
) -> None:
    note_item: dict[str, Any] = {
        "note_id": "66fad51c000000001b0224b8",
        "type": "video",
        "title": "Pinned upstream contract",
        "desc": "contract fixture",
        "time": 1_724_000_000,
        "last_update_time": 1_724_000_001,
        "xsec_token": "contract-token",
        "user": {"user_id": "creator-id", "nickname": "creator-name"},
        "interact_info": {
            "liked_count": "11",
            "collected_count": "12",
            "comment_count": "13",
            "share_count": "14",
        },
        "video": {
            "consumer": {},
            "media": {
                "stream": {
                    "h264": [
                        {"master_url": "https://video.example.test/first.mp4"},
                        {"master_url": "https://video.example.test/second.mp4"},
                    ]
                }
            },
        },
        "image_list": [
            {"url_default": "https://image.example.test/cover-first.jpg"},
            {"url_default": "https://image.example.test/cover-second.webp"},
        ],
        "tag_list": [{"type": "topic", "name": "contract"}],
    }

    await xhs_store.update_xhs_note(note_item)

    assert len(xhs_store.stored_rows) == 1
    stored = xhs_store.stored_rows[0]
    assert stored["video_url"] == ("https://video.example.test/first.mp4,https://video.example.test/second.mp4")
    assert stored["image_list"] == (
        "https://image.example.test/cover-first.jpg,https://image.example.test/cover-second.webp"
    )
    assert [image["url"] for image in note_item["image_list"]] == [
        "https://image.example.test/cover-first.jpg",
        "https://image.example.test/cover-second.webp",
    ]
