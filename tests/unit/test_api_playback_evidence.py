"""Strict HTTP contract for browser-confirmed playback evidence."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from _api_client import (
    TEST_OPERATOR_CREDENTIAL,
    TEST_OPERATOR_ORIGIN,
    operator_test_settings,
)
from fastapi.testclient import TestClient

import media_sync.interfaces.api as api_module
from media_sync.application import (
    PlaybackEvidenceConfirmation,
    PlaybackEvidenceConfirmationError,
)
from media_sync.config import Settings
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.ports.media_server import MediaServerError
from media_sync.security import OPERATOR_CSRF_HEADER_NAME

AUTHOR_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
EVIDENCE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OBSERVATION_FINGERPRINT = "e" * 64
OBSERVED_AT = datetime(2026, 9, 5, 8, tzinfo=UTC)
CONFIRMED_AT = datetime(2026, 9, 5, 8, 0, 1, tzinfo=UTC)
BEARER_TOKEN = "playback-api-automation-token-0123456789"
PLAYBACK_PATH = "/api/v1/media-server/playback-evidence"


class _FakePlaybackEvidenceService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.error: Exception | None = None
        self.result = PlaybackEvidenceConfirmation(
            id=EVIDENCE_ID,
            author_id=AUTHOR_ID,
            observed_at=OBSERVED_AT,
            confirmed_at=CONFIRMED_AT,
            replayed=False,
        )

    def confirm(self, author_id: str, observation_fingerprint: str) -> PlaybackEvidenceConfirmation:
        self.calls.append((author_id, observation_fingerprint))
        if self.error is not None:
            raise self.error
        return self.result


def _base_settings(tmp_path: Path) -> Settings:
    return Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "exports",
        job_dir=tmp_path / "jobs",
        mediacrawler_runtime_dir=tmp_path / "mediacrawler",
        media_server_provider="emby",
        media_server_base_url="http://127.0.0.1:8096",
        media_server_library_id="private-library",
        media_server_api_key_secret_ref="env:MEDIA_SERVER_API_KEY",
        media_server_library_path="/srv/private-library",
        media_server_allowed_cidrs=("127.0.0.1/32",),
        media_server_operations_enabled=True,
        _env_file=None,
    )


def _install_fake_service(
    monkeypatch: pytest.MonkeyPatch,
    service: _FakePlaybackEvidenceService,
) -> None:
    def service_factory(_database: object, _observation: object) -> _FakePlaybackEvidenceService:
        return service

    monkeypatch.setattr(api_module, "PlaybackEvidenceService", service_factory)


@pytest.fixture
def playback_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, _FakePlaybackEvidenceService]]:
    service = _FakePlaybackEvidenceService()
    _install_fake_service(monkeypatch, service)
    settings = operator_test_settings(_base_settings(tmp_path))
    upgrade_database(settings.resolved_database_url)
    with TestClient(api_module.create_api_app(settings), base_url=TEST_OPERATOR_ORIGIN) as client:
        yield client, service


def _login(client: TestClient) -> str:
    login = client.post(
        "/api/v1/operator-auth/login",
        json={"credential": TEST_OPERATOR_CREDENTIAL},
        headers={"Origin": TEST_OPERATOR_ORIGIN},
    )
    assert login.status_code == 200, login.text
    session = client.get("/api/v1/operator-auth/session")
    assert session.status_code == 200, session.text
    csrf = session.json()["csrf_token"]
    assert isinstance(csrf, str)
    return csrf


def _browser_headers(csrf: str, *, content_type: str | None = "application/json") -> dict[str, str]:
    headers = {
        "Origin": TEST_OPERATOR_ORIGIN,
        OPERATOR_CSRF_HEADER_NAME: csrf,
    }
    if content_type is not None:
        headers["Content-Type"] = content_type
    return headers


def _request_bytes(
    *,
    author_id: object = AUTHOR_ID,
    observation_fingerprint: object = OBSERVATION_FINGERPRINT,
    extra: dict[str, object] | None = None,
) -> bytes:
    payload = {
        "author_id": author_id,
        "observation_fingerprint": observation_fingerprint,
    }
    if extra is not None:
        payload.update(extra)
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def test_create_and_replay_return_the_same_minimal_201_projection(
    playback_api: tuple[TestClient, _FakePlaybackEvidenceService],
) -> None:
    client, service = playback_api
    csrf = _login(client)

    created = client.post(
        PLAYBACK_PATH,
        content=_request_bytes(),
        headers=_browser_headers(csrf),
    )
    service.result = PlaybackEvidenceConfirmation(
        id=EVIDENCE_ID,
        author_id=AUTHOR_ID,
        observed_at=OBSERVED_AT,
        confirmed_at=CONFIRMED_AT,
        replayed=True,
    )
    replayed = client.post(
        PLAYBACK_PATH,
        content=_request_bytes(),
        headers=_browser_headers(csrf),
    )

    expected = {
        "schema_version": 1,
        "id": EVIDENCE_ID,
        "author_id": AUTHOR_ID,
        "observed_at": "2026-09-05T08:00:00+00:00",
        "confirmed_at": "2026-09-05T08:00:01+00:00",
        "replayed": False,
    }
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    assert created.json() == expected
    assert replayed.status_code == 201
    assert replayed.headers["cache-control"] == "no-store"
    assert replayed.json() == {**expected, "replayed": True}
    assert service.calls == [
        (AUTHOR_ID, OBSERVATION_FINGERPRINT),
        (AUTHOR_ID, OBSERVATION_FINGERPRINT),
    ]
    assert OBSERVATION_FINGERPRINT not in created.text
    assert set(created.json()) == {
        "schema_version",
        "id",
        "author_id",
        "observed_at",
        "confirmed_at",
        "replayed",
    }


@pytest.mark.parametrize(
    "content_type",
    [
        None,
        "",
        "text/plain",
        "application/problem+json",
        "application/json; charset=utf-16",
        "application/json; profile=private-sentinel",
    ],
)
def test_content_type_is_exact_and_rejected_before_service(
    playback_api: tuple[TestClient, _FakePlaybackEvidenceService],
    content_type: str | None,
) -> None:
    client, service = playback_api
    csrf = _login(client)

    response = client.post(
        PLAYBACK_PATH,
        content=_request_bytes(),
        headers=_browser_headers(csrf, content_type=content_type),
    )

    assert response.status_code == 415
    assert response.json() == {"detail": "playback_evidence_content_type_invalid"}
    assert response.headers["cache-control"] == "no-store"
    assert "private-sentinel" not in response.text
    assert service.calls == []


def test_duplicate_content_type_is_rejected_before_service(
    playback_api: tuple[TestClient, _FakePlaybackEvidenceService],
) -> None:
    client, service = playback_api
    csrf = _login(client)

    response = client.post(
        PLAYBACK_PATH,
        content=_request_bytes(),
        headers=[
            ("Origin", TEST_OPERATOR_ORIGIN),
            (OPERATOR_CSRF_HEADER_NAME, csrf),
            ("Content-Type", "application/json"),
            ("Content-Type", "application/json"),
        ],
    )

    assert response.status_code == 415
    assert response.json() == {"detail": "playback_evidence_content_type_invalid"}
    assert service.calls == []


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "APPLICATION/JSON",
        "application/json;charset=utf-8",
        "application/json; charset=UTF-8",
    ],
)
def test_supported_json_content_types_reach_service(
    playback_api: tuple[TestClient, _FakePlaybackEvidenceService],
    content_type: str,
) -> None:
    client, service = playback_api
    csrf = _login(client)

    response = client.post(
        PLAYBACK_PATH,
        content=_request_bytes(),
        headers=_browser_headers(csrf, content_type=content_type),
    )

    assert response.status_code == 201
    assert service.calls == [(AUTHOR_ID, OBSERVATION_FINGERPRINT)]


def test_body_limit_accepts_1024_bytes_and_rejects_larger_fixed_and_streamed_bodies(
    playback_api: tuple[TestClient, _FakePlaybackEvidenceService],
) -> None:
    client, service = playback_api
    csrf = _login(client)
    request = _request_bytes()
    exact_limit = request + b" " * (1_024 - len(request))
    over_limit = exact_limit + b" "

    accepted = client.post(
        PLAYBACK_PATH,
        content=exact_limit,
        headers=_browser_headers(csrf),
    )
    rejected = client.post(
        PLAYBACK_PATH,
        content=over_limit,
        headers=_browser_headers(csrf),
    )

    def streamed_body() -> Iterator[bytes]:
        yield request
        yield b" " * (1_025 - len(request))

    streamed = client.post(
        PLAYBACK_PATH,
        content=streamed_body(),
        headers=_browser_headers(csrf),
    )

    assert len(exact_limit) == 1_024
    assert accepted.status_code == 201
    assert rejected.status_code == 413
    assert rejected.json() == {"detail": "playback_evidence_body_too_large"}
    assert streamed.status_code == 413
    assert streamed.json() == {"detail": "playback_evidence_body_too_large"}
    assert service.calls == [(AUTHOR_ID, OBSERVATION_FINGERPRINT)]


@pytest.mark.parametrize(
    ("payload", "case"),
    [
        (b"{}", "empty"),
        (b"null", "null"),
        (b"[]", "array"),
        (b"not-json", "malformed"),
        (b'{"author_id":NaN,"observation_fingerprint":"' + b"e" * 64 + b'"}', "non-finite"),
        (b"\xff", "non-utf8"),
        (
            b'{"author_id":"'
            + AUTHOR_ID.encode("ascii")
            + b'","author_id":"'
            + AUTHOR_ID.encode("ascii")
            + b'","observation_fingerprint":"'
            + OBSERVATION_FINGERPRINT.encode("ascii")
            + b'"}',
            "duplicate-author",
        ),
        (
            b'{"author_id":"'
            + AUTHOR_ID.encode("ascii")
            + b'","observation_fingerprint":"'
            + OBSERVATION_FINGERPRINT.encode("ascii")
            + b'","observation_fingerprint":"'
            + OBSERVATION_FINGERPRINT.encode("ascii")
            + b'"}',
            "duplicate-fingerprint",
        ),
        (_request_bytes(author_id=None), "null-author"),
        (_request_bytes(author_id=7), "integer-author"),
        (_request_bytes(author_id=AUTHOR_ID.upper()), "uppercase-author"),
        (_request_bytes(author_id="not-a-canonical-uuid"), "invalid-author"),
        (_request_bytes(observation_fingerprint=None), "null-fingerprint"),
        (_request_bytes(observation_fingerprint=7), "integer-fingerprint"),
        (_request_bytes(observation_fingerprint="E" * 64), "uppercase-fingerprint"),
        (_request_bytes(observation_fingerprint="e" * 63), "short-fingerprint"),
        (_request_bytes(observation_fingerprint="e" * 65), "long-fingerprint"),
        (_request_bytes(observation_fingerprint="g" * 64), "non-hex-fingerprint"),
        (_request_bytes(extra={"provider": "private-provider-sentinel"}), "extra-provider"),
        (_request_bytes(extra={"path": "/private/path/sentinel"}), "extra-path"),
        (_request_bytes(extra={"item_id": "private-item-sentinel"}), "extra-item"),
        (_request_bytes(extra={"observed_at": "2026-09-05T08:00:00Z"}), "extra-time"),
        (_request_bytes(extra={"note": "private-free-text-sentinel"}), "extra-free-text"),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_body_is_an_exact_duplicate_free_canonical_two_field_object(
    playback_api: tuple[TestClient, _FakePlaybackEvidenceService],
    payload: bytes,
    case: str,
) -> None:
    del case
    client, service = playback_api
    csrf = _login(client)

    response = client.post(
        PLAYBACK_PATH,
        content=payload,
        headers=_browser_headers(csrf),
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "playback_evidence_request_invalid"}
    assert response.headers["cache-control"] == "no-store"
    for sentinel in (
        AUTHOR_ID,
        OBSERVATION_FINGERPRINT,
        "private-provider-sentinel",
        "/private/path/sentinel",
        "private-item-sentinel",
        "private-free-text-sentinel",
    ):
        assert sentinel not in response.text
    assert service.calls == []


def test_idempotency_key_is_explicitly_unsupported_and_not_reflected(
    playback_api: tuple[TestClient, _FakePlaybackEvidenceService],
) -> None:
    client, service = playback_api
    csrf = _login(client)
    sentinel = "private-idempotency-sentinel"

    response = client.post(
        PLAYBACK_PATH,
        content=_request_bytes(),
        headers={**_browser_headers(csrf), "Idempotency-Key": sentinel},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "playback_evidence_idempotency_key_unsupported"}
    assert sentinel not in response.text
    assert service.calls == []


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (
            PlaybackEvidenceConfirmationError("playback_evidence_request_invalid"),
            400,
            "playback_evidence_request_invalid",
        ),
        (
            PlaybackEvidenceConfirmationError("playback_evidence_not_confirmable"),
            409,
            "playback_evidence_not_confirmable",
        ),
        (
            PlaybackEvidenceConfirmationError("playback_evidence_identity_conflict"),
            409,
            "playback_evidence_identity_conflict",
        ),
        (
            PlaybackEvidenceConfirmationError("playback_evidence_confirmation_unavailable"),
            503,
            "playback_evidence_confirmation_unavailable",
        ),
        (
            PlaybackEvidenceConfirmationError("playback_evidence_store_unavailable"),
            503,
            "playback_evidence_store_unavailable",
        ),
        (MediaServerError("media_server_operations_disabled"), 403, "media_server_operations_disabled"),
        (MediaServerError("media_server_not_configured"), 409, "media_server_not_configured"),
        (MediaServerError("media_server_item_lookup_ambiguous"), 409, "media_server_item_lookup_ambiguous"),
        (MediaServerError("media_server_publication_changed"), 409, "media_server_publication_changed"),
        (MediaServerError("media_server_item_lookup_incomplete"), 503, "media_server_item_lookup_incomplete"),
        (MediaServerError("media_server_timeout", retryable=True), 503, "media_server_timeout"),
    ],
)
def test_service_errors_map_to_fixed_safe_http_failures(
    playback_api: tuple[TestClient, _FakePlaybackEvidenceService],
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    client, service = playback_api
    csrf = _login(client)
    service.error = error

    response = client.post(
        PLAYBACK_PATH,
        content=_request_bytes(),
        headers=_browser_headers(csrf),
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert response.headers["cache-control"] == "no-store"
    assert AUTHOR_ID not in response.text
    assert OBSERVATION_FINGERPRINT not in response.text
    assert service.calls == [(AUTHOR_ID, OBSERVATION_FINGERPRINT)]


def test_anonymous_origin_and_csrf_rejections_never_enter_confirmation(
    playback_api: tuple[TestClient, _FakePlaybackEvidenceService],
) -> None:
    client, service = playback_api
    request = _request_bytes()

    anonymous = client.post(
        PLAYBACK_PATH,
        content=request,
        headers={"Content-Type": "application/json"},
    )
    assert anonymous.status_code == 401
    assert anonymous.json() == {"detail": "operator_auth_required"}

    csrf = _login(client)
    missing_origin = client.post(
        PLAYBACK_PATH,
        content=request,
        headers={OPERATOR_CSRF_HEADER_NAME: csrf, "Content-Type": "application/json"},
    )
    assert missing_origin.status_code == 403
    assert missing_origin.json() == {"detail": "operator_origin_forbidden"}

    cross_origin = client.post(
        PLAYBACK_PATH,
        content=request,
        headers={
            "Origin": "https://evil.example",
            OPERATOR_CSRF_HEADER_NAME: csrf,
            "Content-Type": "application/json",
        },
    )
    assert cross_origin.status_code == 403
    assert cross_origin.json() == {"detail": "operator_origin_forbidden"}

    missing_csrf = client.post(
        PLAYBACK_PATH,
        content=request,
        headers={"Origin": TEST_OPERATOR_ORIGIN, "Content-Type": "application/json"},
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json() == {"detail": "operator_csrf_forbidden"}

    wrong_csrf = client.post(
        PLAYBACK_PATH,
        content=request,
        headers=_browser_headers("wrong-csrf-sentinel"),
    )
    assert wrong_csrf.status_code == 403
    assert wrong_csrf.json() == {"detail": "operator_csrf_forbidden"}

    duplicate_csrf = client.post(
        PLAYBACK_PATH,
        content=request,
        headers=[
            ("Origin", TEST_OPERATOR_ORIGIN),
            (OPERATOR_CSRF_HEADER_NAME, csrf),
            (OPERATOR_CSRF_HEADER_NAME, csrf),
            ("Content-Type", "application/json"),
        ],
    )
    assert duplicate_csrf.status_code == 403
    assert duplicate_csrf.json() == {"detail": "operator_csrf_forbidden"}

    old_csrf = csrf
    rotated = client.post(
        "/api/v1/operator-auth/login",
        json={"credential": TEST_OPERATOR_CREDENTIAL},
        headers={"Origin": TEST_OPERATOR_ORIGIN},
    )
    assert rotated.status_code == 200
    stale_csrf = client.post(
        PLAYBACK_PATH,
        content=request,
        headers=_browser_headers(old_csrf),
    )
    assert stale_csrf.status_code == 403
    assert stale_csrf.json() == {"detail": "operator_csrf_forbidden"}
    assert service.calls == []


def test_bearer_and_mixed_cookie_bearer_are_rejected_before_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _FakePlaybackEvidenceService()
    _install_fake_service(monkeypatch, service)
    settings = operator_test_settings(_base_settings(tmp_path))
    secret_root = settings.resolved_secret_file_dir
    (secret_root / "playback-bearer.txt").write_text(BEARER_TOKEN, encoding="utf-8")
    values = settings.model_dump(mode="python")
    values["operator_api_token_secret_ref"] = "file:playback-bearer.txt"
    settings = Settings(**values, _env_file=None)
    upgrade_database(settings.resolved_database_url)

    with TestClient(api_module.create_api_app(settings), base_url=TEST_OPERATOR_ORIGIN) as client:
        bearer_only = client.post(
            PLAYBACK_PATH,
            content=_request_bytes(),
            headers={
                "Authorization": f"Bearer {BEARER_TOKEN}",
                "Content-Type": "application/json",
            },
        )
        assert bearer_only.status_code == 403
        assert bearer_only.json() == {"detail": "operator_browser_session_required"}

        csrf = _login(client)
        mixed = client.post(
            PLAYBACK_PATH,
            content=_request_bytes(),
            headers={
                **_browser_headers(csrf),
                "Authorization": f"Bearer {BEARER_TOKEN}",
            },
        )
        assert mixed.status_code == 403
        assert mixed.json() == {"detail": "operator_browser_session_required"}
    assert service.calls == []


def test_openapi_documents_the_exact_write_only_request_and_minimal_response(
    playback_api: tuple[TestClient, _FakePlaybackEvidenceService],
) -> None:
    client, _service = playback_api
    operation = client.app.openapi()["paths"][PLAYBACK_PATH]["post"]

    assert operation["requestBody"] == {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "author_id": {
                            "type": "string",
                            "minLength": 36,
                            "maxLength": 36,
                            "format": "uuid",
                        },
                        "observation_fingerprint": {
                            "type": "string",
                            "minLength": 64,
                            "maxLength": 64,
                            "pattern": "^[0-9a-f]{64}$",
                            "writeOnly": True,
                        },
                    },
                    "required": ["author_id", "observation_fingerprint"],
                    "additionalProperties": False,
                }
            }
        },
    }
    response_schema = operation["responses"]["201"]["content"]["application/json"]["schema"]
    assert response_schema == {
        "type": "object",
        "properties": {
            "schema_version": {"type": "integer", "enum": [1]},
            "id": {"type": "string", "format": "uuid"},
            "author_id": {"type": "string", "format": "uuid"},
            "observed_at": {"type": "string", "format": "date-time"},
            "confirmed_at": {"type": "string", "format": "date-time"},
            "replayed": {"type": "boolean"},
        },
        "required": [
            "schema_version",
            "id",
            "author_id",
            "observed_at",
            "confirmed_at",
            "replayed",
        ],
        "additionalProperties": False,
    }
    assert "observation_fingerprint" not in response_schema["properties"]
