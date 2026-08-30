from __future__ import annotations

import csv
import json
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

import config

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
    timeout = 0.5 if mode == "hang" else 20.0
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
        (b'{"schema_version":1,"status":"authenticated"}', 20, MediaCrawlerLoginStatus.RESULT_INVALID),
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
    def spawn_helper(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        code = (
            "import sys; sys.stdin.buffer.read(); "
            f"sys.stdout.buffer.write({frame!r}); sys.stdout.buffer.flush(); raise SystemExit({returncode})"
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
