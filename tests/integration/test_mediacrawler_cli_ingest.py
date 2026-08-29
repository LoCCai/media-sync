"""Real CLI ingestion path from bounded MediaCrawler JSONL into SQLite."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

import media_sync.interfaces.cli as cli_module
from media_sync.config import get_settings
from media_sync.domain import LoginMethod, Platform
from media_sync.infrastructure.db import Database, IngestionMode
from media_sync.infrastructure.db.models import Account, Asset, Author, Content, Subscription, SyncRun
from media_sync.integrations.mediacrawler.bridge import MediaCrawlerRunMode, RunnerManifest
from media_sync.integrations.mediacrawler.policies import WatchdogLimits, build_run_paths, inspect_output
from media_sync.integrations.mediacrawler.receipt import (
    CompletionReceiptError,
    CompletionReceiptErrorCode,
    completion_receipt_path,
    write_completion_receipt,
)
from media_sync.interfaces.cli import app
from media_sync.security import REDACTED, SecretValue

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
XHS_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "mediacrawler" / "xhs" / "contents.v1.jsonl"
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
COOKIE_SENTINEL = "cookie-original-must-never-reach-sqlite"
CREATOR_REFERENCE_SENTINEL = "creator-reference-original-must-never-reach-sqlite"
CREATOR_REFERENCE_SECRET = (
    f"https://www.xiaohongshu.com/user/profile/stable-xhs-creator?upsig={CREATOR_REFERENCE_SENTINEL}"
)

runner = CliRunner()


def _invoke(arguments: list[str]) -> dict[str, object]:
    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.output
    assert "Traceback" not in result.output
    payload = json.loads(result.output)
    assert isinstance(payload, dict)
    return payload


def _write_secret_bearing_fixture(output_path: Path) -> None:
    records: list[dict[str, object]] = []
    for line in XHS_FIXTURE.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        assert isinstance(record, dict)
        record["cookie"] = COOKIE_SENTINEL
        record["creator_reference_secret"] = CREATOR_REFERENCE_SENTINEL
        records.append(record)
    output_path.write_text(
        "".join(f"{json.dumps(record, ensure_ascii=False, separators=(',', ':'))}\n" for record in records),
        encoding="utf-8",
        newline="\n",
    )


def _write_plain_secret_echo_fixture(output_path: Path) -> None:
    record = json.loads(XHS_FIXTURE.read_text(encoding="utf-8").splitlines()[0])
    assert isinstance(record, dict)
    record["title"] = f"ordinary title echoed {COOKIE_SENTINEL}"
    record["ordinary_note"] = f"ordinary raw echoed {CREATOR_REFERENCE_SECRET}"
    output_path.write_text(
        f"{json.dumps(record, ensure_ascii=False, separators=(',', ':'))}\n",
        encoding="utf-8",
        newline="\n",
    )


def test_sync_ingest_validates_normalizes_batches_and_replays_without_secret_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / "state"
    database_path = state_dir / "cli-ingest.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    runtime_root = (tmp_path / "runtime" / "mediacrawler").resolve()
    lock_path = (tmp_path / "upstreams.lock.json").resolve()
    monkeypatch.setenv("MEDIA_SYNC_STATE_DIR", str(state_dir))
    monkeypatch.setenv("MEDIA_SYNC_ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setenv("MEDIA_SYNC_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("MEDIA_SYNC_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", database_url)
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setenv("MEDIA_SYNC_MEDIACRAWLER_LOCK_PATH", str(lock_path))
    monkeypatch.setenv("MEDIA_SYNC_TEST_COOKIE", COOKIE_SENTINEL)
    monkeypatch.setenv("MEDIA_SYNC_TEST_CREATOR_REFERENCE", CREATOR_REFERENCE_SECRET)
    get_settings.cache_clear()

    try:
        initialized = runner.invoke(app, ["db", "init"])
        assert initialized.exit_code == 0, initialized.output

        account_payload = _invoke(
            [
                "account",
                "add",
                "--platform",
                Platform.XHS.value,
                "--display-name",
                "XHS Cookie Fixture Account",
                "--adapter",
                "mediacrawler",
                "--login-method",
                LoginMethod.COOKIE.value,
                "--credential-ref",
                "env:MEDIA_SYNC_TEST_COOKIE",
                "--json",
            ]
        )
        account_id = UUID(str(account_payload["id"]))
        assert account_payload["adapter"] == "mediacrawler"
        assert account_payload["login_method"] == LoginMethod.COOKIE.value

        subscription_payload = _invoke(
            [
                "subscription",
                "add",
                "--account-id",
                str(account_id),
                "--platform",
                Platform.XHS.value,
                "--creator-remote-id",
                "stable-xhs-creator",
                "--display-name",
                "XHS Fixture Creator",
                "--creator-reference-ref",
                "env:MEDIA_SYNC_TEST_CREATOR_REFERENCE",
                "--json",
            ]
        )
        subscription_id = UUID(str(subscription_payload["id"]))

        first_job_id = uuid4()
        second_job_id = uuid4()
        quarantine_job_id = uuid4()
        secret_echo_job_id = uuid4()
        first_paths = build_run_paths(runtime_root, Platform.XHS, account_id, first_job_id)
        second_paths = build_run_paths(runtime_root, Platform.XHS, account_id, second_job_id)
        for paths in (first_paths, second_paths):
            paths.profile_root.mkdir(parents=True, exist_ok=True)
            paths.output_root.mkdir(parents=True)
            _write_secret_bearing_fixture(paths.output_root / "contents.v1.jsonl")

        def manifest_for(*, job_id: UUID, checkpoint_revision_before: int) -> RunnerManifest:
            paths = build_run_paths(runtime_root, Platform.XHS, account_id, job_id)
            return RunnerManifest(
                checkout_root=(tmp_path / "external" / "MediaCrawler").resolve(),
                lock_path=lock_path,
                python_executable=(tmp_path / "external" / "python.exe").resolve(),
                integration_root=runtime_root,
                account_id=account_id,
                subscription_id=subscription_id,
                job_id=job_id,
                checkpoint_revision_before=checkpoint_revision_before,
                account_root=paths.account_root,
                profile_root=paths.profile_root,
                job_root=paths.job_root,
                output_root=paths.output_root,
                upstream_sha=UPSTREAM_SHA,
                platform=Platform.XHS,
                login_method=LoginMethod.COOKIE,
                intended_mode=MediaCrawlerRunMode.FORWARD,
                author_remote_id_fingerprint_sha256=hashlib.sha256(b"stable-xhs-creator").hexdigest(),
                creator_fingerprint_sha256=hashlib.sha256(CREATOR_REFERENCE_SECRET.encode("utf-8")).hexdigest(),
                watchdogs=WatchdogLimits(
                    max_seconds=30,
                    max_output_bytes=1_000_000,
                    max_output_items=10,
                    max_output_files=4,
                    max_line_bytes=100_000,
                ),
            )

        first_manifest = manifest_for(job_id=first_job_id, checkpoint_revision_before=0)
        second_manifest = manifest_for(job_id=second_job_id, checkpoint_revision_before=2)
        quarantine_paths = build_run_paths(runtime_root, Platform.XHS, account_id, quarantine_job_id)
        quarantine_paths.profile_root.mkdir(parents=True, exist_ok=True)
        quarantine_paths.output_root.mkdir(parents=True)
        (quarantine_paths.output_root / "unknown.v1.jsonl").write_text("{}\n", encoding="utf-8")
        quarantine_manifest = manifest_for(job_id=quarantine_job_id, checkpoint_revision_before=0)
        secret_echo_paths = build_run_paths(runtime_root, Platform.XHS, account_id, secret_echo_job_id)
        secret_echo_paths.profile_root.mkdir(parents=True, exist_ok=True)
        secret_echo_paths.output_root.mkdir(parents=True)
        _write_plain_secret_echo_fixture(secret_echo_paths.output_root / "contents.v1.jsonl")
        secret_echo_manifest = manifest_for(job_id=secret_echo_job_id, checkpoint_revision_before=0)
        for paths, manifest in (
            (first_paths, first_manifest),
            (second_paths, second_manifest),
            (quarantine_paths, quarantine_manifest),
            (secret_echo_paths, secret_echo_manifest),
        ):
            paths.manifest_path.write_text(
                json.dumps(manifest.as_payload(), ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
                newline="\n",
            )
        for paths, manifest in (
            (first_paths, first_manifest),
            (second_paths, second_manifest),
            (quarantine_paths, quarantine_manifest),
        ):
            write_completion_receipt(
                manifest,
                inspect_output(paths.output_root, manifest.watchdogs),
                known_secrets=(),
            )
        with pytest.raises(CompletionReceiptError) as secret_disclosure:
            write_completion_receipt(
                secret_echo_manifest,
                inspect_output(secret_echo_paths.output_root, secret_echo_manifest.watchdogs),
                known_secrets=(SecretValue(COOKIE_SENTINEL), CREATOR_REFERENCE_SECRET),
            )
        assert secret_disclosure.value.code is CompletionReceiptErrorCode.KNOWN_SECRET_DISCLOSURE
        assert COOKIE_SENTINEL not in str(secret_disclosure.value)
        assert CREATOR_REFERENCE_SENTINEL not in str(secret_disclosure.value)
        assert not completion_receipt_path(secret_echo_manifest.job_root).exists()
        manifests_by_path = {
            first_paths.manifest_path: first_manifest,
            second_paths.manifest_path: second_manifest,
            quarantine_paths.manifest_path: quarantine_manifest,
            secret_echo_paths.manifest_path: secret_echo_manifest,
        }
        loaded_paths: list[Path] = []
        verified_manifests: list[RunnerManifest] = []

        def load_manifest(manifest_path: Path) -> RunnerManifest:
            resolved_path = manifest_path.resolve()
            loaded_paths.append(resolved_path)
            return manifests_by_path[resolved_path]

        def verify_checkout(candidate: RunnerManifest) -> None:
            verified_manifests.append(candidate)

        # Only external-checkout boundaries are replaced. Output inspection,
        # JSONL reading, normalization and database ingestion remain real.
        monkeypatch.setattr(cli_module.RunnerManifest, "load", staticmethod(load_manifest))
        monkeypatch.setattr(cli_module, "verify_manifest_checkout", verify_checkout)

        def ingest_arguments(job_id: UUID, expected_revision: int) -> list[str]:
            return [
                "sync",
                "ingest",
                "--subscription-id",
                str(subscription_id),
                "--job-id",
                str(job_id),
                "--expected-revision",
                str(expected_revision),
                "--mode",
                IngestionMode.FORWARD.value,
                "--batch-size",
                "1",
                "--json",
            ]

        manifests_by_path[first_paths.manifest_path] = replace(
            first_manifest,
            author_remote_id_fingerprint_sha256=hashlib.sha256(b"different-author").hexdigest(),
        )
        rejected = runner.invoke(app, ingest_arguments(first_job_id, 0))
        assert rejected.exit_code == 2
        assert "Invalid value: MediaCrawler output validation was rejected" in rejected.output
        assert COOKIE_SENTINEL not in rejected.output
        assert CREATOR_REFERENCE_SENTINEL not in rejected.output
        rejection_database = Database(database_url)
        try:
            with rejection_database.session() as session:
                subscription = session.get(Subscription, str(subscription_id))
                assert subscription is not None
                assert subscription.checkpoint_revision == 0
                assert session.scalar(select(func.count()).select_from(SyncRun)) == 0
        finally:
            rejection_database.dispose()

        manifests_by_path[first_paths.manifest_path] = replace(
            first_manifest,
            creator_fingerprint_sha256=hashlib.sha256(b"different-creator-reference").hexdigest(),
        )
        rejected = runner.invoke(app, ingest_arguments(first_job_id, 0))
        assert rejected.exit_code == 2
        assert "Invalid value: MediaCrawler output validation was rejected" in rejected.output
        assert COOKIE_SENTINEL not in rejected.output
        assert CREATOR_REFERENCE_SENTINEL not in rejected.output
        rejection_database = Database(database_url)
        try:
            with rejection_database.session() as session:
                subscription = session.get(Subscription, str(subscription_id))
                assert subscription is not None
                assert subscription.checkpoint_revision == 0
                assert session.scalar(select(func.count()).select_from(SyncRun)) == 0
        finally:
            rejection_database.dispose()

        manifests_by_path[first_paths.manifest_path] = first_manifest
        quarantined = runner.invoke(app, ingest_arguments(quarantine_job_id, 0))
        assert quarantined.exit_code == 2
        assert "Invalid value: MediaCrawler output validation was rejected" in quarantined.output
        quarantine_database = Database(database_url)
        try:
            with quarantine_database.session() as session:
                subscription = session.get(Subscription, str(subscription_id))
                assert subscription is not None
                assert subscription.checkpoint_revision == 0
                assert session.scalar(select(func.count()).select_from(SyncRun)) == 0
        finally:
            quarantine_database.dispose()

        secret_echo_rejected = runner.invoke(app, ingest_arguments(secret_echo_job_id, 0))
        assert secret_echo_rejected.exit_code == 2
        assert "Invalid value: MediaCrawler output validation was rejected" in secret_echo_rejected.output
        assert COOKIE_SENTINEL not in secret_echo_rejected.output
        assert CREATOR_REFERENCE_SENTINEL not in secret_echo_rejected.output
        secret_echo_database = Database(database_url)
        try:
            with secret_echo_database.session() as session:
                subscription = session.get(Subscription, str(subscription_id))
                assert subscription is not None
                assert subscription.checkpoint_revision == 0
                assert session.scalar(select(func.count()).select_from(SyncRun)) == 0
        finally:
            secret_echo_database.dispose()
        rejected_sqlite_bytes = b"".join(
            path.read_bytes() for path in sorted(database_path.parent.glob(f"{database_path.name}*")) if path.is_file()
        )
        assert COOKIE_SENTINEL.encode() not in rejected_sqlite_bytes
        assert CREATOR_REFERENCE_SENTINEL.encode() not in rejected_sqlite_bytes

        first = _invoke(ingest_arguments(first_job_id, 0))
        second = _invoke(ingest_arguments(second_job_id, 2))

        assert first == {
            "run_id": first["run_id"],
            "subscription_id": str(subscription_id),
            "status": "succeeded",
            "mode": "forward",
            "input_count": 2,
            "accepted_count": 2,
            "skipped_count": 0,
            "discovered_count": 2,
            "asset_count": 4,
            "quarantined_count": 0,
            "truncated_tail": False,
            "committed_batches": 2,
            "checkpoint_revision": 2,
        }
        assert second == {
            "run_id": second["run_id"],
            "subscription_id": str(subscription_id),
            "status": "succeeded",
            "mode": "forward",
            "input_count": 2,
            "accepted_count": 0,
            "skipped_count": 2,
            "discovered_count": 0,
            "asset_count": 0,
            "quarantined_count": 0,
            "truncated_tail": False,
            "committed_batches": 1,
            "checkpoint_revision": 3,
        }
        assert loaded_paths == [
            first_paths.manifest_path,
            first_paths.manifest_path,
            quarantine_paths.manifest_path,
            secret_echo_paths.manifest_path,
            first_paths.manifest_path,
            second_paths.manifest_path,
        ]
        assert verified_manifests == [
            quarantine_manifest,
            secret_echo_manifest,
            first_manifest,
            second_manifest,
        ]

        database = Database(database_url)
        try:
            with database.session() as session:
                account = session.get(Account, str(account_id))
                subscription = session.get(Subscription, str(subscription_id))
                first_run = session.get(SyncRun, str(first["run_id"]))
                second_run = session.get(SyncRun, str(second["run_id"]))
                contents = list(session.scalars(select(Content).order_by(Content.remote_id)))
                assert account is not None
                assert subscription is not None
                assert first_run is not None
                assert second_run is not None
                assert account.adapter == "mediacrawler"
                assert account.login_method == LoginMethod.COOKIE.value
                assert session.scalar(select(func.count()).select_from(Author)) == 1
                assert session.scalar(select(func.count()).select_from(Content)) == 2
                assert session.scalar(select(func.count()).select_from(Asset)) == 4
                assert session.scalar(select(func.count()).select_from(SyncRun)) == 2
                assert subscription.checkpoint_revision == 3
                assert subscription.watermark_remote_ids == ["xhs-image-002", "xhs-mixed-001"]
                assert first_run.status == second_run.status == "succeeded"
                assert first_run.checkpoint_revision_before == 0
                assert first_run.checkpoint_revision_after == 2
                assert first_run.discovered_count == 2
                assert first_run.asset_count == 4
                assert second_run.checkpoint_revision_before == 2
                assert second_run.checkpoint_revision_after == 3
                assert second_run.discovered_count == 0
                assert second_run.asset_count == 0
                for content in contents:
                    raw_record = content.raw["record"]
                    assert raw_record["cookie"] == REDACTED
                    assert raw_record["creator_reference_secret"] == REDACTED
        finally:
            database.dispose()

        sqlite_bytes = b"".join(
            path.read_bytes() for path in sorted(database_path.parent.glob(f"{database_path.name}*")) if path.is_file()
        )
        assert COOKIE_SENTINEL.encode() not in sqlite_bytes
        assert CREATOR_REFERENCE_SENTINEL.encode() not in sqlite_bytes
        assert COOKIE_SENTINEL not in json.dumps((first, second))
        assert CREATOR_REFERENCE_SENTINEL not in json.dumps((first, second))
    finally:
        get_settings.cache_clear()
