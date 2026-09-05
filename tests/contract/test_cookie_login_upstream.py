"""Real locked clients/login modules with offline third-party/network boundaries.

No AST extraction, browser launch, credentials or platform access. Signature
helper binding is exercised; third-party crypto engines are deterministic fakes.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import cookie_login_runner as runner
from media_sync.integrations.mediacrawler import cookie_reuse as reuse
from media_sync.integrations.mediacrawler.browser_policy import install_bundled_chromium_policy
from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout
from media_sync.integrations.mediacrawler.cookie_login import CookieLoginRequest, parse_cookie_header

COOKIE = "session=PRIVATE==; web_session=WEB==; a1=DEVICE==; d_c0=SIGN=="


@pytest.fixture(scope="module")
def checkout() -> Path:
    return verify_mediacrawler_checkout(
        Path(__file__).resolve().parents[2] / "upstreams.lock.json",
        license_acknowledged=True,
    ).root


def stub(monkeypatch: pytest.MonkeyPatch, name: str, **values: Any) -> ModuleType:
    module = ModuleType(name)
    module.__dict__.update(values)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def load(monkeypatch: pytest.MonkeyPatch, name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def offline(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("unexpected browser, original HTTP, login or content request")

    class Base:
        pass

    class ProxyMixin:
        def init_proxy_pool(self, value: Any) -> None:
            assert value is None

        async def _refresh_proxy_if_expired(self) -> None:
            forbidden()

    config = stub(
        monkeypatch,
        "config",
        __file__=str(checkout / "config/__init__.py"),
        SAVE_LOGIN_STATE=True,
        XHS_INTERNATIONAL=False,
    )
    utils = stub(
        monkeypatch,
        "tools.utils",
        __file__=str(checkout / "tools/utils.py"),
        logger=SimpleNamespace(info=lambda *a: None, warning=lambda *a: None, error=lambda *a: None),
        get_user_agent=lambda: "offline-desktop",
        get_mobile_user_agent=lambda: "offline-mobile",
        get_unix_timestamp=lambda: 1,
        convert_str_cookie_to_dict=forbidden,
    )
    stub(monkeypatch, "tools", utils=utils, __path__=[])
    stub(
        monkeypatch,
        "tools.crawler_util",
        __file__=str(checkout / "tools/crawler_util.py"),
        extract_text_from_html=forbidden,
        convert_str_cookie_to_dict=forbidden,
    )
    stub(monkeypatch, "tools.httpx_util", make_async_client=forbidden)
    stub(monkeypatch, "tools.user_hash", anonymize_user_id=forbidden, mask_nickname=forbidden)
    stub(monkeypatch, "base", __path__=[])
    stub(monkeypatch, "base.base_crawler", AbstractApiClient=Base, AbstractLogin=Base)
    stub(monkeypatch, "proxy", __path__=[])
    stub(monkeypatch, "proxy.proxy_mixin", ProxyRefreshMixin=ProxyMixin)
    stub(monkeypatch, "playwright", __path__=[])
    stub(
        monkeypatch,
        "playwright.async_api",
        BrowserContext=object,
        Page=object,
        TimeoutError=TimeoutError,
        async_playwright=forbidden,
    )
    stub(
        monkeypatch,
        "tenacity",
        retry=lambda *a, **k: lambda method: method,
        RetryError=RuntimeError,
        stop_after_attempt=lambda *a: None,
        wait_fixed=lambda *a: None,
        retry_if_result=lambda *a: None,
        retry_if_not_exception_type=lambda *a: None,
    )
    stub(monkeypatch, "model", __path__=[])
    stub(monkeypatch, "model.m_bilibili", VideoUrlInfo=object, CreatorUrlInfo=object)
    stub(monkeypatch, "model.m_zhihu", ZhihuComment=object, ZhihuContent=object, ZhihuCreator=object)
    stub(monkeypatch, "parsel", Selector=object)
    stub(monkeypatch, "constant", __path__=[])
    constant = load(monkeypatch, "constant.zhihu", checkout / "constant/zhihu.py")
    sys.modules["constant"].zhihu = constant
    stub(monkeypatch, "cache", __path__=[])
    stub(monkeypatch, "cache.cache_factory", CacheFactory=object)
    stub(monkeypatch, "media_platform", __path__=[])
    signed: list[Any] = []

    class Xhshow:
        def sign_headers_get(self, **kwargs: Any) -> dict[str, str]:
            signed.append(("xhs", kwargs))
            return {"x-s": "signed", "x-t": "1", "x-s-common": "common"}

    stub(monkeypatch, "xhshow", Xhshow=Xhshow)

    class JavaScript:
        def call(self, name: str, uri: str, cookie: str) -> dict[str, str]:
            assert name == "get_sign" and uri == "/api/v4/me" and cookie == COOKIE
            signed.append(("zhihu", uri))
            return {"x-zst-81": "signed-81", "x-zse-96": "signed-96"}

    def compile_js(source: str) -> JavaScript:
        assert "get_sign" in source
        return JavaScript()

    def get_runtime(name: str) -> Any:
        assert name == "Node"
        return SimpleNamespace(compile=compile_js)

    stub(monkeypatch, "execjs", compile=compile_js, get=get_runtime)
    for name in ("bilibili", "weibo", "xhs", "zhihu", "douyin", "kuaishou", "tieba"):
        stub(monkeypatch, f"media_platform.{name}", __path__=[str(checkout / "media_platform" / name)])
    return {"config": config, "utils": utils, "forbidden": forbidden, "signed": signed}


@pytest.mark.parametrize("platform", [Platform.BILI, Platform.WB, Platform.XHS, Platform.ZHIHU])
@pytest.mark.parametrize("accepted", [True, False])
async def test_complete_locked_clients_only_request_one_fixed_self_api(
    checkout: Path,
    offline: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    platform: Platform,
    accepted: bool,
) -> None:
    name, class_name, host, uri = runner._SELF_ENDPOINTS[platform]
    root = checkout / "media_platform" / name
    for part in ("field", "exception"):
        load(monkeypatch, f"media_platform.{name}.{part}", root / f"{part}.py")
    if platform is Platform.XHS:
        stub(monkeypatch, "media_platform.xhs.help", get_search_id=lambda: "offline-import-default")
        stub(monkeypatch, "media_platform.xhs.extractor", XiaoHongShuExtractor=object)
        stub(monkeypatch, "media_platform.xhs.xhs_sign", get_trace_id=lambda: "trace")
        load(monkeypatch, "media_platform.xhs.playwright_sign", root / "playwright_sign.py")
    elif platform in {Platform.BILI, Platform.ZHIHU}:
        load(monkeypatch, f"media_platform.{name}.help", root / "help.py")
    client_module = load(monkeypatch, f"media_platform.{name}.client", root / "client.py")
    client_type = getattr(client_module, class_name)
    for method_name, method in vars(client_type).items():
        if inspect.iscoroutinefunction(method) and method_name not in {"get", "_pre_headers", "query_self"}:
            monkeypatch.setattr(client_type, method_name, offline["forbidden"])
    prepared = {"config": offline["config"], client_module.__name__: client_module}
    original_import = importlib.import_module
    monkeypatch.delitem(sys.modules, "config")
    monkeypatch.delitem(sys.modules, client_module.__name__)
    monkeypatch.setattr(
        runner.importlib,
        "import_module",
        lambda value, *a: prepared[value] if value in prepared else original_import(value, *a),
    )
    monkeypatch.chdir(checkout)
    monkeypatch.syspath_prepend(str(checkout))
    seen = []

    def fetch(url: str, headers: dict[str, str], deadline: float) -> dict[str, Any]:
        seen.append(url)
        assert url == host + uri and deadline > time.monotonic()
        assert headers.get("Cookie", headers.get("cookie")) == COOKIE
        if platform is Platform.XHS:
            assert headers["X-S"] == "signed"
        if platform is Platform.ZHIHU:
            assert headers["x-zse-96"] == "signed-96" and "include=" not in url
        return {
            Platform.BILI: {"code": 0, "data": {"isLogin": accepted}},
            Platform.WB: {"ok": 1, "data": {"login": accepted}},
            Platform.XHS: {"code": 0, "data": {"result": {"success": accepted}}},
            Platform.ZHIHU: {"uid": "123", "name": "Name"} if accepted else {"error": {"code": 401}},
        }[platform]

    monkeypatch.setattr(runner, "_fetch_json", fetch)
    req = CookieLoginRequest(uuid4(), platform, uuid4(), parse_cookie_header(COOKIE))
    if accepted:
        await runner._verify_remote(checkout, req, time.monotonic() + 5)
    else:
        with pytest.raises(runner._VerificationFailure, match="rejected"):
            await runner._verify_remote(checkout, req, time.monotonic() + 5)
    assert seen == [host + uri]
    assert len(offline["signed"]) == int(platform in {Platform.XHS, Platform.ZHIHU})
    assert not any(
        key.endswith(".core") or key.endswith(".login") for key in sys.modules if key.startswith("media_platform.")
    )


async def test_zhihu_without_node_fails_closed_before_http(
    checkout: Path,
    offline: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = checkout / "media_platform/zhihu"
    for part in ("field", "exception", "help", "client"):
        load(monkeypatch, f"media_platform.zhihu.{part}", root / f"{part}.py")
    prepared = {"config": offline["config"], "media_platform.zhihu.client": sys.modules["media_platform.zhihu.client"]}
    original_import = importlib.import_module
    for name in prepared:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(
        runner.importlib,
        "import_module",
        lambda value, *a: prepared[value] if value in prepared else original_import(value, *a),
    )

    def missing_node(name: str) -> Any:
        assert name == "Node"
        raise RuntimeError("private-runtime-diagnostic")

    monkeypatch.setattr(sys.modules["execjs"], "get", missing_node)
    monkeypatch.setattr(runner, "_fetch_json", offline["forbidden"])
    monkeypatch.chdir(checkout)
    monkeypatch.syspath_prepend(str(checkout))
    req = CookieLoginRequest(uuid4(), Platform.ZHIHU, uuid4(), parse_cookie_header(COOKIE))
    with pytest.raises(runner._VerificationFailure, match=r"^configuration_invalid$"):
        await runner._verify_remote(checkout, req, time.monotonic() + 5)
    assert offline["signed"] == []


@pytest.mark.parametrize("platform", list(Platform))
async def test_cookie_reuse_has_no_persistent_profile_and_injects_before_first_pong(
    checkout: Path,
    offline: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    platform: Platform,
) -> None:
    name, crawler_name, login_name, domain = reuse._PLATFORMS[platform]
    root = checkout / "media_platform" / name
    login_module = load(monkeypatch, f"media_platform.{name}.login", root / "login.py")
    login_type = getattr(login_module, login_name)
    crawler_type = type(
        crawler_name, (), {"__module__": f"media_platform.{name}.core", "launch_browser": offline["forbidden"]}
    )
    stub(monkeypatch, f"media_platform.{name}.core", __file__=str(root / "core.py"), **{crawler_name: crawler_type})
    for method in ("login_by_qrcode", "login_by_mobile", "check_login_state"):
        monkeypatch.setattr(login_type, method, offline["forbidden"], raising=False)
    factory = SimpleNamespace(create_crawler=lambda **kwargs: crawler_type())
    # Production installs the factory policy before our class-local compatibility
    # patch; verify its bundled executable selector is still applied afterwards.
    install_bundled_chromium_policy(SimpleNamespace(CrawlerFactory=factory))
    reuse.install_cookie_reuse(checkout, platform, COOKIE)
    assert offline["config"].SAVE_LOGIN_STATE is False and offline["config"].ENABLE_CDP_MODE is False
    assert offline["utils"].convert_str_cookie_to_dict("test=value==") == {"test": "value=="}
    contexts = []

    class Context:
        def __init__(self) -> None:
            self.cookies: list[Any] = []

        async def add_cookies(self, values: list[Any]) -> None:
            self.cookies = values

    class Browser:
        async def new_context(self, **kwargs: Any) -> Context:
            assert "storage_state" not in kwargs and kwargs["service_workers"] == "block"
            context = Context()
            assert context.cookies == []  # A pre-existing profile cannot be selected.
            contexts.append(context)
            return context

        async def close(self) -> None:
            pass

    async def launch(**kwargs: Any) -> Browser:
        assert "user_data_dir" not in kwargs
        assert kwargs["executable_path"] == "bundled-only"
        return Browser()

    chromium = SimpleNamespace(
        executable_path="bundled-only",
        launch=launch,
        launch_persistent_context=offline["forbidden"],
    )
    context = await factory.create_crawler(platform=platform.value).launch_browser(chromium, None, "UA", headless=True)
    expected = {"session": "PRIVATE==", "web_session": "WEB==", "a1": "DEVICE==", "d_c0": "SIGN=="}
    assert {item["name"]: item["value"] for item in context.cookies} == expected
    assert all(item["domain"] == domain and item["path"] == "/" for item in context.cookies)
    login = login_type.__new__(login_type)
    login.browser_context = context
    await login.begin()
    assert {item["name"]: item["value"] for item in context.cookies} == expected
    assert len(contexts) == 1
