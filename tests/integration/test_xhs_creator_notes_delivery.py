from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from media_sync.domain import AuthStatus, LoginMethod
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    SubscriptionRepository,
)
from media_sync.infrastructure.db.models import (
    Content,
    Job,
    Subscription,
    SyncRunContent,
    XhsSubscriptionProgress,
)
from media_sync.integrations.mediacrawler.bridge import MediaCrawlerBridge, MediaCrawlerRunSpec, RunnerManifest
from media_sync.integrations.mediacrawler.checkout import VerifiedPython
from media_sync.integrations.mediacrawler.policies import inspect_output
from media_sync.integrations.mediacrawler.receipt import write_completion_receipt
from media_sync.integrations.mediacrawler.runner import MediaCrawlerProcessResult, MediaCrawlerProcessStatus
from media_sync.integrations.mediacrawler.subscription_policy import MediaCrawlerSubscriptionPolicy
from media_sync.integrations.mediacrawler.xhs_creator_notes import (
    XHS_SCAN_COVERAGE_FILENAME,
    XHS_SCAN_IDENTITY_FIELD,
    XhsCreatorPage,
    XhsNoteIdentity,
    XhsScanCoverage,
    XhsScanState,
    XhsScanUnit,
)
from media_sync.scheduler.handlers import SubscriptionHandlerRegistry
from media_sync.scheduler.mediacrawler_handler import MediaCrawlerScheduledHandler
from media_sync.scheduler.pipeline_receipt import PipelineDeliveryReceipt
from media_sync.scheduler.pipeline_worker import PipelineHandlerResult, PipelineSubscriptionWorker
from media_sync.scheduler.service import DurableSchedulerService, SubscriptionWorker
from media_sync.scheduler.xhs_delivery_progress import XhsDeliveryProgressRepository, xhs_delivery_progress_payload
from media_sync.scheduler.xhs_scan_continuation import XhsScanContinuationPolicy
from media_sync.security import SecretValue
from tests.integration import test_mediacrawler_scheduler_handler as support

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CREATOR_ID = "5f1234567890abcdef123456"
CREATOR_SECRET_REF = "env:EXECUTION0076_XHS_CREATOR"
COOKIE_SECRET_REF = "env:EXECUTION0076_XHS_COOKIE"
CREATOR_REFERENCE = (
    f"https://www.xiaohongshu.com/user/profile/{CREATOR_ID}?xsec_token=execution-0076-creator-token&xsec_source=pc_user"
)
UPSTREAM_SHA = support.PINNED_SHA


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'xhs-delivery.sqlite3').as_posix()}")
    instance.create_schema()
    yield instance
    instance.dispose()


class _Resolver:
    def resolve(self, reference: str) -> SecretValue:
        if reference == CREATOR_SECRET_REF:
            return SecretValue(CREATOR_REFERENCE)
        if reference == COOKIE_SECRET_REF:
            return SecretValue("execution-0076-cookie")
        raise AssertionError("unexpected secret reference")


