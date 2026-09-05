"""Choose the installed Playwright Chromium without owning browser lifetimes.

The pinned upstream uses system Chrome channels on five platforms. Container
images install Playwright's bundled Chromium instead. This child-local adapter
changes only browser selectors, leaving the upstream's persistent profile,
context options and cleanup ownership intact; it never modifies the checkout.
"""

from __future__ import annotations

from types import MethodType
from typing import Any

_POLICY_MARKER = "_media_sync_bundled_chromium_policy"
_INVALID_POLICY = "MediaCrawler bundled browser policy is unavailable"


class _BundledChromium:
    def __init__(self, chromium: Any) -> None:
        executable = getattr(chromium, "executable_path", None)
        if not isinstance(executable, str) or not executable:
            raise RuntimeError(_INVALID_POLICY)
        self._chromium = chromium
        self._executable = executable

    def __getattr__(self, name: str) -> Any:
        return getattr(self._chromium, name)

    def _options(self, options: dict[str, Any]) -> dict[str, Any]:
        options.pop("channel", None)
        options["executable_path"] = self._executable
        return options

    async def launch(self, *args: Any, **kwargs: Any) -> Any:
        return await self._chromium.launch(*args, **self._options(kwargs))

    async def launch_persistent_context(self, *args: Any, **kwargs: Any) -> Any:
        return await self._chromium.launch_persistent_context(*args, **self._options(kwargs))


def _install_on_crawler(crawler: Any) -> None:
    original = getattr(crawler, "launch_browser", None)
    if not callable(original):
        raise RuntimeError(_INVALID_POLICY)
    if getattr(original, _POLICY_MARKER, False) is True:
        return

    async def launch_browser(_instance: Any, chromium: Any, *args: Any, **kwargs: Any) -> Any:
        return await original(_BundledChromium(chromium), *args, **kwargs)

    setattr(launch_browser, _POLICY_MARKER, True)
    crawler.launch_browser = MethodType(launch_browser, crawler)


def install_bundled_chromium_policy(upstream_main: Any) -> None:
    """Wrap each factory-created crawler, including upstream ``main()`` paths.

    Installation is idempotent and restricted to the imported child process.
    It does not create, close, catch errors from or otherwise retain browsers.
    Existing runner boundaries retain responsibility for safe error reporting.
    """

    factory: Any = getattr(upstream_main, "CrawlerFactory", None)
    original = getattr(factory, "create_crawler", None)
    if not callable(original):
        raise RuntimeError(_INVALID_POLICY)
    if getattr(original, _POLICY_MARKER, False) is True:
        return

    def create_crawler(*args: Any, **kwargs: Any) -> Any:
        crawler = original(*args, **kwargs)
        _install_on_crawler(crawler)
        return crawler

    setattr(create_crawler, _POLICY_MARKER, True)
    factory.create_crawler = staticmethod(create_crawler)
