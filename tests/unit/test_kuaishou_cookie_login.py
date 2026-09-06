"""Synthetic current-user evidence and closed private POST boundaries."""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

import httpx
import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import kuaishou_cookie_login as module
from media_sync.integrations.mediacrawler.cookie_login import CookieLoginRequest, parse_cookie_header
from media_sync.integrations.mediacrawler.cookie_login_runner import _VerificationFailure

COOKIE = 'kuaishou.web.cp.api_ph=PRIVATE_CP==; session=PRIVATE_SESSION==; marker="quoted=="'


def evidence() -> dict[str, Any]:
    return {
        "data": {
            "userInfo": {
                "userId": 123456,
                "name": "测试当前用户",
                "id": "incidental",
                "avatar": "https://unknown.example/PRIVATE",
            }
        }
    }


def request(cookie: str = COOKIE, platform: Platform = Platform.KS) -> CookieLoginRequest:
    return CookieLoginRequest(uuid4(), platform, uuid4(), parse_cookie_header(cookie))


def headers(cookie: str = COOKIE) -> dict[str, str]:
    return {
        "User-Agent": "synthetic-agent",
        "Cookie": cookie,
        "Origin": module._ORIGIN,
        "Referer": module._ORIGIN + "/",
        "Content-Type": "application/json",
    }


@pytest.mark.parametrize("errors", ["absent", None, []])
def test_remote_self_identity_without_error_is_required(errors: Any) -> None:
    raw = evidence()
    if errors != "absent":
        raw["errors"] = errors
    assert module._authenticated(raw) is None


@pytest.mark.parametrize("uid", [None, "123", True, False, 0, -1, 2**64, 1.5, {}, [], "guest"])
def test_uid_must_be_positive_json_integer(uid: Any) -> None:
    raw = evidence()
    raw["data"]["userInfo"]["userId"] = uid
    with pytest.raises(_VerificationFailure, match="result_invalid"):
        module._authenticated(raw)


@pytest.mark.parametrize("name", [None, "", " ", False, 123, [], {}, "\nprivate", "\ud800", "x" * 513])
def test_name_is_bounded_printable_remote_string(name: Any) -> None:
    raw = evidence()
    raw["data"]["userInfo"]["name"] = name
    with pytest.raises(_VerificationFailure):
        module._authenticated(raw)


@pytest.mark.parametrize("value", [[{"message": "PRIVATE"}], {}, False, True, 0, 1, "", "PRIVATE"])
def test_unknown_graphql_errors_never_authenticate(value: Any) -> None:
    raw = evidence()
    raw["errors"] = value
    with pytest.raises(_VerificationFailure) as error:
        module._authenticated(raw)
    assert str(error.value) == "result_invalid"


@pytest.mark.parametrize("level", ["root", "data", "user"])
@pytest.mark.parametrize(
    "flag,value",
    [
        ("guest", True),
        ("isGuest", 0),
        ("is_guest", None),
        ("isLogin", False),
        ("is_login", 1),
        ("loggedIn", None),
        ("error", None),
        ("errorCode", 0),
        ("error_code", "PRIVATE"),
    ],
)
def test_guest_login_and_error_contradictions_fail_closed(level: str, flag: str, value: Any) -> None:
    raw = evidence()
    target = raw if level == "root" else raw["data"] if level == "data" else raw["data"]["userInfo"]
    target[flag] = value
    with pytest.raises(_VerificationFailure):
        module._authenticated(raw)


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"data": None},
        {"data": []},
        {"data": {}},
        {"data": {"userInfo": None}},
        {"data": {"userInfo": []}},
        {"data": {"visionProfile": {"user_id": "123"}}},
        {"data": {"userInfo": {"id": "123", "name": "target"}}},
    ],
)
def test_local_markers_or_public_profile_shape_cannot_prove_current_user(raw: Any) -> None:
    with pytest.raises(_VerificationFailure):
        module._authenticated(raw)


