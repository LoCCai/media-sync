"""Execution 0075 atomic paused-policy update contract."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from media_sync.application.subscription_policy_update import (
    SubscriptionPolicyUpdate,
    SubscriptionPolicyUpdateError,
    update_subscription_policy,
)
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    SubscriptionRepository,
)
from media_sync.infrastructure.db.models import BiliSubscriptionProgress, Job, Operation, Subscription, SyncRun
from media_sync.integrations.mediacrawler.subscription_policy import MediaCrawlerSubscriptionPolicy
from media_sync.scheduler.bili_delivery_progress import BiliDeliveryProgressRepository

_NOW = datetime(2026, 9, 7, 8, 0, tzinfo=UTC)
_SECRET_REFERENCE = "env:MEDIA_SYNC_PRIVATE_CREATOR_REFERENCE"


@pytest.fixture
def database(tmp_path: Path):
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'policy.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


@pytest.fixture(scope="module")
def postgresql_database() -> Iterator[Database]:
    raw_url = os.environ.get("MEDIA_SYNC_TEST_POSTGRESQL_URL")
    if not raw_url:
        pytest.skip("MEDIA_SYNC_TEST_POSTGRESQL_URL is not set; real PostgreSQL policy races were not run")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("MEDIA_SYNC_TEST_POSTGRESQL_URL must identify PostgreSQL")
    url = url.set(drivername="postgresql+psycopg")
    admin = Database(url.render_as_string(hide_password=False))
    schema = f"media_sync_policy_{uuid4().hex}"
    scoped: Database | None = None
    created = False
    try:
        with admin.engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        created = True
        options = f"-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=10000"
        scoped_url = url.update_query_dict({"options": options}, append=False)
        scoped = Database(scoped_url.render_as_string(hide_password=False))
        scoped.create_schema()
        yield scoped
    finally:
        if scoped is not None:
            scoped.dispose()
        if created:
            with admin.engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        admin.dispose()


def _seed(
    database: Database,
    *,
    platform: str = "xhs",
    adapter: str = "mediacrawler",
    enabled: bool = False,
    with_private_state: bool = True,
) -> UUID:
    suffix = uuid4().hex
    policy = MediaCrawlerSubscriptionPolicy(
        allow_full_history=True,
        request_delay_seconds=5,
        headless=True,
        creator_secret_ref=_SECRET_REFERENCE,
        bili_scope="uploads" if platform == "bili" else None,
    )
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=platform,
            display_name=f"Policy fixture {suffix}",
            adapter=adapter,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform=platform, remote_id=f"{platform}-creator-{suffix}", display_name="Creator")
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            enabled=enabled,
            interval_seconds=21_600,
            max_items=30,
            policy={"mediacrawler": policy.to_payload()},
            next_run_at=_NOW + timedelta(hours=3),
        )
        if with_private_state:
            subscription.cursor = {"value": "private-forward-cursor"}
            subscription.backfill_cursor = {"value": "private-backfill-cursor"}
            subscription.checkpoint_revision = 7
            subscription.watermarked_at = _NOW - timedelta(days=1)
            subscription.watermark_remote_ids = ["private-watermark"]
            subscription.last_run_at = _NOW - timedelta(hours=2)
            subscription.last_success_at = _NOW - timedelta(hours=2)
            subscription.consecutive_failures = 3
        return UUID(subscription.id)


def _update(
    *,
    expected_revision: int = 0,
    interval_seconds: int = 3_600,
    max_items: int = 12,
    request_delay_seconds: float = 8.5,
    headless: bool = False,
    bili_scope: str | None = None,
) -> SubscriptionPolicyUpdate:
    return SubscriptionPolicyUpdate(
        interval_seconds=interval_seconds,
        max_items=max_items,
        request_delay_seconds=request_delay_seconds,
        headless=headless,
        expected_schedule_revision=expected_revision,
        bili_scope=bili_scope,
    )


def test_update_preserves_private_policy_checkpoint_schedule_and_media_authority(database: Database) -> None:
    identifier = _seed(database)
    with database.session() as session:
        before = session.get(Subscription, str(identifier))
        assert before is not None
        preserved = {
            "cursor": before.cursor,
            "backfill_cursor": before.backfill_cursor,
            "checkpoint_revision": before.checkpoint_revision,
            "watermarked_at": before.watermarked_at,
            "watermark_remote_ids": before.watermark_remote_ids,
            "last_run_at": before.last_run_at,
            "last_success_at": before.last_success_at,
            "next_run_at": before.next_run_at,
            "consecutive_failures": before.consecutive_failures,
        }

    result = update_subscription_policy(database, identifier, _update())
    payload = result.to_payload()

    assert result.changed is True and result.schedule_revision == 1
    assert payload == {
        "id": str(identifier),
        "platform": "xhs",
        "status": "paused",
        "enabled": False,
        "interval_seconds": 3_600,
        "max_items": 12,
        "schedule_revision": 1,
        "checkpoint_revision": 7,
        "next_run_at": (_NOW + timedelta(hours=3)).isoformat(),
        "policy_summary": {
            "adapter": "mediacrawler",
            "schema_version": 1,
            "allow_full_history": True,
            "request_delay_seconds": 8.5,
            "headless": False,
            "creator_reference_configured": True,
        },
        "changed": True,
        "checkpoint_preserved": True,
        "media_preserved": True,
    }
    assert _SECRET_REFERENCE not in json.dumps(payload)
    with database.session() as session:
        after = session.get(Subscription, str(identifier))
        assert after is not None
        for field, value in preserved.items():
            assert getattr(after, field) == value
        assert after.interval_seconds == 3_600 and after.max_items == 12
        assert after.policy["mediacrawler"]["creator_input"] == {"secret_ref": _SECRET_REFERENCE}
        assert after.policy["mediacrawler"]["allow_full_history"] is True


def test_exact_noop_is_repeatable_without_consuming_a_revision(database: Database) -> None:
    identifier = _seed(database, with_private_state=False)
    same = _update(
        interval_seconds=21_600,
        max_items=30,
        request_delay_seconds=5,
        headless=True,
    )

    first = update_subscription_policy(database, identifier, same)
    second = update_subscription_policy(database, identifier, same)

    assert first.changed is second.changed is False
    assert first.schedule_revision == second.schedule_revision == 0


@pytest.mark.parametrize(
    "setup,update,code",
    [
        ("enabled", _update(), "subscription_policy_requires_paused"),
        ("removed", _update(), "subscription_policy_removed"),
        ("fake", _update(), "subscription_policy_unsupported_adapter"),
        ("stale", _update(expected_revision=1), "subscription_policy_revision_conflict"),
        ("corrupt", _update(), "subscription_policy_invalid"),
        ("foreign_scope", _update(bili_scope="uploads"), "subscription_policy_options_invalid"),
    ],
)
def test_rejections_are_fixed_and_write_nothing(
    database: Database,
    setup: str,
    update: SubscriptionPolicyUpdate,
    code: str,
) -> None:
    identifier = _seed(
        database,
        adapter="fake" if setup == "fake" else "mediacrawler",
        enabled=setup == "enabled",
    )
    with database.session() as session:
        row = session.get(Subscription, str(identifier))
        assert row is not None
        if setup == "removed":
            row.deleted_at = _NOW
        elif setup == "corrupt":
            row.policy = {"mediacrawler": {"schema_version": 1}}
        before = (row.interval_seconds, row.max_items, row.schedule_revision, row.policy)

    with pytest.raises(SubscriptionPolicyUpdateError, match=rf"^{code}$"):
        update_subscription_policy(database, identifier, update)

    with database.session() as session:
        row = session.get(Subscription, str(identifier))
        assert row is not None
        assert (row.interval_seconds, row.max_items, row.schedule_revision, row.policy) == before


def test_missing_and_invalid_direct_inputs_are_closed(database: Database) -> None:
    with pytest.raises(SubscriptionPolicyUpdateError, match="not_found"):
        update_subscription_policy(database, uuid4(), _update())
    identifier = _seed(database)
    with pytest.raises(SubscriptionPolicyUpdateError, match="options_invalid"):
        update_subscription_policy(database, identifier, _update(interval_seconds=59))
    with pytest.raises(SubscriptionPolicyUpdateError, match="options_invalid"):
        update_subscription_policy(database, identifier, _update(request_delay_seconds=float("nan")))
    with pytest.raises(SubscriptionPolicyUpdateError, match="options_invalid"):
        update_subscription_policy(database, identifier, _update(bili_scope=[]))  # type: ignore[arg-type]


@pytest.mark.parametrize("busy_kind", ["job", "run", "operation"])
def test_active_job_run_or_operation_fences_the_edit(database: Database, busy_kind: str) -> None:
    identifier = _seed(database)
    with database.session() as session:
        subscription = session.get(Subscription, str(identifier))
        assert subscription is not None
        if busy_kind == "job":
            session.add(
                Job(
                    subscription_id=subscription.id,
                    account_id=subscription.account_id,
                    platform=subscription.account.platform,
                    job_type="sync.subscription",
                    natural_key=f"policy-busy:{identifier}",
                    status="queued",
                    payload={},
                )
            )
        elif busy_kind == "run":
            session.add(SyncRun(subscription_id=subscription.id, status="failed_retryable"))
        else:
            session.add(
                Operation(
                    kind="subscription-delivery",
                    state="queued",
                    request_fingerprint="a" * 64,
                    target_type="subscription",
                    target_id=subscription.id,
                    correlation_id=str(uuid4()),
                )
            )

    with pytest.raises(SubscriptionPolicyUpdateError, match="busy"):
        update_subscription_policy(database, identifier, _update())
    with database.session() as session:
        row = session.get(Subscription, str(identifier))
        assert row is not None and row.schedule_revision == 0 and row.interval_seconds == 21_600


def test_concurrent_writers_allow_exactly_one_revision_owner(database: Database) -> None:
    identifier = _seed(database, with_private_state=False)
    barrier = Barrier(2)

    def write(interval: int) -> str:
        barrier.wait(timeout=5)
        try:
            update_subscription_policy(database, identifier, _update(interval_seconds=interval))
        except SubscriptionPolicyUpdateError as error:
            return error.code
        return "changed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, (3_600, 7_200)))

    assert sorted(outcomes) == ["changed", "subscription_policy_revision_conflict"]
    with database.session() as session:
        row = session.get(Subscription, str(identifier))
        assert row is not None and row.schedule_revision == 1
        assert row.interval_seconds in {3_600, 7_200}


def test_real_postgresql_policy_writers_have_one_revision_owner(postgresql_database: Database) -> None:
    identifier = _seed(postgresql_database, with_private_state=False)
    barrier = Barrier(2)

    def write(interval: int) -> str:
        barrier.wait(timeout=5)
        try:
            update_subscription_policy(postgresql_database, identifier, _update(interval_seconds=interval))
        except SubscriptionPolicyUpdateError as error:
            return error.code
        return "changed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, (3_600, 7_200)))

    assert sorted(outcomes) == ["changed", "subscription_policy_revision_conflict"]


def test_real_postgresql_active_operation_nowait_is_a_fixed_busy_error(
    postgresql_database: Database,
) -> None:
    identifier = _seed(postgresql_database, with_private_state=False)
    with postgresql_database.session() as session:
        operation = Operation(
            kind="subscription-delivery",
            state="queued",
            request_fingerprint="b" * 64,
            target_type="subscription",
            target_id=str(identifier),
            correlation_id=str(uuid4()),
        )
        session.add(operation)
        session.flush()
        operation_id = operation.id

    blocker = postgresql_database.session_factory()
    try:
        blocker.scalar(select(Operation).where(Operation.id == operation_id).with_for_update())
        with pytest.raises(SubscriptionPolicyUpdateError, match=r"^subscription_policy_busy$"):
            update_subscription_policy(postgresql_database, identifier, _update())
    finally:
        blocker.rollback()
        blocker.close()


def test_bili_policy_change_is_requalified_only_when_the_next_cycle_materializes(database: Database) -> None:
    identifier = _seed(database, platform="bili", with_private_state=False)
    with database.session() as session:
        subscription = SubscriptionRepository(session).get(str(identifier))
        assert subscription is not None
        progress = BiliDeliveryProgressRepository(session).ensure_for_materialization(
            subscription,
            upstream_sha="a" * 40,
            schedule_revision=0,
            now=_NOW,
            resume_blocked=False,
        )
        assert progress is not None
        old_generation = progress.generation_id
        old_fingerprint = progress.policy_fingerprint_sha256

    result = update_subscription_policy(database, identifier, _update(bili_scope="uploads"))
    assert result.changed is True and result.schedule_revision == 1
    with database.session() as session:
        unchanged = session.get(BiliSubscriptionProgress, str(identifier))
        assert unchanged is not None
        assert unchanged.generation_id == old_generation
        subscription = SubscriptionRepository(session).get(str(identifier))
        assert subscription is not None
        refreshed = BiliDeliveryProgressRepository(session).ensure_for_materialization(
            subscription,
            upstream_sha="a" * 40,
            schedule_revision=1,
            now=_NOW + timedelta(minutes=1),
            resume_blocked=False,
        )
        assert refreshed is not None
        assert refreshed.generation_id != old_generation
        assert refreshed.policy_fingerprint_sha256 != old_fingerprint
        assert refreshed.phase == "backfill"


def test_bili_scope_and_item_limit_are_validated_together(database: Database) -> None:
    identifier = _seed(database, platform="bili", with_private_state=False)
    with pytest.raises(SubscriptionPolicyUpdateError, match="options_invalid"):
        update_subscription_policy(database, identifier, _update(max_items=1, bili_scope="dynamics"))

    changed = update_subscription_policy(database, identifier, _update(max_items=2, bili_scope="both"))

    assert changed.policy.bili_scope == "both"
    assert changed.to_payload()["policy_summary"]["bili_scope"] == "both"  # type: ignore[index]
