"""One fully offline synchronization-to-Emby pipeline qualification."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select, text

from media_sync.adapters.fake import FakePlatformAdapter
from media_sync.application.downloads import AssetDownloadRequest, AssetDownloadService
from media_sync.application.emby import EmbyExportRequest, EmbyExportService
from media_sync.application.sync import SyncRequest, SyncService
from media_sync.domain import (
    AccountRef,
    AssetKind,
    AssetSnapshot,
    AuthorSnapshot,
    ContentKind,
    ContentSnapshot,
    LoginMethod,
    Platform,
    RunStatus,
)
from media_sync.exporters.emby import EmbyExporter
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    SQLAlchemySyncRepository,
    SubscriptionRepository,
    upgrade_database,
)
from media_sync.infrastructure.db.models import Asset, Author, Content, ExportRecord, Job, Subscription, SyncRun
from media_sync.media import DirectLocator, SafeHttpClient, SecureMediaDownloader, ValidatedTarget, parse_locator

FIXED_AT = datetime(2026, 8, 30, 8, 9, 10, tzinfo=UTC)
ORIGIN_URL = "https://media.pipeline.test/assets/offline.png"
SECRET_SENTINEL = "SENTINEL-runtime-signed-query-0005"
SIGNED_URL = f"https://cdn.pipeline.test/final.png?signature={SECRET_SENTINEL}"
PNG = b"\x89PNG\r\n\x1a\n" + b"fully-offline-media-pipeline"
EXPECTED_AUTHOR_DIRECTORY = "bili-creator-offline-creator-0005-12221fa2fb873a33"


class _RecordingPublicResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        self.calls.append((hostname, port))
        return ("8.8.8.8",)


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file()
    }


def _assert_no_runtime_secret(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            payload = path.read_bytes()
            assert SECRET_SENTINEL.encode() not in payload
            assert SIGNED_URL.encode() not in payload
            assert b"?signature=" not in payload


@pytest.mark.asyncio
async def test_offline_sync_download_export_pipeline_is_secure_and_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "offline-pipeline.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    upgrade_database(database_url)
    database = Database(database_url)
    archive_root = tmp_path / "archive"
    library_root = tmp_path / "library"

    try:
        author_snapshot = AuthorSnapshot(
            platform=Platform.BILI,
            remote_id="offline-creator-0005",
            display_name="Offline Creator & XML",
            handle="offline-creator",
            profile_url="https://fixture.invalid/bili/offline-creator-0005",
        )
        content_snapshot = ContentSnapshot(
            platform=Platform.BILI,
            remote_id="offline-post-0005",
            author_remote_id=author_snapshot.remote_id,
            remote_type="post",
            kind=ContentKind.GALLERY,
            title="Offline post & <XML>",
            body="Offline body with 图文 and <escaped> text.",
            canonical_url="https://fixture.invalid/bili/posts/offline-post-0005",
            published_at=FIXED_AT,
            metrics={"likes": 5},
            raw={"fixture": "offline-pipeline"},
        )
        asset_snapshot = AssetSnapshot(
            platform=Platform.BILI,
            remote_id="offline-image-0005",
            content_remote_id=content_snapshot.remote_id,
            kind=AssetKind.IMAGE,
            source_url=ORIGIN_URL,
            position=0,
            mime_type="image/png",
            raw={"fixture": "offline-pipeline"},
        )
        adapter = FakePlatformAdapter(
            Platform.BILI,
            author=author_snapshot,
            contents=(content_snapshot,),
            assets={content_snapshot.remote_id: (asset_snapshot,)},
        )

        with database.session() as session:
            account = AccountRepository(session).create(
                platform=Platform.BILI.value,
                adapter="fake",
                display_name="offline-pipeline-account",
                login_method=LoginMethod.COOKIE.value,
                auth_status="authenticated",
            )
            seeded_author = AuthorRepository(session).upsert(
                AuthorUpsert(
                    platform=Platform.BILI.value,
                    remote_id=author_snapshot.remote_id,
                    display_name="Subscription placeholder",
                ),
                seen_at=FIXED_AT,
            )
            subscription = SubscriptionRepository(session).create(
                account_id=account.id,
                author_id=seeded_author.id,
            )
            author_id = seeded_author.id
            account_ref = AccountRef(
                account_id=UUID(account.id),
                platform=Platform.BILI,
                login_method=LoginMethod.COOKIE,
                adapter="fake",
            )
            subscription_id = UUID(subscription.id)

        sync_request = SyncRequest(
            subscription_id=subscription_id,
            account=account_ref,
            creator_reference=author_snapshot.remote_id,
            max_items=1,
            page_size=1,
            max_pages=1,
        )
        with database.session() as session:
            first_sync = await SyncService(adapter, SQLAlchemySyncRepository(session)).run(sync_request)
        assert first_sync.status is RunStatus.SUCCEEDED
        assert (first_sync.processed_count, first_sync.asset_count, first_sync.final_cursor) == (1, 1, None)

        with database.session() as session:
            discovered = session.scalar(select(Asset))
            assert discovered is not None
            asset_id = UUID(discovered.id)
            parsed_locator = parse_locator(discovered.locator)
            assert isinstance(parsed_locator, DirectLocator)
            assert parsed_locator.url == discovered.source_url == ORIGIN_URL
            assert urlsplit(parsed_locator.url).query == ""
            assert discovered.status == "discovered"
            assert discovered.generation == 1

        resolver = _RecordingPublicResolver()
        network_calls: list[str] = []
        pinned_targets: list[ValidatedTarget] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_url = str(request.url)
            network_calls.append(requested_url)
            if requested_url == ORIGIN_URL:
                assert request.headers["host"] == "media.pipeline.test"
                return httpx.Response(302, headers={"Location": SIGNED_URL})
            assert requested_url == SIGNED_URL
            assert request.headers["host"] == "cdn.pipeline.test"
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(PNG)),
                    "Content-Type": "image/png",
                    "ETag": '"offline-pipeline-v1"',
                },
                content=PNG,
            )

        def transport_factory(target: ValidatedTarget) -> httpx.BaseTransport:
            pinned_targets.append(target)
            return httpx.MockTransport(handler)

        downloader = SecureMediaDownloader(
            SafeHttpClient(resolver, transport_factory=transport_factory),
        )
        download_service = AssetDownloadService(database, downloader, clock=lambda: FIXED_AT)
        download_request = AssetDownloadRequest(
            asset_id=asset_id,
            worker_id="offline-download-worker",
            work_root=tmp_path / "download-work",
            archive_root=archive_root,
            lease_seconds=60,
        )
        first_download = download_service.run(download_request)
        expected_checksum = hashlib.sha256(PNG).hexdigest()
        expected_archive_path = archive_root / "sha256" / expected_checksum[:2] / f"{expected_checksum}.png"
        assert first_download.disposition == "downloaded"
        assert first_download.archive_path == expected_archive_path.absolute()
        assert first_download.archive_path.read_bytes() == PNG
        assert first_download.checksum_sha256 == expected_checksum
        assert first_download.mime_type == "image/png"
        assert network_calls == [ORIGIN_URL, SIGNED_URL]
        assert resolver.calls == [("media.pipeline.test", 443), ("cdn.pipeline.test", 443)]
        assert [target.address for target in pinned_targets] == ["8.8.8.8", "8.8.8.8"]

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=tmp_path / "export-work"),
            clock=lambda: FIXED_AT,
        )
        export_request = EmbyExportRequest(author_id, "offline-export-worker", lease_seconds=60)
        first_export = export_service.export_author(export_request)
        assert first_export.already_exported is False
        assert first_export.output_path == EXPECTED_AUTHOR_DIRECTORY
        assert first_export.rendered_fingerprint is not None

        author_directory = library_root / EXPECTED_AUTHOR_DIRECTORY
        manifest_path = author_directory / ".media-sync-managed-v1.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["author"] == {"platform": "bili", "remote_id": author_snapshot.remote_id}
        assert manifest["source_fingerprint"] == first_export.source_fingerprint
        assert manifest["tree_sha256"] == first_export.rendered_fingerprint
        assert len(manifest["files"]) == first_export.managed_file_count

        manifest_paths = [row["path"] for row in manifest["files"]]
        published_paths = sorted(
            path.relative_to(author_directory).as_posix()
            for path in author_directory.rglob("*")
            if path.is_file() and path != manifest_path
        )
        assert manifest_paths == published_paths
        for row in manifest["files"]:
            output = author_directory.joinpath(*row["path"].split("/"))
            payload = output.read_bytes()
            assert len(payload) == row["size_bytes"]
            assert hashlib.sha256(payload).hexdigest() == row["sha256"]
        canonical_rows = (
            json.dumps(manifest["files"], ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        assert hashlib.sha256(canonical_rows).hexdigest() == manifest["tree_sha256"]

        tvshow = ET.fromstring((author_directory / "tvshow.nfo").read_bytes())
        episode_path = next(author_directory.glob("Season 2026/*.nfo"))
        episode = ET.fromstring(episode_path.read_bytes())
        assert tvshow.tag == "tvshow"
        assert tvshow.findtext("title") == author_snapshot.display_name
        assert episode.tag == "episodedetails"
        assert episode.findtext("title") == content_snapshot.title
        assert episode.findtext("plot") == content_snapshot.body
        assert episode.findtext("uniqueid") == content_snapshot.remote_id
        unique_id = episode.find("uniqueid")
        assert unique_id is not None
        assert unique_id.attrib == {"type": "media-sync-bili-post", "default": "true"}

        content_source_path = next(author_directory.glob("Season 2026/*.assets/source.json"))
        content_source = json.loads(content_source_path.read_text(encoding="utf-8"))
        assert not {"canonical_url", "locator", "raw", "source_url"} & content_source.keys()
        assert expected_checksum in {row["sha256"] for row in manifest["files"]}
        first_archive_tree = _tree(archive_root)
        first_export_tree = _tree(author_directory)
        _assert_no_runtime_secret(archive_root)
        _assert_no_runtime_secret(library_root)

        with database.session() as session:
            second_sync = await SyncService(adapter, SQLAlchemySyncRepository(session)).run(sync_request)
        second_download = download_service.run(download_request)
        second_export = export_service.export_author(
            EmbyExportRequest(author_id, "offline-export-worker-replay", lease_seconds=60)
        )

        assert second_sync.status is RunStatus.SUCCEEDED
        assert (second_sync.processed_count, second_sync.asset_count, second_sync.final_cursor) == (1, 1, None)
        assert second_download.disposition == "already_verified"
        assert second_download.archive_path == first_download.archive_path
        assert second_download.checksum_sha256 == first_download.checksum_sha256
        assert second_export.already_exported is True
        assert second_export.job_id == first_export.job_id
        assert second_export.source_fingerprint == first_export.source_fingerprint
        assert second_export.rendered_fingerprint == first_export.rendered_fingerprint
        assert network_calls == [ORIGIN_URL, SIGNED_URL]
        assert _tree(archive_root) == first_archive_tree
        assert _tree(author_directory) == first_export_tree

        with database.session() as session:
            assets = list(session.scalars(select(Asset)).all())
            jobs = list(session.scalars(select(Job).order_by(Job.job_type)).all())
            records = list(session.scalars(select(ExportRecord)).all())
            runs = list(session.scalars(select(SyncRun).order_by(SyncRun.created_at)).all())
            persisted_subscription = session.get(Subscription, str(subscription_id))
            persisted_author = session.get(Author, author_id)
            persisted_content = session.scalar(select(Content))
            revision = session.scalar(text("SELECT version_num FROM alembic_version"))

            assert session.scalar(select(func.count()).select_from(Author)) == 1
            assert session.scalar(select(func.count()).select_from(Content)) == 1
            assert session.scalar(select(func.count()).select_from(Asset)) == 1
            assert session.scalar(select(func.count()).select_from(SyncRun)) == 2
        assert revision == "0008_playback_evidence"
        assert persisted_author is not None and persisted_author.display_name == author_snapshot.display_name
        assert persisted_content is not None and persisted_content.remote_id == content_snapshot.remote_id
        assert persisted_subscription is not None and persisted_subscription.checkpoint_revision == 2
        assert [run.status for run in runs] == ["succeeded", "succeeded"]
        assert len(assets) == 1
        assert assets[0].status == "verified"
        assert assets[0].generation == 1
        assert assets[0].checksum_sha256 == expected_checksum
        assert assets[0].local_path == str(expected_archive_path.absolute())
        assert isinstance(parse_locator(assets[0].locator), DirectLocator)
        assert len(jobs) == 2
        assert {job.job_type for job in jobs} == {"asset_download", "export.emby"}
        assert {job.status for job in jobs} == {"succeeded"}
        assert {job.attempts for job in jobs} == {1}
        assert len(records) == 1
        assert records[0].status == "succeeded"
        assert records[0].rendered_fingerprint == first_export.rendered_fingerprint
        assert SECRET_SENTINEL not in repr(
            [
                assets[0].source_url,
                assets[0].locator,
                *[job.payload for job in jobs],
                *[run.manifest for run in runs],
            ]
        )
        _assert_no_runtime_secret(archive_root)
        _assert_no_runtime_secret(library_root)
    finally:
        database.dispose()

    sqlite_artifacts = [path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file()]
    assert sqlite_artifacts
    for sqlite_artifact in sqlite_artifacts:
        payload = sqlite_artifact.read_bytes()
        assert SECRET_SENTINEL.encode() not in payload
        assert SIGNED_URL.encode() not in payload
        assert b"?signature=" not in payload
