from __future__ import annotations

import contextlib
import csv
import json
import multiprocessing
import os
import subprocess
import sys
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import login_runner as runner_module
from media_sync.integrations.mediacrawler.checkout import VerifiedCheckout, VerifiedPython
from media_sync.integrations.mediacrawler.login import (
    MediaCrawlerLoginMode,
    MediaCrawlerLoginRequest,
    MediaCrawlerLoginResult,
    MediaCrawlerLoginStatus,
)
from media_sync.integrations.mediacrawler.login_runner import MediaCrawlerLoginProcessRunner
from media_sync.integrations.mediacrawler.policies import build_run_paths
from media_sync.integrations.mediacrawler.runner import _AccountFileLock

UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
ACCOUNT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

_LOGIN_CLASS_NAMES = {
    Platform.XHS: "XiaoHongShuLogin",
    Platform.DY: "DouYinLogin",
    Platform.KS: "KuaishouLogin",
    Platform.BILI: "BilibiliLogin",
    Platform.WB: "WeiboLogin",
    Platform.TIEBA: "BaiduTieBaLogin",
    Platform.ZHIHU: "ZhiHuLogin",
}
_CORE_PACKAGE_NAMES = {
    Platform.XHS: "xhs",
    Platform.DY: "douyin",
    Platform.KS: "kuaishou",
    Platform.BILI: "bilibili",
    Platform.WB: "weibo",
    Platform.TIEBA: "tieba",
    Platform.ZHIHU: "zhihu",
}

_CONFIG = """
PLATFORM = "xhs"
LOGIN_TYPE = "qrcode"
CRAWLER_TYPE = "search"
COOKIES = "must-be-cleared"
"""

_MAIN = """
import importlib
from pathlib import Path

import config

Path(__file__).with_name("upstream-imported").write_text("imported", encoding="utf-8")
crawler = None
PACKAGES = {
    "xhs": "xhs",
    "dy": "douyin",
    "ks": "kuaishou",
    "bili": "bilibili",
    "wb": "weibo",
    "tieba": "tieba",
    "zhihu": "zhihu",
}


class CrawlerFactory:
    @staticmethod
    def create_crawler(platform):
        module = importlib.import_module(f"media_platform.{PACKAGES[platform]}.core")
        return module.FakeCrawler()


async def async_cleanup():
    return None
"""

_UTILS = """
def show_qrcode(value):
    raise RuntimeError("QR bytes escaped the headed browser")
"""

_CORE_TEMPLATE = r"""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import config
from tools import utils

ROOT = Path(__file__).resolve().parents[2]
LOGIN_CLASS = "{login_class}"
FACTORY_NAME = "{factory_name}"


def profile_root():
    return Path(os.path.join(os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM)).resolve()


def mode():
    return (ROOT / "mode.txt").read_text(encoding="utf-8").strip()


class FakeClient:
    async def pong(self, *args, **kwargs):
        return (profile_root() / "authenticated.state").is_file() and mode() != "expired"

    async def update_cookies(self, *args, **kwargs):
        if mode() == "linger_after_result":
            grandchild = subprocess.Popen(
                [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            (ROOT / "pids.json").write_text(
                json.dumps({{"child": os.getpid(), "grandchild": grandchild.pid}}),
                encoding="utf-8",
            )
        return None


class {login_class}:
    def __init__(self, *args, **kwargs):
        return None

    async def begin(self):
        selected = mode()
        if selected == "system_exit":
            raise SystemExit(0)
        if selected in {{"hang", "cancel"}}:
            grandchild = subprocess.Popen(
                [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            (ROOT / "pids.json").write_text(
                json.dumps({{"child": os.getpid(), "grandchild": grandchild.pid}}),
                encoding="utf-8",
            )
            while True:
                await asyncio.sleep(1)
        utils.show_qrcode("QR-SECRET-MUST-STAY-IN-BROWSER")
        target = profile_root()
        target.mkdir(parents=True, exist_ok=True)
        (target / "authenticated.state").write_text("ok", encoding="utf-8")


class FakeCrawler:
    async def _create_client(self, *_args, **_kwargs):
        return FakeClient()

    async def start(self):
        client = await getattr(self, FACTORY_NAME)(None)
        if not await client.pong():
            login = globals()[LOGIN_CLASS]()
            await login.begin()
            await client.update_cookies()
        if config.CRAWLER_TYPE in {{"search", "detail", "creator"}}:
            (ROOT / "content-side-effect").write_text(config.CRAWLER_TYPE, encoding="utf-8")


setattr(FakeCrawler, FACTORY_NAME, FakeCrawler._create_client)
"""


