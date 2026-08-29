"""End-to-end CLI smoke for the network-free execution 0003 vertical slice."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

from media_sync.config import get_settings
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.models import Account, Asset, Author, Content, Subscription, SyncRun
from media_sync.interfaces.cli import app

runner = CliRunner()


def _invoke(arguments: list[str]) -> str:
    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.output
    assert "Traceback" not in result.output
    return result.output


def test_cli_database_account_subscription_and_repeatable_sync_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "state" / "workflow.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MEDIA_SYNC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MEDIA_SYNC_ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setenv("MEDIA_SYNC_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("MEDIA_SYNC_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", database_url)
    get_settings.cache_clear()

    captured_output: list[str] = []
    try:
        captured_output.append(_invoke(["db", "init"]))
        account_arguments = [
            "account",
            "add",
            "--platform",
            "bili",
            "--display-name",
            "Fixture Account",
            "--login-method",
            "cookie",
            "--credential-ref",
            "keyring:sentinel-credential",
            "--json",
        ]
        account_output = _invoke(account_arguments)
        captured_output.append(account_output)
        account_payload = json.loads(account_output)
        assert account_payload["created"] is True
        account_id = account_payload["id"]

        repeated_account_output = _invoke(account_arguments)
        captured_output.append(repeated_account_output)
        assert json.loads(repeated_account_output)["created"] is False

        account_list_output = _invoke(["account", "list", "--json"])
        captured_output.append(account_list_output)
        assert [item["id"] for item in json.loads(account_list_output)] == [account_id]
        account_text_output = _invoke(["account", "list"])
        captured_output.append(account_text_output)
        assert account_id in account_text_output

        subscription_arguments = [
            "subscription",
            "add",
            "--account-id",
            account_id,
            "--platform",
            "bili",
            "--creator-remote-id",
            "creator-001",
            "--display-name",
            "Fixture Creator",
            "--json",
        ]
        subscription_output = _invoke(subscription_arguments)
        captured_output.append(subscription_output)
        subscription_payload = json.loads(subscription_output)
        assert subscription_payload["created"] is True
        subscription_id = subscription_payload["id"]

        repeated_subscription_output = _invoke(subscription_arguments)
        captured_output.append(repeated_subscription_output)
        assert json.loads(repeated_subscription_output)["created"] is False

        conflicting_subscription_arguments = [*subscription_arguments]
        conflicting_subscription_arguments[conflicting_subscription_arguments.index("Fixture Creator")] = (
            "Mutated Creator"
        )
        conflicting_subscription_arguments.extend(["--max-items", "31"])
        conflicting_subscription = runner.invoke(app, conflicting_subscription_arguments)
        assert conflicting_subscription.exit_code == 2
        assert "subscription already exists with different scheduling" in conflicting_subscription.output
        assert "options" in conflicting_subscription.output
        assert "Traceback" not in conflicting_subscription.output
        captured_output.append(conflicting_subscription.output)

        rollback_database = Database(database_url)
        try:
            with rollback_database.session() as session:
                rolled_back_author = session.scalar(select(Author))
                rolled_back_subscription = session.scalar(select(Subscription))
                assert rolled_back_author is not None
                assert rolled_back_author.display_name == "Fixture Creator"
                assert rolled_back_subscription is not None
                assert rolled_back_subscription.max_items == 30
        finally:
            rollback_database.dispose()

        first_sync_output = _invoke(["sync", "run", "--subscription-id", subscription_id])
        second_sync_output = _invoke(["sync", "run", "--subscription-id", subscription_id, "--json"])
        captured_output.extend((first_sync_output, second_sync_output))
        assert first_sync_output.startswith("Sync run: ")
        assert "status=succeeded" in first_sync_output
        assert "processed_count=4" in first_sync_output
        assert "asset_count=4" in first_sync_output
        second_sync_payload = json.loads(second_sync_output)
        assert second_sync_payload["status"] == "succeeded"
        assert second_sync_payload["processed_count"] == 4
        assert second_sync_payload["asset_count"] == 4

        subscription_list_output = _invoke(["subscription", "list", "--json"])
        captured_output.append(subscription_list_output)
        listed_subscriptions = json.loads(subscription_list_output)
        assert [item["id"] for item in listed_subscriptions] == [subscription_id]
        assert listed_subscriptions[0]["watermarked_at"] is not None
        assert listed_subscriptions[0]["last_success_at"] is not None
        subscription_text_output = _invoke(["subscription", "list"])
        captured_output.append(subscription_text_output)
        assert subscription_id in subscription_text_output

        combined_output = "\n".join(captured_output)
        for forbidden in (
            "sentinel-credential",
            "credential_ref",
            "profile_path",
            "source_url",
            "fixture.invalid",
            '"raw"',
        ):
            assert forbidden not in combined_output

        database = Database(database_url)
        try:
            with database.session() as session:
                assert session.scalar(select(func.count()).select_from(Account)) == 1
                assert session.scalar(select(func.count()).select_from(Author)) == 1
                assert session.scalar(select(func.count()).select_from(Subscription)) == 1
                assert session.scalar(select(func.count()).select_from(Content)) == 4
                assert session.scalar(select(func.count()).select_from(Asset)) == 4
                assert session.scalar(select(func.count()).select_from(SyncRun)) == 2
        finally:
            database.dispose()
    finally:
        get_settings.cache_clear()
