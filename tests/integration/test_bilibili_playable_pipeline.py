"""Offline Bilibili metadata-to-playable-Emby pipeline qualification."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
from media_sync.infrastructure.db.asset_identity import stable_asset_key
from media_sync.infrastructure.db.models import (
    Asset,
    AssetRefreshSource,
    Content,
    ExportRecord,
    Job,
    Subscription,
    SyncRun,
)
from media_sync.integrations.mediacrawler import MediaCrawlerDetailRequest, MediaCrawlerDetailResult
from media_sync.integrations.mediacrawler.bilibili_media import (
    BILIBILI_PAGES_FIELD,
    BILIBILI_PROGRESSIVE_BACKUPS_FIELD,
    BILIBILI_PROGRESSIVE_FORMAT_FIELD,
    BILIBILI_PROGRESSIVE_SEGMENTS_FIELD,
)
from media_sync.integrations.mediacrawler.normalizers import NormalizationContext, normalize_jsonl_bytes
from media_sync.media import (
    AdapterRefreshLocator,
    FFmpegStreamCopyMuxer,
    FFprobeMediaProbe,
    MediaRequestProfile,
    ProbeResult,
    ResolvedFlvLocator,
    ResolvedFlvSegmentsLocator,
    ResolvedLocator,
    ResolvedSegmentsLocator,
    SafeHttpClient,
    SecureMediaDownloader,
    ValidatedTarget,
    parse_locator,
)
from media_sync.security import SecretResolver

FIXED_AT = datetime(2026, 8, 31, 8, 9, 10, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
AUTHOR_REMOTE_ID = "424242"
CONTENT_ID = "987654321"
VIDEO_REMOTE_ID = f"{CONTENT_ID}:video:0"
PRIVATE_PROGRESSIVE_FIELD = "__media_sync_bili_progressive_url"
SIGNED_SENTINEL = "EXECUTION-0013-" + "SIGNED-URL-MUST-STAY-EPHEMERAL"
SIGNED_URL = (
    f"https://cn-bj-cm-01.bilivideo.com/upgcxcode/offline/first-page.mp4?deadline=1798765432&upsig={SIGNED_SENTINEL}"
)
BACKUP_SENTINEL = "EXECUTION-0026-BACKUP-URL-MUST-STAY-EPHEMERAL"
BACKUP_URL = (
    "https://backup-cn-bj-cm-01.bilivideo.com/upgcxcode/offline/first-page.mp4"
    f"?deadline=1798765432&upsig={BACKUP_SENTINEL}"
)
SECOND_SENTINEL = "EXECUTION-0029-SECOND-SEGMENT-MUST-STAY-EPHEMERAL"
SECOND_SIGNED_URL = (
    "https://second-cn-bj-cm-01.bilivideo.com/upgcxcode/offline/first-page-part2.mp4"
    f"?deadline=1798765432&upsig={SECOND_SENTINEL}"
)
MP4 = b"\x00\x00\x00\x18ftypisom" + b"execution-0013-offline-progressive-video"


def _jsonl(record: Mapping[str, object]) -> bytes:
    return (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


FORWARD_JSONL = _jsonl(
    {
        "desc": "Execution 0013 ordinary upload, logical first page.",
        "title": "Offline first-page progressive video",
        "video_id": CONTENT_ID,
        "video_type": "video",
        "video_url": f"https://www.bilibili.com/video/av{CONTENT_ID}",
    }
)
DETAIL_JSONL = _jsonl(
    {
        PRIVATE_PROGRESSIVE_FIELD: SIGNED_URL,
        BILIBILI_PROGRESSIVE_BACKUPS_FIELD: [BACKUP_URL],
        "desc": "Execution 0013 ordinary upload, logical first page.",
        "title": "Offline first-page progressive video",
        "video_id": CONTENT_ID,
        "video_type": "video",
        "video_url": f"https://www.bilibili.com/video/av{CONTENT_ID}",
    }
)
FLV_DETAIL_JSONL = _jsonl(
    {
        PRIVATE_PROGRESSIVE_FIELD: SIGNED_URL,
        BILIBILI_PROGRESSIVE_BACKUPS_FIELD: [BACKUP_URL],
        BILIBILI_PROGRESSIVE_FORMAT_FIELD: "flv",
        "desc": "Execution 0027 explicit FLV source, logical first page.",
        "title": "Offline first-page FLV remux video",
        "video_id": CONTENT_ID,
        "video_type": "video",
        "video_url": f"https://www.bilibili.com/video/av{CONTENT_ID}",
    }
)
SEGMENTS_DETAIL_JSONL = _jsonl(
    {
        BILIBILI_PAGES_FIELD: [{"page": 1, "cid": 24680}],
        BILIBILI_PROGRESSIVE_SEGMENTS_FIELD: {
            "cid": 24680,
            "segments": [
                {"url": SIGNED_URL, "backup_urls": [BACKUP_URL]},
                {"url": SECOND_SIGNED_URL},
            ],
        },
        "desc": "Execution 0029 ordinary multi-segment source, logical first page.",
        "title": "Offline first-page multi-segment concat video",
        "video_id": CONTENT_ID,
        "video_type": "video",
        "video_url": f"https://www.bilibili.com/video/av{CONTENT_ID}",
    }
)
SEGMENTS_FLV_DETAIL_JSONL = _jsonl(
    {
        BILIBILI_PAGES_FIELD: [{"page": 1, "cid": 24680}],
        BILIBILI_PROGRESSIVE_SEGMENTS_FIELD: {
            "cid": 24680,
            "format": "flv",
            "segments": [
                {"url": SIGNED_URL, "backup_urls": [BACKUP_URL]},
                {"url": SECOND_SIGNED_URL},
            ],
        },
        "desc": "Execution 0030 explicit multi-segment FLV source, logical first page.",
        "title": "Offline first-page multi-segment FLV concat video",
        "video_id": CONTENT_ID,
        "video_type": "video",
        "video_url": f"https://www.bilibili.com/video/av{CONTENT_ID}",
    }
)


def _policy() -> dict[str, object]:
    return {
        "mediacrawler": {
            "schema_version": 1,
            "allow_full_history": False,
            "request_delay_seconds": 1.0,
            "headless": True,
        }
    }


def _start_ingesting_run(database: Database, subscription_id: str) -> str:
    with database.session() as session:
        runs = SyncRunRepository(session)
        run = runs.create(subscription_id=subscription_id)
        runs.set_status(run.id, RunStatus.CLAIMED.value, expected_status=RunStatus.QUEUED.value)
        runs.set_status(run.id, RunStatus.RUNNING.value, expected_status=RunStatus.CLAIMED.value)
        runs.set_status(run.id, RunStatus.INGESTING.value, expected_status=RunStatus.RUNNING.value)
        return run.id


@dataclass(frozen=True, slots=True)
class _Seed:
    author_id: str
    subscription_id: str


def _seed_subscription(database: Database) -> _Seed:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=Platform.BILI.value,
            adapter="mediacrawler",
            display_name="execution-0013-offline-account",
            login_method=LoginMethod.QR.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=Platform.BILI.value,
                remote_id=AUTHOR_REMOTE_ID,
                display_name="Bilibili Offline Creator",
            ),
            seen_at=FIXED_AT,
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            policy=_policy(),
        )
        return _Seed(author_id=author.id, subscription_id=subscription.id)


class _FakeDetailRunner:
    instances: ClassVar[list[_FakeDetailRunner]] = []

    def __init__(self, **kwargs: object) -> None:
        self.constructor_kwargs = kwargs
        self.calls: list[MediaCrawlerDetailRequest] = []
        type(self).instances.append(self)

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        self.calls.append(request)
        return MediaCrawlerDetailResult(DETAIL_JSONL, UPSTREAM_SHA)


@dataclass(slots=True)
class _RecordingRefresher:
    delegate: LazyMediaCrawlerLocatorRefresher
    results: list[ResolvedLocator] = field(default_factory=list)

    def resolve(self, locator: AdapterRefreshLocator) -> ResolvedLocator:
        resolved = self.delegate.resolve(locator)
        self.results.append(resolved)
        return resolved


class _RecordingPublicResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        self.calls.append((hostname, port))
        return ("8.8.8.8",)


class _ControlledMp4Probe:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    def probe(self, path: Path, *, timeout_seconds: float, max_output_bytes: int) -> ProbeResult:
        assert timeout_seconds > 0
        assert max_output_bytes > 0
        self.calls.append(path)
        assert path.read_bytes() == MP4
        return ProbeResult("video/mp4", "mp4")


def _tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file()
    }


def _assert_signed_url_absent(*roots: Path) -> None:
    forbidden = (
        SIGNED_URL.encode(),
        SIGNED_SENTINEL.encode(),
        BACKUP_URL.encode(),
        BACKUP_SENTINEL.encode(),
        SECOND_SIGNED_URL.encode(),
        SECOND_SENTINEL.encode(),
        b"upsig=EXECUTION-0013",
        b"upsig=EXECUTION-0026",
        b"upsig=EXECUTION-0029",
        BILIBILI_PROGRESSIVE_FORMAT_FIELD.encode(),
        BILIBILI_PROGRESSIVE_SEGMENTS_FIELD.encode(),
    )
    for root in roots:
        retained = {root.name: root.read_bytes()} if root.is_file() else _tree(root)
        for relative_path, payload in retained.items():
            assert all(token not in payload for token in forbidden), relative_path


def test_bilibili_progressive_video_reaches_emby_without_persisting_signed_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "bilibili-playable.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    archive_root = tmp_path / "archive"
    library_root = tmp_path / "library"
    runtime_root = tmp_path / "mediacrawler-runtime"
    download_work_root = tmp_path / "download-work"
    export_work_root = tmp_path / "export-work"
    runtime_root.mkdir()
    upgrade_database(database_url)
    database = Database(database_url)
    _FakeDetailRunner.instances = []
    monkeypatch.setattr(mediacrawler_runtime, "MediaCrawlerDetailProcessRunner", _FakeDetailRunner)

    try:
        seed = _seed_subscription(database)
        normalized = normalize_jsonl_bytes(
            FORWARD_JSONL,
            NormalizationContext(
                platform=Platform.BILI,
                creator_remote_id=AUTHOR_REMOTE_ID,
                creator_display_name="Bilibili Offline Creator",
                upstream_sha=UPSTREAM_SHA,
                ingested_at=FIXED_AT,
            ),
        )
        assert not normalized.quarantined and not normalized.truncated_tail
        assert len(normalized.records) == 1
        discovered_video = normalized.records[0].assets
        assert len(discovered_video) == 1
        assert discovered_video[0].remote_id == VIDEO_REMOTE_ID
        assert discovered_video[0].kind is AssetKind.VIDEO
        assert discovered_video[0].source_url is None

        first_run_id = _start_ingesting_run(database, seed.subscription_id)
        first_ingest = MediaCrawlerIngestionService(database).ingest(
            normalized.records,
            subscription_id=seed.subscription_id,
            run_id=first_run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )
        assert (first_ingest.accepted_count, first_ingest.discovered_count, first_ingest.asset_count) == (1, 1, 1)

        with database.session() as session:
            asset = session.scalar(select(Asset))
            source = session.scalar(select(AssetRefreshSource))
            assert asset is not None and source is not None
            asset_id = UUID(asset.id)
            persisted_locator = parse_locator(asset.locator)
            assert isinstance(persisted_locator, AdapterRefreshLocator)
            assert persisted_locator.adapter == "mediacrawler"
            assert persisted_locator.asset_key == stable_asset_key(
                platform=Platform.BILI.value,
                content_remote_type="content",
                content_remote_id=CONTENT_ID,
                kind=AssetKind.VIDEO.value,
                position=0,
                remote_id=VIDEO_REMOTE_ID,
            )
            assert asset.source_url is None
            assert (asset.remote_id, asset.kind, asset.position, asset.generation) == (
                VIDEO_REMOTE_ID,
                AssetKind.VIDEO.value,
                0,
                1,
            )
            assert source.asset_id == asset.id
            assert source.subscription_id == seed.subscription_id
            assert source.last_run_id == first_run_id
            assert source.observation_kind == "ingested"
            assert source.observed_generation == asset.generation
            assert source.observed_semantic_fingerprint == asset.semantic_fingerprint
            assert source.observed_locator_fingerprint == asset.locator_fingerprint

        lazy_refresher = LazyMediaCrawlerLocatorRefresher(
            database,
            asset_id=asset_id,
            subscription_id=UUID(seed.subscription_id),
            lock_path=tmp_path / "upstreams.lock.json",
            integration_root=runtime_root,
            python_executable=tmp_path / "python",
            secret_resolver=SecretResolver({}),
            license_acknowledged=True,
        )
        refresher = _RecordingRefresher(lazy_refresher)
        resolver = _RecordingPublicResolver()
        targets: list[ValidatedTarget] = []
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            assert str(request.url) in {SIGNED_URL, BACKUP_URL}
            assert request.headers["referer"] == "https://www.bilibili.com/"
            assert request.headers["origin"] == "https://www.bilibili.com"
            assert request.headers["user-agent"].startswith("Mozilla/5.0")
            assert request.headers["accept-encoding"] == "identity"
            assert "cookie" not in request.headers
            assert "authorization" not in request.headers
            if str(request.url) == SIGNED_URL:
                assert request.headers["host"] == "cn-bj-cm-01.bilivideo.com"
                return httpx.Response(503)
            assert request.headers["host"] == "backup-cn-bj-cm-01.bilivideo.com"
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(MP4)),
                    "Content-Type": "video/mp4",
                    "ETag": '"execution-0013-v1"',
                },
                content=MP4,
            )

        def transport_factory(target: ValidatedTarget) -> httpx.BaseTransport:
            targets.append(target)
            return httpx.MockTransport(handler)

        probe = _ControlledMp4Probe()
        downloader = SecureMediaDownloader(
            SafeHttpClient(resolver, transport_factory=transport_factory),
            refresher=refresher,
            probe=probe,
        )
        download_service = AssetDownloadService(database, downloader, clock=lambda: FIXED_AT)
        download_request = AssetDownloadRequest(
            asset_id=asset_id,
            worker_id="execution-0013-download",
            work_root=download_work_root,
            archive_root=archive_root,
            lease_seconds=60,
        )
        first_download = download_service.run(download_request)
        expected_checksum = hashlib.sha256(MP4).hexdigest()
        expected_archive = archive_root / "sha256" / expected_checksum[:2] / f"{expected_checksum}.mp4"

        assert first_download.disposition == "downloaded"
        assert first_download.archive_path == expected_archive.absolute()
        assert first_download.archive_path.read_bytes() == MP4
        assert first_download.checksum_sha256 == expected_checksum
        assert first_download.mime_type == "video/mp4"
        assert len(probe.calls) == 1
        assert resolver.calls == [
            ("cn-bj-cm-01.bilivideo.com", 443),
            ("backup-cn-bj-cm-01.bilivideo.com", 443),
        ]
        assert [target.address for target in targets] == ["8.8.8.8", "8.8.8.8"]
        assert [str(request.url) for request in requests] == [SIGNED_URL, BACKUP_URL]
        assert len(refresher.results) == 1
        assert refresher.results[0].url == SIGNED_URL
        assert refresher.results[0].backup_urls == (BACKUP_URL,)
        assert refresher.results[0].request_profile is MediaRequestProfile.BILIBILI_MEDIA
        assert SIGNED_SENTINEL not in repr(refresher.results[0])
        assert len(_FakeDetailRunner.instances) == 1
        detail_runner = _FakeDetailRunner.instances[0]
        assert len(detail_runner.calls) == 1
        detail_request = detail_runner.calls[0]
        assert detail_request.platform is Platform.BILI
        assert detail_request.login_method is LoginMethod.QR
        assert detail_request.content_remote_id == CONTENT_ID
        assert detail_request.subscription_id == UUID(seed.subscription_id)
        assert detail_request.bili_progressive_detail is True
        assert SIGNED_SENTINEL not in repr(detail_request)
        assert SIGNED_SENTINEL not in repr(MediaCrawlerDetailResult(DETAIL_JSONL, UPSTREAM_SHA))

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        first_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0013-export", lease_seconds=60)
        )
        assert first_export.already_exported is False
        author_directory = library_root / first_export.output_path
        exported_video = next(author_directory.glob("Season 2026/*.mp4"))
        assert exported_video.read_bytes() == MP4
        assert (author_directory / "tvshow.nfo").is_file()
        assert next(author_directory.glob("Season 2026/*.nfo")).is_file()
        assert (author_directory / ".media-sync-managed-v1.json").is_file()
        source_document = json.loads(next(author_directory.glob("Season 2026/*.assets/source.json")).read_text("utf-8"))
        assert not {"canonical_url", "locator", "raw", "source_url"} & source_document.keys()

        first_archive_tree = _tree(archive_root)
        first_library_tree = _tree(author_directory)
        _assert_signed_url_absent(runtime_root, download_work_root, archive_root, export_work_root, library_root)

        second_run_id = _start_ingesting_run(database, seed.subscription_id)
        second_ingest = MediaCrawlerIngestionService(database).ingest(
            normalized.records,
            subscription_id=seed.subscription_id,
            run_id=second_run_id,
            expected_revision=1,
            mode=IngestionMode.FORWARD,
        )
        second_download = download_service.run(download_request)
        second_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0013-export-replay", lease_seconds=60)
        )

        assert (second_ingest.accepted_count, second_ingest.discovered_count, second_ingest.asset_count) == (1, 0, 0)
        assert second_ingest.checkpoint_revision == 2
        assert second_download.disposition == "already_verified"
        assert second_download.job_id == first_download.job_id
        assert second_download.archive_path == first_download.archive_path
        assert second_download.checksum_sha256 == first_download.checksum_sha256
        assert second_export.already_exported is True
        assert second_export.job_id == first_export.job_id
        assert second_export.source_fingerprint == first_export.source_fingerprint
        assert second_export.rendered_fingerprint == first_export.rendered_fingerprint
        assert len(requests) == 2
        assert len(refresher.results) == len(detail_runner.calls) == 1
        assert len(probe.calls) == 1
        assert _tree(archive_root) == first_archive_tree
        assert _tree(author_directory) == first_library_tree

        with database.session() as session:
            final_asset = session.scalar(select(Asset))
            final_content = session.scalar(select(Content))
            final_source = session.scalar(select(AssetRefreshSource))
            subscription = session.get(Subscription, seed.subscription_id)
            jobs = list(session.scalars(select(Job).order_by(Job.job_type)).all())
            runs = list(session.scalars(select(SyncRun).order_by(SyncRun.created_at)).all())
            exports = list(session.scalars(select(ExportRecord)).all())
            assert final_asset is not None and final_content is not None and final_source is not None
            assert subscription is not None
            assert final_asset.source_url is None
            assert final_asset.status == "verified"
            assert final_asset.generation == 1
            assert final_asset.local_path == str(expected_archive.absolute())
            assert final_asset.checksum_sha256 == expected_checksum
            assert final_asset.mime_type == "video/mp4"
            assert isinstance(parse_locator(final_asset.locator), AdapterRefreshLocator)
            assert final_source.last_run_id == second_run_id
            assert final_source.observed_generation == 1
            assert subscription.checkpoint_revision == 2
            assert [run.status for run in runs] == ["succeeded", "succeeded"]
            assert {job.job_type for job in jobs} == {"asset_download", "export.emby"}
            assert all(job.status == "succeeded" and job.attempts == 1 for job in jobs)
            assert len(exports) == 1 and exports[0].status == "succeeded"
            durable_json = json.dumps(
                {
                    "asset": {
                        "locator": final_asset.locator,
                        "raw": final_asset.raw,
                        "source_url": final_asset.source_url,
                    },
                    "content": {"canonical_url": final_content.canonical_url, "raw": final_content.raw},
                    "jobs": [job.payload for job in jobs],
                    "runs": [run.manifest for run in runs],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            assert PRIVATE_PROGRESSIVE_FIELD not in durable_json
            assert SIGNED_SENTINEL not in durable_json
            assert SIGNED_URL not in durable_json
            assert BACKUP_SENTINEL not in durable_json
            assert BACKUP_URL not in durable_json

        _assert_signed_url_absent(runtime_root, download_work_root, archive_root, export_work_root, library_root)
    finally:
        database.dispose()

    sqlite_artifacts = [path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file()]
    assert sqlite_artifacts
    _assert_signed_url_absent(*sqlite_artifacts)


class _FlvDetailRunner:
    instances: ClassVar[list[_FlvDetailRunner]] = []

    def __init__(self, **kwargs: object) -> None:
        self.constructor_kwargs = kwargs
        self.calls: list[MediaCrawlerDetailRequest] = []
        type(self).instances.append(self)

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        self.calls.append(request)
        return MediaCrawlerDetailResult(FLV_DETAIL_JSONL, UPSTREAM_SHA)


@dataclass(slots=True)
class _RecordingFlvRefresher:
    delegate: LazyMediaCrawlerLocatorRefresher
    results: list[ResolvedFlvLocator] = field(default_factory=list)

    def resolve(self, locator: AdapterRefreshLocator) -> ResolvedFlvLocator:
        resolved = self.delegate.resolve(locator)
        assert isinstance(resolved, ResolvedFlvLocator)
        self.results.append(resolved)
        return resolved


@dataclass(slots=True)
class _RecordingProductionProbe:
    delegate: FFprobeMediaProbe
    calls: list[Path] = field(default_factory=list)

    def probe(self, path: Path, *, timeout_seconds: float, max_output_bytes: int) -> ProbeResult | None:
        self.calls.append(path)
        return self.delegate.probe(
            path,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )


@dataclass(slots=True)
class _RecordingProductionMuxer:
    delegate: FFmpegStreamCopyMuxer
    remux_calls: list[tuple[Path, Path]] = field(default_factory=list)
    concat_calls: list[tuple[Path, Path, str]] = field(default_factory=list)

    def remux(
        self,
        source_path: Path,
        output_path: Path,
        *,
        root: Path,
        timeout_seconds: float,
        max_output_bytes: int,
        max_media_bytes: int,
    ) -> None:
        self.remux_calls.append((source_path, output_path))
        self.delegate.remux(
            source_path,
            output_path,
            root=root,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
            max_media_bytes=max_media_bytes,
        )

    def concat(
        self,
        list_path: Path,
        output_path: Path,
        *,
        root: Path,
        timeout_seconds: float,
        max_output_bytes: int,
        max_media_bytes: int,
    ) -> None:
        script = list_path.read_text("ascii")
        self.concat_calls.append((list_path, output_path, script))
        self.delegate.concat(
            list_path,
            output_path,
            root=root,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
            max_media_bytes=max_media_bytes,
        )


def _generate_mixed_flv(root: Path, ffmpeg: str) -> bytes:
    root.mkdir()
    source = root / "source.flv"
    command = (
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=64x64:r=5:d=0.6",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=44100:duration=0.6",
        "-shortest",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        "-f",
        "flv",
        "-y",
        str(source),
    )
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"local FLV fixture generation is unavailable: {type(exc).__name__}")
    payload = source.read_bytes()
    assert payload.startswith(b"FLV")
    return payload


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


def test_bilibili_flv_backup_reaches_emby_through_production_remux_with_zero_work_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg is None or ffprobe is None:
        pytest.skip("ffmpeg and ffprobe are required for production-process qualification")
    flv_bytes = _generate_mixed_flv(tmp_path / "fixtures", ffmpeg)
    database_path = tmp_path / "bilibili-flv.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    archive_root = tmp_path / "archive"
    library_root = tmp_path / "library"
    runtime_root = tmp_path / "mediacrawler-runtime"
    download_work_root = tmp_path / "download-work"
    export_work_root = tmp_path / "export-work"
    runtime_root.mkdir()
    upgrade_database(database_url)
    database = Database(database_url)
    _FlvDetailRunner.instances = []
    monkeypatch.setattr(mediacrawler_runtime, "MediaCrawlerDetailProcessRunner", _FlvDetailRunner)

    try:
        seed = _seed_subscription(database)
        normalized = normalize_jsonl_bytes(
            FORWARD_JSONL,
            NormalizationContext(
                platform=Platform.BILI,
                creator_remote_id=AUTHOR_REMOTE_ID,
                creator_display_name="Bilibili Offline Creator",
                upstream_sha=UPSTREAM_SHA,
                ingested_at=FIXED_AT,
            ),
        )
        assert not normalized.quarantined and not normalized.truncated_tail
        assert [(asset.remote_id, asset.kind, asset.source_url) for asset in normalized.records[0].assets] == [
            (VIDEO_REMOTE_ID, AssetKind.VIDEO, None)
        ]
        run_id = _start_ingesting_run(database, seed.subscription_id)
        ingestion = MediaCrawlerIngestionService(database).ingest(
            normalized.records,
            subscription_id=seed.subscription_id,
            run_id=run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )
        assert (ingestion.accepted_count, ingestion.discovered_count, ingestion.asset_count) == (1, 1, 1)

        with database.session() as session:
            asset = session.scalar(select(Asset))
            assert asset is not None
            asset_id = UUID(asset.id)
            assert isinstance(parse_locator(asset.locator), AdapterRefreshLocator)
            assert asset.source_url is None

        delegate = LazyMediaCrawlerLocatorRefresher(
            database,
            asset_id=asset_id,
            subscription_id=UUID(seed.subscription_id),
            lock_path=tmp_path / "upstreams.lock.json",
            integration_root=runtime_root,
            python_executable=tmp_path / "python",
            secret_resolver=SecretResolver({}),
            license_acknowledged=True,
        )
        refresher = _RecordingFlvRefresher(delegate)
        resolver = _RecordingPublicResolver()
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            assert str(request.url) in {SIGNED_URL, BACKUP_URL}
            assert request.headers["referer"] == "https://www.bilibili.com/"
            assert request.headers["origin"] == "https://www.bilibili.com"
            assert request.headers["accept-encoding"] == "identity"
            assert "cookie" not in request.headers and "authorization" not in request.headers
            if str(request.url) == SIGNED_URL:
                return httpx.Response(503)
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(flv_bytes)),
                    "Content-Type": "video/x-flv",
                    "ETag": '"execution-0027-flv-v1"',
                },
                content=flv_bytes,
            )

        production_probe = _RecordingProductionProbe(FFprobeMediaProbe(ffprobe))
        production_muxer = _RecordingProductionMuxer(FFmpegStreamCopyMuxer(ffmpeg))
        downloader = SecureMediaDownloader(
            SafeHttpClient(
                resolver,
                transport_factory=lambda _target: httpx.MockTransport(handler),
            ),
            refresher=refresher,
            probe=production_probe,
            muxer=production_muxer,
        )
        service = AssetDownloadService(database, downloader, clock=lambda: FIXED_AT)
        download_request = AssetDownloadRequest(
            asset_id=asset_id,
            worker_id="execution-0027-download",
            work_root=download_work_root,
            archive_root=archive_root,
            lease_seconds=60,
        )

        downloaded = service.run(download_request)

        assert downloaded.disposition == "downloaded"
        assert downloaded.archive_path is not None and downloaded.archive_path.suffix == ".mp4"
        assert downloaded.archive_path.read_bytes() != flv_bytes
        assert b"ftyp" in downloaded.archive_path.read_bytes()[:32]
        assert downloaded.mime_type == "video/mp4"
        assert downloaded.checksum_sha256 == hashlib.sha256(downloaded.archive_path.read_bytes()).hexdigest()
        assert _stream_types(downloaded.archive_path, ffprobe) == {"video", "audio"}
        assert [str(request.url) for request in requests] == [SIGNED_URL, BACKUP_URL]
        assert resolver.calls == [
            ("cn-bj-cm-01.bilivideo.com", 443),
            ("backup-cn-bj-cm-01.bilivideo.com", 443),
        ]
        assert len(refresher.results) == 1
        target = refresher.results[0]
        assert target.source.urls == (SIGNED_URL, BACKUP_URL)
        assert target.source.request_profile is MediaRequestProfile.BILIBILI_MEDIA
        assert SIGNED_SENTINEL not in repr(target)
        assert len(_FlvDetailRunner.instances) == 1
        assert len(_FlvDetailRunner.instances[0].calls) == 1
        assert len(production_probe.calls) == 2
        assert len(production_muxer.remux_calls) == 1
        assert not tuple((download_work_root / "parts").glob(f"{asset_id}.1*"))
        assert not tuple(archive_root.rglob("*.flv"))

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        exported = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0027-export", lease_seconds=60)
        )
        assert exported.already_exported is False
        author_directory = library_root / exported.output_path
        emby_video = next(author_directory.glob("Season 2026/*.mp4"))
        assert emby_video.read_bytes() == downloaded.archive_path.read_bytes()
        assert _stream_types(emby_video, ffprobe) == {"video", "audio"}
        assert not tuple(author_directory.rglob("*.flv"))
        assert (author_directory / "tvshow.nfo").is_file()
        assert next(author_directory.glob("Season 2026/*.nfo")).is_file()
        source_document = json.loads(next(author_directory.glob("Season 2026/*.assets/source.json")).read_text("utf-8"))
        assert not {"canonical_url", "locator", "raw", "source_url"} & source_document.keys()

        archive_tree = _tree(archive_root)
        library_tree = _tree(author_directory)
        replayed_download = service.run(download_request)
        replayed_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0027-export-replay", lease_seconds=60)
        )
        assert replayed_download.disposition == "already_verified"
        assert replayed_export.already_exported is True
        assert len(_FlvDetailRunner.instances[0].calls) == 1
        assert len(requests) == 2
        assert len(production_probe.calls) == 2
        assert len(production_muxer.remux_calls) == 1
        assert _tree(archive_root) == archive_tree
        assert _tree(author_directory) == library_tree

        with database.session() as session:
            persisted_asset = session.get(Asset, str(asset_id))
            content = session.scalar(select(Content))
            jobs = tuple(session.scalars(select(Job).order_by(Job.job_type, Job.id)).all())
            exports = tuple(session.scalars(select(ExportRecord)).all())
            assert persisted_asset is not None and content is not None
            assert persisted_asset.status == "verified" and persisted_asset.generation == 1
            assert persisted_asset.mime_type == "video/mp4"
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
            assert PRIVATE_PROGRESSIVE_FIELD not in durable
            assert BILIBILI_PROGRESSIVE_FORMAT_FIELD not in durable
            assert SIGNED_URL not in durable and BACKUP_URL not in durable

        _assert_signed_url_absent(runtime_root, download_work_root, archive_root, export_work_root, library_root)
    finally:
        database.dispose()

    sqlite_artifacts = tuple(path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file())
    assert sqlite_artifacts
    _assert_signed_url_absent(*sqlite_artifacts)


class _SegmentsDetailRunner:
    instances: ClassVar[list[_SegmentsDetailRunner]] = []

    def __init__(self, **kwargs: object) -> None:
        self.constructor_kwargs = kwargs
        self.calls: list[MediaCrawlerDetailRequest] = []
        type(self).instances.append(self)

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        self.calls.append(request)
        return MediaCrawlerDetailResult(SEGMENTS_DETAIL_JSONL, UPSTREAM_SHA)


@dataclass(slots=True)
class _RecordingSegmentsRefresher:
    delegate: LazyMediaCrawlerLocatorRefresher
    results: list[ResolvedSegmentsLocator] = field(default_factory=list)

    def resolve(self, locator: AdapterRefreshLocator) -> ResolvedSegmentsLocator:
        resolved = self.delegate.resolve(locator)
        assert isinstance(resolved, ResolvedSegmentsLocator)
        self.results.append(resolved)
        return resolved


def _generate_two_mp4_segments(root: Path, ffmpeg: str) -> tuple[bytes, bytes]:
    root.mkdir()
    first = root / "first.mp4"
    second = root / "second.mp4"
    try:
        subprocess.run(
            (
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=64x64:r=5:d=0.6",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=44100:duration=0.6",
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-f",
                "mp4",
                "-y",
                str(first),
            ),
            check=True,
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            (
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:s=64x64:r=5:d=0.6",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=44100:duration=0.6",
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-f",
                "mp4",
                "-y",
                str(second),
            ),
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"local MP4 segment fixture generation is unavailable: {type(exc).__name__}")
    first_payload = first.read_bytes()
    second_payload = second.read_bytes()
    assert first_payload[4:8] == b"ftyp"
    assert second_payload[4:8] == b"ftyp"
    assert first_payload != second_payload
    return first_payload, second_payload


def test_bilibili_multi_segment_backup_reaches_emby_through_production_concat_with_zero_work_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg is None or ffprobe is None:
        pytest.skip("ffmpeg and ffprobe are required for production-process qualification")
    first_segment, second_segment = _generate_two_mp4_segments(tmp_path / "fixtures", ffmpeg)
    database_path = tmp_path / "bilibili-segments.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    archive_root = tmp_path / "archive"
    library_root = tmp_path / "library"
    runtime_root = tmp_path / "mediacrawler-runtime"
    download_work_root = tmp_path / "download-work"
    export_work_root = tmp_path / "export-work"
    runtime_root.mkdir()
    upgrade_database(database_url)
    database = Database(database_url)
    _SegmentsDetailRunner.instances = []
    monkeypatch.setattr(mediacrawler_runtime, "MediaCrawlerDetailProcessRunner", _SegmentsDetailRunner)

    try:
        seed = _seed_subscription(database)
        normalized = normalize_jsonl_bytes(
            FORWARD_JSONL,
            NormalizationContext(
                platform=Platform.BILI,
                creator_remote_id=AUTHOR_REMOTE_ID,
                creator_display_name="Bilibili Offline Creator",
                upstream_sha=UPSTREAM_SHA,
                ingested_at=FIXED_AT,
            ),
        )
        assert not normalized.quarantined and not normalized.truncated_tail
        assert [(asset.remote_id, asset.kind, asset.source_url) for asset in normalized.records[0].assets] == [
            (VIDEO_REMOTE_ID, AssetKind.VIDEO, None)
        ]
        run_id = _start_ingesting_run(database, seed.subscription_id)
        ingestion = MediaCrawlerIngestionService(database).ingest(
            normalized.records,
            subscription_id=seed.subscription_id,
            run_id=run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )
        assert (ingestion.accepted_count, ingestion.discovered_count, ingestion.asset_count) == (1, 1, 1)

        with database.session() as session:
            asset = session.scalar(select(Asset))
            assert asset is not None
            asset_id = UUID(asset.id)
            assert isinstance(parse_locator(asset.locator), AdapterRefreshLocator)
            assert asset.source_url is None

        delegate = LazyMediaCrawlerLocatorRefresher(
            database,
            asset_id=asset_id,
            subscription_id=UUID(seed.subscription_id),
            lock_path=tmp_path / "upstreams.lock.json",
            integration_root=runtime_root,
            python_executable=tmp_path / "python",
            secret_resolver=SecretResolver({}),
            license_acknowledged=True,
        )
        refresher = _RecordingSegmentsRefresher(delegate)
        resolver = _RecordingPublicResolver()
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            assert str(request.url) in {SIGNED_URL, BACKUP_URL, SECOND_SIGNED_URL}
            assert request.headers["referer"] == "https://www.bilibili.com/"
            assert request.headers["origin"] == "https://www.bilibili.com"
            assert request.headers["accept-encoding"] == "identity"
            assert "cookie" not in request.headers and "authorization" not in request.headers
            if str(request.url) == SIGNED_URL:
                return httpx.Response(503)
            if str(request.url) == BACKUP_URL:
                return httpx.Response(
                    200,
                    headers={
                        "Content-Length": str(len(first_segment)),
                        "Content-Type": "video/mp4",
                        "ETag": '"execution-0029-segment-0"',
                    },
                    content=first_segment,
                )
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(second_segment)),
                    "Content-Type": "video/mp4",
                    "ETag": '"execution-0029-segment-1"',
                },
                content=second_segment,
            )

        production_probe = _RecordingProductionProbe(FFprobeMediaProbe(ffprobe))
        production_muxer = _RecordingProductionMuxer(FFmpegStreamCopyMuxer(ffmpeg))
        downloader = SecureMediaDownloader(
            SafeHttpClient(
                resolver,
                transport_factory=lambda _target: httpx.MockTransport(handler),
            ),
            refresher=refresher,
            probe=production_probe,
            muxer=production_muxer,
        )
        service = AssetDownloadService(database, downloader, clock=lambda: FIXED_AT)
        download_request = AssetDownloadRequest(
            asset_id=asset_id,
            worker_id="execution-0029-download",
            work_root=download_work_root,
            archive_root=archive_root,
            lease_seconds=60,
        )

        downloaded = service.run(download_request)

        assert downloaded.disposition == "downloaded"
        assert downloaded.archive_path is not None and downloaded.archive_path.suffix == ".mp4"
        final_bytes = downloaded.archive_path.read_bytes()
        assert b"ftyp" in final_bytes[:32]
        assert final_bytes != first_segment and final_bytes != second_segment
        assert downloaded.mime_type == "video/mp4"
        assert downloaded.checksum_sha256 == hashlib.sha256(final_bytes).hexdigest()
        assert _stream_types(downloaded.archive_path, ffprobe) == {"video", "audio"}
        assert [str(request.url) for request in requests] == [SIGNED_URL, BACKUP_URL, SECOND_SIGNED_URL]
        assert resolver.calls == [
            ("cn-bj-cm-01.bilivideo.com", 443),
            ("backup-cn-bj-cm-01.bilivideo.com", 443),
            ("second-cn-bj-cm-01.bilivideo.com", 443),
        ]
        assert len(refresher.results) == 1
        target = refresher.results[0]
        assert [segment.urls for segment in target.segments] == [
            (SIGNED_URL, BACKUP_URL),
            (SECOND_SIGNED_URL,),
        ]
        assert all(segment.request_profile is MediaRequestProfile.BILIBILI_MEDIA for segment in target.segments)
        assert SIGNED_SENTINEL not in repr(target)
        assert len(_SegmentsDetailRunner.instances) == 1
        assert len(_SegmentsDetailRunner.instances[0].calls) == 1
        assert len(production_probe.calls) == 3
        assert len(production_muxer.concat_calls) == 1
        assert len(production_muxer.remux_calls) == 0
        list_path, _output_path, script = production_muxer.concat_calls[0]
        assert list_path.parent == download_work_root / "parts"
        assert script == (f"file '{asset_id}.1.bili-segment-000.part'\nfile '{asset_id}.1.bili-segment-001.part'\n")
        assert not list_path.exists()
        assert not tuple((download_work_root / "parts").glob(f"{asset_id}.1.segments.txt"))

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        exported = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0029-export", lease_seconds=60)
        )
        assert exported.already_exported is False
        author_directory = library_root / exported.output_path
        emby_video = next(author_directory.glob("Season 2026/*.mp4"))
        assert emby_video.read_bytes() == final_bytes
        assert _stream_types(emby_video, ffprobe) == {"video", "audio"}
        assert (author_directory / "tvshow.nfo").is_file()
        assert next(author_directory.glob("Season 2026/*.nfo")).is_file()
        source_document = json.loads(next(author_directory.glob("Season 2026/*.assets/source.json")).read_text("utf-8"))
        assert not {"canonical_url", "locator", "raw", "source_url"} & source_document.keys()

        archive_tree = _tree(archive_root)
        library_tree = _tree(author_directory)
        replayed_download = service.run(download_request)
        replayed_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0029-export-replay", lease_seconds=60)
        )
        assert replayed_download.disposition == "already_verified"
        assert replayed_export.already_exported is True
        assert len(_SegmentsDetailRunner.instances[0].calls) == 1
        assert len(requests) == 3
        assert len(production_probe.calls) == 3
        assert len(production_muxer.concat_calls) == 1
        assert _tree(archive_root) == archive_tree
        assert _tree(author_directory) == library_tree

        with database.session() as session:
            persisted_asset = session.get(Asset, str(asset_id))
            content = session.scalar(select(Content))
            jobs = tuple(session.scalars(select(Job).order_by(Job.job_type, Job.id)).all())
            exports = tuple(session.scalars(select(ExportRecord)).all())
            assert persisted_asset is not None and content is not None
            assert persisted_asset.status == "verified" and persisted_asset.generation == 1
            assert persisted_asset.mime_type == "video/mp4"
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
            assert BILIBILI_PROGRESSIVE_SEGMENTS_FIELD not in durable
            assert SIGNED_URL not in durable and BACKUP_URL not in durable and SECOND_SIGNED_URL not in durable

        _assert_signed_url_absent(runtime_root, download_work_root, archive_root, export_work_root, library_root)
    finally:
        database.dispose()

    sqlite_artifacts = tuple(path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file())
    assert sqlite_artifacts
    _assert_signed_url_absent(*sqlite_artifacts)


class _FlvSegmentsDetailRunner:
    instances: ClassVar[list[_FlvSegmentsDetailRunner]] = []

    def __init__(self, **kwargs: object) -> None:
        self.constructor_kwargs = kwargs
        self.calls: list[MediaCrawlerDetailRequest] = []
        type(self).instances.append(self)

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        self.calls.append(request)
        return MediaCrawlerDetailResult(SEGMENTS_FLV_DETAIL_JSONL, UPSTREAM_SHA)


@dataclass(slots=True)
class _RecordingFlvSegmentsRefresher:
    delegate: LazyMediaCrawlerLocatorRefresher
    results: list[ResolvedFlvSegmentsLocator] = field(default_factory=list)

    def resolve(self, locator: AdapterRefreshLocator) -> ResolvedFlvSegmentsLocator:
        resolved = self.delegate.resolve(locator)
        assert isinstance(resolved, ResolvedFlvSegmentsLocator)
        self.results.append(resolved)
        return resolved


def _generate_two_flv_segments(root: Path, ffmpeg: str) -> tuple[bytes, bytes]:
    root.mkdir()
    first = root / "first.flv"
    second = root / "second.flv"
    try:
        subprocess.run(
            (
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=64x64:r=5:d=0.6",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=44100:duration=0.6",
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-f",
                "flv",
                "-y",
                str(first),
            ),
            check=True,
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            (
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:s=64x64:r=5:d=0.6",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=44100:duration=0.6",
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-f",
                "flv",
                "-y",
                str(second),
            ),
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"local FLV segment fixture generation is unavailable: {type(exc).__name__}")
    first_payload = first.read_bytes()
    second_payload = second.read_bytes()
    assert first_payload.startswith(b"FLV") and second_payload.startswith(b"FLV")
    assert first_payload != second_payload
    return first_payload, second_payload


def test_bilibili_multi_segment_flv_backup_reaches_emby_through_production_concat_with_zero_work_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg is None or ffprobe is None:
        pytest.skip("ffmpeg and ffprobe are required for production-process qualification")
    first_segment, second_segment = _generate_two_flv_segments(tmp_path / "fixtures", ffmpeg)
    database_path = tmp_path / "bilibili-flv-segments.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    archive_root = tmp_path / "archive"
    library_root = tmp_path / "library"
    runtime_root = tmp_path / "mediacrawler-runtime"
    download_work_root = tmp_path / "download-work"
    export_work_root = tmp_path / "export-work"
    runtime_root.mkdir()
    upgrade_database(database_url)
    database = Database(database_url)
    _FlvSegmentsDetailRunner.instances = []
    monkeypatch.setattr(mediacrawler_runtime, "MediaCrawlerDetailProcessRunner", _FlvSegmentsDetailRunner)

    try:
        seed = _seed_subscription(database)
        normalized = normalize_jsonl_bytes(
            FORWARD_JSONL,
            NormalizationContext(
                platform=Platform.BILI,
                creator_remote_id=AUTHOR_REMOTE_ID,
                creator_display_name="Bilibili Offline Creator",
                upstream_sha=UPSTREAM_SHA,
                ingested_at=FIXED_AT,
            ),
        )
        assert not normalized.quarantined and not normalized.truncated_tail
        run_id = _start_ingesting_run(database, seed.subscription_id)
        ingestion = MediaCrawlerIngestionService(database).ingest(
            normalized.records,
            subscription_id=seed.subscription_id,
            run_id=run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )
        assert (ingestion.accepted_count, ingestion.discovered_count, ingestion.asset_count) == (1, 1, 1)

        with database.session() as session:
            asset = session.scalar(select(Asset))
            assert asset is not None
            asset_id = UUID(asset.id)

        delegate = LazyMediaCrawlerLocatorRefresher(
            database,
            asset_id=asset_id,
            subscription_id=UUID(seed.subscription_id),
            lock_path=tmp_path / "upstreams.lock.json",
            integration_root=runtime_root,
            python_executable=tmp_path / "python",
            secret_resolver=SecretResolver({}),
            license_acknowledged=True,
        )
        refresher = _RecordingFlvSegmentsRefresher(delegate)
        resolver = _RecordingPublicResolver()
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            assert str(request.url) in {SIGNED_URL, BACKUP_URL, SECOND_SIGNED_URL}
            assert request.headers["referer"] == "https://www.bilibili.com/"
            assert request.headers["origin"] == "https://www.bilibili.com"
            assert request.headers["accept-encoding"] == "identity"
            assert "cookie" not in request.headers and "authorization" not in request.headers
            if str(request.url) == SIGNED_URL:
                return httpx.Response(503)
            if str(request.url) == BACKUP_URL:
                return httpx.Response(
                    200,
                    headers={
                        "Content-Length": str(len(first_segment)),
                        "Content-Type": "video/x-flv",
                        "ETag": '"execution-0030-segment-0"',
                    },
                    content=first_segment,
                )
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(second_segment)),
                    "Content-Type": "video/x-flv",
                    "ETag": '"execution-0030-segment-1"',
                },
                content=second_segment,
            )

        production_probe = _RecordingProductionProbe(FFprobeMediaProbe(ffprobe))
        production_muxer = _RecordingProductionMuxer(FFmpegStreamCopyMuxer(ffmpeg))
        downloader = SecureMediaDownloader(
            SafeHttpClient(
                resolver,
                transport_factory=lambda _target: httpx.MockTransport(handler),
            ),
            refresher=refresher,
            probe=production_probe,
            muxer=production_muxer,
        )
        service = AssetDownloadService(database, downloader, clock=lambda: FIXED_AT)
        download_request = AssetDownloadRequest(
            asset_id=asset_id,
            worker_id="execution-0030-download",
            work_root=download_work_root,
            archive_root=archive_root,
            lease_seconds=60,
        )

        downloaded = service.run(download_request)

        assert downloaded.disposition == "downloaded"
        assert downloaded.archive_path is not None and downloaded.archive_path.suffix == ".mp4"
        final_bytes = downloaded.archive_path.read_bytes()
        assert b"ftyp" in final_bytes[:32]
        assert final_bytes != first_segment and final_bytes != second_segment
        assert downloaded.mime_type == "video/mp4"
        assert downloaded.checksum_sha256 == hashlib.sha256(final_bytes).hexdigest()
        assert _stream_types(downloaded.archive_path, ffprobe) == {"video", "audio"}
        assert [str(request.url) for request in requests] == [SIGNED_URL, BACKUP_URL, SECOND_SIGNED_URL]
        assert len(refresher.results) == 1
        target = refresher.results[0]
        assert isinstance(target.source, ResolvedSegmentsLocator)
        assert [segment.urls for segment in target.source.segments] == [
            (SIGNED_URL, BACKUP_URL),
            (SECOND_SIGNED_URL,),
        ]
        assert SIGNED_SENTINEL not in repr(target)
        assert len(_FlvSegmentsDetailRunner.instances) == 1
        assert len(_FlvSegmentsDetailRunner.instances[0].calls) == 1
        assert len(production_probe.calls) == 3
        assert len(production_muxer.concat_calls) == 1
        assert len(production_muxer.remux_calls) == 0
        list_path, _output_path, script = production_muxer.concat_calls[0]
        assert list_path.parent == download_work_root / "parts"
        assert script == (f"file '{asset_id}.1.bili-segment-000.part'\nfile '{asset_id}.1.bili-segment-001.part'\n")
        assert not list_path.exists()
        assert not tuple(archive_root.rglob("*.flv"))

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        exported = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0030-export", lease_seconds=60)
        )
        assert exported.already_exported is False
        author_directory = library_root / exported.output_path
        emby_video = next(author_directory.glob("Season 2026/*.mp4"))
        assert emby_video.read_bytes() == final_bytes
        assert _stream_types(emby_video, ffprobe) == {"video", "audio"}
        assert not tuple(author_directory.rglob("*.flv"))
        assert (author_directory / "tvshow.nfo").is_file()
        assert next(author_directory.glob("Season 2026/*.nfo")).is_file()

        archive_tree = _tree(archive_root)
        library_tree = _tree(author_directory)
        replayed_download = service.run(download_request)
        replayed_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0030-export-replay", lease_seconds=60)
        )
        assert replayed_download.disposition == "already_verified"
        assert replayed_export.already_exported is True
        assert len(_FlvSegmentsDetailRunner.instances[0].calls) == 1
        assert len(requests) == 3
        assert len(production_probe.calls) == 3
        assert len(production_muxer.concat_calls) == 1
        assert _tree(archive_root) == archive_tree
        assert _tree(author_directory) == library_tree

        with database.session() as session:
            persisted_asset = session.get(Asset, str(asset_id))
            assert persisted_asset is not None
            assert persisted_asset.status == "verified" and persisted_asset.generation == 1
            assert persisted_asset.mime_type == "video/mp4"
            durable = json.dumps(
                {
                    "asset": {
                        "locator": persisted_asset.locator,
                        "raw": persisted_asset.raw,
                        "source_url": persisted_asset.source_url,
                    },
                    "jobs": [job.payload for job in session.scalars(select(Job).order_by(Job.job_type, Job.id)).all()],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            assert BILIBILI_PROGRESSIVE_SEGMENTS_FIELD not in durable
            assert SIGNED_URL not in durable and BACKUP_URL not in durable and SECOND_SIGNED_URL not in durable

        _assert_signed_url_absent(runtime_root, download_work_root, archive_root, export_work_root, library_root)
    finally:
        database.dispose()

    sqlite_artifacts = tuple(path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file())
    assert sqlite_artifacts
    _assert_signed_url_absent(*sqlite_artifacts)
