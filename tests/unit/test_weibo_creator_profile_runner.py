from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import creator_profile_runner as module

UID = "123"
PROFILE_URL = "https://m.weibo.cn/api/container/getIndex?" + urlencode(
    {"jumpfrom": "weibocom", "type": "uid", "value": UID, "containerid": "100505" + UID}
)


class Client:
    def __init__(self) -> None:
        self.headers = {"Cookie": "SUB=PRIVATE==", "User-Agent": "offline-agent"}
        self.profile_url = PROFILE_URL

    async def get(self, path: str) -> object:
        return await self.request("GET", "https://m.weibo.cn" + path, headers=self.headers)

    async def get_creator_info_by_id(self, uid: str) -> object:
        assert uid == UID
        return await self.request("GET", self.profile_url, headers=self.headers)


@pytest.fixture
def response(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, object], list[str]]:
    responses: dict[str, object] = {
        "auth": {"ok": 1, "data": {"login": True}},
        "profile": {
            "ok": 1,
            "data": {
                "userInfo": {
                    "id": 123,
                    "screen_name": "准确微博昵称",
                    "avatar_hd": "https://tva1.sinaimg.cn/large/abc.jpg",
                },
                "cards": [{"ignored": "private incidental text"}],
            },
        },
    }
    seen: list[str] = []

    def fetch(url: str, headers: dict[str, str], deadline: float) -> object:
        assert headers == {"Cookie": "SUB=PRIVATE==", "User-Agent": "offline-agent"}
        seen.append(url)
        return responses["auth" if len(seen) == 1 else "profile"]

    monkeypatch.setattr(module, "_fetch_raw_api_json", fetch)
    return responses, seen


async def test_weibo_exact_auth_then_profile_and_private_result(response: tuple[dict[str, object], list[str]]) -> None:
    _responses, seen = response
    profile = await module._query_weibo_client(Client(), UID, time.monotonic() + 3)
    assert seen == ["https://m.weibo.cn/api/config", PROFILE_URL]
    assert profile.remote_id == UID and profile.display_name == "准确微博昵称"
    assert "准确微博昵称" not in repr(profile)
    request = module.MediaCrawlerCreatorProfileRequest(uuid4(), Platform.WB, UID, uuid4())
    result = module._result(request, module.MediaCrawlerCreatorProfileStatus.SUCCEEDED, "a" * 40, profile)
    assert module._parse_result(module._result_frame(result)[4:], request) == result


@pytest.mark.parametrize(
    "raw,expected",
    [
        ({"ok": 1, "data": {"login": False}}, "auth_expired"),
        ({"ok": 1, "data": {"login": 1}}, "result_invalid"),
        ({"ok": 1, "data": {}}, "result_invalid"),
        ({"ok": True, "data": {"login": True}}, "temporary"),
        ({"ok": 0, "data": {"login": True}}, "temporary"),
        ({"ok": 1, "data": []}, "result_invalid"),
    ],
)
async def test_auth_must_be_explicit_and_profile_never_requested(
    response: tuple[dict[str, object], list[str]], raw: object, expected: str
) -> None:
    responses, seen = response
    responses["auth"] = raw
    with pytest.raises(module._LookupFailure) as caught:
        await module._query_weibo_client(Client(), UID, time.monotonic() + 3)
    assert caught.value.status.value == expected
    assert seen == ["https://m.weibo.cn/api/config"]


@pytest.mark.parametrize("remote_id", [124, "0123", True, 123.0, None, "123\n"])
async def test_response_identity_must_match(response: tuple[dict[str, object], list[str]], remote_id: object) -> None:
    responses, _seen = response
    responses["profile"] = {"ok": 1, "data": {"userInfo": {"id": remote_id, "screen_name": "Name"}}}
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await module._query_weibo_client(Client(), UID, time.monotonic() + 3)


@pytest.mark.parametrize("name", [None, "", "   ", "x" * 513, "x\nCookie=private", 123])
async def test_invalid_name_never_becomes_a_profile(
    response: tuple[dict[str, object], list[str]], name: object
) -> None:
    responses, _seen = response
    responses["profile"] = {"ok": 1, "data": {"userInfo": {"id": 123, "screen_name": name}}}
    with pytest.raises(ValueError):
        await module._query_weibo_client(Client(), UID, time.monotonic() + 3)


