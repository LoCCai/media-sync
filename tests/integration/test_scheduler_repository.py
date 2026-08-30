"""Offline integration coverage for the durable subscription scheduler repository."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event, current_thread
from typing import Literal
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    JobRepository,
    LeaseLostError,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import Job, SchedulerLane, Subscription
from media_sync.scheduler.policy import RetryPolicy
from media_sync.scheduler.repository import (
    SCHEDULE_PAYLOAD_SCHEMA_VERSION,
    SYNC_SUBSCRIPTION_JOB_TYPE,
    LanePolicy,
    SchedulerJobSummary,
    SchedulerRepository,
    SchedulerRepositoryError,
)


def _database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(_database_url(tmp_path / "scheduler.sqlite3"))
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_subscription(
    database: Database,
    *,
    platform: str,
    remote_id: str,
    now: datetime,
    enabled: bool = True,
    next_run_at: datetime | None = None,
    interval_seconds: int = 60,
    adapter: str = "fake",
) -> tuple[str, str]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=platform,
            adapter=adapter,
            display_name=f"account-{remote_id}",
            login_method="qr",
            auth_status="authenticated",
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=platform,
                remote_id=remote_id,
                display_name=f"author-{remote_id}",
            )
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            enabled=enabled,
            interval_seconds=interval_seconds,
            next_run_at=next_run_at,
            policy={"handler": "fake"},
        )
        subscription.created_at = now
        subscription.updated_at = now
        session.flush()
        return account.id, subscription.id


def test_claim_adapter_allowlist_skips_unsupported_queue_head_without_mutation(database: Database) -> None:
    now = datetime(2026, 8, 30, 4, 0, tzinfo=UTC)
    _mc_account_id, mediacrawler_subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="allowlist-mediacrawler",
        now=now - timedelta(minutes=2),
        next_run_at=now - timedelta(minutes=2),
        adapter="mediacrawler",
    )
    _fake_account_id, fake_subscription_id = _seed_subscription(
        database,
        platform="bili",
        remote_id="allowlist-fake",
        now=now - timedelta(minutes=1),
        next_run_at=now - timedelta(minutes=1),
    )
    with database.session() as session:
        repository = SchedulerRepository(session)
        assert len(repository.materialize_due(limit=10, now=now)) == 2
        claim = repository.claim_next(
            worker_id="adapter-allowlist-worker",
            global_capacity=2,
            adapter_allowlist=("fake",),
            now=now,
        )
        assert claim is not None and claim.subscription_id == fake_subscription_id
        mediacrawler_job = session.scalar(select(Job).where(Job.subscription_id == mediacrawler_subscription_id))
        mediacrawler_subscription = session.get(Subscription, mediacrawler_subscription_id)
        assert mediacrawler_job is not None
        assert (mediacrawler_job.status, mediacrawler_job.attempts) == ("queued", 0)
        assert mediacrawler_subscription is not None and mediacrawler_subscription.consecutive_failures == 0


def _materialize_one(database: Database, subscription_id: str, *, now: datetime) -> str:
    with database.session() as session:
        cycles = SchedulerRepository(session).materialize_due(limit=100, now=now)
        matches = [cycle for cycle in cycles if cycle.subscription_id == subscription_id]
        assert len(matches) == 1
        return matches[0].job_id


def _claim_and_start(
    database: Database,
    *,
    worker_id: str,
    now: datetime,
    global_capacity: int = 10,
    lease_seconds: int = 30,
) -> tuple[str, str]:
    with database.session() as session:
        repository = SchedulerRepository(session)
        claim = repository.claim_next(
            worker_id=worker_id,
            global_capacity=global_capacity,
            lease_seconds=lease_seconds,
            now=now,
        )
        assert claim is not None
        running = repository.start(
            claim.job_id,
            worker_id=worker_id,
            lease_token=claim.lease_token,
            now=now,
        )
        return running.job_id, running.lease_token


def _job_execution_state(job: Job) -> dict[str, object]:
    return {
        "status": job.status,
        "priority": job.priority,
        "attempts": job.attempts,
        "run_id": job.run_id,
        "lease_owner": job.lease_owner,
        "lease_token": job.lease_token,
        "lease_expires_at": job.lease_expires_at,
        "available_at": job.available_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "updated_at": job.updated_at,
        "last_error_code": job.last_error_code,
        "last_error_message": job.last_error_message,
    }


def _attach_succeeded_run(
    database: Database,
    *,
    subscription_id: str,
    job_id: str,
    worker_id: str,
    lease_token: str,
    now: datetime,
) -> str:
    with database.session() as session:
        runs = SyncRunRepository(session)
        run = runs.create(subscription_id=subscription_id, attempt=1)
        runs.set_status(run.id, "claimed", expected_status="queued", at=now)
        runs.set_status(run.id, "running", expected_status="claimed", at=now)
        SchedulerRepository(session).attach_run(
            job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            run_id=run.id,
            expected_current_run_id=None,
            now=now,
        )
        runs.set_status(run.id, "ingesting", expected_status="running", at=now)
        runs.set_status(run.id, "succeeded", expected_status="ingesting", at=now)
        return run.id


def test_due_materialization_is_bounded_ordered_closed_and_fixed_delay(database: Database) -> None:
    now = datetime(2026, 8, 30, 3, 0, tzinfo=UTC)
    _account_null, null_due_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="null-due",
        now=now - timedelta(minutes=4),
        next_run_at=None,
    )
    _account_past, past_due_id = _seed_subscription(
        database,
        platform="bili",
        remote_id="past-due",
        now=now - timedelta(minutes=3),
        next_run_at=now - timedelta(minutes=1),
    )
    _seed_subscription(
        database,
        platform="dy",
        remote_id="future",
        now=now - timedelta(minutes=2),
        next_run_at=now + timedelta(minutes=1),
    )
    _seed_subscription(
        database,
        platform="ks",
        remote_id="disabled",
        now=now - timedelta(minutes=1),
        enabled=False,
        next_run_at=None,
    )

    with database.session() as session:
        repository = SchedulerRepository(session)
        first = repository.materialize_due(limit=1, now=now)
        second = repository.materialize_due(limit=10, now=now)
        assert [cycle.subscription_id for cycle in first] == [null_due_id]
        assert [cycle.subscription_id for cycle in second] == [past_due_id]

    with database.session() as session:
        jobs = session.scalars(select(Job).where(Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE)).all()
        assert len(jobs) == 2
        for job in jobs:
            assert set(job.payload) == {
                "schema_version",
                "subscription_id",
                "schedule_revision",
                "retry_policy",
            }
            assert job.payload["schema_version"] == SCHEDULE_PAYLOAD_SCHEMA_VERSION
            assert job.payload["retry_policy"] == RetryPolicy().to_payload()
            assert job.natural_key == f"subscription:{job.subscription_id}:schedule:0"
        assert {job.subscription_id for job in jobs} == {null_due_id, past_due_id}

    job_id, token = _claim_and_start(database, worker_id="worker-fixed-delay", now=now)
    finished_at = now + timedelta(seconds=10)
    with database.session() as session:
        completed = SchedulerRepository(session).succeed(
            job_id,
            worker_id="worker-fixed-delay",
            lease_token=token,
            now=finished_at,
        )
        assert completed.status == "succeeded"
        completed_subscription_id = completed.subscription_id
    with database.session() as session:
        subscription = session.get(Subscription, completed_subscription_id)
        assert subscription is not None
        assert subscription.next_run_at == finished_at + timedelta(seconds=60)
        assert subscription.last_success_at == finished_at
        assert subscription.consecutive_failures == 0
        assert SchedulerRepository(session).materialize_due(limit=10, now=finished_at) == []


def test_concurrent_ticks_on_independent_sqlite_connections_create_one_cycle(database: Database) -> None:
    now = datetime(2026, 8, 30, 4, 0, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="concurrent",
        now=now,
        next_run_at=None,
    )
    start = Barrier(2)

    def materialize() -> int:
        start.wait(timeout=10)
        with database.session() as session:
            return len(SchedulerRepository(session).materialize_due(limit=1, now=now))

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (executor.submit(materialize), executor.submit(materialize))
        results = sorted(future.result() for future in futures)

    assert results == [0, 1]
    with database.session() as session:
        jobs = session.scalars(
            select(Job).where(
                Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                Job.subscription_id == subscription_id,
            )
        ).all()
        assert len(jobs) == 1
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None and subscription.schedule_revision == 1


def test_independent_sqlite_claims_respect_platform_capacity(database: Database) -> None:
    now = datetime(2026, 8, 30, 4, 30, tzinfo=UTC)
    _seed_subscription(
        database,
        platform="xhs",
        remote_id="capacity-one",
        now=now - timedelta(minutes=1),
        next_run_at=None,
    )
    _seed_subscription(
        database,
        platform="xhs",
        remote_id="capacity-two",
        now=now,
        next_run_at=None,
    )
    with database.session() as session:
        repository = SchedulerRepository(session)
        assert len(repository.materialize_due(limit=10, now=now)) == 2
        repository.update_lane(
            LanePolicy(
                scope_type="platform",
                platform="xhs",
                max_concurrency=1,
                min_start_interval_seconds=0,
            ),
            now=now,
        )

    start = Barrier(2)

    def claim(worker_id: str) -> str | None:
        start.wait(timeout=10)
        with database.session() as session:
            result = SchedulerRepository(session).claim_next(
                worker_id=worker_id,
                global_capacity=2,
                now=now,
            )
            return None if result is None else result.job_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (executor.submit(claim, "capacity-a"), executor.submit(claim, "capacity-b"))
        results = [future.result() for future in futures]
    assert sum(result is not None for result in results) == 1
    with database.session() as session:
        active = session.scalars(
            select(Job).where(
                Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                Job.status == "claimed",
                Job.platform == "xhs",
            )
        ).all()
        assert len(active) == 1


def test_independent_sqlite_claims_respect_global_capacity(database: Database) -> None:
    now = datetime(2026, 8, 30, 4, 40, tzinfo=UTC)
    _seed_subscription(
        database,
        platform="xhs",
        remote_id="global-capacity-one",
        now=now - timedelta(minutes=2),
        next_run_at=now - timedelta(minutes=2),
    )
    _seed_subscription(
        database,
        platform="bili",
        remote_id="global-capacity-two",
        now=now - timedelta(minutes=1),
        next_run_at=now - timedelta(minutes=1),
    )
    with database.session() as session:
        cycles = SchedulerRepository(session).materialize_due(limit=10, now=now)
        assert len(cycles) == 2
        queued_job_ids = {cycle.job_id for cycle in cycles}

    start = Barrier(2)

    def claim(worker_id: str) -> str | None:
        independent = Database(database.url)
        try:
            with independent.session() as session:
                session.connection()
                start.wait(timeout=10)
                result = SchedulerRepository(session).claim_next(
                    worker_id=worker_id,
                    global_capacity=1,
                    now=now,
                )
                return None if result is None else result.job_id
        finally:
            independent.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (executor.submit(claim, "global-a"), executor.submit(claim, "global-b"))
        results = [future.result() for future in futures]

    claimed_job_ids = {job_id for job_id in results if job_id is not None}
    assert results.count(None) == 1
    assert len(claimed_job_ids) == 1
    assert claimed_job_ids <= queued_job_ids


def test_account_capacity_limits_shared_account_despite_platform_capacity(database: Database) -> None:
    now = datetime(2026, 8, 30, 4, 50, tzinfo=UTC)
    account_id, first_subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="shared-account-one",
        now=now - timedelta(minutes=2),
        next_run_at=now - timedelta(minutes=2),
    )
    with database.session() as session:
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform="xhs",
                remote_id="shared-account-two",
                display_name="author-shared-account-two",
            )
        )
        second_subscription = SubscriptionRepository(session).create(
            account_id=account_id,
            author_id=author.id,
            interval_seconds=60,
            next_run_at=now - timedelta(minutes=1),
            policy={"handler": "fake"},
        )
        second_subscription.created_at = now - timedelta(minutes=1)
        second_subscription.updated_at = now - timedelta(minutes=1)
        session.flush()
        second_subscription_id = second_subscription.id

    with database.session() as session:
        repository = SchedulerRepository(session)
        cycles = repository.materialize_due(limit=10, now=now)
        assert {cycle.subscription_id for cycle in cycles} == {
            first_subscription_id,
            second_subscription_id,
        }
        repository.update_lane(
            LanePolicy(
                scope_type="platform",
                platform="xhs",
                max_concurrency=2,
                min_start_interval_seconds=0,
            ),
            now=now,
        )
        repository.update_lane(
            LanePolicy(
                scope_type="account",
                platform="xhs",
                account_id=account_id,
                max_concurrency=1,
                min_start_interval_seconds=0,
            ),
            now=now,
        )

    first_connection = Database(database.url)
    try:
        with first_connection.session() as session:
            first_claim = SchedulerRepository(session).claim_next(
                worker_id="account-capacity-first",
                global_capacity=2,
                now=now,
            )
    finally:
        first_connection.dispose()
    assert first_claim is not None

    second_connection = Database(database.url)
    try:
        with second_connection.session() as session:
            second_claim = SchedulerRepository(session).claim_next(
                worker_id="account-capacity-second",
                global_capacity=2,
                now=now,
            )
    finally:
        second_connection.dispose()
    assert second_claim is None

    with database.session() as session:
        shared_account_jobs = session.scalars(
            select(Job).where(
                Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                Job.account_id == account_id,
            )
        ).all()
        assert sorted(job.status for job in shared_account_jobs) == ["claimed", "queued"]


@pytest.mark.parametrize("outcome", ["succeed", "cancel"])
def test_min_start_interval_survives_terminal_outcome_until_exact_deadline(
    database: Database,
    outcome: Literal["succeed", "cancel"],
) -> None:
    now = datetime(2026, 8, 30, 4, 55, tzinfo=UTC)
    first_account_id, first_subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id=f"persistent-interval-first-{outcome}",
        now=now - timedelta(minutes=2),
        next_run_at=now - timedelta(minutes=2),
    )
    second_account_id, second_subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id=f"persistent-interval-second-{outcome}",
        now=now - timedelta(minutes=1),
        next_run_at=now - timedelta(minutes=1),
    )
    with database.session() as session:
        repository = SchedulerRepository(session)
        cycles = repository.materialize_due(limit=10, now=now)
        jobs_by_subscription = {cycle.subscription_id: cycle.job_id for cycle in cycles}
        assert set(jobs_by_subscription) == {first_subscription_id, second_subscription_id}
        repository.update_lane(
            LanePolicy(
                scope_type="platform",
                platform="xhs",
                max_concurrency=2,
                min_start_interval_seconds=30,
            ),
            now=now,
        )
        for account_id in (first_account_id, second_account_id):
            repository.update_lane(
                LanePolicy(
                    scope_type="account",
                    platform="xhs",
                    account_id=account_id,
                    max_concurrency=2,
                    min_start_interval_seconds=0,
                ),
                now=now,
            )

    worker_id = f"persistent-interval-{outcome}"
    with database.session() as session:
        repository = SchedulerRepository(session)
        claim = repository.claim_next(worker_id=worker_id, global_capacity=2, now=now)
        assert claim is not None
        assert claim.job_id == jobs_by_subscription[first_subscription_id]
        running = repository.start(
            claim.job_id,
            worker_id=worker_id,
            lease_token=claim.lease_token,
            now=now,
        )
        terminal_at = now + timedelta(seconds=1)
        if outcome == "succeed":
            terminal = repository.succeed(
                running.job_id,
                worker_id=worker_id,
                lease_token=running.lease_token,
                now=terminal_at,
            )
            assert terminal.status == "succeeded"
        else:
            terminal = repository.cancel(running.job_id, now=terminal_at)
            assert terminal.status == "cancelled"

    deadline = now + timedelta(seconds=30)
    with database.session() as session:
        platform_lane = SchedulerRepository(session).get_lane(
            scope_type="platform",
            platform="xhs",
        )
        assert platform_lane is not None
        assert platform_lane.next_start_at == deadline

    before_deadline = Database(database.url)
    try:
        with before_deadline.session() as session:
            blocked = SchedulerRepository(session).claim_next(
                worker_id=f"before-deadline-{outcome}",
                global_capacity=2,
                now=deadline - timedelta(microseconds=1),
            )
    finally:
        before_deadline.dispose()
    assert blocked is None

    at_deadline = Database(database.url)
    try:
        with at_deadline.session() as session:
            permitted = SchedulerRepository(session).claim_next(
                worker_id=f"at-deadline-{outcome}",
                global_capacity=2,
                now=deadline,
            )
    finally:
        at_deadline.dispose()
    assert permitted is not None
    assert permitted.job_id == jobs_by_subscription[second_subscription_id]


def test_independent_sqlite_claims_reserve_one_expired_circuit_probe(database: Database) -> None:
    now = datetime(2026, 8, 30, 4, 58, tzinfo=UTC)
    first_account_id, _first_subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="concurrent-probe-one",
        now=now - timedelta(minutes=2),
        next_run_at=now - timedelta(minutes=2),
    )
    second_account_id, _second_subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="concurrent-probe-two",
        now=now - timedelta(minutes=1),
        next_run_at=now - timedelta(minutes=1),
    )
    with database.session() as session:
        repository = SchedulerRepository(session)
        cycles = repository.materialize_due(limit=10, now=now)
        assert len(cycles) == 2
        queued_job_ids = {cycle.job_id for cycle in cycles}
        repository.update_lane(
            LanePolicy(
                scope_type="platform",
                platform="xhs",
                max_concurrency=2,
                min_start_interval_seconds=0,
            ),
            now=now,
        )
        for account_id in (first_account_id, second_account_id):
            repository.update_lane(
                LanePolicy(
                    scope_type="account",
                    platform="xhs",
                    account_id=account_id,
                    max_concurrency=2,
                    min_start_interval_seconds=0,
                ),
                now=now,
            )
        platform_lane = session.scalar(
            select(SchedulerLane).where(
                SchedulerLane.scope_type == "platform",
                SchedulerLane.platform == "xhs",
            )
        )
        assert platform_lane is not None
        platform_lane.circuit_state = "open"
        platform_lane.circuit_open_until = now
        platform_lane.next_start_at = None
        session.flush()

    start = Barrier(2)

    def claim(worker_id: str) -> str | None:
        independent = Database(database.url)
        try:
            with independent.session() as session:
                session.connection()
                start.wait(timeout=10)
                result = SchedulerRepository(session).claim_next(
                    worker_id=worker_id,
                    global_capacity=2,
                    now=now,
                )
                return None if result is None else result.job_id
        finally:
            independent.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (executor.submit(claim, "probe-race-a"), executor.submit(claim, "probe-race-b"))
        results = [future.result() for future in futures]

    claimed_job_ids = {job_id for job_id in results if job_id is not None}
    assert results.count(None) == 1
    assert len(claimed_job_ids) == 1
    winner = claimed_job_ids.pop()
    assert winner in queued_job_ids

    with database.session() as session:
        platform_lane = session.scalar(
            select(SchedulerLane).where(
                SchedulerLane.scope_type == "platform",
                SchedulerLane.platform == "xhs",
            )
        )
        assert platform_lane is not None
        assert platform_lane.circuit_state == "half_open"
        assert platform_lane.half_open_job_id == winner


def test_scoped_generic_claim_rejects_empty_types_before_mutation_and_preserves_0005_jobs(
    database: Database,
) -> None:
    now = datetime(2026, 8, 30, 5, 0, tzinfo=UTC)
    expired_at = now - timedelta(seconds=1)
    with database.session() as session:
        jobs = JobRepository(session)
        download = jobs.enqueue(
            job_type="asset_download",
            natural_key="download-scope-sentinel",
            payload={"prepared_result": "unchanged-download"},
        )
        export = jobs.enqueue(
            job_type="export.emby",
            natural_key="export-scope-sentinel",
            payload={"publication_intent": "unchanged-export"},
        )
        sync = jobs.enqueue(
            job_type=SYNC_SUBSCRIPTION_JOB_TYPE,
            natural_key="scope-only-sync",
        )
        for job in (download, export, sync):
            job.status = "running"
            job.attempts = 1
            job.lease_owner = "expired-worker"
            job.lease_token = f"token-{job.id}"[:36]
            job.lease_expires_at = expired_at
        session.flush()
        download_id, export_id, sync_id = download.id, export.id, sync.id

    with database.session() as session:
        with pytest.raises(ValueError, match="must not be empty"):
            JobRepository(session).claim_next(
                worker_id="sync-worker",
                now=now,
                job_types=(),
            )
        session.expire_all()
        assert session.get(Job, download_id).status == "running"  # type: ignore[union-attr]
        assert session.get(Job, export_id).status == "running"  # type: ignore[union-attr]
        assert session.get(Job, sync_id).status == "running"  # type: ignore[union-attr]

    with database.session() as session:
        claimed = JobRepository(session).claim_next(
            worker_id="sync-worker",
            now=now,
            job_types=(SYNC_SUBSCRIPTION_JOB_TYPE,),
        )
        assert claimed is not None and claimed.id == sync_id

    with database.session() as session:
        persisted_download = session.get(Job, download_id)
        persisted_export = session.get(Job, export_id)
        assert persisted_download is not None and persisted_export is not None
        assert (
            persisted_download.status,
            persisted_download.attempts,
            persisted_download.lease_owner,
            persisted_download.payload,
        ) == ("running", 1, "expired-worker", {"prepared_result": "unchanged-download"})
        assert (
            persisted_export.status,
            persisted_export.attempts,
            persisted_export.lease_owner,
            persisted_export.payload,
        ) == ("running", 1, "expired-worker", {"publication_intent": "unchanged-export"})


def test_claim_scans_past_blocked_head_and_enforces_single_half_open_probe(database: Database) -> None:
    now = datetime(2026, 8, 30, 6, 0, tzinfo=UTC)
    xhs_account, first_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="blocked-head",
        now=now - timedelta(minutes=2),
        next_run_at=None,
    )
    _bili_account, second_id = _seed_subscription(
        database,
        platform="bili",
        remote_id="fair-tail",
        now=now - timedelta(minutes=1),
        next_run_at=None,
    )
    with database.session() as session:
        SchedulerRepository(session).materialize_due(limit=10, now=now)
        session.add(
            SchedulerLane(
                scope_type="platform",
                platform="xhs",
                next_start_at=now + timedelta(minutes=1),
            )
        )

    with database.session() as session:
        repository = SchedulerRepository(session)
        claim = repository.claim_next(
            worker_id="fair-worker",
            global_capacity=2,
            now=now,
        )
        assert claim is not None and claim.subscription_id == second_id
        assert claim.subscription_id != first_id
        repository.cancel(claim.job_id, now=now)
        repository.pause_subscription(second_id, now=now)

    later = now + timedelta(minutes=2)
    _third_account, third_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="half-open-one",
        now=later - timedelta(minutes=2),
        next_run_at=None,
    )
    _fourth_account, fourth_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="half-open-two",
        now=later - timedelta(minutes=1),
        next_run_at=None,
    )
    with database.session() as session:
        repository = SchedulerRepository(session)
        repository.materialize_due(limit=10, now=later)
        repository.update_lane(
            LanePolicy(
                scope_type="platform",
                platform="xhs",
                max_concurrency=2,
                min_start_interval_seconds=0,
            ),
            now=later,
        )
        account_policy = LanePolicy(
            scope_type="account",
            platform="xhs",
            account_id=xhs_account,
            max_concurrency=2,
            min_start_interval_seconds=0,
        )
        repository.update_lane(account_policy, now=later)
        platform_lane = session.scalar(
            select(SchedulerLane).where(
                SchedulerLane.scope_type == "platform",
                SchedulerLane.platform == "xhs",
            )
        )
        assert platform_lane is not None
        platform_lane.circuit_state = "open"
        platform_lane.circuit_open_until = later - timedelta(seconds=1)
        platform_lane.next_start_at = None
        session.flush()

    with database.session() as session:
        repository = SchedulerRepository(session)
        probe = repository.claim_next(worker_id="probe-one", global_capacity=3, now=later)
        assert probe is not None and probe.subscription_id in {first_id, third_id, fourth_id}
        blocked = repository.claim_next(worker_id="probe-two", global_capacity=3, now=later)
        assert blocked is None

    with database.session() as session:
        platform_lane = session.scalar(
            select(SchedulerLane).where(
                SchedulerLane.scope_type == "platform",
                SchedulerLane.platform == "xhs",
            )
        )
        assert platform_lane is not None
        assert platform_lane.circuit_state == "half_open"
        assert platform_lane.half_open_job_id is not None


def test_waiting_requires_explicit_resume_and_cancel_fences_heartbeat(database: Database) -> None:
    now = datetime(2026, 8, 30, 7, 0, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="waiting",
        now=now,
        next_run_at=None,
    )
    _materialize_one(database, subscription_id, now=now)
    job_id, token = _claim_and_start(database, worker_id="waiting-worker", now=now)

    with database.session() as session:
        repository = SchedulerRepository(session)
        renewed = repository.heartbeat(
            job_id,
            worker_id="waiting-worker",
            lease_token=token,
            lease_seconds=30,
            now=now + timedelta(seconds=10),
        )
        assert renewed.lease_expires_at == now + timedelta(seconds=40)
        waiting = repository.wait(
            job_id,
            worker_id="waiting-worker",
            lease_token=token,
            status="waiting_auth",
            error_code="auth_expired",
            now=now + timedelta(seconds=11),
        )
        assert waiting.status == "waiting_auth"

    with database.session() as session:
        repository = SchedulerRepository(session)
        assert (
            repository.claim_next(
                worker_id="automatic-worker",
                global_capacity=1,
                now=now + timedelta(minutes=1),
            )
            is None
        )
        resumed = repository.resume(job_id, now=now + timedelta(minutes=1))
        assert resumed.status == "queued"

    resumed_at = now + timedelta(minutes=1, seconds=5)
    with database.session() as session:
        repository = SchedulerRepository(session)
        claim = repository.claim_next(
            worker_id="resumed-worker",
            global_capacity=1,
            now=resumed_at,
        )
        assert claim is not None and claim.job_id == job_id
        running = repository.start(
            claim.job_id,
            worker_id="resumed-worker",
            lease_token=claim.lease_token,
            now=resumed_at,
        )
        cancelled = repository.cancel(job_id, now=resumed_at + timedelta(seconds=1))
        assert cancelled.status == "cancelled"
        with pytest.raises(LeaseLostError):
            repository.heartbeat(
                job_id,
                worker_id="resumed-worker",
                lease_token=running.lease_token,
                now=resumed_at + timedelta(seconds=2),
            )


def test_independent_cancel_and_heartbeat_are_writer_serialized_and_aba_safe(database: Database) -> None:
    now = datetime(2026, 8, 30, 7, 30, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="bili",
        remote_id="writer-aba",
        now=now,
        next_run_at=None,
    )
    _materialize_one(database, subscription_id, now=now)
    job_id, token = _claim_and_start(database, worker_id="aba-worker", now=now)
    start = Barrier(2)

    def heartbeat() -> str:
        start.wait(timeout=10)
        try:
            with database.session() as session:
                SchedulerRepository(session).heartbeat(
                    job_id,
                    worker_id="aba-worker",
                    lease_token=token,
                    now=now + timedelta(seconds=1),
                )
        except LeaseLostError:
            return "lease_lost"
        return "renewed"

    def cancel() -> str:
        start.wait(timeout=10)
        with database.session() as session:
            return (
                SchedulerRepository(session)
                .cancel(
                    job_id,
                    now=now + timedelta(seconds=1),
                )
                .status
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        heartbeat_future = executor.submit(heartbeat)
        cancel_future = executor.submit(cancel)
        assert cancel_future.result() == "cancelled"
        assert heartbeat_future.result() in {"renewed", "lease_lost"}
    with database.session() as session:
        job = session.get(Job, job_id)
        assert job is not None and job.status == "cancelled"
        assert job.lease_owner is None and job.lease_token is None


def test_assert_owned_holds_sqlite_writer_slot_against_independent_cancel(database: Database) -> None:
    now = datetime(2026, 8, 30, 7, 35, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="bili",
        remote_id="guarded-cancel",
        now=now,
        next_run_at=None,
    )
    _materialize_one(database, subscription_id, now=now)
    job_id, token = _claim_and_start(database, worker_id="guarded-worker", now=now)
    guard_ready = Event()
    release_guard = Event()
    cancel_sql_started = Event()
    cancel_done = Event()

    def guard_and_mutate() -> int:
        with database.session() as session:
            repository = SchedulerRepository(session)
            owned = repository.assert_owned(
                job_id,
                worker_id="guarded-worker",
                lease_token=token,
                now=now + timedelta(seconds=1),
            )
            assert owned.job_id == job_id
            job = session.get(Job, job_id)
            assert job is not None
            job.priority = 17
            session.flush()
            guard_ready.set()
            if not release_guard.wait(timeout=10):
                raise AssertionError("timed out waiting to release guarded transaction")
            return job.priority

    def cancel_independently() -> str:
        if not guard_ready.wait(timeout=10):
            raise AssertionError("guarded transaction did not acquire the writer slot")
        try:
            with database.session() as session:
                return (
                    SchedulerRepository(session)
                    .cancel(
                        job_id,
                        now=now + timedelta(seconds=2),
                    )
                    .status
                )
        finally:
            cancel_done.set()

    def note_cancel_update(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        if current_thread().name.startswith("cancel-writer") and statement.lstrip().upper().startswith("UPDATE"):
            cancel_sql_started.set()

    event.listen(database.engine, "before_cursor_execute", note_cancel_update)
    try:
        with (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="guard-owner") as guard_executor,
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="cancel-writer") as cancel_executor,
        ):
            guard_future = guard_executor.submit(guard_and_mutate)
            try:
                assert guard_ready.wait(timeout=10)
                cancel_future = cancel_executor.submit(cancel_independently)
                assert cancel_sql_started.wait(timeout=10)
                assert not cancel_done.is_set()
                assert not cancel_future.done()
            finally:
                release_guard.set()
            assert guard_future.result(timeout=10) == 17
            assert cancel_future.result(timeout=10) == "cancelled"
    finally:
        release_guard.set()
        event.remove(database.engine, "before_cursor_execute", note_cancel_update)

    with database.session() as session:
        cancelled = session.get(Job, job_id)
        assert cancelled is not None
        assert cancelled.status == "cancelled"
        assert cancelled.priority == 17
        assert cancelled.lease_owner is None
        assert cancelled.lease_token is None
        before_stale_guard = _job_execution_state(cancelled)

    with database.session() as session, pytest.raises(LeaseLostError):
        SchedulerRepository(session).assert_owned(
            job_id,
            worker_id="guarded-worker",
            lease_token=token,
            now=now + timedelta(seconds=3),
        )

    with database.session() as session:
        cancelled = session.get(Job, job_id)
        assert cancelled is not None
        assert _job_execution_state(cancelled) == before_stale_guard


def test_assert_owned_rejects_reclaimed_token_without_mutating_replacement(database: Database) -> None:
    now = datetime(2026, 8, 30, 7, 40, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="guarded-reclaim",
        now=now,
        next_run_at=None,
    )
    _materialize_one(database, subscription_id, now=now)
    job_id, stale_token = _claim_and_start(
        database,
        worker_id="stale-worker",
        now=now,
        lease_seconds=1,
    )

    reclaimed_at = now + timedelta(seconds=6)
    with database.session() as session:
        repository = SchedulerRepository(session)
        replacement = repository.claim_next(
            worker_id="replacement-worker",
            global_capacity=1,
            lease_seconds=30,
            now=reclaimed_at,
        )
        assert replacement is not None
        assert replacement.job_id == job_id
        running = repository.start(
            replacement.job_id,
            worker_id="replacement-worker",
            lease_token=replacement.lease_token,
            now=reclaimed_at,
        )
        replacement_token = running.lease_token
        assert replacement_token != stale_token

    with database.session() as session:
        replacement_job = session.get(Job, job_id)
        assert replacement_job is not None
        assert replacement_job.status == "running"
        assert replacement_job.lease_owner == "replacement-worker"
        assert replacement_job.lease_token == replacement_token
        assert replacement_job.run_id is None
        before_stale_guard = _job_execution_state(replacement_job)

    with database.session() as session, pytest.raises(LeaseLostError):
        SchedulerRepository(session).assert_owned(
            job_id,
            worker_id="stale-worker",
            lease_token=stale_token,
            now=reclaimed_at,
        )

    with database.session() as session:
        replacement_job = session.get(Job, job_id)
        assert replacement_job is not None
        assert _job_execution_state(replacement_job) == before_stale_guard


def test_attach_run_requires_exact_lease_scope_and_expected_attachment(database: Database) -> None:
    now = datetime(2026, 8, 30, 7, 42, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="bili",
        remote_id="attach-run",
        now=now,
        next_run_at=None,
    )
    _foreign_account_id, foreign_subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="attach-run-foreign",
        now=now,
        enabled=False,
        next_run_at=None,
    )
    _materialize_one(database, subscription_id, now=now)
    job_id, token = _claim_and_start(database, worker_id="attach-worker", now=now)
    with database.session() as session:
        runs = SyncRunRepository(session)
        first_run_id = runs.create(subscription_id=subscription_id).id
        second_run_id = runs.create(subscription_id=subscription_id).id
        foreign_run_id = runs.create(subscription_id=foreign_subscription_id).id

    with database.session() as session:
        attached = SchedulerRepository(session).attach_run(
            job_id,
            worker_id="attach-worker",
            lease_token=token,
            run_id=first_run_id,
            expected_current_run_id=None,
            now=now + timedelta(seconds=1),
        )
        assert attached.run_id == first_run_id

    with database.session() as session, pytest.raises(LeaseLostError, match="attachment changed"):
        SchedulerRepository(session).attach_run(
            job_id,
            worker_id="attach-worker",
            lease_token=token,
            run_id=second_run_id,
            expected_current_run_id=None,
            now=now + timedelta(seconds=2),
        )
    with database.session() as session, pytest.raises(SchedulerRepositoryError, match="scope is invalid"):
        SchedulerRepository(session).attach_run(
            job_id,
            worker_id="attach-worker",
            lease_token=token,
            run_id=foreign_run_id,
            expected_current_run_id=first_run_id,
            now=now + timedelta(seconds=2),
        )

    with database.session() as session, pytest.raises(SchedulerRepositoryError, match="not terminal"):
        SchedulerRepository(session).attach_run(
            job_id,
            worker_id="attach-worker",
            lease_token=token,
            run_id=second_run_id,
            expected_current_run_id=first_run_id,
            now=now + timedelta(seconds=3),
        )
    with database.session() as session:
        SyncRunRepository(session).set_status(
            first_run_id,
            "cancelled",
            expected_status="queued",
            error_code="scheduler_replaced",
            at=now + timedelta(seconds=3),
        )
        attached = SchedulerRepository(session).attach_run(
            job_id,
            worker_id="attach-worker",
            lease_token=token,
            run_id=second_run_id,
            expected_current_run_id=first_run_id,
            now=now + timedelta(seconds=3),
        )
        assert attached.run_id == second_run_id
    with database.session() as session:
        job = session.get(Job, job_id)
        assert job is not None and job.run_id == second_run_id
        cancelled = SchedulerRepository(session).cancel(job_id, now=now + timedelta(seconds=4))
        assert cancelled.status == "cancelled"
    with database.session() as session:
        attached_run = SyncRunRepository(session).require(second_run_id)
        assert attached_run.status == "cancelled"
        assert attached_run.error_code == "scheduler_cancelled"


def test_reclaim_cancels_attached_run_before_replacement_attempt(database: Database) -> None:
    now = datetime(2026, 8, 30, 7, 44, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="reclaim-attached-run",
        now=now,
        next_run_at=None,
    )
    _materialize_one(database, subscription_id, now=now)
    job_id, stale_token = _claim_and_start(
        database,
        worker_id="stale-run-worker",
        now=now,
        lease_seconds=1,
    )
    with database.session() as session:
        runs = SyncRunRepository(session)
        run = runs.create(subscription_id=subscription_id)
        runs.set_status(run.id, "claimed", expected_status="queued", at=now)
        runs.set_status(run.id, "running", expected_status="claimed", at=now)
        SchedulerRepository(session).attach_run(
            job_id,
            worker_id="stale-run-worker",
            lease_token=stale_token,
            run_id=run.id,
            expected_current_run_id=None,
            now=now,
        )
        run_id = run.id

    reclaimed_at = now + timedelta(seconds=6)
    with database.session() as session:
        replacement = SchedulerRepository(session).claim_next(
            worker_id="replacement-run-worker",
            global_capacity=1,
            lease_seconds=30,
            now=reclaimed_at,
        )
        assert replacement is not None
        assert replacement.job_id == job_id
        assert replacement.attempt == 2
        assert replacement.run_id == run_id
    with database.session() as session:
        cancelled_run = SyncRunRepository(session).require(run_id)
        assert cancelled_run.status == "cancelled"
        assert cancelled_run.error_code == "scheduler_lease_lost"

    with database.session() as session, pytest.raises(LeaseLostError):
        SchedulerRepository(session).attach_run(
            job_id,
            worker_id="stale-run-worker",
            lease_token=stale_token,
            run_id=str(uuid4()),
            expected_current_run_id=run_id,
            now=reclaimed_at,
        )


def test_reclaim_reconciles_succeeded_attachment_at_last_attempt(database: Database) -> None:
    now = datetime(2026, 8, 30, 7, 44, 30, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="bili",
        remote_id="reclaim-succeeded-run",
        now=now,
        next_run_at=None,
    )
    with database.session() as session:
        cycles = SchedulerRepository(session).materialize_due(
            limit=1,
            retry_policy=RetryPolicy(max_attempts=1),
            now=now,
        )
        assert len(cycles) == 1
        job_id = cycles[0].job_id
    worker_id = "last-attempt-success-worker"
    job_id, lease_token = _claim_and_start(
        database,
        worker_id=worker_id,
        now=now,
        lease_seconds=1,
    )
    run_id = _attach_succeeded_run(
        database,
        subscription_id=subscription_id,
        job_id=job_id,
        worker_id=worker_id,
        lease_token=lease_token,
        now=now,
    )

    reclaimed_at = now + timedelta(seconds=2)
    with database.session() as session:
        replacement = SchedulerRepository(session).claim_next(
            worker_id="must-not-replace-success",
            global_capacity=1,
            lease_seconds=30,
            now=reclaimed_at,
        )
        assert replacement is None

    with database.session() as session:
        job = session.get(Job, job_id)
        subscription = session.get(Subscription, subscription_id)
        run = SyncRunRepository(session).require(run_id)
        assert job is not None
        assert (job.status, job.attempts, job.run_id) == ("succeeded", 1, run_id)
        assert job.lease_owner is None and job.lease_token is None
        assert job.last_error_code is None
        assert run.status == "succeeded"
        assert subscription is not None
        assert subscription.consecutive_failures == 0
        assert subscription.last_success_at == reclaimed_at
        assert subscription.next_run_at == reclaimed_at + timedelta(seconds=60)


def test_cancel_reconciles_succeeded_attachment_instead_of_cancelling(database: Database) -> None:
    now = datetime(2026, 8, 30, 7, 44, 45, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="cancel-succeeded-run",
        now=now,
        next_run_at=None,
    )
    _materialize_one(database, subscription_id, now=now)
    worker_id = "cancel-authoritative-success-worker"
    job_id, lease_token = _claim_and_start(database, worker_id=worker_id, now=now)
    run_id = _attach_succeeded_run(
        database,
        subscription_id=subscription_id,
        job_id=job_id,
        worker_id=worker_id,
        lease_token=lease_token,
        now=now,
    )

    cancelled_at = now + timedelta(seconds=1)
    with database.session() as session:
        reconciled = SchedulerRepository(session).cancel(job_id, now=cancelled_at)
        assert (reconciled.status, reconciled.run_id) == ("succeeded", run_id)

    with database.session() as session:
        job = session.get(Job, job_id)
        subscription = session.get(Subscription, subscription_id)
        run = SyncRunRepository(session).require(run_id)
        assert job is not None and job.status == "succeeded"
        assert job.last_error_code is None
        assert run.status == "succeeded"
        assert subscription is not None
        assert subscription.consecutive_failures == 0
        assert subscription.last_success_at == cancelled_at


@pytest.mark.parametrize("outcome", ["fail", "wait"])
@pytest.mark.parametrize("pass_run_id", [False, True], ids=["implicit-attachment", "explicit-attachment"])
def test_failure_finalizers_reject_authoritative_succeeded_attachment(
    database: Database,
    outcome: Literal["fail", "wait"],
    pass_run_id: bool,
) -> None:
    now = datetime(2026, 8, 30, 7, 44, 50, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="bili",
        remote_id=f"reject-succeeded-{outcome}-{pass_run_id}",
        now=now,
        next_run_at=None,
    )
    _materialize_one(database, subscription_id, now=now)
    worker_id = "reject-succeeded-finalizer-worker"
    job_id, lease_token = _claim_and_start(database, worker_id=worker_id, now=now)
    run_id = _attach_succeeded_run(
        database,
        subscription_id=subscription_id,
        job_id=job_id,
        worker_id=worker_id,
        lease_token=lease_token,
        now=now,
    )

    with (
        database.session() as session,
        pytest.raises(
            SchedulerRepositoryError,
            match="succeeded attached run",
        ),
    ):
        repository = SchedulerRepository(session)
        if outcome == "fail":
            repository.fail(
                job_id,
                worker_id=worker_id,
                lease_token=lease_token,
                error_code="temporary_upstream",
                run_id=run_id if pass_run_id else None,
                now=now + timedelta(seconds=1),
            )
        else:
            repository.wait(
                job_id,
                worker_id=worker_id,
                lease_token=lease_token,
                status="waiting_auth",
                error_code="auth_expired",
                run_id=run_id if pass_run_id else None,
                now=now + timedelta(seconds=1),
            )

    with database.session() as session:
        job = session.get(Job, job_id)
        subscription = session.get(Subscription, subscription_id)
        run = SyncRunRepository(session).require(run_id)
        assert job is not None and job.status == "running"
        assert job.run_id == run_id and job.lease_token == lease_token
        assert run.status == "succeeded"
        assert subscription is not None and subscription.consecutive_failures == 0


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        ("succeed", "succeeded"),
        ("fail", "failed_retryable"),
        ("wait", "waiting_auth"),
    ],
)
def test_result_run_binding_rejects_unknown_and_foreign_subscription_runs(
    database: Database,
    outcome: Literal["succeed", "fail", "wait"],
    expected_status: str,
) -> None:
    now = datetime(2026, 8, 30, 7, 45, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="bili",
        remote_id=f"run-binding-{outcome}",
        now=now,
        next_run_at=None,
    )
    _foreign_account_id, foreign_subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id=f"foreign-run-{outcome}",
        now=now,
        enabled=False,
        next_run_at=None,
    )
    _materialize_one(database, subscription_id, now=now)
    worker_id = f"run-binding-worker-{outcome}"
    job_id, token = _claim_and_start(database, worker_id=worker_id, now=now)

    with database.session() as session:
        run_repository = SyncRunRepository(session)
        owned_run_id = run_repository.create(subscription_id=subscription_id).id
        foreign_run_id = run_repository.create(subscription_id=foreign_subscription_id).id

    def finalize(repository: SchedulerRepository, run_id: str) -> SchedulerJobSummary:
        if outcome == "succeed":
            return repository.succeed(
                job_id,
                worker_id=worker_id,
                lease_token=token,
                run_id=run_id,
                now=now + timedelta(seconds=1),
            )
        if outcome == "fail":
            return repository.fail(
                job_id,
                worker_id=worker_id,
                lease_token=token,
                error_code="temporary_upstream",
                run_id=run_id,
                now=now + timedelta(seconds=1),
            )
        return repository.wait(
            job_id,
            worker_id=worker_id,
            lease_token=token,
            status="waiting_auth",
            error_code="auth_expired",
            run_id=run_id,
            now=now + timedelta(seconds=1),
        )

    with database.session() as session:
        running = session.get(Job, job_id)
        assert running is not None
        initial_state = _job_execution_state(running)

    for invalid_run_id in (str(uuid4()), foreign_run_id):
        with database.session() as session, pytest.raises(SchedulerRepositoryError, match="run scope is invalid"):
            finalize(SchedulerRepository(session), invalid_run_id)
        with database.session() as session:
            running = session.get(Job, job_id)
            assert running is not None
            assert running.status == "running"
            assert running.lease_owner == worker_id
            assert running.lease_token == token
            assert running.run_id is None
            assert _job_execution_state(running) == initial_state

    with database.session() as session:
        completed = finalize(SchedulerRepository(session), owned_run_id)
        assert completed.status == expected_status
        assert completed.run_id == owned_run_id

    with database.session() as session:
        completed_job = session.get(Job, job_id)
        assert completed_job is not None
        assert completed_job.status == expected_status
        assert completed_job.run_id == owned_run_id


def test_retry_exhaustion_terminalizes_once_and_scheduler_summaries_are_redacted(database: Database) -> None:
    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="retry",
        now=now,
        next_run_at=None,
    )
    with database.session() as session:
        cycles = SchedulerRepository(session).materialize_due(
            limit=1,
            now=now,
            retry_policy=RetryPolicy(max_attempts=2),
        )
        assert len(cycles) == 1

    first_job, first_token = _claim_and_start(database, worker_id="retry-worker-one", now=now)
    retry_at = now + timedelta(seconds=30)
    with database.session() as session:
        failed = SchedulerRepository(session).fail(
            first_job,
            worker_id="retry-worker-one",
            lease_token=first_token,
            error_code="temporary_upstream",
            retry_at=retry_at,
            now=now + timedelta(seconds=1),
        )
        assert failed.status == "retry_wait"
        assert "payload" not in repr(failed)
        assert "lease_token" not in repr(failed)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None and subscription.next_run_at is None

    second_job, second_token = _claim_and_start(
        database,
        worker_id="retry-worker-two",
        now=retry_at + timedelta(seconds=5),
    )
    assert second_job == first_job
    finished_at = retry_at + timedelta(seconds=6)
    with database.session() as session:
        terminal = SchedulerRepository(session).fail(
            second_job,
            worker_id="retry-worker-two",
            lease_token=second_token,
            error_code="temporary_upstream",
            now=finished_at,
        )
        assert terminal.status == "failed_terminal"
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        assert subscription.next_run_at == finished_at + timedelta(seconds=60)
        assert subscription.consecutive_failures == 1
        job = session.get(Job, first_job)
        assert job is not None
        assert job.last_error_code == "temporary_upstream"
        assert job.last_error_message is None

    with database.session() as session:
        assert SchedulerRepository(session).cancel(first_job, now=finished_at + timedelta(seconds=1)).status == (
            "failed_terminal"
        )
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None and subscription.consecutive_failures == 1


def test_expired_half_open_probe_reopens_circuit_before_retry_requeue(database: Database) -> None:
    now = datetime(2026, 8, 30, 8, 30, tzinfo=UTC)
    account_id, subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="expired-probe",
        now=now,
        next_run_at=None,
    )
    _materialize_one(database, subscription_id, now=now)
    with database.session() as session:
        repository = SchedulerRepository(session)
        repository.update_lane(
            LanePolicy(
                scope_type="platform",
                platform="xhs",
                min_start_interval_seconds=0,
            ),
            now=now,
        )
        repository.update_lane(
            LanePolicy(
                scope_type="account",
                platform="xhs",
                account_id=account_id,
                min_start_interval_seconds=0,
            ),
            now=now,
        )
        lanes = session.scalars(select(SchedulerLane)).all()
        for lane in lanes:
            lane.circuit_state = "open"
            lane.circuit_open_until = now - timedelta(seconds=1)
        session.flush()

    with database.session() as session:
        probe = SchedulerRepository(session).claim_next(
            worker_id="expiring-probe",
            global_capacity=1,
            lease_seconds=1,
            now=now,
        )
        assert probe is not None

    expired_at = now + timedelta(seconds=2)
    with database.session() as session:
        assert (
            SchedulerRepository(session).claim_next(
                worker_id="replacement-probe",
                global_capacity=1,
                now=expired_at,
            )
            is None
        )
    with database.session() as session:
        lane_summaries = SchedulerRepository(session).list_lanes()
        assert len(lane_summaries) == 2
        assert all(lane.circuit_state == "open" for lane in lane_summaries)
        assert all(lane.half_open_job_id is None for lane in lane_summaries)
        job = session.get(Job, probe.job_id)
        assert job is not None and job.status == "queued"


def test_invalid_closed_payload_terminalizes_and_defers_subscription_without_storm(database: Database) -> None:
    now = datetime(2026, 8, 30, 8, 45, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="invalid-payload",
        now=now,
        next_run_at=None,
    )
    job_id = _materialize_one(database, subscription_id, now=now)
    with database.session() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.payload = {"schema_version": 1, "unexpected": "closed-schema-rejected"}
        session.flush()

    with database.session() as session:
        repository = SchedulerRepository(session)
        assert repository.claim_next(worker_id="schema-worker", global_capacity=1, now=now) is None
    with database.session() as session:
        job = session.get(Job, job_id)
        subscription = session.get(Subscription, subscription_id)
        assert job is not None and job.status == "failed_terminal"
        assert job.last_error_code == "schema_invalid"
        assert subscription is not None
        assert subscription.next_run_at == now + timedelta(seconds=60)
        assert subscription.consecutive_failures == 1
        assert SchedulerRepository(session).materialize_due(limit=1, now=now + timedelta(seconds=1)) == []


def test_resume_releases_only_its_exact_probe_and_preserves_unrelated_open_circuit(database: Database) -> None:
    now = datetime(2026, 8, 30, 8, 50, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="xhs",
        remote_id="resume-circuit",
        now=now,
        next_run_at=None,
    )
    _materialize_one(database, subscription_id, now=now)
    job_id, token = _claim_and_start(database, worker_id="waiting-user", now=now)
    with database.session() as session:
        SchedulerRepository(session).wait(
            job_id,
            worker_id="waiting-user",
            lease_token=token,
            status="waiting_user",
            error_code="captcha_required",
            now=now + timedelta(seconds=1),
        )
    with database.session() as session:
        platform_lane = session.scalar(
            select(SchedulerLane).where(
                SchedulerLane.scope_type == "platform",
                SchedulerLane.platform == "xhs",
            )
        )
        assert platform_lane is not None
        platform_lane.circuit_state = "open"
        platform_lane.circuit_open_until = now + timedelta(minutes=5)
        platform_lane.consecutive_failures = 7
        platform_lane.half_open_job_id = None
        session.flush()
    with database.session() as session:
        assert SchedulerRepository(session).resume(job_id, now=now + timedelta(seconds=2)).status == "queued"
    with database.session() as session:
        lane = SchedulerRepository(session).get_lane(scope_type="platform", platform="xhs")
        assert lane is not None
        assert lane.circuit_state == "open"
        assert lane.consecutive_failures == 7


def test_subscription_controls_preserve_pause_and_run_now_boundaries(database: Database) -> None:
    now = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
    _account_id, subscription_id = _seed_subscription(
        database,
        platform="bili",
        remote_id="controls",
        now=now,
        next_run_at=now + timedelta(hours=1),
    )
    with database.session() as session:
        repository = SchedulerRepository(session)
        assert repository.pause_subscription(subscription_id, now=now).enabled is False
        run_now = repository.run_now(subscription_id, now=now)
        assert run_now.enabled is False and run_now.next_run_at is None
        assert repository.materialize_due(limit=1, now=now) == []
        assert repository.resume_subscription(subscription_id, now=now).enabled is True
        assert len(repository.materialize_due(limit=1, now=now)) == 1


def test_scheduler_rejects_foreign_jobs_and_raw_error_vocabulary(database: Database) -> None:
    now = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)
    with database.session() as session:
        foreign = JobRepository(session).enqueue(
            job_type="asset_download",
            natural_key="foreign-job",
            payload={"prepared_result": "sentinel-secret-value"},
        )
        foreign_id = foreign.id
    with database.session() as session:
        repository = SchedulerRepository(session)
        with pytest.raises(SchedulerRepositoryError, match="foreign job type"):
            repository.cancel(foreign_id, now=now)
        persisted_foreign = session.get(Job, foreign_id)
        assert persisted_foreign is not None
        assert persisted_foreign.status == "queued"
        assert persisted_foreign.payload == {"prepared_result": "sentinel-secret-value"}
