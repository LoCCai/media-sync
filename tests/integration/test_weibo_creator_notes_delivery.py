"""Weibo delivery progress transitions driven only by closed pipeline receipts."""

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
    WeiboSubscriptionProgress,
)
from media_sync.infrastructure.db.models import Job, Subscription, SyncRun, SyncRunContent
from media_sync.integrations.mediacrawler.normalizers import NormalizationContext, normalize_record
from media_sync.integrations.mediacrawler.subscription_policy import MediaCrawlerSubscriptionPolicy
from media_sync.integrations.mediacrawler.weibo_creator_work import (
    WeiboCreatorPage,
    WeiboScanState,
    WeiboScanUnit,
    WeiboWorkIdentity,
)
from media_sync.scheduler.pipeline_receipt import PipelineDeliveryReceipt
from media_sync.scheduler.weibo_delivery_progress import (
    WEIBO_ACCESS_RESTRICTED_BLOCKED_CODE,
    WEIBO_STALL_BLOCKED_CODE,
    WeiboDeliveryProgressRepository,
    weibo_delivery_progress_payload,
    weibo_policy_fingerprint,
)

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
CREATOR_ID = "5123456789012345"
AUTHOR_SHA = hashlib.sha256(CREATOR_ID.encode()).hexdigest()
CREATOR_SHA = hashlib.sha256(CREATOR_ID.encode()).hexdigest()
NOTE_ONE = "5100000000000001"
NOTE_TWO = "5100000000000002"


@pytest.fixture
def database(tmp_path: Path) -> Database:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'weibo-delivery.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _identity(note_id: str, listing: str = "listing") -> WeiboWorkIdentity:
    return WeiboWorkIdentity(
        note_id=note_id,
        listing_sha256=hashlib.sha256(f"{note_id}-{listing}".encode()).hexdigest(),
    )


def _seed(database: Database) -> str:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="wb",
            adapter="mediacrawler",
            display_name="Execution 0084 Weibo",
            login_method=LoginMethod.COOKIE.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="wb", remote_id=CREATOR_ID, display_name="Execution 0084 creator")
        )
        policy = MediaCrawlerSubscriptionPolicy(
            allow_full_history=True,
            request_delay_seconds=2,
            headless=True,
            creator_secret_ref="env:EXECUTION0084_WEIBO_CREATOR",
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            interval_seconds=21_600,
            max_items=20,
            policy={"mediacrawler": policy.to_payload()},
        )
        row = WeiboDeliveryProgressRepository(session).ensure_for_materialization(
            subscription,
            upstream_sha=UPSTREAM_SHA,
            schedule_revision=0,
            now=NOW,
            resume_blocked=False,
        )
        assert row is not None
        return subscription.id


def _records(note_ids: tuple[str, ...]):
    now = datetime.now(UTC)
    return tuple(
        normalize_record(
            {
                "note_id": note_id,
                "content": f"fixture {note_id}",
                "create_time": 1_788_235_200,
                "liked_count": "0",
                "comments_count": "0",
                "shared_count": "0",
                "note_url": f"https://m.weibo.cn/detail/{note_id}",
            },
            NormalizationContext(Platform.WB, CREATOR_ID, "Weibo Creator", UPSTREAM_SHA, now),
        )
        for note_id in note_ids
    )


