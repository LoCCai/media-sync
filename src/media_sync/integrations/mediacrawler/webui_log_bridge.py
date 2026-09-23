"""Bounded bridge from the native crawler WebUI log stream to the log center.

Execution 0078: the WebUI manager already redacts each crawler line before it
reaches the in-memory panel (``push_log``).  This module mirrors the same
already-redacted line into the private rolling log center as a ``process_output``
event on the ``upstream`` stream — but only when the line keeps an explicit
pinned MediaCrawler log shape and carries no forbidden content.  Anything else
is dropped: the bridge must never widen what the log center accepts, never
affect the panel, and never raise into the WebUI event loop.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from media_sync.infrastructure.observability.events import (
    normalize_process_output_message,
    process_output_message_has_explicit_shape,
    process_output_message_has_forbidden_content,
)
from media_sync.security.redaction import redact_text

_CRAWLER_LOG_LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})
_BRIDGE_MAX_MESSAGE_CHARACTERS = 2048


class _LogStoreLike(Protocol):
    def emit(self, event: Mapping[str, object]) -> bool: ...


def crawler_log_bridge(
    store: _LogStoreLike | None,
) -> Callable[[str, str], bool] | None:
    """Build the bounded publish function for one manager instance.

    The returned callable takes the raw line and its WebUI level, applies the
    same redaction budget the panel uses, and returns whether the log center
    accepted the event.  It never raises.
    """

    if store is None:
        return None

    def publish(message: str, level: str = "info") -> bool:
        if not isinstance(message, str) or not message.strip():
            return False
        safe = redact_text(message, max_length=_BRIDGE_MAX_MESSAGE_CHARACTERS)
        if not safe or safe == "[REDACTED]":
            return False
        normalized = normalize_process_output_message(safe)
        if normalize_process_output_message(normalized) != normalized:
            return False
        if not process_output_message_has_explicit_shape(safe):
            return False
        if process_output_message_has_forbidden_content(safe):
            return False
        canonical_level = level.lower().strip()
        if canonical_level not in _CRAWLER_LOG_LEVELS:
            canonical_level = "info"
        try:
            return bool(
                store.emit(
                    {
                        "event_code": "process_output",
                        "module": "crawler",
                        "level": canonical_level,
                        "stream": "upstream",
                        "message": normalized,
                    }
                )
            )
        except Exception:
            return False

    return publish
