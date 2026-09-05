from pathlib import Path

import pytest
from pydantic import ValidationError

from media_sync.config import Settings


def test_settings_builds_default_sqlite_url_from_state_dir(tmp_path: Path) -> None:
    settings = Settings(state_dir=tmp_path / "state", _env_file=None)

    assert settings.resolved_database_url == f"sqlite+pysqlite:///{(tmp_path / 'state/media-sync.sqlite3').as_posix()}"
    assert settings.resolved_secret_file_dir == (tmp_path / "state/secrets").resolve()
    assert settings.resolved_mediacrawler_runtime_dir == (tmp_path / "state/mediacrawler").resolve()


def test_settings_allows_explicit_secret_file_root(tmp_path: Path) -> None:
    secret_root = tmp_path / "private"

    settings = Settings(secret_file_dir=secret_root, _env_file=None)

    assert settings.resolved_secret_file_dir == secret_root.resolve()
    assert not secret_root.exists()


def test_settings_allows_explicit_mediacrawler_runtime_without_creating_it(tmp_path: Path) -> None:
    runtime_root = tmp_path / "private-runtime"
    python_executable = tmp_path / "upstream-python"

    settings = Settings(
        mediacrawler_runtime_dir=runtime_root,
        mediacrawler_python_executable=python_executable,
        _env_file=None,
    )

    assert settings.resolved_mediacrawler_runtime_dir == runtime_root.resolve()
    assert settings.mediacrawler_python_executable == python_executable
    assert not runtime_root.exists()


def test_settings_creates_only_declared_runtime_directories(tmp_path: Path) -> None:
    roots = [tmp_path / name for name in ("state", "archive", "exports", "jobs")]
    settings = Settings(
        state_dir=roots[0],
        archive_dir=roots[1],
        export_dir=roots[2],
        job_dir=roots[3],
        _env_file=None,
    )

    settings.ensure_directories()

    assert all(path.is_dir() for path in roots)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["archive", "exports", "jobs", "state"]


