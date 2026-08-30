from __future__ import annotations

import asyncio
import json
from pathlib import Path
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


def test_system_exit_zero_is_an_explicit_failed_child_result(monkeypatch: pytest.MonkeyPatch) -> None:
    async def exit_zero(_request: object) -> MediaCrawlerLoginStatus:
        raise SystemExit(0)

    monkeypatch.setattr(runner_module, "_run_upstream", exit_zero)
    request = runner_module._ChildRequest(
        checkout_root=Path.cwd(),
        paths=runner_module.build_run_paths(Path.cwd() / ".test-login", Platform.XHS, ACCOUNT_ID, ACCOUNT_ID),
        platform=Platform.XHS,
        mode=MediaCrawlerLoginMode.INTERACTIVE_QR,
    )

    assert asyncio.run(runner_module._execute_child(request)) is MediaCrawlerLoginStatus.FAILED


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
