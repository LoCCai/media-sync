"""Short-transaction MediaCrawler normalized-output ingestion coverage."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

import media_sync.infrastructure.db.mediacrawler_ingestion as ingestion_module
from media_sync.domain import (
    AssetKind,
    AssetSnapshot,
    AuthorSnapshot,
    ContentKind,
    ContentSnapshot,
    Platform,
    RunStatus,
)
from media_sync.infrastructure.db import (
    AccountRepository,
    AssetRefreshSourceRepository,
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    Database,
    IngestionMode,
    MediaCrawlerIngestionService,
    RepositoryError,
    StaleCheckpointError,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import Asset, AssetRefreshSource, Author, Content, Subscription, SyncRun
from media_sync.integrations.mediacrawler.normalizers import (
    NormalizationContext,
    NormalizedMediaRecord,
    normalize_jsonl_bytes,
)
from media_sync.media.locator import AdapterRefreshLocator, locator_fingerprint, parse_locator


def _database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


class _TrackingDatabase(Database):
    def __init__(self, database_url: str) -> None:
        super().__init__(database_url)
        self.active_sessions = 0
        self.opened_sessions = 0

    @contextmanager
    def session(self) -> Iterator[Session]:
        self.active_sessions += 1
        self.opened_sessions += 1
        try:
            with super().session() as session:
                yield session
        finally:
            self.active_sessions -= 1


@pytest.fixture
def database(tmp_path: Path) -> Iterator[_TrackingDatabase]:
    instance = _TrackingDatabase(_database_url(tmp_path / "mediacrawler-ingestion.sqlite3"))
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_subscription(
    database: Database,
    *,
    account_name: str = "mediacrawler-ingestion-account",
    adapter: str = "mediacrawler",
    platform: Platform = Platform.BILI,
    cursor: dict[str, object] | None = None,
    backfill_cursor: dict[str, object] | None = None,
    next_run_at: datetime | None = None,
) -> str:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=platform.value,
            display_name=account_name,
            adapter=adapter,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=platform.value,
                remote_id="creator-001",
                display_name="Creator One",
            )
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            cursor=cursor,
            backfill_cursor=backfill_cursor,
            next_run_at=next_run_at,
        )
        return subscription.id


def _create_run(database: Database, subscription_id: str) -> str:
    with database.session() as session:
        repository = SyncRunRepository(session)
        run = repository.create(subscription_id=subscription_id)
        repository.set_status(run.id, RunStatus.CLAIMED.value, expected_status=RunStatus.QUEUED.value)
        repository.set_status(run.id, RunStatus.RUNNING.value, expected_status=RunStatus.CLAIMED.value)
        repository.set_status(run.id, RunStatus.INGESTING.value, expected_status=RunStatus.RUNNING.value)
        return run.id


def _record(
    remote_id: str,
    published_at: datetime | None,
    *,
    remote_type: str = "content",
    asset_source_url: str | None = None,
) -> NormalizedMediaRecord:
    author = AuthorSnapshot(
        platform=Platform.BILI,
        remote_id="creator-001",
        display_name="Creator One",
    )
    content = ContentSnapshot(
        platform=Platform.BILI,
        remote_id=remote_id,
        remote_type=remote_type,
        author_remote_id=author.remote_id,
        kind=ContentKind.DYNAMIC if remote_type == "dynamic" else ContentKind.VIDEO,
        title=f"Title {remote_type}:{remote_id}",
        published_at=published_at,
    )
    asset_kind = AssetKind.IMAGE if remote_type == "dynamic" else AssetKind.VIDEO
    asset = AssetSnapshot(
        platform=Platform.BILI,
        remote_id=f"{remote_type}:{remote_id}:asset",
        content_remote_id=remote_id,
        kind=asset_kind,
        source_url=asset_source_url or f"https://example.invalid/{remote_type}/{remote_id}",
    )
    return NormalizedMediaRecord(author=author, content=content, assets=(asset,))


def test_kuaishou_media_queries_are_ephemeral_across_normalization_and_sqlite(
    database: Database,
) -> None:
    known_sentinel = f"KS_KNOWN_QUERY_SENTINEL_{uuid4().hex}"
    unknown_sentinel = f"KS_UNKNOWN_QUERY_SENTINEL_{uuid4().hex}"
    fragment_sentinel = f"KS_FRAGMENT_SENTINEL_{uuid4().hex}"
    username_sentinel = f"KS_USERNAME_SENTINEL_{uuid4().hex}"
    password_sentinel = f"KS_PASSWORD_SENTINEL_{uuid4().hex}"
    nested_sentinel = f"KS_NESTED_SHAPE_SENTINEL_{uuid4().hex}"
    video_url = (
        f"https://{username_sentinel}:{password_sentinel}@video.kuaishou.test/media/ks-video-001.mp4"
        f"?auth={known_sentinel}&clientCacheKey={unknown_sentinel}#{fragment_sentinel}"
    )
    cover_url = (
        f"https://{username_sentinel}:{password_sentinel}@image.kuaishou.test/media/ks-video-001.jpg"
        f"?signature={known_sentinel}&futureProofKey={unknown_sentinel}#{fragment_sentinel}"
    )
    record = {
        "video_id": "ks-video-001",
        "video_type": "video",
        "title": "Kuaishou fixture",
        "desc": "One ordinary video",
        "create_time": "1767225600",
        "video_url": "https://www.kuaishou.com/short-video/ks-video-001",
        "video_play_url": [
            video_url,
            {"url": f"https://nested.kuaishou.test/video.mp4?future={nested_sentinel}"},
        ],
        "video_cover_url": [
            cover_url,
            [{"href": f"https://nested.kuaishou.test/cover.jpg?future={nested_sentinel}"}],
        ],
    }
    batch = normalize_jsonl_bytes(
        (json.dumps(record, separators=(",", ":")) + "\n").encode(),
        NormalizationContext(
            platform=Platform.KS,
            creator_remote_id="creator-001",
            creator_display_name="Creator One",
            upstream_sha="d6f7c5bb906b6dac40ddf343ef9e26438a3de092",
            ingested_at=datetime(2026, 8, 31, tzinfo=UTC),
        ),
    )

    assert not batch.quarantined
    assert len(batch.records) == 1
    normalized = batch.records[0]
    assert tuple(asset.source_url for asset in normalized.assets) == (video_url, cover_url)
    retained_record = normalized.content.raw["record"]
    assert retained_record["video_play_url"] == ("https://video.kuaishou.test/media/ks-video-001.mp4", None)
    assert retained_record["video_cover_url"] == ("https://image.kuaishou.test/media/ks-video-001.jpg", (None,))
    assert normalized.author.raw == normalized.content.raw
    assert all(asset.raw == normalized.content.raw for asset in normalized.assets)

    subscription_id = _seed_subscription(database, platform=Platform.KS)
    result = MediaCrawlerIngestionService(database).ingest(
        batch.records,
        subscription_id=subscription_id,
        run_id=_create_run(database, subscription_id),
        expected_revision=0,
        mode=IngestionMode.FORWARD,
    )
    assert result.accepted_count == 1
    assert result.asset_count == 2

    forbidden = (
        known_sentinel,
        unknown_sentinel,
        fragment_sentinel,
        username_sentinel,
        password_sentinel,
        nested_sentinel,
    )
    with database.session() as session:
        author = session.scalar(select(Author).where(Author.platform == Platform.KS.value))
        content = session.scalar(select(Content).where(Content.platform == Platform.KS.value))
        assets = tuple(
            session.scalars(select(Asset).where(Asset.platform == Platform.KS.value).order_by(Asset.kind)).all()
        )
        assert author is not None and content is not None and len(assets) == 2
        retained_values = json.dumps(
            {
                "author_raw": author.raw,
                "content_raw": content.raw,
                "assets": [
                    {"source_url": asset.source_url, "locator": asset.locator, "raw": asset.raw} for asset in assets
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        assert all(sentinel not in retained_values for sentinel in forbidden)
        assert {asset.source_url for asset in assets} == {
            "https://video.kuaishou.test/media/ks-video-001.mp4",
            "https://image.kuaishou.test/media/ks-video-001.jpg",
        }
        for asset in assets:
            locator = parse_locator(asset.locator)
            assert isinstance(locator, AdapterRefreshLocator)
            assert locator.adapter == "mediacrawler"

    database_path_value = make_url(database.url).database
    assert database_path_value is not None
    database.dispose()
    database_path = Path(database_path_value)
    sqlite_bytes = b"".join(path.read_bytes() for path in database_path.parent.glob(f"{database_path.name}*"))
    assert all(sentinel.encode() not in sqlite_bytes for sentinel in forbidden)


def test_ingestion_records_exact_refresh_source_and_archive_reset_keeps_it_eligible(
    database: Database,
) -> None:
    subscription_id = _seed_subscription(database)
    run_id = _create_run(database, subscription_id)

    result = MediaCrawlerIngestionService(database).ingest(
        (_record("provenance", None),),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=0,
        mode=IngestionMode.FORWARD,
    )
    assert result.checkpoint_revision == 1

    with database.session() as session:
        asset = session.scalar(select(Asset))
        source = session.scalar(select(AssetRefreshSource))
        assert asset is not None and source is not None
        assert source.asset_id == asset.id
        assert source.subscription_id == subscription_id
        assert source.last_run_id == run_id
        assert source.observation_kind == "ingested"
        assert source.observed_generation == asset.generation == 1
        assert source.observed_semantic_fingerprint == asset.semantic_fingerprint
        assert source.observed_locator_fingerprint == asset.locator_fingerprint
        assert [item.subscription_id for item in AssetRefreshSourceRepository(session).list_eligible(asset.id)] == [
            subscription_id
        ]

        asset.status = "verified"
        asset.local_path = "archive/sha256/aa/provenance.mp4"
        asset.checksum_sha256 = "a" * 64
        asset.size_bytes = 17
        session.flush()
        reset = AssetRepository(session).reset_verified_archive(
            asset.id,
            expected_generation=1,
            expected_local_path="archive/sha256/aa/provenance.mp4",
            expected_checksum_sha256="a" * 64,
            expected_size_bytes=17,
            error_code="archive_blob_missing",
            error_message="fixture archive is missing",
        )
        assert reset.generation == 2
        assert source.observed_generation == 1
        assert [item.subscription_id for item in AssetRefreshSourceRepository(session).list_eligible(asset.id)] == [
            subscription_id
        ]


def test_invalid_account_relation_rolls_back_asset_observation_and_checkpoint(database: Database) -> None:
    subscription_id = _seed_subscription(
        database,
        account_name="non-mediacrawler-account",
        adapter="native",
    )
    run_id = _create_run(database, subscription_id)

    with pytest.raises(RepositoryError, match="observation relation is not exact"):
        MediaCrawlerIngestionService(database).ingest(
            (_record("must-rollback", None),),
            subscription_id=subscription_id,
            run_id=run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        run = session.get(SyncRun, run_id)
        assert subscription is not None and run is not None
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(AssetRefreshSource)) == 0
        assert subscription.checkpoint_revision == 0
        assert run.status == RunStatus.INGESTING.value
        assert run.checkpoint_revision_after is None


def test_wrong_run_is_rejected_before_ingestion_mutation(database: Database) -> None:
    expected_subscription_id = _seed_subscription(database, account_name="expected-account")
    other_subscription_id = _seed_subscription(database, account_name="other-account")
    wrong_run_id = _create_run(database, other_subscription_id)

    with pytest.raises(RepositoryError, match="sync run belongs to a different subscription"):
        MediaCrawlerIngestionService(database).ingest(
            (_record("wrong-run", None),),
            subscription_id=expected_subscription_id,
            run_id=wrong_run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )

    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(AssetRefreshSource)) == 0
        assert session.get(Subscription, expected_subscription_id).checkpoint_revision == 0  # type: ignore[union-attr]
        assert session.get(Subscription, other_subscription_id).checkpoint_revision == 0  # type: ignore[union-attr]


def test_multi_account_replacement_updates_only_observing_source_and_both_fingerprints_fence_generation(
    database: Database,
) -> None:
    first_subscription_id = _seed_subscription(database, account_name="first-account")
    second_subscription_id = _seed_subscription(database, account_name="second-account")
    original = _record(
        "shared-asset",
        None,
        asset_source_url="https://example.invalid/content/shared-original.mp4",
    )

    for subscription_id in (first_subscription_id, second_subscription_id):
        MediaCrawlerIngestionService(database).ingest(
            (original,),
            subscription_id=subscription_id,
            run_id=_create_run(database, subscription_id),
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )

    with database.session() as session:
        asset = session.scalar(select(Asset))
        assert asset is not None
        original_semantic = asset.semantic_fingerprint
        original_locator = asset.locator_fingerprint
        assert asset.generation == 1
        assert {source.subscription_id for source in AssetRefreshSourceRepository(session).list_eligible(asset.id)} == {
            first_subscription_id,
            second_subscription_id,
        }

    replacement_run_id = _create_run(database, first_subscription_id)
    MediaCrawlerIngestionService(database).ingest(
        (
            _record(
                "shared-asset",
                None,
                asset_source_url="https://example.invalid/content/shared-replacement.mp4",
            ),
        ),
        subscription_id=first_subscription_id,
        run_id=replacement_run_id,
        expected_revision=1,
        mode=IngestionMode.FORWARD,
    )

    with database.session() as session:
        asset = session.scalar(select(Asset))
        content = session.scalar(select(Content))
        assert asset is not None and content is not None
        assert asset.generation == 2
        assert asset.semantic_fingerprint != original_semantic
        assert asset.locator_fingerprint == original_locator
        sources = {
            source.subscription_id: source for source in AssetRefreshSourceRepository(session).list_for_asset(asset.id)
        }
        assert sources[first_subscription_id].last_run_id == replacement_run_id
        assert sources[first_subscription_id].observed_generation == 2
        assert sources[first_subscription_id].observed_semantic_fingerprint == asset.semantic_fingerprint
        assert sources[second_subscription_id].observed_generation == 1
        assert sources[second_subscription_id].observed_semantic_fingerprint == original_semantic
        assert [source.subscription_id for source in AssetRefreshSourceRepository(session).list_eligible(asset.id)] == [
            first_subscription_id
        ]

        semantic_before_locator_replacement = asset.semantic_fingerprint
        locator_replacement = AssetRepository(session).upsert_for_content(
            content.id,
            AssetUpsert(
                platform=Platform.BILI.value,
                content_remote_type=content.remote_type,
                content_remote_id=content.remote_id,
                remote_id=asset.remote_id,
                kind=asset.kind,
                position=asset.position,
                source_url="https://example.invalid/content/shared-replacement.mp4",
                locator=AdapterRefreshLocator(
                    adapter="mediacrawler",
                    asset_key="alternate-persisted-locator",
                ).as_dict(),
            ),
        )
        assert locator_replacement.generation == 3
        assert locator_replacement.semantic_fingerprint == semantic_before_locator_replacement
        assert locator_replacement.locator_fingerprint != original_locator
        assert AssetRefreshSourceRepository(session).list_eligible(asset.id) == []


def test_older_run_replay_never_regresses_refresh_source_run_order_or_seen_time(database: Database) -> None:
    subscription_id = _seed_subscription(database)
    initial_run_id = _create_run(database, subscription_id)
    MediaCrawlerIngestionService(database).ingest(
        (_record("run-order", None),),
        subscription_id=subscription_id,
        run_id=initial_run_id,
        expected_revision=0,
        mode=IngestionMode.FORWARD,
    )
    run_ids = sorted((_create_run(database, subscription_id), _create_run(database, subscription_id)))
    older_run_id, newer_run_id = run_ids
    equal_created_at = datetime(2027, 1, 1, tzinfo=UTC)
    newer_seen_at = equal_created_at + timedelta(hours=1)
    older_replay_seen_at = equal_created_at + timedelta(hours=2)

    with database.session() as session:
        for run_id in run_ids:
            run = session.get(SyncRun, run_id)
            assert run is not None
            run.created_at = equal_created_at

    with database.session() as session:
        asset = session.scalar(select(Asset))
        assert asset is not None
        repository = AssetRefreshSourceRepository(session)
        repository.upsert_observation(
            asset_id=asset.id,
            subscription_id=subscription_id,
            last_run_id=newer_run_id,
            seen_at=newer_seen_at,
        )
        replayed = repository.upsert_observation(
            asset_id=asset.id,
            subscription_id=subscription_id,
            last_run_id=older_run_id,
            seen_at=older_replay_seen_at,
        )
        assert replayed.last_run_id == newer_run_id
        assert replayed.last_seen_at == older_replay_seen_at


def test_mediacrawler_discovery_replay_preserves_verified_asset_bytes(database: Database) -> None:
    subscription_id = _seed_subscription(database)
    first_run_id = _create_run(database, subscription_id)
    first_url = "https://example.invalid/content/replayed?opaque=sentinel-secret-first"
    replay_url = "https://example.invalid/content/replayed?opaque=sentinel-secret-second"

    first = MediaCrawlerIngestionService(database).ingest(
        (_record("replayed", None, asset_source_url=first_url),),
        subscription_id=subscription_id,
        run_id=first_run_id,
        expected_revision=0,
        mode=IngestionMode.FORWARD,
    )
    assert first.accepted_count == 1

    with database.session() as session:
        stored = session.scalar(select(Asset))
        assert stored is not None
        stored.status = "verified"
        stored.mime_type = "video/mp4"
        stored.size_bytes = 23
        stored.checksum_sha256 = "b" * 64
        stored.local_path = "archive/sha256/bb/verified.mp4"
        original_id = stored.id
        original_generation = stored.generation
        original_locator_fingerprint = stored.locator_fingerprint

    replay_run_id = _create_run(database, subscription_id)
    replay = MediaCrawlerIngestionService(database).ingest(
        (_record("replayed", None, asset_source_url=replay_url),),
        subscription_id=subscription_id,
        run_id=replay_run_id,
        expected_revision=1,
        mode=IngestionMode.FORWARD,
    )
    assert replay.accepted_count == 1
    assert replay.discovered_count == replay.asset_count == 0

    with database.session() as session:
        stored = session.scalar(select(Asset))
        assert stored is not None
        assert stored.id == original_id
        assert stored.generation == original_generation
        assert stored.semantic_fingerprint is not None
        assert stored.locator_fingerprint == original_locator_fingerprint
        locator = parse_locator(stored.locator)
        assert isinstance(locator, AdapterRefreshLocator)
        assert locator.adapter == "mediacrawler"
        assert stored.locator_fingerprint == locator_fingerprint(locator)
        assert stored.source_url == "https://example.invalid/content/replayed"
        assert stored.status == "verified"
        assert stored.mime_type == "video/mp4"
        assert stored.size_bytes == 23
        assert stored.checksum_sha256 == "b" * 64
        assert stored.local_path == "archive/sha256/bb/verified.mp4"

    database_path_value = make_url(database.url).database
    assert database_path_value is not None
    database.dispose()
    database_path = Path(database_path_value)
    for sqlite_file in database_path.parent.glob(f"{database_path.name}*"):
        database_bytes = sqlite_file.read_bytes()
        assert b"sentinel-secret-first" not in database_bytes
        assert b"sentinel-secret-second" not in database_bytes


def test_multiple_batches_use_fresh_sessions_and_replay_idempotently(database: _TrackingDatabase) -> None:
    subscription_id = _seed_subscription(database)
    run_id = _create_run(database, subscription_id)
    newest = datetime(2026, 8, 30, 5, tzinfo=UTC)
    records = tuple(
        _record(
            f"item-{index}",
            newest if index < 2 else newest - timedelta(minutes=index),
        )
        for index in range(5)
    )
    sessions_before = database.opened_sessions

    def generated_records() -> Iterator[NormalizedMediaRecord]:
        for record in records:
            # Iterable evaluation happens before even the preflight session.
            assert database.active_sessions == 0
            yield record

    service = MediaCrawlerIngestionService(database, batch_size=2)
    first = service.ingest(
        generated_records(),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=0,
        mode=IngestionMode.FORWARD,
        continuation={"head": "complete"},
    )

    assert first.input_count == first.accepted_count == 5
    assert first.skipped_count == 0
    assert first.discovered_count == first.asset_count == 5
    assert first.committed_batches == 3
    assert first.checkpoint_revision == 3
    assert first.watermarked_at == newest
    assert first.watermark_remote_ids == ("item-0", "item-1")
    assert database.opened_sessions - sessions_before == 4  # preflight + three independent batches

    replay_run_id = _create_run(database, subscription_id)
    replay = service.ingest(
        records,
        subscription_id=subscription_id,
        run_id=replay_run_id,
        expected_revision=3,
        crawl_revision_before=0,
        mode=IngestionMode.FORWARD,
    )

    assert replay.accepted_count == 0
    assert replay.skipped_count == 5
    assert replay.discovered_count == replay.asset_count == 0
    assert replay.committed_batches == 1
    assert replay.checkpoint_revision == 4

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        run = session.get(SyncRun, run_id)
        replay_run = session.get(SyncRun, replay_run_id)
        assert subscription is not None
        assert run is not None
        assert replay_run is not None
        assert session.scalar(select(func.count()).select_from(Content)) == 5
        assert session.scalar(select(func.count()).select_from(Asset)) == 5
        assert subscription.cursor == {"head": "complete"}
        assert subscription.checkpoint_revision == 4
        assert run.checkpoint_revision_before == 0
        assert run.checkpoint_revision_after == 3
        assert run.status == RunStatus.SUCCEEDED.value
        assert run.discovered_count == 5
        assert run.updated_count == 0
        assert run.asset_count == 5
        assert replay_run.checkpoint_revision_before == 3
        assert replay_run.checkpoint_revision_after == 4
        assert replay_run.status == RunStatus.SUCCEEDED.value
        assert replay_run.discovered_count == replay_run.asset_count == 0


@pytest.mark.parametrize(
    "continuation",
    [None, {"head": "stale-recovery"}],
    ids=("explicit-clear", "explicit-mapping"),
)
def test_recovery_replay_rejects_explicit_continuation(
    database: Database,
    continuation: dict[str, object] | None,
) -> None:
    subscription_id = _seed_subscription(database, cursor={"head": "origin"})
    interleaved_at = datetime(2026, 8, 30, 5, 30, tzinfo=UTC)
    with database.session() as session:
        SubscriptionRepository(session).publish_checkpoint(
            subscription_id,
            expected_revision=0,
            cursor={"head": "interleaved"},
            watermarked_at=interleaved_at,
            watermark_remote_ids=("interleaved",),
        )
    recovery_run_id = _create_run(database, subscription_id)

    with pytest.raises(ValueError, match="continuation must be omitted"):
        MediaCrawlerIngestionService(database).ingest(
            (_record("stale-recovery", interleaved_at + timedelta(minutes=1)),),
            subscription_id=subscription_id,
            run_id=recovery_run_id,
            expected_revision=1,
            crawl_revision_before=0,
            mode=IngestionMode.FORWARD,
            continuation=continuation,
        )

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        recovery_run = session.get(SyncRun, recovery_run_id)
        assert subscription is not None
        assert recovery_run is not None
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        assert subscription.cursor == {"head": "interleaved"}
        assert subscription.checkpoint_revision == 1
        assert subscription.watermarked_at == interleaved_at
        assert subscription.watermark_remote_ids == ["interleaved"]
        assert recovery_run.status == RunStatus.INGESTING.value
        assert recovery_run.checkpoint_revision_before == 1
        assert recovery_run.checkpoint_revision_after is None


def test_late_same_timestamp_and_remote_type_namespacing(database: Database) -> None:
    subscription_id = _seed_subscription(database)
    watermark = datetime(2026, 8, 30, 4, tzinfo=UTC)
    with database.session() as session:
        SubscriptionRepository(session).publish_checkpoint(
            subscription_id,
            expected_revision=0,
            cursor={"head": "before"},
            watermarked_at=watermark,
            watermark_remote_ids=("shared-id",),
        )
    run_id = _create_run(database, subscription_id)

    result = MediaCrawlerIngestionService(database).ingest(
        (
            _record("shared-id", watermark),
            _record("shared-id", watermark, remote_type="dynamic"),
            _record("late-id", watermark),
            _record("older-id", watermark - timedelta(seconds=1)),
        ),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=1,
        mode=IngestionMode.FORWARD,
        continuation={"head": "after"},
    )

    assert result.accepted_count == 2
    assert result.skipped_count == 2
    assert result.watermarked_at == watermark
    assert result.watermark_remote_ids == ("dynamic:shared-id", "late-id", "shared-id")
    with database.session() as session:
        stored_keys = set(session.execute(select(Content.remote_type, Content.remote_id)).all())
        subscription = session.get(Subscription, subscription_id)
        assert stored_keys == {("content", "late-id"), ("dynamic", "shared-id")}
        assert subscription is not None
        assert subscription.watermark_remote_ids == ["dynamic:shared-id", "late-id", "shared-id"]


def test_backfill_and_new_head_advance_only_their_own_checkpoints(database: Database) -> None:
    scheduled_at = datetime(2026, 8, 31, tzinfo=UTC)
    subscription_id = _seed_subscription(
        database,
        cursor={"head": "h0"},
        backfill_cursor={"page": "b0"},
        next_run_at=scheduled_at,
    )
    backfill_run_id = _create_run(database, subscription_id)
    old_time = datetime(2025, 8, 30, tzinfo=UTC)

    backfill = MediaCrawlerIngestionService(database, batch_size=1).ingest(
        (_record("old-1", old_time), _record("old-2", old_time - timedelta(days=1))),
        subscription_id=subscription_id,
        run_id=backfill_run_id,
        expected_revision=0,
        mode=IngestionMode.BACKFILL,
        continuation={"page": "b1"},
    )
    assert backfill.checkpoint_revision == 2
    assert backfill.watermarked_at is None

    forward_run_id = _create_run(database, subscription_id)
    new_time = datetime(2026, 8, 30, 6, tzinfo=UTC)
    forward = MediaCrawlerIngestionService(database).ingest(
        (_record("new-head", new_time),),
        subscription_id=subscription_id,
        run_id=forward_run_id,
        expected_revision=2,
        mode=IngestionMode.FORWARD,
        continuation={"head": "h1"},
    )
    assert forward.checkpoint_revision == 3

    resumed_backfill_run_id = _create_run(database, subscription_id)
    resumed_backfill = MediaCrawlerIngestionService(database).ingest(
        (_record("old-3", old_time - timedelta(days=2)),),
        subscription_id=subscription_id,
        run_id=resumed_backfill_run_id,
        expected_revision=3,
        mode=IngestionMode.BACKFILL,
        continuation={"page": "b2"},
    )
    assert resumed_backfill.checkpoint_revision == 4

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        assert subscription.cursor == {"head": "h1"}
        assert subscription.backfill_cursor == {"page": "b2"}
        assert subscription.watermarked_at == new_time
        assert subscription.watermark_remote_ids == ["new-head"]
        assert subscription.next_run_at == scheduled_at


def test_stale_ingestion_does_not_write_records_or_newer_checkpoint(database: Database) -> None:
    scheduled_at = datetime(2026, 8, 31, tzinfo=UTC)
    subscription_id = _seed_subscription(database, next_run_at=scheduled_at)
    winner_run_id = _create_run(database, subscription_id)
    stale_run_id = _create_run(database, subscription_id)
    observed_at = datetime(2026, 8, 30, 7, tzinfo=UTC)
    service = MediaCrawlerIngestionService(database)

    winner = service.ingest(
        (_record("winner", observed_at),),
        subscription_id=subscription_id,
        run_id=winner_run_id,
        expected_revision=0,
        mode=IngestionMode.FORWARD,
        continuation={"head": "winner"},
    )
    assert winner.checkpoint_revision == 1

    with pytest.raises(StaleCheckpointError) as captured:
        service.ingest(
            (_record("stale", observed_at + timedelta(hours=1)),),
            subscription_id=subscription_id,
            run_id=stale_run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
            continuation={"head": "stale"},
        )
    assert captured.value.actual_revision == 1

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        stale_run = session.get(SyncRun, stale_run_id)
        assert subscription is not None
        assert stale_run is not None
        assert set(session.scalars(select(Content.remote_id))) == {"winner"}
        assert subscription.cursor == {"head": "winner"}
        assert subscription.watermarked_at == observed_at
        assert subscription.watermark_remote_ids == ["winner"]
        assert subscription.next_run_at == scheduled_at
        assert subscription.checkpoint_revision == 1
        assert stale_run.checkpoint_revision_before == 0
        assert stale_run.checkpoint_revision_after is None
        assert stale_run.discovered_count == stale_run.asset_count == 0


def test_final_status_failure_rolls_back_batch_and_allows_new_run_retry(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscription_id = _seed_subscription(database, cursor={"head": "before"})
    failed_run_id = _create_run(database, subscription_id)
    observed_at = datetime(2026, 8, 30, 7, 30, tzinfo=UTC)
    first_record = _record("finalize-first", observed_at)
    final_record = _record("finalize-final", observed_at + timedelta(minutes=1))
    original_set_status = SyncRunRepository.set_status

    def fail_succeeded_status(
        self: SyncRunRepository,
        target_run_id: str,
        status: str,
        *,
        expected_status: str,
        message: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        at: datetime | None = None,
    ) -> SyncRun:
        if status == RunStatus.SUCCEEDED.value:
            raise RepositoryError("injected succeeded-status failure")
        return original_set_status(
            self,
            target_run_id,
            status,
            expected_status=expected_status,
            message=message,
            error_code=error_code,
            error_message=error_message,
            at=at,
        )

    monkeypatch.setattr(SyncRunRepository, "set_status", fail_succeeded_status)
    with pytest.raises(RepositoryError, match="injected succeeded-status failure"):
        MediaCrawlerIngestionService(database, batch_size=1).ingest(
            # The service must commit the older batch before finalization of
            # the second batch fails, even when the crawl is newest-first.
            (final_record, first_record),
            subscription_id=subscription_id,
            run_id=failed_run_id,
            expected_revision=0,
            crawl_revision_before=0,
            mode=IngestionMode.FORWARD,
        )
    monkeypatch.setattr(SyncRunRepository, "set_status", original_set_status)

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        failed_run = session.get(SyncRun, failed_run_id)
        assert subscription is not None
        assert failed_run is not None
        assert set(session.scalars(select(Content.remote_id))) == {first_record.content.remote_id}
        assert session.scalar(select(func.count()).select_from(Asset)) == 1
        assert subscription.cursor == {"head": "before"}
        assert subscription.checkpoint_revision == 1
        assert subscription.watermarked_at == first_record.content.published_at
        assert subscription.watermark_remote_ids == [first_record.content.remote_id]
        assert failed_run.status == RunStatus.INGESTING.value
        assert failed_run.checkpoint_revision_before == 0
        assert failed_run.checkpoint_revision_after == 1
        assert failed_run.cursor_after == {"head": "before"}
        assert failed_run.discovered_count == 1
        assert failed_run.asset_count == 1

    with database.session() as session:
        SyncRunRepository(session).set_status(
            failed_run_id,
            RunStatus.FAILED_RETRYABLE.value,
            expected_status=RunStatus.INGESTING.value,
            error_code="ingestion_failed",
        )

    retry_run_id = _create_run(database, subscription_id)
    retried = MediaCrawlerIngestionService(database, batch_size=1).ingest(
        (final_record, first_record),
        subscription_id=subscription_id,
        run_id=retry_run_id,
        expected_revision=1,
        crawl_revision_before=0,
        mode=IngestionMode.FORWARD,
    )
    assert retried.accepted_count == 1
    assert retried.skipped_count == 1
    assert retried.discovered_count == retried.asset_count == 1
    assert retried.checkpoint_revision == 2

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        failed_run = session.get(SyncRun, failed_run_id)
        retry_run = session.get(SyncRun, retry_run_id)
        assert subscription is not None
        assert failed_run is not None
        assert retry_run is not None
        assert set(session.scalars(select(Content.remote_id))) == {
            first_record.content.remote_id,
            final_record.content.remote_id,
        }
        assert session.scalar(select(func.count()).select_from(Asset)) == 2
        assert subscription.cursor == {"head": "before"}
        assert subscription.checkpoint_revision == 2
        assert subscription.watermarked_at == final_record.content.published_at
        assert subscription.watermark_remote_ids == [final_record.content.remote_id]
        assert failed_run.status == RunStatus.FAILED_RETRYABLE.value
        assert failed_run.checkpoint_revision_after == 1
        assert failed_run.discovered_count == failed_run.asset_count == 1
        assert retry_run.status == RunStatus.SUCCEEDED.value
        assert retry_run.checkpoint_revision_before == 1
        assert retry_run.checkpoint_revision_after == 2
        assert retry_run.discovered_count == retry_run.asset_count == 1


def test_partial_forward_failure_interleaved_with_newer_run_recovers_missing_older_item(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscription_id = _seed_subscription(database)
    first_run_id = _create_run(database, subscription_id)
    base = datetime(2026, 8, 30, 8, tzinfo=UTC)
    older = _record("receipt-a-older", base)
    newer = _record("receipt-a-newer", base + timedelta(minutes=1))
    original_upsert = ingestion_module._upsert_batch
    calls = 0

    def fail_second_batch(session: Session, records: tuple[NormalizedMediaRecord, ...]) -> tuple[int, int]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RepositoryError("injected second-batch failure")
        return original_upsert(session, records)

    monkeypatch.setattr(ingestion_module, "_upsert_batch", fail_second_batch)
    with pytest.raises(RepositoryError, match="injected second-batch failure"):
        MediaCrawlerIngestionService(database, batch_size=1).ingest(
            # Deliberately newest-first, matching common upstream ordering.
            (newer, older),
            subscription_id=subscription_id,
            run_id=first_run_id,
            expected_revision=0,
            crawl_revision_before=0,
            mode=IngestionMode.FORWARD,
        )
    monkeypatch.setattr(ingestion_module, "_upsert_batch", original_upsert)

    with database.session() as session:
        failed_repository = SyncRunRepository(session)
        failed_repository.set_status(
            first_run_id,
            RunStatus.FAILED_RETRYABLE.value,
            expected_status=RunStatus.INGESTING.value,
            error_code="ingestion_failed",
        )
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        assert subscription.checkpoint_revision == 1
        assert subscription.watermarked_at == older.content.published_at
        assert set(session.scalars(select(Content.remote_id))) == {older.content.remote_id}

    interleaved_run_id = _create_run(database, subscription_id)
    interleaved = _record("receipt-b-newest", base + timedelta(minutes=2))
    interleaved_result = MediaCrawlerIngestionService(database).ingest(
        (interleaved,),
        subscription_id=subscription_id,
        run_id=interleaved_run_id,
        expected_revision=1,
        crawl_revision_before=1,
        mode=IngestionMode.FORWARD,
    )
    assert interleaved_result.checkpoint_revision == 2

    recovery_run_id = _create_run(database, subscription_id)
    recovered = MediaCrawlerIngestionService(database, batch_size=1).ingest(
        (newer, older),
        subscription_id=subscription_id,
        run_id=recovery_run_id,
        expected_revision=2,
        crawl_revision_before=0,
        mode=IngestionMode.FORWARD,
    )
    assert recovered.accepted_count == 1
    assert recovered.skipped_count == 1
    assert recovered.discovered_count == recovered.asset_count == 1
    assert recovered.checkpoint_revision == 3

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        recovery_run = session.get(SyncRun, recovery_run_id)
        assert subscription is not None
        assert recovery_run is not None
        assert set(session.scalars(select(Content.remote_id))) == {
            older.content.remote_id,
            newer.content.remote_id,
            interleaved.content.remote_id,
        }
        assert subscription.watermarked_at == interleaved.content.published_at
        assert subscription.watermark_remote_ids == [interleaved.content.remote_id]
        assert recovery_run.status == RunStatus.SUCCEEDED.value
        assert recovery_run.checkpoint_revision_before == 2
        assert recovery_run.checkpoint_revision_after == 3


def test_ownership_guard_fences_every_ingestion_transaction_before_mutation(database: Database) -> None:
    subscription_id = _seed_subscription(database)
    run_id = _create_run(database, subscription_id)
    base = datetime(2026, 8, 30, 8, 30, tzinfo=UTC)
    older = _record("guarded-older", base)
    newer = _record("guarded-newer", base + timedelta(minutes=1))
    guarded_sessions: list[Session] = []

    def guard(session: Session) -> None:
        guarded_sessions.append(session)
        if len(guarded_sessions) == 3:
            raise RepositoryError("injected ownership loss")

    with pytest.raises(RepositoryError, match="injected ownership loss"):
        MediaCrawlerIngestionService(database, batch_size=1).ingest(
            (newer, older),
            subscription_id=subscription_id,
            run_id=run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
            ownership_guard=guard,
        )

    assert len(guarded_sessions) == 3
    assert len({id(session) for session in guarded_sessions}) == 3
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        run = session.get(SyncRun, run_id)
        assert subscription is not None and run is not None
        assert set(session.scalars(select(Content.remote_id))) == {older.content.remote_id}
        assert subscription.checkpoint_revision == 1
        assert run.checkpoint_revision_after == 1
        assert run.status == RunStatus.INGESTING.value


def test_omitted_continuation_preserves_forward_and_backfill_cursors(database: Database) -> None:
    subscription_id = _seed_subscription(
        database,
        cursor={"head": "keep"},
        backfill_cursor={"page": "keep"},
    )
    forward_run_id = _create_run(database, subscription_id)
    MediaCrawlerIngestionService(database).ingest(
        (_record("preserve-forward", datetime(2026, 8, 30, 9, tzinfo=UTC)),),
        subscription_id=subscription_id,
        run_id=forward_run_id,
        expected_revision=0,
        mode=IngestionMode.FORWARD,
    )
    backfill_run_id = _create_run(database, subscription_id)
    MediaCrawlerIngestionService(database).ingest(
        (_record("preserve-backfill", datetime(2025, 8, 30, 9, tzinfo=UTC)),),
        subscription_id=subscription_id,
        run_id=backfill_run_id,
        expected_revision=1,
        mode=IngestionMode.BACKFILL,
    )

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        assert subscription.cursor == {"head": "keep"}
        assert subscription.backfill_cursor == {"page": "keep"}
