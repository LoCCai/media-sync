"""Lease-fenced application orchestration for one media asset download."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from media_sync.domain import AssetKind, AssetStatus, Platform
from media_sync.infrastructure.db import (
    AssetConflictError,
    AssetLeaseLostError,
    AssetRepository,
    Database,
    JobRepository,
    LeaseLostError,
    NotFoundError,
    RepositoryError,
)
from media_sync.media import (
    ArchivePublisher,
    DownloadRequest,
    DownloadResult,
    MediaDownloadError,
    SecureMediaDownloader,
    parse_locator,
)
from media_sync.security.paths import PathLockBusyError, PathSecurityError, ensure_secure_root, exclusive_file_lock

from .operations import DurableSubjectHook, DurableSubjectRef

ASSET_DOWNLOAD_JOB_TYPE = "asset_download"


def _requires_static_image(platform: str, kind: str) -> bool:
    return platform in {Platform.TIEBA.value, Platform.ZHIHU.value} and kind == AssetKind.IMAGE.value


_ORCHESTRATION_ERRORS: dict[str, tuple[str, bool]] = {
    "asset_download_not_found": ("asset was not found", False),
    "asset_download_busy": ("asset download is owned by another active worker", True),
    "asset_download_terminal": ("asset download has reached a terminal state", False),
    "asset_download_state_changed": ("asset download state changed concurrently", True),
    "asset_download_state_invalid": ("asset download state is inconsistent", False),
    "asset_download_io_scope_mismatch": ("asset download I/O scope does not match its durable job", False),
    "asset_download_lease_lost": ("asset download lease was lost", True),
    "asset_download_lease_check_failed": ("asset download lease could not be checked", True),
    "asset_download_start_failed": ("asset download could not be started", True),
    "asset_download_finalize_failed": ("asset download could not be finalized", True),
    "asset_download_failure_finalize_failed": ("asset download failure could not be finalized", True),
    "asset_download_archive_reset_failed": ("invalid verified archive state could not be reset", True),
    "asset_download_worker_failed": ("asset download worker failed unexpectedly", True),
}


class AssetDownloadOrchestrationError(RuntimeError):
    """A redaction-safe, fixed-code application failure."""

    def __init__(self, code: str) -> None:
        try:
            message, retryable = _ORCHESTRATION_ERRORS[code]
        except KeyError as exc:  # pragma: no cover - programmer error
            raise ValueError("unknown asset download orchestration error code") from exc
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(f"{code}: {message}")

    @classmethod
    def _from_fixed(cls, code: str, *, retryable: bool) -> AssetDownloadOrchestrationError:
        try:
            message, _default_retryable = _ORCHESTRATION_ERRORS[code]
        except KeyError as exc:  # pragma: no cover - programmer error
            raise ValueError("unknown asset download orchestration error code") from exc
        instance = cls.__new__(cls)
        instance.code = code
        instance.message = message
        instance.retryable = retryable
        RuntimeError.__init__(instance, f"{code}: {message}")
        return instance

    @classmethod
    def _from_media(cls, error: MediaDownloadError, *, retryable: bool) -> AssetDownloadOrchestrationError:
        instance = cls.__new__(cls)
        instance.code = error.code
        instance.message = error.message
        instance.retryable = retryable
        RuntimeError.__init__(instance, f"{error.code}: {error.message}")
        return instance


def _canonical_local_root(value: Path) -> Path:
    """Normalize a local root without resolving or following filesystem links."""

    expanded = Path(value).expanduser().absolute()
    return Path(os.path.normpath(os.fspath(expanded)))


def asset_download_io_scope_fingerprint(work_root: Path, archive_root: Path) -> str:
    """Return a non-reversible identity for one local download coordination domain."""

    payload = {
        "archive_root": os.path.normcase(os.fspath(_canonical_local_root(archive_root))),
        "work_root": os.path.normcase(os.fspath(_canonical_local_root(work_root))),
    }
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class AssetDownloadRequest:
    """Persistable identifiers and local roots for one download attempt."""

    asset_id: UUID
    worker_id: str
    work_root: Path
    archive_root: Path
    lease_seconds: int = 60 * 60
    max_attempts: int = 5
    priority: int = 0

    def __post_init__(self) -> None:
        try:
            asset_id = self.asset_id if isinstance(self.asset_id, UUID) else UUID(str(self.asset_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("asset_id must be a UUID") from exc
        if not isinstance(self.worker_id, str):
            raise ValueError("worker_id must contain between 1 and 255 printable characters")
        worker_id = self.worker_id.strip()
        if (
            not worker_id
            or len(worker_id) > 255
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in worker_id)
        ):
            raise ValueError("worker_id must contain between 1 and 255 printable characters")
        if (
            isinstance(self.lease_seconds, bool)
            or not isinstance(self.lease_seconds, int)
            or not 1 <= self.lease_seconds <= 86_400
        ):
            raise ValueError("lease_seconds must be between 1 and 86400")
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or not 1 <= self.max_attempts <= 100
        ):
            raise ValueError("max_attempts must be between 1 and 100")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ValueError("priority must be an integer")
        object.__setattr__(self, "asset_id", asset_id)
        object.__setattr__(self, "worker_id", worker_id)
        object.__setattr__(self, "work_root", _canonical_local_root(self.work_root))
        object.__setattr__(self, "archive_root", _canonical_local_root(self.archive_root))

    @property
    def io_scope_fingerprint(self) -> str:
        """Bind the durable job to these roots without persisting either path."""

        return asset_download_io_scope_fingerprint(self.work_root, self.archive_root)


@dataclass(frozen=True, slots=True)
class AssetDownloadOutcome:
    """Verified database state returned without remote or secret material."""

    asset_id: UUID
    generation: int
    job_id: UUID | None
    status: AssetStatus
    disposition: Literal["downloaded", "already_verified"]
    archive_path: Path
    checksum_sha256: str
    size_bytes: int
    mime_type: str


@dataclass(frozen=True, slots=True)
class _PreparedDownload:
    asset_id: UUID
    generation: int
    kind: AssetKind
    require_static_image: bool
    locator: Mapping[str, object] = field(repr=False)
    job_id: UUID
    lease_token: str = field(repr=False)
    attempts: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class _PreparedRecovery:
    asset_id: UUID
    generation: int
    kind: AssetKind
    require_static_image: bool
    locator: Mapping[str, object] = field(repr=False)
    job_id: UUID
    lease_owner: str | None
    lease_token: str | None = field(repr=False)
    job_status: Literal["running", "failed_retryable", "failed_terminal"]
    attempts: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class _StartDecision:
    prepared: _PreparedDownload | None = None
    recovery: _PreparedRecovery | None = None
    outcome: AssetDownloadOutcome | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class _ClassifiedFailure:
    code: str
    message: str
    retryable: bool


def asset_download_natural_key(asset_id: UUID, generation: int) -> str:
    """Bind the one durable download job to an immutable asset generation."""

    if not isinstance(asset_id, UUID):
        raise TypeError("asset_id must be a UUID")
    if isinstance(generation, bool) or generation < 1:
        raise ValueError("generation must be positive")
    return f"{asset_id}:{generation}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AssetDownloadService:
    """Run database transitions around network and filesystem work.

    The start and finalization phases each use one short transaction.  Locator
    parsing, DNS, HTTP, probing and archive publication happen between them,
    while no SQLAlchemy session is open.
    """

    def __init__(
        self,
        database: Database,
        downloader: SecureMediaDownloader,
        *,
        clock: Callable[[], datetime] = _utc_now,
        verified_archive_recovery_preflight: Callable[[], None] | None = None,
    ) -> None:
        if verified_archive_recovery_preflight is not None and not callable(verified_archive_recovery_preflight):
            raise TypeError("verified_archive_recovery_preflight must be callable")
        self._database = database
        self._downloader = downloader
        self._clock = clock
        self._verified_archive_recovery_preflight = verified_archive_recovery_preflight

    def run(
        self,
        request: AssetDownloadRequest,
        *,
        subject_hook: DurableSubjectHook | None = None,
    ) -> AssetDownloadOutcome:
        """Download one asset or return its already-verified state."""

        try:
            work_root = ensure_secure_root(request.work_root)
            lock_relative = Path("orchestration-locks") / f"{request.asset_id}.lock"
            with exclusive_file_lock(work_root, lock_relative):
                return self._run_locked(request, subject_hook=subject_hook)
        except PathLockBusyError:
            raise AssetDownloadOrchestrationError("asset_download_busy") from None
        except PathSecurityError:
            error = MediaDownloadError("filesystem_unsafe")
            raise AssetDownloadOrchestrationError._from_media(error, retryable=False) from None

    def _run_locked(
        self,
        request: AssetDownloadRequest,
        *,
        subject_hook: DurableSubjectHook | None,
    ) -> AssetDownloadOutcome:
        """Hold the work-root/asset orchestration lock through DB finalization."""

        decision = self._begin(request, subject_hook=subject_hook)
        if decision.recovery is not None:
            recovery = decision.recovery
            recovered_result = self._recover_published_result(request, recovery)
            if recovered_result is None:
                decision = self._begin(
                    request,
                    allow_prepared_recovery=False,
                    subject_hook=subject_hook,
                )
            else:
                prepared_recovery = self._takeover_prepared_recovery(
                    request,
                    recovery,
                )
                self._validate_recovered_archive(request, prepared_recovery, recovered_result)
                return self._finalize_success(request, prepared_recovery, recovered_result)
        if decision.outcome is not None:
            self._validate_verified_archive(request, decision.outcome)
            self._cleanup_partial_best_effort(request, decision.outcome.generation)
            return decision.outcome
        if decision.error_code is not None:
            raise AssetDownloadOrchestrationError(decision.error_code)
        prepared = decision.prepared
        if prepared is None:  # pragma: no cover - closed internal decision shape
            raise AssetDownloadOrchestrationError("asset_download_state_invalid")

        try:
            locator = parse_locator(prepared.locator)
            result = self._downloader.download(
                DownloadRequest(
                    asset_id=prepared.asset_id,
                    generation=prepared.generation,
                    locator=locator,
                    work_root=request.work_root,
                    archive_root=request.archive_root,
                    expected_kind=prepared.kind,
                    require_static_image=prepared.require_static_image,
                    before_archive_commit=lambda: self._guard_publish(request, prepared),
                )
            )
        except AssetDownloadOrchestrationError:
            raise
        except MediaDownloadError as error:
            retryable = error.retryable and prepared.attempts < prepared.max_attempts
            failure = _ClassifiedFailure(
                code=error.code,
                message=error.message,
                retryable=retryable,
            )
            self._record_failure(request, prepared, failure)
            raise AssetDownloadOrchestrationError._from_media(error, retryable=retryable) from None
        except Exception:
            failure = _ClassifiedFailure(
                code="asset_download_worker_failed",
                message=_ORCHESTRATION_ERRORS["asset_download_worker_failed"][0],
                retryable=prepared.attempts < prepared.max_attempts,
            )
            self._record_failure(request, prepared, failure)
            raise AssetDownloadOrchestrationError._from_fixed(
                "asset_download_worker_failed",
                retryable=failure.retryable,
            ) from None

        return self._finalize_success(request, prepared, result)

    def _recover_published_result(
        self,
        request: AssetDownloadRequest,
        recovery: _PreparedRecovery,
    ) -> DownloadResult | None:
        try:
            locator = parse_locator(recovery.locator)
            return self._downloader.recover_published(
                DownloadRequest(
                    asset_id=recovery.asset_id,
                    generation=recovery.generation,
                    locator=locator,
                    work_root=request.work_root,
                    archive_root=request.archive_root,
                    expected_kind=recovery.kind,
                    require_static_image=recovery.require_static_image,
                )
            )
        except MediaDownloadError as error:
            raise AssetDownloadOrchestrationError._from_media(error, retryable=error.retryable) from None
        except Exception:
            raise AssetDownloadOrchestrationError._from_fixed(
                "asset_download_worker_failed",
                retryable=recovery.attempts < recovery.max_attempts,
            ) from None

    def _takeover_prepared_recovery(
        self,
        request: AssetDownloadRequest,
        recovery: _PreparedRecovery,
    ) -> _PreparedDownload:
        try:
            now = self._now()
            with self._database.session() as session:
                jobs = JobRepository(session)
                if recovery.job_status == "running":
                    if recovery.lease_owner is None or recovery.lease_token is None:
                        raise AssetLeaseLostError("expired prepared lease identity is incomplete")
                    running = jobs.takeover_expired_running_lease(
                        str(recovery.job_id),
                        expected_worker_id=recovery.lease_owner,
                        expected_lease_token=recovery.lease_token,
                        worker_id=request.worker_id,
                        lease_seconds=request.lease_seconds,
                        now=now,
                    )
                else:
                    running = jobs.resume_reclaimed_prepared_result(
                        str(recovery.job_id),
                        expected_status=recovery.job_status,
                        worker_id=request.worker_id,
                        lease_seconds=request.lease_seconds,
                        now=now,
                    )
                if running.lease_token is None:
                    raise AssetLeaseLostError("prepared recovery did not establish a lease token")
                assets = AssetRepository(session)
                asset = assets.require(str(recovery.asset_id))
                if recovery.job_status != "running" and asset.status != AssetStatus.DOWNLOADING.value:
                    expected_asset_status = (
                        AssetStatus.FAILED_RETRYABLE.value
                        if recovery.job_status == "failed_retryable"
                        else AssetStatus.FAILED_TERMINAL.value
                    )
                    asset = assets.resume_reclaimed_prepared_result(
                        asset.id,
                        expected_generation=recovery.generation,
                        expected_status=expected_asset_status,
                        job_id=running.id,
                        worker_id=request.worker_id,
                        lease_token=running.lease_token,
                        at=now,
                    )
                if (
                    asset.generation != recovery.generation
                    or asset.status != AssetStatus.DOWNLOADING.value
                    or asset.download_job_id != running.id
                    or running.lease_token is None
                ):
                    raise AssetLeaseLostError("prepared download ownership changed during recovery")
                return _PreparedDownload(
                    asset_id=recovery.asset_id,
                    generation=recovery.generation,
                    kind=recovery.kind,
                    require_static_image=recovery.require_static_image,
                    locator=recovery.locator,
                    job_id=recovery.job_id,
                    lease_token=running.lease_token,
                    attempts=running.attempts,
                    max_attempts=running.max_attempts,
                )
        except (AssetLeaseLostError, LeaseLostError, NotFoundError):
            raise AssetDownloadOrchestrationError("asset_download_lease_lost") from None
        except AssetDownloadOrchestrationError:
            raise
        except Exception:
            raise AssetDownloadOrchestrationError("asset_download_start_failed") from None

    def _validate_recovered_archive(
        self,
        request: AssetDownloadRequest,
        prepared: _PreparedDownload,
        result: DownloadResult,
    ) -> None:
        try:
            ArchivePublisher(request.archive_root).validate_existing(
                result.archive_path,
                sha256=result.sha256,
                size_bytes=result.size_bytes,
            )
            self._guard_publish(request, prepared)
        except AssetDownloadOrchestrationError:
            raise
        except MediaDownloadError as error:
            raise AssetDownloadOrchestrationError._from_media(error, retryable=error.retryable) from None

    def _guard_publish(self, request: AssetDownloadRequest, prepared: _PreparedDownload) -> None:
        """Renew the exact lease and recheck asset ownership before archive publication."""

        try:
            now = self._now()
            with self._database.session() as session:
                JobRepository(session).renew_unreclaimed_lease(
                    str(prepared.job_id),
                    worker_id=request.worker_id,
                    lease_token=prepared.lease_token,
                    lease_seconds=request.lease_seconds,
                    now=now,
                )
                asset = AssetRepository(session).require(str(prepared.asset_id))
                if (
                    asset.generation != prepared.generation
                    or asset.status != AssetStatus.DOWNLOADING.value
                    or asset.download_job_id != str(prepared.job_id)
                ):
                    raise AssetLeaseLostError("asset download ownership changed before publication")
        except (AssetLeaseLostError, LeaseLostError, NotFoundError):
            raise AssetDownloadOrchestrationError("asset_download_lease_lost") from None
        except AssetDownloadOrchestrationError:
            raise
        except Exception:
            raise AssetDownloadOrchestrationError("asset_download_lease_check_failed") from None

    def _validate_verified_archive(self, request: AssetDownloadRequest, outcome: AssetDownloadOutcome) -> None:
        try:
            ArchivePublisher(request.archive_root).validate_existing(
                outcome.archive_path,
                sha256=outcome.checksum_sha256,
                size_bytes=outcome.size_bytes,
            )
        except MediaDownloadError as error:
            if error.code in {"archive_blob_missing", "archive_blob_invalid"}:
                self._preflight_verified_archive_recovery()
            if error.code == "archive_blob_invalid":
                try:
                    quarantined = ArchivePublisher(request.archive_root).quarantine_invalid(
                        outcome.archive_path,
                        sha256=outcome.checksum_sha256,
                        size_bytes=outcome.size_bytes,
                    )
                except MediaDownloadError as quarantine_error:
                    if quarantine_error.code == "archive_blob_missing":
                        error = quarantine_error
                    else:
                        raise AssetDownloadOrchestrationError._from_media(
                            quarantine_error,
                            retryable=quarantine_error.retryable,
                        ) from None
                else:
                    if quarantined is None:
                        return
            if error.code in {"archive_blob_missing", "archive_blob_invalid"}:
                try:
                    with self._database.session() as session:
                        AssetRepository(session).reset_verified_archive(
                            str(outcome.asset_id),
                            expected_generation=outcome.generation,
                            expected_local_path=str(outcome.archive_path),
                            expected_checksum_sha256=outcome.checksum_sha256,
                            expected_size_bytes=outcome.size_bytes,
                            error_code=error.code,
                            error_message=error.message,
                            at=self._now(),
                        )
                except AssetConflictError:
                    raise AssetDownloadOrchestrationError("asset_download_state_changed") from None
                except Exception:
                    raise AssetDownloadOrchestrationError("asset_download_archive_reset_failed") from None
            raise AssetDownloadOrchestrationError._from_media(error, retryable=error.retryable) from None

    def _preflight_verified_archive_recovery(self) -> None:
        """Authorize a needed repair before quarantine or durable generation reset."""

        preflight = self._verified_archive_recovery_preflight
        if preflight is None:
            return
        try:
            preflight()
        except AssetDownloadOrchestrationError:
            raise
        except MediaDownloadError as error:
            raise AssetDownloadOrchestrationError._from_media(error, retryable=error.retryable) from None
        except Exception:
            raise AssetDownloadOrchestrationError("asset_download_start_failed") from None

    def _begin(
        self,
        request: AssetDownloadRequest,
        *,
        allow_prepared_recovery: bool = True,
        subject_hook: DurableSubjectHook | None = None,
    ) -> _StartDecision:
        decision: _StartDecision | None = None
        try:
            now = self._now()
            with self._database.session() as session:
                assets = AssetRepository(session)
                jobs = JobRepository(session)
                asset = assets.require(str(request.asset_id))

                if asset.status == AssetStatus.VERIFIED.value:
                    verified_job = jobs.get(asset.download_job_id) if asset.download_job_id is not None else None
                    invalid_verified_job = (asset.download_job_id is not None and verified_job is None) or (
                        verified_job is not None
                        and (
                            verified_job.payload.get("asset_id") != str(request.asset_id)
                            or verified_job.payload.get("generation") != asset.generation
                        )
                    )
                    if verified_job is not None and not invalid_verified_job:
                        self._link_job_subject(session, subject_hook, verified_job.id)
                    if invalid_verified_job:
                        decision = _StartDecision(error_code="asset_download_state_invalid")
                    elif (
                        verified_job is not None
                        and verified_job.payload.get("io_scope_fingerprint") != request.io_scope_fingerprint
                    ):
                        decision = _StartDecision(error_code="asset_download_io_scope_mismatch")
                    else:
                        decision = _StartDecision(outcome=self._verified_outcome(asset, disposition="already_verified"))
                elif asset.status == AssetStatus.FAILED_TERMINAL.value:
                    terminal_job = jobs.get(asset.download_job_id) if asset.download_job_id is not None else None
                    if terminal_job is not None:
                        self._link_job_subject(session, subject_hook, terminal_job.id)
                    if (
                        allow_prepared_recovery
                        and terminal_job is not None
                        and terminal_job.status == "failed_terminal"
                        and terminal_job.last_error_code == "lease_expired"
                        and terminal_job.lease_owner is None
                        and terminal_job.lease_token is None
                        and terminal_job.lease_expires_at is None
                        and asset.last_error_code == "download_lease_expired"
                    ):
                        if (
                            terminal_job.payload.get("asset_id") != str(request.asset_id)
                            or terminal_job.payload.get("generation") != asset.generation
                        ):
                            decision = _StartDecision(error_code="asset_download_state_invalid")
                        elif terminal_job.payload.get("io_scope_fingerprint") != request.io_scope_fingerprint:
                            decision = _StartDecision(error_code="asset_download_io_scope_mismatch")
                        else:
                            decision = _StartDecision(
                                recovery=_PreparedRecovery(
                                    asset_id=UUID(asset.id),
                                    generation=asset.generation,
                                    kind=AssetKind(asset.kind),
                                    require_static_image=_requires_static_image(asset.platform, asset.kind),
                                    locator=MappingProxyType(dict(asset.locator)),
                                    job_id=UUID(terminal_job.id),
                                    lease_owner=None,
                                    lease_token=None,
                                    job_status="failed_terminal",
                                    attempts=terminal_job.attempts,
                                    max_attempts=terminal_job.max_attempts,
                                )
                            )
                    else:
                        decision = _StartDecision(error_code="asset_download_terminal")
                else:
                    natural_key = asset_download_natural_key(request.asset_id, asset.generation)
                    job = jobs.enqueue(
                        job_type=ASSET_DOWNLOAD_JOB_TYPE,
                        natural_key=natural_key,
                        payload={
                            "asset_id": str(request.asset_id),
                            "generation": asset.generation,
                            "io_scope_fingerprint": request.io_scope_fingerprint,
                        },
                        priority=request.priority,
                        max_attempts=request.max_attempts,
                        available_at=now,
                    )
                    self._link_job_subject(session, subject_hook, job.id)

                    if (
                        job.payload.get("asset_id") != str(request.asset_id)
                        or job.payload.get("generation") != asset.generation
                    ):
                        decision = _StartDecision(error_code="asset_download_state_invalid")
                    elif job.payload.get("io_scope_fingerprint") != request.io_scope_fingerprint:
                        decision = _StartDecision(error_code="asset_download_io_scope_mismatch")
                    elif (
                        allow_prepared_recovery
                        and asset.status == AssetStatus.FAILED_RETRYABLE.value
                        and asset.download_job_id == job.id
                        and asset.last_error_code == "download_lease_expired"
                        and job.status == "failed_retryable"
                        and job.last_error_code == "lease_expired"
                        and 0 < job.attempts < job.max_attempts
                        and job.lease_owner is None
                        and job.lease_token is None
                        and job.lease_expires_at is None
                    ):
                        decision = _StartDecision(
                            recovery=_PreparedRecovery(
                                asset_id=UUID(asset.id),
                                generation=asset.generation,
                                kind=AssetKind(asset.kind),
                                require_static_image=_requires_static_image(asset.platform, asset.kind),
                                locator=MappingProxyType(dict(asset.locator)),
                                job_id=UUID(job.id),
                                lease_owner=None,
                                lease_token=None,
                                job_status="failed_retryable",
                                attempts=job.attempts,
                                max_attempts=job.max_attempts,
                            )
                        )
                    elif asset.status == AssetStatus.DOWNLOADING.value:
                        if asset.download_job_id != job.id:
                            decision = _StartDecision(error_code="asset_download_state_invalid")
                        elif (
                            allow_prepared_recovery
                            and job.status == "failed_terminal"
                            and job.last_error_code == "lease_expired"
                            and job.lease_owner is None
                            and job.lease_token is None
                            and job.lease_expires_at is None
                        ):
                            decision = _StartDecision(
                                recovery=_PreparedRecovery(
                                    asset_id=UUID(asset.id),
                                    generation=asset.generation,
                                    kind=AssetKind(asset.kind),
                                    require_static_image=_requires_static_image(asset.platform, asset.kind),
                                    locator=MappingProxyType(dict(asset.locator)),
                                    job_id=UUID(job.id),
                                    lease_owner=None,
                                    lease_token=None,
                                    job_status="failed_terminal",
                                    attempts=job.attempts,
                                    max_attempts=job.max_attempts,
                                )
                            )
                        elif (
                            allow_prepared_recovery
                            and job.status == "running"
                            and job.lease_owner is not None
                            and job.lease_token is not None
                            and job.lease_expires_at is not None
                            and job.lease_expires_at <= now
                        ):
                            decision = _StartDecision(
                                recovery=_PreparedRecovery(
                                    asset_id=UUID(asset.id),
                                    generation=asset.generation,
                                    kind=AssetKind(asset.kind),
                                    require_static_image=_requires_static_image(asset.platform, asset.kind),
                                    locator=MappingProxyType(dict(asset.locator)),
                                    job_id=UUID(job.id),
                                    lease_owner=job.lease_owner,
                                    lease_token=job.lease_token,
                                    job_status="running",
                                    attempts=job.attempts,
                                    max_attempts=job.max_attempts,
                                )
                            )
                        else:
                            reclaimed = jobs.reclaim_expired(job_id=job.id, now=now)
                            if reclaimed or job.status in {"failed_retryable", "failed_terminal"}:
                                asset = assets.recover_expired_download(
                                    asset.id,
                                    expected_generation=asset.generation,
                                    expected_status=AssetStatus.DOWNLOADING.value,
                                    job_id=job.id,
                                    at=now,
                                )
                                if asset.status == AssetStatus.FAILED_TERMINAL.value:
                                    decision = _StartDecision(error_code="asset_download_terminal")
                            else:
                                decision = _StartDecision(error_code="asset_download_busy")

                    if decision is None:
                        if asset.status in {
                            AssetStatus.DISCOVERED.value,
                            AssetStatus.FAILED_RETRYABLE.value,
                        }:
                            asset = assets.queue(
                                asset.id,
                                expected_generation=asset.generation,
                                expected_status=asset.status,
                                at=now,
                            )
                        elif asset.status != AssetStatus.QUEUED.value:
                            decision = _StartDecision(error_code="asset_download_state_invalid")

                    if decision is None:
                        claimed = jobs.claim(
                            job.id,
                            worker_id=request.worker_id,
                            lease_seconds=request.lease_seconds,
                            now=now,
                        )
                        if claimed is None:
                            refreshed = jobs.get(job.id)
                            code = (
                                "asset_download_terminal"
                                if refreshed is not None and refreshed.status == "failed_terminal"
                                else "asset_download_busy"
                            )
                            decision = _StartDecision(error_code=code)
                        elif claimed.lease_token is None:  # pragma: no cover - repository invariant
                            decision = _StartDecision(error_code="asset_download_state_invalid")
                        else:
                            running = jobs.start(
                                claimed.id,
                                worker_id=request.worker_id,
                                lease_token=claimed.lease_token,
                                now=now,
                            )
                            downloading = assets.start(
                                asset.id,
                                expected_generation=asset.generation,
                                expected_status=AssetStatus.QUEUED.value,
                                job_id=running.id,
                                worker_id=request.worker_id,
                                lease_token=claimed.lease_token,
                                at=now,
                            )
                            decision = _StartDecision(
                                prepared=_PreparedDownload(
                                    asset_id=UUID(downloading.id),
                                    generation=downloading.generation,
                                    kind=AssetKind(downloading.kind),
                                    require_static_image=_requires_static_image(downloading.platform, downloading.kind),
                                    locator=MappingProxyType(dict(downloading.locator)),
                                    job_id=UUID(running.id),
                                    lease_token=claimed.lease_token,
                                    attempts=running.attempts,
                                    max_attempts=running.max_attempts,
                                )
                            )
        except AssetDownloadOrchestrationError:
            raise
        except NotFoundError:
            raise AssetDownloadOrchestrationError("asset_download_not_found") from None
        except AssetConflictError:
            raise AssetDownloadOrchestrationError("asset_download_state_changed") from None
        except (AssetLeaseLostError, LeaseLostError):
            raise AssetDownloadOrchestrationError("asset_download_lease_lost") from None
        except RepositoryError:
            raise AssetDownloadOrchestrationError("asset_download_state_invalid") from None
        except Exception:
            raise AssetDownloadOrchestrationError("asset_download_start_failed") from None

        if decision is None:  # pragma: no cover - every branch closes the decision
            raise AssetDownloadOrchestrationError("asset_download_state_invalid")
        return decision

    @staticmethod
    def _link_job_subject(
        session: Session,
        subject_hook: DurableSubjectHook | None,
        job_id: str,
    ) -> None:
        if subject_hook is not None:
            subject_hook(session, DurableSubjectRef("job", job_id))

    def _finalize_success(
        self,
        request: AssetDownloadRequest,
        prepared: _PreparedDownload,
        result: DownloadResult,
    ) -> AssetDownloadOutcome:
        try:
            now = self._now()
            with self._database.session() as session:
                jobs = JobRepository(session)
                jobs.renew_unreclaimed_lease(
                    str(prepared.job_id),
                    worker_id=request.worker_id,
                    lease_token=prepared.lease_token,
                    lease_seconds=request.lease_seconds,
                    now=now,
                )
                verified = AssetRepository(session).verify(
                    str(prepared.asset_id),
                    expected_generation=prepared.generation,
                    expected_status=AssetStatus.DOWNLOADING.value,
                    job_id=str(prepared.job_id),
                    worker_id=request.worker_id,
                    lease_token=prepared.lease_token,
                    mime_type=result.mime_type,
                    size_bytes=result.size_bytes,
                    checksum_sha256=result.sha256,
                    local_path=str(result.archive_path.absolute()),
                    etag=result.etag,
                    last_modified=result.last_modified,
                    at=now,
                )
                jobs.complete(
                    str(prepared.job_id),
                    worker_id=request.worker_id,
                    lease_token=prepared.lease_token,
                    now=now,
                )
                outcome = self._verified_outcome(verified, disposition="downloaded")
        except (AssetLeaseLostError, LeaseLostError, AssetConflictError):
            raise AssetDownloadOrchestrationError("asset_download_lease_lost") from None
        except Exception:
            raise AssetDownloadOrchestrationError("asset_download_finalize_failed") from None
        self._cleanup_partial_best_effort(request, prepared.generation)
        return outcome

    def _cleanup_partial_best_effort(self, request: AssetDownloadRequest, generation: int) -> None:
        """Retry-safe cleanup that can never reverse an already committed verification."""

        try:
            self._downloader.cleanup_partial(request.asset_id, generation, request.work_root)
        except Exception:
            return

    def _record_failure(
        self,
        request: AssetDownloadRequest,
        prepared: _PreparedDownload,
        failure: _ClassifiedFailure,
    ) -> None:
        try:
            now = self._now()
            with self._database.session() as session:
                failed_asset = AssetRepository(session).fail(
                    str(prepared.asset_id),
                    expected_generation=prepared.generation,
                    expected_status=AssetStatus.DOWNLOADING.value,
                    job_id=str(prepared.job_id),
                    worker_id=request.worker_id,
                    lease_token=prepared.lease_token,
                    retryable=failure.retryable,
                    error_code=failure.code,
                    error_message=failure.message,
                    at=now,
                )
                failed_job = JobRepository(session).fail(
                    str(prepared.job_id),
                    worker_id=request.worker_id,
                    lease_token=prepared.lease_token,
                    retryable=failure.retryable,
                    error_code=failure.code,
                    error_message=failure.message,
                    now=now,
                )
                expected_asset_status = (
                    AssetStatus.FAILED_RETRYABLE.value
                    if failed_job.status in {"failed_retryable", "retry_wait"}
                    else AssetStatus.FAILED_TERMINAL.value
                )
                if failed_asset.status != expected_asset_status:
                    raise RepositoryError("asset and job failure states diverged")
        except (AssetLeaseLostError, LeaseLostError, AssetConflictError):
            raise AssetDownloadOrchestrationError("asset_download_lease_lost") from None
        except Exception:
            raise AssetDownloadOrchestrationError("asset_download_failure_finalize_failed") from None

    def _now(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware timestamp")
        return current.astimezone(UTC)

    @staticmethod
    def _verified_outcome(
        asset: object,
        *,
        disposition: Literal["downloaded", "already_verified"],
    ) -> AssetDownloadOutcome:
        asset_id = getattr(asset, "id", None)
        generation = getattr(asset, "generation", None)
        job_id = getattr(asset, "download_job_id", None)
        local_path = getattr(asset, "local_path", None)
        checksum = getattr(asset, "checksum_sha256", None)
        size = getattr(asset, "size_bytes", None)
        mime_type = getattr(asset, "mime_type", None)
        status = getattr(asset, "status", None)
        if (
            not isinstance(asset_id, str)
            or isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 1
            or (job_id is not None and not isinstance(job_id, str))
            or not isinstance(local_path, str)
            or not local_path
            or not isinstance(checksum, str)
            or len(checksum) != 64
            or any(character not in "0123456789abcdef" for character in checksum)
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or not isinstance(mime_type, str)
            or not mime_type
            or status != AssetStatus.VERIFIED.value
        ):
            raise AssetDownloadOrchestrationError("asset_download_state_invalid")
        try:
            parsed_asset_id = UUID(asset_id)
            parsed_job_id = UUID(job_id) if job_id is not None else None
        except ValueError:
            raise AssetDownloadOrchestrationError("asset_download_state_invalid") from None
        return AssetDownloadOutcome(
            asset_id=parsed_asset_id,
            generation=generation,
            job_id=parsed_job_id,
            status=AssetStatus.VERIFIED,
            disposition=disposition,
            archive_path=Path(local_path),
            checksum_sha256=checksum,
            size_bytes=size,
            mime_type=mime_type,
        )


__all__ = [
    "ASSET_DOWNLOAD_JOB_TYPE",
    "AssetDownloadOrchestrationError",
    "AssetDownloadOutcome",
    "AssetDownloadRequest",
    "AssetDownloadService",
    "asset_download_natural_key",
]
