"""Content-addressed immutable archive publication."""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from media_sync.media.errors import MediaDownloadError
from media_sync.security.paths import (
    PathLockBusyError,
    PathSecurityError,
    assert_regular_file,
    confined_file,
    create_regular_file,
    ensure_secure_directory,
    ensure_secure_root,
    exclusive_file_lock,
    open_regular_read_file,
    safe_unlink,
)

_COPY_CHUNK_BYTES = 1024 * 1024
_BLOB_LOCK_TIMEOUT_SECONDS = 30.0
_BLOB_LOCK_POLL_SECONDS = 0.005


@dataclass(frozen=True, slots=True)
class ArchivedBlob:
    path: Path
    sha256: str
    size_bytes: int


def hash_file(path: Path, *, root: Path) -> tuple[str, int]:
    """Hash a safe regular file without following filesystem indirection."""

    try:
        assert_regular_file(path, root=root)
        digest = hashlib.sha256()
        size = 0
        with open_regular_read_file(path, root=root) as handle:
            opened = os.fstat(handle.fileno())
            while chunk := handle.read(_COPY_CHUNK_BYTES):
                digest.update(chunk)
                size += len(chunk)
            after_read = os.fstat(handle.fileno())
        current = assert_regular_file(path, root=root)
        identities = (
            (opened.st_dev, opened.st_ino),
            (after_read.st_dev, after_read.st_ino),
            (current.st_dev, current.st_ino),
        )
        if len(set(identities)) != 1:
            raise PathSecurityError
        return digest.hexdigest(), size
    except PathSecurityError as exc:
        raise MediaDownloadError("filesystem_unsafe") from exc
    except OSError as exc:
        raise MediaDownloadError("filesystem_write_failed") from exc


