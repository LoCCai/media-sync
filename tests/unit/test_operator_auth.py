"""Single-operator runtime and deny-by-default ASGI boundary tests."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

import media_sync.security.operator_auth as operator_auth_module
from media_sync.security import (
    MAX_OPERATOR_SECRET_BYTES,
    OPERATOR_CSRF_HEADER_NAME,
    OPERATOR_SESSION_COOKIE_NAME,
    EnvironmentSecretProvider,
    OperatorAuditCode,
    OperatorAuthConfigurationError,
    OperatorAuthErrorCode,
    OperatorAuthMethod,
    OperatorAuthMiddleware,
    OperatorAuthRuntime,
    OperatorLoginRejected,
    SecretReference,
    SecretResolver,
    SecretScheme,
    SecretValue,
    bearer_token_from_headers,
    derive_operator_origin_policy,
    is_anonymous_operator_request,
    operator_auth_method,
    resolve_operator_auth_runtime,
    session_cookie_from_headers,
    validate_operator_secrets,
)

_BROWSER_CREDENTIAL = "correct-horse-battery-staple"
_BEARER_TOKEN = "automation-token-0123456789abcdef"


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _RandomBytes:
    def __init__(self) -> None:
        self.counter = 0

    def __call__(self, size: int) -> bytes:
        self.counter += 1
        return bytes([self.counter]) * size


def _runtime(
    *,
    clock: _Clock | None = None,
    audit: list[OperatorAuditCode] | None = None,
    bearer: bool = True,
    failure_limit: int = 5,
    minimum_login_seconds: float = 0,
) -> OperatorAuthRuntime:
    resolved_clock = clock or _Clock()
    return OperatorAuthRuntime(
        SecretValue(_BROWSER_CREDENTIAL),
        bearer_token=SecretValue(_BEARER_TOKEN) if bearer else None,
        session_ttl_seconds=60,
        audit_sink=(audit.append if audit is not None else lambda _code: None),
        _clock=resolved_clock,
        _sleeper=resolved_clock.sleep,
        _random_bytes=_RandomBytes(),
        _failure_limit=failure_limit,
        _failure_window_seconds=10,
        _minimum_login_seconds=minimum_login_seconds,
    )


@pytest.mark.parametrize(
    "value",
    [
        "short",
        "a" * 32,
        "valid-looking-secret\n",
        "x" * (MAX_OPERATOR_SECRET_BYTES + 1),
    ],
)
def test_operator_secret_validation_rejects_weak_control_and_oversized_values(value: str) -> None:
    with pytest.raises(OperatorAuthConfigurationError, match=r"^operator_auth_configuration_invalid$"):
        validate_operator_secrets(SecretValue(value))


def test_operator_secret_validation_requires_distinct_header_safe_bearer() -> None:
    validate_operator_secrets(SecretValue(_BROWSER_CREDENTIAL), SecretValue(_BEARER_TOKEN))

    for bearer in (_BROWSER_CREDENTIAL, "bearer token with spaces", "令牌-0123456789abcdef"):
        with pytest.raises(OperatorAuthConfigurationError):
            validate_operator_secrets(SecretValue(_BROWSER_CREDENTIAL), SecretValue(bearer))


def test_runtime_factory_collapses_missing_and_resolution_failures() -> None:
    resolver = SecretResolver(
        {
            SecretScheme.ENV: EnvironmentSecretProvider(
                {
                    "MEDIA_SYNC_BROWSER_TEST": _BROWSER_CREDENTIAL,
                    "MEDIA_SYNC_BEARER_TEST": _BEARER_TOKEN,
                }
            )
        }
    )

    runtime = resolve_operator_auth_runtime(
        SecretReference.parse("env:MEDIA_SYNC_BROWSER_TEST"),
        SecretReference.parse("env:MEDIA_SYNC_BEARER_TEST"),
        resolver,
        60,
    )
    assert runtime.bearer_enabled

    for reference in (None, SecretReference.parse("env:MEDIA_SYNC_MISSING")):
        with pytest.raises(OperatorAuthConfigurationError) as raised:
            resolve_operator_auth_runtime(reference, None, resolver, 60)
        assert str(raised.value) == "operator_auth_configuration_invalid"
        assert "MEDIA_SYNC_MISSING" not in str(raised.value)


def test_runtime_rotates_expires_logs_out_and_does_not_survive_restart() -> None:
    clock = _Clock()
    audit: list[OperatorAuditCode] = []
    runtime = _runtime(clock=clock, audit=audit)

    first = runtime.login(_BROWSER_CREDENTIAL)
    assert _BROWSER_CREDENTIAL not in repr(runtime)
    assert first.cookie_value not in repr(first)
    assert first.csrf_token not in repr(first)
    assert runtime.session(first.cookie_value) is not None
    assert runtime.verify_cookie_csrf(first.cookie_value, first.csrf_token)

    second = runtime.login(_BROWSER_CREDENTIAL)
    assert runtime.session(first.cookie_value) is None
    assert runtime.session(second.cookie_value) is not None
    assert not _runtime().session(second.cookie_value)

    assert runtime.logout(second.cookie_value)
    assert runtime.session(second.cookie_value) is None

    third = runtime.login(_BROWSER_CREDENTIAL)
    clock.advance(60)
    assert runtime.session(third.cookie_value) is None
    assert runtime.session(third.cookie_value) is None
    assert audit == [
        OperatorAuditCode.LOGIN_SUCCEEDED,
        OperatorAuditCode.LOGIN_SUCCEEDED,
        OperatorAuditCode.LOGOUT_SUCCEEDED,
        OperatorAuditCode.LOGIN_SUCCEEDED,
        OperatorAuditCode.SESSION_EXPIRED,
    ]


def test_runtime_credential_rotation_invalidates_session_and_bearer() -> None:
    runtime = _runtime()
    issued = runtime.login(_BROWSER_CREDENTIAL)
    assert runtime.authenticate("invalid", _BEARER_TOKEN) is OperatorAuthMethod.BEARER

    runtime.rotate_credentials(
        SecretValue("another-correct-horse-battery"),
        SecretValue("another-automation-token-abcdef"),
    )

    assert runtime.session(issued.cookie_value) is None
    assert not runtime.authenticate_bearer(_BEARER_TOKEN)
    assert runtime.authenticate_bearer("another-automation-token-abcdef")


def test_concurrent_old_credential_login_cannot_survive_completed_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(bearer=False)
    comparison_started = threading.Event()
    release_comparison = threading.Event()
    rotation_started = threading.Event()
    rotation_completed = threading.Event()
    issued_sessions: list[object] = []
    login_errors: list[BaseException] = []
    original_compare = operator_auth_module.hmac.compare_digest

    def controlled_compare(left: bytes, right: bytes) -> bool:
        result = original_compare(left, right)
        if threading.current_thread().name == "old-login" and right is runtime._browser_digest:
            comparison_started.set()
            assert release_comparison.wait(5)
        return result

    def login_with_old_credential() -> None:
        try:
            issued_sessions.append(runtime.login(_BROWSER_CREDENTIAL))
        except BaseException as error:  # pragma: no cover - asserted below
            login_errors.append(error)

    def rotate() -> None:
        rotation_started.set()
        runtime.rotate_credentials(SecretValue("replacement-browser-credential-012345"))
        rotation_completed.set()

    monkeypatch.setattr(operator_auth_module.hmac, "compare_digest", controlled_compare)
    login_thread = threading.Thread(target=login_with_old_credential, name="old-login")
    rotation_thread = threading.Thread(target=rotate, name="credential-rotation")
    login_thread.start()
    assert comparison_started.wait(5)
    rotation_thread.start()
    assert rotation_started.wait(5)
    rotation_completed.wait(0.1)
    release_comparison.set()
    login_thread.join(5)
    rotation_thread.join(5)

    assert not login_thread.is_alive()
    assert not rotation_thread.is_alive()
    assert rotation_completed.is_set()
    assert login_errors == []
    assert len(issued_sessions) == 1
    assert runtime.session(issued_sessions[0].cookie_value) is None  # type: ignore[attr-defined]


def test_global_failure_limiter_is_bounded_deterministic_and_recovers() -> None:
    clock = _Clock()
    audit: list[OperatorAuditCode] = []
    runtime = _runtime(
        clock=clock,
        audit=audit,
        failure_limit=2,
        minimum_login_seconds=0.25,
    )

    for _ in range(2):
        before = clock()
        with pytest.raises(OperatorLoginRejected) as raised:
            runtime.login("incorrect-credential-value")
        assert raised.value.code is OperatorAuthErrorCode.LOGIN_FAILED
        assert clock() - before == pytest.approx(0.25)

    with pytest.raises(OperatorLoginRejected) as limited:
        runtime.login(_BROWSER_CREDENTIAL)
    assert limited.value.code is OperatorAuthErrorCode.LOGIN_RATE_LIMITED
    assert limited.value.status_code == 429
    assert 1 <= (limited.value.retry_after_seconds or 0) <= 10

    clock.advance(11)
    assert runtime.login(_BROWSER_CREDENTIAL)
    assert audit == [
        OperatorAuditCode.LOGIN_FAILED,
        OperatorAuditCode.LOGIN_FAILED,
        OperatorAuditCode.LOGIN_RATE_LIMITED,
        OperatorAuditCode.LOGIN_SUCCEEDED,
    ]


def test_loopback_origin_derivation_and_exact_header_matching() -> None:
    policy = derive_operator_origin_policy("127.0.0.1", 8632, None)

    assert policy.origins == ("http://127.0.0.1:8632",)
    assert policy.allowed_hosts == frozenset({"127.0.0.1:8632"})
    assert not policy.secure_cookie
    assert policy.allows_host("127.0.0.1:8632")
    assert not policy.allows_host("127.0.0.1")
    assert policy.allows_origin("http://127.0.0.1:8632")
    assert not policy.allows_origin("http://127.0.0.1:8632/")

    ipv6 = derive_operator_origin_policy("::1", 80, None)
    assert ipv6.origins == ("http://[::1]",)
    assert ipv6.allowed_hosts == frozenset({"[::1]"})


def test_non_loopback_bind_requires_explicit_canonical_browser_origins() -> None:
    loopback_http = derive_operator_origin_policy(
        "0.0.0.0",
        8632,
        ("http://127.0.0.1:8632",),
    )
    assert loopback_http.origins == ("http://127.0.0.1:8632",)
    assert loopback_http.allowed_hosts == frozenset({"127.0.0.1:8632"})
    assert not loopback_http.secure_cookie

    policy = derive_operator_origin_policy(
        "0.0.0.0",
        8632,
        ("https://media.example", "https://media.example:8443"),
    )
    assert policy.secure_cookie
    assert policy.allowed_hosts == frozenset({"media.example", "media.example:8443"})

    invalid_origins: tuple[tuple[str, ...] | None, ...] = (
        None,
        (),
        ("http://media.example",),
        ("https://MEDIA.example",),
        ("https://media.example/",),
        ("https://*.example",),
        ("https://例子.example",),
        ("https://media.example", "https://media.example"),
    )
    for origins in invalid_origins:
        with pytest.raises(OperatorAuthConfigurationError):
            derive_operator_origin_policy("0.0.0.0", 8632, origins)


def test_anonymous_table_is_exact_and_immutable_files_must_exist_as_regular_files(tmp_path: Path) -> None:
    immutable = tmp_path / "_app" / "immutable" / "chunks"
    immutable.mkdir(parents=True)
    (immutable / "app.js").write_text("export {};", encoding="utf-8")

    assert is_anonymous_operator_request("GET", "/api/v1/health")
    assert is_anonymous_operator_request("HEAD", "/")
    assert is_anonymous_operator_request("GET", "/_app/immutable/chunks/app.js", web_root=tmp_path)
    assert not is_anonymous_operator_request("POST", "/api/v1/health")
    assert not is_anonymous_operator_request("POST", "/api/v1/operator-auth/session")
    assert not is_anonymous_operator_request("GET", "/api/v1/settings")
    assert not is_anonymous_operator_request("GET", "/legacy")
    assert not is_anonymous_operator_request("GET", "/deep/link")
    assert not is_anonymous_operator_request("GET", "/_app/immutable/chunks/missing.js", web_root=tmp_path)
    assert not is_anonymous_operator_request("GET", "/_app/immutable/../version.json", web_root=tmp_path)


def test_strict_cookie_and_bearer_extractors_reject_duplicates_and_wrong_channels() -> None:
    runtime = _runtime()
    issued = runtime.login(_BROWSER_CREDENTIAL)
    cookie = f"{OPERATOR_SESSION_COOKIE_NAME}={issued.cookie_value}".encode()

    assert session_cookie_from_headers([(b"cookie", cookie)]) == issued.cookie_value
    assert session_cookie_from_headers([(b"cookie", cookie + b"; " + cookie)]) is None
    assert session_cookie_from_headers([(b"cookie", cookie), (b"cookie", cookie)]) is None
    assert bearer_token_from_headers([(b"authorization", f"Bearer {_BEARER_TOKEN}".encode())]) == _BEARER_TOKEN
    assert bearer_token_from_headers([(b"authorization", f"Bearer  {_BEARER_TOKEN}".encode())]) is None
    assert bearer_token_from_headers([(b"cookie", f"bearer={_BEARER_TOKEN}".encode())]) is None


def _middleware_client(
    runtime: OperatorAuthRuntime,
) -> tuple[TestClient, list[tuple[str, str, OperatorAuthMethod | None]]]:
    entered: list[tuple[str, str, OperatorAuthMethod | None]] = []

    async def endpoint(request: Request) -> JSONResponse:
        entered.append((request.method, request.url.path, operator_auth_method(request.scope)))
        return JSONResponse({"entered": True})

    routes = [
        Route("/api/v1/health", endpoint, methods=["GET"]),
        Route("/api/v1/operator-auth/login", endpoint, methods=["POST"]),
        Route("/private", endpoint, methods=["GET", "HEAD"]),
        Route("/mutate", endpoint, methods=["POST"]),
        Route("/api/v1/operator-auth/logout", endpoint, methods=["POST"]),
        Route("/api/v1/media-server/playback-evidence", endpoint, methods=["POST"]),
    ]
    app = OperatorAuthMiddleware(
        Starlette(routes=routes),
        runtime=runtime,
        origin_policy=derive_operator_origin_policy("127.0.0.1", 8632, None),
    )
    return TestClient(app, base_url="http://127.0.0.1:8632"), entered


def _browser_headers(issued_cookie: str, csrf: str | None = None) -> dict[str, str]:
    headers = {"cookie": f"{OPERATOR_SESSION_COOKIE_NAME}={issued_cookie}"}
    if csrf is not None:
        headers["origin"] = "http://127.0.0.1:8632"
        headers[OPERATOR_CSRF_HEADER_NAME] = csrf
    return headers


def test_middleware_denies_before_handler_and_preserves_head_security_headers() -> None:
    client, entered = _middleware_client(_runtime())

    assert client.get("/api/v1/health").status_code == 200
    rejected = client.get("/private")
    assert rejected.status_code == 401
    assert rejected.json() == {"detail": "operator_auth_required"}
    assert rejected.headers["cache-control"] == "no-store"
    assert rejected.headers["x-content-type-options"] == "nosniff"

    head = client.head("/private")
    assert head.status_code == 401
    assert head.content == b""
    assert head.headers["content-length"] == str(len(b'{"detail":"operator_auth_required"}'))
    assert entered == [("GET", "/api/v1/health", None)]


def test_middleware_host_login_origin_browser_csrf_and_bearer_precedence() -> None:
    runtime = _runtime()
    client, entered = _middleware_client(runtime)
    issued = runtime.login(_BROWSER_CREDENTIAL)

    assert client.get("/private", headers={"host": "evil.example"}).status_code == 403
    assert client.post("/api/v1/operator-auth/login").status_code == 403
    assert (
        client.post(
            "/api/v1/operator-auth/login",
            headers={"origin": "http://127.0.0.1:8632"},
        ).status_code
        == 200
    )

    browser_headers = _browser_headers(issued.cookie_value)
    assert client.get("/private", headers=browser_headers).status_code == 200
    assert client.post("/mutate", headers=browser_headers).status_code == 403
    assert client.post("/mutate", headers=_browser_headers(issued.cookie_value, "wrong")).status_code == 403
    assert client.post("/mutate", headers=_browser_headers(issued.cookie_value, issued.csrf_token)).status_code == 200

    bearer_headers = {"authorization": f"Bearer {_BEARER_TOKEN}"}
    assert client.get("/private", headers=bearer_headers).status_code == 200
    assert client.post("/mutate", headers=bearer_headers).status_code == 200
    browser_only = client.post("/api/v1/media-server/playback-evidence", headers=bearer_headers)
    assert browser_only.status_code == 403
    assert browser_only.json() == {"detail": "operator_browser_session_required"}
    cookie_and_bearer = _browser_headers(issued.cookie_value, issued.csrf_token)
    cookie_and_bearer.update(bearer_headers)
    mixed_authority = client.post(
        "/api/v1/media-server/playback-evidence",
        headers=cookie_and_bearer,
    )
    assert mixed_authority.status_code == 403
    assert mixed_authority.json() == {"detail": "operator_browser_session_required"}
    assert not any(path == "/api/v1/media-server/playback-evidence" for _method, path, _auth in entered)

    assert ("POST", "/mutate", OperatorAuthMethod.BROWSER) in entered
    assert ("POST", "/mutate", OperatorAuthMethod.BEARER) in entered


def test_middleware_does_not_trust_forwarded_authority() -> None:
    runtime = _runtime()
    client, entered = _middleware_client(runtime)
    issued = runtime.login(_BROWSER_CREDENTIAL)
    headers = _browser_headers(issued.cookie_value)
    headers.update(
        {
            "host": "evil.example",
            "x-forwarded-host": "127.0.0.1:8632",
            "x-forwarded-proto": "http",
        }
    )

    response = client.get("/private", headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "operator_host_forbidden"}
    assert entered == []


@pytest.mark.parametrize("factory", [lambda: _runtime(bearer=False), lambda: _runtime()])
def test_runtime_never_accepts_tokens_from_unconfigured_or_wrong_values(
    factory: Callable[[], OperatorAuthRuntime],
) -> None:
    runtime = factory()
    assert not runtime.authenticate_bearer("wrong-automation-token-abcdef")
