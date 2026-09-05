from __future__ import annotations

import io
import json
import time
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import creator_profile_runner as module
from media_sync.integrations.mediacrawler.creator_profile_runner import (
    MediaCrawlerCreatorProfile,
    MediaCrawlerCreatorProfileRequest,
    MediaCrawlerCreatorProfileResult,
    MediaCrawlerCreatorProfileStatus,
)
from media_sync.media.errors import MediaDownloadError

SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
REQUEST = MediaCrawlerCreatorProfileRequest(uuid4(), Platform.BILI, "123", uuid4())
PROFILE = MediaCrawlerCreatorProfile("123", "私密昵称", "https://i0.hdslb.com/bfs/face/avatar.jpg")


@pytest.mark.parametrize(
    "creator_id", ["0", "01", "-1", " 1", "\uff11\uff12\uff13", "1\n", "https://bili.test/123", str(2**64), True]
)
def test_request_rejects_noncanonical_bili_identity(creator_id: object) -> None:
    with pytest.raises(ValueError, match="creator_profile_identity_invalid"):
        replace(REQUEST, creator_remote_id=creator_id)


@pytest.mark.parametrize("timeout", [True, 0, -1, 45.1, float("inf"), float("nan"), "45"])
def test_execution_budget_is_strict(timeout: object) -> None:
    with pytest.raises(ValueError, match="creator_profile_budget_invalid"):
        replace(REQUEST, timeout_seconds=timeout)


@pytest.mark.parametrize("field", ["account_id", "request_id"])
def test_request_requires_typed_uuid(field: str) -> None:
    with pytest.raises(ValueError):
        replace(REQUEST, **{field: str(uuid4())})


def test_closed_result_frame_roundtrips_without_repr_disclosure() -> None:
    result = module._result(REQUEST, MediaCrawlerCreatorProfileStatus.SUCCEEDED, SHA, PROFILE)
    assert PROFILE.display_name not in repr(result) and PROFILE.avatar_url not in repr(result)
    assert PROFILE.display_name not in repr(PROFILE) and PROFILE.avatar_url not in repr(PROFILE)
    frame = module._result_frame(result)
    payload = module._read_stream_frame(io.BytesIO(frame), module.MAX_PROFILE_RESULT_BYTES)
    assert module._parse_result(payload, REQUEST) == result


@pytest.mark.parametrize("field", ["account_id", "request_id", "creator_remote_id", "platform"])
def test_result_rejects_any_identity_mismatch(field: str) -> None:
    raw = json.loads(
        module._result_frame(module._result(REQUEST, MediaCrawlerCreatorProfileStatus.SUCCEEDED, SHA, PROFILE))[4:]
    )
    raw[field] = {
        "account_id": str(uuid4()),
        "request_id": str(uuid4()),
        "creator_remote_id": "456",
        "platform": "xhs",
    }[field]
    with pytest.raises(ValueError):
        module._parse_result(json.dumps(raw).encode(), REQUEST)


@pytest.mark.parametrize(
    "mutation", ["extra", "bool-version", "unknown-status", "failure-profile", "wrong-profile", "bad-sha"]
)
def test_result_schema_is_closed(mutation: str) -> None:
    raw = json.loads(
        module._result_frame(module._result(REQUEST, MediaCrawlerCreatorProfileStatus.SUCCEEDED, SHA, PROFILE))[4:]
    )
    if mutation == "extra":
        raw["cookie"] = "SECRET"
    elif mutation == "bool-version":
        raw["schema_version"] = True
    elif mutation == "unknown-status":
        raw["status"] = "raw /private/path"
    elif mutation == "failure-profile":
        raw["status"] = "temporary"
    elif mutation == "wrong-profile":
        raw["profile"]["remote_id"] = "456"
    else:
        raw["upstream_sha"] = "invalid"
    with pytest.raises(ValueError):
        module._parse_result(json.dumps(raw).encode(), REQUEST)


@pytest.mark.parametrize("frame", [b"", b"\0\0", (0).to_bytes(4, "big"), (16385).to_bytes(4, "big"), b"\0\0\0\x05abc"])
def test_frame_rejects_empty_oversized_and_truncated_bytes(frame: bytes) -> None:
    with pytest.raises(ValueError):
        module._read_stream_frame(io.BytesIO(frame), module.MAX_PROFILE_RESULT_BYTES)


def test_duplicate_json_fields_are_rejected() -> None:
    with pytest.raises(ValueError):
        module._json(b'{"status":"succeeded","status":"temporary"}', 100)


