"""Real isolated child/process-tree coverage for the diagnostic side channel."""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler.login import MediaCrawlerLoginMode, MediaCrawlerLoginStatus
from tests.contract.test_mediacrawler_login import (
    _request,
    _runner,
    _wait_for_json,
    _wait_for_pids_to_exit,
    _write_fake_checkout,
)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("success", MediaCrawlerLoginStatus.AUTHENTICATED),
        ("browser_failure", MediaCrawlerLoginStatus.BROWSER_LAUNCH_FAILED),
        ("browser_timeout", MediaCrawlerLoginStatus.UPSTREAM_BROWSER_TIMEOUT),
        ("system_exit_private", MediaCrawlerLoginStatus.UPSTREAM_LOGIN_EXITED),
        ("post_update_false", MediaCrawlerLoginStatus.LOGIN_CONFIRMATION_FAILED),
    ],
)
def test_real_child_v1_result_and_identity_free_safe_side_channel(
    tmp_path: Path,
    mode: str,
    expected: MediaCrawlerLoginStatus,
) -> None:
    checkout = _write_fake_checkout(tmp_path / "checkout")
    (checkout / "mode.txt").write_text(mode, encoding="utf-8")
    observed: list[Any] = []
    result = _runner(checkout, tmp_path / "runtime").run(
        _request(Platform.BILI, MediaCrawlerLoginMode.INTERACTIVE_QR),
        diagnostic_hook=observed.append,
    )
    assert result.status is expected
    assert observed
    assert all(
        "account_id" not in value and "login_session_id" not in value and "operation_id" not in value
        for value in observed
    )
    text = repr(observed)
    assert "PRIVATE" not in text and "secret" not in text and "https://" not in text
    assert any(value["phase"] == "session_probe" for value in observed) or mode == "browser_failure"
    terminals = [value for value in observed if value["event_code"] == "login_terminal"]
    if mode == "success":
        assert not terminals
    else:
        assert len(terminals) == 1
    if mode == "post_update_false":
        assert terminals[0]["phase"] == "login_confirmation"
        assert terminals[0]["error_type"] == "confirmation_rejected"
    if mode == "browser_failure":
        assert terminals[0]["phase"] == "browser_launch"
        assert terminals[0]["error_type"] == "browser_launch_failed"
    assert observed[-1]["phase"] == "cleanup"


@pytest.mark.parametrize("cancel", [True, False])
def test_parent_receives_live_events_before_deadline_or_cancel_and_joins_tree(tmp_path: Path, cancel: bool) -> None:
    checkout = _write_fake_checkout(tmp_path / "checkout")
    (checkout / "mode.txt").write_text("hang", encoding="utf-8")
    observed: list[Any] = []
    active = threading.Event()
    cancellation = threading.Event()
    parent_thread: list[int] = []

    def observe(value: Mapping[str, object]) -> None:
        observed.append(dict(value))
        parent_thread.append(threading.get_ident())
        if (
            value["phase"] == "upstream_execution"
            and value["source_frame"] == "login"
            and value["outcome"] == "started"
        ):
            active.set()

    def run() -> Any:
        return _runner(checkout, tmp_path / "runtime").run(
            _request(Platform.BILI, MediaCrawlerLoginMode.INTERACTIVE_QR, timeout_seconds=3),
            diagnostic_hook=observe,
            cancellation=cancellation,
        )

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run)
        assert active.wait(2)
        assert not future.done()
        pids = _wait_for_json(checkout / "pids.json")
        if cancel:
            cancellation.set()
        result = future.result(timeout=15)
    assert result.status is (MediaCrawlerLoginStatus.CANCELLED if cancel else MediaCrawlerLoginStatus.TIMED_OUT)
    assert time.monotonic() - started < 15
    assert len(set(parent_thread)) == 1
    assert observed[-1]["event_code"] == "login_terminal"
    assert observed[-1]["error_type"] == ("cancelled" if cancel else "timeout")
    _wait_for_pids_to_exit(pids["child"], pids["grandchild"])
    assert not any(thread.name == "media-sync-login-events-read" for thread in threading.enumerate())


def test_broken_diagnostic_sink_does_not_change_authentication(tmp_path: Path) -> None:
    checkout = _write_fake_checkout(tmp_path / "checkout")

    def failed_sink(_value: Mapping[str, object]) -> None:
        raise OSError("PRIVATE-SINK-FAILURE")

    result = _runner(checkout, tmp_path / "runtime").run(
        _request(Platform.BILI, MediaCrawlerLoginMode.INTERACTIVE_QR),
        diagnostic_hook=failed_sink,
    )
    assert result.authenticated
