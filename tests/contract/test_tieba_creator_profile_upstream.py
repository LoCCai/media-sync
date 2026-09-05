"""Real locked Tieba creator/browser/sign chain with original synthetic HTTP data."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from media_sync.integrations.mediacrawler import tieba_creator_profile as module
from media_sync.integrations.mediacrawler.creator_profile_runner import _LookupFailure
from media_sync.security.secrets import SecretValue
from tests.contract.test_cookie_login_upstream import checkout as checkout
from tests.contract.test_cookie_login_upstream import load, stub
from tests.contract.test_cookie_login_upstream import offline as offline
from tests.unit.test_tieba_creator_profile import COOKIE, PORTRAIT, STAMP, evidence, headers, with_avatar


@pytest.fixture
def locked(checkout: Path, offline: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    class RetryError(Exception):
        pass

    monkeypatch.setattr(sys.modules["tenacity"], "RetryError", RetryError)
    stub(monkeypatch, "model.m_baidu_tieba", TiebaComment=object, TiebaCreator=object, TiebaNote=object)
    stub(monkeypatch, "proxy.proxy_ip_pool", ProxyIpPool=object)
    stub(monkeypatch, "requests", get=offline["forbidden"], post=offline["forbidden"], Session=offline["forbidden"])
    constant = load(monkeypatch, "constant.baidu_tieba", checkout / "constant/baidu_tieba.py")
    monkeypatch.setattr(sys.modules["constant"], "baidu_tieba", constant, raising=False)
    for name in ("field", "help", "client"):
        load(monkeypatch, f"media_platform.tieba.{name}", checkout / f"media_platform/tieba/{name}.py")
    client_module = sys.modules["media_platform.tieba.client"]
    client_type = client_module.BaiduTieBaClient
    assert client_type.__module__ == client_module.__name__
    for name, method in vars(client_type).items():
        if inspect.iscoroutinefunction(method) and name not in {
            "get_creator_info_by_url",
            "_fetch_json_by_browser",
            "_ensure_tieba_origin",
        }:
            monkeypatch.setattr(client_type, name, offline["forbidden"])
    monkeypatch.setattr(client_type, "_sync_request", offline["forbidden"])
    monkeypatch.chdir(checkout)
    monkeypatch.syspath_prepend(str(checkout))
    return SimpleNamespace(
        client=client_module,
        helper=sys.modules["media_platform.tieba.help"],
        config=offline["config"],
        utils=offline["utils"],
        forbidden=offline["forbidden"],
    )


@pytest.mark.parametrize("cookie_mode", [False, True], ids=["saved", "candidate"])
@pytest.mark.parametrize(
    "outcome",
    [
        "success",
        "timestamp",
        "fallback_name",
        "unknown_avatar",
        "wrong_avatar",
        "explicit_avatar",
        "no_code",
        "error",
        "wrong_portrait",
        "missing_portrait",
        "bad_stamp",
        "duplicate_json",
        "nan",
        "surrogate",
        "redirect",
        "oversize",
    ],
)
async def test_real_signed_lookup_and_private_cookie_context(
    checkout: Path,
    locked: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cookie_mode: bool,
    outcome: str,
) -> None:
    import media_sync.media.network as network

    requests: list[httpx.Request] = []
    signatures: list[dict[str, Any]] = []
    creators: list[str] = []
    closes: list[str] = []
    injected: list[dict[str, Any]] = []
    original_sign = locked.client.BaiduTieBaClient._sign_pc_params
    original_creator = locked.client.BaiduTieBaClient.get_creator_info_by_url

    def signed(params: dict[str, Any]) -> str:
        signatures.append(dict(params))
        return original_sign(params)

    async def creator(client: Any, url: str) -> Any:
        creators.append(url)
        return await original_creator(client, url)

    monkeypatch.setattr(locked.client.BaiduTieBaClient, "_sign_pc_params", staticmethod(signed))
    monkeypatch.setattr(locked.client.BaiduTieBaClient, "get_creator_info_by_url", creator)
    raw = evidence(timestamp=outcome in {"timestamp", "explicit_avatar"})
    if outcome == "fallback_name":
        raw["data"]["user"]["name_show"] = ""
    elif outcome == "no_code":
        del raw["error_code"]
    elif outcome == "error":
        raw["error_code"] = 210001
    elif outcome == "wrong_portrait":
        raw["data"]["user"]["portrait"] = "tb.1." + "b" * 28
    elif outcome == "missing_portrait":
        del raw["data"]["user"]["portrait"]
    elif outcome == "bad_stamp":
        raw["data"]["user"]["portrait"] += "?t=123"
    elif outcome == "surrogate":
        raw["data"]["user"]["name_show"] = "\ud800"
    elif outcome in {"unknown_avatar", "wrong_avatar", "explicit_avatar"}:
        with_avatar(
            raw,
            {
                "unknown_avatar": "https://unknown.example/PRIVATE_AVATAR",
                "wrong_avatar": module._AVATAR + "tb.1." + "b" * 28,
                "explicit_avatar": module._AVATAR + PORTRAIT + STAMP,
            }[outcome],
        )
    payload = json.dumps(raw).encode()
    if outcome == "duplicate_json":
        payload = payload.replace(b'"error_code": 0', b'"error_code": 1, "error_code": 0')
    elif outcome == "nan":
        payload = payload.replace(b'"id": 123', b'"id": NaN')

    def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET" and request.url.host == "tieba.baidu.com" and not request.content
        assert request.headers["cookie"] == COOKIE and request.headers["accept-encoding"] == "identity"
        assert request.url.path == "/c/u/pc/homeSidebarRight"
        assert signatures == [module._params(PORTRAIT)]
        params = parse_qs(request.url.query.decode(), keep_blank_values=True)
        assert params == {
            key: [value]
            for key, value in {**module._params(PORTRAIT), "sign": original_sign(module._params(PORTRAIT))}.items()
        }
        if outcome == "redirect":
            return httpx.Response(302, headers={"location": "https://unknown.example/PRIVATE_REDIRECT"})
        return httpx.Response(
            200,
            headers={"content-type": "application/json; charset=utf-8"},
            stream=httpx.ByteStream(b"x" * (module.MAX_PROFILE_API_BYTES + 1) if outcome == "oversize" else payload),
        )

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))

    class Context:
        async def route(self, pattern: str, handler: Any) -> None:
            assert pattern == "**/*"
            for url in ("https://tieba.baidu.com", "https://tieba.baidu.com/c/s/pc/sync", "https://unknown.example"):
                aborted: list[bool] = []

                async def abort(observed: list[bool] = aborted) -> None:
                    observed.append(True)

                await handler(SimpleNamespace(request=SimpleNamespace(url=url), abort=abort))
                assert aborted == [True]

        async def add_cookies(self, values: list[dict[str, Any]]) -> None:
            assert cookie_mode
            injected.extend(values)

        async def new_page(self) -> None:
            pytest.fail("no real browser page or navigation needed")

        async def close(self) -> None:
            closes.append("context")

    context = Context()

    async def cookies(value: Any, urls: list[str]) -> tuple[str, dict[str, str]]:
        assert not cookie_mode and value is context and urls == ["https://tieba.baidu.com"]
        return COOKIE, {}

    monkeypatch.setattr(locked.utils, "convert_browser_context_cookies", cookies, raising=False)

    class Browser:
        async def new_context(self, **kwargs: Any) -> Context:
            assert cookie_mode and kwargs == {"accept_downloads": False, "service_workers": "block"}
            return context

        async def close(self) -> None:
            closes.append("browser")

    class Playwright:
        async def __aenter__(self) -> Any:
            async def persistent(**kwargs: Any) -> Context:
                assert not cookie_mode and kwargs["user_data_dir"] == str(tmp_path / "profile")
                assert kwargs["headless"] and kwargs["service_workers"] == "block"
                return context

            async def fresh(**kwargs: Any) -> Browser:
                assert cookie_mode and "user_data_dir" not in kwargs and kwargs["executable_path"] == "bundled"
                return Browser()

            return SimpleNamespace(
                chromium=SimpleNamespace(executable_path="bundled", launch=fresh, launch_persistent_context=persistent)
            )

        async def __aexit__(self, *args: Any) -> None:
            pass

    prepared = {
        "config": locked.config,
        "media_platform.tieba.client": locked.client,
        "media_platform.tieba.help": locked.helper,
        "tools.utils": locked.utils,
        "playwright.async_api": SimpleNamespace(async_playwright=Playwright),
    }
    original_import = importlib.import_module

    def importing(name: str, *args: Any) -> Any:
        assert name not in {"media_platform.tieba.core", "media_platform.tieba.login", "store.tieba"}
        return prepared[name] if name in prepared else original_import(name, *args)

    monkeypatch.delitem(sys.modules, "config")
    monkeypatch.delitem(sys.modules, "media_platform.tieba.client")
    monkeypatch.setattr(module.importlib, "import_module", importing)
    success = outcome in {"success", "timestamp", "fallback_name", "unknown_avatar", "wrong_avatar", "explicit_avatar"}
    if success:
        result = await module.lookup_tieba(
            checkout,
            tmp_path / "profile",
            PORTRAIT,
            time.monotonic() + 10,
            cookie=SecretValue(COOKIE) if cookie_mode else None,
        )
        assert result.remote_id == PORTRAIT
        assert result.display_name == ("Platform username" if outcome == "fallback_name" else "原始平台昵称")
        assert result.avatar_url == (
            None if outcome in {"unknown_avatar", "wrong_avatar"} else module._AVATAR + raw["data"]["user"]["portrait"]
        )
        assert "PRIVATE" not in repr(result) and "not retained" not in repr(result)
    else:
        with pytest.raises(_LookupFailure, match="result_invalid") as error:
            await module.lookup_tieba(
                checkout,
                tmp_path / "profile",
                PORTRAIT,
                time.monotonic() + 10,
                cookie=SecretValue(COOKIE) if cookie_mode else None,
            )
        assert "PRIVATE" not in str(error.value)
    assert len(requests) == len(signatures) == 1
    assert creators == ["https://tieba.baidu.com/home/main?id=" + PORTRAIT]
    assert closes == ["context"] + (["browser"] if cookie_mode else [])
    assert bool(injected) is cookie_mode
    assert all(item["domain"] == ".tieba.baidu.com" and item["secure"] is True for item in injected)
    assert {item["name"]: item["value"] for item in injected} == (module.cookie_pairs(COOKIE) if cookie_mode else {})
    assert locked.config.COOKIES == "" and locked.config.ENABLE_IP_PROXY is False


@pytest.mark.parametrize(
    "change",
    [
        "cookie",
        "host",
        "params",
        "signature",
        "script",
        "body",
        "method",
        "url",
        "second_evaluate",
        "goto",
        "bypass_creator",
        "substitute_extract",
        "mutate_extract",
        "twice_extract",
        "bypass_fetch",
        "twice_fetch",
        "cancel",
    ],
)
async def test_real_methods_cannot_escape_one_call_or_substitute_response(
    checkout: Path, locked: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    client = locked.client.BaiduTieBaClient(
        headers=headers(), playwright_page=None, ip_pool=None, default_ip_proxy=None
    )
    original_creator = client.get_creator_info_by_url
    original_fetch = client._fetch_json_by_browser
    original_sign = client._sign_pc_params
    original_extract = client._page_extractor.extract_creator_info_from_api
    calls: list[str] = []

    def transport(url: str, headers: dict[str, str], deadline: float, *, remote_id: str) -> bytes:
        calls.append(url)
        return json.dumps(evidence()).encode()

    monkeypatch.setattr(module, "_fetch", transport)

    async def altered_creator(url: str) -> Any:
        if change == "cancel":
            raise asyncio.CancelledError
        if change == "bypass_creator":
            return module.parse_tieba_profile_json(evidence(), PORTRAIT)
        if change == "cookie":
            client.headers["Cookie"] = "changed"
        elif change == "host":
            client._host = "https://tieba.baidu.com.evil.invalid"
        elif change in {"params", "signature", "script", "body", "method", "url", "second_evaluate", "goto"}:
            if change == "params":
                return await client._fetch_json_by_browser(
                    module._PATH, params={**module._params(PORTRAIT), "un": "other"}, use_sign=True
                )
            if change == "signature":
                guarded_sign = client._sign_pc_params

                def wrong_sign(params: Any) -> str:
                    guarded_sign(params)
                    return "b" * 32

                client._sign_pc_params = wrong_sign
            else:
                page = client.playwright_page
                guarded_evaluate = page.evaluate

                async def altered_evaluate(expression: str, arguments: dict[str, Any]) -> Any:
                    if change == "goto":
                        await page.goto("https://tieba.baidu.com/")
                    if change == "script":
                        expression += "\n// changed"
                    elif change in {"body", "method", "url"}:
                        arguments[change] = {"body": "private=1", "method": "POST", "url": "https://unknown.example"}[
                            change
                        ]
                    result = await guarded_evaluate(expression, arguments)
                    if change == "second_evaluate":
                        await guarded_evaluate(expression, arguments)
                    return result

                page.evaluate = altered_evaluate
        if change in {"substitute_extract", "mutate_extract", "twice_extract"}:
            value = await client._fetch_json_by_browser(module._PATH, params=module._params(PORTRAIT), use_sign=True)
            if change == "mutate_extract":
                value["data"]["user"]["name_show"] = "substituted nickname"
            result = client._page_extractor.extract_creator_info_from_api(
                dict(value) if change == "substitute_extract" else value
            )
            if change == "twice_extract":
                client._page_extractor.extract_creator_info_from_api(value)
            return result
        if change == "bypass_fetch":
            return client._page_extractor.extract_creator_info_from_api(evidence())
        result = await original_creator(url)
        if change == "twice_fetch":
            await client._fetch_json_by_browser(module._PATH, params=module._params(PORTRAIT), use_sign=True)
        return result

    client.get_creator_info_by_url = altered_creator
    with pytest.raises(asyncio.CancelledError if change == "cancel" else _LookupFailure):
        await module.query_tieba_client(client, PORTRAIT, time.monotonic() + 10)
    assert client.playwright_page is None
    assert client._fetch_json_by_browser == original_fetch and client._sign_pc_params == original_sign
    assert client._page_extractor.extract_creator_info_from_api == original_extract
    assert len(calls) <= 1
