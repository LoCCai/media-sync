"""Credential-free smoke of the exact blank headed login-browser preflight."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from media_sync.integrations.mediacrawler.checkout import CheckoutValidationError, verify_mediacrawler_browser


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, type=Path, help="MediaCrawler runtime Python executable")
    arguments = parser.parse_args(argv)
    try:
        version = verify_mediacrawler_browser(arguments.python, interactive=True)
    except CheckoutValidationError:
        print(json.dumps({"ok": False, "code": "login_browser_probe_failed"}))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "browser": "bundled-chromium",
                "mode": "headed-persistent",
                "version": version,
                "live_qualification": "NOT_RUN",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
