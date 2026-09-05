"""Restart-safe forward/backfill checkpoint and fencing coverage."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError

from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    StaleCheckpointError,
    SubscriptionRemovalError,
    SubscriptionRepository,
    SyncRunRepository,
    create_database_engine,
)
from media_sync.infrastructure.db.models import Subscription, SyncRun

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"


@dataclass(frozen=True, slots=True)
class _CheckpointCandidate:
    cursor_version: int
    page: int
    next_run_at: datetime
    watermark: datetime


def _database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def _alembic_config(database_url: str) -> Config:
    configuration = Config(str(ALEMBIC_INI))
    configuration.set_main_option("sqlalchemy.url", database_url)
    return configuration


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    database_url = _database_url(tmp_path / "checkpoint.sqlite3")
    command.upgrade(_alembic_config(database_url), "head")
    instance = Database(database_url)
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_subscription(database: Database, *, next_run_at: datetime | None = None) -> str:
    with database.session() as session:
        account = AccountRepository(session).create(platform="bili", display_name="checkpoint-account")
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="bili", remote_id="checkpoint-author", display_name="Checkpoint Author")
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            cursor={"head": "initial"},
            cursor_version=7,
            backfill_cursor={"page": 1},
            next_run_at=next_run_at,
        )
        return subscription.id


def test_0002_upgrades_existing_0001_rows_with_zero_revision(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path / "upgrade-existing.sqlite3")
    configuration = _alembic_config(database_url)
    command.upgrade(configuration, "0001_core")

    engine = create_database_engine(database_url)
    observed_at = "2026-08-30 00:00:00"
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO accounts (id, platform, display_name) VALUES ('account-1', 'bili', 'primary')")
            )
            connection.execute(
                text(
                    "INSERT INTO authors "
                    "(id, platform, remote_id, display_name, first_seen_at, last_seen_at) "
                    "VALUES ('author-1', 'bili', 'creator-1', 'Creator', :observed_at, :observed_at)"
                ),
                {"observed_at": observed_at},
            )
            connection.execute(
                text(
                    "INSERT INTO subscriptions (id, account_id, author_id, cursor, backfill_cursor) "
                    "VALUES ('subscription-1', 'account-1', 'author-1', '{\"head\": 1}', '{\"page\": 9}')"
                )
            )
    finally:
        engine.dispose()

    command.upgrade(configuration, "head")
    migrated = Database(database_url)
    try:
        with migrated.session() as session:
            subscription = session.get(Subscription, "subscription-1")
            assert subscription is not None
            assert subscription.checkpoint_revision == 0
            assert subscription.cursor == {"head": 1}
            assert subscription.backfill_cursor == {"page": 9}
    finally:
        migrated.dispose()


def test_forward_and_backfill_checkpoints_advance_independently(database: Database) -> None:
    scheduled_at = datetime(2026, 8, 31, 1, tzinfo=UTC)
    watermarked_at = datetime(2026, 8, 30, 1, tzinfo=UTC)
    subscription_id = _seed_subscription(database, next_run_at=scheduled_at)

    with database.session() as session:
        repository = SubscriptionRepository(session)
        backfill = repository.publish_checkpoint(
            subscription_id,
            expected_revision=0,
            backfill_cursor={"page": 2},
        )
        assert backfill.checkpoint_revision == 1
        assert backfill.cursor == {"head": "initial"}
        assert backfill.cursor_version == 7
        assert backfill.backfill_cursor == {"page": 2}
        assert backfill.next_run_at == scheduled_at

    with database.session() as session:
        repository = SubscriptionRepository(session)
        forward = repository.publish_checkpoint(
            subscription_id,
            expected_revision=1,
            cursor={"head": "new"},
            watermarked_at=watermarked_at,
            watermark_remote_ids=("item-b", "item-a"),
        )
        assert forward.checkpoint_revision == 2
        assert forward.cursor == {"head": "new"}
        assert forward.cursor_version == 7
        assert forward.backfill_cursor == {"page": 2}
        assert forward.next_run_at == scheduled_at

        merged = repository.publish_checkpoint(
            subscription_id,
            expected_revision=2,
            watermarked_at=watermarked_at,
            watermark_remote_ids=("item-c", "item-a"),
        )
        assert merged.checkpoint_revision == 3
        assert merged.watermark_remote_ids == ["item-a", "item-b", "item-c"]


def test_database_rejects_a_negative_checkpoint_revision(database: Database) -> None:
    subscription_id = _seed_subscription(database)

    with pytest.raises(IntegrityError), database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        subscription.checkpoint_revision = -1
        session.flush()

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        assert subscription.checkpoint_revision == 0


def test_stale_overlapping_run_cannot_mutate_any_checkpoint_field(database: Database) -> None:
    initial_schedule = datetime(2026, 8, 31, 1, tzinfo=UTC)
    subscription_id = _seed_subscription(database, next_run_at=initial_schedule)

    with database.session() as session:
        run_repository = SyncRunRepository(session)
        run_ids = {
            "worker-a": run_repository.create(subscription_id=subscription_id).id,
            "worker-b": run_repository.create(subscription_id=subscription_id).id,
        }

    candidates = {
        "worker-a": _CheckpointCandidate(
            cursor_version=8,
            page=22,
            next_run_at=initial_schedule + timedelta(hours=6),
            watermark=datetime(2026, 8, 30, 2, tzinfo=UTC),
        ),
        "worker-b": _CheckpointCandidate(
            cursor_version=9,
            page=33,
            next_run_at=initial_schedule + timedelta(hours=12),
            watermark=datetime(2026, 8, 30, 3, tzinfo=UTC),
        ),
    }
    start = Barrier(2)

    def publish(worker_id: str) -> tuple[str, str, datetime | None]:
        candidate = candidates[worker_id]
        worker_database = Database(database.url)
        try:
            with worker_database.session() as session:
                start.wait()
                try:
                    published = SubscriptionRepository(session).publish_checkpoint(
                        subscription_id,
                        expected_revision=0,
                        cursor={"head": worker_id},
                        cursor_version=candidate.cursor_version,
                        backfill_cursor={"page": candidate.page},
                        next_run_at=candidate.next_run_at,
                        succeeded_at=candidate.watermark,
                        watermarked_at=candidate.watermark,
                        watermark_remote_ids=(f"{worker_id}-b", f"{worker_id}-a"),
                    )
                except StaleCheckpointError as error:
                    # The context deliberately commits after the caught
                    # conflict.  A failed CAS must still have no side effect.
                    assert error.expected_revision == 0
                    assert error.actual_revision == 1
                    return worker_id, "stale", None
                SyncRunRepository(session).record_checkpoint_publication(
                    run_ids[worker_id],
                    expected_revision=0,
                    published_revision=published.checkpoint_revision,
                )
                return worker_id, "published", published.updated_at
        finally:
            worker_database.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(publish, candidates))

    assert sorted(result[1] for result in results) == ["published", "stale"]
    winner_id, _status, winner_updated_at = next(result for result in results if result[1] == "published")
    stale_id = next(result[0] for result in results if result[1] == "stale")
    winner = candidates[winner_id]

    with database.session() as session:
        subscription = session.scalar(select(Subscription).where(Subscription.id == subscription_id))
        winner_run = session.get(SyncRun, run_ids[winner_id])
        stale_run = session.get(SyncRun, run_ids[stale_id])
        assert subscription is not None
        assert winner_run is not None
        assert stale_run is not None
        assert subscription.checkpoint_revision == 1
        assert subscription.cursor == {"head": winner_id}
        assert subscription.cursor_version == winner.cursor_version
        assert subscription.backfill_cursor == {"page": winner.page}
        assert subscription.next_run_at == winner.next_run_at
        assert subscription.watermarked_at == winner.watermark
        assert subscription.watermark_remote_ids == [f"{winner_id}-a", f"{winner_id}-b"]
        assert subscription.last_run_at == winner.watermark
        assert subscription.last_success_at == winner.watermark
        assert subscription.updated_at == winner_updated_at
        assert winner_run.checkpoint_revision_before == 0
        assert winner_run.checkpoint_revision_after == 1
        assert stale_run.checkpoint_revision_before == 0
        assert stale_run.checkpoint_revision_after is None


def test_stale_publication_can_be_caught_without_dirtying_the_transaction(database: Database) -> None:
    subscription_id = _seed_subscription(database)
    with database.session() as session:
        SubscriptionRepository(session).publish_checkpoint(
            subscription_id,
            expected_revision=0,
            cursor={"head": "winner"},
            backfill_cursor={"page": 2},
        )

    with database.session() as session, pytest.raises(StaleCheckpointError):
        SubscriptionRepository(session).publish_checkpoint(
            subscription_id,
            expected_revision=0,
            cursor={"head": "stale"},
            cursor_version=999,
            backfill_cursor=None,
            next_run_at=None,
            watermarked_at=datetime(2026, 8, 31, tzinfo=UTC),
            watermark_remote_ids=("stale",),
        )

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        assert subscription.checkpoint_revision == 1
        assert subscription.cursor == {"head": "winner"}
        assert subscription.cursor_version == 7
        assert subscription.backfill_cursor == {"page": 2}
        assert subscription.next_run_at is None
        assert subscription.watermarked_at is None
        assert subscription.watermark_remote_ids == []


@pytest.mark.parametrize("expected_revision", [0, 99], ids=["current", "stale"])
def test_removed_checkpoint_cas_is_writer_first_and_caught_failure_changes_nothing(
    database: Database, expected_revision: int
) -> None:
    subscription_id = _seed_subscription(database)
    deleted_at = datetime(2026, 9, 5, tzinfo=UTC)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        subscription.deleted_at = deleted_at
        subscription.enabled = False

    statements: list[str] = []

    def capture(
        connection: object, cursor: object, statement: str, parameters: object, context: object, executemany: bool
    ) -> None:
        if statement.lstrip().upper().startswith(("SELECT", "UPDATE", "INSERT", "DELETE")):
            statements.append(statement)

    event.listen(database.engine, "before_cursor_execute", capture)
    try:
        with database.session() as session:
            with pytest.raises(SubscriptionRemovalError, match="subscription_removed"):
                SubscriptionRepository(session).publish_checkpoint(
                    subscription_id,
                    expected_revision=expected_revision,
                    cursor={"head": "must-not-publish"},
                    backfill_cursor=None,
                    next_run_at=deleted_at,
                )
            # Deliberately commit a caught conflict, proving the CAS changed
            # neither revision nor data rather than relying on a rollback.
            assert session.in_transaction()
        assert statements[0].startswith("UPDATE subscriptions")
        assert "subscriptions.deleted_at IS NULL" in statements[0]
    finally:
        event.remove(database.engine, "before_cursor_execute", capture)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        assert subscription.deleted_at == deleted_at and not subscription.enabled
        assert subscription.checkpoint_revision == 0 and subscription.cursor == {"head": "initial"}
        assert subscription.backfill_cursor == {"page": 1} and subscription.next_run_at is None