def _write_fake_checkout(root: Path) -> Path:
    root.mkdir()
    (root / "config.py").write_text(textwrap.dedent(_CONFIG), encoding="utf-8")
    (root / "main.py").write_text(textwrap.dedent(_MAIN), encoding="utf-8")
    (root / "mode.txt").write_text("success", encoding="utf-8")
    tools = root / "tools"
    tools.mkdir()
    (tools / "__init__.py").write_text("", encoding="utf-8")
    (tools / "utils.py").write_text(textwrap.dedent(_UTILS), encoding="utf-8")
    media_platform = root / "media_platform"
    media_platform.mkdir()
    (media_platform / "__init__.py").write_text("", encoding="utf-8")
    for platform in Platform:
        package = media_platform / _CORE_PACKAGE_NAMES[platform]
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        source = _CORE_TEMPLATE.format(
            login_class=_LOGIN_CLASS_NAMES[platform],
            factory_name=runner_module._CLIENT_FACTORY_NAMES[platform],
        )
        (package / "core.py").write_text(textwrap.dedent(source), encoding="utf-8")
    return root


def _runner(
    checkout: Path,
    integration_root: Path,
    *,
    enabled: bool = True,
    license_acknowledged: bool = True,
) -> MediaCrawlerLoginProcessRunner:
    def verify_checkout(_lock_path: Path, acknowledged: bool) -> VerifiedCheckout:
        assert acknowledged
        return VerifiedCheckout(
            root=checkout,
            commit=UPSTREAM_SHA,
            repository="https://github.com/NanmiCoder/MediaCrawler.git",
            license_name="NON-COMMERCIAL LEARNING LICENSE 1.1",
            lock_path=checkout / "upstreams.lock.json",
        )

    def verify_python(_executable: Path) -> VerifiedPython:
        return VerifiedPython(executable=Path(sys.executable).resolve())

    return MediaCrawlerLoginProcessRunner(
        lock_path=checkout / "upstreams.lock.json",
        integration_root=integration_root,
        python_executable=Path(sys.executable),
        enabled=enabled,
        license_acknowledged=license_acknowledged,
        checkout_verifier=verify_checkout,
        python_verifier=verify_python,
    )


def _request(
    platform: Platform,
    mode: MediaCrawlerLoginMode,
    *,
    timeout_seconds: float = 10.0,
) -> MediaCrawlerLoginRequest:
    return MediaCrawlerLoginRequest(
        account_id=ACCOUNT_ID,
        platform=platform,
        mode=mode,
        timeout_seconds=timeout_seconds,
        poll_seconds=0.02,
    )


