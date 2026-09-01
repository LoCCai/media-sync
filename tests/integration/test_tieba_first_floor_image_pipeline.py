"""Offline Tieba ordinary first-floor image/gallery-to-Emby qualification."""

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
from media_sync.integrations.mediacrawler.tieba_media import TIEBA_IMAGE_FIELD, TIEBA_IMAGES_FIELD
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

FIXED_AT = datetime(2026, 9, 2, 12, 34, 56, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
AUTHOR_REMOTE_ID = "execution-0020-tieba-creator"
CONTENT_ID = "10376710029"
ASSET_REMOTE_ID = f"{CONTENT_ID}:image:0"
CANONICAL_URL = f"https://tieba.baidu.com/p/{CONTENT_ID}"
IMAGE_ID = "489c9a3df8dcd1009420153b348b4710b8122fc3"
IMAGE_HINT = f"https://tiebapic.baidu.com/forum/pic/item/{IMAGE_ID}.jpg"
SECOND_IMAGE_ID = "0123456789abcdef0123456789abcdef01234567"
SECOND_IMAGE_HINT = f"https://tiebapic.baidu.com/forum/pic/item/{SECOND_IMAGE_ID}.png"
DISCOVERY_V1_TOKEN = "2026-09-02-17_EXECUTION0020DISCOVERYV1PRIVATE"
DISCOVERY_V2_TOKEN = "2026-09-02-17_EXECUTION0020DISCOVERYV2PRIVATE"
REFRESH_TOKEN = "2026-09-02-17_EXECUTION0020REFRESHPRIVATE"
NESTED_TOKEN = "2026-09-02-17_EXECUTION0020NESTEDPRIVATE"
DOUBLE_DISCOVERY_V1_TOKENS = (
    "2026-09-02-17_EXECUTION0021DISCOVERYV1POSITION0PRIVATE",
    "2026-09-02-17_EXECUTION0021DISCOVERYV1POSITION1PRIVATE",
)
DOUBLE_DISCOVERY_V2_TOKENS = (
    "2026-09-02-17_EXECUTION0021DISCOVERYV2POSITION0PRIVATE",
    "2026-09-02-17_EXECUTION0021DISCOVERYV2POSITION1PRIVATE",
)
DOUBLE_REFRESH_TOKENS = (
    "2026-09-02-17_EXECUTION0021REFRESHPOSITION0PRIVATE",
    "2026-09-02-17_EXECUTION0021REFRESHPOSITION1PRIVATE",
)
DOUBLE_NESTED_TOKEN = "2026-09-02-17_EXECUTION0021NESTEDPRIVATE"
DISCOVERY_IMAGE_V1 = f"{IMAGE_HINT}?tbpicau={DISCOVERY_V1_TOKEN}"
DISCOVERY_IMAGE_V2 = f"{IMAGE_HINT}?tbpicau={DISCOVERY_V2_TOKEN}"
REFRESH_IMAGE = f"{IMAGE_HINT}?tbpicau={REFRESH_TOKEN}"
JPEG = b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAx"
    "NDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    "MjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBA"
    "QAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1"
    "hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+"
    "Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEE"
    "BSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hp"
    "anN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP"
    "09fb3+Pn6/9oADAMBAAIRAxEAPwDi6KKK+ZP3E//Z"
)
PNG = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
DOUBLE_IMAGE_HINTS = (IMAGE_HINT, SECOND_IMAGE_HINT)
DOUBLE_ASSET_REMOTE_IDS = tuple(f"{CONTENT_ID}:image:{position}" for position in range(2))
DOUBLE_DISCOVERY_IMAGES_V1 = tuple(
    f"{hint}?tbpicau={token}" for hint, token in zip(DOUBLE_IMAGE_HINTS, DOUBLE_DISCOVERY_V1_TOKENS, strict=True)
)
DOUBLE_DISCOVERY_IMAGES_V2 = tuple(
    f"{hint}?tbpicau={token}" for hint, token in zip(DOUBLE_IMAGE_HINTS, DOUBLE_DISCOVERY_V2_TOKENS, strict=True)
)
DOUBLE_REFRESH_IMAGES = tuple(
    f"{hint}?tbpicau={token}" for hint, token in zip(DOUBLE_IMAGE_HINTS, DOUBLE_REFRESH_TOKENS, strict=True)
)
DOUBLE_IMAGE_BYTES = (JPEG, PNG)
FORBIDDEN_VALUES = (
    TIEBA_IMAGE_FIELD,
    TIEBA_IMAGES_FIELD,
    DISCOVERY_V1_TOKEN,
    DISCOVERY_V2_TOKEN,
    REFRESH_TOKEN,
    NESTED_TOKEN,
    DISCOVERY_IMAGE_V1,
    DISCOVERY_IMAGE_V2,
    REFRESH_IMAGE,
    *DOUBLE_DISCOVERY_V1_TOKENS,
    *DOUBLE_DISCOVERY_V2_TOKENS,
    *DOUBLE_REFRESH_TOKENS,
    DOUBLE_NESTED_TOKEN,
    *DOUBLE_DISCOVERY_IMAGES_V1,
    *DOUBLE_DISCOVERY_IMAGES_V2,
    *DOUBLE_REFRESH_IMAGES,
    "tbpicau=",
)


