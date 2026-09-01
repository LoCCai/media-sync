"""Offline Bilibili bounded multipart progressive-to-Emby qualification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
from media_sync.domain import AuthStatus, LoginMethod, Platform, RunStatus
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
from media_sync.integrations.mediacrawler.bilibili_media import (
    BILIBILI_PAGES_FIELD,
    BILIBILI_PROGRESSIVE_PAGE_FIELD,
)
from media_sync.integrations.mediacrawler.normalizers import NormalizationContext, normalize_jsonl_bytes
from media_sync.media import ProbeResult, SafeHttpClient, SecureMediaDownloader, ValidatedTarget
from media_sync.security import SecretResolver

FIXED_AT = datetime(2026, 9, 2, 12, 34, 56, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
AUTHOR_REMOTE_ID = "424242"
CONTENT_ID = "987654321"
CIDS = (24680, 97531, 86420)
REMOTE_IDS = tuple(f"{CONTENT_ID}:video:cid:{cid}" for cid in CIDS)
PAGES = tuple({"page": index, "cid": cid} for index, cid in enumerate(CIDS, 1))
SIGNED_SENTINEL = "EXECUTION-0023-SIGNED-URL-MUST-STAY-EPHEMERAL"
SIGNED_URLS = {
    cid: (
        f"https://cn-bj-cm-0{index}.bilivideo.com/upgcxcode/offline/p{index}.mp4"
        f"?deadline=1798765432&upsig={SIGNED_SENTINEL}-P{index}"
    )
    for index, cid in enumerate(CIDS, 1)
}
MEDIA_BYTES = {
    cid: b"\x00\x00\x00\x18ftypisom" + f"execution-0023-page-{index}".encode() for index, cid in enumerate(CIDS, 1)
}


def _jsonl(record: Mapping[str, object]) -> bytes:
    return (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


FORWARD_JSONL = _jsonl(
    {
        BILIBILI_PAGES_FIELD: PAGES,
        "desc": "Execution 0023 ordinary bounded three-page upload.",
        "title": "Offline three-page progressive upload",
        "video_id": CONTENT_ID,
        "video_type": "video",
        "video_url": f"https://www.bilibili.com/video/av{CONTENT_ID}",
    }
)


def _detail_jsonl(cid: int) -> bytes:
    return _jsonl(
        {
            BILIBILI_PAGES_FIELD: PAGES,
            BILIBILI_PROGRESSIVE_PAGE_FIELD: {"cid": cid, "url": SIGNED_URLS[cid]},
            "desc": "Execution 0023 ordinary bounded three-page upload.",
            "title": "Offline three-page progressive upload",
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


@dataclass(frozen=True, slots=True)
class _Seed:
    author_id: str
    subscription_id: str


def _seed(database: Database) -> _Seed:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=Platform.BILI.value,
            adapter="mediacrawler",
            display_name="execution-0023-offline-account",
            login_method=LoginMethod.QR.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=Platform.BILI.value,
                remote_id=AUTHOR_REMOTE_ID,
                display_name="Bilibili Multipart Offline Creator",
            ),
            seen_at=FIXED_AT,
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            policy=_policy(),
        )
        return _Seed(author_id=author.id, subscription_id=subscription.id)


def _start_ingesting_run(database: Database, subscription_id: str) -> str:
    with database.session() as session:
        runs = SyncRunRepository(session)
        run = runs.create(subscription_id=subscription_id)
        runs.set_status(run.id, RunStatus.CLAIMED.value, expected_status=RunStatus.QUEUED.value)
        runs.set_status(run.id, RunStatus.RUNNING.value, expected_status=RunStatus.CLAIMED.value)
        runs.set_status(run.id, RunStatus.INGESTING.value, expected_status=RunStatus.RUNNING.value)
        return run.id


class _TargetedDetailRunner:
    calls: ClassVar[list[MediaCrawlerDetailRequest]] = []

    def __init__(self, **_kwargs: object) -> None:
        pass

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        assert request.bili_progressive_detail is True
        cid = request.bili_video_cid
        assert cid in CIDS
        assert isinstance(cid, int)
        type(self).calls.append(request)
        return MediaCrawlerDetailResult(_detail_jsonl(cid), UPSTREAM_SHA)


class _RecordingResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        self.calls.append((hostname, port))
        return ("8.8.8.8",)


class _ControlledProbe:
    def __init__(self) -> None:
        self.payloads: list[bytes] = []

    def probe(self, path: Path, *, timeout_seconds: float, max_output_bytes: int) -> ProbeResult:
        assert timeout_seconds > 0 and max_output_bytes > 0
        payload = path.read_bytes()
        assert payload in MEDIA_BYTES.values()
        self.payloads.append(payload)
        return ProbeResult("video/mp4", "mp4")


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
        BILIBILI_PAGES_FIELD.encode(),
        BILIBILI_PROGRESSIVE_PAGE_FIELD.encode(),
    )
    for root in roots:
        retained = {root.name: root.read_bytes()} if root.is_file() else _tree(root)
        for relative_path, payload in retained.items():
            assert all(token not in payload for token in forbidden), relative_path


def test_three_bilibili_pages_reach_emby_and_replay_without_new_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "bilibili-multipart.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    archive_root = tmp_path / "archive"
    library_root = tmp_path / "library"
    runtime_root = tmp_path / "mediacrawler-runtime"
    download_work_root = tmp_path / "download-work"
    export_work_root = tmp_path / "export-work"
    runtime_root.mkdir()
    upgrade_database(database_url)
    database = Database(database_url)
    _TargetedDetailRunner.calls = []
    monkeypatch.setattr(mediacrawler_runtime, "MediaCrawlerDetailProcessRunner", _TargetedDetailRunner)

    try:
        seed = _seed(database)
        normalized = normalize_jsonl_bytes(
            FORWARD_JSONL,
            NormalizationContext(
                platform=Platform.BILI,
                creator_remote_id=AUTHOR_REMOTE_ID,
                creator_display_name="Bilibili Multipart Offline Creator",
                upstream_sha=UPSTREAM_SHA,
                ingested_at=FIXED_AT,
            ),
        )
        assert not normalized.quarantined and not normalized.truncated_tail
        assert len(normalized.records) == 1
        discovered = normalized.records[0].assets
        assert [(asset.remote_id, asset.position, asset.source_url) for asset in discovered] == [
            (REMOTE_IDS[0], 0, None),
            (REMOTE_IDS[1], 1, None),
            (REMOTE_IDS[2], 2, None),
        ]

        first_run_id = _start_ingesting_run(database, seed.subscription_id)
        first_ingest = MediaCrawlerIngestionService(database).ingest(
            normalized.records,
            subscription_id=seed.subscription_id,
            run_id=first_run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )
        assert (first_ingest.accepted_count, first_ingest.discovered_count, first_ingest.asset_count) == (1, 1, 3)

        with database.session() as session:
            persisted = tuple(session.scalars(select(Asset).order_by(Asset.position)).all())
            sources = tuple(session.scalars(select(AssetRefreshSource).order_by(AssetRefreshSource.asset_id)).all())
            assert len(persisted) == len(sources) == 3
            asset_ids = tuple(UUID(asset.id) for asset in persisted)
            assert [(asset.remote_id, asset.position, asset.source_url, asset.generation) for asset in persisted] == [
                (REMOTE_IDS[0], 0, None, 1),
                (REMOTE_IDS[1], 1, None, 1),
                (REMOTE_IDS[2], 2, None, 1),
            ]

        resolver = _RecordingResolver()
        probe = _ControlledProbe()
        http_requests: list[httpx.Request] = []
        expected_by_url = {url: MEDIA_BYTES[cid] for cid, url in SIGNED_URLS.items()}

        def handler(request: httpx.Request) -> httpx.Response:
            http_requests.append(request)
            url = str(request.url)
            payload = expected_by_url[url]
            assert request.headers["referer"] == "https://www.bilibili.com/"
            assert request.headers["origin"] == "https://www.bilibili.com"
            assert request.headers["user-agent"].startswith("Mozilla/5.0")
            assert request.headers["accept-encoding"] == "identity"
            assert "cookie" not in request.headers and "authorization" not in request.headers
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(payload)),
                    "Content-Type": "video/mp4",
                    "ETag": f'"execution-0023-{len(http_requests)}"',
                },
                content=payload,
            )

        def transport_factory(_target: ValidatedTarget) -> httpx.BaseTransport:
            return httpx.MockTransport(handler)

        download_services: list[AssetDownloadService] = []
        download_requests: list[AssetDownloadRequest] = []
        first_downloads = []
        for position, asset_id in enumerate(asset_ids):
            refresher = LazyMediaCrawlerLocatorRefresher(
                database,
                asset_id=asset_id,
                subscription_id=UUID(seed.subscription_id),
                lock_path=tmp_path / "upstreams.lock.json",
                integration_root=runtime_root,
                python_executable=tmp_path / "python",
                secret_resolver=SecretResolver({}),
                license_acknowledged=True,
            )
            downloader = SecureMediaDownloader(
                SafeHttpClient(resolver, transport_factory=transport_factory),
                refresher=refresher,
                probe=probe,
            )
            service = AssetDownloadService(database, downloader, clock=lambda: FIXED_AT)
            request = AssetDownloadRequest(
                asset_id=asset_id,
                worker_id=f"execution-0023-download-{position}",
                work_root=download_work_root,
                archive_root=archive_root,
                lease_seconds=60,
            )
            download_services.append(service)
            download_requests.append(request)
            first_downloads.append(service.run(request))

        assert all(outcome.disposition == "downloaded" for outcome in first_downloads)
        assert [request.bili_video_cid for request in _TargetedDetailRunner.calls] == list(CIDS)
        assert all(request.bili_progressive_detail for request in _TargetedDetailRunner.calls)
        assert len(http_requests) == len(resolver.calls) == len(probe.payloads) == 3
        assert {outcome.checksum_sha256 for outcome in first_downloads} == {
            hashlib.sha256(payload).hexdigest() for payload in MEDIA_BYTES.values()
        }
        assert all(outcome.archive_path is not None and outcome.archive_path.is_file() for outcome in first_downloads)

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        first_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0023-export", lease_seconds=60)
        )
        assert first_export.already_exported is False
        author_directory = library_root / first_export.output_path
        videos = tuple(sorted(author_directory.glob("Season 2026/*.mp4"), key=lambda path: path.name))
        assert len(videos) == 3
        assert {path.read_bytes() for path in videos} == set(MEDIA_BYTES.values())
        assert sum("-part-" in path.name for path in videos) == 2
        assert (author_directory / "tvshow.nfo").is_file()
        assert len(tuple(author_directory.glob("Season 2026/*.nfo"))) == 1
        source_document = json.loads(next(author_directory.glob("Season 2026/*.assets/source.json")).read_text("utf-8"))
        assert [asset["remote_id"] for asset in source_document["assets"]] == list(REMOTE_IDS)
        assert not {"canonical_url", "locator", "raw", "source_url"} & source_document.keys()

        first_archive_tree = _tree(archive_root)
        first_library_tree = _tree(author_directory)
        _assert_ephemeral_absent(runtime_root, download_work_root, archive_root, export_work_root, library_root)

        second_run_id = _start_ingesting_run(database, seed.subscription_id)
        second_ingest = MediaCrawlerIngestionService(database).ingest(
            normalized.records,
            subscription_id=seed.subscription_id,
            run_id=second_run_id,
            expected_revision=1,
            mode=IngestionMode.FORWARD,
        )
        second_downloads = [
            service.run(request) for service, request in zip(download_services, download_requests, strict=True)
        ]
        second_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0023-export-replay", lease_seconds=60)
        )

        assert (second_ingest.accepted_count, second_ingest.discovered_count, second_ingest.asset_count) == (1, 0, 0)
        assert all(outcome.disposition == "already_verified" for outcome in second_downloads)
        assert second_export.already_exported is True
        assert len(_TargetedDetailRunner.calls) == len(http_requests) == len(resolver.calls) == len(probe.payloads) == 3
        assert _tree(archive_root) == first_archive_tree
        assert _tree(author_directory) == first_library_tree

        with database.session() as session:
            assets = tuple(session.scalars(select(Asset).order_by(Asset.position)).all())
            content = session.scalar(select(Content))
            subscription = session.get(Subscription, seed.subscription_id)
            jobs = tuple(session.scalars(select(Job).order_by(Job.job_type, Job.id)).all())
            exports = tuple(session.scalars(select(ExportRecord)).all())
            assert content is not None and subscription is not None
            assert all(asset.status == "verified" and asset.generation == 1 for asset in assets)
            assert subscription.checkpoint_revision == 2
            assert {job.job_type for job in jobs} == {"asset_download", "export.emby"}
            assert all(job.status == "succeeded" and job.attempts == 1 for job in jobs)
            assert len(exports) == 1 and exports[0].status == "succeeded"
            durable = json.dumps(
                {
                    "assets": [
                        {"locator": asset.locator, "raw": asset.raw, "source_url": asset.source_url} for asset in assets
                    ],
                    "content": {"canonical_url": content.canonical_url, "raw": content.raw},
                    "jobs": [job.payload for job in jobs],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            assert SIGNED_SENTINEL not in durable
            assert BILIBILI_PAGES_FIELD not in durable
            assert BILIBILI_PROGRESSIVE_PAGE_FIELD not in durable

        _assert_ephemeral_absent(runtime_root, download_work_root, archive_root, export_work_root, library_root)
    finally:
        database.dispose()

    sqlite_artifacts = [path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file()]
    assert sqlite_artifacts
    _assert_ephemeral_absent(*sqlite_artifacts)
