from __future__ import annotations

import asyncio

import pytest
from starlette.types import Message, Receive, Scope, Send

from media_sync.security import (
    OPERATOR_SESSION_COOKIE_NAME,
    OperatorAuthMethod,
    OperatorAuthMiddleware,
    OperatorAuthRuntime,
    SecretValue,
    derive_operator_origin_policy,
    operator_auth_method,
)


def _exchange(
    *, path: str, authenticated: bool, origin: bytes | None
) -> tuple[list[Message], list[OperatorAuthMethod | None]]:
    runtime = OperatorAuthRuntime(SecretValue("test-browser-credential-0123456789"), _minimum_login_seconds=0)
    headers: list[tuple[bytes, bytes]] = [(b"host", b"127.0.0.1:8632")]
    if origin is not None:
        headers.append((b"origin", origin))
    if authenticated:
        session = runtime.login("test-browser-credential-0123456789")
        headers.append((b"cookie", f"{OPERATOR_SESSION_COOKIE_NAME}={session.cookie_value}".encode()))
    entered: list[OperatorAuthMethod | None] = []

    async def downstream(scope: Scope, _receive: Receive, send: Send) -> None:
        entered.append(operator_auth_method(scope))
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.close", "code": 1000})

    middleware = OperatorAuthMiddleware(
        downstream,
        runtime=runtime,
        origin_policy=derive_operator_origin_policy("127.0.0.1", 8632, None),
    )

    async def request() -> list[Message]:
        messages: list[Message] = []

        async def receive() -> Message:
            return {"type": "websocket.connect"}

        async def send(message: Message) -> None:
            messages.append(message)

        scope: Scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "scheme": "ws",
            "headers": headers,
        }
        await middleware(scope, receive, send)
        return messages

    return asyncio.run(request()), entered


@pytest.mark.parametrize(
    ("path", "authenticated", "origin"),
    [
        ("/crawler/api/ws/logs", False, b"http://127.0.0.1:8632"),
        ("/crawler/api/ws/logs", True, None),
        ("/crawler/api/ws/logs", True, b"http://evil.invalid"),
        ("/api/private-ws", True, b"http://127.0.0.1:8632"),
    ],
)
def test_websocket_boundary_rejects_anonymous_wrong_origin_and_unknown_routes(
    path: str, authenticated: bool, origin: bytes | None
) -> None:
    messages, entered = _exchange(path=path, authenticated=authenticated, origin=origin)
    assert entered == []
    assert messages == [{"type": "websocket.close", "code": 4403, "reason": "operator_auth_required"}]


@pytest.mark.parametrize("path", ["/crawler/api/ws/logs", "/crawler/api/ws/status"])
def test_authenticated_exact_origin_websocket_reaches_upstream(path: str) -> None:
    messages, entered = _exchange(path=path, authenticated=True, origin=b"http://127.0.0.1:8632")
    assert entered == [OperatorAuthMethod.BROWSER]
    assert messages == [{"type": "websocket.accept"}, {"type": "websocket.close", "code": 1000}]
