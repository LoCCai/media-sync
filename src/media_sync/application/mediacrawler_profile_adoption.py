"""Adopt a verified snapshot of the upstream WebUI Chromium profile."""

from __future__ import annotations

import contextlib
import math
import os
import stat
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError

from media_sync.domain import AuthStatus, LoginMethod, Platform
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.profile_adoption_repository import (
    PROFILE_ADOPTION_ACCOUNT_ERROR_CODES,
    ProfileAdoptionAccountError,
    ProfileAdoptionAccountRepository,
    ProfileAdoptionAccountSnapshot,
)
from media_sync.integrations.mediacrawler import (
    MediaCrawlerAccountLock,
    MediaCrawlerLoginMode,
    MediaCrawlerLoginRequest,
    MediaCrawlerLoginResult,
    MediaCrawlerLoginStatus,
)
from media_sync.integrations.mediacrawler.policies import RunPaths, build_run_paths
from media_sync.scheduler.repository import SchedulerRepository, SchedulerRepositoryError

PROFILE_ADOPTION_ERROR_CODES = frozenset(
    {
        *PROFILE_ADOPTION_ACCOUNT_ERROR_CODES,
        "profile_adoption_source_missing",
        "profile_adoption_source_invalid",
        "profile_adoption_source_empty",
        "profile_adoption_copy_failed",
        "profile_adoption_probe_failed",
        "profile_adoption_probe_unavailable",
        "profile_adoption_result_invalid",
        "profile_adoption_cancelled",
        "profile_adoption_filesystem_failed",
        "profile_adoption_rollback_failed",
        "profile_adoption_cleanup_failed",
    }
)

_ERROR_MESSAGES = {
    "profile_adoption_account_not_found": "the target account was not found",
    "profile_adoption_account_ineligible": "the target account is not an eligible MediaCrawler account",
    "profile_adoption_busy": "the target account or login state is busy",
    "profile_adoption_conflict": "the target account authentication generation changed",
    "profile_adoption_source_missing": "the upstream WebUI has no saved profile for this platform",
    "profile_adoption_source_invalid": "the upstream WebUI profile tree is unsafe or unstable",
    "profile_adoption_source_empty": "the upstream WebUI profile contains no regular files",
    "profile_adoption_copy_failed": "the upstream WebUI profile could not be copied safely",
    "profile_adoption_probe_failed": "the copied profile did not authenticate",
    "profile_adoption_probe_unavailable": "the saved-session probe is unavailable",
    "profile_adoption_result_invalid": "the saved-session probe returned an invalid result",
    "profile_adoption_cancelled": "profile adoption was cancelled",
    "profile_adoption_filesystem_failed": "the account profile could not be replaced safely",
    "profile_adoption_rollback_failed": "the previous account profile could not be restored safely",
    "profile_adoption_cleanup_failed": "temporary profile data could not be removed safely",
}

_PROBE_FAILURE_CODES = {
    MediaCrawlerLoginStatus.EXPIRED: "profile_adoption_probe_failed",
    MediaCrawlerLoginStatus.FAILED: "profile_adoption_probe_failed",
    MediaCrawlerLoginStatus.BROWSER_LAUNCH_FAILED: "profile_adoption_probe_unavailable",
    MediaCrawlerLoginStatus.UPSTREAM_LOGIN_EXITED: "profile_adoption_probe_failed",
    MediaCrawlerLoginStatus.UPSTREAM_BROWSER_TIMEOUT: "profile_adoption_probe_unavailable",
    MediaCrawlerLoginStatus.LOGIN_CONFIRMATION_FAILED: "profile_adoption_probe_failed",
    MediaCrawlerLoginStatus.TIMED_OUT: "profile_adoption_probe_unavailable",
    MediaCrawlerLoginStatus.CANCELLED: "profile_adoption_cancelled",
    MediaCrawlerLoginStatus.ACCOUNT_BUSY: "profile_adoption_busy",
    MediaCrawlerLoginStatus.CONFIGURATION_INVALID: "profile_adoption_probe_unavailable",
    MediaCrawlerLoginStatus.START_FAILED: "profile_adoption_probe_unavailable",
    MediaCrawlerLoginStatus.RESULT_INVALID: "profile_adoption_result_invalid",
}

