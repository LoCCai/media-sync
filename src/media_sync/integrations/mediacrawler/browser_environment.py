"""Approved environment shared by preflight and MediaCrawler browser children.

Only the browser cache is inherited, never arbitrary Playwright/Python options,
proxy credentials, operator secrets or the parent's integration control input.
"""

from __future__ import annotations

import os

BROWSER_CHILD_ENV_ALLOWLIST = frozenset(
    {
        "APPDATA",
        "COMSPEC",
        "DISPLAY",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PLAYWRIGHT_BROWSERS_PATH",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMW6432",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WAYLAND_DISPLAY",
        "WINDIR",
        "XAUTHORITY",
        "XDG_RUNTIME_DIR",
    }
)


def browser_child_environment() -> dict[str, str]:
    """Return a fresh allowlisted snapshot without private or control data."""

    return {name: value for name, value in os.environ.items() if name.upper() in BROWSER_CHILD_ENV_ALLOWLIST}