@pytest.mark.parametrize(
    "cookie", ["session=valid", "kuaishou.web.api_ph=OTHER", "kuaishou.web.cp.api_ph=", 'kuaishou.web.cp.api_ph=""']
)
def test_source_cookie_prerequisite_missing_fails_before_any_request(cookie: str) -> None:
    with pytest.raises(_VerificationFailure, match="result_invalid"):
        module._body(cookie)


@pytest.mark.parametrize("value", ["RAW==", '"RAW=="', "%20encoded=="])
def test_cp_cookie_private_body_preserves_original_value_without_substitution(value: str) -> None:
    body = module._body(f"kuaishou.web.cp.api_ph={value}; kuaishou.web.api_ph=NOT_USED")
    assert body[module._CP_COOKIE] == value
    assert body["operationName"] == "userInfoQuery" and body["variables"] == {}
    assert body["query"] == module._QUERY and "NOT_USED" not in json.dumps(body)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"[]",
        b'{"data":{},"data":{}}',
        b'{"data":{"userInfo":{"userId":123,"userId":456,"name":"PRIVATE"}}}',
        b'{"data":{"value":NaN}}',
        b'{"data":{"value":Infinity}}',
        b"\xff",
        pytest.param(b'{"data":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}", id="deep-json"),
        pytest.param(b"x" * (module.MAX_API_BYTES + 1), id="oversize"),
    ],
)
def test_raw_json_is_bounded_strict_utf8_object(payload: bytes) -> None:
    with pytest.raises(_VerificationFailure, match="result_invalid"):
        module._json(payload)


@pytest.mark.parametrize(
    "change",
    [
        None,
        "redirect",
        "unauthorized",
        "forbidden",
        "error",
        "compressed",
        "html",
        "length",
        "oversize",
        "private_dns",
        "cookie_drop",
        "cookie_changed",
        "body_cp_changed",
        "query_changed",
        "variables",
        "header",
        "origin",
        "wrong_url",
        "url_query",
        "deadline",
        "timeout",
        "network",
    ],
)
def test_pinned_private_post_refuses_unsafe_transport_and_changed_body(
    monkeypatch: pytest.MonkeyPatch, change: str | None
) -> None:
    import media_sync.media.network as network

    calls: list[httpx.Request] = []
    outgoing = headers()
    body = module._body(COOKIE)
    url = module._ENDPOINT
    if change == "cookie_drop":
        del outgoing["Cookie"]
    elif change == "cookie_changed":
        outgoing["Cookie"] = COOKIE.replace("PRIVATE_CP", "CHANGED")
    elif change == "body_cp_changed":
        body[module._CP_COOKIE] = "CHANGED"
    elif change == "query_changed":
        body["query"] += " query target($id: String!) { user(id: $id) { userId } }"
    elif change == "variables":
        body["variables"] = {"userId": "123"}
    elif change == "header":
        outgoing["Authorization"] = "PRIVATE"
    elif change == "origin":
        outgoing["Origin"] = "https://unknown.example"
    elif change == "wrong_url":
        url += "/wrong"
    elif change == "url_query":
        url += "?__NS_hxfalcon=not-approved"
    encoded = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
    payload = json.dumps(evidence()).encode()

    def transport(incoming: httpx.Request) -> httpx.Response:
        calls.append(incoming)
        assert incoming.method == "POST" and incoming.url.query == b""
        assert incoming.headers["cookie"] == COOKIE and incoming.headers["accept-encoding"] == "identity"
        assert incoming.content == module._encode_body(COOKIE).encode()
        if change == "timeout":
            raise httpx.ReadTimeout("PRIVATE")
        if change == "network":
            raise httpx.ConnectError("PRIVATE")
        response_headers = {"content-type": "application/json"}
        if change == "compressed":
            response_headers["content-encoding"] = "gzip"
        elif change == "html":
            response_headers["content-type"] = "text/html"
        elif change == "length":
            response_headers["content-length"] = str(module.MAX_API_BYTES + 1)
        return httpx.Response(
            {"redirect": 302, "unauthorized": 401, "forbidden": 403, "error": 500}.get(change or "", 200),
            headers=response_headers,
            stream=httpx.ByteStream(b"x" * (module.MAX_API_BYTES + 1) if change == "oversize" else payload),
        )

    monkeypatch.setattr(
        network.SocketAddressResolver, "resolve", lambda *args: ["127.0.0.1" if change == "private_dns" else "8.8.8.8"]
    )
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))
    if change is None:
        assert module._fetch(url, encoded, outgoing, time.monotonic() + 5) == evidence()
    else:
        with pytest.raises(_VerificationFailure) as error:
            module._fetch(url, encoded, outgoing, time.monotonic() + (-1 if change == "deadline" else 5))
        assert str(error.value) == {
            "unauthorized": "rejected",
            "timeout": "timed_out",
            "deadline": "timed_out",
            "network": "verification_unavailable",
        }.get(change, "result_invalid")
    assert len(calls) == int(
        change
        not in {
            "private_dns",
            "cookie_drop",
            "cookie_changed",
            "body_cp_changed",
            "query_changed",
            "variables",
            "header",
            "origin",
            "wrong_url",
            "url_query",
            "deadline",
        }
    )