_COPY_CHUNK_BYTES = 1024 * 1024
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class MediaCrawlerProfileAdoptionError(RuntimeError):
    """A stable, redaction-safe failure from the profile adoption boundary."""

    def __init__(self, code: str) -> None:
        normalized = code if code in PROFILE_ADOPTION_ERROR_CODES else "profile_adoption_filesystem_failed"
        self.code = normalized
        self.message = _ERROR_MESSAGES[normalized]
        super().__init__(f"{normalized}: {self.message}")


@dataclass(frozen=True, slots=True)
class MediaCrawlerProfileAdoptionRequest:
    """One explicit WebUI-profile snapshot hand-off to an existing account."""

    account_id: UUID
    expected_auth_revision: int
    timeout_seconds: float = 180.0
    poll_seconds: float = 0.05

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, UUID):
            raise ValueError("account_id must be a UUID")
        if type(self.expected_auth_revision) is not int or not 0 <= self.expected_auth_revision < 2**63 - 1:
            raise ValueError("expected_auth_revision must be a non-negative signed 64-bit generation")
        timeout = self.timeout_seconds
        poll = self.poll_seconds
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not math.isfinite(timeout)
            or not 0 < float(timeout) <= 3_600
        ):
            raise ValueError("timeout_seconds must be finite and between zero and 3600")
        if (
            isinstance(poll, bool)
            or not isinstance(poll, int | float)
            or not math.isfinite(poll)
            or not 0 < float(poll) <= 5
            or float(poll) >= float(timeout)
        ):
            raise ValueError("poll_seconds must be finite, positive, at most five, and shorter than timeout")
        object.__setattr__(self, "timeout_seconds", float(timeout))
        object.__setattr__(self, "poll_seconds", float(poll))


@dataclass(frozen=True, slots=True)
class MediaCrawlerProfileAdoptionResult:
    """Public result for a verified and durably published saved session."""

    account_id: UUID
    platform: Platform
    auth_revision: int
    upstream_sha: str
    profile_file_count: int
    profile_byte_count: int
    resumed_job_count: int
    login_method: LoginMethod = LoginMethod.SAVED_SESSION
    auth_status: AuthStatus = AuthStatus.AUTHENTICATED

    def to_payload(self) -> dict[str, object]:
        return {
            "account_id": str(self.account_id),
            "platform": self.platform.value,
            "login_method": self.login_method.value,
            "auth_status": self.auth_status.value,
            "auth_revision": self.auth_revision,
            "upstream_sha": self.upstream_sha,
            "profile_file_count": self.profile_file_count,
            "profile_byte_count": self.profile_byte_count,
            "resumed_job_count": self.resumed_job_count,
        }


@dataclass(frozen=True, slots=True)
class _CopyStats:
    files: int = 0
    bytes: int = 0

    def add(self, *, files: int = 0, bytes_: int = 0) -> _CopyStats:
        return _CopyStats(self.files + files, self.bytes + bytes_)

    def added(self, other: _CopyStats) -> _CopyStats:
        return _CopyStats(self.files + other.files, self.bytes + other.bytes)


class _Runner(Protocol):
    def run(
        self,
        request: MediaCrawlerLoginRequest,
        *,
        cancellation: threading.Event | None = None,
    ) -> MediaCrawlerLoginResult: ...


class _AccountLock(Protocol):
    def acquire(self) -> bool: ...

    def release(self) -> None: ...


_AccountLockFactory = Callable[[Path, Platform, UUID], _AccountLock]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _same_file_identity(first: os.stat_result, second: os.stat_result) -> bool:
    if not stat.S_ISREG(first.st_mode) or not stat.S_ISREG(second.st_mode):
        return False
    first_identity = (first.st_dev, first.st_ino)
    second_identity = (second.st_dev, second.st_ino)
    return (not all(first_identity) or first_identity == second_identity) and first.st_size == second.st_size


