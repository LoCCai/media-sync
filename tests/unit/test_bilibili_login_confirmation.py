from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import Any

import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import login_runner
from media_sync.integrations.mediacrawler.login import MediaCrawlerLoginStatus

_PRIVATE = "synthetic-private-confirmation-message-472931"


class _Client:
    def __init__(self, result: object, *, initial: object = False, update_error: BaseException | None = None):
        self.result = result
        self.initial = initial
        self.update_error = update_error
        self.calls: list[str] = []
        self.pong_count = 0
        self.update_arguments: tuple[tuple[Any, ...], dict[str, Any]] | None = None

    async def pong(self) -> object:
        self.calls.append("pong")
        self.pong_count += 1
        result = self.initial if self.pong_count == 1 else self.result
        if isinstance(result, BaseException):
            raise result
        return result

    async def update_cookies(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append("update")
        self.update_arguments = (args, kwargs)
        if self.update_error is not None:
            raise self.update_error


async def _guard(client: Any, platform: Platform = Platform.BILI) -> Any:
    async def factory() -> Any:
        return client

    name = login_runner._CLIENT_FACTORY_NAMES[platform]
    crawler = SimpleNamespace(**{name: factory})
    login_runner._install_client_guard(crawler, platform)
    assert await getattr(crawler, name)() is client
    return client


@pytest.mark.parametrize(
    ("result", "error_type"),
    [
        (True, login_runner._LoginAuthenticated),
        (False, login_runner._LoginConfirmationFailed),
        (None, login_runner._ChildConfigurationError),
        (0, login_runner._ChildConfigurationError),
        (1, login_runner._ChildConfigurationError),
        ("true", login_runner._ChildConfigurationError),
        ({"authenticated": True}, login_runner._ChildConfigurationError),
    ],
)
async def test_bilibili_update_requires_exactly_one_strict_positive_remote_confirmation(
    result: object, error_type: type[Exception]
) -> None:
    client = await _guard(_Client(result))
    assert await client.pong() is False
    context = object()
    with pytest.raises(error_type) as caught:
        await client.update_cookies(context, urls=["https://www.bilibili.com"])
    assert client.calls == ["pong", "update", "pong"]
    assert client.update_arguments == ((context,), {"urls": ["https://www.bilibili.com"]})
    assert str(caught.value) == ""


async def test_bilibili_confirmation_calls_captured_original_not_replaced_wrapper() -> None:
    client = await _guard(_Client(True))
    assert await client.pong() is False

    async def forbidden() -> None:
        pytest.fail("confirmation called the mutable wrapped client.pong")

    client.pong = forbidden
    with pytest.raises(login_runner._LoginAuthenticated):
        await client.update_cookies()
    assert client.calls == ["pong", "update", "pong"]


@pytest.mark.parametrize("platform", [platform for platform in Platform if platform is not Platform.BILI])
async def test_other_platform_updates_keep_existing_success_without_another_probe(platform: Platform) -> None:
    client = await _guard(_Client(RuntimeError(_PRIVATE)), platform)
    assert await client.pong() is False
    with pytest.raises(login_runner._LoginAuthenticated):
        await client.update_cookies()
    assert client.calls == ["pong", "update"]


@pytest.mark.parametrize("platform", list(Platform))
async def test_initial_positive_probe_still_stops_before_login_or_cookie_update(platform: Platform) -> None:
    client = await _guard(_Client(RuntimeError(_PRIVATE), initial=True), platform)
    with pytest.raises(login_runner._LoginAuthenticated):
        await client.pong()
    assert client.calls == ["pong"]


@pytest.mark.parametrize("phase", ["update", "confirmation"])
@pytest.mark.parametrize("error_type", [RuntimeError, TimeoutError, asyncio.CancelledError, SystemExit])
async def test_guard_preserves_existing_exception_and_cancellation_control(
    phase: str, error_type: type[BaseException]
) -> None:
    error = error_type(_PRIVATE)
    client = await _guard(_Client(error, update_error=error if phase == "update" else None))
    assert await client.pong() is False
    with pytest.raises(error_type) as caught:
        await client.update_cookies()
    assert caught.value is error
    assert client.calls == (["pong", "update"] if phase == "update" else ["pong", "update", "pong"])


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (True, MediaCrawlerLoginStatus.AUTHENTICATED),
        (False, MediaCrawlerLoginStatus.FAILED),
        (1, MediaCrawlerLoginStatus.CONFIGURATION_INVALID),
        (RuntimeError(_PRIVATE), MediaCrawlerLoginStatus.FAILED),
        (TimeoutError(_PRIVATE), MediaCrawlerLoginStatus.FAILED),
    ],
)
async def test_controlled_child_maps_post_update_results_without_sensitive_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    result: object,
    expected: MediaCrawlerLoginStatus,
) -> None:
    client = await _guard(_Client(result))

    async def upstream(_request: Any) -> MediaCrawlerLoginStatus:
        try:
            assert await client.pong() is False
            await client.update_cookies()
        except login_runner._LoginAuthenticated:
            return MediaCrawlerLoginStatus.AUTHENTICATED
        pytest.fail("post-update outcome continued into crawling")

    monkeypatch.setattr(login_runner, "_run_upstream", upstream)
    status = await login_runner._execute_controlled_child(None, None)
    assert status is expected
    assert client.calls == ["pong", "update", "pong"]
    captured = capsys.readouterr()
    assert _PRIVATE not in captured.out + captured.err + repr(status)


async def test_controlled_child_cancels_pending_bilibili_confirmation_and_waits_for_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancellation = threading.Event()
    cleaned = False
    calls: list[str] = []

    class Client:
        async def pong(self) -> bool:
            calls.append("pong")
            if len(calls) == 1:
                return False
            cancellation.set()
            await asyncio.Event().wait()
            return True

        async def update_cookies(self) -> None:
            calls.append("update")

    client = await _guard(Client())

    async def upstream(_request: Any) -> MediaCrawlerLoginStatus:
        nonlocal cleaned
        try:
            assert await client.pong() is False
            await client.update_cookies()
            pytest.fail("cancelled confirmation continued into crawling")
        finally:
            cleaned = True

    monkeypatch.setattr(login_runner, "_run_upstream", upstream)
    status = await asyncio.wait_for(login_runner._execute_controlled_child(None, cancellation), timeout=2.0)
    assert status is MediaCrawlerLoginStatus.CANCELLED
    assert cleaned
    assert calls == ["pong", "update", "pong"]
