"""Safe child-output capture, loss accounting and Docker store wiring."""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from media_sync.infrastructure.observability import output_capture as capture_module
from media_sync.infrastructure.observability.events import EventValidationError, validate_event
from media_sync.infrastructure.observability.output_capture import (
    ProcessOutputCapture,
    decode_process_output_context,
    encode_process_output_context,
    log_store_from_environment,
    sanitize_output_line,
)
from media_sync.infrastructure.observability.store import LogStore
from media_sync.security import SecretValue

SECRET = "COOKIE-SENTINEL-6c4f038e"
PINNED_PREFIX = "2026-09-06 15:00:00 MediaCrawler {level} (login.py:99) - "


def _context() -> dict[str, object]:
    return {
        "account_id": str(uuid4()),
        "subscription_id": str(uuid4()),
        "job_id": str(uuid4()),
        "run_id": str(uuid4()),
        "platform": "bili",
        "attempt": 2,
    }


def _process(stdout: bytes, stderr: bytes) -> SimpleNamespace:
    return SimpleNamespace(stdout=io.BytesIO(stdout), stderr=io.BytesIO(stderr))


def test_process_output_context_projects_canonical_parent_ids_only() -> None:
    operation_id = str(uuid4())
    correlation_id = str(uuid4())
    login_session_id = str(uuid4())
    encoded = encode_process_output_context(
        {
            "operation_id": operation_id,
            "correlation_id": correlation_id,
            "login_session_id": login_session_id,
            "account_id": str(uuid4()),
            "untrusted": "ignored",
        }
    )

    assert encoded is not None
    assert decode_process_output_context(encoded) == {
        "correlation_id": correlation_id,
        "login_session_id": login_session_id,
        "operation_id": operation_id,
    }
    assert "account_id" not in encoded
    assert "untrusted" not in encoded


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "[]",
        '{"schema_version":true,"operation_id":"11111111-1111-4111-8111-111111111111"}',
        '{"schema_version":1}',
        '{"schema_version":1,"operation_id":"not-a-uuid"}',
        '{"schema_version":1,"operation_id":"11111111-1111-4111-8111-111111111111","login_session_id":"invalid"}',
        '{"schema_version":1,"operation_id":"11111111-1111-4111-8111-111111111111",'
        '"operation_id":"22222222-2222-4222-8222-222222222222"}',
        '{"schema_version":1,"operation_id":"11111111-1111-4111-8111-111111111111",'
        '"account_id":"22222222-2222-4222-8222-222222222222"}',
        '{"schema_version":1,"operation_id":"11111111-1111-4111-8111-111111111111","secret":"sentinel"}',
    ],
)
def test_process_output_context_rejects_the_complete_hostile_envelope(value: object) -> None:
    assert decode_process_output_context(value) == {}


def test_invalid_parent_context_is_not_partially_encoded() -> None:
    assert (
        encode_process_output_context(
            {
                "operation_id": "11111111-1111-4111-8111-111111111111",
                "login_session_id": "invalid",
            }
        )
        is None
    )


def test_sanitizer_removes_known_secret_assignments_signed_urls_and_controls() -> None:
    raw = (
        f"\x1b[31mrequest failed cookie={SECRET}, url=https://cdn.invalid/video.mp4?token=SIGNED-VALUE\x1b[0m\t retry\n"
    ).encode()
    message = sanitize_output_line(raw, known_secrets=(SecretValue(SECRET),))
    assert message is not None
    assert "request failed" in message
    assert "[REDACTED]" in message
    assert SECRET not in message
    assert "SIGNED-VALUE" not in message
    assert "\x1b" not in message
    assert "\n" not in message


def test_free_text_is_allowed_only_for_independently_redacted_process_output() -> None:
    safe = {
        "event_code": "process_output",
        "module": "crawler",
        "level": "error",
        "stream": "upstream",
        "message": "Traceback: browser navigation failed",
    }
    assert validate_event(safe) == safe
    assert validate_event({**safe, "message": "[REDACTED]"})["message"] == "[REDACTED]"
    with pytest.raises(EventValidationError):
        validate_event({**safe, "message": f"cookie={SECRET}"})
    with pytest.raises(EventValidationError):
        validate_event({**safe, "message": "the creator caption says login error"})
    with pytest.raises(EventValidationError):
        validate_event(
            {
                "event_code": "service_started",
                "module": "crawler",
                "level": "info",
                "message": "arbitrary text",
            }
        )


