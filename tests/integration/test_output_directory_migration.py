"""Migration and metadata keep output policy constraints and history intact."""

from __future__ import annotations

from importlib import import_module
from importlib.resources import as_file, files
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from media_sync.infrastructure.db import AccountRepository, Database, upgrade_database
from media_sync.infrastructure.db.migration import MIGRATIONS_PACKAGE

PARENT = "0011_cookie_login"
HEAD = "0012_library_output_policy"


def _downgrade(database: Database) -> None:
    with as_file(files(MIGRATIONS_PACKAGE)) as path:
        config = Config()
        config.set_main_option("script_location", str(path))
        config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
        command.downgrade(config, PARENT)


def test_upgrade_is_additive_and_empty_policy_downgrade_preserves_history(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}")
    try:
        upgrade_database(database.url, PARENT)
        with database.session() as session:
            account = AccountRepository(session).create(
                platform="bili", display_name="Synthetic", adapter="mediacrawler"
            )
            account_id = account.id
        with database.engine.connect() as connection:
            before = connection.execute(text("SELECT * FROM accounts")).all()
        upgrade_database(database.url)
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
            assert connection.scalar(text("SELECT count(*) FROM library_output_policy")) == 0
            assert connection.scalar(text("SELECT count(*) FROM author_output_bindings")) == 0
            assert connection.execute(text("SELECT * FROM accounts")).all() == before
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        _downgrade(database)
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == PARENT
            assert connection.scalar(text("SELECT id FROM accounts")) == account_id
            assert connection.execute(text("SELECT * FROM accounts")).all() == before
    finally:
        database.dispose()


@pytest.mark.parametrize("metadata", [False, True])
def test_policy_constraints_match_metadata_and_migration(tmp_path: Path, metadata: bool) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'schema.sqlite3').as_posix()}")
    try:
        if metadata:
            database.create_schema()
        else:
            upgrade_database(database.url)
        columns = {column["name"] for column in inspect(database.engine).get_columns("library_output_policy")}
        assert columns == {
            "id",
            "revision",
            "shared_root",
            "layout",
            "created_at",
            "updated_at",
            "bili_root",
            "dy_root",
            "ks_root",
            "tieba_root",
            "wb_root",
            "xhs_root",
            "zhihu_root",
        }
        with database.engine.begin() as connection:
            connection.execute(
                text("INSERT INTO library_output_policy (id,shared_root,layout) VALUES (1,'/media','legacy_flat')")
            )
        for assignment in (
            "id=2",
            "revision=-1",
            "revision=9007199254740992",
            "shared_root=''",
            "bili_root=''",
            "layout='unknown'",
        ):
            with database.engine.begin() as connection, pytest.raises(IntegrityError):
                connection.execute(text(f"UPDATE library_output_policy SET {assignment}"))
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM library_output_policy")) == 1
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    finally:
        database.dispose()


def test_downgrade_refuses_even_initialized_policy_without_files(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'history.sqlite3').as_posix()}")
    try:
        upgrade_database(database.url)
        with database.engine.begin() as connection:
            connection.execute(
                text("INSERT INTO library_output_policy (id,shared_root,layout) VALUES (1,'/media','legacy_flat')")
            )
        with pytest.raises(RuntimeError, match="history_prevents_downgrade"):
            _downgrade(database)
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
            assert connection.scalar(text("SELECT shared_root FROM library_output_policy")) == "/media"
    finally:
        database.dispose()


def test_offline_downgrade_requires_online_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = import_module(f"media_sync.infrastructure.db.migrations.versions.{HEAD}")
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_context=lambda: SimpleNamespace(as_sql=True)))
    with pytest.raises(RuntimeError, match="requires_online_audit"):
        migration.downgrade()