def _pid_is_alive(process_id: int) -> bool:
    if os.name == "nt":
        completed = subprocess.run(
            ("tasklist.exe", "/FI", f"PID eq {process_id}", "/FO", "CSV", "/NH"),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return any(
            len(row) > 1 and row[1].isdigit() and int(row[1]) == process_id
            for row in csv.reader(completed.stdout.splitlines())
        )
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    return True


def _wait_for_pids_to_exit(*process_ids: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and any(_pid_is_alive(process_id) for process_id in process_ids):
        time.sleep(0.05)
    assert all(not _pid_is_alive(process_id) for process_id in process_ids)


def _wait_for_json(path: Path, timeout: float = 10.0) -> dict[str, int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            time.sleep(0.02)
            continue
        if isinstance(value, dict) and all(isinstance(item, int) for item in value.values()):
            return value
        time.sleep(0.02)
    raise AssertionError("login process probe was not written within the deadline")


def _parse_result_wire(wire: bytes) -> MediaCrawlerLoginStatus:
    length_bytes = wire[: runner_module._LOGIN_RESULT_LENGTH_BYTES]
    assert len(length_bytes) == runner_module._LOGIN_RESULT_LENGTH_BYTES
    length = int.from_bytes(length_bytes, byteorder="big")
    payload = wire[runner_module._LOGIN_RESULT_LENGTH_BYTES :]
    assert len(payload) == length
    return runner_module._parse_child_frame(payload)


def _raw_child_environment() -> dict[str, str]:
    environment = {
        name: value for name, value in os.environ.items() if name.upper() in runner_module._CHILD_ENV_ALLOWLIST
    }
    environment.update(
        {
            runner_module._CONTROL_ENV: runner_module._CONTROL_VERSION,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return environment


def _spawn_raw_login_child(checkout: Path) -> subprocess.Popen[bytes]:
    command = (
        sys.executable,
        "-I",
        "-u",
        "-B",
        str(Path(runner_module.__file__).resolve()),
        "--child",
    )
    common: dict[str, object] = {
        "cwd": checkout,
        "env": _raw_child_environment(),
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        return subprocess.Popen(
            command,
            creationflags=(
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            ),
            **common,  # type: ignore[arg-type]
        )
    return subprocess.Popen(command, start_new_session=True, **common)  # type: ignore[arg-type]


def _raw_login_payload(checkout: Path, integration_root: Path) -> bytes:
    verified = VerifiedCheckout(
        root=checkout,
        commit=UPSTREAM_SHA,
        repository="https://github.com/NanmiCoder/MediaCrawler.git",
        license_name="NON-COMMERCIAL LEARNING LICENSE 1.1",
        lock_path=checkout / "upstreams.lock.json",
    )
    paths = build_run_paths(integration_root, Platform.XHS, ACCOUNT_ID, ACCOUNT_ID)
    return runner_module._child_payload(
        _request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR, timeout_seconds=60),
        verified,
        paths,
    )


def _force_close_raw_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    _force_close_pid_tree(process.pid)
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        process.wait(timeout=5)


def _force_close_pid_tree(process_id: int) -> None:
    if not _pid_is_alive(process_id):
        return
    if os.name == "nt":
        subprocess.run(
            ("taskkill.exe", "/PID", str(process_id), "/T", "/F"),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            shell=False,
        )
    else:
        with contextlib.suppress(OSError):
            os.killpg(process_id, 9)


def _hard_kill_parent(process_id: int) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ("taskkill.exe", "/PID", str(process_id), "/F"),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            shell=False,
        )
        assert completed.returncode == 0
        return
    os.kill(process_id, 9)


def _run_hard_death_login_parent(checkout: Path, integration_root: Path, parent_probe: Path) -> None:
    parent_probe.write_text(json.dumps({"parent": os.getpid()}), encoding="utf-8")
    _runner(checkout, integration_root).run(
        _request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR, timeout_seconds=60)
    )


def _run_hard_death_after_login_result(
    checkout: Path,
    integration_root: Path,
    parent_probe: Path,
    close_probe: Path,
) -> None:
    original_close = runner_module._close_control

    def delay_parent_close(process: subprocess.Popen[bytes]) -> None:
        close_probe.write_text(json.dumps({"parent": os.getpid()}), encoding="utf-8")
        time.sleep(60)
        original_close(process)

    runner_module._close_control = delay_parent_close
    parent_probe.write_text(json.dumps({"parent": os.getpid()}), encoding="utf-8")
    _runner(checkout, integration_root).run(
        _request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR, timeout_seconds=60)
    )


@pytest.mark.parametrize("platform", list(Platform))
def test_locked_upstream_exposes_the_exact_seven_platform_auth_guard_points(platform: Platform) -> None:
    checkout = Path(__file__).resolve().parents[2] / ".upstream" / "MediaCrawler"
    package = _CORE_PACKAGE_NAMES[platform]
    core = (checkout / "media_platform" / package / "core.py").read_text(encoding="utf-8")
    login = (checkout / "media_platform" / package / "login.py").read_text(encoding="utf-8")

    assert runner_module._CLIENT_FACTORY_NAMES[platform] in core
    assert _LOGIN_CLASS_NAMES[platform] in core
    assert ".pong(" in core
    assert "await login_obj.begin()" in core
    assert ".update_cookies(" in core
    assert 'config.CRAWLER_TYPE == "search"' in core
    assert 'config.CRAWLER_TYPE == "detail"' in core
    assert 'config.CRAWLER_TYPE == "creator"' in core
    assert runner_module.LOGIN_ONLY_CRAWLER_TYPE not in core
    assert "utils.show_qrcode" in login


@pytest.mark.parametrize("platform", list(Platform))
def test_seven_platform_login_contract_has_no_content_or_qr_export(tmp_path: Path, platform: Platform) -> None:
    checkout = _write_fake_checkout(tmp_path / "upstream")
    integration_root = tmp_path / "runtime"
    runner = _runner(checkout, integration_root)
    hooks: list[str] = []

    interactive = runner.run(
        _request(platform, MediaCrawlerLoginMode.INTERACTIVE_QR),
        on_account_locked=lambda: hooks.append("interactive"),
    )
    probe = runner.run(
        _request(platform, MediaCrawlerLoginMode.SAVED_SESSION_PROBE),
        on_account_locked=lambda: hooks.append("probe"),
    )
    (checkout / "mode.txt").write_text("expired", encoding="utf-8")
    expired = runner.run(
        _request(platform, MediaCrawlerLoginMode.SAVED_SESSION_PROBE),
        on_account_locked=lambda: hooks.append("expired"),
    )

    assert interactive.status is MediaCrawlerLoginStatus.AUTHENTICATED
    assert probe.status is MediaCrawlerLoginStatus.AUTHENTICATED
    assert expired.status is MediaCrawlerLoginStatus.EXPIRED
    assert hooks == ["interactive", "probe", "expired"]
    assert not (checkout / "content-side-effect").exists()
    assert list((integration_root / "jobs").iterdir()) == []
    profile = build_run_paths(integration_root, platform, ACCOUNT_ID, ACCOUNT_ID).profile_root
    assert (profile / "authenticated.state").read_text(encoding="utf-8") == "ok"
    assert "QR-SECRET" not in repr((interactive, probe, expired))
    assert str(profile) not in repr((interactive, probe, expired))


def test_system_exit_zero_cannot_authenticate(tmp_path: Path) -> None:
    checkout = _write_fake_checkout(tmp_path / "upstream")
    (checkout / "mode.txt").write_text("system_exit", encoding="utf-8")

    result = _runner(checkout, tmp_path / "runtime").run(_request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR))

    assert result.status is MediaCrawlerLoginStatus.FAILED


def test_hook_runs_once_with_lock_held_and_exception_prevents_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = _write_fake_checkout(tmp_path / "upstream")
    integration_root = tmp_path / "runtime"
    runner = _runner(checkout, integration_root)
    execute_calls: list[str] = []
    account_root = build_run_paths(integration_root, Platform.XHS, ACCOUNT_ID, ACCOUNT_ID).account_root

    def fake_execute(*_args: object, **_kwargs: object) -> MediaCrawlerLoginResult:
        execute_calls.append("spawn")
        return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.AUTHENTICATED, UPSTREAM_SHA)

    monkeypatch.setattr(runner, "_execute", fake_execute)
    hook_calls: list[str] = []

    def hook() -> None:
        contender = _AccountFileLock(account_root)
        assert not contender.acquire()
        hook_calls.append("hook")

    result = runner.run(_request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR), on_account_locked=hook)

    assert result.authenticated
    assert hook_calls == ["hook"]
    assert execute_calls == ["spawn"]

    def rejected_hook() -> None:
        raise RuntimeError("repository transition rejected")

    with pytest.raises(RuntimeError, match="repository transition rejected"):
        runner.run(
            _request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR),
            on_account_locked=rejected_hook,
        )
    assert execute_calls == ["spawn"]
    released = _AccountFileLock(account_root)
    assert released.acquire()
    released.release()


