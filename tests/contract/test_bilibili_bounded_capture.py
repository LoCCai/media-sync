"""Real locked client, signer, creator class and JSONL store; mock HTTP transport."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from urllib.parse import parse_qs
from uuid import UUID

import httpx
import pytest

from media_sync.integrations.mediacrawler import bilibili_capture
from media_sync.integrations.mediacrawler.bilibili_media import BILIBILI_PAGES_FIELD, install_bilibili_media_capture
from media_sync.integrations.mediacrawler.bilibili_scan import (
    BILI_SCAN_COVERAGE_FILENAME,
    BILI_SCAN_IDENTITY_FIELD,
    BiliScanCoverage,
    BiliScanState,
)
from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout


def stub(monkeypatch: pytest.MonkeyPatch, name: str, **values: object) -> ModuleType:
    module = ModuleType(name)
    module.__dict__.update(values)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def load(monkeypatch: pytest.MonkeyPatch, name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checkout() -> Any:
    return verify_mediacrawler_checkout(
        Path(__file__).resolve().parents[2] / "upstreams.lock.json", license_acknowledged=True
    )


@pytest.fixture
def runtime(checkout: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    root = checkout.root
    rows: list[dict[str, object]] = []
    requests: list[httpx.Request] = []
    sleeps: list[float] = []
    behavior: dict[str, object] = {"total": 67, "failure": None, "cached_wbi": False}

    async def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("unrequested upstream API/browser/DB/media path")

    class BaseClient:
        pass

    class BaseCrawler:
        pass

    class BaseStore:
        pass

    class ProxyMixin:
        def init_proxy_pool(self, value: object) -> None:
            assert value is None

        async def _refresh_proxy_if_expired(self) -> None:
            pass

    class Writer:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs == {"crawler_type": "creator", "platform": "bili"}

        async def write_to_jsonl(self, *, item: dict[str, object], item_type: str) -> None:
            assert item_type == "contents"
            rows.append(dict(item))

    class Page:
        async def evaluate(self, script: str) -> dict[str, str]:
            assert script == "() => window.localStorage"
            if behavior["cached_wbi"]:
                return {
                    "wbi_img_url": "https://i0.hdslb.com/bfs/wbi/" + "a" * 32 + ".png",
                    "wbi_sub_url": "https://i0.hdslb.com/bfs/wbi/" + "b" * 32 + ".png",
                }
            return {}

    config = stub(
        monkeypatch,
        "config",
        __file__=str(root / "config/__init__.py"),
        START_DAY="2026-09-01",
        END_DAY="2026-09-01",
        SAVE_DATA_OPTION="jsonl",
        CREATOR_MODE=True,
        ENABLE_GET_COMMENTS=False,
        ENABLE_GET_SUB_COMMENTS=False,
        ENABLE_GET_MEIDAS=False,
        ENABLE_GET_MEDIAS=False,
        ENABLE_IP_PROXY=False,
        DISABLE_SSL_VERIFY=False,
    )
    utils = SimpleNamespace(
        logger=SimpleNamespace(info=lambda *args: None, error=lambda *args: None, warning=lambda *args: None),
        get_user_agent=lambda: "offline-bili-contract",
        get_unix_timestamp=lambda: 1_783_296_000,
        get_current_timestamp=lambda: 1_783_296_000,
    )
    stub(monkeypatch, "tools", utils=utils, words=object(), __path__=[str(root / "tools")])
    stub(monkeypatch, "tools.cdp_browser", CDPBrowserManager=object)
    stub(
        monkeypatch,
        "tools.user_hash",
        anonymize_user_id=lambda value: "masked-id",
        mask_nickname=lambda value: "masked-name",
    )
    stub(monkeypatch, "tools.async_file_writer", AsyncFileWriter=Writer)
    httpx_util = load(monkeypatch, "tools.httpx_util", root / "tools/httpx_util.py")
    stub(monkeypatch, "base", __path__=[])
    stub(
        monkeypatch,
        "base.base_crawler",
        AbstractApiClient=BaseClient,
        AbstractCrawler=BaseCrawler,
        AbstractStore=BaseStore,
        AbstractStoreImage=BaseStore,
        AbstractStoreVideo=BaseStore,
    )
    stub(monkeypatch, "proxy", __path__=[])
    stub(monkeypatch, "proxy.proxy_mixin", ProxyRefreshMixin=ProxyMixin)
    stub(monkeypatch, "proxy.proxy_ip_pool", IpInfoModel=object, create_ip_pool=forbidden)
    stub(monkeypatch, "database", __path__=[])
    stub(monkeypatch, "database.db_session", get_session=forbidden)
    stub(monkeypatch, "database.models", BilibiliVideoComment=object, BilibiliVideo=object, BilibiliUpDynamic=object)
    stub(monkeypatch, "database.mongodb_store_base", MongoDBStoreBase=object)
    stub(monkeypatch, "model", __path__=[])
    stub(monkeypatch, "model.m_bilibili", VideoUrlInfo=object, CreatorUrlInfo=object)
    stub(
        monkeypatch,
        "var",
        crawler_type_var=SimpleNamespace(get=lambda: "creator"),
        source_keyword_var=SimpleNamespace(get=lambda: ""),
    )
    stub(monkeypatch, "pandas")
    stub(monkeypatch, "aiofiles", open=forbidden)
    stub(monkeypatch, "playwright", __path__=[])
    stub(
        monkeypatch,
        "playwright.async_api",
        BrowserContext=object,
        BrowserType=object,
        Page=object,
        Playwright=object,
        async_playwright=forbidden,
    )
    stub(monkeypatch, "playwright._impl", __path__=[])
    stub(monkeypatch, "playwright._impl._errors", TargetClosedError=RuntimeError)
    store_parent = stub(monkeypatch, "store", __path__=[str(root / "store")])
    stub(monkeypatch, "store.bilibili", __path__=[str(root / "store/bilibili")])
    load(monkeypatch, "store.bilibili._store_impl", root / "store/bilibili/_store_impl.py")
    load(monkeypatch, "store.bilibili.bilibilli_store_media", root / "store/bilibili/bilibilli_store_media.py")
    store = load(monkeypatch, "store.bilibili", root / "store/bilibili/__init__.py")
    monkeypatch.setattr(store_parent, "bilibili", store, raising=False)
    stub(monkeypatch, "media_platform", __path__=[str(root / "media_platform")])
    stub(monkeypatch, "media_platform.bilibili", __path__=[str(root / "media_platform/bilibili")])
    stub(monkeypatch, "media_platform.bilibili.login", BilibiliLogin=object)
    for name in ("field", "exception", "help", "client", "core"):
        load(monkeypatch, "media_platform.bilibili." + name, root / f"media_platform/bilibili/{name}.py")
    core = sys.modules["media_platform.bilibili.core"]
    client_module = sys.modules["media_platform.bilibili.client"]
    for name in (
        "start",
        "search",
        "get_creator_details",
        "get_all_creator_details",
        "get_dynamics",
        "get_specified_videos",
        "get_bilibili_video",
        "batch_get_video_comments",
        "get_fans",
        "get_followings",
    ):
        monkeypatch.setattr(core.BilibiliCrawler, name, forbidden)

    def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert request.url.host == "api.bilibili.com"
        assert request.headers["Cookie"] == "SESSDATA=PRIVATE_TEST_ONLY"
        query = parse_qs(request.url.query.decode())
        if request.url.path == "/x/web-interface/nav":
            # Locked get_wbi_keys calls request without headers. Set below only for this branch.
            data = {
                "wbi_img": {
                    "img_url": "https://i0.hdslb.com/bfs/wbi/" + "a" * 32 + ".png",
                    "sub_url": "https://i0.hdslb.com/bfs/wbi/" + "b" * 32 + ".png",
                }
            }
        elif request.url.path == "/x/space/wbi/arc/search":
            assert query["order"] == ["pubdate"]
            assert query["ps"] == ["30"]
            assert query["mid"] == ["42"]
            assert len(query["w_rid"][0]) == 32
            if behavior["failure"] == "list":
                return httpx.Response(200, json={"code": -352, "message": "risk_control"})
            if behavior["failure"] == "redirect":
                return httpx.Response(302, headers={"Location": "https://blocked.invalid/"}, json={"code": -1})
            number = int(query["pn"][0])
            total = int(behavior["total"])
            data = {
                "page": {"pn": number, "ps": 30, "count": total},
                "list": {
                    "vlist": [
                        {"aid": index, "bvid": f"BV{index:010d}", "created": 100_000 - index, "mid": 42}
                        for index in range((number - 1) * 30 + 1, min(number * 30, total) + 1)
                    ]
                },
            }
        elif request.url.path == "/x/web-interface/view/detail":
            if behavior["failure"] == "detail":
                return httpx.Response(200, json={"code": -404, "message": "gone"})
            index = int(query["bvid"][0][2:])
            view = {
                "aid": index,
                "bvid": query["bvid"][0],
                "pubdate": 100_000 - index,
                "owner": {"mid": 42, "name": "creator"},
                "stat": {},
                "cid": 101,
                "pages": [{"page": 1, "cid": 101}],
                "title": "contract",
                "desc": "contract",
                "pic": "https://i0.hdslb.com/cover.jpg",
            }
            if behavior["failure"] in {"aid", "bvid", "pubdate", "owner", "pages"}:
                key = str(behavior["failure"])
                view[key] = {
                    "aid": 999,
                    "bvid": "BV9999999999",
                    "pubdate": 1,
                    "owner": {"mid": 43},
                    "pages": [{"page": 2, "cid": 101}],
                }[key]
            data = {"View": view}
        else:
            pytest.fail("unexpected HTTP API")
        return httpx.Response(200, json={"code": 0, "data": data})

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        assert kwargs.get("verify") is True
        assert kwargs.get("proxy") is None
        assert "follow_redirects" not in kwargs
        return httpx.AsyncClient(
            **kwargs,
            transport=httpx.MockTransport(transport),
            trust_env=False,
            headers={"Cookie": "SESSDATA=PRIVATE_TEST_ONLY"},
        )

    monkeypatch.setattr(httpx_util, "httpx", SimpleNamespace(AsyncClient=client_factory))

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(bilibili_capture.asyncio, "sleep", sleep)
    account = UUID("a45dd777-9633-4168-b432-677e6c7b97be")
    fingerprint = hashlib.sha256(b"42").hexdigest()
    manifest = SimpleNamespace(
        bili_scan=BiliScanState.initial(account, fingerprint, checkout.commit),
        platform=SimpleNamespace(value="bili"),
        account_id=account,
        author_remote_id_fingerprint_sha256=fingerprint,
        upstream_sha=checkout.commit,
        checkout_root=root,
        output_root=tmp_path,
        max_items=1,
        request_delay_seconds=0.01,
    )
    crawler = core.BilibiliCrawler()
    crawler.bili_client = client_module.BilibiliClient(
        headers={"Cookie": "SESSDATA=PRIVATE_TEST_ONLY"},
        playwright_page=Page(),
        cookie_dict={"SESSDATA": "PRIVATE_TEST_ONLY"},
    )
    install_bilibili_media_capture(root)
    return SimpleNamespace(
        manifest=manifest,
        crawler=crawler,
        config=config,
        behavior=behavior,
        rows=rows,
        requests=requests,
        sleeps=sleeps,
    )


@pytest.mark.parametrize("cached", [False, True])
async def test_real_locked_signed_transport_and_store_are_bounded(runtime: Any, cached: bool) -> None:
    runtime.behavior["cached_wbi"] = cached
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    await runtime.crawler.get_creator_videos(42)
    paths = [request.url.path for request in runtime.requests]
    assert paths == ([] if cached else ["/x/web-interface/nav"]) + [
        "/x/space/wbi/arc/search",
        "/x/web-interface/view/detail",
    ]
    assert runtime.sleeps == [0.01] * (len(paths) - 1)
    assert len(runtime.rows) == 1
    assert runtime.rows[0][BILI_SCAN_IDENTITY_FIELD] == {
        "aid": "1",
        "bvid": "BV0000000001",
        "pubdate": 99999,
        "author_fingerprint_sha256": hashlib.sha256(b"42").hexdigest(),
    }
    assert runtime.rows[0][BILIBILI_PAGES_FIELD] == [{"page": 1, "cid": 101}]
    content = (runtime.manifest.output_root / BILI_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8")
    assert "PRIVATE_TEST_ONLY" not in content
    coverage = BiliScanCoverage.from_json_line(content)
    coverage.validate(runtime.manifest.bili_scan, 1, ("1",))
    assert coverage.list_attempts == 1 and coverage.detail_attempts == 1


@pytest.mark.parametrize("failure", ["list", "redirect", "detail", "aid", "bvid", "pubdate", "owner", "pages"])
async def test_http_or_detail_failure_never_retries_or_emits_coverage(runtime: Any, failure: str) -> None:
    runtime.behavior["failure"] = failure
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    with pytest.raises((RuntimeError, sys.modules["media_platform.bilibili.exception"].DataFetchError)):
        await runtime.crawler.get_creator_videos(42)
    assert not runtime.rows
    assert not (runtime.manifest.output_root / BILI_SCAN_COVERAGE_FILENAME).exists()
    assert len(runtime.requests) == (2 if failure in {"list", "redirect"} else 3)
    assert all(request.url.host == "api.bilibili.com" for request in runtime.requests)


async def test_wrong_creator_rejected_before_any_http(runtime: Any) -> None:
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    with pytest.raises(RuntimeError):
        await runtime.crawler.get_creator_videos(43)
    assert not runtime.requests


@pytest.mark.parametrize("maximum", [30, 100])
async def test_detail_hard_cap_thirty_on_large_requested_unit(runtime: Any, maximum: int) -> None:
    runtime.manifest.max_items = maximum
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    await runtime.crawler.get_creator_videos(42)
    assert len(runtime.rows) == 30
    assert sum(request.url.path == "/x/web-interface/view/detail" for request in runtime.requests) == 30
    assert sum(request.url.path == "/x/space/wbi/arc/search" for request in runtime.requests) == 1
