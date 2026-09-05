from __future__ import annotations

import asyncio
import io
import json
import threading
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import login_runner
from media_sync.integrations.mediacrawler.browser_policy import BrowserLaunchFailure, install_bundled_chromium_policy
from media_sync.integrations.mediacrawler.login import (
    MediaCrawlerLoginMode,
    MediaCrawlerLoginRequest,
    MediaCrawlerLoginStatus,
)

_PRIVATE = "synthetic-private-browser-message-837126"
_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _main_for(crawler: Any) -> Any:
    class Factory:
        @staticmethod
        def create_crawler(platform: str) -> Any:
            assert platform == "xhs"
            return crawler

    return SimpleNamespace(CrawlerFactory=Factory)


def _wrap(crawler: Any, enabled: bool) -> Any:
    main = _main_for(crawler)
    install_bundled_chromium_policy(main, classify_launch_errors=enabled)
    assert main.CrawlerFactory.create_crawler("xhs") is crawler
    return main


@pytest.mark.parametrize("method", ["launch", "launch_persistent_context"])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize(
    "error_type", [RuntimeError, TimeoutError, asyncio.CancelledError, SystemExit, KeyboardInterrupt]
)
async def test_launch_boundary_classifies_only_opted_in_exceptions(
    method: str, enabled: bool, error_type: type[BaseException]
) -> None:
    error = error_type(_PRIVATE)

    async def fail(**_kwargs: Any) -> Any:
        raise error

    class Crawler:
        async def launch_browser(self, chromium: Any) -> Any:
            return await getattr(chromium, method)(channel="chrome")

    crawler = Crawler()
    _wrap(crawler, enabled)
    chromium = SimpleNamespace(executable_path="/synthetic/chromium", **{method: fail})
    expected_type = BrowserLaunchFailure if enabled and isinstance(error, Exception) else error_type
    with pytest.raises(expected_type) as caught:
        await crawler.launch_browser(chromium)
    if expected_type is BrowserLaunchFailure:
        assert str(caught.value) == "MediaCrawler browser launch failed"
        assert _PRIVATE not in repr(caught.value)
        assert _PRIVATE not in "".join(traceback.format_exception(caught.value))
        assert caught.value.__cause__ is None
        assert caught.value.__suppress_context__ is True
    else:
        assert caught.value is error


@pytest.mark.parametrize("phase", ["executable", "method_lookup", "new_context", "page", "client", "upstream_launcher"])
async def test_other_phases_preserve_original_error_instead_of_guessing_launch_failure(phase: str) -> None:
    error = RuntimeError(_PRIVATE)

    async def fail() -> None:
        raise error

    class Chromium:
        @property
        def executable_path(self) -> str:
            if phase == "executable":
                raise error
            return "/synthetic/chromium"

        @property
        def launch(self) -> Any:
            if phase == "method_lookup":
                raise error

            async def launch(**_kwargs: Any) -> Any:
                return SimpleNamespace(new_context=fail)

            return launch

    class Crawler:
        async def launch_browser(self, chromium: Any) -> None:
            if phase == "upstream_launcher":
                raise error
            browser = await chromium.launch()
            if phase == "new_context":
                await browser.new_context()
            if phase in {"page", "client"}:
                await fail()

    crawler = Crawler()
    _wrap(crawler, True)
    with pytest.raises(RuntimeError) as caught:
        await crawler.launch_browser(Chromium())
    assert caught.value is error


@pytest.mark.parametrize("mode", [False, True])
def test_policy_modes_are_idempotent_but_conflicting_factory_or_instance_modes_fail(mode: bool) -> None:
    class Crawler:
        async def launch_browser(self, chromium: Any) -> None:
            pass

    crawler = Crawler()
    main = _wrap(crawler, mode)
    original_factory = main.CrawlerFactory.create_crawler
    original_launcher = crawler.launch_browser
    install_bundled_chromium_policy(main, classify_launch_errors=mode)
    main.CrawlerFactory.create_crawler("xhs")
    assert main.CrawlerFactory.create_crawler is original_factory
    assert crawler.launch_browser is original_launcher
    with pytest.raises(RuntimeError, match=r"^MediaCrawler bundled browser policy is unavailable$"):
        install_bundled_chromium_policy(main, classify_launch_errors=not mode)
    alternate = _main_for(crawler)
    install_bundled_chromium_policy(alternate, classify_launch_errors=not mode)
    with pytest.raises(RuntimeError, match=r"^MediaCrawler bundled browser policy is unavailable$"):
        alternate.CrawlerFactory.create_crawler("xhs")
    assert crawler.launch_browser is original_launcher


@pytest.mark.parametrize("mode", [None, 0, 1, "true", {}])
def test_policy_mode_rejects_non_boolean_values(mode: Any) -> None:
    with pytest.raises(RuntimeError, match=r"^MediaCrawler bundled browser policy is unavailable$"):
        install_bundled_chromium_policy(SimpleNamespace(), classify_launch_errors=mode)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (BrowserLaunchFailure(), MediaCrawlerLoginStatus.BROWSER_LAUNCH_FAILED),
        (RuntimeError(_PRIVATE), MediaCrawlerLoginStatus.FAILED),
        (SystemExit(0), MediaCrawlerLoginStatus.FAILED),
        (SystemExit(1), MediaCrawlerLoginStatus.FAILED),
        (asyncio.CancelledError(), MediaCrawlerLoginStatus.FAILED),
        (login_runner._ChildConfigurationError(), MediaCrawlerLoginStatus.CONFIGURATION_INVALID),
    ],
)
async def test_controlled_child_preserves_existing_error_meanings(
    monkeypatch: pytest.MonkeyPatch, error: BaseException, expected: MediaCrawlerLoginStatus
) -> None:
    async def fail(_request: Any) -> Any:
        raise error

    monkeypatch.setattr(login_runner, "_run_upstream", fail)
    assert await login_runner._execute_controlled_child(None, None) is expected


