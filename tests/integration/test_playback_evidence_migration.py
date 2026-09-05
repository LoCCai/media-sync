"""Migration and metadata coverage for the playback-evidence ledger."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from importlib.resources import as_file, files
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from media_sync.infrastructure.db import (
    AuthorRepository,
    AuthorUpsert,
    Database,
    JobRepository,
    PlaybackEvidence,
    create_database_engine,
    upgrade_database,
)
from media_sync.infrastructure.db.migration import MIGRATIONS_PACKAGE

HEAD_REVISION = "0008_playback_evidence"
PARENT_REVISION = "0007_media_server_operations"
NOW = datetime(2026, 9, 5, 8, tzinfo=UTC)
EVIDENCE_ID = "10000000-0000-4000-8000-000000000001"


def _database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def _alembic_config(database_url: str, *, output: StringIO | None = None) -> Config:
    configuration = Config(output_buffer=output)
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return configuration


def _downgrade(database_url: str, revision: str) -> None:
    migrations = files(MIGRATIONS_PACKAGE)
    with as_file(migrations) as migration_path:
        configuration = _alembic_config(database_url)
        configuration.set_main_option("script_location", str(migration_path))
        command.downgrade(configuration, revision)


def _offline_downgrade(database_url: str) -> None:
    output = StringIO()
    migrations = files(MIGRATIONS_PACKAGE)
    with as_file(migrations) as migration_path:
        configuration = _alembic_config(database_url, output=output)
        configuration.set_main_option("script_location", str(migration_path))
        command.downgrade(
            configuration,
            f"{HEAD_REVISION}:{PARENT_REVISION}",
            sql=True,
        )


def _offline_upgrade(database_url: str) -> str:
    output = StringIO()
    migrations = files(MIGRATIONS_PACKAGE)
    with as_file(migrations) as migration_path:
        configuration = _alembic_config(database_url, output=output)
        configuration.set_main_option("script_location", str(migration_path))
        command.upgrade(
            configuration,
            f"{PARENT_REVISION}:{HEAD_REVISION}",
            sql=True,
        )
    return output.getvalue()


def _seed_parents(database_url: str, suffix: str = "migration") -> tuple[str, str]:
    database = Database(database_url)
    try:
        with database.session() as session:
            author = AuthorRepository(session).upsert(
                AuthorUpsert(platform="xhs", remote_id=f"author-{suffix}", display_name=f"Author {suffix}")
            )
            job = JobRepository(session).enqueue(
                job_type="export.emby",
                natural_key=f"publication-{suffix}",
                payload={"schema_version": 1},
                available_at=NOW,
            )
            return author.id, job.id
    finally:
        database.dispose()


def _valid_values(parent_author_id: str, parent_job_id: str, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "id": EVIDENCE_ID,
        "schema_version": 1,
        "author_id": parent_author_id,
        "publication_job_id": parent_job_id,
        "profile_fingerprint": "a" * 64,
        "publication_fingerprint": "b" * 64,
        "selector_fingerprint": "c" * 64,
        "item_fingerprint": "d" * 64,
        "observation_fingerprint": "e" * 64,
        "observed_at": NOW,
        "confirmed_at": NOW + timedelta(seconds=1),
    }
    values.update(overrides)
    return values


def _insert_evidence(engine: Engine, values: Mapping[str, object]) -> None:
    columns = ", ".join(values)
    parameters = ", ".join(f":{name}" for name in values)
    with engine.begin() as connection:
        connection.execute(
            text(f"INSERT INTO playback_evidence ({columns}) VALUES ({parameters})"),
            dict(values),
        )


def _table_signature(engine: Engine) -> dict[str, object]:
    inspector = inspect(engine)
    columns = {
        column["name"]: (
            type(column["type"]).__name__,
            getattr(column["type"], "length", None),
            column["nullable"],
            column.get("default"),
            column["primary_key"],
        )
        for column in inspector.get_columns("playback_evidence")
    }
    foreign_keys = {
        (
            tuple(foreign_key["constrained_columns"]),
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
            foreign_key["options"].get("ondelete"),
        )
        for foreign_key in inspector.get_foreign_keys("playback_evidence")
    }
    return {
        "columns": columns,
        "primary_key": inspector.get_pk_constraint("playback_evidence"),
        "unique": inspector.get_unique_constraints("playback_evidence"),
        "indexes": inspector.get_indexes("playback_evidence"),
        "checks": {constraint["name"] for constraint in inspector.get_check_constraints("playback_evidence")},
        "foreign_keys": foreign_keys,
    }


def test_0008_upgrades_fresh_and_populated_0007_databases_without_changing_parents(tmp_path: Path) -> None:
    fresh_url = _database_url(tmp_path / "fresh.sqlite3")
    upgrade_database(fresh_url, PARENT_REVISION)
    upgrade_database(fresh_url, HEAD_REVISION)
    fresh_engine = create_database_engine(fresh_url)
    try:
        assert "playback_evidence" in inspect(fresh_engine).get_table_names()
        with fresh_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD_REVISION
            assert connection.scalar(text("SELECT COUNT(*) FROM playback_evidence")) == 0
    finally:
        fresh_engine.dispose()

    populated_url = _database_url(tmp_path / "populated.sqlite3")
    upgrade_database(populated_url, PARENT_REVISION)
    author_id, job_id = _seed_parents(populated_url, "populated")
    upgrade_database(populated_url, HEAD_REVISION)
    populated_engine = create_database_engine(populated_url)
    try:
        with populated_engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM authors WHERE id = :id"), {"id": author_id}) == 1
            assert connection.scalar(text("SELECT COUNT(*) FROM jobs WHERE id = :id"), {"id": job_id}) == 1
            assert connection.scalar(text("SELECT COUNT(*) FROM playback_evidence")) == 0
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        populated_engine.dispose()


@pytest.mark.parametrize(
    ("database_url", "timestamp_type"),
    [
        ("sqlite+pysqlite:///offline.sqlite3", "DATETIME"),
        ("postgresql://example.invalid/media_sync", "TIMESTAMP WITH TIME ZONE"),
    ],
)
def test_0008_offline_upgrade_is_portable_and_contains_the_complete_ledger(
    database_url: str,
    timestamp_type: str,
) -> None:
    sql = _offline_upgrade(database_url)

    assert "CREATE TABLE playback_evidence" in sql
    assert f"observed_at {timestamp_type} NOT NULL" in sql
    assert f"confirmed_at {timestamp_type} NOT NULL" in sql
    assert "FOREIGN KEY(author_id) REFERENCES authors (id) ON DELETE RESTRICT" in sql
    assert "FOREIGN KEY(publication_job_id) REFERENCES jobs (id) ON DELETE RESTRICT" in sql
    assert "CONSTRAINT uq_playback_evidence_observation_fingerprint UNIQUE (observation_fingerprint)" in sql
    assert (
        "CREATE INDEX ix_playback_evidence_author_confirmed ON playback_evidence (author_id, confirmed_at, id)"
    ) in sql


def test_0008_migration_and_create_all_have_equivalent_playback_evidence_metadata(tmp_path: Path) -> None:
    migrated_url = _database_url(tmp_path / "migrated.sqlite3")
    upgrade_database(migrated_url, HEAD_REVISION)
    migrated_engine = create_database_engine(migrated_url)

    metadata_database = Database(_database_url(tmp_path / "metadata.sqlite3"))
    try:
        metadata_database.create_schema()
        assert _table_signature(migrated_engine) == _table_signature(metadata_database.engine)
        signature = _table_signature(migrated_engine)
        assert signature["foreign_keys"] == {
            (("author_id",), "authors", ("id",), "RESTRICT"),
            (("publication_job_id",), "jobs", ("id",), "RESTRICT"),
        }
        assert {constraint["name"] for constraint in signature["unique"]} == {
            "uq_playback_evidence_observation_fingerprint"
        }
        assert {(index["name"], tuple(index["column_names"])) for index in signature["indexes"]} == {
            ("ix_playback_evidence_author_confirmed", ("author_id", "confirmed_at", "id"))
        }
        assert signature["checks"] == {
            "ck_playback_evidence_schema_version_supported",
            "ck_playback_evidence_id_canonical_uuid",
            "ck_playback_evidence_author_id_canonical_uuid",
            "ck_playback_evidence_publication_job_id_canonical_uuid",
            "ck_playback_evidence_profile_fingerprint_sha256",
            "ck_playback_evidence_publication_fingerprint_sha256",
            "ck_playback_evidence_selector_fingerprint_sha256",
            "ck_playback_evidence_item_fingerprint_sha256",
            "ck_playback_evidence_observation_fingerprint_sha256",
            "ck_playback_evidence_timestamps_ordered",
        }
    finally:
        migrated_engine.dispose()
        metadata_database.dispose()


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "not-a-uuid"},
        {"id": "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"},
        {"schema_version": 2},
        {"author_id": "10000000-0000-4000-8000-00000000000g"},
        {"publication_job_id": "10000000000040008000000000000002"},
        {"profile_fingerprint": "A" * 64},
        {"publication_fingerprint": "g" * 64},
        {"selector_fingerprint": "c" * 63},
        {"item_fingerprint": "d" * 65},
        {"observation_fingerprint": "not-a-digest"},
        {"confirmed_at": NOW - timedelta(microseconds=1)},
    ],
)
def test_0008_rejects_invalid_uuid_digest_schema_and_timestamp_rows(
    tmp_path: Path,
    overrides: dict[str, object],
) -> None:
    database_url = _database_url(tmp_path / "constraints.sqlite3")
    upgrade_database(database_url, HEAD_REVISION)
    author_id, job_id = _seed_parents(database_url, "constraints")
    engine = create_database_engine(database_url)
    try:
        with pytest.raises(IntegrityError):
            _insert_evidence(engine, _valid_values(author_id, job_id, **overrides))
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM playback_evidence")) == 0
    finally:
        engine.dispose()


def test_0008_restricts_parent_deletion_and_blocks_nonempty_downgrade(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path / "guarded.sqlite3")
    upgrade_database(database_url, HEAD_REVISION)
    author_id, job_id = _seed_parents(database_url, "guarded")
    engine = create_database_engine(database_url)
    try:
        _insert_evidence(engine, _valid_values(author_id, job_id))
        for table_name, parent_id in (("authors", author_id), ("jobs", job_id)):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(text(f"DELETE FROM {table_name} WHERE id = :id"), {"id": parent_id})

        with pytest.raises(RuntimeError, match="playback_evidence_rows_prevent_downgrade"):
            _downgrade(database_url, PARENT_REVISION)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD_REVISION
            assert connection.scalar(text("SELECT COUNT(*) FROM playback_evidence")) == 1
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []

        with engine.begin() as connection:
            connection.execute(text("DELETE FROM playback_evidence WHERE id = :id"), {"id": EVIDENCE_ID})
    finally:
        engine.dispose()

    _downgrade(database_url, PARENT_REVISION)
    downgraded_engine = create_database_engine(database_url)
    try:
        assert "playback_evidence" not in inspect(downgraded_engine).get_table_names()
        with downgraded_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == PARENT_REVISION
            assert connection.scalar(text("SELECT COUNT(*) FROM authors WHERE id = :id"), {"id": author_id}) == 1
            assert connection.scalar(text("SELECT COUNT(*) FROM jobs WHERE id = :id"), {"id": job_id}) == 1
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        downgraded_engine.dispose()


def test_0008_offline_downgrade_is_rejected_before_emitting_destructive_sql() -> None:
    with pytest.raises(RuntimeError, match="playback_evidence_downgrade_requires_online_audit"):
        _offline_downgrade("sqlite+pysqlite:///offline.sqlite3")


def test_playback_evidence_model_has_no_mutable_or_requester_columns() -> None:
    assert set(PlaybackEvidence.__table__.columns.keys()) == {
        "id",
        "schema_version",
        "author_id",
        "publication_job_id",
        "profile_fingerprint",
        "publication_fingerprint",
        "selector_fingerprint",
        "item_fingerprint",
        "observation_fingerprint",
        "observed_at",
        "confirmed_at",
    }