def test_disabled_gate_and_busy_lock_do_not_call_hook_or_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = _write_fake_checkout(tmp_path / "upstream")
    integration_root = tmp_path / "runtime"
    calls: list[str] = []
    gated_runners = (
        _runner(checkout, integration_root, enabled=False),
        _runner(checkout, integration_root, license_acknowledged=False),
    )
    for gated in gated_runners:
        monkeypatch.setattr(gated, "_execute", lambda *_args, **_kwargs: calls.append("spawn"))
        off = gated.run(
            _request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR),
            on_account_locked=lambda: calls.append("hook"),
        )
        assert off.status is MediaCrawlerLoginStatus.CONFIGURATION_INVALID
    assert calls == []

    active = _runner(checkout, integration_root)
    paths = active._prepare_paths(_request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR))
    held = _AccountFileLock(paths.account_root)
    assert held.acquire()
    try:
        busy = active.run(
            _request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR),
            on_account_locked=lambda: calls.append("hook"),
        )
    finally:
        held.release()
    assert busy.status is MediaCrawlerLoginStatus.ACCOUNT_BUSY
    assert calls == []


def test_missing_saved_profile_is_expired_without_hook_or_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = _write_fake_checkout(tmp_path / "upstream")
    runner = _runner(checkout, tmp_path / "runtime")
    calls: list[str] = []
    monkeypatch.setattr(runner, "_execute", lambda *_args, **_kwargs: calls.append("spawn"))

    result = runner.run(
        _request(Platform.ZHIHU, MediaCrawlerLoginMode.SAVED_SESSION_PROBE),
        on_account_locked=lambda: calls.append("hook"),
    )

    assert result.status is MediaCrawlerLoginStatus.EXPIRED
    assert calls == []


