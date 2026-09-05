from __future__ import annotations

import io
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
from PIL import Image, PngImagePlugin

from media_sync.application import creator_avatar as avatar
from media_sync.application import creator_avatar_worker as worker
from media_sync.application.creator_avatar_worker import decode_avatar, retrieve_avatar
from media_sync.media.errors import MediaDownloadError
from media_sync.media.network import NetworkLimits, SafeHttpClient, ValidatedTarget

URL = "https://i1.hdslb.com/bfs/face/" + "a" * 40 + ".jpg"
# These are synthetic policy examples, not observed or upstream-qualified avatars.
WB_URL = "https://tvax1.sinaimg.cn/crop.0.0.512.512.1024/avatar_Test-123.jpg"
TB_PORTRAIT = "tb.1." + "a" * 28
TB_URL = "https://gss0.bdstatic.com/6LZ1dD3d1sgCo2Kml5_Y_D3/sys/portrait/item/" + TB_PORTRAIT
AVATAR_URLS = [
    pytest.param(URL, id="bili"),
    pytest.param(WB_URL, id="wb"),
    pytest.param(TB_URL, id="tieba"),
    pytest.param(TB_URL + "?t=1234567890", id="tieba-timestamp"),
]


@pytest.mark.parametrize("suffix", ["", "?t=1234567890"])
def test_tieba_source_backed_shape_is_bound_to_exact_creator(suffix: str) -> None:
    url = TB_URL + suffix
    assert avatar.validate_creator_avatar_url(url) == url
    assert avatar.validate_creator_avatar_url(url, platform="tieba", creator_remote_id=TB_PORTRAIT) == url
    for platform, creator in [
        ("bili", TB_PORTRAIT),
        ("wb", TB_PORTRAIT),
        ("tieba", None),
        ("tieba", "tb.1." + "b" * 28),
    ]:
        with pytest.raises(ValueError, match="creator_avatar_url_invalid"):
            avatar.validate_creator_avatar_url(url, platform=platform, creator_remote_id=creator)


@pytest.mark.parametrize("host", [f"{prefix}{index}" for prefix in ("tva", "tvax") for index in range(1, 5)])
@pytest.mark.parametrize("path", ["crop.0.0.512.512.1024", "large", "bmiddle", "small", "thumbnail"])
@pytest.mark.parametrize("extension", ["jpg", "jpeg", "png", "webp"])
def test_synthetic_weibo_avatar_policy_accepts_explicit_shapes(host: str, path: str, extension: str) -> None:
    url = f"https://{host}.sinaimg.cn/{path}/avatar_Test-123.{extension}"
    assert avatar.validate_creator_avatar_url(url) == url
    with pytest.raises(ValueError, match="creator_avatar_url_invalid"):
        avatar.validate_bili_avatar_url(url)


@pytest.mark.parametrize("host", ["i0", "i1", "i2"])
@pytest.mark.parametrize("length", [32, 64])
@pytest.mark.parametrize("extension", ["jpg", "jpeg", "png", "webp"])
def test_bili_dedicated_validator_preserves_its_contract(host: str, length: int, extension: str) -> None:
    url = f"https://{host}.hdslb.com/bfs/face/{'a' * length}.{extension}"
    assert avatar.validate_bili_avatar_url(url) == url
    assert avatar.validate_creator_avatar_url(url) == url