@pytest.mark.parametrize("status", [MediaCrawlerLoginStatus.AUTHENTICATED, MediaCrawlerLoginStatus.EXPIRED])
async def test_controlled_child_preserves_success_and_saved_session_expiry(
    monkeypatch: pytest.MonkeyPatch, status: MediaCrawlerLoginStatus
) -> None:
    async def succeed(_request: Any) -> MediaCrawlerLoginStatus:
        return status

    monkeypatch.setattr(login_runner, "_run_upstream", succeed)
    assert await login_runner._execute_controlled_child(None, None) is status


def _request() -> MediaCrawlerLoginRequest:
    return MediaCrawlerLoginRequest(_ID, Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR, timeout_seconds=1)


@pytest.mark.parametrize(
    ("disposition", "tree_closed", "expected"),
    [
        ("frame", True, MediaCrawlerLoginStatus.BROWSER_LAUNCH_FAILED),
        ("frame", False, MediaCrawlerLoginStatus.RESULT_INVALID),
        ("cancel", True, MediaCrawlerLoginStatus.CANCELLED),
        ("cancel", False, MediaCrawlerLoginStatus.RESULT_INVALID),
        ("timeout", True, MediaCrawlerLoginStatus.TIMED_OUT),
        ("timeout", False, MediaCrawlerLoginStatus.RESULT_INVALID),
        ("start", True, MediaCrawlerLoginStatus.START_FAILED),
    ],
)
def test_parent_fences_take_priority_over_complete_browser_failure_frame(
    monkeypatch: pytest.MonkeyPatch, disposition: str, tree_closed: bool, expected: MediaCrawlerLoginStatus
) -> None:
    frame = b'{"schema_version":1,"status":"browser_launch_failed"}'
    process = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(len(frame).to_bytes(4, "big") + frame), pid=0)
    cancellation = threading.Event()

    class Reader:
        def __init__(self, *, target: Any, **_kwargs: Any) -> None:
            self.target = target

        def start(self) -> None:
            if disposition != "timeout":
                self.target()
            if disposition == "cancel":
                cancellation.set()

        def join(self, *, timeout: float) -> None:
            if disposition == "timeout":
                self.target()

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(login_runner, "_spawn_login_child", lambda *_args: process)
    monkeypatch.setattr(login_runner._WindowsJob, "attach", lambda _process: object())
    monkeypatch.setattr(login_runner, "_write_login_start", lambda *_args: disposition != "start")
    monkeypatch.setattr(login_runner, "_stop_child", lambda *_args: None)
    monkeypatch.setattr(login_runner, "_close_control", lambda *_args: None)
    monkeypatch.setattr(login_runner, "_close_process_tree", lambda *_args: tree_closed)
    monkeypatch.setattr(login_runner.threading, "Thread", Reader)
    if disposition == "timeout":
        ticks = iter([0, 2])
        monkeypatch.setattr(login_runner.time, "monotonic", lambda: next(ticks))
    result = login_runner.MediaCrawlerLoginProcessRunner._execute(
        Path("unused"), Path("unused"), b"{}", _request(), -1, cancellation, _SHA
    )
    assert result.status is expected


@pytest.mark.parametrize(
    "status", ["authenticated", "expired", "failed", "cancelled", "configuration_invalid", "browser_launch_failed"]
)
def test_v1_frame_accepts_old_and_new_closed_statuses(status: str) -> None:
    frame = json.dumps({"schema_version": 1, "status": status}).encode("ascii")
    assert login_runner._parse_child_frame(frame).value == status


@pytest.mark.parametrize(
    "frame",
    [
        b'{"schema_version":true,"status":"failed"}',
        b'{"schema_version":1.0,"status":"failed"}',
        b'{"schema_version":1,"status":"browser_launch_failed","reason":"private"}',
        b'{"schema_version":1,"status":"browser_launch_failed","status":"authenticated"}',
        b'{"schema_version":1,"schema_version":1,"status":"failed"}',
        b'{"schema_version":1,"status":"unknown"}',
        b'{"schema_version":1,"status":"timed_out"}',
        b'{"schema_version":1,"status":"start_failed"}',
        b'{"schema_version":1,"status":"result_invalid"}',
        b'{"schema_version":1,"status":"account_busy"}',
    ],
)
def test_v1_frame_stays_closed_to_unknown_extra_and_parent_only_states(frame: bytes) -> None:
    with pytest.raises(ValueError):
        login_runner._parse_child_frame(frame)


@pytest.mark.parametrize("version", [True, False, 1.0, "1", None])
def test_child_request_version_rejects_boolean_and_non_integer_aliases(version: Any) -> None:
    payload = {
        "schema_version": version,
        "checkout_root": str(Path.cwd()),
        "integration_root": str(Path.cwd() / "unused"),
        "account_id": str(_ID),
        "execution_id": str(_ID),
        "platform": "xhs",
        "mode": "interactive_qr",
    }
    with pytest.raises(login_runner._ChildConfigurationError):
        login_runner._ChildRequest.load(json.dumps(payload).encode("ascii"))
