"""Prove migrations work from package resources, including a built wheel."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from importlib.resources import as_file, files
from io import StringIO
from pathlib import Path
from uuid import UUID
from zipfile import ZipFile

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Connection

from media_sync.application.downloads import (
    ASSET_DOWNLOAD_JOB_TYPE,
    AssetDownloadRequest,
    AssetDownloadService,
    asset_download_natural_key,
)
from media_sync.application.emby import EmbyExportRequest, EmbyExportService
from media_sync.exporters.emby import EmbyExporter, ExportError
from media_sync.infrastructure.db import (
    AccountRepository,
    Asset,
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    Database,
    ExportRecord,
    Job,
    JobRepository,
    SubscriptionRepository,
)
from media_sync.infrastructure.db.asset_identity import stable_asset_key
from media_sync.infrastructure.db.migration import MIGRATIONS_PACKAGE, upgrade_database
from media_sync.media import AdapterRefreshLocator, SafeHttpClient, SecureMediaDownloader, ValidatedTarget

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class _PublicResolver:
    def resolve(self, _hostname: str, _port: int) -> Sequence[str]:
        return ("8.8.8.8",)


def _offline_downloader(payload: bytes) -> SecureMediaDownloader:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Length": str(len(payload)),
                "Content-Type": "application/octet-stream",
                "ETag": '"migration-roundtrip"',
            },
            content=payload,
        )

    def transport_factory(_target: ValidatedTarget) -> httpx.BaseTransport:
        return httpx.MockTransport(handler)

    return SecureMediaDownloader(SafeHttpClient(_PublicResolver(), transport_factory=transport_factory))


def _downgrade_packaged_database(database_url: str, revision: str) -> None:
    migrations = files(MIGRATIONS_PACKAGE)
    with as_file(migrations) as migration_path:
        configuration = Config()
        configuration.set_main_option("script_location", str(migration_path))
        configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
        command.downgrade(configuration, revision)


def _offline_0006_sql(database_url: str) -> str:
    output = StringIO()
    migrations = files(MIGRATIONS_PACKAGE)
    with as_file(migrations) as migration_path:
        configuration = Config(output_buffer=output)
        configuration.set_main_option("script_location", str(migration_path))
        configuration.set_main_option("sqlalchemy.url", database_url)
        command.upgrade(
            configuration,
            "0005_asset_refresh_sources:0006_operations_observability",
            sql=True,
        )
    return output.getvalue()


def _execution_0005_job_evidence(connection: Connection) -> dict[str, dict[str, object]]:
    rows = connection.execute(
        text(
            "SELECT id, run_id, job_type, natural_key, payload, typeof(payload) AS payload_storage_type, "
            "status, priority, attempts, max_attempts, available_at, lease_owner, lease_token, "
            "lease_expires_at, last_error_code, last_error_message, started_at, finished_at, "
            "created_at, updated_at FROM jobs "
            "WHERE job_type IN ('asset_download', 'export.emby') ORDER BY id"
        )
    ).mappings()
    return {str(row["id"]): dict(row) for row in rows}


def _emby_record_evidence(connection: Connection) -> dict[str, dict[str, object]]:
    rows = connection.execute(
        text(
            "SELECT id, content_id, exporter, exporter_version, source_fingerprint, output_path, "
            "rendered_fingerprint, status, error_message, exported_at, created_at, updated_at "
            "FROM export_records WHERE exporter = 'emby' ORDER BY id"
        )
    ).mappings()
    return {str(row["id"]): dict(row) for row in rows}


def test_programmatic_upgrade_uses_packaged_resources_and_handles_percent_path(tmp_path: Path) -> None:
    migrations = files(MIGRATIONS_PACKAGE)
    assert (migrations / "env.py").is_file()
    assert (migrations / "script.py.mako").is_file()
    assert (migrations / "versions" / "0001_initial_schema.py").is_file()

    database_path = tmp_path / "packaged%migration.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    upgrade_database(database_url)
    upgrade_database(database_url)

    engine = create_engine(database_url)
    try:
        assert "accounts" in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0006_operations_observability"
    finally:
        engine.dispose()


def test_built_wheel_contains_and_runs_packaged_migrations(tmp_path: Path) -> None:
    uv_executable = shutil.which("uv")
    if uv_executable is None:  # pragma: no cover - the repository workflow installs uv
        pytest.skip("uv is required for the wheel integration check")

    wheel_directory = tmp_path / "wheel"
    build = subprocess.run(
        [uv_executable, "build", "--wheel", "--out-dir", str(wheel_directory)],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    wheels = list(wheel_directory.glob("media_sync-*.whl"))
    assert len(wheels) == 1

    installed_root = tmp_path / "site-packages"
    with ZipFile(wheels[0]) as wheel:
        wheel_names = set(wheel.namelist())
        required_resources = {
            "media_sync/infrastructure/db/migrations/env.py",
            "media_sync/infrastructure/db/migrations/script.py.mako",
            "media_sync/infrastructure/db/migrations/versions/0001_initial_schema.py",
            "media_sync/infrastructure/db/migrations/versions/0002_checkpoint_fencing.py",
            "media_sync/infrastructure/db/migrations/versions/0003_media_download_emby.py",
            "media_sync/infrastructure/db/migrations/versions/0004_scheduler_control_plane.py",
            "media_sync/infrastructure/db/migrations/versions/0005_asset_refresh_sources.py",
            "media_sync/infrastructure/db/migrations/versions/0006_operations_observability.py",
        }
        assert required_resources <= wheel_names
        wheel.extractall(installed_root)

    installed_database = tmp_path / "installed-wheel.sqlite3"
    smoke_script = """
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

import media_sync
from media_sync.infrastructure.db import upgrade_database

installed_root = Path(sys.argv[1]).resolve()
module_path = Path(media_sync.__file__).resolve()
if not module_path.is_relative_to(installed_root):
    raise AssertionError(f"loaded source tree instead of wheel: {module_path}")