class _SealedXhsPages:
    """Replace network I/O while retaining every local production boundary."""

    def __init__(self) -> None:
        self.history = {
            "": (tuple(range(0, 3)), "cursor-one", True),
            "cursor-one": (tuple(range(3, 6)), "cursor-two", True),
            "cursor-two": ((6,), "", False),
        }
        self.head = tuple(range(0, 3))
        self.run_number = 0
        self.restricted_cursors: set[str] = set()
        self.failed_notes: set[int] = set()
        self.coverages: list[XhsScanCoverage] = []
        self.manifests: list[RunnerManifest] = []
        self.detail_note_ids: list[list[str]] = []

    def run(self, spec: MediaCrawlerRunSpec, cancellation: Event | None = None) -> MediaCrawlerProcessResult:
        assert cancellation is not None and not cancellation.is_set()
        manifest = RunnerManifest.load(spec.paths.manifest_path)
        assert manifest == spec.manifest and manifest.xhs_scan is not None
        self.manifests.append(manifest)
        self.run_number += 1
        self.detail_note_ids.append([])
        unit = XhsScanUnit(manifest.xhs_scan, manifest.max_items)
        rows: list[dict[str, object]] = []
        while (action := unit.next_action()).kind != "stop":
            if action.kind == "list":
                assert action.cursor is not None
                if manifest.xhs_scan.lane == "history" and action.cursor in self.restricted_cursors:
                    unit.observe_access_restricted()
                    continue
                if manifest.xhs_scan.lane == "head":
                    indexes, next_cursor, has_more = self.head, "head-tail", True
                else:
                    indexes, next_cursor, has_more = self.history[action.cursor]
                identities = tuple(
                    XhsNoteIdentity(
                        f"{index:024x}",
                        hashlib.sha256(f"listing-{index}".encode()).hexdigest(),
                        hashlib.sha256(f"fresh-{self.run_number}-{index}".encode()).hexdigest(),
                        "pc_user",
                    )
                    for index in indexes
                )
                unit.observe_page(XhsCreatorPage(action.cursor, next_cursor, has_more, identities))
                continue
            identity = action.identity
            assert identity is not None
            if action.kind == "unchanged":
                unit.skip_unchanged(identity)
                continue
            token = f"fresh-{self.run_number}-{int(identity.note_id, 16)}"
            assert hashlib.sha256(token.encode()).hexdigest() == identity.token_sha256
            self.detail_note_ids[-1].append(identity.note_id)
            if int(identity.note_id, 16) in self.failed_notes:
                unit.fail(identity)
                continue
            rows.append(
                {
                    "note_id": identity.note_id,
                    "type": "normal",
                    "title": f"XHS note {identity.note_id}",
                    "desc": "execution 0076 sealed fixture",
                    "time": 1_788_235_200_000 + int(identity.note_id, 16),
                    "video_url": "",
                    "image_list": "",
                    "xsec_token": token,
                    XHS_SCAN_IDENTITY_FIELD: {
                        **identity.as_mapping(),
                        "creator_fingerprint_sha256": manifest.creator_fingerprint_sha256,
                    },
                }
            )
            unit.store(identity)
        coverage = unit.coverage()
        self.coverages.append(coverage)
        if rows:
            (manifest.output_root / "xhs-notes.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=True, separators=(",", ":")) + "\n" for row in rows),
                encoding="utf-8",
                newline="\n",
            )
        (manifest.output_root / XHS_SCAN_COVERAGE_FILENAME).write_text(
            coverage.to_json_line(),
            encoding="utf-8",
            newline="\n",
        )
        write_completion_receipt(manifest, inspect_output(manifest.output_root, manifest.watchdogs), known_secrets=())
        return MediaCrawlerProcessResult(MediaCrawlerProcessStatus.SUCCEEDED, "sealed XHS page")


def _policy(delay_seconds: int = 300) -> XhsScanContinuationPolicy:
    return XhsScanContinuationPolicy(delay_seconds, UPSTREAM_SHA)


def _seed(database: Database) -> str:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="xhs",
            adapter="mediacrawler",
            display_name="Execution 0076 XHS",
            login_method=LoginMethod.COOKIE.value,
            credential_ref=COOKIE_SECRET_REF,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="xhs", remote_id=CREATOR_ID, display_name="Execution 0076 creator")
        )
        policy = MediaCrawlerSubscriptionPolicy(
            allow_full_history=True,
            request_delay_seconds=2,
            headless=True,
            creator_secret_ref=CREATOR_SECRET_REF,
        )
        return (
            SubscriptionRepository(session)
            .create(
                account_id=account.id,
                author_id=author.id,
                interval_seconds=21_600,
                max_items=2,
                policy={"mediacrawler": policy.to_payload()},
                next_run_at=support.NOW - timedelta(seconds=1),
            )
            .id
        )


def _worker(
    database: Database,
    runtime_root: Path,
    runner: _SealedXhsPages,
    clock: support._Clock,
    *,
    continuation_policy: XhsScanContinuationPolicy | None = None,
) -> SubscriptionWorker:
    handler = MediaCrawlerScheduledHandler(
        database,
        lock_path=REPOSITORY_ROOT / "upstreams.lock.json",
        integration_root=runtime_root,
        python_executable=Path(sys.executable),
        secret_resolver=_Resolver(),  # type: ignore[arg-type]
        enabled=True,
        license_acknowledged=True,
        bridge=MediaCrawlerBridge(lambda executable: VerifiedPython(executable.expanduser().resolve())),
        runner=runner,
        clock=clock,
    )
    return SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"mediacrawler": handler}),
        clock=clock,
        xhs_scan_continuation=continuation_policy or _policy(),
    )


