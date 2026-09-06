"""Focused coverage for durable pipeline coordinator enqueue and claim."""

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
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import Job, Subscription
from media_sync.scheduler.pipeline import (
    PIPELINE_COORDINATOR_INVALID_ERROR_CODE,
    PIPELINE_COORDINATOR_STALE_ERROR_CODE,
    PIPELINE_MAX_ATTEMPTS,
    PIPELINE_PAYLOAD_SCHEMA_VERSION,
    PIPELINE_SUBSCRIPTION_JOB_TYPE,
    PipelineExactConflictError,
    PipelineJobRepository,
    PipelineJobRepositoryError,
    pipeline_subscription_natural_key,
)
from media_sync.scheduler.policy import RetryPolicy
from media_sync.scheduler.repository import (
    SYNC_SUBSCRIPTION_JOB_TYPE,
    SchedulerExactConflictError,
    SchedulerRepository,
)

NOW = datetime(2026, 8, 31, 1, 30, tzinfo=UTC)


def test_exact_pipeline_resolves_and_claims_only_the_succeeded_source(database: Database) -> None:
    other_source, other_job, other_subscription, _ = _succeeded_sync(database, remote_id="exact-other")
    source, job_id, subscription, run_id = _succeeded_sync(
        database, remote_id="exact-target", now=NOW + timedelta(seconds=10)
    )
    now = NOW + timedelta(seconds=12)
    with database.session() as session:
        other = session.get(Job, other_job)
        assert other is not None
        other.priority = 100
        session.flush()
        repository = PipelineJobRepository(session)
        target = repository.get_for_succeeded_sync(source, run_id=run_id, expected_subscription_id=subscription)
        assert target is not None and target.job_id == job_id
        claim = repository.claim_exact(
            job_id,
            expected_subscription_id=subscription,
            expected_sync_job_id=source,
            expected_run_id=run_id,
            worker_id="exact-pipeline",
            now=now,
        )
        assert claim is not None and (claim.job_id, claim.sync_job_id, claim.run_id) == (job_id, source, run_id)
        assert (other.status, other.attempts) == ("queued", 0)
        assert other_source != source and other_subscription != subscription


@pytest.mark.parametrize(
    "mismatch", ["subscription", "source", "run", "foreign_type", "removed", "paused", "stale_source"]
)
def test_exact_pipeline_mismatch_never_consumes_a_job(database: Database, mismatch: str) -> None:

    source, job_id, subscription, run_id = _succeeded_sync(database, remote_id="mismatch")
    with database.session() as session:
        repository = PipelineJobRepository(session)
        observed = session.get(Job, job_id)
        assert observed is not None
        exact_job = job_id
        exact_subscription, exact_source, exact_run = subscription, source, run_id
        if mismatch == "subscription":
            exact_subscription = str(uuid4())
        elif mismatch == "source":
            exact_source = str(uuid4())
        elif mismatch == "run":
            exact_run = str(uuid4())
        elif mismatch == "foreign_type":
            exact_job = source
        elif mismatch in {"removed", "paused"}:
            row = session.get(Subscription, subscription)
            assert row is not None
            if mismatch == "removed":
                row.deleted_at = NOW
            else:
                row.enabled = False
        else:
            source_job = session.get(Job, source)
            assert source_job is not None
            source_job.run_id = None
        session.flush()
        with pytest.raises(PipelineJobRepositoryError):
            repository.claim_exact(
                exact_job,
                expected_subscription_id=exact_subscription,
                expected_sync_job_id=exact_source,
                expected_run_id=exact_run,
                worker_id="exact",
                now=NOW + timedelta(seconds=2),
            )
        session.refresh(observed)
        assert (observed.status, observed.attempts, observed.lease_token) == ("queued", 0, None)