database_url = sys.argv[2]
upgrade_database(database_url)
engine = create_engine(database_url)
try:
    if "accounts" not in inspect(engine).get_table_names():
        raise AssertionError("packaged migration did not create accounts")
    with engine.connect() as connection:
        if connection.scalar(text("SELECT version_num FROM alembic_version")) != "0006_operations_observability":
            raise AssertionError("unexpected migration revision")
finally:
    engine.dispose()
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(installed_root)
    environment.pop("MEDIA_SYNC_DATABASE_URL", None)
    smoke = subprocess.run(
        [
            sys.executable,
            "-c",
            smoke_script,
            str(installed_root),
            f"sqlite+pysqlite:///{installed_database.as_posix()}",
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr


@pytest.mark.parametrize(
    ("database_url", "timestamp_type"),
    [
        ("sqlite+pysqlite:///offline.sqlite3", "DATETIME"),
        ("postgresql://example.invalid/media_sync", "TIMESTAMP WITH TIME ZONE"),
    ],
)
def test_0006_offline_ddl_is_portable_and_uses_an_explicit_stream_clock(
    database_url: str,
    timestamp_type: str,
) -> None:
    sql = _offline_0006_sql(database_url)

    for table_name in (
        "operation_event_stream_state",
        "operations",
        "operation_events",
        "operation_subjects",
    ):
        assert f"CREATE TABLE {table_name}" in sql
    assert f"updated_at {timestamp_type}" in sql
    assert "stream_sequence BIGINT NOT NULL" in sql
    assert "stream_sequence BIGSERIAL" not in sql
    assert "stream_sequence GENERATED" not in sql
    assert (
        "INSERT INTO operation_event_stream_state (id, last_sequence, pruned_through_sequence) VALUES (1, 0, 0)"
    ) in sql
    assert (
        "CREATE UNIQUE INDEX uq_operations_active_exclusive_key ON operations (exclusive_key) "
        "WHERE exclusive_key IS NOT NULL AND state IN ('queued', 'running')"
    ) in sql
    assert (
        "CREATE UNIQUE INDEX uq_operations_kind_idempotency_key_hash "
        "ON operations (kind, idempotency_key_hash) WHERE idempotency_key_hash IS NOT NULL"
    ) in sql
    assert "ck_operation_events_event_code" in sql
    if database_url.startswith("postgresql"):
        assert "id SERIAL" not in sql


def test_0006_sqlite_roundtrip_creates_only_bounded_operation_control_plane(tmp_path: Path) -> None:
    database_path = tmp_path / "operations-observability.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    operation_tables = {
        "operation_event_stream_state",
        "operation_events",
        "operation_subjects",
        "operations",
    }
    upgrade_database(database_url, "0005_asset_refresh_sources")
    engine = create_engine(database_url)
    try:
        assert operation_tables.isdisjoint(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    def assert_head() -> None:
        current_engine = create_engine(database_url)
        try:
            inspector = inspect(current_engine)
            assert operation_tables <= set(inspector.get_table_names())
            assert inspector.get_pk_constraint("operation_events")["constrained_columns"] == ["stream_sequence"]
            assert {column["name"] for column in inspector.get_columns("operation_subjects")} == {
                "operation_id",
                "subject_type",
                "subject_id",
                "role",
                "created_at",
            }
            operation_indexes = {index["name"]: index for index in inspector.get_indexes("operations")}
            assert operation_indexes["uq_operations_active_exclusive_key"]["unique"] == 1
            assert operation_indexes["uq_operations_kind_idempotency_key_hash"]["unique"] == 1
            event_foreign_keys = {
                tuple(foreign_key["constrained_columns"]): foreign_key["options"].get("ondelete")
                for foreign_key in inspector.get_foreign_keys("operation_events")
            }
            subject_foreign_keys = {
                tuple(foreign_key["constrained_columns"]): foreign_key["options"].get("ondelete")
                for foreign_key in inspector.get_foreign_keys("operation_subjects")
            }
            assert event_foreign_keys == {("operation_id",): "CASCADE"}
            assert subject_foreign_keys == {("operation_id",): "CASCADE"}
            with current_engine.connect() as connection:
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0006_operations_observability"
                )
                assert connection.execute(
                    text("SELECT id, last_sequence, pruned_through_sequence FROM operation_event_stream_state")
                ).all() == [(1, 0, 0)]
                assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        finally:
            current_engine.dispose()

    upgrade_database(database_url)
    assert_head()
    _downgrade_packaged_database(database_url, "0005_asset_refresh_sources")
    downgraded = create_engine(database_url)
    try:
        assert operation_tables.isdisjoint(inspect(downgraded).get_table_names())
        with downgraded.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0005_asset_refresh_sources"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        downgraded.dispose()
    upgrade_database(database_url)
    assert_head()


def test_0005_roundtrip_conservatively_backfills_only_unique_mediacrawler_source(tmp_path: Path) -> None:
    database_path = tmp_path / "asset-refresh-sources.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    upgrade_database(database_url, "0004_scheduler_control_plane")

    seeded = Database(database_url)
    try:
        with seeded.session() as session:

            def seed_asset(
                suffix: str,
                *,
                adapters: tuple[str, ...],
            ) -> tuple[str, list[str], str, str]:
                author, contents = AuthorRepository(session).upsert_with_contents(
                    AuthorUpsert(platform="xhs", remote_id=f"author-{suffix}", display_name=f"Author {suffix}"),
                    [ContentUpsert(remote_id=f"content-{suffix}", kind="image")],
                )
                subscription_ids = []
                for index, adapter in enumerate(adapters):
                    account = AccountRepository(session).create(
                        platform="xhs",
                        adapter=adapter,
                        display_name=f"account-{suffix}-{index}",
                    )
                    subscription = SubscriptionRepository(session).create(
                        account_id=account.id,
                        author_id=author.id,
                    )
                    subscription_ids.append(subscription.id)
                content = contents[0]
                locator = AdapterRefreshLocator(
                    adapter="mediacrawler",
                    asset_key=stable_asset_key(
                        platform="xhs",
                        content_remote_type=content.remote_type,
                        content_remote_id=content.remote_id,
                        kind="image",
                        position=0,
                        remote_id=f"asset-{suffix}",
                    ),
                )
                asset = AssetRepository(session).upsert_for_content(
                    content.id,
                    AssetUpsert(
                        platform="xhs",
                        remote_id=f"asset-{suffix}",
                        kind="image",
                        position=0,
                        locator=locator.as_dict(),
                    ),
                )
                return asset.id, subscription_ids, asset.semantic_fingerprint, asset.locator_fingerprint

            unique_asset_id, unique_subscription_ids, semantic_fingerprint, locator_fingerprint = seed_asset(
                "unique",
                adapters=("mediacrawler",),
            )
            ambiguous_asset_id, _ambiguous_subscription_ids, _, _ = seed_asset(
                "ambiguous",
                adapters=("mediacrawler", "mediacrawler"),
            )
            no_candidate_asset_id, _no_candidate_subscription_ids, _, _ = seed_asset(
                "none",
                adapters=("native",),
            )
    finally:
        seeded.dispose()

    def assert_head_and_backfill() -> None:
        engine = create_engine(database_url)
        try:
            inspector = inspect(engine)
            assert inspector.get_pk_constraint("asset_refresh_sources")["constrained_columns"] == [
                "asset_id",
                "subscription_id",
            ]
            assert {
                "ck_asset_refresh_sources_observation_kind",
                "ck_asset_refresh_sources_observed_generation_positive",
                "ck_asset_refresh_sources_observed_semantic_fingerprint_shape",
                "ck_asset_refresh_sources_observed_locator_fingerprint_shape",
                "ck_asset_refresh_sources_seen_at_order",
            } <= {constraint["name"] for constraint in inspector.get_check_constraints("asset_refresh_sources")}
            indexes = {index["name"]: index for index in inspector.get_indexes("asset_refresh_sources")}
            assert indexes["ix_asset_refresh_sources_subscription_id"]["column_names"] == ["subscription_id"]
            assert indexes["ix_asset_refresh_sources_asset_fingerprints"]["column_names"] == [
                "asset_id",
                "observed_semantic_fingerprint",
                "observed_locator_fingerprint",
            ]
            foreign_keys = {
                tuple(foreign_key["constrained_columns"]): foreign_key["options"].get("ondelete")
                for foreign_key in inspector.get_foreign_keys("asset_refresh_sources")
            }
            assert foreign_keys == {
                ("asset_id",): "CASCADE",
                ("subscription_id",): "CASCADE",
                ("last_run_id",): "SET NULL",
            }
            with engine.connect() as connection:
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0006_operations_observability"
                )
                rows = connection.execute(
                    text(
                        "SELECT asset_id, subscription_id, last_run_id, observation_kind, observed_generation, "
                        "observed_semantic_fingerprint, observed_locator_fingerprint "
                        "FROM asset_refresh_sources ORDER BY asset_id, subscription_id"
                    )
                ).all()
                assert rows == [
                    (
                        unique_asset_id,
                        unique_subscription_ids[0],
                        None,
                        "legacy_unique_inferred",
                        1,
                        semantic_fingerprint,
                        locator_fingerprint,
                    )
                ]
                assert (
                    connection.scalar(
                        text(
                            "SELECT COUNT(*) FROM asset_refresh_sources "
                            "WHERE asset_id IN (:ambiguous_asset_id, :no_candidate_asset_id)"
                        ),
                        {
                            "ambiguous_asset_id": ambiguous_asset_id,
                            "no_candidate_asset_id": no_candidate_asset_id,
                        },
                    )
                    == 0
                )
                assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        finally:
            engine.dispose()

    upgrade_database(database_url)
    assert_head_and_backfill()

    _downgrade_packaged_database(database_url, "0004_scheduler_control_plane")
    downgraded = create_engine(database_url)
    try:
        assert "asset_refresh_sources" not in inspect(downgraded).get_table_names()
        with downgraded.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0004_scheduler_control_plane"
            assert connection.scalar(text("SELECT COUNT(*) FROM assets")) == 3
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        downgraded.dispose()

    upgrade_database(database_url)
    assert_head_and_backfill()


