"""Durable exact-attachment ownership conflicts survive worker acknowledgement loss."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select, update

from media_sync.infrastructure.db import Database, SyncRunRepository
from media_sync.infrastructure.db.models import Job, SchedulerLane, Subscription, SyncRun
from media_sync.scheduler.handlers import SubscriptionHandlerRegistry, SubscriptionHandlerResult
from media_sync.scheduler.mediacrawler_handler import MediaCrawlerScheduledHandler
from media_sync.scheduler.repository import SchedulerLeaseLostError, SchedulerRepository, SchedulerRepositoryError
from media_sync.scheduler.service import DurableSchedulerService, SubscriptionWorker
from tests.integration import test_bili_bounded_scheduler as bounded
from tests.integration import test_content_ownership_ingestion as ingestion
from tests.integration import test_scheduler_repository as support

_NOW = datetime(2026, 8, 30, 7, 44, 30, tzinfo=UTC)
_CODE = "content_ownership_conflict"


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'ownership-reconciliation.sqlite3').as_posix()}")
    instance.create_schema()
    yield instance
    instance.dispose()


def _seed_attached(
    database: Database, *, code: str = _CODE, status: str = "failed_terminal"
) -> tuple[str, str, str, str]:
    _, subscription_id = support._seed_subscription(database, platform="bili", remote_id="conflict-author", now=_NOW)
    job_id = support._materialize_one(database, subscription_id, now=_NOW)
    assert support._claim_and_start(database, worker_id="original", now=_NOW, lease_seconds=30)[0] == job_id
    with database.session() as session:
        job = session.get(Job, job_id)
        assert job is not None and job.lease_token is not None
        token = job.lease_token
        runs = SyncRunRepository(session)
        run = runs.create(subscription_id=subscription_id, attempt=1)
        runs.set_status(run.id, "claimed", expected_status="queued", at=_NOW)
        runs.set_status(run.id, "running", expected_status="claimed", at=_NOW)
        SchedulerRepository(session).attach_run(
            job_id,
            worker_id="original",
            lease_token=token,
            run_id=run.id,
            expected_current_run_id=None,
            now=_NOW,
        )
        if status != "running":
            runs.set_status(run.id, status, expected_status="running", error_code=code, at=_NOW)
        else:
            run.error_code = code
        return subscription_id, job_id, run.id, token


def _assert_terminal(database: Database, job_id: str, run_id: str, *, lane_failures: int = 0) -> None:
    with database.session() as session:
        job = session.get(Job, job_id)
        run = session.get(SyncRun, run_id)
        assert job is not None and run is not None
        assert (job.status, job.last_error_code, job.run_id) == ("failed_terminal", _CODE, run_id)
        assert (run.status, run.error_code) == ("failed_terminal", _CODE)
        assert job.lease_owner is job.lease_token is job.lease_expires_at is None
        assert job.last_error_message is None
        assert job.attempts == 1
        lanes = list(session.scalars(select(SchedulerLane)))
        assert lanes and all(lane.consecutive_failures == lane_failures for lane in lanes)
        assert bounded._pipeline_count(session) == 0


@pytest.mark.asyncio
async def test_terminal_write_acknowledgement_loss_uses_exact_attached_conflict(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ingestion._seed_existing(database, "1000")
    runtime_root = (tmp_path / "runtime").resolve()
    bounded._seed(database, runtime_root)
    clock = bounded.support._Clock()
    DurableSchedulerService(database, clock=clock).tick(limit=1)
    original = MediaCrawlerScheduledHandler._set_run_failure

    def lose_ack(self: MediaCrawlerScheduledHandler, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **kwargs)
        raise OSError("private terminal write acknowledgement unavailable")

    monkeypatch.setattr(MediaCrawlerScheduledHandler, "_set_run_failure", lose_ack)
    runner = bounded._SealedSyntheticUploads()
    result = await bounded._worker(database, runtime_root, runner, clock).run_once(worker_id="lost-terminal-ack")
    assert (result.status, result.error_code) == ("failed_terminal", _CODE)
    assert result.job_id is not None and result.run_id is not None
    _assert_terminal(database, str(result.job_id), str(result.run_id))
    assert not runner.manifests[0].job_root.exists()


def test_expired_lease_reconciles_terminal_conflict_without_replacement_or_circuit_failure(database: Database) -> None:
    subscription_id, job_id, run_id, _ = _seed_attached(database)
    with database.session() as session:
        replacement = SchedulerRepository(session).claim_next(
            worker_id="replacement", global_capacity=1, now=_NOW + timedelta(seconds=31)
        )
        assert replacement is None
    _assert_terminal(database, job_id, run_id)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None and subscription.consecutive_failures == 1
        assert subscription.last_success_at is None
        assert subscription.next_run_at == _NOW + timedelta(seconds=91)


@pytest.mark.parametrize("outcome", ["success", "retry", "auth", "user", "fail_closed"])
def test_worker_finalization_uses_exact_conflict_for_every_advisory_outcome(database: Database, outcome: str) -> None:
    _, job_id, run_id, token = _seed_attached(database)
    with database.session() as session:
        claim = SchedulerRepository(session).assert_owned(job_id, worker_id="original", lease_token=token, now=_NOW)
    worker = SubscriptionWorker(database, SubscriptionHandlerRegistry({}), clock=lambda: _NOW)
    advisory = {
        "success": SubscriptionHandlerResult.success(UUID(run_id)),
        "retry": SubscriptionHandlerResult.failure("unexpected_handler_failure"),
        "auth": SubscriptionHandlerResult.failure("auth_expired", run_id=UUID(run_id)),
        "user": SubscriptionHandlerResult.failure("captcha_required"),
        "fail_closed": SubscriptionHandlerResult.failure("schema_invalid"),
    }[outcome]
    if outcome == "fail_closed":
        result = worker._fail_closed(claim, worker_id="original", result=advisory)
        assert (result.status, result.error_code) == ("failed_terminal", _CODE)
    else:
        summary = worker._finalize(claim, worker_id="original", result=advisory)
        assert (summary.status, summary.last_error_code) == ("failed_terminal", _CODE)
    _assert_terminal(database, job_id, run_id)


@pytest.mark.parametrize("mode", ["cancel", "retry_wait", "failed_retryable", "queued", "resume", "removal"])
def test_recovery_and_operator_actions_cannot_restart_attached_conflict(database: Database, mode: str) -> None:
    subscription_id, job_id, run_id, _ = _seed_attached(database)
    if mode != "cancel":
        with database.session() as session:
            job = session.get(Job, job_id)
            assert job is not None
            job.status = "waiting_auth" if mode == "resume" else "retry_wait" if mode == "removal" else mode
            job.lease_owner = job.lease_token = job.lease_expires_at = None
            job.available_at = _NOW
    with database.session() as session:
        repository = SchedulerRepository(session)
        if mode == "cancel":
            result = repository.cancel(job_id, now=_NOW)
        elif mode == "resume":
            result = repository.resume(job_id, now=_NOW)
        elif mode == "removal":
            lanes = tuple(session.scalars(select(SchedulerLane)))
            result = repository.cancel_unstarted_for_removal(job_id, now=_NOW, locked_lanes=lanes)
        else:
            assert repository.claim_next(worker_id="no-restart", global_capacity=1, now=_NOW) is None
            result = repository.cancel(job_id, now=_NOW)
        assert (result.status, result.last_error_code) == ("failed_terminal", _CODE)
        again = repository.cancel(job_id, now=_NOW + timedelta(seconds=1))
        assert again == result
    _assert_terminal(database, job_id, run_id)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None and subscription.consecutive_failures == 1


@pytest.mark.parametrize("state", ["closed", "half_open", "open"])
def test_conflict_preserves_lane_failures_and_only_releases_its_own_probe(database: Database, state: str) -> None:
    _, job_id, run_id, token = _seed_attached(database)
    with database.session() as session:
        for lane in session.scalars(select(SchedulerLane)):
            lane.consecutive_failures = 2
            lane.circuit_state = state
            lane.half_open_job_id = job_id if state == "half_open" else None
            lane.circuit_open_until = _NOW + timedelta(minutes=5) if state == "open" else None
    with database.session() as session:
        SchedulerRepository(session).fail(
            job_id, worker_id="original", lease_token=token, error_code="unexpected_handler_failure", now=_NOW
        )
    _assert_terminal(database, job_id, run_id, lane_failures=2)
    with database.session() as session:
        for lane in session.scalars(select(SchedulerLane)):
            assert lane.circuit_state == ("open" if state == "open" else "closed")
            assert lane.half_open_job_id is None
            assert lane.circuit_open_until == (_NOW + timedelta(minutes=5) if state == "open" else None)


@pytest.mark.parametrize("changed", ["owner", "token", "expired", "cancelled", "deleted"])
def test_stale_worker_cannot_reconcile_conflict(database: Database, changed: str) -> None:
    subscription_id, job_id, run_id, token = _seed_attached(database)
    with database.session() as session:
        job = session.get(Job, job_id)
        assert job is not None
        if changed == "owner":
            job.lease_owner = "other-worker"
        elif changed == "token":
            job.lease_token = "different-token"
        elif changed == "expired":
            job.lease_expires_at = _NOW
        elif changed == "cancelled":
            job.status = "cancelled"
            job.lease_owner = job.lease_token = job.lease_expires_at = None
        else:
            subscription = session.get(Subscription, subscription_id)
            assert subscription is not None
            subscription.deleted_at = _NOW
        session.flush()
        before = support._job_execution_state(job)
    with database.session() as session, pytest.raises(SchedulerLeaseLostError):
        SchedulerRepository(session).succeed(job_id, worker_id="original", lease_token=token, run_id=run_id, now=_NOW)
    with database.session() as session:
        job = session.get(Job, job_id)
        assert job is not None and support._job_execution_state(job) == before
        assert session.get(SyncRun, run_id).status == "failed_terminal"
        assert all(lane.consecutive_failures == 0 for lane in session.scalars(select(SchedulerLane)))


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("running", _CODE),
        ("failed_retryable", _CODE),
        ("failed_terminal", "content_ownership_conflict: private-sentinel"),
        ("failed_terminal", "CONTENT_OWNERSHIP_CONFLICT"),
        ("failed_terminal", "schema_invalid"),
    ],
)
def test_reclaim_does_not_promote_similar_strings_or_nonterminal_runs(
    database: Database, status: str, code: str
) -> None:
    _, job_id, run_id, _ = _seed_attached(database, status=status, code=code)
    with database.session() as session:
        replacement = SchedulerRepository(session).claim_next(
            worker_id="ordinary-recovery", global_capacity=1, now=_NOW + timedelta(seconds=31)
        )
        assert replacement is not None and replacement.job_id == job_id and replacement.attempt == 2
        job = session.get(Job, job_id)
        assert job is not None and job.last_error_code == "unexpected_handler_failure"
        assert job.run_id == run_id


def test_live_conflict_is_not_reclaimed_before_lease_expiry(database: Database) -> None:
    _, job_id, _, _ = _seed_attached(database)
    with database.session() as session:
        assert (
            SchedulerRepository(session).claim_next(
                worker_id="too-early", global_capacity=1, now=_NOW + timedelta(seconds=29)
            )
            is None
        )
        job = session.get(Job, job_id)
        assert job is not None and job.status == "running" and job.attempts == 1


@pytest.mark.parametrize("attached", [True, False])
def test_unattached_historical_conflict_is_not_handler_authority(database: Database, attached: bool) -> None:
    subscription_id, job_id, historical_id, token = _seed_attached(database)
    with database.session() as session:
        current = SyncRunRepository(session).create(subscription_id=subscription_id, attempt=2)
        current_id = current.id
        job = session.get(Job, job_id)
        assert job is not None
        job.run_id = current_id if attached else None
    with database.session() as session:
        repository = SchedulerRepository(session)
        if attached:
            with pytest.raises(SchedulerRepositoryError, match="does not match"):
                repository.fail(
                    job_id,
                    worker_id="original",
                    lease_token=token,
                    run_id=historical_id,
                    error_code="unexpected_handler_failure",
                    now=_NOW,
                )
        else:
            # Do not adopt the returned historical Run and accidentally make it
            # authoritative during the next lease/retry recovery.
            with pytest.raises(SchedulerRepositoryError, match="requires its current attachment"):
                repository.fail(
                    job_id,
                    worker_id="original",
                    lease_token=token,
                    run_id=historical_id,
                    error_code="unexpected_handler_failure",
                    now=_NOW,
                )
    if attached:
        with database.session() as session:
            result = SchedulerRepository(session).fail(
                job_id,
                worker_id="original",
                lease_token=token,
                error_code="unexpected_handler_failure",
                now=_NOW,
            )
            assert result.status == "failed_retryable" and result.run_id == current_id


def test_explicit_legacy_conflict_result_can_bind_its_run_at_finalization(database: Database) -> None:
    _, job_id, run_id, token = _seed_attached(database)
    with database.session() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.run_id = None
    with database.session() as session:
        result = SchedulerRepository(session).fail(
            job_id,
            worker_id="original",
            lease_token=token,
            error_code=_CODE,
            run_id=run_id,
            now=_NOW,
        )
        assert (result.status, result.last_error_code, result.run_id) == ("failed_terminal", _CODE, run_id)
    _assert_terminal(database, job_id, run_id)


def test_finalization_refreshes_stale_run_and_job_identity_maps(database: Database) -> None:
    subscription_id, job_id, historical_id, token = _seed_attached(database)
    with database.session() as session:
        repository = SchedulerRepository(session)
        cached_job = session.get(Job, job_id)
        cached_run = session.get(SyncRun, historical_id)
        assert cached_job is not None and cached_run is not None
        current = SyncRunRepository(session).create(subscription_id=subscription_id, attempt=2)
        current_id = current.id
        # Model identity-map lag after independently committed SQL without
        # relying on SQLite's driver-specific read-transaction timing.
        session.execute(
            update(Job).where(Job.id == job_id).values(run_id=current_id).execution_options(synchronize_session=False)
        )
        assert cached_job.run_id == historical_id
        result = repository.fail(
            job_id,
            worker_id="original",
            lease_token=token,
            error_code="unexpected_handler_failure",
            now=_NOW,
        )
        assert result.status == "failed_retryable" and result.run_id == current_id


def test_finalization_reads_durable_run_columns_not_cached_status(database: Database) -> None:
    _, job_id, run_id, token = _seed_attached(database, status="running", code="schema_invalid")
    with database.session() as session:
        cached = session.get(SyncRun, run_id)
        assert cached is not None and cached.status == "running"
        session.execute(
            update(SyncRun)
            .where(SyncRun.id == run_id)
            .values(status="failed_terminal", error_code=_CODE)
            .execution_options(synchronize_session=False)
        )
        assert cached.status == "running"
        result = SchedulerRepository(session).fail(
            job_id,
            worker_id="original",
            lease_token=token,
            error_code="unexpected_handler_failure",
            now=_NOW,
        )
        assert (result.status, result.last_error_code) == ("failed_terminal", _CODE)
    _assert_terminal(database, job_id, run_id)


def test_invalid_queued_attachment_does_not_block_other_candidates(database: Database) -> None:
    _, invalid_id, run_id, _ = _seed_attached(database)
    _, valid_subscription = support._seed_subscription(database, platform="xhs", remote_id="unblocked-author", now=_NOW)
    valid_id = support._materialize_one(database, valid_subscription, now=_NOW)
    with database.session() as session:
        invalid = session.get(Job, invalid_id)
        assert invalid is not None
        invalid.status = "queued"
        invalid.priority = 100
        invalid.lease_owner = invalid.lease_token = invalid.lease_expires_at = None
        invalid.payload = {"invalid": True}
        session.flush()
        claim = SchedulerRepository(session).claim_next(worker_id="valid-next", global_capacity=1, now=_NOW)
        assert claim is not None and claim.job_id == valid_id
        session.refresh(invalid)
        assert invalid.status == "failed_terminal" and invalid.last_error_code == "schema_invalid"
        assert session.get(SyncRun, run_id).error_code == _CODE


@pytest.mark.parametrize("changed", ["attachment", "token", "cancel"])
def test_conflict_compare_and_swap_rejects_changed_observation(database: Database, changed: str) -> None:
    subscription_id, job_id, run_id, _ = _seed_attached(database)
    with database.session() as session:
        repository = SchedulerRepository(session)
        stale = session.get(Job, job_id)
        assert stale is not None
        if changed == "attachment":
            other = SyncRunRepository(session).create(subscription_id=subscription_id, attempt=2)
            values: dict[str, Any] = {"run_id": other.id}
        elif changed == "token":
            values = {"lease_token": "replacement-token"}
        else:
            values = {"status": "cancelled", "lease_owner": None, "lease_token": None, "lease_expires_at": None}
        session.execute(
            update(Job).where(Job.id == job_id).values(**values).execution_options(synchronize_session=False)
        )
        assert stale.run_id == run_id and stale.status == "running"
        with pytest.raises(SchedulerRepositoryError, match="attachment changed during reconciliation"):
            repository._reconcile_ownership_conflict_attachment(stale, now=_NOW)
        session.refresh(stale)
        assert all(getattr(stale, key) == value for key, value in values.items())
        assert stale.last_error_code is None
        assert all(lane.consecutive_failures == 0 for lane in session.scalars(select(SchedulerLane)))
        assert session.get(Subscription, subscription_id).consecutive_failures == 0


def test_foreign_subscription_attachment_is_not_conflict_authority(database: Database) -> None:
    _, job_id, _, token = _seed_attached(database)
    _, other_subscription = support._seed_subscription(database, platform="xhs", remote_id="foreign-owner", now=_NOW)
    with database.session() as session:
        runs = SyncRunRepository(session)
        other = runs.create(subscription_id=other_subscription)
        runs.set_status(other.id, "claimed", expected_status="queued", at=_NOW)
        runs.set_status(other.id, "running", expected_status="claimed", at=_NOW)
        runs.set_status(other.id, "failed_terminal", expected_status="running", error_code=_CODE, at=_NOW)
        job = session.get(Job, job_id)
        assert job is not None
        job.run_id = other.id
    with database.session() as session, pytest.raises(SchedulerRepositoryError, match="attached run scope is invalid"):
        SchedulerRepository(session).fail(
            job_id, worker_id="original", lease_token=token, error_code="unexpected_handler_failure", now=_NOW
        )
    with database.session() as session:
        job = session.get(Job, job_id)
        assert job is not None and job.status == "running" and job.last_error_code is None


def test_conflict_does_not_release_another_jobs_half_open_probe(database: Database) -> None:
    _, job_id, run_id, token = _seed_attached(database)
    _, other_subscription = support._seed_subscription(database, platform="xhs", remote_id="probe-owner", now=_NOW)
    other_job = support._materialize_one(database, other_subscription, now=_NOW)
    with database.session() as session:
        for lane in session.scalars(select(SchedulerLane)):
            lane.consecutive_failures = 2
            lane.circuit_state = "half_open"
            lane.half_open_job_id = other_job
    with database.session() as session:
        SchedulerRepository(session).fail(
            job_id, worker_id="original", lease_token=token, error_code="unexpected_handler_failure", now=_NOW
        )
    _assert_terminal(database, job_id, run_id, lane_failures=2)
    with database.session() as session:
        for lane in session.scalars(select(SchedulerLane)):
            assert lane.circuit_state == "half_open" and lane.half_open_job_id == other_job


@pytest.mark.parametrize("status", ["retry_wait", "failed_retryable", "running"])
def test_corrupt_recovery_payload_does_not_block_other_subscriptions_or_rewrite_schedule(
    database: Database, status: str
) -> None:
    subscription_id, invalid_id, run_id, _ = _seed_attached(database)
    _, valid_subscription = support._seed_subscription(
        database, platform="xhs", remote_id="valid-after-corrupt-recovery", now=_NOW
    )
    valid_id = support._materialize_one(database, valid_subscription, now=_NOW)
    with database.session() as session:
        invalid = session.get(Job, invalid_id)
        subscription = session.get(Subscription, subscription_id)
        assert invalid is not None and subscription is not None
        invalid.status = status
        invalid.payload = {"invalid": True}
        if status != "running":
            invalid.lease_owner = invalid.lease_token = invalid.lease_expires_at = None
        # A corrupt historical cycle cannot prove authority over this schedule.
        subscription.schedule_revision += 1
        subscription.next_run_at = _NOW + timedelta(hours=1)
        session.flush()
        expected_schedule = SchedulerRepository(session).get_subscription_schedule(subscription_id)
    with database.session() as session:
        claim = SchedulerRepository(session).claim_next(
            worker_id="valid-after-corrupt", global_capacity=1, now=_NOW + timedelta(seconds=31)
        )
        assert claim is not None and claim.job_id == valid_id
        assert SchedulerRepository(session).get_subscription_schedule(subscription_id) == expected_schedule
    _assert_terminal(database, invalid_id, run_id)
