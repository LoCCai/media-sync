"""Dynamic local outputs cannot borrow an unrelated fixed server path mapping."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.integration.test_media_server_publication import (
    _exporter,
    _profile,
    _publish,
    _RecordingExporter,
    _seed_author,
)

from media_sync.application.media_server_publication import MediaServerPublicationResolver
from media_sync.infrastructure.db import Database
from media_sync.ports.media_server import MediaServerError


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'publication-scope.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def test_optional_scope_guard_preserves_legacy_target_and_checks_before_and_after_inspection(
    database: Database, tmp_path: Path
) -> None:
    author_id = _seed_author(database)
    exporter = _exporter(tmp_path)
    _publish(database, exporter, author_id)
    recording = _RecordingExporter(exporter)
    profile = _profile("/server/existing-library")
    calls: list[str] = []

    def selected_scope(identifier: str) -> str:
        calls.append(identifier)
        return exporter.coordination_scope

    legacy = MediaServerPublicationResolver(database, recording, profile).resolve(author_id)
    guarded = MediaServerPublicationResolver(database, recording, profile, scope_resolver=selected_scope)
    assert guarded.resolve(author_id) == legacy
    assert guarded.resolve(author_id) == legacy
    assert calls == [author_id] * 4
    assert recording.starts == [0, 0, 0]


@pytest.mark.parametrize("scope", ["a" * 64, "invalid", None, True, "raise"])
def test_unknown_changed_or_unavailable_output_scope_rejects_before_filesystem_inspection(
    database: Database, tmp_path: Path, scope: Any
) -> None:
    author_id = _seed_author(database)
    exporter = _exporter(tmp_path)
    _publish(database, exporter, author_id)
    recording = _RecordingExporter(exporter)
    calls: list[str] = []

    def selected_scope(identifier: str) -> Any:
        calls.append(identifier)
        if scope == "raise":
            raise RuntimeError("private-path-and-credentials")
        return scope

    resolver = MediaServerPublicationResolver(
        database, recording, _profile("/server/existing-library"), scope_resolver=selected_scope
    )
    with pytest.raises(MediaServerError) as raised:
        resolver.resolve(author_id)
    assert raised.value.code == "media_server_publication_not_ready"
    assert raised.value.__cause__ is None
    assert "private-path" not in str(raised.value)
    assert calls == [author_id]
    assert recording.starts == []


@pytest.mark.parametrize("failure", ["changed", "unavailable"])
def test_scope_change_during_inspection_cannot_return_a_stale_server_target(
    database: Database, tmp_path: Path, failure: str
) -> None:
    author_id = _seed_author(database)
    exporter = _exporter(tmp_path)
    _publish(database, exporter, author_id)
    after_inspection = [False]
    calls: list[str] = []

    def selected_scope(identifier: str) -> str:
        calls.append(identifier)
        if after_inspection[0]:
            if failure == "unavailable":
                raise RuntimeError("private-output-resolver-failed")
            return "b" * 64
        return exporter.coordination_scope

    def changed() -> None:
        after_inspection[0] = True

    recording = _RecordingExporter(exporter, after_complete=changed)
    resolver = MediaServerPublicationResolver(
        database, recording, _profile("/server/existing-library"), scope_resolver=selected_scope
    )
    with pytest.raises(MediaServerError) as raised:
        resolver.resolve(author_id)
    assert raised.value.code == "media_server_publication_not_ready"
    assert calls == [author_id, author_id]
    assert recording.starts == [0]


def test_author_specific_scope_gate_does_not_disable_another_legacy_bound_author(
    database: Database, tmp_path: Path
) -> None:
    changed_id = _seed_author(database, remote_id="changed-author")
    legacy_id = _seed_author(database, remote_id="legacy-author", content_count=0)
    exporter = _exporter(tmp_path)
    _publish(database, exporter, changed_id)
    legacy_publication = _publish(database, exporter, legacy_id)
    scopes = {changed_id: "c" * 64, legacy_id: exporter.coordination_scope}
    recording = _RecordingExporter(exporter)
    resolver = MediaServerPublicationResolver(
        database, recording, _profile("/server/existing-library"), scope_resolver=scopes.__getitem__
    )
    with pytest.raises(MediaServerError) as raised:
        resolver.resolve(changed_id)
    assert raised.value.code == "media_server_publication_not_ready"
    allowed = resolver.resolve(legacy_id)
    assert allowed.author_id == legacy_id
    assert allowed.publication_job_id == legacy_publication.job_id
    assert recording.starts == [0]


def test_scope_resolver_constructor_rejects_non_callable(database: Database, tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="scope_resolver must be callable"):
        MediaServerPublicationResolver(
            database,
            _exporter(tmp_path),
            _profile("/server/existing-library"),
            scope_resolver="not-callable",  # type: ignore[arg-type]
        )
