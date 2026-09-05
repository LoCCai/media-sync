"""Fail-closed single-operator authentication primitives.

This module deliberately owns no FastAPI route.  It provides a small,
process-local runtime and a pure ASGI boundary so the interface layer can wire
login/session/logout contracts without weakening authentication in tests or
future routes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import logging
import math
import re
import secrets
import threading
import time
import unicodedata
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .paths import PathSecurityError, assert_existing_regular_file
from .secrets import SecretError, SecretReference, SecretResolver, SecretValue

MIN_OPERATOR_SECRET_BYTES = 16
MAX_OPERATOR_SECRET_BYTES = 1_024
MIN_OPERATOR_SESSION_TTL_SECONDS = 60
MAX_OPERATOR_SESSION_TTL_SECONDS = 8 * 60 * 60
MAX_OPERATOR_ORIGINS = 8
MAX_OPERATOR_ORIGIN_BYTES = 2_048
OPERATOR_SESSION_COOKIE_NAME = "media_sync_operator_session"
OPERATOR_CSRF_HEADER_NAME = "x-media-sync-csrf"
OPERATOR_AUTH_SCOPE_KEY = "media_sync.operator_auth_method"

_TOKEN_BYTES = 32
_TOKEN_TEXT_LENGTH = 43
_MAX_COOKIE_HEADER_BYTES = 4_096
_MAX_AUTHORIZATION_HEADER_BYTES = MAX_OPERATOR_SECRET_BYTES + 16
_MAX_HOST_HEADER_BYTES = 512
_DEFAULT_LOGIN_FAILURE_LIMIT = 5
_DEFAULT_LOGIN_FAILURE_WINDOW_SECONDS = 60
_DEFAULT_MINIMUM_LOGIN_SECONDS = 0.075
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_PUBLIC_ROUTES = frozenset(
    {
        ("GET", "/api/v1/health"),
        ("HEAD", "/api/v1/health"),
        ("GET", "/api/v1/ready"),
        ("HEAD", "/api/v1/ready"),
        ("POST", "/api/v1/operator-auth/login"),
        ("GET", "/api/v1/operator-auth/session"),
        ("GET", "/"),
        ("HEAD", "/"),
        ("GET", "/favicon.svg"),
        ("HEAD", "/favicon.svg"),
        ("GET", "/_app/version.json"),
        ("HEAD", "/_app/version.json"),
    }
)
_DEFAULT_BROWSER_ONLY_ROUTES = frozenset(
    {
        ("POST", "/api/v1/operator-auth/logout"),
        ("POST", "/api/v1/media-server/playback-evidence"),
    }
)
_STATIC_COMPONENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*\Z")
_OPAQUE_TOKEN = re.compile(rf"[A-Za-z0-9_-]{{{_TOKEN_TEXT_LENGTH}}}\Z")
_BEARER_TOKEN = re.compile(r"[A-Za-z0-9\-._~+/]+={0,2}\Z")
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_LOGGER = logging.getLogger(__name__)
_DUMMY_DIGEST = hashlib.sha256(b"media-sync:operator-auth:dummy:v1").digest()


class OperatorAuthConfigurationError(ValueError):
    """A redaction-safe startup rejection for an invalid auth boundary."""

    code = "operator_auth_configuration_invalid"

    def __init__(self) -> None:
        super().__init__(self.code)


class OperatorAuthErrorCode(StrEnum):
    """Fixed public failure codes; none contain request-derived values."""

    AUTH_REQUIRED = "operator_auth_required"
    BROWSER_SESSION_REQUIRED = "operator_browser_session_required"
    CSRF_FORBIDDEN = "operator_csrf_forbidden"
    HOST_FORBIDDEN = "operator_host_forbidden"
    LOGIN_FAILED = "operator_login_failed"
    LOGIN_RATE_LIMITED = "operator_login_rate_limited"
    ORIGIN_FORBIDDEN = "operator_origin_forbidden"


class OperatorAuditCode(StrEnum):
    """The complete fixed-code audit vocabulary owned by this runtime."""

    LOGIN_SUCCEEDED = "operator_login_succeeded"
    LOGIN_FAILED = "operator_login_failed"
    LOGIN_RATE_LIMITED = "operator_login_rate_limited"
    LOGOUT_SUCCEEDED = "operator_logout_succeeded"
    SESSION_EXPIRED = "operator_session_expired"


class OperatorAuthMethod(StrEnum):
    """Non-secret authentication authority attached to one ASGI request."""

    BROWSER = "browser"
    BEARER = "bearer"


class OperatorLoginRejected(RuntimeError):
    """A fixed, redaction-safe login rejection."""

    def __init__(
        self,
        code: OperatorAuthErrorCode,
        *,
        status_code: int,
        retry_after_seconds: int | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class OperatorOriginPolicy:
    """Canonical browser origins and the exact Host authorities they imply."""

    origins: tuple[str, ...]
    allowed_hosts: frozenset[str]
    secure_cookie: bool

    def allows_host(self, value: str | None) -> bool:
        """Accept only an exact, already-canonical Host authority."""

        return _bounded_ascii(value, max_bytes=_MAX_HOST_HEADER_BYTES) in self.allowed_hosts

    def allows_origin(self, value: str | None) -> bool:
        """Accept only an exact configured Origin; ``null`` is never authority."""

        return _bounded_ascii(value, max_bytes=MAX_OPERATOR_ORIGIN_BYTES) in self.origins


@dataclass(frozen=True, slots=True)
class IssuedOperatorSession:
    """One newly issued browser session; secrets never appear in repr."""

    cookie_value: str = field(repr=False)
    csrf_token: str = field(repr=False)
    max_age_seconds: int


@dataclass(frozen=True, slots=True)
class OperatorSessionView:
    """The bounded session bootstrap returned after cookie authentication."""

    csrf_token: str = field(repr=False)
    expires_in_seconds: int


@dataclass(slots=True)
class _OperatorSessionState:
    cookie_digest: bytes = field(repr=False)
    csrf_token: str = field(repr=False)
    csrf_digest: bytes = field(repr=False)
    expires_at: float = field(repr=False)


class _GlobalFailureLimiter:
    """One bounded, client-agnostic sliding-window failure limiter."""

    __slots__ = ("_failures", "_limit", "_window_seconds")

    def __init__(self, *, limit: int, window_seconds: int) -> None:
        if type(limit) is not int or limit < 1 or type(window_seconds) is not int or window_seconds < 1:
            raise OperatorAuthConfigurationError
        self._limit = limit
        self._window_seconds = window_seconds
        self._failures: deque[float] = deque(maxlen=limit)

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._failures and self._failures[0] <= cutoff:
            self._failures.popleft()

    def retry_after(self, now: float) -> int | None:
        self._prune(now)
        if len(self._failures) < self._limit:
            return None
        return max(1, math.ceil(self._failures[0] + self._window_seconds - now))

    def record_failure(self, now: float) -> None:
        self._prune(now)
        if len(self._failures) < self._limit:
            self._failures.append(now)

    def clear(self) -> None:
        self._failures.clear()


def _default_audit_sink(code: OperatorAuditCode) -> None:
    _LOGGER.info("%s", code.value)


def _bounded_ascii(value: str | None, *, max_bytes: int) -> str | None:
    if type(value) is not str or not value or len(value) > max_bytes:
        return None
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError:
        return None
    if len(encoded) > max_bytes or any(byte < 0x20 or byte == 0x7F for byte in encoded):
        return None
    return value


def _secret_bytes(secret: SecretValue, *, bearer: bool) -> bytes:
    if not isinstance(secret, SecretValue):
        raise OperatorAuthConfigurationError
    value = secret.reveal()
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as error:  # pragma: no cover - Python strings normally encode cleanly
        raise OperatorAuthConfigurationError from error
    if not MIN_OPERATOR_SECRET_BYTES <= len(encoded) <= MAX_OPERATOR_SECRET_BYTES:
        raise OperatorAuthConfigurationError
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise OperatorAuthConfigurationError
    if len(set(value)) < 4:
        raise OperatorAuthConfigurationError
    if bearer and (
        _bounded_ascii(value, max_bytes=MAX_OPERATOR_SECRET_BYTES) is None or _BEARER_TOKEN.fullmatch(value) is None
    ):
        raise OperatorAuthConfigurationError
    return encoded


def validate_operator_secrets(
    browser_credential: SecretValue,
    bearer_token: SecretValue | None = None,
) -> None:
    """Apply the dedicated bounded/weak-secret rules without retaining input."""

    browser_bytes = _secret_bytes(browser_credential, bearer=False)
    if bearer_token is None:
        return
    bearer_bytes = _secret_bytes(bearer_token, bearer=True)
    browser_digest = hashlib.sha256(browser_bytes).digest()
    bearer_digest = hashlib.sha256(bearer_bytes).digest()
    if hmac.compare_digest(browser_digest, bearer_digest):
        raise OperatorAuthConfigurationError


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _canonical_dns_or_ip_host(host: str) -> str:
    if not host or len(host) > 253 or host != host.lower() or host.endswith(".") or "%" in host:
        raise OperatorAuthConfigurationError
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if any(_DNS_LABEL.fullmatch(label) is None for label in host.split(".")):
            raise OperatorAuthConfigurationError from None
        return host
    canonical = address.compressed.lower()
    if host != canonical:
        raise OperatorAuthConfigurationError
    return canonical


def _canonical_origin(value: str) -> tuple[str, str, str]:
    raw = _bounded_ascii(value, max_bytes=MAX_OPERATOR_ORIGIN_BYTES)
    if raw is None or raw != raw.strip() or "\\" in raw or "*" in raw:
        raise OperatorAuthConfigurationError
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as error:
        raise OperatorAuthConfigurationError from error
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
    ):
        raise OperatorAuthConfigurationError
    host = _canonical_dns_or_ip_host(parsed.hostname)
    if parsed.scheme == "http" and not _is_loopback_host(host):
        raise OperatorAuthConfigurationError
    effective_port = port if port is not None else (80 if parsed.scheme == "http" else 443)
    if not 1 <= effective_port <= 65_535:  # pragma: no cover - urlsplit enforces this
        raise OperatorAuthConfigurationError
    bracketed = f"[{host}]" if ":" in host else host
    default_port = 80 if parsed.scheme == "http" else 443
    authority = bracketed if effective_port == default_port else f"{bracketed}:{effective_port}"
    canonical = f"{parsed.scheme}://{authority}"
    if raw != canonical:
        raise OperatorAuthConfigurationError
    return canonical, authority, parsed.scheme


def _canonical_loopback_bind_host(value: str) -> str | None:
    raw = _bounded_ascii(value, max_bytes=253)
    if raw is None or raw != raw.strip() or raw != raw.lower():
        return None
    if raw == "localhost":
        return raw
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return None
    if not address.is_loopback or raw != address.compressed.lower():
        return None
    return raw


def derive_operator_origin_policy(
    bind_host: str,
    bind_port: int,
    configured_origins: Sequence[str] | None,
) -> OperatorOriginPolicy:
    """Derive exact Host authority from loopback, or validate explicit origins."""

    if type(bind_port) is not int or not 1 <= bind_port <= 65_535:
        raise OperatorAuthConfigurationError
    loopback_host = _canonical_loopback_bind_host(bind_host)
    if configured_origins is None:
        if loopback_host is None:
            raise OperatorAuthConfigurationError
        bracketed = f"[{loopback_host}]" if ":" in loopback_host else loopback_host
        authority = bracketed if bind_port == 80 else f"{bracketed}:{bind_port}"
        origin = f"http://{authority}"
        return OperatorOriginPolicy(origins=(origin,), allowed_hosts=frozenset({authority}), secure_cookie=False)
    if isinstance(configured_origins, str) or not 1 <= len(configured_origins) <= MAX_OPERATOR_ORIGINS:
        raise OperatorAuthConfigurationError
    canonical_items = tuple(_canonical_origin(value) for value in configured_origins)
    origins = tuple(item[0] for item in canonical_items)
    if len(set(origins)) != len(origins):
        raise OperatorAuthConfigurationError
    schemes = {item[2] for item in canonical_items}
    if len(schemes) != 1:
        raise OperatorAuthConfigurationError
    return OperatorOriginPolicy(
        origins=origins,
        allowed_hosts=frozenset(item[1] for item in canonical_items),
        secure_cookie=schemes == {"https"},
    )


def resolve_operator_auth_runtime(
    browser_reference: SecretReference | None,
    bearer_reference: SecretReference | None,
    resolver: SecretResolver,
    session_ttl_seconds: int,
) -> OperatorAuthRuntime:
    """Resolve the complete auth authority through one redaction-safe factory."""

    if browser_reference is None:
        raise OperatorAuthConfigurationError
    try:
        browser_credential = resolver.resolve(browser_reference)
        bearer_token = resolver.resolve(bearer_reference) if bearer_reference is not None else None
    except SecretError as error:
        raise OperatorAuthConfigurationError from error
    return OperatorAuthRuntime(
        browser_credential,
        bearer_token=bearer_token,
        session_ttl_seconds=session_ttl_seconds,
    )


def _domain_digest(domain: bytes, value: bytes) -> bytes:
    return hashlib.sha256(domain + b"\0" + value).digest()


def _candidate_bytes(value: object, *, bearer: bool = False, opaque: bool = False) -> bytes:
    if type(value) is not str or len(value) > MAX_OPERATOR_SECRET_BYTES:
        return _DUMMY_DIGEST
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:  # pragma: no cover - Python strings normally encode cleanly
        return _DUMMY_DIGEST
    if not encoded or len(encoded) > MAX_OPERATOR_SECRET_BYTES:
        return _DUMMY_DIGEST
    if bearer and (
        _bounded_ascii(value, max_bytes=MAX_OPERATOR_SECRET_BYTES) is None or _BEARER_TOKEN.fullmatch(value) is None
    ):
        return _DUMMY_DIGEST
    if opaque and _OPAQUE_TOKEN.fullmatch(value) is None:
        return _DUMMY_DIGEST
    return encoded


class OperatorAuthRuntime:
    """Thread-safe, process-local authority for one operator and one session."""

    def __init__(
        self,
        browser_credential: SecretValue,
        *,
        bearer_token: SecretValue | None = None,
        session_ttl_seconds: int = MAX_OPERATOR_SESSION_TTL_SECONDS,
        audit_sink: Callable[[OperatorAuditCode], None] | None = None,
        _clock: Callable[[], float] = time.monotonic,
        _sleeper: Callable[[float], None] = time.sleep,
        _random_bytes: Callable[[int], bytes] = secrets.token_bytes,
        _failure_limit: int = _DEFAULT_LOGIN_FAILURE_LIMIT,
        _failure_window_seconds: int = _DEFAULT_LOGIN_FAILURE_WINDOW_SECONDS,
        _minimum_login_seconds: float = _DEFAULT_MINIMUM_LOGIN_SECONDS,
    ) -> None:
        validate_operator_secrets(browser_credential, bearer_token)
        if (
            type(session_ttl_seconds) is not int
            or not MIN_OPERATOR_SESSION_TTL_SECONDS <= session_ttl_seconds <= MAX_OPERATOR_SESSION_TTL_SECONDS
            or not math.isfinite(_minimum_login_seconds)
            or _minimum_login_seconds < 0
        ):
            raise OperatorAuthConfigurationError
        self._browser_digest = _domain_digest(
            b"media-sync:operator-browser-credential:v1",
            browser_credential.reveal().encode(),
        )
        self._bearer_digest = (
            _domain_digest(b"media-sync:operator-bearer-credential:v1", bearer_token.reveal().encode())
            if bearer_token is not None
            else None
        )
        self._session_ttl_seconds = session_ttl_seconds
        self._audit_sink = audit_sink or _default_audit_sink
        self._clock = _clock
        self._sleeper = _sleeper
        self._random_bytes = _random_bytes
        self._minimum_login_seconds = _minimum_login_seconds
        self._limiter = _GlobalFailureLimiter(limit=_failure_limit, window_seconds=_failure_window_seconds)
        self._session: _OperatorSessionState | None = None
        self._lock = threading.RLock()

    def __repr__(self) -> str:
        return "OperatorAuthRuntime([REDACTED])"

    @property
    def bearer_enabled(self) -> bool:
        with self._lock:
            return self._bearer_digest is not None

    @property
    def session_ttl_seconds(self) -> int:
        return self._session_ttl_seconds

    def _emit(self, code: OperatorAuditCode) -> None:
        try:
            self._audit_sink(code)
        except Exception:  # pragma: no cover - a logging outage must not change authority
            _LOGGER.error("operator_auth_audit_sink_failed")

    def _new_opaque_token(self, domain: bytes) -> str:
        random_value = self._random_bytes(_TOKEN_BYTES)
        if type(random_value) is not bytes or len(random_value) != _TOKEN_BYTES:
            raise RuntimeError("operator_auth_random_source_failed")
        digest = hashlib.sha256(domain + b"\0" + random_value).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def _expire_locked(self, now: float) -> bool:
        if self._session is None or now < self._session.expires_at:
            return False
        self._session = None
        return True

    def _finish_login_delay(self, started_at: float) -> None:
        remaining = self._minimum_login_seconds - (self._clock() - started_at)
        if remaining > 0:
            self._sleeper(remaining)

    def login(self, submitted_credential: object) -> IssuedOperatorSession:
        """Verify, rate-limit, rotate, and issue one browser session."""

        started_at = self._clock()
        candidate = _candidate_bytes(submitted_credential)
        candidate_digest = _domain_digest(b"media-sync:operator-browser-credential:v1", candidate)
        result: IssuedOperatorSession | None = None
        rejection: OperatorLoginRejected | None = None
        audit_code: OperatorAuditCode
        with self._lock:
            credential_matches = hmac.compare_digest(candidate_digest, self._browser_digest)
            now = self._clock()
            retry_after = self._limiter.retry_after(now)
            if retry_after is not None:
                rejection = OperatorLoginRejected(
                    OperatorAuthErrorCode.LOGIN_RATE_LIMITED,
                    status_code=429,
                    retry_after_seconds=retry_after,
                )
                audit_code = OperatorAuditCode.LOGIN_RATE_LIMITED
            elif not credential_matches:
                self._limiter.record_failure(now)
                rejection = OperatorLoginRejected(OperatorAuthErrorCode.LOGIN_FAILED, status_code=401)
                audit_code = OperatorAuditCode.LOGIN_FAILED
            else:
                cookie = self._new_opaque_token(b"media-sync:operator-session-cookie:v1")
                csrf = self._new_opaque_token(b"media-sync:operator-session-csrf:v1")
                self._session = _OperatorSessionState(
                    cookie_digest=_domain_digest(b"media-sync:operator-session-cookie:v1", cookie.encode("ascii")),
                    csrf_token=csrf,
                    csrf_digest=_domain_digest(b"media-sync:operator-session-csrf:v1", csrf.encode("ascii")),
                    expires_at=now + self._session_ttl_seconds,
                )
                self._limiter.clear()
                result = IssuedOperatorSession(
                    cookie_value=cookie,
                    csrf_token=csrf,
                    max_age_seconds=self._session_ttl_seconds,
                )
                audit_code = OperatorAuditCode.LOGIN_SUCCEEDED
        self._finish_login_delay(started_at)
        self._emit(audit_code)
        if rejection is not None:
            raise rejection
        if result is None:  # pragma: no cover - exhaustive branches above
            raise RuntimeError("operator_auth_login_failed_closed")
        return result

    def session(self, cookie_value: object) -> OperatorSessionView | None:
        """Return CSRF bootstrap only for the current, unexpired cookie."""

        candidate = _candidate_bytes(cookie_value, opaque=True)
        candidate_digest = _domain_digest(b"media-sync:operator-session-cookie:v1", candidate)
        expired = False
        result: OperatorSessionView | None = None
        with self._lock:
            now = self._clock()
            expired = self._expire_locked(now)
            expected = self._session.cookie_digest if self._session is not None else _DUMMY_DIGEST
            matches = hmac.compare_digest(candidate_digest, expected)
            if matches and self._session is not None:
                result = OperatorSessionView(
                    csrf_token=self._session.csrf_token,
                    expires_in_seconds=max(1, math.ceil(self._session.expires_at - now)),
                )
        if expired:
            self._emit(OperatorAuditCode.SESSION_EXPIRED)
        return result

    def authenticate_bearer(self, submitted_token: object) -> bool:
        """Compare an optional, header-only bearer token in constant time."""

        candidate = _candidate_bytes(submitted_token, bearer=True)
        candidate_digest = _domain_digest(b"media-sync:operator-bearer-credential:v1", candidate)
        with self._lock:
            expected = self._bearer_digest if self._bearer_digest is not None else _DUMMY_DIGEST
            matches = hmac.compare_digest(candidate_digest, expected)
            return self._bearer_digest is not None and matches

    def authenticate(self, cookie_value: object, bearer_token: object) -> OperatorAuthMethod | None:
        """Apply the frozen browser-first, Bearer-second precedence."""

        if self.session(cookie_value) is not None:
            return OperatorAuthMethod.BROWSER
        if self.authenticate_bearer(bearer_token):
            return OperatorAuthMethod.BEARER
        return None

    def verify_cookie_csrf(self, cookie_value: object, csrf_token: object) -> bool:
        """Atomically bind CSRF proof to the still-current browser session."""

        cookie_candidate = _candidate_bytes(cookie_value, opaque=True)
        csrf_candidate = _candidate_bytes(csrf_token, opaque=True)
        cookie_digest = _domain_digest(b"media-sync:operator-session-cookie:v1", cookie_candidate)
        csrf_digest = _domain_digest(b"media-sync:operator-session-csrf:v1", csrf_candidate)
        expired = False
        with self._lock:
            expired = self._expire_locked(self._clock())
            expected_cookie = self._session.cookie_digest if self._session is not None else _DUMMY_DIGEST
            expected_csrf = self._session.csrf_digest if self._session is not None else _DUMMY_DIGEST
            cookie_matches = hmac.compare_digest(cookie_digest, expected_cookie)
            csrf_matches = hmac.compare_digest(csrf_digest, expected_csrf)
            valid = self._session is not None and cookie_matches and csrf_matches
        if expired:
            self._emit(OperatorAuditCode.SESSION_EXPIRED)
        return valid

    def logout(self, cookie_value: object) -> bool:
        """Invalidate only the exact current session; stale cookies are harmless."""

        candidate = _candidate_bytes(cookie_value, opaque=True)
        candidate_digest = _domain_digest(b"media-sync:operator-session-cookie:v1", candidate)
        expired = False
        removed = False
        with self._lock:
            expired = self._expire_locked(self._clock())
            expected = self._session.cookie_digest if self._session is not None else _DUMMY_DIGEST
            matches = hmac.compare_digest(candidate_digest, expected)
            if self._session is not None and matches:
                self._session = None
                removed = True
        if expired:
            self._emit(OperatorAuditCode.SESSION_EXPIRED)
        if removed:
            self._emit(OperatorAuditCode.LOGOUT_SUCCEEDED)
        return removed

    def rotate_credentials(
        self,
        browser_credential: SecretValue,
        bearer_token: SecretValue | None = None,
    ) -> None:
        """Replace process credentials and invalidate every prior session."""

        validate_operator_secrets(browser_credential, bearer_token)
        browser_digest = _domain_digest(
            b"media-sync:operator-browser-credential:v1",
            browser_credential.reveal().encode(),
        )
        bearer_digest = (
            _domain_digest(b"media-sync:operator-bearer-credential:v1", bearer_token.reveal().encode())
            if bearer_token is not None
            else None
        )
        with self._lock:
            self._browser_digest = browser_digest
            self._bearer_digest = bearer_digest
            self._session = None
            self._limiter.clear()


def _single_header(headers: Sequence[tuple[bytes, bytes]], name: bytes, *, max_bytes: int) -> str | None:
    values = [value for key, value in headers if key.lower() == name]
    if len(values) != 1 or not values[0] or len(values[0]) > max_bytes:
        return None
    try:
        decoded = values[0].decode("ascii")
    except UnicodeDecodeError:
        return None
    if any(character < " " or character == "\x7f" for character in decoded):
        return None
    return decoded


def session_cookie_from_headers(headers: Sequence[tuple[bytes, bytes]]) -> str | None:
    """Extract one strict opaque session cookie without accepting ambiguity."""

    raw = _single_header(headers, b"cookie", max_bytes=_MAX_COOKIE_HEADER_BYTES)
    if raw is None:
        return None
    found: str | None = None
    for component in raw.split(";"):
        item = component.strip()
        name, separator, value = item.partition("=")
        if not separator or not name:
            return None
        if name != OPERATOR_SESSION_COOKIE_NAME:
            continue
        if found is not None or _OPAQUE_TOKEN.fullmatch(value) is None:
            return None
        found = value
    return found


def bearer_token_from_headers(headers: Sequence[tuple[bytes, bytes]]) -> str | None:
    """Extract only one strict ``Authorization: Bearer`` value."""

    raw = _single_header(headers, b"authorization", max_bytes=_MAX_AUTHORIZATION_HEADER_BYTES)
    if raw is None:
        return None
    scheme, separator, token = raw.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token or " " in token:
        return None
    if len(token) > MAX_OPERATOR_SECRET_BYTES or _BEARER_TOKEN.fullmatch(token) is None:
        return None
    return token


def csrf_token_from_headers(headers: Sequence[tuple[bytes, bytes]]) -> str | None:
    """Extract one bounded CSRF header; duplicate values fail closed."""

    return _single_header(headers, OPERATOR_CSRF_HEADER_NAME.encode("ascii"), max_bytes=_TOKEN_TEXT_LENGTH)


def is_anonymous_operator_request(
    method: str,
    path: str,
    *,
    web_root: Path | None = None,
) -> bool:
    """Match the exact public table or a currently safe immutable file."""

    normalized_method = method.upper()
    if (normalized_method, path) in _PUBLIC_ROUTES:
        return True
    prefix = "/_app/immutable/"
    if normalized_method not in {"GET", "HEAD"} or not path.startswith(prefix) or web_root is None:
        return False
    relative = path.removeprefix("/")
    components = relative.split("/")
    if not components or any(_STATIC_COMPONENT.fullmatch(component) is None for component in components):
        return False
    root = web_root.absolute()
    candidate = root.joinpath(*components)
    try:
        assert_existing_regular_file(candidate, root=root)
    except PathSecurityError:
        return False
    return True


def operator_auth_method(scope: Scope) -> OperatorAuthMethod | None:
    """Read the non-secret method assigned by :class:`OperatorAuthMiddleware`."""

    state = scope.get("state")
    value = state.get(OPERATOR_AUTH_SCOPE_KEY) if isinstance(state, dict) else None
    if not isinstance(value, str):
        return None
    try:
        return OperatorAuthMethod(value)
    except ValueError:
        return None


class OperatorAuthMiddleware:
    """Pure ASGI Host/auth/origin boundary with denial as the default."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        runtime: OperatorAuthRuntime,
        origin_policy: OperatorOriginPolicy,
        web_root: Path | None = None,
        browser_only_routes: frozenset[tuple[str, str]] = _DEFAULT_BROWSER_ONLY_ROUTES,
    ) -> None:
        self.app = app
        self.runtime = runtime
        self.origin_policy = origin_policy
        self.web_root = web_root
        self.browser_only_routes = browser_only_routes

    async def _reject(
        self,
        scope: Scope,
        send: Send,
        code: OperatorAuthErrorCode,
        status_code: int,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        body = f'{{"detail":"{code.value}"}}'.encode("ascii")
        is_head = scope.get("method") == "HEAD"
        headers: list[tuple[bytes, bytes]] = [
            (b"cache-control", b"no-store"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
            (b"referrer-policy", b"no-referrer"),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
        ]
        path = scope.get("path")
        if isinstance(path, str) and not path.startswith("/api/"):
            headers.append(
                (
                    b"content-security-policy",
                    b"default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
                )
            )
        if retry_after_seconds is not None:
            headers.append((b"retry-after", str(retry_after_seconds).encode("ascii")))
        await send({"type": "http.response.start", "status": status_code, "headers": headers})
        await send({"type": "http.response.body", "body": b"" if is_head else body, "more_body": False})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope.get("type")
        if scope_type == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope_type == "websocket":
            await send({"type": "websocket.close", "code": 4403, "reason": OperatorAuthErrorCode.AUTH_REQUIRED.value})
            return
        if scope_type != "http":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", ())
        host = _single_header(headers, b"host", max_bytes=_MAX_HOST_HEADER_BYTES)
        if not self.origin_policy.allows_host(host):
            await self._reject(scope, send, OperatorAuthErrorCode.HOST_FORBIDDEN, 403)
            return

        method = str(scope.get("method", "")).upper()
        path = scope.get("path")
        if not isinstance(path, str):
            path = ""
        downstream_send = send
        if method == "HEAD":

            async def head_safe_send(message: Message) -> None:
                if message["type"] == "http.response.body":
                    message = {**message, "body": b""}
                await send(message)

            downstream_send = head_safe_send
        route = (method, path)
        origin = _single_header(headers, b"origin", max_bytes=MAX_OPERATOR_ORIGIN_BYTES)
        if route == ("POST", "/api/v1/operator-auth/login"):
            if not self.origin_policy.allows_origin(origin):
                await self._reject(scope, send, OperatorAuthErrorCode.ORIGIN_FORBIDDEN, 403)
                return
            await self.app(scope, receive, downstream_send)
            return
        if is_anonymous_operator_request(method, path, web_root=self.web_root):
            await self.app(scope, receive, downstream_send)
            return

        cookie = session_cookie_from_headers(headers)
        bearer = bearer_token_from_headers(headers)
        if route in self.browser_only_routes and any(name.lower() == b"authorization" for name, _value in headers):
            await self._reject(scope, send, OperatorAuthErrorCode.BROWSER_SESSION_REQUIRED, 403)
            return
        auth_method = self.runtime.authenticate(cookie, bearer)
        if auth_method is None:
            await self._reject(scope, send, OperatorAuthErrorCode.AUTH_REQUIRED, 401)
            return
        if route in self.browser_only_routes and auth_method is not OperatorAuthMethod.BROWSER:
            await self._reject(scope, send, OperatorAuthErrorCode.BROWSER_SESSION_REQUIRED, 403)
            return
        if auth_method is OperatorAuthMethod.BROWSER and method not in _SAFE_METHODS:
            csrf = csrf_token_from_headers(headers)
            if not self.origin_policy.allows_origin(origin):
                await self._reject(scope, send, OperatorAuthErrorCode.ORIGIN_FORBIDDEN, 403)
                return
            if not self.runtime.verify_cookie_csrf(cookie, csrf):
                await self._reject(scope, send, OperatorAuthErrorCode.CSRF_FORBIDDEN, 403)
                return

        state = scope.setdefault("state", {})
        if not isinstance(state, dict):
            await self._reject(scope, send, OperatorAuthErrorCode.AUTH_REQUIRED, 401)
            return
        state[OPERATOR_AUTH_SCOPE_KEY] = auth_method.value
        await self.app(scope, receive, downstream_send)


__all__ = [
    "MAX_OPERATOR_ORIGINS",
    "MAX_OPERATOR_SECRET_BYTES",
    "MAX_OPERATOR_SESSION_TTL_SECONDS",
    "MIN_OPERATOR_SECRET_BYTES",
    "MIN_OPERATOR_SESSION_TTL_SECONDS",
    "OPERATOR_AUTH_SCOPE_KEY",
    "OPERATOR_CSRF_HEADER_NAME",
    "OPERATOR_SESSION_COOKIE_NAME",
    "IssuedOperatorSession",
    "OperatorAuditCode",
    "OperatorAuthConfigurationError",
    "OperatorAuthErrorCode",
    "OperatorAuthMethod",
    "OperatorAuthMiddleware",
    "OperatorAuthRuntime",
    "OperatorLoginRejected",
    "OperatorOriginPolicy",
    "OperatorSessionView",
    "bearer_token_from_headers",
    "csrf_token_from_headers",
    "derive_operator_origin_policy",
    "is_anonymous_operator_request",
    "operator_auth_method",
    "resolve_operator_auth_runtime",
    "session_cookie_from_headers",
    "validate_operator_secrets",
]
