"""SSRF-resistant HTTP primitives with DNS-to-connection pinning."""

from __future__ import annotations

import contextlib
import ipaddress
import socket
import ssl
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, TypeAlias, cast
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpcore
import httpx

from media_sync.media.errors import MediaDownloadError

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
SocketOption: TypeAlias = tuple[int, int, int] | tuple[int, int, bytes | bytearray] | tuple[int, int, None, int]


class AddressResolver(Protocol):
    """Injectable hostname resolver used before each connection."""

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        """Return every address the hostname can currently resolve to."""
        ...


class SocketAddressResolver:
    """System resolver that returns a stable, de-duplicated address set."""

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        try:
            records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError) as exc:
            raise MediaDownloadError("network_dns_failed") from exc
        return tuple(sorted({str(record[4][0]) for record in records}))


@dataclass(frozen=True, slots=True)
class ValidatedTarget:
    """One runtime URL and the public address selected for its connection."""

    url: str = field(repr=False)
    scheme: str
    hostname: str
    port: int
    address: str

    @property
    def host_header(self) -> str:
        host = f"[{self.hostname}]" if ":" in self.hostname else self.hostname
        default_port = 80 if self.scheme == "http" else 443
        return host if self.port == default_port else f"{host}:{self.port}"


TransportFactory = Callable[[ValidatedTarget], httpx.BaseTransport]


@dataclass(frozen=True, slots=True)
class NetworkLimits:
    """Hard limits for one redirect chain."""

    max_redirects: int = 5
    timeout_seconds: float = 120.0
    max_url_chars: int = 4096
    max_header_count: int = 64
    max_header_line_bytes: int = 8192
    max_header_bytes: int = 65536

    def __post_init__(self) -> None:
        if self.max_redirects < 0:
            raise ValueError("max_redirects must be non-negative")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        for value in (
            self.max_url_chars,
            self.max_header_count,
            self.max_header_line_bytes,
            self.max_header_bytes,
        ):
            if value <= 0:
                raise ValueError("network size limits must be positive")


def _canonical_runtime_url(raw: str, *, limit: int) -> str:
    if not isinstance(raw, str) or raw != raw.strip() or len(raw) > limit:
        raise MediaDownloadError("network_url_invalid")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in raw):
        raise MediaDownloadError("network_url_invalid")
    if "\\" in raw or "#" in raw:
        raise MediaDownloadError("network_url_invalid")
    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise MediaDownloadError("network_url_invalid") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or hostname is None:
        raise MediaDownloadError("network_url_invalid")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise MediaDownloadError("network_url_invalid")
    try:
        canonical_host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise MediaDownloadError("network_url_invalid") from exc
    if not canonical_host or "%" in canonical_host:
        raise MediaDownloadError("network_url_invalid")
    default_port = 80 if scheme == "http" else 443
    effective_port = default_port if port is None else port
    if effective_port <= 0 or effective_port > 65535:
        raise MediaDownloadError("network_url_invalid")
    bracketed = f"[{canonical_host}]" if ":" in canonical_host else canonical_host
    authority = bracketed if effective_port == default_port else f"{bracketed}:{effective_port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, authority, path, parsed.query, ""))


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    hostname = parsed.hostname
    if hostname is None:  # pragma: no cover - callers canonicalize first
        raise MediaDownloadError("network_url_invalid")
    return parsed.scheme, hostname, parsed.port or (80 if parsed.scheme == "http" else 443)


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_unspecified
        and not address.is_reserved
    )


def validate_target(url: str, resolver: AddressResolver, *, max_url_chars: int = 4096) -> ValidatedTarget:
    """Validate a URL and every DNS answer, then choose one pinned public IP."""

    canonical_url = _canonical_runtime_url(url, limit=max_url_chars)
    parsed = urlsplit(canonical_url)
    hostname = parsed.hostname
    if hostname is None:  # pragma: no cover - canonicalization proves this
        raise MediaDownloadError("network_url_invalid")
    port = parsed.port or (80 if parsed.scheme == "http" else 443)
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]
    if literal is not None:
        if not _is_public(literal):
            raise MediaDownloadError("network_address_forbidden")
        addresses = (literal,)
    else:
        try:
            raw_addresses = resolver.resolve(hostname, port)
        except MediaDownloadError:
            raise
        except Exception as exc:
            raise MediaDownloadError("network_dns_failed") from exc
        if not raw_addresses:
            raise MediaDownloadError("network_dns_failed")
        parsed_addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        try:
            for raw_address in raw_addresses:
                parsed_addresses.append(ipaddress.ip_address(raw_address))
        except ValueError as exc:
            raise MediaDownloadError("network_dns_failed") from exc
        public = [_is_public(address) for address in parsed_addresses]
        if any(public) and not all(public):
            raise MediaDownloadError("network_dns_mixed")
        if not all(public):
            raise MediaDownloadError("network_address_forbidden")
        addresses = tuple(parsed_addresses)
    selected = min(addresses, key=lambda item: (item.version, int(item)))
    return ValidatedTarget(
        url=canonical_url,
        scheme=parsed.scheme,
        hostname=hostname,
        port=port,
        address=str(selected),
    )


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    def __init__(self, target: ValidatedTarget) -> None:
        self._target = target
        self._delegate = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SocketOption] | None = None,
    ) -> httpcore.NetworkStream:
        if host.rstrip(".").lower() != self._target.hostname or port != self._target.port:
            raise httpcore.ConnectError("connection target rejected")
        return self._delegate.connect_tcp(
            self._target.address,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[SocketOption] | None = None,
    ) -> httpcore.NetworkStream:
        raise httpcore.ConnectError("unix sockets are disabled")