@pytest.mark.parametrize("state", ["retry_wait", "claimed", "succeeded"])
def test_exact_pipeline_does_not_accelerate_retry_or_steal_lease(database: Database, state: str) -> None:
    source, job_id, subscription, run_id = _succeeded_sync(database, remote_id="blocked")
    now = NOW + timedelta(seconds=2)
    with database.session() as session:
        jobs = JobRepository(session)
        observed = session.get(Job, job_id)
        assert observed is not None
        if state == "claimed":
            assert jobs.claim(job_id, worker_id="supervisor", now=now)
        else:
            observed.status = state
            observed.available_at = now + timedelta(hours=1)
        session.flush()
        attempts, token = observed.attempts, observed.lease_token
        assert (
            PipelineJobRepository(session).claim_exact(
                job_id,
                expected_subscription_id=subscription,
                expected_sync_job_id=source,
                expected_run_id=run_id,
                worker_id="exact",
                now=now,
            )
            is None
        )
        session.refresh(observed)
        assert (observed.status, observed.attempts, observed.lease_token) == (state, attempts, token)


def test_exact_pipeline_lookup_rejects_wrong_subscription(database: Database) -> None:
    source, _job, _subscription, run = _succeeded_sync(database, remote_id="lookup")
    with database.session() as session, pytest.raises(PipelineExactConflictError, match="subscription_delivery_stale"):
        PipelineJobRepository(session).get_for_succeeded_sync(source, run_id=run, expected_subscription_id=str(uuid4()))


def test_exact_pipeline_duplicate_claims_have_one_owner(database: Database) -> None:
    source, job_id, subscription, run_id = _succeeded_sync(database, remote_id="pipeline-race")
    barrier = Barrier(2)

    def claim(worker: str) -> str | None:
        barrier.wait(timeout=10)
        with database.session() as session:
            result = PipelineJobRepository(session).claim_exact(
                job_id,
                expected_subscription_id=subscription,
                expected_sync_job_id=source,
                expected_run_id=run_id,
                worker_id=worker,
                now=NOW + timedelta(seconds=2),
            )
            return result.job_id if result else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, ["pipeline-a", "pipeline-b"]), key=str) == sorted([job_id, None], key=str)
    with database.session() as session:
        row = session.get(Job, job_id)
        assert row is not None and row.attempts == 1


def test_pipeline_enqueue_serializes_exact_materialization_pipeline_fence(database: Database) -> None:
    source, old_coordinator, subscription, run_id = _succeeded_sync(database, remote_id="enqueue-fence-race")
    with database.session() as session:
        coordinator = session.get(Job, old_coordinator)
        assert coordinator is not None
        session.delete(coordinator)

    pipeline_at_subscription_lock = Event()
    release_pipeline = Event()
    materialize_writer_started = Event()

    def observe_sql(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        sql = statement.lstrip().upper()
        if (
            current_thread().name.startswith("pipeline-enqueue")
            and sql.startswith("SELECT")
            and "FROM SUBSCRIPTIONS" in sql
        ):
            pipeline_at_subscription_lock.set()
            if not release_pipeline.wait(timeout=10):
                raise AssertionError("timed out waiting to release pipeline enqueue")
        if current_thread().name.startswith("exact-materialize") and sql.startswith("UPDATE JOBS"):
            materialize_writer_started.set()

    def enqueue_pipeline() -> str:
        with database.session() as session:
            return PipelineJobRepository(session).enqueue_succeeded_sync(source, run_id=run_id, now=NOW).job_id

    def materialize_exact() -> str:
        with database.session() as session:
            try:
                SchedulerRepository(session).materialize_one(
                    subscription,
                    expected_schedule_revision=1,
                    now=NOW + timedelta(seconds=2),
                )
            except SchedulerExactConflictError as exc:
                return exc.code
            return "materialized"

    event.listen(database.engine, "before_cursor_execute", observe_sql)
    try:
        with (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline-enqueue") as pipeline_executor,
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="exact-materialize") as scheduler_executor,
        ):
            pipeline_future = pipeline_executor.submit(enqueue_pipeline)
            assert pipeline_at_subscription_lock.wait(timeout=10)
            scheduler_future = scheduler_executor.submit(materialize_exact)
            assert materialize_writer_started.wait(timeout=10)
            assert not scheduler_future.done()
            release_pipeline.set()
            coordinator_id = pipeline_future.result(timeout=10)
            assert scheduler_future.result(timeout=10) == "subscription_delivery_busy"
    finally:
        release_pipeline.set()
        event.remove(database.engine, "before_cursor_execute", observe_sql)

    with database.session() as session:
        pipelines = list(
            session.scalars(
                select(Job).where(
                    Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE,
                    Job.subscription_id == subscription,
                )
            )
        )
        sync_jobs = list(
            session.scalars(
                select(Job).where(
                    Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                    Job.subscription_id == subscription,
                )
            )
        )
        assert len(pipelines) == 1 and pipelines[0].id == coordinator_id
        assert len(sync_jobs) == 1 and sync_jobs[0].id == source and sync_jobs[0].status == "succeeded"