def test_capture_keeps_upstream_lines_but_only_summarizes_protocol_stdout() -> None:
    events: list[Mapping[str, object]] = []
    context = _context()
    capture = ProcessOutputCapture(context=context, known_secrets=(SECRET,), event_sink=events.append)
    process = _process(
        f'{{"status":"failed","cookie":"{SECRET}"}}\n'.encode(),
        f"login starting\nERROR cookie={SECRET}\n".encode(),
    )
    assert capture.attach(process)
    capture.close()

    lines = [event for event in events if event["event_code"] == "process_output"]
    assert [event["message"] for event in lines] == ["ERROR cookie=[REDACTED]"]
    assert [event["level"] for event in lines] == ["error"]
    assert all(event["stream"] == "upstream" for event in lines)
    assert all(all(event[key] == value for key, value in context.items()) for event in events)
    protocol = [
        event
        for event in events
        if event["event_code"] == "process_output_summary" and event["stream"] == "stdout_protocol"
    ]
    assert len(protocol) == 1 and protocol[0]["count"] == 1
    assert any(
        event["event_code"] == "process_output_dropped"
        and event["error_type"] == "policy_filtered"
        and event["count"] == 1
        for event in events
    )
    assert SECRET not in json.dumps(events)


@pytest.mark.parametrize(
    ("level", "expected_level", "detail"),
    [
        ("INFO", "info", "browser login started"),
        ("WARNING", "warning", "browser login retry scheduled"),
        ("ERROR", "error", "browser navigation failed"),
    ],
)
def test_capture_normalizes_the_exact_pinned_mediacrawler_formatter(
    level: str,
    expected_level: str,
    detail: str,
) -> None:
    events: list[Mapping[str, object]] = []
    capture = ProcessOutputCapture(context=_context(), event_sink=events.append)
    raw_message = PINNED_PREFIX.format(level=level) + detail

    assert capture.attach(_process(b"", f"{raw_message}\n".encode()))
    capture.close()

    lines = [event for event in events if event["event_code"] == "process_output"]
    assert [(event["level"], event["message"]) for event in lines] == [(expected_level, f"{level} {detail}")]
    assert "MediaCrawler" not in json.dumps(lines)
    with pytest.raises(EventValidationError):
        validate_event(
            {
                "event_code": "process_output",
                "module": "crawler",
                "level": expected_level,
                "stream": "upstream",
                "message": raw_message,
            }
        )


def test_pinned_formatter_payloads_remain_fail_closed_in_events_and_raw_segments(tmp_path: Path) -> None:
    state = tmp_path / "state"
    sentinels = (
        "JSON-PAYLOAD-SENTINEL",
        "HTML-PAYLOAD-SENTINEL",
        "CONTENT-PAYLOAD-SENTINEL",
        "COOKIE-PAYLOAD-SENTINEL",
        "AUTH-PAYLOAD-SENTINEL",
        "STORAGE-PAYLOAD-SENTINEL",
        "QR-PAYLOAD-SENTINEL",
        "SIGNED-URL-PAYLOAD-SENTINEL",
        "WINDOWS-PATH-PAYLOAD-SENTINEL",
        "POSIX-PATH-PAYLOAD-SENTINEL",
    )
    prefix = PINNED_PREFIX.format(level="ERROR")
    unsafe = [
        prefix + f'response: {{"error":"{sentinels[0]}"}}',
        prefix + f"<html><body>{sentinels[1]}</body></html>",
        prefix + f"content={sentinels[2]}",
        prefix + f"Cookie: sid={sentinels[3]}",
        prefix + f"Authorization: Bearer {sentinels[4]}",
        prefix + f'storage_state={{"cookies":["{sentinels[5]}"]}}',
        prefix + f"qrcode=data:image/png;base64,{sentinels[6]}",
        prefix + f"request failed at https://cdn.invalid/video?token={sentinels[7]}",
        prefix + rf"profile C:\Users\private\{sentinels[8]}",
        prefix + f"profile /home/private/{sentinels[9]}/state.json",
    ]
    capture = ProcessOutputCapture(
        context=_context(),
        environment={"MEDIA_SYNC_STATE_DIR": str(state)},
    )

    assert capture.attach(_process(b"", ("\n".join([*unsafe, prefix + "browser navigation failed"]) + "\n").encode()))
    capture.close()

    reader = LogStore(state / "logs")
    try:
        events = reader.query(limit=200)["events"]
    finally:
        reader.close()
    serialized = json.dumps(events)
    raw_segments = b"".join(path.read_bytes() for path in (state / "logs").iterdir())
    assert any(
        event["event_code"] == "process_output" and event.get("message") == "ERROR browser navigation failed"
        for event in events
    )
    assert any(
        event["event_code"] == "process_output_dropped"
        and event.get("error_type") == "policy_filtered"
        and event.get("count") == 4
        for event in events
    )
    for sentinel in sentinels:
        assert sentinel not in serialized
        assert sentinel.encode() not in raw_segments
    assert "MediaCrawler ERROR (login.py:99)" not in serialized
    assert b"MediaCrawler ERROR (login.py:99)" not in raw_segments


