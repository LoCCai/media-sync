"""Offline Weibo ordinary-image-to-Emby qualification."""

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
    Subscription,
    SyncRun,
)
from media_sync.integrations.mediacrawler import MediaCrawlerDetailRequest, MediaCrawlerDetailResult
from media_sync.integrations.mediacrawler.normalizers import NormalizationContext, normalize_jsonl_bytes
from media_sync.integrations.mediacrawler.weibo_media import WEIBO_IMAGES_FIELD
from media_sync.media import (
    AdapterRefreshLocator,
    MediaRequestProfile,
    ProbeResult,
    ResolvedLocator,
    SafeHttpClient,
    SecureMediaDownloader,
    ValidatedTarget,
    parse_locator,
)
from media_sync.security import SecretResolver

FIXED_AT = datetime(2026, 8, 31, 20, 16, 17, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
AUTHOR_REMOTE_ID = "1234567890"
CONTENT_ID = "5123456789012345"
IMAGE_REMOTE_IDS = tuple(f"{CONTENT_ID}:image:{position}" for position in range(2))
IMAGE_HINTS = (
    "https://i1.wp.com/wx1.sinaimg.cn/large/media001.png",
    "https://i1.wp.com/wx2.sinaimg.cn/large/media002.png",
)
PID_SENTINELS = ("EXECUTION0016PRIVATEPID0", "EXECUTION0016PRIVATEPID1")
SIGNED_URL_SENTINEL = "https://wx-private.sinaimg.cn/large/private.png?signature=EXECUTION0016SIGNATUREMUSTSTAYPRIVATE"
PNGS = (
    b"\x89PNG\r\n\x1a\n" + b"execution-0016-offline-weibo-image-zero",
    b"\x89PNG\r\n\x1a\n" + b"execution-0016-offline-weibo-image-one",
)
FORBIDDEN_VALUES = (WEIBO_IMAGES_FIELD, *PID_SENTINELS, SIGNED_URL_SENTINEL, "?signature=", "?token=")


def _jsonl(record: Mapping[str, object]) -> bytes:
    return (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _weibo_record() -> dict[str, object]:
    return {
        "note_id": CONTENT_ID,
        "content": "Execution 0016 ordinary original Weibo image gallery.",
        "create_time": 1788180000,
        "create_date_time": "2026-08-31 20:00:00",
        "liked_count": "16",
        "comments_count": "1",
        "shared_count": "0",
        "last_modify_ts": 1788180100,
        "note_url": f"https://m.weibo.cn/detail/{CONTENT_ID}",
        "creator_hash": "untrusted-weibo-creator",
        "nickname": "Untrusted nickname",
        "source_keyword": "fixture",
        WEIBO_IMAGES_FIELD: [{"pid": pid, "url": url} for pid, url in zip(PID_SENTINELS, IMAGE_HINTS, strict=True)],
        "future_private_shape": {WEIBO_IMAGES_FIELD: SIGNED_URL_SENTINEL},
    }


WEIBO_JSONL = _jsonl(_weibo_record())


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
            display_name="execution-0016-offline-account",
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
        return MediaCrawlerDetailResult(WEIBO_JSONL, UPSTREAM_SHA)


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


class _UnexpectedStructuralProbe:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    def probe(self, path: Path, *, timeout_seconds: float, max_output_bytes: int) -> ProbeResult:
        self.calls.append(path)
        raise AssertionError("a sniffed PNG must not invoke the structural media probe")


@dataclass(frozen=True, slots=True)
class _DownloadHarness:
    service: AssetDownloadService
    request: AssetDownloadRequest
    refresher: _RecordingRefresher


def _download_harness(
    database: Database,
    *,
    asset_id: UUID,
    subscription_id: UUID,
    tmp_path: Path,
    runtime_root: Path,
    download_work_root: Path,
    archive_root: Path,
    http: SafeHttpClient,
    probe: _UnexpectedStructuralProbe,
) -> _DownloadHarness:
    lazy_refresher = LazyMediaCrawlerLocatorRefresher(
        database,
        asset_id=asset_id,
        subscription_id=subscription_id,
        lock_path=tmp_path / "upstreams.lock.json",
        integration_root=runtime_root,
        python_executable=tmp_path / "python",
        secret_resolver=SecretResolver({}),
        license_acknowledged=True,
    )
    refresher = _RecordingRefresher(lazy_refresher)
    downloader = SecureMediaDownloader(http, refresher=refresher, probe=probe)
    return _DownloadHarness(
        service=AssetDownloadService(database, downloader, clock=lambda: FIXED_AT),
        request=AssetDownloadRequest(
            asset_id=asset_id,
            worker_id="execution-0016-image-download",
            work_root=download_work_root,
            archive_root=archive_root,
            lease_seconds=60,
        ),
        refresher=refresher,
    )


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


def test_weibo_image_gallery_reaches_emby_and_replays_without_private_capture_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "weibo-image.sqlite3"
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
        normalized = normalize_jsonl_bytes(WEIBO_JSONL, _normalization_context())
        assert not normalized.quarantined and not normalized.truncated_tail
        assert len(normalized.records) == 1
        record = normalized.records[0]
        assert record.content.kind is ContentKind.GALLERY
        assert WEIBO_IMAGES_FIELD not in record.content.raw["record"]
        assert all(pid not in repr(record.content.raw) for pid in PID_SENTINELS)
        assert SIGNED_URL_SENTINEL not in repr(record.content.raw)
        assert [(asset.kind, asset.position, asset.remote_id) for asset in record.assets] == [
            (AssetKind.IMAGE, position, IMAGE_REMOTE_IDS[position]) for position in range(2)
        ]
        assert tuple(asset_source_hint(asset.source_url) for asset in record.assets) == IMAGE_HINTS
        assert all("?" not in hint and "#" not in hint for hint in IMAGE_HINTS)

        first_run_id = _start_ingesting_run(database, seed.subscription_id)
        first_ingest = MediaCrawlerIngestionService(database).ingest(
            normalized.records,
            subscription_id=seed.subscription_id,
            run_id=first_run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )
        assert (first_ingest.accepted_count, first_ingest.discovered_count, first_ingest.asset_count) == (1, 1, 2)

        with database.session() as session:
            assets = list(session.scalars(select(Asset).order_by(Asset.position)).all())
            sources = {source.asset_id: source for source in session.scalars(select(AssetRefreshSource)).all()}
            assert len(assets) == len(sources) == 2
            for position, asset in enumerate(assets):
                locator = parse_locator(asset.locator)
                assert isinstance(locator, AdapterRefreshLocator)
                assert locator.adapter == "mediacrawler"
                assert locator.asset_key == stable_asset_key(
                    platform=Platform.WB.value,
                    content_remote_type="content",
                    content_remote_id=CONTENT_ID,
                    kind=AssetKind.IMAGE.value,
                    position=position,
                    remote_id=IMAGE_REMOTE_IDS[position],
                )
                assert (asset.remote_id, asset.position, asset.generation, asset.source_url) == (
                    IMAGE_REMOTE_IDS[position],
                    position,
                    1,
                    IMAGE_HINTS[position],
                )
                source = sources[asset.id]
                assert source.subscription_id == seed.subscription_id
                assert source.last_run_id == first_run_id
                assert source.observation_kind == "ingested"
                assert source.observed_generation == 1
                assert source.observed_semantic_fingerprint == asset.semantic_fingerprint
                assert source.observed_locator_fingerprint == asset.locator_fingerprint
            asset_ids = tuple(UUID(asset.id) for asset in assets)

        resolver = _RecordingPublicResolver()
        targets: list[ValidatedTarget] = []
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            request_url = str(request.url)
            assert request_url in IMAGE_HINTS
            position = IMAGE_HINTS.index(request_url)
            assert set(request.headers) == {"accept", "accept-encoding", "connection", "host", "user-agent"}
            assert request.headers["accept-encoding"] == "identity"
            assert request.headers["host"] == "i1.wp.com"
            assert not request.headers["user-agent"].startswith("Mozilla/5.0")
            assert "cookie" not in request.headers
            assert "authorization" not in request.headers
            assert "referer" not in request.headers
            assert "origin" not in request.headers
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(PNGS[position])),
                    "Content-Type": "image/png",
                    "ETag": f'"execution-0016-image-{position}-v1"',
                },
                content=PNGS[position],
            )

        def transport_factory(target: ValidatedTarget) -> httpx.BaseTransport:
            targets.append(target)
            return httpx.MockTransport(handler)

        probe = _UnexpectedStructuralProbe()
        http = SafeHttpClient(resolver, transport_factory=transport_factory)
        harnesses = tuple(
            _download_harness(
                database,
                asset_id=asset_id,
                subscription_id=UUID(seed.subscription_id),
                tmp_path=tmp_path,
                runtime_root=runtime_root,
                download_work_root=download_work_root,
                archive_root=archive_root,
                http=http,
                probe=probe,
            )
            for asset_id in asset_ids
        )

        first_downloads = tuple(harness.service.run(harness.request) for harness in harnesses)
        checksums = tuple(hashlib.sha256(payload).hexdigest() for payload in PNGS)
        expected_archives = tuple(archive_root / "sha256" / checksum[:2] / f"{checksum}.png" for checksum in checksums)
        for position, first_download in enumerate(first_downloads):
            assert first_download.disposition == "downloaded"
            assert (first_download.archive_path, first_download.checksum_sha256, first_download.mime_type) == (
                expected_archives[position].absolute(),
                checksums[position],
                "image/png",
            )
            assert expected_archives[position].read_bytes() == PNGS[position]
        assert probe.calls == []
        assert resolver.calls == [("i1.wp.com", 443), ("i1.wp.com", 443)]
        assert [target.address for target in targets] == ["8.8.8.8", "8.8.8.8"]
        assert [str(request.url) for request in requests] == list(IMAGE_HINTS)
        assert tuple(harness.refresher.results[0].url for harness in harnesses) == IMAGE_HINTS
        assert all(harness.refresher.results[0].request_profile is MediaRequestProfile.DEFAULT for harness in harnesses)

        assert len(_FakeDetailRunner.instances) == 2
        for detail_instance in _FakeDetailRunner.instances:
            assert detail_instance.constructor_kwargs == {
                "integration_root": runtime_root,
                "license_acknowledged": True,
                "lock_path": tmp_path / "upstreams.lock.json",
                "python_executable": tmp_path / "python",
            }
            assert len(detail_instance.calls) == 1
            detail_request = detail_instance.calls[0]
            assert detail_request.account_id == UUID(seed.account_id)
            assert detail_request.subscription_id == UUID(seed.subscription_id)
            assert detail_request.platform is Platform.WB
            assert detail_request.login_method is LoginMethod.QR
            assert detail_request.content_remote_id == CONTENT_ID
            assert detail_request.resolved_detail_reference() == CONTENT_ID
            assert detail_request.bili_progressive_detail is False

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        first_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0016-export", lease_seconds=60)
        )
        assert first_export.already_exported is False
        author_directory = library_root / first_export.output_path
        poster = next(author_directory.glob("Season */*-poster.png"))
        backdrop = next(author_directory.glob("Season */*-backdrop.png"))
        gallery = tuple(sorted(author_directory.glob("Season */*.assets/gallery-*.png")))
        assert len(gallery) == 2
        assert gallery[0].name.startswith("gallery-001-")
        assert gallery[1].name.startswith("gallery-002-")
        assert poster.read_bytes() == PNGS[0]
        assert backdrop.read_bytes() == PNGS[1]
        assert tuple(path.read_bytes() for path in gallery) == PNGS
        assert (author_directory / "tvshow.nfo").is_file()
        episode_nfo = next(author_directory.glob("Season */*.nfo"))
        episode_nfo_payload = episode_nfo.read_bytes()
        assert CONTENT_ID.encode() in episode_nfo_payload
        assert poster.name.encode() in episode_nfo_payload
        assert backdrop.name.encode() in episode_nfo_payload
        assert (author_directory / ".media-sync-managed-v1.json").is_file()
        source_path = next(author_directory.glob("Season */*.assets/source.json"))
        source_document = json.loads(source_path.read_text("utf-8"))
        assert source_document["platform"] == Platform.WB.value
        assert source_document["remote_id"] == CONTENT_ID
        assert [
            (item["kind"], item["position"], item["remote_id"], item["checksum_sha256"])
            for item in source_document["assets"]
        ] == [
            (AssetKind.IMAGE.value, position, IMAGE_REMOTE_IDS[position], checksums[position]) for position in range(2)
        ]
        assert not {"canonical_url", "locator", "raw", "source_url"} & source_document.keys()

        first_archive_tree = _tree(archive_root)
        first_library_tree = _tree(author_directory)
        _assert_private_values_absent(
            runtime_root,
            download_work_root,
            archive_root,
            export_work_root,
            library_root,
        )

        replay_batch = normalize_jsonl_bytes(WEIBO_JSONL, _normalization_context())
        second_run_id = _start_ingesting_run(database, seed.subscription_id)
        second_ingest = MediaCrawlerIngestionService(database).ingest(
            replay_batch.records,
            subscription_id=seed.subscription_id,
            run_id=second_run_id,
            expected_revision=1,
            mode=IngestionMode.FORWARD,
        )
        assert (second_ingest.accepted_count, second_ingest.discovered_count, second_ingest.asset_count) == (0, 0, 0)
        assert second_ingest.checkpoint_revision == 2

        replay_downloads = tuple(harness.service.run(harness.request) for harness in harnesses)
        replay_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0016-export-replay", lease_seconds=60)
        )
        for replay_download, first_download in zip(replay_downloads, first_downloads, strict=True):
            assert replay_download.disposition == "already_verified"
            assert replay_download.job_id == first_download.job_id
            assert replay_download.archive_path == first_download.archive_path
        assert replay_export.already_exported is True
        assert replay_export.job_id == first_export.job_id
        assert replay_export.source_fingerprint == first_export.source_fingerprint
        assert replay_export.rendered_fingerprint == first_export.rendered_fingerprint
        assert len(_FakeDetailRunner.instances) == len(requests) == len(targets) == 2
        assert sum(len(instance.calls) for instance in _FakeDetailRunner.instances) == 2
        assert resolver.calls == [("i1.wp.com", 443), ("i1.wp.com", 443)]
        assert probe.calls == []
        assert _tree(archive_root) == first_archive_tree
        assert _tree(author_directory) == first_library_tree

        with database.session() as session:
            final_assets = list(session.scalars(select(Asset).order_by(Asset.position)).all())
            final_content = session.scalar(select(Content))
            final_sources = {source.asset_id: source for source in session.scalars(select(AssetRefreshSource)).all()}
            subscription = session.get(Subscription, seed.subscription_id)
            jobs = list(session.scalars(select(Job).order_by(Job.job_type, Job.natural_key)).all())
            runs = list(session.scalars(select(SyncRun).order_by(SyncRun.created_at)).all())
            exports = list(session.scalars(select(ExportRecord)).all())
            assert len(final_assets) == len(final_sources) == 2 and final_content is not None
            assert subscription is not None
            for position, final_asset in enumerate(final_assets):
                assert final_asset.status == "verified" and final_asset.generation == 1
                assert final_asset.source_url == IMAGE_HINTS[position]
                assert final_asset.local_path == str(expected_archives[position].absolute())
                assert final_asset.checksum_sha256 == checksums[position]
                assert final_asset.mime_type == "image/png"
                assert isinstance(parse_locator(final_asset.locator), AdapterRefreshLocator)
                final_source = final_sources[final_asset.id]
                assert final_source.last_run_id == first_run_id and final_source.observed_generation == 1
            assert subscription.checkpoint_revision == 2
            assert [run.status for run in runs] == ["succeeded", "succeeded"]
            assert [job.job_type for job in jobs].count("asset_download") == 2
            assert [job.job_type for job in jobs].count("export.emby") == 1
            assert all(job.status == "succeeded" and job.attempts == 1 for job in jobs)
            assert len(exports) == 1 and exports[0].status == "succeeded"
            durable_json = json.dumps(
                {
                    "assets": [
                        {
                            "locator": asset.locator,
                            "raw": asset.raw,
                            "source_url": asset.source_url,
                        }
                        for asset in final_assets
                    ],
                    "content": {"canonical_url": final_content.canonical_url, "raw": final_content.raw},
                    "jobs": [job.payload for job in jobs],
                    "runs": [run.manifest for run in runs],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            assert all(value not in durable_json for value in FORBIDDEN_VALUES)

        _assert_private_values_absent(
            runtime_root,
            download_work_root,
            archive_root,
            export_work_root,
            library_root,
        )
    finally:
        database.dispose()

    sqlite_artifacts = [path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file()]
    assert sqlite_artifacts
    _assert_private_values_absent(*sqlite_artifacts)
