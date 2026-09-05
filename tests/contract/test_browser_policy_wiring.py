"""Execute pinned factory/launch bodies and real child entry wiring without browsers.

Only constructors, platform work and unrelated capture/configuration are stubbed.
No source-string assertions, checkout imports, user profiles or network are used.
"""

from __future__ import annotations

import ast
import contextlib
import importlib
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from media_sync.domain import LoginMethod, Platform
from media_sync.integrations.mediacrawler import browser_policy, cookie_reuse, detail_runner, login_runner, runner
from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout
from media_sync.integrations.mediacrawler.login import MediaCrawlerLoginMode, MediaCrawlerLoginStatus
from media_sync.integrations.mediacrawler.policies import WatchdogLimits

_PLATFORM_SOURCES = {
    Platform.XHS: "xhs",
    Platform.DY: "douyin",
    Platform.KS: "kuaishou",
    Platform.BILI: "bilibili",
    Platform.WB: "weibo",
    Platform.TIEBA: "tieba",
    Platform.ZHIHU: "zhihu",
}


@pytest.fixture(scope="module")
def pinned_nodes() -> tuple[list[ast.stmt], dict[Platform, tuple[str, ast.AsyncFunctionDef]]]:
    checkout = verify_mediacrawler_checkout(
        Path(__file__).resolve().parents[2] / "upstreams.lock.json", license_acknowledged=True
    )
    main_tree = ast.parse((checkout.root / "main.py").read_text(encoding="utf-8"))
    factory = [node for node in main_tree.body if isinstance(node, ast.ClassDef) and node.name == "CrawlerFactory"]
    main = [node for node in main_tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "main"]
    assert len(factory) == len(main) == 1
    launchers = {}
    for platform, directory in _PLATFORM_SOURCES.items():
        tree = ast.parse((checkout.root / "media_platform" / directory / "core.py").read_text(encoding="utf-8"))
        matches = [
            (node.name, method)
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            for method in node.body
            if isinstance(method, ast.AsyncFunctionDef) and method.name == "launch_browser"
        ]
        assert len(matches) == 1
        launchers[platform] = matches[0]
    return [*factory, *main], launchers


def _compile(nodes: list[ast.stmt], namespace: dict[str, Any]) -> None:
    module = ast.fix_missing_locations(
        ast.Module(
            body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes],
            type_ignores=[],
        )
    )
    exec(compile(module, "<verified-pinned-browser-wiring>", "exec"), namespace)


class _Chromium:
    executable_path = "/synthetic/bundled/chromium"

    def __init__(self, events: list[str], failure: Exception | None = None) -> None:
        self.events = events
        self.failure = failure
        self.calls: list[dict[str, Any]] = []
        self.context = object()

    async def launch_persistent_context(self, **kwargs: Any) -> object:
        self.events.append("browser")
        self.calls.append(kwargs)
        assert kwargs["executable_path"] == self.executable_path
        assert "channel" not in kwargs
        if self.failure is not None:
            raise self.failure
        return self.context