@pytest.mark.parametrize("raw_name", [None, "", "x" * 513, "name\r\nCookie: secret"])
def test_invalid_profile_name_is_not_promoted(raw_name: object) -> None:
    with pytest.raises(ValueError):
        MediaCrawlerCreatorProfile("123", raw_name, None)


def test_only_success_can_carry_profile_and_requires_qualified_sha() -> None:
    for status in MediaCrawlerCreatorProfileStatus:
        if status is not MediaCrawlerCreatorProfileStatus.SUCCEEDED:
            with pytest.raises(ValueError):
                MediaCrawlerCreatorProfileResult(
                    status, REQUEST.account_id, Platform.BILI, "123", REQUEST.request_id, SHA, PROFILE
                )
    with pytest.raises(ValueError):
        module._result(REQUEST, MediaCrawlerCreatorProfileStatus.SUCCEEDED, None, PROFILE)


class _Client:
    def __init__(self, *, authenticated: object = True, raw: object | None = None) -> None:
        self.headers = {"Cookie": "PRIVATE_COOKIE", "User-Agent": "offline"}
        self.authenticated = authenticated
        self.raw = raw if raw is not None else {"mid": 123, "name": "Name", "face": None}
        self.profile_calls = 0

    async def get(self, uri: str, *, enable_params_sign: bool) -> object:
        assert uri == module._NAV_PATH and not enable_params_sign
        return {"isLogin": self.authenticated}

    async def get_creator_info(self, creator_id: int) -> object:
        assert creator_id == 123
        self.profile_calls += 1
        return self.raw


@pytest.mark.parametrize(
    "authenticated, status", [(False, "auth_expired"), (1, "result_invalid"), (None, "result_invalid")]
)
async def test_auth_failure_never_calls_profile_or_login(authenticated: object, status: str) -> None:
    client = _Client(authenticated=authenticated)
    with pytest.raises(module._LookupFailure) as caught:
        await module._query_bili_client(client, "123", time.monotonic() + 5)
    assert caught.value.status.value == status and client.profile_calls == 0


@pytest.mark.parametrize("mid", [124, "0123", True, 123.0, None])
async def test_profile_remote_identity_is_verified(mid: object) -> None:
    client = _Client(raw={"mid": mid, "name": "Name"})
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await module._query_bili_client(client, "123", time.monotonic() + 5)
    assert client.profile_calls == 1


async def test_client_wrapper_rejects_content_routes_and_request_amplification(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client()
    await module._query_bili_client(client, "123", time.monotonic() + 5)
    requests: list[str] = []

    def fetch(url: str, headers: object, deadline: float) -> dict[str, object]:
        requests.append(url)
        return {}

    monkeypatch.setattr(module, "_fetch_api_json", fetch)
    for url in (
        "http://api.bilibili.com/x/web-interface/nav",
        "https://127.0.0.1/x/web-interface/nav",
        "https://api.bilibili.com/x/space/wbi/arc/search",
        "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space",
        "https://api.bilibili.com/x/space/wbi/acc/info#secret",
    ):
        with pytest.raises(module._LookupFailure):
            await client.request("GET", url)
    assert requests == []
    url = "https://api.bilibili.com/x/space/wbi/acc/info?mid=123"
    await client.request("GET", url)
    with pytest.raises(module._LookupFailure):
        await client.request("GET", url)
    assert requests == [url]


@pytest.mark.parametrize(
    "response_mode", ["redirect", "oversized", "bad-json", "duplicate", "failed-code", "invalid-data"]
)
def test_http_api_transport_is_bounded_and_never_follows_redirects(
    monkeypatch: pytest.MonkeyPatch, response_mode: str
) -> None:
    import media_sync.media.network as network

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if response_mode == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        body = {
            "oversized": b"x" * (module.MAX_PROFILE_API_BYTES + 1),
            "bad-json": b"not json",
            "duplicate": b'{"code":0,"code":1,"data":{}}',
            "failed-code": b'{"code":-1,"data":{}}',
            "invalid-data": b'{"code":0,"data":[]}',
        }[response_mode]
        return httpx.Response(200, content=body)

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(handler))
    with pytest.raises((ValueError, module._LookupFailure)):
        module._fetch_api_json(
            "https://api.bilibili.com/x/web-interface/nav", {"Cookie": "PRIVATE_COOKIE"}, time.monotonic() + 2
        )
    assert len(seen) == 1 and seen[0].headers["Cookie"] == "PRIVATE_COOKIE"


def test_http_api_rejects_private_dns_before_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    import media_sync.media.network as network

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["127.0.0.1"])
    with pytest.raises(MediaDownloadError):
        module._fetch_api_json("https://api.bilibili.com/x/web-interface/nav", {}, time.monotonic() + 2)
