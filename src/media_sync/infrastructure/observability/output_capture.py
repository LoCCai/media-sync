"""Bounded, redaction-safe capture for child-process diagnostic streams.

The protocol stdout channel is drained and summarized but never persisted as
free text.  Human-oriented upstream stdout/stderr may be combined onto the
``upstream`` channel by a supervised child and is persisted one sanitized line
at a time.  Capturing is best effort and can never change process authority.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, Protocol

from media_sync.infrastructure.observability.events import (
    MAX_MESSAGE_BYTES,
    MAX_NUMBER,
    EventValidationError,
    canonical_uuid,
    normalize_process_output_message,
    process_output_message_has_explicit_shape,
    process_output_message_has_forbidden_content,
    validate_event,
)
from media_sync.infrastructure.observability.store import LogStore, LogStoreError
from media_sync.security.redaction import REDACTED, TRUNCATED, redact_text
from media_sync.security.secrets import SecretValue

if TYPE_CHECKING:
    from media_sync.integrations.mediacrawler.bridge import RunnerManifest

_READ_BYTES = 8192
_MAX_RAW_LINE_BYTES = 65_536
_MAX_CAPTURE_BYTES = 4 * 1024 * 1024
_MAX_CAPTURE_LINES = 4096
_JOIN_SECONDS = 2.0
PROCESS_OUTPUT_CONTEXT_ENV = "MEDIA_SYNC_PROCESS_OUTPUT_CONTEXT"
_PROCESS_OUTPUT_CONTEXT_VERSION = 1
_MAX_PROCESS_OUTPUT_CONTEXT_BYTES = 512
_PROCESS_OUTPUT_CONTEXT_KEYS = frozenset({"operation_id", "correlation_id", "login_session_id"})
_ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_ERROR_WORD = re.compile(r"(?i)(?:^|\W)(?:error|exception|fatal|traceback|failed|failure)(?:$|\W)")
_WARNING_WORD = re.compile(r"(?i)(?:^|\W)(?:warn(?:ing)?|deprecated|retry)(?:$|\W)")
_HIGH_RISK_ENVELOPE = re.compile(
    r"(?ix)(?:"
    r"\bset-cookie\s*:|"
    r"\bauthorization\s*(?:(?::|=)\s*|\s+bearer\s+)(?!\[REDACTED\])|"
    r"\bstorage[_-]?state\b|"
    r"\bcookies?\s*[:=]\s*(?!\[REDACTED\])(?:\[|\{|\()|"
    r"['\"]name['\"]\s*:\s*['\"](?:sessdata|bili_jct|sid|session|token)|"
    r"\b(?:ac_time_value|a1|bili_jct|csrf|ms_?token|sessdata|sid|webid|xsec_?token)\b"
    r"\s*[:=]\s*(?!\[REDACTED\])|"
    r"data:image/(?:png|jpeg|webp);base64,|"
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b|"
    r"\b(?:qr|qr[_-]?code|qrcode)\b\s*[:=]\s*(?!\[REDACTED\])\S+"
    r")"
)
_ABSOLUTE_PATH = re.compile(r"(?i)(?:^|[\s\"'=])(?:[a-z]:[\\/]|\\\\[^\\/\s]+[\\/]|/(?!/)(?:[^/\s]+/)+)[^\s\"']*")
_HTTP_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_QR_ASSIGNMENT = re.compile(r"(?i)\b(qr|qr[_-]?code|qrcode)(\s*[:=]\s*)\S+")
_QR_DATA = re.compile(r"(?i)data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=_-]+")
_OPAQUE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_+/=-])(?=[A-Za-z0-9_+/=-]{24,}(?![A-Za-z0-9_+/=-]))"
    r"(?=[A-Za-z0-9_+/=-]*[0-9_+/=])[A-Za-z0-9_+/=-]+"
)


class _Process(Protocol):
    stdout: IO[bytes] | None
    stderr: IO[bytes] | None


@dataclass(slots=True)
class _StreamStats:
    bytes_read: int = 0
    lines_seen: int = 0
    lines_emitted: int = 0
    invalid_encoding: int = 0
    line_too_large: int = 0
    capture_budget_exhausted: int = 0
    log_sink_rejected: int = 0
    policy_filtered: int = 0


def _bounded(value: int) -> int:
    return min(MAX_NUMBER, max(0, value))


def encode_process_output_context(values: Mapping[str, object]) -> str | None:
    """Project parent-validated IDs into one closed child environment value."""

    if not isinstance(values, Mapping):
        return None
    payload: dict[str, object] = {"schema_version": _PROCESS_OUTPUT_CONTEXT_VERSION}
    for key in _PROCESS_OUTPUT_CONTEXT_KEYS:
        if key not in values:
            continue
        try:
            payload[key] = canonical_uuid(values[key])
        except EventValidationError:
            return None
    if len(payload) == 1:
        return None
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return encoded if len(encoded.encode("ascii")) <= _MAX_PROCESS_OUTPUT_CONTEXT_BYTES else None


def decode_process_output_context(value: object) -> dict[str, str]:
    """Fail closed on duplicate, extra, mixed-invalid or noncanonical fields."""

    if (
        type(value) is not str
        or not value
        or "\x00" in value
        or len(value.encode("utf-8", errors="replace")) > _MAX_PROCESS_OUTPUT_CONTEXT_BYTES
    ):
        return {}

    def strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError
            result[key] = item
        return result

    try:
        payload = json.loads(value, object_pairs_hook=strict_object)
        if not isinstance(payload, dict) or set(payload) - ({"schema_version"} | _PROCESS_OUTPUT_CONTEXT_KEYS):
            return {}
        if (
            type(payload.get("schema_version")) is not int
            or payload["schema_version"] != _PROCESS_OUTPUT_CONTEXT_VERSION
            or len(payload) == 1
        ):
            return {}
        result: dict[str, str] = {}
        for key, item in payload.items():
            if key == "schema_version":
                continue
            result[key] = canonical_uuid(item)
        return result
    except (EventValidationError, TypeError, UnicodeError, ValueError):
        return {}


def _secret_fragments(values: Sequence[str | SecretValue]) -> tuple[str, ...]:
    fragments: set[str] = set()
    for value in values:
        revealed = value.reveal() if isinstance(value, SecretValue) else value
        if not revealed:
            continue
        fragments.add(revealed)
        fragments.update(part for part in revealed.splitlines() if part)
    return tuple(sorted(fragments, key=len, reverse=True))


def _fit_message(value: str) -> str:
    """Fit one already-redacted line into the event schema's encoded budget."""

    if len(json.dumps(value, ensure_ascii=True).encode("ascii")) <= MAX_MESSAGE_BYTES:
        return value
    suffix = TRUNCATED
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = value[:middle].rstrip() + suffix
        if len(json.dumps(candidate, ensure_ascii=True).encode("ascii")) <= MAX_MESSAGE_BYTES:
            low = middle
        else:
            high = middle - 1
    return value[:low].rstrip() + suffix


