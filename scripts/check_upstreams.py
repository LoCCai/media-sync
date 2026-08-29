"""Verify local upstream checkouts against upstreams.lock.json."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    lock_path = root / "upstreams.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    for entry in lock["upstreams"]:
        checkout = root / entry["local_path"]
        if not checkout.is_dir():
            errors.append(f"{entry['name']}: checkout missing at {entry['local_path']}")
            continue
        try:
            actual_commit = git(checkout, "rev-parse", "HEAD")
            actual_remote = git(checkout, "remote", "get-url", "origin")
        except (OSError, subprocess.CalledProcessError) as exc:
            errors.append(f"{entry['name']}: git inspection failed: {exc}")
            continue
        if actual_commit != entry["commit"]:
            errors.append(f"{entry['name']}: commit {actual_commit} != {entry['commit']}")
        if actual_remote.rstrip("/") != entry["repository"].rstrip("/"):
            errors.append(f"{entry['name']}: remote {actual_remote!r} != {entry['repository']!r}")

    if errors:
        print("Upstream validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Upstreams OK ({len(lock['upstreams'])} locked checkouts verified).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
