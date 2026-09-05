from __future__ import annotations

import ast
import asyncio
import os
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from media_sync.integrations.mediacrawler.browser_policy import BrowserLaunchFailure, install_bundled_chromium_policy
from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout

_PLATFORMS = ("xhs", "douyin", "kuaishou", "bilibili", "weibo", "tieba", "zhihu")


class FakeChromium:
    executable_path = "/synthetic/bundled/chromium"
    name = "chromium"

    def __init__(self, error: BaseException | None = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.context = SimpleNamespace(close=self.close)
        self.browser = SimpleNamespace(new_context=self.new_context, close=self.close)
        self.close_count = 0
        self.error = error

    async def close(self) -> None:
        self.close_count += 1

    async def launch(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("launch", args, kwargs))
        if self.error is not None:
            raise self.error
        return self.browser

    async def launch_persistent_context(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("persistent", args, kwargs))
        if self.error is not None:
            raise self.error
        return self.context

    async def new_context(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("new_context", args, kwargs))
        return self.context


@pytest.fixture(scope="module")
def pinned_launchers() -> dict[str, tuple[Callable[..., Any], SimpleNamespace]]:
    checkout = verify_mediacrawler_checkout(
        Path(__file__).resolve().parents[2] / "upstreams.lock.json", license_acknowledged=True
    )
    launchers = {}
    for platform in _PLATFORMS:
        source_path = checkout.root / "media_platform" / platform / "core.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        matches = [
            method
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            for method in node.body
            if isinstance(method, ast.AsyncFunctionDef) and method.name == "launch_browser"
        ]
        assert len(matches) == 1
        config = SimpleNamespace(SAVE_LOGIN_STATE=True, USER_DATA_DIR="/synthetic/profile-%s", PLATFORM=platform)
        namespace: dict[str, Any] = {
            "config": config,
            "os": os,
            "utils": SimpleNamespace(logger=SimpleNamespace(info=lambda *_args: None)),
        }
        module = ast.fix_missing_locations(
            ast.Module(
                body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *matches],
                type_ignores=[],
            )
        )
        exec(compile(module, str(source_path), "exec"), namespace)
        launchers[platform] = (namespace["launch_browser"], config)
    return launchers


def _main_for(crawler: Any) -> Any:
    class Factory:
        @staticmethod
        def create_crawler(platform: str) -> Any:
            assert platform == "fixture"
            return crawler

    return SimpleNamespace(CrawlerFactory=Factory)


@pytest.mark.parametrize("platform", _PLATFORMS)
@pytest.mark.parametrize("persistent", [True, False])
@pytest.mark.parametrize("headless", [True, False])
async def test_pinned_launches_change_only_browser_selectors(
    pinned_launchers: dict[str, tuple[Callable[..., Any], SimpleNamespace]],
    platform: str,
    persistent: bool,
    headless: bool,
) -> None:
    launcher, config = pinned_launchers[platform]
    config.SAVE_LOGIN_STATE = persistent
    crawler = type("Crawler", (), {"launch_browser": launcher})()
    proxy = {"server": "http://synthetic.invalid:8080", "username": "fixture", "password": "fixture"}
    baseline = FakeChromium()
    await crawler.launch_browser(baseline, proxy, "fixture-agent", headless=headless)
    upstream_main = _main_for(crawler)
    install_bundled_chromium_policy(upstream_main)
    assert upstream_main.CrawlerFactory.create_crawler("fixture") is crawler
    chromium = FakeChromium()
    context = await crawler.launch_browser(
        chromium=chromium, playwright_proxy=proxy, user_agent="fixture-agent", headless=headless
    )
    expected = [(kind, args, dict(options)) for kind, args, options in baseline.calls]
    expected[0][2].pop("channel", None)
    expected[0][2]["executable_path"] = chromium.executable_path
    assert chromium.calls == expected
    assert context is chromium.context
    assert chromium.calls[0][2]["proxy"] is proxy
    assert chromium.close_count == 0
    await context.close()
    assert chromium.close_count == 1


