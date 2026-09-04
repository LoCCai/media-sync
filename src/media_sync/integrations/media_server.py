"""SSRF-resistant Emby/Jellyfin inspection and targeted refresh connector."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import re
import socket
import ssl
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from queue import SimpleQueue
from types import TracebackType
from typing import Literal, Protocol, TypeAlias, cast
from urllib.parse import urlsplit

import httpcore
import httpx

from media_sync.config import MediaServerProfile, MediaServerSafeSummary
from media_sync.ports.media_server import (
    MediaServerError,
    MediaServerItemLookupResult,
    MediaServerLookupTarget,
    MediaServerProbeResult,
    MediaServerScanResult,
)
from media_sync.security.secrets import SecretError, SecretReference, SecretValue

SocketOption: TypeAlias = tuple[int, int, int] | tuple[int, int, bytes | bytearray] | tuple[int, int, None, int]

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_TARGETED_SCAN_UNSUPPORTED = frozenset({404, 405, 501})
_EMBY_SCAN_QUERY: tuple[tuple[str, str], ...] = (
    ("Recursive", "true"),
    ("MetadataRefreshMode", "Default"),
    ("ImageRefreshMode", "Default"),
    ("ReplaceAllMetadata", "false"),
    ("ReplaceAllImages", "false"),
)
_JELLYFIN_SCAN_QUERY: tuple[tuple[str, str], ...] = (
    ("metadataRefreshMode", "Default"),
    ("imageRefreshMode", "Default"),
    ("replaceAllMetadata", "false"),
    ("replaceAllImages", "false"),
)
_EMBY_LOOKUP_LIMIT = 2
_WIRE_FIXED_MESSAGE = "[REDACTED MEDIA-SERVER WIRE EVENT]"
_WIRE_LOGGER_ROOTS = ("httpcore", "httpx")
_MIN_SENSITIVE_SUBSTRING_CHARS = 8
_LOOKUP_INCOMPLETE_CODES = frozenset(
    {
        "media_server_timeout",
        "media_server_header_limit",
        "media_server_body_limit",
        "media_server_response_invalid",
        "media_server_schema_invalid",
    }
)
_LogRecordFactory: TypeAlias = Callable[..., logging.LogRecord]
_LoggerMakeRecord: TypeAlias = Callable[..., logging.LogRecord]
_STANDARD_LOG_RECORD_FIELDS = frozenset(
    {
        *logging.LogRecord("", 0, "", 0, "", (), None).__dict__,
        "asctime",
        "message",
    }
)


class _SensitiveWireLogFilter(logging.Filter):
    def __init__(self, values: Sequence[str], *, replace_message: bool) -> None:
        super().__init__()
        self._values = tuple(sorted({value for value in values if value}, key=len, reverse=True))
        self._replace_message = replace_message

    def filter(self, record: logging.LogRecord) -> bool:
        if self._replace_message:
            message = _WIRE_FIXED_MESSAGE
        else:
            try:
                message = record.getMessage()
            except BaseException:
                message = _WIRE_FIXED_MESSAGE
            for value in self._values:
                message = message.replace(value, "[REDACTED]")
        record.msg = message
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        for key in tuple(record.__dict__):
            if key not in _STANDARD_LOG_RECORD_FIELDS:
                record.__dict__[key] = "[REDACTED]"
        return True


_wire_log_factory_lock = threading.Lock()
_wire_log_redactors: ContextVar[tuple[_SensitiveWireLogFilter, ...]] = ContextVar(
    "media_server_wire_log_redactors",
    default=(),
)
_wire_log_factory_users = 0
_wire_log_factory: _LogRecordFactory | None = None
_wire_log_previous_factory: _LogRecordFactory | None = None
_wire_log_make_record: _LoggerMakeRecord | None = None
_wire_log_previous_make_record: _LoggerMakeRecord | None = None


def _set_logger_make_record(value: _LoggerMakeRecord) -> None:
    logging.Logger.makeRecord = value  # type: ignore[method-assign]


def _install_wire_log_factory() -> None:
    global _wire_log_factory
    global _wire_log_factory_users
    global _wire_log_previous_factory
    global _wire_log_make_record
    global _wire_log_previous_make_record

    with _wire_log_factory_lock:
        if _wire_log_factory_users == 0:
            previous = logging.getLogRecordFactory()

            def factory(*args: object, **kwargs: object) -> logging.LogRecord:
                record = previous(*args, **kwargs)
                record_name = record.name or ""
                if any(record_name == root or record_name.startswith(f"{root}.") for root in _WIRE_LOGGER_ROOTS):
                    for active_redaction in _wire_log_redactors.get():
                        active_redaction.filter(record)
                return record

            _wire_log_previous_factory = previous
            _wire_log_factory = factory
            logging.setLogRecordFactory(factory)
            previous_make_record = logging.Logger.makeRecord

            def make_record(
                logger: logging.Logger,
                name: str,
                level: int,
                filename: str,
                line_number: int,
                message: object,
                args: tuple[object, ...] | Mapping[str, object],
                exception_info: (
                    tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None] | None
                ),
                function_name: str | None = None,
                extra: Mapping[str, object] | None = None,
                stack_info: str | None = None,
            ) -> logging.LogRecord:
                record = previous_make_record(
                    logger,
                    name,
                    level,
                    filename,
                    line_number,
                    message,
                    args,
                    exception_info,
                    function_name,
                    extra,
                    stack_info,
                )
                record_name = record.name or ""
                if any(record_name == root or record_name.startswith(f"{root}.") for root in _WIRE_LOGGER_ROOTS):
                    for active_redaction in _wire_log_redactors.get():
                        active_redaction.filter(record)
                return record

            _wire_log_previous_make_record = previous_make_record
            _wire_log_make_record = make_record
            _set_logger_make_record(make_record)
        _wire_log_factory_users += 1


def _remove_wire_log_factory() -> None:
    global _wire_log_factory
    global _wire_log_factory_users
    global _wire_log_previous_factory
    global _wire_log_make_record
    global _wire_log_previous_make_record

    with _wire_log_factory_lock:
        _wire_log_factory_users -= 1
        if _wire_log_factory_users:
            return
        factory = _wire_log_factory
        previous = _wire_log_previous_factory
        if factory is not None and previous is not None and logging.getLogRecordFactory() is factory:
            logging.setLogRecordFactory(previous)
        make_record = _wire_log_make_record
        previous_make_record = _wire_log_previous_make_record
        if make_record is not None and previous_make_record is not None and logging.Logger.makeRecord is make_record:
            _set_logger_make_record(previous_make_record)
        _wire_log_factory = None
        _wire_log_previous_factory = None
        _wire_log_make_record = None
        _wire_log_previous_make_record = None


@contextmanager
def _redact_wire_logs(*values: str, replace_message: bool = False) -> Iterator[None]:
    """Redact this request's selectors without changing process logger policy."""

    redaction = _SensitiveWireLogFilter(values, replace_message=replace_message)
    token = _wire_log_redactors.set((*_wire_log_redactors.get(), redaction))
    _install_wire_log_factory()
    try:
        yield
    finally:
        try:
            _wire_log_redactors.reset(token)
        finally:
            _remove_wire_log_factory()