async def _qualify_delivery(
    database: Database,
    clock: support._Clock,
    *,
    continuation_policy: XhsScanContinuationPolicy | None = None,
) -> None:
    with database.session() as session:
        pipeline = session.scalar(
            select(Job)
            .where(Job.job_type == "pipeline.subscription", Job.status == "queued")
            .order_by(Job.created_at, Job.id)
        )
        assert pipeline is not None and pipeline.subscription_id is not None and pipeline.run_id is not None
        subscription = session.get(Subscription, pipeline.subscription_id)
        assert subscription is not None
        observed = int(
            session.scalar(
                select(func.count())
                .select_from(SyncRunContent)
                .where(
                    SyncRunContent.run_id == pipeline.run_id,
                    SyncRunContent.subscription_id == subscription.id,
                )
            )
            or 0
        )
        export = Job(
            id=str(uuid4()),
            job_type="export.emby",
            natural_key=f"xhs-test-export:{pipeline.id}",
            payload={"author_id": subscription.author_id, "result": {"managed_file_count": observed + 1}},
            status="succeeded",
            max_attempts=1,
            available_at=clock.value,
            finished_at=clock.value,
        )
        session.add(export)
        session.flush()
        receipt = PipelineDeliveryReceipt(
            subscription_id=subscription.id,
            account_id=subscription.account_id,
            author_id=subscription.author_id,
            platform="xhs",
            export_job_id=export.id,
            selected_asset_count=0,
            verified_asset_count=0,
            downloaded_count=0,
            already_verified_count=0,
            publication_disposition="published",
            managed_file_count=observed + 1,
            directory_verified=True,
            schema_version=2,
            source_run_id=pipeline.run_id,
            observed_content_count=observed,
            delivered_content_count=observed,
        )
    result = await PipelineSubscriptionWorker(
        database,
        lambda _claim: PipelineHandlerResult.success(receipt),
        clock=clock,
        xhs_delivery_policy=continuation_policy or _policy(),
    ).run_once(worker_id=f"xhs-delivery-{uuid4()}")
    assert (result.status, result.error_code) == ("succeeded", None)


@pytest.mark.asyncio
async def test_xhs_zero_fast_continuation_keeps_delivery_progress_on_ordinary_interval(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database)
    clock = support._Clock()
    policy = _policy(0)
    runner = _SealedXhsPages()

    scheduler = DurableSchedulerService(database, clock=clock, xhs_scan_continuation=policy)
    assert scheduler.tick(limit=1).materialized_count == 1
    result = await _worker(
        database,
        (tmp_path / "runtime-zero-delay").resolve(),
        runner,
        clock,
        continuation_policy=policy,
    ).run_once(worker_id="xhs-zero-delay-sync")
    assert result.status == "succeeded"
    await _qualify_delivery(database, clock, continuation_policy=policy)

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        progress = session.get(XhsSubscriptionProgress, subscription_id)
        assert subscription is not None and progress is not None
        assert progress.batch_count == 1 and progress.last_pipeline_job_id is not None
        assert subscription.next_run_at == clock.value + timedelta(seconds=subscription.interval_seconds)