@pytest.mark.parametrize("platform", _PLATFORMS)
@pytest.mark.parametrize("persistent", [True, False])
async def test_login_opt_in_classifies_exact_pinned_launch_failures(
    pinned_launchers: dict[str, tuple[Callable[..., Any], SimpleNamespace]], platform: str, persistent: bool
) -> None:
    launcher, config = pinned_launchers[platform]
    config.SAVE_LOGIN_STATE = persistent
    crawler = type("Crawler", (), {"launch_browser": launcher})()
    upstream_main = _main_for(crawler)
    install_bundled_chromium_policy(upstream_main, classify_launch_errors=True)
    upstream_main.CrawlerFactory.create_crawler("fixture")
    chromium = FakeChromium(RuntimeError("synthetic launch failure"))
    with pytest.raises(BrowserLaunchFailure, match=r"^MediaCrawler browser launch failed$"):
        await crawler.launch_browser(chromium, None, None)
    assert len(chromium.calls) == 1
    assert chromium.close_count == 0


@pytest.mark.parametrize("platform", _PLATFORMS)
@pytest.mark.parametrize("error", [RuntimeError("synthetic launch failure"), asyncio.CancelledError()])
async def test_pinned_launch_errors_and_cancellation_keep_original_lifecycle(
    pinned_launchers: dict[str, tuple[Callable[..., Any], SimpleNamespace]], platform: str, error: BaseException
) -> None:
    launcher, config = pinned_launchers[platform]
    config.SAVE_LOGIN_STATE = True
    crawler = type("Crawler", (), {"launch_browser": launcher})()
    upstream_main = _main_for(crawler)
    install_bundled_chromium_policy(upstream_main)
    upstream_main.CrawlerFactory.create_crawler("fixture")
    chromium = FakeChromium(error)
    with pytest.raises(type(error)) as caught:
        await crawler.launch_browser(chromium, None, None)
    assert caught.value is error
    assert len(chromium.calls) == 1
    assert chromium.close_count == 0


async def test_factory_and_instance_installation_are_idempotent_and_preserve_extra_options() -> None:
    options = {"channel": "chrome", "executable_path": "/synthetic/other", "args": ["--fixture"], "timeout": 123}

    class Crawler:
        async def launch_browser(self, chromium: Any, marker: object) -> Any:
            assert marker is options
            assert chromium.name == "chromium"
            return await chromium.launch_persistent_context("/synthetic/profile", **options)

    crawler = Crawler()
    upstream_main = _main_for(crawler)
    install_bundled_chromium_policy(upstream_main)
    factory = upstream_main.CrawlerFactory.create_crawler
    install_bundled_chromium_policy(upstream_main)
    assert upstream_main.CrawlerFactory.create_crawler is factory
    upstream_main.CrawlerFactory.create_crawler(platform="fixture")
    wrapped = crawler.launch_browser
    upstream_main.CrawlerFactory.create_crawler("fixture")
    assert crawler.launch_browser is wrapped
    chromium = FakeChromium()
    assert await crawler.launch_browser(chromium, options) is chromium.context
    assert chromium.calls == [
        (
            "persistent",
            ("/synthetic/profile",),
            {"executable_path": chromium.executable_path, "args": ["--fixture"], "timeout": 123},
        )
    ]
    assert options["channel"] == "chrome"
    assert options["executable_path"] == "/synthetic/other"


@pytest.mark.parametrize(
    "main", [None, SimpleNamespace(), SimpleNamespace(CrawlerFactory=SimpleNamespace(create_crawler=None))]
)
def test_missing_factory_fails_with_fixed_safe_message(main: Any) -> None:
    with pytest.raises(RuntimeError, match=r"^MediaCrawler bundled browser policy is unavailable$"):
        install_bundled_chromium_policy(main)


def test_missing_crawler_launch_fails_with_fixed_safe_message() -> None:
    main = _main_for(SimpleNamespace())
    install_bundled_chromium_policy(main)
    with pytest.raises(RuntimeError, match=r"^MediaCrawler bundled browser policy is unavailable$"):
        main.CrawlerFactory.create_crawler("fixture")


@pytest.mark.parametrize("executable", [None, "", 12])
async def test_missing_bundled_executable_fails_before_launch(executable: object) -> None:
    class Crawler:
        async def launch_browser(self, chromium: Any) -> Any:
            pytest.fail("invalid runtime must not reach the upstream launcher")

    crawler = Crawler()
    main = _main_for(crawler)
    install_bundled_chromium_policy(main)
    main.CrawlerFactory.create_crawler("fixture")
    with pytest.raises(RuntimeError, match=r"^MediaCrawler bundled browser policy is unavailable$"):
        await crawler.launch_browser(SimpleNamespace(executable_path=executable))