def test_exact_materialization_serializes_pipeline_enqueue_supersession_fence(database: Database) -> None:
    source, old_coordinator, subscription, run_id = _succeeded_sync(
        database, remote_id="materialize-first-enqueue-fence"
    )
    with database.session() as session:
        coordinator = session.get(Job, old_coordinator)
        assert coordinator is not None
        session.delete(coordinator)

    exact_at_subscription_lock = Event()
    release_exact = Event()
    pipeline_writer_started = Event()

    def observe_sql(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        sql = statement.lstrip().upper()
        if (
            current_thread().name.startswith("exact-materialize-first")
            and sql.startswith("SELECT")
            and "FROM SUBSCRIPTIONS" in sql
        ):
            exact_at_subscription_lock.set()
            if not release_exact.wait(timeout=10):
                raise AssertionError("timed out waiting to release exact materialization")
        if current_thread().name.startswith("pipeline-enqueue-second") and sql.startswith("UPDATE JOBS"):
            pipeline_writer_started.set()

    def materialize_exact() -> str:
        with database.session() as session:
            return (
                SchedulerRepository(session)
                .materialize_one(
                    subscription,
                    expected_schedule_revision=1,
                    now=NOW + timedelta(seconds=2),
                )
                .job_id
            )

    def enqueue_pipeline() -> str:
        with database.session() as session:
            try:
                PipelineJobRepository(session).enqueue_succeeded_sync(source, run_id=run_id, now=NOW)
            except PipelineJobRepositoryError as exc:
                return str(exc)
            return "enqueued"

    event.listen(database.engine, "before_cursor_execute", observe_sql)
    try:
        with (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="exact-materialize-first") as scheduler_executor,
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline-enqueue-second") as pipeline_executor,
        ):
            scheduler_future = scheduler_executor.submit(materialize_exact)
            assert exact_at_subscription_lock.wait(timeout=10)
            pipeline_future = pipeline_executor.submit(enqueue_pipeline)
            assert pipeline_writer_started.wait(timeout=10)
            assert not pipeline_future.done()
            release_exact.set()
            new_sync_id = scheduler_future.result(timeout=10)
            assert pipeline_future.result(timeout=10) == "pipeline source was superseded by an active sync"
    finally:
        release_exact.set()
        event.remove(database.engine, "before_cursor_execute", observe_sql)

    with database.session() as session:
        pipelines = list(
            session.scalars(
                select(Job).where(
                    Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE,
                    Job.subscription_id == subscription,
                )
            )
        )
        sync_jobs = list(
            session.scalars(
                select(Job).where(
                    Job.job_type == SYNC_SUBSCRIPTION_JOB_TYPE,
                    Job.subscription_id == subscription,
                )
            )
        )
        assert pipelines == []
        assert {(job.id, job.status) for job in sync_jobs} == {
            (source, "succeeded"),
            (new_sync_id, "queued"),
        }


def test_exact_pipeline_lookup_does_not_create_missing_coordinator(database: Database) -> None:
    source, job_id, subscription, run_id = _succeeded_sync(database, remote_id="pipeline-missing")
    with database.session() as session:
        row = session.get(Job, job_id)
        assert row is not None
        session.delete(row)
        session.flush()
        assert (
            PipelineJobRepository(session).get_for_succeeded_sync(
                source, run_id=run_id, expected_subscription_id=subscription
            )
            is None
        )
        assert list(session.scalars(select(Job).where(Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE))) == []


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'pipeline-jobs.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def test_pipeline_coordinator_budget_does_not_share_the_child_retry_limit() -> None:
    # Asset and export children default to five attempts.  The coordinator
    # needs enough room to revisit many distinct children without inheriting
    # the attempts already consumed by earlier assets.
    assert PIPELINE_MAX_ATTEMPTS == 100


