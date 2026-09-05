"""Closed Cookie syntax, remote evidence and private process frames; no live IO."""

from __future__ import annotations

import io
import json
import threading
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import cookie_login_runner as module
from media_sync.integrations.mediacrawler.cookie_login import (
    CookieLoginRequest,
    CookieLoginResult,
    cookie_pairs,
    parse_cookie_header,
)
from media_sync.media.errors import MediaDownloadError


def request(platform: Platform = Platform.BILI) -> CookieLoginRequest:
    return CookieLoginRequest(uuid4(), platform, uuid4(), parse_cookie_header("session=PRIVATE==; a1=device"))


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " ",
        "a",
        "a=b;;c=d",
        "a=b; a=c",
        "a=b\r\nCookie:c=d",
        "a=中",
        "a=\x7f",
        "a=b; Path=/",
        "Domain=example.com",
        "Secure=true",
        "$Path=/",
        "https://x.test/a=b",
        '{"a":"b"}',
        '[{"name":"a","value":"b"}]',
        'a="b',
        'a=b"',
        'a="b"c"',
        "a=b\\c",
        "a=b,c",
        "a=b c",
        "a=b; HttpOnly",
        "a=b; SameSite=Lax",
        "a=b; Max-Age=3",
        "a=" + "x" * 16384,
        ";".join(f"a{i}=x" for i in range(129)),
    ],
)
def test_rejects_ambiguous_cookie_without_echo(raw: str) -> None:
    with pytest.raises(ValueError) as caught:
        parse_cookie_header(raw)
    assert str(caught.value) == "cookie_header_invalid"


def test_parser_preserves_values_order_empty_and_bounded_pairs() -> None:
    secret = parse_cookie_header("  a=PRIVATE==;b=abc%3D; empty=;  ")
    assert secret.reveal() == "a=PRIVATE==; b=abc%3D; empty="
    assert cookie_pairs(secret.reveal()) == {"a": "PRIVATE==", "b": "abc%3D", "empty": ""}
    assert "PRIVATE" not in repr(secret) + str(secret) + repr(request())
    assert len(cookie_pairs(";".join(f"a{i}=x" for i in range(128)))) == 128
    assert len(parse_cookie_header("a=" + "x" * 16382).reveal()) == 16384


def test_parser_preserves_balanced_quoted_values_without_unquoting() -> None:
    raw = 'd_c0="BASE64==|123"; a=""; b="value"'
    assert parse_cookie_header(raw).reveal() == raw
    assert cookie_pairs(raw) == {"d_c0": '"BASE64==|123"', "a": '""', "b": '"value"'}


def test_normalization_cannot_expand_beyond_header_bound() -> None:
    raw = "a=" + "x" * 16377 + ";b=y"
    assert len(raw) == 16383
    assert len(parse_cookie_header(raw).reveal()) == 16384
    with pytest.raises(ValueError, match=r"^cookie_header_invalid$"):
        parse_cookie_header(raw + "z")


@pytest.mark.parametrize("timeout", [0, -1, 46, True, float("nan"), float("inf"), "45"])
def test_request_budget_is_closed(timeout: object) -> None:
    with pytest.raises(ValueError):
        replace(request(), timeout_seconds=timeout)


@pytest.mark.parametrize("platform", [Platform.DY, Platform.KS, Platform.TIEBA])
def test_unqualified_platform_never_spawns_or_writes(tmp_path: Path, platform: Platform) -> None:
    runner = module.CookieLoginProcessRunner(
        lock_path=tmp_path / "missing",
        integration_root=tmp_path / "missing-runtime",
        python_executable=Path("python"),
        enabled=True,
        license_acknowledged=True,
    )
    assert runner.run(request(platform)).status == "verification_unavailable"
    assert list(tmp_path.iterdir()) == []


def test_disabled_and_precancelled_never_spawn(tmp_path: Path) -> None:
    runner = module.CookieLoginProcessRunner(
        lock_path=tmp_path / "missing",
        integration_root=tmp_path,
        python_executable=Path("python"),
        enabled=False,
        license_acknowledged=True,
    )
    assert runner.run(request()).status == "configuration_invalid"
    runner._enabled = True
    cancelled = threading.Event()
    cancelled.set()
    assert runner.run(request(), cancellation=cancelled).status == "cancelled"


