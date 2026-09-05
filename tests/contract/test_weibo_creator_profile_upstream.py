"""Locked Weibo client methods with synthetic browser and bounded HTTP transport."""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import time
from functools import wraps
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from media_sync.integrations.mediacrawler import creator_profile_runner as module
from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout
from media_sync.security.secrets import SecretValue


def stub(monkeypatch: pytest.MonkeyPatch, name: str, **values: Any) -> ModuleType:
    result = ModuleType(name)
    result.__dict__.update(values)
    monkeypatch.setitem(sys.modules, name, result)
    return result


def load(monkeypatch: pytest.MonkeyPatch, name: str, source: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec is not None and spec.loader is not None
    result = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, result)
    spec.loader.exec_module(result)
    return result


@pytest.fixture(scope="module")
def checkout() -> Path:
    return verify_mediacrawler_checkout(
        Path(__file__).resolve().parents[2] / "upstreams.lock.json", license_acknowledged=True
    ).root


@pytest.fixture
def locked_client(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any, Any]:
    def forbidden(*args: object, **kwargs: object) -> Any:
        pytest.fail("unexpected original HTTP, login, content, media, or browser-cookie conversion")

    class ProxyMixin:
        def init_proxy_pool(self, value: object) -> None:
            assert value is None

        async def _refresh_proxy_if_expired(self) -> None:
            forbidden()

    config = stub(monkeypatch, "config", __file__=str(checkout / "config/__init__.py"))
    utils = stub(
        monkeypatch,
        "tools.utils",
        __file__=str(checkout / "tools/utils.py"),
        get_mobile_user_agent=lambda: "offline-mobile",
        convert_str_cookie_to_dict=forbidden,
    )
    stub(monkeypatch, "tools", utils=utils, __path__=[])
    stub(monkeypatch, "tools.httpx_util", make_async_client=forbidden)
    stub(monkeypatch, "proxy", __path__=[])
    stub(monkeypatch, "proxy.proxy_mixin", ProxyRefreshMixin=ProxyMixin)
    stub(monkeypatch, "playwright", __path__=[])
    stub(monkeypatch, "playwright.async_api", Page=object, BrowserContext=object)

    def retry_trap(*args: object, **kwargs: object) -> Any:
        def decorate(method: Any) -> Any:
            @wraps(method)
            async def forbidden_retry(*args: object, **kwargs: object) -> Any:
                forbidden()

            forbidden_retry.retry = "forbidden-retry-decorator"
            return forbidden_retry

        return decorate

    stub(
        monkeypatch, "tenacity", retry=retry_trap, stop_after_attempt=lambda *args: None, wait_fixed=lambda *args: None
    )
    stub(monkeypatch, "media_platform", __path__=[])
    stub(monkeypatch, "media_platform.weibo", __path__=[str(checkout / "media_platform/weibo")])
    for name in ("field", "exception"):
        load(monkeypatch, "media_platform.weibo." + name, checkout / f"media_platform/weibo/{name}.py")
    client = load(monkeypatch, "media_platform.weibo.client", checkout / "media_platform/weibo/client.py")
    # The retry dependency is a trap, not a real retry engine. The locked
    # decorated request must be replaced before even entering that decorator.
    assert hasattr(client.WeiboClient.request, "retry")
    for name, method in vars(client.WeiboClient).items():
        if inspect.iscoroutinefunction(method) and name not in {"request", "get", "get_creator_info_by_id"}:
            monkeypatch.setattr(client.WeiboClient, name, forbidden)
    return config, utils, client


