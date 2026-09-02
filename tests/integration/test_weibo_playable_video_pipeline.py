"""Offline Weibo ordinary-original-video-to-Emby qualification."""

from __future__ import annotations

import hashlib
import json
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
from media_sync.domain import AssetKind, AuthStatus, ContentKind, LoginMethod, Platform, RunStatus
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
from media_sync.infrastructure.db.asset_identity import asset_source_hint, stable_asset_key
from media_sync.infrastructure.db.models import (
    Asset,
    AssetRefreshSource,
    Content,
    ExportRecord,
    Job,
)
from media_sync.integrations.mediacrawler import MediaCrawlerDetailRequest, MediaCrawlerDetailResult
from media_sync.integrations.mediacrawler.normalizers import NormalizationContext, normalize_jsonl_bytes
from media_sync.integrations.mediacrawler.weibo_media import WEIBO_VIDEO_FIELD
from media_sync.media import (
    AdapterRefreshLocator,
    MediaRequestProfile,
    ProbeResult,
    ResolvedLocator,
    SafeHttpClient,
    SecureMediaDownloader,
    parse_locator,
)
from media_sync.security import SecretResolver

FIXED_AT = datetime(2026, 8, 31, 20, 16, 17, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
AUTHOR_REMOTE_ID = "1234567890"
CONTENT_ID = "5123456789012345"
VIDEO_REMOTE_ID = f"{CONTENT_ID}:video:0"
VIDEO_HINT = "https://f.us.sinaimg.cn/o0/weibo-playable.mp4"
SIGNED_SENTINEL = "EXECUTION0031SIGNATUREMUSTSTAYPRIVATE"
SIGNED_URL = (
    f"https://f.us.sinaimg.cn/o0/weibo-playable.mp4?KID=unistore,video&Expires=4102444800&ssig={SIGNED_SENTINEL}"
)
MP4 = b"\x00\x00\x00\x18ftypisom" + b"execution-0031-offline-weibo-playable-video"
FORBIDDEN_VALUES = (WEIBO_VIDEO_FIELD, SIGNED_URL, SIGNED_SENTINEL, "?KID=", "?ssig=")


def _jsonl(record: Mapping[str, object]) -> bytes:
    return (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _weibo_video_record(signed_url: str) -> dict[str, object]:
    return {
        "note_id": CONTENT_ID,
        "content": "Execution 0031 ordinary original Weibo playable video.",
        "create_time": 1788180000,
        "create_date_time": "2026-08-31 20:00:00",
        "liked_count": "31",
        "comments_count": "1",
        "shared_count": "0",
        "last_modify_ts": 1788180100,
        "note_url": f"https://m.weibo.cn/detail/{CONTENT_ID}",
        "creator_hash": "untrusted-weibo-creator",
        "nickname": "Untrusted nickname",
        "source_keyword": "fixture",
        WEIBO_VIDEO_FIELD: {"url": signed_url},
    }


FORWARD_JSONL = _jsonl(_weibo_video_record(SIGNED_URL))


def _normalization_context() -> NormalizationContext:
    return NormalizationContext(
        platform=Platform.WB,
        creator_remote_id=AUTHOR_REMOTE_ID,
        creator_display_name="Weibo Offline Creator",
        upstream_sha=UPSTREAM_SHA,
        ingested_at=FIXED_AT,
    )


def _policy() -> dict[str, object]:
    return {
        "mediacrawler": {
            "schema_version": 1,
            "allow_full_history": True,
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
    account_id: str
    author_id: str
    subscription_id: str


def _seed_subscription(database: Database) -> _Seed:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=Platform.WB.value,
            adapter="mediacrawler",
            display_name="execution-0031-offline-account",
            login_method=LoginMethod.QR.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=Platform.WB.value,
                remote_id=AUTHOR_REMOTE_ID,
                display_name="Weibo Offline Creator",
            ),
            seen_at=FIXED_AT,
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            policy=_policy(),
        )
        return _Seed(account_id=account.id, author_id=author.id, subscription_id=subscription.id)


class _FakeDetailRunner:
    instances: ClassVar[list[_FakeDetailRunner]] = []

    def __init__(self, **kwargs: object) -> None:
        self.constructor_kwargs = kwargs
        self.calls: list[MediaCrawlerDetailRequest] = []
        type(self).instances.append(self)

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        self.calls.append(request)
        return MediaCrawlerDetailResult(FORWARD_JSONL, UPSTREAM_SHA)


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


def _assert_private_values_absent(*roots: Path) -> None:
    forbidden = tuple(value.encode() for value in FORBIDDEN_VALUES)
    for root in roots:
        retained = {root.name: root.read_bytes()} if root.is_file() else _tree(root)
        for relative_path, payload in retained.items():
            assert all(value not in payload for value in forbidden), relative_path


def test_weibo_video_normalization_requires_the_private_capture_field() -> None:
    normalized = normalize_jsonl_bytes(FORWARD_JSONL, _normalization_context())

    assert not normalized.quarantined and not normalized.truncated_tail
    assert len(normalized.records) == 1
    record = normalized.records[0]
    assert record.content.kind is ContentKind.VIDEO
    assert [(asset.kind, asset.position, asset.remote_id) for asset in record.assets] == [
        (AssetKind.VIDEO, 0, VIDEO_REMOTE_ID)
    ]
    assert [asset.source_url for asset in record.assets] == [SIGNED_URL]

    stripped = _jsonl(
        {
            "note_id": CONTENT_ID,
            "content": "plain text note without media",
            "note_url": f"https://m.weibo.cn/detail/{CONTENT_ID}",
        }
    )
    text_only = normalize_jsonl_bytes(stripped, _normalization_context())
    assert text_only.records[0].content.kind is ContentKind.TEXT
    assert text_only.records[0].assets == ()


def test_weibo_playable_video_reaches_emby_without_persisting_signed_queries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "weibo-playable.sqlite3"
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
        normalized = normalize_jsonl_bytes(FORWARD_JSONL, _normalization_context())
        assert not normalized.quarantined and not normalized.truncated_tail
        discovered = normalized.records[0].assets
        assert [(asset.kind, asset.position, asset.remote_id) for asset in discovered] == [
            (AssetKind.VIDEO, 0, VIDEO_REMOTE_ID)
        ]
        assert [asset_source_hint(asset.source_url) for asset in discovered] == [VIDEO_HINT]

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
            content = session.scalar(select(Content))
            sources = tuple(session.scalars(select(AssetRefreshSource)).all())
            assert asset is not None and content is not None
            asset_id = UUID(asset.id)
            locator = parse_locator(asset.locator)
            assert isinstance(locator, AdapterRefreshLocator)
            assert locator.asset_key == stable_asset_key(
                platform=Platform.WB.value,
                content_remote_type="content",
                content_remote_id=CONTENT_ID,
                kind=AssetKind.VIDEO.value,
                position=0,
                remote_id=VIDEO_REMOTE_ID,
            )
            assert (asset.remote_id, asset.position, asset.generation, asset.source_url) == (
                VIDEO_REMOTE_ID,
                0,
                1,
                VIDEO_HINT,
            )
            assert content.kind == ContentKind.VIDEO.value
            assert len(sources) == 1 and sources[0].subscription_id == seed.subscription_id

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
        probe = _ControlledMp4Probe()
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            assert str(request.url) == SIGNED_URL
            assert set(request.headers) == {"accept", "accept-encoding", "connection", "host", "user-agent"}
            assert request.headers["accept-encoding"] == "identity"
            assert not request.headers["user-agent"].startswith("Mozilla/5.0")
            assert "cookie" not in request.headers
            assert "authorization" not in request.headers
            assert "referer" not in request.headers
            assert "origin" not in request.headers
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(MP4)),
                    "Content-Type": "video/mp4",
                    "ETag": '"execution-0031-weibo-video-v1"',
                },
                content=MP4,
            )

        downloader = SecureMediaDownloader(
            SafeHttpClient(
                resolver,
                transport_factory=lambda _target: httpx.MockTransport(handler),
            ),
            refresher=refresher,
            probe=probe,
        )
        service = AssetDownloadService(database, downloader, clock=lambda: FIXED_AT)
        download_request = AssetDownloadRequest(
            asset_id=asset_id,
            worker_id="execution-0031-video-download",
            work_root=download_work_root,
            archive_root=archive_root,
            lease_seconds=60,
        )

        downloaded = service.run(download_request)

        assert downloaded.disposition == "downloaded"
        assert downloaded.archive_path is not None and downloaded.archive_path.suffix == ".mp4"
        assert downloaded.archive_path.read_bytes() == MP4
        assert downloaded.mime_type == "video/mp4"
        assert downloaded.checksum_sha256 == hashlib.sha256(MP4).hexdigest()
        assert [str(request.url) for request in requests] == [SIGNED_URL]
        assert resolver.calls == [("f.us.sinaimg.cn", 443)]
        assert len(refresher.results) == 1
        target = refresher.results[0]
        assert target.url == SIGNED_URL
        assert target.request_profile is MediaRequestProfile.DEFAULT
        assert SIGNED_SENTINEL not in repr(target)
        assert len(_FakeDetailRunner.instances) == 1
        assert len(_FakeDetailRunner.instances[0].calls) == 1
        assert len(probe.calls) == 1

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        exported = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0031-export", lease_seconds=60)
        )
        assert exported.already_exported is False
        author_directory = library_root / exported.output_path
        emby_video = next(author_directory.glob("Season 2026/*.mp4"))
        assert emby_video.read_bytes() == MP4
        assert (author_directory / "tvshow.nfo").is_file()
        assert next(author_directory.glob("Season 2026/*.nfo")).is_file()
        source_document = json.loads(next(author_directory.glob("Season 2026/*.assets/source.json")).read_text("utf-8"))
        assert not {"canonical_url", "locator", "raw", "source_url"} & source_document.keys()

        archive_tree = _tree(archive_root)
        library_tree = _tree(author_directory)
        replayed_download = service.run(download_request)
        replayed_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0031-export-replay", lease_seconds=60)
        )
        assert replayed_download.disposition == "already_verified"
        assert replayed_export.already_exported is True
        assert len(_FakeDetailRunner.instances[0].calls) == 1
        assert len(requests) == 1
        assert len(probe.calls) == 1
        assert _tree(archive_root) == archive_tree
        assert _tree(author_directory) == library_tree

        with database.session() as session:
            persisted_asset = session.get(Asset, str(asset_id))
            jobs = tuple(session.scalars(select(Job).order_by(Job.job_type, Job.id)).all())
            exports = tuple(session.scalars(select(ExportRecord)).all())
            assert persisted_asset is not None
            assert persisted_asset.status == "verified" and persisted_asset.generation == 1
            assert persisted_asset.mime_type == "video/mp4"
            assert persisted_asset.source_url == VIDEO_HINT
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
                    "jobs": [job.payload for job in jobs],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            assert WEIBO_VIDEO_FIELD not in durable
            assert SIGNED_URL not in durable

        _assert_private_values_absent(runtime_root, download_work_root, archive_root, export_work_root, library_root)
    finally:
        database.dispose()

    sqlite_artifacts = tuple(path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file())
    assert sqlite_artifacts
    _assert_private_values_absent(*sqlite_artifacts)