@pytest.mark.parametrize(
    ("request_bytes", "case"),
    [
        (b"", "eof"),
        ((0).to_bytes(runner_module._LOGIN_REQUEST_LENGTH_BYTES, "big"), "empty"),
        (
            (runner_module.MAX_LOGIN_REQUEST_BYTES + 1).to_bytes(
                runner_module._LOGIN_REQUEST_LENGTH_BYTES,
                "big",
            ),
            "oversized",
        ),
        ((8).to_bytes(runner_module._LOGIN_REQUEST_LENGTH_BYTES, "big") + b"short", "truncated"),
    ],
)
def test_child_rejects_invalid_request_before_upstream_import(
    tmp_path: Path,
    request_bytes: bytes,
    case: str,
) -> None:
    del case
    checkout = _write_fake_checkout(tmp_path / "upstream")
    process = _spawn_raw_login_child(checkout)
    try:
        assert process.stdin is not None
        if request_bytes:
            process.stdin.write(request_bytes)
            process.stdin.flush()
        process.stdin.close()
        assert process.wait(timeout=5) == 20
        assert process.stdout is not None
        assert _parse_result_wire(process.stdout.read()) is MediaCrawlerLoginStatus.CONFIGURATION_INVALID
        assert not (checkout / "upstream-imported").exists()
    finally:
        _force_close_raw_tree(process)
        if process.stdout is not None:
            process.stdout.close()


@pytest.mark.parametrize(
    ("control", "case"),
    [(None, "eof"), (b"media-sync-invalid-control-v1\n", "malformed")],
)
def test_child_waits_for_start_and_fails_closed_on_prestart_control(
    tmp_path: Path,
    control: bytes | None,
    case: str,
) -> None:
    del case
    checkout = _write_fake_checkout(tmp_path / "upstream")
    payload = _raw_login_payload(checkout, tmp_path / "runtime")
    process = _spawn_raw_login_child(checkout)
    try:
        assert process.stdin is not None
        process.stdin.write(runner_module._login_request_frame(payload))
        process.stdin.flush()
        time.sleep(0.2)
        assert process.poll() is None
        assert not (checkout / "upstream-imported").exists()
        if control is None:
            process.stdin.close()
        else:
            process.stdin.write(control)
            process.stdin.flush()
        assert process.wait(timeout=5) == 20
        assert process.stdout is not None
        assert _parse_result_wire(process.stdout.read()) is MediaCrawlerLoginStatus.CONFIGURATION_INVALID
        assert not (checkout / "upstream-imported").exists()
    finally:
        with contextlib.suppress(OSError, ValueError):
            if process.stdin is not None:
                process.stdin.close()
        _force_close_raw_tree(process)
        if process.stdout is not None:
            process.stdout.close()


@pytest.mark.parametrize(
    ("control", "case"),
    [(None, "eof"), (b"media-sync-invalid-control-v1\n", "malformed")],
)
def test_running_child_treats_parent_eof_or_invalid_control_as_tree_loss(
    tmp_path: Path,
    control: bytes | None,
    case: str,
) -> None:
    del case
    checkout = _write_fake_checkout(tmp_path / "upstream")
    (checkout / "mode.txt").write_text("hang", encoding="utf-8")
    payload = _raw_login_payload(checkout, tmp_path / "runtime")
    process = _spawn_raw_login_child(checkout)
    pids: dict[str, int] = {}
    try:
        assert process.stdin is not None
        process.stdin.write(runner_module._login_request_frame(payload))
        process.stdin.write(runner_module._CONTROL_START)
        process.stdin.flush()
        pids = _wait_for_json(checkout / "pids.json")
        assert process.poll() is None
        if control is None:
            process.stdin.close()
        else:
            process.stdin.write(control)
            process.stdin.flush()
        process.wait(timeout=10)
        _wait_for_pids_to_exit(*(int(value) for value in pids.values()))
        assert not (checkout / "content-side-effect").exists()
    finally:
        with contextlib.suppress(OSError, ValueError):
            if process.stdin is not None:
                process.stdin.close()
        _force_close_raw_tree(process)
        for process_id in pids.values():
            _force_close_pid_tree(int(process_id))
        if process.stdout is not None:
            process.stdout.close()


