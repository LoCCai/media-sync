"""Authenticated, thin mounting adapter for the pinned MediaCrawler WebUI."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import importlib
import os
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MethodType, ModuleType
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from media_sync.config import Settings
from media_sync.security import redact_text

from .browser_environment import browser_child_environment
from .checkout import CheckoutValidationError, verify_mediacrawler_checkout, verify_mediacrawler_python
from .runner import _close_process_tree, _WindowsJob

_MAX_COOKIE_BYTES = 64 * 1024
_MAX_LOG_MESSAGE_CHARACTERS = 8 * 1024
_MAX_LOG_READ_CHARACTERS = _MAX_LOG_MESSAGE_CHARACTERS + _MAX_COOKIE_BYTES + 1
_MAX_LOG_QUEUE_ITEMS = 512
_MAX_QR_BYTES = 2 * 1024 * 1024
_MAX_QR_AGE_SECONDS = 180
_QR_ROUTE = "/api/crawler/qrcode"


class _PreparedCommand(list[str]):
    """Command plus the one-shot private material needed to launch it."""

    __slots__ = ("cookie_file", "known_secrets")

    def __init__(
        self,
        values: list[str],
        *,
        cookie_file: Path | None,
        known_secrets: tuple[str, ...],
    ) -> None:
        super().__init__(values)
        self.cookie_file = cookie_file
        self.known_secrets = known_secrets

    def detach(self) -> tuple[Path | None, tuple[str, ...]]:
        cookie_file = self.cookie_file
        known_secrets = self.known_secrets
        self.cookie_file = None
        self.known_secrets = ()
        return cookie_file, known_secrets

    def cleanup(self) -> None:
        cookie_file, _known_secrets = self.detach()
        if cookie_file is not None:
            with contextlib.suppress(OSError):
                cookie_file.unlink(missing_ok=True)


@dataclass(slots=True)
class _ManagedRun:
    process: Any
    cookie_file: Path | None
    known_secrets: tuple[str, ...]
    qr_path: Path
    windows_job: Any = None
    close_task: asyncio.Task[bool] | None = None
    resources_cleaned: bool = False


def _module_belongs_to(module: ModuleType, root: Path) -> bool:
    location = getattr(module, "__file__", None)
    if not isinstance(location, str):
        return False
    try:
        return Path(location).resolve().is_relative_to(root)
    except OSError:
        return False


def _import_upstream(checkout: Path, name: str) -> ModuleType:
    package = sys.modules.get("api")
    if isinstance(package, ModuleType) and not _module_belongs_to(package, checkout):
        raise RuntimeError("mediacrawler_webui_module_conflict")
    if str(checkout) not in sys.path:
        sys.path.insert(0, str(checkout))
    module = importlib.import_module(name)
    if not _module_belongs_to(module, checkout):
        raise RuntimeError("mediacrawler_webui_module_mismatch")
    return module


def _write_private_cookie(directory: Path, value: str) -> Path:
    try:
        encoded_size = len(value.encode("utf-8"))
    except (AttributeError, UnicodeError) as error:
        raise ValueError("mediacrawler_webui_cookie_invalid") from error
    if not 0 < encoded_size <= _MAX_COOKIE_BYTES:
        raise ValueError("mediacrawler_webui_cookie_invalid")
    directory.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        directory.chmod(0o700)
    path = directory / f"cookie-{uuid4().hex}.txt"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(value)
    except BaseException:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)
        raise
    return path


def _remove_private_cookies(directory: Path) -> None:
    """Remove only abandoned WebUI Cookie hand-off files."""

    try:
        candidates = tuple(directory.glob("cookie-*.txt"))
    except OSError:
        return
    for candidate in candidates:
        with contextlib.suppress(OSError):
            candidate.unlink(missing_ok=True)


def _configure_manager(
    manager: Any,
    *,
    checkout: Path,
    python: Path,
    runtime_root: Path,
) -> Any:
    output_root = runtime_root / "webui-output"
    profile_root = runtime_root / "webui-profiles"
    private_root = runtime_root / "webui-private"
    qr_path = runtime_root / "webui-login-qr.png"
    child = Path(__file__).with_name("webui_child.py").resolve()
    for directory in (output_root, profile_root, private_root):
        directory.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            directory.chmod(0o700)
    _remove_private_cookies(private_root)
    with contextlib.suppress(OSError):
        qr_path.unlink(missing_ok=True)

    manager._project_root = checkout
    manager._media_sync_qr_path = qr_path
    manager._media_sync_active_run = None
    manager._log_queue = asyncio.Queue(maxsize=_MAX_LOG_QUEUE_ITEMS)

    original_create_log_entry = manager._create_log_entry

    def create_log_entry(self: Any, message: str, level: str = "info") -> Any:
        del self
        safe_message = redact_text(str(message), max_length=_MAX_LOG_MESSAGE_CHARACTERS)
        return original_create_log_entry(safe_message, level)

    def build_command(self: Any, config: Any) -> _PreparedCommand:
        del self
        with contextlib.suppress(OSError):
            qr_path.unlink(missing_ok=True)
        cookie_file: Path | None = None
        raw_cookie = config.cookies
        cookie = raw_cookie if isinstance(raw_cookie, str) else ""
        known_secrets = (cookie,) if cookie else ()
        try:
            # Resolve every caller-controlled, non-secret argument before
            # materialising the one-shot Cookie file.  A malformed request
            # therefore cannot strand private input halfway through assembly.
            crawler_arguments = [
                "--platform",
                config.platform.value,
                "--lt",
                config.login_type.value,
                "--type",
                config.crawler_type.value,
                "--save_data_option",
                config.save_option.value,
            ]
            if config.crawler_type.value == "search" and config.keywords:
                crawler_arguments.extend(("--keywords", config.keywords))
            elif config.crawler_type.value == "detail" and config.specified_ids:
                crawler_arguments.extend(("--specified_id", config.specified_ids))
            elif config.crawler_type.value == "creator" and config.creator_ids:
                crawler_arguments.extend(("--creator_id", config.creator_ids))
            if config.start_page != 1:
                crawler_arguments.extend(("--start", str(config.start_page)))
            crawler_arguments.extend(("--get_comment", "true" if config.enable_comments else "false"))
            crawler_arguments.extend(("--get_sub_comment", "true" if config.enable_sub_comments else "false"))
            if config.max_notes_count is not None:
                crawler_arguments.extend(("--crawler_max_notes_count", str(config.max_notes_count)))
            if config.max_comments_count is not None:
                crawler_arguments.extend(("--max_comments_count_singlenotes", str(config.max_comments_count)))
            crawler_arguments.extend(("--headless", "true" if config.headless else "false"))

            command = [
                str(python),
                str(child),
                "--checkout",
                str(checkout),
                "--output-root",
                str(output_root),
                "--profile-root",
                str(profile_root),
                "--qr-path",
                str(qr_path),
            ]
            if cookie:
                cookie_file = _write_private_cookie(private_root, cookie)
                command.extend(("--cookie-file", str(cookie_file)))
            command.append("--")
            command.extend(crawler_arguments)
            return _PreparedCommand(
                command,
                cookie_file=cookie_file,
                known_secrets=known_secrets,
            )
        except BaseException:
            if cookie_file is not None:
                with contextlib.suppress(OSError):
                    cookie_file.unlink(missing_ok=True)
            raise

    def public_config(config: Any) -> Any | None:
        model_copy = getattr(config, "model_copy", None)
        if callable(model_copy):
            with contextlib.suppress(Exception):
                return model_copy(update={"cookies": ""})
        try:
            result = copy.copy(config)
            result.cookies = ""
            return result
        except Exception:
            return None

    async def push_log(
        self: Any,
        message: str,
        level: str = "info",
        *,
        known_secrets: tuple[str, ...] = (),
    ) -> None:
        safe_message = redact_text(
            message,
            known_secrets=known_secrets,
            max_length=_MAX_LOG_MESSAGE_CHARACTERS,
        )
        entry = self._create_log_entry(safe_message, level)
        await self._push_log(entry)

    async def close_tree(run: _ManagedRun) -> bool:
        if run.close_task is None:
            run.close_task = asyncio.create_task(asyncio.to_thread(_close_process_tree, run.process, run.windows_job))
        return bool(await asyncio.shield(run.close_task))

    def cleanup_resources(run: _ManagedRun) -> None:
        if run.resources_cleaned:
            return
        run.resources_cleaned = True
        if run.cookie_file is not None:
            with contextlib.suppress(OSError):
                run.cookie_file.unlink(missing_ok=True)
        run.cookie_file = None
        run.known_secrets = ()
        with contextlib.suppress(OSError):
            run.qr_path.unlink(missing_ok=True)

    async def read_output(self: Any, run: _ManagedRun | None = None) -> None:
        selected = run if run is not None else self._media_sync_active_run
        if not isinstance(selected, _ManagedRun):
            return
        process = selected.process
        stream = process.stdout
        try:
            if stream is not None:
                discarding_line = False
                while True:
                    chunk = await asyncio.to_thread(stream.readline, _MAX_LOG_READ_CHARACTERS)
                    if not chunk:
                        break
                    line_ended = chunk.endswith(("\n", "\r"))
                    if discarding_line:
                        if line_ended or len(chunk) < _MAX_LOG_READ_CHARACTERS:
                            discarding_line = False
                        continue
                    if not line_ended and len(chunk) >= _MAX_LOG_READ_CHARACTERS:
                        await push_log(
                            self,
                            "Crawler output line omitted because it exceeded the safety limit",
                            "warning",
                        )
                        discarding_line = True
                        continue
                    message = chunk.rstrip("\r\n")
                    if message:
                        level = self._parse_log_level(message)
                        await push_log(self, message, level, known_secrets=selected.known_secrets)

            return_code = process.poll()
            if return_code is None:
                return_code = await asyncio.to_thread(process.wait)
            if self._media_sync_active_run is selected and self.status == "running":
                if return_code == 0:
                    await push_log(self, "Crawler completed successfully", "success")
                else:
                    await push_log(self, f"Crawler exited with code: {return_code}", "warning")
                self.status = "idle"
                self.current_config = None
        except asyncio.CancelledError:
            raise
        except Exception:
            if self._media_sync_active_run is selected:
                self.status = "error"
                self.current_config = None
            await push_log(self, "Error reading crawler output", "error")
        finally:
            await close_tree(selected)
            if stream is not None:
                with contextlib.suppress(OSError, ValueError):
                    stream.close()
            cleanup_resources(selected)
            if self._media_sync_active_run is selected:
                self._media_sync_active_run = None
                self.process = None
                self.current_config = None
                if self.status in {"running", "stopping"}:
                    self.status = "idle"
            if self._read_task is asyncio.current_task():
                self._read_task = None

    async def await_reader(self: Any) -> None:
        reader = self._read_task
        if reader is not None and reader is not asyncio.current_task():
            with contextlib.suppress(asyncio.CancelledError):
                await reader

    async def start(self: Any, config: Any) -> bool:
        async with self._lock:
            active = self._media_sync_active_run
            if isinstance(active, _ManagedRun) and active.process.poll() is None:
                return False
            if isinstance(active, _ManagedRun):
                await close_tree(active)
            await await_reader(self)
            if isinstance(active, _ManagedRun):
                cleanup_resources(active)
                if self._media_sync_active_run is active:
                    self._media_sync_active_run = None
                    self.process = None
                    self.current_config = None

            self._logs = []
            self._log_id = 0
            while True:
                try:
                    self._log_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            prepared: _PreparedCommand | None = None
            process: Any = None
            run: _ManagedRun | None = None
            try:
                prepared = build_command(self, config)
                await push_log(
                    self,
                    f"Starting crawler: {' '.join(prepared)}",
                    known_secrets=prepared.known_secrets,
                )
                popen_options: dict[str, Any] = {
                    "stdout": subprocess.PIPE,
                    "stderr": subprocess.STDOUT,
                    "stdin": subprocess.DEVNULL,
                    "text": True,
                    "encoding": "utf-8",
                    "errors": "replace",
                    "bufsize": 1,
                    "cwd": str(checkout),
                    "env": {
                        **browser_child_environment(),
                        "PYTHONIOENCODING": "utf-8",
                        "PYTHONUTF8": "1",
                        "PYTHONUNBUFFERED": "1",
                    },
                    "shell": False,
                    "close_fds": True,
                }
                if os.name == "nt":
                    popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    popen_options["start_new_session"] = True
                process = subprocess.Popen(prepared, **popen_options)
                cookie_file, known_secrets = prepared.detach()
                run = _ManagedRun(
                    process=process,
                    cookie_file=cookie_file,
                    known_secrets=known_secrets,
                    qr_path=qr_path,
                )
                run.windows_job = _WindowsJob.attach(process)

                self.process = process
                self.status = "running"
                self.started_at = datetime.now()
                self.current_config = public_config(config)
                self._media_sync_active_run = run
                await push_log(
                    self,
                    f"Crawler started on platform: {config.platform.value}, type: {config.crawler_type.value}",
                    "success",
                )
                self._read_task = asyncio.create_task(read_output(self, run))
            except Exception:
                if prepared is not None:
                    prepared.cleanup()
                if process is not None:
                    orphan = run or _ManagedRun(process, None, (), qr_path)
                    await close_tree(orphan)
                    cleanup_resources(orphan)
                if self._media_sync_active_run is run:
                    self._media_sync_active_run = None
                self.process = None
                self.status = "error"
                self.current_config = None
                await push_log(self, "Failed to start crawler", "error")
                return False
            return True

    async def stop(self: Any) -> bool:
        async with self._lock:
            run = self._media_sync_active_run
            if not isinstance(run, _ManagedRun) or run.process.poll() is not None:
                if isinstance(run, _ManagedRun):
                    await close_tree(run)
                    await await_reader(self)
                    cleanup_resources(run)
                    if self._media_sync_active_run is run:
                        self._media_sync_active_run = None
                        self.process = None
                        self.current_config = None
                return False
            self.status = "stopping"
            await push_log(self, "Stopping crawler process tree...", "warning")
            stopped = await close_tree(run)
            await await_reader(self)
            self.status = "idle"
            self.current_config = None
            self.process = None
            if stopped:
                await push_log(self, "Crawler process tree terminated", "info")
            else:
                await push_log(self, "Crawler process tree cleanup could not be confirmed", "error")
            return stopped

    async def shutdown(self: Any) -> None:
        async with self._lock:
            run = self._media_sync_active_run
            if isinstance(run, _ManagedRun):
                self.status = "stopping"
                await close_tree(run)
            await await_reader(self)
            if isinstance(run, _ManagedRun):
                cleanup_resources(run)
            self._media_sync_active_run = None
            self.process = None
            self.current_config = None
            self.status = "idle"

    manager._create_log_entry = MethodType(create_log_entry, manager)
    manager._build_command = MethodType(build_command, manager)
    manager._read_output = MethodType(read_output, manager)
    manager.start = MethodType(start, manager)
    manager.stop = MethodType(stop, manager)
    manager.shutdown = MethodType(shutdown, manager)
    return manager


def _unavailable_app() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])
    async def unavailable(path: str) -> JSONResponse:
        del path
        return JSONResponse(
            status_code=503,
            content={"detail": "mediacrawler_webui_unavailable"},
            headers={"Cache-Control": "no-store"},
        )

    return app


def _current_qr_response(path: Path) -> Response:
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or not 0 < metadata.st_size <= _MAX_QR_BYTES
            or time.time() - metadata.st_mtime > _MAX_QR_AGE_SECONDS
        ):
            raise OSError
        content = path.read_bytes()
    except OSError:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="mediacrawler_qr_unavailable") from None
    if len(content) != metadata.st_size:
        raise HTTPException(status_code=404, detail="mediacrawler_qr_unavailable")
    return Response(
        content=content,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "X-Media-Sync-QR-Digest": hashlib.sha256(content).hexdigest(),
        },
    )


def _install_environment_check(upstream_app: FastAPI, *, commit: str, python: Path) -> None:
    """Replace upstream's ``uv run`` probe with the already-qualified runtime.

    The checkout and interpreter are verified before the upstream application
    is mounted.  Running ``uv`` here would create another environment inside
    the locked checkout and could unexpectedly require network access.
    """

    matches = [
        index
        for index, route in enumerate(upstream_app.router.routes)
        if getattr(route, "path", None) == "/api/env/check" and "GET" in (getattr(route, "methods", None) or set())
    ]
    if len(matches) != 1:
        raise RuntimeError("mediacrawler_webui_environment_route_mismatch")
    route_index = matches[0]
    upstream_app.router.routes.pop(route_index)

    async def qualified_environment() -> dict[str, object]:
        return {
            "success": True,
            "message": "Pinned MediaCrawler runtime is ready",
            "output": f"commit={commit}; python={python}",
        }

    upstream_app.add_api_route(
        "/api/env/check",
        qualified_environment,
        methods=["GET"],
        include_in_schema=False,
    )
    installed = upstream_app.router.routes.pop()
    upstream_app.router.routes.insert(route_index, installed)


def _enforce_same_origin(upstream_app: FastAPI) -> None:
    """Remove the upstream development CORS grant before mounting it."""

    if getattr(upstream_app.state, "media_sync_same_origin", False) is True:
        return
    retained = [
        middleware
        for middleware in upstream_app.user_middleware
        if getattr(middleware, "cls", None) is not CORSMiddleware
    ]
    if len(retained) == len(upstream_app.user_middleware):
        raise RuntimeError("mediacrawler_webui_cors_boundary_missing")
    upstream_app.user_middleware[:] = retained
    upstream_app.middleware_stack = None
    upstream_app.state.media_sync_same_origin = True


def create_mediacrawler_webui_app(settings: Settings) -> FastAPI:
    """Return the pinned upstream app, or a fixed-code unavailable surface."""

    if settings.mediacrawler_python_executable is None:
        return _unavailable_app()
    try:
        checkout = verify_mediacrawler_checkout(settings.mediacrawler_lock_path, license_acknowledged=True)
        python = verify_mediacrawler_python(settings.mediacrawler_python_executable)
        main_module = _import_upstream(checkout.root, "api.main")
        crawler_module = _import_upstream(checkout.root, "api.routers.crawler")
        data_module = _import_upstream(checkout.root, "api.routers.data")
        websocket_module = _import_upstream(checkout.root, "api.routers.websocket")
        services_module = _import_upstream(checkout.root, "api.services")
        manager_module = _import_upstream(checkout.root, "api.services.crawler_manager")
    except (CheckoutValidationError, ImportError, OSError, RuntimeError):
        return _unavailable_app()

    runtime_root = settings.resolved_mediacrawler_runtime_dir
    manager = _configure_manager(
        manager_module.CrawlerManager(),
        checkout=checkout.root,
        python=python.executable,
        runtime_root=runtime_root,
    )
    services_module.__dict__["crawler_manager"] = manager
    crawler_module.__dict__["crawler_manager"] = manager
    websocket_module.__dict__["crawler_manager"] = manager
    output_root = runtime_root / "webui-output"
    data_module.__dict__["DATA_DIR"] = output_root
    upstream_app: FastAPI = main_module.app
    _enforce_same_origin(upstream_app)
    _install_environment_check(upstream_app, commit=checkout.commit, python=python.executable)
    upstream_app.state.media_sync_qr_path = runtime_root / "webui-login-qr.png"
    upstream_app.state.media_sync_output_root = output_root
    upstream_app.state.media_sync_manager = manager
    upstream_app.state.media_sync_shutdown = manager.shutdown

    if not any(getattr(route, "path", None) == _QR_ROUTE for route in upstream_app.routes):

        @upstream_app.get(_QR_ROUTE, include_in_schema=False)
        async def current_qr(request: Request) -> Response:
            return _current_qr_response(request.app.state.media_sync_qr_path)

    return upstream_app


__all__ = ["create_mediacrawler_webui_app"]
