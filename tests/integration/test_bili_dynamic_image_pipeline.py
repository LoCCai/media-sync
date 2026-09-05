"""Offline dynamic publication -> actual secure image archive -> local Emby output.

The seed intentionally enters the repository boundary with normalized records;
sealed discovery/coverage is exercised separately by bridge/scheduler tests.
Only detail lookup and network transport are fake; no media server is used.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import ClassVar
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from media_sync.application import mediacrawler_download as runtime
from media_sync.application.downloads import AssetDownloadOrchestrationError
from media_sync.application.emby import EmbyExportRequest, EmbyExportService
from media_sync.application.mediacrawler_download import LazyMediaCrawlerLocatorRefresher
from media_sync.domain import AssetKind, AuthStatus, ContentKind, LoginMethod, Platform
from media_sync.exporters.emby import EmbyExporter
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    IngestionMode,
    MediaCrawlerIngestionService,
    SubscriptionRepository,
    upgrade_database,
)
from media_sync.infrastructure.db.models import Asset, Content, Subscription, SyncRun
from media_sync.integrations.mediacrawler import MediaCrawlerDetailRequest, MediaCrawlerDetailResult
from media_sync.integrations.mediacrawler.bilibili_dynamic import (
    BILI_DYNAMIC_FIELD,
    BILI_DYNAMIC_SOURCE_FIELD,
    BiliDynamicIdentity,
    BiliDynamicPayload,
)
from media_sync.integrations.mediacrawler.bilibili_multifeed import state_for_cursor
from media_sync.integrations.mediacrawler.normalizers import NormalizationContext, normalize_jsonl_bytes
from media_sync.media import MediaDownloadError, MediaRequestProfile, SafeHttpClient
from media_sync.security import SecretResolver
from tests.integration import test_weibo_image_pipeline as support
from tests.unit.test_bili_dynamic_refresh import _DID, _MID, _PUB_TS, _payload


def _jsonl(*payloads: BiliDynamicPayload) -> bytes:
    return b"".join((json.dumps(payload.to_record()) + "\n").encode() for payload in payloads)


class _DetailRunner:
    calls: ClassVar[list[MediaCrawlerDetailRequest]] = []
    payload: ClassVar[BiliDynamicPayload]

    def __init__(self, **kwargs: object) -> None:
        pass

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        self.calls.append(request)
        return MediaCrawlerDetailResult(_jsonl(self.payload), support.UPSTREAM_SHA)


@pytest.fixture
def database(tmp_path: Path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'dynamic.sqlite3').as_posix()}"
    upgrade_database(url)
    database = Database(url)
    try:
        yield database
    finally:
        database.dispose()


def _seed(database: Database) -> support._Seed:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=Platform.BILI.value,
            adapter="mediacrawler",
            display_name="Offline dynamic account",
            login_method=LoginMethod.SAVED_SESSION.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform=Platform.BILI.value, remote_id=_MID, display_name="Offline dynamic creator"),
            seen_at=support.FIXED_AT,
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            policy={
                "mediacrawler": {
                    "schema_version": 2,
                    "bili_scope": "dynamics",
                    "request_delay_seconds": 0.01,
                    "allow_full_history": False,
                    "headless": True,
                }
            },
        )
        return support._Seed(account.id, author.id, subscription.id)


def _publish(database: Database, seed: support._Seed, *payloads: BiliDynamicPayload) -> tuple[UUID, ...]:
    batch = normalize_jsonl_bytes(
        _jsonl(*payloads),
        NormalizationContext(
            platform=Platform.BILI,
            creator_remote_id=_MID,
            creator_display_name="Offline dynamic creator",
            upstream_sha=support.UPSTREAM_SHA,
            ingested_at=support.FIXED_AT,
        ),
    )
    assert not batch.quarantined and len(batch.records) == len(payloads)
    with database.session() as session:
        subscription = session.get(Subscription, seed.subscription_id)
        assert subscription is not None
        cursor = subscription.cursor["value"] if subscription.cursor else None
        revision = subscription.checkpoint_revision
    next_cursor = state_for_cursor(
        cursor,
        account_id=UUID(seed.account_id),
        author_fingerprint_sha256=hashlib.sha256(seed.author_id.encode()).hexdigest(),
        upstream_sha=support.UPSTREAM_SHA,
        scope="dynamics",
    ).to_cursor()
    run_id = support._start_ingesting_run(database, seed.subscription_id)
    with database.session() as session:
        run = session.get(SyncRun, run_id)
        assert run is not None
        run.cursor_before = {"value": cursor} if cursor else None
    result = MediaCrawlerIngestionService(database).ingest_bili_bounded(
        batch.records,
        subscription_id=seed.subscription_id,
        run_id=run_id,
        expected_revision=revision,
        input_cursor=cursor,
        next_cursor=next_cursor,
    )
    assert result.accepted_count == len(payloads)
    with database.session() as session:
        return tuple(UUID(asset.id) for asset in session.scalars(select(Asset).order_by(Asset.position)).all())


def _lazy(database: Database, seed: support._Seed, asset_id: UUID, tmp_path: Path) -> LazyMediaCrawlerLocatorRefresher:
    return LazyMediaCrawlerLocatorRefresher(
        database,
        asset_id=asset_id,
        subscription_id=UUID(seed.subscription_id),
        lock_path=tmp_path / "upstreams.lock.json",
        integration_root=tmp_path / "runtime",
        python_executable=tmp_path / "python",
        secret_resolver=SecretResolver({}),
        license_acknowledged=True,
    )


def test_dynamic_draw_and_word_reach_real_archive_and_local_emby_idempotently(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = _seed(database)
    draw = _payload()
    word = BiliDynamicPayload(
        BiliDynamicIdentity(str(int(_DID) + 1), "DYNAMIC_TYPE_WORD", _PUB_TS + 1, int(_MID)),
        "Complete offline WORD body.",
        None,
    )
    asset_ids = _publish(database, seed, draw, word)
    assert len(asset_ids) == 2
    _DetailRunner.calls = []
    _DetailRunner.payload = replace(
        draw,
        images=tuple(
            replace(image, url=image.url.replace("i0.hdslb.com", "i2.hdslb.com").replace("old", "PRIVATE_ROTATED"))
            for image in draw.images
        ),
    )
    monkeypatch.setattr(runtime, "MediaCrawlerDetailProcessRunner", _DetailRunner)
    urls = tuple(image.url for image in _DetailRunner.payload.images)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        position = urls.index(str(request.url))
        assert request.headers["referer"] == "https://www.bilibili.com/"
        assert request.headers["accept-encoding"] == "identity"
        assert "cookie" not in request.headers and "authorization" not in request.headers
        return httpx.Response(
            200,
            headers={"Content-Type": "image/png", "Content-Length": str(len(support.PNGS[position]))},
            content=support.PNGS[position],
        )

    resolver = support._RecordingPublicResolver()
    probe = support._UnexpectedStructuralProbe()
    http = SafeHttpClient(resolver, transport_factory=lambda target: httpx.MockTransport(handler))
    archive_root, library_root = tmp_path / "archive", tmp_path / "library"
    harnesses = tuple(
        support._download_harness(
            database,
            asset_id=asset_id,
            subscription_id=UUID(seed.subscription_id),
            tmp_path=tmp_path,
            runtime_root=tmp_path / "runtime",
            download_work_root=tmp_path / "download-work",
            archive_root=archive_root,
            http=http,
            probe=probe,
        )
        for asset_id in asset_ids
    )
    downloads = tuple(harness.service.run(harness.request) for harness in harnesses)
    for position, download in enumerate(downloads):
        assert download.disposition == "downloaded"
        assert download.archive_path.read_bytes() == support.PNGS[position]
        assert download.checksum_sha256 == hashlib.sha256(support.PNGS[position]).hexdigest()
        assert harnesses[position].refresher.results[0].request_profile is MediaRequestProfile.BILIBILI_MEDIA
    assert probe.calls == [] and len(requests) == len(_DetailRunner.calls) == 2
    for detail_request in _DetailRunner.calls:
        assert detail_request.bili_dynamic_detail and not detail_request.bili_progressive_detail
        assert detail_request.resolved_detail_reference() == _DID
        assert detail_request.bili_dynamic_pub_ts == _PUB_TS
    export = EmbyExportService(
        database, EmbyExporter(library_root, staging_root=tmp_path / "export-work"), clock=lambda: support.FIXED_AT
    )
    first = export.export_author(EmbyExportRequest(seed.author_id, "execution-0062-export", lease_seconds=60))
    author_root = library_root / first.output_path
    galleries = sorted(author_root.glob("Season */*.assets/gallery-*.png"))
    assert tuple(path.read_bytes() for path in galleries) == support.PNGS
    assert next(author_root.glob("Season */*-poster.png")).read_bytes() == support.PNGS[0]
    assert next(author_root.glob("Season */*-backdrop.png")).read_bytes() == support.PNGS[1]
    bodies = [path.read_text("utf-8") for path in author_root.glob("Season */*.assets/body.txt")]
    assert draw.text in bodies and word.text in bodies
    assert len(list(author_root.glob("Season */*.nfo"))) == 2
    sources = [json.loads(path.read_text("utf-8")) for path in author_root.glob("Season */*.assets/source.json")]
    assert {source["remote_id"] for source in sources} == {_DID, word.identity.did}
    assert all(source["content_kind"] == ContentKind.DYNAMIC.value for source in sources)
    assert sum(len(source["assets"]) for source in sources) == 2
    for source in sources:
        assert not {"raw", "locator", "source_url"} & source.keys()
    archive_before, library_before = support._tree(archive_root), support._tree(library_root)
    replay = tuple(harness.service.run(harness.request) for harness in harnesses)
    second = export.export_author(EmbyExportRequest(seed.author_id, "execution-0062-export-replay", lease_seconds=60))
    assert all(
        item.disposition == "already_verified" and item.job_id == prior.job_id
        for item, prior in zip(replay, downloads, strict=True)
    )
    assert second.already_exported and second.job_id == first.job_id
    assert (second.source_fingerprint, second.rendered_fingerprint) == (
        first.source_fingerprint,
        first.rendered_fingerprint,
    )
    assert support._tree(archive_root) == archive_before and support._tree(library_root) == library_before
    assert len(requests) == len(_DetailRunner.calls) == 2
    assert resolver.calls == [("i2.hdslb.com", 443)] * 2
    for root in (archive_root, library_root, tmp_path / "download-work", tmp_path / "export-work"):
        assert all(
            b"PRIVATE_ROTATED" not in value and BILI_DYNAMIC_FIELD.encode() not in value
            for value in support._tree(root).values()
        )
    with database.session() as session:
        for asset in session.scalars(select(Asset)).all():
            assert asset.status == "verified" and asset.kind == AssetKind.IMAGE.value
            assert "?" not in asset.source_url


@pytest.mark.parametrize("change", ["missing", "remote_id", "position", "source_did", "source_mid", "type", "hint"])
def test_current_complete_database_slots_are_required_before_detail(
    database: Database, tmp_path: Path, change: str
) -> None:
    seed = _seed(database)
    ids = _publish(database, seed, _payload())
    with database.session() as session:
        tail = session.get(Asset, str(ids[1]))
        content = session.scalar(select(Content))
        assert tail is not None and content is not None
        if change == "missing":
            session.delete(tail)
        elif change == "remote_id":
            tail.remote_id = tail.remote_id[:-1] + ("0" if tail.remote_id[-1] != "0" else "1")
        elif change == "position":
            tail.position = 3
        elif change == "hint":
            tail.source_url += "?token=should-not-be-durable"
        else:
            raw = json.loads(json.dumps(content.raw))
            identity = raw["record"][BILI_DYNAMIC_SOURCE_FIELD]["identity"]
            if change == "source_did":
                identity["did"] = str(int(_DID) + 1)
            elif change == "source_mid":
                identity["author_mid"] = int(_MID) + 1
            else:
                identity["dynamic_type"] = "DYNAMIC_TYPE_WORD"
            content.raw = raw
    with pytest.raises(MediaDownloadError, match="locator_refresh_configuration_invalid"):
        _lazy(database, seed, ids[0], tmp_path).preflight()


def test_shrinking_gallery_binds_new_complete_slots_but_never_old_tail(database: Database, tmp_path: Path) -> None:
    seed = _seed(database)
    old_ids = _publish(database, seed, _payload())
    smaller = replace(_payload(), images=_payload().images[:1])
    new_ids = _publish(database, seed, smaller)
    assert new_ids == old_ids  # historical tail retained; current position reuses DB identity with new generation.
    context = _lazy(database, seed, new_ids[0], tmp_path)._load_context()
    assert list(context.bili_dynamic_image_remote_ids) == smaller.source_mapping()["image_remote_ids"]
    with pytest.raises(MediaDownloadError):
        _lazy(database, seed, old_ids[1], tmp_path).preflight()


def test_non_bili_dynamic_policy_cannot_enter_download_context(database: Database, tmp_path: Path) -> None:
    seed = support._seed_subscription(database)
    batch = normalize_jsonl_bytes(support.WEIBO_JSONL, support._normalization_context())
    MediaCrawlerIngestionService(database).ingest(
        batch.records,
        subscription_id=seed.subscription_id,
        run_id=support._start_ingesting_run(database, seed.subscription_id),
        expected_revision=0,
        mode=IngestionMode.FORWARD,
    )
    with database.session() as session:
        subscription = session.get(Subscription, seed.subscription_id)
        asset = session.scalar(select(Asset).order_by(Asset.position))
        assert subscription is not None and asset is not None
        subscription.policy = {
            "mediacrawler": {
                "schema_version": 2,
                "bili_scope": "dynamics",
                "allow_full_history": False,
                "headless": True,
                "request_delay_seconds": 0.01,
            }
        }
        asset_id = UUID(asset.id)
    with pytest.raises(MediaDownloadError, match="locator_refresh_configuration_invalid"):
        _lazy(database, seed, asset_id, tmp_path).preflight()


@pytest.mark.parametrize("change", ["tail", "order", "delete", "dimension"])
def test_changed_complete_gallery_cannot_download_even_unchanged_first_slot(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    seed = _seed(database)
    original = _payload()
    ids = _publish(database, seed, original)
    images = original.images
    if change == "tail":
        images = (images[0], replace(images[1], url=images[1].url.replace("second.png", "changed.png")))
    elif change == "order":
        images = tuple(reversed(images))
    elif change == "delete":
        images = images[:1]
    else:
        images = (images[0], replace(images[1], width=images[1].width + 1))
    _DetailRunner.payload = replace(original, images=images)
    _DetailRunner.calls = []
    monkeypatch.setattr(runtime, "MediaCrawlerDetailProcessRunner", _DetailRunner)

    def forbidden_transport(target: object) -> httpx.BaseTransport:
        raise AssertionError("changed attachment must fail before HTTP")

    resolver = support._RecordingPublicResolver()
    harness = support._download_harness(
        database,
        asset_id=ids[0],
        subscription_id=UUID(seed.subscription_id),
        tmp_path=tmp_path,
        runtime_root=tmp_path / "runtime",
        download_work_root=tmp_path / "download-work",
        archive_root=tmp_path / "archive",
        http=SafeHttpClient(resolver, transport_factory=forbidden_transport),
        probe=support._UnexpectedStructuralProbe(),
    )
    with pytest.raises(AssetDownloadOrchestrationError, match="locator_refresh_schema_changed"):
        harness.service.run(harness.request)
    assert len(_DetailRunner.calls) == 1 and resolver.calls == []
    assert support._tree(tmp_path / "archive") == {}
    with database.session() as session:
        asset = session.get(Asset, str(ids[0]))
        assert asset is not None and asset.status != "verified" and asset.local_path is None
