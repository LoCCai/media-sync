from __future__ import annotations

import io
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image, PngImagePlugin

from media_sync.application import creator_avatar as avatar
from media_sync.application.creator_avatar_worker import decode_avatar, retrieve_avatar
from media_sync.media.errors import MediaDownloadError
from media_sync.media.network import NetworkLimits, SafeHttpClient

URL = "https://i1.hdslb.com/bfs/face/" + "a" * 40 + ".jpg"


def _png(*, animated: bool = False) -> bytes:
    output = io.BytesIO()
    meta = PngImagePlugin.PngInfo()
    meta.add_text("private", "must-not-survive")
    Image.new("RGB", (16, 16), "red").save(
        output,
        format="PNG",
        pnginfo=meta,
        save_all=animated,
        append_images=[Image.new("RGB", (16, 16), "blue")] if animated else [],
    )
    return output.getvalue()


@pytest.mark.parametrize(
    "url",
    [
        "http://i1.hdslb.com/bfs/face/" + "a" * 40 + ".jpg",
        URL + "?token=private",
        URL + "@100w.webp",
        URL + "#x",
        URL.replace("i1.hdslb.com", "127.0.0.1"),
        URL.replace("i1.hdslb.com", "i1.hdslb.com.evil.test"),
        URL.replace("i1.hdslb.com", "user@i1.hdslb.com"),
        URL.replace("i1.hdslb.com", "i1.hdslb.com:443"),
        URL.replace("/face/", "/archive/"),
        URL.replace(".jpg", ".svg"),
        "//i1.hdslb.com/x",
        "data:image/png,x",
        "",
    ],
)
def test_url_closed_before_process_or_network(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_: object, **__: object) -> None:
        pytest.fail("invalid avatar reached subprocess")

    monkeypatch.setattr(subprocess, "run", forbidden)
    assert avatar.fetch_creator_avatar(url) is None


def test_decoder_reencodes_and_discards_metadata() -> None:
    value = decode_avatar(_png())
    with Image.open(io.BytesIO(value)) as image:
        assert image.format == "PNG" and image.size == (16, 16)
        assert "private" not in image.info
    assert b"must-not-survive" not in value


@pytest.mark.parametrize(
    "value",
    [b"", b"<svg></svg>", b"<html>error</html>", b"x" * (avatar.MAX_AVATAR_BYTES + 1)],
    ids=["empty", "svg", "html", "overflow"],
)
def test_bad_image_rejected(value: bytes) -> None:
    with pytest.raises((ValueError, OSError)):
        decode_avatar(value)


def test_animated_and_excessive_dimensions_rejected() -> None:
    with pytest.raises(ValueError):
        decode_avatar(_png(animated=True))
    output = io.BytesIO()
    Image.new("RGB", (3000, 3000)).save(output, format="PNG")
    with pytest.raises((ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError)):
        decode_avatar(output.getvalue())


class Resolver:
    def __init__(self, addresses: tuple[str, ...] = ("8.8.8.8",)) -> None:
        self.addresses = addresses

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        assert hostname == "i1.hdslb.com" and port == 443
        return self.addresses


def _client(handler: Any, addresses: tuple[str, ...] = ("8.8.8.8",)) -> SafeHttpClient:
    return SafeHttpClient(
        Resolver(addresses),
        transport_factory=lambda target: httpx.MockTransport(handler),
        limits=NetworkLimits(max_redirects=0, timeout_seconds=7),
    )


def test_pinned_get_no_private_headers_and_static_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == URL
        assert "cookie" not in request.headers and "authorization" not in request.headers
        assert "referer" not in request.headers and "origin" not in request.headers
        return httpx.Response(200, headers={"Content-Type": "image/png"}, stream=httpx.ByteStream(_png()))

    assert retrieve_avatar(URL, client=_client(handler)).startswith(b"\x89PNG")


@pytest.mark.parametrize("addresses", [("127.0.0.1",), ("192.168.31.249",), ("8.8.8.8", "::1")])
def test_private_or_mixed_dns_never_connects(addresses: tuple[str, ...]) -> None:
    def handler(_: object) -> None:
        pytest.fail("private DNS connected")

    with pytest.raises(MediaDownloadError):
        retrieve_avatar(URL, client=_client(handler, addresses))


@pytest.mark.parametrize(
    "status,headers,payload",
    [
        (302, {"Location": "http://127.0.0.1/private"}, b""),
        (404, {"Content-Type": "image/png"}, b""),
        (200, {"Content-Type": "text/html"}, b"private"),
        (200, {"Content-Type": "image/png", "Content-Encoding": "gzip"}, b""),
        (200, {"Content-Type": "image/png", "Content-Length": str(avatar.MAX_AVATAR_BYTES + 1)}, b""),
        (200, {"Content-Type": "image/png"}, b"x" * (avatar.MAX_AVATAR_BYTES + 1)),
    ],
    ids=["redirect", "status", "type", "encoding", "declared-overflow", "stream-overflow"],
)
def test_network_rejects_redirect_type_encoding_and_overflow(
    status: int, headers: dict[str, str], payload: bytes
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, headers=headers, stream=httpx.ByteStream(payload))

    with pytest.raises((ValueError, MediaDownloadError)):
        retrieve_avatar(URL, client=_client(handler))
    assert len(calls) == 1


def test_parent_deadline_and_private_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIA_SYNC_PRIVATE_TEST", "private")

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert argv[1] == "-I" and argv[-1].endswith("creator_avatar_worker.py")
        assert kwargs["input"] == URL.encode("ascii")
        assert kwargs["timeout"] == 10
        assert "MEDIA_SYNC_PRIVATE_TEST" not in kwargs["env"]
        raise subprocess.TimeoutExpired(argv, 10)

    monkeypatch.setattr(subprocess, "run", run)
    assert avatar.fetch_creator_avatar(URL) is None


def test_real_isolated_worker_rejects_invalid_input_without_network() -> None:
    worker = Path(avatar.__file__).with_name("creator_avatar_worker.py")
    result = subprocess.run(
        [__import__("sys").executable, "-I", str(worker)],
        input=b"http://127.0.0.1/x",
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1 and result.stdout == b"" and result.stderr == b""
