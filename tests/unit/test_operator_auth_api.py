"""FastAPI and CLI-facing contracts for the 0055-A authentication boundary."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from _api_client import TEST_OPERATOR_CREDENTIAL, TEST_OPERATOR_ORIGIN, operator_test_settings
from fastapi.testclient import TestClient
from starlette.types import Message, Scope

import media_sync.interfaces.api as api_module
from media_sync.config import Settings
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.security import (
    OPERATOR_CSRF_HEADER_NAME,
    OPERATOR_SESSION_COOKIE_NAME,
    OperatorAuthConfigurationError,
)

_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _base_settings(tmp_path: Path) -> Settings:
    return Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "exports",
        job_dir=tmp_path / "jobs",
        mediacrawler_runtime_dir=tmp_path / "mediacrawler",
        _env_file=None,
    )


def _authenticated_settings(tmp_path: Path) -> Settings:
    settings = operator_test_settings(_base_settings(tmp_path))
    upgrade_database(settings.resolved_database_url)
    return settings


def _concrete_path(path: str) -> str:
    if path == "/{frontend_path:path}":
        return "/private/deep-link"
    for name in (
        "account_id",
        "login_session_id",
        "subscription_id",
        "job_id",
        "asset_id",
        "content_id",
        "author_id",
        "operation_id",
    ):
        path = path.replace(f"{{{name}}}", _UUID)
    return path


def test_app_factory_rejects_missing_auth_before_database_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_database(_url: str) -> object:
        raise AssertionError("database construction must follow operator auth resolution")

    monkeypatch.setattr(api_module, "Database", unexpected_database)

    with pytest.raises(OperatorAuthConfigurationError, match=r"^operator_auth_configuration_invalid$"):
        api_module.create_api_app(_base_settings(tmp_path))


def test_all_62_routes_are_denied_by_default_except_the_exact_public_table(tmp_path: Path) -> None:
    settings = _authenticated_settings(tmp_path)
    app = api_module.create_api_app(settings)
    routes = app.routes
    assert len(routes) == 62
    public_routes = {
        ("GET", "/api/v1/health"),
        ("HEAD", "/api/v1/health"),
        ("GET", "/api/v1/ready"),
        ("HEAD", "/api/v1/ready"),
        ("POST", "/api/v1/operator-auth/login"),
        ("GET", "/api/v1/operator-auth/session"),
        ("GET", "/"),
        ("HEAD", "/"),
    }

    with TestClient(app, base_url=TEST_OPERATOR_ORIGIN) as client:
        observed: set[tuple[str, str]] = set()
        for route in routes:
            path_template = route.path
            methods = route.methods
            for method in sorted(methods):
                path = _concrete_path(path_template)
                headers = (
                    {"Origin": TEST_OPERATOR_ORIGIN}
                    if (method, path_template)
                    == (
                        "POST",
                        "/api/v1/operator-auth/login",
                    )
                    else None
                )
                response = client.request(method, path, headers=headers)
                observed.add((method, path_template))
                if (method, path_template) in public_routes:
                    assert response.status_code not in {401, 403}, (method, path_template, response.text)
                else:
                    assert response.status_code == 401, (method, path_template, response.text)
                    if method == "HEAD":
                        assert response.content == b""
                    else:
                        assert response.json() == {"detail": "operator_auth_required"}

    assert public_routes <= observed


def test_login_session_csrf_logout_rotation_and_head_contract(tmp_path: Path) -> None:
    settings = _authenticated_settings(tmp_path)
    app = api_module.create_api_app(settings)

    with TestClient(app, base_url=TEST_OPERATOR_ORIGIN) as client:
        anonymous = client.get("/api/v1/operator-auth/session")
        assert anonymous.status_code == 200
        assert anonymous.json() == {"authenticated": False}
        assert anonymous.headers["cache-control"] == "no-store"

        wrong_origin = client.post(
            "/api/v1/operator-auth/login",
            json={"credential": TEST_OPERATOR_CREDENTIAL},
            headers={"Origin": "https://evil.example"},
        )
        assert wrong_origin.status_code == 403
        assert wrong_origin.json() == {"detail": "operator_origin_forbidden"}

        sentinel = "incorrect-private-credential-sentinel"
        rejected = client.post(
            "/api/v1/operator-auth/login",
            json={"credential": sentinel},
            headers={"Origin": TEST_OPERATOR_ORIGIN},
        )
        assert rejected.status_code == 401
        assert rejected.json() == {"detail": "operator_login_failed"}
        assert sentinel not in rejected.text

        login = client.post(
            "/api/v1/operator-auth/login",
            json={"credential": TEST_OPERATOR_CREDENTIAL},
            headers={"Origin": TEST_OPERATOR_ORIGIN},
        )
        assert login.status_code == 200
        assert login.json() == {"authenticated": True, "expires_in_seconds": 28_800}
        cookie_header = login.headers["set-cookie"]
        lowered_cookie = cookie_header.lower()
        assert f"{OPERATOR_SESSION_COOKIE_NAME}=" in cookie_header
        assert "httponly" in lowered_cookie
        assert "samesite=strict" in lowered_cookie
        assert "path=/" in lowered_cookie
        assert "max-age=28800" in lowered_cookie
        assert "domain=" not in lowered_cookie
        assert "secure" not in lowered_cookie
        first_cookie = client.cookies.get(OPERATOR_SESSION_COOKIE_NAME)
        assert first_cookie is not None

        rotated = client.post(
            "/api/v1/operator-auth/login",
            json={"credential": TEST_OPERATOR_CREDENTIAL},
            headers={"Origin": TEST_OPERATOR_ORIGIN},
        )
        second_cookie = client.cookies.get(OPERATOR_SESSION_COOKIE_NAME)
        assert rotated.status_code == 200
        assert second_cookie is not None and second_cookie != first_cookie
        assert app.state.operator_auth_runtime.session(first_cookie) is None

        session = client.get("/api/v1/operator-auth/session")
        csrf = session.json()["csrf_token"]
        assert isinstance(csrf, str) and csrf != TEST_OPERATOR_CREDENTIAL
        assert client.get("/api/v1/settings").status_code == 200

        missing_origin = client.post("/api/v1/subscriptions/preview", json={})
        assert missing_origin.status_code == 403
        assert missing_origin.json() == {"detail": "operator_origin_forbidden"}
        missing_csrf = client.post(
            "/api/v1/subscriptions/preview",
            json={},
            headers={"Origin": TEST_OPERATOR_ORIGIN},
        )
        assert missing_csrf.status_code == 403
        assert missing_csrf.json() == {"detail": "operator_csrf_forbidden"}
        passed_boundary = client.post(
            "/api/v1/subscriptions/preview",
            json={},
            headers={"Origin": TEST_OPERATOR_ORIGIN, OPERATOR_CSRF_HEADER_NAME: csrf},
        )
        assert passed_boundary.status_code == 422

        logout = client.post(
            "/api/v1/operator-auth/logout",
            headers={"Origin": TEST_OPERATOR_ORIGIN, OPERATOR_CSRF_HEADER_NAME: csrf},
        )
        assert logout.status_code == 204
        assert logout.content == b""
        assert client.get("/api/v1/settings").status_code == 401
        protected_head = client.head("/api/docs")
        assert protected_head.status_code == 401
        assert protected_head.content == b""
        assert protected_head.headers["cache-control"] == "no-store"
        assert protected_head.headers["x-content-type-options"] == "nosniff"


def test_login_openapi_keeps_the_strict_write_only_request_contract(tmp_path: Path) -> None:
    schema = api_module.create_api_app(_authenticated_settings(tmp_path)).openapi()

    request_body = schema["paths"]["/api/v1/operator-auth/login"]["post"]["requestBody"]
    credential = request_body["content"]["application/json"]["schema"]
    assert request_body["required"] is True
    assert credential == {
        "type": "object",
        "properties": {
            "credential": {
                "type": "string",
                "minLength": 1,
                "maxLength": 1_024,
                "writeOnly": True,
            }
        },
        "required": ["credential"],
        "additionalProperties": False,
    }


def test_bearer_is_header_only_nonambient_and_cannot_use_browser_only_routes(tmp_path: Path) -> None:
    secret_root = tmp_path / "state" / "secrets"
    secret_root.mkdir(parents=True)
    browser_credential = "browser-credential-0123456789"
    bearer_token = "automation-token-0123456789abcdef"
    (secret_root / "browser.txt").write_text(browser_credential, encoding="utf-8")
    (secret_root / "bearer.txt").write_text(bearer_token, encoding="utf-8")
    settings = Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "exports",
        job_dir=tmp_path / "jobs",
        operator_credential_secret_ref="file:browser.txt",
        operator_api_token_secret_ref="file:bearer.txt",
        operator_allowed_origins=(TEST_OPERATOR_ORIGIN,),
        _env_file=None,
    )
    upgrade_database(settings.resolved_database_url)

    with TestClient(api_module.create_api_app(settings), base_url=TEST_OPERATOR_ORIGIN) as client:
        authorization = {"Authorization": f"Bearer {bearer_token}"}
        assert client.get("/api/v1/settings", headers=authorization).status_code == 200
        assert client.post("/api/v1/subscriptions/preview", json={}, headers=authorization).status_code == 422
        logout = client.post("/api/v1/operator-auth/logout", headers=authorization)
        assert logout.status_code == 403
        assert logout.json() == {"detail": "operator_browser_session_required"}
        playback = client.post("/api/v1/media-server/playback-evidence", headers=authorization)
        assert playback.status_code == 403
        assert playback.json() == {"detail": "operator_browser_session_required"}
        assert client.get(f"/api/v1/settings?token={bearer_token}").status_code == 401
        client.cookies.set("bearer", bearer_token)
        assert client.get("/api/v1/settings").status_code == 401


def test_host_gate_precedes_public_routes_and_ignores_forwarded_authority(tmp_path: Path) -> None:
    settings = _authenticated_settings(tmp_path)
    client = TestClient(api_module.create_api_app(settings), base_url=TEST_OPERATOR_ORIGIN)

    denied = client.get(
        "/api/v1/health",
        headers={
            "Host": "evil.example",
            "X-Forwarded-Host": "127.0.0.1:8632",
            "X-Forwarded-Proto": "http",
        },
    )

    assert denied.status_code == 403
    assert denied.json() == {"detail": "operator_host_forbidden"}
    allowed = client.get(
        "/api/v1/health",
        headers={"X-Forwarded-Host": "evil.example", "X-Forwarded-Proto": "https"},
    )
    assert allowed.status_code == 200


def test_public_static_allowlist_requires_exact_safe_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    web_root = tmp_path / "web"
    immutable = web_root / "_app" / "immutable" / "chunks"
    immutable.mkdir(parents=True)
    (web_root / "index.html").write_text("<!doctype html><title>console</title>", encoding="utf-8")
    (web_root / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (web_root / "_app" / "version.json").write_text('{"version":"test"}', encoding="utf-8")
    (immutable / "app.js").write_text("export {};", encoding="utf-8")
    monkeypatch.setattr(api_module, "_resolve_web_root", lambda: web_root)
    settings = _authenticated_settings(tmp_path)

    with TestClient(api_module.create_api_app(settings), base_url=TEST_OPERATOR_ORIGIN) as client:
        for path in ("/", "/favicon.svg", "/_app/version.json", "/_app/immutable/chunks/app.js"):
            assert client.get(path).status_code == 200
            assert client.head(path).status_code == 200
        missing = client.get("/_app/immutable/chunks/missing.js")
        assert missing.status_code == 401
        assert client.get("/private/deep-link").status_code == 401
        login = client.post(
            "/api/v1/operator-auth/login",
            json={"credential": TEST_OPERATOR_CREDENTIAL},
            headers={"Origin": TEST_OPERATOR_ORIGIN},
        )
        assert login.status_code == 200
        assert client.get("/private/deep-link").status_code == 200


def test_login_failure_limit_returns_fixed_429_without_echo(tmp_path: Path) -> None:
    settings = _authenticated_settings(tmp_path)
    sentinel = "incorrect-private-credential-sentinel"

    with TestClient(api_module.create_api_app(settings), base_url=TEST_OPERATOR_ORIGIN) as client:
        for _ in range(5):
            response = client.post(
                "/api/v1/operator-auth/login",
                json={"credential": sentinel},
                headers={"Origin": TEST_OPERATOR_ORIGIN},
            )
            assert response.status_code == 401
        limited = client.post(
            "/api/v1/operator-auth/login",
            json={"credential": TEST_OPERATOR_CREDENTIAL},
            headers={"Origin": TEST_OPERATOR_ORIGIN},
        )

    assert limited.status_code == 429
    assert limited.json() == {"detail": "operator_login_rate_limited"}
    assert 1 <= int(limited.headers["retry-after"]) <= 60
    assert sentinel not in limited.text


@pytest.mark.parametrize(
    ("body", "content_type", "status_code", "detail"),
    [
        (b'{"credential":"one","credential":"two"}', "application/json", 400, "operator_login_request_invalid"),
        (b'{"credential":"one","extra":true}', "application/json", 400, "operator_login_request_invalid"),
        (b'{"credential":1}', "application/json", 400, "operator_login_request_invalid"),
        (b'{"credential":NaN}', "application/json", 400, "operator_login_request_invalid"),
        (b"[" * 1_100 + b"0" + b"]" * 1_100, "application/json", 400, "operator_login_request_invalid"),
        (b"not-json", "application/json", 400, "operator_login_request_invalid"),
        (b'{"credential":"value"}', "text/plain", 415, "operator_login_content_type_invalid"),
        (b"x" * 8_193, "application/json", 413, "operator_login_body_too_large"),
    ],
)
def test_login_body_is_bounded_single_field_strict_json(
    tmp_path: Path,
    body: bytes,
    content_type: str,
    status_code: int,
    detail: str,
) -> None:
    settings = _authenticated_settings(tmp_path)
    client = TestClient(api_module.create_api_app(settings), base_url=TEST_OPERATOR_ORIGIN)

    response = client.post(
        "/api/v1/operator-auth/login",
        content=body,
        headers={"Origin": TEST_OPERATOR_ORIGIN, "Content-Type": content_type},
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert response.headers["cache-control"] == "no-store"
    assert "one" not in response.text
    assert "two" not in response.text


def test_public_build_notice_head_response_has_no_asgi_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_module, "_resolve_web_root", lambda: None)
    app = api_module.create_api_app(_authenticated_settings(tmp_path))

    async def exchange() -> list[Message]:
        messages: list[Message] = []
        request_sent = False

        async def receive() -> Message:
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            messages.append(message)

        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": "HEAD",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"127.0.0.1:8632")],
            "client": ("testclient", 50_000),
            "server": ("127.0.0.1", 8632),
            "state": {},
        }
        await app(scope, receive, send)
        return messages

    messages = asyncio.run(exchange())
    starts = [message for message in messages if message["type"] == "http.response.start"]
    assert len(starts) == 1
    assert starts[0]["status"] == 200
    assert int(dict(starts[0]["headers"])[b"content-length"]) > 0
    assert all(message.get("body", b"") == b"" for message in messages if message["type"] == "http.response.body")


def test_missing_build_root_and_protected_legacy_are_inert_notices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_module, "_resolve_web_root", lambda: None)
    app = api_module.create_api_app(_authenticated_settings(tmp_path))
    client = TestClient(app, base_url=TEST_OPERATOR_ORIGIN)

    notice = client.get("/?credential=private-query-sentinel")
    assert notice.status_code == 200
    assert "Console build missing" in notice.text
    assert "pnpm build" in notice.text
    assert "uv run media-sync --help" in notice.text
    assert notice.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in notice.headers["content-security-policy"]
    assert "private-query-sentinel" not in notice.text
    for forbidden in ("<script", "<form", "<input", "<button", "fetch(", "{{NOTICE_"):
        assert forbidden not in notice.text
    for method in ("GET", "HEAD"):
        refused = client.request(method, "/legacy", headers={"Accept": "text/html"}, follow_redirects=False)
        assert refused.status_code == 401
        assert "location" not in refused.headers

    login = client.post(
        "/api/v1/operator-auth/login",
        json={"credential": TEST_OPERATOR_CREDENTIAL},
        headers={"Origin": TEST_OPERATOR_ORIGIN},
    )
    assert login.status_code == 200
    legacy = client.get("/legacy")
    assert legacy.status_code == 200
    assert "Legacy console retired" in legacy.text
    assert "Console build missing" not in legacy.text
    assert '<a href="/">' in legacy.text
    assert legacy.headers["cache-control"] == "no-store"
    for forbidden in ("<script", "<form", "<input", "<button", "fetch(", "{{NOTICE_"):
        assert forbidden not in legacy.text
    head = client.head("/legacy")
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-length"] == legacy.headers["content-length"]


def test_browser_deep_link_redirect_login_and_authenticated_spa(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_root = tmp_path / "web"
    web_root.mkdir()
    (web_root / "index.html").write_text("<!doctype html><title>Console v2</title>", encoding="utf-8")
    monkeypatch.setattr(api_module, "_resolve_web_root", lambda: web_root)
    app = api_module.create_api_app(_authenticated_settings(tmp_path))
    client = TestClient(app, base_url=TEST_OPERATOR_ORIGIN)

    redirected = client.get(
        "/subscriptions?return_to=https://evil.example&credential=private-query-sentinel",
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        follow_redirects=False,
    )
    assert redirected.status_code == 303
    assert redirected.headers["location"] == "/?return_to=%2Fsubscriptions"
    public_login = client.get(redirected.headers["location"])
    assert public_login.status_code == 200
    assert "Console v2" in public_login.text
    assert "private-query-sentinel" not in public_login.text
    login = client.post(
        "/api/v1/operator-auth/login",
        json={"credential": TEST_OPERATOR_CREDENTIAL},
        headers={"Origin": TEST_OPERATOR_ORIGIN},
    )
    assert login.status_code == 200
    authenticated = client.get("/subscriptions", headers={"Accept": "text/html"}, follow_redirects=False)
    assert authenticated.status_code == 200
    assert "location" not in authenticated.headers
    assert "Console v2" in authenticated.text


def test_https_origin_sets_secure_host_only_cookie_for_non_loopback_bind(tmp_path: Path) -> None:
    secret_root = tmp_path / "state" / "secrets"
    secret_root.mkdir(parents=True)
    (secret_root / "browser.txt").write_text(TEST_OPERATOR_CREDENTIAL, encoding="utf-8")
    origin = "https://console.example"
    settings = Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "exports",
        job_dir=tmp_path / "jobs",
        api_host="0.0.0.0",
        operator_credential_secret_ref="file:browser.txt",
        operator_allowed_origins=(origin,),
        _env_file=None,
    )

    client = TestClient(api_module.create_api_app(settings), base_url=origin)
    response = client.post(
        "/api/v1/operator-auth/login",
        json={"credential": TEST_OPERATOR_CREDENTIAL},
        headers={"Origin": origin},
    )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie
    assert "domain=" not in cookie