@pytest.mark.parametrize("descriptor", [-1, True, "3", 1.5])
def test_lock_descriptor_type_is_closed(descriptor: object) -> None:
    with pytest.raises(ValueError, match=r"^cookie_login_lock_invalid$"):
        replace(request(), account_lock_fd=descriptor)


def test_missing_lock_descriptor_fails_without_spawning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        pytest.fail("a validation process must inherit the held account lock")

    monkeypatch.setattr(module, "_spawn_login_child", forbidden)
    runner = module.CookieLoginProcessRunner(
        lock_path=tmp_path / "missing",
        integration_root=tmp_path,
        python_executable=Path("python"),
        enabled=True,
        license_acknowledged=True,
    )
    assert runner.run(request()).status == "configuration_invalid"


def test_descriptor_is_parent_local_and_not_serialized() -> None:
    incoming = replace(request(), account_lock_fd=12345)
    payload = module._request_payload(incoming)
    assert "account_lock_fd" not in payload and "12345" not in repr(incoming)
    assert module._load_request(payload).account_lock_fd is None


@pytest.mark.parametrize(
    "mutate", ["account_id", "platform", "operation_id", "schema_version", "status", "extra", "sha"]
)
def test_result_frames_are_identity_bound_and_closed(mutate: str) -> None:
    incoming = request()
    frame = module._result_frame(module._result(incoming, "authenticated", "a" * 40))
    raw = json.loads(frame[4:])
    assert module._parse_result(frame[4:], incoming).status == "authenticated"
    values = {
        "account_id": str(uuid4()),
        "platform": "xhs",
        "operation_id": str(uuid4()),
        "schema_version": True,
        "status": "PRIVATE_ERROR",
        "extra": "Cookie=PRIVATE",
        "sha": "private",
    }
    raw["upstream_sha" if mutate == "sha" else mutate] = values[mutate]
    with pytest.raises(ValueError):
        module._parse_result(json.dumps(raw).encode(), incoming)


@pytest.mark.parametrize("payload", [b"", b"\0\0", b"\0\0\0\0", b"\0\0\0\x08{}", b"\0\x01\0\0"])
def test_bounded_frame_rejects_truncation_and_oversize(payload: bytes) -> None:
    with pytest.raises(ValueError):
        module._read_stream_frame(io.BytesIO(payload), module.MAX_RESULT_BYTES)


def test_authenticated_result_requires_sha_and_supported_platform() -> None:
    incoming = request()
    with pytest.raises(ValueError):
        CookieLoginResult("authenticated", incoming.account_id, incoming.platform, incoming.operation_id)
    with pytest.raises(ValueError):
        CookieLoginResult("authenticated", incoming.account_id, Platform.DY, incoming.operation_id, "a" * 40)
    with pytest.raises(ValueError):
        module._json(b'{"status":"rejected","status":"authenticated"}', 100)


GOOD = {
    Platform.BILI: {"code": 0, "data": {"isLogin": True}},
    Platform.WB: {"ok": 1, "data": {"login": True}},
    Platform.XHS: {"code": 0, "success": True, "data": {"result": {"success": True}}},
    Platform.ZHIHU: {"uid": "123abc", "name": "Name"},
}


@pytest.mark.parametrize("platform", list(GOOD))
def test_each_remote_self_contract_accepts_explicit_evidence(platform: Platform) -> None:
    module._authenticated(platform, GOOD[platform])


