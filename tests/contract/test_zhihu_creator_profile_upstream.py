"""Full locked Zhihu client/help and real locked Node script, offline transport.

Only third-party import surfaces/browser/network are synthetic. The script is
loaded from the verified checkout and receives the synthetic Cookie over stdin.
"""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from media_sync.integrations.mediacrawler import zhihu_creator_profile as module
from media_sync.integrations.mediacrawler.creator_profile_runner import _LookupFailure
from media_sync.security.secrets import SecretValue
from tests.contract.test_cookie_login_upstream import checkout as checkout
from tests.contract.test_cookie_login_upstream import load
from tests.contract.test_cookie_login_upstream import offline as offline
from tests.unit.test_zhihu_creator_profile import COOKIE, TOKEN, _headers, _html


@pytest.fixture
def locked(checkout: Path, offline: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node runtime unavailable for the locked real Zhihu signature script")
    signed: list[tuple[str, str, dict[str, str]]] = []

    class JavaScript:
        def __init__(self, source: str) -> None:
            self.source = source

        def call(self, name: str, path: str, cookie: str) -> dict[str, str]:
            assert name == "get_sign"
            command = (
                self.source
                + "\nprocess.stdout.write(JSON.stringify(get_sign("
                + json.dumps(path)
                + ","
                + json.dumps(cookie)
                + ")));"
            )
            result = subprocess.run(
                [node, "-e", "eval(require('fs').readFileSync(0,'utf8'))"],
                input=command.encode(),
                capture_output=True,
                check=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            output = json.loads(result.stdout)
            assert set(output) == {"x-zst-81", "x-zse-96"} and output["x-zse-96"].startswith("2.0_")
            signed.append((path, cookie, output))
            return output

    for part in ("field", "exception", "help", "client"):
        loaded = load(monkeypatch, f"media_platform.zhihu.{part}", checkout / f"media_platform/zhihu/{part}.py")
        if part == "help":
            helper = loaded
    helper.execjs.get = lambda name: SimpleNamespace(compile=JavaScript) if name == "Node" else offline["forbidden"]()
    helper.execjs.compile = JavaScript
    client_module = sys.modules["media_platform.zhihu.client"]
    assert client_module.ZhiHuClient.__module__ == "media_platform.zhihu.client"
    monkeypatch.chdir(checkout)
    return SimpleNamespace(
        client=client_module, helper=helper, signed=signed, config=offline["config"], utils=offline["utils"]
    )


@pytest.mark.parametrize("cookie_mode", [False, True], ids=["saved", "candidate"])
@pytest.mark.parametrize(
    "outcome",
    ["success", "auth_error", "public_as_self", "wrong_token", "missing_token", "redirect", "oversize", "missing_dc0"],
)
async def test_locked_two_signed_requests_and_browser_network_denied(
    checkout: Path,
    locked: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cookie_mode: bool,
    outcome: str,
) -> None:
    import media_sync.media.network as network

    candidate = COOKIE if outcome != "missing_dc0" else "z_c0=PRIVATE_ONLY=="
    requests: list[httpx.Request] = []
    closes: list[str] = []
    injected: list[dict[str, str]] = []
    observed_profiles: list[str] = []
    original_profile = locked.client.ZhiHuClient.get_creator_info

    async def counted(client: Any, token: str) -> Any:
        observed_profiles.append(token)
        return await original_profile(client, token)

    monkeypatch.setattr(locked.client.ZhiHuClient, "get_creator_info", counted)

    def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET" and request.url.host == "www.zhihu.com" and request.url.query == b""
        assert request.headers["cookie"] == candidate and request.headers["accept-encoding"] == "identity"
        path, cookie, signed = locked.signed[-1]
        assert path == request.url.path and cookie == candidate
        assert all(request.headers[key] == value for key, value in signed.items())
        if request.url.path == "/api/v4/me":
            data = {"uid": "123", "name": "Authenticated self"}
            if outcome == "auth_error":
                data = {"error": {"code": 401}}
            elif outcome == "public_as_self":
                data = {"urlToken": TOKEN, "name": "public target", "id": "456"}
            return httpx.Response(
                200, headers={"content-type": "application/json"}, stream=httpx.ByteStream(json.dumps(data).encode())
            )
        assert request.url.path == "/people/" + TOKEN
        if outcome == "redirect":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        row: dict[str, Any] = {"urlToken": TOKEN, "name": "Unmasked raw nickname"}
        if outcome == "wrong_token":
            row["urlToken"] = "someone-else"
        elif outcome == "missing_token":
            del row["urlToken"]
        payload = _html(row).encode() if outcome != "oversize" else b"x" * (module.MAX_PROFILE_HTML_BYTES + 1)
        return httpx.Response(
            200, headers={"content-type": "text/html; charset=utf-8"}, stream=httpx.ByteStream(payload)
        )

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))

    class Context:
        async def route(self, pattern: str, handler: Any) -> None:
            assert pattern == "**/*"
            for url in ("https://www.zhihu.com/", "https://www.zhihu.com/search", "https://unknown.example/script"):
                aborted: list[bool] = []

                async def abort(observed: list[bool] = aborted) -> None:
                    observed.append(True)

                await handler(SimpleNamespace(request=SimpleNamespace(url=url), abort=abort))
                assert aborted == [True]

        async def add_cookies(self, values: list[dict[str, str]]) -> None:
            assert cookie_mode
            injected.extend(values)

        async def new_page(self) -> None:
            pytest.fail("profile does not need any browser page or navigation")

        async def close(self) -> None:
            closes.append("context")

    context = Context()

    async def cookies(value: object, urls: list[str]) -> tuple[str, dict[str, str]]:
        assert not cookie_mode and value is context and urls == ["https://www.zhihu.com"]
        return candidate, {}

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
                assert kwargs["executable_path"] == "bundled" and kwargs["service_workers"] == "block"
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
        "tools.utils": locked.utils,
        "media_platform.zhihu.client": locked.client,
        "media_platform.zhihu.help": locked.helper,
        "playwright.async_api": SimpleNamespace(async_playwright=Playwright),
    }
    original_import = importlib.import_module
    original_compile = locked.helper.execjs.compile

    def importing(name: str, *args: Any) -> Any:
        assert name not in {"media_platform.zhihu.core", "media_platform.zhihu.login", "store.zhihu"}
        return prepared[name] if name in prepared else original_import(name, *args)

    monkeypatch.delitem(sys.modules, "config")
    monkeypatch.delitem(sys.modules, "media_platform.zhihu.client")
    monkeypatch.setattr(module.importlib, "import_module", importing)
    if outcome == "success":
        result = await module.lookup_zhihu(
            checkout,
            tmp_path / "profile",
            TOKEN,
            time.monotonic() + 15,
            cookie=SecretValue(candidate) if cookie_mode else None,
        )
        assert (
            result.remote_id == TOKEN and result.display_name == "Unmasked raw nickname" and result.avatar_url is None
        )
    else:
        expected_status = (
            "auth_expired"
            if outcome == "auth_error"
            else "configuration_invalid"
            if outcome == "missing_dc0"
            else "result_invalid"
        )
        with pytest.raises(_LookupFailure, match=expected_status):
            await module.lookup_zhihu(
                checkout,
                tmp_path / "profile",
                TOKEN,
                time.monotonic() + 15,
                cookie=SecretValue(candidate) if cookie_mode else None,
            )
    count = 0 if outcome == "missing_dc0" else 1 if outcome in {"auth_error", "public_as_self"} else 2
    assert len(requests) == len(locked.signed) == count
    assert observed_profiles == ([TOKEN] if count == 2 else [])
    assert closes == ["context"] + (["browser"] if cookie_mode else [])
    assert bool(injected) is cookie_mode and all(item["domain"] == ".zhihu.com" for item in injected)
    assert locked.helper.execjs.compile is original_compile and locked.config.COOKIES == ""


