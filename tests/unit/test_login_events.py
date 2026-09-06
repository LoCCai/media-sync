from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from media_sync.integrations.mediacrawler import login_events as events

PRIVATE = "PRIVATE-COOKIE-QR https://private.invalid/?token=secret traceback locator=secret"


def _wire(value: dict[str, object]) -> bytes:
    raw = json.dumps(value).encode("ascii")
    return len(raw).to_bytes(4, "big") + raw


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_id", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        ("operation_id", "private"),
        ("phase", PRIVATE),
        ("action", PRIVATE),
        ("error_type", PRIVATE),
        ("source_frame", PRIVATE),
        ("outcome", "authenticated"),
        ("elapsed_ms", True),
        ("elapsed_ms", -1),
        ("elapsed_ms", 3_600_001),
        ("schema_version", True),
        ("event_code", "raw_traceback"),
    ],
)
def test_diagnostic_schema_rejects_extra_identity_and_nonfixed_values(field: str, value: object) -> None:
    candidate = events.event("qr_locate", "wait_selector", "started")
    candidate[field] = value
    with pytest.raises(ValueError, match="invalid login diagnostic"):
        events.parse_event(json.dumps(candidate).encode("ascii"))


@pytest.mark.parametrize("raw", [b"", b"x" * 769, b"[]", b"null", b"\xff", b'{"phase":1,"phase":2}'])
def test_frame_rejects_bad_encoding_duplicates_shapes_and_size(raw: bytes) -> None:
    with pytest.raises(ValueError, match="invalid login diagnostic"):
        events.parse_event(raw)


def test_v1_result_cannot_accept_diagnostic_fields() -> None:
    from media_sync.integrations.mediacrawler.login_runner import _parse_child_frame

    with pytest.raises(ValueError):
        _parse_child_frame(b'{"schema_version":1,"status":"authenticated","phase":"session_probe"}')


@pytest.mark.parametrize("tail", [b"\x00", b"\0\0\3\xff", b"\0\0\0\x08bad", b"\0\0\0\0"])
def test_reader_preserves_valid_event_before_truncated_or_invalid_tail(tail: bytes) -> None:
    first = events.event("platform_navigation", "navigate", "started", source_frame="page")
    observed: list[Any] = []
    reader = events.EventReader(io.BytesIO(_wire(first) + tail))
    reader.start()
    reader.close(observed.append)
    assert observed[0] == first
    assert observed[-1]["event_code"] == "login_diagnostics_degraded"
    assert reader.degraded


def test_reader_keeps_draining_after_invalid_json_without_forwarding_raw_text() -> None:
    raw = PRIVATE.encode("ascii")
    valid = events.event("qr_relay", "relay_write", "succeeded")
    observed: list[Any] = []
    reader = events.EventReader(io.BytesIO(len(raw).to_bytes(4, "big") + raw + _wire(valid)))
    reader.start()
    reader.close(observed.append)
    assert observed[0] == valid
    assert PRIVATE not in repr(observed)
    assert reader.degraded


def test_reader_flood_is_bounded_and_marks_loss() -> None:
    value = events.event("session_probe", "probe", "started")
    observed: list[Any] = []
    reader = events.EventReader(io.BytesIO(_wire(value) * (events.MAX_EVENTS + 100)))
    reader.start()
    reader.close(observed.append)
    assert len(observed) <= events.MAX_PENDING_EVENTS + 1
    assert observed[-1]["event_code"] == "login_diagnostics_degraded"


def test_writer_reader_pipe_roundtrip_does_not_inherit_private_descriptor() -> None:
    read_fd, write_fd = os.pipe()
    reader = events.EventReader(os.fdopen(read_fd, "rb"))
    writer = events.EventWriter(write_fd)
    observed: list[Any] = []
    try:
        assert not os.get_inheritable(write_fd)
        reader.start()
        writer.emit(events.event("qr_relay", "relay_write", "succeeded"))
        writer.close()
        reader.close(observed.append)
    finally:
        writer.close()
    assert len(observed) == 1
    assert observed[0]["phase"] == "qr_relay"


def test_writer_is_bounded_when_parent_does_not_drain() -> None:
    read_fd, write_fd = os.pipe()
    writer = events.EventWriter(write_fd)
    began = time.monotonic()
    try:
        for _ in range(20_000):
            writer.emit(events.event("qr_locate", "wait_selector", "started"))
        writer.close()
        assert time.monotonic() - began < 4
        assert writer._queue.qsize() <= events.MAX_PENDING_EVENTS
    finally:
        os.close(read_fd)


class BrowserTimeout(Exception):
    pass


