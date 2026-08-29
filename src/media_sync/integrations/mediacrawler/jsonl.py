"""Bounded streaming reader for MediaCrawler's append-only JSONL output."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from media_sync.domain import freeze_mapping

DEFAULT_MAX_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_LINE_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_PATH_CHARS = 4_096
DEFAULT_MAX_RECORDS = 10_000


class QuarantineReason(StrEnum):
    """Stable, non-secret reason codes safe for manifests and operator output."""

    INVALID_UTF8 = "invalid_utf8"
    INVALID_JSON = "invalid_json"
    NON_OBJECT = "non_object"
    UNKNOWN_RECORD = "unknown_record"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_RECORD = "invalid_record"


class JsonlLimitError(ValueError):
    """Raised before an input can exceed its configured resource budget."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"MediaCrawler JSONL {code}")


class JsonlSourceError(ValueError):
    """Raised when an input path cannot be treated as one safe regular file."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"MediaCrawler JSONL {code}")


@dataclass(frozen=True, slots=True)
class JsonlRecord:
    """One decoded JSON object with safe source-location metadata."""

    line_number: int
    byte_count: int
    fingerprint_sha256: str
    value: Mapping[str, object] = field(repr=False)


@dataclass(frozen=True, slots=True)
class QuarantinedRecord:
    """A rejected line descriptor that deliberately never retains its contents."""

    line_number: int
    byte_count: int
    fingerprint_sha256: str
    reason: QuarantineReason


JsonlEvent = JsonlRecord | QuarantinedRecord


@dataclass(frozen=True, slots=True)
class JsonlReadResult:
    """Materialized result for callers that want one bounded batch."""

    records: tuple[JsonlRecord, ...]
    quarantined: tuple[QuarantinedRecord, ...]
    bytes_read: int
    records_seen: int
    truncated_tail: bool


def _reject_nonstandard_number(value: str) -> None:
    del value
    raise ValueError("non-standard JSON number")


def _fingerprint(raw_line: bytes) -> str:
    return hashlib.sha256(raw_line).hexdigest()


class JsonlReader:
    """Replayable iterator that never loads the complete upstream file into memory."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
        max_path_chars: int = DEFAULT_MAX_PATH_CHARS,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> None:
        if isinstance(max_bytes, bool) or max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        if isinstance(max_line_bytes, bool) or max_line_bytes < 1:
            raise ValueError("max_line_bytes must be positive")
        if isinstance(max_path_chars, bool) or max_path_chars < 1:
            raise ValueError("max_path_chars must be positive")
        if isinstance(max_records, bool) or max_records < 1:
            raise ValueError("max_records must be positive")
        if len(str(path)) > max_path_chars:
            raise JsonlSourceError("path_too_long")
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.max_line_bytes = max_line_bytes
        self.max_path_chars = max_path_chars
        self.max_records = max_records
        self.bytes_read = 0
        self.records_seen = 0
        self.truncated_tail = False

    def __iter__(self) -> Iterator[JsonlEvent]:
        self._reset()

        try:
            if self.path.is_symlink():
                raise JsonlSourceError("symlink_not_allowed")
            if not self.path.is_file():
                raise JsonlSourceError("source_not_regular_file")
            source = self.path.open("rb")
        except JsonlSourceError:
            raise
        except OSError:
            raise JsonlSourceError("source_unreadable") from None

        with source:
            yield from self._iter_source(source)

    def iter_payload(self, payload: bytes) -> Iterator[JsonlEvent]:
        """Decode one already-verified immutable payload without reopening a path."""

        self._reset()
        with io.BytesIO(payload) as source:
            yield from self._iter_source(source)

    def _reset(self) -> None:
        self.bytes_read = 0
        self.records_seen = 0
        self.truncated_tail = False

    def _iter_source(self, source: io.BufferedIOBase) -> Iterator[JsonlEvent]:
        line_number = 0
        while True:
            remaining = self.max_bytes - self.bytes_read
            raw_line = source.readline(min(remaining, self.max_line_bytes) + 1)
            if not raw_line:
                break
            line_number += 1
            self.bytes_read += len(raw_line)
            if self.bytes_read > self.max_bytes:
                raise JsonlLimitError("byte_limit_exceeded")
            if len(raw_line) > self.max_line_bytes:
                raise JsonlLimitError("line_limit_exceeded")
            if not raw_line.strip(b" \t\r\n"):
                continue

            self.records_seen += 1
            if self.records_seen > self.max_records:
                raise JsonlLimitError("record_limit_exceeded")

            byte_count = len(raw_line)
            fingerprint = _fingerprint(raw_line)
            terminal_fragment = not raw_line.endswith(b"\n")
            if line_number == 1 and raw_line.startswith(b"\xef\xbb\xbf"):
                raw_line = raw_line.removeprefix(b"\xef\xbb\xbf")

            try:
                decoded = raw_line.decode("utf-8").strip()
            except UnicodeDecodeError:
                if terminal_fragment:
                    self.truncated_tail = True
                    break
                yield QuarantinedRecord(
                    line_number=line_number,
                    byte_count=byte_count,
                    fingerprint_sha256=fingerprint,
                    reason=QuarantineReason.INVALID_UTF8,
                )
                continue

            try:
                loaded = json.loads(decoded, parse_constant=_reject_nonstandard_number)
            except (json.JSONDecodeError, ValueError):
                if terminal_fragment:
                    self.truncated_tail = True
                    break
                yield QuarantinedRecord(
                    line_number=line_number,
                    byte_count=byte_count,
                    fingerprint_sha256=fingerprint,
                    reason=QuarantineReason.INVALID_JSON,
                )
                continue

            if not isinstance(loaded, dict):
                yield QuarantinedRecord(
                    line_number=line_number,
                    byte_count=byte_count,
                    fingerprint_sha256=fingerprint,
                    reason=QuarantineReason.NON_OBJECT,
                )
                continue
            value = cast(dict[str, Any], loaded)
            yield JsonlRecord(
                line_number=line_number,
                byte_count=byte_count,
                fingerprint_sha256=fingerprint,
                value=freeze_mapping(value),
            )


