"""Real locked Tieba get/constructor, original synthetic HTTP-only self responses."""

from __future__ import annotations

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
from media_sync.media.errors import MediaDownloadError
from tests.contract.test_cookie_login_upstream import checkout as checkout
from tests.contract.test_cookie_login_upstream import load, stub
from tests.contract.test_cookie_login_upstream import offline as offline
from tests.unit.test_tieba_cookie_login import COOKIE, PORTRAIT, evidence, request

URL = "https://tieba.baidu.com/mo/q/newmoindex?need_user=1"
SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"


@pytest.fixture
def tieba(checkout: Path, offline: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    import media_sync.media.network as network

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
    module = sys.modules["media_platform.tieba.client"]
    client_type = module.BaiduTieBaClient
    for method_name, method in vars(client_type).items():
        if inspect.iscoroutinefunction(method) and method_name != "get":
            monkeypatch.setattr(client_type, method_name, offline["forbidden"])
    monkeypatch.setattr(client_type, "_sync_request", offline["forbidden"])
    prepared = {"config": offline["config"], module.__name__: module}
    original_import = importlib.import_module
    for name in prepared:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(
        runner.importlib, "import_module", lambda name, *args: prepared.get(name) or original_import(name, *args)
    )
    monkeypatch.chdir(checkout)
    monkeypatch.syspath_prepend(str(checkout))
    settings = {
        "body": evidence(),
        "http_status": 200,
        "raw": None,
        "content_type": "application/json",
        "dns": "8.8.8.8",
    }
    seen: list[httpx.Request] = []
    targets = []

    def respond(incoming: httpx.Request) -> httpx.Response:
        seen.append(incoming)
        assert incoming.method == "GET" and str(incoming.url) == URL
        assert incoming.headers["host"] == "tieba.baidu.com"
        assert incoming.headers["origin"] == "https://tieba.baidu.com"
        assert incoming.headers["referer"] == "https://tieba.baidu.com/"
        assert incoming.headers["user-agent"] == "offline-desktop"
        assert incoming.headers["accept-encoding"] == "identity"
        body = settings["raw"]
        if body is None:
            body = json.dumps(settings["body"]).encode()
        return httpx.Response(
            settings["http_status"],
            stream=httpx.ByteStream(body),
            headers={"content-type": settings["content_type"], "Location": "http://127.0.0.1/private"},
        )

    def pinned(target):
        targets.append(target)
        return httpx.MockTransport(respond)

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: [settings["dns"]])
    monkeypatch.setattr(network, "PinnedHTTPTransport", pinned)
    return SimpleNamespace(
        client_type=client_type, settings=settings, seen=seen, targets=targets, config=offline["config"]
    )


@pytest.mark.parametrize(
    "candidate", [COOKIE, "BDUSS=short-but-remotely-checked", 'BDUSS="quoted=="; arbitrary=byte-preserved']
)
async def test_real_locked_get_and_pinned_http_use_exact_candidate_and_one_self_query(
    checkout: Path,
    tieba: SimpleNamespace,
    candidate: str,
) -> None:
    incoming = request(candidate)
    await runner._verify_remote(checkout, incoming, time.monotonic() + 5)
    assert len(tieba.seen) == len(tieba.targets) == 1
    assert tieba.seen[0].headers["cookie"] == candidate
    assert tieba.config.ENABLE_IP_PROXY is False and tieba.config.COOKIES == ""
    assert not any(key.endswith((".core", ".login")) for key in sys.modules if key.startswith("media_platform."))


@pytest.mark.parametrize(
    "failure",
    [
        "missing_no",
        "string_no",
        "nonzero_no",
        "guest",
        "missing_id",
        "bool_id",
        "string_id",
        "public_profile",
        "portrait",
        "body_error",
    ],
)
async def test_successful_http_cannot_authorize_missing_or_ambiguous_self_evidence(
    checkout: Path,
    tieba: SimpleNamespace,
    failure: str,
) -> None:
    raw = tieba.settings["body"]
    if failure == "missing_no":
        raw.pop("no")
    elif failure == "string_no":
        raw["no"] = "0"
    elif failure == "nonzero_no":
        raw["no"] = 220021
    elif failure == "guest":
        raw["data"]["is_guest"] = True
    elif failure == "missing_id":
        raw["data"].pop("id")
    elif failure == "bool_id":
        raw["data"]["id"] = True
    elif failure == "string_id":
        raw["data"]["id"] = "123456789"
    elif failure == "public_profile":
        raw["data"] = {"user": raw["data"], "STOKEN": "present"}
    elif failure == "portrait":
        raw["data"]["portrait"] = "https://example.invalid/avatar.jpg"
    else:
        raw["error"] = "PRIVATE_CANDIDATE and remote diagnostic"
    with pytest.raises(runner._VerificationFailure, match=r"^result_invalid$"):
        await runner._verify_remote(checkout, request(), time.monotonic() + 5)
    assert len(tieba.seen) == 1


