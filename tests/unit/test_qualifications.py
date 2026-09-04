"""Schema-v1 automated versus human qualification boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from media_sync.application.qualifications import QualificationService
from media_sync.infrastructure.db import (
    Account,
    Asset,
    Author,
    Content,
    Database,
    ExportRecord,
    OperationSnapshot,
    Subscription,
    SyncRun,
)
from media_sync.infrastructure.db.migration import upgrade_database


def _database(tmp_path: Path) -> Database:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'qualification.sqlite3').as_posix()}"
    upgrade_database(database_url)
    return Database(database_url)


def _operation(kind: str, *, state: str, result: dict[str, object]) -> OperationSnapshot:
    at = datetime(2026, 9, 5, 1, 2, 3, tzinfo=UTC)
    return OperationSnapshot(
        id=str(uuid4()),
        kind=kind,
        state=state,
        phase=None,
        progress_current=None,
        progress_total=None,
        progress_unit=None,
        requested_at=at,
        started_at=at,
        finished_at=at,
        requested_by="local-api",
        target_type=None,
        target_id=None,
        correlation_id=str(uuid4()),
        cancel_requested_at=None,
        error_code=None,
        result_summary=result,
        event_sequence=3,
        revision=2,
    )


def test_qualification_snapshot_counts_local_evidence_without_promoting_human_pass(tmp_path: Path) -> None:
    database = _database(tmp_path)
    account_id = str(uuid4())
    author_id = str(uuid4())
    subscription_id = str(uuid4())
    content_id = str(uuid4())
    at = datetime(2026, 9, 5, 1, 2, 3, tzinfo=UTC)
    try:
        with database.session() as session:
            session.add(
                Account(
                    id=account_id,
                    platform="bili",
                    adapter="mediacrawler",
                    display_name="qualified-local-evidence",
                    auth_status="authenticated",
                )
            )
            session.add(
                Author(
                    id=author_id,
                    platform="bili",
                    remote_id="123",
                    display_name="creator",
                )
            )
            session.add(Subscription(id=subscription_id, account_id=account_id, author_id=author_id))
            session.add(
                SyncRun(
                    id=str(uuid4()),
                    subscription_id=subscription_id,
                    status="succeeded",
                    started_at=at,
                    finished_at=at,
                )
            )
            session.add(
                Content(
                    id=content_id,
                    author_id=author_id,
                    platform="bili",
                    remote_type="video",
                    remote_id="BV1",
                    kind="video",
                    first_seen_at=at,
                    last_seen_at=at,
                )
            )
            session.flush()
            session.add(
                Asset(
                    id=str(uuid4()),
                    content_id=content_id,
                    platform="bili",
                    kind="video",
                    position=0,
                    status="verified",
                    semantic_fingerprint="1" * 64,
                    locator_fingerprint="2" * 64,
                )
            )
            session.add(
                ExportRecord(
                    id=str(uuid4()),
                    content_id=content_id,
                    exporter="emby",
                    exporter_version="1",
                    source_fingerprint="3" * 64,
                    output_path="opaque-to-the-projection",
                    status="succeeded",
                    exported_at=at,
                )
            )

        probe = _operation(
            "media-server-probe",
            state="succeeded",
            result={
                "provider": "emby",
                "server_version": "4.9.0",
                "library_id_digest": "4" * 64,
                "library_present": True,
            },
        )
        payload = QualificationService(database).snapshot(
            media_server_configured=True,
            media_server_operations={"media-server-probe": probe},
            generated_at=at,
        )
    finally:
        database.dispose()

    assert payload["schema_version"] == 1
    assert payload["policy"]["automated_evidence_confers_human_pass"] is False  # type: ignore[index]
    platform_rows = {row["platform"]: row for row in payload["platforms"]}  # type: ignore[union-attr]
    bili = platform_rows["bili"]
    assert bili["automated_evidence"] == {
        "account_count": 1,
        "authenticated_account_count": 1,
        "subscription_count": 1,
        "successful_sync_run_count": 1,
        "content_count": 1,
        "verified_asset_count": 1,
        "successful_export_count": 1,
    }
    assert all(
        capability["human_status"] == "NOT_RUN"
        for capability in bili["human_qualification"]  # type: ignore[union-attr]
    )
    assert platform_rows["xhs"]["automated_evidence"]["content_count"] == 0  # type: ignore[index]

    media_server = payload["media_server"]
    assert media_server["configured"] is True  # type: ignore[index]
    latest_probe = media_server["automated_evidence"]["latest_probe"]  # type: ignore[index]
    assert latest_probe["operation_id"] == probe.id
    assert latest_probe["result"]["provider"] == "emby"
    capability_rows = {
        row["capability"]: row
        for row in media_server["human_qualification"]  # type: ignore[index]
    }
    assert capability_rows["targeted_scan_acceptance"] == {
        "capability": "targeted_scan_acceptance",
        "implementation_status": "IMPLEMENTED",
        "human_status": "NOT_RUN",
    }
    assert capability_rows["scan_completion"] == {
        "capability": "scan_completion",
        "implementation_status": "NOT_IMPLEMENTED",
        "human_status": None,
    }


def test_qualification_snapshot_has_all_seven_platforms_and_no_host_or_secret_fields(tmp_path: Path) -> None:
    database = _database(tmp_path)
    try:
        payload = QualificationService(database).snapshot(media_server_configured=False)
    finally:
        database.dispose()

    rows = payload["platforms"]
    assert [row["platform"] for row in rows] == ["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"]  # type: ignore[union-attr]
    serialized = repr(payload).lower()
    assert "secret_ref" not in serialized
    assert "output_path" not in serialized
    assert "base_url" not in serialized
    assert "cidr" not in serialized
    assert "human_status': 'pass" not in serialized