def _runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pinned_nodes: tuple[list[ast.stmt], dict[Platform, tuple[str, ast.AsyncFunctionDef]]],
    platform: Platform,
    *,
    authenticated: bool = False,
    launch_failure: Exception | None = None,
) -> SimpleNamespace:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", sys.argv.copy())
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.delitem(sys.modules, "config", raising=False)
    monkeypatch.delitem(sys.modules, "main", raising=False)
    config = ModuleType("config")
    config.__dict__.update(
        __file__=str(checkout / "config.py"),
        SAVE_LOGIN_STATE=True,
        USER_DATA_DIR=str(tmp_path / "profile-%s"),
        PLATFORM=platform.value,
        SAVE_DATA_OPTION="jsonl",
        COOKIES="",
    )
    events: list[str] = []
    chromium = _Chromium(events, launch_failure)
    upstream = ModuleType("main")
    upstream.__file__ = str(checkout / "main.py")

    async def parse_cmd() -> SimpleNamespace:
        return SimpleNamespace(init_db=False)

    async def no_op() -> None:
        return None

    async def cleanup() -> None:
        events.append("cleanup")

    upstream.__dict__.update(
        config=config,
        cmd_arg=SimpleNamespace(parse_cmd=parse_cmd),
        _flush_excel_if_needed=lambda: None,
        _generate_wordcloud_if_needed=no_op,
        async_cleanup=cleanup,
        crawler=None,
    )
    for code, (name, launcher) in pinned_nodes[1].items():
        namespace: dict[str, Any] = {
            "config": config,
            "os": os,
            "utils": SimpleNamespace(logger=SimpleNamespace(info=lambda *_args: None)),
        }
        _compile([launcher], namespace)

        def initialize(self: Any, *, selected: Platform = code) -> None:
            self.selected = selected
            events.append(f"factory:{selected.value}")

        async def start(self: Any) -> None:
            events.append("start")
            self.context = await self.launch_browser(chromium, None, "fixture-agent", headless=False)
            callback = getattr(self, "get_specified_videos", None)
            if callback is not None:
                await callback([])
            if authenticated:
                raise login_runner._LoginAuthenticated

        async def get_video_info_task(self: Any, *, aid: int, bvid: str, semaphore: Any) -> None:
            assert aid == 123 and bvid == ""
            events.append("aid-detail")
            return None

        upstream.__dict__[name] = type(
            name,
            (),
            {
                "__init__": initialize,
                "start": start,
                "launch_browser": namespace["launch_browser"],
                "get_video_info_task": get_video_info_task,
            },
        )
    _compile(pinned_nodes[0], upstream.__dict__)
    original_import = importlib.import_module

    def fake_import(name: str, package: str | None = None) -> Any:
        if name == "config":
            return config
        if name == "main":
            return upstream
        return original_import(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    install = browser_policy.install_bundled_chromium_policy

    policy_modes: list[bool] = []

    def observed_install(main: Any, *, classify_launch_errors: bool = False) -> None:
        assert main is upstream
        events.append("install")
        policy_modes.append(classify_launch_errors)
        install(main, classify_launch_errors=classify_launch_errors)

    monkeypatch.setattr(browser_policy, "install_bundled_chromium_policy", observed_install)
    monkeypatch.setattr(login_runner, "install_bundled_chromium_policy", observed_install)
    monkeypatch.setattr(detail_runner, "install_bundled_chromium_policy", observed_install)

    def synthetic_cookie_reuse(root: Path, selected: Platform, cookie: str) -> None:
        # This fixture executes extracted upstream browser bodies, not a full
        # checkout. Cookie injection has its own actual-module contract tests.
        assert root == checkout and selected is platform and cookie == "session=fixture"
        events.append("cookie-reuse")

    monkeypatch.setattr(cookie_reuse, "install_cookie_reuse", synthetic_cookie_reuse)
    return SimpleNamespace(
        checkout=checkout, config=config, main=upstream, events=events, chromium=chromium, policy_modes=policy_modes
    )


@pytest.mark.parametrize("platform", tuple(Platform))
async def test_pinned_factory_dispatches_each_platform_through_real_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_nodes: Any, platform: Platform
) -> None:
    fixture = _runtime(tmp_path, monkeypatch, pinned_nodes, platform)
    browser_policy.install_bundled_chromium_policy(fixture.main)
    crawler = fixture.main.CrawlerFactory.create_crawler(platform=platform.value)
    assert crawler.selected is platform
    await crawler.start()
    assert crawler.context is fixture.chromium.context
    assert fixture.events == ["install", f"factory:{platform.value}", "start", "browser"]
    assert fixture.policy_modes == [False]


