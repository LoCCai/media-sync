"""Real pinned KS GraphQL/post methods, with no browser/network platform I/O."""

from __future__ import annotations

import inspect
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from media_sync.integrations.mediacrawler import kuaishou_creator_profile as module
from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout
from media_sync.security.secrets import SecretValue
from tests.contract.test_weibo_creator_profile_upstream import load, stub

UID = "3x4jtnbfter525a"


@pytest.fixture(scope="module")
def checkout() -> Path:
    return verify_mediacrawler_checkout(
        Path(__file__).resolve().parents[2] / "upstreams.lock.json",
        license_acknowledged=True,
    ).root


@pytest.fixture
def locked_client(checkout, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("unexpected login, pong, original HTTP, signing, content, or media method")

    class ProxyMixin:
        def init_proxy_pool(self, pool):
            assert pool is None

        async def _refresh_proxy_if_expired(self):
            forbidden()

    class AbstractClient:
        pass

    config = stub(monkeypatch, "config", __file__=str(checkout / "config/__init__.py"))
    utils = stub(
        monkeypatch,
        "tools.utils",
        __file__=str(checkout / "tools/utils.py"),
        get_user_agent=lambda: "offline-agent",
    )
    stub(monkeypatch, "tools", utils=utils, __path__=[])
    stub(monkeypatch, "tools.httpx_util", make_async_client=forbidden)
    stub(monkeypatch, "base", __path__=[])
    stub(monkeypatch, "base.base_crawler", AbstractApiClient=AbstractClient)
    stub(monkeypatch, "proxy", __path__=[])
    stub(monkeypatch, "proxy.proxy_mixin", ProxyRefreshMixin=ProxyMixin)
    stub(monkeypatch, "playwright", __path__=[])
    stub(monkeypatch, "playwright.async_api", Page=object, BrowserContext=object)
    stub(monkeypatch, "media_platform", __path__=[])
    stub(monkeypatch, "media_platform.kuaishou", __path__=[str(checkout / "media_platform/kuaishou")])
    stub(monkeypatch, "media_platform.kuaishou.help", get_ks_sign_from_playwright=forbidden)
    for name in ("exception", "graphql", "client"):
        loaded = load(monkeypatch, "media_platform.kuaishou." + name, checkout / f"media_platform/kuaishou/{name}.py")
    for name, method in vars(loaded.KuaiShouClient).items():
        if inspect.iscoroutinefunction(method) and name not in {"request", "post", "get_creator_profile"}:
            monkeypatch.setattr(loaded.KuaiShouClient, name, forbidden)
    return config, utils, loaded


@pytest.mark.parametrize("cookie_mode", [False, True], ids=["saved-session", "existing-cookie"])
@pytest.mark.parametrize(
    "outcome", ["success", "wrong-id", "missing-id", "bool-result", "errors", "redirect", "malformed"]
)
async def test_locked_ks_single_graphql_profile_and_isolated_credentials(
    checkout,
    locked_client,
    tmp_path,
    monkeypatch,
    cookie_mode,
    outcome,
):
    import media_sync.media.network as network

    config, utils, client_module = locked_client
    cookie_text = ("session=NEW==" if cookie_mode else "session=SAVED==") + '; marker="quoted=="'
    requests = []
    profile_calls = []
    injected = []
    closed = []
    options = {}
    pages = []
    query_source = (checkout / "media_platform/kuaishou/graphql/vision_profile.graphql").read_text()
    actual = client_module.KuaiShouClient.get_creator_profile

    async def counted(client, creator_id):
        profile_calls.append(creator_id)
        return await actual(client, creator_id)

    monkeypatch.setattr(client_module.KuaiShouClient, "get_creator_profile", counted)

    def transport(request):
        requests.append(request)
        assert request.method == "POST" and str(request.url) == "https://www.kuaishou.com/graphql"
        assert request.headers["Cookie"] == cookie_text
        assert request.headers["Origin"] == "https://www.kuaishou.com"
        assert request.headers["Referer"] == "https://www.kuaishou.com/"
        assert request.headers["User-Agent"] == "offline-agent"
        assert request.headers["Accept-Encoding"] == "identity"
        assert request.headers["Content-Type"] == "application/json;charset=UTF-8"
        assert json.loads(request.content) == {
            "operationName": "visionProfile",
            "variables": {"userId": UID},
            "query": query_source,
        }
        if outcome == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        if outcome == "malformed":
            return httpx.Response(200, headers={"Content-Type": "application/json"}, stream=httpx.ByteStream(b"bad"))
        profile = {
            "user_id": "3xWrong" if outcome == "wrong-id" else UID,
            "user_name": "真实字段合成昵称",
            "headurl": "http://127.0.0.1/never-fetch-avatar",
            "user_text": "incidental private text",
        }
        if outcome == "missing-id":
            del profile["user_id"]
        raw = {
            "data": {
                "visionProfile": {
                    "result": True if outcome == "bool-result" else 1,
                    "userProfile": {"profile": profile},
                }
            },
        }
        if outcome == "errors":
            raw["errors"] = [{"message": "private error body"}]
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=httpx.ByteStream(json.dumps(raw).encode()),
        )

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))
    # The transport should never inherit these deliberately unusable proxies.
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")

    class Page:
        async def goto(self, url, **kwargs):
            pages.append(url)
            fulfilled = []

            async def fulfill(**values):
                assert values == {"status": 200, "content_type": "text/html", "body": "<!doctype html><title></title>"}
                fulfilled.append(True)

            async def abort():
                pytest.fail("same-origin blank document must be fulfilled locally")

            await context.router(
                SimpleNamespace(
                    request=SimpleNamespace(url=url, is_navigation_request=lambda: True),
                    fulfill=fulfill,
                    abort=abort,
                )
            )
            assert fulfilled == [True]

    class Context:
        router: Any

        async def add_cookies(self, values):
            assert cookie_mode
            injected.extend(values)

        async def route(self, pattern, router):
            assert pattern == "**/*"
            self.router = router

        async def new_page(self):
            return Page()

        async def close(self):
            closed.append("context")

    context = Context()

    async def saved_cookies(value, urls):
        assert not cookie_mode, "existing Cookie must never reread or merge a saved browser profile"
        assert value is context and urls == ["https://www.kuaishou.com"]
        return cookie_text, {"session": "SAVED==", "marker": '"quoted=="'}

    monkeypatch.setattr(utils, "convert_browser_context_cookies", saved_cookies, raising=False)

    class Browser:
        async def new_context(self, **kwargs):
            assert cookie_mode and "user_data_dir" not in kwargs
            options.update(kwargs)
            return context

        async def close(self):
            closed.append("browser")

    class Playwright:
        async def __aenter__(self):
            async def persistent(**kwargs):
                assert not cookie_mode
                options.update(kwargs)
                return context

            async def fresh(**kwargs):
                assert cookie_mode and "user_data_dir" not in kwargs
                options.update(kwargs)
                return Browser()

            return SimpleNamespace(
                chromium=SimpleNamespace(
                    executable_path="bundled-chromium",
                    launch_persistent_context=persistent,
                    launch=fresh,
                )
            )

        async def __aexit__(self, *args):
            pass

    prepared = {
        "config": config,
        "tools.utils": utils,
        "media_platform.kuaishou.client": client_module,
        "playwright.async_api": SimpleNamespace(async_playwright=Playwright),
    }
    original_import = module.importlib.import_module

    def import_module(name, *args):
        assert name not in {"media_platform.kuaishou.core", "media_platform.kuaishou.login", "store.kuaishou"}
        return prepared[name] if name in prepared else original_import(name, *args)

    monkeypatch.delitem(sys.modules, "config")
    monkeypatch.delitem(sys.modules, "media_platform.kuaishou.client")
    monkeypatch.setattr(module.importlib, "import_module", import_module)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.chdir(tmp_path)
    saved_profile = tmp_path / "profile"
    cookie = SecretValue(cookie_text) if cookie_mode else None
    if outcome == "success":
        result = await module.lookup_kuaishou(checkout, saved_profile, UID, time.monotonic() + 10, cookie=cookie)
        assert result.remote_id == UID and result.display_name == "真实字段合成昵称" and result.avatar_url is None
        assert "incidental" not in repr(result)
    else:
        with pytest.raises((module._LookupFailure, ValueError)) as caught:
            await module.lookup_kuaishou(checkout, saved_profile, UID, time.monotonic() + 10, cookie=cookie)
        assert "auth_expired" not in str(caught.value)
        assert "private" not in str(caught.value)
    assert len(requests) == 1 and profile_calls == [UID]
    assert config.COOKIES == ""
    assert options["headless"] is True and options["accept_downloads"] is False
    assert options["service_workers"] == "block" and options["executable_path"] == "bundled-chromium"
    assert options.get("user_data_dir") == (None if cookie_mode else str(saved_profile))
    assert closed == (["context", "browser"] if cookie_mode else ["context"])
    assert pages == ["https://www.kuaishou.com/"]
    if cookie_mode:
        assert injected == [
            {"name": "session", "value": "NEW==", "domain": ".kuaishou.com", "path": "/", "secure": True},
            {"name": "marker", "value": '"quoted=="', "domain": ".kuaishou.com", "path": "/", "secure": True},
        ]
    assert not saved_profile.exists()
    for url in (module._ENDPOINT, module._ORIGIN + "/profile/" + UID, "http://127.0.0.1/private"):
        aborted = []

        async def abort(aborted=aborted):
            aborted.append(True)

        async def fulfill(**kwargs):
            pytest.fail("nonblank browser request must not be fulfilled")

        await context.router(
            SimpleNamespace(
                request=SimpleNamespace(url=url, is_navigation_request=lambda: True),
                abort=abort,
                fulfill=fulfill,
            )
        )
        assert aborted == [True]