@pytest.fixture
def shapes(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    class Page:
        fail = ""

        def __init__(self) -> None:
            self.calls: list[str] = []

        async def goto(self, *args: Any, **kwargs: Any) -> None:
            self.calls.append("goto")
            if self.fail == "goto":
                raise BrowserTimeout(PRIVATE)

        async def wait_for_selector(self, *args: Any, **kwargs: Any) -> None:
            self.calls.append("wait_for_selector")
            if self.fail == "wait_for_selector":
                raise BrowserTimeout(PRIVATE)

        async def click(self, *args: Any, **kwargs: Any) -> None:
            self.calls.append("click")
            if self.fail == "click":
                raise BrowserTimeout(PRIVATE)

    class Login:
        async def popup_login_dialog(self) -> None:
            try:
                await page.wait_for_selector(PRIVATE)
            except BrowserTimeout:
                await page.click(PRIVATE)

        async def check_login_state(self) -> bool:
            return True

    class HttpClient:
        calls = 0

        async def get(self, *args: Any, **kwargs: Any) -> None:
            self.calls += 1
            raise TimeoutError(PRIVATE)

    async def find_qr(*args: Any, **kwargs: Any) -> str:
        try:
            await page.wait_for_selector(PRIVATE)
            await HttpClient().get(PRIVATE)
        except Exception:
            return ""
        return "unused"

    page = Page()
    utils = SimpleNamespace(find_login_qrcode=find_qr)
    api = SimpleNamespace(Page=Page, TimeoutError=BrowserTimeout)
    original_import = events.importlib.import_module

    def import_module(name: str) -> Any:
        if name == "playwright.async_api":
            return api
        if name == "httpx":
            return SimpleNamespace(AsyncClient=HttpClient)
        return original_import(name)

    monkeypatch.setattr(events.importlib, "import_module", import_module)
    return SimpleNamespace(page=page, Page=Page, Login=Login, HttpClient=HttpClient, utils=utils)


@pytest.mark.parametrize("action,expected_phase", [("goto", "platform_navigation"), ("click", "upstream_execution")])
async def test_actual_browser_timeout_captured_before_propagation_with_no_argument_leak(
    shapes: Any,
    action: str,
    expected_phase: str,
) -> None:
    recorded: list[Any] = []
    observer = events.LoginObserver(recorded.append)
    original = getattr(shapes.Page, action)
    shapes.page.fail = action
    with events.instrument_login(observer, SimpleNamespace(), shapes.Login, shapes.utils):
        with pytest.raises(BrowserTimeout) as caught:
            await getattr(shapes.page, action)(PRIVATE, timeout=10)
        observer.terminal(caught.value)
    assert getattr(shapes.Page, action) is original
    terminal = recorded[-1]
    assert terminal["event_code"] == "login_terminal"
    assert terminal["error_type"] == "playwright_timeout"
    assert terminal["source_frame"] == "page"
    assert terminal["phase"] == expected_phase
    assert PRIVATE not in repr(recorded)
    assert shapes.page.calls == [action]


async def test_handled_dialog_timeout_then_click_success_is_not_terminal(shapes: Any) -> None:
    recorded: list[Any] = []
    observer = events.LoginObserver(recorded.append)
    shapes.page.fail = "wait_for_selector"
    with events.instrument_login(observer, SimpleNamespace(), shapes.Login, shapes.utils):
        await shapes.Login().popup_login_dialog()
    assert any(value["action"] == "wait_selector" and value["error_type"] == "playwright_timeout" for value in recorded)
    assert recorded[-1]["phase"] == "login_dialog"
    assert recorded[-1]["outcome"] == "succeeded"
    assert all(value["event_code"] == "login_stage" for value in recorded)
    assert shapes.page.calls == ["wait_for_selector", "click"]


@pytest.mark.parametrize("failed_action", ["wait_for_selector", "httpx_get"])
async def test_qr_helper_swallowed_error_retains_safe_inner_action_without_inventing_terminal(
    shapes: Any,
    failed_action: str,
) -> None:
    recorded: list[Any] = []
    observer = events.LoginObserver(recorded.append)
    shapes.page.fail = failed_action
    with events.instrument_login(observer, SimpleNamespace(), shapes.Login, shapes.utils):
        assert await shapes.utils.find_login_qrcode(shapes.page, PRIVATE) == ""
        observer.terminal(SystemExit(0))
    failures = [value for value in recorded if value["outcome"] == "failed"]
    assert failures[0]["phase"] == ("qr_locate" if failed_action == "wait_for_selector" else "qr_image_fetch")
    assert failures[0]["error_type"] == ("playwright_timeout" if failed_action == "wait_for_selector" else "timeout")
    assert failures[-1]["event_code"] == "login_terminal"
    assert failures[-1]["phase"] == "upstream_execution"
    assert failures[-1]["error_type"] == "system_exit"
    assert PRIVATE not in repr(recorded)


@pytest.mark.parametrize("relayed", [True, False])
async def test_waiting_scan_requires_observed_qr_relay(shapes: Any, relayed: bool) -> None:
    recorded: list[Any] = []
    observer = events.LoginObserver(recorded.append)
    if relayed:
        observer.qr_relayed.set()
    with events.instrument_login(observer, SimpleNamespace(), shapes.Login, shapes.utils):
        assert await shapes.Login().check_login_state()
    assert recorded[0]["phase"] == ("waiting_scan" if relayed else "login_confirmation")


def test_cleanup_failure_never_replaces_primary_terminal_and_sink_failure_is_ignored() -> None:
    recorded: list[Any] = []
    observer = events.LoginObserver(recorded.append)
    primary = TimeoutError(PRIVATE)
    with pytest.raises(TimeoutError), observer.span("platform_navigation", "navigate", "page"):
        raise primary
    observer.terminal(primary)
    with pytest.raises(OSError), observer.span("cleanup", "cleanup", "cleanup"):
        raise OSError(PRIVATE)
    terminal = [value for value in recorded if value["event_code"] == "login_terminal"]
    assert len(terminal) == 1
    assert terminal[0]["phase"] == "platform_navigation"
    assert recorded[-1]["phase"] == "cleanup"

    def broken(_value: Any) -> None:
        raise OSError(PRIVATE)

    with events.LoginObserver(broken).span("session_probe", "probe", "client"):
        pass


def test_cancellation_observation_preserves_exact_exception() -> None:
    recorded: list[Any] = []
    observer = events.LoginObserver(recorded.append)
    cancellation = asyncio.CancelledError(PRIVATE)
    with pytest.raises(asyncio.CancelledError) as caught, observer.span("qr_locate", "wait_selector", "page"):
        raise cancellation
    assert caught.value is cancellation
    assert recorded[-1]["outcome"] == "cancelled"
    assert recorded[-1]["error_type"] == "cancelled"
    assert PRIVATE not in repr(recorded)


@pytest.mark.parametrize("source", ["page", "browser_context"])
async def test_navigation_context_timeout_is_observed_before_upstream_fallback(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> None:
    class Browser:
        calls = 0

        @contextlib.asynccontextmanager
        async def waiting(self, *args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            yield object()
            raise BrowserTimeout(PRIVATE)

        expect_navigation = waiting
        expect_page = waiting

    api = SimpleNamespace(Page=Browser, BrowserContext=Browser, TimeoutError=BrowserTimeout)
    original_import = events.importlib.import_module
    monkeypatch.setattr(
        events.importlib, "import_module", lambda name: api if name == "playwright.async_api" else original_import(name)
    )
    recorded: list[Any] = []
    observer = events.LoginObserver(recorded.append)
    browser = Browser()
    with events.instrument_login(observer, SimpleNamespace(), SimpleNamespace(), SimpleNamespace()):
        try:
            async with getattr(browser, "expect_navigation" if source == "page" else "expect_page")(PRIVATE):
                pass
        except BrowserTimeout:
            pass
    assert browser.calls == 1
    assert recorded[-1]["phase"] == "platform_navigation"
    assert recorded[-1]["action"] == "wait_load"
    assert recorded[-1]["error_type"] == "playwright_timeout"
    assert recorded[-1]["source_frame"] == source
    assert not any(value["event_code"] == "login_terminal" for value in recorded)
    assert PRIVATE not in repr(recorded)


@pytest.mark.parametrize("mode", ["good", "invalid_image", "write_error"])
def test_qr_relay_observes_success_only_after_atomic_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
) -> None:
    from media_sync.integrations.mediacrawler import login_runner

    utils = SimpleNamespace(__file__=str(tmp_path / "utils.py"), show_qrcode=lambda _value: None)
    original_import = events.importlib.import_module
    monkeypatch.setattr(
        events.importlib, "import_module", lambda name: utils if name == "tools.utils" else original_import(name)
    )
    monkeypatch.setattr(
        login_runner, "_normalize_qr_image", lambda _value: None if mode == "invalid_image" else b"fixed-image"
    )
    if mode == "write_error":

        def fail_replace(*_args: Any) -> None:
            raise OSError(PRIVATE)

        monkeypatch.setattr(login_runner.os, "replace", fail_replace)
    recorded: list[Any] = []
    observer = events.LoginObserver(recorded.append)
    destination = tmp_path / "qr.png"
    with login_runner._disable_qr_export(tmp_path, destination, observer):
        utils.show_qrcode(PRIVATE)
    assert observer.qr_relayed.is_set() is (mode == "good")
    assert destination.exists() is (mode == "good")
    assert recorded[-1]["phase"] == "qr_relay"
    assert recorded[-1]["outcome"] == ("succeeded" if mode == "good" else "failed")
    assert PRIVATE not in repr(recorded)
