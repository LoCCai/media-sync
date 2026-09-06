"""Offline output binding at the runtime/CLI boundary, with actual library files."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

from media_sync.application.output_directories import OutputDirectoryError, OutputDirectoryService
from media_sync.application.pipeline import SubscriptionPipelineError
from media_sync.application.pipeline_runtime import LocalPipelineRuntimeConfig, SubscriptionPipelineExecutor
from media_sync.config import Settings
from media_sync.infrastructure.db import AuthorRepository, AuthorUpsert, ContentUpsert, Database
from media_sync.infrastructure.db.models import Job, Subscription
from media_sync.interfaces import cli
from media_sync.media import SafeHttpClient, ValidatedTarget
from media_sync.scheduler.pipeline_worker import classify_pipeline_failure
from media_sync.security import SecretResolver
from tests.integration import test_pipeline_runtime as support
from tests.integration import test_pipeline_worker as worker_support
from tests.unit._api_client import authenticated_test_client


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'directories.sqlite3').as_posix()}")
    database.create_schema()
    yield database
    database.dispose()


def _settings(tmp_path: Path, database: Database) -> Settings:
    return Settings(
        _env_file=None,
        database_url=str(database.engine.url),
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "media",
        job_dir=tmp_path / "jobs",
        secret_file_dir=tmp_path / "secrets",
        mediacrawler_runtime_dir=tmp_path / "runtime",
        mediacrawler_lock_path=tmp_path / "source" / "upstreams.lock.json",
    )


def _config(
    settings: Settings,
    resolver: Callable[[str], Path],
    requests: list[str],
    *,
    on_download: Callable[[], None] | None = None,
) -> LocalPipelineRuntimeConfig:
    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if on_download is not None:
            on_download()
        return httpx.Response(200, headers={"Content-Type": "image/png"}, content=support.PNG)

    def transport(_target: ValidatedTarget) -> httpx.BaseTransport:
        return httpx.MockTransport(handle)

    return LocalPipelineRuntimeConfig(
        work_root=settings.job_dir / "downloads",
        archive_root=settings.archive_dir,
        export_root=settings.export_dir,
        export_staging_root=settings.job_dir / "emby-export",
        mediacrawler_lock_path=settings.mediacrawler_lock_path,
        mediacrawler_runtime_root=settings.resolved_mediacrawler_runtime_dir,
        mediacrawler_python_executable=None,
        secret_resolver=SecretResolver.local(file_root=settings.resolved_secret_file_dir),
        output_root_resolver=resolver,
        http_client_factory=lambda: SafeHttpClient(support._PublicResolver(), transport_factory=transport),
    )


def _author_id(database: Database, subscription_id: UUID) -> str:
    with database.session() as session:
        subscription = session.get(Subscription, str(subscription_id))
        assert subscription is not None
        return subscription.author_id


def test_runtime_resolves_at_execution_and_freezes_root_before_downloading(database: Database, tmp_path: Path) -> None:
    subscription_id, account_id, _asset_id = support._seed_direct_asset(database)
    settings = _settings(tmp_path, database)
    selected_root = tmp_path / "not-selected"
    calls: list[str] = []
    requests: list[str] = []

    def bind(author_id: str) -> Path:
        calls.append(author_id)
        return selected_root

    def change_callback_during_download() -> None:
        nonlocal selected_root
        selected_root = tmp_path / "not-used-during-attempt"

    executor = SubscriptionPipelineExecutor(
        database, _config(settings, bind, requests, on_download=change_callback_during_download)
    )
    selected_root = tmp_path / "execution-root"
    outcome = executor.run(
        subscription_id, expected_account_id=account_id, expected_platform="bili", worker_id="frozen-root"
    )
    assert calls == [_author_id(database, subscription_id)]
    assert requests == [support.ASSET_URL]
    assert (tmp_path / "execution-root" / outcome.export.output_path / "tvshow.nfo").is_file()
    assert not settings.export_dir.exists()
    assert not selected_root.exists()


def test_fresh_shared_service_binds_platform_root_and_replays_without_network(
    database: Database, tmp_path: Path
) -> None:
    subscription_id, account_id, _asset_id = support._seed_direct_asset(database)
    settings = _settings(tmp_path, database)
    requests: list[str] = []
    directories = OutputDirectoryService(database, settings)
    executor = SubscriptionPipelineExecutor(database, _config(settings, directories.bind_author_root, requests))
    first = executor.run(
        subscription_id, expected_account_id=account_id, expected_platform="bili", worker_id="fresh-directory"
    )
    # Independent DB/service/runtime instance reads the same durable author binding.
    independent = Database(settings.resolved_database_url)
    try:
        independent_service = OutputDirectoryService(independent, settings)
        second_executor = SubscriptionPipelineExecutor(
            independent, _config(settings, independent_service.bind_author_root, requests)
        )
        second = second_executor.run(
            subscription_id, expected_account_id=account_id, expected_platform="bili", worker_id="independent-directory"
        )
    finally:
        independent.dispose()
    root = settings.export_dir / "bili"
    assert directories.resolve_author_root(_author_id(database, subscription_id)) == root
    assert (root / first.export.output_path / "tvshow.nfo").is_file()
    assert list((root / first.export.output_path).rglob("*.png"))
    assert requests == [support.ASSET_URL]
    assert second.export.already_exported and second.export.job_id == first.export.job_id
    assert [item.disposition for item in second.downloads] == ["already_verified"]
    assert settings.archive_dir.exists() and settings.job_dir.exists()


@pytest.mark.parametrize("scope_error", ["account", "platform", "missing", "removed"])
def test_scope_is_proved_before_output_binding_or_download(
    database: Database, tmp_path: Path, scope_error: str
) -> None:
    subscription_id, account_id, _asset_id = support._seed_direct_asset(database)
    if scope_error == "removed":
        from datetime import UTC, datetime

        with database.session() as session:
            session.get(Subscription, str(subscription_id)).deleted_at = datetime.now(UTC)
    calls: list[str] = []
    requests: list[str] = []

    def bind(author_id: str) -> Path:
        calls.append(author_id)
        return tmp_path / "unexpected-output"

    executor = SubscriptionPipelineExecutor(database, _config(_settings(tmp_path, database), bind, requests))
    with pytest.raises(SubscriptionPipelineError):
        executor.run(
            uuid4() if scope_error == "missing" else subscription_id,
            expected_account_id=uuid4() if scope_error == "account" else account_id,
            expected_platform="dy" if scope_error == "platform" else "bili",
            worker_id="invalid-scope",
        )
    assert not calls and not requests
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


@pytest.mark.parametrize(
    "code",
    [
        "output_directory_invalid",
        "output_directory_unsafe",
        "output_directory_overlap",
        "output_directory_conflict",
        "output_directory_migration_required",
        "output_directory_author_not_found",
        "output_directory_unavailable",
    ],
)
def test_binding_error_is_fixed_and_has_correct_retryability(database: Database, tmp_path: Path, code: str) -> None:
    subscription_id, account_id, _asset_id = support._seed_direct_asset(database)
    requests: list[str] = []

    def reject(_author_id: str) -> Path:
        raise OutputDirectoryError(code)

    executor = SubscriptionPipelineExecutor(database, _config(_settings(tmp_path, database), reject, requests))
    with pytest.raises(SubscriptionPipelineError) as rejected:
        executor.run(
            subscription_id, expected_account_id=account_id, expected_platform="bili", worker_id="bad-directory"
        )
    retryable = code == "output_directory_unavailable"
    expected = "pipeline_output_directory_unavailable" if retryable else "pipeline_output_directory_invalid"
    assert rejected.value.code == expected and rejected.value.retryable is retryable
    assert classify_pipeline_failure(expected).retryable is retryable
    assert not requests
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


@pytest.mark.parametrize("value", [None, "not-a-path", Path("relative")])
def test_invalid_resolver_result_cannot_create_files(database: Database, tmp_path: Path, value: Any) -> None:
    subscription_id, account_id, _asset_id = support._seed_direct_asset(database)
    requests: list[str] = []
    executor = SubscriptionPipelineExecutor(database, _config(_settings(tmp_path, database), lambda _: value, requests))
    with pytest.raises(SubscriptionPipelineError, match="pipeline_output_directory_invalid"):
        executor.run(
            subscription_id, expected_account_id=account_id, expected_platform="bili", worker_id="bad-resolver"
        )
    assert not requests


@pytest.mark.parametrize("code", ["output_directory_unsafe", "output_directory_unavailable"])
def test_cli_manual_export_reports_safe_binding_failure_before_export(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
) -> None:
    author_id = str(uuid4())
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(tmp_path, database))

    def reject(_service: OutputDirectoryService, _author_id: str) -> Path:
        raise OutputDirectoryError(code) from RuntimeError("PRIVATE-path-and-credential-sentinel")

    monkeypatch.setattr(OutputDirectoryService, "bind_author_root", reject)
    monkeypatch.setattr(cli, "EmbyExporter", lambda *_args, **_kwargs: pytest.fail("exporter must not be constructed"))
    result = CliRunner().invoke(cli.app, ["emby", "export", "--author-id", author_id, "--json"])
    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "author_id": author_id,
        "status": "failed",
        "error_code": code,
        "retryable": code == "output_directory_unavailable",
    }
    assert "PRIVATE" not in result.output


def test_cli_manual_export_uses_bound_root_and_unchanged_job_staging(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, database)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    author_id = str(uuid4())
    trace: list[object] = []
    bound_root = tmp_path / "manual-target" / "bili"

    def bind(_service: OutputDirectoryService, identifier: str) -> Path:
        trace.append(("bind", identifier))
        return bound_root

    class Exporter:
        def __init__(self, export_root: Path, *, staging_root: Path) -> None:
            trace.append(("exporter", export_root, staging_root))

    class Service:
        def __init__(self, _database: Database, _exporter: Exporter) -> None:
            pass

        def export_author(self, request: Any) -> Any:
            trace.append(("export", request.author_id))
            return SimpleNamespace(
                job_id=str(uuid4()),
                source_fingerprint="a" * 64,
                output_path="author",
                rendered_fingerprint="b" * 64,
                managed_file_count=1,
                already_exported=False,
            )

    monkeypatch.setattr(OutputDirectoryService, "bind_author_root", bind)
    monkeypatch.setattr(cli, "EmbyExporter", Exporter)
    monkeypatch.setattr(cli, "EmbyExportService", Service)
    result = CliRunner().invoke(cli.app, ["emby", "export", "--author-id", author_id, "--json"])
    assert result.exit_code == 0, result.output
    assert trace == [
        ("bind", author_id),
        ("exporter", bound_root, settings.job_dir / "emby-export"),
        ("export", author_id),
    ]


def _text_pipeline(database: Database, suffix: str) -> tuple[str, str]:
    job_id, _sync_job_id, subscription_id, _account_id, _run_id = worker_support._seed_pipeline(
        database, remote_id=suffix
    )
    author_id = _author_id(database, UUID(subscription_id))
    with database.session() as session:
        AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(platform="bili", remote_id=suffix, display_name=f"Creator {suffix}"),
            (
                ContentUpsert(
                    remote_id=f"text-{suffix}",
                    remote_type="post",
                    kind="text",
                    title="Offline publication",
                    body="图文归档内容",
                ),
            ),
        )
    return job_id, author_id


def _real_worker(database: Database, settings: Settings, identifier: str) -> Any:
    return cli._build_pipeline_worker(
        database,
        settings,
        worker_id=identifier,
        retry_delay_seconds=30,
        enable_mediacrawler=False,
        accept_mediacrawler_license=False,
        xhs_detail_reference_ref=None,
    )


def test_api_save_is_seen_by_existing_and_independent_workers_and_library_inspection(
    database: Database, tmp_path: Path
) -> None:
    settings = _settings(tmp_path, database)
    first_job_id, first_author_id = _text_pipeline(database, "existing-worker")
    existing_worker = _real_worker(database, settings, "already-created-worker")
    new_shared_root = tmp_path / "api-configured-library"
    dy_override = tmp_path / "dy-override"
    assert settings.media_server_provider is None
    with authenticated_test_client(settings) as client:
        saved = client.put(
            "/api/v1/settings/output",
            json={
                "expected_revision": 0,
                "shared_root": str(new_shared_root),
                "platform_overrides": {},
                "layout": "platform_subdirectories",
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["revision"] == 1
        assert not new_shared_root.exists(), "saving policy must not create library files"
        first = asyncio.run(existing_worker.run_once(worker_id="existing-worker-run"))
        assert first.job_id == first_job_id and first.status == "succeeded", first
        first_inspection = client.get(f"/api/v1/library/{first_author_id}")
        assert first_inspection.status_code == 200, first_inspection.text
        assert first_inspection.json()["freshness"] == "current"
        assert first_inspection.json()["integrity"] == "complete"
        # Used platform stays fixed while an unused platform remains editable.
        updated = client.put(
            "/api/v1/settings/output",
            json={
                "expected_revision": 1,
                "shared_root": str(new_shared_root),
                "platform_overrides": {"dy": str(dy_override)},
                "layout": "platform_subdirectories",
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["revision"] == 2
        assert not dy_override.exists()
        rejected = client.put(
            "/api/v1/settings/output",
            json={
                "expected_revision": 2,
                "shared_root": str(tmp_path / "must-not-move"),
                "platform_overrides": {},
                "layout": "platform_subdirectories",
            },
        )
        assert rejected.status_code == 409, rejected.text
        assert rejected.json()["detail"] == "output_directory_migration_required"
        second_job_id, second_author_id = _text_pipeline(database, "independent-worker")
        independent_database = Database(settings.resolved_database_url)
        try:
            independent_worker = _real_worker(independent_database, settings, "new-worker-stale-env")
            second = asyncio.run(independent_worker.run_once(worker_id="independent-worker-run"))
            assert second.job_id == second_job_id and second.status == "succeeded", second
        finally:
            independent_database.dispose()
        second_inspection = client.get(f"/api/v1/library/{second_author_id}")
        assert second_inspection.status_code == 200, second_inspection.text
        assert second_inspection.json()["freshness"] == "current"
        assert second_inspection.json()["integrity"] == "complete"
        assert client.get("/api/v1/settings/output").json()["revision"] == 2
    assert len(list((new_shared_root / "bili").rglob("tvshow.nfo"))) == 2
    bodies = list((new_shared_root / "bili").rglob("body.txt"))
    assert len(bodies) == 2
    assert all(path.read_text(encoding="utf-8") == "图文归档内容" for path in bodies)
    assert not settings.export_dir.exists()
    assert not (tmp_path / "must-not-move").exists()


def test_bound_root_blocks_change_before_first_file_write(database: Database, tmp_path: Path) -> None:
    subscription_id, account_id, _asset_id = support._seed_direct_asset(database)
    settings = _settings(tmp_path, database)
    first_service = OutputDirectoryService(database, settings)
    independent_database = Database(settings.resolved_database_url)
    observations: list[str] = []
    requests: list[str] = []
    try:
        second_service = OutputDirectoryService(independent_database, settings)

        def try_change_after_binding() -> None:
            current = second_service.get_policy()
            with pytest.raises(OutputDirectoryError) as rejected:
                second_service.update(
                    expected_revision=current["revision"],
                    shared_root=str(tmp_path / "changed-inflight"),
                    platform_overrides={},
                    layout="platform_subdirectories",
                )
            assert rejected.value.code == "output_directory_migration_required"
            observations.append("bound-before-downloading")

        executor = SubscriptionPipelineExecutor(
            database,
            _config(settings, first_service.bind_author_root, requests, on_download=try_change_after_binding),
        )
        outcome = executor.run(
            subscription_id, expected_account_id=account_id, expected_platform="bili", worker_id="immutable-binding"
        )
    finally:
        independent_database.dispose()
    assert observations == ["bound-before-downloading"]
    assert (settings.export_dir / "bili" / outcome.export.output_path / "tvshow.nfo").is_file()
    assert not (tmp_path / "changed-inflight").exists()
