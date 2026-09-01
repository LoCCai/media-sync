"""Offline XHS creator-authority gallery-to-Emby qualification."""

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
    Account,
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
from media_sync.security import EnvironmentSecretProvider, SecretResolver, SecretScheme

FIXED_AT = datetime(2026, 9, 1, 9, 17, 0, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
AUTHOR_REMOTE_ID = "5f58bd990000000001003753"
CONTENT_ID = "66fad51c000000001b0224b8"
DISTRACTOR_ID = "66fad51c000000001b0224b9"
CREATOR_MAX_ITEMS = 7
CREATOR_SECRET_REF = "env:MEDIA_SYNC_EXECUTION0017_XHS_CREATOR_URL"
CREATOR_TOKEN = "EXECUTION0017XHSCREATORTOKEN"
CREATOR_REFERENCE = (
    f"https://www.xiaohongshu.com/user/profile/{AUTHOR_REMOTE_ID}?xsec_token={CREATOR_TOKEN}&xsec_source=pc_search"
)
IMAGE_REMOTE_IDS = tuple(f"{CONTENT_ID}:image:{position}" for position in range(2))
IMAGE_HINTS = (
    "https://cdn.example.test/xhs/gallery-first.png",
    "https://cdn.example.test/xhs/gallery-second.png",
)
DISCOVERY_SIGNATURES = ("EXECUTION0017DISCOVERYZERO", "EXECUTION0017DISCOVERYONE")
REFRESH_SIGNATURES = ("EXECUTION0017REFRESHZERO", "EXECUTION0017REFRESHONE")
DISCOVERY_IMAGE_URLS = tuple(
    f"{hint}?signature={signature}" for hint, signature in zip(IMAGE_HINTS, DISCOVERY_SIGNATURES, strict=True)
)
REFRESH_IMAGE_URLS = tuple(
    f"{hint}?signature={signature}" for hint, signature in zip(IMAGE_HINTS, REFRESH_SIGNATURES, strict=True)
)
DISCOVERY_NOTE_TOKEN = "EXECUTION0017DISCOVERYNOTETOKEN"
REFRESH_NOTE_TOKEN = "EXECUTION0017REFRESHNOTETOKEN"
DISTRACTOR_TOKEN = "EXECUTION0017DISTRACTORTOKEN"
DISTRACTOR_IMAGE_URL = "https://cdn.example.test/xhs/distractor.png?signature=EXECUTION0017DISTRACTORIMAGE"
PNGS = (
    b"\x89PNG\r\n\x1a\n" + b"execution-0017-offline-xhs-gallery-zero",
    b"\x89PNG\r\n\x1a\n" + b"execution-0017-offline-xhs-gallery-one",
)
FORBIDDEN_VALUES = (
    CREATOR_REFERENCE,
    CREATOR_TOKEN,
    DISCOVERY_NOTE_TOKEN,
    REFRESH_NOTE_TOKEN,
    DISTRACTOR_TOKEN,
    *DISCOVERY_SIGNATURES,
    *REFRESH_SIGNATURES,
    DISTRACTOR_IMAGE_URL,
    "xsec_token=",
    "?signature=",
)


def _jsonl(*records: Mapping[str, object]) -> bytes:
    return b"".join(
        (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for record in records
    )


def _xhs_record(
    note_id: str,
    image_urls: Sequence[str],
    *,
    note_token: str,
    title: str,
) -> dict[str, object]:
    return {
        "note_id": note_id,
        "type": "normal",
        "title": title,
        "desc": f"{title} offline fixture",
        "video_url": "",
        "time": 1788235200000,
        "last_update_time": 1788235260000,
        "creator_hash": "untrusted-xhs-creator",
        "nickname": "Untrusted nickname",
        "liked_count": "17",
        "collected_count": "2",
        "comment_count": "1",
        "share_count": "0",
        "image_list": ",".join(image_urls),
        "tag_list": "offline,gallery",
        "last_modify_ts": 1788235320000,
        "note_url": (f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={note_token}&xsec_source=pc_search"),
        "source_keyword": "fixture",
        "xsec_token": note_token,
    }


DISCOVERY_JSONL = _jsonl(
    _xhs_record(
        CONTENT_ID,
        DISCOVERY_IMAGE_URLS,
        note_token=DISCOVERY_NOTE_TOKEN,
        title="Execution 0017 XHS gallery",
    )
)
REFRESH_JSONL = _jsonl(
    _xhs_record(
        DISTRACTOR_ID,
        (DISTRACTOR_IMAGE_URL,),
        note_token=DISTRACTOR_TOKEN,
        title="Distractor note",
    ),
    _xhs_record(
        CONTENT_ID,
        REFRESH_IMAGE_URLS,
        note_token=REFRESH_NOTE_TOKEN,
        title="Execution 0017 XHS gallery",
    ),
)


def _normalization_context() -> NormalizationContext:
    return NormalizationContext(
        platform=Platform.XHS,
        creator_remote_id=AUTHOR_REMOTE_ID,
        creator_display_name="XHS Offline Creator",
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
            "creator_input": {"secret_ref": CREATOR_SECRET_REF},
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
            platform=Platform.XHS.value,
            adapter="mediacrawler",
            display_name="execution-0017-offline-account",
            login_method=LoginMethod.QR.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=Platform.XHS.value,
                remote_id=AUTHOR_REMOTE_ID,
                display_name="XHS Offline Creator",
            ),
            seen_at=FIXED_AT,
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            policy=_policy(),
            max_items=CREATOR_MAX_ITEMS,
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
        return MediaCrawlerDetailResult(REFRESH_JSONL, UPSTREAM_SHA)


@dataclass(slots=True)
class _RecordingRefresher:
    delegate: LazyMediaCrawlerLocatorRefresher
    results: list[ResolvedLocator] = field(default_factory=list)

    def resolve(self, locator: AdapterRefreshLocator) -> ResolvedLocator:
        result = self.delegate.resolve(locator)
        self.results.append(result)
        return result


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
    secret_resolver: SecretResolver,
) -> _DownloadHarness:
    lazy = LazyMediaCrawlerLocatorRefresher(
        database,
        asset_id=asset_id,
        subscription_id=subscription_id,
        lock_path=tmp_path / "upstreams.lock.json",
        integration_root=runtime_root,
        python_executable=tmp_path / "python",
        secret_resolver=secret_resolver,
        license_acknowledged=True,
    )
    refresher = _RecordingRefresher(lazy)
    return _DownloadHarness(
        AssetDownloadService(
            database,
            SecureMediaDownloader(http, refresher=refresher, probe=probe),
            clock=lambda: FIXED_AT,
        ),
        AssetDownloadRequest(
            asset_id=asset_id,
            worker_id="execution-0017-xhs-download",
            work_root=download_work_root,
            archive_root=archive_root,
            lease_seconds=60,
        ),
        refresher,
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


def test_xhs_creator_authority_gallery_reaches_emby_and_replays_without_network_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "xhs-creator-authority.sqlite3"
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
        normalized = normalize_jsonl_bytes(DISCOVERY_JSONL, _normalization_context())
        assert not normalized.quarantined and not normalized.truncated_tail
        assert len(normalized.records) == 1
        record = normalized.records[0]
        assert record.content.kind is ContentKind.GALLERY
        assert [(asset.kind, asset.position, asset.remote_id) for asset in record.assets] == [
            (AssetKind.IMAGE, position, IMAGE_REMOTE_IDS[position]) for position in range(2)
        ]
        assert tuple(asset_source_hint(asset.source_url) for asset in record.assets) == IMAGE_HINTS

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
            sources = {item.asset_id: item for item in session.scalars(select(AssetRefreshSource)).all()}
            assert len(assets) == len(sources) == 2
            for position, asset in enumerate(assets):
                locator = parse_locator(asset.locator)
                assert isinstance(locator, AdapterRefreshLocator)
                assert locator.asset_key == stable_asset_key(
                    platform=Platform.XHS.value,
                    content_remote_type="content",
                    content_remote_id=CONTENT_ID,
                    kind=AssetKind.IMAGE.value,
                    position=position,
                    remote_id=IMAGE_REMOTE_IDS[position],
                )
                assert asset.source_url == IMAGE_HINTS[position]
                assert sources[asset.id].subscription_id == seed.subscription_id
                assert sources[asset.id].last_run_id == first_run_id
                assert sources[asset.id].observed_generation == 1
            asset_ids = tuple(UUID(asset.id) for asset in assets)

        public_resolver = _RecordingPublicResolver()
        targets: list[ValidatedTarget] = []
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            request_url = str(request.url)
            assert request_url in REFRESH_IMAGE_URLS
            position = REFRESH_IMAGE_URLS.index(request_url)
            assert set(request.headers) == {"accept", "accept-encoding", "connection", "host", "user-agent"}
            assert request.headers["accept-encoding"] == "identity"
            assert request.headers["host"] == "cdn.example.test"
            for forbidden_header in ("cookie", "authorization", "referer", "origin"):
                assert forbidden_header not in request.headers
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(PNGS[position])),
                    "Content-Type": "image/png",
                    "ETag": f'"execution-0017-xhs-{position}-v1"',
                },
                content=PNGS[position],
            )

        def transport_factory(target: ValidatedTarget) -> httpx.BaseTransport:
            targets.append(target)
            return httpx.MockTransport(handler)

        probe = _UnexpectedStructuralProbe()
        http = SafeHttpClient(public_resolver, transport_factory=transport_factory)
        secret_resolver = SecretResolver(
            {
                SecretScheme.ENV: EnvironmentSecretProvider(
                    {"MEDIA_SYNC_EXECUTION0017_XHS_CREATOR_URL": CREATOR_REFERENCE}
                )
            }
        )
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
                secret_resolver=secret_resolver,
            )
            for asset_id in asset_ids
        )

        first_downloads = tuple(harness.service.run(harness.request) for harness in harnesses)
        checksums = tuple(hashlib.sha256(payload).hexdigest() for payload in PNGS)
        expected_archives = tuple(archive_root / "sha256" / value[:2] / f"{value}.png" for value in checksums)
        for position, outcome in enumerate(first_downloads):
            assert outcome.disposition == "downloaded"
            assert outcome.archive_path == expected_archives[position].absolute()
            assert outcome.checksum_sha256 == checksums[position]
            assert outcome.mime_type == "image/png"
            assert expected_archives[position].read_bytes() == PNGS[position]
        assert probe.calls == []
        assert public_resolver.calls == [("cdn.example.test", 443), ("cdn.example.test", 443)]
        assert [target.address for target in targets] == ["8.8.8.8", "8.8.8.8"]
        assert [str(request.url) for request in requests] == list(REFRESH_IMAGE_URLS)
        assert tuple(harness.refresher.results[0].url for harness in harnesses) == REFRESH_IMAGE_URLS
        assert all(harness.refresher.results[0].request_profile is MediaRequestProfile.DEFAULT for harness in harnesses)

        assert len(_FakeDetailRunner.instances) == 2
        for instance in _FakeDetailRunner.instances:
            assert len(instance.calls) == 1
            detail_request = instance.calls[0]
            assert detail_request.account_id == UUID(seed.account_id)
            assert detail_request.subscription_id == UUID(seed.subscription_id)
            assert detail_request.platform is Platform.XHS
            assert detail_request.login_method is LoginMethod.QR
            assert detail_request.content_remote_id == CONTENT_ID
            assert detail_request.detail_reference is None
            assert detail_request.creator_reference is not None
            assert detail_request.creator_reference.reveal() == CREATOR_REFERENCE
            assert detail_request.creator_max_items == CREATOR_MAX_ITEMS
            assert CREATOR_TOKEN not in repr(detail_request)

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        first_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0017-xhs-export", lease_seconds=60)
        )
        assert first_export.already_exported is False
        author_directory = library_root / first_export.output_path
        poster = next(author_directory.glob("Season */*-poster.png"))
        backdrop = next(author_directory.glob("Season */*-backdrop.png"))
        gallery = tuple(sorted(author_directory.glob("Season */*.assets/gallery-*.png")))
        assert poster.read_bytes() == PNGS[0]
        assert backdrop.read_bytes() == PNGS[1]
        assert len(gallery) == 2 and tuple(path.read_bytes() for path in gallery) == PNGS
        assert (author_directory / "tvshow.nfo").is_file()
        episode_nfo = next(author_directory.glob("Season */*.nfo"))
        assert CONTENT_ID.encode() in episode_nfo.read_bytes()
        source_path = next(author_directory.glob("Season */*.assets/source.json"))
        source_document = json.loads(source_path.read_text("utf-8"))
        assert source_document["platform"] == Platform.XHS.value
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
        _assert_private_values_absent(runtime_root, download_work_root, archive_root, export_work_root, library_root)

        replay = normalize_jsonl_bytes(DISCOVERY_JSONL, _normalization_context())
        second_run_id = _start_ingesting_run(database, seed.subscription_id)
        second_ingest = MediaCrawlerIngestionService(database).ingest(
            replay.records,
            subscription_id=seed.subscription_id,
            run_id=second_run_id,
            expected_revision=1,
            mode=IngestionMode.FORWARD,
        )
        assert (second_ingest.accepted_count, second_ingest.discovered_count, second_ingest.asset_count) == (0, 0, 0)

        replay_downloads = tuple(harness.service.run(harness.request) for harness in harnesses)
        replay_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0017-xhs-export-replay", lease_seconds=60)
        )
        for replay_outcome, first_outcome in zip(replay_downloads, first_downloads, strict=True):
            assert replay_outcome.disposition == "already_verified"
            assert replay_outcome.job_id == first_outcome.job_id
            assert replay_outcome.archive_path == first_outcome.archive_path
        assert replay_export.already_exported is True
        assert replay_export.job_id == first_export.job_id
        assert len(_FakeDetailRunner.instances) == len(requests) == len(targets) == 2
        assert sum(len(instance.calls) for instance in _FakeDetailRunner.instances) == 2
        assert _tree(archive_root) == first_archive_tree
        assert _tree(author_directory) == first_library_tree

        with database.session() as session:
            final_account = session.get(Account, seed.account_id)
            final_subscription = session.get(Subscription, seed.subscription_id)
            final_assets = list(session.scalars(select(Asset).order_by(Asset.position)).all())
            final_sources = list(session.scalars(select(AssetRefreshSource)).all())
            final_content = session.scalar(select(Content))
            jobs = list(session.scalars(select(Job).order_by(Job.job_type, Job.natural_key)).all())
            runs = list(session.scalars(select(SyncRun).order_by(SyncRun.created_at)).all())
            exports = list(session.scalars(select(ExportRecord)).all())
            assert final_account is not None and final_subscription is not None and final_content is not None
            assert (final_account.platform, final_account.login_method) == (Platform.XHS.value, LoginMethod.QR.value)
            assert final_subscription.account_id == seed.account_id
            assert final_subscription.author_id == seed.author_id
            assert final_subscription.max_items == CREATOR_MAX_ITEMS
            assert final_subscription.policy == _policy()
            assert len(final_assets) == len(final_sources) == 2
            assert all(asset.status == "verified" and asset.generation == 1 for asset in final_assets)
            assert all(source.subscription_id == seed.subscription_id for source in final_sources)
            assert [run.status for run in runs] == ["succeeded", "succeeded"]
            assert [job.job_type for job in jobs].count("asset_download") == 2
            assert [job.job_type for job in jobs].count("export.emby") == 1
            assert len(exports) == 1 and exports[0].status == "succeeded"
            durable_json = json.dumps(
                {
                    "account": {"credential_ref": final_account.credential_ref},
                    "subscription": final_subscription.policy,
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
            for value in FORBIDDEN_VALUES:
                assert value not in durable_json, value

        _assert_private_values_absent(runtime_root, download_work_root, archive_root, export_work_root, library_root)
    finally:
        database.dispose()

    sqlite_artifacts = [path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file()]
    assert sqlite_artifacts
    _assert_private_values_absent(*sqlite_artifacts)
