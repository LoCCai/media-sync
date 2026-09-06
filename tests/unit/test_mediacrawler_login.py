from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import login_runner as runner_module
from media_sync.integrations.mediacrawler.login import (
    MediaCrawlerLoginMode,
    MediaCrawlerLoginRequest,
    MediaCrawlerLoginResult,
    MediaCrawlerLoginStatus,
)

ACCOUNT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"


def test_login_request_is_closed_and_normalized() -> None:
    request = MediaCrawlerLoginRequest(
        account_id=ACCOUNT_ID,
        platform="xhs",  # type: ignore[arg-type]
        mode="interactive_qr",  # type: ignore[arg-type]
        timeout_seconds=120,
        poll_seconds=1,
    )

    assert request.platform is Platform.XHS
    assert request.mode is MediaCrawlerLoginMode.INTERACTIVE_QR
    assert request.timeout_seconds == 120.0
    assert request.poll_seconds == 1.0


@pytest.mark.parametrize(
    ("timeout", "poll"),
    [(True, 0.1), (0, 0.1), (float("inf"), 0.1), (10, True), (10, 0), (10, 10)],
)
def test_login_request_rejects_invalid_watchdogs(timeout: object, poll: object) -> None:
    with pytest.raises(ValueError):
        MediaCrawlerLoginRequest(
            account_id=ACCOUNT_ID,
            platform=Platform.XHS,
            mode=MediaCrawlerLoginMode.INTERACTIVE_QR,
            timeout_seconds=timeout,  # type: ignore[arg-type]
            poll_seconds=poll,  # type: ignore[arg-type]
        )


def test_login_result_requires_sha_only_for_authentication() -> None:
    result = MediaCrawlerLoginResult(MediaCrawlerLoginStatus.AUTHENTICATED, UPSTREAM_SHA.upper())

    assert result.authenticated
    assert result.upstream_sha == UPSTREAM_SHA
    assert not MediaCrawlerLoginResult(MediaCrawlerLoginStatus.EXPIRED).authenticated
    with pytest.raises(ValueError):
        MediaCrawlerLoginResult(MediaCrawlerLoginStatus.AUTHENTICATED)


def test_child_frame_is_exact_and_rejects_duplicate_or_trailing_frames() -> None:
    valid = json.dumps(
        {"schema_version": runner_module.LOGIN_RUNNER_SCHEMA_VERSION, "status": "authenticated"},
        separators=(",", ":"),
    ).encode("ascii")

    assert runner_module._parse_child_frame(valid) is MediaCrawlerLoginStatus.AUTHENTICATED
    duplicate = b'{"schema_version":1,"status":"failed","status":"authenticated"}'
    with pytest.raises(ValueError):
        runner_module._parse_child_frame(duplicate)
    with pytest.raises(ValueError):
        runner_module._parse_child_frame(valid + valid)
    with pytest.raises(ValueError):
        runner_module._parse_child_frame(b"x" * (runner_module.MAX_LOGIN_RESULT_BYTES + 1))


@pytest.mark.parametrize("exit_code", [0, 1, "PRIVATE-UPSTREAM-EXIT"])
def test_system_exit_is_an_explicit_non_success_child_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    exit_code: object,
) -> None:
    async def exit_zero(_request: object) -> MediaCrawlerLoginStatus:
        raise SystemExit(exit_code)

    monkeypatch.setattr(runner_module, "_run_upstream", exit_zero)
    request = runner_module._ChildRequest(
        checkout_root=Path.cwd(),
        paths=runner_module.build_run_paths(Path.cwd() / ".test-login", Platform.XHS, ACCOUNT_ID, ACCOUNT_ID),
        platform=Platform.XHS,
        mode=MediaCrawlerLoginMode.INTERACTIVE_QR,
    )

    result = asyncio.run(runner_module._execute_child(request))
    assert result is MediaCrawlerLoginStatus.UPSTREAM_LOGIN_EXITED
    captured = capsys.readouterr()
    assert "PRIVATE-UPSTREAM-EXIT" not in captured.out + captured.err + repr(result)


@pytest.mark.parametrize(
    "status",
    [
        MediaCrawlerLoginStatus.UPSTREAM_LOGIN_EXITED,
        MediaCrawlerLoginStatus.UPSTREAM_BROWSER_TIMEOUT,
        MediaCrawlerLoginStatus.LOGIN_CONFIRMATION_FAILED,
    ],
)
def test_new_child_diagnostics_round_trip_only_as_closed_status(status: MediaCrawlerLoginStatus) -> None:
    frame = json.dumps({"schema_version": 1, "status": status.value}).encode("ascii")
    assert runner_module._parse_child_frame(frame) is status
    assert not MediaCrawlerLoginResult(status, UPSTREAM_SHA).authenticated


@pytest.mark.parametrize("value", ["unknown_timeout", "TimeoutError: PRIVATE-UPSTREAM-ERROR", "network_failure"])
def test_child_frame_rejects_unknown_or_exception_like_status(value: str) -> None:
    frame = json.dumps({"schema_version": 1, "status": value}).encode("ascii")
    with pytest.raises(ValueError):
        runner_module._parse_child_frame(frame)
    with pytest.raises(ValueError):
        MediaCrawlerLoginResult(value)  # type: ignore[arg-type]


class _PlaywrightTimeoutError(Exception):
    pass


class _PlaywrightTimeoutSubclass(_PlaywrightTimeoutError):
    pass


_PRIVATE_ERROR = "PRIVATE-UPSTREAM-ERROR https://private.invalid Cookie=secret TimeoutError"
_SameNameTimeoutError = type("TimeoutError", (Exception,), {})


