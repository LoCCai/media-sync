"""Offline full-chain qualification for resident scheduler supervision."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from media_sync.application import LoginSessionReconciliationSummary
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    SubscriptionRepository,
)
from media_sync.infrastructure.db.models import Asset, Content, Job, SyncRun
from media_sync.scheduler import (
    DurableSchedulerService,
    FakeSubscriptionHandler,
    PipelineHandlerResult,
    PipelineSubscriptionClaim,
    PipelineSubscriptionWorker,
    ResidentSchedulerSupervisor,
    ResidentSupervisorConfig,
    SubscriptionHandlerRegistry,
    SubscriptionWorker,
)

NOW = datetime(2026, 8, 31, 5, 0, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'resident-supervisor.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_due_fake_subscription(database: Database) -> str:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter="fake",
            display_name="resident-supervisor-fake-account",
            login_method="cookie",
            auth_status="authenticated",
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform="bili",
                remote_id="creator-001",
                display_name="Resident supervisor fixture creator",
            )
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            interval_seconds=60,
            max_items=5,
            next_run_at=None,
        )
        return subscription.id


@pytest.mark.asyncio
async def test_one_resident_cycle_drives_fake_sync_through_durable_pipeline_success(
    database: Database,
) -> None:
    subscription_id = _seed_due_fake_subscription(database)
    sweep_limits: list[int] = []
    pipeline_claims: list[PipelineSubscriptionClaim] = []

    def clock() -> datetime:
        return NOW

    def stale_login_sweep(*, limit: int) -> LoginSessionReconciliationSummary:
        sweep_limits.append(limit)
        return LoginSessionReconciliationSummary(scanned=0, recovered=0, busy=0, conflicted=0)

    def pipeline_handler(claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        pipeline_claims.append(claim)
        return PipelineHandlerResult.success()

    supervisor = ResidentSchedulerSupervisor(
        stale_login_sweep=stale_login_sweep,
        scheduler=DurableSchedulerService(database, clock=clock),
        subscription_worker=SubscriptionWorker(
            database,
            SubscriptionHandlerRegistry({"fake": FakeSubscriptionHandler(database)}),
            clock=clock,
            random_fraction=lambda: 0,
            claim_registered_only=True,
        ),
        pipeline_worker=PipelineSubscriptionWorker(database, pipeline_handler, clock=clock),
        subscription_worker_id="integration-resident-sync",
        pipeline_worker_id="integration-resident-pipeline",
        config=ResidentSupervisorConfig(
            login_sweep_limit=9,
            materialize_limit=10,
            subscription_jobs_per_cycle=10,
            pipeline_jobs_per_cycle=10,
            subscription_global_capacity=1,
        ),
    )

    result = await supervisor.run_cycle()

    assert sweep_limits == [9]
    assert (
        result.cycles,
        result.materialized,
        result.subscription_attempts,
        result.pipeline_attempts,
        result.outcome,
    ) == (1, 1, 1, 1, "cycle_complete")
    assert len(pipeline_claims) == 1
    claim = pipeline_claims[0]
    assert claim.subscription_id == subscription_id
    assert claim.platform == "bili"

    with database.session() as session:
        jobs = list(session.scalars(select(Job).order_by(Job.job_type)).all())
        runs = list(session.scalars(select(SyncRun)).all())
        contents = list(session.scalars(select(Content)).all())
        assets = list(session.scalars(select(Asset)).all())

    assert [(job.job_type, job.status, job.attempts) for job in jobs] == [
        ("pipeline.subscription", "succeeded", 1),
        ("sync.subscription", "succeeded", 1),
    ]
    assert len(runs) == 1 and runs[0].status == "succeeded"
    assert len(contents) == 4
    assert len(assets) == 4
    assert result.login_scanned == result.login_recovered == result.login_busy == result.login_conflicted == 0