def _jsonl(record: Mapping[str, object]) -> bytes:
    return (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _thread_record(image_url: str) -> dict[str, object]:
    return {
        "note_id": CONTENT_ID,
        "title": "Execution 0020 Tieba first-floor image",
        "desc": "Execution 0020 ordinary Tieba first floor with one static image.",
        "note_url": CANONICAL_URL,
        "publish_time": "2026-09-02 20:00:00",
        "creator_hash": "untrusted-creator-hash",
        "user_nickname": "Untrusted nickname",
        "tieba_name": "测试吧",
        "tieba_link": "https://tieba.baidu.com/f?kw=test",
        "total_replay_num": 20,
        "total_replay_page": 1,
        "source_keyword": "fixture",
        "last_modify_ts": 1788350520,
        TIEBA_IMAGE_FIELD: image_url,
        "future_private_shape": {
            TIEBA_IMAGE_FIELD: f"{IMAGE_HINT}?tbpicau={NESTED_TOKEN}",
        },
    }


def _two_image_thread_record(image_urls: tuple[str, str]) -> dict[str, object]:
    return {
        "note_id": CONTENT_ID,
        "title": "Execution 0021 Tieba first-floor two-image gallery",
        "desc": "Execution 0021 ordinary Tieba first floor with exactly two ordered static images.",
        "note_url": CANONICAL_URL,
        "publish_time": "2026-09-02 20:21:00",
        "creator_hash": "untrusted-creator-hash",
        "user_nickname": "Untrusted nickname",
        "tieba_name": "测试吧",
        "tieba_link": "https://tieba.baidu.com/f?kw=test",
        "total_replay_num": 21,
        "total_replay_page": 2,
        "source_keyword": "fixture",
        "last_modify_ts": 1788351660,
        TIEBA_IMAGES_FIELD: list(image_urls),
        "future_private_shape": {
            TIEBA_IMAGES_FIELD: [
                f"{IMAGE_HINT}?tbpicau={DOUBLE_NESTED_TOKEN}",
                f"{SECOND_IMAGE_HINT}?tbpicau={DOUBLE_NESTED_TOKEN}",
            ],
        },
    }


DISCOVERY_JSONL_V1 = _jsonl(_thread_record(DISCOVERY_IMAGE_V1))
DISCOVERY_JSONL_V2 = _jsonl(_thread_record(DISCOVERY_IMAGE_V2))
DETAIL_JSONL = _jsonl(_thread_record(REFRESH_IMAGE))
DOUBLE_DISCOVERY_JSONL_V1 = _jsonl(_two_image_thread_record(DOUBLE_DISCOVERY_IMAGES_V1))
DOUBLE_DISCOVERY_JSONL_V2 = _jsonl(_two_image_thread_record(DOUBLE_DISCOVERY_IMAGES_V2))
DOUBLE_DETAIL_JSONL = _jsonl(_two_image_thread_record(DOUBLE_REFRESH_IMAGES))


def _normalization_context() -> NormalizationContext:
    return NormalizationContext(
        platform=Platform.TIEBA,
        creator_remote_id=AUTHOR_REMOTE_ID,
        creator_display_name="Tieba Offline Creator",
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
            platform=Platform.TIEBA.value,
            adapter="mediacrawler",
            display_name="execution-0020-offline-account",
            login_method=LoginMethod.QR.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=Platform.TIEBA.value,
                remote_id=AUTHOR_REMOTE_ID,
                display_name="Tieba Offline Creator",
            ),
            seen_at=FIXED_AT,
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            policy=_policy(),
            max_items=23,
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


class _TwoImageDetailRunner:
    instances: ClassVar[list[_TwoImageDetailRunner]] = []

    def __init__(self, **kwargs: object) -> None:
        self.constructor_kwargs = kwargs
        self.calls: list[MediaCrawlerDetailRequest] = []
        type(self).instances.append(self)

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        self.calls.append(request)
        return MediaCrawlerDetailResult(DOUBLE_DETAIL_JSONL, UPSTREAM_SHA)


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
        raise AssertionError("a qualified static Tieba image must not invoke the structural media probe")


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


def test_tieba_first_floor_image_reaches_emby_and_query_only_replay_does_no_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "tieba-first-floor-image.sqlite3"
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
        assert TIEBA_IMAGE_FIELD not in repr(record.content.raw)
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
                platform=Platform.TIEBA.value,
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
            assert request.headers["host"] == "tiebapic.baidu.com"
            assert not request.headers["user-agent"].startswith("Mozilla/5.0")
            assert not {"cookie", "authorization", "referer", "origin"} & set(request.headers)
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(JPEG)),
                    "Content-Type": "image/jpeg",
                    "ETag": '"execution-0020-image-v1"',
                },
                content=JPEG,
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
            worker_id="execution-0020-image-download",
            work_root=download_work_root,
            archive_root=archive_root,
            lease_seconds=60,
        )
        first_download = download_service.run(download_request)
        checksum = hashlib.sha256(JPEG).hexdigest()
        expected_archive = archive_root / "sha256" / checksum[:2] / f"{checksum}.jpg"
        assert first_download.disposition == "downloaded"
        assert (first_download.archive_path, first_download.checksum_sha256, first_download.mime_type) == (
            expected_archive.absolute(),
            checksum,
            "image/jpeg",
        )
        assert expected_archive.read_bytes() == JPEG
        assert probe.calls == []
        assert resolver.calls == [("tiebapic.baidu.com", 443)]
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
        assert detail_request.platform is Platform.TIEBA
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
            EmbyExportRequest(seed.author_id, "execution-0020-export", lease_seconds=60)
        )
        assert first_export.already_exported is False
        author_directory = library_root / first_export.output_path
        poster = next(author_directory.glob("Season */*-poster.jpg"))
        backdrop = next(author_directory.glob("Season */*-backdrop.jpg"))
        gallery = next(author_directory.glob("Season */*.assets/gallery-*.jpg"))
        assert poster.read_bytes() == backdrop.read_bytes() == gallery.read_bytes() == JPEG
        body = next(author_directory.glob("Season */*.assets/body.txt"))
        assert b"ordinary Tieba first floor" in body.read_bytes()
        episode_nfo = next(author_directory.glob("Season */*.nfo"))
        assert CONTENT_ID.encode() in episode_nfo.read_bytes()
        source_path = next(author_directory.glob("Season */*.assets/source.json"))
        source_document = json.loads(source_path.read_text("utf-8"))
        assert source_document["platform"] == Platform.TIEBA.value
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
            EmbyExportRequest(seed.author_id, "execution-0020-export-replay", lease_seconds=60)
        )
        assert replay_download.disposition == "already_verified"
        assert replay_download.job_id == first_download.job_id
        assert replay_export.already_exported is True
        assert replay_export.job_id == first_export.job_id
        assert len(_FakeDetailRunner.instances) == len(requests) == len(targets) == 1
        assert resolver.calls == [("tiebapic.baidu.com", 443)]
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