def test_0003_upgrade_preserves_only_complete_verified_legacy_asset(tmp_path: Path) -> None:
    database_path = tmp_path / "upgrade-from-0002.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    upgrade_database(database_url, "0002_checkpoint")

    verified_author_id = "11111111-1111-4111-8111-111111111111"
    verified_content_id = "22222222-2222-4222-8222-222222222222"
    verified_asset_id = "33333333-3333-4333-8333-333333333333"
    reset_author_id = "44444444-4444-4444-8444-444444444444"
    reset_content_id = "55555555-5555-4555-8555-555555555555"
    reset_asset_ids = {
        "downloading": "66666666-6666-4666-8666-666666666661",
        "downloaded": "66666666-6666-4666-8666-666666666662",
        "exported": "66666666-6666-4666-8666-666666666663",
        "verified": "66666666-6666-4666-8666-666666666664",
    }
    secret_path_asset_id = "77777777-7777-4777-8777-777777777777"
    secret_path_sentinel = "migration-path-credential-sentinel-0003"
    observed_at = datetime(2026, 8, 30, 1, 2, 3, tzinfo=UTC)
    payload = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    checksum = hashlib.sha256(payload).hexdigest()
    source_path = (tmp_path / "legacy-archive" / "image.png").absolute()
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(payload)

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO authors "
                    "(id, platform, remote_id, display_name, first_seen_at, last_seen_at) "
                    "VALUES (:verified_author_id, 'bili', 'creator-verified', 'Verified Creator', :at, :at), "
                    "(:reset_author_id, 'bili', 'creator-reset', 'Reset Creator', :at, :at)"
                ),
                {
                    "verified_author_id": verified_author_id,
                    "reset_author_id": reset_author_id,
                    "at": observed_at,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO contents "
                    "(id, author_id, platform, remote_type, remote_id, kind, first_seen_at, last_seen_at) "
                    "VALUES (:verified_content_id, :verified_author_id, 'bili', 'image', "
                    "'image-verified', 'image', :at, :at), "
                    "(:reset_content_id, :reset_author_id, 'bili', 'video', "
                    "'video-reset', 'video', :at, :at)"
                ),
                {
                    "verified_content_id": verified_content_id,
                    "verified_author_id": verified_author_id,
                    "reset_content_id": reset_content_id,
                    "reset_author_id": reset_author_id,
                    "at": observed_at,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO assets "
                    "(id, content_id, platform, remote_id, kind, position, source_url, locator, "
                    "mime_type, size_bytes, checksum_sha256, local_path, status, created_at, updated_at) VALUES "
                    "(:id, :content_id, 'bili', :remote_id, :kind, :position, "
                    ":source_url, '{}', :mime_type, :size_bytes, :checksum, "
                    ":local_path, :status, :at, :at)"
                ),
                [
                    {
                        "id": verified_asset_id,
                        "content_id": verified_content_id,
                        "remote_id": "remote-image-verified",
                        "kind": "image",
                        "position": 0,
                        "source_url": "https://cdn.example.test/image.png",
                        "mime_type": "image/png",
                        "size_bytes": len(payload),
                        "checksum": checksum,
                        "local_path": str(source_path),
                        "status": "verified",
                        "at": observed_at,
                    },
                    *[
                        {
                            "id": reset_asset_ids[status],
                            "content_id": reset_content_id,
                            "remote_id": f"remote-{status}",
                            "kind": "image",
                            "position": position,
                            "source_url": "https://cdn.example.test/image.png",
                            "mime_type": "image/jpeg" if status != "verified" else None,
                            "size_bytes": len(payload) if status != "verified" else None,
                            "checksum": checksum if status != "verified" else None,
                            "local_path": str(source_path) if status != "verified" else "relative/incomplete.mp4",
                            "status": status,
                            "at": observed_at,
                        }
                        for position, status in enumerate(("downloading", "downloaded", "exported", "verified"))
                    ],
                    {
                        "id": secret_path_asset_id,
                        "content_id": reset_content_id,
                        "remote_id": "remote-secret-path",
                        "kind": "video",
                        "position": 9,
                        "source_url": (f"https://cdn.example.test/token%252F{secret_path_sentinel}%252Fvideo.mp4"),
                        "mime_type": None,
                        "size_bytes": None,
                        "checksum": None,
                        "local_path": None,
                        "status": "discovered",
                        "at": observed_at,
                    },
                ],
            )
    finally:
        engine.dispose()

    upgrade_database(database_url)
    migrated = Database(database_url)
    try:
        with migrated.session() as session:
            verified = session.get(Asset, verified_asset_id)
            assert verified is not None
            assert verified.generation == 1
            assert len(verified.semantic_fingerprint) == 64
            assert len(verified.locator_fingerprint) == 64
            assert verified.status == "verified"
            assert verified.mime_type == "image/png"
            assert verified.size_bytes == len(payload)
            assert verified.checksum_sha256 == checksum
            assert verified.local_path == str(source_path)
            assert verified.downloaded_at == observed_at
            assert verified.verified_at == observed_at
            assert verified.last_error_code is None

            reset_assets = [session.get(Asset, reset_asset_ids[status]) for status in reset_asset_ids]
            assert all(asset is not None for asset in reset_assets)
            for asset in reset_assets:
                assert asset is not None
                assert asset.status == "discovered"
                assert asset.mime_type is None
                assert asset.size_bytes is None
                assert asset.checksum_sha256 is None
                assert asset.local_path is None
                assert asset.downloaded_at is None
                assert asset.verified_at is None
                assert asset.last_error_code == "legacy_asset_reset"
                assert asset.last_error_at == observed_at

            secret_path_asset = session.get(Asset, secret_path_asset_id)
            assert secret_path_asset is not None
            assert secret_path_asset.source_url is None
            assert secret_path_asset.locator["type"] == "adapter_refresh"
            assert secret_path_asset.locator["adapter"] == "legacy"
            assert secret_path_sentinel not in str(secret_path_asset.locator)

        exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "export-work")
        outcome = EmbyExportService(migrated, exporter).export_author(
            EmbyExportRequest(verified_author_id, "migration-test-worker", lease_seconds=60)
        )
        assert outcome.already_exported is False
        assert outcome.rendered_fingerprint is not None
        exported_media = list((tmp_path / "library" / outcome.output_path).glob("Season 2026/*.png"))
        assert exported_media
        assert all(path.read_bytes() == payload for path in exported_media)
        with migrated.session() as session:
            job = session.get(Job, outcome.job_id)
            records = list(session.scalars(select(ExportRecord)).all())
        assert job is not None and job.status == "succeeded"
        assert len(records) == 1 and records[0].status == "succeeded"
    finally:
        migrated.dispose()

    assert secret_path_sentinel.encode() not in database_path.read_bytes()


