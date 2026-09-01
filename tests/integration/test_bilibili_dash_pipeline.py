"""Offline Bilibili DASH components-to-production-mux-to-Emby qualification."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from media_sync.application import mediacrawler_download as mediacrawler_runtime
from media_sync.application.downloads import AssetDownloadRequest, AssetDownloadService
from media_sync.application.emby import EmbyExportRequest, EmbyExportService
from media_sync.application.mediacrawler_download import LazyMediaCrawlerLocatorRefresher
from media_sync.domain import AssetKind, AuthStatus, LoginMethod, Platform, RunStatus
from media_sync.exporters.emby import EmbyExporter
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    IngestionMode,
    MediaCrawlerIngestionService,
    SubscriptionRepository,
    SyncRunRepository,
    upgrade_database,
)
from media_sync.infrastructure.db.models import Asset, AssetRefreshSource, Content, ExportRecord, Job, Subscription
from media_sync.integrations.mediacrawler import MediaCrawlerDetailRequest, MediaCrawlerDetailResult
from media_sync.integrations.mediacrawler.bilibili_media import BILIBILI_DASH_PAGE_FIELD, BILIBILI_PAGES_FIELD
from media_sync.integrations.mediacrawler.normalizers import NormalizationContext, normalize_jsonl_bytes
from media_sync.media import (
    AdapterRefreshLocator,
    FFmpegStreamCopyMuxer,
    FFprobeMediaProbe,
    MediaRequestProfile,
    ResolvedDashLocator,
    ResolvedMediaTarget,
    SafeHttpClient,
    SecureMediaDownloader,
    ValidatedTarget,
    parse_locator,
)
from media_sync.security import SecretResolver

FIXED_AT = datetime(2026, 9, 2, 8, 9, 10, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
AUTHOR_REMOTE_ID = "424242"
CONTENT_ID = "987654321"
VIDEO_REMOTE_ID = f"{CONTENT_ID}:video:0"
CID = 24680
SIGNED_SENTINEL = "EXECUTION-0024-DASH-SIGNED-URL-MUST-STAY-EPHEMERAL"
VIDEO_URL = f"https://video.dash-integration.test/video.m4s?deadline=4102444800&sig={SIGNED_SENTINEL}-video"
AUDIO_URL = f"https://audio.dash-integration.test/audio.m4s?deadline=4102444800&sig={SIGNED_SENTINEL}-audio"
VIDEO_BACKUP_URL = (
    f"https://video-backup.dash-integration.test/video.m4s?deadline=4102444800&sig={SIGNED_SENTINEL}-video-backup"
)
AUDIO_BACKUP_URL = (
    f"https://audio-backup.dash-integration.test/audio.m4s?deadline=4102444800&sig={SIGNED_SENTINEL}-audio-backup"
)


def _jsonl(record: Mapping[str, object]) -> bytes:
    return (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


FORWARD_JSONL = _jsonl(
    {
        "desc": "Execution 0024 offline DASH qualification.",
        "title": "Offline DASH video",
        "video_id": CONTENT_ID,
        "video_type": "video",
        "video_url": f"https://www.bilibili.com/video/av{CONTENT_ID}",
    }
)


def _detail_jsonl() -> bytes:
    return _jsonl(
        {
            BILIBILI_DASH_PAGE_FIELD: {
                "cid": CID,
                "video": {
                    "url": VIDEO_URL,
                    "backup_urls": [VIDEO_BACKUP_URL],
                    "quality": 127,
                    "codec": "avc",
                },
                "audio": {
                    "url": AUDIO_URL,
                    "backup_urls": [AUDIO_BACKUP_URL],
                    "quality": 30251,
                },
            },
            BILIBILI_PAGES_FIELD: [{"page": 1, "cid": CID}],
            "desc": "Execution 0024 offline DASH qualification.",
            "title": "Offline DASH video",
            "video_id": CONTENT_ID,
            "video_type": "video",
            "video_url": f"https://www.bilibili.com/video/av{CONTENT_ID}",
        }
    )


class _DetailRunner:
    calls: ClassVar[list[MediaCrawlerDetailRequest]] = []

    def __init__(self, **_kwargs: object) -> None:
        pass

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        type(self).calls.append(request)
        assert request.platform is Platform.BILI
        assert request.content_remote_id == CONTENT_ID
        assert request.bili_progressive_detail is True
        assert request.bili_video_cid is None
        return MediaCrawlerDetailResult(_detail_jsonl(), UPSTREAM_SHA)


class _RecordingRefresher:
    def __init__(self, delegate: LazyMediaCrawlerLocatorRefresher) -> None:
        self.delegate = delegate
        self.results: list[ResolvedMediaTarget] = []

    def resolve(self, locator: AdapterRefreshLocator) -> ResolvedMediaTarget:
        result = self.delegate.resolve(locator)
        self.results.append(result)
        return result


class _PublicResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        self.calls.append((hostname, port))
        return ("8.8.8.8",)


def _policy() -> dict[str, object]:
    return {
        "mediacrawler": {
            "schema_version": 1,
            "allow_full_history": False,
            "request_delay_seconds": 1.0,
            "headless": True,
        }
    }


def _seed(database: Database) -> tuple[str, str]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=Platform.BILI.value,
            adapter="mediacrawler",
            display_name="execution-0024-offline-account",
            login_method=LoginMethod.QR.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=Platform.BILI.value,
                remote_id=AUTHOR_REMOTE_ID,
                display_name="Bilibili DASH Offline Creator",
            ),
            seen_at=FIXED_AT,
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            policy=_policy(),
        )
        return author.id, subscription.id


def _start_ingesting_run(database: Database, subscription_id: str) -> str:
    with database.session() as session:
        runs = SyncRunRepository(session)
        run = runs.create(subscription_id=subscription_id)
        runs.set_status(run.id, RunStatus.CLAIMED.value, expected_status=RunStatus.QUEUED.value)
        runs.set_status(run.id, RunStatus.RUNNING.value, expected_status=RunStatus.CLAIMED.value)
        runs.set_status(run.id, RunStatus.INGESTING.value, expected_status=RunStatus.RUNNING.value)
        return run.id


def _generate_components(root: Path, ffmpeg: str) -> tuple[bytes, bytes]:
    root.mkdir()
    video_path = root / "video.mp4"
    audio_path = root / "audio.m4a"
    commands = (
        (
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64:r=5:d=0.4",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-y",
            str(video_path),
        ),
        (
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=0.4",
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-movflags",
            "+faststart",
            "-y",
            str(audio_path),
        ),
    )
    try:
        for command in commands:
            subprocess.run(command, check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"local ffmpeg fixture generation is unavailable: {type(exc).__name__}")
    return video_path.read_bytes(), audio_path.read_bytes()


def _tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file()
    }


def _assert_ephemeral_absent(*roots: Path) -> None:
    forbidden = (
        SIGNED_SENTINEL.encode(),
        VIDEO_URL.encode(),
        AUDIO_URL.encode(),
        VIDEO_BACKUP_URL.encode(),
        AUDIO_BACKUP_URL.encode(),
        BILIBILI_DASH_PAGE_FIELD.encode(),
        BILIBILI_PAGES_FIELD.encode(),
    )
    for root in roots:
        retained = {root.name: root.read_bytes()} if root.is_file() else _tree(root)
        for relative_path, payload in retained.items():
            assert all(token not in payload for token in forbidden), relative_path


def _stream_types(path: Path, ffprobe: str) -> set[str]:
    completed = subprocess.run(
        (
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(path),
        ),
        check=True,
        capture_output=True,
        timeout=30,
    )
    payload = json.loads(completed.stdout)
    return {stream["codec_type"] for stream in payload["streams"]}


def test_bilibili_dash_backup_components_reach_emby_through_production_ffmpeg_and_ffprobe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg is None or ffprobe is None:
        pytest.skip("ffmpeg and ffprobe are required for production-process qualification")
    video_bytes, audio_bytes = _generate_components(tmp_path / "fixtures", ffmpeg)
    database_path = tmp_path / "bilibili-dash.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    archive_root = tmp_path / "archive"
    library_root = tmp_path / "library"
    runtime_root = tmp_path / "mediacrawler-runtime"
    download_work_root = tmp_path / "download-work"
    export_work_root = tmp_path / "export-work"
    runtime_root.mkdir()
    upgrade_database(database_url)
    database = Database(database_url)
    _DetailRunner.calls = []
    monkeypatch.setattr(mediacrawler_runtime, "MediaCrawlerDetailProcessRunner", _DetailRunner)

    try:
        author_id, subscription_id = _seed(database)
        normalized = normalize_jsonl_bytes(
            FORWARD_JSONL,
            NormalizationContext(
                platform=Platform.BILI,
                creator_remote_id=AUTHOR_REMOTE_ID,
                creator_display_name="Bilibili DASH Offline Creator",
                upstream_sha=UPSTREAM_SHA,
                ingested_at=FIXED_AT,
            ),
        )
        assert not normalized.quarantined and not normalized.truncated_tail
        assert [(asset.remote_id, asset.kind, asset.source_url) for asset in normalized.records[0].assets] == [
            (VIDEO_REMOTE_ID, AssetKind.VIDEO, None)
        ]
        run_id = _start_ingesting_run(database, subscription_id)
        ingestion = MediaCrawlerIngestionService(database).ingest(
            normalized.records,
            subscription_id=subscription_id,
            run_id=run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )
        assert (ingestion.accepted_count, ingestion.discovered_count, ingestion.asset_count) == (1, 1, 1)

        with database.session() as session:
            asset = session.scalar(select(Asset))
            source = session.scalar(select(AssetRefreshSource))
            assert asset is not None and source is not None
            asset_id = UUID(asset.id)
            assert isinstance(parse_locator(asset.locator), AdapterRefreshLocator)
            assert (asset.remote_id, asset.kind, asset.position, asset.source_url) == (
                VIDEO_REMOTE_ID,
                AssetKind.VIDEO.value,
                0,
                None,
            )

        delegate = LazyMediaCrawlerLocatorRefresher(
            database,
            asset_id=asset_id,
            subscription_id=UUID(subscription_id),
            lock_path=tmp_path / "upstreams.lock.json",
            integration_root=runtime_root,
            python_executable=tmp_path / "python",
            secret_resolver=SecretResolver({}),
            license_acknowledged=True,
        )
        refresher = _RecordingRefresher(delegate)
        resolver = _PublicResolver()
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            url = str(request.url)
            assert request.headers["referer"] == "https://www.bilibili.com/"
            assert request.headers["origin"] == "https://www.bilibili.com"
            assert request.headers["accept-encoding"] == "identity"
            assert "cookie" not in request.headers and "authorization" not in request.headers
            if url == VIDEO_URL:
                return httpx.Response(503)
            if url == AUDIO_URL:
                return httpx.Response(403)
            if url == VIDEO_BACKUP_URL:
                payload, media_type, etag = video_bytes, "video/mp4", '"execution-0024-video"'
            elif url == AUDIO_BACKUP_URL:
                payload, media_type, etag = audio_bytes, "audio/mp4", '"execution-0024-audio"'
            else:
                raise AssertionError("unexpected DASH component URL")
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(payload)), "Content-Type": media_type, "ETag": etag},
                content=payload,
            )

        def transport_factory(_target: ValidatedTarget) -> httpx.BaseTransport:
            return httpx.MockTransport(handler)

        downloader = SecureMediaDownloader(
            SafeHttpClient(resolver, transport_factory=transport_factory),
            refresher=refresher,
            probe=FFprobeMediaProbe(ffprobe),
            muxer=FFmpegStreamCopyMuxer(ffmpeg),
        )
        service = AssetDownloadService(database, downloader, clock=lambda: FIXED_AT)
        download_request = AssetDownloadRequest(
            asset_id=asset_id,
            worker_id="execution-0024-download",
            work_root=download_work_root,
            archive_root=archive_root,
            lease_seconds=60,
        )

        downloaded = service.run(download_request)

        assert downloaded.disposition == "downloaded"
        assert downloaded.archive_path is not None and downloaded.archive_path.is_file()
        assert downloaded.mime_type == "video/mp4"
        assert downloaded.checksum_sha256 == hashlib.sha256(downloaded.archive_path.read_bytes()).hexdigest()
        assert _stream_types(downloaded.archive_path, ffprobe) == {"video", "audio"}
        assert [str(request.url) for request in requests] == [
            VIDEO_URL,
            VIDEO_BACKUP_URL,
            AUDIO_URL,
            AUDIO_BACKUP_URL,
        ]
        assert resolver.calls == [
            ("video.dash-integration.test", 443),
            ("video-backup.dash-integration.test", 443),
            ("audio.dash-integration.test", 443),
            ("audio-backup.dash-integration.test", 443),
        ]
        assert len(_DetailRunner.calls) == 1
        assert len(refresher.results) == 1 and isinstance(refresher.results[0], ResolvedDashLocator)
        target = refresher.results[0]
        assert isinstance(target, ResolvedDashLocator)
        assert target.selection_key == (127, "avc", 30251)
        assert target.video.request_profile is MediaRequestProfile.BILIBILI_MEDIA
        assert target.audio is not None and target.audio.request_profile is MediaRequestProfile.BILIBILI_MEDIA
        assert target.video.backup_urls == (VIDEO_BACKUP_URL,)
        assert target.audio.backup_urls == (AUDIO_BACKUP_URL,)
        assert SIGNED_SENTINEL not in repr(target)
        assert not tuple((download_work_root / "parts").glob(f"{asset_id}.1*"))

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        exported = export_service.export_author(EmbyExportRequest(author_id, "execution-0024-export", lease_seconds=60))
        assert exported.already_exported is False
        author_directory = library_root / exported.output_path
        emby_video = next(author_directory.glob("Season 2026/*.mp4"))
        assert emby_video.read_bytes() == downloaded.archive_path.read_bytes()
        assert _stream_types(emby_video, ffprobe) == {"video", "audio"}
        assert (author_directory / "tvshow.nfo").is_file()
        assert next(author_directory.glob("Season 2026/*.nfo")).is_file()
        source_document = json.loads(next(author_directory.glob("Season 2026/*.assets/source.json")).read_text("utf-8"))
        assert not {"canonical_url", "locator", "raw", "source_url"} & source_document.keys()

        archive_tree = _tree(archive_root)
        library_tree = _tree(author_directory)
        replayed_download = service.run(download_request)
        replayed_export = export_service.export_author(
            EmbyExportRequest(author_id, "execution-0024-export-replay", lease_seconds=60)
        )
        assert replayed_download.disposition == "already_verified"
        assert replayed_export.already_exported is True
        assert len(_DetailRunner.calls) == 1
        assert len(requests) == 4
        assert _tree(archive_root) == archive_tree
        assert _tree(author_directory) == library_tree

        with database.session() as session:
            persisted_asset = session.get(Asset, str(asset_id))
            content = session.scalar(select(Content))
            subscription = session.get(Subscription, subscription_id)
            jobs = tuple(session.scalars(select(Job).order_by(Job.job_type, Job.id)).all())
            exports = tuple(session.scalars(select(ExportRecord)).all())
            assert persisted_asset is not None and content is not None and subscription is not None
            assert persisted_asset.status == "verified" and persisted_asset.generation == 1
            assert subscription.checkpoint_revision == 1
            assert {job.job_type for job in jobs} == {"asset_download", "export.emby"}
            assert all(job.status == "succeeded" and job.attempts == 1 for job in jobs)
            assert len(exports) == 1 and exports[0].status == "succeeded"
            durable = json.dumps(
                {
                    "asset": {
                        "locator": persisted_asset.locator,
                        "raw": persisted_asset.raw,
                        "source_url": persisted_asset.source_url,
                    },
                    "content": {"canonical_url": content.canonical_url, "raw": content.raw},
                    "jobs": [job.payload for job in jobs],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            assert SIGNED_SENTINEL not in durable
            assert BILIBILI_DASH_PAGE_FIELD not in durable
            assert BILIBILI_PAGES_FIELD not in durable

        _assert_ephemeral_absent(runtime_root, download_work_root, archive_root, export_work_root, library_root)
    finally:
        database.dispose()

    sqlite_artifacts = tuple(path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file())
    assert sqlite_artifacts
    _assert_ephemeral_absent(*sqlite_artifacts)
