"""Closed KS author-profile request/identity contract, independent of login."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest

from media_sync.integrations.mediacrawler import kuaishou_creator_profile as module
from media_sync.media.errors import MediaDownloadError

UID = "3x4jtnbfter525a"
QUERY = "query visionProfile($userId: String) { visionProfile(userId: $userId) { result } }"
HEADERS = {
    "User-Agent": "offline",
    "Cookie": "session=PRIVATE==",
    "Origin": module._ORIGIN,
    "Referer": module._ORIGIN + "/",
    "Content-Type": "application/json;charset=UTF-8",
}


def response() -> dict[str, Any]:
    return {
        "data": {
            "visionProfile": {
                "result": 1,
                "userProfile": {
                    "profile": {"user_id": UID, "user_name": "准确昵称", "headurl": "http://127.0.0.1/private"},
                    "ignored": "incidental private content",
                },
            }
        }
    }


class Client:
    def __init__(self) -> None:
        self.headers = dict(HEADERS)
        self.url = module._ENDPOINT
        self.method = "POST"
        self.operation = "visionProfile"
        self.variables = {"userId": UID}
        self.query = QUERY
        self.extra: dict[str, Any] = {}

    async def get_creator_profile(self, remote_id: str):
        return await self.request(
            self.method,
            self.url,
            headers=self.headers,
            data=json.dumps(
                {"operationName": self.operation, "variables": self.variables, "query": self.query},
                separators=(",", ":"),
                ensure_ascii=False,
            ),
            **self.extra,
        )


async def query(client: Client):
    return await module._query_kuaishou_client(client, UID, time.monotonic() + 5, expected_query=QUERY)


@pytest.fixture
def intercepted(monkeypatch: pytest.MonkeyPatch):
    raw = response()
    seen = []

    def fetch(body, headers, deadline):
        seen.append((body, dict(headers)))
        return raw

    monkeypatch.setattr(module, "_fetch_profile_json", fetch)
    return raw, seen


async def test_exact_profile_ignores_unqualified_avatar_and_incidental_fields(intercepted):
    _raw, seen = intercepted
    client = Client()
    result = await query(client)
    assert result.remote_id == UID and result.display_name == "准确昵称" and result.avatar_url is None
    assert "准确昵称" not in repr(result) and "private" not in repr(result)
    assert len(seen) == 1 and seen[0][1] == HEADERS
    with pytest.raises(module._LookupFailure):
        await client.get_creator_profile(UID)
    assert len(seen) == 1


@pytest.mark.parametrize("identity", [None, 123, True, "", UID.upper(), UID + " ", "3xDifferent"])
async def test_missing_wrong_or_coerced_profile_identity_is_rejected(intercepted, identity):
    raw, seen = intercepted
    raw["data"]["visionProfile"]["userProfile"]["profile"]["user_id"] = identity
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query(Client())
    assert len(seen) == 1


@pytest.mark.parametrize("name", [None, "", "  ", 123, "x" * 513, "name\nprivate"])
async def test_bad_nickname_never_falls_back_to_input_or_masked_name(intercepted, name):
    raw, _seen = intercepted
    raw["data"]["visionProfile"]["userProfile"]["profile"]["user_name"] = name
    with pytest.raises(ValueError):
        await query(Client())


@pytest.mark.parametrize("mutation", ["errors", "data", "wrapper", "alias", "profile", "bool", "zero"])
async def test_incomplete_or_ambiguous_graphql_response_fails_closed(intercepted, mutation):
    raw, _seen = intercepted
    if mutation == "errors":
        raw["errors"] = [{"message": "private server body"}]
    elif mutation == "data":
        raw["data"] = []
    elif mutation == "wrapper":
        raw["data"] = raw["data"]["visionProfile"]
    elif mutation == "alias":
        raw["data"]["other"] = {}
    elif mutation == "profile":
        del raw["data"]["visionProfile"]["userProfile"]["profile"]
    else:
        raw["data"]["visionProfile"]["result"] = True if mutation == "bool" else 0
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query(Client())


@pytest.mark.parametrize("mutation", ["url", "method", "query", "variables", "operation", "extra"])
async def test_exact_request_fence_blocks_scope_expansion_before_transport(intercepted, mutation):
    _raw, seen = intercepted
    client = Client()
    setattr(
        client,
        mutation,
        {
            "url": "https://www.kuaishou.com/graphql?next=1",
            "method": "GET",
            "query": QUERY + " mutation",
            "variables": {"userId": UID, "pcursor": "next"},
            "operation": "visionProfileUserList",
            "extra": {"follow_redirects": True},
        }[mutation],
    )
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query(client)
    assert seen == []


@pytest.mark.parametrize("kind", ["redirect", "401", "compressed", "type", "size", "duplicate", "malformed"])
async def test_bounded_transport_does_not_redirect_retry_or_classify_self_auth(monkeypatch, kind):
    import media_sync.media.network as network

    seen = []

    def transport(request):
        seen.append(request)
        if kind == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        if kind == "401":
            return httpx.Response(401)
        body = json.dumps(response()).encode()
        headers = {"Content-Type": "application/json"}
        if kind == "compressed":
            headers["Content-Encoding"] = "gzip"
        elif kind == "type":
            headers["Content-Type"] = "text/html"
        elif kind == "size":
            body = b"x" * (module.MAX_PROFILE_API_BYTES + 1)
        elif kind == "duplicate":
            body = b'{"data":{},"data":{}}'
        elif kind == "malformed":
            body = b"invalid"
        return httpx.Response(200, headers=headers, stream=httpx.ByteStream(body))

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))
    with pytest.raises((module._LookupFailure, ValueError)) as error:
        await query(Client())
    assert "auth_expired" not in str(error.value)
    assert len(seen) == 1


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["192.168.1.1"], ["8.8.8.8", "127.0.0.1"]])
async def test_private_or_mixed_dns_never_opens_http(monkeypatch, addresses):
    import media_sync.media.network as network

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: addresses)
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda *args: pytest.fail("unsafe target reached HTTP"))
    with pytest.raises(MediaDownloadError):
        await query(Client())


async def test_elapsed_deadline_never_resolves_dns(monkeypatch):
    import media_sync.media.network as network

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: pytest.fail("late DNS"))
    with pytest.raises(module._LookupFailure, match="timed_out"):
        await module._query_kuaishou_client(Client(), UID, time.monotonic() - 1, expected_query=QUERY)


async def test_client_cannot_substitute_cookie_after_request_binding(intercepted):
    _raw, seen = intercepted

    class ChangedClient(Client):
        async def get_creator_profile(self, remote_id):
            self.headers["Cookie"] = "session=DIFFERENT"
            return await super().get_creator_profile(remote_id)

    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query(ChangedClient())
    assert seen == []


async def test_client_cannot_skip_real_request_and_return_injected_profile(intercepted):
    _raw, seen = intercepted

    class NoRequestClient(Client):
        async def get_creator_profile(self, remote_id):
            return response()["data"]

    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await query(NoRequestClient())
    assert seen == []


@pytest.mark.parametrize("invalid", ["extra", "origin", "referer", "type", "newline", "size"])
async def test_transport_header_boundary_rejects_expansion_before_dns(monkeypatch, invalid):
    import media_sync.media.network as network

    monkeypatch.setattr(
        network.SocketAddressResolver, "resolve", lambda *args: pytest.fail("invalid headers reached DNS")
    )
    headers = dict(HEADERS)
    key, value = {
        "extra": ("Authorization", "private"),
        "origin": ("Origin", "https://other.example"),
        "referer": ("Referer", module._ORIGIN + "/profile/other"),
        "type": ("Content-Type", "text/plain"),
        "newline": ("User-Agent", "agent\r\nCookie: private"),
        "size": ("Cookie", "x" * 65537),
    }[invalid]
    headers[key] = value
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        module._fetch_profile_json(b"{}", headers, time.monotonic() + 3)


@pytest.mark.parametrize("declared", ["-1", "1.5", "1, 2", "9" * 20])
def test_invalid_declared_response_size_is_rejected_without_parsing(monkeypatch, declared):
    import media_sync.media.network as network

    seen = []

    def transport(request):
        seen.append(request)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json", "Content-Length": declared},
            stream=httpx.ByteStream(b"private-body-never-parsed"),
        )

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        module._fetch_profile_json(b"{}", HEADERS, time.monotonic() + 3)
    assert len(seen) == 1


def test_body_without_content_length_remains_stream_bounded(monkeypatch):
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
        module._fetch_profile_json(b"{}", HEADERS, time.monotonic() + 3)