def test_0003_roundtrip_releases_generation_and_terminal_emby_identities(tmp_path: Path) -> None:
    database_path = tmp_path / "roundtrip-0003.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    upgrade_database(database_url)

    observed_at = datetime(2026, 8, 30, 8, 9, 10, tzinfo=UTC)
    payload = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    digest = hashlib.sha256(payload).hexdigest()
    work_root = tmp_path / "download-work"
    archive_root = tmp_path / "archive"
    library_root = tmp_path / "library"
    export_work_root = tmp_path / "export-work"

    database = Database(database_url)
    try:
        with database.session() as session:
            author, contents = AuthorRepository(session).upsert_with_contents(
                AuthorUpsert(platform="xhs", remote_id="roundtrip-author", display_name="Roundtrip Author"),
                [
                    ContentUpsert(
                        remote_id="roundtrip-image",
                        remote_type="note",
                        kind="image",
                        title="Migration roundtrip image",
                        published_at=observed_at,
                    )
                ],
                seen_at=observed_at,
            )
            asset = AssetRepository(session).upsert_for_content(
                contents[0].id,
                AssetUpsert(
                    platform="xhs",
                    content_remote_type="note",
                    content_remote_id="roundtrip-image",
                    remote_id="roundtrip-image-asset",
                    kind="image",
                    position=0,
                    source_url="https://media.example.test/roundtrip.png",
                ),
            )
            author_id = author.id
            asset_id = UUID(asset.id)

        download_request = AssetDownloadRequest(
            asset_id=asset_id,
            worker_id="roundtrip-download-worker",
            work_root=work_root,
            archive_root=archive_root,
            lease_seconds=60,
            max_attempts=1,
        )
        download_service = AssetDownloadService(
            database,
            _offline_downloader(payload),
            clock=lambda: observed_at,
        )
        generation_one = download_service.run(download_request)
        assert generation_one.generation == 1

        exporter = EmbyExporter(library_root, staging_root=export_work_root)
        export_service = EmbyExportService(database, exporter, clock=lambda: observed_at)
        anchor = export_service.export_author(
            EmbyExportRequest(author_id, "roundtrip-export-anchor", lease_seconds=60, max_attempts=1)
        )
        assert anchor.already_exported is False

        with database.session() as session:
            assets = AssetRepository(session)
            current = assets.require(str(asset_id))
            generation_two = assets.reset_verified_archive(
                current.id,
                expected_generation=current.generation,
                expected_local_path=str(generation_one.archive_path),
                expected_checksum_sha256=digest,
                expected_size_bytes=len(payload),
                error_code="roundtrip_generation_reset",
                error_message="exercise a generation identity across migration downgrade",
                at=observed_at,
            )
            assert generation_two.generation == 2

        downloaded_generation_two = download_service.run(download_request)
        assert downloaded_generation_two.generation == 2
        downloaded_generation_two.archive_path.chmod(0o600)
        downloaded_generation_two.archive_path.unlink()

        with pytest.raises(ExportError) as failed_export:
            export_service.export_author(
                EmbyExportRequest(author_id, "roundtrip-export-terminal", lease_seconds=60, max_attempts=1)
            )
        assert failed_export.value.code == "asset_source_missing"

        with database.session() as session:
            generation_two_job = JobRepository(session).get_by_key(
                ASSET_DOWNLOAD_JOB_TYPE,
                asset_download_natural_key(asset_id, 2),
            )
            export_jobs = list(session.scalars(select(Job).where(Job.job_type == "export.emby")).all())
            anchor_job = next(job for job in export_jobs if job.status == "succeeded")
            terminal_job = next(job for job in export_jobs if job.status == "failed_terminal")
            successful_record = session.scalar(select(ExportRecord).where(ExportRecord.status == "succeeded"))
            terminal_record = session.scalar(select(ExportRecord).where(ExportRecord.status == "failed_terminal"))
            assert generation_two_job is not None and generation_two_job.status == "succeeded"
            assert successful_record is not None
            assert terminal_record is not None
            generation_two_job_id = generation_two_job.id
            generation_two_job_key = generation_two_job.natural_key
            anchor_job_id = anchor_job.id
            successful_record_id = successful_record.id
            terminal_record_id = terminal_record.id
            terminal_job_id = terminal_job.id
            terminal_job_key = terminal_job.natural_key
            terminal_source_fingerprint = terminal_job.payload["source_fingerprint"]
            # An invalid shape is not a recoverable publication intent and must
            # not turn this disposable terminal identity into a preserved one.
            terminal_job.payload = {**terminal_job.payload, "intent": {"schema_version": 1}}
    finally:
        database.dispose()

    _downgrade_packaged_database(database_url, "0002_checkpoint")

    downgraded_engine = create_engine(database_url)
    try:
        with downgraded_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002_checkpoint"
            assert "generation" not in {column["name"] for column in inspect(connection).get_columns("assets")}
            assert connection.scalar(text("SELECT COUNT(*) FROM jobs WHERE job_type = 'asset_download'")) == 0
            assert (
                connection.scalar(
                    text("SELECT COUNT(*) FROM jobs WHERE job_type = 'export.emby' AND status <> 'succeeded'")
                )
                == 0
            )
            assert (
                connection.scalar(
                    text("SELECT COUNT(*) FROM export_records WHERE exporter = 'emby' AND status <> 'succeeded'")
                )
                == 0
            )
            assert connection.scalar(text("SELECT COUNT(*) FROM jobs WHERE id = :id"), {"id": anchor_job_id}) == 1
            assert (
                connection.scalar(
                    text("SELECT COUNT(*) FROM export_records WHERE id = :id"),
                    {"id": successful_record_id},
                )
                == 1
            )
            assert connection.scalar(text("SELECT COUNT(*) FROM jobs WHERE id = :id"), {"id": terminal_job_id}) == 0
            assert (
                connection.scalar(
                    text("SELECT COUNT(*) FROM export_records WHERE id = :id"),
                    {"id": terminal_record_id},
                )
                == 0
            )
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        downgraded_engine.dispose()

    upgrade_database(database_url)
    upgraded = Database(database_url)
    try:
        with upgraded.session() as session:
            assets = AssetRepository(session)
            reset_candidate = assets.require(str(asset_id))
            assert reset_candidate.generation == 1
            assert reset_candidate.download_job_id is None
            repaired = assets.reset_verified_archive(
                reset_candidate.id,
                expected_generation=reset_candidate.generation,
                expected_local_path=str(downloaded_generation_two.archive_path),
                expected_checksum_sha256=digest,
                expected_size_bytes=len(payload),
                error_code="archive_blob_missing",
                error_message="roundtrip intentionally removed the verified blob",
                at=observed_at,
            )
            assert repaired.generation == 2

        replacement_download = AssetDownloadService(
            upgraded,
            _offline_downloader(payload),
            clock=lambda: observed_at,
        ).run(download_request)
        assert replacement_download.generation == 2
        assert replacement_download.job_id is not None
        assert str(replacement_download.job_id) != generation_two_job_id

        replacement_export = EmbyExportService(
            upgraded,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: observed_at,
        ).export_author(EmbyExportRequest(author_id, "roundtrip-export-replacement", lease_seconds=60, max_attempts=1))
        assert replacement_export.already_exported is False
        assert replacement_export.job_id != terminal_job_id
        assert replacement_export.source_fingerprint == terminal_source_fingerprint

        with upgraded.session() as session:
            replacement_download_job = JobRepository(session).get_by_key(
                ASSET_DOWNLOAD_JOB_TYPE,
                asset_download_natural_key(asset_id, 2),
            )
            replacement_export_job = session.get(Job, replacement_export.job_id)
            preserved_anchor = session.get(Job, anchor_job_id)
            records = list(session.scalars(select(ExportRecord)).all())
            assert replacement_download_job is not None
            assert replacement_download_job.id != generation_two_job_id
            assert replacement_download_job.natural_key == generation_two_job_key
            assert replacement_download_job.status == "succeeded"
            assert replacement_export_job is not None
            assert replacement_export_job.natural_key == terminal_job_key
            assert replacement_export_job.status == "succeeded"
            assert replacement_export_job.payload["predecessor_job_id"] == anchor_job_id
            assert preserved_anchor is not None and preserved_anchor.status == "succeeded"
            assert {record.status for record in records} == {"succeeded"}
            assert {record.source_fingerprint for record in records} == {
                anchor.source_fingerprint,
                replacement_export.source_fingerprint,
            }

        with upgraded.engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        upgraded.dispose()


