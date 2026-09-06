"""Real locked KS constructor/post with synthetic, pinned and bounded transport."""

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

import httpx
import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import cookie_login_runner as runner
from media_sync.integrations.mediacrawler import kuaishou_cookie_login as module
from tests.contract.test_cookie_login_upstream import checkout as checkout
from tests.contract.test_cookie_login_upstream import load, stub
from tests.contract.test_cookie_login_upstream import offline as offline
from tests.unit.test_kuaishou_cookie_login import COOKIE, evidence, headers, request


@pytest.fixture
def kuaishou(checkout: Path, offline: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    import media_sync.media.network as network

    stub(monkeypatch, "media_platform.kuaishou.help", get_ks_sign_from_playwright=offline["forbidden"])
    for part in ("exception", "graphql", "client"):
        load(monkeypatch, f"media_platform.kuaishou.{part}", checkout / f"media_platform/kuaishou/{part}.py")
    client_module = sys.modules["media_platform.kuaishou.client"]
    client_type = client_module.KuaiShouClient
    for method_name, method in vars(client_type).items():
        if inspect.iscoroutinefunction(method) and method_name not in {"post", "request"}:
            monkeypatch.setattr(client_type, method_name, offline["forbidden"])
    prepared = {"config": offline["config"], client_module.__name__: client_module}
    original_import = importlib.import_module
    for name in prepared:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(
        module.importlib, "import_module", lambda name, *args: prepared.get(name) or original_import(name, *args)
    )
    monkeypatch.chdir(checkout)
    monkeypatch.syspath_prepend(str(checkout))
    settings = {
        "body": evidence(),
        "status": 200,
        "raw": None,
        "dns": "8.8.8.8",
        "content_type": "application/json",
        "encoding": "identity",
    }
    seen: list[httpx.Request] = []
    targets = []
    clients = []
    original_init = client_type.__init__

    def init(instance, *args, **kwargs):
        assert kwargs["playwright_page"] is None and kwargs["proxy"] is None
        original_init(instance, *args, **kwargs)
        clients.append(instance)

    monkeypatch.setattr(client_type, "__init__", init)

    def respond(incoming: httpx.Request) -> httpx.Response:
        seen.append(incoming)
        assert incoming.method == "POST" and str(incoming.url) == module._ENDPOINT
        assert incoming.headers["host"] == "www.kuaishou.com"
        assert incoming.headers["origin"] == module._ORIGIN
        assert incoming.headers["referer"] == module._ORIGIN + "/"
        assert incoming.headers["accept-encoding"] == "identity"
        assert incoming.headers["content-type"] == "application/json"
        assert incoming.content == module._encode_body(incoming.headers["Cookie"]).encode()
        payload = settings["raw"]
        if payload is None:
            payload = json.dumps(settings["body"]).encode()
        return httpx.Response(
            settings["status"],
            stream=httpx.ByteStream(payload),
            headers={
                "content-type": settings["content_type"],
                "content-encoding": settings["encoding"],
                "location": "http://127.0.0.1/PRIVATE",
            },
        )

    def pinned(target):
        targets.append(target)
        return httpx.MockTransport(respond)

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: [settings["dns"]])
    monkeypatch.setattr(network, "PinnedHTTPTransport", pinned)
    return SimpleNamespace(
        client_type=client_type,
        client_module=client_module,
        config=offline["config"],
        settings=settings,
        seen=seen,
        targets=targets,
        clients=clients,
    )


@pytest.mark.parametrize(
    "candidate",
    [
        COOKIE,
        'kuaishou.web.cp.api_ph="quoted=="; arbitrary=exact',
        "kuaishou.web.cp.api_ph=%20encoded==; kuaishou.web.api_ph=NOT_USED",
    ],
)
async def test_real_locked_post_and_constructor_use_exact_cookie_one_fixed_self_query(
    checkout: Path,
    kuaishou: SimpleNamespace,
    candidate: str,
) -> None:
    assert await module.verify_kuaishou_cookie(checkout, request(candidate), time.monotonic() + 5) is None
    assert len(kuaishou.seen) == len(kuaishou.targets) == len(kuaishou.clients) == 1
    incoming = kuaishou.seen[0]
    assert incoming.headers["cookie"] == candidate
    body = json.loads(incoming.content)
    assert body == module._body(candidate) and body["variables"] == {}
    assert kuaishou.clients[0].request.__func__ is kuaishou.client_type.request
    assert kuaishou.config.COOKIES == "" and kuaishou.config.ENABLE_IP_PROXY is False
    assert kuaishou.config.STATIC_PROXY_URL == "" and kuaishou.config.PLATFORM == "ks"
    assert not any(key.endswith((".core", ".login")) for key in sys.modules if key.startswith("media_platform."))