def _run_unit(
    database: Database,
    subscription_id: str,
    note_ids: tuple[str, ...],
    *,
    next_since_id: str,
    declared_total: int | None,
) -> SyncRun:
    """Commit one bounded unit through the production ingestion path."""

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        cursor = subscription.cursor
        before_value = cursor.get("value") if isinstance(cursor, dict) else None
        revision = subscription.checkpoint_revision
        account_id = subscription.account_id
        policy_fingerprint = weibo_policy_fingerprint(subscription.policy, subscription.max_items)
    state = WeiboScanState.for_cursor(
        before_value,
        account_id=UUID(account_id),
        author_fingerprint_sha256=AUTHOR_SHA,
        creator_fingerprint_sha256=CREATOR_SHA,
        upstream_sha=UPSTREAM_SHA,
    )
    page = WeiboCreatorPage(
        state.since_id,
        next_since_id,
        declared_total,
        tuple(_identity(note_id) for note_id in note_ids),
    )
    unit = WeiboScanUnit(state, 20)
    unit.observe_page(page)
    for identity in page.identities:
        if unit.next_action().kind == "unchanged":
            unit.skip_unchanged(identity)
        else:
            unit.store(identity)
    coverage = unit.coverage()

    with database.session() as session:
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
    MediaCrawlerIngestionService(database).ingest_weibo_bounded(
        _records(tuple(identity.note_id for identity in coverage.successful)),
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
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        revision = subscription.checkpoint_revision
        account_id = subscription.account_id
        policy_fingerprint = weibo_policy_fingerprint(subscription.policy, subscription.max_items)
    state = WeiboScanState.initial(UUID(account_id), AUTHOR_SHA, CREATOR_SHA, UPSTREAM_SHA)
    unit = WeiboScanUnit(state, 20)
    unit.observe_access_restricted()
    coverage = unit.coverage()
    with database.session() as session:
        run = SyncRunRepository(session).create(
            subscription_id=subscription_id,
            cursor_before=None,
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
    MediaCrawlerIngestionService(database).ingest_weibo_bounded(
        (),
        subscription_id=subscription_id,
        run_id=run.id,
        expected_revision=revision,
        input_cursor=None,
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
            natural_key=f"weibo-test-export-{natural_suffix}:{run.id}",
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
            platform="wb",
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
            platform="wb",
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


def test_inferred_end_reconciles_then_enters_incremental(database: Database) -> None:
    subscription_id = _seed(database)
    # total == 10 with one page consumed is the arithmetic end candidate.
    run1 = _run_unit(
        database,
        subscription_id,
        (NOTE_ONE, NOTE_TWO),
        next_since_id="next-since",
        declared_total=10,
    )
    pipeline1, receipt1 = _publish_source_and_pipeline(database, subscription_id, run1, natural_suffix="backfill")
    with database.session() as session:
        row = WeiboDeliveryProgressRepository(session).publish_success(
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
        assert row.declared_total == 10
        assert row.batch_count == 1 and row.backfill_batch_count == 1
        assert row.note_observation_count == 2
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None and subscription.cursor is not None
        head_state = WeiboScanState.from_cursor(subscription.cursor["value"])
        assert head_state.lane == "head"
        assert head_state.head_boundary is not None

    run2 = _run_unit(
        database,
        subscription_id,
        (NOTE_ONE, NOTE_TWO),
        next_since_id="head-tail",
        declared_total=10,
    )
    pipeline2, receipt2 = _publish_source_and_pipeline(database, subscription_id, run2, natural_suffix="reconcile")
    with database.session() as session:
        row = WeiboDeliveryProgressRepository(session).publish_success(
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
        payload = weibo_delivery_progress_payload(
            session.get(Subscription, subscription_id),
            upstream_sha=UPSTREAM_SHA,
        )
        assert payload is not None and payload["initialized"] is True
        assert payload["phase"] == "incremental"
        assert payload["baseline_snapshot_complete"] is True
        assert payload["declared_total"] == 10


def test_restricted_list_unit_blocks_with_fixed_code_and_no_source_end(database: Database) -> None:
    subscription_id = _seed(database)
    run = _run_unit_restricted(database, subscription_id)
    pipeline, receipt = _publish_source_and_pipeline(database, subscription_id, run, natural_suffix="restricted")
    with database.session() as session:
        row = WeiboDeliveryProgressRepository(session).publish_success(
            pipeline,
            receipt,
            upstream_sha=UPSTREAM_SHA,
            continuation_delay_seconds=300,
            now=NOW,
        )
        assert row is not None
        assert row.phase == "blocked"
        assert row.blocked_code == WEIBO_ACCESS_RESTRICTED_BLOCKED_CODE
        assert row.source_end_observed_at is None
        payload = weibo_delivery_progress_payload(
            session.get(Subscription, subscription_id),
            upstream_sha=UPSTREAM_SHA,
        )
        assert payload is not None
        assert payload["phase"] == "blocked"
        assert payload["blocked_code"] == WEIBO_ACCESS_RESTRICTED_BLOCKED_CODE
        assert payload["source_end_observed_at"] is None


def test_stalled_cursor_blocks_with_its_own_code(database: Database) -> None:
    subscription_id = _seed(database)
    pipeline = None
    for index in range(4):
        run = _run_unit(
            database,
            subscription_id,
            (NOTE_ONE, NOTE_TWO) if index == 0 else (),
            next_since_id="pinned",
            declared_total=1_000,
        )
        pipeline, receipt = _publish_source_and_pipeline(
            database,
            subscription_id,
            run,
            natural_suffix=f"stall-{index}",
        )
        with database.session() as session:
            row = WeiboDeliveryProgressRepository(session).publish_success(
                pipeline,
                receipt,
                upstream_sha=UPSTREAM_SHA,
                continuation_delay_seconds=300,
                now=NOW,
            )
            assert row is not None
    assert row.phase == "blocked"
    assert row.blocked_code == WEIBO_STALL_BLOCKED_CODE


def test_terminal_failure_blocks_with_the_fixed_code(database: Database) -> None:
    subscription_id = _seed(database)
    with database.session() as session:
        job = Job(
            id=str(uuid4()),
            job_type="pipeline.subscription",
            natural_key=f"pipeline-failed:{subscription_id}",
            subscription_id=subscription_id,
            platform="wb",
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
        WeiboDeliveryProgressRepository(session).publish_terminal_failure(
            job,
            error_code="weibo_access_restricted",
            upstream_sha=UPSTREAM_SHA,
            now=NOW,
        )
        row = session.get(WeiboSubscriptionProgress, subscription_id)
        assert row is not None
        assert row.phase == "blocked" and row.blocked_code == "weibo_access_restricted"
        assert session.scalars(select(WeiboSubscriptionProgress.subscription_id)).all() == [subscription_id]
