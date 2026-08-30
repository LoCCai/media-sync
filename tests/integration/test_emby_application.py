"""Offline database-to-Emby orchestration and fencing coverage."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import select, update

from media_sync.application.emby import (
    EmbyExportOutcome,
    EmbyExportRequest,
    EmbyExportService,
    emby_export_natural_key,
    export_error_is_retryable,
)
from media_sync.exporters.emby import EmbyExporter, ExportAuthor, ExportError, author_relative_directory
from media_sync.infrastructure.db import (
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    Database,
    ExportRecordConflictError,
    ExportRecordRepository,
    JobRepository,
)
from media_sync.infrastructure.db.models import Asset, Author, Content, ExportRecord, Job

NOW = datetime(2026, 8, 30, 1, 2, 3, tzinfo=UTC)


def test_export_request_normalizes_identifiers_and_rejects_invalid_controls() -> None:
    author_id = "00000000-0000-0000-0000-000000000001"
    request = EmbyExportRequest(f"  {author_id}  ", "  worker-a  ")

    assert request.author_id == author_id
    assert request.worker_id == "worker-a"
    with pytest.raises(ValueError, match="author_id"):
        EmbyExportRequest("not-a-uuid", "worker")
    with pytest.raises(ValueError, match="worker_id"):
        EmbyExportRequest(author_id, "worker\nsecond-line")
    with pytest.raises(ValueError, match="lease_seconds"):
        EmbyExportRequest(author_id, "worker", lease_seconds=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="max_attempts"):
        EmbyExportRequest(author_id, "worker", max_attempts=True)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "code",
    [
        "asset_not_verified",
        "export_prepare_conflict",
        "export_prepare_failed",
        "export_job_unavailable",
        "export_lease_lost",
        "export_lease_check_failed",
        "export_finalize_failed",
        "export_failure_finalize_failed",
        "publish_capture_failed",
        "no_clobber_publish_failed",
    ],
)
def test_transient_export_failures_are_classified_retryable(code: str) -> None:
    assert export_error_is_retryable(code) is True


@pytest.mark.parametrize(
    "code",
    [
        "author_not_found",
        "export_job_terminal",
        "managed_file_modified",
        "no_clobber_unsupported",
        "publish_recovery_required",
        "publish_transaction_invalid",
    ],
)
def test_terminal_or_manual_export_failures_are_not_classified_retryable(code: str) -> None:
    assert export_error_is_retryable(code) is False


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'emby.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_author(
    database: Database,
    source_root: Path,
    *,
    include_video: bool = True,
    secret: str | None = None,
) -> tuple[str, str | None]:
    with database.session() as session:
        author, contents = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(
                platform="xhs",
                remote_id="creator-1",
                display_name="Creator One",
                handle="@creator",
                raw={"ignored": secret} if secret else {},
            ),
            [
                ContentUpsert(
                    remote_id="text-1",
                    remote_type="note",
                    kind="text",
                    title="Text post",
                    body="A text-only post",
                    published_at=NOW,
                    raw={"ignored": secret} if secret else {},
                    metrics={"ignored": secret} if secret else {},
                    canonical_url=f"https://example.invalid/post?token={secret}" if secret else None,
                ),
                *(
                    [
                        ContentUpsert(
                            remote_id="video-1",
                            remote_type="note",
                            kind="video",
                            title="Video post",
                            body="A video post",
                            published_at=NOW,
                        )
                    ]
                    if include_video
                    else []
                ),
            ],
            seen_at=NOW,
        )
        video_content = next((content for content in contents if content.remote_id == "video-1"), None)
        asset_id: str | None = None
        if video_content is not None:
            source_root.mkdir(parents=True, exist_ok=True)
            payload = b"offline-video-payload"
            source = (source_root / "video.mp4").absolute()
            source.write_bytes(payload)
            asset = AssetRepository(session).upsert_for_content(
                video_content.id,
                AssetUpsert(
                    platform="xhs",
                    content_remote_type="note",
                    content_remote_id="video-1",
                    kind="video",
                    position=0,
                    remote_id="asset-video-1",
                    source_url="https://cdn.example.invalid/video",
                ),
            )
            asset.status = "verified"
            asset.local_path = str(source)
            asset.checksum_sha256 = hashlib.sha256(payload).hexdigest()
            asset.size_bytes = len(payload)
            asset.mime_type = "video/mp4"
            asset.verified_at = NOW
            if secret is not None:
                asset.source_url = f"https://cdn.example.invalid/video?signature={secret}"
                asset.locator = {"version": 1, "type": "direct", "url": asset.source_url}
                asset.raw = {"response_headers": {"cookie": secret}}
            asset_id = asset.id
        return author.id, asset_id


def _service(
    database: Database,
    tmp_path: Path,
    *,
    fault: Callable[[str, str | None], None] | None = None,
    clock: Callable[[], datetime] = lambda: NOW,
) -> EmbyExportService:
    exporter = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=fault,
    )
    return EmbyExportService(database, exporter, clock=clock)


def _export(database: Database, tmp_path: Path, author_id: str, *, worker: str = "worker-a") -> EmbyExportOutcome:
    return _service(database, tmp_path).export_author(EmbyExportRequest(author_id, worker, lease_seconds=60))


def test_db_snapshot_exports_golden_tree_and_is_idempotent(database: Database, tmp_path: Path) -> None:
    author_id, _ = _seed_author(database, tmp_path / "archive")
    service = _service(database, tmp_path)

    first = service.export_author(EmbyExportRequest(author_id, "worker-a", lease_seconds=60))
    before = {
        path.relative_to(tmp_path / "library").as_posix(): path.read_bytes()
        for path in sorted((tmp_path / "library").rglob("*"))
        if path.is_file()
    }
    repeated = service.export_author(EmbyExportRequest(author_id, "worker-b", lease_seconds=60))
    after = {
        path.relative_to(tmp_path / "library").as_posix(): path.read_bytes()
        for path in sorted((tmp_path / "library").rglob("*"))
        if path.is_file()
    }

    assert first.already_exported is False
    assert repeated.already_exported is True
    assert repeated.job_id == first.job_id
    assert repeated.source_fingerprint == first.source_fingerprint
    assert repeated.rendered_fingerprint == first.rendered_fingerprint
    assert repeated.managed_file_count == first.managed_file_count
    assert first.rendered_fingerprint == "651eb1ad41bde0f84b3eccc3ecf27c8ac03635b3049251e08f3261504949f8c6"
    assert len(first.rendered_fingerprint or "") == 64
    assert not Path(first.output_path).is_absolute()
    assert before == after
    assert any(path.endswith(".mp4") for path in before)
    assert any(path.endswith("body.txt") for path in before)

    with database.session() as session:
        jobs = list(session.scalars(select(Job)).all())
        records = list(session.scalars(select(ExportRecord).order_by(ExportRecord.content_id)).all())
        assets = list(session.scalars(select(Asset)).all())
    assert len(jobs) == 1
    assert jobs[0].status == "succeeded"
    assert len(records) == 2
    assert {record.status for record in records} == {"succeeded"}
    assert {record.rendered_fingerprint for record in records} == {first.rendered_fingerprint}
    assert {record.output_path for record in records} == {first.output_path}
    assert {asset.status for asset in assets} == {"verified"}


def test_asset_generation_repair_escapes_terminal_missing_source_identity(
    database: Database,
    tmp_path: Path,
) -> None:
    payload = b"offline-video-payload"
    digest = hashlib.sha256(payload).hexdigest()
    author_id, asset_id = _seed_author(database, tmp_path / "archive")
    assert asset_id is not None
    with database.session() as session:
        asset = AssetRepository(session).require(asset_id)
        original_path = Path(str(asset.local_path))
        assert asset.generation == 1
        assert asset.checksum_sha256 == digest
    original_path.unlink()
    service = _service(database, tmp_path)

    with pytest.raises(ExportError) as missing:
        service.export_author(EmbyExportRequest(author_id, "missing-source-worker", max_attempts=1))

    assert missing.value.code == "asset_source_missing"
    with database.session() as session:
        failed_job = session.scalar(select(Job).where(Job.job_type == "export.emby"))
        failed_records = list(session.scalars(select(ExportRecord)).all())
        assert failed_job is not None
        assert failed_job.status == "failed_terminal"
        assert {record.status for record in failed_records} == {"failed_terminal"}
        failed_source_fingerprint = str(failed_job.payload["source_fingerprint"])
        failed_natural_key = failed_job.natural_key
        failed_job_id = failed_job.id

        assets = AssetRepository(session)
        asset = assets.require(asset_id)
        repaired = assets.reset_verified_archive(
            asset.id,
            expected_generation=asset.generation,
            expected_local_path=str(original_path),
            expected_checksum_sha256=digest,
            expected_size_bytes=len(payload),
            error_code="archive_blob_missing",
            error_message="verified source disappeared before export",
            at=NOW + timedelta(seconds=1),
        )
        assert repaired.generation == 2
        assert repaired.status == "discovered"
        original_path.write_bytes(payload)
        repaired.status = "verified"
        repaired.local_path = str(original_path)
        repaired.checksum_sha256 = digest
        repaired.size_bytes = len(payload)
        repaired.mime_type = "video/mp4"
        repaired.downloaded_at = NOW + timedelta(seconds=2)
        repaired.verified_at = NOW + timedelta(seconds=2)

    recovered = service.export_author(EmbyExportRequest(author_id, "repaired-source-worker", max_attempts=1))
    replayed = service.export_author(EmbyExportRequest(author_id, "replay-worker", max_attempts=1))

    assert recovered.already_exported is False
    assert replayed.already_exported is True
    assert replayed.job_id == recovered.job_id
    assert recovered.job_id != failed_job_id
    assert recovered.source_fingerprint != failed_source_fingerprint
    video = next((tmp_path / "library" / recovered.output_path).glob("Season 2026/*.mp4"))
    assert video.read_bytes() == payload
    content_sources = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (tmp_path / "library" / recovered.output_path).glob("Season 2026/*.assets/source.json")
    ]
    video_source = next(source for source in content_sources if source["assets"])
    assert video_source["assets"] == [
        {
            "checksum_sha256": digest,
            "generation": 2,
            "kind": "video",
            "mime_type": "video/mp4",
            "position": 0,
            "remote_id": "asset-video-1",
            "size_bytes": len(payload),
        }
    ]
    with database.session() as session:
        jobs = list(session.scalars(select(Job).where(Job.job_type == "export.emby").order_by(Job.created_at)).all())
        records = list(session.scalars(select(ExportRecord)).all())
        repaired_asset = AssetRepository(session).require(asset_id)
    assert [(job.status, job.attempts) for job in jobs] == [("failed_terminal", 1), ("succeeded", 1)]
    assert jobs[0].natural_key == failed_natural_key
    assert jobs[1].natural_key != failed_natural_key
    assert {record.status for record in records if record.source_fingerprint == failed_source_fingerprint} == {
        "failed_terminal"
    }
    assert {record.status for record in records if record.source_fingerprint == recovered.source_fingerprint} == {
        "succeeded"
    }
    assert repaired_asset.generation == 2
    assert repaired_asset.status == "verified"
    assert repaired_asset.checksum_sha256 == digest


def test_succeeded_export_replay_rejects_missing_managed_file(database: Database, tmp_path: Path) -> None:
    author_id, _ = _seed_author(database, tmp_path / "archive")
    service = _service(database, tmp_path)
    first = service.export_author(EmbyExportRequest(author_id, "worker-a", lease_seconds=60))
    managed_nfo = next((tmp_path / "library" / first.output_path).glob("Season 2026/*.nfo"))
    managed_nfo.unlink()

    with pytest.raises(ExportError) as raised:
        service.export_author(EmbyExportRequest(author_id, "worker-b", lease_seconds=60))

    assert raised.value.code == "published_export_invalid"
    with database.session() as session:
        jobs = list(session.scalars(select(Job)).all())
        records = list(session.scalars(select(ExportRecord)).all())
    assert len(jobs) == 1
    assert jobs[0].status == "succeeded"
    assert {record.status for record in records} == {"succeeded"}


def test_succeeded_export_replay_rejects_manifest_metadata_only_tampering(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "archive")
    service = _service(database, tmp_path)
    first = service.export_author(EmbyExportRequest(author_id, "worker-a", lease_seconds=60))
    manifest_path = tmp_path / "library" / first.output_path / ".media-sync-managed-v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["content_fingerprints"][0]["sha256"] = "f" * 64
    tampered = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    manifest_path.write_bytes(tampered)

    with pytest.raises(ExportError) as raised:
        service.export_author(EmbyExportRequest(author_id, "worker-b", lease_seconds=60))

    assert raised.value.code == "published_export_invalid"
    assert manifest_path.read_bytes() == tampered


def test_db_tree_anchor_rejects_forged_manifest_claiming_user_file(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "unused", include_video=False)
    with database.session() as session:
        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        content.tombstoned_at = NOW
    service = _service(database, tmp_path)
    empty = service.export_author(EmbyExportRequest(author_id, "worker-empty", lease_seconds=60))
    author_directory = tmp_path / "library" / empty.output_path
    manifest_path = author_directory / ".media-sync-managed-v1.json"
    user_file = author_directory / "user-preserve.txt"
    user_payload = b"must remain user-owned"
    user_file.write_bytes(user_payload)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"].append(
        {
            "path": user_file.name,
            "sha256": hashlib.sha256(user_payload).hexdigest(),
            "size_bytes": len(user_payload),
        }
    )
    manifest["files"].sort(key=lambda row: (row["path"].casefold(), row["path"]))
    canonical_rows = (
        json.dumps(manifest["files"], ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    manifest["tree_sha256"] = hashlib.sha256(canonical_rows).hexdigest()
    forged = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    manifest_path.write_bytes(forged)

    with pytest.raises(ExportError) as replayed:
        service.export_author(EmbyExportRequest(author_id, "worker-replay", lease_seconds=60))
    assert replayed.value.code == "published_export_invalid"

    with database.session() as session:
        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        content.tombstoned_at = None
    with pytest.raises(ExportError) as advanced:
        service.export_author(EmbyExportRequest(author_id, "worker-advanced", lease_seconds=60))
    assert advanced.value.code == "predecessor_mismatch"
    assert user_file.read_bytes() == user_payload
    assert manifest_path.read_bytes() == forged


def test_first_export_rejects_unexpected_managed_manifest_without_overwrite(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "unused", include_video=False)
    author = ExportAuthor(
        platform="xhs",
        remote_id="creator-1",
        display_name="Creator One",
        handle="@creator",
    )
    author_directory = tmp_path / "library" / author_relative_directory(author)
    author_directory.mkdir(parents=True)
    manifest = author_directory / ".media-sync-managed-v1.json"
    sentinel = b'{"untrusted":true}\n'
    manifest.write_bytes(sentinel)

    with pytest.raises(ExportError) as raised:
        _export(database, tmp_path, author_id)

    assert raised.value.code == "predecessor_mismatch"
    assert manifest.read_bytes() == sentinel


def test_tombstone_to_empty_snapshot_removes_managed_content_and_replays(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "unused", include_video=False)
    service = _service(database, tmp_path)
    populated = service.export_author(EmbyExportRequest(author_id, "worker-a", lease_seconds=60))
    author_directory = tmp_path / "library" / populated.output_path
    assert list(author_directory.rglob("*.nfo"))

    with database.session() as session:
        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        content.tombstoned_at = NOW + timedelta(seconds=1)

    emptied = service.export_author(EmbyExportRequest(author_id, "worker-b", lease_seconds=60))
    replayed = service.export_author(EmbyExportRequest(author_id, "worker-c", lease_seconds=60))

    assert emptied.already_exported is False
    assert emptied.source_fingerprint != populated.source_fingerprint
    assert emptied.managed_file_count == 2
    assert replayed.already_exported is True
    assert replayed.rendered_fingerprint == emptied.rendered_fingerprint
    assert replayed.managed_file_count == emptied.managed_file_count
    assert [path.name for path in author_directory.rglob("*.nfo")] == ["tvshow.nfo"]
    with database.session() as session:
        jobs = list(session.scalars(select(Job).order_by(Job.created_at, Job.id)).all())
        records = list(session.scalars(select(ExportRecord)).all())
    assert len(jobs) == 2
    assert {job.status for job in jobs} == {"succeeded"}
    assert len(records) == 1
    assert records[0].status == "succeeded"


def test_text_without_assets_is_allowed_but_discovered_asset_blocks_export(
    database: Database,
    tmp_path: Path,
) -> None:
    text_author, _ = _seed_author(database, tmp_path / "unused", include_video=False)
    result = _export(database, tmp_path / "text-export", text_author)
    assert result.already_exported is False
    with database.session() as session:
        job_count_before = len(list(session.scalars(select(Job)).all()))

    blocked_author, asset_id = _seed_author(database, tmp_path / "blocked-archive")
    assert asset_id is not None
    with database.session() as session:
        asset = session.get(Asset, asset_id)
        assert asset is not None
        asset.status = "discovered"
        asset.local_path = None
        asset.checksum_sha256 = None
        asset.size_bytes = None
        asset.mime_type = None
        asset.verified_at = None

    with pytest.raises(ExportError) as raised:
        _export(database, tmp_path / "blocked-export", blocked_author)
    assert raised.value.code == "asset_not_verified"

    with database.session() as session:
        asset = session.get(Asset, asset_id)
        assert asset is not None
        asset.status = "verified"
    with pytest.raises(ExportError) as incomplete:
        _export(database, tmp_path / "blocked-export", blocked_author)
    assert incomplete.value.code == "verified_asset_incomplete"

    with database.session() as session:
        jobs_after = list(session.scalars(select(Job)).all())
    assert len(jobs_after) == job_count_before


def test_user_modified_managed_file_is_preserved_and_failure_is_terminal(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "archive")
    first = _export(database, tmp_path, author_id)
    edited = next((tmp_path / "library" / first.output_path).glob("Season 2026/*video-1*.nfo"))
    edited.write_bytes(b"user-owned-change")
    with database.session() as session:
        content = session.scalar(select(Content).where(Content.remote_id == "video-1"))
        assert content is not None
        content.title = "Changed title"

    with pytest.raises(ExportError) as raised:
        _export(database, tmp_path, author_id, worker="worker-b")

    assert raised.value.code == "predecessor_mismatch"
    assert edited.read_bytes() == b"user-owned-change"
    with pytest.raises(ExportError) as repeated:
        _export(database, tmp_path, author_id, worker="worker-c")
    assert repeated.value.code == "export_job_terminal"
    assert edited.read_bytes() == b"user-owned-change"
    with database.session() as session:
        jobs = list(session.scalars(select(Job).order_by(Job.created_at)).all())
        failed_records = list(
            session.scalars(select(ExportRecord).where(ExportRecord.status == "failed_terminal")).all()
        )
    assert [job.status for job in jobs] == ["succeeded", "failed_terminal"]
    assert {record.error_message for record in failed_records} == {"predecessor_mismatch"}


def test_stale_publish_is_retryable_with_the_same_owned_job(database: Database, tmp_path: Path) -> None:
    author_id, _ = _seed_author(database, tmp_path / "archive")
    _export(database, tmp_path, author_id)
    with database.session() as session:
        content = session.scalar(select(Content).where(Content.remote_id == "video-1"))
        assert content is not None
        content.title = "New snapshot title"

    changed = False
    original_manifest: bytes | None = None

    def advance_manifest(event: str, _: str | None) -> None:
        nonlocal changed, original_manifest
        if event != "before_manifest" or changed:
            return
        changed = True
        manifest = next((tmp_path / "library").rglob(".media-sync-managed-v1.json"))
        original_manifest = manifest.read_bytes()
        manifest.write_bytes(original_manifest + b" ")

    stale_service = _service(database, tmp_path, fault=advance_manifest)
    with pytest.raises(ExportError) as raised:
        stale_service.export_author(EmbyExportRequest(author_id, "worker-stale", lease_seconds=60))
    assert raised.value.code == "stale_publish"
    staging_root = tmp_path / "work" / "staging"
    assert all(path.is_dir() and len(path.relative_to(staging_root).parts) == 1 for path in staging_root.rglob("*"))

    with database.session() as session:
        retryable_job = session.scalar(select(Job).where(Job.status == "failed_retryable"))
        retryable_records = list(
            session.scalars(select(ExportRecord).where(ExportRecord.status == "failed_retryable")).all()
        )
    assert retryable_job is not None
    assert retryable_job.last_error_code == "stale_publish"
    assert retryable_records
    assert {record.error_message for record in retryable_records} == {"stale_publish"}

    assert original_manifest is not None
    next((tmp_path / "library").rglob(".media-sync-managed-v1.json")).write_bytes(original_manifest)
    retried = _export(database, tmp_path, author_id, worker="worker-retry")
    assert retried.job_id == retryable_job.id
    assert retried.already_exported is False
    with database.session() as session:
        job = session.get(Job, retryable_job.id)
        retried_records = list(
            session.scalars(
                select(ExportRecord).where(ExportRecord.source_fingerprint == retried.source_fingerprint)
            ).all()
        )
    assert job is not None and job.status == "succeeded"
    assert {record.status for record in retried_records} == {"succeeded"}


def test_stale_lease_after_render_never_publishes_or_completes(database: Database, tmp_path: Path) -> None:
    author_id, _ = _seed_author(database, tmp_path / "archive")
    expired = False

    def expire_lease(event: str, _: str | None) -> None:
        nonlocal expired
        if event != "after_stage_file" or expired:
            return
        expired = True
        with database.session() as session:
            session.execute(
                update(Job)
                .where(Job.job_type == "export.emby", Job.status == "running")
                .values(lease_expires_at=NOW - timedelta(seconds=1))
            )

    service = _service(database, tmp_path, fault=expire_lease)
    with pytest.raises(ExportError) as raised:
        service.export_author(EmbyExportRequest(author_id, "stale-worker", lease_seconds=60, max_attempts=1))

    assert raised.value.code == "export_lease_lost"
    assert not list((tmp_path / "library").rglob(".media-sync-managed-v1.json"))
    staging_root = tmp_path / "work" / "staging"
    assert all(path.is_dir() and len(path.relative_to(staging_root).parts) == 1 for path in staging_root.rglob("*"))
    with database.session() as session:
        job = session.scalar(select(Job))
        records = list(session.scalars(select(ExportRecord)).all())
    assert job is not None and job.status == "running"
    assert {record.status for record in records} == {"running"}
    assert all(record.rendered_fingerprint is None for record in records)

    with pytest.raises(ExportError) as exhausted:
        _service(database, tmp_path).export_author(
            EmbyExportRequest(author_id, "recovery-worker", lease_seconds=60, max_attempts=1)
        )
    assert exhausted.value.code == "export_job_terminal"
    with database.session() as session:
        terminal_job = session.scalar(select(Job))
        terminal_records = list(session.scalars(select(ExportRecord)).all())
    assert terminal_job is not None and terminal_job.status == "failed_terminal"
    assert terminal_job.last_error_code == "lease_expired"
    assert {record.status for record in terminal_records} == {"failed_terminal"}
    assert {record.error_message for record in terminal_records} == {"export_lease_expired"}


def test_finalize_failure_rolls_back_records_and_job_together(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "archive")
    original_complete = ExportRecordRepository.complete
    injected = False

    def fail_after_first_complete(self: ExportRecordRepository, *args: object, **kwargs: object) -> ExportRecord:
        nonlocal injected
        record = original_complete(self, *args, **kwargs)  # type: ignore[arg-type]
        if not injected:
            injected = True
            raise RuntimeError("signed-url-secret-must-not-persist")
        return record

    monkeypatch.setattr(ExportRecordRepository, "complete", fail_after_first_complete)
    with pytest.raises(ExportError) as raised:
        _export(database, tmp_path, author_id)

    assert raised.value.code == "export_finalize_failed"
    assert list((tmp_path / "library").rglob(".media-sync-managed-v1.json"))
    with database.session() as session:
        job = session.scalar(select(Job))
        records = list(session.scalars(select(ExportRecord)).all())
    assert job is not None and job.status == "running"
    assert {record.status for record in records} == {"running"}
    assert all(record.rendered_fingerprint is None and record.exported_at is None for record in records)
    assert all("signed-url-secret" not in (record.error_message or "") for record in records)


def test_last_attempt_published_tree_recovers_without_republishing_network_inputs(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "archive")
    original_complete = JobRepository.complete

    def fail_job_finalize(self: JobRepository, *args: object, **kwargs: object) -> Job:
        raise RuntimeError("crash after filesystem publication")

    monkeypatch.setattr(JobRepository, "complete", fail_job_finalize)
    with pytest.raises(ExportError) as failed:
        _service(database, tmp_path).export_author(
            EmbyExportRequest(author_id, "worker-crash", lease_seconds=60, max_attempts=1)
        )
    assert failed.value.code == "export_finalize_failed"
    with database.session() as session:
        job = session.scalar(select(Job))
        records = list(session.scalars(select(ExportRecord)).all())
    assert job is not None and job.status == "running" and job.attempts == job.max_attempts == 1
    assert "intent" in job.payload and "result" not in job.payload
    assert len(job.payload["intent"]["records"]) == 2
    assert {item["source_fingerprint"] for item in job.payload["intent"]["records"]} == {
        job.payload["source_fingerprint"]
    }
    assert {record.status for record in records} == {"running"}

    monkeypatch.setattr(JobRepository, "complete", original_complete)
    recovered = _service(database, tmp_path, clock=lambda: NOW + timedelta(seconds=61)).export_author(
        EmbyExportRequest(author_id, "worker-recover", lease_seconds=60, max_attempts=1)
    )

    assert recovered.already_exported is True
    assert recovered.job_id == job.id
    with database.session() as session:
        finalized = session.get(Job, job.id)
        finalized_records = list(session.scalars(select(ExportRecord)).all())
    assert finalized is not None and finalized.status == "succeeded" and finalized.attempts == 1
    assert (
        "intent" not in finalized.payload
        and finalized.payload["result"]["tree_sha256"] == recovered.rendered_fingerprint
    )
    assert {record.status for record in finalized_records} == {"succeeded"}


def test_pending_intent_refuses_manifest_metadata_tamper_recovery(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "archive")
    original_complete = JobRepository.complete

    def fail_job_finalize(self: JobRepository, *args: object, **kwargs: object) -> Job:
        raise RuntimeError("crash after filesystem publication")

    monkeypatch.setattr(JobRepository, "complete", fail_job_finalize)
    with pytest.raises(ExportError) as failed:
        _service(database, tmp_path).export_author(
            EmbyExportRequest(author_id, "worker-crash", lease_seconds=60, max_attempts=1)
        )
    assert failed.value.code == "export_finalize_failed"
    manifest_path = next((tmp_path / "library").rglob(".media-sync-managed-v1.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["content_fingerprints"][0]["sha256"] = "f" * 64
    tampered = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    manifest_path.write_bytes(tampered)

    monkeypatch.setattr(JobRepository, "complete", original_complete)
    with pytest.raises(ExportError) as recovery:
        _service(database, tmp_path, clock=lambda: NOW + timedelta(seconds=61)).export_author(
            EmbyExportRequest(author_id, "worker-recover", lease_seconds=60, max_attempts=1)
        )

    assert recovery.value.code == "export_job_terminal"
    assert manifest_path.read_bytes() == tampered
    with database.session() as session:
        job = session.scalar(select(Job))
        records = list(session.scalars(select(ExportRecord)).all())
    assert job is not None and job.status == "failed_terminal"
    assert "intent" in job.payload and "result" not in job.payload
    assert {record.status for record in records} == {"failed_terminal"}


def test_recovery_finalizes_published_b_before_exporting_current_c(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "unused", include_video=False)
    first = _export(database, tmp_path, author_id)
    with database.session() as session:
        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        content.title = "Snapshot B"

    original_complete = JobRepository.complete

    def fail_job_finalize(self: JobRepository, *args: object, **kwargs: object) -> Job:
        raise RuntimeError("crash after B publication")

    monkeypatch.setattr(JobRepository, "complete", fail_job_finalize)
    with pytest.raises(ExportError) as failed_b:
        _service(database, tmp_path).export_author(
            EmbyExportRequest(author_id, "worker-b", lease_seconds=60, max_attempts=1)
        )
    assert failed_b.value.code == "export_finalize_failed"

    monkeypatch.setattr(JobRepository, "complete", original_complete)
    with database.session() as session:
        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        content.title = "Snapshot C"
    current = _service(database, tmp_path, clock=lambda: NOW + timedelta(seconds=61)).export_author(
        EmbyExportRequest(author_id, "worker-c", lease_seconds=60, max_attempts=1)
    )

    assert current.already_exported is False
    assert current.source_fingerprint != first.source_fingerprint
    with database.session() as session:
        jobs = list(session.scalars(select(Job).order_by(Job.created_at, Job.id)).all())
    assert len(jobs) == 3 and {job.status for job in jobs} == {"succeeded"}
    by_id = {job.id: job for job in jobs}
    heads = {job.payload["predecessor_job_id"] for job in jobs if job.payload["predecessor_job_id"] is not None}
    assert len(heads) == 2
    current_job = next(job for job in jobs if job.id == current.job_id)
    recovered_b = by_id[current_job.payload["predecessor_job_id"]]
    assert recovered_b.payload["predecessor_job_id"] == first.job_id
    assert recovered_b.payload["result"]["tree_sha256"]


def test_publication_chain_allows_source_cycle_a_b_a(database: Database, tmp_path: Path) -> None:
    author_id, _ = _seed_author(database, tmp_path / "unused", include_video=False)
    first_a = _export(database, tmp_path, author_id)
    with database.session() as session:
        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        content.title = "Snapshot B"
    snapshot_b = _export(database, tmp_path, author_id, worker="worker-b")
    with database.session() as session:
        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        content.title = "Text post"
    second_a = _export(database, tmp_path, author_id, worker="worker-a2")

    assert second_a.already_exported is False
    assert second_a.source_fingerprint == first_a.source_fingerprint
    assert second_a.rendered_fingerprint == first_a.rendered_fingerprint
    with database.session() as session:
        jobs = list(session.scalars(select(Job)).all())
        records = list(session.scalars(select(ExportRecord)).all())
    assert len(jobs) == 3 and len({job.natural_key for job in jobs}) == 3
    second_a_job = next(job for job in jobs if job.id == second_a.job_id)
    assert second_a_job.payload["predecessor_job_id"] == snapshot_b.job_id
    assert len(records) == 2 and {record.status for record in records} == {"succeeded"}


def test_export_records_are_keyed_by_whole_author_snapshot_changes(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "archive")
    first = _export(database, tmp_path, author_id)
    with database.session() as session:
        changed = session.scalar(select(Content).where(Content.remote_id == "text-1"))
        assert changed is not None
        changed.title = "Only c1 changed"
    second = _export(database, tmp_path, author_id, worker="worker-second")
    with database.session() as session:
        changed = session.scalar(select(Content).where(Content.remote_id == "text-1"))
        assert changed is not None
        changed.tombstoned_at = NOW
    third = _export(database, tmp_path, author_id, worker="worker-third")
    with database.session() as session:
        author = session.get(Author, author_id)
        assert author is not None
        author.display_name = "Creator Renamed"
        author.handle = "@renamed"
    fourth = _export(database, tmp_path, author_id, worker="worker-fourth")

    assert (
        len({first.source_fingerprint, second.source_fingerprint, third.source_fingerprint, fourth.source_fingerprint})
        == 4
    )
    with database.session() as session:
        jobs = list(session.scalars(select(Job)).all())
        records = list(session.scalars(select(ExportRecord)).all())
    assert len(jobs) == 4 and {job.status for job in jobs} == {"succeeded"}
    assert len(records) == 6 and {record.status for record in records} == {"succeeded"}
    records_by_source = {
        source: [record for record in records if record.source_fingerprint == source]
        for source in {
            first.source_fingerprint,
            second.source_fingerprint,
            third.source_fingerprint,
            fourth.source_fingerprint,
        }
    }
    assert [len(records_by_source[outcome.source_fingerprint]) for outcome in (first, second, third, fourth)] == [
        2,
        2,
        1,
        1,
    ]


def test_concurrent_children_of_one_predecessor_leave_one_durable_head(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "unused", include_video=False)
    predecessor = _export(database, tmp_path, author_id)
    barrier = Barrier(2)

    class RenderBarrierExporter:
        def __init__(self, exporter: EmbyExporter) -> None:
            self._exporter = exporter

        @property
        def export_root(self) -> Path:
            return self._exporter.export_root

        @property
        def coordination_scope(self) -> str:
            return self._exporter.coordination_scope

        def render(self, *args: object, **kwargs: object) -> object:
            rendered = self._exporter.render(*args, **kwargs)  # type: ignore[arg-type]
            barrier.wait(timeout=10)
            return rendered

        def publish(self, *args: object, **kwargs: object) -> object:
            return self._exporter.publish(*args, **kwargs)  # type: ignore[arg-type,return-value]

        def discard(self, *args: object, **kwargs: object) -> None:
            self._exporter.discard(*args, **kwargs)  # type: ignore[arg-type]

        def validate_published(self, *args: object, **kwargs: object) -> int:
            return self._exporter.validate_published(*args, **kwargs)  # type: ignore[arg-type]

    service_a = EmbyExportService(
        database,
        RenderBarrierExporter(EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work-a")),  # type: ignore[arg-type]
        clock=lambda: NOW,
    )
    service_b = EmbyExportService(
        database,
        RenderBarrierExporter(EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work-b")),  # type: ignore[arg-type]
        clock=lambda: NOW,
    )
    request_a = EmbyExportRequest(author_id, "worker-a", lease_seconds=60)
    request_b = EmbyExportRequest(author_id, "worker-b", lease_seconds=60)
    with database.session() as session:
        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        content.title = "Concurrent A"
    prepared_a = service_a._prepare(request_a, scan_recovery=False)
    with database.session() as session:
        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        content.title = "Concurrent B"
    prepared_b = service_b._prepare(request_b, scan_recovery=False)
    assert hasattr(prepared_a, "predecessor") and hasattr(prepared_b, "predecessor")
    assert prepared_a.predecessor is not None and prepared_a.predecessor.job_id == predecessor.job_id  # type: ignore[union-attr]
    assert prepared_b.predecessor is not None and prepared_b.predecessor.job_id == predecessor.job_id  # type: ignore[union-attr]

    outcomes: list[EmbyExportOutcome] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(service_a._run_prepared, request_a, prepared_a),  # type: ignore[arg-type]
            pool.submit(service_b._run_prepared, request_b, prepared_b),  # type: ignore[arg-type]
        ]
        for future in futures:
            try:
                outcomes.append(future.result(timeout=20))
            except ExportError as error:
                errors.append(error.code)

    assert len(outcomes) == 1
    assert errors == ["stale_publish"]
    with database.session() as session:
        jobs = list(session.scalars(select(Job)).all())
    succeeded = [job for job in jobs if job.status == "succeeded"]
    retryable = [job for job in jobs if job.status == "failed_retryable"]
    assert len(succeeded) == 2 and len(retryable) == 1
    winner = next(job for job in succeeded if job.id != predecessor.job_id)
    assert winner.payload["predecessor_job_id"] == predecessor.job_id

    converged = _service(database, tmp_path).export_author(
        EmbyExportRequest(author_id, "worker-converge", lease_seconds=60)
    )
    with database.session() as session:
        final_jobs = list(session.scalars(select(Job).where(Job.status == "succeeded")).all())
    assert converged.source_fingerprint == next(
        job.payload["source_fingerprint"] for job in final_jobs if job.id == converged.job_id
    )
    assert len(final_jobs) in {2, 3}


def test_publication_scope_is_non_disclosing_and_isolates_library_roots(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "unused", include_video=False)
    first = _export(database, tmp_path / "target-a", author_id)
    second = _export(database, tmp_path / "target-b", author_id, worker="worker-b")

    assert first.source_fingerprint == second.source_fingerprint
    assert first.job_id != second.job_id
    with database.session() as session:
        jobs = list(session.scalars(select(Job)).all())
    scopes = {job.payload["publication_scope"] for job in jobs}
    assert len(jobs) == 2 and len(scopes) == 2
    assert all(isinstance(scope, str) and len(scope) == 64 for scope in scopes)
    assert str(tmp_path) not in repr([job.payload for job in jobs])
    assert {job.payload["predecessor_job_id"] for job in jobs} == {None}


def test_publication_chain_rejects_cycle_even_with_recomputed_natural_key(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "unused", include_video=False)
    first = _export(database, tmp_path, author_id)
    with database.session() as session:
        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        content.title = "Second"
    second = _export(database, tmp_path, author_id, worker="worker-b")
    with database.session() as session:
        first_job = session.get(Job, first.job_id)
        second_job = session.get(Job, second.job_id)
        assert first_job is not None and second_job is not None
        payload = dict(first_job.payload)
        payload["predecessor_job_id"] = second.job_id
        first_job.payload = payload
        first_job.natural_key = emby_export_natural_key(
            author_id,
            str(payload["publication_scope"]),
            str(payload["output_path"]),
            str(payload["source_fingerprint"]),
            second.job_id,
        )

    with pytest.raises(ExportError) as raised:
        _service(database, tmp_path).export_author(EmbyExportRequest(author_id, "worker-cycle", lease_seconds=60))
    assert raised.value.code == "export_state_inconsistent"


def test_publication_chain_rejects_disconnected_succeeded_component(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id, _ = _seed_author(database, tmp_path / "unused", include_video=False)
    first = _export(database, tmp_path, author_id)
    with database.session() as session:
        first_job = session.get(Job, first.job_id)
        assert first_job is not None
        scope = str(first_job.payload["publication_scope"])
        output_path = str(first_job.payload["output_path"])
        source = "f" * 64
        session.add(
            Job(
                job_type="export.emby",
                natural_key=emby_export_natural_key(author_id, scope, output_path, source, None),
                payload={
                    "schema_version": 1,
                    "author_id": author_id,
                    "exporter": "emby",
                    "exporter_version": "emby-jellyfin-v1",
                    "publication_scope": scope,
                    "output_path": output_path,
                    "source_fingerprint": source,
                    "predecessor_job_id": None,
                    "result": {
                        "schema_version": 1,
                        "tree_sha256": "e" * 64,
                        "manifest_sha256": "d" * 64,
                        "managed_file_count": 0,
                    },
                },
                status="succeeded",
                attempts=1,
                max_attempts=1,
                available_at=NOW,
                finished_at=NOW,
            )
        )

    with pytest.raises(ExportError) as raised:
        _service(database, tmp_path).export_author(
            EmbyExportRequest(author_id, "worker-disconnected", lease_seconds=60)
        )
    assert raised.value.code == "export_state_inconsistent"


def test_export_omits_raw_locator_and_signed_url_sentinel(database: Database, tmp_path: Path) -> None:
    sentinel = "SENTINEL-cookie-signature-0005"
    author_id, _ = _seed_author(database, tmp_path / "archive", secret=sentinel)

    outcome = _export(database, tmp_path, author_id)

    exported_bytes = b"\n".join(path.read_bytes() for path in (tmp_path / "library").rglob("*") if path.is_file())
    assert sentinel.encode() not in exported_bytes
    with database.session() as session:
        job = session.scalar(select(Job))
        records = list(session.scalars(select(ExportRecord)).all())
    assert job is not None and sentinel not in repr(job.payload)
    assert sentinel not in repr(
        [(record.output_path, record.error_message, record.rendered_fingerprint) for record in records]
    )
    assert outcome.already_exported is False

    with database.session() as session:
        content = session.scalar(select(Content).where(Content.remote_id == "text-1"))
        assert content is not None
        content.title = "A new source snapshot"

    def leak_from_runtime(_: str, __: str | None) -> None:
        raise RuntimeError(sentinel)

    with pytest.raises(ExportError) as raised:
        _service(database, tmp_path, fault=leak_from_runtime).export_author(
            EmbyExportRequest(author_id, "worker-secret", lease_seconds=60)
        )
    assert raised.value.code == "unexpected_export_failure"
    with database.session() as session:
        failed_job = session.scalar(select(Job).where(Job.status == "failed_retryable"))
        failed_records = list(
            session.scalars(select(ExportRecord).where(ExportRecord.status == "failed_retryable")).all()
        )
    assert failed_job is not None
    assert (failed_job.last_error_code, failed_job.last_error_message) == (
        "unexpected_export_failure",
        "Classified Emby export failure: unexpected_export_failure",
    )
    assert {record.error_message for record in failed_records} == {"unexpected_export_failure"}
    assert sentinel not in repr(
        [
            failed_job.last_error_code,
            failed_job.last_error_message,
            *[record.error_message for record in failed_records],
        ]
    )


def test_export_record_repository_lifecycle_is_strict_cas(database: Database, tmp_path: Path) -> None:
    author_id, _ = _seed_author(database, tmp_path / "unused", include_video=False)
    with database.session() as session:
        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        records = ExportRecordRepository(session)
        running = records.begin(
            content_id=content.id,
            exporter="test",
            exporter_version="v1",
            source_fingerprint="a" * 64,
            output_path="relative/creator",
        )
        with pytest.raises(ExportRecordConflictError):
            records.begin(
                content_id=content.id,
                exporter="test",
                exporter_version="v1",
                source_fingerprint="a" * 64,
                output_path="relative/creator",
            )
        failed = records.fail(
            running.id,
            expected_source_fingerprint="a" * 64,
            expected_output_path="relative/creator",
            retryable=True,
            error_code="stale_publish",
        )
        failed_status = failed.status
        retried = records.begin(
            content_id=content.id,
            exporter="test",
            exporter_version="v1",
            source_fingerprint="a" * 64,
            output_path="relative/creator",
        )
        completed = records.complete(
            retried.id,
            expected_source_fingerprint="a" * 64,
            expected_output_path="relative/creator",
            rendered_fingerprint="b" * 64,
        )
        assert (failed_status, completed.status, completed.rendered_fingerprint) == (
            "failed_retryable",
            "succeeded",
            "b" * 64,
        )
        with pytest.raises(ExportRecordConflictError):
            records.fail(
                completed.id,
                expected_source_fingerprint="a" * 64,
                expected_output_path="relative/creator",
                retryable=False,
                error_code="should_not_apply",
            )