@pytest.mark.parametrize(
    "platform,raw,status",
    [
        (Platform.BILI, {"code": 0, "data": {"isLogin": False}}, "rejected"),
        (Platform.BILI, {"code": -101}, "rejected"),
        (Platform.BILI, {"code": False, "data": {"isLogin": True}}, "result_invalid"),
        (Platform.BILI, {"code": 0, "data": {"isLogin": 1}}, "result_invalid"),
        (Platform.BILI, {"code": 0, "data": {"SESSDATA": "exists"}}, "result_invalid"),
        (Platform.WB, {"ok": 1, "data": {"login": False}}, "rejected"),
        (Platform.WB, {"ok": True, "data": {"login": True}}, "result_invalid"),
        (Platform.WB, {"ok": 1, "data": {"login": "true"}}, "result_invalid"),
        (Platform.XHS, {"data": {"result": {"success": False}}}, "rejected"),
        (Platform.XHS, {"data": {"result": {"success": 1}}}, "result_invalid"),
        (Platform.XHS, {"data": {"result": {"success": True}, "is_guest": True}}, "rejected"),
        (Platform.XHS, {"success": True, "data": {"nickname": "public"}}, "result_invalid"),
        (Platform.ZHIHU, {"uid": "123", "name": "Name", "error": {"code": 401}}, "rejected"),
        (Platform.ZHIHU, {"uid": True, "name": "Name"}, "result_invalid"),
        (Platform.ZHIHU, {"uid": "123", "name": ""}, "result_invalid"),
        (Platform.ZHIHU, {"name": "public", "z_c0": "exists"}, "result_invalid"),
        (Platform.KS, {"data": {"visionProfileUserList": {"result": 1}}}, "verification_unavailable"),
    ],
)
def test_http_ok_public_profiles_and_cookie_markers_are_not_auth(platform: Platform, raw: dict, status: str) -> None:
    with pytest.raises(module._VerificationFailure) as caught:
        module._authenticated(platform, raw)
    assert caught.value.status == status


@pytest.mark.parametrize("mode", ["ok", "redirect", "unauthorized", "html", "duplicate", "oversize", "list"])
def test_transport_pins_dns_limits_body_and_never_redirects(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    import media_sync.media.network as network

    seen = []

    def respond(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if mode == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        if mode == "unauthorized":
            return httpx.Response(401)
        bodies = {
            "ok": b'{"code":0,"data":{"isLogin":true}}',
            "html": b"<html>private</html>",
            "duplicate": b'{"x":1,"x":2}',
            "oversize": b"x" * (module.MAX_API_BYTES + 1),
            "list": b"[]",
        }
        return httpx.Response(200, stream=httpx.ByteStream(bodies[mode]), headers={"content-type": "application/json"})

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(respond))
    if mode == "ok":
        assert (
            module._fetch_json(
                "https://api.bilibili.com/x/web-interface/nav", {"Cookie": "secret=="}, time.monotonic() + 5
            )["code"]
            == 0
        )
    else:
        with pytest.raises((module._VerificationFailure, ValueError)):
            module._fetch_json(
                "https://api.bilibili.com/x/web-interface/nav", {"Cookie": "secret=="}, time.monotonic() + 5
            )
    assert len(seen) == 1 and seen[0].headers["cookie"] == "secret=="


@pytest.mark.parametrize(
    "url",
    [
        "http://api.bilibili.com/x/web-interface/nav",
        "https://127.0.0.1/private",
        "https://api.bilibili.com/x/web-interface/nav?foo=bar",
        "https://m.weibo.cn/api/config#fragment",
        "https://api.bilibili.com/x/space/wbi/arc/search",
    ],
)
def test_arbitrary_routes_are_rejected_before_dns(url: str) -> None:
    with pytest.raises(module._VerificationFailure):
        module._fetch_json(url, {}, time.monotonic() + 1)


def test_private_dns_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    import media_sync.media.network as network

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["127.0.0.1"])
    with pytest.raises(MediaDownloadError):
        module._fetch_json("https://api.bilibili.com/x/web-interface/nav", {}, time.monotonic() + 1)


@pytest.mark.parametrize(
    "headers",
    [
        {"content-type": "application/json", "content-encoding": "gzip"},
        {"content-type": "application/json", "content-encoding": "br"},
        {"content-type": "text/html"},
        {},
        {"content-type": "application/json", "content-length": "131073"},
        {"content-type": "application/json", "content-length": "-1"},
        {"content-type": "application/json", "content-length": "1e3"},
    ],
)
def test_encoded_or_wrongly_described_body_is_rejected_before_read(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
) -> None:
    import media_sync.media.network as network

    class Unreadable(httpx.SyncByteStream):
        def __iter__(self):
            pytest.fail("body must not be consumed or decompressed")
            yield b""

    monkeypatch.setattr(network.SocketAddressResolver, "resolve", lambda *args: ["8.8.8.8"])
    monkeypatch.setattr(
        network,
        "PinnedHTTPTransport",
        lambda target: httpx.MockTransport(lambda req: httpx.Response(200, stream=Unreadable(), headers=headers)),
    )
    with pytest.raises(module._VerificationFailure, match="result_invalid"):
        module._fetch_json("https://api.bilibili.com/x/web-interface/nav", {}, time.monotonic() + 1)
