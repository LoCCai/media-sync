"""Legacy sealed output cannot cross a new scope, including the CLI/DB gap."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

import media_sync.interfaces.cli as cli_module
from media_sync.application.bilibili_subscription_scope import change_bilibili_scope
from media_sync.config import get_settings
from media_sync.domain import ContentKind, Platform
from media_sync.infrastructure.db import Database, MediaCrawlerIngestionService, RepositoryError
from media_sync.infrastructure.db.models import Account, Asset, Author, Content, RunEvent, Subscription, SyncRun
from media_sync.integrations.mediacrawler.bridge import RunnerManifest
from media_sync.integrations.mediacrawler.policies import inspect_output
from media_sync.integrations.mediacrawler.receipt import write_completion_receipt
from media_sync.integrations.mediacrawler.subscription_policy import MediaCrawlerSubscriptionPolicy
from tests.contract.test_bilibili_scan_bridge import _output
from tests.contract.test_mediacrawler_bridge import _bridge, _make_fake_project, _request
from tests.integration.test_bili_bounded_ingestion import _record, _run, _seed


@dataclass(frozen=True)
class _LegacyCliCase:
    database: Database
    manifest: RunnerManifest

    def switch_to_dynamics(self) -> None:
        with self.database.session() as session:
            row = session.get(Subscription, str(self.manifest.subscription_id))
            assert row is not None
            revision = row.schedule_revision
        result = change_bilibili_scope(
            self.database,
            self.manifest.subscription_id,
            scope="dynamics",
            max_items=2,
            expected_schedule_revision=revision,
        )
        assert result["changed"] is True

    def invoke(self):
        return CliRunner().invoke(
            cli_module.app,
            [
                "sync",
                "ingest",
                "--subscription-id",
                str(self.manifest.subscription_id),
                "--job-id",
                str(self.manifest.job_id),
                "--expected-revision",
                "0",
                "--json",
            ],
        )


@pytest.fixture
def legacy_cli_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_LegacyCliCase]:
    project = _make_fake_project(tmp_path / "upstream")
    request = replace(
        _request(project, tmp_path / "runtime", platform=Platform.BILI, creator="252671524"),
        author_remote_id="252671524",
        max_items=2,
        allow_full_history=False,
        bili_bounded_capture=True,
    )
    manifest = _bridge().prepare(request).manifest
    # No dynamic record can trigger a content-based policy check here. Even an
    # empty legacy source-end unit needs current policy publication authority.
    _output(manifest, empty=True)
    write_completion_receipt(manifest, inspect_output(manifest.output_root, manifest.watchdogs), known_secrets=())
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'scope-fence.sqlite3').as_posix()}")
    database.create_schema()
    with database.session() as session:
        author_id = str(uuid4())
        session.add(
            Account(
                id=str(manifest.account_id),
                platform="bili",
                adapter="mediacrawler",
                display_name="Offline scope fixture",
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
                max_items=2,
                enabled=False,
                policy={"mediacrawler": MediaCrawlerSubscriptionPolicy(False, 2, True).to_payload()},
            )
        )
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", str(database.engine.url))
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_RUNTIME_DIR", str(manifest.integration_root))
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_LOCK_PATH", str(manifest.lock_path))
    for name in ("STATE", "ARCHIVE", "EXPORT", "JOB"):
        monkeypatch.setenv(f"MEDIA_SYNC_{name}_DIR", str(tmp_path / name.lower()))
    get_settings.cache_clear()
    try:
        yield _LegacyCliCase(database, manifest)
    finally:
        get_settings.cache_clear()
        database.dispose()


def _assert_no_publication(case: _LegacyCliCase, *, expected_runs: int) -> None:
    with case.database.session() as session:
        row = session.get(Subscription, str(case.manifest.subscription_id))
        assert row is not None
        assert row.policy["mediacrawler"]["bili_scope"] == "dynamics"
        assert row.checkpoint_revision == 0 and row.cursor is None
        assert row.last_success_at is None
        assert not row.enabled
        runs = list(session.scalars(select(SyncRun)))
        assert len(runs) == expected_runs
        for run in runs:
            assert run.status == "failed_retryable"
            assert run.discovered_count == run.updated_count == run.asset_count == 0
            assert run.checkpoint_revision_after is None and run.cursor_after is None
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(RunEvent).where(RunEvent.to_status == "succeeded")) == 0


def test_cli_rejects_empty_v1_artifact_after_legitimate_scope_change(legacy_cli_case: _LegacyCliCase) -> None:
    legacy_cli_case.switch_to_dynamics()
    result = legacy_cli_case.invoke()
    assert result.exit_code != 0, result.output
    assert "output validation was rejected" in result.output
    _assert_no_publication(legacy_cli_case, expected_runs=0)


def test_cli_rechecks_legacy_scope_inside_publication_after_validation_gap(
    legacy_cli_case: _LegacyCliCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = cli_module.load_normalized_output
    changed = False

    def load_then_change(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        # Current policy has already passed CLI validation, but no Run exists
        # yet. The public paused/idle scope-edit service legitimately succeeds.
        legacy_cli_case.switch_to_dynamics()
        changed = True
        return result

    monkeypatch.setattr(cli_module, "load_normalized_output", load_then_change)
    result = legacy_cli_case.invoke()
    assert changed
    assert result.exit_code != 0, result.output
    assert "ingestion failed safely" in result.output
    _assert_no_publication(legacy_cli_case, expected_runs=1)


def test_exact_successful_dynamic_run_replay_survives_narrower_scope_and_limit(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'scope-replay.sqlite3').as_posix()}")
    database.create_schema()
    try:
        identifier = _seed(database, max_items=2)
        with database.session() as session:
            row = session.get(Subscription, identifier)
            assert row is not None
            row.policy = {
                "mediacrawler": MediaCrawlerSubscriptionPolicy(False, 2, True, bili_scope="dynamics").to_payload()
            }
        run_id = _run(database, identifier)
        video = _record("1234")
        dynamic = replace(
            video,
            content=replace(video.content, remote_type="dynamic", kind=ContentKind.DYNAMIC),
            assets=(),
        )
        service = MediaCrawlerIngestionService(database)
        options = dict(
            subscription_id=identifier,
            run_id=run_id,
            expected_revision=0,
            input_cursor=None,
            next_cursor="private-completed-unit",
            bili_scope="dynamics",
        )
        published = service.ingest_bili_bounded((dynamic, video), **options)
        assert published.discovered_count == 2 and published.committed_batches == 1
        with database.session() as session:
            row = session.get(Subscription, identifier)
            assert row is not None
            row.enabled = False
            revision = row.schedule_revision
        change_bilibili_scope(
            database,
            UUID(identifier),
            scope="uploads",
            max_items=1,
            expected_schedule_revision=revision,
        )
        replay = service.ingest_bili_bounded((dynamic, video), **options)
        assert replay.committed_batches == replay.accepted_count == replay.discovered_count == 0
        assert replay.skipped_count == 2 and replay.checkpoint_revision == 1
        with pytest.raises(RepositoryError, match="completed Bili unit"):
            service.ingest_bili_bounded((dynamic, video), **{**options, "next_cursor": "different-private-unit"})
        with database.session() as session:
            row = session.get(Subscription, identifier)
            run = session.get(SyncRun, run_id)
            assert row is not None and run is not None
            assert row.policy["mediacrawler"]["bili_scope"] == "uploads" and row.max_items == 1
            assert row.cursor == {"value": "private-completed-unit"} and row.checkpoint_revision == 1
            assert run.status == "succeeded" and run.discovered_count == 2 and run.asset_count == 1
            assert session.scalar(select(func.count()).select_from(Content)) == 2
            assert session.scalar(select(func.count()).select_from(Asset)) == 1
            assert (
                session.scalar(select(func.count()).select_from(RunEvent).where(RunEvent.to_status == "succeeded")) == 1
            )
    finally:
        database.dispose()
