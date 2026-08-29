"""Prove migrations work from package resources, including a built wheel."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from zipfile import ZipFile

import pytest
from sqlalchemy import create_engine, inspect, text

from media_sync.infrastructure.db.migration import MIGRATIONS_PACKAGE, upgrade_database

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


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
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002_checkpoint"
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
        if connection.scalar(text("SELECT version_num FROM alembic_version")) != "0002_checkpoint":
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