@pytest.mark.parametrize("platform", tuple(Platform))
async def test_real_login_entry_installs_policy_before_pinned_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_nodes: Any, platform: Platform
) -> None:
    fixture = _runtime(tmp_path, monkeypatch, pinned_nodes, platform, authenticated=True)
    monkeypatch.setattr(login_runner, "_configure_upstream", lambda *_args: None)
    monkeypatch.setattr(login_runner, "_install_client_guard", lambda *_args: None)
    monkeypatch.setattr(login_runner, "_disable_qr_export", lambda *_args: contextlib.nullcontext())
    request = SimpleNamespace(
        checkout_root=fixture.checkout,
        platform=platform,
        mode=MediaCrawlerLoginMode.INTERACTIVE_QR,
        paths=SimpleNamespace(account_root=tmp_path / "unused-account"),
    )

    assert await login_runner._run_upstream(request) is MediaCrawlerLoginStatus.AUTHENTICATED
    assert fixture.events == ["install", f"factory:{platform.value}", "start", "browser", "cleanup"]
    assert fixture.policy_modes == [True]


@pytest.mark.parametrize("platform", tuple(Platform))
async def test_real_login_child_classifies_pinned_launch_failure_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_nodes: Any, platform: Platform
) -> None:
    fixture = _runtime(
        tmp_path,
        monkeypatch,
        pinned_nodes,
        platform,
        launch_failure=RuntimeError("synthetic-secret-browser-error"),
    )
    monkeypatch.setattr(login_runner, "_configure_upstream", lambda *_args: None)
    monkeypatch.setattr(login_runner, "_install_client_guard", lambda *_args: None)
    monkeypatch.setattr(login_runner, "_disable_qr_export", lambda *_args: contextlib.nullcontext())
    request = SimpleNamespace(
        checkout_root=fixture.checkout,
        platform=platform,
        mode=MediaCrawlerLoginMode.INTERACTIVE_QR,
        paths=SimpleNamespace(account_root=tmp_path / "unused-account"),
    )

    assert await login_runner._execute_child(request) is MediaCrawlerLoginStatus.BROWSER_LAUNCH_FAILED
    assert fixture.events == ["install", f"factory:{platform.value}", "start", "browser", "cleanup"]
    assert fixture.policy_modes == [True]
    assert fixture.config.COOKIES == ""


def _disable_capture_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    for module_name, function in (
        ("bilibili_media", "install_bilibili_media_capture"),
        ("weibo_media", "install_weibo_media_capture"),
        ("tieba_media", "install_tieba_media_capture"),
        ("zhihu_media", "install_zhihu_media_capture"),
        ("kuaishou_media", "install_kuaishou_media_capture"),
        ("xhs_live", "install_xhs_live_capture"),
    ):
        module = importlib.import_module(f"media_sync.integrations.mediacrawler.{module_name}")
        monkeypatch.setattr(module, function, lambda *_args, **_kwargs: None)
        if hasattr(detail_runner, function):
            monkeypatch.setattr(detail_runner, function, lambda *_args, **_kwargs: None)


@pytest.mark.parametrize("platform,bounded", [(platform, False) for platform in Platform] + [(Platform.BILI, True)])
async def test_real_creator_entry_installs_policy_before_pinned_main_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_nodes: Any, platform: Platform, bounded: bool
) -> None:
    fixture = _runtime(tmp_path, monkeypatch, pinned_nodes, platform)
    from media_sync.integrations.mediacrawler import bridge

    monkeypatch.setattr(bridge, "verify_manifest_checkout", lambda _manifest: SimpleNamespace(root=fixture.checkout))
    monkeypatch.setattr(runner, "_configure_upstream", lambda *_args: None)
    _disable_capture_hooks(monkeypatch)
    if bounded:
        from media_sync.integrations.mediacrawler import bilibili_capture

        monkeypatch.setattr(
            bilibili_capture, "install_bilibili_capture_shim", lambda manifest: fixture.events.append("bounded-capture")
        )
    output = tmp_path / "output"
    output.mkdir()
    manifest = SimpleNamespace(
        request_delay_seconds=1.0,
        python_executable=Path(sys.executable).parent.resolve() / Path(sys.executable).name,
        output_root=output,
        platform=platform,
        login_method=LoginMethod.COOKIE,
        watchdogs=WatchdogLimits(max_seconds=5, poll_seconds=0.01),
        max_items=1,
        bili_scan=object() if bounded else None,
    )

    assert await runner._execute_child(manifest, "fixture-author", "session=fixture", None) == 0
    assert fixture.events == ["install"] + (["bounded-capture"] if bounded else []) + [
        "cookie-reuse",
        f"factory:{platform.value}",
        "start",
        "browser",
        "cleanup",
    ]
    assert fixture.policy_modes == [False]


