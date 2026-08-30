"""Offline Kuaishou single-video-to-playable-Emby qualification."""

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

FIXED_AT = datetime(2026, 8, 31, 9, 10, 11, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
AUTHOR_REMOTE_ID = "3x84qugg4ch9zhs"
CONTENT_ID = "3x3zxz4mjrsc8ke"
VIDEO_REMOTE_ID = f"{CONTENT_ID}:video:0"
COVER_REMOTE_ID = f"{CONTENT_ID}:cover:0"

VIDEO_HINT = f"https://video.example.test/ks/{CONTENT_ID}/main.mp4"
COVER_HINT = f"https://image.example.test/ks/{CONTENT_ID}/cover.png"
FORWARD_V1_SENTINEL = "EXECUTION-0014-" + "FORWARD-SIGNATURE-V1"
FORWARD_V2_SENTINEL = "EXECUTION-0014-" + "FORWARD-SIGNATURE-V2"
DETAIL_SENTINEL = "EXECUTION-0014-" + "DETAIL-SIGNATURE-MUST-STAY-EPHEMERAL"
FORWARD_VIDEO_V1 = f"{VIDEO_HINT}?auth_key={FORWARD_V1_SENTINEL}&quality=1080"
FORWARD_COVER_V1 = f"{COVER_HINT}?auth_key={FORWARD_V1_SENTINEL}&size=large"
FORWARD_VIDEO_V2 = f"{VIDEO_HINT}?auth_key={FORWARD_V2_SENTINEL}&quality=1080"
FORWARD_COVER_V2 = f"{COVER_HINT}?auth_key={FORWARD_V2_SENTINEL}&size=large"
DETAIL_VIDEO_URL = f"{VIDEO_HINT}?auth_key={DETAIL_SENTINEL}&quality=1080"
DETAIL_COVER_URL = f"{COVER_HINT}?auth_key={DETAIL_SENTINEL}&size=large"

MP4 = b"\x00\x00\x00\x18ftypisom" + b"execution-0014-offline-kuaishou-video"
PNG = b"\x89PNG\r\n\x1a\n" + b"execution-0014-offline-kuaishou-cover"
FORBIDDEN_VALUES = (
    FORWARD_V1_SENTINEL,
    FORWARD_V2_SENTINEL,
    DETAIL_SENTINEL,
    FORWARD_VIDEO_V1,
    FORWARD_COVER_V1,
    FORWARD_VIDEO_V2,
    FORWARD_COVER_V2,
    DETAIL_VIDEO_URL,
    DETAIL_COVER_URL,
)


def _jsonl(record: Mapping[str, object]) -> bytes:
    return (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _kuaishou_record(*, video_url: str, cover_url: str) -> dict[str, object]:
    return {
        "creator_hash": "untrusted-kuaishou-creator",
        "desc": "Execution 0014 ordinary Kuaishou video.",
        "nickname": "Untrusted nickname",
        "title": "Offline Kuaishou single video",
        "video_cover_url": cover_url,
        "video_id": CONTENT_ID,
        "video_play_url": video_url,
        "video_type": "1",
        "video_url": f"https://www.kuaishou.com/short-video/{CONTENT_ID}",
    }


FORWARD_JSONL_V1 = _jsonl(_kuaishou_record(video_url=FORWARD_VIDEO_V1, cover_url=FORWARD_COVER_V1))
FORWARD_JSONL_V2 = _jsonl(_kuaishou_record(video_url=FORWARD_VIDEO_V2, cover_url=FORWARD_COVER_V2))
DETAIL_JSONL = _jsonl(_kuaishou_record(video_url=DETAIL_VIDEO_URL, cover_url=DETAIL_COVER_URL))


def _normalization_context() -> NormalizationContext:
    return NormalizationContext(
        platform=Platform.KS,
        creator_remote_id=AUTHOR_REMOTE_ID,
        creator_display_name="Kuaishou Offline Creator",
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
            platform=Platform.KS.value,
            adapter="mediacrawler",
            display_name="execution-0014-offline-account",
            login_method=LoginMethod.QR.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=Platform.KS.value,
                remote_id=AUTHOR_REMOTE_ID,
                display_name="Kuaishou Offline Creator",
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
    worker_id: str,
    tmp_path: Path,
    runtime_root: Path,
    download_work_root: Path,
    archive_root: Path,
    http: SafeHttpClient,
    probe: _ControlledMp4Probe,
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
            worker_id=worker_id,
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


def _assert_ephemeral_values_absent(*roots: Path) -> None:
    forbidden = tuple(value.encode() for value in FORBIDDEN_VALUES)
    for root in roots:
        retained = {root.name: root.read_bytes()} if root.is_file() else _tree(root)
        for relative_path, payload in retained.items():
            assert all(value not in payload for value in forbidden), relative_path


def test_kuaishou_cover_is_optional_during_normalization() -> None:
    normalized = normalize_jsonl_bytes(
        _jsonl(_kuaishou_record(video_url=FORWARD_VIDEO_V1, cover_url="")),
        _normalization_context(),
    )

    assert not normalized.quarantined and not normalized.truncated_tail
    assert len(normalized.records) == 1
    assert [(asset.kind, asset.position) for asset in normalized.records[0].assets] == [(AssetKind.VIDEO, 0)]


def test_kuaishou_single_video_and_cover_reach_emby_without_persisting_signed_queries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "kuaishou-playable.sqlite3"
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
        normalized_v1 = normalize_jsonl_bytes(FORWARD_JSONL_V1, _normalization_context())
        assert not normalized_v1.quarantined and not normalized_v1.truncated_tail
        assert len(normalized_v1.records) == 1
        assert normalized_v1.records[0].author.remote_id == AUTHOR_REMOTE_ID
        discovered_assets = normalized_v1.records[0].assets
        assert [(asset.kind, asset.position, asset.remote_id) for asset in discovered_assets] == [
            (AssetKind.VIDEO, 0, VIDEO_REMOTE_ID),
            (AssetKind.COVER, 0, COVER_REMOTE_ID),
        ]
        assert [asset_source_hint(asset.source_url) for asset in discovered_assets] == [VIDEO_HINT, COVER_HINT]

        first_run_id = _start_ingesting_run(database, seed.subscription_id)
        first_ingest = MediaCrawlerIngestionService(database).ingest(
            normalized_v1.records,
            subscription_id=seed.subscription_id,
            run_id=first_run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )
        assert (first_ingest.accepted_count, first_ingest.discovered_count, first_ingest.asset_count) == (1, 1, 2)

        with database.session() as session:
            assets = {asset.kind: asset for asset in session.scalars(select(Asset)).all()}
            sources = {source.asset_id: source for source in session.scalars(select(AssetRefreshSource)).all()}
            assert set(assets) == {AssetKind.VIDEO.value, AssetKind.COVER.value}
            for kind, expected_remote_id, expected_hint in (
                (AssetKind.VIDEO, VIDEO_REMOTE_ID, VIDEO_HINT),
                (AssetKind.COVER, COVER_REMOTE_ID, COVER_HINT),
            ):
                asset = assets[kind.value]
                locator = parse_locator(asset.locator)
                assert isinstance(locator, AdapterRefreshLocator)
                assert locator.adapter == "mediacrawler"
                assert locator.asset_key == stable_asset_key(
                    platform=Platform.KS.value,
                    content_remote_type="content",
                    content_remote_id=CONTENT_ID,
                    kind=kind.value,
                    position=0,
                    remote_id=expected_remote_id,
                )
                assert (asset.remote_id, asset.position, asset.generation, asset.source_url) == (
                    expected_remote_id,
                    0,
                    1,
                    expected_hint,
                )
                source = sources[asset.id]
                assert source.subscription_id == seed.subscription_id
                assert source.last_run_id == first_run_id
                assert source.observation_kind == "ingested"
                assert source.observed_generation == 1
                assert source.observed_semantic_fingerprint == asset.semantic_fingerprint
                assert source.observed_locator_fingerprint == asset.locator_fingerprint
            asset_ids = {kind: UUID(asset.id) for kind, asset in assets.items()}

        resolver = _RecordingPublicResolver()
        targets: list[ValidatedTarget] = []
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            assert set(request.headers) == {"accept", "accept-encoding", "connection", "host", "user-agent"}
            assert request.headers["accept-encoding"] == "identity"
            assert not request.headers["user-agent"].startswith("Mozilla/5.0")
            assert "cookie" not in request.headers
            assert "authorization" not in request.headers
            assert "referer" not in request.headers
            assert "origin" not in request.headers
            if str(request.url) == DETAIL_VIDEO_URL:
                assert request.headers["host"] == "video.example.test"
                return httpx.Response(
                    200,
                    headers={
                        "Content-Length": str(len(MP4)),
                        "Content-Type": "video/mp4",
                        "ETag": '"execution-0014-video-v1"',
                    },
                    content=MP4,
                )
            if str(request.url) == DETAIL_COVER_URL:
                assert request.headers["host"] == "image.example.test"
                return httpx.Response(
                    200,
                    headers={
                        "Content-Length": str(len(PNG)),
                        "Content-Type": "image/png",
                        "ETag": '"execution-0014-cover-v1"',
                    },
                    content=PNG,
                )
            raise AssertionError("unexpected Kuaishou media URL")

        def transport_factory(target: ValidatedTarget) -> httpx.BaseTransport:
            targets.append(target)
            return httpx.MockTransport(handler)

        probe = _ControlledMp4Probe()
        http = SafeHttpClient(resolver, transport_factory=transport_factory)
        video_harness = _download_harness(
            database,
            asset_id=asset_ids[AssetKind.VIDEO.value],
            subscription_id=UUID(seed.subscription_id),
            worker_id="execution-0014-video-download",
            tmp_path=tmp_path,
            runtime_root=runtime_root,
            download_work_root=download_work_root,
            archive_root=archive_root,
            http=http,
            probe=probe,
        )
        cover_harness = _download_harness(
            database,
            asset_id=asset_ids[AssetKind.COVER.value],
            subscription_id=UUID(seed.subscription_id),
            worker_id="execution-0014-cover-download",
            tmp_path=tmp_path,
            runtime_root=runtime_root,
            download_work_root=download_work_root,
            archive_root=archive_root,
            http=http,
            probe=probe,
        )

        first_video = video_harness.service.run(video_harness.request)
        first_cover = cover_harness.service.run(cover_harness.request)
        video_checksum = hashlib.sha256(MP4).hexdigest()
        cover_checksum = hashlib.sha256(PNG).hexdigest()
        expected_video_archive = archive_root / "sha256" / video_checksum[:2] / f"{video_checksum}.mp4"
        expected_cover_archive = archive_root / "sha256" / cover_checksum[:2] / f"{cover_checksum}.png"

        assert first_video.disposition == first_cover.disposition == "downloaded"
        assert (first_video.archive_path, first_video.checksum_sha256, first_video.mime_type) == (
            expected_video_archive.absolute(),
            video_checksum,
            "video/mp4",
        )
        assert (first_cover.archive_path, first_cover.checksum_sha256, first_cover.mime_type) == (
            expected_cover_archive.absolute(),
            cover_checksum,
            "image/png",
        )
        assert expected_video_archive.read_bytes() == MP4
        assert expected_cover_archive.read_bytes() == PNG
        assert len(probe.calls) == 1
        assert resolver.calls == [("video.example.test", 443), ("image.example.test", 443)]
        assert [target.address for target in targets] == ["8.8.8.8", "8.8.8.8"]
        assert len(requests) == 2
        assert video_harness.refresher.results[0].url == DETAIL_VIDEO_URL
        assert cover_harness.refresher.results[0].url == DETAIL_COVER_URL
        assert all(
            result.request_profile is MediaRequestProfile.DEFAULT
            for result in video_harness.refresher.results + cover_harness.refresher.results
        )
        assert all(DETAIL_SENTINEL not in repr(result) for result in video_harness.refresher.results)
        assert all(DETAIL_SENTINEL not in repr(result) for result in cover_harness.refresher.results)

        assert len(_FakeDetailRunner.instances) == 2
        first_detail_instances = tuple(_FakeDetailRunner.instances)
        first_detail_calls = tuple(call for runner in first_detail_instances for call in runner.calls)
        assert len(first_detail_instances) == 2
        assert len(first_detail_calls) == 2
        expected_runner_kwargs = {
            "integration_root": runtime_root,
            "license_acknowledged": True,
            "lock_path": tmp_path / "upstreams.lock.json",
            "python_executable": tmp_path / "python",
        }
        assert all(runner.constructor_kwargs == expected_runner_kwargs for runner in first_detail_instances)
        for detail_request in first_detail_calls:
            assert detail_request.account_id == UUID(seed.account_id)
            assert detail_request.platform is Platform.KS
            assert detail_request.login_method is LoginMethod.QR
            assert detail_request.content_remote_id == CONTENT_ID
            assert detail_request.subscription_id == UUID(seed.subscription_id)
            assert detail_request.bili_progressive_detail is False
            assert DETAIL_SENTINEL not in repr(detail_request)
        assert DETAIL_SENTINEL not in repr(MediaCrawlerDetailResult(DETAIL_JSONL, UPSTREAM_SHA))

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        first_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0014-export", lease_seconds=60)
        )
        assert first_export.already_exported is False
        author_directory = library_root / first_export.output_path
        exported_video = next(author_directory.glob("Season */*.mp4"))
        exported_poster = next(author_directory.glob("Season */*-poster.png"))
        assert exported_video.read_bytes() == MP4
        assert exported_poster.read_bytes() == PNG
        assert (author_directory / "tvshow.nfo").is_file()
        episode_nfo = next(author_directory.glob("Season */*.nfo"))
        assert CONTENT_ID.encode() in episode_nfo.read_bytes()
        assert (author_directory / ".media-sync-managed-v1.json").is_file()
        source_path = next(author_directory.glob("Season */*.assets/source.json"))
        source_document = json.loads(source_path.read_text("utf-8"))
        assert source_document["platform"] == Platform.KS.value
        assert source_document["remote_id"] == CONTENT_ID
        assert {asset["kind"] for asset in source_document["assets"]} == {
            AssetKind.VIDEO.value,
            AssetKind.COVER.value,
        }
        assert not {"canonical_url", "locator", "raw", "source_url"} & source_document.keys()

        first_archive_tree = _tree(archive_root)
        first_library_tree = _tree(author_directory)
        _assert_ephemeral_values_absent(
            runtime_root,
            download_work_root,
            archive_root,
            export_work_root,
            library_root,
        )

        normalized_v2 = normalize_jsonl_bytes(FORWARD_JSONL_V2, _normalization_context())
        assert not normalized_v2.quarantined and not normalized_v2.truncated_tail
        second_run_id = _start_ingesting_run(database, seed.subscription_id)
        second_ingest = MediaCrawlerIngestionService(database).ingest(
            normalized_v2.records,
            subscription_id=seed.subscription_id,
            run_id=second_run_id,
            expected_revision=1,
            mode=IngestionMode.FORWARD,
        )
        assert (second_ingest.accepted_count, second_ingest.discovered_count, second_ingest.asset_count) == (1, 0, 0)
        assert second_ingest.checkpoint_revision == 2

        second_video = video_harness.service.run(video_harness.request)
        second_cover = cover_harness.service.run(cover_harness.request)
        second_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0014-export-replay", lease_seconds=60)
        )

        assert second_video.disposition == second_cover.disposition == "already_verified"
        assert second_video.job_id == first_video.job_id
        assert second_cover.job_id == first_cover.job_id
        assert second_video.archive_path == first_video.archive_path
        assert second_cover.archive_path == first_cover.archive_path
        assert second_export.already_exported is True
        assert second_export.job_id == first_export.job_id
        assert second_export.source_fingerprint == first_export.source_fingerprint
        assert second_export.rendered_fingerprint == first_export.rendered_fingerprint
        replay_detail_instances = tuple(_FakeDetailRunner.instances)
        replay_detail_calls = tuple(call for runner in replay_detail_instances for call in runner.calls)
        assert replay_detail_instances == first_detail_instances
        assert replay_detail_calls == first_detail_calls
        assert len(requests) == len(targets) == len(resolver.calls) == len(replay_detail_calls) == 2
        assert len(probe.calls) == 1
        assert _tree(archive_root) == first_archive_tree
        assert _tree(author_directory) == first_library_tree

        with database.session() as session:
            final_assets = {asset.kind: asset for asset in session.scalars(select(Asset)).all()}
            final_content = session.scalar(select(Content))
            final_sources = list(session.scalars(select(AssetRefreshSource)).all())
            subscription = session.get(Subscription, seed.subscription_id)
            jobs = list(session.scalars(select(Job).order_by(Job.job_type, Job.natural_key)).all())
            runs = list(session.scalars(select(SyncRun).order_by(SyncRun.created_at)).all())
            exports = list(session.scalars(select(ExportRecord)).all())
            assert final_content is not None and subscription is not None
            assert set(final_assets) == {AssetKind.VIDEO.value, AssetKind.COVER.value}
            assert all(asset.status == "verified" and asset.generation == 1 for asset in final_assets.values())
            assert final_assets[AssetKind.VIDEO.value].source_url == VIDEO_HINT
            assert final_assets[AssetKind.COVER.value].source_url == COVER_HINT
            assert final_assets[AssetKind.VIDEO.value].local_path == str(expected_video_archive.absolute())
            assert final_assets[AssetKind.COVER.value].local_path == str(expected_cover_archive.absolute())
            assert final_assets[AssetKind.VIDEO.value].checksum_sha256 == video_checksum
            assert final_assets[AssetKind.COVER.value].checksum_sha256 == cover_checksum
            assert final_assets[AssetKind.VIDEO.value].mime_type == "video/mp4"
            assert final_assets[AssetKind.COVER.value].mime_type == "image/png"
            assert all(
                isinstance(parse_locator(asset.locator), AdapterRefreshLocator) for asset in final_assets.values()
            )
            assert len(final_sources) == 2
            assert all(
                source.last_run_id == second_run_id and source.observed_generation == 1 for source in final_sources
            )
            assert subscription.checkpoint_revision == 2
            assert [run.status for run in runs] == ["succeeded", "succeeded"]
            assert [job.job_type for job in jobs].count("asset_download") == 2
            assert [job.job_type for job in jobs].count("export.emby") == 1
            assert all(job.status == "succeeded" and job.attempts == 1 for job in jobs)
            assert len(exports) == 1 and exports[0].status == "succeeded"
            durable_json = json.dumps(
                {
                    "assets": [
                        {"locator": asset.locator, "raw": asset.raw, "source_url": asset.source_url}
                        for asset in final_assets.values()
                    ],
                    "content": {"canonical_url": final_content.canonical_url, "raw": final_content.raw},
                    "jobs": [job.payload for job in jobs],
                    "runs": [run.manifest for run in runs],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            assert all(value not in durable_json for value in FORBIDDEN_VALUES)

        _assert_ephemeral_values_absent(
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
    _assert_ephemeral_values_absent(*sqlite_artifacts)
