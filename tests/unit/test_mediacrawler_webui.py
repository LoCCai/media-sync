from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import json
import os
import stat
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from starlette.middleware.cors import CORSMiddleware

from media_sync.config import Settings
from media_sync.integrations.mediacrawler import webui as webui_module
from media_sync.integrations.mediacrawler.webui import (
    _MAX_LOG_QUEUE_ITEMS,
    _MAX_LOG_READ_CHARACTERS,
    _configure_manager,
    _current_qr_response,
    _enforce_same_origin,
    _install_environment_check,
    create_mediacrawler_webui_app,
)
from media_sync.integrations.mediacrawler.webui_child import run


class _Manager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.process: Any = None
        self.status = "idle"
        self.started_at: Any = None
        self.current_config: Any = None
        self._log_id = 0
        self._logs: list[SimpleNamespace] = []
        self._read_task: asyncio.Task[None] | None = None
        self._log_queue: asyncio.Queue[SimpleNamespace] | None = None

    @property
    def logs(self) -> list[SimpleNamespace]:
        return self._logs

    def get_log_queue(self) -> asyncio.Queue[SimpleNamespace]:
        if self._log_queue is None:
            self._log_queue = asyncio.Queue()
        return self._log_queue

    def _create_log_entry(self, message: str, level: str = "info") -> SimpleNamespace:
        self._log_id += 1
        entry = SimpleNamespace(id=self._log_id, level=level, message=message)
        self._logs.append(entry)
        if len(self._logs) > 500:
            self._logs = self._logs[-500:]
        return entry

    async def _push_log(self, entry: SimpleNamespace) -> None:
        if self._log_queue is not None:
            with contextlib.suppress(asyncio.QueueFull):
                self._log_queue.put_nowait(entry)

    def _parse_log_level(self, line: str) -> str:
        return "error" if "ERROR" in line.upper() else "info"


class _OsProxy:
    def __init__(self, name: str) -> None:
        self.name = name

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)


class _FakeProcess:
    def __init__(self, output: Any, *, returncode: int | None = None) -> None:
        self.stdout = output
        self.returncode = returncode
        self.pid = 4815

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class _BlockingStream:
    def __init__(self) -> None:
        self.released = threading.Event()
        self.closed = False

    def readline(self, size: int = -1) -> str:
        del size
        if not self.released.wait(timeout=5):
            raise TimeoutError("test process was not released")
        return ""

    def close(self) -> None:
        self.closed = True


def _messages(manager: _Manager) -> list[str]:
    return [str(entry.message) for entry in manager.logs]


def _config(cookie: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        platform=SimpleNamespace(value="bili"),
        login_type=SimpleNamespace(value="cookie" if cookie else "qrcode"),
        crawler_type=SimpleNamespace(value="creator"),
        save_option=SimpleNamespace(value="jsonl"),
        keywords="",
        specified_ids="",
        creator_ids="252671524",
        start_page=1,
        enable_comments=False,
        enable_sub_comments=False,
        max_notes_count=3,
        max_comments_count=None,
        cookies=cookie,
        headless=False,
    )


def test_manager_uses_fixed_runtime_and_keeps_cookie_out_of_argv(tmp_path: Path) -> None:
    child = Path(__file__).parents[2] / "src" / "media_sync" / "integrations" / "mediacrawler" / "webui_child.py"
    manager = _configure_manager(
        _Manager(),
        checkout=tmp_path / "checkout",
        python=tmp_path / "venv" / "python",
        runtime_root=tmp_path / "runtime",
    )
    secret = "SESSDATA=private-cookie-value"
    command = manager._build_command(_config(secret))

    assert command[0] == str(tmp_path / "venv" / "python")
    assert command[1] == str(child.resolve())
    assert "uv" not in command
    assert secret not in command and secret not in " ".join(command)
    assert command[command.index("--output-root") + 1] == str(tmp_path / "runtime" / "webui-output")
    assert command[command.index("--creator_id") + 1] == "252671524"
    cookie_path = Path(command[command.index("--cookie-file") + 1])
    assert cookie_path.read_text(encoding="utf-8") == secret
    if os.name != "nt":
        assert stat.S_IMODE(cookie_path.stat().st_mode) == 0o600
    command.cleanup()
    assert not cookie_path.exists()


def test_manager_does_not_materialise_cookie_before_public_arguments_are_valid(tmp_path: Path) -> None:
    manager = _configure_manager(
        _Manager(),
        checkout=tmp_path / "checkout",
        python=tmp_path / "venv" / "python",
        runtime_root=tmp_path / "runtime",
    )
    config = _config("SESSDATA=must-not-be-stranded")

    class ExplodingValue:
        def __bool__(self) -> bool:
            raise RuntimeError("synthetic invalid creator input")

    config.creator_ids = ExplodingValue()
    with pytest.raises(RuntimeError, match="synthetic invalid creator input"):
        manager._build_command(config)

    assert list((tmp_path / "runtime" / "webui-private").iterdir()) == []


