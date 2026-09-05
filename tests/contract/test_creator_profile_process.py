"""Real local processes: profile guardian framing, locks and subtree lifetime."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import creator_profile_runner as module
from media_sync.integrations.mediacrawler.creator_profile_runner import (
    MediaCrawlerCreatorProfileProcessRunner,
    MediaCrawlerCreatorProfileRequest,
)
from media_sync.integrations.mediacrawler.policies import build_run_paths
from media_sync.integrations.mediacrawler.runner import _AccountFileLock

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
ACCOUNT = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
_GUARDIAN = r"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from dataclasses import replace
from uuid import UUID

sys.path.insert(0, SOURCE_ROOT)
from media_sync.integrations.mediacrawler import creator_profile_runner as module

def run(envelope):
    mode = envelope.lock_path.name
    request = envelope.request
    child = None
    if mode in {"descendant", "timeout", "cancel", "parent-death"}:
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    report = {"pid": os.getpid(), "child_pid": child.pid if child else None,
              "argv": sys.argv, "private_environment_inherited": "MEDIA_SYNC_PRIVATE_SENTINEL" in os.environ}
    (envelope.paths.account_root / "report.json").write_text(json.dumps(report), encoding="utf-8")
    print("PRIVATE Cookie=sentinel /private/path")
    if mode in {"timeout", "cancel", "parent-death"}:
        time.sleep(120)
    if mode == "wrong-identity":
        request = replace(request, request_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"))
    if mode == "extra-output":
        original = module._emit
        module._emit = lambda frame: original(frame + b"EXTRA")
    if mode == "bad-frame":
        original = module._emit
        module._emit = lambda frame: original((module.MAX_PROFILE_RESULT_BYTES + 1).to_bytes(4, "big"))
    return module._result(request, module.MediaCrawlerCreatorProfileStatus.SUCCEEDED, SHA,
                          module.MediaCrawlerCreatorProfile(request.creator_remote_id, "Private name", None))

module._run_guardian = run
raise SystemExit(module._guardian_entry())
"""


def _pid_alive(pid: int) -> bool:
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
    except ProcessLookupError:
        return False
    return True