class MediaServerAddressResolver(Protocol):
    """Resolve every address for the already-configured origin hostname."""

    def resolve(self, hostname: str, port: int) -> Sequence[str]: ...


class MediaServerSecretResolver(Protocol):
    """Resolve a typed secret at the final connector boundary."""

    def resolve(self, reference: SecretReference | str) -> SecretValue: ...


class SocketMediaServerAddressResolver:
    """System resolver returning a stable, de-duplicated answer set."""

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        try:
            records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError):
            raise MediaServerError("media_server_dns_failed", retryable=True) from None
        return tuple(sorted({str(record[4][0]) for record in records}))


@dataclass(frozen=True, slots=True)
class MediaServerTarget:
    """One validated request origin and its selected pinned address."""

    scheme: str
    hostname: str
    port: int
    address: str
    verify_tls: bool

    @property
    def host_header(self) -> str:
        host = f"[{self.hostname}]" if ":" in self.hostname else self.hostname
        default_port = 80 if self.scheme == "http" else 443
        return host if self.port == default_port else f"{host}:{self.port}"


MediaServerTransportFactory = Callable[[MediaServerTarget], httpx.BaseTransport]


@dataclass(frozen=True, slots=True)
class MediaServerLimits:
    """Non-configurable response and schema limits for this narrow protocol."""

    max_header_count: int = 64
    max_header_line_bytes: int = 8_192
    max_header_bytes: int = 65_536
    max_body_bytes: int = 262_144
    max_json_depth: int = 8
    max_json_items: int = 2_048
    max_string_chars: int = 4_096
    max_virtual_folders: int = 256
    max_locations_per_folder: int = 64
    jellyfin_lookup_page_size: int = 128
    max_lookup_pages: int = 32
    max_lookup_items: int = 4_096
    max_lookup_bytes: int = 8_388_608

    def __post_init__(self) -> None:
        for value in (
            self.max_header_count,
            self.max_header_line_bytes,
            self.max_header_bytes,
            self.max_body_bytes,
            self.max_json_depth,
            self.max_json_items,
            self.max_string_chars,
            self.max_virtual_folders,
            self.max_locations_per_folder,
            self.jellyfin_lookup_page_size,
            self.max_lookup_pages,
            self.max_lookup_items,
            self.max_lookup_bytes,
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("media-server limits must be positive integers")
        if self.jellyfin_lookup_page_size > 128:
            raise ValueError("Jellyfin lookup page size cannot exceed 128")
        if self.max_lookup_pages > 32:
            raise ValueError("media-server lookup page limit cannot exceed 32")
        if self.max_lookup_items > 4_096:
            raise ValueError("media-server lookup item limit cannot exceed 4096")
        if self.max_lookup_bytes > 8_388_608:
            raise ValueError("media-server lookup byte limit cannot exceed 8 MiB")


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    def __init__(self, target: MediaServerTarget) -> None:
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
            raise httpcore.ConnectError("media-server connection target rejected")
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
        raise httpcore.ConnectError("media-server unix sockets are disabled")


class _CoreResponseStream(httpx.SyncByteStream):
    def __init__(self, stream: Iterable[bytes]) -> None:
        self._stream = stream

    def __iter__(self) -> Iterator[bytes]:
        try:
            yield from self._stream
        except httpcore.TimeoutException:
            raise httpx.ReadTimeout("media-server response timed out") from None
        except Exception:
            raise httpx.ReadError("media-server response stream failed") from None

    def close(self) -> None:
        close = getattr(self._stream, "close", None)
        if close is not None:
            close()


class PinnedMediaServerTransport(httpx.BaseTransport):
    """Connect to one validated IP while retaining the origin Host and TLS SNI."""

    def __init__(self, target: MediaServerTarget) -> None:
        ssl_context = ssl.create_default_context()
        if not target.verify_tls:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl_context,
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
        except httpcore.TimeoutException:
            raise httpx.TimeoutException("media-server request timed out", request=request) from None
        except Exception:
            raise httpx.ConnectError("media-server transport failed", request=request) from None
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_CoreResponseStream(cast(Iterable[bytes], response.stream)),
            extensions=response.extensions,
        )

    def close(self) -> None:
        self._pool.close()


def _check_headers(response: httpx.Response, limits: MediaServerLimits) -> None:
    raw_headers = response.headers.raw
    if len(raw_headers) > limits.max_header_count:
        raise MediaServerError("media_server_header_limit")
    total = 0
    for name, value in raw_headers:
        line_size = len(name) + len(value) + 2
        if line_size > limits.max_header_line_bytes:
            raise MediaServerError("media_server_header_limit")
        total += line_size
        if total > limits.max_header_bytes:
            raise MediaServerError("media_server_header_limit")


def _reject_json_constant(_value: str) -> object:
    raise ValueError("non-finite JSON number")


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    decoded: dict[str, object] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError("duplicate JSON object key")
        decoded[key] = value
    return decoded


class _JsonBudget:
    def __init__(self, limits: MediaServerLimits) -> None:
        self._limits = limits
        self._items = 0

    def check(self, value: object, *, depth: int = 0) -> None:
        self._items += 1
        if depth > self._limits.max_json_depth or self._items > self._limits.max_json_items:
            raise MediaServerError("media_server_schema_invalid")
        if isinstance(value, str):
            if len(value) > self._limits.max_string_chars or any(
                0xD800 <= ord(character) <= 0xDFFF for character in value
            ):
                raise MediaServerError("media_server_schema_invalid")
            return
        if value is None or isinstance(value, bool | int | float):
            return
        if isinstance(value, list):
            for item in value:
                self.check(item, depth=depth + 1)
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str) or len(key) > self._limits.max_string_chars:
                    raise MediaServerError("media_server_schema_invalid")
                self._items += 1
                if self._items > self._limits.max_json_items:
                    raise MediaServerError("media_server_schema_invalid")
                self.check(item, depth=depth + 1)
            return
        raise MediaServerError("media_server_schema_invalid")


