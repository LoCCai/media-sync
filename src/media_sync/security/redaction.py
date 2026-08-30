"""Recursive, deterministic redaction for persistence and operator output."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final
from urllib.parse import parse_qsl, unquote, unquote_plus, urlencode, urlsplit, urlunsplit

from .secrets import InvalidSecretReferenceError, SecretReference, SecretValue

REDACTED: Final = "[REDACTED]"
TRUNCATED: Final = "[TRUNCATED]"

_SECRET_KEY = re.compile(
    r"(?:^|[_-])(?:auth(?:orization)?|cookie|csrf|passwd|password|secret|session|sign(?:ature)?|token)(?:$|[_-])",
    re.IGNORECASE,
)
_COMPOSITE_SECRET_KEY = re.compile(r"(?:^|_)(?:api|access)_?key(?:$|_)")
_SECRET_KEY_NAMES = frozenset(
    {
        "ac_time_value",
        "a1",
        "access_key",
        "accesskey",
        "api_key",
        "apikey",
        "bili_jct",
        "mstoken",
        "private_key",
        "refresh_token",
        "sessdata",
        "signing_key",
        "webid",
        "x_api_key",
        "xapikey",
    }
)
_SECRET_QUERY_NAMES = frozenset(
    {
        "a_bogus",
        "access_key",
        "access_token",
        "api_key",
        "auth",
        "auth_key",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "csrf",
        "expires",
        "hdnts",
        "key_pair_id",
        "ms_token",
        "mstoken",
        "password",
        "policy",
        "session",
        "sig",
        "sign",
        "signature",
        "token",
        "tx_secret",
        "txsecret",
        "upsig",
        "w_rid",
        "ws_secret",
        "wssecret",
        "x_amz_credential",
        "x_amz_security_token",
        "x_amz_signature",
        "x_api_key",
        "x_bogus",
        "x_goog_credential",
        "x_goog_signature",
        "xsec_token",
        "xsectoken",
    }
)
_INLINE_ASSIGNMENT = re.compile(
    r"(?i)(?<![?&\w-])\b(authorization|cookie|csrf|password|passwd|secret|session|token|"
    r"(?:[a-z][a-z0-9]*[_-]?)?(?:api|access)[_-]?key(?:[_-]?id)?|"
    r"private[_-]?key|signing[_-]?key)"
    r"\b(\s*[:=]\s*)([^\r\n,]+)"
)
_HTTP_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_REFERENCE_KEYS = frozenset({"credential_ref", "secret_ref"})
_SECRET_PATH_MARKERS = frozenset(
    {
        "access_key",
        "access_token",
        "accesskey",
        "apikey",
        "api_key",
        "auth",
        "auth_key",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "password",
        "passwd",
        "private_key",
        "refresh_token",
        "secret",
        "session",
        "session_id",
        "sessionid",
        "sig",
        "sign",
        "signature",
        "signing_key",
        "token",
        "x_api_key",
        "xapikey",
    }
)
_MAX_PATH_DECODE_PASSES: Final = 3


@dataclass(frozen=True, slots=True)
class RedactionPolicy:
    """Resource limits prevent attacker-controlled raw envelopes from exploding."""

    max_depth: int = 20
    max_items: int = 20_000
    max_string_length: int = 100_000

    def __post_init__(self) -> None:
        if self.max_depth < 1 or self.max_items < 1 or self.max_string_length < 1:
            raise ValueError("redaction limits must be positive")


def _secret_strings(values: Sequence[str | SecretValue]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for value in values:
        revealed = value.reveal() if isinstance(value, SecretValue) else value
        if revealed:
            normalized.add(revealed)
    return tuple(sorted(normalized, key=len, reverse=True))


def _normalized_secret_name(value: str) -> str:
    # Preserve acronym boundaries so both ``aws_access_key_id`` and
    # ``AWSAccessKeyId`` normalize to the same representation.
    value = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", value)
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    return value.lower().replace("-", "_")


def _is_secret_key_name(value: str) -> bool:
    normalized = _normalized_secret_name(value)
    return (
        normalized in _SECRET_KEY_NAMES
        or _SECRET_KEY.search(normalized) is not None
        or _COMPOSITE_SECRET_KEY.search(normalized) is not None
    )


def _is_secret_query_name(value: str) -> bool:
    normalized = _normalized_secret_name(value)
    return normalized in _SECRET_QUERY_NAMES or _is_secret_key_name(normalized)


def _is_secret_path_marker(value: str) -> bool:
    normalized = _normalized_secret_name(value)
    return normalized in _SECRET_PATH_MARKERS or _COMPOSITE_SECRET_KEY.search(normalized) is not None


def _decoded_path_variants(path: str) -> tuple[str, ...]:
    variants = [path]
    current = path
    for _ in range(_MAX_PATH_DECODE_PASSES):
        decoded = unquote(current)
        if decoded == current:
            break
        variants.append(decoded)
        current = decoded
    return tuple(variants)


def _secret_path_values(path: str) -> tuple[str, ...]:
    """Return values attached to credential-marker path segments.

    Markers must be complete segments (``/token/value``) or complete
    assignment keys (``/token=value`` or ``/file;token=value``).  Checking a
    bounded sequence of percent-decoded variants catches encoded separators
    without treating ordinary names such as ``tokenized-video.mp4`` as secret.
    """

    values: set[str] = set()
    for variant in _decoded_path_variants(path):
        segments = variant.split("/")
        for index, segment in enumerate(segments):
            matrix_parts = segment.split(";")
            marker = matrix_parts[0]
            if _is_secret_path_marker(marker):
                for candidate in segments[index + 1 :]:
                    if candidate:
                        values.add(candidate)
                        break
            for assignment in matrix_parts:
                key, separator, candidate = assignment.partition("=")
                if separator and candidate and _is_secret_path_marker(key):
                    values.add(candidate)
    return tuple(sorted(values, key=len, reverse=True))


def has_secret_url_path(path: str) -> bool:
    """Return whether an HTTP URL path contains credential-shaped material."""

    return bool(_secret_path_values(path))


def secret_url_components(value: str) -> tuple[str, ...]:
    """Return sensitive URL components worth matching as standalone output.

    Encoded and decoded query values plus credential-bound path values are
    retained.  This complements an exact match on the complete URL when a
    child echoes only one signature or credential component.
    """

    try:
        parsed = urlsplit(value)
    except ValueError:
        return ()
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ()

    components: set[str] = set()
    components.update(_secret_path_values(parsed.path))
    for pair in parsed.query.split("&"):
        raw_key, separator, raw_value = pair.partition("=")
        if not separator or not _is_secret_query_name(unquote_plus(raw_key)):
            continue
        if raw_value:
            components.add(raw_value)
            components.add(unquote_plus(raw_value))
    return tuple(sorted((item for item in components if item), key=len, reverse=True))


def _redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return REDACTED
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return REDACTED
    query = parse_qsl(parsed.query, keep_blank_values=True)
    changed = parsed.username is not None or parsed.password is not None
    netloc = parsed.netloc
    if changed:
        hostname = parsed.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        try:
            port = parsed.port
        except ValueError:
            return REDACTED
        netloc = f"{hostname}:{port}" if port is not None else hostname
    safe_query: list[tuple[str, str]] = []
    for key, item in query:
        if _is_secret_query_name(key):
            safe_query.append((key, REDACTED))
            changed = True
        else:
            safe_query.append((key, item))
    fragment = parsed.fragment
    if fragment:
        fragment = REDACTED
        changed = True
    path = parsed.path
    if has_secret_url_path(path):
        path = "/%5BREDACTED%5D"
        changed = True
    if not changed:
        return value
    return urlunsplit((parsed.scheme, netloc, path, urlencode(safe_query), fragment))


def redact_text(
    value: str,
    *,
    known_secrets: Sequence[str | SecretValue] = (),
    max_length: int = 100_000,
) -> str:
    """Remove exact known values, secret assignments and signed URL parameters."""

    secrets = _secret_strings(known_secrets)
    # Keep enough look-ahead to remove a secret that starts immediately before
    # the output boundary. Truncating first could otherwise retain its prefix.
    overlap = max((len(secret) for secret in secrets), default=0)
    bounded = value[: max_length + overlap]
    for secret in secrets:
        bounded = bounded.replace(secret, REDACTED)
    was_truncated = len(value) > max_length
    bounded = bounded[:max_length]
    if was_truncated:
        bounded += TRUNCATED
    bounded = _HTTP_URL.sub(lambda match: _redact_url(match.group(0)), bounded)
    bounded = _INLINE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", bounded)
    return bounded


class _Redactor:
    def __init__(self, policy: RedactionPolicy, known_secrets: Sequence[str | SecretValue]) -> None:
        self.policy = policy
        self.known_secrets = tuple(known_secrets)
        self.items_seen = 0

    def redact(self, value: object, *, depth: int = 0, key: str | None = None) -> object:
        self.items_seen += 1
        if self.items_seen > self.policy.max_items or depth > self.policy.max_depth:
            return TRUNCATED
        if key is not None:
            normalized_key = key.lower()
            if normalized_key in _REFERENCE_KEYS:
                if not isinstance(value, str):
                    return REDACTED
                try:
                    return SecretReference.parse(value).serialize()
                except InvalidSecretReferenceError:
                    return REDACTED
            if _is_secret_key_name(key):
                return REDACTED
        if isinstance(value, SecretValue):
            return REDACTED
        if isinstance(value, str):
            return redact_text(
                value,
                known_secrets=self.known_secrets,
                max_length=self.policy.max_string_length,
            )
        if isinstance(value, bytes | bytearray | memoryview):
            return REDACTED
        if isinstance(value, Mapping):
            return {
                str(item_key): self.redact(item, depth=depth + 1, key=str(item_key)) for item_key, item in value.items()
            }
        if isinstance(value, tuple | list):
            return [self.redact(item, depth=depth + 1) for item in value]
        if isinstance(value, set | frozenset):
            ordered = sorted(value, key=lambda item: (type(item).__name__, repr(item)))
            return [self.redact(item, depth=depth + 1) for item in ordered]
        return value


def redact(
    value: object,
    *,
    known_secrets: Sequence[str | SecretValue] = (),
    policy: RedactionPolicy | None = None,
) -> object:
    """Return a recursively redacted copy without mutating the caller's data."""

    return _Redactor(policy or RedactionPolicy(), known_secrets).redact(value)


def redact_mapping(
    value: Mapping[str, object] | None,
    *,
    known_secrets: Sequence[str | SecretValue] = (),
    policy: RedactionPolicy | None = None,
) -> dict[str, object]:
    """Redact a mapping and preserve a type useful for JSON persistence."""

    result = redact(value or {}, known_secrets=known_secrets, policy=policy)
    if not isinstance(result, dict):  # pragma: no cover - input is always a mapping
        raise TypeError("redaction did not produce a mapping")
    return result


__all__ = [
    "REDACTED",
    "TRUNCATED",
    "RedactionPolicy",
    "has_secret_url_path",
    "redact",
    "redact_mapping",
    "redact_text",
    "secret_url_components",
]
