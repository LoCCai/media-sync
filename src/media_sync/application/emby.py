"""Lease-fenced database orchestration for deterministic Emby exports."""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import NoReturn, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from media_sync.domain.enums import AssetStatus
from media_sync.exporters.emby import (
    LAYOUT_VERSION,
    ContentFingerprint,
    ExportAuthor,
    ExportContent,
    ExportError,
    ExportResult,
    PublishedIdentity,
    RenderedExport,
    VerifiedAsset,
    author_relative_directory,
    content_source_fingerprint,
    export_source_fingerprint,
)
from media_sync.infrastructure.db import (
    Asset,
    Author,
    Content,
    Database,
    ExportRecordRepository,
    Job,
    JobRepository,
    LeaseLostError,
    RepositoryError,
    utc_now,
)

EMBY_EXPORTER_NAME = "emby"
EMBY_EXPORT_JOB_TYPE = "export.emby"

_RETRYABLE_EXPORT_CODES = frozenset(
    {
        "asset_not_verified",
        "author_lock_timeout",
        "export_failure_finalize_failed",
        "export_finalize_failed",
        "export_job_unavailable",
        "export_lease_check_failed",
        "export_lease_lost",
        "export_prepare_conflict",
        "export_prepare_failed",
        "no_clobber_publish_failed",
        "publish_capture_failed",
        "publish_failed",
        "stale_publish",
        "staging_exists",
        "unexpected_export_failure",
    }
)


class EmbyExporterPort(Protocol):
    """Small exporter surface needed by the database application service."""

    @property
    def export_root(self) -> Path: ...

    @property
    def coordination_scope(self) -> str: ...

    def render(
        self,
        author: ExportAuthor,
        contents: Sequence[ExportContent],
        *,
        job_id: str,
        expected_predecessor: PublishedIdentity | None,
    ) -> RenderedExport: ...

    def publish(self, rendered: RenderedExport) -> ExportResult: ...

    def discard(self, rendered: RenderedExport) -> None: ...

    def validate_published(
        self,
        author: ExportAuthor,
        expected_source_fingerprint: str,
        expected_tree_sha256: str,
        expected_manifest_sha256: str,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class EmbyExportRequest:
    """Inputs for one author-snapshot export attempt."""

    author_id: str
    worker_id: str
    lease_seconds: int = 300
    max_attempts: int = 5

    def __post_init__(self) -> None:
        try:
            author_id = str(UUID(self.author_id.strip()))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("author_id must be a UUID") from exc
        if not isinstance(self.worker_id, str):
            raise ValueError("worker_id must contain between 1 and 255 characters")
        worker_id = self.worker_id.strip()
        if (
            not worker_id
            or len(worker_id) > 255
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in worker_id)
        ):
            raise ValueError("worker_id must contain between 1 and 255 printable characters")
        if isinstance(self.lease_seconds, bool) or not 1 <= self.lease_seconds <= 86_400:
            raise ValueError("lease_seconds must be between 1 and 86400")
        if isinstance(self.max_attempts, bool) or not 1 <= self.max_attempts <= 100:
            raise ValueError("max_attempts must be between 1 and 100")
        object.__setattr__(self, "author_id", author_id)
        object.__setattr__(self, "worker_id", worker_id)


@dataclass(frozen=True, slots=True)
class EmbyExportOutcome:
    """Redaction-safe durable outcome of one successful export."""

    job_id: str
    source_fingerprint: str
    output_path: str
    rendered_fingerprint: str | None
    managed_file_count: int
    already_exported: bool


@dataclass(frozen=True, slots=True)
class _SnapshotContent:
    content_id: str
    source_fingerprint: str
    value: ExportContent


@dataclass(frozen=True, slots=True)
class _Snapshot:
    author: ExportAuthor
    contents: tuple[_SnapshotContent, ...]
    source_fingerprint: str
    output_path: str


@dataclass(frozen=True, slots=True)
class _RecordAttempt:
    record_id: str
    content_id: str
    source_fingerprint: str
    status: str
    rendered_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class _PublicationAnchor:
    job_id: str
    predecessor_job_id: str | None
    source_fingerprint: str
    tree_sha256: str
    manifest_sha256: str
    managed_file_count: int

    @property
    def identity(self) -> PublishedIdentity:
        return PublishedIdentity(
            self.source_fingerprint,
            self.tree_sha256,
            self.manifest_sha256,
        )


@dataclass(frozen=True, slots=True)
class _IntentRecord:
    record_id: str
    content_id: str
    source_fingerprint: str


@dataclass(frozen=True, slots=True)
class _PublicationIntent:
    source_fingerprint: str
    tree_sha256: str
    manifest_sha256: str
    managed_file_count: int
    records: tuple[_IntentRecord, ...]


@dataclass(frozen=True, slots=True)
class _PendingPublication:
    job_id: str
    predecessor_job_id: str | None
    source_fingerprint: str
    status: str
    attempts: int
    lease_token: str | None
    lease_expires_at: datetime | None
    payload: dict[str, object]
    intent: _PublicationIntent | None


