"""Bounded, identity-free login observations; never transport upstream text.

This channel is deliberately independent of the strict v1 login result. An
observation is not a login disposition: upstream may handle a failed action and
successfully take a fallback. Only the existing result decides authentication.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import importlib
import json
import os
import queue
import threading
import time
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from typing import IO, Any

DiagnosticHook = Callable[[Mapping[str, object]], None]
MAX_EVENT_BYTES = 768
MAX_EVENTS = 1024
MAX_CHANNEL_BYTES = MAX_EVENTS * (MAX_EVENT_BYTES + 4)
MAX_PENDING_EVENTS = 128
_CHANNEL_COMPLETE = b"\xff\xff\xff\xff"
PHASES = frozenset(
    {
        "preflight",
        "account_lock",
        "browser_launch",
        "platform_navigation",
        "session_probe",
        "login_dialog",
        "qr_locate",
        "qr_image_fetch",
        "qr_relay",
        "waiting_scan",
        "login_confirmation",
        "profile_finalize",
        "cleanup",
        "upstream_execution",
    }
)
ACTIONS = frozenset(
    {
        "prepare",
        "acquire",
        "launch",
        "navigate",
        "click",
        "wait_selector",
        "wait_load",
        "probe",
        "fetch",
        "relay_write",
        "confirm",
        "finalize",
        "cleanup",
        "execute",
        "read_image",
    }
)
OUTCOMES = frozenset({"started", "succeeded", "failed", "cancelled"})
ERROR_TYPES = frozenset(
    {
        "none",
        "playwright_timeout",
        "timeout",
        "os_error",
        "cancelled",
        "system_exit",
        "configuration",
        "confirmation_rejected",
        "browser_launch_failed",
        "unknown",
    }
)
SOURCES = frozenset(
    {
        "parent",
        "runner",
        "client",
        "login",
        "qr_helper",
        "qr_relay",
        "httpx_get",
        "browser_type",
        "browser_context",
        "page",
        "frame",
        "locator",
        "element_handle",
        "cleanup",
    }
)
EVENT_CODES = frozenset({"login_stage", "login_terminal", "login_diagnostics_degraded"})
_FIELDS = frozenset(
    {
        "schema_version",
        "event_code",
        "phase",
        "action",
        "outcome",
        "error_type",
        "source_frame",
        "elapsed_ms",
    }
)


def event(
    phase: str,
    action: str,
    outcome: str,
    *,
    error_type: str = "none",
    source_frame: str = "runner",
    elapsed_ms: int = 0,
    event_code: str = "login_stage",
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "event_code": event_code,
        "phase": phase,
        "action": action,
        "outcome": outcome,
        "error_type": error_type,
        "source_frame": source_frame,
        "elapsed_ms": elapsed_ms,
    }
    validate_event(value)
    return value


def validate_event(value: Mapping[str, object]) -> None:
    if (
        set(value) != _FIELDS
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
        or any(
            type(value.get(key)) is not str or value[key] not in allowed
            for key, allowed in (
                ("phase", PHASES),
                ("action", ACTIONS),
                ("outcome", OUTCOMES),
                ("error_type", ERROR_TYPES),
                ("source_frame", SOURCES),
                ("event_code", EVENT_CODES),
            )
        )
        or type(value.get("elapsed_ms")) is not int
        or not 0 <= value["elapsed_ms"] <= 3_600_000  # type: ignore[operator]
        or (value["outcome"] in {"started", "succeeded"} and value["error_type"] != "none")
    ):
        raise ValueError("invalid login diagnostic event")


def _strict_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid login diagnostic event")
        result[key] = value
    return result


def parse_event(raw: bytes) -> dict[str, object]:
    if not 0 < len(raw) <= MAX_EVENT_BYTES:
        raise ValueError("invalid login diagnostic frame")
    try:
        value = json.loads(raw.decode("ascii"), object_pairs_hook=_strict_pairs)
        if not isinstance(value, dict):
            raise ValueError("invalid login diagnostic event")
        validate_event(value)
    except (ValueError, UnicodeError, TypeError):
        raise ValueError("invalid login diagnostic frame") from None
    return value


def deliver(hook: DiagnosticHook | None, value: Mapping[str, object]) -> None:
    """An optional logging sink cannot change authentication truth."""
    if hook is not None:
        with contextlib.suppress(Exception):
            hook(dict(value))


class EventWriter:
    """Own one non-inheritable duplicate descriptor; never block the crawler."""

    def __init__(self, descriptor: int) -> None:
        self._fd = descriptor
        os.set_inheritable(descriptor, False)
        self._queue: queue.Queue[bytes | None] = queue.Queue(MAX_PENDING_EVENTS)
        self._lock = threading.Lock()
        self._count = 0
        self._closed = False
        self._overflowed = False
        self._thread = threading.Thread(target=self._write, name="media-sync-login-events-write", daemon=True)
        self._thread.start()

    def emit(self, value: Mapping[str, object]) -> None:
        validate_event(value)
        raw = json.dumps(dict(value), ensure_ascii=True, separators=(",", ":")).encode("ascii")
        if len(raw) > MAX_EVENT_BYTES:
            return
        with self._lock:
            if self._closed:
                return
            if self._count >= MAX_EVENTS:
                if not self._overflowed:
                    self._overflowed = True
                    with contextlib.suppress(queue.Full):
                        self._queue.put_nowait(b"\0\0\0\0")
                return
            self._count += 1
            try:
                self._queue.put_nowait(len(raw).to_bytes(4, "big") + raw)
            except queue.Full:
                # An invalid bounded marker tells the parent records were lost.
                # Replace a queued observation; never wait behind a full pipe.
                with contextlib.suppress(queue.Empty):
                    self._queue.get_nowait()
                with contextlib.suppress(queue.Full):
                    self._queue.put_nowait(b"\0\0\0\0")

    def _write(self) -> None:
        try:
            while True:
                raw = self._queue.get()
                if raw is None:
                    return
                view = memoryview(raw)
                while view:
                    size = os.write(self._fd, view)
                    if size <= 0:
                        return
                    view = view[size:]
        except OSError:
            return
        finally:
            with contextlib.suppress(OSError):
                os.close(self._fd)

    def close(self) -> None:
        with self._lock:
            self._closed = True
        try:
            self._queue.put(_CHANNEL_COMPLETE, timeout=0.1)
            self._queue.put(None, timeout=0.1)
        except queue.Full:
            return
        self._thread.join(timeout=0.25)


class EventReader:
    """Drain continuously with bounded memory, invoking hooks only in parent."""

    def __init__(self, stream: IO[bytes] | None) -> None:
        self._stream = stream
        self._lock = threading.Lock()
        self._pending: deque[dict[str, object]] = deque(maxlen=MAX_PENDING_EVENTS)
        self.degraded = False
        self._reported = False
        self._started = False
        self._complete = False
        self._thread = threading.Thread(target=self._read, name="media-sync-login-events-read", daemon=True)

    def start(self) -> None:
        try:
            self._thread.start()
            self._started = True
        except RuntimeError:
            self.degraded = True

    def _read(self) -> None:
        stream = self._stream
        if stream is None:
            return
        total = count = 0
        invalid = False
        try:
            while True:
                if invalid:
                    if not stream.read(4096):
                        return
                    continue
                prefix = stream.read(4)
                if prefix == b"":
                    return
                if prefix == _CHANNEL_COMPLETE and not self._complete:
                    self._complete = True
                    continue
                if self._complete:
                    self.degraded = invalid = True
                    continue
                size = int.from_bytes(prefix, "big")
                total += len(prefix)
                count += 1
                if total > MAX_CHANNEL_BYTES or count > MAX_EVENTS:
                    self.degraded = invalid = True
                    continue
                if len(prefix) == 4 and size == 0:
                    self.degraded = True
                    continue
                if len(prefix) != 4 or not 0 < size <= MAX_EVENT_BYTES:
                    self.degraded = invalid = True
                    continue
                raw = stream.read(size)
                total += len(raw)
                if total > MAX_CHANNEL_BYTES:
                    self.degraded = invalid = True
                    continue
                try:
                    value = parse_event(raw)
                except ValueError:
                    self.degraded = True
                    continue
                with self._lock:
                    if len(self._pending) == MAX_PENDING_EVENTS:
                        self.degraded = True
                    self._pending.append(value)
        except (OSError, ValueError):
            self.degraded = True

    def drain(self, hook: DiagnosticHook | None) -> None:
        with self._lock:
            pending = list(self._pending)
            self._pending.clear()
        for value in pending:
            deliver(hook, value)
        if self.degraded and not self._reported:
            self._reported = True
            deliver(
                hook,
                event(
                    "upstream_execution",
                    "execute",
                    "failed",
                    error_type="unknown",
                    source_frame="parent",
                    event_code="login_diagnostics_degraded",
                ),
            )

    def close(self, hook: DiagnosticHook | None) -> None:
        if self._started:
            self._thread.join(timeout=1.0)
        if not self._complete:
            self.degraded = True
        if self._thread.is_alive():
            # The process tree must already have been closed by the caller.
            # Do not block in buffered close if a broken descendant owns a pipe.
            self.degraded = True
        elif self._stream is not None:
            with contextlib.suppress(OSError):
                self._stream.close()
        self.drain(hook)


def safe_error_type(error: BaseException) -> str:
    if isinstance(error, asyncio.CancelledError):
        return "cancelled"
    if isinstance(error, SystemExit):
        return "system_exit"
    try:
        api = importlib.import_module("playwright.async_api")
        timeout = getattr(api, "TimeoutError", None)
        if isinstance(timeout, type) and issubclass(timeout, Exception) and isinstance(error, timeout):
            return "playwright_timeout"
    except Exception:
        pass
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, OSError):
        return "os_error"
    try:
        httpx = importlib.import_module("httpx")
        timeout = getattr(httpx, "TimeoutException", None)
        if isinstance(timeout, type) and issubclass(timeout, Exception) and isinstance(error, timeout):
            return "timeout"
    except Exception:
        pass
    return "unknown"


class LoginObserver:
    """Child-local scopes and observations, with no exception text inspection."""

    def __init__(
        self,
        hook: DiagnosticHook | None = None,
        *,
        error_classifier: Callable[[BaseException], str] = safe_error_type,
    ) -> None:
        self.hook = hook
        self.error_classifier = error_classifier
        self.phase: contextvars.ContextVar[str] = contextvars.ContextVar("login_phase", default="upstream_execution")
        self.qr_relayed = threading.Event()
        self._failures: deque[tuple[BaseException, dict[str, object]]] = deque(maxlen=32)

    def terminal(self, error: BaseException) -> None:
        """Only the very same propagated exception may name a terminal action."""
        if self.hook is None:
            return
        value = next((dict(frame) for caught, frame in self._failures if caught is error), None)
        if value is None:
            value = event("upstream_execution", "execute", "failed", error_type=self.error_classifier(error))
        value["event_code"] = "login_terminal"
        deliver(self.hook, value)

    @contextlib.contextmanager
    def span(
        self,
        phase: str,
        action: str,
        source: str,
        *,
        succeeded: Callable[[], bool] | None = None,
    ) -> Iterator[None]:
        token = self.phase.set(phase)
        start = time.monotonic()
        deliver(self.hook, event(phase, action, "started", source_frame=source))
        try:
            yield
        except BaseException as error:
            if self.hook is not None:
                frame = event(
                    phase,
                    action,
                    "cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
                    error_type=self.error_classifier(error),
                    source_frame=source,
                    elapsed_ms=min(3_600_000, max(0, int((time.monotonic() - start) * 1000))),
                )
                self._failures.append((error, frame))
                deliver(self.hook, frame)
            raise
        else:
            successful = succeeded is None or succeeded()
            deliver(
                self.hook,
                event(
                    phase,
                    action,
                    "succeeded" if successful else "failed",
                    error_type="none" if successful else "unknown",
                    source_frame=source,
                    elapsed_ms=min(3_600_000, max(0, int((time.monotonic() - start) * 1000))),
                ),
            )
        finally:
            self.phase.reset(token)


@contextlib.contextmanager
def instrument_login(observer: LoginObserver, crawler: Any, login_class: Any, utils: Any) -> Iterator[None]:
    """Restore every child-local hook; capture actions before upstream catches.

    Missing optional shapes reduce diagnostics, not the underlying login. No
    arguments, selectors, response bodies or exception strings are inspected.
    """
    patches: list[tuple[Any, str, Any]] = []

    def wrap(
        owner: Any,
        name: str,
        phase: str | None,
        action: str,
        source: str,
        *,
        scope_only: bool = False,
    ) -> None:
        original = getattr(owner, name, None)
        if not callable(original):
            return

        async def observed(*args: Any, **kwargs: Any) -> Any:
            selected = phase or observer.phase.get()
            if name == "check_login_state":
                selected = "waiting_scan" if observer.qr_relayed.is_set() else "login_confirmation"
            if source == "httpx_get" and observer.phase.get() != "qr_locate":
                return await original(*args, **kwargs)
            if scope_only:
                token = observer.phase.set(selected)
                try:
                    return await original(*args, **kwargs)
                finally:
                    observer.phase.reset(token)
            result: Any = None
            succeeded = (lambda: isinstance(result, str) and bool(result)) if source == "qr_helper" else None
            with observer.span(selected, action, source, succeeded=succeeded):
                result = await original(*args, **kwargs)
            return result

        setattr(owner, name, observed)
        patches.append((owner, name, original))

    def wrap_navigation_context(owner: Any, name: str, source: str) -> None:
        original = getattr(owner, name, None)
        if not callable(original):
            return

        @contextlib.asynccontextmanager
        async def observe_wait(original_context: Any) -> AsyncIterator[Any]:
            with observer.span("platform_navigation", "wait_load", source):
                async with original_context as information:
                    yield information

        def observed(*args: Any, **kwargs: Any) -> Any:
            return observe_wait(original(*args, **kwargs))

        setattr(owner, name, observed)
        patches.append((owner, name, original))

    try:
        wrap(crawler, "launch_browser", "browser_launch", "launch", "runner")
        wrap(crawler, "_navigate_to_tieba_via_baidu", "platform_navigation", "navigate", "runner")
        wrap(login_class, "begin", "upstream_execution", "execute", "login")
        # In the pinned QR methods the click actions open the login dialog;
        # navigation, QR helper and confirmation scopes override this context.
        # Merely entering the method does not publish a dialog stage.
        wrap(login_class, "login_by_qrcode", "login_dialog", "execute", "login", scope_only=True)
        wrap(login_class, "popup_login_dialog", "login_dialog", "execute", "login")
        wrap(login_class, "check_login_state", None, "confirm", "login")
        wrap(utils, "find_login_qrcode", "qr_locate", "read_image", "qr_helper")
        wrap(utils, "find_qrcode_img_from_canvas", "qr_locate", "read_image", "qr_helper")
        try:
            api = importlib.import_module("playwright.async_api")
        except Exception:
            api = None
        shapes = (
            (
                "BrowserType",
                "browser_type",
                (("launch", "browser_launch", "launch"), ("launch_persistent_context", "browser_launch", "launch")),
            ),
            (
                "Page",
                "page",
                (
                    ("goto", "platform_navigation", "navigate"),
                    ("click", None, "click"),
                    ("wait_for_selector", None, "wait_selector"),
                    ("wait_for_load_state", None, "wait_load"),
                    ("wait_for_url", "platform_navigation", "wait_load"),
                ),
            ),
            (
                "Frame",
                "frame",
                (
                    ("goto", "platform_navigation", "navigate"),
                    ("click", None, "click"),
                    ("wait_for_selector", None, "wait_selector"),
                ),
            ),
            ("Locator", "locator", (("click", None, "click"), ("wait_for", None, "wait_selector"))),
            (
                "ElementHandle",
                "element_handle",
                (("click", None, "click"), ("get_property", None, "read_image"), ("screenshot", None, "read_image")),
            ),
        )
        for class_name, source, methods in shapes:
            owner = getattr(api, class_name, None)
            if owner is not None:
                for name, phase, action in methods:
                    wrap(owner, name, phase, action, source)
        for class_name, name, source in (
            ("Page", "expect_navigation", "page"),
            ("Frame", "expect_navigation", "frame"),
            ("BrowserContext", "expect_page", "browser_context"),
        ):
            owner = getattr(api, class_name, None)
            if owner is not None:
                wrap_navigation_context(owner, name, source)
        try:
            httpx = importlib.import_module("httpx")
        except Exception:
            httpx = None
        http_client = getattr(httpx, "AsyncClient", None)
        if http_client is not None:
            wrap(http_client, "get", "qr_image_fetch", "fetch", "httpx_get")
        yield
    finally:
        for owner, name, original in reversed(patches):
            setattr(owner, name, original)