def _running_sync(
    database: Database,
    *,
    remote_id: str,
    now: datetime = NOW,
    max_attempts: int = 5,
    lease_seconds: int = 60,
) -> tuple[str, str, str, str, str]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter="fake",
            display_name=f"account-{remote_id}",
            login_method="qr",
            auth_status="authenticated",
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="bili", remote_id=remote_id, display_name=f"author-{remote_id}")
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            interval_seconds=60,
            next_run_at=None,
            policy={"handler": "fake"},
        )
        subscription_id = subscription.id
        account_id = account.id

    with database.session() as session:
        cycles = SchedulerRepository(session).materialize_due(
            limit=1,
            retry_policy=RetryPolicy(max_attempts=max_attempts),
            now=now,
        )
        assert len(cycles) == 1
        sync_job_id = cycles[0].job_id
        repository = SchedulerRepository(session)
        claim = repository.claim_next(
            worker_id=f"worker-{remote_id}",
            global_capacity=1,
            lease_seconds=lease_seconds,
            now=now,
        )
        assert claim is not None and claim.job_id == sync_job_id
        running = repository.start(
            sync_job_id,
            worker_id=f"worker-{remote_id}",
            lease_token=claim.lease_token,
            now=now,
        )
        return sync_job_id, subscription_id, account_id, running.lease_token, f"worker-{remote_id}"


def _attach_succeeded_run(
    database: Database,
    *,
    sync_job_id: str,
    subscription_id: str,
    worker_id: str,
    lease_token: str,
    now: datetime = NOW,
) -> str:
    with database.session() as session:
        runs = SyncRunRepository(session)
        run = runs.create(subscription_id=subscription_id, attempt=1)
        runs.set_status(run.id, "claimed", expected_status="queued", at=now)
        runs.set_status(run.id, "running", expected_status="claimed", at=now)
        SchedulerRepository(session).attach_run(
            sync_job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            run_id=run.id,
            expected_current_run_id=None,
            now=now,
        )
        runs.set_status(run.id, "ingesting", expected_status="running", at=now)
        runs.set_status(run.id, "succeeded", expected_status="ingesting", at=now)
        return run.id


def _succeeded_sync(
    database: Database,
    *,
    remote_id: str,
    now: datetime = NOW,
) -> tuple[str, str, str, str]:
    sync_job_id, subscription_id, _account_id, lease_token, worker_id = _running_sync(
        database,
        remote_id=remote_id,
        now=now,
    )
    run_id = _attach_succeeded_run(
        database,
        sync_job_id=sync_job_id,
        subscription_id=subscription_id,
        worker_id=worker_id,
        lease_token=lease_token,
        now=now,
    )
    with database.session() as session:
        SchedulerRepository(session).succeed(
            sync_job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            run_id=run_id,
            now=now + timedelta(seconds=1),
        )
        coordinator = JobRepository(session).get_by_key(
            PIPELINE_SUBSCRIPTION_JOB_TYPE,
            pipeline_subscription_natural_key(sync_job_id),
        )
        assert coordinator is not None
        return sync_job_id, coordinator.id, subscription_id, run_id


