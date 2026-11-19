"""Zhihu delivery progress transitions driven only by closed pipeline receipts."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from media_sync.domain import AuthStatus, LoginMethod, Platform
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    MediaCrawlerIngestionService,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import Job, Subscription, SyncRun, SyncRunContent, ZhihuSubscriptionProgress
from media_sync.integrations.mediacrawler.normalizers import NormalizationContext, normalize_record
from media_sync.integrations.mediacrawler.subscription_policy import MediaCrawlerSubscriptionPolicy
from media_sync.integrations.mediacrawler.zhihu_creator_work import (
    ZhihuCreatorPage,
    ZhihuScanState,
    ZhihuScanUnit,
    ZhihuWorkIdentity,
)
from media_sync.scheduler.pipeline_receipt import PipelineDeliveryReceipt
from media_sync.scheduler.zhihu_delivery_progress import (
    ZHIHU_ACCESS_RESTRICTED_BLOCKED_CODE,
    ZhihuDeliveryProgressRepository,
    zhihu_delivery_progress_payload,
    zhihu_policy_fingerprint,
)

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
URL_TOKEN = "zhihu-url-token"
CREATOR_URL = f"https://www.zhihu.com/people/{URL_TOKEN}"
AUTHOR_SHA = hashlib.sha256(URL_TOKEN.encode()).hexdigest()
CREATOR_SHA = hashlib.sha256(CREATOR_URL.encode()).hexdigest()
ANSWER_ONE = "8200000001"
ANSWER_TWO = "8200000002"


@pytest.fixture
def database(tmp_path: Path) -> Database:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'zhihu-delivery.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _identity(content_id: str) -> ZhihuWorkIdentity:
    return ZhihuWorkIdentity(
        content_id=content_id,
        listing_sha256=hashlib.sha256(f"listing-{content_id}".encode()).hexdigest(),
    )


def _seed(database: Database) -> str:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="zhihu",
            adapter="mediacrawler",
            display_name="Execution 0086 Zhihu",
            login_method=LoginMethod.COOKIE.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="zhihu", remote_id=URL_TOKEN, display_name="Execution 0086 creator")
        )
        policy = MediaCrawlerSubscriptionPolicy(
            allow_full_history=True,
            request_delay_seconds=2,
            headless=True,
            creator_secret_ref="env:EXECUTION0086_ZHIHU_CREATOR",
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            interval_seconds=21_600,
            max_items=20,
            policy={"mediacrawler": policy.to_payload()},
        )
        row = ZhihuDeliveryProgressRepository(session).ensure_for_materialization(
            subscription,
            upstream_sha=UPSTREAM_SHA,
            schedule_revision=0,
            now=NOW,
            resume_blocked=False,
        )
        assert row is not None
        return subscription.id


def _records(content_ids: tuple[str, ...]):
    now = datetime.now(UTC)
    return tuple(
        normalize_record(
            {
                "content_id": content_id,
                "content_type": "answer",
                "content_text": f"body {content_id}",
                "content_url": f"https://www.zhihu.com/question/1/answer/{content_id}",
                "created_time": 1_788_235_200,
                "voteup_count": 0,
                "comment_count": 0,
            },
            NormalizationContext(Platform.ZHIHU, URL_TOKEN, "Zhihu Creator", UPSTREAM_SHA, now),
        )
        for content_id in content_ids
    )


def _start_run(database: Database, subscription_id: str) -> tuple[SyncRun, str | None, int]:
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        cursor = subscription.cursor
        before_value = cursor.get("value") if isinstance(cursor, dict) else None
        revision = subscription.checkpoint_revision
        policy_fingerprint = zhihu_policy_fingerprint(subscription.policy, subscription.max_items)
        run = SyncRunRepository(session).create(
            subscription_id=subscription_id,
            cursor_before=None if before_value is None else {"value": before_value},
            checkpoint_revision_before=revision,
            manifest={
                "creator_fingerprint_sha256": CREATOR_SHA,
                "upstream_sha": UPSTREAM_SHA,
                "account_revision": 0,
                "policy_fingerprint_sha256": policy_fingerprint,
            },
        )
        runs = SyncRunRepository(session)
        for old, new in (("queued", "claimed"), ("claimed", "running"), ("running", "ingesting")):
            runs.set_status(run.id, new, expected_status=old)
        return run, before_value, revision


def _run_unit(
    database: Database,
    subscription_id: str,
    content_ids: tuple[str, ...],
    *,
    is_end: bool,
) -> SyncRun:
    run, before_value, revision = _start_run(database, subscription_id)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        account_id = subscription.account_id
    state = ZhihuScanState.for_cursor(
        before_value,
        account_id=UUID(account_id),
        author_fingerprint_sha256=AUTHOR_SHA,
        creator_fingerprint_sha256=CREATOR_SHA,
        upstream_sha=UPSTREAM_SHA,
    )
    unit = ZhihuScanUnit(state, 20)
    limit = unit.next_action().limit or 20
    page = ZhihuCreatorPage(state.offset, limit, is_end, tuple(_identity(value) for value in content_ids))
    unit.observe_page(page)
    while (action := unit.next_action()).kind in {"detail", "unchanged"}:
        identity = action.identity
        assert identity is not None
        if action.kind == "unchanged":
            unit.skip_unchanged(identity)
        else:
            unit.store(identity)
    coverage = unit.coverage()
    MediaCrawlerIngestionService(database).ingest_zhihu_bounded(
        _records(tuple(identity.content_id for identity in coverage.successful)),
        subscription_id=subscription_id,
        run_id=run.id,
        expected_revision=revision,
        input_cursor=before_value,
        next_cursor=coverage.next_state.to_cursor(),
        coverage=coverage,
    )
    with database.session() as session:
        run = session.get(SyncRun, run.id)
        assert run is not None
        session.expunge(run)
        return run


def _run_unit_restricted(database: Database, subscription_id: str) -> SyncRun:
    run, before_value, revision = _start_run(database, subscription_id)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        state = ZhihuScanState.initial(UUID(subscription.account_id), AUTHOR_SHA, CREATOR_SHA, UPSTREAM_SHA)
    unit = ZhihuScanUnit(state, 20)
    unit.observe_access_restricted()
    coverage = unit.coverage()
    MediaCrawlerIngestionService(database).ingest_zhihu_bounded(
        (),
        subscription_id=subscription_id,
        run_id=run.id,
        expected_revision=revision,
        input_cursor=before_value,
        next_cursor=coverage.next_state.to_cursor(),
        coverage=coverage,
    )
    with database.session() as session:
        run = session.get(SyncRun, run.id)
        assert run is not None
        session.expunge(run)
        return run


def _publish_source_and_pipeline(
    database: Database,
    subscription_id: str,
    run: SyncRun,
    *,
    natural_suffix: str,
) -> tuple[Job, PipelineDeliveryReceipt]:
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        count = session.scalar(
            select(func.count())
            .select_from(SyncRunContent)
            .where(
                SyncRunContent.run_id == run.id,
                SyncRunContent.subscription_id == subscription_id,
            )
        )
        source = Job(
            id=str(uuid4()),
            job_type="sync.subscription",
            natural_key=f"source-{natural_suffix}:{run.id}",
            subscription_id=subscription_id,
            run_id=run.id,
            payload={
                "schema_version": 1,
                "subscription_id": subscription_id,
                "schedule_revision": 0,
                "retry_policy": {},
            },
            status="succeeded",
            max_attempts=1,
        )
        session.add(source)
        export = Job(
            id=str(uuid4()),
            job_type="export.emby",
            natural_key=f"zhihu-test-export-{natural_suffix}:{run.id}",
            payload={"author_id": subscription.author_id, "result": {"managed_file_count": count + 1}},
            status="succeeded",
            max_attempts=1,
        )
        session.add(export)
        session.flush()
        receipt = PipelineDeliveryReceipt(
            subscription_id=subscription_id,
            account_id=subscription.account_id,
            author_id=subscription.author_id,
            platform="zhihu",
            export_job_id=export.id,
            selected_asset_count=0,
            verified_asset_count=0,
            downloaded_count=0,
            already_verified_count=0,
            publication_disposition="published",
            managed_file_count=count + 1,
            directory_verified=True,
            schema_version=2,
            source_run_id=run.id,
            observed_content_count=count,
            delivered_content_count=count,
        )
        pipeline = Job(
            id=str(uuid4()),
            job_type="pipeline.subscription",
            natural_key=f"pipeline-{natural_suffix}:{run.id}",
            subscription_id=subscription_id,
            account_id=subscription.account_id,
            platform="zhihu",
            run_id=run.id,
            payload={
                "schema_version": 2,
                "sync_job_id": source.id,
                "subscription_id": subscription_id,
                "run_id": run.id,
                "result": receipt.to_mapping(),
            },
            status="succeeded",
            max_attempts=1,
        )
        session.add(pipeline)
        session.flush()
        session.expunge(pipeline)
        return pipeline, receipt


def test_server_end_reconciles_then_enters_incremental(database: Database) -> None:
    subscription_id = _seed(database)
    run1 = _run_unit(database, subscription_id, (ANSWER_ONE, ANSWER_TWO), is_end=True)
    pipeline1, receipt1 = _publish_source_and_pipeline(database, subscription_id, run1, natural_suffix="backfill")
    with database.session() as session:
        row = ZhihuDeliveryProgressRepository(session).publish_success(
            pipeline1,
            receipt1,
            upstream_sha=UPSTREAM_SHA,
            continuation_delay_seconds=300,
            now=NOW,
        )
        assert row is not None
        assert row.phase == "reconciling"
        assert row.source_end_observed_at is not None
        assert row.source_end_boundary_sha256 is not None
        assert row.last_offset == 0
        assert row.batch_count == 1 and row.backfill_batch_count == 1
        assert row.answer_observation_count == 2
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None and subscription.cursor is not None
        head_state = ZhihuScanState.from_cursor(subscription.cursor["value"])
        assert head_state.lane == "head"
        assert head_state.head_boundary is not None

    run2 = _run_unit(database, subscription_id, (ANSWER_ONE, ANSWER_TWO), is_end=True)
    pipeline2, receipt2 = _publish_source_and_pipeline(database, subscription_id, run2, natural_suffix="reconcile")
    with database.session() as session:
        row = ZhihuDeliveryProgressRepository(session).publish_success(
            pipeline2,
            receipt2,
            upstream_sha=UPSTREAM_SHA,
            continuation_delay_seconds=300,
            now=NOW,
        )
        assert row is not None
        assert row.phase == "incremental"
        assert row.reconciled_at is not None
        assert row.baseline_snapshot_at is not None
        assert row.reconciliation_batch_count == 1
        payload = zhihu_delivery_progress_payload(
            session.get(Subscription, subscription_id),
            upstream_sha=UPSTREAM_SHA,
        )
        assert payload is not None and payload["initialized"] is True
        assert payload["phase"] == "incremental"
        assert payload["baseline_snapshot_complete"] is True
        assert payload["last_offset"] == 0


def test_restricted_feed_blocks_with_fixed_code_and_no_source_end(database: Database) -> None:
    subscription_id = _seed(database)
    run = _run_unit_restricted(database, subscription_id)
    pipeline, receipt = _publish_source_and_pipeline(database, subscription_id, run, natural_suffix="restricted")
    with database.session() as session:
        row = ZhihuDeliveryProgressRepository(session).publish_success(
            pipeline,
            receipt,
            upstream_sha=UPSTREAM_SHA,
            continuation_delay_seconds=300,
            now=NOW,
        )
        assert row is not None
        assert row.phase == "blocked"
        assert row.blocked_code == ZHIHU_ACCESS_RESTRICTED_BLOCKED_CODE
        assert row.source_end_observed_at is None
        payload = zhihu_delivery_progress_payload(
            session.get(Subscription, subscription_id),
            upstream_sha=UPSTREAM_SHA,
        )
        assert payload is not None
        assert payload["phase"] == "blocked"
        assert payload["blocked_code"] == ZHIHU_ACCESS_RESTRICTED_BLOCKED_CODE
        assert payload["source_end_observed_at"] is None


def test_terminal_failure_blocks_with_the_fixed_code(database: Database) -> None:
    subscription_id = _seed(database)
    with database.session() as session:
        job = Job(
            id=str(uuid4()),
            job_type="pipeline.subscription",
            natural_key=f"pipeline-failed:{subscription_id}",
            subscription_id=subscription_id,
            platform="zhihu",
            payload={
                "schema_version": 1,
                "sync_job_id": str(uuid4()),
                "subscription_id": subscription_id,
                "run_id": None,
            },
            status="failed_terminal",
            max_attempts=1,
        )
        session.add(job)
        session.flush()
        session.expunge(job)
        ZhihuDeliveryProgressRepository(session).publish_terminal_failure(
            job,
            error_code="zhihu_access_restricted",
            upstream_sha=UPSTREAM_SHA,
            now=NOW,
        )
        row = session.get(ZhihuSubscriptionProgress, subscription_id)
        assert row is not None
        assert row.phase == "blocked" and row.blocked_code == "zhihu_access_restricted"
        assert session.scalars(select(ZhihuSubscriptionProgress.subscription_id)).all() == [subscription_id]