def test_manager_removes_only_abandoned_cookie_handoffs(tmp_path: Path) -> None:
    private_root = tmp_path / "runtime" / "webui-private"
    private_root.mkdir(parents=True)
    abandoned = private_root / "cookie-deadbeef.txt"
    unrelated = private_root / "keep.txt"
    abandoned.write_text("secret", encoding="utf-8")
    unrelated.write_text("keep", encoding="utf-8")

    _configure_manager(
        _Manager(),
        checkout=tmp_path / "checkout",
        python=tmp_path / "venv" / "python",
        runtime_root=tmp_path / "runtime",
    )

    assert not abandoned.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(("platform_name", "operation"), [("nt", "stop"), ("posix", "shutdown")])
def test_manager_owns_process_group_and_joins_reader_before_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform_name: str,
    operation: str,
) -> None:
    stream = _BlockingStream()
    process = _FakeProcess(stream)
    popen_calls: list[tuple[list[str], dict[str, Any]]] = []
    close_calls: list[tuple[_FakeProcess, object | None]] = []
    attach_calls: list[_FakeProcess] = []
    windows_job = object() if platform_name == "nt" else None

    def popen(command: list[str], **options: Any) -> _FakeProcess:
        popen_calls.append((list(command), options))
        return process

    def close_tree(selected: _FakeProcess, job: object | None) -> bool:
        close_calls.append((selected, job))
        selected.returncode = -15
        selected.stdout.released.set()
        return True

    class WindowsJob:
        @staticmethod
        def attach(selected: _FakeProcess) -> object | None:
            attach_calls.append(selected)
            return windows_job

    monkeypatch.setattr(webui_module, "os", _OsProxy(platform_name))
    monkeypatch.setattr(webui_module.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    monkeypatch.setattr(webui_module.subprocess, "Popen", popen)
    monkeypatch.setattr(webui_module, "_close_process_tree", close_tree)
    monkeypatch.setattr(webui_module, "_WindowsJob", WindowsJob)
    monkeypatch.setenv("MEDIA_SYNC_OPERATOR_PASSWORD", "must-not-reach-crawler")
    manager = _configure_manager(
        _Manager(),
        checkout=tmp_path / "checkout",
        python=tmp_path / "venv" / "python",
        runtime_root=tmp_path / "runtime",
    )
    config = _config("SESSDATA=private-lifecycle-cookie")

    async def exercise() -> tuple[Any, asyncio.Task[None], bool | None]:
        assert await manager.start(config) is True
        active = manager._media_sync_active_run
        reader = manager._read_task
        assert active is not None
        assert reader is not None
        assert manager.current_config.cookies == ""
        active.qr_path.write_bytes(b"temporary-qr")
        if operation == "stop":
            result: bool | None = await manager.stop()
        else:
            await manager.shutdown()
            result = None
        return active, reader, result

    active, reader, result = asyncio.run(exercise())

    assert result is (True if operation == "stop" else None)
    assert reader.done()
    assert stream.closed is True
    assert close_calls == [(process, windows_job)]
    assert attach_calls == [process]
    assert active.resources_cleaned is True
    assert active.cookie_file is None
    assert active.known_secrets == ()
    assert not active.qr_path.exists()
    assert manager._media_sync_active_run is None
    assert manager._read_task is None
    assert manager.process is None
    assert manager.current_config is None
    assert manager.status == "idle"
    assert len(popen_calls) == 1
    command, options = popen_calls[0]
    assert "SESSDATA=private-lifecycle-cookie" not in command
    assert options["shell"] is False
    assert options["close_fds"] is True
    assert options["env"]["PYTHONIOENCODING"] == "utf-8"
    assert options["env"]["PYTHONUTF8"] == "1"
    assert options["env"]["PYTHONUNBUFFERED"] == "1"
    assert "MEDIA_SYNC_OPERATOR_PASSWORD" not in options["env"]
    if platform_name == "nt":
        assert options["creationflags"] == 0x200
        assert "start_new_session" not in options
    else:
        assert options["start_new_session"] is True
        assert "creationflags" not in options


def test_manager_start_failure_removes_private_cookie(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "SESSDATA=private-start-failure"

    def fail_to_start(_command: list[str], **_options: Any) -> _FakeProcess:
        raise OSError("synthetic spawn failure")

    monkeypatch.setattr(webui_module.subprocess, "Popen", fail_to_start)
    manager = _configure_manager(
        _Manager(),
        checkout=tmp_path / "checkout",
        python=tmp_path / "venv" / "python",
        runtime_root=tmp_path / "runtime",
    )

    assert asyncio.run(manager.start(_config(secret))) is False
    assert manager.status == "error"
    assert manager.process is None
    assert list((tmp_path / "runtime" / "webui-private").iterdir()) == []
    assert all(secret not in message for message in _messages(manager))


def test_manager_redacts_output_and_cleans_natural_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "SESSDATA=private-output-cookie"
    process = _FakeProcess(io.StringIO(f"echoed {secret}\ntoken=generic-secret\nnormal line\n"))
    close_calls: list[_FakeProcess] = []

    def close_tree(selected: _FakeProcess, _job: object | None) -> bool:
        close_calls.append(selected)
        return True

    monkeypatch.setattr(webui_module.subprocess, "Popen", lambda _command, **_options: process)
    monkeypatch.setattr(webui_module, "_close_process_tree", close_tree)
    monkeypatch.setattr(webui_module._WindowsJob, "attach", lambda _process: None)
    manager = _configure_manager(
        _Manager(),
        checkout=tmp_path / "checkout",
        python=tmp_path / "venv" / "python",
        runtime_root=tmp_path / "runtime",
    )

    async def exercise() -> Any:
        assert await manager.start(_config(secret)) is True
        active = manager._media_sync_active_run
        reader = manager._read_task
        assert active is not None
        assert reader is not None
        assert manager.current_config.cookies == ""
        await reader
        return active

    active = asyncio.run(exercise())
    messages = _messages(manager)

    assert close_calls == [process]
    assert all(secret not in message and "generic-secret" not in message for message in messages)
    assert any("echoed [REDACTED]" in message for message in messages)
    assert any("token=[REDACTED]" in message for message in messages)
    assert active.resources_cleaned is True
    assert active.cookie_file is None
    assert active.known_secrets == ()
    assert manager._media_sync_active_run is None
    assert manager._read_task is None
    assert manager.process is None
    assert manager.current_config is None
    assert manager.status == "idle"


def test_manager_omits_cross_chunk_line_and_bounds_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "SESSDATA=" + "s" * 128
    prefix = "x" * (_MAX_LOG_READ_CHARACTERS - len(secret) // 2)
    output = "".join(f"bounded line {index}\n" for index in range(520)) + prefix + secret + "\n"
    process = _FakeProcess(io.StringIO(output))
    monkeypatch.setattr(webui_module.subprocess, "Popen", lambda _command, **_options: process)
    monkeypatch.setattr(webui_module, "_close_process_tree", lambda _process, _job: True)
    monkeypatch.setattr(webui_module._WindowsJob, "attach", lambda _process: None)
    manager = _configure_manager(
        _Manager(),
        checkout=tmp_path / "checkout",
        python=tmp_path / "venv" / "python",
        runtime_root=tmp_path / "runtime",
    )

    async def exercise() -> None:
        assert await manager.start(_config(secret)) is True
        reader = manager._read_task
        assert reader is not None
        await reader

    asyncio.run(exercise())
    messages = _messages(manager)

    assert len(manager.logs) == 500
    assert manager._log_queue.maxsize == _MAX_LOG_QUEUE_ITEMS
    assert manager._log_queue.qsize() == _MAX_LOG_QUEUE_ITEMS
    assert all(secret not in message and prefix not in message for message in messages)
    assert messages.count("Crawler output line omitted because it exceeded the safety limit") == 1


def test_child_applies_media_output_profile_cookie_and_qr_relay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "config").mkdir(parents=True)
    (checkout / "tools").mkdir()
    (checkout / "config" / "__init__.py").write_text("", encoding="utf-8")
    (checkout / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (checkout / "tools" / "utils.py").write_text(
        "def show_qrcode(value):\n    raise AssertionError(value)\n", encoding="utf-8"
    )
    (checkout / "tools" / "app_runner.py").write_text(
        "import asyncio\n"
        "def run(main, cleanup, **_kwargs):\n"
        "    async def execute():\n"
        "        try:\n"
        "            await main()\n"
        "        finally:\n"
        "            await cleanup()\n"
        "    asyncio.run(execute())\n",
        encoding="utf-8",
    )
    result = tmp_path / "result.json"
    qr_path = tmp_path / "runtime" / "webui-login-qr.png"
    (checkout / "main.py").write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "import config\n"
        "from tools import utils\n"
        "class DummyCrawler:\n"
        "    async def launch_browser(self, chromium, **kwargs):\n"
        "        return chromium, kwargs\n"
        "class CrawlerFactory:\n"
        "    @staticmethod\n"
        "    def create_crawler(platform):\n"
        "        return DummyCrawler()\n"
        "async def main():\n"
        "    utils.show_qrcode(os.environ['MEDIA_SYNC_TEST_QR'])\n"
        "    crawler = CrawlerFactory.create_crawler('bili')\n"
        "    Path(os.environ['MEDIA_SYNC_TEST_RESULT']).write_text(json.dumps({\n"
        "      'media': config.ENABLE_GET_MEIDAS,\n"
        "      'output': config.SAVE_DATA_PATH,\n"
        "      'profile': config.USER_DATA_DIR,\n"
        "      'cookie_in_child': os.environ['MEDIA_SYNC_TEST_COOKIE'] in sys.argv,\n"
        "      'qr_visible_during_run': Path(os.environ['MEDIA_SYNC_TEST_QR_PATH']).is_file(),\n"
        "      'bundled_browser_policy': hasattr(crawler.launch_browser, '_media_sync_bundled_chromium_policy'),\n"
        "    }), encoding='utf-8')\n"
        "async def async_cleanup():\n"
        "    return None\n",
        encoding="utf-8",
    )
    image = Image.new("RGB", (4, 4), "white")
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    cookie = "SESSDATA=child-private-value"
    cookie_path = tmp_path / "cookie.txt"
    cookie_path.write_text(cookie, encoding="utf-8")
    if os.name != "nt":
        cookie_path.chmod(0o600)
    monkeypatch.setenv("MEDIA_SYNC_TEST_QR", base64.b64encode(encoded.getvalue()).decode("ascii"))
    monkeypatch.setenv("MEDIA_SYNC_TEST_RESULT", str(result))
    monkeypatch.setenv("MEDIA_SYNC_TEST_COOKIE", cookie)
    monkeypatch.setenv("MEDIA_SYNC_TEST_QR_PATH", str(qr_path))
    previous_cwd = Path.cwd()
    previous_argv = sys.argv
    module_names = ("config", "main", "tools", "tools.utils", "tools.app_runner")
    removed = {name: sys.modules.pop(name, None) for name in module_names}
    try:
        run(
            [
                "--checkout",
                str(checkout),
                "--output-root",
                str(tmp_path / "runtime" / "webui-output"),
                "--profile-root",
                str(tmp_path / "runtime" / "webui-profiles"),
                "--qr-path",
                str(qr_path),
                "--cookie-file",
                str(cookie_path),
                "--",
                "--platform",
                "bili",
            ]
        )
    finally:
        os.chdir(previous_cwd)
        sys.argv = previous_argv
        for name in module_names:
            sys.modules.pop(name, None)
        sys.modules.update({name: module for name, module in removed.items() if module is not None})
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload == {
        "media": True,
        "output": str(tmp_path / "runtime" / "webui-output"),
        "profile": str(tmp_path / "runtime" / "webui-profiles" / "%s_user_data_dir"),
        "cookie_in_child": True,
        "qr_visible_during_run": True,
        "bundled_browser_policy": True,
    }
    assert not cookie_path.exists()
    assert not qr_path.exists()


def test_unconfigured_console_fails_with_fixed_code(tmp_path: Path) -> None:
    settings = Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "library",
        job_dir=tmp_path / "jobs",
        mediacrawler_python_executable=None,
    )
    with TestClient(create_mediacrawler_webui_app(settings)) as client:
        response = client.get("/")
    assert response.status_code == 503
    assert response.json() == {"detail": "mediacrawler_webui_unavailable"}
    assert response.headers["cache-control"] == "no-store"


def test_qr_response_is_bounded_private_and_no_store(tmp_path: Path) -> None:
    path = tmp_path / "qr.png"
    content = b"synthetic-png-bytes"
    path.write_bytes(content)
    response = _current_qr_response(path)
    assert response.body == content
    assert response.media_type == "image/png"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert len(response.headers["x-media-sync-qr-digest"]) == 64


def test_environment_check_uses_already_qualified_runtime(tmp_path: Path) -> None:
    app = FastAPI()

    @app.get("/api/env/check")
    async def unsafe_upstream_probe() -> dict[str, bool]:
        raise AssertionError("upstream uv probe must not run")

    python = tmp_path / "venv" / "python"
    _install_environment_check(app, commit="a" * 40, python=python)

    with TestClient(app) as client:
        response = client.get("/api/env/check")
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Pinned MediaCrawler runtime is ready",
        "output": f"commit={'a' * 40}; python={python}",
    }


def test_same_origin_boundary_removes_upstream_development_cors() -> None:
    app = FastAPI()

    @app.get("/")
    async def index() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    with TestClient(app) as client:
        before = client.get("/", headers={"Origin": "http://localhost:5173"})
    assert before.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert before.headers["access-control-allow-credentials"] == "true"

    _enforce_same_origin(app)
    _enforce_same_origin(app)

    with TestClient(app) as client:
        after = client.get("/", headers={"Origin": "http://localhost:5173"})
    assert after.status_code == 200
    assert "access-control-allow-origin" not in after.headers
    assert "access-control-allow-credentials" not in after.headers