@pytest.mark.parametrize(
    "hd,fallback,expected",
    [
        (
            "https://tva1.sinaimg.cn/large/hd.jpg",
            "https://tva1.sinaimg.cn/small/fallback.jpg",
            "https://tva1.sinaimg.cn/large/hd.jpg",
        ),
        (None, "https://tva1.sinaimg.cn/small/fallback.jpg", "https://tva1.sinaimg.cn/small/fallback.jpg"),
        ("", None, None),
        ({"invalid": 1}, "", None),
        ("x" * 2049, "https://tva1.sinaimg.cn/small/fallback.jpg", "https://tva1.sinaimg.cn/small/fallback.jpg"),
    ],
)
async def test_optional_avatar_failure_preserves_name(
    response: tuple[dict[str, object], list[str]], hd: object, fallback: object, expected: object
) -> None:
    responses, _seen = response
    responses["profile"] = {
        "ok": 1,
        "data": {"userInfo": {"id": UID, "screen_name": "Name", "avatar_hd": hd, "profile_image_url": fallback}},
    }
    result = await module._query_weibo_client(Client(), UID, time.monotonic() + 3)
    assert result.avatar_url == expected and result.display_name == "Name"


@pytest.mark.parametrize(
    "url",
    [
        PROFILE_URL + "&page=2",
        PROFILE_URL + "#private",
        PROFILE_URL.replace("100505123", "107603123"),
        PROFILE_URL.replace("value=123", "value=456"),
        PROFILE_URL.replace("m.weibo.cn", "127.0.0.1"),
        PROFILE_URL.replace("https:", "http:"),
        PROFILE_URL + "&value=123",
        "https://m.weibo.cn/comments/hotflow",
    ],
)
async def test_profile_query_closure(response: tuple[dict[str, object], list[str]], url: str) -> None:
    _responses, seen = response
    client = Client()
    client.profile_url = url
    with pytest.raises(module._LookupFailure, match="result_invalid"):
        await module._query_weibo_client(client, UID, time.monotonic() + 3)
    assert len(seen) == 1


async def test_no_post_retry_or_request_after_finished(response: tuple[dict[str, object], list[str]]) -> None:
    _responses, seen = response
    client = Client()
    await module._query_weibo_client(client, UID, time.monotonic() + 3)
    for method, url in (("GET", PROFILE_URL), ("POST", PROFILE_URL), ("GET", "https://m.weibo.cn/api/config")):
        with pytest.raises(module._LookupFailure):
            await client.request(method, url, headers=client.headers)
    assert len(seen) == 2


@pytest.mark.parametrize(
    "platform,expected",
    [
        (Platform.XHS, module.MediaCrawlerCreatorProfileStatus.UNSUPPORTED),
        (Platform.DY, module.MediaCrawlerCreatorProfileStatus.UNSUPPORTED),
        (Platform.KS, module.MediaCrawlerCreatorProfileStatus.AUTH_EXPIRED),
        (Platform.TIEBA, module.MediaCrawlerCreatorProfileStatus.UNSUPPORTED),
        (Platform.ZHIHU, module.MediaCrawlerCreatorProfileStatus.AUTH_EXPIRED),
    ],
)
def test_other_platform_support_and_missing_credentials(
    tmp_path: Path, platform: Platform, expected: module.MediaCrawlerCreatorProfileStatus
) -> None:
    import sys

    runner = module.MediaCrawlerCreatorProfileProcessRunner(
        lock_path=tmp_path / "absent",
        integration_root=tmp_path,
        python_executable=Path(sys.executable),
        enabled=True,
        license_acknowledged=True,
    )
    request = module.MediaCrawlerCreatorProfileRequest(uuid4(), platform, UID, uuid4())
    assert runner.run(request).status is expected


@pytest.mark.parametrize("raw_uid", ["0", "01", str(2**64), True, "1\n"])
def test_weibo_request_keeps_uint64_canonical_uid(raw_uid: object) -> None:
    request = module.MediaCrawlerCreatorProfileRequest(uuid4(), Platform.WB, UID, uuid4())
    with pytest.raises(ValueError):
        replace(request, creator_remote_id=raw_uid)


@pytest.mark.parametrize("kind", ["redirect", "compressed", "wrong_type", "oversize", "duplicate", "malformed"])
async def test_weibo_uses_bounded_transport_and_no_http_retries(monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    import media_sync.media.network as network

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if kind == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        body = b'{"ok":1,"data":{"login":true}}'
        headers = {"Content-Type": "application/json"}
        if kind == "compressed":
            headers["Content-Encoding"] = "gzip"
        elif kind == "wrong_type":
            headers["Content-Type"] = "text/html"
        elif kind == "oversize":
            body = b"x" * (module.MAX_PROFILE_API_BYTES + 1)
        elif kind == "duplicate":
            body = b'{"ok":1,"ok":0,"data":{}}'
        elif kind == "malformed":
            body = b"invalid"
        return httpx.Response(200, headers=headers, stream=httpx.ByteStream(body))

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(handler))
    with pytest.raises((module._LookupFailure, ValueError)):
        await module._query_weibo_client(Client(), UID, time.monotonic() + 3)
    assert len(seen) == 1
    assert seen[0].url == "https://m.weibo.cn/api/config"
    assert seen[0].headers["Cookie"] == "SUB=PRIVATE=="
    assert "PRIVATE" not in json.dumps({"count": len(seen)})
