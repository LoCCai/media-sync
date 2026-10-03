from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select

from media_sync.domain import AuthStatus, LoginMethod, Platform, RunStatus
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    MediaCrawlerIngestionService,
    RepositoryError,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import Content, Subscription, SyncRun, SyncRunContent
from media_sync.integrations.mediacrawler.douyin_creator_work import (
    DouyinCreatorPage,
    DouyinScanCoverage,
    DouyinScanState,
    DouyinScanUnit,
    DouyinWorkIdentity,
)
from media_sync.integrations.mediacrawler.normalizers import NormalizationContext, normalize_record
from media_sync.integrations.mediacrawler.subscription_policy import MediaCrawlerSubscriptionPolicy

NOW = datetime(2026, 9, 10, 9, 0, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
SEC_USER_ID = "MS4wLjABAAAA0123456789abcdefghijklmnopqrstuv"
CREATOR_REFERENCE = f"https://www.douyin.com/user/{SEC_USER_ID}"


@pytest.fixture
def database(tmp_path: Path) -> Database:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'douyin-ingestion.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed(database: Database, *, max_items: int = 18) -> tuple[str, str, DouyinScanState]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="dy",
            adapter="mediacrawler",
            display_name="Douyin bounded ingestion",
            login_method=LoginMethod.SAVED_SESSION.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="dy", remote_id=SEC_USER_ID, display_name="Douyin Creator")
        )
        policy = MediaCrawlerSubscriptionPolicy(
            allow_full_history=True,
            request_delay_seconds=2,
            headless=True,
            creator_secret_ref="env:DY_CREATOR_REFERENCE",
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            max_items=max_items,
            policy={"mediacrawler": policy.to_payload()},
        )
        state = DouyinScanState.initial(
            UUID(account.id),
            hashlib.sha256(SEC_USER_ID.encode()).hexdigest(),
            hashlib.sha256(CREATOR_REFERENCE.encode()).hexdigest(),
            UPSTREAM_SHA,
        )
        run = SyncRunRepository(session).create(
            subscription_id=subscription.id,
            cursor_before=None,
            checkpoint_revision_before=0,
        )
        runs = SyncRunRepository(session)
        runs.set_status(run.id, RunStatus.CLAIMED.value, expected_status=RunStatus.QUEUED.value)
        runs.set_status(run.id, RunStatus.RUNNING.value, expected_status=RunStatus.CLAIMED.value)
        runs.set_status(run.id, RunStatus.INGESTING.value, expected_status=RunStatus.RUNNING.value)
        return subscription.id, run.id, state


def _identity(index: int) -> DouyinWorkIdentity:
    return DouyinWorkIdentity(
        aweme_id=f"{index:019d}",
        listing_sha256=hashlib.sha256(f"listing-{index}".encode()).hexdigest(),
    )


def _record(index: int):
    aweme_id = f"{index:019d}"
    return normalize_record(
        {
            "aweme_id": aweme_id,
            "desc": f"bounded Douyin fixture {index}",
            "create_time": 1_788_235_200 + index,
            "video_download_url": "",
            "note_download_url": "",
            "music_download_url": "",
            "cover_url": "",
        },
        NormalizationContext(Platform.DY, SEC_USER_ID, "Douyin Creator", UPSTREAM_SHA, NOW),
    )


def _coverage(state: DouyinScanState, indexes: range, *, has_more: bool, next_cursor: str) -> DouyinScanCoverage:
    page = DouyinCreatorPage("", next_cursor, has_more, tuple(_identity(index) for index in indexes))
    unit = DouyinScanUnit(state, 18)
    unit.observe_page(page)
    for item in page.identities:
        unit.store(item)
    return unit.coverage()


def test_douyin_page_records_cursor_run_and_contents_in_one_commit(database: Database) -> None:
    subscription_id, run_id, state = _seed(database)
    coverage = _coverage(state, range(3), has_more=True, next_cursor="echo-next/==")
    result = MediaCrawlerIngestionService(database).ingest_douyin_bounded(
        tuple(_record(index) for index in range(3)),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=0,
        input_cursor=None,
        next_cursor=coverage.next_state.to_cursor(),
        coverage=coverage,
    )
    assert (result.accepted_count, result.discovered_count, result.committed_batches) == (3, 3, 1)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        run = session.get(SyncRun, run_id)
        assert subscription is not None and subscription.cursor == {"value": coverage.next_state.to_cursor()}
        assert subscription.checkpoint_revision == 1
        assert run is not None and run.status == "succeeded" and run.cursor_after == subscription.cursor
        observed = tuple(
            session.scalars(
                select(SyncRunContent).where(SyncRunContent.run_id == run_id).order_by(SyncRunContent.position)
            ).all()
        )
        assert [row.position for row in observed] == [0, 1, 2]
        assert session.scalar(select(func.count()).select_from(Content)) == 3

    replay = MediaCrawlerIngestionService(database).ingest_douyin_bounded(
        tuple(_record(index) for index in range(3)),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=0,
        input_cursor=None,
        next_cursor=coverage.next_state.to_cursor(),
        coverage=coverage,
    )
    assert (replay.accepted_count, replay.discovered_count, replay.committed_batches) == (0, 0, 0)


def test_douyin_access_restriction_commits_no_source_end_or_content(database: Database) -> None:
    subscription_id, run_id, state = _seed(database)
    unit = DouyinScanUnit(state, 18)
    unit.observe_access_restricted()
    coverage = unit.coverage()
    result = MediaCrawlerIngestionService(database).ingest_douyin_bounded(
        (),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=0,
        input_cursor=None,
        next_cursor=coverage.next_state.to_cursor(),
        coverage=coverage,
    )
    assert result.accepted_count == result.discovered_count == 0
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        state_after = DouyinScanState.from_cursor(subscription.cursor["value"])
        assert state_after.last_unit is not None
        assert state_after.last_unit.stop_reason == "access_restricted"
        assert state_after.head_boundary is None


def test_douyin_ingestion_rejects_record_not_proven_by_page(database: Database) -> None:
    subscription_id, run_id, state = _seed(database)
    coverage = _coverage(state, range(1), has_more=False, next_cursor="")
    with pytest.raises(RepositoryError, match="scan evidence"):
        MediaCrawlerIngestionService(database).ingest_douyin_bounded(
            (_record(2),),
            subscription_id=subscription_id,
            run_id=run_id,
            expected_revision=0,
            input_cursor=None,
            next_cursor=coverage.next_state.to_cursor(),
            coverage=coverage,
        )
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        run = session.get(SyncRun, run_id)
        assert subscription is not None and subscription.checkpoint_revision == 0 and subscription.cursor is None
        assert run is not None and run.status == "ingesting"
        assert session.scalar(select(func.count()).select_from(Content)) == 0
