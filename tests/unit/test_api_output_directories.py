"""Authenticated output policy settings, no hidden writes or directory migration."""

from __future__ import annotations

from pathlib import Path

import pytest
from _api_client import authenticated_test_client
from sqlalchemy import select

from media_sync.application.output_directories import OutputDirectoryService
from media_sync.config import Settings
from media_sync.infrastructure.db import AuthorRepository, AuthorUpsert, Database, LibraryOutputPolicy
from media_sync.infrastructure.db.migration import upgrade_database


def _settings(tmp_path: Path) -> Settings:
    settings = Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "library",
        job_dir=tmp_path / "jobs",
        _env_file=None,
    )
    upgrade_database(settings.resolved_database_url)
    return settings


def _draft(root: Path, revision: int = 0) -> dict[str, object]:
    return {
        "expected_revision": revision,
        "shared_root": str(root),
        "platform_overrides": {},
        "layout": "platform_subdirectories",
    }


def test_get_and_preview_do_not_initialize_or_create_paths(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.resolved_database_url)
    target = tmp_path / "new-media"
    try:
        with authenticated_test_client(settings) as client:
            current = client.get("/api/v1/settings/output")
            assert current.status_code == 200
            assert current.headers["cache-control"] == "no-store"
            assert current.json()["revision"] == 0
            assert current.json()["initialized"] is False
            assert current.json()["layout"] == "platform_subdirectories"
            draft = _draft(target)
            draft.pop("expected_revision")
            preview = client.post("/api/v1/settings/output/preview", json=draft)
            assert preview.status_code == 200
            assert Path(preview.json()["effective_roots"]["bili"]) == target / "bili"
        with database.session() as session:
            assert session.scalar(select(LibraryOutputPolicy)) is None
        assert not target.exists() and not settings.export_dir.exists()
    finally:
        database.dispose()


def test_save_survives_new_app_and_new_database_and_rejects_stale_cas(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    target = tmp_path / "media"
    with authenticated_test_client(settings) as client:
        saved = client.put("/api/v1/settings/output", json=_draft(target))
        assert saved.status_code == 200
        assert saved.json()["revision"] == 1
        rejected = client.put("/api/v1/settings/output", json=_draft(tmp_path / "other"))
        assert rejected.status_code == 409
        assert rejected.json() == {"detail": "output_directory_conflict", "platforms": []}
    with authenticated_test_client(settings) as client:
        assert client.get("/api/v1/settings/output").json() == saved.json()
    database = Database(settings.resolved_database_url)
    try:
        assert OutputDirectoryService(database, settings).get_policy() == saved.json()
    finally:
        database.dispose()
    assert not target.exists()


def test_bound_platform_is_protected_while_other_platform_remains_editable(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            author = AuthorRepository(session).upsert(
                AuthorUpsert(platform="bili", remote_id="42", display_name="Fixture")
            )
            author_id = author.id
        with authenticated_test_client(settings) as client:
            root = tmp_path / "media"
            assert client.put("/api/v1/settings/output", json=_draft(root)).status_code == 200
            bound = OutputDirectoryService(database, settings).bind_author_root(author_id)
            assert bound == root / "bili"
            proposed = _draft(tmp_path / "other", 1)
            rejected = client.put("/api/v1/settings/output", json=proposed)
            assert rejected.status_code == 409
            assert rejected.json() == {"detail": "output_directory_migration_required", "platforms": ["bili"]}
            proposed["platform_overrides"] = {"bili": str(bound), "dy": str(tmp_path / "douyin")}
            accepted = client.put("/api/v1/settings/output", json=proposed)
            assert accepted.status_code == 200
            assert accepted.json()["protected_platforms"] == ["bili"]
            assert OutputDirectoryService(database, settings).resolve_author_root(author_id) == bound
        assert not root.exists()
    finally:
        database.dispose()


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_revision", True),
        ("expected_revision", -1),
        ("expected_revision", "0"),
        ("expected_revision", 9_007_199_254_740_992),
        ("layout", "anything"),
        ("platform_overrides", {"unknown": None}),
        ("platform_overrides", {"bili": 123}),
        ("shared_root", "x" * 4097),
        ("other", "PRIVATE_SENTINEL"),
    ],
)
def test_closed_strict_body(tmp_path: Path, field: str, value: object) -> None:
    with authenticated_test_client(_settings(tmp_path)) as client:
        draft = _draft(tmp_path / "media")
        draft[field] = value
        response = client.put("/api/v1/settings/output", json=draft)
        assert response.status_code == 422
        assert "PRIVATE_SENTINEL" not in response.text


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/settings/output"),
        ("PUT", "/api/v1/settings/output"),
        ("POST", "/api/v1/settings/output/preview"),
    ],
)
def test_new_routes_require_authentication(tmp_path: Path, method: str, path: str) -> None:
    with authenticated_test_client(_settings(tmp_path)) as client:
        client.cookies.clear()
        assert client.request(method, path, json={}).status_code == 401


@pytest.mark.parametrize(
    "method,path", [("PUT", "/api/v1/settings/output"), ("POST", "/api/v1/settings/output/preview")]
)
def test_unsafe_routes_require_csrf(tmp_path: Path, method: str, path: str) -> None:
    with authenticated_test_client(_settings(tmp_path)) as client:
        client.event_hooks["request"] = []
        response = client.request(method, path, json=_draft(tmp_path / "media"))
        assert response.status_code == 403
        assert response.json()["detail"] in {"operator_csrf_forbidden", "operator_origin_forbidden"}


@pytest.mark.parametrize("kind", ["relative", "private", "overlap"])
def test_safe_errors_have_no_request_paths(tmp_path: Path, kind: str) -> None:
    settings = _settings(tmp_path)
    draft = _draft(tmp_path / "media")
    code = "output_directory_invalid"
    if kind == "relative":
        draft["shared_root"] = "PRIVATE_SENTINEL/relative"
    elif kind == "private":
        draft["shared_root"] = str(settings.state_dir / "PRIVATE_SENTINEL")
        code = "output_directory_unsafe"
    else:
        draft["platform_overrides"] = {"bili": str(tmp_path / "media" / "dy" / "PRIVATE_SENTINEL")}
        code = "output_directory_overlap"
    with authenticated_test_client(settings) as client:
        response = client.put("/api/v1/settings/output", json=draft)
        assert response.status_code == 400
        assert response.json()["detail"] == code
        assert "PRIVATE_SENTINEL" not in response.text
        assert str(tmp_path) not in response.text
