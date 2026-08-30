"""Unit tests for deterministic Emby/Jellyfin layout planning."""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from media_sync.exporters.emby import (
    ExportAuthor,
    ExportConflictError,
    ExportContent,
    ExportError,
    PublishedIdentity,
    VerifiedAsset,
    author_relative_directory,
    content_source_fingerprint,
    export_source_fingerprint,
    stable_episode_number,
)
from media_sync.exporters.emby.layout import build_layout_plan

NOW = datetime(2026, 8, 30, 1, 2, 3, tzinfo=UTC)


def _asset(
    tmp_path: Path,
    name: str,
    payload: bytes,
    *,
    kind: str = "image",
    position: int = 0,
    generation: int = 1,
) -> VerifiedAsset:
    path = tmp_path / name
    path.write_bytes(payload)
    return VerifiedAsset(
        remote_id=name,
        kind=kind,
        position=position,
        local_path=path,
        checksum_sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        mime_type={"image": "image/jpeg", "cover": "image/png", "video": "video/mp4", "audio": "audio/mpeg"}[kind],
        generation=generation,
    )


def _content(remote_id: str, assets: tuple[VerifiedAsset, ...] = ()) -> ExportContent:
    return ExportContent(
        platform="xhs",
        remote_type="note",
        remote_id=remote_id,
        author_remote_id="creator-1",
        kind="mixed",
        first_seen_at=NOW,
        published_at=NOW,
        title="A title",
        body="Text",
        assets=assets,
    )


def test_published_identity_is_frozen_normalized_and_validated() -> None:
    identity = PublishedIdentity(f" {'A' * 64} ", "B" * 64, "C" * 64)

    assert identity == PublishedIdentity("a" * 64, "b" * 64, "c" * 64)
    with pytest.raises(ExportError) as raised:
        PublishedIdentity("not-a-checksum", "b" * 64, "c" * 64)
    assert raised.value.code == "invalid_published_identity"


def test_export_dtos_are_frozen_normalized_and_orm_independent(tmp_path: Path) -> None:
    asset = _asset(tmp_path, "image", b"image")
    content = ExportContent(
        platform=" XHS ",
        remote_type=" NOTE ",
        remote_id=" item ",
        author_remote_id=" creator-1 ",
        kind=" MIXED ",
        first_seen_at=NOW,
        assets=(asset,),
    )
    author = ExportAuthor(" XHS ", " creator-1 ", " Creator ")

    assert (author.platform, content.platform, content.remote_type, content.kind) == ("xhs", "xhs", "note", "mixed")
    with pytest.raises(FrozenInstanceError):
        content.title = "changed"  # type: ignore[misc]
    with pytest.raises(ExportError, match="invalid_first_seen_at"):
        ExportContent(
            platform="xhs",
            remote_type="note",
            remote_id="item",
            author_remote_id="creator-1",
            kind="text",
            first_seen_at=datetime(2026, 1, 1),
        )


def test_source_fingerprints_are_path_and_input_order_independent(tmp_path: Path) -> None:
    first = _asset(tmp_path, "first", b"first", position=2)
    second = _asset(tmp_path, "second", b"second", position=1)
    forward = _content("item", (first, second))
    reverse = _content("item", (second, first))
    author = ExportAuthor("xhs", "creator-1", "Creator")

    assert content_source_fingerprint(forward) == content_source_fingerprint(reverse)
    assert export_source_fingerprint(author, (forward,)) == export_source_fingerprint(author, (reverse,))
    assert len(content_source_fingerprint(forward)) == 64


def test_asset_generation_is_positive_non_boolean_and_changes_source_identity(tmp_path: Path) -> None:
    first = _asset(tmp_path, "generation", b"same-bytes")
    repaired = replace(first, generation=2)

    assert first.generation == 1
    assert content_source_fingerprint(_content("item", (first,))) != content_source_fingerprint(
        _content("item", (repaired,))
    )
    for invalid in (True, 0, -1, 1.0, "1"):
        with pytest.raises(ExportError) as raised:
            replace(first, generation=invalid)  # type: ignore[arg-type]
        assert raised.value.code == "invalid_asset_generation"


def test_paths_are_nfc_windows_safe_bounded_and_title_independent(tmp_path: Path) -> None:
    remote_id = "e\u0301<CON>:bad?*" + "界" * 100
    first_author = ExportAuthor("xhs", remote_id, "First title")
    renamed_author = ExportAuthor("xhs", unicodedata.normalize("NFC", remote_id), "Renamed")
    first_path = author_relative_directory(first_author).as_posix()
    renamed_path = author_relative_directory(renamed_author).as_posix()

    assert first_path == renamed_path
    assert first_path == unicodedata.normalize("NFC", first_path)
    assert not set('<>:"/\\|?*') & set(first_path)
    assert not first_path.endswith((" ", "."))
    assert len(first_path.encode("utf-8")) <= 120

    content_a = _content("ABC")
    content_b = _content("abc")
    plan = build_layout_plan(ExportAuthor("xhs", "creator-1", "Creator"), (content_a, content_b))
    paths = [item.relative_path.as_posix() for item in plan.files]
    assert len(paths) == len({path.casefold() for path in paths})


def test_same_second_and_null_publish_times_have_distinct_stable_episodes() -> None:
    author = ExportAuthor("xhs", "creator-1", "Creator")
    published = _content("published")
    no_publish = ExportContent(
        platform="xhs",
        remote_type="note",
        remote_id="no-publish",
        author_remote_id="creator-1",
        kind="text",
        first_seen_at=NOW,
        published_at=None,
    )
    plan = build_layout_plan(author, (published, no_publish))

    nfos = [item.relative_path.as_posix() for item in plan.files if item.relative_path.suffix == ".nfo"]
    assert len([path for path in nfos if path.startswith("Season 2026/")]) == 2
    assert stable_episode_number("xhs", "note", "published") > 0
    assert stable_episode_number("xhs", "note", "published") != stable_episode_number("xhs", "note", "no-publish")
    assert plan == build_layout_plan(author, (no_publish, published))


def test_episode_hash_collision_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("media_sync.exporters.emby.layout.stable_episode_number", lambda *_: 7)
    author = ExportAuthor("xhs", "creator-1", "Creator")

    with pytest.raises(ExportConflictError) as raised:
        build_layout_plan(author, (_content("one"), _content("two")))

    assert raised.value.code == "episode_number_collision"


def test_content_author_mismatch_and_duplicate_assets_are_rejected(tmp_path: Path) -> None:
    author = ExportAuthor("xhs", "creator-1", "Creator")
    asset = _asset(tmp_path, "same", b"same")
    duplicate = _content("one", (asset, asset))
    mismatch = ExportContent(
        platform="xhs",
        remote_type="note",
        remote_id="two",
        author_remote_id="someone-else",
        kind="text",
        first_seen_at=NOW,
    )

    with pytest.raises(ExportError) as duplicate_error:
        build_layout_plan(author, (duplicate,))
    assert duplicate_error.value.code == "duplicate_asset_identity"
    with pytest.raises(ExportError) as mismatch_error:
        build_layout_plan(author, (mismatch,))
    assert mismatch_error.value.code == "content_author_mismatch"