@dataclass(frozen=True, slots=True)
class _PreparedAttempt:
    job_id: str
    worker_id: str
    lease_token: str
    staging_token: str
    snapshot: _Snapshot
    records: tuple[_RecordAttempt, ...]
    predecessor: _PublicationAnchor | None
    base_payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class _PreparationFailure:
    code: str


@dataclass(frozen=True, slots=True)
class _ExistingExport:
    job_id: str
    snapshot: _Snapshot
    rendered_fingerprint: str
    manifest_sha256: str
    managed_file_count: int


@dataclass(frozen=True, slots=True)
class _RecoveryScan:
    author_id: str
    snapshot: _Snapshot
    pending: tuple[_PendingPublication, ...]


def emby_export_natural_key(
    author_id: str,
    publication_scope: str,
    output_path: str,
    source_fingerprint: str,
    predecessor_job_id: str | None,
) -> str:
    """Bind a publication to its target, desired source, and exact DB predecessor."""

    payload = json.dumps(
        {
            "author_id": author_id,
            "exporter": EMBY_EXPORTER_NAME,
            "exporter_version": LAYOUT_VERSION,
            "output_path": output_path,
            "predecessor_job_id": predecessor_job_id,
            "publication_scope": publication_scope,
            "source_fingerprint": source_fingerprint,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{LAYOUT_VERSION}:{hashlib.sha256(payload).hexdigest()}"


def export_error_is_retryable(code: str) -> bool:
    """Return the fixed retry classification used for jobs and records."""

    return code in _RETRYABLE_EXPORT_CODES


def _classified_export_code(code: str) -> str:
    if 1 <= len(code) <= 128 and all(character in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in code):
        return code
    return "unexpected_export_failure"


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _is_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _base_publication_payload(
    *,
    author_id: str,
    publication_scope: str,
    output_path: str,
    source_fingerprint: str,
    predecessor_job_id: str | None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "author_id": author_id,
        "exporter": EMBY_EXPORTER_NAME,
        "exporter_version": LAYOUT_VERSION,
        "publication_scope": publication_scope,
        "output_path": output_path,
        "source_fingerprint": source_fingerprint,
        "predecessor_job_id": predecessor_job_id,
    }


def _result_payload(
    base: Mapping[str, object],
    *,
    tree_sha256: str,
    manifest_sha256: str,
    managed_file_count: int,
) -> dict[str, object]:
    return {
        **base,
        "result": {
            "schema_version": 1,
            "tree_sha256": tree_sha256,
            "manifest_sha256": manifest_sha256,
            "managed_file_count": managed_file_count,
        },
    }


def _intent_payload(prepared: _PreparedAttempt, rendered: RenderedExport) -> dict[str, object]:
    return {
        **prepared.base_payload,
        "intent": {
            "schema_version": 1,
            "source_fingerprint": prepared.snapshot.source_fingerprint,
            "tree_sha256": rendered.tree_sha256,
            "manifest_sha256": rendered.manifest_sha256,
            "managed_file_count": len(rendered.files),
            "records": [
                {
                    "record_id": item.record_id,
                    "content_id": item.content_id,
                    "source_fingerprint": item.source_fingerprint,
                }
                for item in prepared.records
            ],
        },
    }


def _payload_is_for_target(
    payload: object,
    *,
    author_id: str,
    publication_scope: str,
) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("author_id") != author_id:
        return False
    if payload.get("exporter") != EMBY_EXPORTER_NAME or payload.get("exporter_version") != LAYOUT_VERSION:
        return False
    scope = payload.get("publication_scope")
    if scope is None:
        raise ExportError("export_state_inconsistent")
    if not isinstance(scope, str):
        raise ExportError("export_state_inconsistent")
    return scope == publication_scope


def _parse_publication_base(
    job: Job,
    *,
    author_id: str,
    publication_scope: str,
    output_path: str,
) -> tuple[str, str | None, dict[str, object]]:
    payload = job.payload
    if not _payload_is_for_target(
        payload,
        author_id=author_id,
        publication_scope=publication_scope,
    ):
        raise ExportError("export_state_inconsistent")
    if not isinstance(payload, dict):  # pragma: no cover - narrowed above
        raise ExportError("export_state_inconsistent")
    source_fingerprint = payload.get("source_fingerprint")
    predecessor_job_id = payload.get("predecessor_job_id")
    if (
        payload.get("schema_version") != 1
        or payload.get("output_path") != output_path
        or not _is_sha256(source_fingerprint)
        or (predecessor_job_id is not None and not _is_uuid(predecessor_job_id))
        or predecessor_job_id == job.id
    ):
        raise ExportError("export_state_inconsistent")
    assert isinstance(source_fingerprint, str)
    assert predecessor_job_id is None or isinstance(predecessor_job_id, str)
    expected_key = emby_export_natural_key(
        author_id,
        publication_scope,
        output_path,
        source_fingerprint,
        predecessor_job_id,
    )
    if job.natural_key != expected_key:
        raise ExportError("export_state_inconsistent")
    return source_fingerprint, predecessor_job_id, dict(payload)


def _parse_publication_result(
    job: Job,
    *,
    author_id: str,
    publication_scope: str,
    output_path: str,
) -> _PublicationAnchor:
    source_fingerprint, predecessor_job_id, payload = _parse_publication_base(
        job,
        author_id=author_id,
        publication_scope=publication_scope,
        output_path=output_path,
    )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ExportError("export_state_inconsistent")
    tree_sha256 = result.get("tree_sha256")
    manifest_sha256 = result.get("manifest_sha256")
    managed_file_count = result.get("managed_file_count")
    if (
        result.get("schema_version") != 1
        or not _is_sha256(tree_sha256)
        or not _is_sha256(manifest_sha256)
        or isinstance(managed_file_count, bool)
        or not isinstance(managed_file_count, int)
        or managed_file_count < 0
    ):
        raise ExportError("export_state_inconsistent")
    assert isinstance(tree_sha256, str)
    assert isinstance(manifest_sha256, str)
    return _PublicationAnchor(
        job_id=job.id,
        predecessor_job_id=predecessor_job_id,
        source_fingerprint=source_fingerprint,
        tree_sha256=tree_sha256,
        manifest_sha256=manifest_sha256,
        managed_file_count=managed_file_count,
    )


def _parse_publication_intent(payload: Mapping[str, object], source_fingerprint: str) -> _PublicationIntent | None:
    raw_intent = payload.get("intent")
    if raw_intent is None:
        return None
    if not isinstance(raw_intent, dict):
        raise ExportError("export_state_inconsistent")
    tree_sha256 = raw_intent.get("tree_sha256")
    manifest_sha256 = raw_intent.get("manifest_sha256")
    managed_file_count = raw_intent.get("managed_file_count")
    raw_records = raw_intent.get("records")
    if (
        raw_intent.get("schema_version") != 1
        or raw_intent.get("source_fingerprint") != source_fingerprint
        or not _is_sha256(tree_sha256)
        or not _is_sha256(manifest_sha256)
        or isinstance(managed_file_count, bool)
        or not isinstance(managed_file_count, int)
        or managed_file_count < 0
        or not isinstance(raw_records, list)
    ):
        raise ExportError("export_state_inconsistent")
    records: list[_IntentRecord] = []
    identities: set[tuple[str, str]] = set()
    for value in raw_records:
        if not isinstance(value, dict):
            raise ExportError("export_state_inconsistent")
        record_id = value.get("record_id")
        content_id = value.get("content_id")
        record_source = value.get("source_fingerprint")
        if not _is_uuid(record_id) or not _is_uuid(content_id) or record_source != source_fingerprint:
            raise ExportError("export_state_inconsistent")
        assert isinstance(record_id, str) and isinstance(content_id, str) and isinstance(record_source, str)
        identity = (record_id, content_id)
        if identity in identities:
            raise ExportError("export_state_inconsistent")
        identities.add(identity)
        records.append(_IntentRecord(record_id, content_id, record_source))
    assert isinstance(tree_sha256, str)
    assert isinstance(manifest_sha256, str)
    return _PublicationIntent(
        source_fingerprint=source_fingerprint,
        tree_sha256=tree_sha256,
        manifest_sha256=manifest_sha256,
        managed_file_count=managed_file_count,
        records=tuple(records),
    )


class EmbyExportService:
    """Export a complete active author snapshot without holding I/O transactions."""

    def __init__(
        self,
        database: Database,
        exporter: EmbyExporterPort,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._database = database
        self._exporter = exporter
        publication_scope = exporter.coordination_scope
        if not _is_sha256(publication_scope):
            raise ExportError("export_scope_invalid")
        self._publication_scope = publication_scope
        self._clock = clock

    def export_author(self, request: EmbyExportRequest) -> EmbyExportOutcome:
        """Run one exact job from DB snapshot through publication and atomic finalize."""

        scan_recovery = True
        recovered_count = 0
        while True:
            try:
                prepared = self._prepare(request, scan_recovery=scan_recovery)
            except ExportError:
                raise
            except RepositoryError:
                raise ExportError("export_prepare_conflict") from None
            except Exception:
                raise ExportError("export_prepare_failed") from None

            if isinstance(prepared, _RecoveryScan):
                if self._recover_published_predecessor(prepared):
                    recovered_count += 1
                    if recovered_count > 100:
                        raise ExportError("export_state_inconsistent")
                    scan_recovery = True
                else:
                    scan_recovery = False
                continue
            if isinstance(prepared, _ExistingExport):
                return self._already_exported(prepared)
            if isinstance(prepared, _PreparationFailure):
                raise ExportError(prepared.code)
            return self._run_prepared(request, prepared)

    def _run_prepared(self, request: EmbyExportRequest, prepared: _PreparedAttempt) -> EmbyExportOutcome:
        rendered: RenderedExport | None = None
        try:
            rendered = self._exporter.render(
                prepared.snapshot.author,
                tuple(item.value for item in prepared.snapshot.contents),
                job_id=prepared.staging_token,
                expected_predecessor=(None if prepared.predecessor is None else prepared.predecessor.identity),
            )
            self._validate_rendered(prepared, rendered)
        except ExportError as error:
            self._discard_rendered(rendered)
            self._raise_attempt_failure(prepared, _classified_export_code(error.code))
        except Exception:
            self._discard_rendered(rendered)
            self._raise_attempt_failure(prepared, "unexpected_export_failure")

        try:
            self._renew_before_publish(prepared, request, rendered)
        except LeaseLostError:
            self._discard_rendered(rendered)
            raise ExportError("export_lease_lost") from None
        except Exception:
            self._discard_rendered(rendered)
            raise ExportError("export_lease_check_failed") from None

        try:
            result = self._exporter.publish(rendered)
            self._validate_result(prepared, rendered, result)
        except ExportError as error:
            self._discard_rendered(rendered)
            self._raise_attempt_failure(prepared, _classified_export_code(error.code))
        except Exception:
            self._discard_rendered(rendered)
            self._raise_attempt_failure(prepared, "unexpected_export_failure")

        try:
            self._finalize(prepared, result)
        except LeaseLostError:
            raise ExportError("export_lease_lost") from None
        except Exception:
            raise ExportError("export_finalize_failed") from None

        return EmbyExportOutcome(
            job_id=prepared.job_id,
            source_fingerprint=result.source_fingerprint,
            output_path=prepared.snapshot.output_path,
            rendered_fingerprint=result.tree_sha256,
            managed_file_count=len(result.managed_files),
            already_exported=False,
        )

    def _discard_rendered(self, rendered: RenderedExport | None) -> None:
        if rendered is None:
            return
        with contextlib.suppress(Exception):
            self._exporter.discard(rendered)

    def _prepare(
        self,
        request: EmbyExportRequest,
        *,
        scan_recovery: bool,
    ) -> _PreparedAttempt | _ExistingExport | _PreparationFailure | _RecoveryScan:
        with self._database.session() as session:
            snapshot = self._load_snapshot(session, request.author_id)
            publication_scope = self._publication_scope
            jobs = JobRepository(session)
            records = ExportRecordRepository(session)
            head, pending = self._load_publication_state(
                session,
                author_id=request.author_id,
                publication_scope=publication_scope,
                output_path=snapshot.output_path,
            )
            recoverable = tuple(item for item in pending if item.intent is not None)
            if scan_recovery and recoverable:
                return _RecoveryScan(
                    author_id=request.author_id,
                    snapshot=snapshot,
                    pending=recoverable,
                )
            if head is not None and head.source_fingerprint == snapshot.source_fingerprint:
                return self._load_existing_export(records, snapshot, head)

            predecessor_job_id = None if head is None else head.job_id
            base_payload = _base_publication_payload(
                author_id=request.author_id,
                publication_scope=publication_scope,
                output_path=snapshot.output_path,
                source_fingerprint=snapshot.source_fingerprint,
                predecessor_job_id=predecessor_job_id,
            )
            job = jobs.enqueue(
                job_type=EMBY_EXPORT_JOB_TYPE,
                natural_key=emby_export_natural_key(
                    request.author_id,
                    publication_scope,
                    snapshot.output_path,
                    snapshot.source_fingerprint,
                    predecessor_job_id,
                ),
                payload=base_payload,
                max_attempts=request.max_attempts,
                available_at=self._clock(),
            )
            job_source, job_predecessor, _ = _parse_publication_base(
                job,
                author_id=request.author_id,
                publication_scope=publication_scope,
                output_path=snapshot.output_path,
            )
            if job_source != snapshot.source_fingerprint or job_predecessor != predecessor_job_id:
                raise ExportError("export_state_inconsistent")
            if job.status == "succeeded":
                current_head, _ = self._load_publication_state(
                    session,
                    author_id=request.author_id,
                    publication_scope=publication_scope,
                    output_path=snapshot.output_path,
                )
                if current_head is None or current_head.job_id != job.id:
                    raise RepositoryError("completed publication is not the current chain head")
                return self._load_existing_export(records, snapshot, current_head)

            first_attempt = job.attempts == 0
            claimed = jobs.claim(
                job.id,
                worker_id=request.worker_id,
                lease_seconds=request.lease_seconds,
                now=self._clock(),
            )
            if claimed is None:
                current_job = jobs.get(job.id)
                if current_job is not None and current_job.status in {"failed_terminal", "cancelled"}:
                    terminal_code = (
                        "export_lease_expired"
                        if current_job.last_error_code == "lease_expired"
                        else "export_job_terminal"
                    )
                    self._terminalize_running_records(records, snapshot, error_code=terminal_code)
                    return _PreparationFailure("export_job_terminal")
                return _PreparationFailure("export_job_unavailable")
            if claimed.lease_token is None:  # pragma: no cover - claim writes the token atomically
                raise RepositoryError("claimed export job has no lease token")
            running = jobs.start(
                claimed.id,
                worker_id=request.worker_id,
                lease_token=claimed.lease_token,
                now=self._clock(),
            )

            attempts: list[_RecordAttempt] = []
            expected_record_statuses = (
                ("pending", "failed_retryable", "failed_terminal")
                if first_attempt
                else ("pending", "failed_retryable", "running")
            )
            for item in snapshot.contents:
                record = records.begin(
                    content_id=item.content_id,
                    exporter=EMBY_EXPORTER_NAME,
                    exporter_version=LAYOUT_VERSION,
                    source_fingerprint=snapshot.source_fingerprint,
                    output_path=snapshot.output_path,
                    expected_statuses=expected_record_statuses,
                    at=self._clock(),
                )
                if record.status == "succeeded":
                    if record.output_path != snapshot.output_path or record.rendered_fingerprint is None:
                        raise RepositoryError("reused export record is incomplete")
                elif record.status != "running":
                    raise RepositoryError("export record did not enter a reusable or running state")
                attempts.append(
                    _RecordAttempt(
                        record.id,
                        item.content_id,
                        snapshot.source_fingerprint,
                        record.status,
                        record.rendered_fingerprint,
                    )
                )

            return _PreparedAttempt(
                job_id=running.id,
                worker_id=request.worker_id,
                lease_token=claimed.lease_token,
                staging_token=f"{running.id}-{running.attempts}",
                snapshot=snapshot,
                records=tuple(attempts),
                predecessor=head,
                base_payload=base_payload,
            )

    def _load_publication_state(
        self,
        session: Session,
        *,
        author_id: str,
        publication_scope: str,
        output_path: str,
    ) -> tuple[_PublicationAnchor | None, tuple[_PendingPublication, ...]]:
        anchors: dict[str, _PublicationAnchor] = {}
        pending: list[_PendingPublication] = []
        jobs = list(
            session.scalars(
                select(Job).where(Job.job_type == EMBY_EXPORT_JOB_TYPE).order_by(Job.created_at, Job.id)
            ).all()
        )
        for job in jobs:
            if not _payload_is_for_target(
                job.payload,
                author_id=author_id,
                publication_scope=publication_scope,
            ):
                continue
            source_fingerprint, predecessor_job_id, payload = _parse_publication_base(
                job,
                author_id=author_id,
                publication_scope=publication_scope,
                output_path=output_path,
            )
            if job.status == "succeeded":
                anchors[job.id] = _parse_publication_result(
                    job,
                    author_id=author_id,
                    publication_scope=publication_scope,
                    output_path=output_path,
                )
                continue
            intent = _parse_publication_intent(payload, source_fingerprint)
            if intent is not None and job.status == "cancelled":
                raise ExportError("export_recovery_required")
            pending.append(
                _PendingPublication(
                    job_id=job.id,
                    predecessor_job_id=predecessor_job_id,
                    source_fingerprint=source_fingerprint,
                    status=job.status,
                    attempts=job.attempts,
                    lease_token=job.lease_token,
                    lease_expires_at=job.lease_expires_at,
                    payload=payload,
                    intent=intent,
                )
            )

        if not anchors:
            return None, tuple(item for item in pending if item.predecessor_job_id is None)

        children: dict[str, list[str]] = {job_id: [] for job_id in anchors}
        genesis: list[str] = []
        for anchor in anchors.values():
            predecessor = anchor.predecessor_job_id
            if predecessor is None:
                genesis.append(anchor.job_id)
                continue
            if predecessor not in anchors:
                raise ExportError("export_state_inconsistent")
            children[predecessor].append(anchor.job_id)
        if len(genesis) != 1 or any(len(values) > 1 for values in children.values()):
            raise ExportError("export_state_inconsistent")
        heads = [job_id for job_id, values in children.items() if not values]
        if len(heads) != 1:
            raise ExportError("export_state_inconsistent")
        head = anchors[heads[0]]
        visited: set[str] = set()
        cursor: _PublicationAnchor | None = head
        while cursor is not None:
            if cursor.job_id in visited:
                raise ExportError("export_state_inconsistent")
            visited.add(cursor.job_id)
            cursor = None if cursor.predecessor_job_id is None else anchors.get(cursor.predecessor_job_id)
        if len(visited) != len(anchors) or genesis[0] not in visited:
            raise ExportError("export_state_inconsistent")
        return head, tuple(item for item in pending if item.predecessor_job_id == head.job_id)

    def _recover_published_predecessor(self, scan: _RecoveryScan) -> bool:
        matching: list[_PendingPublication] = []
        for candidate in scan.pending:
            intent = candidate.intent
            if intent is None:  # pragma: no cover - scans are filtered by _prepare
                continue
            try:
                count = self._exporter.validate_published(
                    scan.snapshot.author,
                    intent.source_fingerprint,
                    intent.tree_sha256,
                    intent.manifest_sha256,
                )
            except ExportError as error:
                if error.code == "published_export_invalid":
                    continue
                raise
            if count != intent.managed_file_count:
                raise ExportError("export_state_inconsistent")
            matching.append(candidate)
        if not matching:
            return False
        if len(matching) != 1:
            raise ExportError("export_state_inconsistent")

        candidate = matching[0]
        current = self._clock()
        if candidate.status in {"claimed", "running"} and (
            candidate.lease_expires_at is None or candidate.lease_expires_at > current
        ):
            raise ExportError("export_job_unavailable")
        try:
            self._finalize_recovered_publication(scan, candidate)
        except LeaseLostError:
            raise ExportError("export_job_unavailable") from None
        except ExportError:
            raise
        except Exception:
            raise ExportError("export_finalize_failed") from None
        return True

    def _finalize_recovered_publication(
        self,
        scan: _RecoveryScan,
        candidate: _PendingPublication,
    ) -> None:
        intent = candidate.intent
        if intent is None:  # pragma: no cover - guarded by caller
            raise ExportError("export_state_inconsistent")
        now = self._clock()
        with self._database.session() as session:
            jobs = JobRepository(session)
            job = jobs.get(candidate.job_id)
            if job is None:
                raise LeaseLostError(f"publication job disappeared: {candidate.job_id}")
            if job.status == "succeeded":
                return
            source_fingerprint, predecessor_job_id, payload = _parse_publication_base(
                job,
                author_id=scan.author_id,
                publication_scope=self._publication_scope,
                output_path=scan.snapshot.output_path,
            )
            if (
                payload != candidate.payload
                or source_fingerprint != candidate.source_fingerprint
                or predecessor_job_id != candidate.predecessor_job_id
                or _parse_publication_intent(payload, source_fingerprint) != intent
            ):
                raise LeaseLostError(f"publication intent changed: {candidate.job_id}")

            records = ExportRecordRepository(session)
            for expected in intent.records:
                record = records.get(expected.record_id)
                if (
                    record is None
                    or record.content_id != expected.content_id
                    or record.exporter != EMBY_EXPORTER_NAME
                    or record.exporter_version != LAYOUT_VERSION
                    or record.source_fingerprint != expected.source_fingerprint
                    or record.output_path != scan.snapshot.output_path
                ):
                    raise ExportError("export_state_inconsistent")
                if record.status == "succeeded":
                    if record.rendered_fingerprint != intent.tree_sha256:
                        raise ExportError("export_state_inconsistent")
                    continue
                if record.status not in {"running", "failed_retryable", "failed_terminal"}:
                    raise ExportError("export_state_inconsistent")
                records.complete(
                    record.id,
                    expected_source_fingerprint=expected.source_fingerprint,
                    expected_output_path=scan.snapshot.output_path,
                    rendered_fingerprint=intent.tree_sha256,
                    expected_status=record.status,
                    at=now,
                )

            author_id = payload.get("author_id")
            if not isinstance(author_id, str):
                raise ExportError("export_state_inconsistent")
            base_payload = _base_publication_payload(
                author_id=author_id,
                publication_scope=self._publication_scope,
                output_path=scan.snapshot.output_path,
                source_fingerprint=source_fingerprint,
                predecessor_job_id=predecessor_job_id,
            )
            jobs.complete_recovered_publication(
                job.id,
                expected_status=job.status,
                expected_attempts=job.attempts,
                expected_lease_token=job.lease_token,
                replacement_payload=_result_payload(
                    base_payload,
                    tree_sha256=intent.tree_sha256,
                    manifest_sha256=intent.manifest_sha256,
                    managed_file_count=intent.managed_file_count,
                ),
                now=now,
            )

    def _terminalize_running_records(
        self,
        records: ExportRecordRepository,
        snapshot: _Snapshot,
        *,
        error_code: str,
    ) -> None:
        """Align records after reclaim terminalizes their last job attempt."""

        now = self._clock()
        for item in snapshot.contents:
            record = records.get_by_identity(
                content_id=item.content_id,
                exporter=EMBY_EXPORTER_NAME,
                exporter_version=LAYOUT_VERSION,
                source_fingerprint=snapshot.source_fingerprint,
            )
            if record is None:
                raise RepositoryError("terminal export job is missing its content record")
            if record.status in {"succeeded", "failed_terminal"}:
                continue
            if record.status not in {"running", "failed_retryable"} or record.output_path != snapshot.output_path:
                raise RepositoryError("terminal export job has inconsistent content records")
            records.fail(
                record.id,
                expected_source_fingerprint=snapshot.source_fingerprint,
                expected_output_path=snapshot.output_path,
                retryable=False,
                error_code=error_code,
                expected_status=record.status,
                at=now,
            )

    def _load_snapshot(self, session: Session, author_id: str) -> _Snapshot:
        # Kept as one eager query graph so no ORM object crosses the transaction.
        author = session.scalar(
            select(Author)
            .where(Author.id == author_id)
            .options(selectinload(Author.contents).selectinload(Content.assets))
        )
        if author is None:
            raise ExportError("author_not_found")
        try:
            export_author = ExportAuthor(
                platform=author.platform,
                remote_id=author.remote_id,
                display_name=author.display_name,
                handle=author.handle,
            )
        except ExportError:
            raise ExportError("export_snapshot_invalid") from None

        active_contents = sorted(
            (content for content in author.contents if content.tombstoned_at is None),
            key=lambda content: (content.platform, content.remote_type, content.remote_id, content.id),
        )
        contents: list[_SnapshotContent] = []
        for content in active_contents:
            assets = tuple(
                self._verified_asset(asset)
                for asset in sorted(content.assets, key=lambda asset: (asset.kind, asset.position, asset.id))
            )
            try:
                value = ExportContent(
                    platform=content.platform,
                    remote_type=content.remote_type,
                    remote_id=content.remote_id,
                    author_remote_id=export_author.remote_id,
                    kind=content.kind,
                    first_seen_at=content.first_seen_at,
                    title=content.title,
                    body=content.body,
                    published_at=content.published_at,
                    assets=assets,
                )
            except ExportError:
                raise ExportError("export_snapshot_invalid") from None
            contents.append(
                _SnapshotContent(
                    content_id=content.id,
                    source_fingerprint=content_source_fingerprint(value),
                    value=value,
                )
            )

        frozen_contents = tuple(contents)
        source_fingerprint = export_source_fingerprint(
            export_author,
            tuple(item.value for item in frozen_contents),
        )
        output_path = author_relative_directory(export_author).as_posix()
        relative = PurePosixPath(output_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ExportError("export_output_path_invalid")
        return _Snapshot(export_author, frozen_contents, source_fingerprint, output_path)

    @staticmethod
    def _verified_asset(asset: Asset) -> VerifiedAsset:
        if asset.status != AssetStatus.VERIFIED.value:
            raise ExportError("asset_not_verified")
        local_path = asset.local_path
        checksum = asset.checksum_sha256
        size_bytes = asset.size_bytes
        mime_type = asset.mime_type
        verified_at = asset.verified_at
        if (
            not isinstance(local_path, str)
            or not local_path
            or not Path(local_path).is_absolute()
            or not isinstance(checksum, str)
            or size_bytes is None
            or not isinstance(mime_type, str)
            or not mime_type
            or verified_at is None
        ):
            raise ExportError("verified_asset_incomplete")
        remote_id = asset.remote_id or f"{asset.kind}:{asset.position}"
        try:
            return VerifiedAsset(
                remote_id=remote_id,
                kind=asset.kind,
                position=asset.position,
                local_path=Path(local_path),
                checksum_sha256=checksum,
                size_bytes=size_bytes,
                mime_type=mime_type,
                generation=asset.generation,
            )
        except (ExportError, TypeError, ValueError):
            raise ExportError("verified_asset_incomplete") from None

    def _load_existing_export(
        self,
        records: ExportRecordRepository,
        snapshot: _Snapshot,
        anchor: _PublicationAnchor,
    ) -> _ExistingExport:
        for item in snapshot.contents:
            record = records.get_by_identity(
                content_id=item.content_id,
                exporter=EMBY_EXPORTER_NAME,
                exporter_version=LAYOUT_VERSION,
                source_fingerprint=snapshot.source_fingerprint,
            )
            if (
                record is None
                or record.status != "succeeded"
                or record.output_path != snapshot.output_path
                or record.rendered_fingerprint != anchor.tree_sha256
            ):
                raise ExportError("export_state_inconsistent")
        if anchor.source_fingerprint != snapshot.source_fingerprint:
            raise ExportError("export_state_inconsistent")
        return _ExistingExport(
            job_id=anchor.job_id,
            snapshot=snapshot,
            rendered_fingerprint=anchor.tree_sha256,
            manifest_sha256=anchor.manifest_sha256,
            managed_file_count=anchor.managed_file_count,
        )

    def _already_exported(self, existing: _ExistingExport) -> EmbyExportOutcome:
        rendered_fingerprint = existing.rendered_fingerprint
        managed_file_count = self._exporter.validate_published(
            existing.snapshot.author,
            existing.snapshot.source_fingerprint,
            rendered_fingerprint,
            existing.manifest_sha256,
        )
        if managed_file_count != existing.managed_file_count:
            raise ExportError("export_state_inconsistent")
        return EmbyExportOutcome(
            job_id=existing.job_id,
            source_fingerprint=existing.snapshot.source_fingerprint,
            output_path=existing.snapshot.output_path,
            rendered_fingerprint=rendered_fingerprint,
            managed_file_count=managed_file_count,
            already_exported=True,
        )

    @staticmethod
    def _expected_content_fingerprints(snapshot: _Snapshot) -> tuple[ContentFingerprint, ...]:
        return tuple(
            ContentFingerprint(
                platform=item.value.platform,
                remote_type=item.value.remote_type,
                remote_id=item.value.remote_id,
                sha256=item.source_fingerprint,
            )
            for item in snapshot.contents
        )

    def _validate_rendered(self, prepared: _PreparedAttempt, rendered: RenderedExport) -> None:
        if (
            rendered.job_id != prepared.staging_token
            or rendered.source_fingerprint != prepared.snapshot.source_fingerprint
            or rendered.author_segment != prepared.snapshot.output_path
            or rendered.content_fingerprints != self._expected_content_fingerprints(prepared.snapshot)
        ):
            raise ExportError("render_source_mismatch")
        if any(
            item.status == "succeeded" and item.rendered_fingerprint != rendered.tree_sha256
            for item in prepared.records
        ):
            raise ExportError("export_state_inconsistent")

    def _validate_result(
        self,
        prepared: _PreparedAttempt,
        rendered: RenderedExport,
        result: ExportResult,
    ) -> None:
        expected_directory = self._exporter.export_root / prepared.snapshot.output_path
        if (
            result.layout_version != LAYOUT_VERSION
            or result.author_directory.absolute() != expected_directory.absolute()
            or result.source_fingerprint != prepared.snapshot.source_fingerprint
            or result.content_fingerprints != self._expected_content_fingerprints(prepared.snapshot)
            or result.tree_sha256 != rendered.tree_sha256
            or result.manifest_sha256 != rendered.manifest_sha256
            or result.managed_files != rendered.files
        ):
            raise ExportError("published_result_mismatch")

    def _renew_before_publish(
        self,
        prepared: _PreparedAttempt,
        request: EmbyExportRequest,
        rendered: RenderedExport,
    ) -> None:
        with self._database.session() as session:
            JobRepository(session).renew_lease(
                prepared.job_id,
                worker_id=request.worker_id,
                lease_token=prepared.lease_token,
                lease_seconds=request.lease_seconds,
                replacement_payload=_intent_payload(prepared, rendered),
                now=self._clock(),
            )

    def _finalize(self, prepared: _PreparedAttempt, result: ExportResult) -> None:
        now = self._clock()
        with self._database.session() as session:
            records = ExportRecordRepository(session)
            for item in prepared.records:
                if item.status == "succeeded":
                    continue
                records.complete(
                    item.record_id,
                    expected_source_fingerprint=item.source_fingerprint,
                    expected_output_path=prepared.snapshot.output_path,
                    rendered_fingerprint=result.tree_sha256,
                    at=now,
                )
            JobRepository(session).complete(
                prepared.job_id,
                worker_id=prepared.worker_id,
                lease_token=prepared.lease_token,
                replacement_payload=_result_payload(
                    prepared.base_payload,
                    tree_sha256=result.tree_sha256,
                    manifest_sha256=result.manifest_sha256,
                    managed_file_count=len(result.managed_files),
                ),
                now=now,
            )

    def _record_failure(self, prepared: _PreparedAttempt, code: str) -> None:
        now = self._clock()
        with self._database.session() as session:
            jobs = JobRepository(session)
            job = jobs.get(prepared.job_id)
            if job is None:
                raise LeaseLostError(f"export job is no longer owned: {prepared.job_id}")
            retryable = export_error_is_retryable(code) and job.attempts < job.max_attempts
            records = ExportRecordRepository(session)
            for item in prepared.records:
                if item.status == "succeeded":
                    continue
                records.fail(
                    item.record_id,
                    expected_source_fingerprint=item.source_fingerprint,
                    expected_output_path=prepared.snapshot.output_path,
                    retryable=retryable,
                    error_code=code,
                    at=now,
                )
            jobs.fail(
                prepared.job_id,
                worker_id=prepared.worker_id,
                lease_token=prepared.lease_token,
                retryable=retryable,
                error_code=code,
                error_message=f"Classified Emby export failure: {code}",
                now=now,
            )

    def _raise_attempt_failure(self, prepared: _PreparedAttempt, code: str) -> NoReturn:
        try:
            self._record_failure(prepared, code)
        except LeaseLostError:
            raise ExportError("export_lease_lost") from None
        except Exception:
            raise ExportError("export_failure_finalize_failed") from None
        raise ExportError(code)


__all__ = [
    "EMBY_EXPORTER_NAME",
    "EMBY_EXPORT_JOB_TYPE",
    "EmbyExportOutcome",
    "EmbyExportRequest",
    "EmbyExportService",
    "EmbyExporterPort",
    "emby_export_natural_key",
    "export_error_is_retryable",
]
