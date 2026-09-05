"""Execute locked Bili modules with offline browser/network dependencies.

These are real module imports, not an AST method extraction. They qualify the
single-profile call path and forbidden-content traps, not live platform access.
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from media_sync.integrations.mediacrawler import creator_profile_runner as module
from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout
from media_sync.security.secrets import SecretValue


@pytest.fixture(scope="module")
def checkout() -> Path:
    return verify_mediacrawler_checkout(
        Path(__file__).resolve().parents[2] / "upstreams.lock.json", license_acknowledged=True
    ).root


def _stub(monkeypatch: pytest.MonkeyPatch, name: str, **values: object) -> ModuleType:
    import sys

    instance = ModuleType(name)
    instance.__dict__.update(values)
    monkeypatch.setitem(sys.modules, name, instance)
    return instance


def _load(monkeypatch: pytest.MonkeyPatch, name: str, path: Path) -> ModuleType:
    import sys

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, loaded)
    spec.loader.exec_module(loaded)
    return loaded


@pytest.fixture
def locked_modules(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, ModuleType, ModuleType]:
    class BaseClient:
        pass

    class BaseCrawler:
        pass

    class ProxyMixin:
        def init_proxy_pool(self, pool: object) -> None:
            assert pool is None

    class Login:
        async def begin(self) -> None:
            pytest.fail("QR/login was entered")

    async def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("content/dynamics/comments/store was entered")

    async def cookies(context: object, urls: list[str]) -> tuple[str, dict[str, str]]:
        assert urls == ["https://www.bilibili.com"]
        return "SESSDATA=PRIVATE_COOKIE", {"SESSDATA": "PRIVATE_COOKIE"}

    config = _stub(
        monkeypatch,
        "config",
        START_DAY="2026-09-01",
        END_DAY="2026-09-01",
        __file__=str(checkout / "config" / "__init__.py"),
    )
    utils = SimpleNamespace(
        logger=SimpleNamespace(info=lambda *args: None, error=lambda *args: None, warning=lambda *args: None),
        get_user_agent=lambda: "offline-agent",
        get_unix_timestamp=lambda: 1_783_296_000,
        convert_browser_context_cookies=cookies,
    )
    _stub(monkeypatch, "tools", utils=utils, __path__=[])
    _stub(monkeypatch, "tools.httpx_util", make_async_client=forbidden)
    _stub(monkeypatch, "tools.cdp_browser", CDPBrowserManager=object)
    _stub(monkeypatch, "base", __path__=[])
    _stub(monkeypatch, "base.base_crawler", AbstractApiClient=BaseClient, AbstractCrawler=BaseCrawler)
    _stub(monkeypatch, "proxy", __path__=[])
    _stub(monkeypatch, "proxy.proxy_mixin", ProxyRefreshMixin=ProxyMixin)
    _stub(monkeypatch, "proxy.proxy_ip_pool", IpInfoModel=object, create_ip_pool=forbidden)
    _stub(monkeypatch, "store", bilibili=SimpleNamespace(), __path__=[])
    _stub(monkeypatch, "model", __path__=[])
    _stub(monkeypatch, "model.m_bilibili", VideoUrlInfo=object, CreatorUrlInfo=object)
    _stub(monkeypatch, "var", crawler_type_var=object, source_keyword_var=object)
    _stub(monkeypatch, "pandas")
    _stub(monkeypatch, "playwright", __path__=[])
    _stub(
        monkeypatch,
        "playwright.async_api",
        BrowserContext=object,
        BrowserType=object,
        Page=object,
        Playwright=object,
        async_playwright=forbidden,
    )
    _stub(monkeypatch, "playwright._impl", __path__=[])
    _stub(monkeypatch, "playwright._impl._errors", TargetClosedError=RuntimeError)
    _stub(monkeypatch, "media_platform", __path__=[str(checkout / "media_platform")])
    _stub(monkeypatch, "media_platform.bilibili", __path__=[str(checkout / "media_platform" / "bilibili")])
    _stub(monkeypatch, "media_platform.bilibili.login", BilibiliLogin=Login)
    bili_root = checkout / "media_platform" / "bilibili"
    for name in ("field", "exception", "help"):
        _load(monkeypatch, f"media_platform.bilibili.{name}", bili_root / f"{name}.py")
    client = _load(monkeypatch, "media_platform.bilibili.client", bili_root / "client.py")
    core = _load(monkeypatch, "media_platform.bilibili.core", bili_root / "core.py")
    for name in (
        "start",
        "search",
        "get_creator_details",
        "get_all_creator_details",
        "get_creator_videos",
        "get_dynamics",
        "get_specified_videos",
        "get_bilibili_video",
        "batch_get_video_comments",
        "get_fans",
        "get_followings",
    ):
        monkeypatch.setattr(core.BilibiliCrawler, name, forbidden, raising=False)
    for name in (
        "get_all_creator_videos",
        "get_video_info",
        "get_video_play_url",
        "get_creator_dynamics",
        "get_video_comments",
        "get_creator_fans",
        "get_creator_followings",
        "update_cookies",
        "pong",
    ):
        monkeypatch.setattr(client.BilibiliClient, name, forbidden, raising=False)
    return config, core, client


@pytest.mark.parametrize(
    "cached_wbi, authenticated", [(False, True), (True, True), (False, False)], ids=["nav-wbi", "saved-wbi", "expired"]
)
@pytest.mark.parametrize("cookie_mode", [False, True], ids=["saved-session", "pasted-cookie"])
async def test_locked_bili_modules_only_authenticate_and_query_exact_profile(
    checkout: Path,
    locked_modules: tuple[ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cached_wbi: bool,
    authenticated: bool,
    cookie_mode: bool,
) -> None:
    import sys

    config, core, client_module = locked_modules
    calls: list[str] = []
    profile_calls: list[int] = []
    chromium_options: dict[str, Any] = {}
    page_requests: list[str] = []
    closed: list[bool] = []
    injected: list[dict[str, Any]] = []
    expected_cookie = "SESSDATA=NEW_COOKIE==" if cookie_mode else "SESSDATA=PRIVATE_COOKIE"

    async def exact_cookies(context: object, urls: list[str]) -> tuple[str, dict[str, str]]:
        assert urls == ["https://www.bilibili.com"]
        if cookie_mode:
            assert injected == [
                {"name": "SESSDATA", "value": "NEW_COOKIE==", "domain": ".bilibili.com", "path": "/", "secure": True}
            ]
        return expected_cookie, {"SESSDATA": expected_cookie.partition("=")[2]}

    monkeypatch.setattr(core.utils, "convert_browser_context_cookies", exact_cookies)
    actual_profile = client_module.BilibiliClient.get_creator_info

    async def counted_profile(client: Any, creator_id: int) -> object:
        profile_calls.append(creator_id)
        return await actual_profile(client, creator_id)

    monkeypatch.setattr(client_module.BilibiliClient, "get_creator_info", counted_profile)

    def fetch(url: str, headers: dict[str, str], deadline: float) -> dict[str, object]:
        assert headers["Cookie"] == expected_cookie and deadline > time.monotonic()
        calls.append(url)
        if urlsplit(url).path == module._NAV_PATH:
            return {
                "isLogin": authenticated,
                "wbi_img": {
                    "img_url": f"https://i0.hdslb.com/bfs/wbi/{'a' * 32}.png",
                    "sub_url": f"https://i0.hdslb.com/bfs/wbi/{'b' * 32}.png",
                },
            }
        assert urlsplit(url).path == module._PROFILE_PATH
        query = parse_qs(urlsplit(url).query)
        assert set(query) == {"mid", "wts", "w_rid"} and query["mid"] == ["123"]
        assert len(query["w_rid"][0]) == 32
        return {
            "mid": 123,
            "name": "Observed name",
            "face": "https://i0.hdslb.com/bfs/face/avatar.jpg",
            "ignored": "never persisted",
        }

    monkeypatch.setattr(module, "_fetch_api_json", fetch)

    class Page:
        async def goto(self, url: str, **kwargs: object) -> None:
            page_requests.append(url)
            fulfilled: list[bool] = []

            async def fulfill(**options: object) -> None:
                assert options["status"] == 200 and "html" in str(options["body"])
                fulfilled.append(True)

            async def abort() -> None:
                pytest.fail("fixed same-origin document should be fulfilled")

            await context.router(
                SimpleNamespace(
                    request=SimpleNamespace(is_navigation_request=lambda: True, url=url), fulfill=fulfill, abort=abort
                )
            )
            assert fulfilled == [True]

        async def evaluate(self, code: str) -> dict[str, str]:
            assert code == "() => window.localStorage"
            if not cached_wbi:
                return {}
            return {
                "wbi_img_urls": (
                    f"https://i0.hdslb.com/bfs/wbi/{'a' * 32}.png-https://i0.hdslb.com/bfs/wbi/{'b' * 32}.png"
                )
            }

    class Context:
        router: Any

        async def add_cookies(self, pairs: list[dict[str, Any]]) -> None:
            assert cookie_mode
            injected.extend(pairs)

        async def route(self, pattern: str, handler: object) -> None:
            assert pattern == "**/*"
            self.router = handler

        async def new_page(self) -> Page:
            return Page()

        async def close(self) -> None:
            closed.append(True)

    context = Context()

    class Browser:
        async def new_context(self, **options: object) -> Context:
            assert cookie_mode and "user_data_dir" not in options
            chromium_options.update(options)
            return context

        async def close(self) -> None:
            closed.append(False)

    class Playwright:
        async def __aenter__(self) -> object:
            async def launch(**options: object) -> Context:
                assert not cookie_mode, "Cookie path must never open a saved profile"
                chromium_options.update(options)
                return context

            async def fresh_launch(**options: object) -> Browser:
                assert cookie_mode and "user_data_dir" not in options
                chromium_options.update(options)
                return Browser()

            return SimpleNamespace(
                chromium=SimpleNamespace(
                    executable_path="bundled-chromium", launch_persistent_context=launch, launch=fresh_launch
                )
            )

        async def __aexit__(self, *args: object) -> None:
            return None

    playwright_api = SimpleNamespace(async_playwright=Playwright)
    original_import = module.importlib.import_module
    prepared = {
        "config": config,
        "media_platform.bilibili.core": core,
        "media_platform.bilibili.client": client_module,
        "playwright.async_api": playwright_api,
    }
    monkeypatch.delitem(sys.modules, "config")
    monkeypatch.delitem(sys.modules, "media_platform.bilibili.core")
    monkeypatch.setattr(
        module.importlib,
        "import_module",
        lambda name, *args: prepared[name] if name in prepared else original_import(name, *args),
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    profile = tmp_path / "profile"
    cookie = SecretValue(expected_cookie) if cookie_mode else None
    if authenticated:
        result = await module._lookup_bili(checkout, profile, "123", time.monotonic() + 10, cookie=cookie)
        assert result.remote_id == "123" and result.display_name == "Observed name"
        assert profile_calls == [123]
        assert sum(urlsplit(url).path == module._NAV_PATH for url in calls) == (1 if cached_wbi else 2)
        assert sum(urlsplit(url).path == module._PROFILE_PATH for url in calls) == 1
    else:
        with pytest.raises(module._LookupFailure, match="auth_expired"):
            await module._lookup_bili(checkout, profile, "123", time.monotonic() + 10, cookie=cookie)
        assert profile_calls == [] and len(calls) == 1
    assert chromium_options["headless"] is True and chromium_options["service_workers"] == "block"
    assert chromium_options["accept_downloads"] is False and chromium_options["executable_path"] == "bundled-chromium"
    assert chromium_options.get("user_data_dir") == (None if cookie_mode else str(profile))
    assert page_requests == ["https://www.bilibili.com/"] and closed == ([True, False] if cookie_mode else [True])
    assert not profile.exists()
