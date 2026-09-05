"""Authenticated strict author reads and qualification v3 HTTP scope."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from _api_client import TEST_OPERATOR_ORIGIN, operator_test_settings
from fastapi.testclient import TestClient
from test_api_playback_evidence import AUTHOR_ID, CONFIRMED_AT, EVIDENCE_ID, OBSERVED_AT, _base_settings, _login

import media_sync.interfaces.api as api_module
from media_sync.application.playback_evidence_query import (
    PlaybackEvidenceProjection,
    PlaybackEvidenceQueryError,
    PlaybackEvidenceView,
)
from media_sync.infrastructure.db.migration import upgrade_database

AUTHOR_PATH = f"/api/v1/media-server/playback-evidence/by-author/{AUTHOR_ID}"
TOKEN = "evidence-query-bearer-credential-0123456789"


class _Query:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.error = False

    def snapshot(self, author_id: str, *, limit: int = 20) -> PlaybackEvidenceProjection:
        self.calls.append((author_id, limit))
        if self.error:
            raise PlaybackEvidenceQueryError("playback_evidence_store_unavailable")
        return PlaybackEvidenceProjection(
            author_id,
            CONFIRMED_AT,
            "matched",
            PlaybackEvidenceView(EVIDENCE_ID, author_id, OBSERVED_AT, CONFIRMED_AT, "current"),
            (),
            False,
            limit,
        )


@pytest.fixture
def query_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, _Query]]:
    service = _Query()
    monkeypatch.setattr(api_module, "PlaybackEvidenceQueryService", lambda *_args: service)
    monkeypatch.setenv("EVIDENCE_QUERY_TEST_TOKEN", TOKEN)
    settings = operator_test_settings(_base_settings(tmp_path))
    settings = settings.model_copy(update={"operator_api_token_secret_ref": "env:EVIDENCE_QUERY_TEST_TOKEN"})
    upgrade_database(settings.resolved_database_url)
    with TestClient(api_module.create_api_app(settings), base_url=TEST_OPERATOR_ORIGIN) as client:
        yield client, service


def test_auth_precedes_query_validation_and_work(query_api: tuple[TestClient, _Query]) -> None:
    client, service = query_api
    for path in (
        AUTHOR_PATH,
        AUTHOR_PATH + "?limit=private-sentinel",
        "/api/v1/qualifications?author_id=private-sentinel",
    ):
        response = client.get(path)
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
        assert "private-sentinel" not in response.text
    assert service.calls == []


@pytest.mark.parametrize("mode", ["browser", "bearer"])
def test_safe_author_get_accepts_cookie_or_bearer_with_no_csrf_and_no_internal_identity(
    query_api: tuple[TestClient, _Query], mode: str
) -> None:
    client, service = query_api
    headers = {"Authorization": f"Bearer {TOKEN}"} if mode == "bearer" else {}
    if mode == "browser":
        _login(client)
    response = client.get(AUTHOR_PATH + "?limit=50", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["current"]["id"] == EVIDENCE_ID
    assert payload["scope"] == "author" and payload["human_status"] == "PASS"
    assert payload["limit"] == 50 and service.calls == [(AUTHOR_ID, 50)]
    assert response.headers["cache-control"] == "no-store"
    for forbidden in ("fingerprint", "publication_job", "provider", "path", "private-", TOKEN):
        assert forbidden not in response.text


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=51",
        "limit=-1",
        "limit=01",
        "limit=1&limit=2",
        "limit=1.0",
        "limit=private-sentinel",
        "author_id=" + AUTHOR_ID,
        "provider=private-sentinel",
    ],
)
def test_invalid_queries_never_enter_service(query_api: tuple[TestClient, _Query], query: str) -> None:
    client, service = query_api
    _login(client)
    response = client.get(AUTHOR_PATH + "?" + query)
    assert response.status_code in (400, 422)
    assert "private-sentinel" not in response.text
    assert service.calls == []


@pytest.mark.parametrize("author_id", ["private-sentinel", AUTHOR_ID.upper(), AUTHOR_ID.replace("-", "")])
def test_noncanonical_author_is_rejected_before_query(query_api: tuple[TestClient, _Query], author_id: str) -> None:
    client, service = query_api
    _login(client)
    response = client.get("/api/v1/media-server/playback-evidence/by-author/" + author_id)
    assert response.status_code == 400
    assert response.json() == {"detail": "playback_evidence_request_invalid"}
    assert service.calls == []


def test_qualifications_is_idle_without_author_and_pass_is_scoped_to_one_author(
    query_api: tuple[TestClient, _Query],
) -> None:
    client, service = query_api
    _login(client)
    unrequested = client.get("/api/v1/qualifications")
    assert unrequested.status_code == 200
    assert unrequested.json()["schema_version"] == 3
    assert unrequested.json()["media_server"]["playback_evidence"]["scope"] == "not_requested"
    assert service.calls == []
    requested = client.get("/api/v1/qualifications", params={"author_id": AUTHOR_ID})
    assert requested.status_code == 200, requested.text
    assert service.calls == [(AUTHOR_ID, 20)]
    capabilities = {row["capability"]: row for row in requested.json()["media_server"]["human_qualification"]}
    assert capabilities["playback_evidence"] == {
        "capability": "playback_evidence",
        "implementation_status": "IMPLEMENTED",
        "human_status": "PASS",
        "scope": "author",
        "author_id": AUTHOR_ID,
    }
    assert capabilities["provider_task_completion"]["reason"] == "provider_api_unsupported"
    assert capabilities["automatic_post_export_scan"]["human_status"] is None


@pytest.mark.parametrize(
    "query",
    [
        "author_id=",
        "author_id=private-sentinel",
        f"author_id={AUTHOR_ID}&author_id={AUTHOR_ID}",
        "limit=20",
        "authors=" + AUTHOR_ID,
    ],
)
def test_qualification_rejects_ambiguous_or_unbounded_scope(query_api: tuple[TestClient, _Query], query: str) -> None:
    client, service = query_api
    _login(client)
    response = client.get("/api/v1/qualifications?" + query)
    assert response.status_code == 400
    assert response.json() == {"detail": "playback_evidence_request_invalid"}
    assert service.calls == []


@pytest.mark.parametrize("path", [AUTHOR_PATH, "/api/v1/qualifications?author_id=" + AUTHOR_ID])
def test_storage_failure_does_not_return_stale_pass(query_api: tuple[TestClient, _Query], path: str) -> None:
    client, service = query_api
    _login(client)
    service.error = True
    response = client.get(path)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert "PASS" not in response.text
