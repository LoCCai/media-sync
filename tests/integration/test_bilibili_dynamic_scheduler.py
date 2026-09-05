"""Real scheduler/manifest/seal/normalizer/atomic DB loop; synthetic dynamic source."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from media_sync.infrastructure.db import MediaCrawlerIngestionService
from media_sync.infrastructure.db.models import Content, Subscription, SyncRun
from media_sync.integrations.mediacrawler.bridge import RunnerManifest
from media_sync.integrations.mediacrawler.runner import MediaCrawlerProcessResult, MediaCrawlerProcessStatus
from media_sync.scheduler.service import DurableSchedulerService
from tests.contract.test_bilibili_dynamic_bridge import dynamic_output
from tests.integration import test_mediacrawler_scheduler_handler as support
from tests.integration.test_bili_bounded_scheduler import _LoseCommitAcknowledgement, _seed, _worker
from tests.integration.test_bili_bounded_scheduler import database as _database

database = _database


class DynamicRunner:
    def __init__(self, *, tamper=False):
        self.manifests = []
        self.coverages = []
        self.tamper = tamper

    def run(self, spec, cancellation=None):
        manifest = RunnerManifest.load(spec.paths.manifest_path)
        self.manifests.append(manifest)
        self.coverages.append(dynamic_output(manifest, tamper="body" if self.tamper else None))
        return MediaCrawlerProcessResult(MediaCrawlerProcessStatus.SUCCEEDED, "Synthetic dynamic unit")


@pytest.mark.parametrize("lost_ack", [False, True])
@pytest.mark.asyncio
async def test_dynamic_discovery_and_pending_resume_across_worker_restarts(database, tmp_path, lost_ack):
    root = (tmp_path / "runtime").resolve()
    identifier = _seed(database, root)
    with database.session() as session:
        row = session.get(Subscription, identifier)
        row.max_items = 2
        row.policy = {"mediacrawler": {**row.policy["mediacrawler"], "schema_version": 2, "bili_scope": "dynamics"}}
    clock = support._Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    runner = DynamicRunner()
    for number in range(4):
        assert scheduler.tick(limit=1).materialized_count == 1
        worker = _worker(
            database,
            root,
            runner,
            clock,
            ingestion_factory=_LoseCommitAcknowledgement if lost_ack else MediaCrawlerIngestionService,
        )
        result = await worker.run_once(worker_id="dynamic-offline")
        assert result.status == "succeeded"
        with database.session() as session:
            row = session.get(Subscription, identifier)
            assert row.checkpoint_revision == number + 1
            assert row.watermark_remote_ids == ["legacy-does-not-prove-coverage"]
            assert session.get(SyncRun, str(runner.manifests[-1].sync_run_id)).status == "succeeded"
            clock.value = row.next_run_at + timedelta(seconds=1)
        assert not runner.manifests[-1].job_root.exists()
        assert list(runner.manifests[-1].account_root.rglob("*.json"))
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Content)) == 1
        assert session.scalar(select(Content.remote_type)) == "dynamic"
    assert [row.stop_reason for row in runner.coverages] == [
        "snapshot_saved",
        "snapshot_saved",
        "source_end",
        "source_end",
    ]
