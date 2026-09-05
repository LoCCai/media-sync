"""Closed single-request Douyin profile fence and strict response subset."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode

import httpx
import pytest

from media_sync.integrations.mediacrawler import douyin_creator_profile as module
from media_sync.media.errors import MediaDownloadError

UID = "MS4wLjABAAAA_test-ExactSecUid"
HEADERS = {
    "User-Agent": "offline-agent",
    "Cookie": 'session=PRIVATE==; marker="quoted=="',
    "Host": "www.douyin.com",
    "Origin": module._ORIGIN + "/",
    "Referer": module._ORIGIN + "/",
    "Content-Type": "application/json;charset=UTF-8",
}


def response() -> dict[str, Any]:
    return {
        "status_code": 0,
        "user": {
            "sec_uid": UID,
            "nickname": "准确昵称",
            "avatar_larger": {"url_list": ["http://127.0.0.1/private-avatar"]},
            "signature": "incidental private content",
        },
    }


class Client:
    def __init__(self) -> None:
        self.headers = dict(HEADERS)
        self.playwright_page = object()
        self.params = {"sec_user_id": UID, **module._COMMON, "webid": "1234567890123456789", "msToken": None}
        self.url, self.method = module._ENDPOINT, "GET"
        self.extra: dict[str, Any] = {}
        self.skip_sign = self.repeat = False
        self.after_sign: dict[str, Any] = {}
        self.signing = SimpleNamespace(get_a_bogus=self.sign)

    async def sign(self, uri, query, post, agent, page):
        return "actual-synthetic-signature="

    async def request(self, *args, **kwargs):
        pytest.fail("original HTTP must be replaced")

    async def get_user_info(self, remote_id):
        query = urlencode(self.params)
        self.params["a_bogus"] = (
            "injected"
            if self.skip_sign
            else await self.signing.get_a_bogus(
                module._PATH, query, {}, self.headers["User-Agent"], self.playwright_page
            )
        )
        self.params.update(self.after_sign)
        value = await self.request(self.method, self.url, params=self.params, headers=self.headers, **self.extra)
        if self.repeat:
            await self.request(self.method, self.url, params=self.params, headers=self.headers)
        return value


async def query(client=None, *, deadline=None):
    client = client or Client()
    return await module._query_douyin_client(
        client, UID, deadline or time.monotonic() + 5, signing_module=client.signing
    )


@pytest.fixture
def intercepted(monkeypatch):
    raw, seen = response(), []

    def fetch(query, headers, deadline):
        seen.append((query, dict(headers)))
        return raw

    monkeypatch.setattr(module, "_fetch_profile_json", fetch)
    return raw, seen


async def test_exact_profile_raw_nickname_only_and_signature_query(intercepted):
    _, seen = intercepted
    client = Client()
    original_request, original_sign = client.request, client.signing.get_a_bogus
    result = await query(client)
    assert (result.remote_id, result.display_name, result.avatar_url) == (UID, "准确昵称", None)
    assert "准确昵称" not in repr(result) and "private" not in repr(result)
    assert len(seen) == 1 and seen[0][1] == HEADERS
    assert "msToken=None&" in seen[0][0] and seen[0][0].endswith("&a_bogus=actual-synthetic-signature%3D")
    assert client.request == original_request and client.signing.get_a_bogus == original_sign


@pytest.mark.parametrize("identity", [None, 123, True, "", UID.lower(), UID + " ", "other", [UID]])
async def test_response_identity_must_be_present_exact_string(intercepted, identity):
    raw, _ = intercepted
    raw["user"]["sec_uid"] = identity
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query()


@pytest.mark.parametrize("name", [None, "", "  ", 123, True, "x" * 513, "bad\nname", "bad\ud800name"])
async def test_nickname_is_not_coerced_or_filled_from_request(intercepted, name):
    raw, _ = intercepted
    raw["user"]["nickname"] = name
    with pytest.raises(ValueError, match="result_invalid"):
        await query()


@pytest.mark.parametrize("status", [None, "0", True, False, 1, -1, 0.0])
async def test_integer_zero_is_explicit_conservative_response_subset(intercepted, status):
    raw, _ = intercepted
    raw["status_code"] = status
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query()


@pytest.mark.parametrize(
    "key,value",
    [
        ("sec_user_id", "other"),
        ("aid", "999"),
        ("personal_center_strategy", True),
        ("webid", "1"),
        ("webid", 1234567890123456789),
        ("msToken", "\nPRIVATE"),
        ("msToken", "x" * 2049),
        ("msToken", {}),
        ("next", "1"),
    ],
)
async def test_fixed_parameter_fence_before_transport(intercepted, key, value):
    _, seen = intercepted
    client = Client()
    client.params[key] = value
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query(client)
    assert seen == []


@pytest.mark.parametrize("mutation", ["url", "method", "extra", "skip-sign", "changed-signature", "changed-query"])
async def test_request_and_real_signing_transcript_cannot_be_substituted(intercepted, mutation):
    _, seen = intercepted
    client = Client()
    if mutation == "url":
        client.url += "?next=1"
    elif mutation == "method":
        client.method = "POST"
    elif mutation == "extra":
        client.extra = {"follow_redirects": True}
    elif mutation == "skip-sign":
        client.skip_sign = True
    else:
        client.after_sign = {"a_bogus": "different"} if mutation == "changed-signature" else {"msToken": "changed"}
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query(client)
    assert seen == []


async def test_single_request_budget_and_restore_on_failure(intercepted):
    _, seen = intercepted
    client = Client()
    original_request, original_sign = client.request, client.signing.get_a_bogus
    client.repeat = True
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query(client)
    assert len(seen) == 1
    assert client.request == original_request and client.signing.get_a_bogus == original_sign


async def test_no_request_cannot_return_injected_profile(intercepted):
    _, seen = intercepted
    client = Client()

    async def fake(remote_id):
        return response()

    client.get_user_info = fake
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query(client)
    assert seen == []


@pytest.mark.parametrize("value", [None, [], "private", {"uid": UID, "nickname": "name"}])
async def test_missing_user_envelope_or_other_identity_never_falls_back(intercepted, value):
    raw, _ = intercepted
    raw["user"] = value
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query()


async def test_returned_profile_must_be_same_actual_response_object(intercepted):
    _, seen = intercepted

    class SubstitutedClient(Client):
        async def get_user_info(self, remote_id):
            await super().get_user_info(remote_id)
            return response()

    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query(SubstitutedClient())
    assert len(seen) == 1


async def test_header_cookie_cannot_change_after_binding(intercepted):
    _, seen = intercepted

    class ChangedCookieClient(Client):
        async def get_user_info(self, remote_id):
            self.headers["Cookie"] = "session=DIFFERENT_PRIVATE"
            return await super().get_user_info(remote_id)

    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query(ChangedCookieClient())
    assert seen == []


@pytest.mark.parametrize("signature", [None, 1, "", "x" * 2049, "bad\nPRIVATE"])
async def test_bad_signer_result_never_reaches_http(intercepted, signature):
    _, seen = intercepted
    client = Client()

    async def sign(*args):
        return signature

    client.signing.get_a_bogus = sign
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query(client)
    assert seen == []


async def test_repeated_signature_is_rejected_before_second_call(intercepted):
    _, seen = intercepted

    class RepeatedSigningClient(Client):
        async def get_user_info(self, remote_id):
            await self.signing.get_a_bogus(
                module._PATH, urlencode(self.params), {}, self.headers["User-Agent"], self.playwright_page
            )
            return await super().get_user_info(remote_id)

    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query(RepeatedSigningClient())
    assert seen == []


@pytest.mark.parametrize("invalid", ["", "a" * 256, "中文", "a.b", "a/b", "a%2Fb", "a\n", 1, True])
def test_exact_input_safety_subset(invalid):
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        module._identity(invalid)
    assert module._identity("a" * 255) == "a" * 255


@pytest.mark.parametrize(
    "kind", ["redirect", "401", "compressed", "type", "size", "duplicate", "nonfinite", "malformed", "unicode"]
)
async def test_transport_is_bounded_and_never_classifies_target_as_self(monkeypatch, kind):
    import media_sync.media.network as network

    seen = []

    def transport(request):
        seen.append(request)
        if kind == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        if kind == "401":
            return httpx.Response(401)
        body, headers = json.dumps(response()).encode(), {"Content-Type": "application/json"}
        if kind == "compressed":
            headers["Content-Encoding"] = "gzip"
        elif kind == "type":
            headers["Content-Type"] = "text/html"
        else:
            body = {
                "size": b"x" * (module.MAX_PROFILE_API_BYTES + 1),
                "duplicate": b'{"user":{},"user":{}}',
                "nonfinite": b'{"status_code":NaN}',
                "malformed": b"invalid",
                "unicode": b'{"user":"\xff"}',
            }.get(kind, body)
        return httpx.Response(200, headers=headers, stream=httpx.ByteStream(body))

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))
    with pytest.raises((module._LookupFailure, ValueError)) as caught:
        await query()
    assert "auth_expired" not in str(caught.value) and "PRIVATE" not in str(caught.value)
    assert len(seen) == 1


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["192.168.1.1"], ["8.8.8.8", "127.0.0.1"]])
async def test_private_or_mixed_dns_never_reaches_http(monkeypatch, addresses):
    import media_sync.media.network as network

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: addresses)
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda *args: pytest.fail("private DNS reached HTTP"))
    with pytest.raises(MediaDownloadError):
        await query()


async def test_expired_budget_stops_before_real_signing(intercepted):
    _, seen = intercepted
    client = Client()

    async def forbidden(*args):
        pytest.fail("late signature")

    client.signing.get_a_bogus = forbidden
    with pytest.raises(module._LookupFailure, match="timed_out"):
        await query(client, deadline=time.monotonic() - 1)
    assert seen == []


@pytest.mark.parametrize(
    "key,value",
    [
        ("Host", "localhost"),
        ("Origin", module._ORIGIN),
        ("Referer", module._ORIGIN + "/feed"),
        ("Cookie", "x\r\ny"),
        ("Authorization", "secret"),
        ("Content-Type", "text/plain"),
    ],
)
def test_transport_header_boundary_before_dns(monkeypatch, key, value):
    import media_sync.media.network as network

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: pytest.fail("invalid headers DNS"))
    headers = dict(HEADERS)
    headers[key] = value
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        module._fetch_profile_json("x=1", headers, time.monotonic() + 5)


@pytest.mark.parametrize("declared", ["-1", "1.5", "1, 2", "9" * 100])
def test_invalid_declared_length_is_bounded_before_integer_conversion(monkeypatch, declared):
    import media_sync.media.network as network

    def transport(request):
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json", "Content-Length": declared},
            stream=httpx.ByteStream(b"private-never-parsed"),
        )

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        module._fetch_profile_json("x=1", HEADERS, time.monotonic() + 5)


def test_no_content_length_cannot_bypass_stream_limit(monkeypatch):
    import media_sync.media.network as network

    class OversizedStream(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(module.MAX_PROFILE_API_BYTES // 8192 + 1):
                yield b"x" * 8192

    def transport(request):
        return httpx.Response(200, headers={"Content-Type": "application/json"}, stream=OversizedStream())

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        module._fetch_profile_json("x=1", HEADERS, time.monotonic() + 5)
