"""Pinned Cookie compatibility: fresh contexts and lossless full-field injection."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from media_sync.domain import Platform

from .cookie_login import cookie_pairs, parse_cookie_header

_PLATFORMS = {
    Platform.BILI: ("bilibili", "BilibiliCrawler", "BilibiliLogin", ".bilibili.com"),
    Platform.WB: ("weibo", "WeiboCrawler", "WeiboLogin", ".weibo.cn"),
    Platform.XHS: ("xhs", "XiaoHongShuCrawler", "XiaoHongShuLogin", ".xiaohongshu.com"),
    Platform.ZHIHU: ("zhihu", "ZhihuCrawler", "ZhiHuLogin", ".zhihu.com"),
    Platform.DY: ("douyin", "DouYinCrawler", "DouYinLogin", ".douyin.com"),
    Platform.KS: ("kuaishou", "KuaishouCrawler", "KuaishouLogin", ".kuaishou.com"),
    Platform.TIEBA: ("tieba", "TieBaCrawler", "BaiduTieBaLogin", ".baidu.com"),
}


def _source(module: Any, expected: Path) -> None:
    path = getattr(module, "__file__", None)
    if type(path) is not str or Path(path).resolve() != expected.resolve() or expected.is_symlink():
        raise ValueError("cookie_reuse_configuration_invalid")


def install_cookie_reuse(checkout: Path, platform: Platform, raw_cookie: str) -> None:
    """Install only in a verified, disposable upstream child before start().

    No persistent browser directory is opened, even if an old saved session
    exists. The candidate is installed before the first client/pong is created.
    A failed pong can only reinject that same candidate, never invoke QR.
    """

    pairs = cookie_pairs(parse_cookie_header(raw_cookie).reveal())
    name, crawler_name, login_name, domain = _PLATFORMS[Platform(platform)]
    config: Any = importlib.import_module("config")
    core = importlib.import_module(f"media_platform.{name}.core")
    login = importlib.import_module(f"media_platform.{name}.login")
    utils: Any = importlib.import_module("tools.utils")
    crawler_util: Any = importlib.import_module("tools.crawler_util")
    for module, relative in (
        (config, "config/__init__.py"),
        (core, f"media_platform/{name}/core.py"),
        (login, f"media_platform/{name}/login.py"),
        (utils, "tools/utils.py"),
        (crawler_util, "tools/crawler_util.py"),
    ):
        _source(module, checkout / relative)
    crawler_class = getattr(core, crawler_name, None)
    login_class = getattr(login, login_name, None)
    if (
        crawler_class is None
        or login_class is None
        or getattr(crawler_class, "__module__", None) != core.__name__
        or getattr(login_class, "__module__", None) != login.__name__
        or not callable(getattr(crawler_class, "launch_browser", None))
        or not callable(getattr(login_class, "begin", None))
    ):
        raise ValueError("cookie_reuse_configuration_invalid")

    async def inject(context: Any) -> None:
        await context.add_cookies(
            [
                {"name": key, "value": value, "domain": domain, "path": "/", "secure": True}
                for key, value in pairs.items()
            ]
        )

    async def launch_browser(
        _self: Any,
        chromium: Any,
        playwright_proxy: Any,
        user_agent: str | None,
        headless: bool = True,
    ) -> Any:
        browser = await chromium.launch(headless=headless, proxy=playwright_proxy)
        try:
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
                accept_downloads=False,
                service_workers="block",
            )
            await inject(context)
            return context
        except BaseException:
            await browser.close()
            raise

    async def cookie_only(self: Any) -> None:
        await inject(self.browser_context)

    # Each worker handles exactly one request and exits. These in-memory patches
    # do not change the immutable upstream checkout or the saved-session path.
    config.SAVE_LOGIN_STATE = False
    config.ENABLE_CDP_MODE = False
    config.CDP_CONNECT_EXISTING = False
    config.LOGIN_TYPE = "cookie"
    config.XHS_INTERNATIONAL = False
    utils.convert_str_cookie_to_dict = cookie_pairs
    crawler_util.convert_str_cookie_to_dict = cookie_pairs
    crawler_class.launch_browser = launch_browser
    login_class.begin = cookie_only
    login_class.login_by_cookies = cookie_only


__all__ = ["install_cookie_reuse"]