def test_0003_roundtrip_preserves_published_emby_intent_for_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "roundtrip-0003-intent.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    upgrade_database(database_url)
    observed_at = datetime(2026, 8, 30, 9, 10, 11, tzinfo=UTC)
    library_root = tmp_path / "intent-library"
    export_work_root = tmp_path / "intent-export-work"

    database = Database(database_url)
    try:
        with database.session() as session:
            author, _ = AuthorRepository(session).upsert_with_contents(
                AuthorUpsert(platform="bili", remote_id="intent-author", display_name="Intent Author"),
                [
                    ContentUpsert(
                        remote_id="intent-text",
                        remote_type="dynamic",
                        kind="text",
                        title="Published before database finalization",
                        body="The exact tree must remain recoverable across a migration round trip.",
                        published_at=observed_at,
                    )
                ],
                seen_at=observed_at,
            )
            author_id = author.id

        original_complete = JobRepository.complete

        def fail_job_finalize(self: JobRepository, *args: object, **kwargs: object) -> Job:
            raise RuntimeError("crash after filesystem publication")

        monkeypatch.setattr(JobRepository, "complete", fail_job_finalize)
        with pytest.raises(ExportError) as failed:
            EmbyExportService(
                database,
                EmbyExporter(library_root, staging_root=export_work_root),
                clock=lambda: observed_at,
            ).export_author(EmbyExportRequest(author_id, "intent-crash-worker", lease_seconds=60, max_attempts=1))
        assert failed.value.code == "export_finalize_failed"

        with database.session() as session:
            pending_job = session.scalar(select(Job).where(Job.job_type == "export.emby"))
            pending_record = session.scalar(select(ExportRecord).where(ExportRecord.exporter == "emby"))
            assert pending_job is not None and pending_job.status == "running"
            assert pending_record is not None and pending_record.status == "running"
            assert "intent" in pending_job.payload and "result" not in pending_job.payload
            pending_job_id = pending_job.id
            pending_record_id = pending_record.id
    finally:
        database.dispose()

    _downgrade_packaged_database(database_url, "0002_checkpoint")
    downgraded_engine = create_engine(database_url)
    try:
        with downgraded_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002_checkpoint"
            assert connection.scalar(text("SELECT COUNT(*) FROM jobs WHERE id = :id"), {"id": pending_job_id}) == 1
            assert (
                connection.scalar(text("SELECT COUNT(*) FROM export_records WHERE id = :id"), {"id": pending_record_id})
                == 1
            )
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        downgraded_engine.dispose()

    upgrade_database(database_url)
    monkeypatch.setattr(JobRepository, "complete", original_complete)
    upgraded = Database(database_url)
    try:
        recovered = EmbyExportService(
            upgraded,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: observed_at + timedelta(seconds=61),
        ).export_author(EmbyExportRequest(author_id, "intent-recovery-worker", lease_seconds=60, max_attempts=1))

        assert recovered.already_exported is True
        assert recovered.job_id == pending_job_id
        with upgraded.session() as session:
            recovered_job = session.get(Job, pending_job_id)
            recovered_record = session.get(ExportRecord, pending_record_id)
            assert recovered_job is not None and recovered_job.status == "succeeded"
            assert recovered_record is not None and recovered_record.status == "succeeded"
            assert "intent" not in recovered_job.payload and "result" in recovered_job.payload
        with upgraded.engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        upgraded.dispose()


