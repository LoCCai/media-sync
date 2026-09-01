"""Offline Zhihu ordinary-answer-image-to-Emby qualification."""

from __future__ import annotations

import hashlib
import json
from base64 import b64decode
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
from media_sync.infrastructure.db.models import Asset, AssetRefreshSource, Content, ExportRecord, Job, SyncRun
from media_sync.integrations.mediacrawler import MediaCrawlerDetailRequest, MediaCrawlerDetailResult
from media_sync.integrations.mediacrawler.normalizers import NormalizationContext, normalize_jsonl_bytes
from media_sync.integrations.mediacrawler.zhihu_media import ZHIHU_IMAGE_FIELD
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

FIXED_AT = datetime(2026, 9, 1, 12, 34, 56, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
AUTHOR_REMOTE_ID = "execution-0019-zhihu-creator"
QUESTION_ID = "826896610"
CONTENT_ID = "4885821440"
ASSET_REMOTE_ID = f"{CONTENT_ID}:image:0"
CANONICAL_URL = f"https://www.zhihu.com/question/{QUESTION_ID}/answer/{CONTENT_ID}"
IMAGE_HINT = "https://pic1.zhimg.com/v2-execution-0019-answer.png"
DISCOVERY_V1_SIGNATURE = "EXECUTION0019DISCOVERYV1PRIVATE"
DISCOVERY_V2_SIGNATURE = "EXECUTION0019DISCOVERYV2PRIVATE"
REFRESH_SIGNATURE = "EXECUTION0019REFRESHPRIVATE"
NESTED_SIGNATURE = "EXECUTION0019NESTEDPRIVATE"
DISCOVERY_IMAGE_V1 = f"{IMAGE_HINT}?source={DISCOVERY_V1_SIGNATURE}"
DISCOVERY_IMAGE_V2 = f"{IMAGE_HINT}?source={DISCOVERY_V2_SIGNATURE}"
REFRESH_IMAGE = f"{IMAGE_HINT}?source={REFRESH_SIGNATURE}"
PNG = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
FORBIDDEN_VALUES = (
    ZHIHU_IMAGE_FIELD,
    DISCOVERY_V1_SIGNATURE,
    DISCOVERY_V2_SIGNATURE,
    REFRESH_SIGNATURE,
    NESTED_SIGNATURE,
    DISCOVERY_IMAGE_V1,
    DISCOVERY_IMAGE_V2,
    REFRESH_IMAGE,
    "?source=",
)


def _jsonl(record: Mapping[str, object]) -> bytes:
    return (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _answer_record(image_url: str) -> dict[str, object]:
    return {
        "content_id": CONTENT_ID,
        "content_type": "answer",
        "content_text": "Execution 0019 ordinary Zhihu answer with one static image.",
        "content_url": CANONICAL_URL,
        "question_id": QUESTION_ID,
        "title": "Execution 0019 Zhihu answer image",
        "desc": "Source-bound offline fixture",
        "created_time": 1788235200,
        "updated_time": 1788235260,
        "voteup_count": 19,
        "comment_count": 1,
        "creator_hash": "untrusted-creator-hash",
        "user_nickname": "Untrusted nickname",
        "last_modify_ts": 1788235320,
        ZHIHU_IMAGE_FIELD: image_url,
        "future_private_shape": {ZHIHU_IMAGE_FIELD: f"https://pic2.zhimg.com/nested.png?source={NESTED_SIGNATURE}"},
    }


DISCOVERY_JSONL_V1 = _jsonl(_answer_record(DISCOVERY_IMAGE_V1))
DISCOVERY_JSONL_V2 = _jsonl(_answer_record(DISCOVERY_IMAGE_V2))
DETAIL_JSONL = _jsonl(_answer_record(REFRESH_IMAGE))


def _normalization_context() -> NormalizationContext:
    return NormalizationContext(
        platform=Platform.ZHIHU,
        creator_remote_id=AUTHOR_REMOTE_ID,
        creator_display_name="Zhihu Offline Creator",
        upstream_sha=UPSTREAM_SHA,
        ingested_at=FIXED_AT,
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
    account_id: str
    author_id: str
    subscription_id: str


def _seed_subscription(database: Database) -> _Seed:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=Platform.ZHIHU.value,
            adapter="mediacrawler",
            display_name="execution-0019-offline-account",
            login_method=LoginMethod.QR.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=Platform.ZHIHU.value,
                remote_id=AUTHOR_REMOTE_ID,
                display_name="Zhihu Offline Creator",
            ),
            seen_at=FIXED_AT,
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            policy=_policy(),
            max_items=3,
        )
        return _Seed(account.id, author.id, subscription.id)


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


class _UnexpectedStructuralProbe:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    def probe(self, path: Path, *, timeout_seconds: float, max_output_bytes: int) -> ProbeResult:
        self.calls.append(path)
        raise AssertionError("a sniffed PNG must not invoke the structural media probe")


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
        retained = (
            {
                path.name: path.read_bytes()
                for path in sorted(root.parent.glob(f"{root.name}*"), key=lambda item: item.name)
                if path.is_file()
            }
            if root.is_file()
            else _tree(root)
        )
        for relative_path, payload in retained.items():
            assert all(value not in payload for value in forbidden), relative_path


def test_zhihu_answer_image_reaches_emby_and_query_only_replay_does_no_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "zhihu-answer-image.sqlite3"
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
        normalized = normalize_jsonl_bytes(DISCOVERY_JSONL_V1, _normalization_context())
        assert not normalized.quarantined and not normalized.truncated_tail
        assert len(normalized.records) == 1
        record = normalized.records[0]
        assert record.content.kind is ContentKind.ARTICLE
        assert record.content.canonical_url == CANONICAL_URL
        assert ZHIHU_IMAGE_FIELD not in repr(record.content.raw)
        assert [(asset.kind, asset.position, asset.remote_id) for asset in record.assets] == [
            (AssetKind.IMAGE, 0, ASSET_REMOTE_ID)
        ]
        assert record.assets[0].source_url == DISCOVERY_IMAGE_V1
        assert asset_source_hint(record.assets[0].source_url) == IMAGE_HINT

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
            asset = session.scalars(select(Asset)).one()
            source = session.scalars(select(AssetRefreshSource)).one()
            content = session.scalars(select(Content)).one()
            locator = parse_locator(asset.locator)
            assert isinstance(locator, AdapterRefreshLocator)
            assert locator.asset_key == stable_asset_key(
                platform=Platform.ZHIHU.value,
                content_remote_type="content",
                content_remote_id=CONTENT_ID,
                kind=AssetKind.IMAGE.value,
                position=0,
                remote_id=ASSET_REMOTE_ID,
            )
            assert (asset.remote_id, asset.position, asset.generation, asset.source_url) == (
                ASSET_REMOTE_ID,
                0,
                1,
                IMAGE_HINT,
            )
            assert content.canonical_url == CANONICAL_URL
            assert source.subscription_id == seed.subscription_id
            assert source.last_run_id == first_run_id
            assert source.observed_generation == 1
            asset_id = UUID(asset.id)

        resolver = _RecordingPublicResolver()
        targets: list[ValidatedTarget] = []
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            assert str(request.url) == REFRESH_IMAGE
            assert set(request.headers) == {"accept", "accept-encoding", "connection", "host", "user-agent"}
            assert request.headers["accept-encoding"] == "identity"
            assert request.headers["host"] == "pic1.zhimg.com"
            assert not request.headers["user-agent"].startswith("Mozilla/5.0")
            assert not {"cookie", "authorization", "referer", "origin"} & set(request.headers)
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(PNG)),
                    "Content-Type": "image/png",
                    "ETag": '"execution-0019-image-v1"',
                },
                content=PNG,
            )

        def transport_factory(target: ValidatedTarget) -> httpx.BaseTransport:
            targets.append(target)
            return httpx.MockTransport(handler)

        probe = _UnexpectedStructuralProbe()
        http = SafeHttpClient(resolver, transport_factory=transport_factory)
        lazy = LazyMediaCrawlerLocatorRefresher(
            database,
            asset_id=asset_id,
            subscription_id=UUID(seed.subscription_id),
            lock_path=tmp_path / "upstreams.lock.json",
            integration_root=runtime_root,
            python_executable=tmp_path / "python",
            secret_resolver=SecretResolver({}),
            license_acknowledged=True,
        )
        refresher = _RecordingRefresher(lazy)
        download_service = AssetDownloadService(
            database,
            SecureMediaDownloader(http, refresher=refresher, probe=probe),
            clock=lambda: FIXED_AT,
        )
        download_request = AssetDownloadRequest(
            asset_id=asset_id,
            worker_id="execution-0019-image-download",
            work_root=download_work_root,
            archive_root=archive_root,
            lease_seconds=60,
        )
        first_download = download_service.run(download_request)
        checksum = hashlib.sha256(PNG).hexdigest()
        expected_archive = archive_root / "sha256" / checksum[:2] / f"{checksum}.png"
        assert first_download.disposition == "downloaded"
        assert (first_download.archive_path, first_download.checksum_sha256, first_download.mime_type) == (
            expected_archive.absolute(),
            checksum,
            "image/png",
        )
        assert expected_archive.read_bytes() == PNG
        assert probe.calls == []
        assert resolver.calls == [("pic1.zhimg.com", 443)]
        assert [target.address for target in targets] == ["8.8.8.8"]
        assert [str(request.url) for request in requests] == [REFRESH_IMAGE]
        assert refresher.results == [ResolvedLocator(REFRESH_IMAGE, MediaRequestProfile.DEFAULT)]

        assert len(_FakeDetailRunner.instances) == 1
        detail_instance = _FakeDetailRunner.instances[0]
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
        assert detail_request.platform is Platform.ZHIHU
        assert detail_request.login_method is LoginMethod.QR
        assert detail_request.content_remote_id == CONTENT_ID
        assert detail_request.resolved_detail_reference() == CANONICAL_URL
        assert detail_request.creator_reference is None
        assert detail_request.creator_max_items is None

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        first_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0019-export", lease_seconds=60)
        )
        assert first_export.already_exported is False
        author_directory = library_root / first_export.output_path
        poster = next(author_directory.glob("Season */*-poster.png"))
        backdrop = next(author_directory.glob("Season */*-backdrop.png"))
        gallery = next(author_directory.glob("Season */*.assets/gallery-*.png"))
        assert poster.read_bytes() == backdrop.read_bytes() == gallery.read_bytes() == PNG
        body = next(author_directory.glob("Season */*.assets/body.txt"))
        assert b"ordinary Zhihu answer" in body.read_bytes()
        episode_nfo = next(author_directory.glob("Season */*.nfo"))
        assert CONTENT_ID.encode() in episode_nfo.read_bytes()
        source_path = next(author_directory.glob("Season */*.assets/source.json"))
        source_document = json.loads(source_path.read_text("utf-8"))
        assert source_document["platform"] == Platform.ZHIHU.value
        assert source_document["remote_id"] == CONTENT_ID
        assert [
            (item["kind"], item["position"], item["remote_id"], item["checksum_sha256"])
            for item in source_document["assets"]
        ] == [(AssetKind.IMAGE.value, 0, ASSET_REMOTE_ID, checksum)]
        assert not {"canonical_url", "locator", "raw", "source_url"} & source_document.keys()

        first_archive_tree = _tree(archive_root)
        first_library_tree = _tree(author_directory)
        _assert_private_values_absent(
            database_path,
            runtime_root,
            download_work_root,
            archive_root,
            export_work_root,
            library_root,
        )

        replay = normalize_jsonl_bytes(DISCOVERY_JSONL_V2, _normalization_context())
        assert not replay.quarantined
        second_run_id = _start_ingesting_run(database, seed.subscription_id)
        second_ingest = MediaCrawlerIngestionService(database).ingest(
            replay.records,
            subscription_id=seed.subscription_id,
            run_id=second_run_id,
            expected_revision=1,
            mode=IngestionMode.FORWARD,
        )
        assert (second_ingest.accepted_count, second_ingest.discovered_count, second_ingest.asset_count) == (0, 0, 0)
        assert second_ingest.checkpoint_revision == 2

        replay_download = download_service.run(download_request)
        replay_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0019-export-replay", lease_seconds=60)
        )
        assert replay_download.disposition == "already_verified"
        assert replay_download.job_id == first_download.job_id
        assert replay_export.already_exported is True
        assert replay_export.job_id == first_export.job_id
        assert len(_FakeDetailRunner.instances) == len(requests) == len(targets) == 1
        assert resolver.calls == [("pic1.zhimg.com", 443)]
        assert probe.calls == []
        assert _tree(archive_root) == first_archive_tree
        assert _tree(author_directory) == first_library_tree

        with database.session() as session:
            final_asset = session.scalars(select(Asset)).one()
            final_content = session.scalars(select(Content)).one()
            jobs = list(session.scalars(select(Job).order_by(Job.job_type, Job.natural_key)).all())
            runs = list(session.scalars(select(SyncRun).order_by(SyncRun.created_at)).all())
            exports = list(session.scalars(select(ExportRecord)).all())
            assert final_asset.status == "verified" and final_asset.generation == 1
            assert final_asset.source_url == IMAGE_HINT
            assert final_asset.local_path == str(expected_archive.absolute())
            assert final_asset.checksum_sha256 == checksum
            assert final_content.canonical_url == CANONICAL_URL
            assert [run.status for run in runs] == ["succeeded", "succeeded"]
            assert [job.job_type for job in jobs].count("asset_download") == 1
            assert [job.job_type for job in jobs].count("export.emby") == 1
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
            assert all(value not in durable_json for value in FORBIDDEN_VALUES)

        _assert_private_values_absent(
            database_path,
            runtime_root,
            download_work_root,
            archive_root,
            export_work_root,
            library_root,
        )
    finally:
        database.dispose()
