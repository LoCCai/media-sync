"""Choose the installed Playwright Chromium without owning browser lifetimes.

The pinned upstream uses system Chrome channels on five platforms. Container
images install Playwright's bundled Chromium instead. This child-local adapter
changes only browser selectors, leaving the upstream's persistent profile,
context options and cleanup ownership intact; it never modifies the checkout.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MethodType
from typing import Any

_POLICY_MARKER = "_media_sync_bundled_chromium_policy"
_INVALID_POLICY = "MediaCrawler bundled browser policy is unavailable"


class BrowserLaunchFailure(RuntimeError):
    """A Chromium launch call failed, without exposing its original exception."""

    def __init__(self) -> None:
        super().__init__("MediaCrawler browser launch failed")


@dataclass(frozen=True, slots=True)
class _PolicyMode:
    classify_launch_errors: bool


def _already_installed(original: Any, mode: _PolicyMode) -> bool:
    installed = getattr(original, _POLICY_MARKER, None)
    if installed is None:
        return False
    if not isinstance(installed, _PolicyMode) or installed != mode:
        raise RuntimeError(_INVALID_POLICY)
    return True


class _BundledChromium:
    def __init__(self, chromium: Any, mode: _PolicyMode) -> None:
        executable = getattr(chromium, "executable_path", None)
        if not isinstance(executable, str) or not executable:
            raise RuntimeError(_INVALID_POLICY)
        self._chromium = chromium
        self._executable = executable
        self._mode = mode

    def __getattr__(self, name: str) -> Any:
        return getattr(self._chromium, name)

    def _options(self, options: dict[str, Any]) -> dict[str, Any]:
        options.pop("channel", None)
        options["executable_path"] = self._executable
        return options

    async def launch(self, *args: Any, **kwargs: Any) -> Any:
        launch = self._chromium.launch
        options = self._options(kwargs)
        if not self._mode.classify_launch_errors:
            return await launch(*args, **options)
        try:
            return await launch(*args, **options)
        except Exception:
            raise BrowserLaunchFailure() from None

    async def launch_persistent_context(self, *args: Any, **kwargs: Any) -> Any:
        launch = self._chromium.launch_persistent_context
        options = self._options(kwargs)
        if not self._mode.classify_launch_errors:
            return await launch(*args, **options)
        try:
            return await launch(*args, **options)
        except Exception:
            raise BrowserLaunchFailure() from None


def _install_on_crawler(crawler: Any, mode: _PolicyMode) -> None:
    original = getattr(crawler, "launch_browser", None)
    if not callable(original):
        raise RuntimeError(_INVALID_POLICY)
    if _already_installed(original, mode):
        return

    async def launch_browser(_instance: Any, chromium: Any, *args: Any, **kwargs: Any) -> Any:
        return await original(_BundledChromium(chromium, mode), *args, **kwargs)

    setattr(launch_browser, _POLICY_MARKER, mode)
    crawler.launch_browser = MethodType(launch_browser, crawler)


def install_bundled_chromium_policy(upstream_main: Any, *, classify_launch_errors: bool = False) -> None:
    """Wrap each factory-created crawler, including upstream ``main()`` paths.

    Same-mode installation is idempotent and restricted to the child process.
    It never creates, closes or retains browsers. By default exceptions preserve
    their identity. Login may opt into a fixed failure at the two launch awaits;
    cancellation and other BaseExceptions always retain their original meaning.
    """

    if not isinstance(classify_launch_errors, bool):
        raise RuntimeError(_INVALID_POLICY)
    mode = _PolicyMode(classify_launch_errors)
    factory: Any = getattr(upstream_main, "CrawlerFactory", None)
    original = getattr(factory, "create_crawler", None)
    if not callable(original):
        raise RuntimeError(_INVALID_POLICY)
    if _already_installed(original, mode):
        return

    def create_crawler(*args: Any, **kwargs: Any) -> Any:
        crawler = original(*args, **kwargs)
        _install_on_crawler(crawler, mode)
        return crawler

    setattr(create_crawler, _POLICY_MARKER, mode)
    factory.create_crawler = staticmethod(create_crawler)