class _CoreResponseStream(httpx.SyncByteStream):
    def __init__(self, stream: Iterable[bytes]) -> None:
        self._stream = stream

    def __iter__(self) -> Iterator[bytes]:
        try:
            yield from self._stream
        except Exception as exc:
            raise MediaDownloadError("download_transport") from exc

    def close(self) -> None:
        close = getattr(self._stream, "close", None)
        if close is not None:
            close()


class PinnedHTTPTransport(httpx.BaseTransport):
    """httpcore transport that connects to a validated IP while retaining Host/SNI."""

    def __init__(self, target: ValidatedTarget) -> None:
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            max_connections=1,
            max_keepalive_connections=0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=_PinnedNetworkBackend(target),
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        try:
            response = self._pool.handle_request(core_request)
        except Exception as exc:
            raise MediaDownloadError("download_transport") from exc
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_CoreResponseStream(cast(Iterable[bytes], response.stream)),
            extensions=response.extensions,
        )

    def close(self) -> None:
        self._pool.close()


def _check_headers(response: httpx.Response, limits: NetworkLimits) -> None:
    raw_headers = response.headers.raw
    if len(raw_headers) > limits.max_header_count:
        raise MediaDownloadError("download_header_limit")
    total = 0
    for name, value in raw_headers:
        line_size = len(name) + len(value) + 2
        if line_size > limits.max_header_line_bytes:
            raise MediaDownloadError("download_header_limit")
        total += line_size
        if total > limits.max_header_bytes:
            raise MediaDownloadError("download_header_limit")


class SafeHttpClient:
    """Manual redirect client that validates and pins every network hop."""

    def __init__(
        self,
        resolver: AddressResolver,
        *,
        transport_factory: TransportFactory | None = None,
        limits: NetworkLimits | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._resolver = resolver
        self._transport_factory = transport_factory or PinnedHTTPTransport
        self.limits = limits or NetworkLimits()
        self._monotonic = monotonic

    @contextlib.contextmanager
    def stream(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> Iterator[tuple[httpx.Response, ValidatedTarget]]:
        """Yield the first non-redirect response in a bounded, validated chain."""

        started = self._monotonic()
        total_timeout = min(timeout_seconds or self.limits.timeout_seconds, self.limits.timeout_seconds)
        current = _canonical_runtime_url(url, limit=self.limits.max_url_chars)
        visited: set[str] = set()
        request_headers: dict[str, str] = {}
        for raw_name, value in (headers or {}).items():
            name = raw_name.lower()
            if name not in {"range", "if-range"} or name in request_headers:
                raise MediaDownloadError("download_range_invalid")
            request_headers[name] = value
        request_headers.update({"Accept": "*/*", "Accept-Encoding": "identity"})
        for redirect_count in range(self.limits.max_redirects + 1):
            if current in visited:
                raise MediaDownloadError("download_redirect_invalid")
            visited.add(current)
            elapsed = self._monotonic() - started
            remaining = total_timeout - elapsed
            if remaining <= 0:
                raise MediaDownloadError("download_timeout")
            target = validate_target(current, self._resolver, max_url_chars=self.limits.max_url_chars)
            transport = self._transport_factory(target)
            client = httpx.Client(
                transport=transport,
                follow_redirects=False,
                trust_env=False,
                timeout=httpx.Timeout(remaining),
            )
            response: httpx.Response | None = None
            yielding = False
            try:
                outgoing = dict(request_headers)
                outgoing["Host"] = target.host_header
                request = client.build_request("GET", target.url, headers=outgoing)
                response = client.send(request, stream=True)
                _check_headers(response, self.limits)
                if response.status_code not in _REDIRECT_STATUSES:
                    try:
                        yielding = True
                        yield response, target
                    finally:
                        response.close()
                    return
                locations = response.headers.get_list("location")
                if len(locations) != 1:
                    raise MediaDownloadError("download_redirect_invalid")
                if redirect_count >= self.limits.max_redirects:
                    raise MediaDownloadError("download_redirect_limit")
                redirected = _canonical_runtime_url(
                    urljoin(target.url, locations[0]),
                    limit=self.limits.max_url_chars,
                )
                if target.scheme == "https" and urlsplit(redirected).scheme == "http":
                    raise MediaDownloadError("download_redirect_invalid")
                if _origin(target.url) != _origin(redirected):
                    request_headers.pop("range", None)
                    request_headers.pop("if-range", None)
                current = redirected
            except MediaDownloadError:
                raise
            except httpx.TimeoutException as exc:
                raise MediaDownloadError("download_timeout") from exc
            except httpx.HTTPError as exc:
                raise MediaDownloadError("download_transport") from exc
            except Exception as exc:
                if yielding:
                    raise
                raise MediaDownloadError("download_transport") from exc
            finally:
                if response is not None and not response.is_closed:
                    response.close()
                client.close()
        raise MediaDownloadError("download_redirect_limit")  # pragma: no cover


__all__ = [
    "AddressResolver",
    "NetworkLimits",
    "PinnedHTTPTransport",
    "SafeHttpClient",
    "SocketAddressResolver",
    "TransportFactory",
    "ValidatedTarget",
    "validate_target",
]
