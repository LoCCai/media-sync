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
from media_sync.integrations.mediacrawler.kuaishou_creator_work import (
    KuaishouCreatorPage,
    KuaishouScanCoverage,
    KuaishouScanState,
    KuaishouScanUnit,
    KuaishouWorkIdentity,
)
from media_sync.integrations.mediacrawler.normalizers import NormalizationContext, normalize_record
from media_sync.integrations.mediacrawler.subscription_policy import MediaCrawlerSubscriptionPolicy

NOW = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
USER_ID = "3x4sm73aye7jq7i"
CREATOR_REFERENCE = f"https://www.kuaishou.com/profile/{USER_ID}"


@pytest.fixture
def database(tmp_path: Path) -> Database:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'kuaishou-ingestion.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed(database: Database, *, max_items: int = 18) -> tuple[str, str, KuaishouScanState]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="ks",
            adapter="mediacrawler",
            display_name="Kuaishou bounded ingestion",
            login_method=LoginMethod.SAVED_SESSION.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="ks", remote_id=USER_ID, display_name="Kuaishou Creator")
        )
        policy = MediaCrawlerSubscriptionPolicy(
            allow_full_history=True,
            request_delay_seconds=2,
            headless=True,
            creator_secret_ref="env:KS_CREATOR_REFERENCE",
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            max_items=max_items,
            policy={"mediacrawler": policy.to_payload()},
        )
        state = KuaishouScanState.initial(
            UUID(account.id),
            hashlib.sha256(USER_ID.encode()).hexdigest(),
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


def _photo_id(index: int) -> str:
    return f"3x{index:013x}"


def _identity(index: int) -> KuaishouWorkIdentity:
    return KuaishouWorkIdentity(
        photo_id=_photo_id(index),
        listing_sha256=hashlib.sha256(f"listing-{index}".encode()).hexdigest(),
    )


def _record(index: int):
    return normalize_record(
        {
            "video_id": _photo_id(index),
            "desc": f"bounded Kuaishou fixture {index}",
            "title": f"bounded Kuaishou fixture {index}",
            "create_time": 1_788_235_200 + index,
            "liked_count": "0",
            "viewd_count": "0",
            "video_url": f"https://www.kuaishou.com/short-video/{_photo_id(index)}",
            "video_cover_url": "",
            "video_play_url": "",
        },
        NormalizationContext(Platform.KS, USER_ID, "Kuaishou Creator", UPSTREAM_SHA, NOW),
    )


def _coverage(state: KuaishouScanState, indexes: range, next_cursor: str) -> KuaishouScanCoverage:
    page = KuaishouCreatorPage("", next_cursor, tuple(_identity(index) for index in indexes))
    unit = KuaishouScanUnit(state, 18)
    unit.observe_page(page)
    for item in page.identities:
        unit.store(item)
    return unit.coverage()


def test_kuaishou_page_records_cursor_run_and_contents_in_one_commit(database: Database) -> None:
    subscription_id, run_id, state = _seed(database)
    coverage = _coverage(state, range(3), next_cursor="echo-next/==")
    result = MediaCrawlerIngestionService(database).ingest_kuaishou_bounded(
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

    replay = MediaCrawlerIngestionService(database).ingest_kuaishou_bounded(
        tuple(_record(index) for index in range(3)),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=0,
        input_cursor=None,
        next_cursor=coverage.next_state.to_cursor(),
        coverage=coverage,
    )
    assert (replay.accepted_count, replay.discovered_count, replay.committed_batches) == (0, 0, 0)


def test_kuaishou_access_restriction_commits_no_source_end_or_content(database: Database) -> None:
    subscription_id, run_id, state = _seed(database)
    unit = KuaishouScanUnit(state, 18)
    unit.observe_access_restricted()
    coverage = unit.coverage()
    result = MediaCrawlerIngestionService(database).ingest_kuaishou_bounded(
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
        state_after = KuaishouScanState.from_cursor(subscription.cursor["value"])
        assert state_after.last_unit is not None
        assert state_after.last_unit.stop_reason == "access_restricted"
        assert state_after.head_boundary is None


def test_kuaishou_ingestion_rejects_record_not_proven_by_page(database: Database) -> None:
    subscription_id, run_id, state = _seed(database)
    coverage = _coverage(state, range(1), next_cursor="echo-0")
    with pytest.raises(RepositoryError, match="scan evidence"):
        MediaCrawlerIngestionService(database).ingest_kuaishou_bounded(
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
