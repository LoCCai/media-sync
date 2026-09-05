"""Paused scope edits are fenced, leave checkpoints and original rows intact."""

from dataclasses import replace
from uuid import UUID

import pytest

from media_sync.application.bilibili_subscription_scope import change_bilibili_scope
from media_sync.application.workbench import SubscriptionDraft, WorkbenchError, WorkbenchService
from media_sync.domain import ContentKind, Platform
from media_sync.infrastructure.db import AccountRepository, MediaCrawlerIngestionService
from media_sync.infrastructure.db.models import Subscription, SyncRun
from media_sync.integrations.mediacrawler.subscription_policy import MediaCrawlerSubscriptionPolicy
from tests.integration.test_bili_bounded_ingestion import _record, _run, _seed
from tests.integration.test_bili_bounded_ingestion import database as _database

database = _database


def test_scope_edits_keep_legacy_checkpoints_and_require_paused_idle_revision(database):
    identifier = _seed(database, cursor="legacy-private-cursor")
    with database.session() as session:
        row = session.get(Subscription, identifier)
        row.policy = {"mediacrawler": MediaCrawlerSubscriptionPolicy(False, 2, True).to_payload()}
        revision = row.schedule_revision
    with pytest.raises(ValueError, match="paused"):
        change_bilibili_scope(
            database, UUID(identifier), scope="both", max_items=2, expected_schedule_revision=revision
        )
    with database.session() as session:
        session.get(Subscription, identifier).enabled = False
    changed = change_bilibili_scope(
        database, UUID(identifier), scope="both", max_items=2, expected_schedule_revision=revision
    )
    assert changed["schedule_revision"] == revision + 1
    with database.session() as session:
        row = session.get(Subscription, identifier)
        assert row.cursor == {"value": "legacy-private-cursor"}
        assert row.backfill_cursor == {"legacy": "preserve"}
        assert row.checkpoint_revision == 0 and not row.enabled
    with pytest.raises(ValueError, match="revision"):
        change_bilibili_scope(
            database, UUID(identifier), scope="uploads", max_items=1, expected_schedule_revision=revision
        )
    run_id = _run(database, identifier)
    assert run_id
    with pytest.raises(ValueError, match="idle"):
        change_bilibili_scope(
            database, UUID(identifier), scope="uploads", max_items=1, expected_schedule_revision=revision + 1
        )
    with database.session() as session:
        session.get(SyncRun, run_id).status = "failed_retryable"
    changed = change_bilibili_scope(
        database,
        UUID(identifier),
        scope="uploads",
        max_items=1,
        expected_schedule_revision=revision + 1,
    )
    assert changed["changed"] is True


@pytest.mark.parametrize(
    "platform,scope,maximum,valid",
    [("bili", "both", 2, True), ("bili", "dynamics", 1, False), ("wb", "uploads", 2, False)],
)
def test_subscription_create_scope_validation(database, platform, scope, maximum, valid):
    with database.session() as session:
        account = AccountRepository(session).create(platform=platform, display_name="scope", adapter="mediacrawler")
        draft = SubscriptionDraft(
            UUID(account.id), Platform(platform), "42", "Fixture", bili_scope=scope, max_items=maximum
        )
        if valid:
            result = WorkbenchService(session).create_subscription(draft)
            assert result.to_payload()["policy_summary"]["bili_scope"] == scope
        else:
            with pytest.raises(WorkbenchError):
                WorkbenchService(session).create_subscription(draft)


def test_atomic_dynamic_and_numeric_video_namespaces_do_not_collide(database):
    identifier = _seed(database, max_items=2)
    with database.session() as session:
        session.get(Subscription, identifier).policy = {
            "mediacrawler": MediaCrawlerSubscriptionPolicy(False, 2, True, bili_scope="dynamics").to_payload()
        }
    run = _run(database, identifier)
    video = _record("1234")
    dynamic = replace(video, content=replace(video.content, remote_type="dynamic", kind=ContentKind.DYNAMIC), assets=())
    result = MediaCrawlerIngestionService(database).ingest_bili_bounded(
        (dynamic, video),
        subscription_id=identifier,
        run_id=run,
        expected_revision=0,
        input_cursor=None,
        next_cursor="private-next",
    )
    assert result.discovered_count == 2 and result.checkpoint_revision == 1
    with database.session() as session:
        row = session.get(Subscription, identifier)
        row.enabled = False
        revision = row.schedule_revision
    change_bilibili_scope(database, UUID(identifier), scope="uploads", max_items=1, expected_schedule_revision=revision)
    replay = MediaCrawlerIngestionService(database).ingest_bili_bounded(
        (dynamic, video),
        subscription_id=identifier,
        run_id=run,
        expected_revision=0,
        input_cursor=None,
        next_cursor="private-next",
        bili_scope="dynamics",
    )
    assert replay.committed_batches == 0
