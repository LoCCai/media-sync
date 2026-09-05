"""Exact middleware-only browser navigation without anonymous handler access."""

from __future__ import annotations

import asyncio

import pytest
from starlette.types import Message, Receive, Scope, Send

from media_sync.security import (
    OPERATOR_SESSION_COOKIE_NAME,
    OperatorAuthMiddleware,
    OperatorAuthRuntime,
    SecretValue,
    derive_operator_origin_policy,
    is_anonymous_operator_request,
)

_PATHS = ("/accounts", "/subscriptions", "/contents", "/assets", "/library", "/jobs", "/settings", "/diagnostics")


def _exchange(
    *,
    method: str = "GET",
    path: str = "/accounts",
    raw_path: bytes | None = None,
    accept: bytes | None = b"text/html",
    extra_headers: tuple[tuple[bytes, bytes], ...] = (),
    host: bytes = b"127.0.0.1:8632",
    authenticated: bool = False,
) -> tuple[list[Message], list[str]]:
    entered: list[str] = []
    runtime = OperatorAuthRuntime(SecretValue("test-browser-credential-0123456789"), _minimum_login_seconds=0)
    headers = [(b"host", host), *extra_headers]
    if accept is not None:
        headers.append((b"accept", accept))
    if authenticated:
        issued = runtime.login("test-browser-credential-0123456789")
        headers.append((b"cookie", f"{OPERATOR_SESSION_COOKIE_NAME}={issued.cookie_value}".encode()))

    async def downstream(scope: Scope, _receive: Receive, send: Send) -> None:
        entered.append(str(scope["path"]))
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = OperatorAuthMiddleware(
        downstream,
        runtime=runtime,
        origin_policy=derive_operator_origin_policy("127.0.0.1", 8632, None),
    )

    async def request() -> list[Message]:
        messages: list[Message] = []

        async def receive() -> Message:
            raise AssertionError("anonymous navigation must not consume the request body")

        async def send(message: Message) -> None:
            messages.append(message)

        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "method": method,
            "path": path,
            "raw_path": raw_path if raw_path is not None else path.encode(),
            "query_string": b"return_to=https%3A%2F%2Fevil.example&token=private-query-sentinel",
            "headers": headers,
        }
        await middleware(scope, receive, send)
        return messages

    return asyncio.run(request()), entered


@pytest.mark.parametrize("path", _PATHS)
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_exact_spa_entry_redirects_without_public_authority_or_downstream(method: str, path: str) -> None:
    assert not is_anonymous_operator_request(method, path)
    messages, entered = _exchange(method=method, path=path)
    assert entered == []
    assert len(messages) == 2
    assert messages[0]["status"] == 303
    headers = dict(messages[0]["headers"])
    assert headers[b"location"] == f"/?return_to=%2F{path[1:]}".encode()
    assert headers[b"cache-control"] == b"no-store"
    assert headers[b"content-length"] == b"0"
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"x-frame-options"] == b"DENY"
    assert headers[b"referrer-policy"] == b"no-referrer"
    assert b"frame-ancestors 'none'" in headers[b"content-security-policy"]
    assert b"permissions-policy" in headers
    assert b"set-cookie" not in headers
    assert "private-query-sentinel" not in repr(messages)
    assert "evil.example" not in repr(messages)
    assert messages[1]["body"] == b""


@pytest.mark.parametrize(
    "accept",
    [
        b"text/html",
        b"TEXT/HTML",
        b"text/html;q=0.001",
        b"text/html;q=1.000",
        b"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        b"text/html; charset=utf-8",
    ],
)
def test_explicit_acceptable_html_navigation(accept: bytes) -> None:
    messages, entered = _exchange(accept=accept)
    assert messages[0]["status"] == 303
    assert entered == []


@pytest.mark.parametrize(
    "accept",
    [
        None,
        b"",
        b"*/*",
        b"application/json",
        b"application/xhtml+xml",
        b"text/html;q=0",
        b"text/html;q=0.000,*/*;q=1",
        b"text/html;q=NaN",
        b"text/html;q=1.1",
        b"text/html;q=-1",
        b"text/html;q=",
        b"text/html;q=1;q=1",
        b"text/html;q=1, text/html;q=0",
        b"text/html;broken",
        b"text/html\r\nInjected: true",
        b"text/html;" + b"x" * 4_096,
    ],
)
def test_non_html_disabled_or_ambiguous_accept_remains_fixed_401(accept: bytes | None) -> None:
    messages, entered = _exchange(accept=accept)
    assert messages[0]["status"] == 401
    assert b"location" not in dict(messages[0]["headers"])
    assert messages[1]["body"] == b'{"detail":"operator_auth_required"}'
    assert entered == []


def test_duplicate_accept_header_remains_rejected() -> None:
    messages, entered = _exchange(extra_headers=((b"Accept", b"text/html"),))
    assert messages[0]["status"] == 401
    assert entered == []


@pytest.mark.parametrize(
    "path",
    [
        "/accounts/",
        "/Accounts",
        "/accounts/private",
        "/accounts.html",
        "//accounts",
        "/unknown",
        "/legacy",
        "/api/docs",
        "/api/v1/accounts",
        "/api/v1/unknown",
        "/favicon.svg/private",
        "/_app/immutable/missing.js",
        "/https://evil.example",
    ],
)
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_unknown_api_and_noncanonical_paths_remain_fixed_denials(path: str, method: str) -> None:
    messages, entered = _exchange(path=path, method=method)
    assert messages[0]["status"] == 401
    assert b"location" not in dict(messages[0]["headers"])
    assert messages[1]["body"] == (b"" if method == "HEAD" else b'{"detail":"operator_auth_required"}')
    assert entered == []


@pytest.mark.parametrize("raw_path", [b"/%61ccounts", b"%2Faccounts", b"//accounts", b"/private/../accounts"])
def test_decoded_known_path_does_not_expand_raw_entry_set(raw_path: bytes) -> None:
    messages, entered = _exchange(raw_path=raw_path)
    assert messages[0]["status"] == 401
    assert entered == []


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_non_navigation_methods_keep_denial(method: str) -> None:
    messages, entered = _exchange(method=method)
    assert messages[0]["status"] == 401
    assert entered == []


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_host_check_precedes_even_known_html_navigation(method: str) -> None:
    messages, entered = _exchange(
        method=method,
        host=b"evil.example",
        extra_headers=((b"x-forwarded-host", b"127.0.0.1:8632"), (b"x-forwarded-proto", b"http")),
    )
    assert messages[0]["status"] == 403
    assert b"location" not in dict(messages[0]["headers"])
    assert messages[1]["body"] == (b"" if method == "HEAD" else b'{"detail":"operator_host_forbidden"}')
    assert entered == []


@pytest.mark.parametrize("path", _PATHS)
def test_authenticated_html_navigation_keeps_normal_downstream_authority(path: str) -> None:
    messages, entered = _exchange(path=path, authenticated=True)
    assert messages[0]["status"] == 204
    assert entered == [path]