def test_normal_success_enqueues_one_closed_scoped_job_and_claim_is_type_isolated(database: Database) -> None:
    sync_job_id, subscription_id, account_id, lease_token, worker_id = _running_sync(
        database,
        remote_id="normal-success",
    )
    run_id = _attach_succeeded_run(
        database,
        sync_job_id=sync_job_id,
        subscription_id=subscription_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    finished_at = NOW + timedelta(seconds=1)

    with database.session() as session:
        completed = SchedulerRepository(session).succeed(
            sync_job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            run_id=run_id,
            now=finished_at,
        )
        assert (completed.status, completed.run_id) == ("succeeded", run_id)

    with database.session() as session:
        coordinators = list(session.scalars(select(Job).where(Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE)).all())
        assert len(coordinators) == 1
        coordinator = coordinators[0]
        assert coordinator.natural_key == pipeline_subscription_natural_key(sync_job_id)
        assert coordinator.payload == {
            "schema_version": PIPELINE_PAYLOAD_SCHEMA_VERSION,
            "sync_job_id": sync_job_id,
            "subscription_id": subscription_id,
            "run_id": run_id,
        }
        assert (coordinator.subscription_id, coordinator.account_id, coordinator.platform, coordinator.run_id) == (
            subscription_id,
            account_id,
            "bili",
            run_id,
        )
        assert (coordinator.status, coordinator.attempts, coordinator.max_attempts) == (
            "queued",
            0,
            PIPELINE_MAX_ATTEMPTS,
        )
        assert coordinator.available_at == finished_at
        assert coordinator.scheduled_for == finished_at
        coordinator_id = coordinator.id

        duplicate = PipelineJobRepository(session).enqueue_succeeded_sync(
            sync_job_id,
            run_id=run_id,
            now=finished_at + timedelta(seconds=1),
        )
        assert duplicate.job_id == coordinator_id
        assert len(session.scalars(select(Job).where(Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE)).all()) == 1

    with database.session() as session:
        claim = PipelineJobRepository(session).claim_next(
            worker_id="pipeline-worker",
            lease_seconds=30,
            now=finished_at,
        )
        assert claim is not None
        assert (
            claim.job_id,
            claim.sync_job_id,
            claim.subscription_id,
            claim.account_id,
            claim.platform,
            claim.run_id,
            claim.attempt,
        ) == (coordinator_id, sync_job_id, subscription_id, account_id, "bili", run_id, 1)
        assert "lease_token" not in repr(claim)
        source = session.get(Job, sync_job_id)
        assert source is not None and (source.job_type, source.status, source.attempts) == (
            SYNC_SUBSCRIPTION_JOB_TYPE,
            "succeeded",
            1,
        )
        assert PipelineJobRepository(session).claim_next(worker_id="pipeline-worker-two", now=finished_at) is None


def test_claim_terminalizes_malformed_head_and_claims_next_valid_coordinator(database: Database) -> None:
    _sync_job_id, coordinator_id, _subscription_id, _run_id = _succeeded_sync(
        database,
        remote_id="valid-after-malformed",
    )
    claimed_at = NOW + timedelta(seconds=2)

    with database.session() as session:
        valid = session.get(Job, coordinator_id)
        assert valid is not None
        malformed = JobRepository(session).enqueue(
            job_type=PIPELINE_SUBSCRIPTION_JOB_TYPE,
            natural_key="poison:malformed-coordinator",
            payload={**valid.payload, "unexpected": "must-not-be-persisted-as-an-error"},
            run_id=valid.run_id,
            subscription_id=valid.subscription_id,
            account_id=valid.account_id,
            platform=valid.platform,
            priority=100,
            max_attempts=PIPELINE_MAX_ATTEMPTS,
            available_at=NOW,
        )
        malformed_id = malformed.id

        claim = PipelineJobRepository(session).claim_next(
            worker_id="pipeline-malformed-skip-worker",
            lease_seconds=30,
            now=claimed_at,
        )
        assert claim is not None and claim.job_id == coordinator_id

        rejected = session.get(Job, malformed_id)
        assert rejected is not None
        assert (
            rejected.status,
            rejected.attempts,
            rejected.last_error_code,
            rejected.last_error_message,
        ) == (
            "failed_terminal",
            1,
            PIPELINE_COORDINATOR_INVALID_ERROR_CODE,
            "pipeline coordinator violated its durable contract",
        )
        assert rejected.finished_at == claimed_at
        assert (rejected.lease_owner, rejected.lease_token, rejected.lease_expires_at) == (None, None, None)


def test_claim_terminalizes_stale_head_and_claims_next_valid_coordinator(database: Database) -> None:
    stale_source_id, stale_coordinator_id, _stale_subscription_id, _stale_run_id = _succeeded_sync(
        database,
        remote_id="stale-before-valid",
    )
    _valid_source_id, valid_coordinator_id, _valid_subscription_id, _valid_run_id = _succeeded_sync(
        database,
        remote_id="valid-after-stale",
        now=NOW + timedelta(seconds=5),
    )
    claimed_at = NOW + timedelta(seconds=7)

    with database.session() as session:
        stale_source = session.get(Job, stale_source_id)
        stale = session.get(Job, stale_coordinator_id)
        assert stale_source is not None and stale is not None
        stale_source.payload = {}
        stale.priority = 100
        session.flush()

        claim = PipelineJobRepository(session).claim_next(
            worker_id="pipeline-stale-skip-worker",
            lease_seconds=30,
            now=claimed_at,
        )
        assert claim is not None and claim.job_id == valid_coordinator_id

        rejected = session.get(Job, stale_coordinator_id)
        assert rejected is not None
        assert (
            rejected.status,
            rejected.attempts,
            rejected.last_error_code,
            rejected.last_error_message,
        ) == (
            "failed_terminal",
            1,
            PIPELINE_COORDINATOR_STALE_ERROR_CODE,
            "pipeline coordinator no longer matches its succeeded source",
        )
        assert rejected.finished_at == claimed_at
        assert (rejected.lease_owner, rejected.lease_token, rejected.lease_expires_at) == (None, None, None)


def test_claim_terminalizes_cross_scope_poison_before_application_side_effects(database: Database) -> None:
    source_a_id, coordinator_a_id, _subscription_a_id, _run_a_id = _succeeded_sync(
        database,
        remote_id="cross-scope-source-a",
    )
    source_b_id, coordinator_b_id, subscription_b_id, _run_b_id = _succeeded_sync(
        database,
        remote_id="cross-scope-source-b",
        now=NOW + timedelta(seconds=5),
    )
    claimed_at = NOW + timedelta(seconds=7)

    with database.session() as session:
        source_a = session.get(Job, source_a_id)
        source_b = session.get(Job, source_b_id)
        poisoned = session.get(Job, coordinator_a_id)
        assert source_a is not None and source_b is not None and poisoned is not None
        poisoned.payload = {**poisoned.payload, "subscription_id": subscription_b_id}
        poisoned.subscription_id = subscription_b_id
        poisoned.account_id = source_b.account_id
        poisoned.platform = source_b.platform
        poisoned.priority = 100
        session.flush()

        claim = PipelineJobRepository(session).claim_next(
            worker_id="pipeline-cross-scope-skip-worker",
            lease_seconds=30,
            now=claimed_at,
        )
        assert claim is not None and claim.job_id == coordinator_b_id

        rejected = session.get(Job, coordinator_a_id)
        assert rejected is not None
        assert (
            rejected.status,
            rejected.attempts,
            rejected.last_error_code,
            rejected.last_error_message,
        ) == (
            "failed_terminal",
            1,
            PIPELINE_COORDINATOR_STALE_ERROR_CODE,
            "pipeline coordinator no longer matches its succeeded source",
        )
        assert rejected.finished_at == claimed_at
        assert (rejected.lease_owner, rejected.lease_token, rejected.lease_expires_at) == (None, None, None)


def test_claim_scan_limit_bounds_poison_cleanup_before_later_valid_work(database: Database) -> None:
    _source_id, coordinator_id, _subscription_id, _run_id = _succeeded_sync(
        database,
        remote_id="valid-after-bounded-poison",
    )
    first_claimed_at = NOW + timedelta(seconds=2)

    with database.session() as session:
        valid = session.get(Job, coordinator_id)
        assert valid is not None
        poison_ids: list[str] = []
        for index in range(2):
            poison = JobRepository(session).enqueue(
                job_type=PIPELINE_SUBSCRIPTION_JOB_TYPE,
                natural_key=f"poison:bounded:{index}",
                payload={**valid.payload, "unexpected": index},
                run_id=valid.run_id,
                subscription_id=valid.subscription_id,
                account_id=valid.account_id,
                platform=valid.platform,
                priority=100,
                max_attempts=PIPELINE_MAX_ATTEMPTS,
                available_at=NOW,
            )
            poison_ids.append(poison.id)

        assert (
            PipelineJobRepository(session).claim_next(
                worker_id="pipeline-bounded-poison-first",
                scan_limit=1,
                now=first_claimed_at,
            )
            is None
        )
        poison_jobs = [session.get(Job, poison_id) for poison_id in poison_ids]
        assert all(job is not None for job in poison_jobs)
        poison_statuses = [job.status for job in poison_jobs if job is not None]
        assert poison_statuses.count("failed_terminal") == 1
        assert poison_statuses.count("queued") == 1
        valid_after_first = session.get(Job, coordinator_id)
        assert valid_after_first is not None and valid_after_first.status == "queued"

    with database.session() as session:
        claim = PipelineJobRepository(session).claim_next(
            worker_id="pipeline-bounded-poison-second",
            scan_limit=2,
            now=first_claimed_at + timedelta(seconds=1),
        )
        assert claim is not None and claim.job_id == coordinator_id
        assert all(
            (job := session.get(Job, poison_id)) is not None and job.status == "failed_terminal"
            for poison_id in poison_ids
        )


def test_expired_succeeded_run_reconciliation_enqueues_exactly_one_coordinator(database: Database) -> None:
    sync_job_id, subscription_id, _account_id, lease_token, worker_id = _running_sync(
        database,
        remote_id="reconciled-success",
        max_attempts=1,
        lease_seconds=1,
    )
    run_id = _attach_succeeded_run(
        database,
        sync_job_id=sync_job_id,
        subscription_id=subscription_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    reconciled_at = NOW + timedelta(seconds=2)

    with database.session() as session:
        assert (
            SchedulerRepository(session).claim_next(
                worker_id="replacement-must-not-run",
                global_capacity=1,
                now=reconciled_at,
            )
            is None
        )

    with database.session() as session:
        source = session.get(Job, sync_job_id)
        coordinators = list(session.scalars(select(Job).where(Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE)).all())
        assert source is not None and (source.status, source.run_id) == ("succeeded", run_id)
        assert len(coordinators) == 1
        assert coordinators[0].natural_key == pipeline_subscription_natural_key(sync_job_id)
        assert SchedulerRepository(session).cancel(sync_job_id, now=reconciled_at + timedelta(seconds=1)).status == (
            "succeeded"
        )
        PipelineJobRepository(session).enqueue_succeeded_sync(
            sync_job_id,
            run_id=run_id,
            now=reconciled_at + timedelta(seconds=1),
        )
        assert len(session.scalars(select(Job).where(Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE)).all()) == 1


@pytest.mark.parametrize("outcome", ["fail", "wait", "cancel"])
def test_non_success_outcomes_never_enqueue_pipeline_job(
    database: Database,
    outcome: Literal["fail", "wait", "cancel"],
) -> None:
    sync_job_id, _subscription_id, _account_id, lease_token, worker_id = _running_sync(
        database,
        remote_id=f"no-pipeline-{outcome}",
    )
    with database.session() as session:
        repository = SchedulerRepository(session)
        if outcome == "fail":
            summary = repository.fail(
                sync_job_id,
                worker_id=worker_id,
                lease_token=lease_token,
                error_code="schema_invalid",
                now=NOW + timedelta(seconds=1),
            )
            assert summary.status == "failed_terminal"
        elif outcome == "wait":
            summary = repository.wait(
                sync_job_id,
                worker_id=worker_id,
                lease_token=lease_token,
                status="waiting_auth",
                error_code="auth_expired",
                now=NOW + timedelta(seconds=1),
            )
            assert summary.status == "waiting_auth"
        else:
            summary = repository.cancel(sync_job_id, now=NOW + timedelta(seconds=1))
            assert summary.status == "cancelled"

    with database.session() as session:
        assert session.scalar(select(Job.id).where(Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE)) is None


def test_malformed_idempotency_collision_rolls_back_sync_success_in_same_transaction(database: Database) -> None:
    sync_job_id, subscription_id, account_id, lease_token, worker_id = _running_sync(
        database,
        remote_id="atomic-rollback",
    )
    run_id = _attach_succeeded_run(
        database,
        sync_job_id=sync_job_id,
        subscription_id=subscription_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    with database.session() as session:
        JobRepository(session).enqueue(
            job_type=PIPELINE_SUBSCRIPTION_JOB_TYPE,
            natural_key=pipeline_subscription_natural_key(sync_job_id),
            payload={
                "schema_version": PIPELINE_PAYLOAD_SCHEMA_VERSION,
                "sync_job_id": sync_job_id,
                "subscription_id": subscription_id,
                "run_id": run_id,
                "unexpected": "must-not-be-accepted",
            },
            run_id=run_id,
            subscription_id=subscription_id,
            account_id=account_id,
            platform="bili",
            max_attempts=PIPELINE_MAX_ATTEMPTS,
            available_at=NOW,
        )

    with pytest.raises(PipelineJobRepositoryError, match="closed schema"), database.session() as session:
        SchedulerRepository(session).succeed(
            sync_job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            run_id=run_id,
            now=NOW + timedelta(seconds=1),
        )

    with database.session() as session:
        source = session.get(Job, sync_job_id)
        assert source is not None
        assert (source.status, source.run_id, source.lease_token) == ("running", run_id, lease_token)
        assert len(session.scalars(select(Job).where(Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE)).all()) == 1

    rejected_at = NOW + timedelta(seconds=2)
    with database.session() as session:
        assert (
            PipelineJobRepository(session).claim_next(
                worker_id="pipeline-invalid-collision-cleaner",
                scan_limit=1,
                now=rejected_at,
            )
            is None
        )
        rejected = session.scalar(select(Job).where(Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE))
        assert rejected is not None
        assert (rejected.status, rejected.last_error_code) == (
            "failed_terminal",
            PIPELINE_COORDINATOR_INVALID_ERROR_CODE,
        )

    recovered_at = NOW + timedelta(seconds=3)
    with database.session() as session:
        summary = SchedulerRepository(session).succeed(
            sync_job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            run_id=run_id,
            now=recovered_at,
        )
        assert summary.status == "succeeded"
        repaired = session.scalar(select(Job).where(Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE))
        assert repaired is not None
        assert (repaired.status, repaired.attempts, repaired.last_error_code) == ("queued", 0, None)
        assert repaired.payload == {
            "schema_version": PIPELINE_PAYLOAD_SCHEMA_VERSION,
            "sync_job_id": sync_job_id,
            "subscription_id": subscription_id,
            "run_id": run_id,
        }


def test_stale_exact_key_collision_is_rejected_then_repaired_on_success_retry(database: Database) -> None:
    sync_job_id, subscription_id, _account_id, lease_token, worker_id = _running_sync(
        database,
        remote_id="stale-collision-source",
    )
    run_id = _attach_succeeded_run(
        database,
        sync_job_id=sync_job_id,
        subscription_id=subscription_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    with database.session() as session:
        other_account = AccountRepository(session).create(
            platform="bili",
            adapter="fake",
            display_name="stale collision other account",
            login_method="qr",
            auth_status="authenticated",
        )
        other_author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform="bili",
                remote_id="stale-collision-other-scope",
                display_name="stale collision other author",
            )
        )
        other_subscription = SubscriptionRepository(session).create(
            account_id=other_account.id,
            author_id=other_author.id,
        )
        other_subscription_id = other_subscription.id
        other_account_id = other_account.id
        JobRepository(session).enqueue(
            job_type=PIPELINE_SUBSCRIPTION_JOB_TYPE,
            natural_key=pipeline_subscription_natural_key(sync_job_id),
            payload={
                "schema_version": PIPELINE_PAYLOAD_SCHEMA_VERSION,
                "sync_job_id": sync_job_id,
                "subscription_id": other_subscription_id,
                "run_id": run_id,
            },
            run_id=run_id,
            subscription_id=other_subscription_id,
            account_id=other_account_id,
            platform="bili",
            max_attempts=PIPELINE_MAX_ATTEMPTS,
            available_at=NOW,
        )

    with pytest.raises(PipelineJobRepositoryError, match="conflicts"), database.session() as session:
        SchedulerRepository(session).succeed(
            sync_job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            run_id=run_id,
            now=NOW + timedelta(seconds=2),
        )

    with database.session() as session:
        assert (
            PipelineJobRepository(session).claim_next(
                worker_id="pipeline-stale-collision-cleaner",
                scan_limit=1,
                now=NOW + timedelta(seconds=3),
            )
            is None
        )
        rejected = session.scalar(select(Job).where(Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE))
        assert rejected is not None
        assert (rejected.status, rejected.last_error_code) == (
            "failed_terminal",
            PIPELINE_COORDINATOR_STALE_ERROR_CODE,
        )

    with database.session() as session:
        summary = SchedulerRepository(session).succeed(
            sync_job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            run_id=run_id,
            now=NOW + timedelta(seconds=4),
        )
        assert summary.status == "succeeded"
        repaired = session.scalar(select(Job).where(Job.job_type == PIPELINE_SUBSCRIPTION_JOB_TYPE))
        assert repaired is not None
        assert (repaired.status, repaired.subscription_id, repaired.account_id, repaired.attempts) == (
            "queued",
            subscription_id,
            summary.account_id,
            0,
        )