@pytest.mark.parametrize("platform", tuple(Platform))
async def test_real_detail_entry_installs_policy_before_pinned_main_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_nodes: Any, platform: Platform
) -> None:
    fixture = _runtime(tmp_path, monkeypatch, pinned_nodes, platform)
    monkeypatch.setattr(detail_runner, "_configure_upstream", lambda *_args: None)
    _disable_capture_hooks(monkeypatch)
    request = SimpleNamespace(
        checkout_root=fixture.checkout,
        platform=platform,
        login_method=LoginMethod.COOKIE,
        detail_reference="fixture-reference",
        bili_dynamic_detail=False,
        cookie="session=fixture",
    )

    assert await detail_runner._run_upstream(request) == (fixture.main, None)
    assert fixture.events == ["install", "cookie-reuse", f"factory:{platform.value}", "start", "browser"]
    assert fixture.policy_modes == [False]


async def test_explicit_dynamic_detail_dispatch_precedes_numeric_aid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_nodes: Any
) -> None:
    fixture = _runtime(tmp_path, monkeypatch, pinned_nodes, Platform.BILI)
    monkeypatch.setattr(detail_runner, "_configure_upstream", lambda *_args: None)
    _disable_capture_hooks(monkeypatch)
    result = detail_runner._BiliDynamicDetailResult(b"private-in-memory-fixture")

    async def dynamic(main: object, request: object) -> detail_runner._BiliDynamicDetailResult:
        assert main is fixture.main
        fixture.events.append("dynamic-detail")
        return result

    async def aid(*args: object) -> None:
        raise AssertionError("numeric DID must never enter numeric AID dispatch")

    monkeypatch.setattr(detail_runner, "_run_bilibili_dynamic", dynamic)
    monkeypatch.setattr(detail_runner, "_run_bilibili_aid", aid)
    request = SimpleNamespace(
        checkout_root=fixture.checkout,
        platform=Platform.BILI,
        login_method=LoginMethod.COOKIE,
        detail_reference="123456789012345678",
        bili_dynamic_detail=True,
        cookie="session=fixture",
    )
    assert await detail_runner._run_upstream(request) == (fixture.main, result)
    assert fixture.events == ["install", "cookie-reuse", "dynamic-detail"]


async def test_real_bilibili_aid_detail_branch_uses_same_installed_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_nodes: Any
) -> None:
    fixture = _runtime(tmp_path, monkeypatch, pinned_nodes, Platform.BILI)
    monkeypatch.setattr(detail_runner, "_configure_upstream", lambda *_args: None)
    request = SimpleNamespace(
        checkout_root=fixture.checkout,
        platform=Platform.BILI,
        login_method=LoginMethod.COOKIE,
        detail_reference="123",
        bili_progressive_detail=False,
        bili_dynamic_detail=False,
        cookie="session=fixture",
    )

    assert await detail_runner._run_upstream(request) == (fixture.main, None)
    assert fixture.events == ["install", "cookie-reuse", "factory:bili", "start", "browser", "aid-detail"]
    assert fixture.policy_modes == [False]
