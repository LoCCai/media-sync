"""CLI consumes v2 discovery/details and rejects mismatched subscription scope."""

import json
from dataclasses import replace
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from media_sync.config import get_settings
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.models import Account, Author, Subscription
from media_sync.integrations.mediacrawler.subscription_policy import MediaCrawlerSubscriptionPolicy
from media_sync.interfaces.cli import app
from tests.contract.test_bilibili_dynamic_bridge import continue_manifest, dynamic_output, dynamic_spec


@pytest.mark.parametrize("mismatched", [False, True])
def test_cli_sealed_dynamic_discovery_then_content(tmp_path, monkeypatch, mismatched):
    spec = dynamic_spec(tmp_path)
    manifest = spec.manifest
    dynamic_output(manifest)
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'cli.sqlite3').as_posix()}")
    database.create_schema()
    with database.session() as session:
        author = str(uuid4())
        session.add(
            Account(
                id=str(manifest.account_id),
                platform="bili",
                adapter="mediacrawler",
                display_name="Fixture",
                login_method=manifest.login_method.value,
            )
        )
        session.add(Author(id=author, platform="bili", remote_id="252671524", display_name="Fixture"))
        session.flush()
        session.add(
            Subscription(
                id=str(manifest.subscription_id),
                account_id=str(manifest.account_id),
                author_id=author,
                max_items=2,
                policy={
                    "mediacrawler": MediaCrawlerSubscriptionPolicy(
                        False, 2, True, bili_scope="uploads" if mismatched else "dynamics"
                    ).to_payload()
                },
            )
        )
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", str(database.engine.url))
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_RUNTIME_DIR", str(manifest.integration_root))
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_LOCK_PATH", str(manifest.lock_path))
    for name in ("STATE", "ARCHIVE", "EXPORT", "JOB"):
        monkeypatch.setenv(f"MEDIA_SYNC_{name}_DIR", str(tmp_path / name.lower()))
    get_settings.cache_clear()
    try:
        for revision in range(2):
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
                    str(revision),
                    "--json",
                ],
            )
            if mismatched:
                assert result.exit_code != 0
                with database.session() as session:
                    assert session.get(Subscription, str(manifest.subscription_id)).checkpoint_revision == 0
                break
            assert result.exit_code == 0, result.output
            payload = json.loads(result.output)
            assert payload["accepted_count"] == revision
            with database.session() as session:
                row = session.get(Subscription, str(manifest.subscription_id))
                assert row.checkpoint_revision == revision + 1
                from media_sync.integrations.mediacrawler.bilibili_multifeed import state_from_cursor

                state = state_from_cursor(row.cursor["value"])
                state = replace(state, dynamics=replace(state.dynamics, next_lane="head"))
                row.cursor = {"value": state.to_cursor()}
            if revision == 0:
                manifest = continue_manifest(manifest, state)
                dynamic_output(manifest)
    finally:
        database.dispose()
        get_settings.cache_clear()
