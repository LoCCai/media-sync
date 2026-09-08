"""Closed deployment provenance and preflight evidence contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.interfaces import cli as cli_module
from media_sync.interfaces.cli import _KNOWN_DATABASE_REVISIONS, _read_build_manifest, collect_database_status

REVISION = "47ca1079bb5db3d1e93b172402c5edeeb04f998c"


def test_known_database_revision_allowlist_matches_packaged_migrations() -> None:
    versions = Path(__file__).resolve().parents[2] / "src/media_sync/infrastructure/db/migrations/versions"
    discovered = {path.stem for path in versions.glob("[0-9][0-9][0-9][0-9]_*.py")}

    assert discovered == _KNOWN_DATABASE_REVISIONS


def test_missing_build_manifest_is_honest_not_run(tmp_path: Path) -> None:
    assert _read_build_manifest(tmp_path / "missing.txt") == {
        "status": "not_run",
        "present": False,
        "source_revision": None,
        "source_revision_status": "not_run",
        "facts": {},
    }


@pytest.mark.parametrize(
    ("value", "expected_status", "expected_revision"),
    [
        (REVISION, "pass", REVISION),
        ("unavailable", "not_run", None),
        (None, "not_run", None),
    ],
)
def test_build_manifest_accepts_only_closed_source_states(
    tmp_path: Path,
    value: str | None,
    expected_status: str,
    expected_revision: str | None,
) -> None:
    manifest = tmp_path / "BUILD-MANIFEST.txt"
    source_line = "" if value is None else f"source_revision: {value}\n"
    manifest.write_text(
        f"python: Python 3.13.15\n{source_line}web_lock_sha256: {'a' * 64}\nprivate_name: DO_NOT_RENDER\n",
        encoding="utf-8",
    )

    report = _read_build_manifest(manifest)

    assert report == {
        "status": "pass",
        "present": True,
        "source_revision": expected_revision,
        "source_revision_status": expected_status,
        "facts": {"python": "Python 3.13.15", "web_lock_sha256": "a" * 64},
    }
    assert "DO_NOT_RENDER" not in json.dumps(report)


@pytest.mark.parametrize(
    "source_lines",
    [
        "source_revision: DO_NOT_RENDER_PRIVATE_VALUE\n",
        f"source_revision: {REVISION.upper()}\n",
        f"source_revision: {REVISION}\nsource_revision: {'b' * 40}\n",
    ],
)
def test_invalid_or_duplicate_source_revision_fails_without_echo(tmp_path: Path, source_lines: str) -> None:
    manifest = tmp_path / "BUILD-MANIFEST.txt"
    manifest.write_text(f"python: Python 3.13.15\n{source_lines}", encoding="utf-8")

    report = _read_build_manifest(manifest)

    assert report == {
        "status": "fail",
        "present": True,
        "source_revision": None,
        "source_revision_status": "fail",
        "facts": {"python": "Python 3.13.15"},
    }
    assert "DO_NOT_RENDER" not in json.dumps(report)
    assert REVISION not in json.dumps(report)


def test_known_older_database_revision_is_visible_without_accepting_it(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    upgrade_database(database_url)
    database = Database(database_url)
    try:
        with database.session() as session:
            session.execute(text("UPDATE alembic_version SET version_num = '0014_bili_delivery_baseline'"))
        report = collect_database_status(database_url)
    finally:
        database.dispose()

    assert report["reachable"] is True
    assert report["revision"] == "0014_bili_delivery_baseline"
    assert report["expected_revision"] == "0015_xhs_creator_notes"
    assert report["revision_current"] is False
    assert report["ok"] is False


def test_container_contract_carries_revision_without_copying_project_git_metadata() -> None:
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    compose = (root / "docker-compose.example.yml").read_text(encoding="utf-8")
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert "ARG MEDIA_SYNC_SOURCE_REVISION=unavailable" in dockerfile
    assert "ARG MEDIA_SYNC_SOURCE_REVISION\n" in dockerfile
    assert "^(unavailable|[0-9a-f]{40})$" in dockerfile
    assert 'LABEL org.opencontainers.image.revision="${MEDIA_SYNC_SOURCE_REVISION}"' in dockerfile
    assert 'echo "source_revision: ${MEDIA_SYNC_SOURCE_REVISION}"' in dockerfile
    assert "COPY .git" not in dockerfile
    assert dockerignore[0] == ".git"
    assert "MEDIA_SYNC_SOURCE_REVISION: ${MEDIA_SYNC_SOURCE_REVISION:-unavailable}" in compose
    assert "export MEDIA_SYNC_SOURCE_REVISION=$(git rev-parse HEAD)" in compose


@pytest.mark.parametrize(("ready", "expected_exit_code"), [(True, 0), (False, 1)])
def test_deep_doctor_json_uses_the_api_readiness_report(
    monkeypatch: pytest.MonkeyPatch,
    ready: bool,
    expected_exit_code: int,
) -> None:
    calls: list[tuple[object, bool]] = []
    settings = object()
    report = {
        "ok": ready,
        "status": "ready" if ready else "blocked",
        "code": "ready" if ready else "checkout_invalid",
        "live_qualification": "NOT_RUN",
        "source_revision": REVISION,
    }

    def collect(received: object, *, license_acknowledged: bool) -> dict[str, object]:
        calls.append((received, license_acknowledged))
        return report

    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    monkeypatch.setattr(cli_module, "collect_deep_readiness_report", collect)

    result = CliRunner().invoke(
        cli_module.app,
        ["doctor", "--deep", "--accept-mediacrawler-license", "--json"],
    )

    assert result.exit_code == expected_exit_code, result.output
    assert json.loads(result.output) == report
    assert calls == [(settings, True)]