def test_tieba_first_floor_two_image_gallery_reaches_emby_and_query_only_replay_does_no_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "tieba-first-floor-two-image.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    archive_root = tmp_path / "archive"
    library_root = tmp_path / "library"
    runtime_root = tmp_path / "mediacrawler-runtime"
    download_work_root = tmp_path / "download-work"
    export_work_root = tmp_path / "export-work"
    runtime_root.mkdir()
    upgrade_database(database_url)
    database = Database(database_url)
    _TwoImageDetailRunner.instances = []
    monkeypatch.setattr(mediacrawler_runtime, "MediaCrawlerDetailProcessRunner", _TwoImageDetailRunner)

    try:
        seed = _seed_subscription(database)
        normalized = normalize_jsonl_bytes(DOUBLE_DISCOVERY_JSONL_V1, _normalization_context())
        assert not normalized.quarantined and not normalized.truncated_tail
        assert len(normalized.records) == 1
        record = normalized.records[0]
        assert record.content.kind is ContentKind.ARTICLE
        assert record.content.canonical_url == CANONICAL_URL
        assert TIEBA_IMAGE_FIELD not in repr(record.content.raw)
        assert TIEBA_IMAGES_FIELD not in repr(record.content.raw)
        assert [(asset.kind, asset.position, asset.remote_id) for asset in record.assets] == [
            (AssetKind.IMAGE, position, DOUBLE_ASSET_REMOTE_IDS[position]) for position in range(2)
        ]
        assert tuple(asset.source_url for asset in record.assets) == DOUBLE_DISCOVERY_IMAGES_V1
        assert tuple(asset_source_hint(asset.source_url) for asset in record.assets) == DOUBLE_IMAGE_HINTS

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
            content = session.scalars(select(Content)).one()
            assert len(assets) == len(sources) == 2
            assert content.canonical_url == CANONICAL_URL
            for position, asset in enumerate(assets):
                locator = parse_locator(asset.locator)
                assert isinstance(locator, AdapterRefreshLocator)
                assert locator.asset_key == stable_asset_key(
                    platform=Platform.TIEBA.value,
                    content_remote_type="content",
                    content_remote_id=CONTENT_ID,
                    kind=AssetKind.IMAGE.value,
                    position=position,
                    remote_id=DOUBLE_ASSET_REMOTE_IDS[position],
                )
                assert (asset.remote_id, asset.position, asset.generation, asset.source_url) == (
                    DOUBLE_ASSET_REMOTE_IDS[position],
                    position,
                    1,
                    DOUBLE_IMAGE_HINTS[position],
                )
                source = sources[asset.id]
                assert source.subscription_id == seed.subscription_id
                assert source.last_run_id == first_run_id
                assert source.observed_generation == 1
            asset_ids = tuple(UUID(asset.id) for asset in assets)

        resolver = _RecordingPublicResolver()
        targets: list[ValidatedTarget] = []
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            request_url = str(request.url)
            assert request_url in DOUBLE_REFRESH_IMAGES
            position = DOUBLE_REFRESH_IMAGES.index(request_url)
            mime_type = ("image/jpeg", "image/png")[position]
            assert set(request.headers) == {"accept", "accept-encoding", "connection", "host", "user-agent"}
            assert request.headers["accept-encoding"] == "identity"
            assert request.headers["host"] == "tiebapic.baidu.com"
            assert not request.headers["user-agent"].startswith("Mozilla/5.0")
            assert not {"cookie", "authorization", "referer", "origin"} & set(request.headers)
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(DOUBLE_IMAGE_BYTES[position])),
                    "Content-Type": mime_type,
                    "ETag": f'"execution-0021-image-{position}-v1"',
                },
                content=DOUBLE_IMAGE_BYTES[position],
            )

        def transport_factory(target: ValidatedTarget) -> httpx.BaseTransport:
            targets.append(target)
            return httpx.MockTransport(handler)

        probe = _UnexpectedStructuralProbe()
        http = SafeHttpClient(resolver, transport_factory=transport_factory)
        harnesses: list[tuple[AssetDownloadService, AssetDownloadRequest, _RecordingRefresher]] = []
        for position, asset_id in enumerate(asset_ids):
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
            service = AssetDownloadService(
                database,
                SecureMediaDownloader(http, refresher=refresher, probe=probe),
                clock=lambda: FIXED_AT,
            )
            request = AssetDownloadRequest(
                asset_id=asset_id,
                worker_id=f"execution-0021-image-{position}-download",
                work_root=download_work_root,
                archive_root=archive_root,
                lease_seconds=60,
            )
            harnesses.append((service, request, refresher))

        first_downloads = tuple(service.run(request) for service, request, _refresher in harnesses)
        checksums = tuple(hashlib.sha256(payload).hexdigest() for payload in DOUBLE_IMAGE_BYTES)
        expected_archives = (
            archive_root / "sha256" / checksums[0][:2] / f"{checksums[0]}.jpg",
            archive_root / "sha256" / checksums[1][:2] / f"{checksums[1]}.png",
        )
        for position, download in enumerate(first_downloads):
            assert download.disposition == "downloaded"
            assert download.archive_path == expected_archives[position].absolute()
            assert download.checksum_sha256 == checksums[position]
            assert download.mime_type == ("image/jpeg", "image/png")[position]
            assert expected_archives[position].read_bytes() == DOUBLE_IMAGE_BYTES[position]
        assert probe.calls == []
        assert resolver.calls == [("tiebapic.baidu.com", 443), ("tiebapic.baidu.com", 443)]
        assert [target.address for target in targets] == ["8.8.8.8", "8.8.8.8"]
        assert [str(request.url) for request in requests] == list(DOUBLE_REFRESH_IMAGES)
        assert [refresher.results[0] for _service, _request, refresher in harnesses] == [
            ResolvedLocator(url, MediaRequestProfile.DEFAULT) for url in DOUBLE_REFRESH_IMAGES
        ]

        assert len(_TwoImageDetailRunner.instances) == 2
        for detail_instance in _TwoImageDetailRunner.instances:
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
            assert detail_request.platform is Platform.TIEBA
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
            EmbyExportRequest(seed.author_id, "execution-0021-export", lease_seconds=60)
        )
        assert first_export.already_exported is False
        author_directory = library_root / first_export.output_path
        poster = next(author_directory.glob("Season */*-poster.jpg"))
        backdrop = next(author_directory.glob("Season */*-backdrop.png"))
        gallery = tuple(sorted(author_directory.glob("Season */*.assets/gallery-*")))
        assert len(gallery) == 2
        assert gallery[0].name.startswith("gallery-001-")
        assert gallery[1].name.startswith("gallery-002-")
        assert poster.read_bytes() == JPEG
        assert backdrop.read_bytes() == PNG
        assert tuple(path.read_bytes() for path in gallery) == DOUBLE_IMAGE_BYTES
        body = next(author_directory.glob("Season */*.assets/body.txt"))
        assert b"exactly two ordered static images" in body.read_bytes()
        episode_nfo = next(author_directory.glob("Season */*.nfo"))
        episode_nfo_payload = episode_nfo.read_bytes()
        assert CONTENT_ID.encode() in episode_nfo_payload
        assert poster.name.encode() in episode_nfo_payload
        assert backdrop.name.encode() in episode_nfo_payload
        source_path = next(author_directory.glob("Season */*.assets/source.json"))
        source_document = json.loads(source_path.read_text("utf-8"))
        assert source_document["platform"] == Platform.TIEBA.value
        assert source_document["remote_id"] == CONTENT_ID
        assert [
            (item["kind"], item["position"], item["remote_id"], item["checksum_sha256"])
            for item in source_document["assets"]
        ] == [
            (AssetKind.IMAGE.value, position, DOUBLE_ASSET_REMOTE_IDS[position], checksums[position])
            for position in range(2)
        ]
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

        replay = normalize_jsonl_bytes(DOUBLE_DISCOVERY_JSONL_V2, _normalization_context())
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

        replay_downloads = tuple(service.run(request) for service, request, _refresher in harnesses)
        replay_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0021-export-replay", lease_seconds=60)
        )
        assert all(download.disposition == "already_verified" for download in replay_downloads)
        assert tuple(download.job_id for download in replay_downloads) == tuple(
            download.job_id for download in first_downloads
        )
        assert replay_export.already_exported is True
        assert replay_export.job_id == first_export.job_id
        assert len(_TwoImageDetailRunner.instances) == len(requests) == len(targets) == 2
        assert resolver.calls == [("tiebapic.baidu.com", 443), ("tiebapic.baidu.com", 443)]
        assert probe.calls == []
        assert _tree(archive_root) == first_archive_tree
        assert _tree(author_directory) == first_library_tree

        with database.session() as session:
            final_assets = list(session.scalars(select(Asset).order_by(Asset.position)).all())
            final_content = session.scalars(select(Content)).one()
            jobs = list(session.scalars(select(Job).order_by(Job.job_type, Job.natural_key)).all())
            runs = list(session.scalars(select(SyncRun).order_by(SyncRun.created_at)).all())
            exports = list(session.scalars(select(ExportRecord)).all())
            assert len(final_assets) == 2
            for position, final_asset in enumerate(final_assets):
                assert final_asset.status == "verified" and final_asset.generation == 1
                assert final_asset.source_url == DOUBLE_IMAGE_HINTS[position]
                assert final_asset.local_path == str(expected_archives[position].absolute())
                assert final_asset.checksum_sha256 == checksums[position]
            assert final_content.canonical_url == CANONICAL_URL
            assert [run.status for run in runs] == ["succeeded", "succeeded"]
            assert [job.job_type for job in jobs].count("asset_download") == 2
            assert [job.job_type for job in jobs].count("export.emby") == 1
            assert all(job.status == "succeeded" and job.attempts == 1 for job in jobs)
            assert len(exports) == 1 and exports[0].status == "succeeded"
            durable_json = json.dumps(
                {
                    "assets": [
                        {"locator": asset.locator, "raw": asset.raw, "source_url": asset.source_url}
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
            database_path,
            runtime_root,
            download_work_root,
            archive_root,
            export_work_root,
            library_root,
        )
    finally:
        database.dispose()
