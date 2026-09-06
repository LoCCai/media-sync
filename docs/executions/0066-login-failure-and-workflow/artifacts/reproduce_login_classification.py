"""Reproduce QR failure classification using locked modules and synthetic pages.

From the repository root, run this file with:
    uv run --no-sync python -X utf8 -B <path-to-this-script>

This is an offline diagnostic, not a real platform qualification. It imports
the complete locked login/helper modules, replaces only browser/dependency
boundaries, and records the application's actual closed failure status. No
Cookie, browser, platform request, real identity or production data is used.
Synthetic timeouts occur immediately; the script does not measure live timing.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
REPOSITORY = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY))

import pytest  # noqa: E402
from tests.contract.test_cookie_login_upstream import load, offline  # noqa: E402

from media_sync.integrations.mediacrawler import login_runner as runner  # noqa: E402
from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout  # noqa: E402

EXPECTED_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
CASES = (
    ("douyin", "DouYinLogin", "popup_click_timeout"),
    ("douyin", "DouYinLogin", "qr_selector_timeout"),
    ("kuaishou", "KuaishouLogin", "qr_selector_timeout"),
    ("weibo", "WeiboLogin", "qr_selector_timeout"),
    ("tieba", "BaiduTieBaLogin", "qr_selector_timeout"),
)


class SyntheticPage:
    def __init__(self, platform: str, case: str) -> None:
        self.platform = platform
        self.case = case
        self.calls: list[list[object]] = []

    async def wait_for_selector(self, selector: str, **kwargs: object) -> object:
        self.calls.append(["wait", selector, kwargs.get("timeout", "default")])
        if self.platform == "douyin" and "login-panel-new" in selector and self.case != "popup_click_timeout":
            return object()
        raise TimeoutError("SYNTHETIC_SELECTOR_TIMEOUT")

    def locator(self, selector: str) -> SyntheticPage:
        self.calls.append(["locator", selector])
        return self

    async def click(self) -> None:
        self.calls.append(["click"])
        if self.case == "popup_click_timeout":
            raise TimeoutError("SYNTHETIC_CLICK_TIMEOUT")

    async def goto(self, _url: str) -> None:
        self.calls.append(["goto", "synthetic_sso"])


async def reproduce() -> None:
    verified = verify_mediacrawler_checkout(REPOSITORY / "upstreams.lock.json", license_acknowledged=True)
    if verified.commit != EXPECTED_SHA:
        raise RuntimeError("diagnostic requires its explicitly reviewed upstream commit")
    checkout = verified.root
    with pytest.MonkeyPatch.context() as patch:
        # Existing contract fixtures forbid original HTTP, browser creation,
        # login/content side effects and proxy refresh. Retry decorators are
        # offline fakes; these cases fail before the login-state poll begins.
        environment = offline.__wrapped__(checkout, patch)
        patch.setattr(sys.modules["playwright.async_api"], "Cookie", dict, raising=False)
        helper = load(patch, "tools.crawler_util", checkout / "tools/crawler_util.py")
        environment["utils"].find_login_qrcode = helper.find_login_qrcode
        environment["utils"].show_qrcode = environment["forbidden"]

        async def fast_sleep(_seconds: float) -> None:
            pass

        outcomes = []
        for platform, class_name, case in CASES:
            page = SyntheticPage(platform, case)
            calls = page.calls
            module = load(
                patch,
                f"media_platform.{platform}.login",
                checkout / f"media_platform/{platform}/login.py",
            )
            module.asyncio = SimpleNamespace(sleep=fast_sleep, get_running_loop=asyncio.get_running_loop)
            login = getattr(module, class_name)("qrcode", SimpleNamespace(), page)

            async def execute(_request: object, login=login) -> None:
                with runner._silenced_upstream():
                    await login.begin()
                raise AssertionError("unexpected successful login")

            patch.setattr(runner, "_run_upstream", execute)
            status = await runner._execute_controlled_child(None, None)
            # Before the diagnostic fix all five statuses were 'failed'. Keep
            # recording any future safe classification for before/after review,
            # but never accept an authentication success in a timeout case.
            assert status.value != "authenticated"
            assert any(call[0] == "wait" for call in calls)
            expected_waits = 2 if platform == "tieba" or (platform == "douyin" and case == "qr_selector_timeout") else 1
            assert sum(call[0] == "wait" for call in calls) == expected_waits
            outcomes.append({"platform": platform, "case": case, "status": status.value, "calls": calls})

        print(json.dumps({"upstream_sha": EXPECTED_SHA, "offline_cases": outcomes}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(reproduce())
