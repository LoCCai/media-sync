from pathlib import Path

import pytest
from pydantic import ValidationError

from media_sync.config import Settings


def test_settings_builds_default_sqlite_url_from_state_dir(tmp_path: Path) -> None:
    settings = Settings(state_dir=tmp_path / "state", _env_file=None)

    assert settings.resolved_database_url == f"sqlite+pysqlite:///{(tmp_path / 'state/media-sync.sqlite3').as_posix()}"
    assert settings.resolved_secret_file_dir == (tmp_path / "state/secrets").resolve()
    assert settings.resolved_mediacrawler_runtime_dir == (tmp_path / "state/mediacrawler").resolve()


def test_settings_allows_explicit_secret_file_root(tmp_path: Path) -> None:
    secret_root = tmp_path / "private"

    settings = Settings(secret_file_dir=secret_root, _env_file=None)

    assert settings.resolved_secret_file_dir == secret_root.resolve()
    assert not secret_root.exists()


def test_settings_allows_explicit_mediacrawler_runtime_without_creating_it(tmp_path: Path) -> None:
    runtime_root = tmp_path / "private-runtime"
    python_executable = tmp_path / "upstream-python"

    settings = Settings(
        mediacrawler_runtime_dir=runtime_root,
        mediacrawler_python_executable=python_executable,
        _env_file=None,
    )

    assert settings.resolved_mediacrawler_runtime_dir == runtime_root.resolve()
    assert settings.mediacrawler_python_executable == python_executable
    assert not runtime_root.exists()


def test_settings_creates_only_declared_runtime_directories(tmp_path: Path) -> None:
    roots = [tmp_path / name for name in ("state", "archive", "exports", "jobs")]
    settings = Settings(
        state_dir=roots[0],
        archive_dir=roots[1],
        export_dir=roots[2],
        job_dir=roots[3],
        _env_file=None,
    )

    settings.ensure_directories()

    assert all(path.is_dir() for path in roots)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["archive", "exports", "jobs", "state"]


@pytest.mark.parametrize("value", ["trace", "", "verbose"])
def test_settings_rejects_unknown_log_level(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(log_level=value, _env_file=None)


def test_settings_normalizes_log_level() -> None:
    assert Settings(log_level=" warning ", _env_file=None).log_level == "WARNING"