@pytest.mark.parametrize("value", [None, True, 1, b"https://tvax1.sinaimg.cn/large/avatar.jpg", {}, []])
def test_generic_validator_rejects_non_strings(value: object) -> None:
    with pytest.raises(ValueError, match="creator_avatar_url_invalid"):
        avatar.validate_creator_avatar_url(value)


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
        WB_URL.replace("https://", "http://"),
        WB_URL + "?token=private",
        WB_URL + "#private",
        WB_URL + "@100w.webp",
        WB_URL + "\n",
        " " + WB_URL,
        WB_URL.replace("tvax1.sinaimg.cn", "127.0.0.1"),
        WB_URL.replace("tvax1.sinaimg.cn", "[::1]"),
        WB_URL.replace("tvax1.sinaimg.cn", "tvax1.sinaimg.cn.evil.test"),
        WB_URL.replace("tvax1.sinaimg.cn", "sub.tvax1.sinaimg.cn"),
        WB_URL.replace("tvax1.sinaimg.cn", "tvax1.sinaimg.cn."),
        WB_URL.replace("tvax1.sinaimg.cn", "TVAX1.sinaimg.cn"),
        WB_URL.replace("tvax1.sinaimg.cn", "user:private@tvax1.sinaimg.cn"),
        WB_URL.replace("tvax1.sinaimg.cn", "tvax1.sinaimg.cn:443"),
        WB_URL.replace("tvax1.sinaimg.cn", "tvax1.sinaimg.cn:8443"),
        WB_URL.replace("tvax1", "tvax0"),
        WB_URL.replace("tvax1", "tvax5"),
        WB_URL.replace("tvax1", "tva0"),
        WB_URL.replace("tvax1", "tva5"),
        WB_URL.replace("sinaimg.cn", "sinaimg.com"),
        WB_URL.replace(".cn/", ".cn\\"),
        WB_URL.replace(".cn/", ".cn//"),
        WB_URL.replace("crop.0.0.512.512.1024", "crop.0.0.512.512"),
        WB_URL.replace("crop.0.0.512.512.1024", "crop.0.0.512.512.100000"),
        WB_URL.replace("crop.0.0.512.512.1024", "crop.-1.0.512.512.1024"),
        WB_URL.replace("crop.0.0.512.512.1024", "original"),
        WB_URL.replace("/avatar_", "/../avatar_"),
        WB_URL.replace("/avatar_", "/%2e%2e/avatar_"),
        WB_URL.replace("avatar_Test-123", "avatar%2fprivate"),
        WB_URL.replace("avatar_Test-123", "avatar%2Ejpg"),
        WB_URL.replace("avatar_Test-123", "avatar;private"),
        WB_URL.replace("avatar_Test-123", "头像"),
        WB_URL.replace("avatar_Test-123", ""),
        WB_URL.replace("avatar_Test-123", "a" * 129),
        WB_URL.replace("avatar_Test-123", "a" * 300),
        WB_URL.replace(".jpg", ".svg"),
        WB_URL.replace(".jpg", ".gif"),
        WB_URL.replace(".jpg", ".JPG"),
        WB_URL + "/private",
        TB_URL.replace("https://", "http://"),
        TB_URL.replace("gss0.", "gss1."),
        TB_URL.replace("bdstatic.com", "bdstatic.com.evil.test"),
        TB_URL.replace("gss0.bdstatic.com", "127.0.0.1"),
        TB_URL.replace("gss0.bdstatic.com", "user@gss0.bdstatic.com"),
        TB_URL.replace("gss0.bdstatic.com", "gss0.bdstatic.com:443"),
        TB_URL.replace("/item/", "/small/"),
        TB_URL + ".jpg",
        TB_URL + "/private",
        TB_URL + "?token=private",
        TB_URL + "?t=123456789",
        TB_URL + "?t=12345678901",
        TB_URL + "?t=\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19\uff10",
        TB_URL + "?t=1234567890&t=1234567890",
        TB_URL + "?t=1234567890&token=private",
        TB_URL + "?t=%31%32%33%34%35%36%37%38%39%30",
        TB_URL + "#fragment",
        TB_URL + "\n",
        TB_URL[:-1] + ".",
        TB_URL[:-3] + "..a",
        TB_URL.replace(TB_PORTRAIT, "tb.1." + "a" * 27),
        TB_URL.replace(TB_PORTRAIT, "tb.1." + "a" * 32),
    ],
)
def test_url_closed_before_process_or_network(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_: object, **__: object) -> None:
        pytest.fail("invalid avatar reached subprocess")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(worker, "SafeHttpClient", forbidden)
    with pytest.raises(ValueError, match="creator_avatar_url_invalid"):
        avatar.validate_creator_avatar_url(url)
    assert avatar.fetch_creator_avatar(url) is None
    # The worker checks independently before constructing a resolver/client.
    with pytest.raises(ValueError, match="creator_avatar_url_invalid"):
        retrieve_avatar(url)


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
    def __init__(self, hostname: str, addresses: tuple[str, ...] = ("8.8.8.8",)) -> None:
        self.hostname = hostname
        self.addresses = addresses

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        assert hostname == self.hostname and port == 443
        return self.addresses


def _client(handler: Any, addresses: tuple[str, ...] = ("8.8.8.8",), *, url: str = URL) -> SafeHttpClient:
    hostname = urlsplit(url).hostname
    assert hostname is not None

    def transport(target: ValidatedTarget) -> httpx.MockTransport:
        assert target.url == url and target.hostname == hostname and target.port == 443
        assert target.address == "8.8.8.8"
        return httpx.MockTransport(handler)

    return SafeHttpClient(
        Resolver(hostname, addresses),
        transport_factory=transport,
        limits=NetworkLimits(max_redirects=0, timeout_seconds=7),
    )