@pytest.mark.parametrize(
    "candidate",
    ["session=present", "kuaishou.web.api_ph=NOT_THE_CP_KEY", "kuaishou.web.cp.api_ph=", 'kuaishou.web.cp.api_ph=""'],
)
async def test_cp_cookie_missing_fails_before_import_constructor_or_network(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
    candidate: str,
) -> None:
    def forbidden(*args, **kwargs):
        pytest.fail("missing CP Cookie must fail before importing upstream or requesting")

    monkeypatch.setattr(module.importlib, "import_module", forbidden)
    monkeypatch.setattr(module, "_fetch", forbidden)
    with pytest.raises(runner._VerificationFailure, match=r"^result_invalid$"):
        await module.verify_kuaishou_cookie(checkout, request(candidate), time.monotonic() + 5)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_user",
        "public_profile",
        "string_uid",
        "bool_uid",
        "zero_uid",
        "guest",
        "login_false",
        "unknown_errors",
        "error_zero",
        "blank_name",
    ],
)
async def test_http_200_does_not_authorize_ambiguous_or_target_identity(
    checkout: Path,
    kuaishou: SimpleNamespace,
    mutation: str,
) -> None:
    raw = kuaishou.settings["body"]
    user = raw["data"]["userInfo"]
    if mutation == "missing_user":
        raw["data"]["userInfo"] = None
    elif mutation == "public_profile":
        raw["data"] = {"visionProfile": user}
    elif mutation == "string_uid":
        user["userId"] = "123456"
    elif mutation == "bool_uid":
        user["userId"] = True
    elif mutation == "zero_uid":
        user["userId"] = 0
    elif mutation == "guest":
        user["isGuest"] = True
    elif mutation == "login_false":
        raw["isLogin"] = False
    elif mutation == "unknown_errors":
        raw["errors"] = [{"message": "PRIVATE", "code": 123}]
    elif mutation == "error_zero":
        user["errorCode"] = 0
    else:
        user["name"] = " "
    with pytest.raises(runner._VerificationFailure, match=r"^result_invalid$"):
        await module.verify_kuaishou_cookie(checkout, request(), time.monotonic() + 5)
    assert len(kuaishou.seen) == 1 and kuaishou.config.COOKIES == ""
    assert kuaishou.clients[0].request.__func__ is kuaishou.client_type.request


@pytest.mark.parametrize(
    "failure,status",
    [
        ("unauthorized", "rejected"),
        ("redirect", "result_invalid"),
        ("forbidden", "result_invalid"),
        ("duplicate", "result_invalid"),
        ("oversize", "result_invalid"),
        ("compressed", "result_invalid"),
        ("private_dns", "result_invalid"),
        ("html", "result_invalid"),
    ],
)
async def test_full_locked_post_transport_fails_closed_without_retry_or_redirect(
    checkout: Path,
    kuaishou: SimpleNamespace,
    failure: str,
    status: str,
) -> None:
    if failure in {"unauthorized", "redirect", "forbidden"}:
        kuaishou.settings["status"] = {"unauthorized": 401, "redirect": 302, "forbidden": 403}[failure]
    elif failure == "duplicate":
        kuaishou.settings["raw"] = b'{"data":{},"data":{"userInfo":{"userId":123,"name":"PRIVATE"}}}'
    elif failure == "oversize":
        kuaishou.settings["raw"] = b"x" * (module.MAX_API_BYTES + 1)
    elif failure == "compressed":
        kuaishou.settings["encoding"] = "gzip"
    elif failure == "private_dns":
        kuaishou.settings["dns"] = "127.0.0.1"
    else:
        kuaishou.settings["content_type"] = "text/html"
    with pytest.raises(runner._VerificationFailure, match=f"^{status}$"):
        await module.verify_kuaishou_cookie(checkout, request(), time.monotonic() + 5)
    assert len(kuaishou.seen) == len(kuaishou.targets) == int(failure != "private_dns")
    assert kuaishou.config.COOKIES == ""