@pytest.mark.parametrize(
    "failure,status",
    [
        ("unauthorized", "rejected"),
        ("redirect", "result_invalid"),
        ("forbidden", "result_invalid"),
        ("html", "result_invalid"),
        ("duplicate", None),
        ("oversize", "result_invalid"),
        ("list", None),
    ],
)
async def test_http_failures_are_bounded_and_never_retried_or_redirected(
    checkout: Path,
    tieba: SimpleNamespace,
    failure: str,
    status: str | None,
) -> None:
    if failure in {"unauthorized", "redirect", "forbidden"}:
        tieba.settings["http_status"] = {"unauthorized": 401, "redirect": 302, "forbidden": 403}[failure]
    elif failure == "html":
        tieba.settings.update(content_type="text/html", raw=b"<html>PRIVATE_ERROR</html>")
    elif failure == "duplicate":
        tieba.settings["raw"] = b'{"no":1,"no":0,"data":{}}'
    elif failure == "oversize":
        tieba.settings["raw"] = b"x" * (runner.MAX_API_BYTES + 1)
    else:
        tieba.settings["raw"] = b"[]"
    with pytest.raises((runner._VerificationFailure, ValueError)) as error:
        await runner._verify_remote(checkout, request(), time.monotonic() + 5)
    if status is not None:
        assert error.value.status == status
    assert len(tieba.seen) == 1 and "PRIVATE" not in str(error.value)


@pytest.mark.parametrize(
    "mutation", ["twice", "zero", "public_profile", "no_query", "extra_query", "host", "cookie", "raw_content", "proxy"]
)
async def test_locked_get_dispatch_drift_cannot_expand_authority_or_substitute_cookie(
    checkout: Path,
    tieba: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    original_get = tieba.client_type.get

    async def changed(instance, uri, params=None, **kwargs):
        if mutation == "zero":
            return evidence()
        if mutation == "public_profile":
            uri, params = "/home/get/panel", {"un": PORTRAIT}
        elif mutation == "no_query":
            params = None
        elif mutation == "extra_query":
            params = params | {"user_id": 123456789}
        elif mutation == "host":
            instance._host = "https://tieba.baidu.com.evil.invalid"
        elif mutation == "cookie":
            kwargs["headers"] = kwargs["headers"] | {"Cookie": "BDUSS=SUBSTITUTED"}
        elif mutation == "raw_content":
            kwargs["return_ori_content"] = True
        elif mutation == "proxy":
            kwargs["proxy"] = "http://127.0.0.1:1234"
        response = await original_get(instance, uri, params, **kwargs)
        if mutation == "twice":
            await original_get(instance, uri, params, **kwargs)
        return response

    monkeypatch.setattr(tieba.client_type, "get", changed)
    with pytest.raises(runner._VerificationFailure, match=r"^result_invalid$"):
        await runner._verify_remote(checkout, request(), time.monotonic() + 5)
    assert len(tieba.seen) == (1 if mutation == "twice" else 0)


async def test_private_resolved_address_never_receives_candidate(checkout: Path, tieba: SimpleNamespace) -> None:
    tieba.settings["dns"] = "127.0.0.1"
    with pytest.raises(MediaDownloadError):
        await runner._verify_remote(checkout, request(), time.monotonic() + 5)
    assert not tieba.seen and not tieba.targets


@pytest.mark.parametrize("accepted", [True, False])
def test_worker_frame_only_reports_bound_status_after_real_locked_self_check(
    checkout: Path,
    tieba: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    accepted: bool,
) -> None:
    incoming = request()
    if not accepted:
        tieba.settings["body"]["no"] = 220021
    envelope = {
        "schema_version": runner.SCHEMA_VERSION,
        "request": runner._request_payload(incoming),
        "deadline": time.monotonic() + 5,
        "checkout_root": str(checkout),
        "upstream_sha": SHA,
    }
    frames = []
    monkeypatch.setattr(runner, "_read_control_frame", lambda: json.dumps(envelope).encode())
    monkeypatch.setattr(runner, "_emit", frames.append)
    assert runner._worker_entry() == 0
    assert len(frames) == 1
    result = runner._parse_result(frames[0][4:], incoming)
    assert result.platform is Platform.TIEBA and result.status == ("authenticated" if accepted else "result_invalid")
    assert len(tieba.seen) == 1
    assert "PRIVATE" not in repr(frames) and PORTRAIT not in repr(frames)
