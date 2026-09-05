"""Real local guardian/descendant processes, never a platform or browser."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import cookie_login_runner as module
from media_sync.integrations.mediacrawler.cookie_login import CookieLoginRequest, parse_cookie_header
from media_sync.integrations.mediacrawler.runner import _AccountFileLock

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
GUARDIAN = r"""
import json
import os
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
sys.path.insert(0, SOURCE_ROOT)
from media_sync.integrations.mediacrawler import cookie_login_runner as module

def run(envelope):
    mode = envelope.lock_path.name
    child = None
    if mode in {"descendant", "timeout", "cancel", "parent-death"}:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    report = {"pid": os.getpid(), "child": child.pid if child else None, "argv": sys.argv,
              "env_leak": "MEDIA_SYNC_COOKIE_SENTINEL" in os.environ,
              "cookie_preserved": envelope.request.cookie.reveal() == "session=PRIVATE=="}
    (envelope.lock_path.parent / "report.json").write_text(json.dumps(report), encoding="utf-8")
    print("Cookie=PRIVATE== /private/path")
    if mode in {"timeout", "cancel", "parent-death"}:
        time.sleep(120)
    request = envelope.request
    if mode == "wrong-identity":
        request = replace(request, operation_id=uuid4())
    original = module._emit
    if mode == "extra-output":
        module._emit = lambda frame: original(frame + b"EXTRA")
    if mode == "oversize":
        module._emit = lambda frame: original((module.MAX_RESULT_BYTES + 1).to_bytes(4, "big"))
    return module._result(request, "authenticated", SHA)
module._run_guardian = run
raise SystemExit(module._guardian_entry())
"""


def alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def until(predicate, seconds: float = 10) -> None:
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline
        time.sleep(0.02)


@pytest.fixture
def guardian(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    script = tmp_path / "cookie-guardian.py"
    script.write_text(f"SOURCE_ROOT={str(SOURCE_ROOT)!r}\nSHA={SHA!r}\n" + GUARDIAN, encoding="utf-8")
    monkeypatch.setattr(
        module, "_command", lambda mode, executable: (str(executable), "-I", "-u", "-B", str(script), mode)
    )
    monkeypatch.setenv("MEDIA_SYNC_COOKIE_SENTINEL", "private-parent-env")
    return script


def runner(tmp_path: Path, mode: str) -> module.CookieLoginProcessRunner:
    return module.CookieLoginProcessRunner(
        lock_path=tmp_path / mode,
        integration_root=tmp_path / "never-created",
        python_executable=Path(sys.executable),
        enabled=True,
        license_acknowledged=True,
    )


@pytest.fixture
def held_lock(tmp_path: Path):
    account_root = tmp_path / "account"
    account_root.mkdir()
    lock = _AccountFileLock(account_root)
    assert lock.acquire()
    try:
        yield lock
    finally:
        lock.release()


def request(timeout: float = 8, *, account_lock_fd: int) -> CookieLoginRequest:
    return CookieLoginRequest(
        uuid4(),
        Platform.BILI,
        uuid4(),
        parse_cookie_header("session=PRIVATE=="),
        timeout,
        account_lock_fd=account_lock_fd,
    )


@pytest.mark.parametrize(
    "mode,status",
    [
        ("success", "authenticated"),
        ("descendant", "authenticated"),
        ("wrong-identity", "result_invalid"),
        ("extra-output", "result_invalid"),
        ("oversize", "result_invalid"),
    ],
)
def test_real_frames_and_descendants(
    tmp_path: Path,
    guardian: Path,
    mode: str,
    status: str,
    capfd,
    held_lock: _AccountFileLock,
) -> None:
    result = runner(tmp_path, mode).run(request(account_lock_fd=held_lock.descriptor))
    assert result.status == status
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["cookie_preserved"] and not report["env_leak"]
    assert "PRIVATE" not in str(report["argv"]) and "PRIVATE" not in str(capfd.readouterr())
    until(lambda: not alive(report["pid"]))
    if report["child"]:
        until(lambda: not alive(report["child"]))
    assert not (tmp_path / "never-created").exists()


@pytest.mark.parametrize("mode", ["timeout", "cancel"])
def test_timeout_and_cancellation_kill_entire_tree(
    tmp_path: Path,
    guardian: Path,
    mode: str,
    held_lock: _AccountFileLock,
) -> None:
    cancelled = threading.Event()
    result = []
    thread = threading.Thread(
        target=lambda: result.append(
            runner(tmp_path, mode).run(
                request(2 if mode == "timeout" else 8, account_lock_fd=held_lock.descriptor),
                cancellation=cancelled,
            )
        )
    )
    thread.start()
    try:
        until(lambda: (tmp_path / "report.json").exists())
        report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        if mode == "cancel":
            cancelled.set()
        thread.join(15)
        assert not thread.is_alive()
        assert result[0].status == ("timed_out" if mode == "timeout" else "cancelled")
        until(lambda: not alive(report["pid"]) and not alive(report["child"]))
    finally:
        cancelled.set()
        thread.join(15)


def test_cleanup_uncertainty_can_never_be_authenticated(
    tmp_path: Path,
    guardian: Path,
    monkeypatch: pytest.MonkeyPatch,
    held_lock: _AccountFileLock,
) -> None:
    original = module._close_process_tree

    def unresolved(process, job):
        assert original(process, job)
        return False

    monkeypatch.setattr(module, "_close_process_tree", unresolved)
    assert runner(tmp_path, "success").run(request(account_lock_fd=held_lock.descriptor)).status == "cleanup_failed"


def test_guardian_inherits_lock_after_parent_descriptor_is_closed(
    tmp_path: Path,
    guardian: Path,
    held_lock: _AccountFileLock,
) -> None:
    cancelled = threading.Event()
    incoming = request(account_lock_fd=held_lock.descriptor)
    result = []
    thread = threading.Thread(
        target=lambda: result.append(runner(tmp_path, "cancel").run(incoming, cancellation=cancelled))
    )
    thread.start()
    contender = _AccountFileLock(tmp_path / "account")
    try:
        until(lambda: (tmp_path / "report.json").exists())
        # A hard process exit closes its descriptor without issuing LOCK_UN.
        # Simulate exactly that ownership loss while keeping the guardian alive.
        os.close(held_lock.descriptor)
        held_lock._descriptor = None
        assert not contender.acquire()
    finally:
        cancelled.set()
        thread.join(15)
        contender.release()
    assert not thread.is_alive() and result[0].status == "cancelled"
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    until(lambda: not alive(report["pid"]) and not alive(report["child"]))
    assert contender.acquire()
    contender.release()


def test_hard_parent_death_closes_guardian_and_descendant(tmp_path: Path, guardian: Path) -> None:
    script = tmp_path / "caller.py"
    script.write_text(
        f"""
import sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, {str(SOURCE_ROOT)!r})
from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import cookie_login_runner as module
from media_sync.integrations.mediacrawler.cookie_login import CookieLoginRequest, parse_cookie_header
from media_sync.integrations.mediacrawler.runner import _AccountFileLock
module._command = lambda mode, executable: (str(executable), "-I", "-u", "-B", {str(guardian)!r}, mode)
account_root = Path({str(tmp_path / "parent-account")!r})
account_root.mkdir()
lock = _AccountFileLock(account_root)
assert lock.acquire()
runner = module.CookieLoginProcessRunner(lock_path=Path({str(tmp_path / "parent-death")!r}),
    integration_root=Path({str(tmp_path / "never-created")!r}), python_executable=Path(sys.executable),
    enabled=True, license_acknowledged=True)
runner.run(CookieLoginRequest(uuid4(), Platform.BILI, uuid4(), parse_cookie_header("session=PRIVATE=="),
    account_lock_fd=lock.descriptor))
""",
        encoding="utf-8",
    )
    parent = subprocess.Popen(
        [sys.executable, "-I", "-u", "-B", str(script)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        until(lambda: (tmp_path / "report.json").exists())
        report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        competing_lock = _AccountFileLock(tmp_path / "parent-account")
        assert not competing_lock.acquire()
        parent.kill()
        parent.wait(timeout=5)
        until(lambda: not alive(report["pid"]) and not alive(report["child"]))
        assert competing_lock.acquire()
        competing_lock.release()
    finally:
        with contextlib.suppress(OSError):
            parent.kill()
        parent.wait(timeout=5)
