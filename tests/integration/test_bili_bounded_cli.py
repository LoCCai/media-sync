"""The real CLI cannot bypass bounded coverage or promote the old watermark."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from media_sync.config import get_settings
from media_sync.domain import RunStatus
from media_sync.infrastructure.db import (
    ContentOwnershipConflictError,
    Database,
    MediaCrawlerIngestionService,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import Account, AssetRefreshSource, Author, Content, Subscription, SyncRun
from media_sync.integrations.mediacrawler.policies import inspect_output
from media_sync.integrations.mediacrawler.receipt import write_completion_receipt
from media_sync.interfaces.cli import _mark_ingest_failure, app
from tests.contract.test_bilibili_scan_bridge import _output, _spec
from tests.integration.test_content_ownership_ingestion import _existing_snapshot, _seed_existing


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("publication", ["normal", "lost_ack", "no_commit", "ownership_conflict", "late_conflict"])
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
    original_content = None
    if publication == "ownership_conflict" and not empty:
        _seed_existing(database, "1234")
        original_content = _existing_snapshot(database, "1234")
    if publication != "normal":
        original = MediaCrawlerIngestionService.ingest_bili_bounded

        def publish(self, *args, **kwargs):
            if publication == "ownership_conflict":
                try:
                    return original(self, *args, **kwargs)
                except ContentOwnershipConflictError as error:
                    error.args = ("private-conflict-must-not-leak",)
                    error.code = "private_conflict_code_must_not_leak"
                    raise
            if publication in {"lost_ack", "late_conflict"}:
                original(self, *args, **kwargs)
                if publication == "late_conflict":
                    error = ContentOwnershipConflictError()
                    error.args = ("private-late-failure-must-not-leak",)
                    raise error
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
        assert "private-conflict-must-not-leak" not in result.output
        assert "private_conflict_code_must_not_leak" not in result.output
        if original_content is not None:
            assert result.exit_code == 1, result.output
            payload = json.loads(result.output)
            assert payload == {
                "run_id": payload["run_id"],
                "status": "failed_terminal",
                "error_code": "content_ownership_conflict",
                "retryable": False,
            }
            assert _existing_snapshot(database, "1234") == original_content
            with database.session() as session:
                subscription = session.get(Subscription, str(manifest.subscription_id))
                run = session.get(SyncRun, payload["run_id"])
                assert subscription.checkpoint_revision == 0 and subscription.cursor is None
                assert run.status == "failed_terminal" and run.error_code == "content_ownership_conflict"
                assert run.error_message is None and run.discovered_count == run.asset_count == 0
                assert session.scalar(select(func.count()).select_from(Content)) == 1
                assert session.scalar(select(func.count()).select_from(AssetRefreshSource)) == 1
            return
        if publication == "no_commit":
            assert result.exit_code != 0
            with database.session() as session:
                subscription = session.get(Subscription, str(manifest.subscription_id))
                assert subscription.checkpoint_revision == 0 and subscription.cursor is None
                assert not list(session.scalars(select(SyncRun).where(SyncRun.status == "succeeded")))
            return
        assert result.exit_code == 0, result.output
        assert "private-late-failure-must-not-leak" not in result.output
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


def test_legacy_cli_conflict_reports_terminal_without_erasing_earlier_committed_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _spec(tmp_path)
    manifest = replace(spec.manifest, bili_scan=None, max_items=30, allow_full_history=True)
    spec.paths.manifest_path.write_text(
        json.dumps(manifest.as_payload(), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (manifest.output_root / "contents.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "video_id": remote_id,
                    "create_time": 1767225600 + index,
                    "title": "Legacy synthetic upload",
                }
            )
            + "\n"
            for index, remote_id in enumerate(("100", "200"))
        ),
        encoding="utf-8",
    )
    write_completion_receipt(manifest, inspect_output(manifest.output_root, manifest.watchdogs), known_secrets=())
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'legacy-cli.sqlite3').as_posix()}")
    database.create_schema()
    original_run_id = _seed_existing(database, "200")
    original_content = _existing_snapshot(database, "200")
    with database.session() as session:
        author_id = str(uuid4())
        session.add(
            Account(
                id=str(manifest.account_id),
                platform="bili",
                adapter="mediacrawler",
                display_name="Legacy CLI fixture",
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
                max_items=30,
            )
        )
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", str(database.engine.url))
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_RUNTIME_DIR", str(manifest.integration_root))
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_LOCK_PATH", str(manifest.lock_path))
    for name in ("STATE", "ARCHIVE", "EXPORT", "JOB"):
        monkeypatch.setenv(f"MEDIA_SYNC_{name}_DIR", str(tmp_path / name.lower()))
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(
            app,
            [
                "sync",
                "ingest",
                "--subscription-id",
                str(manifest.subscription_id),
                "--job-id",
                str(manifest.job_id),
                "--expected-revision",
                "0",
                "--batch-size",
                "1",
                "--json",
            ],
        )
        assert result.exit_code == 1, result.output
        payload = json.loads(result.output)
        assert payload["status"] == "failed_terminal" and payload["error_code"] == "content_ownership_conflict"
        assert payload["retryable"] is False
        assert _existing_snapshot(database, "200") == original_content
        with database.session() as session:
            run = session.get(SyncRun, payload["run_id"])
            subscription = session.get(Subscription, str(manifest.subscription_id))
            assert run.status == "failed_terminal" and run.error_code == "content_ownership_conflict"
            assert run.error_message is None and run.discovered_count == run.asset_count == 1
            assert run.checkpoint_revision_after == subscription.checkpoint_revision == 1
            assert subscription.last_success_at is None
            assert set(session.scalars(select(Content.remote_id))) == {"100", "200"}
            assert set(session.scalars(select(AssetRefreshSource.last_run_id))) == {original_run_id, run.id}
    finally:
        get_settings.cache_clear()
        database.dispose()


@pytest.mark.parametrize(
    "failure",
    ["write_failed", "ack_lost", "read_failed", "read_unexpected", "publication_read_failed", "wrong_code", "normal"],
)
def test_cli_conflict_reports_only_freshly_confirmed_failure_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    manifest = _spec(tmp_path).manifest
    _output(manifest)
    write_completion_receipt(manifest, inspect_output(manifest.output_root, manifest.watchdogs), known_secrets=())
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'failure-truth.sqlite3').as_posix()}")
    database.create_schema()
    _seed_existing(database, "1234")
    original_content = _existing_snapshot(database, "1234")
    with database.session() as session:
        author_id = str(uuid4())
        session.add(
            Account(
                id=str(manifest.account_id),
                platform="bili",
                adapter="mediacrawler",
                display_name="Failure truth fixture",
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
            )
        )
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", str(database.engine.url))
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_RUNTIME_DIR", str(manifest.integration_root))
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_LOCK_PATH", str(manifest.lock_path))
    for name in ("STATE", "ARCHIVE", "EXPORT", "JOB"):
        monkeypatch.setenv(f"MEDIA_SYNC_{name}_DIR", str(tmp_path / name.lower()))
    get_settings.cache_clear()
    original_set_status = SyncRunRepository.set_status
    original_require = SyncRunRepository.require
    original_ingest = MediaCrawlerIngestionService.ingest_bili_bounded
    write_attempted = False
    read_after_write = 0
    conflict_observed = False

    def ingest(self, *args, **kwargs):
        nonlocal conflict_observed
        try:
            return original_ingest(self, *args, **kwargs)
        except ContentOwnershipConflictError:
            conflict_observed = True
            raise

    def transition(self, run_id, status, **kwargs):
        nonlocal write_attempted
        if status != "failed_terminal":
            return original_set_status(self, run_id, status, **kwargs)
        write_attempted = True
        if failure == "write_failed":
            raise SQLAlchemyError("private-write-error-must-not-leak")
        if failure == "wrong_code":
            kwargs["error_code"] = "private_stored_code_must_not_leak"
        run = original_set_status(self, run_id, status, **kwargs)
        if failure == "ack_lost":
            self.session.commit()
            raise SQLAlchemyError("private-commit-ack-error-must-not-leak")
        return run

    def require(self, run_id):
        nonlocal read_after_write
        if failure == "publication_read_failed" and conflict_observed:
            raise SQLAlchemyError("private-publication-read-error-must-not-leak")
        if write_attempted:
            read_after_write += 1
            if failure == "read_failed":
                raise SQLAlchemyError("private-read-error-must-not-leak")
            if failure == "read_unexpected":
                raise RuntimeError("private-unexpected-read-error-must-not-leak")
        return original_require(self, run_id)

    monkeypatch.setattr(SyncRunRepository, "set_status", transition)
    monkeypatch.setattr(SyncRunRepository, "require", require)
    monkeypatch.setattr(MediaCrawlerIngestionService, "ingest_bili_bounded", ingest)
    try:
        result = CliRunner().invoke(
            app,
            [
                "sync",
                "ingest",
                "--subscription-id",
                str(manifest.subscription_id),
                "--job-id",
                str(manifest.job_id),
                "--expected-revision",
                "0",
                "--json",
            ],
        )
        assert result.exit_code == 1, result.output
        payload = json.loads(result.output)
        with database.session() as session:
            run = session.get(SyncRun, payload["run_id"])
            assert run is not None
            assert run.status == (
                "ingesting" if failure in {"write_failed", "publication_read_failed"} else "failed_terminal"
            )
            assert run.error_message is None
            assert session.get(Subscription, str(manifest.subscription_id)).checkpoint_revision == 0
        if failure not in {"ack_lost", "normal"}:
            assert payload["status"] == "unknown"
            assert payload["error_code"] == "ingestion_state_unconfirmed"
            assert payload["observed_error_code"] == "content_ownership_conflict"
            assert payload["retryable"] is None
        else:
            assert payload["status"] == "failed_terminal"
            assert payload["error_code"] == "content_ownership_conflict"
            assert payload["retryable"] is False
        if failure == "publication_read_failed":
            assert not write_attempted
        else:
            assert read_after_write >= 1
        assert "private-" not in result.output
        assert "private_stored_code" not in result.output
        assert _existing_snapshot(database, "1234") == original_content
    finally:
        get_settings.cache_clear()
        database.dispose()


def test_failed_transition_confirmation_does_not_overwrite_an_already_successful_run(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'successful-run.sqlite3').as_posix()}")
    database.create_schema()
    try:
        run_id = _seed_existing(database, "1234")
        content = _existing_snapshot(database, "1234")
        assert not _mark_ingest_failure(
            database,
            run_id,
            "content_ownership_conflict",
            status=RunStatus.FAILED_TERMINAL,
        )
        with database.session() as session:
            run = session.get(SyncRun, run_id)
            assert run.status == "succeeded" and run.error_code is None and run.error_message is None
        assert _existing_snapshot(database, "1234") == content
    finally:
        database.dispose()