def _printable_output_line(raw: bytes) -> str | None:
    if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_RAW_LINE_BYTES or b"\x00" in raw:
        return None
    try:
        decoded = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    decoded = _ANSI_ESCAPE.sub("", decoded).rstrip("\r\n")
    printable = "".join(
        " " if character == "\t" else character for character in decoded if character.isprintable() or character == "\t"
    )
    printable = printable.strip()
    return printable


def _sanitize_printable_output_line(
    printable: str,
    *,
    known_secrets: Sequence[str | SecretValue] = (),
) -> str:
    if _HIGH_RISK_ENVELOPE.search(printable) is not None or _ABSOLUTE_PATH.search(printable) is not None:
        return REDACTED
    printable = _HTTP_URL.sub("[REDACTED_URL]", printable)
    redacted = redact_text(printable, known_secrets=_secret_fragments(known_secrets), max_length=8192)
    redacted = _QR_DATA.sub("[REDACTED]", redacted)
    redacted = _QR_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", redacted)
    redacted = _OPAQUE_TOKEN.sub("[REDACTED]", redacted)
    # Re-run the generic redactor after exact-secret replacement so an event
    # accepted by this helper is also independently accepted by validate_event.
    redacted = redact_text(redacted, max_length=8192)
    return _fit_message(redacted)


