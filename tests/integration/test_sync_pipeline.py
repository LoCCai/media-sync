"""End-to-end synchronization coverage through the real SQLite adapter."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from media_sync.adapters.fake import FakePlatformAdapter
from media_sync.application import SyncRequest, SyncService
from media_sync.domain import (
    AccountRef,
    AssetKind,
    AssetSnapshot,
    ContentSnapshot,
    LoginMethod,
    Platform,
    RunStatus,
)
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    SQLAlchemySyncRepository,
    SubscriptionRepository,
)
from media_sync.infrastructure.db.models import Asset, Author, Content, RunEvent, Subscription, SyncRun
from media_sync.media.locator import AdapterRefreshLocator, DirectLocator, locator_fingerprint, parse_locator


def _database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(_database_url(tmp_path / "sync-pipeline.sqlite3"))
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_subscription(database: Database) -> tuple[AccountRef, UUID]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=Platform.BILI.value,
            adapter="fake",
            display_name="integration-account",
            login_method=LoginMethod.COOKIE.value,
            auth_status="authenticated",
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=Platform.BILI.value,
                remote_id="creator-001",
                display_name="Seed creator",
            )
        )
        subscription = SubscriptionRepository(session).create(account_id=account.id, author_id=author.id)
        return (
            AccountRef(
                account_id=UUID(account.id),
                platform=Platform.BILI,
                login_method=LoginMethod.COOKIE,
                adapter="fake",
            ),
            UUID(subscription.id),
        )


@pytest.mark.asyncio
async def test_fake_sync_twice_persists_normalized_incremental_state(database: Database) -> None:
    account, subscription_id = _seed_subscription(database)
    adapter = FakePlatformAdapter()

    with database.session() as session:
        first = await SyncService(adapter, SQLAlchemySyncRepository(session)).run(
            SyncRequest(
                subscription_id=subscription_id,
                account=account,
                creator_reference="creator-001",
                max_items=3,
                page_size=2,
            )
        )
        assert first.status is RunStatus.SUCCEEDED
        assert first.processed_count == 3
        assert first.final_cursor is not None

    with database.session() as session:
        second = await SyncService(adapter, SQLAlchemySyncRepository(session)).run(
            SyncRequest(
                subscription_id=subscription_id,
                account=account,
                creator_reference="creator-001",
                cursor=first.final_cursor,
                max_items=3,
                page_size=2,
            )
        )
        assert second.status is RunStatus.SUCCEEDED
        assert second.processed_count == 1
        assert second.final_cursor is None

    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Author)) == 1
        assert session.scalar(select(func.count()).select_from(Content)) == 4
        assert session.scalar(select(func.count()).select_from(Asset)) == 4
        assert session.scalar(select(func.count()).select_from(SyncRun)) == 2
        assert session.scalar(select(func.count()).select_from(RunEvent)) == 10
        assert all(isinstance(parse_locator(asset.locator), DirectLocator) for asset in session.scalars(select(Asset)))

        subscription = session.get(Subscription, str(subscription_id))
        assert subscription is not None
        assert subscription.cursor is None
        assert subscription.cursor_version == 1
        assert subscription.checkpoint_revision == 2
        assert subscription.watermarked_at == first.watermark == second.watermark
        assert subscription.watermark_remote_ids == [
            "item-001",
            "item-003",
            "item-004",
            "item-duplicate",
        ]

        first_run = session.get(SyncRun, str(first.run_id))
        second_run = session.get(SyncRun, str(second.run_id))
        assert first_run is not None
        assert second_run is not None
        expected_cursor = {"value": first.final_cursor.value}
        assert first_run.cursor_before is None
        assert first_run.cursor_after == expected_cursor
        assert first_run.checkpoint_revision_before == 0
        assert first_run.checkpoint_revision_after == 1
        assert second_run.cursor_before == expected_cursor
        assert second_run.cursor_after is None
        assert second_run.checkpoint_revision_before == 1
        assert second_run.checkpoint_revision_after == 2
        assert first_run.status == second_run.status == RunStatus.SUCCEEDED.value
        assert first_run.discovered_count == first.processed_count == 3
        assert first_run.updated_count == 0
        assert first_run.asset_count == first.asset_count == 3
        assert second_run.discovered_count == second.processed_count == 1
        assert second_run.updated_count == 0
        assert second_run.asset_count == second.asset_count == 1

        for run_id in (first_run.id, second_run.id):
            events = list(
                session.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.sequence))
            )
            assert [event.sequence for event in events] == [1, 2, 3, 4, 5]
            assert [event.to_status for event in events] == [
                RunStatus.QUEUED.value,
                RunStatus.CLAIMED.value,
                RunStatus.RUNNING.value,
                RunStatus.INGESTING.value,
                RunStatus.SUCCEEDED.value,
            ]


@pytest.mark.asyncio
async def test_fake_discovery_replay_preserves_verified_asset_bytes(database: Database) -> None:
    account, subscription_id = _seed_subscription(database)
    first_url = "https://fixture.invalid/bili/assets/item-001/000.jpg?quality=720"
    replay_url = "https://fixture.invalid/bili/assets/item-001/000.jpg?quality=1080"

    def adapter(source_url: str) -> FakePlatformAdapter:
        return FakePlatformAdapter(
            assets={
                "item-001": (
                    AssetSnapshot(
                        platform=Platform.BILI,
                        remote_id="item-001-asset-000",
                        content_remote_id="item-001",
                        kind=AssetKind.IMAGE,
                        source_url=source_url,
                        mime_type="image/jpeg",
                    ),
                )
            }
        )

    request = SyncRequest(
        subscription_id=subscription_id,
        account=account,
        creator_reference="creator-001",
        max_items=1,
        page_size=1,
    )
    with database.session() as session:
        first = await SyncService(adapter(first_url), SQLAlchemySyncRepository(session)).run(request)
        assert first.status is RunStatus.SUCCEEDED

    with database.session() as session:
        stored = session.scalar(select(Asset))
        assert stored is not None
        stored.status = "verified"
        stored.mime_type = "image/jpeg"
        stored.size_bytes = 17
        stored.checksum_sha256 = "a" * 64
        stored.local_path = "archive/sha256/aa/verified.jpg"
        original_id = stored.id
        original_generation = stored.generation
        original_locator_fingerprint = stored.locator_fingerprint

    with database.session() as session:
        replay = await SyncService(adapter(replay_url), SQLAlchemySyncRepository(session)).run(request)
        assert replay.status is RunStatus.SUCCEEDED

    with database.session() as session:
        stored = session.scalar(select(Asset))
        assert stored is not None
        assert stored.id == original_id
        assert stored.generation == original_generation
        assert stored.semantic_fingerprint is not None
        assert stored.locator_fingerprint == original_locator_fingerprint
        parsed_locator = parse_locator(stored.locator)
        assert isinstance(parsed_locator, AdapterRefreshLocator)
        assert stored.locator_fingerprint == locator_fingerprint(parsed_locator)
        assert stored.source_url == "https://fixture.invalid/bili/assets/item-001/000.jpg"
        assert stored.status == "verified"
        assert stored.mime_type == "image/jpeg"
        assert stored.size_bytes == 17
        assert stored.checksum_sha256 == "a" * 64
        assert stored.local_path == "archive/sha256/aa/verified.jpg"


class _FailOnSecondContentRepository(SQLAlchemySyncRepository):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.write_count = 0

    def upsert_content_with_assets(
        self,
        snapshot: ContentSnapshot,
        assets: Sequence[AssetSnapshot],
    ) -> UUID:
        self.write_count += 1
        if self.write_count == 2:
            raise RuntimeError("injected second content write failure")
        return super().upsert_content_with_assets(snapshot, assets)


class _AbortFailedSync(RuntimeError):
    pass


@pytest.mark.asyncio
async def test_failed_second_write_can_roll_back_the_complete_outer_transaction(database: Database) -> None:
    account, subscription_id = _seed_subscription(database)

    with pytest.raises(_AbortFailedSync, match="reject failed synchronization"), database.session() as session:
        repository = _FailOnSecondContentRepository(session)
        result = await SyncService(FakePlatformAdapter(), repository).run(
            SyncRequest(
                subscription_id=subscription_id,
                account=account,
                creator_reference="creator-001",
                max_items=4,
                page_size=2,
            )
        )

        assert repository.write_count == 2
        assert result.status is RunStatus.FAILED_RETRYABLE
        assert result.error_code == "unexpected_failure"
        assert session.scalar(select(func.count()).select_from(Content)) == 1
        assert session.scalar(select(func.count()).select_from(SyncRun)) == 1

        # SyncService classifies ordinary exceptions as a result.  The
        # transaction owner converts that unsuccessful outcome back into
        # an exception, making Database.session roll back the whole run.
        raise _AbortFailedSync("reject failed synchronization")

    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Author)) == 1
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(SyncRun)) == 0
        assert session.scalar(select(func.count()).select_from(RunEvent)) == 0

        subscription = session.get(Subscription, str(subscription_id))
        assert subscription is not None
        assert subscription.cursor is None
        assert subscription.checkpoint_revision == 0
        assert subscription.watermarked_at is None
        assert subscription.watermark_remote_ids == []
