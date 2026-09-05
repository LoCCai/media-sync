"""Dynamic refresh executes the locked client and signer against mock HTTP."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID

import httpx
import pytest

from media_sync.domain import LoginMethod, Platform
from media_sync.integrations.mediacrawler import detail_runner as module
from media_sync.integrations.mediacrawler.bilibili_dynamic import (
    BILI_DYNAMIC_DETAIL_FEATURES,
    BILI_DYNAMIC_DETAIL_PATH,
    BILI_DYNAMIC_FIELD,
    BILI_OPUS_DETAIL_FEATURES,
    BILI_OPUS_DETAIL_PATH,
    BiliDynamicPayload,
)
from media_sync.integrations.mediacrawler.policies import WatchdogLimits, build_run_paths
from tests.contract.test_bilibili_bounded_capture import checkout as checkout
from tests.contract.test_bilibili_bounded_capture import runtime as runtime
from tests.unit.test_bili_dynamic_refresh import _DID, _MID, _PUB_TS, _payload, _request


def _detail(*, opus: bool = False) -> dict[str, Any]:
    images = _payload().images
    return {
        "id_str": _DID,
        "type": "DYNAMIC_TYPE_DRAW",
        "visible": True,
        "modules": {
            "module_author": {"type": "AUTHOR_TYPE_NORMAL", "mid": int(_MID), "pub_ts": _PUB_TS},
            "module_dynamic": {
                "desc": {"text": "Bound original text"},
                "major": {"type": "MAJOR_TYPE_OPUS", "opus": {"summary": {"text": "Not full text"}}}
                if opus
                else {
                    "type": "MAJOR_TYPE_DRAW",
                    "draw": {
                        "items": [{"src": image.url, "width": image.width, "height": image.height} for image in images]
                    },
                },
            },
        },
    }


def _opus() -> dict[str, Any]:
    return {
        "id_str": _DID,
        "basic": {"uid": int(_MID), "comment_type": 11},
        "modules": [
            {"module_type": "MODULE_TYPE_AUTHOR", "module_author": {"mid": int(_MID), "pub_ts": _PUB_TS}},
            {
                "module_type": "MODULE_TYPE_CONTENT",
                "module_content": {
                    "paragraphs": [
                        {
                            "para_type": 1,
                            "text": {"nodes": [{"type": "TEXT_NODE_TYPE_WORD", "word": {"words": "Complete text"}}]},
                        },
                        {
                            "para_type": 2,
                            "pic": {
                                "pics": [
                                    {"url": image.url, "width": image.width, "height": image.height}
                                    for image in _payload().images
                                ]
                            },
                        },
                    ]
                },
            },
        ],
    }


def _child(tmp_path: Path, *, checkout_root: Path | None = None) -> module._ChildRequest:
    return module._ChildRequest(
        checkout_root=checkout_root or tmp_path,
        account_root=tmp_path / "account",
        profile_root=tmp_path / "account/browser_data/bili_user_data_dir",
        job_root=tmp_path / "job",
        output_root=tmp_path / "job/output",
        platform=Platform.BILI,
        login_method=LoginMethod.SAVED_SESSION,
        content_remote_id=_DID,
        author_remote_id=_MID,
        detail_reference=_DID,
        bili_dynamic_detail=True,
        bili_dynamic_type="DYNAMIC_TYPE_DRAW",
        bili_dynamic_pub_ts=_PUB_TS,
        request_delay_seconds=0.01,
        watchdogs=WatchdogLimits(max_seconds=5, poll_seconds=0.01),
    )


@pytest.mark.parametrize("opus", [False, True])
@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("change", [None, "missing_buvid3", "hidden", "additional", "orig"])
async def test_locked_client_refreshes_only_exact_did_and_necessary_opus(
    runtime: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, opus: bool, cached: bool, change: str | None
) -> None:
    runtime.behavior["cached_wbi"] = cached
    runtime.crawler.bili_client.cookie_dict["buvid3"] = "PRIVATE_SYNTHETIC_DEVICE"
    if change == "missing_buvid3":
        del runtime.crawler.bili_client.cookie_dict["buvid3"]
    requests: list[httpx.Request] = []

    def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET" and request.url.host == "api.bilibili.com"
        assert request.headers["Cookie"] == "SESSDATA=PRIVATE_TEST_ONLY"
        query = parse_qs(request.url.query.decode())
        if request.url.path == "/x/web-interface/nav":
            data: dict[str, Any] = {
                "wbi_img": {
                    "img_url": f"https://i0.hdslb.com/bfs/wbi/{'a' * 32}.png",
                    "sub_url": f"https://i0.hdslb.com/bfs/wbi/{'b' * 32}.png",
                }
            }
        else:
            expected_features = (
                BILI_DYNAMIC_DETAIL_FEATURES
                if request.url.path == BILI_DYNAMIC_DETAIL_PATH
                else BILI_OPUS_DETAIL_FEATURES
            )
            assert request.url.path in {BILI_DYNAMIC_DETAIL_PATH, BILI_OPUS_DETAIL_PATH}
            assert set(query) == {"id", "features", "w_rid", "wts"}
            assert query["id"] == [_DID] and query["features"] == [expected_features]
            assert len(query["w_rid"][0]) == 32
            data = {"item": _detail(opus=opus) if request.url.path == BILI_DYNAMIC_DETAIL_PATH else _opus()}
            if request.url.path == BILI_DYNAMIC_DETAIL_PATH:
                if change == "hidden":
                    data["item"]["visible"] = False
                elif change == "additional":
                    data["item"]["modules"]["module_dynamic"]["additional"] = {"type": "ADDITIONAL_TYPE_RESERVE"}
                elif change == "orig":
                    data["item"]["orig"] = {"id_str": "111"}
        return httpx.Response(200, json={"code": 0, "data": data})

    def client_factory(**kwargs: Any) -> httpx.AsyncClient:
        assert kwargs.get("verify") is True and kwargs.get("proxy") is None
        assert "follow_redirects" not in kwargs
        return httpx.AsyncClient(
            **kwargs,
            transport=httpx.MockTransport(transport),
            trust_env=False,
            headers={"Cookie": "SESSDATA=PRIVATE_TEST_ONLY"},
        )

    monkeypatch.setattr(sys.modules["tools.httpx_util"], "httpx", SimpleNamespace(AsyncClient=client_factory))

    async def start(instance: Any) -> None:
        await instance.get_specified_videos([_DID])

    runtime.crawler.start = MethodType(start, runtime.crawler)
    upstream = SimpleNamespace(CrawlerFactory=SimpleNamespace(create_crawler=lambda *, platform: runtime.crawler))
    original_request = runtime.crawler.bili_client.request
    original_keys = runtime.crawler.bili_client.get_wbi_keys
    rejected = change in {"hidden", "additional", "orig"} or (opus and change == "missing_buvid3")
    if rejected:
        from media_sync.integrations.mediacrawler.bilibili_dynamic import BiliDynamicUnsupportedError

        with pytest.raises(
            module._ChildConfigurationError if change == "missing_buvid3" else BiliDynamicUnsupportedError
        ):
            await module._run_bilibili_dynamic(upstream, _child(tmp_path))
    else:
        result = await module._run_bilibili_dynamic(upstream, _child(tmp_path))
        record = json.loads(result.jsonl)
        parsed = BiliDynamicPayload.from_mapping(record[BILI_DYNAMIC_FIELD])
        assert parsed.identity.did == _DID and parsed.identity.author_mid == int(_MID)
        assert parsed.text == ("Complete text" if opus else "Bound original text")
        assert len(parsed.images) == 2 and parsed.video_reference is None
    assert runtime.crawler.bili_client.request == original_request
    assert runtime.crawler.bili_client.get_wbi_keys == original_keys
    assert runtime.rows == []
    paths = [BILI_DYNAMIC_DETAIL_PATH] + ([BILI_OPUS_DETAIL_PATH] if opus and not rejected else [])
    expected_paths = ([] if cached else ["/x/web-interface/nav"]) + paths
    assert [request.url.path for request in requests] == expected_paths
    assert runtime.sleeps == [0.01] * (len(expected_paths) - 1)


@pytest.mark.parametrize(
    "change",
    [
        "did",
        "type",
        "author",
        "pub_ts",
        "author_type",
        "view",
        "opus_did",
        "opus_author",
        "opus_timestamp",
        "opus_missing",
    ],
)
async def test_detail_identity_drift_fails_without_aid_or_creator_fallback(tmp_path: Path, change: str) -> None:
    item = _detail(opus=change.startswith("opus"))
    opus_item: dict[str, Any] | None = _opus()
    if change == "did":
        item["id_str"] = "987654321"
    elif change == "type":
        item["type"] = "DYNAMIC_TYPE_AV"
    elif change == "author":
        item["modules"]["module_author"]["mid"] += 1
    elif change == "pub_ts":
        item["modules"]["module_author"]["pub_ts"] += 1
    elif change == "author_type":
        item["modules"]["module_author"]["type"] = "AUTHOR_TYPE_PGC"
    elif change == "view":
        item = {"View": {"aid": int(_DID)}}
    elif change == "opus_did":
        opus_item["id_str"] = "987654321"
    elif change == "opus_author":
        opus_item["basic"]["uid"] += 1
    elif change == "opus_timestamp":
        opus_item["modules"][0]["module_author"]["pub_ts"] += 1
    elif change == "opus_missing":
        opus_item = None
    paths: list[str] = []

    async def get(path: str, params: dict[str, object], **kwargs: object) -> object:
        assert params["id"] == _DID and kwargs == {"enable_params_sign": True}
        assert path in {BILI_DYNAMIC_DETAIL_PATH, BILI_OPUS_DETAIL_PATH}
        return await crawler.bili_client.request(
            method="GET",
            url="https://api.bilibili.com" + path + "?" + urlencode(params | {"wts": _PUB_TS, "w_rid": "a" * 32}),
        )

    async def request(method: str, url: str, **kwargs: object) -> object:
        path = urlsplit(url).path
        paths.append(path)
        return {"item": item if path == BILI_DYNAMIC_DETAIL_PATH else opus_item}

    crawler = SimpleNamespace(
        bili_client=SimpleNamespace(
            get=get, request=request, get_wbi_keys=lambda: None, cookie_dict={"buvid3": "PRIVATE_SYNTHETIC_DEVICE"}
        )
    )

    async def start() -> None:
        await crawler.get_specified_videos([_DID])

    crawler.start = start
    upstream = SimpleNamespace(CrawlerFactory=SimpleNamespace(create_crawler=lambda **kwargs: crawler))
    with pytest.raises(ValueError):
        await module._run_bilibili_dynamic(upstream, _child(tmp_path))
    assert paths == [BILI_DYNAMIC_DETAIL_PATH] + ([BILI_OPUS_DETAIL_PATH] if change.startswith("opus") else [])


def test_closed_child_frame_preserves_mode_and_rejects_tampering(
    checkout: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request()
    paths = build_run_paths(tmp_path, Platform.BILI, request.account_id, UUID("44444444-4444-4444-8444-444444444444"))
    raw = json.loads(module.MediaCrawlerDetailProcessRunner._child_payload(request, checkout, paths))
    monkeypatch.chdir(checkout.root)
    loaded = module._ChildRequest.load(json.dumps(raw).encode())
    assert loaded.bili_dynamic_detail and loaded.bili_dynamic_type == "DYNAMIC_TYPE_DRAW"
    assert loaded.bili_dynamic_pub_ts == _PUB_TS and loaded.detail_reference == _DID
    changes = [
        {"bili_dynamic_detail": False},
        {"bili_dynamic_detail": 1},
        {"bili_dynamic_type": "DYNAMIC_TYPE_AV"},
        {"bili_dynamic_pub_ts": True},
        {"bili_dynamic_pub_ts": 0},
        {"bili_progressive_detail": True},
        {"detail_reference": "123"},
        {"bili_video_cid": 123},
        {"schema_version": module.DETAIL_RUNNER_SCHEMA_VERSION - 1},
        {"unexpected_mode": True},
    ]
    for change in changes:
        with pytest.raises(module._ChildConfigurationError):
            module._ChildRequest.load(json.dumps(raw | change).encode())
    del raw["bili_dynamic_detail"]
    with pytest.raises(module._ChildConfigurationError):
        module._ChildRequest.load(json.dumps(raw).encode())


async def test_dynamic_execute_child_does_not_accept_a_foreign_output_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = module._BiliDynamicDetailResult((json.dumps(_payload().to_record()) + "\n").encode())

    async def watch(request: object) -> tuple[None, module._BiliDynamicDetailResult]:
        return None, result

    monkeypatch.setattr(module, "_watch_upstream", watch)
    monkeypatch.setattr(module, "_read_content_jsonl", lambda request: b'{"video_id":"123"}\n')
    assert await module._execute_child(_child(tmp_path)) == ("result_invalid", b"")
    monkeypatch.setattr(module, "_read_content_jsonl", lambda request: b"")
    assert await module._execute_child(_child(tmp_path)) == ("succeeded", result.jsonl)


async def test_dynamic_unsupported_returns_only_fixed_safe_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from media_sync.integrations.mediacrawler.bilibili_dynamic import BiliDynamicUnsupportedError

    async def watch(request: object) -> object:
        raise BiliDynamicUnsupportedError

    monkeypatch.setattr(module, "_watch_upstream", watch)
    assert await module._execute_child(_child(tmp_path)) == ("unsupported", b"")


@pytest.mark.parametrize(
    "change",
    ["method", "host", "path", "did", "features", "extra", "duplicate", "fragment", "signature", "wts"],
)
async def test_dynamic_request_guard_blocks_unrequested_http_and_restores_client(tmp_path: Path, change: str) -> None:
    observed: list[str] = []

    async def original(method: str, url: str, **kwargs: object) -> object:
        observed.append(url)
        return {"item": _detail()}

    async def get(path: str, params: dict[str, object], **kwargs: object) -> object:
        query = params | {"wts": _PUB_TS, "w_rid": "a" * 32}
        if change in {"did", "features", "wts"}:
            query[{"did": "id"}.get(change, change)] = "invalid"
        if change == "signature":
            query["w_rid"] = "g" * 32
        if change == "extra":
            query["aid"] = "123"
        url = "https://api.bilibili.com" + path + "?" + urlencode(query)
        if change == "host":
            url = url.replace("api.bilibili.com", "unrequested.example")
        if change == "path":
            url = url.replace(path, "/x/web-interface/view")
        if change == "duplicate":
            url += "&id=" + _DID
        if change == "fragment":
            url += "#hidden"
        return await client.request(method="POST" if change == "method" else "GET", url=url)

    client = SimpleNamespace(get=get, request=original, get_wbi_keys=lambda: None)
    crawler = SimpleNamespace(bili_client=client)

    async def start() -> None:
        await crawler.get_specified_videos([_DID])

    crawler.start = start
    upstream = SimpleNamespace(CrawlerFactory=SimpleNamespace(create_crawler=lambda **kwargs: crawler))
    with pytest.raises(ValueError):
        await module._run_bilibili_dynamic(upstream, _child(tmp_path))
    assert observed == [] and client.request is original


@pytest.mark.parametrize("change", ["endpoint_twice", "nav_twice", "nav_after", "bypass", "cancel", "oversize", "line"])
async def test_dynamic_http_budget_and_cancellation_restore_client(tmp_path: Path, change: str) -> None:
    observed: list[str] = []

    async def original(method: str, url: str, **kwargs: object) -> object:
        observed.append(url)
        if change == "cancel":
            raise asyncio.CancelledError
        return {"item": _detail(), "padding": "x" * 2000 if change == "oversize" else ""}

    async def get(path: str, params: dict[str, object], **kwargs: object) -> object:
        endpoint = "https://api.bilibili.com" + path + "?" + urlencode(params | {"wts": _PUB_TS, "w_rid": "a" * 32})
        nav = "https://api.bilibili.com/x/web-interface/nav"
        if change == "bypass":
            return {"item": _detail()}
        if change == "nav_twice":
            await client.request(method="GET", url=nav)
            return await client.request(method="GET", url=nav)
        response = await client.request(method="GET", url=endpoint)
        if change in {"endpoint_twice", "nav_after"}:
            return await client.request(method="GET", url=nav if change == "nav_after" else endpoint)
        return response

    client = SimpleNamespace(get=get, request=original, get_wbi_keys=lambda: None)
    crawler = SimpleNamespace(bili_client=client)

    async def start() -> None:
        await crawler.get_specified_videos([_DID])

    crawler.start = start
    upstream = SimpleNamespace(CrawlerFactory=SimpleNamespace(create_crawler=lambda **kwargs: crawler))
    request = _child(tmp_path)
    if change == "oversize":
        request = replace(request, watchdogs=replace(request.watchdogs, max_output_bytes=1024, max_line_bytes=1024))
    elif change == "line":
        request = replace(request, watchdogs=replace(request.watchdogs, max_line_bytes=100))
    with pytest.raises(asyncio.CancelledError if change == "cancel" else ValueError):
        await module._run_bilibili_dynamic(upstream, request)
    assert len(observed) == (0 if change == "bypass" else 1)
    assert client.request is original
