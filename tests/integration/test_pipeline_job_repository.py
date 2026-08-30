"""Focused coverage for durable pipeline coordinator enqueue and claim."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import pytest
from sqlalchemy import select

from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    JobRepository,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import Job
from media_sync.scheduler.pipeline import (
    PIPELINE_COORDINATOR_INVALID_ERROR_CODE,
    PIPELINE_COORDINATOR_STALE_ERROR_CODE,
    PIPELINE_MAX_ATTEMPTS,
    PIPELINE_PAYLOAD_SCHEMA_VERSION,
    PIPELINE_SUBSCRIPTION_JOB_TYPE,
    PipelineJobRepository,
    PipelineJobRepositoryError,
    pipeline_subscription_natural_key,
)
from media_sync.scheduler.policy import RetryPolicy
from media_sync.scheduler.repository import SYNC_SUBSCRIPTION_JOB_TYPE, SchedulerRepository

NOW = datetime(2026, 8, 31, 1, 30, tzinfo=UTC)


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
