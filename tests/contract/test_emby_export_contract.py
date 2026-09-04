"""Filesystem contract tests for Emby/Jellyfin layout v1."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest

import media_sync.exporters.emby.exporter as exporter_module
from media_sync.exporters.emby import (
    LAYOUT_VERSION,
    EmbyExporter,
    ExportAuthor,
    ExportConflictError,
    ExportContent,
    ExportError,
    ExportResult,
    ManagedFile,
    ManagedFileInspection,
    PublishedIdentity,
    RenderedExport,
    VerifiedAsset,
)

NOW = datetime(2026, 8, 30, 1, 2, 3, 456789, tzinfo=UTC)


def _identity(value: ExportResult | RenderedExport) -> PublishedIdentity:
    return PublishedIdentity(value.source_fingerprint, value.tree_sha256, value.manifest_sha256)


def _inspection_entry(result: ExportResult, entry_kind: str) -> Path:
    if entry_kind == "lock":
        lock_files = list((result.author_directory.parent / ".media-sync-locks-v1").glob("*.lock"))
        assert len(lock_files) == 1
        return lock_files[0]
    if entry_kind == "manifest":
        return result.manifest_path
    assert entry_kind == "managed_file"
    relative_path = result.managed_files[0].relative_path
    return result.author_directory.joinpath(*relative_path.split("/"))


def _inspection_directory(result: ExportResult, directory_kind: str) -> Path:
    root = result.author_directory.parent
    managed_parent = _inspection_entry(result, "managed_file").parent
    return {
        "root": root,
        "lock_parent": root / ".media-sync-locks-v1",
        "author": result.author_directory,
        "managed_parent": managed_parent,
    }[directory_kind]


def _write_asset(
    root: Path,
    name: str,
    payload: bytes,
    *,
    kind: str,
    position: int,
    mime_type: str,
) -> VerifiedAsset:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_bytes(payload)
    return VerifiedAsset(
        remote_id=name,
        kind=kind,
        position=position,
        local_path=path,
        checksum_sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        mime_type=mime_type,
    )


def _fixture(tmp_path: Path, *, title: str = "Title\x01 & <XML>") -> tuple[ExportAuthor, ExportContent]:
    sources = tmp_path / "archive"
    video = _write_asset(sources, "video", b"video-bytes", kind="video", position=0, mime_type="video/mp4")
    cover = _write_asset(sources, "cover", b"cover-bytes", kind="cover", position=0, mime_type="image/png")
    image_a = _write_asset(sources, "image-a", b"image-a", kind="image", position=2, mime_type="image/jpeg")
    image_b = _write_asset(sources, "image-b", b"image-b", kind="image", position=1, mime_type="image/webp")
    author = ExportAuthor("xhs", "creator/CON", "Creator\x00 & <Name>", "@creator")
    content = ExportContent(
        platform="xhs",
        remote_type="note",
        remote_id="item:1?",
        author_remote_id="creator/CON",
        kind="mixed",
        first_seen_at=NOW,
        published_at=NOW,
        title=title,
        body="Body\x0b & <plot>\n第二行",
        assets=(image_a, cover, video, image_b),
    )
    return author, content


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file()
    }


def _tree_hashes(root: Path) -> dict[str, str]:
    return {path: hashlib.sha256(payload).hexdigest() for path, payload in _tree(root).items()}


def test_golden_tree_nfo_provenance_and_reversed_input_are_byte_identical(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    first_exporter = EmbyExporter(tmp_path / "library-a", staging_root=tmp_path / "work-a")
    reversed_content = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title=content.title,
        body=content.body,
        assets=tuple(reversed(content.assets)),
    )
    second_exporter = EmbyExporter(tmp_path / "library-b", staging_root=tmp_path / "work-b")

    first = first_exporter.export(author, (content,), job_id="job-a", expected_predecessor=None)
    second = second_exporter.export(author, (reversed_content,), job_id="job-b", expected_predecessor=None)
    first_tree = _tree(first.author_directory)
    second_tree = _tree(second.author_directory)

    assert first.layout_version == LAYOUT_VERSION
    assert first.tree_sha256 == second.tree_sha256
    assert first_tree == second_tree
    base = "S2026E0620286506-xhs-note-item_1_-7f5742797cd2a479"
    assert sorted(first_tree) == [
        ".media-sync-managed-v1.json",
        f"Season 2026/{base}-backdrop.jpg",
        f"Season 2026/{base}-poster.png",
        f"Season 2026/{base}.assets/body.txt",
        f"Season 2026/{base}.assets/cover-001-cover-ad7a3201b4c4a2fe.png",
        f"Season 2026/{base}.assets/gallery-001-image-b-dd5b64e73bc64755.webp",
        f"Season 2026/{base}.assets/gallery-002-image-a-5c7e1eacc4283ae4.jpg",
        f"Season 2026/{base}.assets/source.json",
        f"Season 2026/{base}.mp4",
        f"Season 2026/{base}.nfo",
        "source.json",
        "tvshow.nfo",
    ]
    assert first.tree_sha256 == "8a5278bc56a366995508a0af67723d8f330058a8ba13268abbaf0ef2028b07df"

    episode_path = next(first.author_directory.glob("Season 2026/*.nfo"))
    episode_bytes = episode_path.read_bytes()
    assert b"\r\n" not in episode_bytes
    assert b"\x00" not in episode_bytes and b"\x01" not in episode_bytes and b"\x0b" not in episode_bytes
    episode = ET.fromstring(episode_bytes)
    assert [element.tag for element in episode] == [
        "title",
        "showtitle",
        "season",
        "episode",
        "aired",
        "dateadded",
        "plot",
        "uniqueid",
        "studio",
        "thumb",
        "fanart",
    ]
    uniqueid = episode.find("uniqueid")
    assert uniqueid is not None
    assert uniqueid.attrib == {"type": "media-sync-xhs-note", "default": "true"}

    content_source_path = next(first.author_directory.glob("Season 2026/*.assets/source.json"))
    source_payload = json.loads(content_source_path.read_text(encoding="utf-8"))
    assert set(source_payload) == {
        "assets",
        "author_remote_id",
        "content_kind",
        "entity",
        "first_seen_at",
        "layout_version",
        "platform",
        "published_at",
        "remote_id",
        "remote_type",
        "schema_version",
        "source_fingerprint",
    }
    serialized_source = content_source_path.read_text(encoding="utf-8")
    assert {asset["generation"] for asset in source_payload["assets"]} == {1}
    assert "locator" not in serialized_source and "raw" not in serialized_source and "http" not in serialized_source
    assert str(tmp_path) not in serialized_source

    video_output = next(first.author_directory.glob("Season 2026/*.mp4"))
    assert video_output.read_bytes() == b"video-bytes"
    assert os.stat(video_output).st_ino != os.stat(content.assets[2].local_path).st_ino


def test_manifest_has_exact_relative_hash_contract(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    extra_cover = _write_asset(
        tmp_path / "archive",
        "cover-extra",
        b"cover-extra",
        kind="cover",
        position=9,
        mime_type="image/jpeg",
    )
    avatar = _write_asset(
        tmp_path / "archive",
        "avatar",
        b"avatar",
        kind="avatar",
        position=0,
        mime_type="image/png",
    )
    content = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title=content.title,
        body=content.body,
        assets=(*content.assets, extra_cover, avatar),
    )
    result = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work").export(
        author,
        (content,),
        job_id="manifest",
        expected_predecessor=None,
    )
    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert set(payload) == {
        "author",
        "content_fingerprints",
        "files",
        "layout_version",
        "schema_version",
        "source_fingerprint",
        "tree_sha256",
    }
    assert payload["schema_version"] == 1
    assert payload["layout_version"] == LAYOUT_VERSION
    assert payload["tree_sha256"] == result.tree_sha256
    assert result.manifest_path.stat().st_nlink == 1
    assert [row["path"] for row in payload["files"]] == [item.relative_path for item in result.managed_files]
    assert all(
        not Path(row["path"]).is_absolute() and set(row) == {"path", "sha256", "size_bytes"} for row in payload["files"]
    )
    for row in payload["files"]:
        destination = result.author_directory.joinpath(*row["path"].split("/"))
        assert len(destination.read_bytes()) == row["size_bytes"]
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == row["sha256"]
    published_hashes = {row["sha256"] for row in payload["files"]}
    assert {asset.checksum_sha256 for asset in content.assets} <= published_hashes


def test_validate_published_returns_managed_count_and_ignores_unmanaged_files(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    result = exporter.export(author, (content,), job_id="validate", expected_predecessor=None)
    unmanaged = result.author_directory / "user-owned.txt"
    unmanaged.write_bytes(b"leave me alone")

    count = exporter.validate_published(
        author,
        result.source_fingerprint,
        result.tree_sha256,
        result.manifest_sha256,
    )

    assert count == len(result.managed_files)
    assert unmanaged.read_bytes() == b"leave me alone"


def test_inspect_published_verifies_only_a_bounded_manifest_page(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    result = exporter.export(author, (content,), job_id="inspect-page", expected_predecessor=None)

    inspected = exporter.inspect_published(
        author,
        _identity(result),
        start_index=0,
        limit=2,
        max_bytes=1024 * 1024,
        deadline=time.monotonic() + 10,
    )

    assert inspected.files == tuple(
        ManagedFileInspection(item.relative_path, item.sha256, item.size_bytes) for item in result.managed_files[:2]
    )
    assert inspected.start_index == 0
    assert inspected.next_index == 2
    assert inspected.managed_file_count == len(result.managed_files)
    assert inspected.complete is False
    assert inspected.budget_exhausted is False
    assert inspected.bytes_read == sum(item.size_bytes for item in result.managed_files[:2])


def test_inspect_published_last_nonzero_page_is_not_a_complete_tree(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    result = exporter.export(author, (content,), job_id="inspect-last-page", expected_predecessor=None)
    start_index = len(result.managed_files) - 1

    inspected = exporter.inspect_published(
        author,
        _identity(result),
        start_index=start_index,
        limit=128,
        max_bytes=1024 * 1024,
        deadline=time.monotonic() + 10,
    )

    assert inspected.start_index == start_index
    assert inspected.next_index == len(result.managed_files)
    assert inspected.files == (
        ManagedFileInspection(
            result.managed_files[-1].relative_path,
            result.managed_files[-1].sha256,
            result.managed_files[-1].size_bytes,
        ),
    )
    assert inspected.complete is False
    assert inspected.budget_exhausted is False


def test_inspect_published_stops_inside_file_without_claiming_it_verified(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    result = exporter.export(author, (content,), job_id="inspect-budget", expected_predecessor=None)

    inspected = exporter.inspect_published(
        author,
        _identity(result),
        start_index=0,
        limit=128,
        max_bytes=1,
        deadline=time.monotonic() + 10,
    )

    assert inspected.files == ()
    assert inspected.next_index == 0
    assert inspected.bytes_read == 1
    assert inspected.complete is False
    assert inspected.budget_exhausted is True


def test_inspect_published_never_creates_a_missing_lock_or_directory(tmp_path: Path) -> None:
    author, _ = _fixture(tmp_path)
    export_root = tmp_path / "missing-library"
    exporter = EmbyExporter(export_root, staging_root=tmp_path / "work")
    identity = PublishedIdentity("a" * 64, "b" * 64, "c" * 64)
    before = set(tmp_path.iterdir())

    with pytest.raises(ExportError) as raised:
        exporter.inspect_published(
            author,
            identity,
            start_index=0,
            limit=1,
            max_bytes=1,
            deadline=time.monotonic() + 10,
        )

    assert raised.value.code == "published_tree_drifted"
    assert set(tmp_path.iterdir()) == before
    assert not export_root.exists()


def test_inspect_published_does_not_recreate_a_removed_existing_lock(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    result = exporter.export(author, (content,), job_id="inspect-no-lock-create", expected_predecessor=None)
    lock_file = next((tmp_path / "library" / ".media-sync-locks-v1").glob("*.lock"))
    lock_file.unlink()
    tree_before = _tree(tmp_path / "library")

    with pytest.raises(ExportError) as raised:
        exporter.inspect_published(
            author,
            _identity(result),
            start_index=0,
            limit=1,
            max_bytes=1024,
            deadline=time.monotonic() + 10,
        )

    assert raised.value.code == "published_tree_drifted"
    assert _tree(tmp_path / "library") == tree_before
    assert not lock_file.exists()


@pytest.mark.parametrize("entry_kind", ["lock", "manifest", "managed_file"])
def test_inspect_published_rejects_hardlinked_entries(tmp_path: Path, entry_kind: str) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    result = exporter.export(author, (content,), job_id=f"inspect-{entry_kind}-hardlink", expected_predecessor=None)
    target = _inspection_entry(result, entry_kind)
    original_bytes = target.read_bytes()
    external_link = tmp_path / f"external-{entry_kind}-hardlink"
    try:
        os.link(target, external_link)
    except OSError:
        pytest.skip("hardlink creation is unavailable on this host")

    with pytest.raises(ExportError) as raised:
        exporter.inspect_published(
            author,
            _identity(result),
            start_index=0,
            limit=128,
            max_bytes=1024 * 1024,
            deadline=time.monotonic() + 10,
        )

    assert raised.value.code == "published_tree_drifted"
    assert target.read_bytes() == original_bytes
    assert external_link.read_bytes() == original_bytes


@pytest.mark.parametrize("entry_kind", ["lock", "manifest", "managed_file"])
def test_inspect_published_rejects_symlinked_entries(tmp_path: Path, entry_kind: str) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    result = exporter.export(author, (content,), job_id=f"inspect-{entry_kind}-symlink", expected_predecessor=None)
    target = _inspection_entry(result, entry_kind)
    original_bytes = target.read_bytes()
    displaced = target.with_name(f"{target.name}.before-inspection")
    target.rename(displaced)
    try:
        target.symlink_to(displaced)
    except OSError:
        displaced.rename(target)
        pytest.skip("file symlinks are unavailable on this host")

    try:
        with pytest.raises(ExportError) as raised:
            exporter.inspect_published(
                author,
                _identity(result),
                start_index=0,
                limit=128,
                max_bytes=1024 * 1024,
                deadline=time.monotonic() + 10,
            )

        assert raised.value.code == "published_tree_drifted"
        assert displaced.read_bytes() == original_bytes
    finally:
        target.unlink()
        displaced.rename(target)


@pytest.mark.parametrize(
    ("entry_kind", "expected_event"),
    [
        ("lock", "inspect_manifest_opened"),
        ("manifest", "inspect_manifest_opened"),
        ("managed_file", "inspect_file_opened"),
    ],
)
def test_inspect_published_rejects_same_byte_entry_replacement_during_read(
    tmp_path: Path,
    entry_kind: str,
    expected_event: str,
) -> None:
    author, content = _fixture(tmp_path)
    entered = Event()
    release = Event()
    selected_relative_path: list[str] = []

    def wait_after_open(event: str, relative_path: str | None) -> None:
        if event != expected_event:
            return
        if entry_kind == "managed_file" and relative_path != selected_relative_path[0]:
            return
        entered.set()
        assert release.wait(timeout=5)

    exporter = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=wait_after_open,
    )
    result = exporter.export(author, (content,), job_id=f"inspect-{entry_kind}-replacement", expected_predecessor=None)
    selected_relative_path.append(result.managed_files[0].relative_path)
    target = _inspection_entry(result, entry_kind)
    replacement = tmp_path / f"same-byte-{entry_kind}-replacement"
    replacement.write_bytes(target.read_bytes())
    replace_error: OSError | None = None

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            exporter.inspect_published,
            author,
            _identity(result),
            start_index=0,
            limit=128,
            max_bytes=1024 * 1024,
            deadline=time.monotonic() + 10,
        )
        try:
            assert entered.wait(timeout=5)
            try:
                os.replace(replacement, target)
            except OSError as error:
                replace_error = error
        finally:
            release.set()

        if replace_error is None:
            with pytest.raises(ExportError) as raised:
                pending.result(timeout=5)
            assert raised.value.code == "published_tree_drifted"
        else:
            inspected = pending.result(timeout=5)
            if os.name != "nt":
                pytest.skip("same-filesystem entry replacement is unavailable on this host")
            assert inspected.complete is True
            assert target.read_bytes() == replacement.read_bytes()


@pytest.mark.parametrize("replace_target", ["root", "lock_parent", "author", "managed_parent"])
def test_inspect_published_rejects_parent_replaced_by_link_during_read(
    tmp_path: Path,
    replace_target: str,
) -> None:
    author, content = _fixture(tmp_path)
    entered = Event()
    release = Event()
    selected_relative_path: list[str] = []
    expected_event = "inspect_file_opened" if replace_target == "managed_parent" else "inspect_manifest_opened"

    def wait_after_open(event: str, relative_path: str | None) -> None:
        if event != expected_event:
            return
        if replace_target == "managed_parent" and relative_path != selected_relative_path[0]:
            return
        entered.set()
        assert release.wait(timeout=5)

    exporter = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=wait_after_open,
    )
    result = exporter.export(author, (content,), job_id=f"inspect-parent-{replace_target}", expected_predecessor=None)
    selected_relative_path.append(result.managed_files[0].relative_path)
    manifest_bytes = result.manifest_path.read_bytes()
    target = _inspection_directory(result, replace_target)
    displaced = target.with_name(f"{target.name}-during-inspection")
    rename_error: OSError | None = None
    link_error: OSError | None = None
    replaced = False

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            exporter.inspect_published,
            author,
            _identity(result),
            start_index=0,
            limit=128,
            max_bytes=1024 * 1024,
            deadline=time.monotonic() + 10,
        )
        try:
            assert entered.wait(timeout=5)
            try:
                target.rename(displaced)
            except OSError as error:
                rename_error = error
            else:
                try:
                    target.symlink_to(displaced, target_is_directory=True)
                except OSError as error:
                    link_error = error
                    displaced.rename(target)
                else:
                    replaced = True
        finally:
            release.set()

        try:
            if replaced:
                with pytest.raises(ExportError) as raised:
                    pending.result(timeout=5)
                assert raised.value.code == "published_tree_drifted"
            else:
                inspected = pending.result(timeout=5)
                if rename_error is not None and os.name == "nt":
                    assert inspected.complete is True
                elif link_error is not None:
                    pytest.skip("directory symlinks are unavailable on this host")
                else:
                    pytest.skip("directory replacement is unavailable on this host")
        finally:
            if replaced:
                target.unlink()
                displaced.rename(target)

    assert result.manifest_path.read_bytes() == manifest_bytes


@pytest.mark.parametrize("replace_target", ["root", "lock_parent", "author", "managed_parent"])
def test_inspect_published_rejects_same_tree_directory_replacement_during_read(
    tmp_path: Path,
    replace_target: str,
) -> None:
    author, content = _fixture(tmp_path)
    entered = Event()
    release = Event()
    selected_relative_path: list[str] = []
    expected_event = "inspect_file_opened" if replace_target == "managed_parent" else "inspect_manifest_opened"

    def wait_after_open(event: str, relative_path: str | None) -> None:
        if event != expected_event:
            return
        if replace_target == "managed_parent" and relative_path != selected_relative_path[0]:
            return
        entered.set()
        assert release.wait(timeout=5)

    exporter = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=wait_after_open,
    )
    result = exporter.export(
        author,
        (content,),
        job_id=f"inspect-same-tree-{replace_target}",
        expected_predecessor=None,
    )
    selected_relative_path.append(result.managed_files[0].relative_path)
    target = _inspection_directory(result, replace_target)
    replacement = tmp_path / f"same-tree-{replace_target}-replacement"
    displaced = target.with_name(f"{target.name}-before-replacement")
    shutil.copytree(target, replacement)
    rename_error: OSError | None = None
    install_error: OSError | None = None
    replaced = False

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            exporter.inspect_published,
            author,
            _identity(result),
            start_index=0,
            limit=128,
            max_bytes=1024 * 1024,
            deadline=time.monotonic() + 10,
        )
        try:
            assert entered.wait(timeout=5)
            try:
                target.rename(displaced)
            except OSError as error:
                rename_error = error
            else:
                try:
                    replacement.rename(target)
                except OSError as error:
                    install_error = error
                    displaced.rename(target)
                else:
                    replaced = True
        finally:
            release.set()

        try:
            if replaced:
                with pytest.raises(ExportError) as raised:
                    pending.result(timeout=5)
                assert raised.value.code == "published_tree_drifted"
                assert _tree(target) == _tree(displaced)
            else:
                inspected = pending.result(timeout=5)
                if rename_error is not None and os.name == "nt":
                    assert inspected.complete is True
                elif install_error is not None:
                    pytest.skip("same-filesystem directory replacement is unavailable on this host")
                else:
                    pytest.skip("directory rename is unavailable on this host")
        finally:
            if replaced:
                shutil.rmtree(target)
                displaced.rename(target)


def test_manifest_byte_anchor_rejects_content_fingerprint_only_tampering(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    result = exporter.export(author, (content,), job_id="manifest-byte-anchor", expected_predecessor=None)
    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    payload["content_fingerprints"][0]["sha256"] = "f" * 64
    tampered = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    result.manifest_path.write_bytes(tampered)

    with pytest.raises(ExportError) as validated:
        exporter.validate_published(
            author,
            result.source_fingerprint,
            result.tree_sha256,
            result.manifest_sha256,
        )
    assert validated.value.code == "published_export_invalid"
    with pytest.raises(ExportConflictError) as rendered:
        exporter.render(
            author,
            (content,),
            job_id="manifest-byte-anchor-next",
            expected_predecessor=_identity(result),
        )
    assert rendered.value.code == "predecessor_mismatch"
    assert result.manifest_path.read_bytes() == tampered


@pytest.mark.parametrize("mutation", ["delete", "modify"])
def test_validate_published_rejects_missing_or_modified_managed_file(
    tmp_path: Path,
    mutation: str,
) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    result = exporter.export(
        author,
        (content,),
        job_id=f"validate-{mutation}",
        expected_predecessor=None,
    )
    manifest_before = result.manifest_path.read_bytes()
    target = result.author_directory.joinpath(*result.managed_files[0].relative_path.split("/"))
    if mutation == "delete":
        target.unlink()
    else:
        target.write_bytes(b"managed-file-user-edit")

    with pytest.raises(ExportError) as raised:
        exporter.validate_published(
            author,
            result.source_fingerprint,
            result.tree_sha256,
            result.manifest_sha256,
        )

    assert raised.value.code == "published_export_invalid"
    assert result.manifest_path.read_bytes() == manifest_before
    if mutation == "delete":
        assert not target.exists()
    else:
        assert target.read_bytes() == b"managed-file-user-edit"


def test_validate_published_accepts_committed_cleanup_residue_without_mutating_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    rendered = exporter.render(author, (content,), job_id="committed-residue", expected_predecessor=None)
    monkeypatch.setattr(exporter_module, "_cleanup_transaction", lambda _transaction: None)
    result = exporter.publish(rendered)
    transaction_root = result.author_directory / ".media-sync-transactions-v1"
    residue_before = _tree(transaction_root)

    count = exporter.validate_published(
        author,
        result.source_fingerprint,
        result.tree_sha256,
        result.manifest_sha256,
    )

    assert count == len(result.managed_files)
    assert residue_before
    assert _tree(transaction_root) == residue_before


def test_validate_published_rejects_uncommitted_transaction_without_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author, content = _fixture(tmp_path, title="Before")
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = exporter.export(author, (content,), job_id="validate-initial", expected_predecessor=None)
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body="After",
        assets=content.assets,
    )
    rendered = exporter.render(
        author,
        (changed,),
        job_id="validate-uncommitted",
        expected_predecessor=_identity(initial),
    )

    def fail_after_file(event: str, _: str | None) -> None:
        if event == "after_publish_file":
            raise RuntimeError("leave transaction uncommitted")

    monkeypatch.setattr(exporter_module, "_rollback_transaction", lambda *_args: False)
    interrupted = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=fail_after_file,
    )
    with pytest.raises(ExportError):
        interrupted.publish(rendered)
    tree_before = _tree(initial.author_directory)

    with pytest.raises(ExportError) as raised:
        exporter.validate_published(
            author,
            rendered.source_fingerprint,
            rendered.tree_sha256,
            rendered.manifest_sha256,
        )

    assert raised.value.code == "published_export_invalid"
    assert _tree(initial.author_directory) == tree_before


def test_empty_snapshot_removes_old_managed_content_and_remains_inspectable(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = exporter.export(author, (content,), job_id="before-empty-snapshot", expected_predecessor=None)
    content_managed_paths = [
        item.relative_path for item in initial.managed_files if item.relative_path not in {"source.json", "tvshow.nfo"}
    ]
    season_directory = next(initial.author_directory.glob("Season *"))
    unmanaged = season_directory / "user-owned.txt"
    unmanaged.write_bytes(b"preserve across empty snapshot")

    empty = exporter.export(
        author,
        (),
        job_id="empty-snapshot",
        expected_predecessor=_identity(initial),
    )

    assert empty.content_fingerprints == ()
    assert [item.relative_path for item in empty.managed_files] == ["source.json", "tvshow.nfo"]
    assert all(not initial.author_directory.joinpath(*path.split("/")).exists() for path in content_managed_paths)
    assert unmanaged.read_bytes() == b"preserve across empty snapshot"
    manifest = json.loads(empty.manifest_path.read_text(encoding="utf-8"))
    assert manifest["content_fingerprints"] == []
    assert manifest["source_fingerprint"] == empty.source_fingerprint
    assert (
        exporter.validate_published(
            author,
            empty.source_fingerprint,
            empty.tree_sha256,
            empty.manifest_sha256,
        )
        == 2
    )


def test_validate_published_rejects_wrong_source_fingerprint_without_writes(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    result = exporter.export(author, (content,), job_id="validate-wrong-source", expected_predecessor=None)
    tree_before = _tree(result.author_directory)

    with pytest.raises(ExportError) as raised:
        exporter.validate_published(author, "0" * 64, result.tree_sha256, result.manifest_sha256)

    assert raised.value.code == "published_export_invalid"
    assert _tree(result.author_directory) == tree_before


def test_first_publish_allows_unrelated_unmanaged_file_without_manifest(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    author_directory = exporter.export_root.joinpath(*author_relative_parts(author))
    author_directory.mkdir(parents=True)
    unmanaged = author_directory / "user-owned.txt"
    unmanaged.write_bytes(b"preserve on first publish")

    result = exporter.export(author, (content,), job_id="first-with-unmanaged", expected_predecessor=None)

    assert unmanaged.read_bytes() == b"preserve on first publish"
    assert unmanaged.name not in {item.relative_path for item in result.managed_files}


def test_trusted_predecessor_rejects_self_consistent_manifest_claiming_user_file(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = exporter.export(author, (content,), job_id="trusted-predecessor", expected_predecessor=None)
    unmanaged = initial.author_directory / "user-owned.txt"
    unmanaged_payload = b"must never become exporter-managed"
    unmanaged.write_bytes(unmanaged_payload)
    manifest = json.loads(initial.manifest_path.read_text(encoding="utf-8"))
    manifest["files"].append(
        {
            "path": unmanaged.name,
            "sha256": hashlib.sha256(unmanaged_payload).hexdigest(),
            "size_bytes": len(unmanaged_payload),
        }
    )
    manifest["files"].sort(key=lambda row: (row["path"].casefold(), row["path"]))
    canonical_rows = (
        json.dumps(manifest["files"], ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    manifest["tree_sha256"] = hashlib.sha256(canonical_rows).hexdigest()
    forged_manifest = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    initial.manifest_path.write_bytes(forged_manifest)

    with pytest.raises(ExportConflictError) as raised:
        exporter.render(
            author,
            (content,),
            job_id="reject-forged-predecessor",
            expected_predecessor=_identity(initial),
        )

    assert raised.value.code == "predecessor_mismatch"
    assert unmanaged.read_bytes() == unmanaged_payload
    assert initial.manifest_path.read_bytes() == forged_manifest


def test_published_desired_tree_rolls_forward_before_db_finalize_and_republishes_idempotently(
    tmp_path: Path,
) -> None:
    author, content = _fixture(tmp_path, title="Before")
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    predecessor = exporter.export(author, (content,), job_id="roll-forward-predecessor", expected_predecessor=None)
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="Desired",
        body="Desired",
        assets=content.assets,
    )
    trusted_predecessor = _identity(predecessor)
    first_render = exporter.render(
        author,
        (changed,),
        job_id="roll-forward-first",
        expected_predecessor=trusted_predecessor,
    )
    published = exporter.publish(first_render)
    published_manifest = published.manifest_path.read_bytes()
    published_tree = _tree(published.author_directory)

    retry_render = exporter.render(
        author,
        (changed,),
        job_id="roll-forward-retry",
        expected_predecessor=trusted_predecessor,
    )
    assert retry_render.predecessor_manifest_sha256 == hashlib.sha256(published_manifest).hexdigest()
    retried = exporter.publish(retry_render)
    finalized_render = exporter.render(
        author,
        (changed,),
        job_id="roll-forward-finalized",
        expected_predecessor=_identity(published),
    )
    finalized = exporter.publish(finalized_render)

    assert retried.tree_sha256 == published.tree_sha256 == finalized.tree_sha256
    assert _tree(finalized.author_directory) == published_tree


def test_desired_identity_rejects_old_predecessor_and_requires_exact_manifest_bytes(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path, title="Before")
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    predecessor = exporter.export(author, (content,), job_id="desired-predecessor", expected_predecessor=None)
    desired_content = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="Desired",
        body=content.body,
        assets=content.assets,
    )
    desired = exporter.render(
        author,
        (desired_content,),
        job_id="desired-staged",
        expected_predecessor=_identity(predecessor),
    )

    with pytest.raises(ExportConflictError) as old_predecessor:
        exporter.render(
            author,
            (desired_content,),
            job_id="desired-before-publish",
            expected_predecessor=_identity(desired),
        )
    assert old_predecessor.value.code == "predecessor_mismatch"
    published = exporter.publish(desired)
    manifest = json.loads(published.manifest_path.read_text(encoding="utf-8"))
    manifest["content_fingerprints"] = []
    tampered = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    published.manifest_path.write_bytes(tampered)

    with pytest.raises(ExportConflictError) as raised:
        exporter.render(
            author,
            (desired_content,),
            job_id="desired-not-exact",
            expected_predecessor=_identity(published),
        )

    assert raised.value.code == "predecessor_mismatch"
    assert published.manifest_path.read_bytes() == tampered


def test_unmanaged_casefold_and_modified_managed_conflicts_are_preserved(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    rendered = exporter.render(author, (content,), job_id="casefold", expected_predecessor=None)
    author_directory = exporter.export_root / rendered.author_segment
    author_directory.mkdir(parents=True)
    unmanaged = author_directory / "TVSHOW.NFO"
    unmanaged.write_bytes(b"user")

    with pytest.raises(ExportConflictError) as case_error:
        exporter.publish(rendered)
    assert case_error.value.code == "casefold_path_conflict"
    assert unmanaged.read_bytes() == b"user"

    unmanaged.unlink()
    result = exporter.publish(rendered)
    managed = result.author_directory / "tvshow.nfo"
    managed.write_bytes(b"user-edited")
    with pytest.raises(ExportConflictError) as modified_error:
        exporter.render(
            author,
            (content,),
            job_id="modified",
            expected_predecessor=_identity(result),
        )
    assert modified_error.value.code == "predecessor_mismatch"
    assert managed.read_bytes() == b"user-edited"


def test_modified_stale_predecessor_file_is_rejected_and_preserved(tmp_path: Path) -> None:
    author, first = _fixture(tmp_path)
    second = ExportContent(
        platform="xhs",
        remote_type="note",
        remote_id="second",
        author_remote_id=author.remote_id,
        kind="text",
        first_seen_at=NOW,
        body="second",
    )
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = exporter.export(author, (first, second), job_id="initial", expected_predecessor=None)
    old_manifest = initial.manifest_path.read_bytes()
    second_nfo = next(path for path in initial.author_directory.glob("Season 2026/*.nfo") if "second" in path.name)
    second_source = next(
        path
        for path in initial.author_directory.glob("Season 2026/*.assets/source.json")
        if "second" in path.parent.name
    )
    second_nfo.write_bytes(b"user-edited-stale")

    with pytest.raises(ExportConflictError) as raised:
        exporter.export(
            author,
            (first,),
            job_id="remove",
            expected_predecessor=_identity(initial),
        )

    assert raised.value.code == "predecessor_mismatch"
    assert second_nfo.read_bytes() == b"user-edited-stale"
    assert second_source.exists()
    assert initial.manifest_path.read_bytes() == old_manifest


def test_stale_render_cannot_overwrite_newer_manifest(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    old = exporter.render(author, (content,), job_id="old", expected_predecessor=None)
    newer_content = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="Newer title",
        body=content.body,
        assets=content.assets,
    )
    newer = exporter.render(author, (newer_content,), job_id="newer", expected_predecessor=None)
    published = exporter.publish(newer)
    published_bytes = _tree(published.author_directory)

    with pytest.raises(ExportConflictError) as raised:
        exporter.publish(old)

    assert raised.value.code == "stale_publish"
    assert _tree(published.author_directory) == published_bytes


def test_concurrent_publish_across_staging_roots_serializes_one_predecessor(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    bootstrap = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work-bootstrap")
    predecessor = bootstrap.export(
        author,
        (content,),
        job_id="concurrent-predecessor",
        expected_predecessor=None,
    )
    first_entered = Event()
    release_first = Event()
    second_entered = Event()
    first_blocked = False

    def block_first(event: str, _: str | None) -> None:
        nonlocal first_blocked
        if event == "before_publish_file" and not first_blocked:
            first_blocked = True
            first_entered.set()
            if not release_first.wait(timeout=5):
                raise RuntimeError("timed out waiting to release first publisher")

    def observe_second(event: str, _: str | None) -> None:
        if event == "before_publish_file":
            second_entered.set()

    first_exporter = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work-a",
        fault_injector=block_first,
    )
    second_exporter = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work-b",
        fault_injector=observe_second,
    )
    first_changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="Concurrent title A",
        body=content.body,
        assets=content.assets,
    )
    second_changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="Concurrent title B",
        body=content.body,
        assets=content.assets,
    )
    trusted_predecessor = _identity(predecessor)
    first = first_exporter.render(
        author,
        (first_changed,),
        job_id="first",
        expected_predecessor=trusted_predecessor,
    )
    second = second_exporter.render(
        author,
        (second_changed,),
        job_id="second",
        expected_predecessor=trusted_predecessor,
    )

    def publish(pair: tuple[EmbyExporter, RenderedExport]) -> str:
        selected_exporter, rendered = pair
        try:
            selected_exporter.publish(rendered)
        except ExportConflictError as error:
            return error.code
        return "succeeded"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(publish, (first_exporter, first))
        assert first_entered.wait(timeout=5)
        second_future = pool.submit(publish, (second_exporter, second))
        try:
            assert not second_entered.wait(timeout=0.2)
        finally:
            release_first.set()
        outcomes = sorted((first_future.result(), second_future.result()))

    assert outcomes == ["stale_publish", "succeeded"]
    assert not any(predecessor.author_directory.glob(".media-sync-transactions-v1/*"))


def test_failure_after_file_swap_rolls_back_and_can_retry_same_staging(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path, title="Old")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(author, (content,), job_id="initial", expected_predecessor=None)
    before = _tree(initial.author_directory)
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="Changed",
        body="Changed body",
        assets=content.assets,
    )
    triggered = False

    def fail_once(event: str, _: str | None) -> None:
        nonlocal triggered
        if event == "after_publish_file" and not triggered:
            triggered = True
            raise RuntimeError("injected")

    failing = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=fail_once,
    )
    rendered = failing.render(
        author,
        (changed,),
        job_id="failure",
        expected_predecessor=_identity(initial),
    )

    with pytest.raises(ExportError) as raised:
        failing.publish(rendered)
    assert raised.value.code == "publish_failed"
    assert _tree(initial.author_directory) == before

    retried = clean.publish(rendered)
    assert _tree(retried.author_directory) != before
    assert not rendered.staging_directory.exists()


def test_staged_file_swap_after_candidate_seal_cannot_change_published_bytes(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    rendered = clean.render(author, (content,), job_id="stage-swap", expected_predecessor=None)
    changed = False

    def swap_stage(event: str, relative_path: str | None) -> None:
        nonlocal changed
        if event == "before_publish_file" and relative_path is not None and not changed:
            changed = True
            staged = rendered.staging_directory.joinpath(*relative_path.split("/"))
            staged.write_bytes(b"tampered-after-preflight")

    failing = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=swap_stage,
    )

    result = failing.publish(rendered)

    assert changed
    for item in result.managed_files:
        destination = result.author_directory.joinpath(*item.relative_path.split("/"))
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == item.sha256
        assert destination.stat().st_nlink == 1


def test_before_publish_concurrent_edit_is_captured_and_preserved(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path, title="Before")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(author, (content,), job_id="initial-edit", expected_predecessor=None)
    old_manifest = initial.manifest_path.read_bytes()
    changed_content = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body="After",
        assets=content.assets,
    )
    rendered = clean.render(
        author,
        (changed_content,),
        job_id="concurrent-edit",
        expected_predecessor=_identity(initial),
    )
    sentinel = b"user-concurrent-edit"
    edited_target: Path | None = None

    def edit_target(event: str, relative_path: str | None) -> None:
        nonlocal edited_target
        if event == "before_publish_file" and relative_path is not None and edited_target is None:
            edited_target = initial.author_directory.joinpath(*relative_path.split("/"))
            edited_target.write_bytes(sentinel)

    failing = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=edit_target,
    )
    with pytest.raises(ExportConflictError) as raised:
        failing.publish(rendered)

    assert raised.value.code == "managed_file_modified"
    assert edited_target is not None and edited_target.read_bytes() == sentinel
    assert initial.manifest_path.read_bytes() == old_manifest


def test_before_delete_concurrent_edit_is_not_unlinked(tmp_path: Path) -> None:
    author, first = _fixture(tmp_path)
    removed = ExportContent(
        platform="xhs",
        remote_type="note",
        remote_id="delete-me",
        author_remote_id=author.remote_id,
        kind="text",
        first_seen_at=NOW,
        body="remove",
    )
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(author, (first, removed), job_id="initial-delete", expected_predecessor=None)
    old_manifest = initial.manifest_path.read_bytes()
    rendered = clean.render(
        author,
        (first,),
        job_id="concurrent-delete",
        expected_predecessor=_identity(initial),
    )
    sentinel = b"user-concurrent-delete-edit"
    edited_target: Path | None = None

    def edit_stale(event: str, relative_path: str | None) -> None:
        nonlocal edited_target
        if event == "before_delete_file" and relative_path is not None and edited_target is None:
            edited_target = initial.author_directory.joinpath(*relative_path.split("/"))
            edited_target.write_bytes(sentinel)

    failing = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=edit_stale,
    )
    with pytest.raises(ExportConflictError) as raised:
        failing.publish(rendered)

    assert raised.value.code == "managed_file_modified"
    assert edited_target is not None and edited_target.read_bytes() == sentinel
    assert initial.manifest_path.read_bytes() == old_manifest


def test_before_manifest_concurrent_edit_fails_predecessor_cas(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path, title="Before")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(author, (content,), job_id="initial-manifest-cas", expected_predecessor=None)
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body=content.body,
        assets=content.assets,
    )
    rendered = clean.render(
        author,
        (changed,),
        job_id="manifest-cas",
        expected_predecessor=_identity(initial),
    )
    sentinel = b"user-concurrent-manifest-edit"

    def edit_manifest(event: str, _: str | None) -> None:
        if event == "before_manifest":
            initial.manifest_path.write_bytes(sentinel)

    failing = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=edit_manifest,
    )
    with pytest.raises(ExportConflictError) as raised:
        failing.publish(rendered)

    assert raised.value.code == "stale_publish"
    assert initial.manifest_path.read_bytes() == sentinel


def test_before_manifest_edit_to_unchanged_managed_file_cannot_return_success(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path, title="Before")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(
        author,
        (content,),
        job_id="initial-unchanged-file-cas",
        expected_predecessor=None,
    )
    before = _tree(initial.author_directory)
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body="After",
        assets=content.assets,
    )
    rendered = clean.render(
        author,
        (changed,),
        job_id="unchanged-file-cas",
        expected_predecessor=_identity(initial),
    )
    initial_tvshow = next(item for item in initial.managed_files if item.relative_path == "tvshow.nfo")
    desired_tvshow = next(item for item in rendered.files if item.relative_path == "tvshow.nfo")
    assert desired_tvshow == initial_tvshow
    tvshow_path = initial.author_directory / "tvshow.nfo"
    sentinel = b"user-edit-to-unchanged-managed-file"

    def edit_unchanged_file(event: str, _: str | None) -> None:
        if event == "before_manifest":
            tvshow_path.write_bytes(sentinel)

    failing = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=edit_unchanged_file,
    )
    with pytest.raises(ExportConflictError) as raised:
        failing.publish(rendered)

    assert raised.value.code == "managed_file_modified"
    expected = dict(before)
    expected["tvshow.nfo"] = sentinel
    assert _tree(initial.author_directory) == expected
    assert rendered.staging_directory.exists()


def test_after_manifest_edit_without_exception_cannot_return_success(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path, title="Before")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(
        author,
        (content,),
        job_id="initial-final-manifest-cas",
        expected_predecessor=None,
    )
    old_manifest = initial.manifest_path.read_bytes()
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body="After",
        assets=content.assets,
    )
    rendered = clean.render(
        author,
        (changed,),
        job_id="final-manifest-cas",
        expected_predecessor=_identity(initial),
    )
    sentinel = b"user-edit-after-manifest-install"

    def edit_manifest_and_return(event: str, _: str | None) -> None:
        if event == "after_manifest":
            initial.manifest_path.write_bytes(sentinel)

    failing = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=edit_manifest_and_return,
    )
    with pytest.raises(ExportError) as raised:
        failing.publish(rendered)

    assert raised.value.code == "publish_rollback_failed"
    assert initial.manifest_path.read_bytes() == sentinel
    transaction_root = initial.author_directory / ".media-sync-transactions-v1"
    assert any(path.name == "RECOVERY_REQUIRED" for path in transaction_root.rglob("*"))
    assert old_manifest in [path.read_bytes() for path in transaction_root.rglob("*") if path.is_file()]


def test_after_manifest_directory_replacement_preserves_child_bytes(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path, title="Before")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(
        author,
        (content,),
        job_id="initial-manifest-directory",
        expected_predecessor=None,
    )
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body="After",
        assets=content.assets,
    )
    rendered = clean.render(
        author,
        (changed,),
        job_id="manifest-directory",
        expected_predecessor=_identity(initial),
    )
    sentinel = b"manifest-directory-child"

    def replace_manifest_with_directory(event: str, _: str | None) -> None:
        if event == "after_manifest":
            initial.manifest_path.unlink()
            initial.manifest_path.mkdir()
            (initial.manifest_path / "sentinel.bin").write_bytes(sentinel)

    failing = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=replace_manifest_with_directory,
    )
    with pytest.raises(ExportError) as raised:
        failing.publish(rendered)

    assert raised.value.code == "publish_rollback_failed"
    assert initial.manifest_path.is_dir()
    assert (initial.manifest_path / "sentinel.bin").read_bytes() == sentinel
    transaction_root = initial.author_directory / ".media-sync-transactions-v1"
    assert any(path.name == "RECOVERY_REQUIRED" for path in transaction_root.rglob("*"))


def test_after_manifest_exact_hardlink_replacement_is_not_deleted(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path, title="Before")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(
        author,
        (content,),
        job_id="initial-manifest-hardlink",
        expected_predecessor=None,
    )
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body="After",
        assets=content.assets,
    )
    rendered = clean.render(
        author,
        (changed,),
        job_id="manifest-hardlink",
        expected_predecessor=_identity(initial),
    )
    external = tmp_path / "user-manifest-hardlink-source"
    installed_bytes: bytes | None = None

    def replace_manifest_with_hardlink(event: str, _: str | None) -> None:
        nonlocal installed_bytes
        if event == "after_manifest":
            installed_bytes = initial.manifest_path.read_bytes()
            external.write_bytes(installed_bytes)
            initial.manifest_path.unlink()
            os.link(external, initial.manifest_path)

    failing = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=replace_manifest_with_hardlink,
    )
    with pytest.raises(ExportError) as raised:
        failing.publish(rendered)

    assert raised.value.code == "publish_rollback_failed"
    assert installed_bytes is not None
    assert external.read_bytes() == installed_bytes
    assert initial.manifest_path.read_bytes() == installed_bytes
    assert external.stat().st_nlink >= 2
    transaction_root = initial.author_directory / ".media-sync-transactions-v1"
    assert any(path.name == "RECOVERY_REQUIRED" for path in transaction_root.rglob("*"))


def test_rollback_never_overwrites_edit_after_published_file(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path, title="Before")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(author, (content,), job_id="initial-rollback-cas", expected_predecessor=None)
    old_manifest = initial.manifest_path.read_bytes()
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body="After",
        assets=content.assets,
    )
    rendered = clean.render(
        author,
        (changed,),
        job_id="rollback-cas",
        expected_predecessor=_identity(initial),
    )
    sentinel = b"user-edit-after-publish"
    edited_target: Path | None = None

    def edit_then_fail(event: str, relative_path: str | None) -> None:
        nonlocal edited_target
        if event == "after_publish_file" and relative_path is not None and edited_target is None:
            edited_target = initial.author_directory.joinpath(*relative_path.split("/"))
            edited_target.write_bytes(sentinel)
            raise RuntimeError("injected after publish")

    failing = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=edit_then_fail,
    )
    with pytest.raises(ExportError) as raised:
        failing.publish(rendered)

    assert raised.value.code == "publish_rollback_failed"
    assert edited_target is not None and edited_target.read_bytes() == sentinel
    assert initial.manifest_path.read_bytes() == old_manifest
    transaction_root = initial.author_directory / ".media-sync-transactions-v1"
    assert any(path.name.endswith(".old") for path in transaction_root.rglob("*"))


def test_post_publish_edit_without_exception_cannot_advance_false_manifest(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path, title="Before")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(
        author,
        (content,),
        job_id="initial-post-publish-cas",
        expected_predecessor=None,
    )
    old_manifest = initial.manifest_path.read_bytes()
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body="After",
        assets=content.assets,
    )
    rendered = clean.render(
        author,
        (changed,),
        job_id="post-publish-cas",
        expected_predecessor=_identity(initial),
    )
    sentinel = b"user-edit-without-hook-failure"
    edited_target: Path | None = None

    def edit_and_return(event: str, relative_path: str | None) -> None:
        nonlocal edited_target
        if event == "after_publish_file" and relative_path is not None and edited_target is None:
            edited_target = initial.author_directory.joinpath(*relative_path.split("/"))
            edited_target.write_bytes(sentinel)

    failing = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=edit_and_return,
    )
    with pytest.raises(ExportError) as raised:
        failing.publish(rendered)

    assert raised.value.code == "publish_rollback_failed"
    assert edited_target is not None and edited_target.read_bytes() == sentinel
    assert initial.manifest_path.read_bytes() == old_manifest
    transaction_root = initial.author_directory / ".media-sync-transactions-v1"
    assert any(path.name == "RECOVERY_REQUIRED" for path in transaction_root.rglob("*"))


def test_before_publish_directory_replacement_is_restored_without_recursive_cleanup(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path, title="Before")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(author, (content,), job_id="initial-directory-race", expected_predecessor=None)
    old_manifest = initial.manifest_path.read_bytes()
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body="After",
        assets=content.assets,
    )
    rendered = clean.render(
        author,
        (changed,),
        job_id="directory-race",
        expected_predecessor=_identity(initial),
    )
    sentinel = b"directory-child-must-survive"
    replaced_target: Path | None = None

    def replace_with_directory(event: str, relative_path: str | None) -> None:
        nonlocal replaced_target
        if event == "before_publish_file" and relative_path is not None and replaced_target is None:
            replaced_target = initial.author_directory.joinpath(*relative_path.split("/"))
            replaced_target.unlink()
            replaced_target.mkdir()
            (replaced_target / "sentinel.bin").write_bytes(sentinel)

    failing = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=replace_with_directory,
    )
    with pytest.raises(ExportConflictError) as raised:
        failing.publish(rendered)

    assert raised.value.code == "managed_file_modified"
    assert replaced_target is not None and replaced_target.is_dir()
    assert (replaced_target / "sentinel.bin").read_bytes() == sentinel
    assert initial.manifest_path.read_bytes() == old_manifest


def test_link_checksum_race_is_retained_in_recovery_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author, content = _fixture(tmp_path, title="Before")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(author, (content,), job_id="initial-link-race", expected_predecessor=None)
    old_manifest = initial.manifest_path.read_bytes()
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body="After",
        assets=content.assets,
    )
    rendered = clean.render(
        author,
        (changed,),
        job_id="link-race",
        expected_predecessor=_identity(initial),
    )
    sentinel = b"hardlink-race-bytes"
    original_link = os.link
    injected = False

    def link_then_mutate(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        follow_symlinks: bool = True,
    ) -> None:
        nonlocal injected
        original_link(source, destination, follow_symlinks=follow_symlinks)
        if not injected and Path(destination).name != ".media-sync-managed-v1.json":
            injected = True
            Path(destination).write_bytes(sentinel)

    monkeypatch.setattr(exporter_module.os, "link", link_then_mutate)
    with pytest.raises(ExportError) as raised:
        clean.publish(rendered)

    assert injected
    assert raised.value.code == "publish_rollback_failed"
    assert initial.manifest_path.read_bytes() == old_manifest
    transaction_root = initial.author_directory / ".media-sync-transactions-v1"
    preserved_payloads = [path.read_bytes() for path in transaction_root.rglob("*") if path.is_file()]
    assert sentinel in preserved_payloads
    assert any(path.name == "RECOVERY_REQUIRED" for path in transaction_root.rglob("*"))


def test_new_file_publication_is_no_clobber(tmp_path: Path) -> None:
    author, first = _fixture(tmp_path)
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(author, (first,), job_id="initial-no-clobber", expected_predecessor=None)
    old_manifest = initial.manifest_path.read_bytes()
    added = ExportContent(
        platform="xhs",
        remote_type="note",
        remote_id="new-item",
        author_remote_id=author.remote_id,
        kind="text",
        first_seen_at=NOW,
        body="new",
    )
    rendered = clean.render(
        author,
        (first, added),
        job_id="new-no-clobber",
        expected_predecessor=_identity(initial),
    )
    sentinel = b"user-created-concurrently"
    user_target: Path | None = None

    def create_target(event: str, relative_path: str | None) -> None:
        nonlocal user_target
        if (
            event == "before_publish_file"
            and relative_path is not None
            and "new-item" in relative_path
            and user_target is None
        ):
            user_target = initial.author_directory.joinpath(*relative_path.split("/"))
            user_target.write_bytes(sentinel)

    failing = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=create_target,
    )
    with pytest.raises(ExportConflictError) as raised:
        failing.publish(rendered)

    assert raised.value.code == "unmanaged_path_conflict"
    assert user_target is not None and user_target.read_bytes() == sentinel
    assert initial.manifest_path.read_bytes() == old_manifest


def test_next_author_lock_recovers_interrupted_pre_manifest_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author, content = _fixture(tmp_path, title="Before")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(
        author,
        (content,),
        job_id="initial-crash-recovery",
        expected_predecessor=None,
    )
    before = _tree(initial.author_directory)
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body="After",
        assets=content.assets,
    )
    rendered = clean.render(
        author,
        (changed,),
        job_id="interrupted",
        expected_predecessor=_identity(initial),
    )

    def stop_after_one_file(event: str, _: str | None) -> None:
        if event == "after_publish_file":
            raise RuntimeError("simulated process interruption")

    monkeypatch.setattr(exporter_module, "_rollback_transaction", lambda *_: False)
    monkeypatch.setattr(exporter_module, "_mark_transaction_conflict", lambda _transaction: None)
    interrupted = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=stop_after_one_file,
    )
    with pytest.raises(ExportError) as raised:
        interrupted.publish(rendered)
    assert raised.value.code == "publish_rollback_failed"
    assert (initial.author_directory / ".media-sync-transactions-v1").exists()

    clean.render(
        author,
        (changed,),
        job_id="after-recovery",
        expected_predecessor=_identity(initial),
    )

    assert _tree(initial.author_directory) == before
    assert not (initial.author_directory / ".media-sync-transactions-v1").exists()


def test_next_author_lock_recovers_interrupted_final_manifest_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author, content = _fixture(tmp_path, title="Before")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(
        author,
        (content,),
        job_id="initial-manifest-verification-crash",
        expected_predecessor=None,
    )
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body="After",
        assets=content.assets,
    )
    rendered = clean.render(
        author,
        (changed,),
        job_id="manifest-verification-crash",
        expected_predecessor=_identity(initial),
    )
    original_restore = exporter_module._restore_capture_no_clobber

    def interrupt_manifest_restore(capture: Path, destination: Path, actual: ManagedFile) -> bool:
        if capture.name == "manifest.check":
            raise RuntimeError("simulated crash during final manifest verification")
        return original_restore(capture, destination, actual)

    monkeypatch.setattr(exporter_module, "_restore_capture_no_clobber", interrupt_manifest_restore)
    monkeypatch.setattr(exporter_module, "_rollback_transaction", lambda *_args: False)
    monkeypatch.setattr(exporter_module, "_mark_transaction_conflict", lambda _transaction: None)
    interrupted = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    with pytest.raises(ExportError) as raised:
        interrupted.publish(rendered)
    assert raised.value.code == "publish_rollback_failed"
    author_directory = interrupted.export_root / rendered.author_segment
    assert (author_directory / ".media-sync-transactions-v1").exists()
    assert not (author_directory / ".media-sync-managed-v1.json").exists()

    clean.render(
        author,
        (changed,),
        job_id="after-manifest-verification-recovery",
        expected_predecessor=_identity(initial),
    )

    assert clean.validate_published(
        author,
        rendered.source_fingerprint,
        rendered.tree_sha256,
        rendered.manifest_sha256,
    ) == len(rendered.files)
    assert not (author_directory / ".media-sync-transactions-v1").exists()


def test_recovery_retains_evidence_when_desired_manifest_has_modified_unchanged_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author, content = _fixture(tmp_path, title="Before")
    clean = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    initial = clean.export(
        author,
        (content,),
        job_id="initial-invalid-desired-recovery",
        expected_predecessor=None,
    )
    changed = ExportContent(
        platform=content.platform,
        remote_type=content.remote_type,
        remote_id=content.remote_id,
        author_remote_id=content.author_remote_id,
        kind=content.kind,
        first_seen_at=content.first_seen_at,
        published_at=content.published_at,
        title="After",
        body="After",
        assets=content.assets,
    )
    rendered = clean.render(
        author,
        (changed,),
        job_id="invalid-desired-recovery",
        expected_predecessor=_identity(initial),
    )
    initial_tvshow = next(item for item in initial.managed_files if item.relative_path == "tvshow.nfo")
    desired_tvshow = next(item for item in rendered.files if item.relative_path == "tvshow.nfo")
    assert desired_tvshow == initial_tvshow

    def interrupt_after_manifest(event: str, _: str | None) -> None:
        if event == "after_manifest":
            raise RuntimeError("simulated process interruption after manifest install")

    interrupted = EmbyExporter(
        tmp_path / "library",
        staging_root=tmp_path / "work",
        fault_injector=interrupt_after_manifest,
    )
    with monkeypatch.context() as crash:
        crash.setattr(exporter_module, "_rollback_transaction", lambda *_args: False)
        crash.setattr(exporter_module, "_mark_transaction_conflict", lambda _transaction: None)
        with pytest.raises(ExportError) as interrupted_error:
            interrupted.publish(rendered)
    assert interrupted_error.value.code == "publish_rollback_failed"

    author_directory = initial.author_directory
    desired_manifest = initial.manifest_path.read_bytes()
    assert hashlib.sha256(desired_manifest).hexdigest() == rendered.manifest_sha256
    tvshow_path = author_directory / "tvshow.nfo"
    sentinel = b"user-edit-before-desired-tree-recovery"
    tvshow_path.write_bytes(sentinel)

    with pytest.raises(ExportError) as recovery_error:
        clean.render(
            author,
            (changed,),
            job_id="blocked-invalid-desired-recovery",
            expected_predecessor=_identity(rendered),
        )

    assert recovery_error.value.code == "publish_recovery_required"
    assert tvshow_path.read_bytes() == sentinel
    assert initial.manifest_path.read_bytes() == desired_manifest
    transaction_root = author_directory / ".media-sync-transactions-v1"
    assert any(path.name == "RECOVERY_REQUIRED" for path in transaction_root.rglob("*"))
    assert any(path.name == "transaction.json" for path in transaction_root.rglob("*"))


def test_lock_symlink_is_rejected_without_touching_external_file(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    external = tmp_path / "external-lock-target"
    external.write_bytes(b"")
    lock_directory = exporter.export_root / ".media-sync-locks-v1"
    lock_directory.mkdir(parents=True)
    lock_path = lock_directory / f"{author_relative_parts(author)[0]}.lock"
    try:
        lock_path.symlink_to(external)
    except OSError:
        pytest.skip("file symlinks are unavailable on this host")

    with pytest.raises(ExportConflictError) as raised:
        exporter.render(author, (content,), job_id="unsafe-lock", expected_predecessor=None)

    assert raised.value.code == "unsafe_existing_path"
    assert external.read_bytes() == b""


def test_lock_hardlink_is_rejected_without_touching_external_file(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")
    external = tmp_path / "external-hardlink-target"
    external.write_bytes(b"preserve")
    lock_directory = exporter.export_root / ".media-sync-locks-v1"
    lock_directory.mkdir(parents=True)
    lock_path = lock_directory / f"{author_relative_parts(author)[0]}.lock"
    os.link(external, lock_path)

    with pytest.raises(ExportConflictError) as raised:
        exporter.render(author, (content,), job_id="unsafe-hardlink-lock", expected_predecessor=None)

    assert raised.value.code == "unsafe_existing_path"
    assert external.read_bytes() == b"preserve"
    assert external.stat().st_nlink >= 2


def test_cleanup_refuses_staging_symlink_and_never_traverses_it(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    external = tmp_path / "external-directory"
    external.mkdir()
    sentinel = external / "sentinel"
    sentinel.write_bytes(b"preserve")
    staging_root = tmp_path / "work"
    stage = staging_root / "staging" / author_relative_parts(author)[0] / "unsafe-cleanup"
    injected = False

    def inject_link(event: str, _: str | None) -> None:
        nonlocal injected
        if event != "after_stage_file" or injected:
            return
        injected = True
        try:
            (stage / "external-link").symlink_to(external, target_is_directory=True)
        except OSError:
            pytest.skip("directory symlinks are unavailable on this host")
        raise RuntimeError("injected")

    exporter = EmbyExporter(
        tmp_path / "library",
        staging_root=staging_root,
        fault_injector=inject_link,
    )
    with pytest.raises(RuntimeError, match="injected"):
        exporter.render(author, (content,), job_id="unsafe-cleanup", expected_predecessor=None)

    assert sentinel.read_bytes() == b"preserve"
    assert stage.exists()


def test_asset_tamper_aborts_render_and_removes_partial_staging(tmp_path: Path) -> None:
    author, content = _fixture(tmp_path)
    content.assets[0].local_path.write_bytes(b"tampered")
    exporter = EmbyExporter(tmp_path / "library", staging_root=tmp_path / "work")

    with pytest.raises(ExportError) as raised:
        exporter.render(author, (content,), job_id="tamper", expected_predecessor=None)

    assert raised.value.code in {"asset_source_checksum_mismatch", "asset_source_size_mismatch"}
    assert not (exporter.staging_root / "staging").joinpath(*author_relative_parts(author), "tamper").exists()


def author_relative_parts(author: ExportAuthor) -> tuple[str, ...]:
    """Keep the assertion independent of private exporter state."""

    from media_sync.exporters.emby import author_relative_directory

    return author_relative_directory(author).parts
