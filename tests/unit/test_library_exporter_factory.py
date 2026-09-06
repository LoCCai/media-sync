"""Author-routed inspection keeps one signing key and one process-wide budget gate."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.orm import object_session
from tests.integration.test_media_server_publication import _RecordingExporter

from media_sync.application.emby import EmbyExportRequest, EmbyExportService
from media_sync.application.library import LibraryInspectionError, LibraryInspectionService
from media_sync.exporters.emby import EmbyExporter
from media_sync.infrastructure.db import AuthorRepository, AuthorUpsert, ContentUpsert, Database
from media_sync.infrastructure.db.models import Author

NOW = datetime(2026, 9, 6, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'factory.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _publish(database: Database, tmp_path: Path, *, platform: str = "xhs") -> tuple[str, EmbyExporter]:
    with database.session() as session:
        author, _ = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(platform=platform, remote_id=f"{platform}-author", display_name="Library Author"),
            [
                ContentUpsert(
                    remote_id=f"{platform}-post",
                    remote_type="content",
                    kind="text",
                    title="Published title",
                    body="Published body",
                    published_at=NOW,
                )
            ],
            seen_at=NOW,
        )
        author_id = author.id
    exporter = EmbyExporter(tmp_path / platform, staging_root=tmp_path / "fixed-private-staging")
    EmbyExportService(database, exporter).export_author(EmbyExportRequest(author_id, "factory-test"))
    return author_id, exporter


@pytest.mark.parametrize("mode", ["neither", "both", "not-callable"])
def test_constructor_accepts_exactly_one_trusted_exporter_source(database: Database, tmp_path: Path, mode: str) -> None:
    exporter = EmbyExporter(tmp_path / "unused")
    arguments: dict[str, Any] = {}
    if mode == "both":
        arguments = {"exporter": exporter, "exporter_factory": lambda _author: exporter}
    elif mode == "not-callable":
        arguments = {"exporter_factory": "not-a-factory"}
    with pytest.raises(LibraryInspectionError) as raised:
        LibraryInspectionService(database, **arguments)
    assert raised.value.code == "library_inspection_invalid"


def test_long_lived_factory_service_keeps_cursors_and_scope_local_between_authors(
    database: Database, tmp_path: Path
) -> None:
    first_id, first_exporter = _publish(database, tmp_path, platform="xhs")
    second_id, second_exporter = _publish(database, tmp_path, platform="bili")
    roots = {"xhs": first_exporter.export_root, "bili": second_exporter.export_root}
    calls: list[tuple[str, str]] = []

    def factory(author: Author) -> EmbyExporter:
        assert object_session(author) is not None
        calls.append((author.id, author.platform))
        # A fresh exporter on every page must not create a fresh cursor key.
        return EmbyExporter(roots[author.platform], staging_root=tmp_path / "fixed-private-staging")

    library = LibraryInspectionService(database, exporter_factory=factory)
    first = library.inspect(first_id, limit=1, max_bytes=1_000_000, deadline_seconds=10)
    second = library.inspect(second_id, limit=1, max_bytes=1_000_000, deadline_seconds=10)
    assert first.publication is not None and second.publication is not None
    assert first.publication.publication_scope == first_exporter.coordination_scope
    assert second.publication.publication_scope == second_exporter.coordination_scope
    assert first.page.next_cursor is not None and second.page.next_cursor is not None
    first_paths = [item.relative_path for item in first.files]
    current = first
    while current.page.next_cursor is not None:
        current = library.inspect(
            first_id, cursor=current.page.next_cursor, limit=1, max_bytes=1_000_000, deadline_seconds=10
        )
        assert current.publication == first.publication
        first_paths.extend(item.relative_path for item in current.files)
    assert len(first_paths) == len(set(first_paths)) == first.publication.managed_file_count
    assert current.page.next_index == first.publication.managed_file_count
    assert current.page.complete is False
    resumed_second = library.inspect(
        second_id, cursor=second.page.next_cursor, limit=1, max_bytes=1_000_000, deadline_seconds=10
    )
    assert resumed_second.page.start_index == 1
    assert resumed_second.publication == second.publication
    assert set(calls) == {(first_id, "xhs"), (second_id, "bili")}
    assert str(tmp_path) not in repr((first, second, current))


def test_cursor_cannot_cross_author_or_new_selected_scope(database: Database, tmp_path: Path) -> None:
    author_id, exporter = _publish(database, tmp_path)
    other_id, other_exporter = _publish(database, tmp_path, platform="bili")
    selected = {author_id: _RecordingExporter(exporter), other_id: _RecordingExporter(other_exporter)}
    library = LibraryInspectionService(database, exporter_factory=lambda author: selected[author.id])
    first = library.inspect(author_id, limit=1, max_bytes=1_000_000, deadline_seconds=10)
    assert first.page.next_cursor is not None
    with pytest.raises(LibraryInspectionError) as different_author:
        library.inspect(other_id, cursor=first.page.next_cursor, max_bytes=1_000_000, deadline_seconds=10)
    assert different_author.value.code == "library_cursor_stale"
    assert selected[other_id].starts == []

    replacement = EmbyExporter(tmp_path / "other-root", staging_root=tmp_path / "fixed-private-staging")
    EmbyExportService(database, replacement).export_author(EmbyExportRequest(author_id, "replacement-test"))
    selected[author_id] = _RecordingExporter(replacement)
    with pytest.raises(LibraryInspectionError) as different_scope:
        library.inspect(author_id, cursor=first.page.next_cursor, max_bytes=1_000_000, deadline_seconds=10)
    assert different_scope.value.code == "library_cursor_stale"
    assert selected[author_id].starts == []


@pytest.mark.parametrize("identifier", ["../private", "C:\\private\\library", str(uuid4())])
def test_factory_never_receives_client_paths_or_missing_database_identities(
    database: Database, identifier: str
) -> None:
    calls: list[Author] = []

    def unexpected(author: Author) -> Any:
        calls.append(author)
        raise AssertionError("unknown identities must not reach routing")

    with pytest.raises(LibraryInspectionError) as raised:
        LibraryInspectionService(database, exporter_factory=unexpected).inspect(
            identifier, max_bytes=1_000_000, deadline_seconds=10
        )
    assert raised.value.code in {"library_author_invalid", "library_author_not_found"}
    assert calls == []


@pytest.mark.parametrize("failure", ["raise", "missing", "invalid-scope"])
def test_factory_failure_is_safe_and_releases_the_global_gate(database: Database, tmp_path: Path, failure: str) -> None:
    author_id, exporter = _publish(database, tmp_path)

    def broken(_author: Author) -> Any:
        if failure == "raise":
            raise RuntimeError("private-host-path-and-credentials")
        if failure == "missing":
            return None
        return type("InvalidScope", (), {"coordination_scope": "bad", "inspect_published": lambda *a: None})()

    with pytest.raises(LibraryInspectionError) as raised:
        LibraryInspectionService(database, exporter_factory=broken).inspect(
            author_id, max_bytes=1_000_000, deadline_seconds=10
        )
    assert raised.value.code == "library_inspection_failed"
    assert "private-host" not in str(raised.value)
    assert raised.value.__cause__ is None
    healthy = LibraryInspectionService(database, exporter).inspect(author_id, max_bytes=1_000_000, deadline_seconds=10)
    assert healthy.integrity == "complete"


def test_factory_resolution_time_and_byte_budget_keep_resumable_bound_cursors(
    database: Database, tmp_path: Path
) -> None:
    author_id, exporter = _publish(database, tmp_path)
    recording = _RecordingExporter(exporter)
    clock = [10.0]
    slow = [True]

    def factory(_author: Author) -> _RecordingExporter:
        if slow[0]:
            clock[0] += 2
        return recording

    library = LibraryInspectionService(database, exporter_factory=factory, monotonic=lambda: clock[0])
    exhausted = library.inspect(author_id, max_bytes=1_000_000, deadline_seconds=1)
    assert exhausted.integrity_reason_code == "library_inspection_deadline_exceeded"
    assert exhausted.page.bytes_read == 0 and exhausted.page.next_cursor is not None
    assert recording.starts == []
    slow[0] = False
    partial = library.inspect(author_id, cursor=exhausted.page.next_cursor, max_bytes=1, deadline_seconds=10)
    assert partial.integrity_reason_code == "library_inspection_byte_budget_exhausted"
    assert partial.page.bytes_read == 1 and partial.page.next_cursor is not None
    complete = library.inspect(author_id, cursor=partial.page.next_cursor, max_bytes=1_000_000, deadline_seconds=10)
    assert complete.integrity == "complete"
    assert complete.publication == exhausted.publication


def test_factory_and_fixed_services_share_single_flight_before_routing(database: Database, tmp_path: Path) -> None:
    author_id, exporter = _publish(database, tmp_path)
    entered, release = Event(), Event()

    def factory(_author: Author) -> EmbyExporter:
        entered.set()
        assert release.wait(timeout=5)
        return exporter

    dynamic = LibraryInspectionService(database, exporter_factory=factory)
    fixed = LibraryInspectionService(database, exporter)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(dynamic.inspect, author_id, max_bytes=1_000_000, deadline_seconds=10)
        try:
            assert entered.wait(timeout=5)
            with pytest.raises(LibraryInspectionError) as busy:
                fixed.inspect(author_id, max_bytes=1_000_000, deadline_seconds=10)
            assert busy.value.code == "library_inspection_busy"
        finally:
            release.set()
        assert pending.result(timeout=5).integrity == "complete"