@pytest.mark.asyncio
async def test_xhs_three_cursor_history_reconciles_then_delivers_incremental_note(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database)
    clock = support._Clock()
    runtime_root = (tmp_path / "runtime").resolve()
    runner = _SealedXhsPages()
    phases: list[str] = []
    cursor_steps: list[int] = []

    for number in range(8):
        scheduler = DurableSchedulerService(database, clock=clock, xhs_scan_continuation=_policy())
        assert scheduler.tick(limit=1).materialized_count == 1
        result = await _worker(database, runtime_root, runner, clock).run_once(worker_id=f"xhs-sync-{number}")
        assert result.status == "succeeded"
        await _qualify_delivery(database, clock)
        with database.session() as session:
            subscription = session.get(Subscription, subscription_id)
            progress = session.get(XhsSubscriptionProgress, subscription_id)
            assert subscription is not None and progress is not None
            phases.append(progress.phase)
            cursor_steps.append(progress.cursor_step_count)
            assert subscription.next_run_at is not None
            clock.value = subscription.next_run_at + timedelta(seconds=1)
        if phases[-1] == "incremental":
            break

    assert phases[-1] == "incremental"
    assert "reconciling" in phases
    assert cursor_steps[-1] >= 4
    assert {coverage.stop_reason for coverage in runner.coverages} == {"unit_cap_reached", "has_more_false"}
    with database.session() as session:
        assert set(session.scalars(select(Content.remote_id))) == {f"{index:024x}" for index in range(7)}
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        public = xhs_delivery_progress_payload(subscription, upstream_sha=UPSTREAM_SHA)
        assert public is not None and public["baseline_snapshot_complete"] is True
        assert all(value not in repr(public) for value in ("cursor-one", "cursor-two", "head-tail"))
        assert "token" not in repr(public).lower()

    runner.head = (99, 0, 1)
    scheduler = DurableSchedulerService(database, clock=clock, xhs_scan_continuation=_policy())
    assert scheduler.tick(limit=1).materialized_count == 1
    result = await _worker(database, runtime_root, runner, clock).run_once(worker_id="xhs-incremental-new")
    assert result.status == "succeeded"
    await _qualify_delivery(database, clock)
    with database.session() as session:
        assert f"{99:024x}" in set(session.scalars(select(Content.remote_id)))
        progress = session.get(XhsSubscriptionProgress, subscription_id)
        assert progress is not None and progress.phase == "incremental" and progress.incremental_batch_count == 1
    assert runner.detail_note_ids[-1] == [f"{99:024x}"]

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None and subscription.next_run_at is not None
        clock.value = subscription.next_run_at + timedelta(seconds=1)
    scheduler = DurableSchedulerService(database, clock=clock, xhs_scan_continuation=_policy())
    assert scheduler.tick(limit=1).materialized_count == 1
    result = await _worker(database, runtime_root, runner, clock).run_once(worker_id="xhs-incremental-unchanged")
    assert result.status == "succeeded"
    await _qualify_delivery(database, clock)
    assert runner.detail_note_ids[-1] == []
    with database.session() as session:
        assert set(session.scalars(select(Content.remote_id))) == {
            *(f"{index:024x}" for index in range(7)),
            f"{99:024x}",
        }
        progress = session.get(XhsSubscriptionProgress, subscription_id)
        assert progress is not None and progress.incremental_batch_count == 2


@pytest.mark.asyncio
async def test_xhs_access_restriction_backs_off_then_resumes_same_cursor(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database)
    clock = support._Clock()
    runtime_root = (tmp_path / "runtime").resolve()
    runner = _SealedXhsPages()
    runner.restricted_cursors.add("")

    scheduler = DurableSchedulerService(database, clock=clock, xhs_scan_continuation=_policy())
    assert scheduler.tick(limit=1).materialized_count == 1
    result = await _worker(database, runtime_root, runner, clock).run_once(worker_id="xhs-restricted")
    assert result.status == "succeeded"
    await _qualify_delivery(database, clock)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        progress = session.get(XhsSubscriptionProgress, subscription_id)
        assert subscription is not None and progress is not None
        assert (progress.phase, progress.blocked_code, progress.source_end_run_id) == (
            "blocked",
            "xhs_access_restricted",
            None,
        )
        assert subscription.next_run_at == clock.value + timedelta(seconds=subscription.interval_seconds)
        clock.value = subscription.next_run_at + timedelta(seconds=1)

    runner.restricted_cursors.clear()
    assert scheduler.tick(limit=1).materialized_count == 1
    result = await _worker(database, runtime_root, runner, clock).run_once(worker_id="xhs-resumed")
    assert result.status == "succeeded"
    await _qualify_delivery(database, clock)
    with database.session() as session:
        progress = session.get(XhsSubscriptionProgress, subscription_id)
        assert progress is not None
        assert progress.phase == "backfill" and progress.blocked_code is None
        assert progress.note_observation_count == 2


