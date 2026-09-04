"""Current-publication authority for media-server item selectors."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from media_sync.application.emby import (
    EmbyExportOutcome,
    EmbyExportRequest,
    EmbyExportService,
    emby_export_natural_key,
)
from media_sync.application.media_server_publication import MediaServerPublicationResolver
from media_sync.config import MediaServerProfile, Settings
from media_sync.exporters.emby import EmbyExporter, ExportAuthor, PublishedIdentity, PublishedTreeInspection
from media_sync.infrastructure.db import AuthorRepository, AuthorUpsert, ContentUpsert, Database
from media_sync.infrastructure.db.models import Content, Job
from media_sync.ports.media_server import MediaServerError

NOW = datetime(2026, 9, 5, 1, 2, 3, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'media-server-publication.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _profile(server_path: str) -> MediaServerProfile:
    profile = Settings(
        media_server_provider="emby",
        media_server_base_url="http://127.0.0.1:8096",
        media_server_library_id="library",
        media_server_api_key_secret_ref="env:SERVER_KEY",
        media_server_library_path=server_path,
        media_server_allowed_cidrs=("127.0.0.1/32",),
        media_server_operations_enabled=True,
        _env_file=None,
    ).media_server_profile
    assert profile is not None
    return profile


def _seed_author(
    database: Database,
    *,
    remote_id: str = "private-remote-author-sentinel",
    content_count: int = 1,
) -> str:
    contents = tuple(
        ContentUpsert(
            remote_id=f"post-{index:04d}",
            remote_type="note",
            kind="text",
            title=f"Published title {index}",
            body=f"Published body {index}",
            published_at=NOW,
        )
        for index in range(content_count)
    )
    with database.session() as session:
        author, _ = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(
                platform="xhs",
                remote_id=remote_id,
                display_name="Publication Author",
                handle="@publication",
            ),
            contents,
            seen_at=NOW,
        )
        return author.id


def _exporter(tmp_path: Path) -> EmbyExporter:
    return EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")


class _RecordingExporter:
    def __init__(
        self,
        delegate: EmbyExporter,
        *,
        after_complete: Callable[[], None] | None = None,
    ) -> None:
        self.delegate = delegate
        self.starts: list[int] = []
        self._after_complete = after_complete

    @property
    def coordination_scope(self) -> str:
        return self.delegate.coordination_scope

    def inspect_published(
        self,
        author: ExportAuthor,
        expected_identity: PublishedIdentity,
        *,
        start_index: int,
        limit: int,
        max_bytes: int,
        deadline: float,
        monotonic: Callable[[], float],
    ) -> PublishedTreeInspection:
        self.starts.append(start_index)
        result = self.delegate.inspect_published(
            author,
            expected_identity,
            start_index=start_index,
            limit=limit,
            max_bytes=max_bytes,
            deadline=deadline,
            monotonic=monotonic,
        )
        callback = self._after_complete
        if result.next_index == result.managed_file_count and callback is not None:
            self._after_complete = None
            callback()
        return result


def _publish(database: Database, exporter: EmbyExporter, author_id: str) -> EmbyExportOutcome:
    return EmbyExportService(database, exporter, clock=lambda: NOW).export_author(
        EmbyExportRequest(author_id, "publication-resolver-test")
    )


def test_resolver_returns_stable_repr_safe_posix_and_windows_targets(
    database: Database,
    tmp_path: Path,
) -> None:
    remote_id = "private-remote-author-sentinel"
    author_id = _seed_author(database, remote_id=remote_id)
    exporter = _exporter(tmp_path)
    outcome = _publish(database, exporter, author_id)
    recording = _RecordingExporter(exporter)

    posix_resolver = MediaServerPublicationResolver(database, recording, _profile("/private/server/library"))
    posix = posix_resolver.resolve(author_id)
    repeated = posix_resolver.resolve(author_id)
    windows = MediaServerPublicationResolver(database, recording, _profile(r"C:\Private\ServerLibrary")).resolve(
        author_id
    )

    assert posix.author_id == author_id
    assert posix.publication_job_id == outcome.job_id
    assert posix.provider_key == "media-sync-xhs-creator"
    assert posix.provider_value == remote_id
    assert posix.server_path_style == "posix"
    assert posix.server_path == f"/private/server/library/{posix.author_relative_directory}"
    assert windows.server_path_style == "windows"
    assert windows.server_path == f"C:\\Private\\ServerLibrary\\{windows.author_relative_directory}"
    assert windows.publication_fingerprint == posix.publication_fingerprint
    assert repeated.publication_fingerprint == posix.publication_fingerprint
    assert repeated.selector_fingerprint == posix.selector_fingerprint
    assert windows.selector_fingerprint != posix.selector_fingerprint
    assert len(posix.publication_fingerprint) == 64
    assert len(posix.selector_fingerprint) == 64
    assert recording.starts == [0, 0, 0]

    rendered = repr(posix)
    assert remote_id not in rendered
    assert posix.author_relative_directory not in rendered
    assert "/private/server/library" not in rendered
    assert "media-sync-xhs-creator" in rendered


def test_resolver_rejects_invalid_missing_and_outdated_authority_before_inspection(
    database: Database,
    tmp_path: Path,
) -> None:
    exporter = _exporter(tmp_path)
    recording = _RecordingExporter(exporter)
    resolver = MediaServerPublicationResolver(database, recording, _profile("/srv/media"))

    for author_id in (
        "not-an-author-uuid",
        " 00000000-0000-0000-0000-000000000001",
        "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",
        "00000000-0000-0000-0000-000000000001",
    ):
        with pytest.raises(MediaServerError) as raised:
            resolver.resolve(author_id)
        assert raised.value.code == "media_server_publication_not_ready"

    author_id = _seed_author(database)
    with pytest.raises(MediaServerError) as unpublished:
        resolver.resolve(author_id)
    assert unpublished.value.code == "media_server_publication_not_ready"

    _publish(database, exporter, author_id)
    with pytest.raises(MediaServerError) as noncanonical:
        resolver.resolve(f" {author_id}")
    assert noncanonical.value.code == "media_server_publication_not_ready"
    with database.session() as session:
        content = session.scalar(select(Content).where(Content.author_id == author_id))
        assert content is not None
        content.title = "Changed after publication"
    with pytest.raises(MediaServerError) as outdated:
        resolver.resolve(author_id)
    assert outdated.value.code == "media_server_publication_not_ready"
    assert recording.starts == []


def test_resolver_requires_the_hardened_tree_inspection_to_succeed(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id = _seed_author(database)
    exporter = _exporter(tmp_path)
    outcome = _publish(database, exporter, author_id)
    (tmp_path / "library" / outcome.output_path / "source.json").write_bytes(b"tampered")
    recording = _RecordingExporter(exporter)

    with pytest.raises(MediaServerError) as raised:
        MediaServerPublicationResolver(database, recording, _profile("/srv/media")).resolve(author_id)

    assert raised.value.code == "media_server_publication_not_ready"
    assert recording.starts == [0]


def test_resolver_rejects_ambiguous_successful_publication_chain_before_inspection(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id = _seed_author(database)
    exporter = _exporter(tmp_path)
    outcome = _publish(database, exporter, author_id)
    with database.session() as session:
        first = session.get(Job, outcome.job_id)
        assert first is not None
        scope = str(first.payload["publication_scope"])
        source = "f" * 64
        session.add(
            Job(
                job_type="export.emby",
                natural_key=emby_export_natural_key(author_id, scope, outcome.output_path, source, None),
                payload={
                    "schema_version": 1,
                    "author_id": author_id,
                    "exporter": "emby",
                    "exporter_version": "emby-jellyfin-v1",
                    "publication_scope": scope,
                    "output_path": outcome.output_path,
                    "source_fingerprint": source,
                    "predecessor_job_id": None,
                    "result": {
                        "schema_version": 1,
                        "tree_sha256": "e" * 64,
                        "manifest_sha256": "d" * 64,
                        "managed_file_count": 0,
                    },
                },
                status="succeeded",
                attempts=1,
                max_attempts=1,
                available_at=NOW,
                finished_at=NOW,
            )
        )
    recording = _RecordingExporter(exporter)

    with pytest.raises(MediaServerError) as raised:
        MediaServerPublicationResolver(database, recording, _profile("/srv/media")).resolve(author_id)

    assert raised.value.code == "media_server_publication_not_ready"
    assert recording.starts == []


def test_resolver_detects_publication_identity_change_after_complete_inspection(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id = _seed_author(database)
    exporter = _exporter(tmp_path)
    outcome = _publish(database, exporter, author_id)

    def change_identity() -> None:
        with database.session() as session:
            job = session.get(Job, outcome.job_id)
            assert job is not None
            payload = dict(job.payload)
            stored_result = payload.get("result")
            assert isinstance(stored_result, dict)
            result = dict(stored_result)
            result["tree_sha256"] = "f" * 64
            payload["result"] = result
            job.payload = payload

    recording = _RecordingExporter(exporter, after_complete=change_identity)

    with pytest.raises(MediaServerError) as raised:
        MediaServerPublicationResolver(database, recording, _profile("/srv/media")).resolve(author_id)

    assert raised.value.code == "media_server_publication_changed"
    assert recording.starts == [0]


def test_resolver_verifies_every_page_of_a_large_manifest(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id = _seed_author(database, content_count=43)
    exporter = _exporter(tmp_path)
    _publish(database, exporter, author_id)
    recording = _RecordingExporter(exporter)

    target = MediaServerPublicationResolver(database, recording, _profile("/srv/media")).resolve(author_id)

    assert target.managed_file_count == 131
    assert recording.starts == [0, 128]


def test_resolver_rejects_mixed_server_path_before_filesystem_inspection(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id = _seed_author(database)
    exporter = _exporter(tmp_path)
    _publish(database, exporter, author_id)
    recording = _RecordingExporter(exporter)

    with pytest.raises(MediaServerError) as raised:
        MediaServerPublicationResolver(database, recording, _profile(r"/srv/media\mixed")).resolve(author_id)

    assert raised.value.code == "media_server_publication_not_ready"
    assert recording.starts == []


def test_resolver_honors_a_caller_absolute_deadline_before_inspection(
    database: Database,
    tmp_path: Path,
) -> None:
    author_id = _seed_author(database)
    exporter = _exporter(tmp_path)
    _publish(database, exporter, author_id)
    recording = _RecordingExporter(exporter)
    resolver = MediaServerPublicationResolver(
        database,
        recording,
        _profile("/srv/media"),
        monotonic=lambda: 10.0,
    )

    with pytest.raises(MediaServerError) as raised:
        resolver.resolve(author_id, deadline=9.0)

    assert raised.value.code == "media_server_publication_not_ready"
    assert recording.starts == []