@dataclass(frozen=True, slots=True)
class _Discovery:
    server_version: str


@dataclass(frozen=True, slots=True)
class _JsonResponse:
    payload: object
    body_byte_count: int


@dataclass(frozen=True, slots=True)
class _LookupMatch:
    item_id: str
    etag: str | None


class _LookupPassBudget:
    def __init__(self, limits: MediaServerLimits) -> None:
        self._limits = limits
        self.page_count = 0
        self.item_count = 0
        self.response_byte_count = 0

    @property
    def remaining_bytes(self) -> int:
        return self._limits.max_lookup_bytes - self.response_byte_count

    def start_page(self) -> None:
        if self.page_count >= self._limits.max_lookup_pages or self.remaining_bytes < 1:
            raise MediaServerError("media_server_item_lookup_incomplete")
        self.page_count += 1

    def finish_page(self, *, item_count: int, response_byte_count: int) -> None:
        if (
            isinstance(item_count, bool)
            or not isinstance(item_count, int)
            or item_count < 0
            or self.item_count + item_count > self._limits.max_lookup_items
            or response_byte_count < 0
            or self.response_byte_count + response_byte_count > self._limits.max_lookup_bytes
        ):
            raise MediaServerError("media_server_item_lookup_incomplete")
        self.item_count += item_count
        self.response_byte_count += response_byte_count


@dataclass(frozen=True, slots=True)
class _WorkerFailure:
    code: str
    retryable: bool


_ConnectorResult: TypeAlias = MediaServerProbeResult | MediaServerScanResult | MediaServerItemLookupResult
_WorkerOutcome: TypeAlias = _ConnectorResult | _WorkerFailure


@dataclass(frozen=True, slots=True)
class _WorkerCompletion:
    outcome: _WorkerOutcome
    completed_at: float


_PostEntryDecision: TypeAlias = Literal["entered", "cancelled", "expired"]


