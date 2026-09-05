"""HTTP contract for bounded, publication-anchored library inspection."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from _api_client import authenticated_test_client
from fastapi.testclient import TestClient

import media_sync.interfaces.api as api_module
from media_sync.application.library import (
    LibraryInspection,
    LibraryInspectionError,
    LibraryInspectionPage,
    LibraryPublication,
)
from media_sync.config import Settings
from media_sync.exporters.emby import ManagedFileInspection
from media_sync.infrastructure.db.migration import upgrade_database


class _FakeLibraryInspectionService:
    def __init__(self, result: LibraryInspection | LibraryInspectionError) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def inspect(
        self,
        author_id: str,
        *,
        cursor: str | None,
        limit: int,
        max_bytes: int,
        deadline_seconds: float,
    ) -> LibraryInspection:
        self.calls.append(
            {
                "author_id": author_id,
                "cursor": cursor,
                "limit": limit,
                "max_bytes": max_bytes,
                "deadline_seconds": deadline_seconds,
            }
        )
        if isinstance(self.result, LibraryInspectionError):
            raise self.result
        return self.result


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    service: _FakeLibraryInspectionService,
) -> TestClient:
    settings = Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "exports",
        job_dir=tmp_path / "jobs",
        library_inspection_max_bytes=123_456,
        library_inspection_deadline_seconds=2.5,
    )
    upgrade_database(settings.resolved_database_url)
    monkeypatch.setattr(api_module, "LibraryInspectionService", lambda _database, _exporter: service)
    return authenticated_test_client(settings, app_factory=api_module.create_api_app)


def _inspection(author_id: str) -> LibraryInspection:
    publication = LibraryPublication(
        layout_version="1",
        publication_scope="1" * 64,
        job_id=str(uuid4()),
        source_fingerprint="2" * 64,
        tree_sha256="3" * 64,
        manifest_sha256="4" * 64,
        managed_file_count=2,
    )
    return LibraryInspection(
        author_id=author_id,
        publication=publication,
        freshness="current",
        freshness_reason_code=None,
        integrity="page_verified",
        integrity_reason_code=None,
        user_changes_protected=True,
        files=(ManagedFileInspection("video/episode.mp4", "5" * 64, 42),),
        page=LibraryInspectionPage(
            start_index=0,
            next_index=1,
            limit=1,
            returned_count=1,
            bytes_read=42,
            complete=False,
            budget_exhausted=False,
            next_cursor="opaque-cursor",
        ),
        allowed_actions=(),
    )


def test_library_detail_projects_only_logical_manifest_nodes_and_fixed_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author_id = str(uuid4())
    host_path_sentinel = str(tmp_path / "private-export-root")
    service = _FakeLibraryInspectionService(_inspection(author_id))
    client = _client(tmp_path, monkeypatch, service)

    response = client.get(f"/api/v1/library/{author_id}", params={"limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 2
    assert body["author_id"] == author_id
    assert body["freshness"] == "current"
    assert body["integrity"] == "page_verified"
    assert body["files"] == [{"relative_path": "video/episode.mp4", "sha256": "5" * 64, "size_bytes": 42}]
    assert body["page"] == {
        "start_index": 0,
        "next_index": 1,
        "limit": 1,
        "returned_count": 1,
        "bytes_read": 42,
        "complete": False,
        "budget_exhausted": False,
        "next_cursor": "opaque-cursor",
    }
    assert service.calls == [
        {
            "author_id": author_id,
            "cursor": None,
            "limit": 1,
            "max_bytes": 123_456,
            "deadline_seconds": 2.5,
        }
    ]
    serialized = json.dumps(body)
    assert host_path_sentinel not in serialized
    assert "output_path" not in serialized
    assert "payload" not in serialized
    assert "source_url" not in serialized


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("library_author_invalid", 404),
        ("library_author_not_found", 404),
        ("library_cursor_invalid", 400),
        ("library_cursor_stale", 409),
        ("library_publication_inconsistent", 409),
        ("library_inspection_busy", 429),
        ("library_inspection_failed", 503),
    ],
)
def test_library_detail_maps_only_fixed_error_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    status: int,
) -> None:
    service = _FakeLibraryInspectionService(LibraryInspectionError(code))
    client = _client(tmp_path / code, monkeypatch, service)

    response = client.get(f"/api/v1/library/{uuid4()}")

    assert response.status_code == status
    assert response.json() == {"detail": code}
    if status == 429:
        assert response.headers["retry-after"] == "1"


def test_library_detail_rejects_paths_unknown_parameters_and_duplicate_cursor_without_echo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author_id = str(uuid4())
    service = _FakeLibraryInspectionService(_inspection(author_id))
    client = _client(tmp_path, monkeypatch, service)
    sentinel = "private-host-path-sentinel"

    unknown = client.get(f"/api/v1/library/{author_id}", params={"path": sentinel})
    duplicate = client.get(f"/api/v1/library/{author_id}?cursor=first&cursor={sentinel}")
    oversized = client.get(f"/api/v1/library/{author_id}", params={"limit": 129})

    assert unknown.status_code == 400
    assert unknown.json() == {"detail": "library_inspection_invalid"}
    assert sentinel not in unknown.text
    assert duplicate.status_code == 400
    assert duplicate.json() == {"detail": "library_inspection_invalid"}
    assert sentinel not in duplicate.text
    assert oversized.status_code == 422
    assert oversized.json()["detail"] == "request_validation_failed"
    assert service.calls == []
