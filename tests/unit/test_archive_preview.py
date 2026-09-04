"""Archive preview verifies immutable bytes before same-descriptor streaming."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import BinaryIO, cast

import pytest

import media_sync.application.archive_preview as archive_preview_module
from media_sync.application.archive_preview import (
    FALLBACK_ARCHIVE_MEDIA_TYPE,
    SAFE_ARCHIVE_MEDIA_TYPES,
    ArchivePreviewError,
    ArchivePreviewService,
    ArchivePreviewSource,
    parse_single_byte_range,
    safe_archive_media_type,
)

PAYLOAD = bytes(range(256)) * 600


def _source(
    path: Path,
    payload: bytes = PAYLOAD,
    *,
    status: str = "verified",
    mime_type: str | None = "video/mp4",
    checksum: str | None = None,
    size_bytes: int | None = None,
) -> ArchivePreviewSource:
    return ArchivePreviewSource(
        status=status,
        local_path=path,
        checksum_sha256=checksum or hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload) if size_bytes is None else size_bytes,
        mime_type=mime_type,
    )


def _canonical_blob(
    tmp_path: Path,
    payload: bytes = PAYLOAD,
    *,
    extension: str = "mp4",
    read_only: bool = True,
) -> tuple[Path, Path, ArchivePreviewSource]:
    root = tmp_path / "archive"
    digest = hashlib.sha256(payload).hexdigest()
    path = root / "sha256" / digest[:2] / f"{digest}.{extension}"
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    if read_only:
        path.chmod(0o444)
    return root, path, _source(path, payload)


def _assert_code(error: ArchivePreviewError, code: str) -> None:
    assert error.code == code
    assert str(error) == f"{code}: {error.message}"


class _ControlledReader:
    def __init__(self, inner: BinaryIO, *, fail_reads: bool = False, fail_seek: bool = False) -> None:
        self.inner = inner
        self.fail_reads = fail_reads
        self.fail_seek = fail_seek

    @property
    def closed(self) -> bool:
        return self.inner.closed

    def fileno(self) -> int:
        return self.inner.fileno()

    def read(self, size: int = -1) -> bytes:
        if self.fail_reads:
            raise OSError("injected bounded stream read failure")
        return self.inner.read(size)

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if self.fail_seek:
            raise OSError("injected verified descriptor seek failure")
        return self.inner.seek(offset, whence)

    def close(self) -> None:
        self.inner.close()


def _install_controlled_reader(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail_reads: bool = False,
    fail_seek: bool = False,
) -> list[_ControlledReader]:
    opened: list[_ControlledReader] = []
    real_open = archive_preview_module._open_archive_read_file

    def controlled_open(candidate: Path, *, root: Path) -> BinaryIO:
        controlled = _ControlledReader(
            real_open(candidate, root=root),
            fail_reads=fail_reads,
            fail_seek=fail_seek,
        )
        opened.append(controlled)
        return cast(BinaryIO, controlled)

    monkeypatch.setattr(archive_preview_module, "_open_archive_read_file", controlled_open)
    return opened


@pytest.mark.parametrize("status", ["verified", "exported"])
def test_open_verifies_and_streams_one_descriptor_in_bounded_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    root, path, source = _canonical_blob(tmp_path)
    source = _source(path, status=status)
    opened_handles: list[BinaryIO] = []
    real_open = archive_preview_module._open_archive_read_file

    def tracked_open(candidate: Path, *, root: Path) -> BinaryIO:
        handle = real_open(candidate, root=root)
        opened_handles.append(handle)
        return handle

    monkeypatch.setattr(archive_preview_module, "_open_archive_read_file", tracked_open)

    preview = ArchivePreviewService(root).open(source)

    assert len(opened_handles) == 1
    assert opened_handles[0].tell() == 0
    assert preview.start == 0
    assert preview.end == len(PAYLOAD) - 1
    assert preview.content_length == len(PAYLOAD)
    assert preview.partial is False
    assert preview.etag == f'"{hashlib.sha256(PAYLOAD).hexdigest()}"'
    assert preview.media_type == "video/mp4"
    chunks = list(preview.iter_bytes())
    assert b"".join(chunks) == PAYLOAD
    assert all(0 < len(chunk) <= 64 * 1024 for chunk in chunks)
    assert opened_handles[0].closed
    assert preview.closed


def test_partial_preview_seeks_and_reads_only_the_selected_inclusive_range(tmp_path: Path) -> None:
    root, _path, source = _canonical_blob(tmp_path)

    preview = ArchivePreviewService(root).open(source, byte_range=(17, 70_017))

    assert (preview.start, preview.end) == (17, 70_017)
    assert preview.content_length == 70_001
    assert preview.partial is True
    assert b"".join(preview.iter_bytes()) == PAYLOAD[17:70_018]
    assert preview.closed


def test_select_range_reuses_the_verified_descriptor_without_reopening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    opened = _install_controlled_reader(monkeypatch)
    preview = ArchivePreviewService(root).open(source)

    selected = preview.select_range(17, 70_017)

    assert selected is preview
    assert len(opened) == 1
    assert opened[0].inner.tell() == 17
    assert (preview.start, preview.end, preview.content_length, preview.partial) == (17, 70_017, 70_001, True)
    assert b"".join(preview.iter_bytes()) == PAYLOAD[17:70_018]
    assert opened[0].closed


def test_selecting_the_entire_file_is_still_an_explicit_partial_response(tmp_path: Path) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    preview = ArchivePreviewService(root).open(source)

    preview.select_range(0, len(PAYLOAD) - 1)

    assert preview.partial is True
    assert preview.content_length == len(PAYLOAD)
    assert b"".join(preview.iter_bytes()) == PAYLOAD
    assert preview.closed


def test_select_range_is_single_use_and_closes_on_a_second_selection(tmp_path: Path) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    preview = ArchivePreviewService(root).open(source)
    preview.select_range(0, 3)

    with pytest.raises(ArchivePreviewError) as raised:
        preview.select_range(4, 7)

    _assert_code(raised.value, "asset_archive_range_unsatisfiable")
    assert preview.closed


def test_select_range_revalidates_descriptor_snapshot_before_seek_and_closes(tmp_path: Path) -> None:
    root, path, source = _canonical_blob(tmp_path)
    preview = ArchivePreviewService(root).open(source)
    details = path.stat()
    os.utime(path, ns=(details.st_atime_ns, details.st_mtime_ns + 1_000_000_000))

    with pytest.raises(ArchivePreviewError) as raised:
        preview.select_range(0, 3)

    _assert_code(raised.value, "asset_archive_invalid")
    assert preview.closed


def test_select_range_after_stream_claim_is_rejected_and_closes(tmp_path: Path) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    preview = ArchivePreviewService(root).open(source)
    iterator = preview.iter_bytes()

    with pytest.raises(ArchivePreviewError) as raised:
        preview.select_range(0, 3)

    _assert_code(raised.value, "asset_archive_range_unsatisfiable")
    assert preview.closed
    iterator.close()  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("start", "end"),
    [(-1, 1), (0, -1), (2, 1), (0, len(PAYLOAD)), (True, 1)],
)
def test_select_range_rejects_untrusted_offsets_and_closes(
    tmp_path: Path,
    start: int,
    end: int,
) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    preview = ArchivePreviewService(root).open(source)

    with pytest.raises(ArchivePreviewError) as raised:
        preview.select_range(start, end)

    _assert_code(raised.value, "asset_archive_range_unsatisfiable")
    assert preview.closed


def test_empty_blob_has_a_zero_length_full_preview_and_closes(tmp_path: Path) -> None:
    root, _path, source = _canonical_blob(tmp_path, b"", extension="bin")

    preview = ArchivePreviewService(root).open(source)

    assert (preview.start, preview.end, preview.content_length) == (0, -1, 0)
    assert preview.partial is False
    assert list(preview.iter_bytes()) == []
    assert preview.closed


def test_empty_blob_range_selection_is_unsatisfiable_and_closes(tmp_path: Path) -> None:
    root, _path, source = _canonical_blob(tmp_path, b"", extension="bin")
    preview = ArchivePreviewService(root).open(source)

    with pytest.raises(ArchivePreviewError) as raised:
        preview.select_range(0, 0)

    _assert_code(raised.value, "asset_archive_range_unsatisfiable")
    assert preview.closed


def test_explicit_close_is_idempotent_and_prevents_streaming(tmp_path: Path) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    preview = ArchivePreviewService(root).open(source)

    preview.close()
    preview.close()

    assert preview.closed
    with pytest.raises(ArchivePreviewError) as raised:
        preview.iter_bytes()
    _assert_code(raised.value, "asset_archive_invalid")


def test_head_style_validation_without_iteration_closes_the_open_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    opened = _install_controlled_reader(monkeypatch)

    preview = ArchivePreviewService(root).open(source, byte_range=(0, 3))
    assert len(opened) == 1
    assert not opened[0].closed
    assert (preview.partial, preview.start, preview.end, preview.content_length) == (True, 0, 3, 4)
    preview.close()

    assert opened[0].closed
    assert preview.closed


def test_context_manager_closes_after_a_head_style_consumer_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    opened = _install_controlled_reader(monkeypatch)

    with pytest.raises(RuntimeError, match="consumer stopped"), ArchivePreviewService(root).open(source):
        raise RuntimeError("consumer stopped")

    assert len(opened) == 1
    assert opened[0].closed


def test_closing_an_abandoned_iterator_closes_the_descriptor(tmp_path: Path) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    preview = ArchivePreviewService(root).open(source)
    iterator = preview.iter_bytes()

    assert next(iterator) == PAYLOAD[: 64 * 1024]
    iterator.close()  # type: ignore[attr-defined]

    assert preview.closed


def test_stream_read_failure_is_fixed_and_closes_the_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    opened = _install_controlled_reader(monkeypatch)
    preview = ArchivePreviewService(root).open(source)
    assert len(opened) == 1
    opened[0].fail_reads = True

    with pytest.raises(ArchivePreviewError) as raised:
        next(preview.iter_bytes())

    _assert_code(raised.value, "asset_archive_invalid")
    assert "injected bounded stream read failure" not in str(raised.value)
    assert opened[0].closed
    assert preview.closed


def test_post_validation_seek_failure_closes_the_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    opened = _install_controlled_reader(monkeypatch, fail_seek=True)

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(source)

    _assert_code(raised.value, "asset_archive_invalid")
    assert len(opened) == 1
    assert opened[0].closed


def test_hash_read_failure_is_fixed_and_closes_the_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    opened = _install_controlled_reader(monkeypatch, fail_reads=True)

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(source)

    _assert_code(raised.value, "asset_archive_invalid")
    assert len(opened) == 1
    assert opened[0].closed


def test_opened_and_named_identity_mismatch_closes_the_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    replacement = tmp_path / "replacement.mp4"
    replacement.write_bytes(PAYLOAD)
    replacement.chmod(0o444)
    opened = _install_controlled_reader(monkeypatch)

    def replaced_named_stat(candidate: Path, *, root: Path, single_link: bool = True) -> os.stat_result:
        del candidate, root, single_link
        return replacement.lstat()

    monkeypatch.setattr(archive_preview_module, "assert_existing_regular_file", replaced_named_stat)

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(source)

    _assert_code(raised.value, "asset_archive_invalid")
    assert len(opened) == 1
    assert opened[0].closed


def test_unexpected_validation_failure_is_redacted_and_closes_the_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    opened = _install_controlled_reader(monkeypatch)
    real_assert = archive_preview_module.assert_existing_regular_file

    def failed_named_stat(candidate: Path, *, root: Path, single_link: bool = True) -> os.stat_result:
        if not opened:
            return real_assert(candidate, root=root, single_link=single_link)
        raise RuntimeError("sentinel-private-path")

    monkeypatch.setattr(archive_preview_module, "assert_existing_regular_file", failed_named_stat)

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(source)

    _assert_code(raised.value, "asset_archive_invalid")
    assert "sentinel-private-path" not in str(raised.value)
    assert len(opened) == 1
    assert opened[0].closed


@pytest.mark.parametrize("status", ["discovered", "downloaded", "failed_terminal", "", None])
def test_non_ready_status_uses_a_fixed_error(tmp_path: Path, status: str | None) -> None:
    root, path, source = _canonical_blob(tmp_path)
    source = ArchivePreviewSource(
        status=status,
        local_path=path,
        checksum_sha256=source.checksum_sha256,
        size_bytes=source.size_bytes,
        mime_type=source.mime_type,
    )

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(source)

    _assert_code(raised.value, "asset_archive_not_ready")


@pytest.mark.parametrize("missing_field", ["local_path", "checksum_sha256", "size_bytes"])
def test_incomplete_ready_metadata_is_not_ready(tmp_path: Path, missing_field: str) -> None:
    root, path, source = _canonical_blob(tmp_path)
    values: dict[str, object] = {
        "status": source.status,
        "local_path": path,
        "checksum_sha256": source.checksum_sha256,
        "size_bytes": source.size_bytes,
        "mime_type": source.mime_type,
    }
    values[missing_field] = None
    incomplete = ArchivePreviewSource(
        status=values["status"],  # type: ignore[arg-type]
        local_path=values["local_path"],  # type: ignore[arg-type]
        checksum_sha256=values["checksum_sha256"],  # type: ignore[arg-type]
        size_bytes=values["size_bytes"],  # type: ignore[arg-type]
        mime_type=values["mime_type"],  # type: ignore[arg-type]
    )

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(incomplete)

    _assert_code(raised.value, "asset_archive_not_ready")


def test_missing_canonical_blob_uses_a_fixed_path_free_error(tmp_path: Path) -> None:
    root, path, source = _canonical_blob(tmp_path)
    path.chmod(0o600)
    path.unlink()

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(source)

    _assert_code(raised.value, "asset_archive_missing")
    assert str(root) not in str(raised.value)


def test_root_removal_between_preflight_and_open_is_not_recreated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    real_open = archive_preview_module._open_archive_read_file

    def remove_tree_before_open(candidate: Path, *, root: Path) -> BinaryIO:
        candidate.chmod(0o600)
        candidate.unlink()
        candidate.parent.rmdir()
        (root / "sha256").rmdir()
        root.rmdir()
        return real_open(candidate, root=root)

    monkeypatch.setattr(archive_preview_module, "_open_archive_read_file", remove_tree_before_open)

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(source)

    _assert_code(raised.value, "asset_archive_missing")
    assert not root.exists()


@pytest.mark.parametrize("failure", ["content", "size"])
def test_corrupt_blob_is_invalid_and_the_open_descriptor_is_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    root, path, source = _canonical_blob(tmp_path)
    path.chmod(0o600)
    if failure == "content":
        path.write_bytes(b"x" + PAYLOAD[1:])
    else:
        path.write_bytes(PAYLOAD + b"x")
    path.chmod(0o444)
    opened_handles: list[BinaryIO] = []
    real_open = archive_preview_module._open_archive_read_file

    def tracked_open(candidate: Path, *, root: Path) -> BinaryIO:
        handle = real_open(candidate, root=root)
        opened_handles.append(handle)
        return handle

    monkeypatch.setattr(archive_preview_module, "_open_archive_read_file", tracked_open)

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(source)

    _assert_code(raised.value, "asset_archive_invalid")
    if failure == "content":
        assert len(opened_handles) == 1
        assert opened_handles[0].closed
    else:
        assert opened_handles == []


def test_path_outside_exact_digest_location_is_invalid_without_disclosure(tmp_path: Path) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    outside = tmp_path / "sentinel-private-root" / f"{source.checksum_sha256}.mp4"
    outside.parent.mkdir()
    outside.write_bytes(PAYLOAD)
    outside.chmod(0o444)
    outside_source = _source(outside)

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(outside_source)

    _assert_code(raised.value, "asset_archive_invalid")
    assert "sentinel-private-root" not in str(raised.value)
    assert str(outside) not in str(raised.value)


@pytest.mark.parametrize("extension", ["", "tar.gz", "媒体", "mp-4"])
def test_noncanonical_extension_is_invalid(tmp_path: Path, extension: str) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    digest = source.checksum_sha256
    assert digest is not None
    name = digest if not extension else f"{digest}.{extension}"
    invalid = root / "sha256" / digest[:2] / name
    invalid_source = _source(invalid)

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(invalid_source)

    _assert_code(raised.value, "asset_archive_invalid")


def test_symlink_blob_is_invalid(tmp_path: Path) -> None:
    root, path, source = _canonical_blob(tmp_path)
    target = tmp_path / "target.mp4"
    target.write_bytes(PAYLOAD)
    target.chmod(0o444)
    path.chmod(0o600)
    path.unlink()
    try:
        path.symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip("file symlinks are unavailable")

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(source)

    _assert_code(raised.value, "asset_archive_invalid")


def test_hardlinked_blob_is_invalid(tmp_path: Path) -> None:
    root, path, source = _canonical_blob(tmp_path)
    duplicate = tmp_path / "duplicate.mp4"
    try:
        os.link(path, duplicate)
    except (NotImplementedError, OSError):
        pytest.skip("hard links are unavailable")

    try:
        with pytest.raises(ArchivePreviewError) as raised:
            ArchivePreviewService(root).open(source)
        _assert_code(raised.value, "asset_archive_invalid")
    finally:
        path.chmod(0o600)


def test_writable_blob_is_rejected_without_repair(tmp_path: Path) -> None:
    root, path, source = _canonical_blob(tmp_path, read_only=False)

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(source)

    _assert_code(raised.value, "asset_archive_invalid")
    assert path.stat().st_mode & 0o222


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing contract")
def test_windows_preview_handle_denies_write_and_replace_until_close(tmp_path: Path) -> None:
    root, path, source = _canonical_blob(tmp_path)
    replacement = tmp_path / "replacement.mp4"
    replacement.write_bytes(PAYLOAD)
    preview = ArchivePreviewService(root).open(source)
    original = path.stat()

    # Windows permits toggling the DOS read-only bit without opening a file.
    # Even after that toggle, the preview's no-WRITE-sharing handle must keep
    # all content writers and replacements out.
    path.chmod(0o644)
    with pytest.raises(OSError), path.open("r+b") as writer:
        writer.write(b"changed")
    with pytest.raises(OSError):
        os.replace(replacement, path)

    path.chmod(0o444)
    assert b"".join(preview.iter_bytes()) == PAYLOAD
    assert preview.closed

    path.chmod(0o644)
    with path.open("r+b") as writer:
        writer.write(PAYLOAD[:8])
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns + 1_000_000_000))
    os.replace(replacement, path)
    assert path.read_bytes() == PAYLOAD


@pytest.mark.skipif(os.name != "nt", reason="Windows attribute contract")
def test_windows_preview_detects_attribute_change_before_stream_yield_and_closes(tmp_path: Path) -> None:
    root, path, source = _canonical_blob(tmp_path)
    preview = ArchivePreviewService(root).open(source)
    original = path.stat()

    # Windows sharing does not cover FILE_WRITE_ATTRIBUTES, so timestamp APIs
    # may succeed. The descriptor snapshot must still fail closed before any
    # stale-ETag response byte can be yielded.
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns + 1_000_000_000))

    with pytest.raises(ArchivePreviewError) as raised:
        next(preview.iter_bytes())

    _assert_code(raised.value, "asset_archive_invalid")
    assert preview.closed
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing contract")
def test_windows_preview_rejects_a_preexisting_writer_then_opens_after_it_closes(tmp_path: Path) -> None:
    root, path, source = _canonical_blob(tmp_path)
    path.chmod(0o644)
    writer = path.open("r+b")
    path.chmod(0o444)
    try:
        with pytest.raises(ArchivePreviewError) as raised:
            ArchivePreviewService(root).open(source)
        _assert_code(raised.value, "asset_archive_invalid")
    finally:
        writer.close()

    preview = ArchivePreviewService(root).open(source)
    assert b"".join(preview.iter_bytes()) == PAYLOAD
    assert preview.closed


def test_stream_detects_descriptor_metadata_change_and_closes(tmp_path: Path) -> None:
    root, path, source = _canonical_blob(tmp_path)
    preview = ArchivePreviewService(root).open(source)
    iterator: Iterator[bytes] = preview.iter_bytes()
    assert next(iterator) == PAYLOAD[: 64 * 1024]
    path.chmod(0o644)

    with pytest.raises(ArchivePreviewError) as raised:
        next(iterator)

    _assert_code(raised.value, "asset_archive_invalid")
    assert preview.closed


@pytest.mark.parametrize("changed_field", ["st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"])
def test_stream_detects_each_fstat_snapshot_change_and_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_field: str,
) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    opened = _install_controlled_reader(monkeypatch)
    preview = ArchivePreviewService(root).open(source)
    iterator = preview.iter_bytes()
    assert next(iterator) == PAYLOAD[: 64 * 1024]
    real_fstat = os.fstat

    def changed_fstat(descriptor: int) -> object:
        details = real_fstat(descriptor)
        values = {
            "st_mode": details.st_mode,
            "st_nlink": details.st_nlink,
            "st_dev": details.st_dev,
            "st_ino": details.st_ino,
            "st_size": details.st_size,
            "st_mtime_ns": details.st_mtime_ns,
            "st_ctime_ns": details.st_ctime_ns,
            "st_file_attributes": getattr(details, "st_file_attributes", 0),
        }
        values[changed_field] += 1
        return SimpleNamespace(**values)

    monkeypatch.setattr(archive_preview_module.os, "fstat", changed_fstat)

    with pytest.raises(ArchivePreviewError) as raised:
        next(iterator)

    _assert_code(raised.value, "asset_archive_invalid")
    assert len(opened) == 1
    assert opened[0].closed
    assert preview.closed


def test_stream_detects_named_path_replacement_and_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _path, source = _canonical_blob(tmp_path)
    replacement = tmp_path / "replacement.mp4"
    replacement.write_bytes(PAYLOAD)
    replacement.chmod(0o444)
    opened = _install_controlled_reader(monkeypatch)
    preview = ArchivePreviewService(root).open(source)
    iterator = preview.iter_bytes()
    assert next(iterator) == PAYLOAD[: 64 * 1024]

    def replaced_named_stat(candidate: Path, *, root: Path, single_link: bool = True) -> os.stat_result:
        del candidate, root, single_link
        return replacement.lstat()

    monkeypatch.setattr(archive_preview_module, "assert_existing_regular_file", replaced_named_stat)

    with pytest.raises(ArchivePreviewError) as raised:
        next(iterator)

    _assert_code(raised.value, "asset_archive_invalid")
    assert len(opened) == 1
    assert opened[0].closed
    assert preview.closed


@pytest.mark.parametrize("allowed", sorted(SAFE_ARCHIVE_MEDIA_TYPES))
def test_safe_probe_media_types_are_preserved(allowed: str) -> None:
    assert safe_archive_media_type(allowed) == allowed


@pytest.mark.parametrize(
    "unsafe",
    [None, "", "text/html", "image/svg+xml", "application/javascript", "VIDEO/MP4", "video/mp4; charset=utf-8"],
)
def test_unknown_or_executable_media_types_use_binary_fallback(unsafe: str | None) -> None:
    assert safe_archive_media_type(unsafe) == FALLBACK_ARCHIVE_MEDIA_TYPE


def test_open_projects_unknown_mime_to_binary_and_still_closes(tmp_path: Path) -> None:
    root, path, _source_value = _canonical_blob(tmp_path)
    source = _source(path, mime_type="text/html")

    preview = ArchivePreviewService(root).open(source)

    assert preview.media_type == FALLBACK_ARCHIVE_MEDIA_TYPE
    preview.close()
    assert preview.closed


@pytest.mark.parametrize(
    ("header", "size_bytes", "expected"),
    [
        ("bytes=0-0", 10, (0, 0)),
        ("bytes=2-6", 10, (2, 6)),
        ("bytes=2-", 10, (2, 9)),
        ("bytes=-3", 10, (7, 9)),
        ("bytes=0-99", 10, (0, 9)),
        ("bytes=-99", 10, (0, 9)),
        ("bytes=0002-0006", 10, (2, 6)),
        ("Bytes=2-6", 10, (2, 6)),
        ("BYTES=2-6", 10, (2, 6)),
        ("bYtEs=2-6", 10, (2, 6)),
        (" \tbytes=0-1\t ", 10, (0, 1)),
    ],
)
def test_parse_single_byte_range(header: str, size_bytes: int, expected: tuple[int, int]) -> None:
    assert parse_single_byte_range(header, size_bytes) == expected


@pytest.mark.parametrize(
    ("header", "size_bytes"),
    [
        ("bytes=", 10),
        ("bytes=-", 10),
        ("bytes=0-1,3-4", 10),
        ("bytes=4-3", 10),
        ("bytes=10-", 10),
        ("bytes=-0", 10),
        ("bytes=+1-2", 10),
        ("bytes=\uff11-\uff12", 10),
        ("items=0-1", 10),
        ("bytes =0-1", 10),
        ("bytes=0 -1", 10),
        ("bytes=0-0", 0),
        ("bytes=-1", 0),
        ("bytes=0-1", -1),
        ("bytes=" + "9" * 129 + "-", 10),
    ],
)
def test_malformed_multiple_or_unsatisfiable_ranges_use_one_fixed_error(header: str, size_bytes: int) -> None:
    with pytest.raises(ArchivePreviewError) as raised:
        parse_single_byte_range(header, size_bytes)

    _assert_code(raised.value, "asset_archive_range_unsatisfiable")
    assert header not in str(raised.value)


@pytest.mark.parametrize("byte_range", [(-1, 1), (0, -1), (2, 1), (0, len(PAYLOAD)), (True, 1)])
def test_service_rejects_untrusted_preparsed_ranges(tmp_path: Path, byte_range: tuple[int, int]) -> None:
    root, _path, source = _canonical_blob(tmp_path)

    with pytest.raises(ArchivePreviewError) as raised:
        ArchivePreviewService(root).open(source, byte_range=byte_range)

    _assert_code(raised.value, "asset_archive_range_unsatisfiable")
