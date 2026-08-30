"""Bounded, resumable media download orchestration without database concerns."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx

from media_sync.domain import AssetKind
from media_sync.media.archive import ArchivePublisher, hash_file
from media_sync.media.errors import MediaDownloadError
from media_sync.media.locator import (
    AdapterRefreshLocator,
    AssetLocator,
    LocatorRefreshPort,
    locator_fingerprint,
    resolve_locator,
)
from media_sync.media.network import SafeHttpClient
from media_sync.media.probe import MediaProbe, verify_media
from media_sync.security.paths import (
    PathLockBusyError,
    PathSecurityError,
    assert_regular_file,
    atomic_write_bytes,
    confined_file,
    create_regular_file,
    ensure_secure_directory,
    ensure_secure_root,
    exclusive_file_lock,
    open_regular_file,
    read_regular_file_bytes,
    safe_unlink,
)

_CONTENT_RANGE = re.compile(r"bytes ([0-9]+)-([0-9]+)/([0-9]+)\Z")
_UNSATISFIED_RANGE = re.compile(r"bytes \*/([0-9]+)\Z")
_DIGITS = re.compile(r"[0-9]+\Z")
_RETRYABLE_STATUSES = frozenset({408, 425, 429})


@dataclass(frozen=True, slots=True)
class DownloadLimits:
    """Hard limits for a single asset download attempt."""

    max_bytes: int = 8 * 1024 * 1024 * 1024
    max_chunk_bytes: int = 1024 * 1024
    total_timeout_seconds: float = 30 * 60.0
    max_restarts: int = 1
    sniff_bytes: int = 65536
    probe_timeout_seconds: float = 10.0
    probe_output_bytes: int = 65536

    def __post_init__(self) -> None:
        if self.max_bytes <= 0 or self.max_chunk_bytes <= 0:
            raise ValueError("download byte limits must be positive")
        if self.total_timeout_seconds <= 0:
            raise ValueError("download timeout must be positive")
        if self.max_restarts < 0:
            raise ValueError("max_restarts must be non-negative")
        if self.sniff_bytes <= 0 or self.probe_timeout_seconds <= 0 or self.probe_output_bytes <= 0:
            raise ValueError("media probe limits must be positive")


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    """Immutable, generation-fenced input for one asset."""

    asset_id: UUID
    generation: int
    locator: AssetLocator = field(repr=False)
    work_root: Path
    archive_root: Path
    expected_kind: AssetKind | None = None
    before_archive_commit: Callable[[], None] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation < 1:
            raise ValueError("generation must be positive")


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """Locally verified downloader-owned fields."""

    archive_path: Path
    sha256: str
    size_bytes: int
    mime_type: str
    extension: str
    etag: str | None = field(default=None, repr=False)
    last_modified: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.etag is not None and self.last_modified is not None:
            raise ValueError("only one download validator may be returned")

    @property
    def validator(self) -> str | None:
        """Return the selected validator without exposing its kind ambiguously."""

        return self.etag or self.last_modified


ValidatorKind = Literal["etag", "last_modified"]


@dataclass(frozen=True, slots=True)
class PartMetadata:
    """Strict sidecar binding resumable bytes to one asset generation."""

    asset_id: UUID
    generation: int
    locator_fingerprint: str
    validator_kind: ValidatorKind | None
    validator: str | None = field(repr=False)
    expected_length: int | None
    current_length: int
    version: Literal[1] = 1

    def __post_init__(self) -> None:
        if self.generation < 1 or self.current_length < 0:
            raise ValueError("generation must be positive and partial lengths non-negative")
        if self.expected_length is not None and (
            self.expected_length < 0 or self.current_length > self.expected_length
        ):
            raise ValueError("partial expected length is invalid")
        if len(self.locator_fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in self.locator_fingerprint
        ):
            raise ValueError("locator fingerprint is invalid")
        if (self.validator_kind is None) != (self.validator is None):
            raise ValueError("validator kind and value must both be present or absent")
        if self.validator is not None and (
            len(self.validator) > 1024
            or not self.validator
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in self.validator)
        ):
            raise ValueError("validator is invalid")
        if self.validator_kind == "etag" and not _is_strong_etag(self.validator or ""):
            raise ValueError("ETag validator must be strong")
        if self.validator_kind == "last_modified" and not _is_http_date(self.validator or ""):
            raise ValueError("Last-Modified validator must be a valid HTTP date")

    def to_bytes(self) -> bytes:
        payload = {
            "asset_id": str(self.asset_id),
            "current_length": self.current_length,
            "expected_length": self.expected_length,
            "generation": self.generation,
            "locator_fingerprint": self.locator_fingerprint,
            "validator": self.validator,
            "validator_kind": self.validator_kind,
            "version": self.version,
        }
        return (json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")

    @classmethod
    def from_bytes(cls, payload: bytes) -> PartMetadata:
        if len(payload) > 8192:
            raise MediaDownloadError("download_state_invalid")
        try:
            raw = json.loads(payload.decode("ascii"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise MediaDownloadError("download_state_invalid") from exc
        required = {
            "asset_id",
            "current_length",
            "expected_length",
            "generation",
            "locator_fingerprint",
            "validator",
            "validator_kind",
            "version",
        }
        if not isinstance(raw, dict) or set(raw) != required or raw.get("version") != 1:
            raise MediaDownloadError("download_state_invalid")
        try:
            return cls(
                asset_id=UUID(raw["asset_id"]),
                generation=_strict_int(raw["generation"]),
                locator_fingerprint=_strict_str(raw["locator_fingerprint"]),
                validator_kind=_optional_validator_kind(raw["validator_kind"]),
                validator=_optional_str(raw["validator"]),
                expected_length=_optional_int(raw["expected_length"]),
                current_length=_strict_int(raw["current_length"]),
            )
        except (TypeError, ValueError) as exc:
            raise MediaDownloadError("download_state_invalid") from exc


def _strict_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError
    return value


def _optional_int(value: object) -> int | None:
    return None if value is None else _strict_int(value)


def _strict_str(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _optional_str(value: object) -> str | None:
    return None if value is None else _strict_str(value)


def _optional_validator_kind(value: object) -> ValidatorKind | None:
    if value is None:
        return None
    if value == "etag":
        return "etag"
    if value == "last_modified":
        return "last_modified"
    raise TypeError


def _is_strong_etag(value: str) -> bool:
    return len(value) >= 2 and value.startswith('"') and value.endswith('"') and not value.startswith("W/")


def _is_http_date(value: str) -> bool:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return parsed.tzinfo is not None and parsed.astimezone(UTC) is not None


def _response_validator(headers: httpx.Headers) -> tuple[ValidatorKind | None, str | None]:
    etag = headers.get("etag")
    if etag is not None and _is_strong_etag(etag):
        return "etag", etag
    modified = headers.get("last-modified")
    if modified is not None and _is_http_date(modified):
        return "last_modified", modified
    return None, None


def _content_length(headers: httpx.Headers) -> int | None:
    values = headers.get_list("content-length")
    if not values:
        return None
    if len(values) != 1 or _DIGITS.fullmatch(values[0]) is None:
        raise MediaDownloadError("download_content_length_invalid")
    return int(values[0])


def _validate_encoding(headers: httpx.Headers) -> None:
    values = headers.get_list("content-encoding")
    if any(value.strip().lower() != "identity" for value in values):
        raise MediaDownloadError("download_encoding_invalid")


class _RestartRequired(Exception):
    pass


class _PartStore:
    def __init__(self, root: Path, asset_id: UUID, generation: int) -> None:
        self.root = ensure_secure_root(root)
        ensure_secure_directory(self.root, "parts")
        stem = f"{asset_id}.{generation}"
        self.part = confined_file(self.root, Path("parts") / f"{stem}.part")
        self.metadata = confined_file(self.root, Path("parts") / f"{stem}.part.json")

    def load(self, request: DownloadRequest, fingerprint: str) -> PartMetadata | None:
        part_exists = self.part.exists() or self.part.is_symlink()
        metadata_exists = self.metadata.exists() or self.metadata.is_symlink()
        if not part_exists and not metadata_exists:
            return None
        if part_exists != metadata_exists:
            raise _RestartRequired
        try:
            assert_regular_file(self.part, root=self.root)
            details = assert_regular_file(self.metadata, root=self.root)
            if details.st_size > 8192:
                raise MediaDownloadError("download_state_invalid")
            payload = read_regular_file_bytes(self.metadata, root=self.root, max_bytes=8192)
            state = PartMetadata.from_bytes(payload)
            part_details = assert_regular_file(self.part, root=self.root)
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        except OSError as exc:
            raise MediaDownloadError("filesystem_write_failed") from exc
        if state.asset_id != request.asset_id or state.generation != request.generation:
            raise MediaDownloadError("download_state_invalid")
        if state.locator_fingerprint != fingerprint:
            raise _RestartRequired
        if part_details.st_size != state.current_length:
            raise _RestartRequired
        return state

    def create(self) -> None:
        try:
            with create_regular_file(self.part, root=self.root) as handle:
                handle.flush()
                os.fsync(handle.fileno())
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        except OSError as exc:
            raise MediaDownloadError("filesystem_write_failed") from exc

    def save(self, state: PartMetadata) -> None:
        try:
            atomic_write_bytes(
                self.root,
                self.metadata.absolute().relative_to(self.root.absolute()),
                state.to_bytes(),
            )
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        except OSError as exc:
            raise MediaDownloadError("filesystem_write_failed") from exc

    def discard(self) -> None:
        try:
            safe_unlink(self.part, root=self.root, missing_ok=True)
            safe_unlink(self.metadata, root=self.root, missing_ok=True)
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        except OSError as exc:
            raise MediaDownloadError("filesystem_write_failed") from exc


class SecureMediaDownloader:
    """Download, verify and atomically publish one generation-fenced asset."""

    def __init__(
        self,
        http: SafeHttpClient,
        *,
        refresher: LocatorRefreshPort | None = None,
        probe: MediaProbe | None = None,
        limits: DownloadLimits | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._refresher = refresher
        self._probe = probe
        self._limits = limits or DownloadLimits()
        self._monotonic = monotonic

    def download(self, request: DownloadRequest) -> DownloadResult:
        """Return verified local fields; database lifecycle remains the caller's responsibility."""

        try:
            work_root = ensure_secure_root(request.work_root)
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        lock_relative = Path("locks") / f"{request.asset_id}.{request.generation}.lock"
        try:
            with exclusive_file_lock(work_root, lock_relative):
                return self._download_locked(request, work_root)
        except PathLockBusyError as exc:
            raise MediaDownloadError("download_part_busy") from exc
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc

    def cleanup_partial(self, asset_id: UUID, generation: int, work_root: Path) -> None:
        """Safely remove one generation's resumable state under its normal lock."""

        if not isinstance(asset_id, UUID):
            raise ValueError("asset_id must be a UUID")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise ValueError("generation must be positive")
        try:
            root = ensure_secure_root(work_root)
            lock_relative = Path("locks") / f"{asset_id}.{generation}.lock"
            with exclusive_file_lock(root, lock_relative):
                _PartStore(root, asset_id, generation).discard()
        except PathLockBusyError as exc:
            raise MediaDownloadError("download_part_busy") from exc
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        except OSError as exc:
            raise MediaDownloadError("filesystem_write_failed") from exc

    def recover_published(self, request: DownloadRequest) -> DownloadResult | None:
        """Recover a fully prepared part whose immutable archive blob already exists.

        This path performs no locator resolution or network I/O and never
        publishes bytes.  It is intended for a database-finalization retry
        after the original worker committed the blob but lost its lease.
        """

        try:
            work_root = ensure_secure_root(request.work_root)
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        lock_relative = Path("locks") / f"{request.asset_id}.{request.generation}.lock"
        try:
            with exclusive_file_lock(work_root, lock_relative):
                store = _PartStore(work_root, request.asset_id, request.generation)
                try:
                    state = store.load(request, locator_fingerprint(request.locator))
                except _RestartRequired:
                    return None
                if state is None or state.expected_length is None or state.current_length != state.expected_length:
                    return None
                if state.current_length > self._limits.max_bytes:
                    raise MediaDownloadError("download_size_limit")
                digest, size = hash_file(store.part, root=store.root)
                if size != state.current_length:
                    raise MediaDownloadError("download_state_invalid")
                verified = verify_media(
                    store.part,
                    root=store.root,
                    expected_kind=request.expected_kind,
                    advertised_mime=None,
                    probe=self._probe,
                    sniff_bytes=self._limits.sniff_bytes,
                    probe_timeout_seconds=self._limits.probe_timeout_seconds,
                    probe_output_bytes=self._limits.probe_output_bytes,
                )
                archive = ArchivePublisher(request.archive_root)
                archive_path = archive.root / "sha256" / digest[:2] / f"{digest}.{verified.extension}"
                try:
                    blob = archive.validate_existing(archive_path, sha256=digest, size_bytes=size)
                except MediaDownloadError as error:
                    if error.code in {"archive_blob_missing", "archive_blob_invalid"}:
                        return None
                    raise
                return DownloadResult(
                    archive_path=blob.path,
                    sha256=digest,
                    size_bytes=size,
                    mime_type=verified.mime_type,
                    extension=verified.extension,
                    etag=state.validator if state.validator_kind == "etag" else None,
                    last_modified=state.validator if state.validator_kind == "last_modified" else None,
                )
        except PathLockBusyError as exc:
            raise MediaDownloadError("download_part_busy") from exc
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc

    def _download_locked(self, request: DownloadRequest, work_root: Path) -> DownloadResult:
        """Perform all partial-file work while this generation lock is held."""

        archive = ArchivePublisher(request.archive_root)
        store = _PartStore(work_root, request.asset_id, request.generation)
        locator = resolve_locator(request.locator, self._refresher)
        can_refresh_auth = isinstance(request.locator, AdapterRefreshLocator) and self._refresher is not None
        auth_refreshes = 0
        fingerprint = locator_fingerprint(request.locator)
        started = self._monotonic()
        restarts = 0
        while True:
            try:
                state = store.load(request, fingerprint)
            except _RestartRequired:
                if restarts >= self._limits.max_restarts:
                    raise MediaDownloadError("download_restart_limit") from None
                store.discard()
                restarts += 1
                state = None
            remaining = self._remaining(started)
            headers = self._resume_headers(state)
            try:
                with self._http.stream(locator.url, headers=headers, timeout_seconds=remaining) as (response, _target):
                    if can_refresh_auth and response.status_code in {401, 403}:
                        if auth_refreshes >= 1:
                            raise MediaDownloadError("locator_refresh_auth_expired")
                        locator = resolve_locator(request.locator, self._refresher)
                        auth_refreshes += 1
                        continue
                    outcome = self._consume_response(
                        response,
                        store=store,
                        request=request,
                        fingerprint=fingerprint,
                        state=state,
                        started=started,
                    )
            except _RestartRequired:
                if restarts >= self._limits.max_restarts:
                    raise MediaDownloadError("download_restart_limit") from None
                store.discard()
                restarts += 1
                continue
            completed_state, advertised_mime = outcome
            digest, size = hash_file(store.part, root=store.root)
            if size != completed_state.current_length:
                raise MediaDownloadError("download_state_invalid")
            verified = verify_media(
                store.part,
                root=store.root,
                expected_kind=request.expected_kind,
                advertised_mime=advertised_mime,
                probe=self._probe,
                sniff_bytes=self._limits.sniff_bytes,
                probe_timeout_seconds=self._limits.probe_timeout_seconds,
                probe_output_bytes=self._limits.probe_output_bytes,
            )
            blob = archive.publish(
                store.part,
                source_root=store.root,
                sha256=digest,
                size_bytes=size,
                extension=verified.extension,
                before_commit=request.before_archive_commit,
            )
            return DownloadResult(
                archive_path=blob.path,
                sha256=digest,
                size_bytes=size,
                mime_type=verified.mime_type,
                extension=verified.extension,
                etag=completed_state.validator if completed_state.validator_kind == "etag" else None,
                last_modified=(
                    completed_state.validator if completed_state.validator_kind == "last_modified" else None
                ),
            )

    def _remaining(self, started: float) -> float:
        remaining = self._limits.total_timeout_seconds - (self._monotonic() - started)
        if remaining <= 0:
            raise MediaDownloadError("download_timeout")
        return remaining

    @staticmethod
    def _resume_headers(state: PartMetadata | None) -> Mapping[str, str]:
        if state is None or state.current_length == 0 or state.validator is None:
            return {}
        return {"Range": f"bytes={state.current_length}-", "If-Range": state.validator}

    def _consume_response(
        self,
        response: httpx.Response,
        *,
        store: _PartStore,
        request: DownloadRequest,
        fingerprint: str,
        state: PartMetadata | None,
        started: float,
    ) -> tuple[PartMetadata, str | None]:
        _validate_encoding(response.headers)
        if state is not None and state.current_length > 0 and state.validator is not None:
            if response.status_code == 200:
                raise _RestartRequired
            if response.status_code == 416:
                match = _UNSATISFIED_RANGE.fullmatch(response.headers.get("content-range", ""))
                validator_kind, validator = _response_validator(response.headers)
                if (
                    match is not None
                    and int(match.group(1)) == state.current_length
                    and state.expected_length == state.current_length
                    and validator_kind == state.validator_kind
                    and validator == state.validator
                ):
                    return state, response.headers.get("content-type")
                raise _RestartRequired
            if response.status_code != 206:
                self._raise_status(response.status_code)
            expected_length = self._validate_partial_response(response, state)
            return (
                self._stream_bytes(
                    response,
                    store=store,
                    request=request,
                    fingerprint=fingerprint,
                    state=state,
                    expected_length=expected_length,
                    append=True,
                    started=started,
                ),
                response.headers.get("content-type"),
            )
        if response.status_code != 200:
            if response.status_code in {206, 416}:
                raise MediaDownloadError("download_range_invalid")
            self._raise_status(response.status_code)
        length = _content_length(response.headers)
        if length is not None and length > self._limits.max_bytes:
            raise MediaDownloadError("download_size_limit")
        validator_kind, validator = _response_validator(response.headers)
        if state is not None:
            store.discard()
        store.create()
        initial = PartMetadata(
            asset_id=request.asset_id,
            generation=request.generation,
            locator_fingerprint=fingerprint,
            validator_kind=validator_kind,
            validator=validator,
            expected_length=length,
            current_length=0,
        )
        store.save(initial)
        return (
            self._stream_bytes(
                response,
                store=store,
                request=request,
                fingerprint=fingerprint,
                state=initial,
                expected_length=length,
                append=False,
                started=started,
            ),
            response.headers.get("content-type"),
        )

    def _validate_partial_response(self, response: httpx.Response, state: PartMetadata) -> int:
        raw_range = response.headers.get("content-range", "")
        match = _CONTENT_RANGE.fullmatch(raw_range)
        if match is None:
            raise MediaDownloadError("download_range_invalid")
        start, end, total = (int(match.group(index)) for index in range(1, 4))
        if start != state.current_length or end < start or end >= total:
            raise MediaDownloadError("download_range_invalid")
        if state.expected_length is not None and total != state.expected_length:
            raise MediaDownloadError("download_range_invalid")
        length = _content_length(response.headers)
        if length is None or length != end - start + 1:
            raise MediaDownloadError("download_range_invalid")
        validator_kind, validator = _response_validator(response.headers)
        if validator_kind != state.validator_kind or validator != state.validator:
            raise MediaDownloadError("download_range_invalid")
        if total > self._limits.max_bytes:
            raise MediaDownloadError("download_size_limit")
        return total

    def _stream_bytes(
        self,
        response: httpx.Response,
        *,
        store: _PartStore,
        request: DownloadRequest,
        fingerprint: str,
        state: PartMetadata,
        expected_length: int | None,
        append: bool,
        started: float,
    ) -> PartMetadata:
        current = state.current_length if append else 0
        write_state = state
        try:
            with open_regular_file(store.part, root=store.root, append=append) as handle:
                try:
                    chunks = response.iter_bytes() if response.is_stream_consumed else response.iter_raw()
                    for chunk in chunks:
                        self._remaining(started)
                        if not chunk:
                            continue
                        if len(chunk) > self._limits.max_chunk_bytes:
                            raise MediaDownloadError("download_chunk_limit")
                        if current + len(chunk) > self._limits.max_bytes:
                            raise MediaDownloadError("download_size_limit")
                        if expected_length is not None and current + len(chunk) > expected_length:
                            raise MediaDownloadError("download_content_length_invalid")
                        handle.write(chunk)
                        current += len(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
                except Exception:
                    handle.flush()
                    os.fsync(handle.fileno())
                    write_state = PartMetadata(
                        asset_id=request.asset_id,
                        generation=request.generation,
                        locator_fingerprint=fingerprint,
                        validator_kind=state.validator_kind,
                        validator=state.validator,
                        expected_length=expected_length,
                        current_length=current,
                    )
                    store.save(write_state)
                    raise
        except MediaDownloadError:
            raise
        except (httpx.HTTPError, OSError) as exc:
            raise MediaDownloadError("download_interrupted") from exc
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        except Exception as exc:
            raise MediaDownloadError("download_interrupted") from exc
        completed_length = current if expected_length is None else expected_length
        completed = PartMetadata(
            asset_id=request.asset_id,
            generation=request.generation,
            locator_fingerprint=fingerprint,
            validator_kind=state.validator_kind,
            validator=state.validator,
            expected_length=completed_length,
            current_length=current,
        )
        store.save(completed)
        if expected_length is not None and current != expected_length:
            raise MediaDownloadError("download_interrupted")
        return completed

    @staticmethod
    def _raise_status(status_code: int) -> None:
        if status_code in _RETRYABLE_STATUSES or 500 <= status_code <= 599:
            raise MediaDownloadError("download_http_retryable")
        raise MediaDownloadError("download_http_terminal")


__all__ = [
    "DownloadLimits",
    "DownloadRequest",
    "DownloadResult",
    "PartMetadata",
    "SecureMediaDownloader",
]
