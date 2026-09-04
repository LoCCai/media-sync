"""Database-authorized, read-only managed-library inspection contracts."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import func, select

from media_sync.application.emby import EmbyExportRequest, EmbyExportService
from media_sync.application.library import LibraryInspectionError, LibraryInspectionService
from media_sync.exporters.emby import EmbyExporter
from media_sync.infrastructure.db import (
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    Database,
)
from media_sync.infrastructure.db.models import ExportRecord, Job

NOW = datetime(2026, 9, 5, 1, 2, 3, tzinfo=UTC)
CURSOR_KEY = b"library-inspection-test-key-v1!!"


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'library.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_author(database: Database, *, with_content: bool = True) -> str:
    with database.session() as session:
        author, _ = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(
                platform="xhs",
                remote_id="library-author",
                display_name="Library Author",
                handle="@library",
                raw={"private": "do-not-return"},
            ),
            (
                [
                    ContentUpsert(
                        remote_id="post-1",
                        remote_type="note",
                        kind="text",
                        title="Published title",
                        body="Published body",
                        published_at=NOW,
                        canonical_url="https://example.invalid/private-source",
                    )
                ]
                if with_content
                else []
            ),
            seen_at=NOW,
        )
        return author.id


def _components(
    database: Database,
    tmp_path: Path,
    *,
    fault: object | None = None,
) -> tuple[EmbyExporter, EmbyExportService, LibraryInspectionService]:
    exporter = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=fault,  # type: ignore[arg-type]
    )
    return (
        exporter,
        EmbyExportService(database, exporter, clock=lambda: NOW),
        LibraryInspectionService(database, exporter, cursor_key=CURSOR_KEY),
    )


def test_paginated_inspection_reaches_end_without_claiming_whole_tree_completion(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id = _seed_author(database)
    _, export_service, library = _components(database, tmp_path)
    published = export_service.export_author(EmbyExportRequest(author_id, "publisher"))
    unmanaged = tmp_path / "library" / published.output_path / "private-unmanaged-name.txt"
    unmanaged.write_bytes(b"preserve")

    result = library.inspect(author_id, limit=2, max_bytes=1_000_000, deadline_seconds=10)
    observed_paths = [item.relative_path for item in result.files]
    while result.page.next_cursor is not None:
        assert result.integrity == "page_verified"
        result = library.inspect(
            author_id,
            cursor=result.page.next_cursor,
            limit=2,
            max_bytes=1_000_000,
            deadline_seconds=10,
        )
        observed_paths.extend(item.relative_path for item in result.files)

    assert result.freshness == "current"
    assert result.integrity == "page_verified"
    assert result.page.complete is False
    assert result.page.next_cursor is None
    assert result.page.next_index == result.publication.managed_file_count  # type: ignore[union-attr]
    assert len(observed_paths) == len(set(observed_paths))
    assert len(observed_paths) == result.publication.managed_file_count  # type: ignore[union-attr]
    assert "private-unmanaged-name.txt" not in repr(result)
    assert unmanaged.read_bytes() == b"preserve"

    complete = library.inspect(author_id, limit=128, max_bytes=1_000_000, deadline_seconds=10)
    assert complete.integrity == "complete"
    assert complete.page.complete is True
    assert complete.page.start_index == 0
    assert complete.page.next_cursor is None


def test_cursor_is_tamper_evident_and_stale_after_new_publication(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id = _seed_author(database)
    _, export_service, library = _components(database, tmp_path)
    export_service.export_author(EmbyExportRequest(author_id, "publisher-a"))
    first = library.inspect(author_id, limit=1, max_bytes=1_000_000, deadline_seconds=10)
    assert first.page.next_cursor is not None
    cursor = first.page.next_cursor
    index = len(cursor) // 2
    tampered = cursor[:index] + ("A" if cursor[index] != "A" else "B") + cursor[index + 1 :]

    with pytest.raises(LibraryInspectionError) as invalid:
        library.inspect(author_id, cursor=tampered, max_bytes=1_000_000, deadline_seconds=10)
    assert invalid.value.code == "library_cursor_invalid"

    with database.session() as session:
        content = session.scalar(select(ExportRecord.content_id).limit(1))
        assert content is not None
        from media_sync.infrastructure.db.models import Content

        stored = session.get(Content, content)
        assert stored is not None
        stored.title = "A newer snapshot"
    export_service.export_author(EmbyExportRequest(author_id, "publisher-b"))

    with pytest.raises(LibraryInspectionError) as stale:
        library.inspect(author_id, cursor=cursor, max_bytes=1_000_000, deadline_seconds=10)
    assert stale.value.code == "library_cursor_stale"


def test_freshness_is_independent_from_published_tree_integrity(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id = _seed_author(database)
    _, export_service, library = _components(database, tmp_path)
    export_service.export_author(EmbyExportRequest(author_id, "publisher"))

    with database.session() as session:
        from media_sync.infrastructure.db.models import Content

        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        content.title = "Not published yet"
    outdated = library.inspect(author_id, max_bytes=1_000_000, deadline_seconds=10)
    assert (outdated.freshness, outdated.integrity) == ("outdated", "complete")

    with database.session() as session:
        from media_sync.infrastructure.db.models import Content

        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        AssetRepository(session).upsert_for_content(
            content.id,
            AssetUpsert(
                platform="xhs",
                content_remote_type="note",
                content_remote_id=content.remote_id,
                kind="image",
                position=0,
                remote_id="not-verified",
                source_url="https://example.invalid/private-asset",
            ),
        )
    blocked = library.inspect(author_id, max_bytes=1_000_000, deadline_seconds=10)
    assert (blocked.freshness, blocked.integrity) == ("blocked", "complete")
    assert blocked.freshness_reason_code == "library_snapshot_blocked"


def test_not_published_and_empty_publication_are_distinct(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id = _seed_author(database, with_content=False)
    _, export_service, library = _components(database, tmp_path)

    missing = library.inspect(author_id, max_bytes=1_000_000, deadline_seconds=10)
    assert (missing.freshness, missing.integrity, missing.publication) == (
        "not_published",
        "not_available",
        None,
    )

    export_service.export_author(EmbyExportRequest(author_id, "empty-publisher"))
    empty = library.inspect(author_id, max_bytes=1_000_000, deadline_seconds=10)
    assert (empty.freshness, empty.integrity) == ("current", "complete")
    assert empty.publication is not None and empty.publication.managed_file_count > 0
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ExportRecord)) == 0


def test_unpublished_unexportable_snapshot_is_blocked_without_export_action(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id = _seed_author(database)
    with database.session() as session:
        from media_sync.infrastructure.db.models import Content

        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        AssetRepository(session).upsert_for_content(
            content.id,
            AssetUpsert(
                platform="xhs",
                content_remote_type="note",
                content_remote_id=content.remote_id,
                kind="image",
                position=0,
                remote_id="not-verified-before-first-export",
                source_url="https://example.invalid/private-asset",
            ),
        )
    _, _, library = _components(database, tmp_path)

    blocked = library.inspect(author_id, max_bytes=1_000_000, deadline_seconds=10)

    assert (blocked.freshness, blocked.integrity) == ("blocked", "not_available")
    assert blocked.freshness_reason_code == "library_snapshot_blocked"
    assert blocked.allowed_actions == ()


def test_byte_budget_never_promotes_a_partial_file_to_verified(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id = _seed_author(database)
    _, export_service, library = _components(database, tmp_path)
    export_service.export_author(EmbyExportRequest(author_id, "publisher"))

    result = library.inspect(author_id, max_bytes=1, deadline_seconds=10)

    assert result.integrity == "budget_exhausted"
    assert result.integrity_reason_code == "library_inspection_byte_budget_exhausted"
    assert result.page.bytes_read == 1
    assert result.page.next_index == 0
    assert result.files == ()
    assert result.page.next_cursor is not None


def test_managed_drift_is_safe_and_inspection_does_not_mutate_database(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id = _seed_author(database)
    _, export_service, library = _components(database, tmp_path)
    published = export_service.export_author(EmbyExportRequest(author_id, "publisher"))
    healthy = library.inspect(author_id, limit=1, max_bytes=1_000_000, deadline_seconds=10)
    target = tmp_path / "library" / published.output_path / healthy.files[0].relative_path
    target.write_bytes(b"same tree authority cannot come from disk alone")
    with database.session() as session:
        before = (
            session.scalar(select(func.count()).select_from(Job)),
            session.scalar(select(func.count()).select_from(ExportRecord)),
        )

    drifted = library.inspect(author_id, max_bytes=1_000_000, deadline_seconds=10)

    assert drifted.integrity == "drifted"
    assert drifted.integrity_reason_code == "library_tree_drifted"
    assert drifted.files == () and drifted.page.complete is False
    assert str(tmp_path) not in repr(drifted)
    assert "private-source" not in repr(drifted)
    with database.session() as session:
        after = (
            session.scalar(select(func.count()).select_from(Job)),
            session.scalar(select(func.count()).select_from(ExportRecord)),
        )
    assert after == before


def test_process_wide_single_flight_fails_busy_without_waiting(
    database: Database,
    tmp_path: Path,
) -> None:
    entered = Event()
    release = Event()

    def fault(event: str, _relative_path: str | None) -> None:
        if event == "inspect_file_opened":
            entered.set()
            assert release.wait(timeout=5)

    author_id = _seed_author(database)
    exporter, export_service, first_service = _components(database, tmp_path, fault=fault)
    export_service.export_author(EmbyExportRequest(author_id, "publisher"))
    second_service = LibraryInspectionService(database, exporter, cursor_key=CURSOR_KEY)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            first_service.inspect,
            author_id,
            max_bytes=1_000_000,
            deadline_seconds=10,
        )
        assert entered.wait(timeout=5)
        with pytest.raises(LibraryInspectionError) as busy:
            second_service.inspect(author_id, max_bytes=1_000_000, deadline_seconds=10)
        assert busy.value.code == "library_inspection_busy"
        release.set()
        assert pending.result(timeout=5).integrity == "complete"


@pytest.mark.parametrize(
    ("author_id", "limit", "max_bytes", "deadline", "code"),
    [
        ("not-a-uuid", 1, 1, 1.0, "library_author_invalid"),
        ("00000000-0000-0000-0000-000000000001", 129, 1, 1.0, "library_inspection_invalid"),
        ("00000000-0000-0000-0000-000000000001", 1, -1, 1.0, "library_inspection_invalid"),
        ("00000000-0000-0000-0000-000000000001", 1, 1, -1.0, "library_inspection_invalid"),
    ],
)
def test_request_controls_are_closed_and_bounded(
    database: Database,
    tmp_path: Path,
    author_id: str,
    limit: int,
    max_bytes: int,
    deadline: float,
    code: str,
) -> None:
    _, _, library = _components(database, tmp_path)
    with pytest.raises(LibraryInspectionError) as raised:
        library.inspect(author_id, limit=limit, max_bytes=max_bytes, deadline_seconds=deadline)
    assert raised.value.code == code
