"""Real locked client/help/Node signature, synthetic bounded HTTP and browser.

No third-party response fixture or platform I/O is used. Synthetic private
values reach Node only over stdin, never argv or an on-disk script.
"""

from __future__ import annotations

import inspect
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from media_sync.integrations.mediacrawler import douyin_creator_profile as module
from media_sync.security.secrets import SecretValue
from tests.contract.test_cookie_login_upstream import checkout as checkout
from tests.contract.test_cookie_login_upstream import load
from tests.contract.test_cookie_login_upstream import offline as offline
from tests.contract.test_weibo_creator_profile_upstream import stub
from tests.unit.test_douyin_creator_profile import UID, response


@pytest.fixture
def locked(checkout: Path, offline: dict[str, Any], monkeypatch: pytest.MonkeyPatch):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node runtime unavailable for the real locked Douyin signature script")
    signed, compiled, client_calls = [], [], []
    forbidden = offline["forbidden"]

    class JavaScript:
        def __init__(self, source: str):
            assert source == (checkout / "libs/douyin.js").read_text(encoding="utf-8-sig")
            compiled.append(True)
            self.source = source

        def call(self, name: str, query: str, agent: str):
            assert name == "sign_datail" and agent == "offline-agent"
            command = self.source + "\nprocess.stdout.write(JSON.stringify(sign_datail(" + json.dumps(query)
            command += "," + json.dumps(agent) + ")));"
            args = [node, "-e", "eval(require('fs').readFileSync(0,'utf8'))"]
            assert not any("PRIVATE" in item for item in args)
            result = subprocess.run(
                args,
                input=command.encode(),
                capture_output=True,
                check=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            signature = json.loads(result.stdout)
            assert isinstance(signature, str) and len(signature) > 50 and signature.endswith("=")
            signed.append((query, agent, signature))
            return signature

    execjs = sys.modules["execjs"]
    monkeypatch.setattr(execjs, "compile", forbidden)
    monkeypatch.setattr(
        execjs, "get", lambda name: SimpleNamespace(compile=JavaScript) if name == "Node" else forbidden()
    )
    stub(monkeypatch, "var", request_keyword_var=object())
    stub(monkeypatch, "model.m_douyin", VideoUrlInfo=object, CreatorUrlInfo=object)
    monkeypatch.setattr(sys.modules["tools.crawler_util"], "extract_url_params_to_dict", forbidden, raising=False)
    for part in ("field", "exception"):
        load(monkeypatch, f"media_platform.douyin.{part}", checkout / f"media_platform/douyin/{part}.py")
    original_import = module.importlib.import_module
    loaded: dict[str, Any] = {}

    def import_client():
        assert execjs.compile is not forbidden, "the real helper must compile only after selecting Node"
        loaded["helper"] = load(monkeypatch, "media_platform.douyin.help", checkout / "media_platform/douyin/help.py")
        client_module = load(monkeypatch, "media_platform.douyin.client", checkout / "media_platform/douyin/client.py")
        loaded["client"] = client_module
        original_profile = client_module.DouYinClient.get_user_info

        async def profile(client, sec_user_id):
            client_calls.append(sec_user_id)
            return await original_profile(client, sec_user_id)

        monkeypatch.setattr(client_module.DouYinClient, "get_user_info", profile)
        for name, method in vars(client_module.DouYinClient).items():
            if inspect.iscoroutinefunction(method) and name not in {
                "get_user_info",
                "get",
                "request",
                "_DouYinClient__process_req_params",
            }:
                monkeypatch.setattr(client_module.DouYinClient, name, forbidden)
        return client_module

    prepared = {"config": offline["config"], "tools.utils": offline["utils"], "execjs": execjs}

    def import_module(name, *args):
        assert name not in {"media_platform.douyin.core", "media_platform.douyin.login", "store.douyin"}
        if name == "media_platform.douyin.client":
            return import_client()
        if name == "media_platform.douyin.help":
            return loaded["helper"]
        return prepared[name] if name in prepared else original_import(name, *args)

    monkeypatch.delitem(sys.modules, "config")
    monkeypatch.setattr(module.importlib, "import_module", import_module)
    monkeypatch.setattr(sys, "path", list(sys.path))
    return SimpleNamespace(
        signed=signed,
        compiled=compiled,
        calls=client_calls,
        loaded=loaded,
        config=offline["config"],
        utils=offline["utils"],
        prepared=prepared,
        execjs=execjs,
        forbidden=forbidden,
    )


@pytest.mark.parametrize("cookie_mode", [False, True], ids=["saved", "candidate"])
@pytest.mark.parametrize(
    "outcome",
    [
        "success",
        "wrong-id",
        "missing-id",
        "bool-status",
        "missing-status",
        "nickname",
        "redirect",
        "oversize",
        "duplicate",
        "private-error",
    ],
)
async def test_real_locked_signature_and_exact_single_request_without_browser_network(
    checkout, locked, tmp_path, monkeypatch, cookie_mode, outcome
):
    import media_sync.media.network as network

    cookie_text = ("session=PRIVATE_NEW==" if cookie_mode else "session=PRIVATE_SAVED==") + '; marker="quoted=="'
    requests, closes, injected, navigations, evaluations, options = [], [], [], [], [], {}
    # Fresh Cookie contexts have no localStorage; do not guess a token from
    # Cookies or fetch another token endpoint. The signer sees literal None.
    storage = {} if cookie_mode else {"xmst": "PRIVATE_LOCAL_TOKEN==", "HasUserLogin": "1"}

    def transport(request):
        requests.append(request)
        assert request.method == "GET" and request.url.host == "www.douyin.com"
        assert request.url.path == module._PATH and request.url.fragment == ""
        assert request.headers["Cookie"] == cookie_text
        assert request.headers["Origin"] == module._ORIGIN + "/"
        assert request.headers["Referer"] == module._ORIGIN + "/"
        assert request.headers["Accept-Encoding"] == "identity"
        assert request.headers["User-Agent"] == "offline-agent"
        actual_query = request.url.query.decode("ascii")
        unsigned, signature = actual_query.rsplit("&a_bogus=", 1)
        assert unsigned == locked.signed[0][0]
        assert parse_qs("signature=" + signature)["signature"] == [locked.signed[0][2]]
        fields = parse_qs(unsigned)
        assert fields["sec_user_id"] == [UID]
        assert fields["msToken"] == (["None"] if cookie_mode else [storage["xmst"]])
        assert len(fields["webid"][0]) == 19 and fields["webid"][0].isascii()
        if outcome == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        if outcome == "private-error":
            return httpx.Response(403, stream=httpx.ByteStream(b"PRIVATE_SERVER_ERROR_COOKIE"))
        raw = response()
        if outcome == "wrong-id":
            raw["user"]["sec_uid"] = "wrong"
        elif outcome == "missing-id":
            del raw["user"]["sec_uid"]
        elif outcome == "bool-status":
            raw["status_code"] = False
        elif outcome == "missing-status":
            del raw["status_code"]
        elif outcome == "nickname":
            raw["user"]["nickname"] = "bad\ud800name"
        payload = json.dumps(raw).encode()
        if outcome == "oversize":
            payload = b"x" * (module.MAX_PROFILE_API_BYTES + 1)
        elif outcome == "duplicate":
            payload = b'{"status_code":0,"user":{},"user":{}}'
        return httpx.Response(200, headers={"Content-Type": "application/json"}, stream=httpx.ByteStream(payload))

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")

    class Page:
        async def goto(self, url, **kwargs):
            navigations.append(url)
            assert url == module._ORIGIN + "/" and kwargs["timeout"] <= 10000
            fulfilled = []

            async def fulfill(**values):
                assert values == {"status": 200, "content_type": "text/html", "body": "<!doctype html><title></title>"}
                fulfilled.append(True)

            await context.router(
                SimpleNamespace(
                    request=SimpleNamespace(url=url, is_navigation_request=lambda: True),
                    fulfill=fulfill,
                    abort=locked.forbidden,
                )
            )
            assert fulfilled == [True]

        async def evaluate(self, script):
            evaluations.append(script)
            assert script in {"() => navigator.userAgent", "() => window.localStorage"}
            return "offline-agent" if script == "() => navigator.userAgent" else dict(storage)

    class Context:
        router: Any

        async def route(self, pattern, router):
            assert pattern == "**/*"
            self.router = router

        async def new_page(self):
            return Page()

        async def add_cookies(self, values):
            assert cookie_mode
            injected.extend(values)

        async def close(self):
            closes.append("context")

    context = Context()

    async def cookies(value, urls):
        assert not cookie_mode, "candidate Cookie must never merge saved-session fields"
        assert value is context and urls == [module._ORIGIN]
        return cookie_text, {}

    monkeypatch.setattr(locked.utils, "convert_browser_context_cookies", cookies, raising=False)

    class Browser:
        async def new_context(self, **kwargs):
            assert cookie_mode and "user_data_dir" not in kwargs
            options.update(kwargs)
            return context

        async def close(self):
            closes.append("browser")

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
                    executable_path="bundled-chromium", launch_persistent_context=persistent, launch=fresh
                )
            )

        async def __aexit__(self, *args):
            pass

    locked.prepared["playwright.async_api"] = SimpleNamespace(async_playwright=Playwright)
    monkeypatch.chdir(tmp_path)
    saved_profile = tmp_path / "saved-profile"
    credential = SecretValue(cookie_text) if cookie_mode else None
    if outcome == "success":
        result = await module.lookup_douyin(checkout, saved_profile, UID, time.monotonic() + 10, cookie=credential)
        assert (result.remote_id, result.display_name, result.avatar_url) == (UID, "准确昵称", None)
        assert "private" not in repr(result) and "PRIVATE" not in repr(result)
    else:
        with pytest.raises((module._LookupFailure, ValueError)) as caught:
            await module.lookup_douyin(checkout, saved_profile, UID, time.monotonic() + 10, cookie=credential)
        assert "auth_expired" not in str(caught.value) and "PRIVATE" not in str(caught.value)
    assert len(requests) == 1 and len(locked.signed) == 1 and locked.compiled == [True] and locked.calls == [UID]
    assert locked.execjs.compile is locked.forbidden
    assert locked.config.COOKIES == ""
    assert navigations == [module._ORIGIN + "/"]
    assert evaluations == ["() => navigator.userAgent", "() => window.localStorage"]
    assert options["headless"] is True and options["accept_downloads"] is False
    assert options["service_workers"] == "block" and options["executable_path"] == "bundled-chromium"
    assert options.get("user_data_dir") == (None if cookie_mode else str(saved_profile))
    assert closes == (["context", "browser"] if cookie_mode else ["context"])
    assert not saved_profile.exists()
    if cookie_mode:
        assert injected == [
            {"name": "session", "value": "PRIVATE_NEW==", "domain": ".douyin.com", "path": "/", "secure": True},
            {"name": "marker", "value": '"quoted=="', "domain": ".douyin.com", "path": "/", "secure": True},
        ]
    else:
        assert injected == []
    for url in (module._ENDPOINT, module._ORIGIN + "/user/" + UID, "http://127.0.0.1/private"):
        aborted = []

        async def abort(observed=aborted):
            observed.append(True)

        await context.router(
            SimpleNamespace(
                request=SimpleNamespace(url=url, is_navigation_request=lambda: True),
                abort=abort,
                fulfill=locked.forbidden,
            )
        )
        assert aborted == [True]


async def test_missing_node_fails_before_helper_browser_or_network(checkout, locked, monkeypatch, tmp_path):
    def no_node(name):
        raise RuntimeError("PRIVATE runtime paths must not escape")

    monkeypatch.setattr(locked.execjs, "get", no_node)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(module._LookupFailure, match="configuration_invalid") as caught:
        await module.lookup_douyin(checkout, tmp_path / "profile", UID, time.monotonic() + 5)
    assert "PRIVATE" not in str(caught.value)
    assert locked.compiled == [] and locked.calls == [] and locked.signed == []
    assert locked.execjs.compile is locked.forbidden