@pytest.mark.asyncio
async def test_xhs_head_drift_requires_a_second_stable_reconciliation(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database)
    clock = support._Clock()
    runtime_root = (tmp_path / "runtime").resolve()
    runner = _SealedXhsPages()

    # Complete history with max_items=2, then insert one head note before reconciliation.
    for number in range(5):
        scheduler = DurableSchedulerService(database, clock=clock, xhs_scan_continuation=_policy())
        assert scheduler.tick(limit=1).materialized_count == 1
        result = await _worker(database, runtime_root, runner, clock).run_once(worker_id=f"xhs-history-{number}")
        assert result.status == "succeeded"
        await _qualify_delivery(database, clock)
        with database.session() as session:
            subscription = session.get(Subscription, subscription_id)
            progress = session.get(XhsSubscriptionProgress, subscription_id)
            assert subscription is not None and progress is not None and subscription.next_run_at is not None
            clock.value = subscription.next_run_at + timedelta(seconds=1)
    with database.session() as session:
        progress = session.get(XhsSubscriptionProgress, subscription_id)
        assert progress is not None and progress.phase == "reconciling"

    runner.head = (99, 0, 1)
    for number in range(2):
        scheduler = DurableSchedulerService(database, clock=clock, xhs_scan_continuation=_policy())
        assert scheduler.tick(limit=1).materialized_count == 1
        result = await _worker(database, runtime_root, runner, clock).run_once(worker_id=f"xhs-drift-{number}")
        assert result.status == "succeeded"
        await _qualify_delivery(database, clock)
        with database.session() as session:
            subscription = session.get(Subscription, subscription_id)
            assert subscription is not None and subscription.next_run_at is not None
            clock.value = subscription.next_run_at + timedelta(seconds=1)
    with database.session() as session:
        progress = session.get(XhsSubscriptionProgress, subscription_id)
        assert progress is not None and progress.phase == "reconciling"
        assert progress.baseline_snapshot_at is None

    # One more complete re-list (two bounded units) is required for the new boundary to become stable.
    for number in range(2):
        scheduler = DurableSchedulerService(database, clock=clock, xhs_scan_continuation=_policy())
        assert scheduler.tick(limit=1).materialized_count == 1
        result = await _worker(database, runtime_root, runner, clock).run_once(worker_id=f"xhs-drift-stable-{number}")
        assert result.status == "succeeded"
        await _qualify_delivery(database, clock)
        with database.session() as session:
            subscription = session.get(Subscription, subscription_id)
            assert subscription is not None and subscription.next_run_at is not None
            clock.value = subscription.next_run_at + timedelta(seconds=1)
    with database.session() as session:
        progress = session.get(XhsSubscriptionProgress, subscription_id)
        assert progress is not None and progress.phase == "incremental"
        assert progress.baseline_snapshot_at is not None
        assert f"{99:024x}" in set(session.scalars(select(Content.remote_id)))


@pytest.mark.asyncio
async def test_xhs_failed_note_is_partial_without_hiding_unrelated_notes(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database)
    clock = support._Clock()
    runtime_root = (tmp_path / "runtime").resolve()
    runner = _SealedXhsPages()
    runner.failed_notes.add(1)
    scheduler = DurableSchedulerService(database, clock=clock, xhs_scan_continuation=_policy())
    assert scheduler.tick(limit=1).materialized_count == 1
    result = await _worker(database, runtime_root, runner, clock).run_once(worker_id="xhs-partial")
    assert result.status == "succeeded"
    await _qualify_delivery(database, clock)
    with database.session() as session:
        progress = session.get(XhsSubscriptionProgress, subscription_id)
        assert progress is not None
        assert (progress.partial_batch_count, progress.failed_note_count, progress.note_observation_count) == (1, 1, 1)
        assert set(session.scalars(select(Content.remote_id))) == {f"{0:024x}"}


def test_xhs_creator_authority_change_invalidates_cursor_before_next_child(database: Database) -> None:
    subscription_id = _seed(database)
    old_reference = CREATOR_REFERENCE
    new_reference = CREATOR_REFERENCE.replace("execution-0076-creator-token", "replacement-token")
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        repository = XhsDeliveryProgressRepository(session)
        progress = repository.ensure_for_materialization(
            subscription,
            upstream_sha=UPSTREAM_SHA,
            schedule_revision=subscription.schedule_revision,
            now=support.NOW,
            resume_blocked=False,
        )
        assert progress is not None
        old_fingerprint = hashlib.sha256(old_reference.encode()).hexdigest()
        repository.ensure_creator_binding(
            subscription,
            upstream_sha=UPSTREAM_SHA,
            creator_fingerprint_sha256=old_fingerprint,
            now=support.NOW,
        )
        subscription.cursor = {
            "value": XhsScanState.initial(
                UUID(subscription.account_id),
                hashlib.sha256(subscription.author.remote_id.encode()).hexdigest(),
                old_fingerprint,
                UPSTREAM_SHA,
            ).to_cursor()
        }
        checkpoint_before = subscription.checkpoint_revision
        reset = repository.ensure_creator_binding(
            subscription,
            upstream_sha=UPSTREAM_SHA,
            creator_fingerprint_sha256=hashlib.sha256(new_reference.encode()).hexdigest(),
            now=support.NOW + timedelta(seconds=1),
        )
        assert reset is True
        assert subscription.cursor is None and subscription.checkpoint_revision == checkpoint_before + 1
        assert progress.phase == "backfill" and progress.batch_count == 0
        assert progress.creator_fingerprint_sha256 == hashlib.sha256(new_reference.encode()).hexdigest()