@pytest.mark.parametrize(
    "raw",
    [
        b"ERROR cookies: [{'name':'SESSDATA','value':'cookie-sentinel'}]",
        b"ERROR Set-Cookie: sid=cookie-sentinel",
        b"ERROR Authorization: Bearer cookie-sentinel",
        b"ERROR Authorization Bearer cookie-sentinel",
        b"ERROR SESSDATA=cookie-sentinel",
        b'ERROR storage_state={"cookies":[{"name":"sid","value":"cookie-sentinel"}]}',
        b"ERROR data:image/png;base64,Y29va2llLXNlbnRpbmVs",
        b"ERROR qrcode=Y29va2llLXNlbnRpbmVs",
        b"ERROR eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb29raWUifQ.c2VudGluZWwtc2lnbmF0dXJl",
        b"ERROR profile C:\\Users\\private\\browser-data",
        b"ERROR profile /home/private/browser-data/state.json",
    ],
)
def test_high_risk_envelopes_and_private_paths_are_redacted_whole(raw: bytes) -> None:
    message = sanitize_output_line(raw)
    assert message == "[REDACTED]"
    assert "cookie-sentinel" not in message
    event = validate_event(
        {
            "event_code": "process_output",
            "module": "crawler",
            "level": "error",
            "stream": "upstream",
            "message": message,
        }
    )
    assert event["message"] == "[REDACTED]"


def test_urls_drop_all_query_and_fragment_values() -> None:
    message = sanitize_output_line(
        b"ERROR request failed at https://cdn.invalid/video.mp4?quality=1080&token=sentinel#private"
    )

    assert message == "ERROR request failed at [REDACTED_URL]"
    assert "1080" not in message
    assert "sentinel" not in message
    assert "private" not in message
    assert (
        validate_event(
            {
                "event_code": "process_output",
                "module": "crawler",
                "level": "error",
                "stream": "upstream",
                "message": message,
            }
        )["message"]
        == message
    )


@pytest.mark.parametrize(
    "message",
    [
        "ERROR cookies: [{'name':'SESSDATA','value':'sentinel'}]",
        "ERROR Set-Cookie: sid=sentinel",
        "ERROR Authorization: Bearer sentinel",
        "ERROR Authorization Bearer sentinel",
        "ERROR SESSDATA=sentinel",
        'ERROR storage_state={"cookies":[]}',
        "ERROR data:image/png;base64,c2VudGluZWw=",
        "ERROR eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJzZW50aW5lbCJ9.c2VudGluZWwtc2lnbmF0dXJl",
        "ERROR https://cdn.invalid/video?token=sentinel",
        r"ERROR C:\Users\private\profile",
        "ERROR /home/private/profile/state.json",
        'ERROR {"title":"a work says login error"}',
        'ERROR ["a work says login error"]',
        "ERROR <div>a work says login error</div>",
        "ERROR content=a work says login error",
    ],
)
def test_event_validator_rejects_unredacted_or_content_shaped_messages(message: str) -> None:
    with pytest.raises(EventValidationError):
        validate_event(
            {
                "event_code": "process_output",
                "module": "crawler",
                "level": "error",
                "stream": "upstream",
                "message": message,
            }
        )