def read_jsonl(
    path: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
    max_path_chars: int = DEFAULT_MAX_PATH_CHARS,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> JsonlReadResult:
    """Read one capped file as a batch while retaining quarantine metadata."""

    reader = JsonlReader(
        path,
        max_bytes=max_bytes,
        max_line_bytes=max_line_bytes,
        max_path_chars=max_path_chars,
        max_records=max_records,
    )
    records: list[JsonlRecord] = []
    quarantined: list[QuarantinedRecord] = []
    for event in reader:
        if isinstance(event, JsonlRecord):
            records.append(event)
        else:
            quarantined.append(event)
    return JsonlReadResult(
        records=tuple(records),
        quarantined=tuple(quarantined),
        bytes_read=reader.bytes_read,
        records_seen=reader.records_seen,
        truncated_tail=reader.truncated_tail,
    )


def read_jsonl_bytes(
    payload: bytes,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> JsonlReadResult:
    """Read one immutable receipt-verified payload without path reuse."""

    reader = JsonlReader(
        "<validated-output-snapshot>",
        max_bytes=max_bytes,
        max_line_bytes=max_line_bytes,
        max_records=max_records,
    )
    records: list[JsonlRecord] = []
    quarantined: list[QuarantinedRecord] = []
    for event in reader.iter_payload(payload):
        if isinstance(event, JsonlRecord):
            records.append(event)
        else:
            quarantined.append(event)
    return JsonlReadResult(
        records=tuple(records),
        quarantined=tuple(quarantined),
        bytes_read=reader.bytes_read,
        records_seen=reader.records_seen,
        truncated_tail=reader.truncated_tail,
    )


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_LINE_BYTES",
    "DEFAULT_MAX_PATH_CHARS",
    "DEFAULT_MAX_RECORDS",
    "JsonlEvent",
    "JsonlLimitError",
    "JsonlReadResult",
    "JsonlReader",
    "JsonlRecord",
    "JsonlSourceError",
    "QuarantineReason",
    "QuarantinedRecord",
    "read_jsonl",
    "read_jsonl_bytes",
]
