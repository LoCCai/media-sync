"""Durable exact receipts survive observer races and reject foreign evidence."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from media_sync.application.operations import OperationCoordinator
from media_sync.application.subscription_delivery import build_subscription_delivery_result
from media_sync.infrastructure.db import (
    Database,
    JobRepository,
    OperationConflictError,
    OperationRepository,
    OperationSubjectInput,
)
from media_sync.infrastructure.db.models import Job, Operation, Subscription
from media_sync.scheduler.pipeline import PipelineJobRepository, PipelineJobRepositoryError
from media_sync.scheduler.pipeline_receipt import PipelineDeliveryReceipt
from media_sync.scheduler.pipeline_worker import PipelineHandlerResult, PipelineSubscriptionWorker
from tests.integration.test_pipeline_worker import NOW, _seed_pipeline


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    database = Database(f"sqlite:///{(tmp_path / 'receipts.sqlite3').as_posix()}")
    database.create_schema()
    yield database
    database.dispose()


def seed(database: Database) -> tuple[tuple[str, str, str, str, str], PipelineDeliveryReceipt]:
    ids = _seed_pipeline(database, remote_id="receipt")
    with database.session() as session:
        author_id = session.get(Subscription, ids[2]).author_id
        export = JobRepository(session).enqueue(
            job_type="export.emby",
            natural_key="receipt-export",
            payload={"author_id": author_id, "result": {"managed_file_count": 3}},
        )
        export.status = "succeeded"
        receipt = PipelineDeliveryReceipt(
            ids[2], ids[3], author_id, "bili", export.id, 1, 1, 1, 0, "published", 3, True
        )
    return ids, receipt


async def run(database: Database, ids: tuple[str, str, str, str, str], receipt: PipelineDeliveryReceipt):
    worker = PipelineSubscriptionWorker(
        database, lambda _claim: PipelineHandlerResult.success(receipt), clock=lambda: NOW
    )
    return await worker.run_exact(
        ids[0],
        expected_subscription_id=ids[2],
        expected_sync_job_id=ids[1],
        expected_run_id=ids[4],
        worker_id="receipt",
    )


@pytest.mark.asyncio
async def test_receipt_and_success_persist_together_and_exact_idle_reconstructs_without_handler(
    database: Database,
) -> None:
    ids, receipt = seed(database)
    first = await run(database, ids, receipt)
    assert first.status == "succeeded" and first.receipt == receipt
    with database.session() as session:
        job = session.get(Job, ids[0])
        assert job.payload == {
            "schema_version": 2,
            "sync_job_id": ids[1],
            "subscription_id": ids[2],
            "run_id": ids[4],
            "result": receipt.to_mapping(),
        }
        assert PipelineJobRepository(session).get(ids[0]).receipt == receipt

    def forbidden(_claim: object):
        pytest.fail("already completed exact job must not invoke handler")

    worker = PipelineSubscriptionWorker(database, forbidden, clock=lambda: NOW)
    observed = await worker.run_exact(
        ids[0],
        expected_subscription_id=ids[2],
        expected_sync_job_id=ids[1],
        expected_run_id=ids[4],
        worker_id="observer",
    )
    assert observed.status == "succeeded" and observed.receipt == receipt
    result = build_subscription_delivery_result(
        database, subscription_id=ids[2], sync_job_id=ids[1], run_id=ids[4], pipeline_job_id=ids[0]
    )
    assert result["directory_verified"] is True and result["export_job_id"] == receipt.export_job_id


@pytest.mark.asyncio
async def test_lost_success_acknowledgement_reobserves_the_committed_receipt(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids, receipt = seed(database)
    original = database.session
    lost = False

    @contextmanager
    def session_with_lost_ack() -> Iterator[Session]:
        nonlocal lost
        with original() as session:
            yield session
            job = session.get(Job, ids[0])
            lose_now = not lost and job is not None and job.status == "succeeded"
        if lose_now:
            lost = True
            raise OSError("synthetic completed transaction acknowledgement loss")

    monkeypatch.setattr(database, "session", session_with_lost_ack)
    result = await run(database, ids, receipt)
    assert lost and result.status == "succeeded" and result.receipt == receipt


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["extra", "missing", "bool", "foreign_account", "foreign_export", "unfinished"])
async def test_durable_v2_receipt_rejects_unknown_or_foreign_evidence(database: Database, tamper: str) -> None:
    ids, receipt = seed(database)
    assert (await run(database, ids, receipt)).status == "succeeded"
    with database.session() as session:
        job = session.get(Job, ids[0])
        value = dict(job.payload["result"])
        if tamper == "extra":
            value["private_path"] = "PRIVATE_SENTINEL"
        elif tamper == "missing":
            value.pop("managed_file_count")
        elif tamper == "bool":
            value["selected_asset_count"] = True
        elif tamper == "foreign_account":
            value["account_id"] = str(uuid4())
        elif tamper == "foreign_export":
            session.get(Job, receipt.export_job_id).payload = {
                "author_id": str(uuid4()),
                "result": {"managed_file_count": 3},
            }
        else:
            job.status = "queued"
        job.payload = {**job.payload, "result": value}
        flag_modified(job, "payload")
    with database.session() as session, pytest.raises(PipelineJobRepositoryError):
        PipelineJobRepository(session).get(ids[0])


@pytest.mark.asyncio
async def test_foreign_receipt_cannot_be_committed_as_success(database: Database) -> None:
    ids, receipt = seed(database)
    forged = PipelineDeliveryReceipt.from_mapping({**receipt.to_mapping(), "author_id": str(uuid4())})
    result = await run(database, ids, forged)
    assert result.status != "succeeded" and result.receipt is None
    with database.session() as session:
        job = session.get(Job, ids[0])
        assert job.status != "succeeded" and job.payload["schema_version"] == 1 and "result" not in job.payload


@pytest.mark.asyncio
async def test_receipt_binding_wait_cannot_borrow_an_expired_completion_lease(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids, receipt = seed(database)
    current = NOW
    original = PipelineJobRepository.completion_payload

    def delayed(repository: PipelineJobRepository, job: Job, value: PipelineDeliveryReceipt):
        nonlocal current
        payload = original(repository, job, value)
        current = NOW + timedelta(seconds=61)
        return payload

    monkeypatch.setattr(PipelineJobRepository, "completion_payload", delayed)
    worker = PipelineSubscriptionWorker(
        database, lambda _claim: PipelineHandlerResult.success(receipt), clock=lambda: current
    )
    result = await worker.run_exact(
        ids[0],
        expected_subscription_id=ids[2],
        expected_sync_job_id=ids[1],
        expected_run_id=ids[4],
        worker_id="expiring",
        lease_seconds=60,
    )
    assert result.status == "fenced" and result.receipt is None
    with database.session() as session:
        job = session.get(Job, ids[0])
        assert job.status == "running" and job.payload["schema_version"] == 1 and "result" not in job.payload


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", [False, True])
async def test_expired_operation_reconstructs_only_exact_succeeded_receipt_chain(
    database: Database, tamper: bool
) -> None:
    ids, receipt = seed(database)
    assert (await run(database, ids, receipt)).status == "succeeded"
    with database.session() as session:
        operations = OperationRepository(session)
        operation = operations.create_or_replay(
            kind="subscription-delivery",
            request_fingerprint="a" * 64,
            target_type="subscription",
            target_id=ids[2],
            at=NOW,
        )
        lease = operations.claim(
            operation.operation_id, expected_revision=operation.revision, lease_owner="gone", lease_seconds=1, at=NOW
        )
        operations.link_subject(
            operation.operation_id,
            OperationSubjectInput("job", ids[1], "execution"),
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            at=NOW,
        )
        if tamper:
            session.get(Job, receipt.export_job_id).status = "failed_terminal"
    coordinator = OperationCoordinator(database, clock=lambda: NOW + timedelta(seconds=5))
    try:
        result = coordinator.reconcile_expired(at=NOW + timedelta(seconds=5))
        assert result.succeeded == int(not tamper)
        assert result.interrupted == int(tamper)
        observed = coordinator.get(operation.operation_id)
        assert observed.state == ("interrupted" if tamper else "succeeded")
        if not tamper:
            assert observed.result_summary["export_job_id"] == receipt.export_job_id
    finally:
        coordinator.shutdown(timeout_seconds=0)


@pytest.mark.parametrize("active_stage", ["sync", "pipeline"])
def test_expired_operation_defers_for_active_chain_and_later_reconstructs_receipt(
    database: Database,
    active_stage: str,
) -> None:
    ids, receipt = seed(database)
    pipeline_claim = None
    with database.session() as session:
        if active_stage == "sync":
            source = session.get(Job, ids[1])
            assert source is not None
            source.status = "running"
            source.attempts = 1
            source.lease_owner = "supervisor"
            source.lease_token = str(uuid4())
            source.lease_expires_at = NOW + timedelta(seconds=60)
            source.finished_at = None
        else:
            pipeline = PipelineJobRepository(session)
            pipeline_claim = pipeline.claim_exact(
                ids[0],
                expected_subscription_id=ids[2],
                expected_sync_job_id=ids[1],
                expected_run_id=ids[4],
                worker_id="supervisor",
                lease_seconds=60,
                now=NOW,
            )
            assert pipeline_claim is not None
            JobRepository(session).start(
                pipeline_claim.job_id,
                worker_id="supervisor",
                lease_token=pipeline_claim.lease_token,
                now=NOW,
            )
        operations = OperationRepository(session)
        operation = operations.create_or_replay(
            kind="subscription-delivery",
            request_fingerprint="b" * 64,
            exclusive_key=f"subscription-delivery:{ids[2]}",
            target_type="subscription",
            target_id=ids[2],
            at=NOW,
        )
        lease = operations.claim(
            operation.operation_id,
            expected_revision=operation.revision,
            lease_owner="gone",
            lease_seconds=1,
            at=NOW,
        )
        operations.link_subject(
            operation.operation_id,
            OperationSubjectInput("job", ids[1], "execution"),
            expected_revision=lease.revision,
            lease_owner=lease.lease_owner,
            lease_token=lease.lease_token,
            at=NOW,
        )

    coordinator = OperationCoordinator(database, clock=lambda: NOW + timedelta(seconds=5))
    try:
        deferred = coordinator.reconcile_expired(at=NOW + timedelta(seconds=5))
        assert deferred.scanned == 1
        assert (
            deferred.succeeded,
            deferred.failed_terminal,
            deferred.cancelled,
            deferred.interrupted,
            deferred.conflicted,
        ) == (0, 0, 0, 0, 0)
        assert coordinator.get(operation.operation_id).state == "running"

        with database.session() as session:
            retained = session.get(Operation, operation.operation_id)
            assert retained is not None
            assert retained.exclusive_key == f"subscription-delivery:{ids[2]}"
            with pytest.raises(OperationConflictError, match="operation_already_running"):
                OperationRepository(session).create_or_replay(
                    kind="subscription-delivery",
                    request_fingerprint="c" * 64,
                    exclusive_key=f"subscription-delivery:{ids[2]}",
                    target_type="subscription",
                    target_id=ids[2],
                    at=NOW + timedelta(seconds=5),
                )

        with database.session() as session:
            pipeline = PipelineJobRepository(session)
            if active_stage == "sync":
                source = session.get(Job, ids[1])
                assert source is not None
                source.status = "succeeded"
                source.lease_owner = None
                source.lease_token = None
                source.lease_expires_at = None
                source.finished_at = NOW + timedelta(seconds=6)
                session.flush()
                pipeline_claim = pipeline.claim_exact(
                    ids[0],
                    expected_subscription_id=ids[2],
                    expected_sync_job_id=ids[1],
                    expected_run_id=ids[4],
                    worker_id="supervisor",
                    lease_seconds=60,
                    now=NOW + timedelta(seconds=6),
                )
                assert pipeline_claim is not None
                JobRepository(session).start(
                    pipeline_claim.job_id,
                    worker_id="supervisor",
                    lease_token=pipeline_claim.lease_token,
                    now=NOW + timedelta(seconds=6),
                )
            assert pipeline_claim is not None
            job = session.get(Job, pipeline_claim.job_id)
            assert job is not None
            replacement = pipeline.completion_payload(job, receipt)
            JobRepository(session).complete(
                pipeline_claim.job_id,
                worker_id="supervisor",
                lease_token=pipeline_claim.lease_token,
                replacement_payload=replacement,
                now=NOW + timedelta(seconds=6),
            )

        recovered = coordinator.reconcile_expired(at=NOW + timedelta(seconds=7))
        assert recovered.succeeded == 1
        observed = coordinator.get(operation.operation_id)
        assert observed.state == "succeeded"
        assert observed.result_summary["export_job_id"] == receipt.export_job_id
    finally:
        coordinator.shutdown(timeout_seconds=0)