def _require_real_directory(path: Path, *, missing_code: str, invalid_code: str) -> os.stat_result:
    try:
        info = os.lstat(path)
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        raise MediaCrawlerProfileAdoptionError(missing_code) from None
    except OSError:
        raise MediaCrawlerProfileAdoptionError(invalid_code) from None
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info) or resolved != path.absolute():
        raise MediaCrawlerProfileAdoptionError(invalid_code)
    return info


def _ensure_real_directory(path: Path) -> None:
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError:
        raise MediaCrawlerProfileAdoptionError("profile_adoption_filesystem_failed") from None
    _require_real_directory(
        path,
        missing_code="profile_adoption_filesystem_failed",
        invalid_code="profile_adoption_filesystem_failed",
    )
    with contextlib.suppress(OSError):
        path.chmod(0o700)


def _copy_regular_file(source: Path, destination: Path, expected: os.stat_result) -> int:
    source_descriptor = -1
    destination_descriptor = -1
    copied = 0
    try:
        source_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        source_descriptor = os.open(source, source_flags)
        opened = os.fstat(source_descriptor)
        if _is_reparse(opened) or not _same_file_identity(expected, opened):
            raise OSError("source identity changed")
        destination_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        destination_descriptor = os.open(destination, destination_flags, 0o600)
        while True:
            block = os.read(source_descriptor, _COPY_CHUNK_BYTES)
            if not block:
                break
            view = memoryview(block)
            while view:
                written = os.write(destination_descriptor, view)
                if written <= 0:
                    raise OSError("short profile write")
                copied += written
                view = view[written:]
        final_descriptor = os.fstat(source_descriptor)
        final_path = os.lstat(source)
        if (
            copied != expected.st_size
            or _is_reparse(final_descriptor)
            or _is_reparse(final_path)
            or not _same_file_identity(expected, final_descriptor)
            or not _same_file_identity(expected, final_path)
        ):
            raise OSError("source changed while copied")
        return copied
    finally:
        if destination_descriptor >= 0:
            os.close(destination_descriptor)
        if source_descriptor >= 0:
            os.close(source_descriptor)


def _copy_profile_tree(source: Path, destination: Path) -> _CopyStats:
    _require_real_directory(
        source,
        missing_code="profile_adoption_source_missing",
        invalid_code="profile_adoption_source_invalid",
    )
    try:
        destination.mkdir(mode=0o700)
    except OSError:
        raise MediaCrawlerProfileAdoptionError("profile_adoption_copy_failed") from None

    def copy_directory(current_source: Path, current_destination: Path) -> _CopyStats:
        result = _CopyStats()
        try:
            with os.scandir(current_source) as iterator:
                entries = sorted(iterator, key=lambda item: item.name)
        except OSError:
            raise MediaCrawlerProfileAdoptionError("profile_adoption_source_invalid") from None
        for entry in entries:
            source_child = current_source / entry.name
            destination_child = current_destination / entry.name
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                raise MediaCrawlerProfileAdoptionError("profile_adoption_source_invalid") from None
            if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                continue
            if stat.S_ISDIR(info.st_mode):
                try:
                    current = os.lstat(source_child)
                    if not stat.S_ISDIR(current.st_mode) or stat.S_ISLNK(current.st_mode) or _is_reparse(current):
                        raise OSError("source directory changed")
                    destination_child.mkdir(mode=0o700)
                except OSError:
                    raise MediaCrawlerProfileAdoptionError("profile_adoption_source_invalid") from None
                result = result.added(copy_directory(source_child, destination_child))
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            try:
                copied = _copy_regular_file(source_child, destination_child, info)
            except OSError:
                raise MediaCrawlerProfileAdoptionError("profile_adoption_copy_failed") from None
            result = result.add(files=1, bytes_=copied)
        return result

    stats = copy_directory(source, destination)
    if stats.files == 0:
        raise MediaCrawlerProfileAdoptionError("profile_adoption_source_empty")
    return stats


