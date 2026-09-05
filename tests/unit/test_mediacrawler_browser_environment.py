"""Browser lookup must survive isolation without forwarding parent secrets."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import bridge, detail_runner, login_runner
from media_sync.integrations.mediacrawler.browser_environment import browser_child_environment
from media_sync.integrations.mediacrawler.login import (
    MediaCrawlerLoginMode,
    MediaCrawlerLoginRequest,
    MediaCrawlerLoginStatus,
)
from media_sync.integrations.mediacrawler.policies import PRIVATE_INPUT_ENV, WatchdogLimits
from media_sync.media.errors import MediaDownloadError

_APPROVED = {
    "PLAYWRIGHT_BROWSERS_PATH": "/synthetic/shared-browser-cache",
    "HOME": "/synthetic/home",
    "DISPLAY": ":99",
    "XAUTHORITY": "/synthetic/display-authority",
    "HOMEDRIVE": "C:",
    "HOMEPATH": "\\synthetic",
    "PATH": "/synthetic/bin",
}
_UNAPPROVED = {
    "MEDIA_SYNC_OPERATOR_CREDENTIAL": "synthetic-operator-secret",
    "MEDIA_SYNC_OPERATOR_API_TOKEN": "synthetic-api-secret",
    "HTTP_PROXY": "http://user:synthetic-secret@proxy.invalid",
    "HTTPS_PROXY": "http://user:synthetic-secret@proxy.invalid",
    "ALL_PROXY": "http://user:synthetic-secret@proxy.invalid",
    "PYTHONPATH": "/synthetic/untrusted-imports",
    "PYTHONHOME": "/synthetic/untrusted-runtime",
    "NODE_OPTIONS": "--synthetic-untrusted-option",
    "PLAYWRIGHT_DOWNLOAD_HOST": "https://synthetic-secret@mirror.invalid",
    "PLAYWRIGHT_NODEJS_PATH": "/synthetic/untrusted-node",
    "DEBUG": "pw:api",
    "MEDIA_SYNC_LOGIN_CONTROL": "synthetic-parent-control",
    PRIVATE_INPUT_ENV: "synthetic-parent-private-input",
}


def _assert_browser_settings(environment: dict[str, str]) -> None:
    for name, value in _APPROVED.items():
        assert environment.get(name) == value
    for name, value in _UNAPPROVED.items():
        assert environment.get(name) != value


def test_browser_environment_is_fresh_and_secret_denying() -> None:
    with patch.dict(os.environ, {**_APPROVED, **_UNAPPROVED}, clear=True):
        actual = browser_child_environment()
        assert actual == _APPROVED
        actual["PLAYWRIGHT_BROWSERS_PATH"] = "changed-in-child"
        assert browser_child_environment() == _APPROVED
        assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == _APPROVED["PLAYWRIGHT_BROWSERS_PATH"]


@pytest.mark.parametrize("platform", list(Platform))
def test_real_login_spawn_preserves_cache_without_parent_secrets(platform: Platform) -> None:
    captured: dict[str, str] = {}

    def intercept(command: object, cwd: object, environment: dict[str, str], descriptor: object) -> None:
        captured.update(environment)
        raise OSError("synthetic spawn interception; no child launched")

    request = MediaCrawlerLoginRequest(UUID(int=1), platform, MediaCrawlerLoginMode.INTERACTIVE_QR)
    with (
        patch.dict(os.environ, {**_APPROVED, **_UNAPPROVED}, clear=True),
        patch.object(login_runner, "_spawn_login_child", side_effect=intercept) as spawn,
    ):
        result = login_runner.MediaCrawlerLoginProcessRunner._execute(
            Path("synthetic-python"), Path("synthetic-checkout"), b"{}", request, -1, None, "0" * 40
        )
    assert spawn.call_count == 1
    assert result.status is MediaCrawlerLoginStatus.START_FAILED
    _assert_browser_settings(captured)


def test_creator_process_spec_preserves_cache_and_replaces_parent_private_input() -> None:
    with patch.dict(os.environ, {**_APPROVED, **_UNAPPROVED}, clear=True):
        actual, known_secrets = bridge._child_environment("synthetic-author", None)
    _assert_browser_settings(dict(actual))
    assert "synthetic-author" in actual[PRIVATE_INPUT_ENV]
    assert known_secrets == ()


def test_real_detail_spawn_preserves_cache_without_parent_secrets() -> None:
    captured: dict[str, str] = {}

    def intercept(*args: object, **kwargs: object) -> None:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        captured.update(environment)
        raise OSError("synthetic spawn interception; no child launched")

    with (
        patch.dict(os.environ, {**_APPROVED, **_UNAPPROVED}, clear=True),
        patch.object(detail_runner.subprocess, "Popen", side_effect=intercept) as spawn,
        pytest.raises(MediaDownloadError, match="locator_refresh_temporary"),
    ):
        detail_runner.MediaCrawlerDetailProcessRunner._execute(
            Path("synthetic-python"), Path("synthetic-checkout"), b"{}", WatchdogLimits()
        )
    assert spawn.call_count == 1
    _assert_browser_settings(captured)
