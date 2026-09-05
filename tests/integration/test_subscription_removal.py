"""Reversible removal keeps archive/history and fences new subscription work."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from media_sync.application.pipeline import SubscriptionAssetSelector, SubscriptionPipelineError
from media_sync.application.subscription_removal import SubscriptionRemovalError, SubscriptionRemovalService
from media_sync.application.workbench import SubscriptionDraft, WorkbenchError, WorkbenchService
from media_sync.domain import Platform
from media_sync.infrastructure.db import (
    AccountRepository,
    AssetRefreshSourceRepository,
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    Database,
    JobRepository,
    OperationRepository,
    OperationSubjectInput,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.asset_identity import stable_asset_key
from media_sync.infrastructure.db.models import (
    Account,
    Asset,
    AssetRefreshSource,
    Author,
    Content,
    Job,
    RunEvent,
    SchedulerLane,
    Subscription,
    SyncRun,
)
from media_sync.media.locator import AdapterRefreshLocator
from media_sync.scheduler.pipeline import PipelineJobRepository, PipelineJobRepositoryError
from media_sync.scheduler.repository import SchedulerRepository, SchedulerRepositoryError
from media_sync.scheduler.service import DurableSchedulerService

NOW = datetime(2026, 9, 5, 16, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'removal.sqlite3').as_posix()}")
    database.create_schema()
    try:
        yield database
    finally:
        database.dispose()


@dataclass(frozen=True)
class _Scope:
    account: str
    author: str
    subscription: str
    run: str
    asset: str


def _seed(database: Database) -> _Scope:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter="mediacrawler",
            display_name="Offline removal account",
            login_method="saved_session",
            auth_status="authenticated",
        )
        author, contents = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(platform="bili", remote_id="123", display_name="Retained author"),
            [ContentUpsert(remote_id="456", kind="video", title="Retained video")],
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            interval_seconds=60,
            cursor={"head": "retained"},
            backfill_cursor={"page": "retained"},
        )
        subscription.watermarked_at = NOW
        subscription.watermark_remote_ids = ["456"]
        subscription.checkpoint_revision = 4
        session.flush()
        run = SyncRunRepository(session).create(subscription_id=subscription.id, status="running", attempt=1)
        asset_key = stable_asset_key(
            platform="bili",
            content_remote_type="content",
            content_remote_id="456",
            kind="video",
            position=0,
            remote_id="456:video",
        )
        asset = AssetRepository(session).upsert_for_content(
            contents[0].id,
            AssetUpsert(
                platform="bili",
                content_remote_type="content",
                content_remote_id="456",
                kind="video",
                position=0,
                remote_id="456:video",
                source_url="https://example.invalid/video.mp4",
                locator=AdapterRefreshLocator(adapter="mediacrawler", asset_key=asset_key).as_dict(),
            ),
        )
        AssetRefreshSourceRepository(session).upsert_observation(
            asset_id=asset.id,
            subscription_id=subscription.id,
            last_run_id=run.id,
        )
        return _Scope(account.id, author.id, subscription.id, run.id, asset.id)


def _sync_job(database: Database, scope: _Scope, *, status: str = "queued") -> str:
    cycle = DurableSchedulerService(database, clock=lambda: NOW).tick(limit=1).cycles[0]
    with database.session() as session:
        job = session.get(Job, cycle.job_id)
        assert job is not None
        job.status = status
        job.run_id = scope.run
    return cycle.job_id


def _pipeline_job(database: Database, scope: _Scope) -> str:
    source_id = _sync_job(database, scope, status="succeeded")
    with database.session() as session:
        run = session.get(SyncRun, scope.run)
        assert run is not None
        run.status = "succeeded"
        run.finished_at = NOW
        session.flush()
        return PipelineJobRepository(session).enqueue_succeeded_sync(source_id, run_id=scope.run, now=NOW).job_id


def test_remove_restore_preserve_every_history_row_source_checkpoint_and_bytes(
    database: Database, tmp_path: Path
) -> None:
    scope = _seed(database)
    job_id = _sync_job(database, scope, status="failed_terminal")
    archive = tmp_path / "retained-video.mp4"
    archive.write_bytes(b"offline verified archive bytes")
    models = (Account, Author, Subscription, Content, Asset, AssetRefreshSource, SyncRun, RunEvent, Job)
    with database.session() as session:
        before = [session.scalar(select(func.count()).select_from(model)) for model in models]
        assert len(AssetRefreshSourceRepository(session).list_eligible(scope.asset)) == 1
    service = SubscriptionRemovalService(database, clock=lambda: NOW)
    assert service.remove(scope.subscription).to_payload() == {
        "id": scope.subscription,
        "status": "deleted",
        "changed": True,
        "cancelled_jobs": 0,
        "media_preserved": True,
    }
    assert service.remove(scope.subscription).changed is False
    with database.session() as session:
        assert [session.scalar(select(func.count()).select_from(model)) for model in models] == before
        repository = SubscriptionRepository(session)
        assert repository.list() == []
        assert [item.id for item in repository.list(deleted=True)] == [scope.subscription]
        subscription = repository.get(scope.subscription)
        run = session.get(SyncRun, scope.run)
        account = session.get(Account, scope.account)
        job = session.get(Job, job_id)
        assert subscription is not None and run is not None and account is not None and job is not None
        assert subscription.deleted_at == NOW and not subscription.enabled
        assert subscription.cursor == {"head": "retained"} and subscription.backfill_cursor == {"page": "retained"}
        assert subscription.checkpoint_revision == 4 and subscription.watermark_remote_ids == ["456"]
        assert run.status == "running" and run.error_code is None and run.finished_at is None
        assert job.status == "failed_terminal" and job.run_id == scope.run
        assert (account.login_method, account.auth_status) == ("saved_session", "authenticated")
        assert AssetRefreshSourceRepository(session).list_eligible(scope.asset) == []
        assert len(AssetRefreshSourceRepository(session).list_for_asset(scope.asset)) == 1
    assert archive.read_bytes() == b"offline verified archive bytes"
    restored = service.restore(scope.subscription)
    assert restored.status == "paused" and restored.changed and restored.cancelled_jobs == 0
    assert not service.restore(scope.subscription).changed
    assert not DurableSchedulerService(database, clock=lambda: NOW).tick(limit=1).cycles
    with database.session() as session:
        subscription = SubscriptionRepository(session).get(scope.subscription)
        assert subscription is not None and subscription.deleted_at is None and not subscription.enabled
        assert subscription.checkpoint_revision == 4 and subscription.cursor == {"head": "retained"}
        assert [item.id for item in SubscriptionRepository(session).list()] == [scope.subscription]
        assert len(AssetRefreshSourceRepository(session).list_eligible(scope.asset)) == 1
        assert session.get(Job, job_id).status == "failed_terminal"


@pytest.mark.parametrize("status", ["queued", "retry_wait", "waiting_auth", "waiting_user", "failed_retryable"])
def test_remove_cancels_unstarted_sync_without_rewriting_its_run(database: Database, status: str) -> None:
    scope = _seed(database)
    job_id = _sync_job(database, scope, status=status)
    service = SubscriptionRemovalService(database, clock=lambda: NOW)
    assert service.remove(scope.subscription).cancelled_jobs == 1
    service.restore(scope.subscription)
    with database.session() as session:
        job = session.get(Job, job_id)
        run = session.get(SyncRun, scope.run)
        assert job is not None and run is not None
        assert job.status == "cancelled" and job.finished_at == NOW
        assert job.lease_token is None and job.last_error_message is None
        assert run.status == "running" and run.error_code is None and run.finished_at is None
        assert SchedulerRepository(session).claim_next(worker_id="late", global_capacity=1, now=NOW) is None


def test_remove_reconciles_committed_success_then_cancels_new_pending_pipeline(database: Database) -> None:
    scope = _seed(database)
    job_id = _sync_job(database, scope, status="failed_retryable")
    with database.session() as session:
        run = session.get(SyncRun, scope.run)
        assert run is not None
        run.status = "succeeded"
        run.finished_at = NOW
    result = SubscriptionRemovalService(database, clock=lambda: NOW).remove(scope.subscription)
    assert result.cancelled_jobs == 1
    with database.session() as session:
        assert session.get(Job, job_id).status == "succeeded"
        assert session.get(SyncRun, scope.run).status == "succeeded"
        pipeline = session.scalar(select(Job).where(Job.job_type == "pipeline.subscription"))
        assert pipeline is not None and pipeline.status == "cancelled"
        assert PipelineJobRepository(session).claim_next(worker_id="late", now=NOW) is None


@pytest.mark.parametrize("status", ["queued", "retry_wait", "waiting_auth", "waiting_user", "failed_retryable"])
def test_remove_cancels_existing_unstarted_pipeline_and_restore_does_not_restart_it(
    database: Database, status: str
) -> None:
    scope = _seed(database)
    pipeline_id = _pipeline_job(database, scope)
    with database.session() as session:
        job = session.get(Job, pipeline_id)
        assert job is not None
        job.status = status
    service = SubscriptionRemovalService(database, clock=lambda: NOW)
    assert service.remove(scope.subscription).cancelled_jobs == 1
    service.restore(scope.subscription)
    with database.session() as session:
        job = session.get(Job, pipeline_id)
        assert job is not None and job.status == "cancelled" and job.finished_at == NOW
        assert session.get(SyncRun, scope.run).status == "succeeded"
        assert PipelineJobRepository(session).claim_next(worker_id="late", now=NOW) is None


@pytest.mark.parametrize("lease_field", ["lease_owner", "lease_token", "lease_expires_at"])
def test_remove_refuses_unstarted_work_with_any_retained_lease(database: Database, lease_field: str) -> None:
    scope = _seed(database)
    job_id = _sync_job(database, scope)
    with database.session() as session:
        job = session.get(Job, job_id)
        assert job is not None
        setattr(job, lease_field, NOW if lease_field == "lease_expires_at" else "retained")
    with pytest.raises(SubscriptionRemovalError, match="subscription_busy"):
        SubscriptionRemovalService(database, clock=lambda: NOW).remove(scope.subscription)
    with database.session() as session:
        assert session.get(Subscription, scope.subscription).deleted_at is None
        assert session.get(Job, job_id).status == "queued"


@pytest.mark.parametrize("kind", ["sync", "pipeline"])
def test_claim_gates_skip_tombstone_even_if_queued_history_was_directly_rewritten(
    database: Database, kind: str
) -> None:
    scope = _seed(database)
    job_id = _pipeline_job(database, scope) if kind == "pipeline" else _sync_job(database, scope)
    SubscriptionRemovalService(database, clock=lambda: NOW).remove(scope.subscription)
    with database.session() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = "queued"
    with database.session() as session:
        assert JobRepository(session).claim(job_id, worker_id="exact", now=NOW) is None
        assert JobRepository(session).claim_next(worker_id="generic", now=NOW) is None
        assert SchedulerRepository(session).claim_next(worker_id="sync", global_capacity=1, now=NOW) is None
        assert PipelineJobRepository(session).claim_next(worker_id="pipeline", now=NOW) is None
        assert session.get(Job, job_id).status == "queued"
        assert session.get(Job, job_id).attempts == 0


@pytest.mark.parametrize("kind", ["sync", "pipeline"])
@pytest.mark.parametrize("status", ["claimed", "running"])
def test_remove_busy_is_atomic_and_keeps_queued_work(database: Database, kind: str, status: str) -> None:
    scope = _seed(database)
    job_id = _pipeline_job(database, scope) if kind == "pipeline" else _sync_job(database, scope)
    with database.session() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = status
    with pytest.raises(SubscriptionRemovalError) as caught:
        SubscriptionRemovalService(database, clock=lambda: NOW).remove(scope.subscription)
    assert caught.value.code == "subscription_busy"
    with database.session() as session:
        subscription = session.get(Subscription, scope.subscription)
        assert subscription is not None and subscription.deleted_at is None and subscription.enabled
        assert session.get(Job, job_id).status == status


@pytest.mark.parametrize("subject_type", ["subscription", "sync_run", "job", "author", "asset"])
@pytest.mark.parametrize("link", [False, True], ids=["target", "subject"])
def test_active_correlated_operation_blocks_removal_before_cancelling_jobs(
    database: Database,
    subject_type: str,
    link: bool,
) -> None:
    scope = _seed(database)
    job_id = _sync_job(database, scope)
    target = {
        "subscription": scope.subscription,
        "sync_run": scope.run,
        "job": job_id,
        "author": scope.author,
        "asset": scope.asset,
    }[subject_type]
    with database.session() as session:
        OperationRepository(session).create_or_replay(
            kind="scheduler-run",
            request_fingerprint="a" * 64,
            target_type=None if link else subject_type,
            target_id=None if link else target,
            subjects=[OperationSubjectInput(subject_type, target)] if link else [],
            at=NOW,
        )
    with pytest.raises(SubscriptionRemovalError, match="subscription_busy"):
        SubscriptionRemovalService(database, clock=lambda: NOW).remove(scope.subscription)
    with database.session() as session:
        assert session.get(Subscription, scope.subscription).deleted_at is None
        assert session.get(Job, job_id).status == "queued"


def test_removed_subscriptions_reject_all_new_work_and_add_workflow(database: Database) -> None:
    scope = _seed(database)
    source_id = _sync_job(database, scope, status="succeeded")
    with database.session() as session:
        run = session.get(SyncRun, scope.run)
        assert run is not None
        run.status = "succeeded"
    service = SubscriptionRemovalService(database, clock=lambda: NOW)
    service.remove(scope.subscription)
    for action in ("pause_subscription", "resume_subscription", "run_now"):
        with database.session() as session, pytest.raises(SubscriptionRemovalError, match="subscription_removed"):
            getattr(SchedulerRepository(session), action)(scope.subscription, now=NOW)
    with database.session() as session, pytest.raises(SubscriptionRemovalError, match="subscription_removed"):
        SchedulerRepository(session).resume(source_id, now=NOW)
    with database.session() as session, pytest.raises(SubscriptionRemovalError, match="subscription_removed"):
        SubscriptionRepository(session).publish_checkpoint(scope.subscription, expected_revision=4)
    with database.session() as session, pytest.raises(SubscriptionRemovalError, match="subscription_removed"):
        SyncRunRepository(session).create(subscription_id=scope.subscription)
    with database.session() as session, pytest.raises(PipelineJobRepositoryError, match="subscription_removed"):
        PipelineJobRepository(session).enqueue_succeeded_sync(source_id, run_id=scope.run, now=NOW)
    with pytest.raises(SubscriptionPipelineError, match="pipeline_subscription_invalid"):
        SubscriptionAssetSelector(database).select(UUID(scope.subscription))
    for method in ("validate_subscription", "create_subscription"):
        with database.session() as session, pytest.raises(WorkbenchError) as caught:
            getattr(WorkbenchService(session), method)(
                SubscriptionDraft(
                    account_id=UUID(scope.account),
                    platform=Platform.BILI,
                    creator_remote_id="123",
                    display_name="Retained author",
                    allow_full_history=True,
                )
            )
        assert caught.value.code == "subscription_removed"


def test_restore_enabled_subscription_is_conflict_and_invalid_ids_are_closed(database: Database) -> None:
    scope = _seed(database)
    service = SubscriptionRemovalService(database, clock=lambda: NOW)
    with pytest.raises(SubscriptionRemovalError, match="subscription_not_removed"):
        service.restore(scope.subscription)
    for identifier in (str(uuid4()), "SECRET cookie=value /private/path", "", None):
        for method in (service.remove, service.restore):
            with pytest.raises(SubscriptionRemovalError) as caught:
                method(identifier)
            assert str(caught.value) == "subscription_not_found"


@pytest.mark.parametrize("kind", ["sync", "pipeline"])
def test_removal_wins_real_sqlite_claim_race_without_post_removal_work(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    scope = _seed(database)
    job_id = _pipeline_job(database, scope) if kind == "pipeline" else _sync_job(database, scope)
    service = SubscriptionRemovalService(database, clock=lambda: NOW)
    locked, release, claim_entered = Event(), Event(), Event()
    original = service._locked_subscription

    def hold_removal_lock(session: Session, identifier: str) -> Subscription:
        subscription = original(session, identifier)
        locked.set()
        assert release.wait(3)
        return subscription

    def claim() -> object:
        claim_entered.set()
        with database.session() as session:
            if kind == "pipeline":
                return PipelineJobRepository(session).claim_next(worker_id="racing", now=NOW)
            return SchedulerRepository(session).claim_next(worker_id="racing", global_capacity=1, now=NOW)

    monkeypatch.setattr(service, "_locked_subscription", hold_removal_lock)
    with ThreadPoolExecutor(max_workers=2) as executor:
        removing = executor.submit(service.remove, scope.subscription)
        try:
            assert locked.wait(3)
            claiming = executor.submit(claim)
            assert claim_entered.wait(3)
        finally:
            release.set()
        assert removing.result(4).changed
        assert claiming.result(4) is None
    with database.session() as session:
        assert session.get(Job, job_id).status == "cancelled"
        assert session.get(Subscription, scope.subscription).deleted_at is not None


def test_claim_wins_real_sqlite_race_and_removal_refuses_after_commit(database: Database) -> None:
    scope = _seed(database)
    job_id = _sync_job(database, scope)
    claimed, release, remove_entered = Event(), Event(), Event()

    def claim_and_hold() -> None:
        with database.session() as session:
            assert SchedulerRepository(session).claim_next(worker_id="winner", global_capacity=1, now=NOW) is not None
            claimed.set()
            assert release.wait(3)

    def remove() -> str:
        remove_entered.set()
        try:
            SubscriptionRemovalService(database, clock=lambda: NOW).remove(scope.subscription)
        except SubscriptionRemovalError as error:
            return error.code
        return "unexpected_success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        claiming = executor.submit(claim_and_hold)
        try:
            assert claimed.wait(3)
            removing = executor.submit(remove)
            assert remove_entered.wait(3)
        finally:
            release.set()
        claiming.result(4)
        assert removing.result(4) == "subscription_busy"
    with database.session() as session:
        assert session.get(Job, job_id).status == "claimed"
        assert session.get(Subscription, scope.subscription).deleted_at is None


def test_removal_job_and_lane_locks_compile_nowait_without_creating_missing_lanes(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = _seed(database)
    _sync_job(database, scope)
    statements: list[str] = []
    original = Session.scalars

    def capture(session: Session, statement: object, *args: object, **kwargs: object) -> object:
        locking = getattr(statement, "_for_update_arg", None)
        if locking is not None:
            statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return original(session, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "scalars", capture)
    SubscriptionRemovalService(database, clock=lambda: NOW).remove(scope.subscription)
    assert len(statements) == 3
    assert all(sql.endswith("FOR UPDATE NOWAIT") for sql in statements)
    assert "FROM jobs" in statements[0] and "FROM scheduler_lanes" in statements[1]
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SchedulerLane)) == 0


@pytest.mark.parametrize("blocked_lock", [1, 2, 3], ids=["job", "lane", "pipeline-after-cancel"])
@pytest.mark.parametrize("code_attribute", ["sqlstate", "pgcode"])
def test_exact_postgresql_nowait_error_is_fixed_busy_after_full_rollback(
    database: Database, monkeypatch: pytest.MonkeyPatch, blocked_lock: int, code_attribute: str
) -> None:
    scope = _seed(database)
    job_id = _sync_job(database, scope)
    original = Session.scalars
    observed_locks = 0

    def blocked(session: Session, statement: object, *args: object, **kwargs: object) -> object:
        nonlocal observed_locks
        if getattr(statement, "_for_update_arg", None) is not None:
            observed_locks += 1
            if observed_locks == blocked_lock:
                if blocked_lock == 3:
                    assert session.get(Job, job_id).status == "cancelled"
                driver_error = Exception("SECRET Cookie /private/path raw SQL")
                setattr(driver_error, code_attribute, "55P03")
                raise DBAPIError("SECRET statement", {}, driver_error, False)
        return original(session, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "scalars", blocked)
    with pytest.raises(SubscriptionRemovalError) as caught:
        SubscriptionRemovalService(database, clock=lambda: NOW).remove(scope.subscription)
    assert str(caught.value) == "subscription_busy"
    assert observed_locks == blocked_lock
    with database.session() as session:
        assert session.get(Subscription, scope.subscription).deleted_at is None
        assert session.get(Job, job_id).status == "queued"
        assert session.get(SyncRun, scope.run).status == "running"


def test_other_database_failures_are_not_misclassified_as_postgresql_busy(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = _seed(database)
    _sync_job(database, scope)
    original = Session.scalars
    driver_error = Exception("not a lock failure")
    driver_error.sqlstate = "40001"
    failure = DBAPIError("redacted", {}, driver_error, False)

    def blocked(session: Session, statement: object, *args: object, **kwargs: object) -> object:
        if getattr(statement, "_for_update_arg", None) is not None:
            raise failure
        return original(session, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "scalars", blocked)
    with pytest.raises(DBAPIError) as caught:
        SubscriptionRemovalService(database, clock=lambda: NOW).remove(scope.subscription)
    assert caught.value is failure


def test_removal_reconciles_only_locked_existing_lanes_and_keeps_success(database: Database) -> None:
    scope = _seed(database)
    job_id = _sync_job(database, scope, status="failed_retryable")
    with database.session() as session:
        session.get(SyncRun, scope.run).status = "succeeded"
        lane = SchedulerLane(scope_type="platform", platform="bili", consecutive_failures=2)
        foreign_lane = SchedulerLane(scope_type="platform", platform="xhs", consecutive_failures=2)
        session.add_all([lane, foreign_lane])
        session.flush()
        lane_id, foreign_id = lane.id, foreign_lane.id
    SubscriptionRemovalService(database, clock=lambda: NOW).remove(scope.subscription)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SchedulerLane)) == 2
        assert session.get(SchedulerLane, lane_id).consecutive_failures == 0
        assert session.get(SchedulerLane, foreign_id).consecutive_failures == 2
        assert session.get(Job, job_id).status == "succeeded"
        assert session.get(SyncRun, scope.run).status == "succeeded"


def test_removal_helper_rejects_foreign_lane_before_mutation(database: Database) -> None:
    scope = _seed(database)
    job_id = _sync_job(database, scope)
    with database.session() as session:
        foreign_lane = SchedulerLane(scope_type="platform", platform="xhs")
        session.add(foreign_lane)
        session.flush()
        with pytest.raises(SchedulerRepositoryError, match="removal lane scope is invalid"):
            SchedulerRepository(session).cancel_unstarted_for_removal(job_id, now=NOW, locked_lanes=(foreign_lane,))
        assert session.get(Job, job_id).status == "queued"
