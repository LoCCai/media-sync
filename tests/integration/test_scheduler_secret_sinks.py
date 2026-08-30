"""Byte-level secret-sink coverage for scheduler handler failures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    SubscriptionRepository,
)
from media_sync.scheduler.handlers import (
    SubscriptionHandlerRegistry,
    SubscriptionHandlerResult,
    SubscriptionJobContext,
)
from media_sync.scheduler.policy import RetryPolicy
from media_sync.scheduler.service import DurableSchedulerService, SubscriptionWorker

NOW = datetime(2026, 8, 30, 6, 0, tzinfo=UTC)
SENTINEL = "SENTINEL-scheduler-handler-secret-must-not-persist"


class _SecretRaisingHandler:
    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        del context
        raise RuntimeError(f"raw handler failure contains {SENTINEL}")


@pytest.mark.asyncio
async def test_raw_handler_secret_stays_out_of_scheduler_and_retained_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "scheduler.sqlite3"
    archive_root = tmp_path / "archive"
    export_root = tmp_path / "exports"
    operator_output = tmp_path / "operator-output.txt"
    archive_root.mkdir()
    export_root.mkdir()
    (archive_root / "retained-safe-marker.txt").write_text("safe archive marker\n", encoding="utf-8")
    (export_root / "retained-safe-marker.txt").write_text("safe export marker\n", encoding="utf-8")

    database = Database(f"sqlite+pysqlite:///{database_path.as_posix()}")
    database.create_schema()
    try:
        with database.session() as session:
            account = AccountRepository(session).create(
                platform="bili",
                adapter="fake",
                display_name="scheduler-secret-sink",
                login_method="cookie",
                auth_status="authenticated",
                credential_ref="env:MEDIA_SYNC_TEST_COOKIE",
            )
            author = AuthorRepository(session).upsert(
                AuthorUpsert(
                    platform="bili",
                    remote_id="scheduler-secret-author",
                    display_name="Scheduler secret fixture",
                )
            )
            subscription = SubscriptionRepository(session).create(
                account_id=account.id,
                author_id=author.id,
                interval_seconds=60,
                max_items=1,
            )

        scheduler = DurableSchedulerService(database, clock=lambda: NOW)
        tick = scheduler.tick(limit=1, retry_policy=RetryPolicy(max_attempts=1))
        result = await SubscriptionWorker(
            database,
            SubscriptionHandlerRegistry({"fake": _SecretRaisingHandler()}),
            clock=lambda: NOW,
        ).run_once(worker_id="sentinel-worker")
        jobs = scheduler.list_jobs(subscription_id=subscription.id)
        lanes = scheduler.list_lanes()

        # These are the same redaction-safe DTOs available to operator surfaces.
        print(tick)
        print(result)
        print(jobs)
        print(lanes)
        rendered_output = capsys.readouterr().out
        operator_output.write_text(rendered_output, encoding="utf-8")

        assert tick.materialized_count == 1
        assert (result.status, result.error_code) == (
            "failed_terminal",
            "unexpected_handler_failure",
        )
        assert len(jobs) == 1 and jobs[0].last_error_code == "unexpected_handler_failure"
        assert len(lanes) == 2
        assert SENTINEL not in rendered_output
        assert SENTINEL not in repr((tick, result, jobs, lanes))
    finally:
        database.dispose()

    retained_files = tuple(path for path in tmp_path.rglob("*") if path.is_file())
    assert database_path in retained_files
    assert operator_output in retained_files
    assert any(archive_root in path.parents for path in retained_files)
    assert any(export_root in path.parents for path in retained_files)
    assert all(SENTINEL.encode() not in path.read_bytes() for path in retained_files)
