"""Persistent shared roots, read-only safety checks and SQLite CAS races."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from media_sync.application import output_directories as module
from media_sync.application.output_directories import OutputDirectoryError, OutputDirectoryService
from media_sync.config import Settings
from media_sync.exporters.emby import EmbyExporter
from media_sync.infrastructure.db import (
    Author,
    AuthorOutputBinding,
    Content,
    Database,
    ExportRecord,
    Job,
    LibraryOutputPolicy,
    upgrade_database,
)
from media_sync.infrastructure.db.models import PLATFORMS


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        job_dir=tmp_path / "jobs",
        export_dir=tmp_path / "media",
        secret_file_dir=tmp_path / "external-secrets",
        mediacrawler_runtime_dir=tmp_path / "runtime",
        mediacrawler_lock_path=tmp_path / "repository" / "upstreams.lock.json",
        _env_file=None,
    )


@pytest.fixture
def database(settings: Settings) -> Iterator[Database]:
    value = Database(settings.resolved_database_url)
    upgrade_database(value.url)
    try:
        yield value
    finally:
        value.dispose()


def _author(database: Database, platform: str = "bili") -> str:
    with database.session() as session:
        author = Author(platform=platform, remote_id=uuid4().hex, display_name="Synthetic")
        session.add(author)
        session.flush()
        return author.id


def _canonical(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def test_get_preview_and_resolve_are_read_only_with_seven_platform_defaults(
    database: Database, settings: Settings
) -> None:
    service = OutputDirectoryService(database, settings)
    author = _author(database)
    policy = service.get_policy()
    assert policy == {
        "revision": 0,
        "initialized": False,
        "shared_root": _canonical(settings.export_dir),
        "layout": "platform_subdirectories",
        "platform_overrides": dict.fromkeys(sorted(PLATFORMS)),
        "effective_roots": {platform: _canonical(settings.export_dir / platform) for platform in sorted(PLATFORMS)},
        "protected_platforms": [],
    }
    assert service.resolve_author_root(author) == settings.export_dir / "bili"
    assert service.preview(str(settings.export_dir), {}, "platform_subdirectories") == policy
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(LibraryOutputPolicy)) == 0
        assert session.scalar(select(func.count()).select_from(AuthorOutputBinding)) == 0
    assert not settings.export_dir.exists()


@pytest.mark.parametrize("platform", sorted(PLATFORMS))
def test_platform_overrides_persist_across_independent_process_settings(
    database: Database, settings: Settings, platform: str
) -> None:
    selected = settings.export_dir.parent / "custom" / platform
    service = OutputDirectoryService(database, settings)
    policy = service.update(0, str(settings.export_dir), {platform: str(selected)}, "platform_subdirectories")
    assert policy["revision"] == 1 and policy["initialized"] is True
    changed_settings = settings.model_copy(update={"export_dir": settings.export_dir.parent / "wrong-startup-default"})
    independent = Database(database.url)
    try:
        reader = OutputDirectoryService(independent, changed_settings)
        assert reader.get_policy() == policy
        assert reader.resolve_author_root(_author(database, platform)) == selected
    finally:
        independent.dispose()
    assert not selected.exists() and not settings.export_dir.exists()


def test_binding_is_immutable_and_only_affected_platform_changes_are_blocked(
    database: Database, settings: Settings
) -> None:
    service = OutputDirectoryService(database, settings)
    author = _author(database)
    root = service.bind_author_root(author)
    assert root == settings.export_dir / "bili"
    assert service.bind_author_root(author) == root
    assert service.get_policy()["protected_platforms"] == ["bili"]
    with pytest.raises(OutputDirectoryError) as caught:
        service.update(0, str(settings.export_dir.parent / "new-media"), {}, "platform_subdirectories")
    assert caught.value.code == "output_directory_migration_required"
    assert caught.value.platforms == ("bili",)
    assert service.get_policy()["revision"] == 0
    policy = service.update(
        0, str(settings.export_dir), {"xhs": str(settings.export_dir.parent / "xhs")}, "platform_subdirectories"
    )
    assert policy["revision"] == 1
    assert service.resolve_author_root(author) == root
    with database.session() as session:
        binding = session.get(AuthorOutputBinding, author)
        assert binding is not None and binding.policy_revision == 0
        assert session.scalar(select(func.count()).select_from(AuthorOutputBinding)) == 1
    assert not root.exists()


@pytest.mark.parametrize("legacy", ["export_record", "publication_job"])
def test_legacy_output_preserves_flat_scope_without_creating_or_moving_files(
    database: Database, settings: Settings, legacy: str
) -> None:
    author = _author(database)
    with database.session() as session:
        if legacy == "export_record":
            content = Content(author_id=author, platform="bili", remote_id="123", kind="video")
            session.add(content)
            session.flush()
            session.add(
                ExportRecord(
                    content_id=content.id, exporter_version="v1", source_fingerprint="a" * 64, output_path="old-author"
                )
            )
        else:
            session.add(
                Job(job_type="export.emby", natural_key="legacy", payload={"author_id": author}, status="succeeded")
            )
    service = OutputDirectoryService(database, settings)
    assert service.get_policy()["layout"] == "legacy_flat"
    assert service.resolve_author_root(author) == settings.export_dir
    with pytest.raises(OutputDirectoryError, match="migration_required"):
        service.update(0, str(settings.export_dir), {}, "platform_subdirectories")
    with database.session() as session:
        assert session.get(LibraryOutputPolicy, 1) is None
    assert service.bind_author_root(author) == settings.export_dir
    assert service.get_policy()["layout"] == "legacy_flat"
    assert not settings.export_dir.exists()


@pytest.mark.parametrize(
    "value",
    [
        "relative/media",
        "../media",
        "https://example.invalid/media",
        "",
        " /media",
        "/media\nsecret",
        "/media/../secret",
        "/media/./files",
        "a" * 4097,
    ],
)
def test_invalid_path_syntax_is_rejected_without_echoing_input(
    database: Database, settings: Settings, value: str
) -> None:
    with pytest.raises(OutputDirectoryError) as caught:
        OutputDirectoryService(database, settings).preview(value, {}, "platform_subdirectories")
    assert caught.value.code == "output_directory_invalid"
    assert str(caught.value) == "output_directory_invalid"


@pytest.mark.parametrize(
    "private",
    [
        "state",
        "archive",
        "jobs",
        "external-secrets",
        "runtime",
        "repository",
        "repository/src",
        "repository/tests",
        "repository/docs",
        "repository/web",
        "repository/scripts",
        "repository/.git",
        "repository/.upstream",
    ],
)
def test_protected_roots_and_their_children_are_rejected(database: Database, settings: Settings, private: str) -> None:
    service = OutputDirectoryService(database, settings)
    selected = settings.export_dir.parent / private
    for path in (selected, selected / "library"):
        if private == "repository" and path != selected:
            continue  # A named repository data directory is intentionally supported.
        with pytest.raises(OutputDirectoryError, match="output_directory_unsafe"):
            service.preview(str(path), {}, "platform_subdirectories")


def test_repository_exports_data_directory_is_allowed(database: Database, settings: Settings) -> None:
    selected = settings.mediacrawler_lock_path.parent / "exports"
    policy = OutputDirectoryService(database, settings).preview(str(selected), {}, "platform_subdirectories")
    assert policy["shared_root"] == _canonical(selected)
    assert not selected.exists()


def test_native_system_directories_are_never_output_targets(database: Database, settings: Settings) -> None:
    if os.name == "nt":
        targets = [
            Path(os.environ.get("SYSTEMROOT", "C:/Windows")),
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")),
        ]
    else:
        targets = [Path("/etc"), Path("/usr"), Path("/proc"), Path("/sys"), Path("/dev")]
    service = OutputDirectoryService(database, settings)
    for target in targets:
        for candidate in (target, target / "media-sync-library"):
            with pytest.raises(OutputDirectoryError, match="output_directory_unsafe"):
                service.preview(str(candidate), {}, "platform_subdirectories")


@pytest.mark.parametrize("matches", [False, True])
def test_bootstrap_checks_known_legacy_publication_scope_before_binding(
    database: Database, settings: Settings, matches: bool
) -> None:
    author = _author(database)
    previous = settings.export_dir if matches else settings.export_dir.parent / "previous-media"
    scope = EmbyExporter(previous).coordination_scope
    with database.session() as session:
        session.add(
            Job(
                job_type="export.emby",
                natural_key="known-legacy",
                payload={"author_id": author, "publication_scope": scope},
                status="succeeded",
            )
        )
    service = OutputDirectoryService(database, settings)
    if matches:
        assert service.bind_author_root(author) == previous
    else:
        for operation in (service.get_policy, lambda: service.bind_author_root(author)):
            with pytest.raises(OutputDirectoryError, match="output_directory_migration_required") as caught:
                operation()
            assert caught.value.platforms == ("bili",)
        with database.session() as session:
            assert session.get(LibraryOutputPolicy, 1) is None
            assert session.get(AuthorOutputBinding, author) is None
    assert not settings.export_dir.exists() and not previous.exists()


def test_external_sqlite_database_and_ancestor_are_protected(database: Database, settings: Settings) -> None:
    external = settings.export_dir.parent / "external-db"
    other = Database(f"sqlite:///{(external / 'state.sqlite3').as_posix()}")
    try:
        upgrade_database(other.url)
        with pytest.raises(OutputDirectoryError, match="output_directory_unsafe"):
            OutputDirectoryService(other, settings).preview(str(external), {}, "platform_subdirectories")
    finally:
        other.dispose()


@pytest.mark.parametrize("layout", ["legacy_flat", "platform_subdirectories"])
def test_overlapping_platform_roots_are_rejected(database: Database, settings: Settings, layout: str) -> None:
    root = settings.export_dir.parent / "custom"
    with pytest.raises(OutputDirectoryError, match="output_directory_overlap"):
        OutputDirectoryService(database, settings).preview(
            str(settings.export_dir), {"bili": str(root), "xhs": str(root / "nested")}, layout
        )


def test_only_legacy_layout_allows_equal_effective_roots(database: Database, settings: Settings) -> None:
    service = OutputDirectoryService(database, settings)
    assert service.preview(str(settings.export_dir), {}, "legacy_flat")["layout"] == "legacy_flat"
    selected = str(settings.export_dir.parent / "same")
    with pytest.raises(OutputDirectoryError, match="output_directory_overlap"):
        service.preview(str(settings.export_dir), {"bili": selected, "xhs": selected}, "platform_subdirectories")


def test_symlink_ancestor_and_dangling_link_are_rejected(database: Database, settings: Settings) -> None:
    parent = settings.export_dir.parent
    target = parent / "actual"
    target.mkdir()
    link = parent / "alias"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable for this Windows user")
    service = OutputDirectoryService(database, settings)
    with pytest.raises(OutputDirectoryError, match="output_directory_unsafe"):
        service.preview(str(link / "new-root"), {}, "platform_subdirectories")
    dangling = parent / "dangling"
    dangling.symlink_to(parent / "missing", target_is_directory=True)
    with pytest.raises(OutputDirectoryError, match="output_directory_unsafe"):
        service.preview(str(dangling / "new-root"), {}, "platform_subdirectories")


def test_reparse_ancestor_is_rejected_by_lstat_metadata(
    database: Database, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_lstat = Path.lstat
    target = settings.export_dir.parent

    def lstat(path: Path, **kwargs: object) -> object:
        actual = real_lstat(path, **kwargs)
        if path == target:
            return SimpleNamespace(st_mode=actual.st_mode, st_file_attributes=0x400)
        return actual

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(OutputDirectoryError, match="output_directory_unsafe"):
        module._validate_existing_ancestors(settings.export_dir)


def test_persisted_root_is_revalidated_before_use(database: Database, settings: Settings) -> None:
    service = OutputDirectoryService(database, settings)
    author = _author(database)
    service.bind_author_root(author)
    settings.export_dir.write_text("not a directory", encoding="utf-8")
    with pytest.raises(OutputDirectoryError, match="output_directory_unsafe"):
        service.resolve_author_root(author)


@pytest.mark.parametrize("expected", [True, -1, 1.0, "0", 9_007_199_254_740_991])
def test_revision_requires_bounded_exact_integer(database: Database, settings: Settings, expected: object) -> None:
    with pytest.raises(OutputDirectoryError, match="output_directory_invalid"):
        OutputDirectoryService(database, settings).update(expected, str(settings.export_dir), {}, "legacy_flat")  # type: ignore[arg-type]


def test_simultaneous_first_updates_have_one_cas_winner(database: Database, settings: Settings) -> None:
    gate = threading.Barrier(2)

    def attempt(index: int) -> str:
        own_database = Database(database.url)
        try:
            service = OutputDirectoryService(own_database, settings)
            gate.wait(timeout=5)
            try:
                service.update(0, str(settings.export_dir.parent / f"candidate-{index}"), {}, "platform_subdirectories")
            except OutputDirectoryError as error:
                return error.code
            return "saved"
        finally:
            own_database.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, (1, 2)))
    assert sorted(results) == ["output_directory_conflict", "saved"]
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(LibraryOutputPolicy)) == 1
        assert session.get(LibraryOutputPolicy, 1).revision == 1


def test_bind_save_race_never_redirects_bound_author(database: Database, settings: Settings) -> None:
    service = OutputDirectoryService(database, settings)
    author = _author(database)
    gate = threading.Barrier(2)
    new_root = settings.export_dir.parent / "changed"

    def bind() -> Path:
        gate.wait(timeout=5)
        return service.bind_author_root(author)

    def save() -> str:
        gate.wait(timeout=5)
        try:
            service.update(0, str(new_root), {}, "platform_subdirectories")
        except OutputDirectoryError as error:
            return error.code
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        bound = executor.submit(bind)
        saved = executor.submit(save)
        result = saved.result(timeout=10)
        path = bound.result(timeout=10)
    assert result in {"saved", "output_directory_migration_required"}
    assert path == (new_root if result == "saved" else settings.export_dir) / "bili"
    assert service.resolve_author_root(author) == path


@pytest.mark.parametrize("scenario", ["first_update_cas", "bind_save"])
def test_real_postgresql_output_policy_races(settings: Settings, scenario: str) -> None:
    raw_url = os.environ.get("MEDIA_SYNC_TEST_POSTGRESQL_URL")
    if not raw_url:
        pytest.skip("MEDIA_SYNC_TEST_POSTGRESQL_URL is not set; real PostgreSQL race test NOT_RUN")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("MEDIA_SYNC_TEST_POSTGRESQL_URL must identify PostgreSQL")
    url = url.set(drivername="postgresql+psycopg")
    admin = Database(url.render_as_string(hide_password=False))
    schema = f"media_sync_output_{uuid4().hex}"
    scoped: Database | None = None
    created = False
    try:
        with admin.engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        created = True
        options = f"-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=10000"
        scoped_url = url.update_query_dict({"options": options}, append=False)
        scoped = Database(scoped_url.render_as_string(hide_password=False))
        scoped.create_schema()
        if scenario == "first_update_cas":
            test_simultaneous_first_updates_have_one_cas_winner(scoped, settings)
        else:
            test_bind_save_race_never_redirects_bound_author(scoped, settings)
    finally:
        if scoped is not None:
            scoped.dispose()
        if created:
            with admin.engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        admin.dispose()
