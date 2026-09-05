"""Focused HTTP contract for the bounded, redaction-safe support bundle."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from _api_client import authenticated_test_client

from media_sync.config import Settings
from media_sync.infrastructure.db.database import Database
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.infrastructure.db.models import Account, Author, Operation

EXPECTED_REVISION = "0009_subscription_removal"
PRIVATE_TIME = datetime(2037, 1, 2, 3, 4, 5, tzinfo=UTC)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        state_dir=tmp_path / "state-private",
        archive_dir=tmp_path / "archive-private",
        export_dir=tmp_path / "library-private",
        job_dir=tmp_path / "jobs-private",
        mediacrawler_runtime_dir=tmp_path / "mediacrawler-private",
        _env_file=None,
    )


def _migrated_settings(tmp_path: Path) -> Settings:
    settings = _settings(tmp_path)
    upgrade_database(settings.resolved_database_url)
    return settings


def _failed_operation(*, number: int, error_code: str, private_sentinel: str) -> Operation:
    return Operation(
        id=str(UUID(int=number)),
        kind="pipeline-run",
        state="failed_terminal",
        requested_at=PRIVATE_TIME,
        finished_at=PRIVATE_TIME,
        requested_by=f"private-requester-{private_sentinel}",
        request_fingerprint="f" * 64,
        exclusive_key=f"pipeline-run:{private_sentinel}",
        correlation_id=str(UUID(int=number + 10_000)),
        error_code=error_code,
        result_summary={
            "request": {"url": f"https://example.invalid/sync?token={private_sentinel}"},
            "windows_path": rf"C:\Users\private\{private_sentinel}",
            "posix_path": f"/home/private/{private_sentinel}",
            "unc_path": rf"\\server\share\{private_sentinel}",
            "qr_material": private_sentinel,
            "traceback": f"RuntimeError: {private_sentinel}",
        },
    )


def test_support_bundle_returns_raw_canonical_json_with_closed_aggregate_shape(tmp_path: Path) -> None:
    settings = _migrated_settings(tmp_path)
    sentinel = "credential-private-sentinel"
    operation_id = str(UUID(int=501))
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            session.add_all(
                [
                    Account(
                        platform="xhs",
                        display_name="private-account",
                        login_method="cookie",
                        credential_ref=f"keyring:{sentinel}",
                        profile_path=rf"C:\Users\private\{sentinel}",
                    ),
                    Author(
                        platform="xhs",
                        remote_id="private-author",
                        display_name="Private Author",
                        profile_url=f"https://example.invalid/author?cookie={sentinel}",
                        raw={"session_token": sentinel},
                    ),
                    _failed_operation(number=501, error_code="pipeline_run_failed", private_sentinel=sentinel),
                    _failed_operation(number=502, error_code="pipeline_run_failed", private_sentinel=sentinel),
                ]
            )
    finally:
        database.dispose()

    with authenticated_test_client(settings) as client:
        response = client.get("/api/v1/support-bundle")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert response.content == json.dumps(
        body,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")

    assert set(body) == {
        "schema_version",
        "generated_at",
        "project",
        "build",
        "database",
        "entity_counts",
        "operations",
    }
    assert set(body["project"]) == {"name", "version"}
    assert set(body["build"]) == {"expected_schema_revision"}
    assert set(body["database"]) == {
        "reachable",
        "ready",
        "schema_revision",
        "revision_matches",
    }
    assert set(body["entity_counts"]) == {
        "accounts",
        "subscriptions",
        "authors",
        "contents",
        "assets",
        "jobs",
        "operations",
    }
    assert set(body["operations"]) == {"state_counts", "kind_counts", "recent_error_counts"}
    assert all(set(item) == {"state", "count"} for item in body["operations"]["state_counts"])
    assert all(set(item) == {"kind", "count"} for item in body["operations"]["kind_counts"])
    assert all(set(item) == {"error_code", "count"} for item in body["operations"]["recent_error_counts"])
    assert body["build"] == {"expected_schema_revision": EXPECTED_REVISION}
    assert body["database"] == {
        "reachable": True,
        "ready": True,
        "schema_revision": EXPECTED_REVISION,
        "revision_matches": True,
    }
    assert body["entity_counts"] == {
        "accounts": 1,
        "subscriptions": 0,
        "authors": 1,
        "contents": 0,
        "assets": 0,
        "jobs": 0,
        "operations": 2,
    }
    assert body["operations"]["recent_error_counts"] == [{"error_code": "pipeline_run_failed", "count": 2}]

    response_text = response.text
    assert not response.content.startswith(b'"{')
    assert sentinel not in response_text
    assert operation_id not in response_text
    assert "example.invalid" not in response_text
    assert "private-requester" not in response_text
    assert "2037-01-02" not in response_text
    assert "f" * 64 not in response_text
    assert str(tmp_path) not in response_text
    assert tmp_path.as_posix() not in response_text
    assert "C:\\\\Users" not in response_text
    assert "\\\\server" not in response_text
    assert "traceback" not in response_text.lower()
    assert "qr_material" not in response_text.lower()
    assert "session_token" not in response_text.lower()


def test_support_bundle_database_failure_has_only_a_fixed_safe_code(tmp_path: Path) -> None:
    settings = _migrated_settings(tmp_path)
    database_path = Path(settings.resolved_database_url.removeprefix("sqlite+pysqlite:///"))

    with authenticated_test_client(settings) as client:
        database = Database(settings.resolved_database_url)
        try:
            database.drop_schema()
        finally:
            database.dispose()

        response = client.get("/api/v1/support-bundle")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "support_bundle_database_failed"}
    assert str(database_path) not in response.text
    assert database_path.as_posix() not in response.text
    assert "sqlite" not in response.text.lower()