def sanitize_output_line(raw: bytes, *, known_secrets: Sequence[str | SecretValue] = ()) -> str | None:
    """Return one normalized, redacted printable line, or ``None`` for invalid input.

    This helper only sanitizes. ``ProcessOutputCapture`` separately requires an
    explicit log/exception shape and rejects structured/user-content payloads.
    High-risk envelopes and private absolute paths are replaced wholesale: a
    partially useful message is not worth retaining a newly minted credential.
    """

    printable = _printable_output_line(raw)
    if printable is None or not printable:
        return printable
    return _sanitize_printable_output_line(
        normalize_process_output_message(printable),
        known_secrets=known_secrets,
    )


def _message_level(message: str) -> str:
    if _ERROR_WORD.search(message) is not None:
        return "error"
    if _WARNING_WORD.search(message) is not None:
        return "warning"
    return "info"


def _strict_environment_integer(
    environment: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    value = environment.get(name)
    if value is None:
        return default
    if re.fullmatch(r"[1-9][0-9]{0,10}", value) is None:
        return None
    parsed = int(value)
    return parsed if minimum <= parsed <= maximum else None


def log_environment_for_child(environment: Mapping[str, str] | None = None) -> dict[str, str] | None:
    """Return only a validated state root and the three public log budgets."""

    source = os.environ if environment is None else environment
    raw_state = source.get("MEDIA_SYNC_STATE_DIR")
    if not isinstance(raw_state, str) or not raw_state or "\x00" in raw_state or len(raw_state) > 32_767:
        return None
    state_dir = Path(raw_state)
    if not state_dir.is_absolute() or state_dir == Path(state_dir.anchor) or ".." in state_dir.parts:
        return None
    segment = _strict_environment_integer(
        source,
        "MEDIA_SYNC_LOG_SEGMENT_MAX_BYTES",
        16_777_216,
        minimum=16_384,
        maximum=268_435_456,
    )
    total = _strict_environment_integer(
        source,
        "MEDIA_SYNC_LOG_TOTAL_MAX_BYTES",
        1_073_741_824,
        minimum=1_048_576,
        maximum=10_737_418_240,
    )
    retention = _strict_environment_integer(
        source,
        "MEDIA_SYNC_LOG_RETENTION_DAYS",
        7,
        minimum=1,
        maximum=90,
    )
    if segment is None or total is None or retention is None or total < 2 * segment:
        return None
    return {
        "MEDIA_SYNC_STATE_DIR": str(state_dir),
        "MEDIA_SYNC_LOG_SEGMENT_MAX_BYTES": str(segment),
        "MEDIA_SYNC_LOG_TOTAL_MAX_BYTES": str(total),
        "MEDIA_SYNC_LOG_RETENTION_DAYS": str(retention),
    }


def log_store_from_environment(environment: Mapping[str, str] | None = None) -> LogStore | None:
    """Build the same private sliced store used by Docker API/supervisor.

    An explicit absolute ``MEDIA_SYNC_STATE_DIR`` is required.  This avoids a
    library runner unexpectedly creating logs relative to an ambient cwd.
    """

    validated = log_environment_for_child(environment)
    if validated is None:
        return None
    try:
        return LogStore(
            Path(validated["MEDIA_SYNC_STATE_DIR"]) / "logs",
            segment_max_bytes=int(validated["MEDIA_SYNC_LOG_SEGMENT_MAX_BYTES"]),
            total_max_bytes=int(validated["MEDIA_SYNC_LOG_TOTAL_MAX_BYTES"]),
            retention_days=int(validated["MEDIA_SYNC_LOG_RETENTION_DAYS"]),
        )
    except (LogStoreError, OSError, TypeError, ValueError):
        return None


class ProcessOutputCapture:
    """Drain two child pipes and persist bounded safe diagnostic evidence."""

    def __init__(
        self,
        *,
        context: Mapping[str, object],
        known_secrets: Sequence[str | SecretValue] = (),
        event_sink: Callable[[Mapping[str, object]], object] | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._owned_store = log_store_from_environment(environment) if event_sink is None else None
        self._sink: Callable[[Mapping[str, object]], object] | None = event_sink or (
            self._owned_store.emit if self._owned_store else None
        )
        self._context = dict(context)
        self._known_secrets = tuple(known_secrets)
        self._stats = {
            "stdout_protocol": _StreamStats(),
            "upstream": _StreamStats(),
        }
        self._threads: list[threading.Thread] = []
        self._line_lock = threading.Lock()
        self._emitted_lines = 0
        self._attached = False
        self._closed = threading.Event()

    @property
    def enabled(self) -> bool:
        return self._sink is not None

    def attach(self, process: _Process) -> bool:
        if not self.enabled or self._attached or process.stdout is None or process.stderr is None:
            return False
        self._attached = True
        for stream, name, preserve in (
            (process.stdout, "stdout_protocol", False),
            (process.stderr, "upstream", True),
        ):
            worker = threading.Thread(
                target=self._read_stream,
                args=(stream, name, preserve),
                name=f"media-sync-output-{name}",
                daemon=True,
            )
            self._threads.append(worker)
            worker.start()
        return True

    def _event(self, **fields: object) -> bool:
        sink = self._sink
        if sink is None or self._closed.is_set():
            return False
        try:
            result = sink(validate_event({**self._context, **fields}))
            return result is not False
        except BaseException:
            return False

    def _record_line(self, raw: bytes, stats: _StreamStats) -> None:
        printable = _printable_output_line(raw)
        if printable is None:
            stats.invalid_encoding += 1
            return
        if not printable:
            return
        normalized = normalize_process_output_message(printable)
        if process_output_message_has_forbidden_content(normalized) or not process_output_message_has_explicit_shape(
            normalized
        ):
            stats.policy_filtered += 1
            return
        message = _sanitize_printable_output_line(normalized, known_secrets=self._known_secrets)
        if not message:
            return
        with self._line_lock:
            if self._emitted_lines >= _MAX_CAPTURE_LINES:
                stats.capture_budget_exhausted += 1
                return
            self._emitted_lines += 1
        if self._event(
            event_code="process_output",
            module="crawler",
            level=_message_level(normalized),
            phase="upstream_execution",
            action="execute",
            outcome="running",
            stream="upstream",
            message=message,
        ):
            stats.lines_emitted += 1
        else:
            stats.log_sink_rejected += 1

    def _finish_line(
        self,
        pending: bytearray,
        stats: _StreamStats,
        *,
        preserve: bool,
        oversized: bool,
        over_budget: bool,
    ) -> None:
        stats.lines_seen += 1
        if oversized:
            stats.line_too_large += 1
        elif over_budget:
            stats.capture_budget_exhausted += 1
        elif preserve:
            self._record_line(bytes(pending).rstrip(b"\r\n"), stats)
        pending.clear()

    def _read_stream(self, stream: IO[bytes], name: str, preserve: bool) -> None:
        stats = self._stats[name]
        pending = bytearray()
        oversized = False
        over_budget = False
        try:
            while True:
                part = stream.readline(_READ_BYTES)
                if not part:
                    if pending or oversized or over_budget:
                        self._finish_line(
                            pending,
                            stats,
                            preserve=preserve,
                            oversized=oversized,
                            over_budget=over_budget,
                        )
                    return
                stats.bytes_read += len(part)
                if stats.bytes_read > _MAX_CAPTURE_BYTES:
                    over_budget = True
                    pending.clear()
                elif not oversized:
                    if len(pending) + len(part) > _MAX_RAW_LINE_BYTES:
                        oversized = True
                        pending.clear()
                    else:
                        pending.extend(part)
                if part.endswith(b"\n"):
                    self._finish_line(
                        pending,
                        stats,
                        preserve=preserve,
                        oversized=oversized,
                        over_budget=over_budget,
                    )
                    oversized = False
                    over_budget = stats.bytes_read > _MAX_CAPTURE_BYTES
        except (OSError, ValueError):
            stats.log_sink_rejected += 1

    def _emit_summary(self, name: str, stats: _StreamStats, *, complete: bool) -> None:
        self._event(
            event_code="process_output_summary",
            module="crawler",
            level="info" if complete else "warning",
            phase="upstream_execution",
            action="finish",
            outcome="completed" if complete else "interrupted",
            stream=name,
            count=_bounded(stats.lines_seen),
            bytes=_bounded(stats.bytes_read),
        )
        for error_type in (
            "invalid_encoding",
            "line_too_large",
            "capture_budget_exhausted",
            "log_sink_rejected",
            "policy_filtered",
        ):
            count = getattr(stats, error_type)
            if count:
                self._event(
                    event_code="process_output_dropped",
                    module="crawler",
                    level="warning",
                    phase="upstream_execution",
                    action="drop",
                    outcome="skipped",
                    stream=name,
                    error_type=error_type,
                    count=_bounded(count),
                )

    def close(self, timeout: float = _JOIN_SECONDS) -> None:
        if self._closed.is_set():
            return
        deadline = time.monotonic() + max(0.0, timeout)
        for worker in self._threads:
            worker.join(timeout=max(0.0, deadline - time.monotonic()))
        complete = all(not worker.is_alive() for worker in self._threads)
        for name, stats in self._stats.items():
            self._emit_summary(name, stats, complete=complete)
        try:
            if self._owned_store is not None:
                remaining = min(5.0, max(1.0, deadline - time.monotonic()))
                with contextlib.suppress(LogStoreError):
                    self._owned_store.flush(timeout=remaining)
        finally:
            self._closed.set()
            if self._owned_store is not None:
                self._owned_store.close()


@contextmanager
def capture_current_process_output(
    *,
    context: Mapping[str, object],
    known_secrets: Sequence[str | SecretValue] = (),
    environment: Mapping[str, str] | None = None,
) -> Iterator[bool]:
    """Privately capture native/Python fd1+fd2 without touching outer protocols.

    Callers must duplicate any framed stderr writer before entering.  Both
    upstream descriptors are temporarily joined onto an internal pipe; the
    original descriptors are restored before summaries are emitted.
    """

    capture = ProcessOutputCapture(
        context=context,
        known_secrets=known_secrets,
        environment=environment,
    )
    if not capture.enabled:
        yield False
        return

    read_descriptor: int | None = None
    write_descriptor: int | None = None
    stdout_copy: int | None = None
    stderr_copy: int | None = None
    read_stream: IO[bytes] | None = None
    redirected = False

    def finish() -> None:
        if redirected:
            with contextlib.suppress(OSError):
                sys.stdout.flush()
                sys.stderr.flush()
            assert stdout_copy is not None and stderr_copy is not None
            with contextlib.suppress(OSError):
                os.dup2(stdout_copy, 1)
                os.dup2(stderr_copy, 2)
        for descriptor in (stdout_copy, stderr_copy, write_descriptor, read_descriptor):
            if descriptor is not None:
                with contextlib.suppress(OSError):
                    os.close(descriptor)
        capture.close()
        if read_stream is not None:
            with contextlib.suppress(OSError):
                read_stream.close()

    try:
        read_descriptor, write_descriptor = os.pipe()
        os.set_inheritable(read_descriptor, False)
        os.set_inheritable(write_descriptor, False)
        read_stream = os.fdopen(read_descriptor, "rb", buffering=0)
        read_descriptor = None
        local = _LocalCaptureProcess(stdout=io.BytesIO(), stderr=read_stream)
        if not capture.attach(local):
            finish()
            yield False
            return
        stdout_copy, stderr_copy = os.dup(1), os.dup(2)
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(write_descriptor, 1)
        os.dup2(write_descriptor, 2)
        os.close(write_descriptor)
        write_descriptor = None
        redirected = True
    except (OSError, RuntimeError, ValueError):
        finish()
        yield False
        return
    try:
        yield True
    finally:
        finish()


@dataclass(slots=True)
class _LocalCaptureProcess:
    stdout: IO[bytes] | None
    stderr: IO[bytes] | None


def mediacrawler_output_context(manifest: RunnerManifest) -> dict[str, object]:
    """Project only trusted local correlation values from a runner manifest."""

    result: dict[str, object] = {
        "account_id": str(manifest.account_id),
        "subscription_id": str(manifest.subscription_id),
        "job_id": str(manifest.job_id),
        "platform": manifest.platform.value,
    }
    if manifest.sync_run_id is not None:
        result["run_id"] = str(manifest.sync_run_id)
    if manifest.attempt is not None:
        result["attempt"] = manifest.attempt
    return result


__all__ = [
    "PROCESS_OUTPUT_CONTEXT_ENV",
    "ProcessOutputCapture",
    "capture_current_process_output",
    "decode_process_output_context",
    "encode_process_output_context",
    "log_environment_for_child",
    "log_store_from_environment",
    "mediacrawler_output_context",
    "sanitize_output_line",
]
