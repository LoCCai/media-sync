"""Bounded, isolated Bili/Weibo avatar retrieval; no arbitrary URL proxy."""

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
# Deliberately partial: only static crop/size paths on these Sina avatar CDNs.
# No wildcard domain, percent escapes, query, port, default-avatar redirects or
# transforms. Unknown shapes are optional-image misses, not lookup failures.
_WEIBO_AVATAR = re.compile(
    r"https://(?:tvax[1-4]|tva[1-4])\.sinaimg\.cn/"
    r"(?:crop\.[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}|"
    r"(?:large|bmiddle|small|thumbnail))/[A-Za-z0-9_-]{1,128}\.(?:jpg|jpeg|png|webp)\Z"
)


def validate_bili_avatar_url(value: object) -> str:
    if not isinstance(value, str) or _BILI_AVATAR.fullmatch(value) is None:
        raise ValueError("creator_avatar_url_invalid")
    return value


def validate_creator_avatar_url(value: object, *, platform: str | None = None) -> str:
    if type(value) is not str or len(value) > 256:
        raise ValueError("creator_avatar_url_invalid")
    rules = {"bili": _BILI_AVATAR, "wb": _WEIBO_AVATAR}
    if platform is not None and platform not in rules:
        raise ValueError("creator_avatar_url_invalid")
    allowed = tuple(rules.values()) if platform is None else (rules[platform],)
    if not any(rule.fullmatch(value) is not None for rule in allowed):
        raise ValueError("creator_avatar_url_invalid")
    return value


def fetch_creator_avatar(url: str | None) -> bytes | None:
    """Return controlled PNG bytes or no candidate, never error/remote text.

    DNS, HTTP streaming and image decoding all run in one disposable child;
    the parent deadline therefore also bounds a stuck resolver or decoder.
    The child does not spawn descendants or read application credentials.
    """

    try:
        candidate = validate_creator_avatar_url(url)
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
