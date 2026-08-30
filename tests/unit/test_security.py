"""Secret-provider and recursive-redaction tests use sentinel values only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from media_sync.security import (
    REDACTED,
    EnvironmentSecretProvider,
    FileSecretProvider,
    InvalidSecretReferenceError,
    KeyringSecretProvider,
    RedactionPolicy,
    SecretReference,
    SecretResolutionError,
    SecretResolver,
    SecretScheme,
    SecretValue,
    redact,
    redact_mapping,
    redact_text,
    secret_url_components,
)

SENTINEL = "sentinel-secret-value"


@pytest.mark.parametrize(
    ("raw", "scheme", "locator"),
    [
        ("env:MEDIA_SYNC_TEST_COOKIE", SecretScheme.ENV, "MEDIA_SYNC_TEST_COOKIE"),
        ("file:accounts/bili.cookie", SecretScheme.FILE, "accounts/bili.cookie"),
        ("keyring:media-sync/bili-demo", SecretScheme.KEYRING, "media-sync/bili-demo"),
    ],
)
def test_secret_reference_round_trip_without_repr_disclosure(
    raw: str,
    scheme: SecretScheme,
    locator: str,
) -> None:
    reference = SecretReference.parse(raw)

    assert reference.scheme is scheme
    assert reference.locator == locator
    assert reference.serialize() == raw
    assert locator not in repr(reference)
    assert locator not in str(reference)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "cookie:raw",
        "env:NOT VALID",
        "env:COOKIE=value",
        "file:../cookie.txt",
        r"file:..\cookie.txt",
        "file:C:/absolute/cookie.txt",
        "keyring:missing-account",
        "keyring:service/",
        "keyring:service/account;Cookie=value",
    ],
)
def test_secret_reference_rejects_inline_or_unsafe_values(raw: str) -> None:
    with pytest.raises(InvalidSecretReferenceError):
        SecretReference.parse(raw)


def test_environment_provider_and_resolver_never_display_secret() -> None:
    provider = EnvironmentSecretProvider({"MEDIA_SYNC_TEST_COOKIE": SENTINEL})
    resolver = SecretResolver({SecretScheme.ENV: provider})

    secret = resolver.resolve("env:MEDIA_SYNC_TEST_COOKIE")

    assert secret.reveal() == SENTINEL
    assert SENTINEL not in repr(secret)
    assert SENTINEL not in str(secret)
    with pytest.raises(SecretResolutionError, match="unavailable") as raised:
        resolver.resolve("env:MEDIA_SYNC_MISSING")
    assert "MEDIA_SYNC_MISSING" not in str(raised.value)


def test_file_provider_is_utf8_bounded_and_confined(tmp_path: Path) -> None:
    root = tmp_path / "secrets"
    root.mkdir()
    nested = root / "accounts"
    nested.mkdir()
    secret_file = nested / "bili.cookie"
    secret_file.write_text(f"{SENTINEL}\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text(SENTINEL, encoding="utf-8")
    provider = FileSecretProvider(root)

    secret = provider.resolve(SecretReference.parse("file:accounts/bili.cookie"))
    assert secret.reveal() == SENTINEL

    with pytest.raises(InvalidSecretReferenceError):
        SecretReference.parse("file:../outside.txt")
    with pytest.raises(SecretResolutionError, match="unavailable"):
        provider.resolve(SecretReference.parse("file:missing.txt"))


class _FakeKeyring:
    def __init__(self, value: str | None = SENTINEL, *, fail: bool = False) -> None:
        self.value = value
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def get_password(self, service_name: str, username: str) -> str | None:
        self.calls.append((service_name, username))
        if self.fail:
            raise RuntimeError(SENTINEL)
        return self.value


def test_keyring_provider_uses_service_account_and_redacts_backend_errors() -> None:
    backend = _FakeKeyring()
    provider = KeyringSecretProvider(backend)
    reference = SecretReference.parse("keyring:media-sync/bili-demo")

    assert provider.resolve(reference).reveal() == SENTINEL
    assert backend.calls == [("media-sync", "bili-demo")]

    failing = KeyringSecretProvider(_FakeKeyring(fail=True))
    with pytest.raises(SecretResolutionError, match="lookup failed") as raised:
        failing.resolve(reference)
    assert SENTINEL not in str(raised.value)


def test_recursive_redaction_removes_nested_values_and_signed_url_parameters() -> None:
    source = {
        "credential_ref": "env:MEDIA_SYNC_TEST_COOKIE",
        "secret_ref": SENTINEL,
        "headers": {"Authorization": f"Bearer {SENTINEL}"},
        "SESSDATA": SENTINEL,
        "nested": [
            {"cookie": SENTINEL},
            {
                "source_url": (
                    "https://media.example/video.mp4?quality=1080&xsec_token="
                    f"{SENTINEL}&signature=another-secret#fragment-secret"
                )
            },
        ],
        "message": f"request failed token={SENTINEL}",
        "bytes": SENTINEL.encode(),
    }

    result = redact_mapping(source, known_secrets=[SecretValue(SENTINEL)])
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)

    assert SENTINEL not in serialized
    assert "another-secret" not in serialized
    assert "fragment-secret" not in serialized
    assert result["credential_ref"] == "env:MEDIA_SYNC_TEST_COOKIE"
    assert result["secret_ref"] == REDACTED
    assert result["headers"] == {"Authorization": REDACTED}
    assert result["SESSDATA"] == REDACTED
    assert "quality=1080" in serialized
    assert "%5BREDACTED%5D" in serialized
    assert source["nested"][0]["cookie"] == SENTINEL  # type: ignore[index]


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "apiKey",
        "API-KEY",
        "access_key",
        "accessKey",
        "aws_access_key_id",
        "AWSAccessKeyId",
        "google_api_key_value",
        "x-api-key",
        "xApiKey",
        "private_key",
        "signing-key",
    ],
)
def test_recursive_redaction_covers_explicit_composite_secret_keys(key: str) -> None:
    assert redact_mapping({key: SENTINEL}) == {key: REDACTED}


@pytest.mark.parametrize(
    "key",
    ["key", "public_key", "publicKey", "key_id", "keyId", "keyboard_layout", "monkey", "access_keynote"],
)
def test_recursive_redaction_does_not_treat_ordinary_key_names_as_secrets(key: str) -> None:
    assert redact_mapping({key: "ordinary-value"}) == {key: "ordinary-value"}


def test_text_redaction_is_bounded_and_deterministic() -> None:
    value = f"Cookie: {SENTINEL} https://example.test/path?token={SENTINEL}"

    first = redact_text(value, known_secrets=[SENTINEL], max_length=1_000)
    second = redact_text(value, known_secrets=[SENTINEL], max_length=1_000)

    assert first == second
    assert SENTINEL not in first
    assert first.count(REDACTED) >= 1


def test_text_redaction_sanitizes_signed_urls_embedded_in_messages() -> None:
    value = f"download failed at https://media.test/v.mp4?quality=1080&X-Bogus={SENTINEL}"

    result = redact_text(value)

    assert SENTINEL not in result
    assert "quality=1080" in result
    assert "%5BREDACTED%5D" in result


@pytest.mark.parametrize(
    "query_key",
    [
        "upsig",
        "sig",
        "auth_key",
        "wsSecret",
        "txSecret",
        "Policy",
        "Key-Pair-Id",
        "X-Amz-Credential",
        "X-Goog-Signature",
        "api_key",
        "apiKey",
        "X-API-Key",
        "accessKey",
    ],
)
def test_text_redaction_sanitizes_common_signed_url_parameters(query_key: str) -> None:
    value = f"https://media.test/v.mp4?quality=1080&{query_key}={SENTINEL}"

    result = redact_text(value)

    assert SENTINEL not in result
    assert "quality=1080" in result
    assert "%5BREDACTED%5D" in result


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "apiKey",
        "access_key",
        "accessKey",
        "aws_access_key_id",
        "AWSAccessKeyId",
        "x-api-key",
        "xApiKey",
        "private_key",
        "signingKey",
    ],
)
def test_text_redaction_sanitizes_composite_key_assignments(key: str) -> None:
    result = redact_text(f"request failed: {key}={SENTINEL}")

    assert SENTINEL not in result
    assert REDACTED in result


@pytest.mark.parametrize(
    "path",
    [
        f"/token/{SENTINEL}/video.mp4",
        f"/token%2F{SENTINEL}%2Fvideo.mp4",
        f"/token%252F{SENTINEL}%252Fvideo.mp4",
        f"/download;session={SENTINEL}/video.mp4",
        f"/signature={SENTINEL}/video.mp4",
    ],
)
def test_text_redaction_sanitizes_credential_bearing_url_paths(path: str) -> None:
    value = f"request failed at https://media.test{path}?quality=1080"

    result = redact_text(value)

    assert SENTINEL not in result
    assert "https://media.test/%5BREDACTED%5D" in result
    assert "quality=1080" in result


def test_secret_url_components_includes_encoded_path_credential_value() -> None:
    value = f"https://media.test/token%252F{SENTINEL}%252Fvideo.mp4"

    assert SENTINEL in secret_url_components(value)


@pytest.mark.parametrize(
    "path",
    [
        "/tokenized-video.mp4",
        "/session-recording.mp4",
        "/mytoken/file.mp4",
        "/token",
        "/public_key/value/video.mp4",
        "/key/value/video.mp4",
    ],
)
def test_text_redaction_preserves_noncredential_path_boundaries(path: str) -> None:
    value = f"https://media.test{path}"

    assert redact_text(value) == value


@pytest.mark.parametrize(
    "value",
    [
        f"https://[malformed/token/{SENTINEL}/file.mp4",
        f"https:///token/{SENTINEL}/file.mp4",
    ],
)
def test_text_redaction_fails_closed_for_malformed_credential_urls(value: str) -> None:
    result = redact_text(f"request failed at {value}")

    assert SENTINEL not in result
    assert REDACTED in result


def test_text_redaction_removes_url_userinfo_and_boundary_spanning_secret() -> None:
    url = f"request failed at https://operator:{SENTINEL}@media.test/private"

    sanitized_url = redact_text(url)
    boundary_value = f"prefix-{SENTINEL}-suffix"
    sanitized_boundary = redact_text(
        boundary_value,
        known_secrets=[SENTINEL],
        max_length=len("prefix-") + 2,
    )

    assert SENTINEL not in sanitized_url
    assert "operator" not in sanitized_url
    assert "media.test/private" in sanitized_url
    assert SENTINEL[:2] not in sanitized_boundary
    assert "TRUNCATED" in sanitized_boundary


def test_redaction_resource_limits_truncate_hostile_nesting() -> None:
    value: object = "leaf"
    for _ in range(20):
        value = [value]

    result = redact(value, policy=RedactionPolicy(max_depth=3, max_items=10, max_string_length=10))

    assert "TRUNCATED" in repr(result)