@pytest.mark.parametrize("length", ["-1", "1.0", "1e3", "", "12345678901"])
def test_declared_length_must_be_bounded_decimal(monkeypatch: pytest.MonkeyPatch, length: str) -> None:
    import media_sync.media.network as network

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(
        network,
        "PinnedHTTPTransport",
        lambda target: httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                headers={"content-type": "application/json", "content-length": length},
                stream=httpx.ByteStream(json.dumps(evidence()).encode()),
            )
        ),
    )
    with pytest.raises(_VerificationFailure, match=r"^result_invalid$"):
        module._fetch(module._ENDPOINT, module._encode_body(COOKIE).encode(), headers(), time.monotonic() + 5)


@pytest.mark.parametrize("change", ["ascii", "control", "length", "referer", "content_type"])
def test_invalid_headers_fail_before_resolving_dns(monkeypatch: pytest.MonkeyPatch, change: str) -> None:
    import media_sync.media.network as network

    outgoing = headers()
    key, value = {
        "ascii": ("User-Agent", "中文"),
        "control": ("User-Agent", "private\n"),
        "length": ("User-Agent", "x" * 8193),
        "referer": ("Referer", "https://unknown.example/"),
        "content_type": ("Content-Type", "application/json; charset=utf-8"),
    }[change]
    outgoing[key] = value

    def forbidden(*args):
        pytest.fail("malformed header must fail before DNS")

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", forbidden)
    with pytest.raises(_VerificationFailure, match=r"^result_invalid$"):
        module._fetch(module._ENDPOINT, module._encode_body(COOKIE).encode(), outgoing, time.monotonic() + 5)


@pytest.mark.parametrize("expired_at", ["after_dns", "during_stream"])
def test_transport_checks_total_deadline(monkeypatch: pytest.MonkeyPatch, expired_at: str) -> None:
    from types import SimpleNamespace

    import media_sync.media.network as network

    calls = []
    ticks = iter([1.0, 10.0] if expired_at == "after_dns" else [1.0, 1.0, 10.0])
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])

    def respond(incoming):
        calls.append(incoming)
        return httpx.Response(
            200, headers={"content-type": "application/json"}, stream=httpx.ByteStream(json.dumps(evidence()).encode())
        )

    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(respond))
    with pytest.raises(_VerificationFailure, match=r"^timed_out$"):
        module._fetch(module._ENDPOINT, module._encode_body(COOKIE).encode(), headers(), 5.0)
    assert len(calls) == int(expired_at == "during_stream")