class _DeadlineState:
    """Linearize the absolute deadline against the one mutating dispatch."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._expired = False
        self._cancelled = False
        self._post_entered = False

    @property
    def post_entered(self) -> bool:
        with self._lock:
            return self._post_entered

    def active(self, *, now: float, deadline: float) -> bool:
        with self._lock:
            return not self._expired and now < deadline

    def observe_cancellation(self) -> bool:
        with self._lock:
            self._cancelled = True
            return self._post_entered

    def enter_post(
        self,
        *,
        deadline: float,
        monotonic: Callable[[], float],
        cancel_requested: Callable[[], bool] | None,
    ) -> _PostEntryDecision:
        with self._lock:
            if self._expired or monotonic() >= deadline:
                return "expired"
            try:
                cancelled = cancel_requested is None or cancel_requested() is True
            except BaseException:
                cancelled = True
            if self._expired or monotonic() >= deadline:
                self._expired = True
                return "expired"
            if self._cancelled or cancelled:
                self._cancelled = True
                return "cancelled"
            self._post_entered = True
            return "entered"

    def expire(self) -> bool:
        with self._lock:
            self._expired = True
            return self._post_entered


class _PreDispatchCancelled(Exception):
    pass


class _PreDispatchDeadline(Exception):
    pass


class _PostDispatchCancelled(Exception):
    pass


class _GatedTransport(httpx.BaseTransport):
    """Linearize deadline/cancellation at the actual transport entry."""

    def __init__(
        self,
        delegate: httpx.BaseTransport,
        *,
        state: _DeadlineState,
        deadline: float,
        monotonic: Callable[[], float],
        mutation: bool,
        cancel_requested: Callable[[], bool] | None,
    ) -> None:
        self._delegate = delegate
        self._state = state
        self._deadline = deadline
        self._monotonic = monotonic
        self._mutation = mutation
        self._cancel_requested = cancel_requested

    def _cancellation_requested(self) -> bool:
        callback = self._cancel_requested
        if callback is None:
            return True
        try:
            return callback() is True
        except BaseException:
            return True

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self._mutation:
            decision = self._state.enter_post(
                deadline=self._deadline,
                monotonic=self._monotonic,
                cancel_requested=self._cancel_requested,
            )
            if decision == "cancelled":
                raise _PreDispatchCancelled
            if decision == "expired":
                raise _PreDispatchDeadline
        elif not self._state.active(now=self._monotonic(), deadline=self._deadline):
            raise _PreDispatchDeadline

        response = self._delegate.handle_request(request)
        if self._mutation and self._cancellation_requested():
            self._state.observe_cancellation()
            with suppress(BaseException):
                response.close()
            raise _PostDispatchCancelled
        return response

    def close(self) -> None:
        self._delegate.close()


class MediaServerConnector:
    """Perform only identity/library GETs and one exact targeted-refresh POST."""

    def __init__(
        self,
        profile: MediaServerProfile,
        secret_resolver: MediaServerSecretResolver,
        *,
        resolver: MediaServerAddressResolver | None = None,
        transport_factory: MediaServerTransportFactory | None = None,
        transport: httpx.BaseTransport | None = None,
        limits: MediaServerLimits | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(profile, MediaServerProfile):
            raise TypeError("profile must be a MediaServerProfile")
        if not hasattr(secret_resolver, "resolve"):
            raise TypeError("secret_resolver must expose resolve")
        if resolver is not None and not hasattr(resolver, "resolve"):
            raise TypeError("resolver must expose resolve")
        if transport_factory is not None and transport is not None:
            raise ValueError("provide transport_factory or transport, not both")
        if transport_factory is not None and not callable(transport_factory):
            raise TypeError("transport_factory must be callable")
        if transport is not None and not isinstance(transport, httpx.BaseTransport):
            raise TypeError("transport must be an httpx BaseTransport")
        if not callable(monotonic):
            raise TypeError("monotonic must be callable")
        self._profile = profile
        self._secret_resolver = secret_resolver
        self._resolver = resolver or SocketMediaServerAddressResolver()
        if transport is not None:
            self._transport_factory: MediaServerTransportFactory = lambda _target: transport
        else:
            self._transport_factory = transport_factory or PinnedMediaServerTransport
        self._limits = limits or MediaServerLimits()
        self._monotonic = monotonic
        self._execution_gate = threading.Lock()
        self._execution_active = False

    @property
    def profile_fingerprint(self) -> str:
        return self._profile.profile_fingerprint

    @property
    def safe_summary(self) -> MediaServerSafeSummary:
        return self._profile.safe_summary

    def probe(self) -> MediaServerProbeResult:
        """Verify server identity and one uniquely matching virtual folder."""

        deadline = self._monotonic() + self._profile.timeout_seconds
        state = _DeadlineState()
        return cast(
            MediaServerProbeResult,
            self._run_until_deadline(
                lambda: self._probe(deadline, state),
                deadline=deadline,
                state=state,
            ),
        )

    def _probe(self, deadline: float, state: _DeadlineState) -> MediaServerProbeResult:
        self._check_deadline(deadline, state)
        discovery = self._discover(deadline, state)
        self._check_deadline(deadline, state)
        return MediaServerProbeResult(
            provider=self._profile.provider,
            server_version=discovery.server_version,
            library_id_digest=self._profile.library_id_digest,
        )

    def lookup_item(self, target: MediaServerLookupTarget) -> MediaServerItemLookupResult:
        """Return complete exact-match evidence without exposing remote selectors."""

        if not isinstance(target, MediaServerLookupTarget):
            raise TypeError("target must be a MediaServerLookupTarget")
        deadline = self._monotonic() + self._profile.timeout_seconds
        state = _DeadlineState()
        return cast(
            MediaServerItemLookupResult,
            self._run_until_deadline(
                lambda: self._lookup_item(target, deadline, state),
                deadline=deadline,
                state=state,
                timeout_code="media_server_item_lookup_incomplete",
            ),
        )

    def _lookup_item(
        self,
        target: MediaServerLookupTarget,
        deadline: float,
        state: _DeadlineState,
    ) -> MediaServerItemLookupResult:
        try:
            self._check_deadline(deadline, state)
            if self._profile.provider == "emby":
                return self._lookup_emby_item(target, deadline, state)
            return self._lookup_jellyfin_item(target, deadline, state)
        except MediaServerError as error:
            if error.code in _LOOKUP_INCOMPLETE_CODES:
                raise MediaServerError("media_server_item_lookup_incomplete") from None
            raise

    def _lookup_emby_item(
        self,
        target: MediaServerLookupTarget,
        deadline: float,
        state: _DeadlineState,
    ) -> MediaServerItemLookupResult:
        provider_filter = self._emby_provider_filter(target)
        query_items: list[tuple[str, str]] = [("Path", target.server_path)]
        if provider_filter is not None:
            query_items.append(("AnyProviderIdEquals", provider_filter))
        query_items.extend(
            (
                ("ParentId", self._profile.library_id),
                ("Recursive", "true"),
                ("Fields", "Path,ProviderIds"),
                ("EnableImages", "false"),
                ("EnableUserData", "false"),
                ("StartIndex", "0"),
                ("Limit", str(_EMBY_LOOKUP_LIMIT)),
            )
        )
        budget = _LookupPassBudget(self._limits)
        budget.start_page()
        response = self._request(
            "GET",
            "/Items",
            query=tuple(query_items),
            deadline=deadline,
            state=state,
            expect_json=True,
            lookup_request=True,
            body_byte_limit=budget.remaining_bytes,
            sensitive_selectors=(target.provider_key, target.provider_value, target.server_path),
        )
        if not isinstance(response, _JsonResponse):  # pragma: no cover - closed internal call contract
            raise MediaServerError("media_server_item_lookup_incomplete")
        payload = response.payload
        if not isinstance(payload, dict):
            raise MediaServerError("media_server_item_lookup_incomplete")
        raw_items = payload.get("Items")
        if not isinstance(raw_items, list) or len(raw_items) > _EMBY_LOOKUP_LIMIT:
            raise MediaServerError("media_server_item_lookup_incomplete")
        budget.finish_page(item_count=len(raw_items), response_byte_count=response.body_byte_count)

        start_index = payload.get("StartIndex")
        if start_index is not None and (
            isinstance(start_index, bool) or not isinstance(start_index, int) or start_index != 0
        ):
            raise MediaServerError("media_server_item_lookup_incomplete")
        total = payload.get("TotalRecordCount")
        if total is not None and (isinstance(total, bool) or not isinstance(total, int) or total < 0):
            raise MediaServerError("media_server_item_lookup_incomplete")
        if total is not None and total != len(raw_items):
            raise MediaServerError("media_server_item_lookup_incomplete")

        seen_ids: set[str] = set()
        matches: list[_LookupMatch] = []
        for raw_item in raw_items:
            item_id, path, provider_value, etag = self._validated_lookup_row(raw_item, target.provider_key)
            if item_id in seen_ids or path != target.server_path:
                raise MediaServerError("media_server_item_lookup_incomplete")
            seen_ids.add(item_id)
            if provider_filter is not None and provider_value != target.provider_value:
                raise MediaServerError("media_server_item_lookup_incomplete")
            if provider_value == target.provider_value:
                matches.append(_LookupMatch(item_id=item_id, etag=etag))
        if len(matches) > 1:
            raise MediaServerError("media_server_item_lookup_ambiguous")
        if total is None and len(raw_items) == _EMBY_LOOKUP_LIMIT and len(matches) < _EMBY_LOOKUP_LIMIT:
            raise MediaServerError("media_server_item_lookup_incomplete")
        return self._completed_lookup_result(target, matches, seen_ids, budget)

    def _lookup_jellyfin_item(
        self,
        target: MediaServerLookupTarget,
        deadline: float,
        state: _DeadlineState,
    ) -> MediaServerItemLookupResult:
        budget = _LookupPassBudget(self._limits)
        seen_ids: set[str] = set()
        matches: list[_LookupMatch] = []
        expected_total: int | None = None
        start_index = 0
        page_size = self._limits.jellyfin_lookup_page_size

        while expected_total is None or len(seen_ids) < expected_total:
            budget.start_page()
            query = (
                ("parentId", self._profile.library_id),
                ("recursive", "true"),
                ("fields", "Path,ProviderIds,Etag"),
                ("enableImages", "false"),
                ("enableUserData", "false"),
                ("enableTotalRecordCount", "true"),
                ("startIndex", str(start_index)),
                ("limit", str(page_size)),
            )
            response = self._request(
                "GET",
                "/Items",
                query=query,
                deadline=deadline,
                state=state,
                expect_json=True,
                lookup_request=True,
                body_byte_limit=budget.remaining_bytes,
                sensitive_selectors=(target.provider_key, target.provider_value, target.server_path),
            )
            if not isinstance(response, _JsonResponse):  # pragma: no cover - closed internal call contract
                raise MediaServerError("media_server_item_lookup_incomplete")
            payload = response.payload
            if not isinstance(payload, dict):
                raise MediaServerError("media_server_item_lookup_incomplete")
            raw_items = payload.get("Items")
            total = payload.get("TotalRecordCount")
            returned_start = payload.get("StartIndex")
            if (
                not isinstance(raw_items, list)
                or len(raw_items) > page_size
                or isinstance(total, bool)
                or not isinstance(total, int)
                or total < 0
                or isinstance(returned_start, bool)
                or not isinstance(returned_start, int)
                or returned_start != start_index
            ):
                raise MediaServerError("media_server_item_lookup_incomplete")
            budget.finish_page(item_count=len(raw_items), response_byte_count=response.body_byte_count)
            if (
                total > self._limits.max_lookup_items
                or (total + page_size - 1) // page_size > self._limits.max_lookup_pages
                or (expected_total is not None and total != expected_total)
                or start_index + len(raw_items) > total
                or (not raw_items and start_index < total)
            ):
                raise MediaServerError("media_server_item_lookup_incomplete")
            expected_total = total

            for raw_item in raw_items:
                item_id, path, provider_value, etag = self._validated_lookup_row(raw_item, target.provider_key)
                if item_id in seen_ids:
                    raise MediaServerError("media_server_item_lookup_incomplete")
                seen_ids.add(item_id)
                if path == target.server_path and provider_value == target.provider_value:
                    matches.append(_LookupMatch(item_id=item_id, etag=etag))
                    if len(matches) > 1:
                        raise MediaServerError("media_server_item_lookup_ambiguous")
            start_index += len(raw_items)

        if expected_total is None or len(seen_ids) != expected_total:
            raise MediaServerError("media_server_item_lookup_incomplete")
        return self._completed_lookup_result(target, matches, seen_ids, budget)

    @staticmethod
    def _emby_provider_filter(target: MediaServerLookupTarget) -> str | None:
        provider_value = target.provider_value
        if re.fullmatch(r"[A-Za-z0-9_-]{1,512}", provider_value) is None:
            return None
        return f"{target.provider_key}.{provider_value}"

    @staticmethod
    def _validated_lookup_row(raw_item: object, provider_key: str) -> tuple[str, str, str | None, str | None]:
        if not isinstance(raw_item, dict):
            raise MediaServerError("media_server_item_lookup_incomplete")
        item_id = raw_item.get("Id")
        path = raw_item.get("Path")
        provider_ids = raw_item.get("ProviderIds")
        etag = raw_item.get("Etag")
        if (
            not isinstance(item_id, str)
            or not 1 <= len(item_id) <= 128
            or any(
                ord(character) < 0x20 or ord(character) == 0x7F or 0xD800 <= ord(character) <= 0xDFFF
                for character in item_id
            )
            or not isinstance(path, str)
            or not path
            or any(
                ord(character) < 0x20 or ord(character) == 0x7F or 0xD800 <= ord(character) <= 0xDFFF
                for character in path
            )
            or not isinstance(provider_ids, dict)
            or any(
                not isinstance(key, str)
                or not isinstance(value, str)
                or any(0xD800 <= ord(character) <= 0xDFFF for character in key)
                or any(0xD800 <= ord(character) <= 0xDFFF for character in value)
                for key, value in provider_ids.items()
            )
            or (
                etag is not None
                and (
                    not isinstance(etag, str)
                    or not etag
                    or any(
                        ord(character) < 0x20 or ord(character) == 0x7F or 0xD800 <= ord(character) <= 0xDFFF
                        for character in etag
                    )
                )
            )
        ):
            raise MediaServerError("media_server_item_lookup_incomplete")
        raw_provider_value = provider_ids.get(provider_key)
        provider_value = raw_provider_value if isinstance(raw_provider_value, str) else None
        return item_id, path, provider_value, etag

    def _completed_lookup_result(
        self,
        target: MediaServerLookupTarget,
        matches: Sequence[_LookupMatch],
        seen_ids: set[str],
        budget: _LookupPassBudget,
    ) -> MediaServerItemLookupResult:
        fingerprint = hashlib.sha256(b"media-sync:media-server-item-id-set:v1\0")
        for value in (
            self._profile.profile_fingerprint,
            target.provider_key,
            target.provider_value,
            target.server_path,
            *sorted(seen_ids),
        ):
            encoded = value.encode("utf-8")
            fingerprint.update(len(encoded).to_bytes(4, "big"))
            fingerprint.update(encoded)
        match = matches[0] if matches else None
        return MediaServerItemLookupResult(
            lookup_state="matched" if match is not None else "not_found",
            inspected_item_count=budget.item_count,
            page_count=budget.page_count,
            response_byte_count=budget.response_byte_count,
            item_id_set_fingerprint=fingerprint.hexdigest(),
            item_id=None if match is None else match.item_id,
            etag=None if match is None else match.etag,
        )

    def scan(self, cancel_requested: Callable[[], bool]) -> MediaServerScanResult:
        """Dispatch the fixed targeted refresh once and never retry it."""

        if not callable(cancel_requested):
            raise TypeError("cancel_requested must be callable")
        deadline = self._monotonic() + self._profile.timeout_seconds
        state = _DeadlineState()
        return cast(
            MediaServerScanResult,
            self._run_until_deadline(
                lambda: self._scan(cancel_requested, deadline, state),
                deadline=deadline,
                state=state,
            ),
        )

    def _scan(
        self,
        cancel_requested: Callable[[], bool],
        deadline: float,
        state: _DeadlineState,
    ) -> MediaServerScanResult:
        self._check_deadline(deadline, state)
        if self._cancel_requested(cancel_requested):
            raise MediaServerError("media_server_scan_cancelled")
        discovery = self._discover(deadline, state)
        self._check_deadline(deadline, state)
        if self._cancel_requested(cancel_requested):
            raise MediaServerError("media_server_scan_cancelled")
        scan_query = _EMBY_SCAN_QUERY if self._profile.provider == "emby" else _JELLYFIN_SCAN_QUERY
        self._request(
            "POST",
            f"/Items/{self._profile.library_id}/Refresh",
            query=scan_query,
            deadline=deadline,
            state=state,
            mutation=True,
            cancel_requested=cancel_requested,
        )
        self._check_deadline(deadline, state)
        if self._cancel_requested(cancel_requested):
            state.observe_cancellation()
            raise MediaServerError("media_server_scan_acceptance_unknown")
        return MediaServerScanResult(
            provider=self._profile.provider,
            server_version=discovery.server_version,
            library_id_digest=self._profile.library_id_digest,
        )

    def _run_until_deadline(
        self,
        operation: Callable[[], _ConnectorResult],
        *,
        deadline: float,
        state: _DeadlineState,
        timeout_code: str = "media_server_timeout",
    ) -> _ConnectorResult:
        if not self._claim_execution():
            raise MediaServerError("media_server_transport", retryable=True)
        outcomes: SimpleQueue[_WorkerCompletion] = SimpleQueue()
        done = threading.Event()

        def run() -> None:
            try:
                worker_outcome: _WorkerOutcome = operation()
            except MediaServerError as error:
                worker_outcome = _WorkerFailure(error.code, error.retryable)
            except BaseException:
                worker_outcome = self._unexpected_failure(state)
            try:
                completion = _WorkerCompletion(
                    outcome=worker_outcome,
                    completed_at=self._monotonic(),
                )
            except BaseException:
                completion = _WorkerCompletion(
                    outcome=self._unexpected_failure(state),
                    completed_at=deadline,
                )
            finally:
                outcomes.put(completion)
                self._finish_execution()
                done.set()

        worker = threading.Thread(
            target=run,
            name="media-sync-media-server-deadline",
            daemon=True,
        )
        try:
            worker.start()
        except RuntimeError:
            self._finish_execution()
            raise MediaServerError("media_server_transport", retryable=True) from None
        remaining = max(0.0, deadline - self._monotonic())
        completed = done.wait(remaining)
        if not completed:
            raise self._expire_deadline(state, timeout_code=timeout_code) from None
        completion = outcomes.get_nowait()
        if completion.completed_at >= deadline:
            raise self._expire_deadline(state, timeout_code=timeout_code) from None
        outcome = completion.outcome
        if isinstance(outcome, _WorkerFailure):
            raise MediaServerError(outcome.code, retryable=outcome.retryable) from None
        return outcome

    def _claim_execution(self) -> bool:
        with self._execution_gate:
            if self._execution_active:
                return False
            self._execution_active = True
            return True

    def _finish_execution(self) -> None:
        with self._execution_gate:
            self._execution_active = False

    @staticmethod
    def _unexpected_failure(state: _DeadlineState) -> _WorkerFailure:
        if state.post_entered:
            return _WorkerFailure("media_server_scan_acceptance_unknown", False)
        return _WorkerFailure("media_server_transport", True)

    @staticmethod
    def _expire_deadline(state: _DeadlineState, *, timeout_code: str = "media_server_timeout") -> MediaServerError:
        post_entered = state.expire()
        if post_entered:
            return MediaServerError("media_server_scan_acceptance_unknown")
        return MediaServerError(timeout_code, retryable=timeout_code == "media_server_timeout")

    def _check_deadline(self, deadline: float, state: _DeadlineState) -> None:
        if state.active(now=self._monotonic(), deadline=deadline):
            return
        if state.post_entered:
            raise MediaServerError("media_server_scan_acceptance_unknown")
        raise MediaServerError("media_server_timeout", retryable=True)

    def _cancel_requested(self, callback: Callable[[], bool]) -> bool:
        try:
            value = callback()
        except BaseException:
            return True
        return value is True

    def _discover(self, deadline: float, state: _DeadlineState) -> _Discovery:
        system_response = self._request(
            "GET",
            "/System/Info",
            deadline=deadline,
            state=state,
            expect_json=True,
        )
        self._check_deadline(deadline, state)
        if not isinstance(system_response, _JsonResponse):  # pragma: no cover - closed internal call contract
            raise MediaServerError("media_server_schema_invalid")
        system_info = system_response.payload
        if not isinstance(system_info, dict):
            raise MediaServerError("media_server_schema_invalid")
        version = system_info.get("Version")
        if not isinstance(version, str):
            raise MediaServerError("media_server_schema_invalid")
        product_name = system_info.get("ProductName")
        if product_name is not None:
            if not isinstance(product_name, str):
                raise MediaServerError("media_server_schema_invalid")
            normalized_product = product_name.casefold()
            if self._profile.provider not in normalized_product:
                raise MediaServerError("media_server_provider_mismatch")
        try:
            validated_version = MediaServerProbeResult(
                provider=self._profile.provider,
                server_version=version,
                library_id_digest=self._profile.library_id_digest,
            ).server_version
        except (TypeError, ValueError):
            raise MediaServerError("media_server_schema_invalid") from None

        self._check_deadline(deadline, state)
        folders_response = self._request(
            "GET",
            "/Library/VirtualFolders",
            deadline=deadline,
            state=state,
            expect_json=True,
        )
        self._check_deadline(deadline, state)
        if not isinstance(folders_response, _JsonResponse):  # pragma: no cover - closed internal call contract
            raise MediaServerError("media_server_schema_invalid")
        self._validate_library(folders_response.payload)
        return _Discovery(server_version=validated_version)

    def _validate_library(self, payload: object) -> None:
        if not isinstance(payload, list) or len(payload) > self._limits.max_virtual_folders:
            raise MediaServerError("media_server_schema_invalid")
        matches: list[Mapping[str, object]] = []
        for raw_folder in payload:
            if not isinstance(raw_folder, dict):
                raise MediaServerError("media_server_schema_invalid")
            item_id = raw_folder.get("ItemId")
            if item_id is not None and not isinstance(item_id, str):
                raise MediaServerError("media_server_schema_invalid")
            if item_id == self._profile.library_id:
                matches.append(raw_folder)
        if not matches:
            raise MediaServerError("media_server_library_not_found")
        if len(matches) != 1:
            raise MediaServerError("media_server_library_ambiguous")
        locations = matches[0].get("Locations")
        if not isinstance(locations, list) or len(locations) > self._limits.max_locations_per_folder:
            raise MediaServerError("media_server_schema_invalid")
        if any(not isinstance(location, str) for location in locations):
            raise MediaServerError("media_server_schema_invalid")
        if sum(location == self._profile.library_path for location in locations) != 1:
            raise MediaServerError("media_server_library_path_mismatch")

    def _validated_target(self) -> MediaServerTarget:
        parsed = urlsplit(self._profile.origin)
        hostname = parsed.hostname
        if hostname is None:  # pragma: no cover - profile construction proves this
            raise MediaServerError("media_server_address_forbidden")
        port = parsed.port or (80 if parsed.scheme == "http" else 443)
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            literal = None
        addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]
        if literal is not None:
            addresses = (literal,)
        else:
            try:
                raw_addresses = self._resolver.resolve(hostname, port)
            except MediaServerError:
                raise
            except Exception:
                raise MediaServerError("media_server_dns_failed", retryable=True) from None
            if not raw_addresses or isinstance(raw_addresses, str | bytes):
                raise MediaServerError("media_server_dns_failed", retryable=True)
            parsed_addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
            try:
                for raw_address in raw_addresses:
                    parsed_addresses.append(ipaddress.ip_address(raw_address))
            except (TypeError, ValueError):
                raise MediaServerError("media_server_dns_failed", retryable=True) from None
            if not parsed_addresses:
                raise MediaServerError("media_server_dns_failed", retryable=True)
            addresses = tuple(parsed_addresses)
        if not all(self._profile.address_is_allowed(str(address)) for address in addresses):
            raise MediaServerError("media_server_address_forbidden")
        selected = min(addresses, key=lambda address: (address.version, int(address)))
        return MediaServerTarget(
            scheme=parsed.scheme,
            hostname=hostname,
            port=port,
            address=str(selected),
            verify_tls=self._profile.verify_tls,
        )

    def _resolve_secret(self) -> SecretValue:
        try:
            secret = self._secret_resolver.resolve(self._profile.api_key_secret_reference)
        except SecretError:
            raise MediaServerError("media_server_secret_unavailable") from None
        except Exception:
            raise MediaServerError("media_server_secret_unavailable") from None
        if not isinstance(secret, SecretValue):
            raise MediaServerError("media_server_secret_unavailable")
        return secret

    @staticmethod
    def _validated_api_key(secret: SecretValue) -> str:
        value = secret.reveal()
        try:
            encoded = value.encode("ascii")
        except UnicodeError:
            raise MediaServerError("media_server_secret_unavailable") from None
        if not 1 <= len(encoded) <= 4_096 or any(byte < 0x21 or byte > 0x7E for byte in encoded):
            raise MediaServerError("media_server_secret_unavailable")
        return value

    def _reject_sensitive_version(self, path: str, payload: object, api_key: str) -> None:
        if path != "/System/Info" or not isinstance(payload, dict):
            return
        version = payload.get("Version")
        if not isinstance(version, str):
            return
        selectors = (api_key, self._profile.library_id)
        if any(
            version == selector or (len(selector) >= _MIN_SENSITIVE_SUBSTRING_CHARS and selector in version)
            for selector in selectors
        ):
            raise MediaServerError("media_server_schema_invalid")

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: tuple[tuple[str, str], ...] = (),
        deadline: float,
        state: _DeadlineState,
        mutation: bool = False,
        expect_json: bool = False,
        cancel_requested: Callable[[], bool] | None = None,
        lookup_request: bool = False,
        body_byte_limit: int | None = None,
        sensitive_selectors: tuple[str, ...] = (),
    ) -> _JsonResponse | None:
        scan_query = _EMBY_SCAN_QUERY if self._profile.provider == "emby" else _JELLYFIN_SCAN_QUERY
        allowed = {
            ("GET", "/System/Info", ()),
            ("GET", "/Library/VirtualFolders", ()),
            ("POST", f"/Items/{self._profile.library_id}/Refresh", scan_query),
        }
        if lookup_request:
            request_allowed = method == "GET" and path == "/Items" and self._lookup_query_is_allowlisted(query)
        else:
            request_allowed = (method, path, query) in allowed
        if not request_allowed:
            raise ValueError("media-server route is not allowlisted")
        if body_byte_limit is not None and (
            isinstance(body_byte_limit, bool) or not isinstance(body_byte_limit, int) or body_byte_limit < 1
        ):
            raise ValueError("body_byte_limit must be a positive integer")
        self._check_deadline(deadline, state)
        target = self._validated_target()
        self._check_deadline(deadline, state)
        secret = self._resolve_secret()
        api_key = self._validated_api_key(secret)
        self._check_deadline(deadline, state)
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise MediaServerError("media_server_timeout", retryable=True)
        delegate = self._transport_factory(target)
        if not isinstance(delegate, httpx.BaseTransport):
            raise MediaServerError("media_server_transport", retryable=True)
        self._check_deadline(deadline, state)
        transport = _GatedTransport(
            delegate,
            state=state,
            deadline=deadline,
            monotonic=self._monotonic,
            mutation=mutation,
            cancel_requested=cancel_requested,
        )
        client = httpx.Client(
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(remaining),
        )
        response: httpx.Response | None = None
        with _redact_wire_logs(
            api_key,
            self._profile.library_id,
            *sensitive_selectors,
            replace_message=lookup_request,
        ):
            try:
                headers = {
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "Host": target.host_header,
                    "User-Agent": "media-sync/0.1",
                }
                # SecretValue is unwrapped only while constructing the final auth header.
                headers["X-Emby-Token"] = api_key
                request = client.build_request(
                    method,
                    f"{self._profile.origin}{path}",
                    params=query or None,
                    headers=headers,
                    content=b"" if method == "POST" else None,
                )
                self._check_deadline(deadline, state)
                if mutation and (cancel_requested is None or self._cancel_requested(cancel_requested)):
                    state.observe_cancellation()
                    raise MediaServerError("media_server_scan_cancelled")
                response = client.send(request, stream=True)
                self._check_deadline(deadline, state)
                _check_headers(response, self._limits)
                if response.status_code in _REDIRECT_STATUSES:
                    raise MediaServerError("media_server_redirect_forbidden")
                self._check_status(response.status_code, mutation=mutation)
                body = self._read_body(
                    response,
                    deadline=deadline,
                    state=state,
                    max_body_bytes=(
                        self._limits.max_body_bytes
                        if body_byte_limit is None
                        else min(self._limits.max_body_bytes, body_byte_limit)
                    ),
                )
                if not expect_json:
                    return None
                content_types = response.headers.get_list("content-type")
                if len(content_types) > 1 or (
                    content_types
                    and content_types[0].split(";", maxsplit=1)[0].strip().casefold() != "application/json"
                ):
                    raise MediaServerError("media_server_response_invalid")
                try:
                    decoded = body.decode("utf-8")
                    payload = json.loads(
                        decoded,
                        parse_constant=_reject_json_constant,
                        object_pairs_hook=_reject_duplicate_json_keys,
                    )
                except (UnicodeError, TypeError, ValueError):
                    raise MediaServerError("media_server_response_invalid") from None
                self._check_deadline(deadline, state)
                _JsonBudget(self._limits).check(payload)
                self._reject_sensitive_version(path, payload, api_key)
                self._check_deadline(deadline, state)
                return _JsonResponse(payload=payload, body_byte_count=len(body))
            except _PreDispatchCancelled:
                raise MediaServerError("media_server_scan_cancelled") from None
            except _PreDispatchDeadline:
                raise MediaServerError("media_server_timeout", retryable=True) from None
            except _PostDispatchCancelled:
                raise MediaServerError("media_server_scan_acceptance_unknown") from None
            except MediaServerError:
                raise
            except httpx.TimeoutException:
                if mutation and state.post_entered:
                    raise MediaServerError("media_server_scan_acceptance_unknown") from None
                raise MediaServerError("media_server_timeout", retryable=True) from None
            except BaseException:
                if mutation and state.post_entered:
                    raise MediaServerError("media_server_scan_acceptance_unknown") from None
                raise MediaServerError("media_server_transport", retryable=True) from None
            finally:
                cleanup_failed = False
                if response is not None and not response.is_closed:
                    try:
                        response.close()
                    except BaseException:
                        cleanup_failed = True
                try:
                    client.close()
                except BaseException:
                    cleanup_failed = True
                cancelled_after_dispatch = (
                    mutation
                    and state.post_entered
                    and (cancel_requested is None or self._cancel_requested(cancel_requested))
                )
                if cancelled_after_dispatch:
                    state.observe_cancellation()
                    raise MediaServerError("media_server_scan_acceptance_unknown") from None
                if cleanup_failed:
                    if mutation and state.post_entered:
                        raise MediaServerError("media_server_scan_acceptance_unknown") from None
                    raise MediaServerError("media_server_transport", retryable=True) from None

    def _lookup_query_is_allowlisted(self, query: tuple[tuple[str, str], ...]) -> bool:
        if self._profile.provider == "emby":
            names = tuple(name for name, _value in query)
            expected_without_provider = (
                "Path",
                "ParentId",
                "Recursive",
                "Fields",
                "EnableImages",
                "EnableUserData",
                "StartIndex",
                "Limit",
            )
            expected_with_provider = (
                "Path",
                "AnyProviderIdEquals",
                *expected_without_provider[1:],
            )
            if names not in {expected_without_provider, expected_with_provider}:
                return False
            values = dict(query)
            return (
                bool(values["Path"])
                and values["ParentId"] == self._profile.library_id
                and values["Recursive"] == "true"
                and values["Fields"] == "Path,ProviderIds"
                and values["EnableImages"] == "false"
                and values["EnableUserData"] == "false"
                and values["StartIndex"] == "0"
                and values["Limit"] == str(_EMBY_LOOKUP_LIMIT)
                and ("AnyProviderIdEquals" not in values or bool(values["AnyProviderIdEquals"]))
            )
        names = tuple(name for name, _value in query)
        if names != (
            "parentId",
            "recursive",
            "fields",
            "enableImages",
            "enableUserData",
            "enableTotalRecordCount",
            "startIndex",
            "limit",
        ):
            return False
        values = dict(query)
        try:
            start_index = int(values["startIndex"])
            limit = int(values["limit"])
        except (KeyError, ValueError):
            return False
        return (
            values["parentId"] == self._profile.library_id
            and values["recursive"] == "true"
            and values["fields"] == "Path,ProviderIds,Etag"
            and values["enableImages"] == "false"
            and values["enableUserData"] == "false"
            and values["enableTotalRecordCount"] == "true"
            and start_index >= 0
            and limit == self._limits.jellyfin_lookup_page_size
        )

    def _read_body(
        self,
        response: httpx.Response,
        *,
        deadline: float,
        state: _DeadlineState,
        max_body_bytes: int,
    ) -> bytes:
        self._check_deadline(deadline, state)
        content_encodings = response.headers.get_list("content-encoding")
        if content_encodings and any(value.strip().casefold() != "identity" for value in content_encodings):
            raise MediaServerError("media_server_response_invalid")
        lengths = response.headers.get_list("content-length")
        if len(lengths) > 1:
            raise MediaServerError("media_server_response_invalid")
        if lengths:
            try:
                declared = int(lengths[0])
            except ValueError:
                raise MediaServerError("media_server_response_invalid") from None
            if declared < 0:
                raise MediaServerError("media_server_response_invalid")
            if declared > max_body_bytes:
                raise MediaServerError("media_server_body_limit")
        if response.is_stream_consumed:
            body = response.content
            if len(body) > max_body_bytes:
                raise MediaServerError("media_server_body_limit")
            self._check_deadline(deadline, state)
            return body
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_raw():
            self._check_deadline(deadline, state)
            total += len(chunk)
            if total > max_body_bytes:
                raise MediaServerError("media_server_body_limit")
            chunks.append(chunk)
        self._check_deadline(deadline, state)
        return b"".join(chunks)

    @staticmethod
    def _check_status(status_code: int, *, mutation: bool) -> None:
        if 200 <= status_code < 300:
            return
        if mutation:
            if status_code in _TARGETED_SCAN_UNSUPPORTED:
                raise MediaServerError("media_server_targeted_scan_unsupported")
            raise MediaServerError("media_server_scan_rejected")
        if status_code in {401, 403}:
            raise MediaServerError("media_server_authentication_failed")
        if status_code == 429 or 500 <= status_code < 600:
            raise MediaServerError("media_server_http_retryable", retryable=True)
        raise MediaServerError("media_server_http_terminal")


__all__ = [
    "MediaServerAddressResolver",
    "MediaServerConnector",
    "MediaServerLimits",
    "MediaServerSecretResolver",
    "MediaServerTarget",
    "MediaServerTransportFactory",
    "PinnedMediaServerTransport",
    "SocketMediaServerAddressResolver",
]