def test_capture_filters_keyword_content_and_structured_payloads_with_visible_count() -> None:
    events: list[Mapping[str, object]] = []
    sentinel = "UNSAVED-COOKIE-SENTINEL"
    capture = ProcessOutputCapture(context=_context(), event_sink=events.append)
    process = _process(
        b'{"status":"failed"}\n',
        (
            "a creator caption mentions login error\n"
            'ERROR {"title":"a work says login error"}\n'
            "ERROR <div>a work says login error</div>\n"
            "ERROR content=a work says login error\n"
            f"ERROR Set-Cookie: sid={sentinel}\n"
            "ERROR browser navigation failed\n"
        ).encode(),
    )

    assert capture.attach(process)
    capture.close()

    messages = [event["message"] for event in events if event["event_code"] == "process_output"]
    assert messages == ["[REDACTED]", "ERROR browser navigation failed"]
    filtered = [
        event
        for event in events
        if event["event_code"] == "process_output_dropped" and event["error_type"] == "policy_filtered"
    ]
    assert len(filtered) == 1 and filtered[0]["count"] == 4
    assert sentinel not in json.dumps(events)


def test_decode_oversize_budget_and_sink_loss_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture_module, "_MAX_RAW_LINE_BYTES", 12)
    monkeypatch.setattr(capture_module, "_MAX_CAPTURE_LINES", 1)
    events: list[Mapping[str, object]] = []

    def sink(event: Mapping[str, object]) -> bool:
        if event["event_code"] == "process_output":
            return False
        events.append(event)
        return True

    capture = ProcessOutputCapture(context=_context(), event_sink=sink)
    process = _process(b'{"status":"failed"}\n', b"ERROR first\n\xff\n0123456789abcdef\nERROR two\n")
    assert capture.attach(process)
    capture.close()

    losses = {
        str(event["error_type"]): int(event["count"])
        for event in events
        if event["event_code"] == "process_output_dropped" and event["stream"] == "upstream"
    }
    assert losses == {
        "invalid_encoding": 1,
        "line_too_large": 1,
        "capture_budget_exhausted": 1,
        "log_sink_rejected": 1,
    }


def test_docker_state_store_uses_shared_slices_and_never_persists_secret(tmp_path: Path) -> None:
    state = tmp_path / "state"
    environment = {"MEDIA_SYNC_STATE_DIR": str(state)}
    context = _context()
    capture = ProcessOutputCapture(context=context, known_secrets=(SECRET,), environment=environment)
    assert capture.enabled
    process = _process(b'{"status":"failed"}\n', f"ERROR failure token={SECRET}\n".encode())
    assert capture.attach(process)
    capture.close()

    reader = LogStore(state / "logs")
    try:
        events = reader.query(job_id=str(context["job_id"]))["events"]
        assert any(event["event_code"] == "process_output" for event in events)
        summaries = [event for event in events if event["event_code"] == "process_output_summary"]
        assert {event["stream"] for event in summaries} == {"stdout_protocol", "upstream"}
        assert SECRET not in json.dumps(events)
        assert SECRET.encode() not in b"".join(path.read_bytes() for path in (state / "logs").iterdir())
    finally:
        reader.close()


def test_owned_store_flushes_only_after_summary_events_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[Mapping[str, object]] = []
    calls: list[str] = []

    class Store:
        def emit(self, event: Mapping[str, object]) -> bool:
            events.append(dict(event))
            return True

        def flush(self, *, timeout: float) -> bool:
            assert timeout >= 1
            assert {event["stream"] for event in events if event["event_code"] == "process_output_summary"} == {
                "stdout_protocol",
                "upstream",
            }
            calls.append("flush")
            return True

        def close(self) -> None:
            calls.append("close")

    store = Store()
    monkeypatch.setattr(capture_module, "log_store_from_environment", lambda _environment: store)
    capture = ProcessOutputCapture(context=_context(), environment={"MEDIA_SYNC_STATE_DIR": "ignored"})
    assert capture.attach(_process(b'{"status":"failed"}\n', b"ERROR browser failed\n"))

    capture.close()

    assert calls == ["flush", "close"]


def test_environment_store_rejects_relative_root_and_does_not_follow_state_symlink(tmp_path: Path) -> None:
    assert log_store_from_environment({"MEDIA_SYNC_STATE_DIR": "relative/state"}) is None
    assert log_store_from_environment({"MEDIA_SYNC_STATE_DIR": str(Path(tmp_path.anchor))}) is None
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked-state"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not permitted on this host")
    store = log_store_from_environment({"MEDIA_SYNC_STATE_DIR": str(linked)})
    assert store is not None
    assert store.emit({"event_code": "service_started", "module": "crawler", "level": "info"})
    store.close()
    assert list(outside.iterdir()) == []
    assert store.status()["health"] == "unavailable"
    assert store.status()["shutdown_complete"] is True
