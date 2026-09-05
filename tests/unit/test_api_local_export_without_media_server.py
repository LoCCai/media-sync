"""Real local publication remains independent from optional media-server linkage."""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from _api_client import authenticated_test_client
from fastapi.testclient import TestClient
from sqlalchemy import select

import media_sync.application.media_server as media_server_module
from media_sync.config import Settings
from media_sync.infrastructure.db import (
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    Database,
)
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.infrastructure.db.models import ExportRecord, Job

NOW = datetime(2026, 9, 5, tzinfo=UTC)
SYNTHETIC_VIDEO = b"offline-export-byte-fixture-not-playback-evidence"


def _wait_operation(client: TestClient, operation_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/operations/{operation_id}")
        assert response.status_code == 200
        body = response.json()
        if body["state"] not in {"queued", "running"}:
            return body
        time.sleep(0.02)
    raise AssertionError("local export operation did not complete")


@pytest.mark.parametrize("verified", [True, False], ids=["verified-local-export", "unverified-still-blocked"])
def test_authenticated_local_export_needs_no_connector_but_keeps_archive_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    verified: bool,
) -> None:
    settings = Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "library",
        job_dir=tmp_path / "jobs",
        media_server_provider=None,
        media_server_base_url=None,
        media_server_library_id=None,
        media_server_api_key_secret_ref=None,
        media_server_library_path=None,
        media_server_allowed_cidrs=None,
        media_server_operations_enabled=False,
        _env_file=None,
    )
    assert settings.media_server_profile is None
    upgrade_database(settings.resolved_database_url)
    database = Database(settings.resolved_database_url)
    connector_attempts: list[bool] = []

    def forbidden_connector(*_args: object, **_kwargs: object) -> None:
        connector_attempts.append(True)
        raise AssertionError("local export must not construct a media-server connector")

    monkeypatch.setattr(media_server_module, "MediaServerConnector", forbidden_connector)
    source = settings.archive_dir / "fixture.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(SYNTHETIC_VIDEO)
    try:
        with database.session() as session:
            author, contents = AuthorRepository(session).upsert_with_contents(
                AuthorUpsert(platform="bili", remote_id="42", display_name="Offline local creator"),
                [
                    ContentUpsert(
                        remote_id="101",
                        remote_type="video",
                        kind="video",
                        title="Offline export fixture",
                        body="Local files do not prove remote playback.",
                        published_at=NOW,
                    )
                ],
                seen_at=NOW,
            )
            author_id = author.id
            asset = AssetRepository(session).upsert_for_content(
                contents[0].id,
                AssetUpsert(
                    platform="bili",
                    content_remote_type="video",
                    content_remote_id="101",
                    remote_id="101:video:0",
                    kind="video",
                    position=0,
                ),
            )
            if verified:
                asset.status = "verified"
                asset.local_path = str(source)
                asset.checksum_sha256 = hashlib.sha256(SYNTHETIC_VIDEO).hexdigest()
                asset.size_bytes = len(SYNTHETIC_VIDEO)
                asset.mime_type = "video/mp4"
                asset.verified_at = NOW

        with authenticated_test_client(settings) as client:
            status = client.get("/api/v1/media-server")
            assert status.status_code == 200
            assert status.json()["configuration"]["configured"] is False
            assert status.json()["allowed_actions"] == []
            assert client.post("/api/v1/media-server/probe", json={}).status_code == 409
            inspection = client.get(f"/api/v1/library/{author_id}")
            assert inspection.status_code == 200
            assert ("export_author" in inspection.json()["allowed_actions"]) is verified

            started = client.post("/api/v1/emby/export", json={"author_id": author_id})
            assert started.status_code == 202
            finished = _wait_operation(client, started.json()["operation_id"])
            if verified:
                assert finished["state"] == "succeeded"
                assert finished["error_code"] is None
                videos = list(settings.export_dir.rglob("*.mp4"))
                assert len(videos) == 1 and videos[0].read_bytes() == SYNTHETIC_VIDEO
                assert len(list(settings.export_dir.rglob("tvshow.nfo"))) == 1
                assert len(list(settings.export_dir.rglob("*.nfo"))) == 2
                assert len(list(settings.export_dir.rglob("body.txt"))) == 1
                replay = client.post("/api/v1/emby/export", json={"author_id": author_id})
                assert replay.status_code == 202
                replayed = _wait_operation(client, replay.json()["operation_id"])
                assert replayed["state"] == "succeeded"
                assert replayed["result"]["already_exported"] is True
            else:
                assert finished["state"].startswith("failed")
                assert finished["error_code"] == "asset_not_verified"
                assert not list(settings.export_dir.rglob("*.nfo"))
                assert not list(settings.export_dir.rglob("*.mp4"))

        assert connector_attempts == []
        assert source.read_bytes() == SYNTHETIC_VIDEO
        with database.session() as session:
            export_records = session.scalars(select(ExportRecord)).all()
            if verified:
                assert len(export_records) == 1 and export_records[0].status == "succeeded"
                export_jobs = session.scalars(select(Job).where(Job.job_type == "export.emby")).all()
                assert len(export_jobs) == 1 and export_jobs[0].status == "succeeded"
            else:
                assert not export_records
    finally:
        database.dispose()
