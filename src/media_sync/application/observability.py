"""Best-effort lifecycle events with closed fields and task-local UUID context.

No function in this module formats log messages, exceptions or request data.
The durable domain repositories remain authoritative when telemetry is absent.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType

from media_sync.infrastructure.observability.events import (
    ENUM_FIELDS,
    MAX_NUMBER,
    NUMBER_FIELDS,
    UUID_FIELDS,
    EventValidationError,
    canonical_uuid,
    validate_event,
)

EventSink = Callable[[Mapping[str, object]], None]
_CONTEXT: ContextVar[Mapping[str, object]] = ContextVar("media_sync_safe_event_context", default=MappingProxyType({}))
_EMITTING: ContextVar[bool] = ContextVar("media_sync_emitting_safe_event", default=False)


def _identities(values: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in UUID_FIELDS:
        if key not in values:
            continue
        try:
            result[key] = canonical_uuid(values[key])
        except EventValidationError:
            continue
    return result


@contextmanager
def event_context(*, clear: bool = False, **identities: object) -> Iterator[None]:
    """Bind trusted canonical local IDs; explicit invalid/None IDs clear old IDs."""

    merged = {} if clear else dict(_CONTEXT.get())
    for key in identities:
        merged.pop(key, None)
    merged.update(_identities(identities))
    token = _CONTEXT.set(merged)
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def emit_event(sink: EventSink | None, *, event_code: str, module: str, **fields: object) -> None:
    """Emit only the closed vocabulary; telemetry can never fail a domain action."""

    if sink is None or _EMITTING.get():
        return
    token = _EMITTING.set(True)
    try:
        event = dict(_CONTEXT.get())
        # An explicit ID always wins, including an invalid one that clears the
        # inherited value. Never attribute a child to an unrelated parent ID.
        for key in fields:
            event.pop(key, None)
        event.update(_identities(fields))
        event.update(event_code=event_code, module=module, level="info")
        for key, value in fields.items():
            if key in ENUM_FIELDS and type(value) is str and value in ENUM_FIELDS[key]:
                event[key] = value
            elif key == "phase":
                event[key] = "unknown"
            elif key in NUMBER_FIELDS and type(value) is int and 0 <= value <= MAX_NUMBER:
                event[key] = value
        sink(validate_event(event))
    except BaseException:
        # Includes hostile/failed logging handlers; do not recursively log it.
        return
    finally:
        _EMITTING.reset(token)


def elapsed_ms(started: float) -> int:
    return min(MAX_NUMBER, max(0, int((time.monotonic() - started) * 1000)))


_LOGGER_MODULES = (
    ("media_sync.integrations.mediacrawler.login", "login"),
    ("media_sync.integrations.mediacrawler", "crawler"),
    ("media_sync.application.authentication", "login"),
    ("media_sync.application.cookie_login", "cookie_login"),
    ("media_sync.application.creator_profile", "creator_profile"),
    ("media_sync.application.downloading", "download"),
    ("media_sync.application.media_server", "media_server"),
    ("media_sync.application.library", "library"),
    ("media_sync.scheduler.supervisor", "supervisor"),
    ("media_sync.scheduler.pipeline_worker", "pipeline"),
    ("media_sync.scheduler.pipeline", "pipeline"),
    ("media_sync.scheduler", "scheduler"),
    ("media_sync.api", "api"),
    ("media_sync.cli", "cli"),
    ("media_sync.interfaces.api", "api"),
    ("media_sync.interfaces.cli", "cli"),
    ("media_sync.exporters", "exporter"),
)


class SafeEventLoggingHandler(logging.Handler):
    """Count standard log calls without ever accessing their free-text payload."""

    def __init__(self, event_sink: EventSink) -> None:
        super().__init__()
        self.event_sink = event_sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            module = "application"
            if type(record.name) is str:
                for prefix, candidate in _LOGGER_MODULES:
                    if record.name == prefix or record.name.startswith(prefix + "."):
                        module = candidate
                        break
            level = "info"
            if type(record.levelno) is int:
                for threshold, candidate in (
                    (logging.CRITICAL, "critical"),
                    (logging.ERROR, "error"),
                    (logging.WARNING, "warning"),
                    (logging.INFO, "info"),
                    (logging.DEBUG, "debug"),
                ):
                    if record.levelno >= threshold:
                        level = candidate
                        break
            emit_event(
                self.event_sink,
                event_code="application_log_redacted",
                module=module,
                level=level,
                count=1,
            )
        except BaseException:
            return


__all__ = ["EventSink", "SafeEventLoggingHandler", "elapsed_ms", "emit_event", "event_context"]