def test_start_frame_is_sent_only_after_parent_tree_attachment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = tmp_path / "handshake"
    frame = b'{"schema_version":1,"status":"failed"}'
    result_wire = len(frame).to_bytes(runner_module._LOGIN_RESULT_LENGTH_BYTES, "big") + frame

    def spawn_helper(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        code = (
            "from pathlib import Path; import sys; "
            f"probe=Path({str(probe)!r}); probe.with_suffix('.prestart').write_text('waiting'); "
            "size=int.from_bytes(sys.stdin.buffer.read(4),'big'); sys.stdin.buffer.read(size); "
            f"control=sys.stdin.buffer.readline(64); expected={runner_module._CONTROL_START!r}; "
            "probe.with_suffix('.poststart').write_text('started') if control == expected else None; "
            f"sys.stdout.buffer.write({result_wire!r}); sys.stdout.buffer.flush(); raise SystemExit(0)"
        )
        common: dict[str, object] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            return subprocess.Popen(
                (sys.executable, "-I", "-u", "-c", code),
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                **common,  # type: ignore[arg-type]
            )
        return subprocess.Popen(
            (sys.executable, "-I", "-u", "-c", code),
            start_new_session=True,
            **common,  # type: ignore[arg-type]
        )

    monkeypatch.setattr(runner_module, "_spawn_login_child", spawn_helper)
    original_attach = runner_module._WindowsJob.attach.__func__
    observed_prestart = False

    def delayed_attach(
        cls: type[runner_module._WindowsJob],
        process: subprocess.Popen[bytes],
    ) -> runner_module._WindowsJob | None:
        nonlocal observed_prestart
        deadline = time.monotonic() + 5
        while not probe.with_suffix(".prestart").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        observed_prestart = probe.with_suffix(".prestart").is_file()
        assert not probe.with_suffix(".poststart").exists()
        return original_attach(cls, process)

    monkeypatch.setattr(runner_module._WindowsJob, "attach", classmethod(delayed_attach))
    result = MediaCrawlerLoginProcessRunner._execute(
        Path(sys.executable),
        tmp_path,
        b"{}",
        _request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR),
        0,
        None,
        UPSTREAM_SHA,
    )

    assert observed_prestart
    assert probe.with_suffix(".poststart").is_file()
    assert result.status is MediaCrawlerLoginStatus.FAILED


@pytest.mark.skipif(os.name != "nt", reason="outer Job attach failure is Windows-specific")
def test_windows_outer_job_attach_failure_never_sends_start_or_imports_upstream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = _write_fake_checkout(tmp_path / "upstream")
    monkeypatch.setattr(runner_module._WindowsJob, "attach", classmethod(lambda _cls, _process: None))

    result = _runner(checkout, tmp_path / "runtime").run(_request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR))

    assert result.status is MediaCrawlerLoginStatus.START_FAILED
    assert not (checkout / "upstream-imported").exists()


def test_spawn_or_start_write_failure_never_imports_upstream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = _write_fake_checkout(tmp_path / "upstream")
    runner = _runner(checkout, tmp_path / "runtime")

    def fail_spawn(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        raise OSError("injected spawn failure")

    monkeypatch.setattr(runner_module, "_spawn_login_child", fail_spawn)
    spawn_failed = runner.run(_request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR))
    assert spawn_failed.status is MediaCrawlerLoginStatus.START_FAILED
    assert not (checkout / "upstream-imported").exists()

    monkeypatch.undo()
    monkeypatch.setattr(runner_module, "_write_login_start", lambda _process, _payload: False)
    start_failed = runner.run(_request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR))
    assert start_failed.status is MediaCrawlerLoginStatus.START_FAILED
    assert not (checkout / "upstream-imported").exists()


def test_hard_parent_death_stops_login_tree_and_releases_account_lock(tmp_path: Path) -> None:
    checkout = _write_fake_checkout(tmp_path / "upstream")
    (checkout / "mode.txt").write_text("hang", encoding="utf-8")
    integration_root = (tmp_path / "runtime").resolve()
    parent_probe = tmp_path / "parent.json"
    context = multiprocessing.get_context("spawn")
    parent = context.Process(
        target=_run_hard_death_login_parent,
        args=(checkout, integration_root, parent_probe),
    )
    pids: dict[str, int] = {}
    parent.start()
    try:
        parent_pid = _wait_for_json(parent_probe)["parent"]
        pids = _wait_for_json(checkout / "pids.json", timeout=20)
        account_root = build_run_paths(integration_root, Platform.XHS, ACCOUNT_ID, ACCOUNT_ID).account_root
        contender = _AccountFileLock(account_root)
        assert not contender.acquire()

        _hard_kill_parent(parent_pid)
        parent.join(timeout=5)
        assert parent.exitcode is not None
        _wait_for_pids_to_exit(*(int(value) for value in pids.values()))

        deadline = time.monotonic() + 5
        acquired = False
        while not acquired and time.monotonic() < deadline:
            acquired = contender.acquire()
            if not acquired:
                time.sleep(0.05)
        assert acquired
        contender.release()
    finally:
        if parent.is_alive():
            parent.kill()
            parent.join(timeout=5)
        for process_id in pids.values():
            _force_close_pid_tree(int(process_id))


