"""Real operator-login helpers shared by HTTP contract tests."""

from __future__ import annotations

from collections.abc import Callable

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from media_sync.config import Settings
from media_sync.interfaces.api import create_api_app
from media_sync.security import OPERATOR_CSRF_HEADER_NAME, OPERATOR_SESSION_COOKIE_NAME

TEST_OPERATOR_CREDENTIAL = "media-sync-test-operator-credential-v1"
TEST_OPERATOR_ORIGIN = "http://127.0.0.1:8632"
_TEST_CREDENTIAL_FILE = "operator-test-credential.txt"


def operator_test_settings(settings: Settings) -> Settings:
    """Clone settings with one confined file-backed test credential."""

    secret_root = settings.resolved_secret_file_dir
    secret_root.mkdir(parents=True, exist_ok=True)
    (secret_root / _TEST_CREDENTIAL_FILE).write_text(TEST_OPERATOR_CREDENTIAL, encoding="utf-8")
    values = settings.model_dump(mode="python")
    values.update(
        {
            "operator_credential_secret_ref": f"file:{_TEST_CREDENTIAL_FILE}",
            "operator_api_token_secret_ref": None,
            "operator_allowed_origins": (TEST_OPERATOR_ORIGIN,),
        }
    )
    return Settings(**values, _env_file=None)


def authenticate_test_client(client: TestClient) -> str:
    """Perform the production login and session-bootstrap flow."""

    login = client.post(
        "/api/v1/operator-auth/login",
        json={"credential": TEST_OPERATOR_CREDENTIAL},
        headers={"Origin": TEST_OPERATOR_ORIGIN},
    )
    assert login.status_code == 200, login.text
    session = client.get("/api/v1/operator-auth/session")
    assert session.status_code == 200, session.text
    payload = session.json()
    assert payload["authenticated"] is True
    csrf_token = payload["csrf_token"]
    assert isinstance(csrf_token, str)

    def add_browser_proof(request: httpx.Request) -> None:
        if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            request.headers.setdefault("Origin", TEST_OPERATOR_ORIGIN)
            request.headers.setdefault(OPERATOR_CSRF_HEADER_NAME, csrf_token)

    client.event_hooks.setdefault("request", []).append(add_browser_proof)
    return csrf_token


def authenticated_test_client(
    settings: Settings,
    *,
    app_factory: Callable[[Settings], FastAPI] = create_api_app,
) -> TestClient:
    """Build an app with real auth and return its logged-in browser client."""

    authenticated_settings = operator_test_settings(settings)
    client = TestClient(app_factory(authenticated_settings), base_url=TEST_OPERATOR_ORIGIN)
    authenticate_test_client(client)
    return client


def authenticated_asgi_headers(client: TestClient) -> list[tuple[bytes, bytes]]:
    """Return the exact Host and current opaque cookie for direct ASGI tests."""

    cookie = client.cookies.get(OPERATOR_SESSION_COOKIE_NAME)
    assert cookie is not None
    return [
        (b"host", b"127.0.0.1:8632"),
        (b"cookie", f"{OPERATOR_SESSION_COOKIE_NAME}={cookie}".encode("ascii")),
    ]


__all__ = [
    "TEST_OPERATOR_CREDENTIAL",
    "TEST_OPERATOR_ORIGIN",
    "authenticate_test_client",
    "authenticated_asgi_headers",
    "authenticated_test_client",
    "operator_test_settings",
]
