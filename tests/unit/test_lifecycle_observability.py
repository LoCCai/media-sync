"""Closed application event projection; never format arbitrary log payloads."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from uuid import uuid4

import pytest

from media_sync.application.observability import SafeEventLoggingHandler, emit_event, event_context
from media_sync.infrastructure.observability.events import validate_event


class _Unprintable:
    def __str__(self) -> str:
        raise AssertionError("message must never be formatted")

    def __repr__(self) -> str:
        raise AssertionError("args must never be inspected")


@pytest.mark.parametrize(
    ("name", "expected_module"),
    [
        ("media_sync.scheduler.service", "scheduler"),
        ("media_sync.scheduler.pipeline_worker", "pipeline"),
        ("media_sync.scheduler.pipeline.worker", "pipeline"),
        ("media_sync.integrations.mediacrawler.login", "login"),
        ("media_sync.integrations.mediacrawler.reader", "crawler"),
        ("SENTINEL-cookie-secret", "application"),
        ("media_sync.schedulerSECRET", "application"),
    ],
)
def test_standard_logging_never_formats_payload(name: str, expected_module: str) -> None:
    events: list[Mapping[str, object]] = []
    handler = SafeEventLoggingHandler(events.append)
    record = logging.LogRecord(name, logging.ERROR, "SENTINEL-path", 7, _Unprintable(), (_Unprintable(),), None)
    record.exc_info = (RuntimeError, RuntimeError("SENTINEL-password"), None)
    record.exc_text = "SENTINEL-auth-token"
    record.stack_info = "SENTINEL-stack"
    record.getMessage = lambda: pytest.fail("getMessage must never run")  # type: ignore[method-assign]
    handler.handle(record)
    assert events == [
        {"event_code": "application_log_redacted", "module": expected_module, "level": "error", "count": 1}
    ]
    assert validate_event(events[0]) == events[0]


def test_context_ids_explicit_values_win_and_invalid_values_clear_scope() -> None:
    events: list[Mapping[str, object]] = []
    outer, inner, correlation = str(uuid4()), str(uuid4()), str(uuid4())
    with event_context(operation_id=outer, correlation_id=correlation, account_id="SENTINEL-cookie"):
        emit_event(events.append, event_code="job_started", module="scheduler", operation_id=inner)
        emit_event(events.append, event_code="job_started", module="scheduler", operation_id="SENTINEL-invalid")
        with event_context(clear=True, operation_id=inner):
            emit_event(events.append, event_code="job_started", module="scheduler")
        emit_event(events.append, event_code="job_started", module="scheduler")
    emit_event(events.append, event_code="job_started", module="scheduler")
    assert events[0]["operation_id"] == inner
    assert "operation_id" not in events[1]
    assert events[2]["operation_id"] == inner and "correlation_id" not in events[2]
    assert events[3]["operation_id"] == outer
    assert "operation_id" not in events[4]
    assert "SENTINEL" not in repr(events)


def test_unknown_phase_and_extra_raw_fields_are_redacted_without_losing_event() -> None:
    events: list[Mapping[str, object]] = []
    emit_event(
        events.append,
        event_code="operation_phase_changed",
        module="login",
        phase="SENTINEL-secret-phase",
        message="SENTINEL-cookie",
        raw_error=_Unprintable(),
        action="SENTINEL-action",
        duration_ms=-1,
        attempt=True,
    )
    assert events == [{"event_code": "operation_phase_changed", "module": "login", "level": "info", "phase": "unknown"}]


@pytest.mark.parametrize("error", [RuntimeError, SystemExit, KeyboardInterrupt])
def test_sink_errors_never_escape_or_poison_later_events(error: type[BaseException]) -> None:
    def failed_sink(_event: Mapping[str, object]) -> None:
        raise error("SENTINEL-secret")

    emit_event(failed_sink, event_code="job_started", module="scheduler")
    events: list[Mapping[str, object]] = []
    emit_event(events.append, event_code="job_finished", module="scheduler")
    assert len(events) == 1


def test_recursively_logging_sink_is_bounded() -> None:
    events: list[Mapping[str, object]] = []

    def sink(event: Mapping[str, object]) -> None:
        events.append(event)
        emit_event(sink, event_code="job_started", module="scheduler")

    emit_event(sink, event_code="job_started", module="scheduler")
    assert len(events) == 1


async def test_async_tasks_and_thread_offloads_keep_independent_contexts() -> None:
    events: list[Mapping[str, object]] = []
    ids = [str(uuid4()), str(uuid4())]

    async def task(operation_id: str) -> None:
        with event_context(operation_id=operation_id):
            await asyncio.sleep(0)
            await asyncio.to_thread(emit_event, events.append, event_code="job_started", module="scheduler")

    await asyncio.gather(*(task(operation_id) for operation_id in ids))
    assert {event["operation_id"] for event in events} == set(ids)
    emit_event(events.append, event_code="job_started", module="scheduler")
    assert "operation_id" not in events[-1]
