"""Atomic completion receipts and immutable MediaCrawler output snapshots."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import io
import json
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from media_sync.security import SecretValue

from .bridge import (
    LEGACY_MANIFEST_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    MAX_MANIFEST_BYTES,
    MediaCrawlerRunMode,
    RunnerManifest,
)
from .policies import (
    RUNNER_MANIFEST_NAME,
    MediaCrawlerPolicyError,
    OutputStats,
    WatchdogLimits,
)

COMPLETION_RECEIPT_NAME = "completion-receipt.json"
LEGACY_COMPLETION_RECEIPT_SCHEMA_VERSION = 1
COMPLETION_RECEIPT_SCHEMA_VERSION = 2
MAX_COMPLETION_RECEIPT_BYTES = 1_048_576
MAX_RELATIVE_PATH_CHARS = 4_096
_READ_CHUNK_BYTES = 1024 * 1024
_SHA256_LENGTH = 64


class CompletionReceiptErrorCode(StrEnum):
    """Stable, non-secret completion rejection reasons."""

    ALREADY_EXISTS = "already_exists"
    EMPTY_OUTPUT = "empty_output"
    IDENTITY_MISMATCH = "identity_mismatch"
    INCOMPLETE_OUTPUT = "incomplete_output"
    KNOWN_SECRET_DISCLOSURE = "known_secret_disclosure"
    MALFORMED = "malformed"
    OUTPUT_MISMATCH = "output_mismatch"
    UNSAFE_PATH = "unsafe_path"
    WRITE_FAILED = "write_failed"


class CompletionReceiptError(MediaCrawlerPolicyError):
    """A completion receipt or its immutable output snapshot is unsafe."""

    def __init__(self, code: CompletionReceiptErrorCode) -> None:
        self.code = code
        super().__init__(f"MediaCrawler completion receipt rejected: {code.value}")


@dataclass(frozen=True, slots=True)
class CompletionReceiptFile:
    """One exact, relative JSONL file committed by the parent runner."""

    relative_path: str
    size_bytes: int
    sha256: str

    def as_payload(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class CompletionReceipt:
    """Versioned, secret-free proof that one bridge job completed."""

    account_id: UUID
    subscription_id: UUID
    job_id: UUID
    checkpoint_revision_before: int
    platform: str
    intended_mode: MediaCrawlerRunMode
    manifest_sha256: str
    directories: tuple[str, ...]
    files: tuple[CompletionReceiptFile, ...]
    schema_version: int = COMPLETION_RECEIPT_SCHEMA_VERSION
    schedule_revision: int | None = 0
    attempt: int | None = 1
    execution_id: UUID | None = None
    sync_run_id: UUID | None = None

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version not in {
            LEGACY_COMPLETION_RECEIPT_SCHEMA_VERSION,
            COMPLETION_RECEIPT_SCHEMA_VERSION,
        }:
            raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
        if self.schema_version == LEGACY_COMPLETION_RECEIPT_SCHEMA_VERSION:
            if any(
                value is not None
                for value in (
                    self.schedule_revision,
                    self.attempt,
                    self.execution_id,
                    self.sync_run_id,
                )
            ):
                raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
            return
        execution_id = self.execution_id or self.job_id
        sync_run_id = self.sync_run_id or self.job_id
        if type(self.schedule_revision) is not int or self.schedule_revision < 0:
            raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
        if type(self.attempt) is not int or self.attempt < 1:
            raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
        if not isinstance(execution_id, UUID) or not isinstance(sync_run_id, UUID):
            raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
        object.__setattr__(self, "execution_id", execution_id)
        object.__setattr__(self, "sync_run_id", sync_run_id)

    @property
    def scheduler_job_id(self) -> UUID:
        """Return the durable scheduler Job identity (``job_id`` in v1)."""

        return self.job_id

    def as_payload(self) -> dict[str, object]:
        if self.schema_version == LEGACY_COMPLETION_RECEIPT_SCHEMA_VERSION:
            return {
                "schema_version": LEGACY_COMPLETION_RECEIPT_SCHEMA_VERSION,
                "status": "succeeded",
                "account_id": str(self.account_id),
                "subscription_id": str(self.subscription_id),
                "job_id": str(self.job_id),
                "checkpoint_revision_before": self.checkpoint_revision_before,
                "platform": self.platform,
                "intended_mode": self.intended_mode.value,
                "manifest_sha256": self.manifest_sha256,
                "directories": list(self.directories),
                "files": [item.as_payload() for item in self.files],
            }
        if (
            self.schedule_revision is None
            or self.attempt is None
            or self.execution_id is None
            or self.sync_run_id is None
        ):  # pragma: no cover - construction validates this invariant
            raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
        return {
            "schema_version": COMPLETION_RECEIPT_SCHEMA_VERSION,
            "status": "succeeded",
            "account_id": str(self.account_id),
            "subscription_id": str(self.subscription_id),
            "scheduler_job_id": str(self.scheduler_job_id),
            "schedule_revision": self.schedule_revision,
            "attempt": self.attempt,
            "execution_id": str(self.execution_id),
            "sync_run_id": str(self.sync_run_id),
            "checkpoint_revision_before": self.checkpoint_revision_before,
            "platform": self.platform,
            "intended_mode": self.intended_mode.value,
            "manifest_sha256": self.manifest_sha256,
            "directories": list(self.directories),
            "files": [item.as_payload() for item in self.files],
        }


@dataclass(frozen=True, slots=True)
class JsonlSnapshotFile:
    """One validated JSONL file read exactly once into immutable memory."""

    relative_path: str
    sha256: str
    payload: bytes = field(repr=False)

    @property
    def size_bytes(self) -> int:
        return len(self.payload)


@dataclass(frozen=True, slots=True)
class ValidatedOutputSnapshot:
    """Receipt plus exact bytes safe for normalization without reopening paths."""

    receipt: CompletionReceipt
    files: tuple[JsonlSnapshotFile, ...]
    stats: OutputStats


@dataclass(frozen=True, slots=True)
class _FileSignature:
    device: int
    inode: int
    size: int
    links: int
    mode: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True, slots=True)
class _ScannedFile:
    relative_path: str
    path: Path
    signature: _FileSignature


@dataclass(frozen=True, slots=True)
class _TreeScan:
    files: tuple[_ScannedFile, ...]
    directories: frozenset[str]


def completion_receipt_path(job_root: Path) -> Path:
    """Return the one canonical receipt path below a bridge job root."""

    return job_root / COMPLETION_RECEIPT_NAME


def _is_reparse(stat_result: os.stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def _signature(stat_result: os.stat_result) -> _FileSignature:
    modified_ns = int(getattr(stat_result, "st_mtime_ns", stat_result.st_mtime * 1_000_000_000))
    changed_ns = int(getattr(stat_result, "st_ctime_ns", stat_result.st_ctime * 1_000_000_000))
    return _FileSignature(
        device=stat_result.st_dev,
        inode=stat_result.st_ino,
        size=stat_result.st_size,
        links=stat_result.st_nlink,
        mode=stat_result.st_mode,
        modified_ns=modified_ns,
        changed_ns=changed_ns,
    )


def _require_safe_directory(path: Path) -> Path:
    declared = path.expanduser().absolute()
    try:
        path_stat = declared.lstat()
        resolved = declared.resolve(strict=True)
    except OSError as error:
        raise CompletionReceiptError(CompletionReceiptErrorCode.UNSAFE_PATH) from error
    if resolved != declared or not stat.S_ISDIR(path_stat.st_mode) or _is_reparse(path_stat):
        raise CompletionReceiptError(CompletionReceiptErrorCode.UNSAFE_PATH)
    return declared


def _canonical_layout(manifest: RunnerManifest) -> tuple[Path, Path, Path, Path]:
    job_root = _require_safe_directory(manifest.job_root)
    output_root = _require_safe_directory(manifest.output_root)
    manifest_path = job_root / RUNNER_MANIFEST_NAME
    receipt_path = completion_receipt_path(job_root)
    if (
        manifest.job_root != job_root
        or manifest.output_root != output_root
        or output_root.parent != job_root
        or manifest_path != manifest.job_root / RUNNER_MANIFEST_NAME
    ):
        raise CompletionReceiptError(CompletionReceiptErrorCode.UNSAFE_PATH)
    return job_root, output_root, manifest_path, receipt_path


def _safe_relative_entry(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_RELATIVE_PATH_CHARS:
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
    if "\\" in value or any(not character.isprintable() for character in value):
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or str(parsed) != value or any(part in {"", ".", ".."} for part in parsed.parts):
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
    return value


def _safe_relative_file_path(value: object) -> str:
    relative_path = _safe_relative_entry(value)
    if PurePosixPath(relative_path).suffix.lower() != ".jsonl":
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
    return relative_path


def _scan_output_tree(root: Path, limits: WatchdogLimits) -> _TreeScan:
    resolved_root = _require_safe_directory(root)
    pending: list[tuple[Path, PurePosixPath]] = [(resolved_root, PurePosixPath("."))]
    files: list[_ScannedFile] = []
    directories: set[str] = set()
    try:
        while pending:
            directory, relative_directory = pending.pop()
            directory_stat = directory.lstat()
            if not stat.S_ISDIR(directory_stat.st_mode) or _is_reparse(directory_stat):
                raise CompletionReceiptError(CompletionReceiptErrorCode.UNSAFE_PATH)
            with os.scandir(directory) as entries:
                for entry in entries:
                    candidate = Path(entry.path)
                    entry_stat = candidate.lstat()
                    if entry.is_symlink() or _is_reparse(entry_stat):
                        raise CompletionReceiptError(CompletionReceiptErrorCode.UNSAFE_PATH)
                    relative = (
                        PurePosixPath(entry.name)
                        if relative_directory == PurePosixPath(".")
                        else relative_directory / entry.name
                    )
                    relative_text = str(relative)
                    if stat.S_ISDIR(entry_stat.st_mode):
                        _safe_relative_entry(relative_text)
                        directories.add(relative_text)
                        if len(directories) > limits.max_output_files:
                            raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
                        pending.append((candidate, relative))
                        continue
                    if (
                        not stat.S_ISREG(entry_stat.st_mode)
                        or entry_stat.st_nlink != 1
                        or candidate.suffix.lower() != ".jsonl"
                    ):
                        raise CompletionReceiptError(CompletionReceiptErrorCode.UNSAFE_PATH)
                    _safe_relative_file_path(relative_text)
                    files.append(_ScannedFile(relative_text, candidate, _signature(entry_stat)))
                    if len(files) > limits.max_output_files:
                        raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
    except CompletionReceiptError:
        raise
    except OSError as error:
        raise CompletionReceiptError(CompletionReceiptErrorCode.UNSAFE_PATH) from error
    files.sort(key=lambda item: item.relative_path)
    return _TreeScan(tuple(files), frozenset(directories))


def _open_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _read_stable_regular_file(
    path: Path,
    *,
    maximum_bytes: int,
    expected_signature: _FileSignature | None = None,
) -> tuple[bytes, _FileSignature]:
    descriptor: int | None = None
    try:
        if path.is_symlink():
            raise CompletionReceiptError(CompletionReceiptErrorCode.UNSAFE_PATH)
        before = path.lstat()
        before_signature = _signature(before)
        if (
            not stat.S_ISREG(before.st_mode)
            or _is_reparse(before)
            or before.st_nlink != 1
            or before.st_size < 1
            or before.st_size > maximum_bytes
            or (expected_signature is not None and before_signature != expected_signature)
        ):
            raise CompletionReceiptError(CompletionReceiptErrorCode.UNSAFE_PATH)
        descriptor = os.open(path, _open_flags())
        opened = os.fstat(descriptor)
        opened_signature = _signature(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _is_reparse(opened)
            or opened.st_nlink != 1
            or opened_signature != before_signature
        ):
            raise CompletionReceiptError(CompletionReceiptErrorCode.UNSAFE_PATH)

        chunks: list[bytes] = []
        bytes_read = 0
        while bytes_read <= maximum_bytes:
            chunk = os.read(descriptor, min(_READ_CHUNK_BYTES, maximum_bytes + 1 - bytes_read))
            if not chunk:
                break
            chunks.append(chunk)
            bytes_read += len(chunk)
            if bytes_read > maximum_bytes:
                raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        path_after = path.lstat()
        if _signature(after) != opened_signature or _signature(path_after) != opened_signature:
            raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
        return payload, opened_signature
    except CompletionReceiptError:
        raise
    except OSError as error:
        raise CompletionReceiptError(CompletionReceiptErrorCode.UNSAFE_PATH) from error
    finally:
        if descriptor is not None:
            with contextlib.suppress(OSError):
                os.close(descriptor)


def _validate_jsonl_payload(
    payload: bytes,
    limits: WatchdogLimits,
    *,
    known_secret_strings: tuple[str, ...] = (),
) -> int:
    if not payload or not payload.endswith(b"\n"):
        raise CompletionReceiptError(CompletionReceiptErrorCode.INCOMPLETE_OUTPUT)
    encoded_secrets = tuple(secret.encode("utf-8") for secret in known_secret_strings)
    if any(secret in payload for secret in encoded_secrets):
        raise CompletionReceiptError(CompletionReceiptErrorCode.KNOWN_SECRET_DISCLOSURE)
    item_count = 0
    with io.BytesIO(payload) as stream:
        while line := stream.readline(limits.max_line_bytes + 1):
            if len(line) > limits.max_line_bytes:
                raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
            try:
                decoded = line.decode("utf-8")
                record = json.loads(
                    decoded,
                    parse_constant=_reject_nonstandard_number,
                )
            except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
                raise CompletionReceiptError(CompletionReceiptErrorCode.INCOMPLETE_OUTPUT) from error
            if not isinstance(record, Mapping):
                raise CompletionReceiptError(CompletionReceiptErrorCode.INCOMPLETE_OUTPUT)
            if _json_value_contains_known_secret(record, known_secret_strings):
                raise CompletionReceiptError(CompletionReceiptErrorCode.KNOWN_SECRET_DISCLOSURE)
            item_count += 1
            if item_count > limits.max_output_items:
                raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
    return item_count


def _json_value_contains_known_secret(value: object, known_secret_strings: tuple[str, ...]) -> bool:
    """Match exact known strings after JSON unescaping without rendering values."""

    pending = [value]
    while pending:
        candidate = pending.pop()
        if isinstance(candidate, str):
            if any(secret in candidate for secret in known_secret_strings):
                return True
        elif isinstance(candidate, Mapping):
            pending.extend(candidate.keys())
            pending.extend(candidate.values())
        elif isinstance(candidate, list):
            pending.extend(candidate)
    return False


def _known_secret_strings(values: Sequence[str | SecretValue]) -> tuple[str, ...]:
    secrets: set[str] = set()
    for value in values:
        revealed = value.reveal() if isinstance(value, SecretValue) else value
        if revealed:
            secrets.add(revealed)
    return tuple(sorted(secrets, key=len, reverse=True))


def _reject_nonstandard_number(value: str) -> None:
    del value
    raise ValueError("non-standard JSON number")


def _snapshot_tree(
    manifest: RunnerManifest,
    *,
    expected_receipt_files: tuple[CompletionReceiptFile, ...] | None = None,
    expected_directories: tuple[str, ...] | None = None,
    known_secret_strings: tuple[str, ...] = (),
) -> tuple[tuple[JsonlSnapshotFile, ...], tuple[str, ...], OutputStats]:
    _job_root, output_root, _manifest_path, _receipt_path = _canonical_layout(manifest)
    first_scan = _scan_output_tree(output_root, manifest.watchdogs)
    if any(item.signature.size < 1 for item in first_scan.files):
        raise CompletionReceiptError(CompletionReceiptErrorCode.EMPTY_OUTPUT)

    expected_by_path = (
        {item.relative_path: item for item in expected_receipt_files} if expected_receipt_files is not None else None
    )
    scanned_paths = tuple(item.relative_path for item in first_scan.files)
    if expected_by_path is not None and scanned_paths != tuple(expected_by_path):
        raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
    scanned_directories = tuple(sorted(first_scan.directories))
    if expected_directories is not None and scanned_directories != expected_directories:
        raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
    snapshots: list[JsonlSnapshotFile] = []
    total_bytes = 0
    total_items = 0
    for scanned in first_scan.files:
        expected = expected_by_path.get(scanned.relative_path) if expected_by_path is not None else None
        per_file_limit = expected.size_bytes if expected is not None else manifest.watchdogs.max_output_bytes
        payload, _opened_signature = _read_stable_regular_file(
            scanned.path,
            maximum_bytes=per_file_limit,
            expected_signature=scanned.signature,
        )
        digest = hashlib.sha256(payload).hexdigest()
        if expected is not None and (
            len(payload) != expected.size_bytes or not hmac.compare_digest(digest, expected.sha256)
        ):
            raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
        total_bytes += len(payload)
        if total_bytes > manifest.watchdogs.max_output_bytes:
            raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
        total_items += _validate_jsonl_payload(
            payload,
            manifest.watchdogs,
            known_secret_strings=known_secret_strings,
        )
        if total_items > manifest.watchdogs.max_output_items:
            raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
        snapshots.append(JsonlSnapshotFile(scanned.relative_path, digest, payload))

    second_scan = _scan_output_tree(output_root, manifest.watchdogs)
    if second_scan != first_scan:
        raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
    return (
        tuple(snapshots),
        scanned_directories,
        OutputStats(
            bytes_written=total_bytes,
            jsonl_items=total_items,
            files_written=len(snapshots),
        ),
    )


def _canonical_manifest_bytes(manifest: RunnerManifest, manifest_path: Path) -> bytes:
    payload, _signature_value = _read_stable_regular_file(
        manifest_path,
        maximum_bytes=MAX_MANIFEST_BYTES,
    )
    canonical = json.dumps(
        manifest.as_payload(),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if payload != canonical:
        raise CompletionReceiptError(CompletionReceiptErrorCode.IDENTITY_MISMATCH)
    return payload


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
        result[key] = value
    return result


def _parse_uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED) from error
    if str(parsed) != value:
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
    return parsed


def _parse_sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
    return value


def _parse_receipt(payload: bytes) -> CompletionReceipt:
    try:
        raw = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object)
    except CompletionReceiptError:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED) from error
    common_keys = {
        "schema_version",
        "status",
        "account_id",
        "subscription_id",
        "checkpoint_revision_before",
        "platform",
        "intended_mode",
        "manifest_sha256",
        "directories",
        "files",
    }
    if (
        not isinstance(raw, Mapping)
        or type(raw.get("schema_version")) is not int
        or raw.get("schema_version")
        not in {LEGACY_COMPLETION_RECEIPT_SCHEMA_VERSION, COMPLETION_RECEIPT_SCHEMA_VERSION}
        or raw.get("status") != "succeeded"
    ):
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
    schema_version = raw["schema_version"]
    legacy_keys = common_keys | {"job_id"}
    v2_keys = common_keys | {
        "scheduler_job_id",
        "schedule_revision",
        "attempt",
        "execution_id",
        "sync_run_id",
    }
    expected_keys = legacy_keys if schema_version == LEGACY_COMPLETION_RECEIPT_SCHEMA_VERSION else v2_keys
    if set(raw) != expected_keys:
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
    checkpoint_revision = raw.get("checkpoint_revision_before")
    platform = raw.get("platform")
    raw_mode = raw.get("intended_mode")
    if (
        type(checkpoint_revision) is not int
        or checkpoint_revision < 0
        or not isinstance(platform, str)
        or not platform
        or not isinstance(raw_mode, str)
    ):
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
    try:
        intended_mode = MediaCrawlerRunMode(raw_mode)
    except ValueError as error:
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED) from error

    if schema_version == LEGACY_COMPLETION_RECEIPT_SCHEMA_VERSION:
        job_id = _parse_uuid(raw.get("job_id"))
        schedule_revision: int | None = None
        attempt: int | None = None
        execution_id: UUID | None = None
        sync_run_id: UUID | None = None
    else:
        job_id = _parse_uuid(raw.get("scheduler_job_id"))
        execution_id = _parse_uuid(raw.get("execution_id"))
        sync_run_id = _parse_uuid(raw.get("sync_run_id"))
        schedule_revision = raw.get("schedule_revision")
        attempt = raw.get("attempt")
        if type(schedule_revision) is not int or schedule_revision < 0:
            raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
        if type(attempt) is not int or attempt < 1:
            raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)

    raw_directories = raw.get("directories")
    if not isinstance(raw_directories, list):
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
    directories: list[str] = []
    previous_directory: str | None = None
    for raw_directory in raw_directories:
        relative_directory = _safe_relative_entry(raw_directory)
        if previous_directory is not None and relative_directory <= previous_directory:
            raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
        previous_directory = relative_directory
        directories.append(relative_directory)

    raw_files = raw.get("files")
    if not isinstance(raw_files, list):
        raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
    files: list[CompletionReceiptFile] = []
    previous_path: str | None = None
    for raw_file in raw_files:
        if not isinstance(raw_file, Mapping) or set(raw_file) != {"relative_path", "size_bytes", "sha256"}:
            raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
        relative_path = _safe_relative_file_path(raw_file.get("relative_path"))
        size_bytes = raw_file.get("size_bytes")
        if type(size_bytes) is not int or size_bytes < 1:
            raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
        if previous_path is not None and relative_path <= previous_path:
            raise CompletionReceiptError(CompletionReceiptErrorCode.MALFORMED)
        previous_path = relative_path
        files.append(
            CompletionReceiptFile(
                relative_path=relative_path,
                size_bytes=size_bytes,
                sha256=_parse_sha256(raw_file.get("sha256")),
            )
        )
    return CompletionReceipt(
        account_id=_parse_uuid(raw.get("account_id")),
        subscription_id=_parse_uuid(raw.get("subscription_id")),
        job_id=job_id,
        checkpoint_revision_before=checkpoint_revision,
        platform=platform,
        intended_mode=intended_mode,
        manifest_sha256=_parse_sha256(raw.get("manifest_sha256")),
        directories=tuple(directories),
        files=tuple(files),
        schema_version=schema_version,
        schedule_revision=schedule_revision,
        attempt=attempt,
        execution_id=execution_id,
        sync_run_id=sync_run_id,
    )


def _validate_identity(receipt: CompletionReceipt, manifest: RunnerManifest, manifest_bytes: bytes) -> None:
    versions_match = (
        receipt.schema_version == LEGACY_COMPLETION_RECEIPT_SCHEMA_VERSION
        and manifest.schema_version == LEGACY_MANIFEST_SCHEMA_VERSION
    ) or (
        receipt.schema_version == COMPLETION_RECEIPT_SCHEMA_VERSION
        and manifest.schema_version == MANIFEST_SCHEMA_VERSION
    )
    if (
        not versions_match
        or receipt.account_id != manifest.account_id
        or receipt.subscription_id != manifest.subscription_id
        or receipt.job_id != manifest.job_id
        or receipt.checkpoint_revision_before != manifest.checkpoint_revision_before
        or receipt.platform != manifest.platform.value
        or receipt.intended_mode is not manifest.intended_mode
        or not hmac.compare_digest(receipt.manifest_sha256, hashlib.sha256(manifest_bytes).hexdigest())
    ):
        raise CompletionReceiptError(CompletionReceiptErrorCode.IDENTITY_MISMATCH)
    if receipt.schema_version == COMPLETION_RECEIPT_SCHEMA_VERSION and (
        receipt.schedule_revision != manifest.schedule_revision
        or receipt.attempt != manifest.attempt
        or receipt.execution_id != manifest.execution_id
        or receipt.sync_run_id != manifest.sync_run_id
    ):
        raise CompletionReceiptError(CompletionReceiptErrorCode.IDENTITY_MISMATCH)


def require_completion_receipt_absent(manifest: RunnerManifest) -> None:
    """Reject job reuse or a stale temporary receipt before spawning a child."""

    job_root, _output_root, _manifest_path, receipt_path = _canonical_layout(manifest)
    temporary_path = job_root / f".{COMPLETION_RECEIPT_NAME}.tmp"
    try:
        if receipt_path.exists() or receipt_path.is_symlink() or temporary_path.exists() or temporary_path.is_symlink():
            raise CompletionReceiptError(CompletionReceiptErrorCode.ALREADY_EXISTS)
    except OSError as error:
        raise CompletionReceiptError(CompletionReceiptErrorCode.UNSAFE_PATH) from error


def _write_all(descriptor: int, payload: bytes) -> None:
    position = 0
    while position < len(payload):
        written = os.write(descriptor, payload[position:])
        if written < 1:
            raise OSError("short completion receipt write")
        position += written


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        os.fsync(descriptor)
    except OSError:
        # Windows does not offer a portable directory fsync. The receipt file
        # itself was fsynced before the same-directory atomic replacement.
        return
    finally:
        if descriptor is not None:
            with contextlib.suppress(OSError):
                os.close(descriptor)


def write_completion_receipt(
    manifest: RunnerManifest,
    inspected_stats: OutputStats,
    *,
    known_secrets: Sequence[str | SecretValue],
) -> CompletionReceipt:
    """Atomically seal one already-inspected, successful parent-runner output."""

    if manifest.schema_version != MANIFEST_SCHEMA_VERSION:
        # A legacy manifest may only be trusted when an already-existing v1
        # receipt authenticates its exact bytes. It must never gain a new seal.
        raise CompletionReceiptError(CompletionReceiptErrorCode.IDENTITY_MISMATCH)
    if (
        manifest.schedule_revision is None
        or manifest.attempt is None
        or manifest.execution_id is None
        or manifest.sync_run_id is None
    ):  # pragma: no cover - RunnerManifest construction enforces this
        raise CompletionReceiptError(CompletionReceiptErrorCode.IDENTITY_MISMATCH)

    job_root, _output_root, manifest_path, receipt_path = _canonical_layout(manifest)
    require_completion_receipt_absent(manifest)
    snapshots, directories, snapshot_stats = _snapshot_tree(
        manifest,
        known_secret_strings=_known_secret_strings(known_secrets),
    )
    if snapshot_stats != inspected_stats:
        raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
    manifest_bytes = _canonical_manifest_bytes(manifest, manifest_path)
    receipt = CompletionReceipt(
        account_id=manifest.account_id,
        subscription_id=manifest.subscription_id,
        job_id=manifest.job_id,
        checkpoint_revision_before=manifest.checkpoint_revision_before,
        platform=manifest.platform.value,
        intended_mode=manifest.intended_mode,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        directories=directories,
        files=tuple(CompletionReceiptFile(item.relative_path, item.size_bytes, item.sha256) for item in snapshots),
        schema_version=COMPLETION_RECEIPT_SCHEMA_VERSION,
        schedule_revision=manifest.schedule_revision,
        attempt=manifest.attempt,
        execution_id=manifest.execution_id,
        sync_run_id=manifest.sync_run_id,
    )
    encoded = (json.dumps(receipt.as_payload(), ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(encoded) > MAX_COMPLETION_RECEIPT_BYTES:
        raise CompletionReceiptError(CompletionReceiptErrorCode.WRITE_FAILED)

    temporary_path = job_root / f".{COMPLETION_RECEIPT_NAME}.tmp"
    descriptor: int | None = None
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(temporary_path, flags, 0o600)
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary_path, receipt_path)
        _fsync_directory(job_root)
    except OSError as error:
        raise CompletionReceiptError(CompletionReceiptErrorCode.WRITE_FAILED) from error
    finally:
        if descriptor is not None:
            with contextlib.suppress(OSError):
                os.close(descriptor)
        with contextlib.suppress(OSError):
            temporary_path.unlink(missing_ok=True)
    try:
        validated = load_validated_output_snapshot(manifest)
        if validated.receipt != receipt or validated.stats != snapshot_stats:
            raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
    except CompletionReceiptError:
        with contextlib.suppress(OSError):
            receipt_path.unlink(missing_ok=True)
        _fsync_directory(job_root)
        raise
    return receipt


def load_validated_output_snapshot(manifest: RunnerManifest) -> ValidatedOutputSnapshot:
    """Load a strict receipt and return exact JSONL bytes without path reuse."""

    _job_root, _output_root, manifest_path, receipt_path = _canonical_layout(manifest)
    manifest_bytes = _canonical_manifest_bytes(manifest, manifest_path)
    receipt_bytes, _receipt_signature = _read_stable_regular_file(
        receipt_path,
        maximum_bytes=MAX_COMPLETION_RECEIPT_BYTES,
    )
    receipt = _parse_receipt(receipt_bytes)
    _validate_identity(receipt, manifest, manifest_bytes)
    if (
        len(receipt.files) > manifest.watchdogs.max_output_files
        or len(receipt.directories) > manifest.watchdogs.max_output_files
        or sum(item.size_bytes for item in receipt.files) > manifest.watchdogs.max_output_bytes
    ):
        raise CompletionReceiptError(CompletionReceiptErrorCode.OUTPUT_MISMATCH)
    snapshots, _directories, stats = _snapshot_tree(
        manifest,
        expected_receipt_files=receipt.files,
        expected_directories=receipt.directories,
    )
    return ValidatedOutputSnapshot(receipt=receipt, files=snapshots, stats=stats)


__all__ = [
    "COMPLETION_RECEIPT_NAME",
    "COMPLETION_RECEIPT_SCHEMA_VERSION",
    "LEGACY_COMPLETION_RECEIPT_SCHEMA_VERSION",
    "MAX_COMPLETION_RECEIPT_BYTES",
    "CompletionReceipt",
    "CompletionReceiptError",
    "CompletionReceiptErrorCode",
    "CompletionReceiptFile",
    "JsonlSnapshotFile",
    "ValidatedOutputSnapshot",
    "completion_receipt_path",
    "load_validated_output_snapshot",
    "require_completion_receipt_absent",
    "write_completion_receipt",
]
