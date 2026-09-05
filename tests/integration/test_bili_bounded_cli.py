"""The real CLI cannot bypass bounded coverage or promote the old watermark."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from media_sync.config import get_settings
from media_sync.infrastructure.db import Database, MediaCrawlerIngestionService
from media_sync.infrastructure.db.models import Account, Author, Subscription, SyncRun
from media_sync.integrations.mediacrawler.policies import inspect_output
from media_sync.integrations.mediacrawler.receipt import write_completion_receipt
from media_sync.interfaces.cli import app
from tests.contract.test_bilibili_scan_bridge import _output, _spec


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("publication", ["normal", "lost_ack", "no_commit"])
def test_real_cli_ingests_one_sealed_unit_and_rejects_consumed_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, empty: bool, publication: str
) -> None:
    spec = _spec(tmp_path)
    manifest = spec.manifest
    coverage = _output(manifest, empty=empty)
    write_completion_receipt(manifest, inspect_output(manifest.output_root, manifest.watchdogs), known_secrets=())
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'cli.sqlite3').as_posix()}")
    database.create_schema()
    watermark = datetime(2026, 9, 6, tzinfo=UTC)
    with database.session() as session:
        author_id = str(uuid4())
        session.add(
            Account(
                id=str(manifest.account_id),
                platform="bili",
                adapter="mediacrawler",
                display_name="CLI fixture",
                login_method=manifest.login_method.value,
            )
        )
        session.add(Author(id=author_id, platform="bili", remote_id="252671524", display_name="Fixture"))
        session.flush()
        session.add(
            Subscription(
                id=str(manifest.subscription_id),
                account_id=str(manifest.account_id),
                author_id=author_id,
                max_items=1,
                watermarked_at=watermark,
                watermark_remote_ids=["legacy"],
            )
        )
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", str(database.engine.url))
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_RUNTIME_DIR", str(manifest.integration_root))
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_LOCK_PATH", str(manifest.lock_path))
    for name in ("STATE", "ARCHIVE", "EXPORT", "JOB"):
        monkeypatch.setenv(f"MEDIA_SYNC_{name}_DIR", str(tmp_path / name.lower()))
    get_settings.cache_clear()
    if publication != "normal":
        original = MediaCrawlerIngestionService.ingest_bili_bounded

        def publish(self, *args, **kwargs):
            if publication == "lost_ack":
                original(self, *args, **kwargs)
                raise OSError("synthetic commit acknowledgement loss")
            return None

        monkeypatch.setattr(MediaCrawlerIngestionService, "ingest_bili_bounded", publish)
    command = [
        "sync",
        "ingest",
        "--subscription-id",
        str(manifest.subscription_id),
        "--job-id",
        str(manifest.job_id),
        "--expected-revision",
        "0",
        "--json",
    ]
    try:
        result = CliRunner().invoke(app, command)
        if publication == "no_commit":
            assert result.exit_code != 0
            with database.session() as session:
                subscription = session.get(Subscription, str(manifest.subscription_id))
                assert subscription.checkpoint_revision == 0 and subscription.cursor is None
                assert not list(session.scalars(select(SyncRun).where(SyncRun.status == "succeeded")))
            return
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["status"] == "succeeded"
        assert payload["bounded_capture"]["history_complete"] is False
        assert payload["accepted_count"] == (0 if empty else 1)
        assert "bili-scan-v1:" not in result.output
        command[-2] = "1"
        rejected = CliRunner().invoke(app, command)
        assert rejected.exit_code != 0
        with database.session() as session:
            subscription = session.get(Subscription, str(manifest.subscription_id))
            assert subscription is not None
            assert subscription.cursor == {"value": coverage.next_state.to_cursor()}
            assert subscription.checkpoint_revision == 1 and subscription.watermarked_at == watermark
            assert len(list(session.scalars(select(SyncRun).where(SyncRun.status == "succeeded")))) == 1
    finally:
        get_settings.cache_clear()
        database.dispose()
