"""Original Douyin self-protocol adapter over fully synthetic pinned HTTP.

This tests public-source protocol facts, not a nonexistent locked client self
method, a browser session, or a claim of live platform qualification.
"""

from __future__ import annotations

import builtins
import json
import subprocess
import time

import httpx
import pytest

from media_sync.integrations.mediacrawler import douyin_cookie_login as module
from media_sync.security.secrets import SecretValue
from tests.unit.test_douyin_cookie_login import response

COOKIE = 'sessionid=PRIVATE_NEW==;marker="quoted==" ; extra=a%2Fb===;'


@pytest.fixture
def no_browser_process_or_upstream(monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert not name.startswith(("playwright", "execjs", "media_platform")), (
            "self adapter has no browser/upstream path"
        )
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(
        subprocess, "Popen", lambda *args, **kwargs: pytest.fail("self adapter must not spawn a process")
    )


@pytest.mark.parametrize(
    "outcome,status",
    [
        ("success", None),
        ("401", "rejected"),
        ("403", "result_invalid"),
        ("redirect", "result_invalid"),
        ("unknown-code", "result_invalid"),
        ("guest", "result_invalid"),
        ("alternate", "result_invalid"),
        ("wrong-type", "result_invalid"),
        ("compressed", "result_invalid"),
        ("oversize", "result_invalid"),
        ("duplicate", "result_invalid"),
        ("nonfinite", "result_invalid"),
        ("malformed", "result_invalid"),
        ("bad-unicode", "result_invalid"),
        ("empty", "result_invalid"),
        ("transport-error", "verification_unavailable"),
        ("timeout", "timed_out"),
    ],
)
async def test_fixed_single_self_get_exact_private_cookie_and_no_fallback(
    monkeypatch, no_browser_process_or_upstream, tmp_path, capsys, outcome, status
):
    import media_sync.media.network as network

    requests, targets, client_options = [], [], []
    original_client = httpx.Client

    def client(**kwargs):
        client_options.append(kwargs)
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        assert 0 < kwargs["timeout"] <= 10
        assert "cookies" not in kwargs and "auth" not in kwargs and "proxy" not in kwargs
        return original_client(**kwargs)

    monkeypatch.setattr(module.httpx, "Client", client)

    def transport(request):
        requests.append(request)
        assert request.method == "GET" and str(request.url) == module._ENDPOINT
        assert request.url.query == b"" and request.content == b""
        assert request.headers["Cookie"] == COOKIE
        assert request.headers["Host"] == "creator.douyin.com"
        assert request.headers["Referer"] == "https://creator.douyin.com/creator-micro/home"
        assert request.headers["Accept"] == "application/json" and request.headers["Accept-Encoding"] == "identity"
        assert request.headers["User-Agent"] == module._USER_AGENT
        assert "Authorization" not in request.headers
        if outcome == "transport-error":
            raise httpx.ConnectError("PRIVATE_TRANSPORT_DIAGNOSTIC_" + COOKIE)
        if outcome == "timeout":
            raise httpx.ReadTimeout("PRIVATE_TIMEOUT_" + COOKIE)
        if outcome in {"401", "403"}:
            return httpx.Response(int(outcome), stream=httpx.ByteStream(b"PRIVATE_RESPONSE"))
        if outcome == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        raw = response()
        raw["user"].update({"avatar_larger": {"url_list": ["http://127.0.0.1/private"]}, "email": "PRIVATE_EMAIL"})
        if outcome == "unknown-code":
            raw["status_code"] = 99999
        elif outcome == "guest":
            raw["user"]["isGuest"] = True
        elif outcome == "alternate":
            raw["user_info"] = dict(raw["user"])
        payload = json.dumps(raw).encode()
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if outcome == "compressed":
            headers["Content-Encoding"] = "gzip"
        elif outcome == "wrong-type":
            headers["Content-Type"] = "text/html"
        elif outcome == "oversize":
            payload = b"x" * (module.MAX_API_BYTES + 1)
        elif outcome == "duplicate":
            payload = b'{"status_code":0,"user":{},"user":{}}'
        elif outcome == "nonfinite":
            payload = b'{"status_code":NaN}'
        elif outcome == "malformed":
            payload = b"PRIVATE_INVALID_JSON"
        elif outcome == "bad-unicode":
            payload = b'{"user":"\xff"}'
        elif outcome == "empty":
            payload = b""
        return httpx.Response(200, headers=headers, stream=httpx.ByteStream(payload))

    def pinned(target):
        targets.append(target)
        assert target.url == module._ENDPOINT
        return httpx.MockTransport(transport)

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", pinned)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    monkeypatch.chdir(tmp_path)
    if status is None:
        assert await module.verify_douyin_cookie(SecretValue(COOKIE), time.monotonic() + 5) is None
    else:
        with pytest.raises(module._VerificationFailure, match="^" + status + "$") as caught:
            await module.verify_douyin_cookie(SecretValue(COOKIE), time.monotonic() + 5)
        assert "PRIVATE" not in str(caught.value)
    assert len(requests) == len(targets) == len(client_options) == 1
    assert list(tmp_path.iterdir()) == []
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["192.168.31.1"], ["8.8.8.8", "127.0.0.1"], ["::1"]])
async def test_all_dns_answers_must_be_public_before_any_http(monkeypatch, addresses):
    import media_sync.media.network as network

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: addresses)
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda *args: pytest.fail("unsafe DNS reached HTTP"))
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        await module.verify_douyin_cookie(SecretValue(COOKIE), time.monotonic() + 5)


@pytest.mark.parametrize("value", [" ", "sessionid=a; sessionid=b", "sessionid=a\r\nother=b", '{"cookie":"x"}'])
async def test_malformed_candidate_never_reaches_dns(monkeypatch, value):
    import media_sync.media.network as network

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: pytest.fail("invalid candidate DNS"))
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        await module.verify_douyin_cookie(SecretValue(value), time.monotonic() + 5)


@pytest.mark.parametrize("declared", ["-1", "1.5", "1, 2", "9" * 100])
async def test_invalid_declared_size_is_not_parsed(monkeypatch, declared):
    import media_sync.media.network as network

    def transport(request):
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json", "Content-Length": declared},
            stream=httpx.ByteStream(b"PRIVATE_MALFORMED_BODY"),
        )

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        await module.verify_douyin_cookie(SecretValue(COOKIE), time.monotonic() + 5)


async def test_missing_content_length_still_has_a_stream_bound(monkeypatch):
    import media_sync.media.network as network

    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(module.MAX_API_BYTES // 8192 + 1):
                yield b"x" * 8192

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(
        network,
        "PinnedHTTPTransport",
        lambda target: httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"Content-Type": "application/json"}, stream=Stream())
        ),
    )
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        await module.verify_douyin_cookie(SecretValue(COOKIE), time.monotonic() + 5)


async def test_expiration_during_dns_prevents_request(monkeypatch):
    import media_sync.media.network as network

    deadline = time.monotonic() + 5

    def resolve(*args):
        monkeypatch.setattr(module.time, "monotonic", lambda: deadline + 1)
        return ["8.8.8.8"]

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", resolve)
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda *args: pytest.fail("late DNS result HTTP"))
    with pytest.raises(module._VerificationFailure, match=r"^timed_out$"):
        await module.verify_douyin_cookie(SecretValue(COOKIE), deadline)