def _until(predicate: object, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline
        time.sleep(0.02)


@pytest.fixture
def process_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    runtime = tmp_path / "runtime"
    paths = build_run_paths(runtime, Platform.BILI, ACCOUNT, uuid4())
    paths.profile_root.mkdir(parents=True)
    (paths.profile_root / "saved-profile").write_bytes(b"offline profile presence only")
    script = tmp_path / "guardian.py"
    script.write_text(
        f"SOURCE_ROOT = {str(SOURCE_ROOT)!r}\nSHA = {SHA!r}\n" + _GUARDIAN,
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module, "_command", lambda mode, executable: (str(executable), "-I", "-u", "-B", str(script), mode)
    )
    monkeypatch.setenv("MEDIA_SYNC_PRIVATE_SENTINEL", "PRIVATE_COOKIE")
    return runtime, paths.account_root, script


def _runner(runtime: Path, mode: str) -> MediaCrawlerCreatorProfileProcessRunner:
    return MediaCrawlerCreatorProfileProcessRunner(
        lock_path=runtime.parent / mode,
        integration_root=runtime,
        python_executable=Path(sys.executable),
        enabled=True,
        license_acknowledged=True,
    )


def _request(timeout: float = 8) -> MediaCrawlerCreatorProfileRequest:
    return MediaCrawlerCreatorProfileRequest(ACCOUNT, Platform.BILI, "123", uuid4(), timeout_seconds=timeout)


@pytest.mark.parametrize(
    "mode,status",
    [
        ("success", "succeeded"),
        ("descendant", "succeeded"),
        ("wrong-identity", "result_invalid"),
        ("extra-output", "result_invalid"),
        ("bad-frame", "result_invalid"),
        ("timeout", "timed_out"),
    ],
)
def test_real_guardian_has_closed_frames_private_inputs_and_joins_descendants(
    process_environment: tuple[Path, Path, Path], mode: str, status: str
) -> None:
    runtime, account_root, _script = process_environment
    request = _request(2 if mode == "timeout" else 8)
    started = time.monotonic()
    result = _runner(runtime, mode).run(request)
    assert result.status.value == status
    assert time.monotonic() - started < request.timeout_seconds + module.MAX_PROFILE_CLEANUP_SECONDS
    report = json.loads((account_root / "report.json").read_text(encoding="utf-8"))
    assert not report["private_environment_inherited"]
    assert str(ACCOUNT) not in str(report["argv"]) and str(request.request_id) not in str(report["argv"])
    assert not _pid_alive(report["pid"])
    if report["child_pid"]:
        assert not _pid_alive(report["child_pid"])
    lock = _AccountFileLock(account_root)
    assert lock.acquire()
    lock.release()
    assert not (runtime / "jobs").exists()


def test_real_account_lock_is_shared_until_cancelled_tree_is_gone(
    process_environment: tuple[Path, Path, Path],
) -> None:
    runtime, account_root, _script = process_environment
    cancellation = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        active = executor.submit(_runner(runtime, "cancel").run, _request(), cancellation=cancellation)
        try:
            _until(lambda: (account_root / "report.json").exists())
            assert _runner(runtime, "success").run(_request()).status.value == "account_busy"
            lock = _AccountFileLock(account_root)
            assert not lock.acquire()
        finally:
            cancellation.set()
        assert active.result(timeout=15).status.value == "cancelled"
    report = json.loads((account_root / "report.json").read_text(encoding="utf-8"))
    assert not _pid_alive(report["pid"]) and not _pid_alive(report["child_pid"])
    assert lock.acquire()
    lock.release()


def test_hard_parent_death_keeps_guardian_ownership_until_descendants_exit(
    process_environment: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    runtime, account_root, script = process_environment
    driver = tmp_path / "driver.py"
    driver.write_text(
        f"import sys\nsys.path.insert(0, {str(SOURCE_ROOT)!r})\n"
        "from pathlib import Path\nfrom uuid import UUID, uuid4\n"
        "from media_sync.domain import Platform\n"
        "from media_sync.integrations.mediacrawler import creator_profile_runner as m\n"
        f"m._command = lambda mode, executable: (str(executable), '-I', '-u', '-B', {str(script)!r}, mode)\n"
        f"r = m.MediaCrawlerCreatorProfileProcessRunner(lock_path=Path({str(runtime.parent / 'parent-death')!r}), "
        f"integration_root=Path({str(runtime)!r}), python_executable=Path(sys.executable), "
        "enabled=True, license_acknowledged=True)\n"
        f"r.run(m.MediaCrawlerCreatorProfileRequest(UUID({str(ACCOUNT)!r}), Platform.BILI, '123', uuid4()))\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [sys.executable, "-I", "-u", "-B", str(driver)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    report = None
    try:
        _until(lambda: (account_root / "report.json").exists())
        report = json.loads((account_root / "report.json").read_text(encoding="utf-8"))
        process.kill()
        process.wait(timeout=5)
        _until(lambda: not _pid_alive(report["pid"]) and not _pid_alive(report["child_pid"]))
        lock = _AccountFileLock(account_root)
        assert lock.acquire()
        lock.release()
    finally:
        if process.poll() is None:
            process.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)
        if report is not None and _pid_alive(report["pid"]):
            if os.name == "nt":
                subprocess.run(
                    ["taskkill.exe", "/PID", str(report["pid"]), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    check=False,
                )
            else:
                os.killpg(report["pid"], 9)


def test_unresolved_tree_never_releases_lock_and_marks_account_block(
    process_environment: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, account_root, _script = process_environment
    request = _request()
    monkeypatch.setattr(
        MediaCrawlerCreatorProfileProcessRunner,
        "_execute",
        staticmethod(
            lambda *args: (module._result(request, module.MediaCrawlerCreatorProfileStatus.CLEANUP_FAILED), False)
        ),
    )
    before = len(module._RETAINED_LOCKS)
    try:
        assert _runner(runtime, "success").run(request).status.value == "cleanup_failed"
        assert len(module._RETAINED_LOCKS) == before + 1
        contender = _AccountFileLock(account_root)
        assert not contender.acquire()
        assert _runner(runtime, "success").run(request).status.value == "cleanup_failed"
    finally:
        for lock in module._RETAINED_LOCKS[before:]:
            lock.release()
        del module._RETAINED_LOCKS[before:]