def test_0004_real_0003_roundtrip_preserves_0005_evidence_and_releases_sync_identity(tmp_path: Path) -> None:
    database_path = tmp_path / "real-0003-to-0004.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    upgrade_database(database_url, "0003_media_download_emby")

    observed_at = datetime(2026, 8, 30, 12, 13, 14, tzinfo=UTC)
    account_id = "10000000-0000-4000-8000-000000000001"
    author_id = "10000000-0000-4000-8000-000000000002"
    subscription_id = "10000000-0000-4000-8000-000000000003"
    content_id = "10000000-0000-4000-8000-000000000004"
    asset_id = "10000000-0000-4000-8000-000000000005"
    asset_job_id = "10000000-0000-4000-8000-000000000006"
    emby_job_id = "10000000-0000-4000-8000-000000000007"
    export_record_id = "10000000-0000-4000-8000-000000000008"
    platform_lane_id = "10000000-0000-4000-8000-000000000009"
    account_lane_id = "10000000-0000-4000-8000-000000000010"
    sync_job_id = "10000000-0000-4000-8000-000000000011"
    sync_natural_key = f"subscription:{subscription_id}:schedule:0"
    source_fingerprint = "a" * 64
    asset_payload = json.dumps(
        {
            "asset_id": asset_id,
            "generation": 2,
            "io_scope_fingerprint": "d" * 64,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    emby_payload = json.dumps(
        {
            "schema_version": 1,
            "author_id": author_id,
            "exporter": "emby",
            "exporter_version": "emby-jellyfin-v1",
            "publication_scope": "e" * 64,
            "output_path": "xhs/real-0003-author",
            "source_fingerprint": source_fingerprint,
            "predecessor_job_id": None,
            "intent": {
                "schema_version": 1,
                "source_fingerprint": source_fingerprint,
                "tree_sha256": "b" * 64,
                "manifest_sha256": "c" * 64,
                "managed_file_count": 3,
                "records": [
                    {
                        "record_id": export_record_id,
                        "content_id": content_id,
                        "source_fingerprint": source_fingerprint,
                    }
                ],
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO accounts (id, platform, display_name, created_at, updated_at) "
                    "VALUES (:id, 'xhs', 'Real 0003 Account', :at, :at)"
                ),
                {"id": account_id, "at": observed_at},
            )
            connection.execute(
                text(
                    "INSERT INTO authors "
                    "(id, platform, remote_id, display_name, first_seen_at, last_seen_at, created_at, updated_at) "
                    "VALUES (:id, 'xhs', 'real-0003-author', 'Real 0003 Author', :at, :at, :at, :at)"
                ),
                {"id": author_id, "at": observed_at},
            )
            connection.execute(
                text(
                    "INSERT INTO subscriptions (id, account_id, author_id, created_at, updated_at) "
                    "VALUES (:id, :account_id, :author_id, :at, :at)"
                ),
                {
                    "id": subscription_id,
                    "account_id": account_id,
                    "author_id": author_id,
                    "at": observed_at,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO contents "
                    "(id, author_id, platform, remote_type, remote_id, kind, first_seen_at, last_seen_at, "
                    "created_at, updated_at) "
                    "VALUES (:id, :author_id, 'xhs', 'note', 'real-0003-content', 'image', "
                    ":at, :at, :at, :at)"
                ),
                {"id": content_id, "author_id": author_id, "at": observed_at},
            )
            connection.execute(
                text(
                    "INSERT INTO jobs "
                    "(id, run_id, job_type, natural_key, payload, status, priority, attempts, max_attempts, "
                    "available_at, lease_owner, lease_token, lease_expires_at, last_error_code, "
                    "last_error_message, started_at, finished_at, created_at, updated_at) VALUES "
                    "(:asset_job_id, NULL, 'asset_download', :asset_key, :asset_payload, 'running', 7, 2, 5, "
                    ":at, 'download-worker', :asset_token, :lease_expires_at, 'prepared_result', "
                    "'download publication awaits database finalization', :at, NULL, :at, :at), "
                    "(:emby_job_id, NULL, 'export.emby', :emby_key, :emby_payload, 'running', 11, 1, 3, "
                    ":at, 'emby-worker', :emby_token, :lease_expires_at, 'publication_intent', "
                    "'Emby tree is published and awaits recovery', :at, NULL, :at, :at)"
                ),
                {
                    "asset_job_id": asset_job_id,
                    "asset_key": f"{asset_id}:2",
                    "asset_payload": asset_payload,
                    "asset_token": "20000000-0000-4000-8000-000000000001",
                    "emby_job_id": emby_job_id,
                    "emby_key": f"emby-jellyfin-v1:{'f' * 64}",
                    "emby_payload": emby_payload,
                    "emby_token": "20000000-0000-4000-8000-000000000002",
                    "lease_expires_at": observed_at + timedelta(minutes=5),
                    "at": observed_at,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO assets "
                    "(id, content_id, platform, remote_id, kind, position, source_url, locator, "
                    "semantic_fingerprint, locator_fingerprint, generation, download_job_id, queued_at, "
                    "download_started_at, status, raw, created_at, updated_at) "
                    "VALUES (:id, :content_id, 'xhs', 'real-0003-asset', 'image', 0, "
                    "'https://media.example.test/real-0003.png', :locator, :semantic, :locator_fingerprint, "
                    "2, :download_job_id, :at, :at, 'downloading', '{}', :at, :at)"
                ),
                {
                    "id": asset_id,
                    "content_id": content_id,
                    "locator": json.dumps(
                        {"type": "direct", "url": "https://media.example.test/real-0003.png", "version": 1},
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "semantic": "1" * 64,
                    "locator_fingerprint": "2" * 64,
                    "download_job_id": asset_job_id,
                    "at": observed_at,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO export_records "
                    "(id, content_id, exporter, exporter_version, source_fingerprint, output_path, "
                    "rendered_fingerprint, status, error_message, exported_at, created_at, updated_at) "
                    "VALUES (:id, :content_id, 'emby', 'emby-jellyfin-v1', :source_fingerprint, "
                    "'xhs/real-0003-author', NULL, 'running', 'publication awaits finalization', NULL, :at, :at)"
                ),
                {
                    "id": export_record_id,
                    "content_id": content_id,
                    "source_fingerprint": source_fingerprint,
                    "at": observed_at,
                },
            )
        with engine.connect() as connection:
            before_jobs = _execution_0005_job_evidence(connection)
            before_records = _emby_record_evidence(connection)
            assert (
                connection.scalar(
                    text("SELECT download_job_id FROM assets WHERE id = :id"),
                    {"id": asset_id},
                )
                == asset_job_id
            )
    finally:
        engine.dispose()

    upgrade_database(database_url)
    upgraded_engine = create_engine(database_url)
    try:
        with upgraded_engine.begin() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0006_operations_observability"
            assert _execution_0005_job_evidence(connection) == before_jobs
            assert _emby_record_evidence(connection) == before_records
            assert (
                connection.scalar(
                    text("SELECT download_job_id FROM assets WHERE id = :id"),
                    {"id": asset_id},
                )
                == asset_job_id
            )
            assert (
                connection.scalar(
                    text("SELECT schedule_revision FROM subscriptions WHERE id = :id"),
                    {"id": subscription_id},
                )
                == 0
            )
            scoped_values = connection.execute(
                text(
                    "SELECT subscription_id, account_id, platform, scheduled_for FROM jobs "
                    "WHERE id IN (:asset_job_id, :emby_job_id) ORDER BY id"
                ),
                {"asset_job_id": asset_job_id, "emby_job_id": emby_job_id},
            ).all()
            assert scoped_values == [(None, None, None, None), (None, None, None, None)]

            connection.execute(
                text("UPDATE subscriptions SET schedule_revision = 9 WHERE id = :id"),
                {"id": subscription_id},
            )
            sync_statuses = (
                "queued",
                "claimed",
                "running",
                "retry_wait",
                "waiting_auth",
                "waiting_user",
                "failed_retryable",
                "succeeded",
                "failed_terminal",
                "cancelled",
            )
            connection.execute(
                text(
                    "INSERT INTO jobs "
                    "(id, subscription_id, account_id, platform, scheduled_for, job_type, natural_key, payload, "
                    "status, available_at, created_at, updated_at) VALUES "
                    "(:id, :subscription_id, :account_id, :platform, :scheduled_for, 'sync.subscription', "
                    ":natural_key, :payload, :status, :at, :at, :at)"
                ),
                [
                    {
                        "id": sync_job_id if status == "queued" else f"30000000-0000-4000-8000-{index:012d}",
                        "subscription_id": subscription_id if status == "queued" else None,
                        "account_id": account_id if status == "queued" else None,
                        "platform": "xhs" if status == "queued" else None,
                        "scheduled_for": observed_at if status == "queued" else None,
                        "natural_key": sync_natural_key if status == "queued" else f"unscoped-sync-{status}",
                        "payload": json.dumps({"schema_version": 1, "status_fixture": status}, sort_keys=True),
                        "status": status,
                        "at": observed_at,
                    }
                    for index, status in enumerate(sync_statuses, start=1)
                ],
            )
            connection.execute(
                text(
                    "INSERT INTO scheduler_lanes "
                    "(id, scope_type, platform, account_id, circuit_state, half_open_job_id) VALUES "
                    "(:platform_lane_id, 'platform', 'xhs', NULL, 'closed', NULL), "
                    "(:account_lane_id, 'account', 'xhs', :account_id, 'half_open', :half_open_job_id)"
                ),
                {
                    "platform_lane_id": platform_lane_id,
                    "account_lane_id": account_lane_id,
                    "account_id": account_id,
                    "half_open_job_id": sync_job_id,
                },
            )
            assert _execution_0005_job_evidence(connection) == before_jobs
            assert _emby_record_evidence(connection) == before_records
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        upgraded_engine.dispose()

    _downgrade_packaged_database(database_url, "0003_media_download_emby")
    downgraded_engine = create_engine(database_url)
    try:
        with downgraded_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003_media_download_emby"
            assert "scheduler_lanes" not in inspect(connection).get_table_names()
            assert "schedule_revision" not in {
                column["name"] for column in inspect(connection).get_columns("subscriptions")
            }
            job_columns = {column["name"] for column in inspect(connection).get_columns("jobs")}
            assert {"subscription_id", "account_id", "platform", "scheduled_for"}.isdisjoint(job_columns)
            assert connection.scalar(text("SELECT COUNT(*) FROM jobs WHERE job_type = 'sync.subscription'")) == 0
            assert _execution_0005_job_evidence(connection) == before_jobs
            assert _emby_record_evidence(connection) == before_records
            assert (
                connection.scalar(
                    text("SELECT download_job_id FROM assets WHERE id = :id"),
                    {"id": asset_id},
                )
                == asset_job_id
            )
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        downgraded_engine.dispose()

    upgrade_database(database_url)
    reupgraded_engine = create_engine(database_url)
    try:
        with reupgraded_engine.begin() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0006_operations_observability"
            assert (
                connection.scalar(
                    text("SELECT schedule_revision FROM subscriptions WHERE id = :id"),
                    {"id": subscription_id},
                )
                == 0
            )
            assert _execution_0005_job_evidence(connection) == before_jobs
            assert _emby_record_evidence(connection) == before_records
            assert (
                connection.scalar(
                    text("SELECT download_job_id FROM assets WHERE id = :id"),
                    {"id": asset_id},
                )
                == asset_job_id
            )
            connection.execute(
                text(
                    "INSERT INTO jobs "
                    "(id, subscription_id, account_id, platform, scheduled_for, job_type, natural_key, payload, "
                    "status, available_at, created_at, updated_at) VALUES "
                    "(:id, :subscription_id, :account_id, 'xhs', :at, 'sync.subscription', :natural_key, "
                    "'{}', 'queued', :at, :at, :at)"
                ),
                {
                    "id": sync_job_id,
                    "subscription_id": subscription_id,
                    "account_id": account_id,
                    "natural_key": sync_natural_key,
                    "at": observed_at,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO scheduler_lanes (id, scope_type, platform, account_id) VALUES "
                    "(:platform_lane_id, 'platform', 'xhs', NULL), "
                    "(:account_lane_id, 'account', 'xhs', :account_id)"
                ),
                {
                    "platform_lane_id": platform_lane_id,
                    "account_lane_id": account_lane_id,
                    "account_id": account_id,
                },
            )
            assert (
                connection.scalar(
                    text("SELECT status FROM jobs WHERE id = :id"),
                    {"id": sync_job_id},
                )
                == "queued"
            )
            assert connection.scalar(text("SELECT COUNT(*) FROM scheduler_lanes")) == 2
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        reupgraded_engine.dispose()