def _path_exists(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _unlink_no_follow(path: Path) -> None:
    try:
        path.unlink()
    except PermissionError:
        with contextlib.suppress(OSError):
            os.chmod(path, stat.S_IWRITE, follow_symlinks=False)
        path.unlink()


def _remove_tree_no_follow(path: Path) -> None:
    """Remove one exact tree without traversing links or reparse points."""

    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        _unlink_no_follow(path)
        return
    try:
        with os.scandir(path) as iterator:
            entries = tuple(iterator)
    except FileNotFoundError:
        return
    for entry in entries:
        child = path / entry.name
        try:
            child_info = entry.stat(follow_symlinks=False)
        except FileNotFoundError:
            continue
        if stat.S_ISDIR(child_info.st_mode) and not stat.S_ISLNK(child_info.st_mode) and not _is_reparse(child_info):
            _remove_tree_no_follow(child)
        else:
            _unlink_no_follow(child)
    try:
        path.rmdir()
    except PermissionError:
        with contextlib.suppress(OSError):
            path.chmod(stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
        path.rmdir()


class _ProfileReplacement:
    """A lock-scoped reversible directory exchange within one runtime volume."""

    def __init__(self, candidate: Path, target: Path, backup: Path) -> None:
        self.candidate = candidate
        self.target = target
        self.backup = backup
        self.had_target = False
        self.installed = False

    def install(self) -> None:
        _require_real_directory(
            self.candidate,
            missing_code="profile_adoption_filesystem_failed",
            invalid_code="profile_adoption_filesystem_failed",
        )
        if _path_exists(self.backup):
            raise MediaCrawlerProfileAdoptionError("profile_adoption_filesystem_failed")
        if _path_exists(self.target):
            _require_real_directory(
                self.target,
                missing_code="profile_adoption_filesystem_failed",
                invalid_code="profile_adoption_filesystem_failed",
            )
            try:
                os.replace(self.target, self.backup)
            except OSError:
                raise MediaCrawlerProfileAdoptionError("profile_adoption_filesystem_failed") from None
            self.had_target = True
        try:
            os.replace(self.candidate, self.target)
        except OSError:
            if self.had_target:
                try:
                    os.replace(self.backup, self.target)
                except OSError:
                    raise MediaCrawlerProfileAdoptionError("profile_adoption_rollback_failed") from None
            raise MediaCrawlerProfileAdoptionError("profile_adoption_filesystem_failed") from None
        self.installed = True

    def rollback(self) -> None:
        if not self.installed:
            return
        try:
            os.replace(self.target, self.candidate)
            if self.had_target:
                os.replace(self.backup, self.target)
        except OSError:
            # Keep the new profile usable if restoring the previous directory
            # failed halfway through, but never publish authentication for it.
            if not _path_exists(self.target) and _path_exists(self.candidate):
                with contextlib.suppress(OSError):
                    os.replace(self.candidate, self.target)
            raise MediaCrawlerProfileAdoptionError("profile_adoption_rollback_failed") from None
        finally:
            self.installed = False

    def commit(self) -> None:
        if self.had_target:
            try:
                _remove_tree_no_follow(self.backup)
            except OSError:
                raise MediaCrawlerProfileAdoptionError("profile_adoption_cleanup_failed") from None
        self.installed = False


class MediaCrawlerWebUIProfileAdoptionService:
    """Copy, probe, then publish an upstream-console profile under account fencing."""

    def __init__(
        self,
        database: Database,
        runner: _Runner,
        *,
        integration_root: Path,
        clock: Callable[[], datetime] = _utc_now,
        uuid_factory: Callable[[], UUID] = uuid4,
        lock_factory: _AccountLockFactory = MediaCrawlerAccountLock,
    ) -> None:
        if not isinstance(database, Database):
            raise TypeError("database must be a Database")
        if not callable(getattr(runner, "run", None)):
            raise TypeError("runner must implement the MediaCrawler login boundary")
        if not isinstance(integration_root, Path):
            raise TypeError("integration_root must be a Path")
        if not callable(clock) or not callable(uuid_factory) or not callable(lock_factory):
            raise TypeError("clock, uuid_factory, and lock_factory must be callable")
        self._database = database
        self._runner = runner
        self._integration_root = integration_root.expanduser().resolve()
        self._clock = clock
        self._uuid_factory = uuid_factory
        self._lock_factory = lock_factory

    def __call__(
        self,
        account_id: UUID,
        expected_auth_revision: int,
    ) -> MediaCrawlerProfileAdoptionResult:
        """Expose the exact callable shape expected by the mounted WebUI."""

        return self.adopt_account(account_id, expected_auth_revision)

    def adopt_account(
        self,
        account_id: UUID,
        expected_auth_revision: int,
        *,
        cancellation: threading.Event | None = None,
    ) -> MediaCrawlerProfileAdoptionResult:
        return self.adopt(
            MediaCrawlerProfileAdoptionRequest(account_id, expected_auth_revision),
            cancellation=cancellation,
        )

    def adopt(
        self,
        request: MediaCrawlerProfileAdoptionRequest,
        *,
        cancellation: threading.Event | None = None,
    ) -> MediaCrawlerProfileAdoptionResult:
        if not isinstance(request, MediaCrawlerProfileAdoptionRequest):
            raise TypeError("request must be a MediaCrawlerProfileAdoptionRequest")
        if cancellation is not None and not isinstance(cancellation, threading.Event):
            raise TypeError("cancellation must be a threading.Event")
        if cancellation is not None and cancellation.is_set():
            raise MediaCrawlerProfileAdoptionError("profile_adoption_cancelled")

        snapshot = self._snapshot(request)
        try:
            platform = Platform(snapshot.platform)
        except ValueError:
            raise MediaCrawlerProfileAdoptionError("profile_adoption_account_ineligible") from None
        staging_id = self._uuid_factory()
        if not isinstance(staging_id, UUID) or staging_id == request.account_id:
            raise MediaCrawlerProfileAdoptionError("profile_adoption_filesystem_failed")
        staging_paths = build_run_paths(self._integration_root, platform, staging_id, staging_id)
        target_paths = build_run_paths(self._integration_root, platform, request.account_id, request.account_id)
        source_profile = self._integration_root / "webui-profiles" / f"{platform.value}_user_data_dir"
        backup = target_paths.profile_root.parent / f".profile-adoption-backup-{staging_id.hex}"
        staging_created = False
        target_lock: _AccountLock | None = None
        replacement: _ProfileReplacement | None = None

        try:
            staging_created = self._prepare_staging(staging_paths)
            stats = _copy_profile_tree(source_profile, staging_paths.profile_root)
            if cancellation is not None and cancellation.is_set():
                raise MediaCrawlerProfileAdoptionError("profile_adoption_cancelled")
            probe = self._probe(request, platform, staging_id, cancellation)
            if cancellation is not None and cancellation.is_set():
                raise MediaCrawlerProfileAdoptionError("profile_adoption_cancelled")

            self._prepare_target(target_paths)
            target_lock = self._lock_factory(self._integration_root, platform, request.account_id)
            if not target_lock.acquire():
                raise MediaCrawlerProfileAdoptionError("profile_adoption_busy")
            replacement = _ProfileReplacement(staging_paths.profile_root, target_paths.profile_root, backup)
            replacement.install()
            try:
                if cancellation is not None and cancellation.is_set():
                    raise MediaCrawlerProfileAdoptionError("profile_adoption_cancelled")
                at = self._now()
                with self._database.session() as session:
                    revision = ProfileAdoptionAccountRepository(session).publish(snapshot, at=at)
                    resumed_job_count = SchedulerRepository(session).resume_waiting_auth_for_account(
                        request.account_id,
                        now=at,
                    )
            except BaseException:
                replacement.rollback()
                raise
            replacement.commit()
            return MediaCrawlerProfileAdoptionResult(
                account_id=request.account_id,
                platform=platform,
                auth_revision=revision,
                upstream_sha=probe.upstream_sha or "",  # authenticated results always carry a full SHA
                profile_file_count=stats.files,
                profile_byte_count=stats.bytes,
                resumed_job_count=resumed_job_count,
            )
        except ProfileAdoptionAccountError as error:
            raise MediaCrawlerProfileAdoptionError(error.code) from None
        except MediaCrawlerProfileAdoptionError:
            raise
        except (OSError, SQLAlchemyError, SchedulerRepositoryError, ValueError):
            raise MediaCrawlerProfileAdoptionError("profile_adoption_filesystem_failed") from None
        finally:
            if target_lock is not None:
                target_lock.release()
            if staging_created:
                # A failed operation already has a stable primary reason.
                # Successful paths normally leave only an empty browser_data
                # directory and the closed probe lock file here.
                with contextlib.suppress(OSError):
                    _remove_tree_no_follow(staging_paths.account_root)

    def _snapshot(self, request: MediaCrawlerProfileAdoptionRequest) -> ProfileAdoptionAccountSnapshot:
        try:
            with self._database.session() as session:
                return ProfileAdoptionAccountRepository(session).snapshot(
                    str(request.account_id),
                    request.expected_auth_revision,
                )
        except ProfileAdoptionAccountError as error:
            raise MediaCrawlerProfileAdoptionError(error.code) from None
        except (SQLAlchemyError, ValueError):
            raise MediaCrawlerProfileAdoptionError("profile_adoption_conflict") from None

    def _prepare_staging(self, paths: RunPaths) -> bool:
        _ensure_real_directory(paths.integration_root)
        _ensure_real_directory(paths.integration_root / "accounts")
        _ensure_real_directory(paths.account_root.parent)
        try:
            paths.account_root.mkdir(mode=0o700)
        except OSError:
            raise MediaCrawlerProfileAdoptionError("profile_adoption_filesystem_failed") from None
        try:
            _require_real_directory(
                paths.account_root,
                missing_code="profile_adoption_filesystem_failed",
                invalid_code="profile_adoption_filesystem_failed",
            )
            _ensure_real_directory(paths.account_root / "browser_data")
        except BaseException:
            with contextlib.suppress(OSError):
                _remove_tree_no_follow(paths.account_root)
            raise
        return True

    def _prepare_target(self, paths: RunPaths) -> None:
        _ensure_real_directory(paths.integration_root)
        _ensure_real_directory(paths.integration_root / "accounts")
        _ensure_real_directory(paths.account_root.parent)
        _ensure_real_directory(paths.account_root)
        _ensure_real_directory(paths.profile_root.parent)

    def _probe(
        self,
        request: MediaCrawlerProfileAdoptionRequest,
        platform: Platform,
        staging_id: UUID,
        cancellation: threading.Event | None,
    ) -> MediaCrawlerLoginResult:
        probe_request = MediaCrawlerLoginRequest(
            account_id=staging_id,
            platform=platform,
            mode=MediaCrawlerLoginMode.SAVED_SESSION_PROBE,
            timeout_seconds=request.timeout_seconds,
            poll_seconds=request.poll_seconds,
        )
        try:
            result = self._runner.run(probe_request, cancellation=cancellation)
        except Exception:
            raise MediaCrawlerProfileAdoptionError("profile_adoption_probe_unavailable") from None
        if not isinstance(result, MediaCrawlerLoginResult):
            raise MediaCrawlerProfileAdoptionError("profile_adoption_result_invalid")
        if result.status is not MediaCrawlerLoginStatus.AUTHENTICATED:
            raise MediaCrawlerProfileAdoptionError(
                _PROBE_FAILURE_CODES.get(result.status, "profile_adoption_result_invalid")
            )
        if result.upstream_sha is None:
            raise MediaCrawlerProfileAdoptionError("profile_adoption_result_invalid")
        return result

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise MediaCrawlerProfileAdoptionError("profile_adoption_conflict")
        return value.astimezone(UTC)


__all__ = [
    "PROFILE_ADOPTION_ERROR_CODES",
    "MediaCrawlerProfileAdoptionError",
    "MediaCrawlerProfileAdoptionRequest",
    "MediaCrawlerProfileAdoptionResult",
    "MediaCrawlerWebUIProfileAdoptionService",
]