class ArchivePublisher:
    """Publish verified bytes beneath ``sha256/`` without overwriting blobs."""

    def __init__(self, root: Path) -> None:
        try:
            self.root = ensure_secure_root(root)
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc

    def publish(
        self,
        source: Path,
        *,
        source_root: Path,
        sha256: str,
        size_bytes: int,
        extension: str,
        before_commit: Callable[[], None] | None = None,
    ) -> ArchivedBlob:
        if (
            len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
            or not extension.isascii()
            or not extension.isalnum()
            or size_bytes < 0
        ):
            raise MediaDownloadError("archive_blob_invalid")
        actual_hash, actual_size = hash_file(source, root=source_root)
        if actual_hash != sha256 or actual_size != size_bytes:
            raise MediaDownloadError("archive_blob_invalid")
        relative_parent = Path("sha256") / sha256[:2]
        relative = relative_parent / f"{sha256}.{extension}"
        try:
            ensure_secure_directory(self.root, relative_parent)
            destination = confined_file(self.root, relative)
            with self._blob_lock(sha256):
                existing = self._publish_existing_locked(
                    destination,
                    sha256=sha256,
                    size_bytes=size_bytes,
                    before_commit=before_commit,
                )
                if existing is not None:
                    return existing
            temporary = destination.with_name(f".{destination.name}.{os.urandom(12).hex()}.tmp")
            handle = create_regular_file(temporary, root=self.root)
            try:
                with handle:
                    with open_regular_read_file(source, root=source_root) as reader:
                        while chunk := reader.read(_COPY_CHUNK_BYTES):
                            handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
                copied_hash, copied_size = hash_file(temporary, root=self.root)
                if copied_hash != sha256 or copied_size != size_bytes:
                    raise MediaDownloadError("archive_blob_invalid")
                self._make_read_only(temporary)
                with self._blob_lock(sha256):
                    existing = self._publish_existing_locked(
                        destination,
                        sha256=sha256,
                        size_bytes=size_bytes,
                        before_commit=before_commit,
                    )
                    if existing is not None:
                        self._discard_temporary_best_effort(temporary)
                        return existing
                    if before_commit is not None:
                        before_commit()
                    committed = False
                    if os.name == "nt":
                        try:
                            os.rename(temporary, destination)
                            committed = True
                        except FileExistsError:
                            pass
                    else:
                        try:
                            os.link(temporary, destination)
                            committed = True
                        except FileExistsError:
                            pass
                    if committed and os.name != "nt":
                        temporary_details = temporary.lstat()
                        destination_details = destination.lstat()
                        same_inode = (
                            temporary_details.st_dev == destination_details.st_dev
                            and temporary_details.st_ino == destination_details.st_ino
                        )
                        if (
                            not same_inode
                            or not stat.S_ISREG(temporary_details.st_mode)
                            or not stat.S_ISREG(destination_details.st_mode)
                            or temporary_details.st_nlink != 2
                            or destination_details.st_nlink != 2
                        ):
                            raise MediaDownloadError("filesystem_unsafe")
                        temporary.unlink()
                    elif not committed:
                        archived = self._validate_existing(destination, sha256=sha256, size_bytes=size_bytes)
                        if before_commit is not None:
                            before_commit()
                        self._discard_temporary_best_effort(temporary)
                        return archived
                    archived = self._validate_existing(destination, sha256=sha256, size_bytes=size_bytes)
                    return archived
            except Exception:
                if temporary.exists() and not temporary.is_symlink():
                    self._cleanup_temporary_after_failure(temporary, destination)
                raise
        except MediaDownloadError:
            raise
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        except OSError as exc:
            raise MediaDownloadError("filesystem_write_failed") from exc

    def validate_existing(
        self,
        path: Path,
        *,
        sha256: str,
        size_bytes: int,
    ) -> ArchivedBlob:
        """Revalidate one canonical archive path before trusting persisted state."""

        absolute, _extension = self._canonical_blob_path(path, sha256=sha256, size_bytes=size_bytes)
        try:
            with self._blob_lock(sha256):
                if not absolute.exists() and not absolute.is_symlink():
                    raise MediaDownloadError("archive_blob_missing")
                return self._validate_existing(absolute, sha256=sha256, size_bytes=size_bytes)
        except MediaDownloadError as error:
            if error.code == "filesystem_unsafe" and not absolute.exists() and not absolute.is_symlink():
                raise MediaDownloadError("archive_blob_missing") from None
            raise

    def quarantine_invalid(
        self,
        path: Path,
        *,
        sha256: str,
        size_bytes: int,
    ) -> Path | None:
        """Move one invalid canonical blob to retained evidence under the archive root.

        A valid blob is left in place and returns ``None``.  Links, directories,
        and paths outside the exact content-addressed location fail closed.
        """

        absolute, extension = self._canonical_blob_path(path, sha256=sha256, size_bytes=size_bytes)
        try:
            with self._blob_lock(sha256):
                if not absolute.exists() and not absolute.is_symlink():
                    raise MediaDownloadError("archive_blob_missing")
                try:
                    self._validate_existing(absolute, sha256=sha256, size_bytes=size_bytes)
                except MediaDownloadError as error:
                    if error.code != "archive_blob_invalid":
                        raise
                else:
                    return None
                return self._quarantine_locked(absolute, sha256=sha256, extension=extension)
        except MediaDownloadError:
            raise
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        except OSError as exc:
            raise MediaDownloadError("filesystem_write_failed") from exc

    def _canonical_blob_path(self, path: Path, *, sha256: str, size_bytes: int) -> tuple[Path, str]:
        if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256) or size_bytes < 0:
            raise MediaDownloadError("archive_blob_invalid")
        absolute = Path(path).absolute()
        try:
            relative = absolute.relative_to(self.root)
        except ValueError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        if len(relative.parts) != 3 or relative.parts[0] != "sha256" or relative.parts[1] != sha256[:2]:
            raise MediaDownloadError("archive_blob_invalid")
        stem, separator, extension = relative.name.rpartition(".")
        if stem != sha256 or separator != "." or not extension.isascii() or not extension.isalnum():
            raise MediaDownloadError("archive_blob_invalid")
        return absolute, extension

    @contextlib.contextmanager
    def _blob_lock(self, sha256: str) -> Iterator[None]:
        relative = Path(".locks") / "sha256" / sha256[:2] / f"{sha256}.lock"
        deadline = time.monotonic() + _BLOB_LOCK_TIMEOUT_SECONDS
        lock = exclusive_file_lock(self.root, relative)
        while True:
            try:
                lock.__enter__()
                break
            except PathLockBusyError:
                if time.monotonic() >= deadline:
                    raise MediaDownloadError("archive_blob_busy") from None
                time.sleep(_BLOB_LOCK_POLL_SECONDS)
                lock = exclusive_file_lock(self.root, relative)
            except PathSecurityError as exc:
                raise MediaDownloadError("filesystem_unsafe") from exc
        try:
            yield
        finally:
            lock.__exit__(None, None, None)

    def _publish_existing_locked(
        self,
        destination: Path,
        *,
        sha256: str,
        size_bytes: int,
        before_commit: Callable[[], None] | None,
    ) -> ArchivedBlob | None:
        if not destination.exists() and not destination.is_symlink():
            return None
        if before_commit is not None:
            before_commit()
        archived = self._validate_existing(destination, sha256=sha256, size_bytes=size_bytes)
        if before_commit is not None:
            before_commit()
        return archived

    def _quarantine_locked(self, source: Path, *, sha256: str, extension: str) -> Path:
        source_details = assert_regular_file(source, root=self.root)
        relative_parent = Path(".quarantine") / "sha256" / sha256[:2]
        ensure_secure_directory(self.root, relative_parent)
        destination = confined_file(
            self.root,
            relative_parent / f"{sha256}.{extension}.{os.urandom(12).hex()}.corrupt",
        )
        with create_regular_file(destination, root=self.root) as handle:
            handle.flush()
            os.fsync(handle.fileno())
        placeholder = assert_regular_file(destination, root=self.root)
        try:
            current_source = assert_regular_file(source, root=self.root)
            current_placeholder = assert_regular_file(destination, root=self.root)
            if (source_details.st_dev, source_details.st_ino) != (
                current_source.st_dev,
                current_source.st_ino,
            ) or (placeholder.st_dev, placeholder.st_ino) != (
                current_placeholder.st_dev,
                current_placeholder.st_ino,
            ):
                raise PathSecurityError
            os.replace(source, destination)
            moved = assert_regular_file(destination, root=self.root)
            if (moved.st_dev, moved.st_ino) != (source_details.st_dev, source_details.st_ino):
                raise PathSecurityError
            if source.exists() or source.is_symlink():
                raise PathSecurityError
            return destination
        except Exception:
            if destination.exists() and not destination.is_symlink():
                with contextlib.suppress(PathSecurityError, OSError):
                    current = assert_regular_file(destination, root=self.root)
                    if (current.st_dev, current.st_ino) == (placeholder.st_dev, placeholder.st_ino):
                        safe_unlink(destination, root=self.root, missing_ok=True)
            raise

    def _validate_existing(self, path: Path, *, sha256: str, size_bytes: int) -> ArchivedBlob:
        try:
            details = assert_regular_file(path, root=self.root, single_link=False)
            for _attempt in range(100):
                if details.st_nlink == 1:
                    break
                if details.st_nlink != 2:
                    raise PathSecurityError
                time.sleep(0.001)
                details = assert_regular_file(path, root=self.root, single_link=False)
            if details.st_nlink != 1:
                raise PathSecurityError
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        if details.st_size != size_bytes:
            raise MediaDownloadError("archive_blob_invalid")
        actual_hash, actual_size = hash_file(path, root=self.root)
        if actual_hash != sha256 or actual_size != size_bytes:
            raise MediaDownloadError("archive_blob_invalid")
        if details.st_mode & 0o222:
            self._make_read_only(path)
            actual_hash, actual_size = hash_file(path, root=self.root)
            if actual_hash != sha256 or actual_size != size_bytes:
                raise MediaDownloadError("archive_blob_invalid")
        return ArchivedBlob(path=path, sha256=actual_hash, size_bytes=actual_size)

    def _make_read_only(self, path: Path) -> None:
        try:
            before = assert_regular_file(path, root=self.root)
            path.chmod(0o444)
            after = assert_regular_file(path, root=self.root)
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        except OSError as exc:
            raise MediaDownloadError("filesystem_write_failed") from exc
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise MediaDownloadError("filesystem_unsafe")
        if after.st_mode & 0o222:
            raise MediaDownloadError("filesystem_write_failed")

    def _discard_temporary(self, path: Path) -> None:
        try:
            before = assert_regular_file(path, root=self.root)
            if before.st_mode & 0o222 == 0:
                path.chmod(0o600)
                after = assert_regular_file(path, root=self.root)
                if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                    raise PathSecurityError
            safe_unlink(path, root=self.root, missing_ok=True)
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        except OSError as exc:
            raise MediaDownloadError("filesystem_write_failed") from exc

    def _discard_temporary_best_effort(self, path: Path) -> None:
        """Do not reverse a proven canonical commit for orphan cleanup failure."""

        with contextlib.suppress(MediaDownloadError):
            self._discard_temporary(path)

    def _cleanup_temporary_after_failure(self, temporary: Path, destination: Path) -> None:
        try:
            temporary_details = assert_regular_file(temporary, root=self.root, single_link=False)
            if temporary_details.st_nlink == 1:
                self._discard_temporary(temporary)
                return
            if temporary_details.st_nlink != 2 or not destination.exists() or destination.is_symlink():
                raise PathSecurityError
            destination_details = assert_regular_file(destination, root=self.root, single_link=False)
            if (temporary_details.st_dev, temporary_details.st_ino) != (
                destination_details.st_dev,
                destination_details.st_ino,
            ):
                raise PathSecurityError
            temporary.unlink()
        except MediaDownloadError:
            raise
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        except OSError as exc:
            raise MediaDownloadError("filesystem_write_failed") from exc


__all__ = ["ArchivePublisher", "ArchivedBlob", "hash_file"]
