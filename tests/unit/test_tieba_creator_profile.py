"""Original synthetic creator fixtures; no real identity, Cookie or platform call."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest

from media_sync.integrations.mediacrawler import tieba_creator_profile as module
from media_sync.integrations.mediacrawler.creator_profile_runner import _LookupFailure

PORTRAIT = "tb.1.12345678." + "AbCdEf0123456789_-abcd"
COOKIE = 'BDUSS=PRIVATE_TEST_CANDIDATE==; marker="quoted=="'
STAMP = "?t=1777543466"


def evidence(*, timestamp: bool = False) -> dict[str, Any]:
    return {
        "error_code": 0,
        "data": {
            "user": {
                "id": 123,
                "portrait": PORTRAIT + (STAMP if timestamp else ""),
                "name": "Platform username",
                "name_show": "原始平台昵称",
                "private_incidental": "not retained",
            }
        },
    }


def headers() -> dict[str, str]:
    return {
        "User-Agent": "synthetic-desktop",
        "Cookie": COOKIE,
        "Origin": "https://tieba.baidu.com",
        "Referer": "https://tieba.baidu.com/",
    }


def with_avatar(raw: dict[str, Any], avatar: Any) -> dict[str, Any]:
    raw["data"]["user"]["user_show_info"] = {"feed_head": {"image_data": {"img_url": avatar}}}
    return raw


@pytest.mark.parametrize("timestamp", [False, True])
def test_exact_returned_identity_and_raw_name_with_source_backed_avatar(timestamp: bool) -> None:
    result = module.parse_tieba_profile_json(evidence(timestamp=timestamp), PORTRAIT)
    assert result.remote_id == PORTRAIT and result.display_name == "原始平台昵称"
    assert result.avatar_url == module._AVATAR + PORTRAIT + (STAMP if timestamp else "")
    assert "not retained" not in repr(result) and "原始" not in repr(result)


@pytest.mark.parametrize("value", [None, "", "missing"])
def test_missing_or_empty_nickname_uses_real_platform_username(value: Any) -> None:
    raw = evidence()
    if value == "missing":
        del raw["data"]["user"]["name_show"]
    else:
        raw["data"]["user"]["name_show"] = value
    assert module.parse_tieba_profile_json(raw, PORTRAIT).display_name == "Platform username"


@pytest.mark.parametrize("name", [False, 0, [], {}, " ", "\nsecret", "x" * 513, "\ud800"])
def test_bad_nickname_never_str_coerced_or_falls_back(name: Any) -> None:
    raw = evidence()
    raw["data"]["user"]["name_show"] = name
    with pytest.raises(_LookupFailure, match="result_invalid"):
        module.parse_tieba_profile_json(raw, PORTRAIT)


@pytest.mark.parametrize(
    "portrait",
    [
        None,
        123,
        "",
        "tb.1.other",
        PORTRAIT + "?t=1",
        PORTRAIT + "?t=" + "".join(chr(0xFF10 + digit) for digit in range(10)),
        PORTRAIT + STAMP + "&x=1",
        PORTRAIT + STAMP + "?t=1777543466",
        PORTRAIT + "?x=1777543466",
        PORTRAIT + "#fragment",
        PORTRAIT + "/",
        PORTRAIT.upper(),
    ],
)
def test_response_identity_drift_and_unknown_suffix_rejected(portrait: Any) -> None:
    raw = evidence()
    raw["data"]["user"]["portrait"] = portrait
    with pytest.raises(_LookupFailure):
        module.parse_tieba_profile_json(raw, PORTRAIT)


@pytest.mark.parametrize(
    "portrait",
    [
        ".",
        "..",
        "",
        "123",
        "tb.1.short",
        "tb.1." + "a" * 32,
        "tb.1." + "a" * 27,
        "tb.1." + "a" * 27 + ".",
        "tb.1.." + "a" * 28,
        PORTRAIT + STAMP,
        PORTRAIT + "/",
        " " + PORTRAIT,
        "tb.1." + "中" * 28,
    ],
)
def test_only_canonical_modern_input_subset(portrait: str) -> None:
    with pytest.raises(_LookupFailure):
        module.parse_tieba_profile_json(evidence(), portrait)


@pytest.mark.parametrize("tail", ["a" * 28, "a" * 31])
def test_input_subset_bounds(tail: str) -> None:
    assert module._identity("tb.1." + tail) == "tb.1." + tail


@pytest.mark.parametrize(
    "change",
    [
        "missing_code",
        "string_code",
        "bool_code",
        "error_code",
        "no_bool",
        "no_error",
        "no_string",
        "missing_data",
        "list_data",
        "missing_user",
        "list_user",
    ],
)
def test_strict_success_envelope_and_user_object(change: str) -> None:
    raw = evidence()
    if change == "missing_code":
        del raw["error_code"]
    elif change in {"string_code", "bool_code", "error_code"}:
        raw["error_code"] = {"string_code": "0", "bool_code": False, "error_code": 1}[change]
    elif change.startswith("no_"):
        raw["no"] = {"no_bool": False, "no_error": 1, "no_string": "0"}[change]
    elif change == "missing_data":
        del raw["data"]
    elif change == "list_data":
        raw["data"] = []
    elif change == "missing_user":
        del raw["data"]["user"]
    else:
        raw["data"]["user"] = []
    with pytest.raises(_LookupFailure):
        module.parse_tieba_profile_json(raw, PORTRAIT)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"[]",
        b"{}",
        b'{"error_code":1,"error_code":0}',
        b'{"error_code":0,"data":{"x":NaN}}',
        b'{"error_code":false}',
        b"\xff",
        pytest.param(b"x" * (module.MAX_PROFILE_API_BYTES + 1), id="oversize"),
    ],
)
def test_strict_json_before_upstream_parser(payload: bytes) -> None:
    with pytest.raises(_LookupFailure, match="result_invalid"):
        module._json(payload)


@pytest.mark.parametrize("timestamp", [False, True])
@pytest.mark.parametrize(
    "avatar",
    [
        "exact",
        "missing",
        "empty",
        "unknown",
        "other_identity",
        "http",
        "query",
        "port",
        "userinfo",
        "encoding",
        "different_stamp",
        "number",
        "object",
    ],
)
def test_avatar_is_optional_exact_source_backed_and_bound(timestamp: bool, avatar: str) -> None:
    raw = evidence(timestamp=timestamp)
    expected = module._AVATAR + raw["data"]["user"]["portrait"]
    values: dict[str, Any] = {
        "exact": expected,
        "empty": "",
        "unknown": "https://unknown.example/private.png",
        "other_identity": module._AVATAR + "tb.1." + "b" * 28,
        "http": expected.replace("https:", "http:"),
        "query": expected + "&redirect=http://127.0.0.1",
        "port": expected.replace(".com/", ".com:443/"),
        "userinfo": expected.replace("https://", "https://secret@"),
        "encoding": expected.replace("tb.1.", "tb%2e1."),
        "different_stamp": module._AVATAR + PORTRAIT + "?t=0000000000",
        "number": 123,
        "object": {},
    }
    if avatar != "missing":
        with_avatar(raw, values[avatar])
    result = module.parse_tieba_profile_json(raw, PORTRAIT)
    assert result.display_name == "原始平台昵称"
    assert result.avatar_url == (expected if avatar in {"exact", "missing", "empty"} else None)


@pytest.mark.parametrize(
    "change",
    [
        None,
        "redirect",
        "unauthorized",
        "forbidden",
        "server_error",
        "encoding",
        "content_type",
        "length",
        "oversize",
        "private_dns",
        "cookie",
        "header",
        "wrong_url",
        "duplicate_query",
        "wrong_sign",
        "deadline",
    ],
)
def test_fixed_signed_bounded_transport(monkeypatch: pytest.MonkeyPatch, change: str | None) -> None:
    import media_sync.media.network as network

    calls: list[httpx.Request] = []
    url = module._request_url(PORTRAIT, "a" * 32)
    outgoing = headers()
    if change == "cookie":
        outgoing["Cookie"] = ""
    elif change == "header":
        outgoing["Authorization"] = "secret"
    elif change == "wrong_url":
        url = url.replace("homeSidebarRight", "sync")
    elif change == "duplicate_query":
        url += "&portrait=" + PORTRAIT
    elif change == "wrong_sign":
        url = url.replace("a" * 32, "not-a-sign")

    payload = json.dumps(evidence()).encode()

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET" and request.url.host == "tieba.baidu.com" and not request.content
        assert request.headers["cookie"] == COOKIE and request.headers["accept-encoding"] == "identity"
        response_headers = {"content-type": "application/json"}
        if change == "encoding":
            response_headers["content-encoding"] = "gzip"
        elif change == "content_type":
            response_headers["content-type"] = "text/html"
        elif change == "length":
            response_headers["content-length"] = str(module.MAX_PROFILE_API_BYTES + 1)
        return httpx.Response(
            {"redirect": 302, "unauthorized": 401, "forbidden": 403, "server_error": 500}.get(change or "", 200),
            headers=response_headers,
            stream=httpx.ByteStream(b"x" * (module.MAX_PROFILE_API_BYTES + 1) if change == "oversize" else payload),
        )

    monkeypatch.setattr(
        network.SocketAddressResolver, "resolve", lambda *args: ["127.0.0.1" if change == "private_dns" else "8.8.8.8"]
    )
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))
    if change is None:
        assert module._fetch(url, outgoing, time.monotonic() + 5, remote_id=PORTRAIT) == payload
    else:
        with pytest.raises(_LookupFailure) as error:
            module._fetch(url, outgoing, time.monotonic() + (-1 if change == "deadline" else 5), remote_id=PORTRAIT)
        assert str(error.value) != "auth_expired" and "secret" not in str(error.value)
    assert len(calls) == int(
        change not in {"private_dns", "cookie", "header", "wrong_url", "duplicate_query", "wrong_sign", "deadline"}
    )
