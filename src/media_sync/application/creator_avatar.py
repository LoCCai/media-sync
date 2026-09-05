"""Bounded, isolated Bili avatar retrieval; no arbitrary URL proxy."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_PIXELS = 8_000_000
AVATAR_TIMEOUT_SECONDS = 10.0
# The locked upstream returns Bili's b(0..2) avatar CDN form. Unknown
# hosts, image transforms, queries, redirects and alternate paths fail closed.
_BILI_AVATAR = re.compile(r"https://i[012]\.hdslb\.com/bfs/face/[0-9a-f]{32,64}\.(?:jpg|jpeg|png|webp)\Z")


def validate_bili_avatar_url(value: object) -> str:
    if not isinstance(value, str) or _BILI_AVATAR.fullmatch(value) is None:
        raise ValueError("creator_avatar_url_invalid")
    return value


def fetch_creator_avatar(url: str | None) -> bytes | None:
    """Return controlled PNG bytes or no candidate, never error/remote text.

    DNS, HTTP streaming and image decoding all run in one disposable child;
    the parent deadline therefore also bounds a stuck resolver or decoder.
    The child does not spawn descendants or read application credentials.
    """

    try:
        candidate = validate_bili_avatar_url(url)
    except ValueError:
        return None
    environment = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ}
    try:
        result = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).with_name("creator_avatar_worker.py"))],
            input=candidate.encode("ascii"),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=AVATAR_TIMEOUT_SECONDS,
            check=False,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not 8 < len(result.stdout) <= MAX_AVATAR_BYTES:
        return None
    return result.stdout if result.stdout.startswith(b"\x89PNG\r\n\x1a\n") else None