@pytest.mark.parametrize(
    "change",
    ["cookie", "extra_url", "extra_call", "missing_sign", "bypass_get", "bypass_profile", "substitute_html", "cancel"],
)
async def test_request_and_extractor_guards_restore_after_failure(
    checkout: Path, locked: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    import asyncio

    base_headers = {key: value for key, value in _headers().items() if key not in module._SIGN_HEADERS}
    client = locked.client.ZhiHuClient(
        headers=base_headers, playwright_page=None, cookie_dict={"d_c0": "PRIVATE_SIGN=="}, proxy=None
    )
    original_request, original_extract = client.request, client._extractor.extract_creator
    get = client.get
    fetched: list[str] = []

    def fetch(url: str, headers: dict[str, str], deadline: float, *, token: str, html: bool) -> bytes:
        fetched.append(url)
        return _html().encode() if html else b'{"uid":"123","name":"self"}'

    monkeypatch.setattr(module, "_fetch", fetch)
    if change in {"cookie", "missing_sign"}:
        pre_headers = client._pre_headers

        async def altered_headers(url: str) -> dict[str, str]:
            headers = await pre_headers(url)
            if change == "cookie":
                headers["cookie"] = "substituted"
            else:
                del headers["x-zse-96"]
            return headers

        client._pre_headers = altered_headers
    elif change in {"extra_url", "extra_call", "bypass_get", "cancel"}:

        async def altered_get(path: str, **kwargs: Any) -> Any:
            if change == "bypass_get":
                return {"uid": "123", "name": "self"}
            if change == "cancel":
                raise asyncio.CancelledError
            result = await get(path + "/unexpected" if change == "extra_url" else path, **kwargs)
            if change == "extra_call":
                await get(path, **kwargs)
            return result

        client.get = altered_get
    else:

        async def altered_profile(token: str) -> Any:
            if change == "bypass_profile":
                return module.parse_zhihu_profile_html(_html(), token)
            await get("/people/" + token, return_response=True)
            return client._extractor.extract_creator(token, _html())

        client.get_creator_info = altered_profile
    with pytest.raises(asyncio.CancelledError if change == "cancel" else _LookupFailure):
        await module.query_zhihu_client(client, TOKEN, time.monotonic() + 10)
    assert client.request == original_request and client._extractor.extract_creator == original_extract
    assert len(fetched) <= 2
