"""Restart-safe offline qualification for the scheduled media pipeline."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select, text

from media_sync.adapters.fake import FakePlatformAdapter
from media_sync.application.downloads import AssetDownloadRequest, AssetDownloadService
from media_sync.application.emby import EmbyExportRequest, EmbyExportService
from media_sync.domain import (
    AssetKind,
    AssetSnapshot,
    AuthorSnapshot,
    ContentKind,
    ContentSnapshot,
    LoginMethod,
    Platform,
)
from media_sync.exporters.emby import EmbyExporter
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    SubscriptionRepository,
    upgrade_database,
)
from media_sync.infrastructure.db.models import (
    Asset,
    ExportRecord,
    Job,
    SchedulerLane,
    Subscription,
    SyncRun,
)
from media_sync.media import SafeHttpClient, SecureMediaDownloader, ValidatedTarget
from media_sync.scheduler import (
    DurableSchedulerService,
    FakeSubscriptionHandler,
    SubscriptionHandlerRegistry,
    SubscriptionWorker,
)

RUN_AT = datetime(2026, 8, 30, 11, 30, tzinfo=UTC)
RESTART_AT = RUN_AT + timedelta(seconds=1)
INTERVAL_SECONDS = 3_600
ORIGIN_URL = "https://media.scheduled-pipeline.test/assets/offline.png"
SECRET_SENTINEL = "SENTINEL-runtime-signed-query-0005"
SIGNED_URL = f"https://cdn.scheduled-pipeline.test/final.png?signature={SECRET_SENTINEL}"
PNG = b"\x89PNG\r\n\x1a\n" + b"scheduled-offline-media-pipeline"

AUTHOR_SNAPSHOT = AuthorSnapshot(
    platform=Platform.BILI,
    remote_id="scheduled-offline-creator-0006",
    display_name="Scheduled Offline Creator & XML",
    handle="scheduled-offline-creator",
    profile_url="https://fixture.invalid/bili/scheduled-offline-creator-0006",
)
CONTENT_SNAPSHOT = ContentSnapshot(
    platform=Platform.BILI,
    remote_id="scheduled-offline-post-0006",
    author_remote_id=AUTHOR_SNAPSHOT.remote_id,
    remote_type="post",
    kind=ContentKind.GALLERY,
    title="Scheduled offline post & <XML>",
    body="Scheduled offline body with 图文 and <escaped> text.",
    canonical_url="https://fixture.invalid/bili/posts/scheduled-offline-post-0006",
    published_at=RUN_AT,
    metrics={"likes": 6},
    raw={"fixture": "scheduled-offline-pipeline"},
)
ASSET_SNAPSHOT = AssetSnapshot(
    platform=Platform.BILI,
    remote_id="scheduled-offline-image-0006",
    content_remote_id=CONTENT_SNAPSHOT.remote_id,
    kind=AssetKind.IMAGE,
    source_url=ORIGIN_URL,
    position=0,
    mime_type="image/png",
    raw={"fixture": "scheduled-offline-pipeline"},
)


@dataclass(slots=True)
class _NetworkTrace:
    requests: list[str]
    resolutions: list[tuple[str, int]]
    targets: list[ValidatedTarget]

    @classmethod
    def empty(cls) -> _NetworkTrace:
        return cls([], [], [])


class _RecordingPublicResolver:
    def __init__(self, trace: _NetworkTrace) -> None:
        self.trace = trace

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        self.trace.resolutions.append((hostname, port))
        return ("8.8.8.8",)


@dataclass(frozen=True, slots=True)
class _DurableSnapshot:
    jobs: tuple[tuple[object, ...], ...]
    lanes: tuple[tuple[object, ...], ...]
    runs: tuple[tuple[object, ...], ...]
    records: tuple[tuple[object, ...], ...]
    asset: tuple[object, ...]
    subscription: tuple[object, ...]


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file()
    }


def _assert_no_runtime_secret(root: Path) -> None:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        assert SECRET_SENTINEL.encode() not in payload
        assert SIGNED_URL.encode() not in payload
        assert b"?signature=" not in payload


def _adapter_factory(platform: Platform) -> FakePlatformAdapter:
    assert platform is Platform.BILI
    return FakePlatformAdapter(
        platform,
        author=AUTHOR_SNAPSHOT,
        contents=(CONTENT_SNAPSHOT,),
        assets={CONTENT_SNAPSHOT.remote_id: (ASSET_SNAPSHOT,)},
    )


def _scheduler_stack(
    database: Database,
    *,
    now: datetime,
) -> tuple[DurableSchedulerService, SubscriptionWorker]:
    def clock() -> datetime:
        return now

    handler = FakeSubscriptionHandler(database, adapter_factory=_adapter_factory)
    registry = SubscriptionHandlerRegistry({"fake": handler})
    return (
        DurableSchedulerService(database, clock=clock),
        SubscriptionWorker(database, registry, clock=clock, random_fraction=lambda: 0),
    )


def _downloader(trace: _NetworkTrace) -> SecureMediaDownloader:
    def handler(request: httpx.Request) -> httpx.Response:
        requested_url = str(request.url)
        trace.requests.append(requested_url)
        if requested_url == ORIGIN_URL:
            assert request.headers["host"] == "media.scheduled-pipeline.test"
            return httpx.Response(302, headers={"Location": SIGNED_URL})
        assert requested_url == SIGNED_URL
        assert request.headers["host"] == "cdn.scheduled-pipeline.test"
        return httpx.Response(
            200,
            headers={
                "Content-Length": str(len(PNG)),
                "Content-Type": "image/png",
                "ETag": '"scheduled-offline-v1"',
            },
            content=PNG,
        )

    def transport_factory(target: ValidatedTarget) -> httpx.BaseTransport:
        trace.targets.append(target)
        return httpx.MockTransport(handler)

    return SecureMediaDownloader(
        SafeHttpClient(
            _RecordingPublicResolver(trace),
            transport_factory=transport_factory,
        )
    )


def _seed_due_subscription(database: Database) -> tuple[str, str]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=Platform.BILI.value,
            adapter="fake",
            display_name="scheduled-offline-pipeline-account",
            login_method=LoginMethod.COOKIE.value,
            auth_status="authenticated",
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=Platform.BILI.value,
                remote_id=AUTHOR_SNAPSHOT.remote_id,
                display_name="Scheduled subscription placeholder",
            ),
            seen_at=RUN_AT,
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            interval_seconds=INTERVAL_SECONDS,
            max_items=1,
            next_run_at=None,
        )
        return subscription.id, author.id


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _snapshot(database: Database, subscription_id: str) -> _DurableSnapshot:
    with database.session() as session:
        jobs = list(session.scalars(select(Job).order_by(Job.job_type, Job.id)).all())
        lanes = list(
            session.scalars(
                select(SchedulerLane).order_by(
                    SchedulerLane.scope_type,
                    SchedulerLane.platform,
                    SchedulerLane.account_id,
                    SchedulerLane.id,
                )
            ).all()
        )
        runs = list(session.scalars(select(SyncRun).order_by(SyncRun.id)).all())
        records = list(session.scalars(select(ExportRecord).order_by(ExportRecord.id)).all())
        assets = list(session.scalars(select(Asset).order_by(Asset.id)).all())
        subscription = session.get(Subscription, subscription_id)
        assert len(assets) == 1
        assert subscription is not None
        asset = assets[0]
        return _DurableSnapshot(
            jobs=tuple(
                (
                    job.job_type,
                    job.id,
                    job.natural_key,
                    job.status,
                    job.attempts,
                    job.max_attempts,
                    job.run_id,
                    job.subscription_id,
                    job.account_id,
                    job.platform,
                    job.scheduled_for,
                    job.available_at,
                    job.started_at,
                    job.finished_at,
                    job.last_error_code,
                    job.last_error_message,
                    _canonical_json(job.payload),
                )
                for job in jobs
            ),
            lanes=tuple(
                (
                    lane.id,
                    lane.scope_type,
                    lane.platform,
                    lane.account_id,
                    lane.max_concurrency,
                    lane.min_start_interval_seconds,
                    lane.failure_threshold,
                    lane.cooldown_seconds,
                    lane.next_start_at,
                    lane.consecutive_failures,
                    lane.circuit_state,
                    lane.circuit_open_until,
                    lane.half_open_job_id,
                    lane.revision,
                )
                for lane in lanes
            ),
            runs=tuple(
                (
                    run.id,
                    run.subscription_id,
                    run.status,
                    run.attempt,
                    run.checkpoint_revision_before,
                    run.checkpoint_revision_after,
                    _canonical_json(run.manifest),
                )
                for run in runs
            ),
            records=tuple(
                (
                    record.id,
                    record.content_id,
                    record.exporter,
                    record.exporter_version,
                    record.source_fingerprint,
                    record.output_path,
                    record.status,
                    record.rendered_fingerprint,
                )
                for record in records
            ),
            asset=(
                asset.id,
                asset.generation,
                asset.status,
                asset.download_job_id,
                asset.local_path,
                asset.checksum_sha256,
                asset.size_bytes,
                asset.mime_type,
                asset.semantic_fingerprint,
                asset.locator_fingerprint,
            ),
            subscription=(
                subscription.id,
                subscription.enabled,
                subscription.interval_seconds,
                subscription.schedule_revision,
                subscription.checkpoint_revision,
                subscription.next_run_at,
                subscription.last_run_at,
                subscription.last_success_at,
                subscription.consecutive_failures,
            ),
        )


def _assert_database_secret_safe(database: Database, *, local_roots: Sequence[Path]) -> None:
    with database.session() as session:
        jobs = list(session.scalars(select(Job)).all())
        lanes = list(session.scalars(select(SchedulerLane)).all())
        runs = list(session.scalars(select(SyncRun)).all())
        assets = list(session.scalars(select(Asset)).all())

    job_state = [
        {
            "payload": job.payload,
            "last_error_code": job.last_error_code,
            "last_error_message": job.last_error_message,
        }
        for job in jobs
    ]
    lane_state = [
        (
            lane.scope_type,
            lane.platform,
            lane.account_id,
            lane.circuit_state,
            lane.half_open_job_id,
        )
        for lane in lanes
    ]
    durable_state = repr(
        (
            job_state,
            lane_state,
            [run.manifest for run in runs],
            [(asset.source_url, asset.locator) for asset in assets],
        )
    )
    assert SECRET_SENTINEL not in durable_state
    assert SIGNED_URL not in durable_state
    assert "?signature=" not in durable_state
    for root in local_roots:
        assert str(root.absolute()) not in repr(job_state)

    sync_jobs = [job for job in jobs if job.job_type == "sync.subscription"]
    assert len(sync_jobs) == 1
    assert set(sync_jobs[0].payload) == {
        "schema_version",
        "subscription_id",
        "schedule_revision",
        "retry_policy",
    }
    assert not {"creator_reference", "cursor", "credential_ref", "work_root", "archive_root"} & set(
        sync_jobs[0].payload
    )


@pytest.mark.asyncio
async def test_scheduled_offline_pipeline_survives_restart_without_duplicate_identities(tmp_path: Path) -> None:
    database_path = tmp_path / "scheduled-offline-pipeline.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    archive_root = tmp_path / "archive"
    library_root = tmp_path / "library"
    download_work_root = tmp_path / "download-work"
    export_work_root = tmp_path / "export-work"
    local_roots = (archive_root, library_root, download_work_root, export_work_root)
    expected_checksum = hashlib.sha256(PNG).hexdigest()

    upgrade_database(database_url)
    database = Database(database_url)
    try:
        subscription_id, author_id = _seed_due_subscription(database)
        scheduler, worker = _scheduler_stack(database, now=RUN_AT)

        first_tick = scheduler.tick(limit=10)
        first_worker = await worker.run_once(worker_id="scheduled-sync-worker", global_capacity=2)
        first_idle = await worker.run_once(worker_id="scheduled-sync-worker", global_capacity=2)

        assert first_tick.materialized_count == 1
        assert first_tick.cycles[0].subscription_id == subscription_id
        assert first_tick.cycles[0].schedule_revision == 0
        assert first_worker.status == "succeeded"
        assert first_worker.job_id == first_tick.cycles[0].job_id
        assert first_worker.run_id is not None
        assert first_idle.status == "idle"

        with database.session() as session:
            asset = session.scalar(select(Asset))
            subscription = session.get(Subscription, subscription_id)
            jobs_before_downstream = list(session.scalars(select(Job)).all())
            assert asset is not None and subscription is not None
            assert asset.status == "discovered"
            assert asset.download_job_id is None
            assert [job.job_type for job in jobs_before_downstream] == ["sync.subscription"]
            assert session.scalar(select(func.count()).select_from(ExportRecord)) == 0
            assert session.scalar(select(func.count()).select_from(SyncRun)) == 1
            assert subscription.schedule_revision == 1
            assert subscription.checkpoint_revision == 1
            assert subscription.next_run_at == RUN_AT + timedelta(seconds=INTERVAL_SECONDS)
            asset_id = UUID(asset.id)
        assert not archive_root.exists()
        assert not library_root.exists()

        first_trace = _NetworkTrace.empty()
        first_download = AssetDownloadService(
            database,
            _downloader(first_trace),
            clock=lambda: RUN_AT,
        ).run(
            AssetDownloadRequest(
                asset_id=asset_id,
                worker_id="scheduled-download-worker",
                work_root=download_work_root,
                archive_root=archive_root,
                lease_seconds=60,
            )
        )
        first_export = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: RUN_AT,
        ).export_author(EmbyExportRequest(author_id, "scheduled-export-worker", lease_seconds=60))

        assert first_download.disposition == "downloaded"
        assert first_download.job_id is not None
        assert first_download.checksum_sha256 == expected_checksum
        assert first_download.archive_path.read_bytes() == PNG
        assert first_export.already_exported is False
        assert first_export.rendered_fingerprint is not None
        assert first_trace.requests == [ORIGIN_URL, SIGNED_URL]
        assert first_trace.resolutions == [
            ("media.scheduled-pipeline.test", 443),
            ("cdn.scheduled-pipeline.test", 443),
        ]
        assert [target.address for target in first_trace.targets] == ["8.8.8.8", "8.8.8.8"]

        author_directory = library_root / first_export.output_path
        first_archive_tree = _tree(archive_root)
        first_export_tree = _tree(author_directory)
        assert first_archive_tree
        assert first_export_tree
        first_snapshot = _snapshot(database, subscription_id)
        assert {row[0] for row in first_snapshot.jobs} == {
            "sync.subscription",
            "asset_download",
            "export.emby",
        }
        assert all(row[3] == "succeeded" and row[4] == 1 for row in first_snapshot.jobs)
        assert len(first_snapshot.lanes) == 2
        assert len(first_snapshot.runs) == 1
        assert len(first_snapshot.records) == 1
        assert first_snapshot.asset[3] == str(first_download.job_id)
        _assert_database_secret_safe(database, local_roots=local_roots)
        for root in local_roots:
            _assert_no_runtime_secret(root)
    finally:
        database.dispose()

    restarted = Database(database_url)
    try:
        restarted_scheduler, restarted_worker = _scheduler_stack(restarted, now=RESTART_AT)
        second_tick = restarted_scheduler.tick(limit=10)
        second_worker = await restarted_worker.run_once(
            worker_id="scheduled-sync-worker-restarted",
            global_capacity=2,
        )

        assert second_tick.materialized_count == 0
        assert second_worker.status == "idle"

        second_trace = _NetworkTrace.empty()
        second_download = AssetDownloadService(
            restarted,
            _downloader(second_trace),
            clock=lambda: RESTART_AT,
        ).run(
            AssetDownloadRequest(
                asset_id=asset_id,
                worker_id="scheduled-download-worker-restarted",
                work_root=download_work_root,
                archive_root=archive_root,
                lease_seconds=60,
            )
        )
        second_export = EmbyExportService(
            restarted,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: RESTART_AT,
        ).export_author(
            EmbyExportRequest(
                author_id,
                "scheduled-export-worker-restarted",
                lease_seconds=60,
            )
        )

        assert second_download.disposition == "already_verified"
        assert second_download.job_id == first_download.job_id
        assert second_download.archive_path == first_download.archive_path
        assert second_download.checksum_sha256 == first_download.checksum_sha256
        assert second_export.already_exported is True
        assert second_export.job_id == first_export.job_id
        assert second_export.source_fingerprint == first_export.source_fingerprint
        assert second_export.rendered_fingerprint == first_export.rendered_fingerprint
        assert second_trace.requests == []
        assert second_trace.resolutions == []
        assert second_trace.targets == []
        assert _tree(archive_root) == first_archive_tree
        assert _tree(author_directory) == first_export_tree

        second_snapshot = _snapshot(restarted, subscription_id)
        assert second_snapshot == first_snapshot
        assert {row[1] for row in second_snapshot.jobs} == {row[1] for row in first_snapshot.jobs}
        assert {row[0] for row in second_snapshot.jobs} == {
            "sync.subscription",
            "asset_download",
            "export.emby",
        }
        assert len(second_snapshot.lanes) == 2
        assert len(second_snapshot.runs) == 1
        assert len(second_snapshot.records) == 1
        assert second_snapshot.subscription[3:6] == (
            1,
            1,
            RUN_AT + timedelta(seconds=INTERVAL_SECONDS),
        )
        _assert_database_secret_safe(restarted, local_roots=local_roots)
        with restarted.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0005_asset_refresh_sources"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        restarted.dispose()

    sqlite_artifacts = [path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file()]
    assert sqlite_artifacts
    for sqlite_artifact in sqlite_artifacts:
        payload = sqlite_artifact.read_bytes()
        assert SECRET_SENTINEL.encode() not in payload
        assert SIGNED_URL.encode() not in payload
        assert b"?signature=" not in payload
    _assert_no_runtime_secret(tmp_path)