def test_hard_parent_death_after_result_frame_stops_guardian_tree_before_lock_release(tmp_path: Path) -> None:
    checkout = _write_fake_checkout(tmp_path / "upstream")
    (checkout / "mode.txt").write_text("linger_after_result", encoding="utf-8")
    integration_root = (tmp_path / "runtime").resolve()
    parent_probe = tmp_path / "parent.json"
    close_probe = tmp_path / "parent-close.json"
    context = multiprocessing.get_context("spawn")
    parent = context.Process(
        target=_run_hard_death_after_login_result,
        args=(checkout, integration_root, parent_probe, close_probe),
    )
    pids: dict[str, int] = {}
    parent.start()
    try:
        parent_pid = _wait_for_json(parent_probe)["parent"]
        pids = _wait_for_json(checkout / "pids.json", timeout=20)
        assert _wait_for_json(close_probe, timeout=20)["parent"] == parent_pid
        assert all(_pid_is_alive(int(value)) for value in pids.values())

        account_root = build_run_paths(integration_root, Platform.XHS, ACCOUNT_ID, ACCOUNT_ID).account_root
        before_kill = _AccountFileLock(account_root)
        assert not before_kill.acquire()

        _hard_kill_parent(parent_pid)
        parent.join(timeout=5)
        assert parent.exitcode is not None

        deadline = time.monotonic() + 10
        while any(_pid_is_alive(int(value)) for value in pids.values()) and time.monotonic() < deadline:
            contender = _AccountFileLock(account_root)
            if contender.acquire():
                still_alive = any(_pid_is_alive(int(value)) for value in pids.values())
                contender.release()
                assert not still_alive, "account lock was reusable while the guarded login tree still lived"
                break
            time.sleep(0.02)
        _wait_for_pids_to_exit(*(int(value) for value in pids.values()))

        released = _AccountFileLock(account_root)
        assert released.acquire()
        released.release()
    finally:
        if parent.is_alive():
            parent.kill()
            parent.join(timeout=5)
        for process_id in pids.values():
            _force_close_pid_tree(int(process_id))


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("hang", MediaCrawlerLoginStatus.TIMED_OUT),
        ("cancel", MediaCrawlerLoginStatus.CANCELLED),
    ],
)
def test_timeout_and_cancellation_join_the_complete_process_tree(
    tmp_path: Path,
    mode: str,
    expected: MediaCrawlerLoginStatus,
) -> None:
    checkout = _write_fake_checkout(tmp_path / "upstream")
    (checkout / "mode.txt").write_text(mode, encoding="utf-8")
    runner = _runner(checkout, tmp_path / "runtime")
    cancellation = threading.Event()
    timeout = 2.0 if mode == "hang" else 20.0
    request = _request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR, timeout_seconds=timeout)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runner.run, request, cancellation=cancellation)
        deadline = time.monotonic() + 10
        while not (checkout / "pids.json").is_file() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (checkout / "pids.json").is_file()
        if mode == "cancel":
            cancellation.set()
        result = future.result(timeout=20)

    assert result.status is expected
    pids = json.loads((checkout / "pids.json").read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while any(_pid_is_alive(int(value)) for value in pids.values()) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not any(_pid_is_alive(int(value)) for value in pids.values())


@pytest.mark.parametrize(
    ("frame", "returncode", "expected"),
    [
        (b'{"schema_version":1,"status":"failed"}', 0, MediaCrawlerLoginStatus.FAILED),
        (b'{"schema_version":1,"status":"authenticated"}', 20, MediaCrawlerLoginStatus.AUTHENTICATED),
        (
            b'{"schema_version":1,"status":"failed"}{"schema_version":1,"status":"authenticated"}',
            0,
            MediaCrawlerLoginStatus.RESULT_INVALID,
        ),
        (b"x" * (runner_module.MAX_LOGIN_RESULT_BYTES + 1), 0, MediaCrawlerLoginStatus.RESULT_INVALID),
    ],
)
def test_parent_accepts_only_one_bounded_explicit_result_frame(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    frame: bytes,
    returncode: int,
    expected: MediaCrawlerLoginStatus,
) -> None:
    result_wire = len(frame).to_bytes(runner_module._LOGIN_RESULT_LENGTH_BYTES, "big") + frame

    def spawn_helper(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        code = (
            "import sys; size=int.from_bytes(sys.stdin.buffer.read(4),'big'); "
            "sys.stdin.buffer.read(size); sys.stdin.buffer.readline(64); "
            f"sys.stdout.buffer.write({result_wire!r}); sys.stdout.buffer.flush(); raise SystemExit({returncode})"
        )
        if os.name == "nt":
            return subprocess.Popen(
                (sys.executable, "-I", "-u", "-c", code),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        return subprocess.Popen(
            (sys.executable, "-I", "-u", "-c", code),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )

    monkeypatch.setattr(runner_module, "_spawn_login_child", spawn_helper)
    request = _request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR)

    result = MediaCrawlerLoginProcessRunner._execute(
        Path(sys.executable),
        tmp_path,
        b"{}",
        request,
        0,
        None,
        UPSTREAM_SHA,
    )

    assert result.status is expected


@pytest.mark.parametrize(
    "wire",
    [
        b"",
        (0).to_bytes(runner_module._LOGIN_RESULT_LENGTH_BYTES, "big"),
        (runner_module.MAX_LOGIN_RESULT_BYTES + 1).to_bytes(runner_module._LOGIN_RESULT_LENGTH_BYTES, "big"),
        (8).to_bytes(runner_module._LOGIN_RESULT_LENGTH_BYTES, "big") + b"short",
        (
            len(b'{"schema_version":1,"status":"failed"}').to_bytes(
                runner_module._LOGIN_RESULT_LENGTH_BYTES,
                "big",
            )
            + b'{"schema_version":1,"status":"failed"}'
            + b"trailing"
        ),
    ],
)
def test_parent_rejects_missing_invalid_or_appended_result_framing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wire: bytes,
) -> None:
    def spawn_helper(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        code = (
            "import sys; size=int.from_bytes(sys.stdin.buffer.read(4),'big'); "
            "sys.stdin.buffer.read(size); sys.stdin.buffer.readline(64); "
            f"sys.stdout.buffer.write({wire!r}); sys.stdout.buffer.flush(); raise SystemExit(0)"
        )
        common: dict[str, object] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            return subprocess.Popen(
                (sys.executable, "-I", "-u", "-c", code),
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                **common,  # type: ignore[arg-type]
            )
        return subprocess.Popen(
            (sys.executable, "-I", "-u", "-c", code),
            start_new_session=True,
            **common,  # type: ignore[arg-type]
        )

    monkeypatch.setattr(runner_module, "_spawn_login_child", spawn_helper)
    result = MediaCrawlerLoginProcessRunner._execute(
        Path(sys.executable),
        tmp_path,
        b"{}",
        _request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR),
        0,
        None,
        UPSTREAM_SHA,
    )

    assert result.status is MediaCrawlerLoginStatus.RESULT_INVALID


def test_parent_bounds_a_no_frame_child_by_deadline_and_joins_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def spawn_helper(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        code = (
            "import os, sys, time; size=int.from_bytes(sys.stdin.buffer.read(4),'big'); "
            "sys.stdin.buffer.read(size); sys.stdin.buffer.readline(64); os.close(1); time.sleep(60)"
        )
        common: dict[str, object] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            return subprocess.Popen(
                (sys.executable, "-I", "-u", "-c", code),
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                **common,  # type: ignore[arg-type]
            )
        return subprocess.Popen(
            (sys.executable, "-I", "-u", "-c", code),
            start_new_session=True,
            **common,  # type: ignore[arg-type]
        )

    monkeypatch.setattr(runner_module, "_spawn_login_child", spawn_helper)
    started = time.monotonic()
    result = MediaCrawlerLoginProcessRunner._execute(
        Path(sys.executable),
        tmp_path,
        b"{}",
        _request(Platform.XHS, MediaCrawlerLoginMode.INTERACTIVE_QR, timeout_seconds=0.5),
        0,
        None,
        UPSTREAM_SHA,
    )

    assert result.status is MediaCrawlerLoginStatus.TIMED_OUT
    assert time.monotonic() - started < 5
