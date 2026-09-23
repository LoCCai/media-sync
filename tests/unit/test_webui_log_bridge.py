"""Execution 0078: bounded crawler-WebUI → log-center bridge contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from media_sync.infrastructure.observability.events import validate_event
from media_sync.infrastructure.observability.store import LogStore
from media_sync.integrations.mediacrawler.webui_log_bridge import crawler_log_bridge


class _RecordingStore:
    def __init__(self, *, accept: bool = True) -> None:
        self.events: list[dict[str, Any]] = []
        self.accept = accept

    def emit(self, event: dict[str, Any]) -> bool:
        validate_event(event)
        self.events.append(dict(event))
        return self.accept


_PREFIXED = "2026-09-23 11:07:29 MediaCrawler INFO (login.py:63) - [DouYinLogin.begin] login finished"
_PLAIN_SHAPED = "INFO [DouYinLogin.begin] login finished"


def test_bridge_returns_none_without_store() -> None:
    assert crawler_log_bridge(None) is None


def test_bridge_accepts_pinned_prefix_line_and_normalizes_prefix() -> None:
    store = _RecordingStore()
    publish = crawler_log_bridge(store)

    assert publish(_PREFIXED, "info") is True

    assert len(store.events) == 1
    event = store.events[0]
    assert event["event_code"] == "process_output"
    assert event["module"] == "crawler"
    assert event["stream"] == "upstream"
    assert event["level"] == "info"
    assert event["message"].startswith("INFO ")
    assert "MediaCrawler INFO (" not in event["message"]


def test_bridge_rejects_shapeless_and_forbidden_lines() -> None:
    store = _RecordingStore()
    publish = crawler_log_bridge(store)

    assert publish("[DouYinLogin.begin] no level shape") is False
    assert publish("INFO body: some content description") is False
    assert publish("") is False
    assert publish("   ") is False

    assert store.events == []


def test_bridge_clamps_unknown_level_and_never_raises() -> None:
    store = _RecordingStore(accept=False)
    publish = crawler_log_bridge(store)

    assert publish(_PLAIN_SHAPED, "SUCCESS") is False
    assert store.events[0]["level"] == "info"

    class _ExplodingStore:
        def emit(self, event: dict[str, Any]) -> bool:
            raise RuntimeError("store unavailable")

    silent = crawler_log_bridge(_ExplodingStore())
    assert silent(_PLAIN_SHAPED, "warning") is False


def test_bridge_against_real_log_store(tmp_path: Path) -> None:
    store = LogStore(
        tmp_path / "state" / "logs",
        segment_max_bytes=64 * 1024,
        total_max_bytes=256 * 1024,
        retention_days=7,
    )
    publish = crawler_log_bridge(store)
    try:
        assert publish(_PREFIXED, "info") is True
    finally:
        store.close()