@pytest.mark.parametrize("value", ["trace", "", "verbose"])
def test_settings_rejects_unknown_log_level(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(log_level=value, _env_file=None)


def test_settings_normalizes_log_level() -> None:
    assert Settings(log_level=" warning ", _env_file=None).log_level == "WARNING"


def test_operator_auth_settings_are_bounded_canonical_and_repr_safe() -> None:
    settings = Settings(
        operator_credential_secret_ref=" env:OPERATOR_BROWSER_SENTINEL ",
        operator_api_token_secret_ref="file:operator-api-token",
        operator_allowed_origins=("HTTPS://Console.Example:443/", "http://[::1]:8632"),
        operator_session_ttl_seconds=3_600,
        _env_file=None,
    )

    assert settings.operator_credential_secret_ref == "env:OPERATOR_BROWSER_SENTINEL"
    assert settings.operator_api_token_secret_ref == "file:operator-api-token"
    assert settings.operator_allowed_origins == ("https://console.example", "http://[::1]:8632")
    assert settings.operator_session_ttl_seconds == 3_600
    assert settings.operator_credential_secret_reference is not None
    assert settings.operator_api_token_secret_reference is not None
    rendered = repr(settings)
    assert "OPERATOR_BROWSER_SENTINEL" not in rendered
    assert "operator-api-token" not in rendered


def test_operator_origins_accept_json_environment_syntax(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MEDIA_SYNC_OPERATOR_ALLOWED_ORIGINS",
        '["https://console.example:443", "https://backup.example:8443/"]',
    )

    settings = Settings(_env_file=None)

    assert settings.operator_allowed_origins == (
        "https://console.example",
        "https://backup.example:8443",
    )


@pytest.mark.parametrize(
    "value",
    [
        "",
        [],
        ["ftp://console.example"],
        ["https://user@console.example"],
        ["https://console.example/path"],
        ["https://*.example"],
        ["https://console.example:0"],
        ["https://console.example", "HTTPS://CONSOLE.EXAMPLE:443/"],
        ["https://a.example"] * 9,
        [None],
    ],
)
def test_operator_origins_reject_ambiguous_or_unbounded_values(value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(operator_allowed_origins=value, _env_file=None)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [59, 28_801])
def test_operator_session_ttl_rejects_out_of_bounds(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(operator_session_ttl_seconds=value, _env_file=None)


def test_operator_credentials_require_distinct_typed_references() -> None:
    with pytest.raises(ValidationError):
        Settings(operator_credential_secret_ref="inline-secret", _env_file=None)
    with pytest.raises(ValidationError):
        Settings(
            operator_credential_secret_ref="env:SAME_OPERATOR_SECRET",
            operator_api_token_secret_ref="env:SAME_OPERATOR_SECRET",
            _env_file=None,
        )


def _media_server_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "media_server_provider": " EMBY ",
        "media_server_base_url": "HTTPS://Media.Example:443/",
        "media_server_library_id": "library_123",
        "media_server_api_key_secret_ref": "env:MEDIA_SERVER_KEY_SENTINEL",
        "media_server_library_path": "/srv/media/private-path-sentinel",
        "media_server_allowed_cidrs": ("10.20.30.7/24", "2001:db8::1"),
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_media_server_profile_is_canonical_and_summary_is_redacted() -> None:
    settings = _media_server_settings(media_server_operations_enabled=True)
    profile = settings.media_server_profile

    assert profile is not None
    assert profile.provider == "emby"
    assert profile.origin == "https://media.example"
    assert profile.allowed_cidrs == ("10.20.30.0/24", "2001:db8::1/128")
    assert profile.operations_enabled is True
    assert settings.media_server_profile_fingerprint == profile.profile_fingerprint
    assert len(profile.profile_fingerprint) == 64
    assert settings.library_inspection_byte_budget == 1_073_741_824
    assert settings.library_inspection_timeout_seconds == 10.0

    summary = settings.media_server_safe_summary.as_dict()
    assert summary == {
        "configured": True,
        "provider": "emby",
        "origin": "https://media.example",
        "library_id_digest": profile.library_id_digest,
        "profile_fingerprint": profile.profile_fingerprint,
        "verify_tls": True,
        "timeout_seconds": 10.0,
        "operations_enabled": True,
        "allowed_network_count": 2,
        "library_path_configured": True,
        "api_key_configured": True,
    }
    rendered = repr(settings) + repr(profile) + str(profile) + repr(summary)
    for forbidden in (
        "library_123",
        "MEDIA_SERVER_KEY_SENTINEL",
        "/srv/media/private-path-sentinel",
        "10.20.30.0/24",
        "2001:db8::1/128",
    ):
        assert forbidden not in rendered


def test_media_server_cidrs_accept_comma_or_json_environment_syntax(monkeypatch: pytest.MonkeyPatch) -> None:
    common = {
        "MEDIA_SYNC_MEDIA_SERVER_PROVIDER": "jellyfin",
        "MEDIA_SYNC_MEDIA_SERVER_BASE_URL": "http://server.test:8096",
        "MEDIA_SYNC_MEDIA_SERVER_LIBRARY_ID": "abc123",
        "MEDIA_SYNC_MEDIA_SERVER_API_KEY_SECRET_REF": "env:SERVER_KEY",
        "MEDIA_SYNC_MEDIA_SERVER_LIBRARY_PATH": "/media/library",
    }
    for name, value in common.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("MEDIA_SYNC_MEDIA_SERVER_ALLOWED_CIDRS", "127.0.0.1, 10.0.0.9/8")
    assert Settings(_env_file=None).media_server_allowed_cidrs == ("10.0.0.0/8", "127.0.0.1/32")

    monkeypatch.setenv("MEDIA_SYNC_MEDIA_SERVER_ALLOWED_CIDRS", '["192.168.4.9/24"]')
    assert Settings(_env_file=None).media_server_allowed_cidrs == ("192.168.4.0/24",)


@pytest.mark.parametrize(
    "missing",
    [
        "media_server_provider",
        "media_server_base_url",
        "media_server_library_id",
        "media_server_api_key_secret_ref",
        "media_server_library_path",
        "media_server_allowed_cidrs",
    ],
)
def test_media_server_profile_is_all_or_none(missing: str) -> None:
    values: dict[str, object] = {
        "media_server_provider": "emby",
        "media_server_base_url": "https://media.example",
        "media_server_library_id": "library",
        "media_server_api_key_secret_ref": "env:MEDIA_SERVER_KEY",
        "media_server_library_path": "/srv/media",
        "media_server_allowed_cidrs": ("10.0.0.0/8",),
    }
    del values[missing]

    with pytest.raises(ValidationError, match="all-or-none"):
        Settings(**values, _env_file=None)  # type: ignore[arg-type]


def test_media_server_operation_gate_cannot_open_without_profile() -> None:
    with pytest.raises(ValidationError, match="without a complete profile"):
        Settings(media_server_operations_enabled=True, _env_file=None)


@pytest.mark.parametrize(
    "values",
    [
        {"media_server_api_key_secret_ref": "api-key-private-sentinel"},
        {"media_server_api_key_secret_ref": "env:PRIVATE_REFERENCE_SENTINEL"},
    ],
)
def test_settings_validation_errors_hide_secret_inputs(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(**values, _env_file=None)  # type: ignore[arg-type]

    rendered = str(caught.value) + repr(caught.value)
    assert "api-key-private-sentinel" not in rendered
    assert "env:PRIVATE_REFERENCE_SENTINEL" not in rendered


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("media_server_provider", "plex"),
        ("media_server_base_url", "https://user:pass@media.example"),
        ("media_server_base_url", "https://media.example/prefix"),
        ("media_server_base_url", "https://media.example?api_key=secret"),
        ("media_server_library_id", "../global"),
        ("media_server_api_key_secret_ref", "inline-secret"),
        ("media_server_library_path", "relative/path"),
        ("media_server_allowed_cidrs", ("not-a-network",)),
        ("media_server_allowed_cidrs", ()),
        ("media_server_timeout_seconds", 60.1),
        ("library_inspection_max_bytes", 0),
        ("library_inspection_deadline_seconds", float("inf")),
    ],
)
def test_media_server_and_inspection_configuration_fail_closed(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        _media_server_settings(**{field: value})


def test_unconfigured_media_server_summary_is_explicit_and_network_free() -> None:
    settings = Settings(_env_file=None)

    assert settings.media_server_profile is None
    assert settings.media_server_profile_fingerprint is None
    assert settings.media_server_safe_summary.as_dict() == {
        "configured": False,
        "provider": None,
        "origin": None,
        "library_id_digest": None,
        "profile_fingerprint": None,
        "verify_tls": True,
        "timeout_seconds": 10.0,
        "operations_enabled": False,
        "allowed_network_count": 0,
        "library_path_configured": False,
        "api_key_configured": False,
    }