@pytest.mark.parametrize("cookie_mode", [False, True], ids=["saved-session", "pasted-cookie"])
@pytest.mark.parametrize("outcome", ["success", "expired", "malformed", "wrong-id", "redirect"])
async def test_locked_weibo_auth_profile_and_isolated_browser(
    checkout: Path,
    locked_client: tuple[Any, Any, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cookie_mode: bool,
    outcome: str,
) -> None:
    import media_sync.media.network as network

    config, utils, client_module = locked_client
    expected_cookie = 'SUB=NEW_COOKIE==; marker="quoted=="' if cookie_mode else 'SUB=SAVED_COOKIE==; marker="quoted=="'
    requests: list[httpx.Request] = []
    profile_calls: list[str] = []
    injected: list[dict[str, str]] = []
    closed: list[str] = []
    options: dict[str, object] = {}
    pages: list[str] = []

    actual_profile = client_module.WeiboClient.get_creator_info_by_id

    async def counted_profile(client: Any, creator_id: str) -> object:
        profile_calls.append(creator_id)
        return await actual_profile(client, creator_id)

    monkeypatch.setattr(client_module.WeiboClient, "get_creator_info_by_id", counted_profile)

    def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET" and request.url.host == "m.weibo.cn"
        assert request.headers["Cookie"] == expected_cookie
        assert request.headers["User-Agent"] == "offline-mobile"
        assert request.headers["accept-encoding"] == "identity"
        if request.url.path == "/api/config":
            assert request.url.query == b""
            if outcome == "malformed":
                return httpx.Response(
                    200, headers={"Content-Type": "application/json"}, stream=httpx.ByteStream(b"malformed")
                )
            if outcome == "redirect":
                return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
            data: object = {"login": outcome != "expired"}
        else:
            assert request.url.path == "/api/container/getIndex"
            assert parse_qs(request.url.query.decode(), keep_blank_values=True) == {
                "jumpfrom": ["weibocom"],
                "type": ["uid"],
                "value": ["123"],
                "containerid": ["100505123"],
            }
            data = {
                "userInfo": {
                    "id": "456" if outcome == "wrong-id" else "123",
                    "screen_name": "平台昵称",
                    "avatar_hd": "https://tva1.sinaimg.cn/large/abc.jpg",
                },
                "cards": [{"private": "incidental feed must not be stored"}],
            }
        payload = json.dumps({"ok": 1, "data": data}).encode()
        return httpx.Response(200, headers={"Content-Type": "application/json"}, stream=httpx.ByteStream(payload))

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))

    class Page:
        async def goto(self, url: str, **kwargs: object) -> None:
            pages.append(url)
            fulfilled: list[bool] = []

            async def fulfill(**kwargs: object) -> None:
                assert kwargs["status"] == 200
                assert kwargs["body"] == "<!doctype html><title></title>"
                fulfilled.append(True)

            async def abort() -> None:
                pytest.fail("expected blank same-origin route")

            await context.router(
                SimpleNamespace(
                    request=SimpleNamespace(url=url, is_navigation_request=lambda: True), fulfill=fulfill, abort=abort
                )
            )
            assert fulfilled == [True]

    class Context:
        router: Any

        async def add_cookies(self, values: list[dict[str, str]]) -> None:
            assert cookie_mode
            injected.extend(values)

        async def route(self, pattern: str, handler: Any) -> None:
            assert pattern == "**/*"
            self.router = handler

        async def new_page(self) -> Page:
            return Page()

        async def close(self) -> None:
            closed.append("context")

    context = Context()

    async def scoped_cookies(value: object, urls: list[str]) -> tuple[str, dict[str, str]]:
        assert value is context and urls == ["https://m.weibo.cn"]
        assert not cookie_mode, "pasted Cookie must not use a browser reread"
        return expected_cookie, {"SUB": "SAVED_COOKIE==", "marker": '"quoted=="'}

    monkeypatch.setattr(utils, "convert_browser_context_cookies", scoped_cookies, raising=False)

    class Browser:
        async def new_context(self, **kwargs: object) -> Context:
            assert cookie_mode and "user_data_dir" not in kwargs
            options.update(kwargs)
            return context

        async def close(self) -> None:
            closed.append("browser")

    class Playwright:
        async def __aenter__(self) -> object:
            async def persistent(**kwargs: object) -> Context:
                assert not cookie_mode
                options.update(kwargs)
                return context

            async def fresh(**kwargs: object) -> Browser:
                assert cookie_mode and "user_data_dir" not in kwargs
                options.update(kwargs)
                return Browser()

            return SimpleNamespace(
                chromium=SimpleNamespace(
                    executable_path="bundled-chromium", launch_persistent_context=persistent, launch=fresh
                )
            )

        async def __aexit__(self, *args: object) -> None:
            pass

    prepared = {
        "config": config,
        "tools.utils": utils,
        "media_platform.weibo.client": client_module,
        "playwright.async_api": SimpleNamespace(async_playwright=Playwright),
    }
    original_import = module.importlib.import_module

    def import_module(name: str, *args: object) -> Any:
        assert name not in {"media_platform.weibo.core", "media_platform.weibo.login", "store.weibo"}
        return prepared[name] if name in prepared else original_import(name, *args)

    monkeypatch.delitem(sys.modules, "config")
    monkeypatch.delitem(sys.modules, "media_platform.weibo.client")
    monkeypatch.setattr(module.importlib, "import_module", import_module)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.chdir(tmp_path)
    profile = tmp_path / "profile"
    cookie = SecretValue(expected_cookie) if cookie_mode else None
    if outcome == "success":
        result = await module._lookup_weibo(checkout, profile, "123", time.monotonic() + 10, cookie=cookie)
        assert result.remote_id == "123" and result.display_name == "平台昵称"
        assert "incidental feed" not in repr(result)
    else:
        with pytest.raises((module._LookupFailure, ValueError)):
            await module._lookup_weibo(checkout, profile, "123", time.monotonic() + 10, cookie=cookie)
    assert len(requests) == (2 if outcome in {"success", "wrong-id"} else 1)
    assert profile_calls == (["123"] if outcome in {"success", "wrong-id"} else [])
    assert options["headless"] is True and options["accept_downloads"] is False
    assert options["service_workers"] == "block" and options["executable_path"] == "bundled-chromium"
    assert options.get("user_data_dir") == (None if cookie_mode else str(profile))
    assert closed == (["context", "browser"] if cookie_mode else ["context"])
    assert pages == ["https://m.weibo.cn/"]
    assert not profile.exists()
    if cookie_mode:
        assert injected == [
            {"name": "SUB", "value": "NEW_COOKIE==", "domain": ".weibo.cn", "path": "/", "secure": True},
            {"name": "marker", "value": '"quoted=="', "domain": ".weibo.cn", "path": "/", "secure": True},
        ]

    for url in ("https://m.weibo.cn/api/config", "https://tva1.sinaimg.cn/large/abc.jpg", "http://127.0.0.1/private"):
        aborted: list[bool] = []

        async def abort(aborted: list[bool] = aborted) -> None:
            aborted.append(True)

        async def fulfill(**kwargs: object) -> None:
            pytest.fail("nonblank browser request must never be fulfilled")

        await context.router(
            SimpleNamespace(
                request=SimpleNamespace(url=url, is_navigation_request=lambda: True), abort=abort, fulfill=fulfill
            )
        )
        assert aborted == [True]