@pytest.mark.parametrize("url", AVATAR_URLS)
def test_pinned_get_no_private_headers_and_static_result(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://user:private@127.0.0.1:9999")
    monkeypatch.setenv("HTTPS_PROXY", "http://user:private@127.0.0.1:9999")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == url and request.method == "GET"
        assert "cookie" not in request.headers and "authorization" not in request.headers
        assert "referer" not in request.headers and "origin" not in request.headers
        assert "proxy-authorization" not in request.headers
        assert request.headers["host"] == urlsplit(url).hostname
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, headers={"Content-Type": "image/png"}, stream=httpx.ByteStream(_png()))

    value = retrieve_avatar(url, client=_client(handler, url=url))
    assert value.startswith(b"\x89PNG") and b"must-not-survive" not in value
    with Image.open(io.BytesIO(value)) as image:
        assert image.format == "PNG" and image.n_frames == 1 and image.size == (16, 16)


@pytest.mark.parametrize("url", AVATAR_URLS)
@pytest.mark.parametrize(
    "addresses",
    [("127.0.0.1",), ("192.168.31.249",), ("169.254.169.254",), ("::1",), ("8.8.8.8", "::1")],
)
def test_private_or_mixed_dns_never_connects(url: str, addresses: tuple[str, ...]) -> None:
    def handler(_: object) -> None:
        pytest.fail("private DNS connected")

    with pytest.raises(MediaDownloadError):
        retrieve_avatar(url, client=_client(handler, addresses, url=url))


@pytest.mark.parametrize(
    "status,headers,payload",
    [
        (302, {"Location": "http://127.0.0.1/private"}, b""),
        (404, {"Content-Type": "image/png"}, b""),
        (200, {"Content-Type": "text/html"}, b"private"),
        (200, {"Content-Type": "image/png", "Content-Encoding": "gzip"}, b""),
        (200, {"Content-Type": "image/png", "Content-Length": str(avatar.MAX_AVATAR_BYTES + 1)}, b""),
        (200, {"Content-Type": "image/png", "Content-Length": "-1"}, b""),
        (200, {"Content-Type": "image/png", "Content-Length": "2.5"}, b""),
        (200, {"Content-Type": "image/png"}, b"x" * (avatar.MAX_AVATAR_BYTES + 1)),
    ],
    ids=["redirect", "status", "type", "encoding", "declared-overflow", "negative", "decimal", "stream-overflow"],
)
@pytest.mark.parametrize("url", AVATAR_URLS)
def test_network_rejects_redirect_type_encoding_and_overflow(
    url: str, status: int, headers: dict[str, str], payload: bytes
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, headers=headers, stream=httpx.ByteStream(payload))

    with pytest.raises((ValueError, MediaDownloadError)):
        retrieve_avatar(url, client=_client(handler, url=url))
    assert len(calls) == 1


@pytest.mark.parametrize("url", AVATAR_URLS)
def test_parent_deadline_and_private_environment(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIA_SYNC_PRIVATE_TEST", "private")
    monkeypatch.setenv("HTTP_PROXY", "http://user:private@127.0.0.1:9999")
    monkeypatch.setenv("HTTPS_PROXY", "http://user:private@127.0.0.1:9999")

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert argv[1] == "-I" and argv[-1].endswith("creator_avatar_worker.py")
        assert kwargs["input"] == url.encode("ascii")
        assert url not in argv
        assert kwargs["timeout"] == 10
        assert "MEDIA_SYNC_PRIVATE_TEST" not in kwargs["env"]
        assert "HTTP_PROXY" not in kwargs["env"] and "HTTPS_PROXY" not in kwargs["env"]
        assert kwargs["stderr"] == subprocess.DEVNULL
        raise subprocess.TimeoutExpired(argv, 10)

    monkeypatch.setattr(subprocess, "run", run)
    assert avatar.fetch_creator_avatar(url) is None


@pytest.mark.parametrize(
    "raw",
    [
        b"http://127.0.0.1/x",
        (WB_URL + "?token=private").encode("ascii"),
        WB_URL.replace(".jpg", ".svg").encode("ascii"),
        (TB_URL + "?t=1234567890&cookie=private").encode("ascii"),
    ],
    ids=["private-url", "wb-query", "wb-svg", "tieba-extra-query"],
)
def test_real_isolated_worker_rejects_invalid_input_without_network(raw: bytes) -> None:
    worker = Path(avatar.__file__).with_name("creator_avatar_worker.py")
    result = subprocess.run(
        [__import__("sys").executable, "-I", str(worker)],
        input=raw,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1 and result.stdout == b"" and result.stderr == b""
