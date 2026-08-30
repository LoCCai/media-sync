from __future__ import annotations

from collections.abc import Callable, Sequence

import httpx
import pytest

from media_sync.media import MediaDownloadError, NetworkLimits, SafeHttpClient, ValidatedTarget, validate_target


class _Resolver:
    def __init__(self, values: dict[str, Sequence[str]]) -> None:
        self.values = values
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        self.calls.append((hostname, port))
        return self.values.get(hostname, ())


def _factory(
    handler: Callable[[httpx.Request], httpx.Response],
    targets: list[ValidatedTarget],
) -> Callable[[ValidatedTarget], httpx.BaseTransport]:
    def build(target: ValidatedTarget) -> httpx.BaseTransport:
        targets.append(target)
        return httpx.MockTransport(handler)

    return build


def test_safe_http_pins_validated_address_and_sets_origin_headers() -> None:
    resolver = _Resolver({"media.test": ("8.8.8.8", "1.1.1.1")})
    targets: list[ValidatedTarget] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["host"] == "media.test"
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, content=b"ok")

    client = SafeHttpClient(resolver, transport_factory=_factory(handler, targets))
    with client.stream("https://media.test/object") as (response, target):
        assert response.read() == b"ok"
        assert target.address == "1.1.1.1"

    assert targets == [target]
    assert resolver.calls == [("media.test", 443)]


def test_each_redirect_is_resolved_and_public_to_private_is_rejected() -> None:
    resolver = _Resolver({"public.test": ("8.8.8.8",), "private.test": ("127.0.0.1",)})
    targets: list[ValidatedTarget] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://private.test/internal"})

    client = SafeHttpClient(resolver, transport_factory=_factory(handler, targets))
    with pytest.raises(MediaDownloadError) as caught, client.stream("https://public.test/start"):
        pass

    assert caught.value.code == "network_address_forbidden"
    assert [target.hostname for target in targets] == ["public.test"]
    assert resolver.calls == [("public.test", 443), ("private.test", 443)]


def test_mixed_public_and_private_dns_fails_before_transport() -> None:
    resolver = _Resolver({"mixed.test": ("8.8.8.8", "10.0.0.4")})

    with pytest.raises(MediaDownloadError) as caught:
        validate_target("https://mixed.test/file", resolver)

    assert caught.value.code == "network_dns_mixed"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/file",
        "http://[::1]/file",
        "http://169.254.169.254/latest/meta-data",
        "http://0.0.0.0/file",
        "file:///etc/passwd",
        "https://user:pass@media.test/file",
        "https://media.test/file#fragment",
        "https://media.test/file\x00suffix",
        "https://media.test/file\x1fsuffix",
    ],
)
def test_forbidden_literal_and_ambiguous_network_targets_fail_closed(url: str) -> None:
    resolver = _Resolver({})

    with pytest.raises(MediaDownloadError) as caught:
        validate_target(url, resolver)

    assert caught.value.code in {"network_address_forbidden", "network_url_invalid"}
    assert url not in str(caught.value)


def test_redirect_loop_and_limit_are_bounded() -> None:
    resolver = _Resolver({"media.test": ("8.8.8.8",)})

    def loop(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": str(request.url)})

    client = SafeHttpClient(resolver, transport_factory=lambda _target: httpx.MockTransport(loop))
    with pytest.raises(MediaDownloadError) as caught, client.stream("https://media.test/a"):
        pass
    assert caught.value.code == "download_redirect_invalid"

    def onward(request: httpx.Request) -> httpx.Response:
        path_number = int(request.url.path.removeprefix("/"))
        return httpx.Response(302, headers={"Location": f"/{path_number + 1}"})

    limited = SafeHttpClient(
        resolver,
        transport_factory=lambda _target: httpx.MockTransport(onward),
        limits=NetworkLimits(max_redirects=1),
    )
    with pytest.raises(MediaDownloadError) as caught, limited.stream("https://media.test/0"):
        pass
    assert caught.value.code == "download_redirect_limit"


def test_response_header_limits_are_fixed_and_redacted() -> None:
    resolver = _Resolver({"media.test": ("8.8.8.8",)})
    sentinel = "header-secret-value"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"X-Large": sentinel})

    client = SafeHttpClient(
        resolver,
        transport_factory=lambda _target: httpx.MockTransport(handler),
        limits=NetworkLimits(max_header_line_bytes=10),
    )
    with pytest.raises(MediaDownloadError) as caught, client.stream("https://media.test/file"):
        pass
    assert caught.value.code == "download_header_limit"
    assert sentinel not in str(caught.value)


def test_cross_origin_redirect_does_not_forward_range_validator() -> None:
    resolver = _Resolver({"origin.test": ("8.8.8.8",), "cdn.test": ("1.1.1.1",)})
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "origin.test":
            assert request.headers["if-range"] == '"private-validator"'
            return httpx.Response(307, headers={"Location": "https://cdn.test/file?signature=runtime"})
        assert "if-range" not in request.headers
        assert "range" not in request.headers
        return httpx.Response(200, content=b"fresh")

    client = SafeHttpClient(resolver, transport_factory=lambda _target: httpx.MockTransport(handler))
    with client.stream(
        "https://origin.test/file",
        headers={"Range": "bytes=4-", "If-Range": '"private-validator"'},
    ) as (response, _target):
        assert response.read() == b"fresh"
    assert len(requests) == 2


def test_https_redirect_downgrade_is_rejected() -> None:
    resolver = _Resolver({"media.test": ("8.8.8.8",)})

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://media.test/plain"})

    client = SafeHttpClient(resolver, transport_factory=lambda _target: httpx.MockTransport(handler))
    with pytest.raises(MediaDownloadError) as caught, client.stream("https://media.test/start"):
        pass
    assert caught.value.code == "download_redirect_invalid"