@pytest.mark.parametrize(
    "mutation",
    [
        "zero",
        "twice",
        "target_uri",
        "host",
        "query",
        "variables",
        "cp_secret",
        "cookie",
        "headers",
        "wrong_method",
        "extra_kwargs",
        "substitute",
        "mutate",
        "cancel",
    ],
)
async def test_real_post_contract_drift_cannot_expand_authority_or_detach_validated_result(
    checkout: Path,
    kuaishou: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    original_post = kuaishou.client_type.post

    async def changed(instance, uri, data):
        if mutation == "zero":
            return evidence()["data"]
        if mutation == "target_uri":
            uri = "?userId=123456"
        elif mutation == "host":
            instance._host = "https://unknown.example/graphql"
        elif mutation == "query":
            data["query"] += " query target($id: String!) { user(id: $id) { userId } }"
        elif mutation == "variables":
            data["variables"] = {"userId": 123456}
        elif mutation == "cp_secret":
            data[module._CP_COOKIE] = "SUBSTITUTED"
        elif mutation == "cookie":
            instance.headers["Cookie"] = COOKIE.replace("PRIVATE_CP", "SUBSTITUTED")
        elif mutation == "headers":
            instance.headers["Authorization"] = "PRIVATE"
        elif mutation in {"wrong_method", "extra_kwargs"}:
            kwargs = {"headers": instance.headers, "data": module._encode_body(COOKIE)}
            if mutation == "extra_kwargs":
                kwargs["proxy"] = "http://127.0.0.1:1"
            return await instance.request(
                "GET" if mutation == "wrong_method" else "POST",
                module._ENDPOINT,
                **kwargs,
            )
        result = await original_post(instance, uri, data)
        if mutation == "twice":
            await original_post(instance, uri, data)
        elif mutation == "substitute":
            return json.loads(json.dumps(result))
        elif mutation == "mutate":
            result["userInfo"]["userId"] = 234567
        elif mutation == "cancel":
            raise asyncio.CancelledError
        return result

    monkeypatch.setattr(kuaishou.client_type, "post", changed)
    with pytest.raises(asyncio.CancelledError if mutation == "cancel" else runner._VerificationFailure):
        await module.verify_kuaishou_cookie(checkout, request(), time.monotonic() + 5)
    assert len(kuaishou.seen) == int(mutation in {"twice", "substitute", "mutate", "cancel"})
    assert kuaishou.config.COOKIES == ""
    assert kuaishou.clients[0].request.__func__ is kuaishou.client_type.request


@pytest.mark.parametrize(
    "failure", ["config_path", "client_path", "utils_path", "class_origin", "preloaded", "platform", "deadline"]
)
async def test_wrong_origin_configuration_and_deadline_fail_before_request(
    checkout: Path,
    kuaishou: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    if failure == "config_path":
        kuaishou.config.__file__ = str(checkout / "other/config.py")
    elif failure == "client_path":
        kuaishou.client_module.__file__ = str(checkout / "other/client.py")
    elif failure == "utils_path":
        monkeypatch.setattr(sys.modules["tools.utils"], "__file__", str(checkout / "other/utils.py"))
    elif failure == "class_origin":
        monkeypatch.setattr(kuaishou.client_type, "__module__", "unknown")
    elif failure == "preloaded":
        monkeypatch.setitem(sys.modules, "media_platform.kuaishou.client", kuaishou.client_module)
    incoming = request(platform=Platform.BILI if failure == "platform" else Platform.KS)
    expected = (
        "result_invalid" if failure == "platform" else "timed_out" if failure == "deadline" else "configuration_invalid"
    )
    with pytest.raises(runner._VerificationFailure, match=f"^{expected}$"):
        await module.verify_kuaishou_cookie(checkout, incoming, time.monotonic() + (-1 if failure == "deadline" else 5))
    assert not kuaishou.seen


async def test_deadline_after_verified_response_cannot_authenticate(
    kuaishou: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = kuaishou.client_type(headers=headers(), playwright_page=None, cookie_dict={}, proxy=None)
    original_request = client.request
    monkeypatch.setattr(module, "_fetch", lambda *args: evidence())
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: 10.0))
    with pytest.raises(runner._VerificationFailure, match=r"^timed_out$"):
        await module.query_kuaishou_cookie_client(client, COOKIE, 5.0)
    assert client.request == original_request


@pytest.mark.parametrize("case", ["authenticated", "rejected", "result_invalid", "prerequisite"])
def test_private_worker_only_emits_bound_status_after_real_locked_post(
    checkout: Path,
    kuaishou: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    incoming = request("session=PRIVATE" if case == "prerequisite" else COOKIE)
    if case == "rejected":
        kuaishou.settings["status"] = 401
    elif case == "result_invalid":
        kuaishou.settings["body"]["data"]["userInfo"]["userId"] = True
    envelope = {
        "schema_version": runner.SCHEMA_VERSION,
        "request": runner._request_payload(incoming),
        "deadline": time.monotonic() + 5,
        "checkout_root": str(checkout),
        "upstream_sha": "d6f7c5bb906b6dac40ddf343ef9e26438a3de092",
    }
    frames = []
    monkeypatch.setattr(runner, "_read_control_frame", lambda: json.dumps(envelope).encode())
    monkeypatch.setattr(runner, "_emit", frames.append)
    assert runner._worker_entry() == 0
    assert len(frames) == 1
    result = runner._parse_result(frames[0][4:], incoming)
    assert result.platform is Platform.KS and result.status == ("result_invalid" if case == "prerequisite" else case)
    assert len(kuaishou.seen) == int(case != "prerequisite")
    assert "PRIVATE" not in repr(frames) and "123456" not in repr(frames) and "userInfo" not in repr(frames)