@pytest.mark.parametrize(
    ("error", "expected", "loads_playwright"),
    [
        (_PlaywrightTimeoutError(_PRIVATE_ERROR), MediaCrawlerLoginStatus.UPSTREAM_BROWSER_TIMEOUT, True),
        (_PlaywrightTimeoutSubclass(_PRIVATE_ERROR), MediaCrawlerLoginStatus.UPSTREAM_BROWSER_TIMEOUT, True),
        (TimeoutError(_PRIVATE_ERROR), MediaCrawlerLoginStatus.FAILED, True),
        (_SameNameTimeoutError(_PRIVATE_ERROR), MediaCrawlerLoginStatus.FAILED, True),
        (RuntimeError(_PRIVATE_ERROR), MediaCrawlerLoginStatus.FAILED, True),
        (runner_module._LoginConfirmationFailed(), MediaCrawlerLoginStatus.LOGIN_CONFIRMATION_FAILED, False),
        (runner_module.BrowserLaunchFailure(), MediaCrawlerLoginStatus.BROWSER_LAUNCH_FAILED, False),
        (runner_module._ChildConfigurationError(), MediaCrawlerLoginStatus.CONFIGURATION_INVALID, False),
        (asyncio.CancelledError(_PRIVATE_ERROR), MediaCrawlerLoginStatus.FAILED, False),
    ],
)
def test_child_classifies_by_runtime_type_without_text_or_dependency_on_main_process(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: BaseException,
    expected: MediaCrawlerLoginStatus,
    loads_playwright: bool,
) -> None:
    imported: list[str] = []

    def import_module(name: str) -> SimpleNamespace:
        assert name == "playwright.async_api"
        imported.append(name)
        return SimpleNamespace(TimeoutError=_PlaywrightTimeoutError)

    async def upstream(_request: object) -> MediaCrawlerLoginStatus:
        raise error

    monkeypatch.setattr(runner_module.importlib, "import_module", import_module)
    monkeypatch.setattr(runner_module, "_run_upstream", upstream)
    request = runner_module._ChildRequest(
        checkout_root=Path.cwd(),
        paths=runner_module.build_run_paths(Path.cwd() / ".test-login", Platform.DY, ACCOUNT_ID, ACCOUNT_ID),
        platform=Platform.DY,
        mode=MediaCrawlerLoginMode.INTERACTIVE_QR,
    )
    result = asyncio.run(runner_module._execute_child(request))
    assert result is expected
    assert imported == (["playwright.async_api"] if loads_playwright else [])
    captured = capsys.readouterr()
    assert _PRIVATE_ERROR not in captured.out + captured.err + repr(result)


@pytest.mark.parametrize("error_type", [ImportError, RuntimeError])
def test_unavailable_timeout_type_preserves_unknown_failure(
    monkeypatch: pytest.MonkeyPatch, error_type: type[Exception]
) -> None:
    def import_module(_name: str) -> None:
        raise error_type(_PRIVATE_ERROR)

    monkeypatch.setattr(runner_module.importlib, "import_module", import_module)
    assert not runner_module._is_playwright_timeout(TimeoutError(_PRIVATE_ERROR))


@pytest.mark.parametrize("exported_type", [None, "TimeoutError", BaseException, object, 1])
def test_invalid_timeout_export_does_not_reclassify_unknown_error(
    monkeypatch: pytest.MonkeyPatch, exported_type: object
) -> None:
    monkeypatch.setattr(
        runner_module.importlib,
        "import_module",
        lambda _name: SimpleNamespace(TimeoutError=exported_type),
    )
    assert not runner_module._is_playwright_timeout(TimeoutError(_PRIVATE_ERROR))


@pytest.mark.parametrize("platform", list(Platform))
def test_login_only_configuration_disables_content_and_forces_interaction_shape(
    tmp_path: Path,
    platform: Platform,
) -> None:
    config = type("Config", (), {})()
    paths = runner_module.build_run_paths(tmp_path / "integration", platform, ACCOUNT_ID, ACCOUNT_ID)
    request = runner_module._ChildRequest(
        checkout_root=tmp_path,
        paths=paths,
        platform=platform,
        mode=MediaCrawlerLoginMode.INTERACTIVE_QR,
    )

    runner_module._configure_upstream(config, request)

    assert platform.value == config.PLATFORM
    assert config.LOGIN_TYPE == "qrcode"
    assert config.CRAWLER_TYPE == runner_module.LOGIN_ONLY_CRAWLER_TYPE
    assert config.SAVE_LOGIN_STATE is True
    assert config.HEADLESS is False
    assert config.CDP_HEADLESS is False
    assert config.ENABLE_GET_COMMENTS is False
    assert config.ENABLE_GET_SUB_COMMENTS is False
    assert config.ENABLE_GET_MEIDAS is False
    assert config.ENABLE_GET_MEDIAS is False
    assert config.ENABLE_GET_WORDCLOUD is False
    assert config.CREATOR_MODE is False
    for attribute in (*runner_module.CREATOR_CONFIG_ATTRIBUTES.values(), *runner_module._CONTENT_CONFIG_ATTRIBUTES):
        assert getattr(config, attribute) == []


def test_saved_session_configuration_is_headless(tmp_path: Path) -> None:
    config = type("Config", (), {})()
    paths = runner_module.build_run_paths(tmp_path / "integration", Platform.XHS, ACCOUNT_ID, ACCOUNT_ID)
    request = runner_module._ChildRequest(
        checkout_root=tmp_path,
        paths=paths,
        platform=Platform.XHS,
        mode=MediaCrawlerLoginMode.SAVED_SESSION_PROBE,
    )

    runner_module._configure_upstream(config, request)

    assert config.HEADLESS is True
    assert config.CDP_HEADLESS is True
