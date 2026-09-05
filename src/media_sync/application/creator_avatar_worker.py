"""Disposable network/decoder process. Its only output is bounded static PNG."""

from __future__ import annotations

import importlib
import io
import sys
import time
import warnings
from pathlib import Path
from typing import Any

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from media_sync.application.creator_avatar import (
    MAX_AVATAR_BYTES,
    MAX_AVATAR_PIXELS,
    validate_bili_avatar_url,
)
from media_sync.media.network import NetworkLimits, SafeHttpClient, SocketAddressResolver


def decode_avatar(payload: bytes) -> bytes:
    if not 0 < len(payload) <= MAX_AVATAR_BYTES:
        raise ValueError("creator_avatar_invalid")
    image_module: Any = importlib.import_module("PIL.Image")
    image_module.MAX_IMAGE_PIXELS = MAX_AVATAR_PIXELS
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with image_module.open(io.BytesIO(payload)) as probe:
            if (
                probe.format not in {"JPEG", "PNG", "WEBP"}
                or probe.width * probe.height > MAX_AVATAR_PIXELS
                or getattr(probe, "n_frames", 1) != 1
            ):
                raise ValueError("creator_avatar_invalid")
            probe.verify()
        with image_module.open(io.BytesIO(payload)) as source:
            source.load()
            source.thumbnail((512, 512))
            # A fresh image strips EXIF, ICC, text chunks and other metadata.
            controlled = image_module.new("RGBA", source.size)
            controlled.paste(source.convert("RGBA"))
            output = io.BytesIO()
            controlled.save(output, format="PNG")
    value = output.getvalue()
    if not 8 < len(value) <= MAX_AVATAR_BYTES:
        raise ValueError("creator_avatar_invalid")
    return value


def retrieve_avatar(url: str, *, client: SafeHttpClient | None = None) -> bytes:
    candidate = validate_bili_avatar_url(url)
    network = client or SafeHttpClient(
        SocketAddressResolver(), limits=NetworkLimits(max_redirects=0, timeout_seconds=7, max_url_chars=256)
    )
    deadline = time.monotonic() + 7
    chunks = bytearray()
    with network.stream(candidate, timeout_seconds=7) as (response, target):
        if target.url != candidate or response.status_code != 200:
            raise ValueError("creator_avatar_invalid")
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise ValueError("creator_avatar_invalid")
        if response.headers.get("content-type", "").split(";", 1)[0].strip().lower() not in {
            "image/png",
            "image/jpeg",
            "image/webp",
        }:
            raise ValueError("creator_avatar_invalid")
        length = response.headers.get("content-length")
        if length is not None and (not length.isascii() or not length.isdecimal() or int(length) > MAX_AVATAR_BYTES):
            raise ValueError("creator_avatar_invalid")
        for chunk in response.iter_raw(chunk_size=64 * 1024):
            if time.monotonic() >= deadline or len(chunks) + len(chunk) > MAX_AVATAR_BYTES:
                raise ValueError("creator_avatar_invalid")
            chunks.extend(chunk)
    return decode_avatar(bytes(chunks))


def main() -> int:
    try:
        # POSIX adds kernel bounds; Windows still has the parent wall deadline,
        # closed input/output and image dimension bounds. No child is spawned.
        if sys.platform != "win32":
            resource = importlib.import_module("resource")
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
        raw = sys.stdin.buffer.read(257)
        if not 0 < len(raw) <= 256:
            return 1
        result = retrieve_avatar(raw.decode("ascii"))
        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
