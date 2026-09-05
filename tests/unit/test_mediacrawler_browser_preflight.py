"""Blank-browser preflight matches login launch without user profile access."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from media_sync.integrations.mediacrawler import checkout, runner
from media_sync.integrations.mediacrawler.browser_environment import browser_child_environment
from media_sync.integrations.mediacrawler.checkout import CheckoutValidationError, verify_mediacrawler_browser

_VERSION = "151.0.7922.34"
_PRIVATE = "private-browser-profile credential-sentinel"


def test_probe_has_isolated_stdin_timeout_and_shared_secret_denying_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/installed/bundled-browsers")
    monkeypatch.setenv("DISPLAY", ":99")
    for name in ("PYTHONPATH", "PYTHONHOME", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "MEDIA_SYNC_API_TOKEN"):
        monkeypatch.setenv(name, _PRIVATE)
    calls: list[tuple[str, ...]] = []

    def run(arguments: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        assert arguments[:3] == (str(checkout.normalize_python_executable(Path(sys.executable))), "-I", "-c")
        assert kwargs == {
            "check": False,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": 45,
            "env": browser_child_environment(),
        }
        assert kwargs["env"]["PLAYWRIGHT_BROWSERS_PATH"] == "/installed/bundled-browsers"
        assert kwargs["env"]["DISPLAY"] == ":99"
        assert _PRIVATE not in str(kwargs)
        assert "GIT_CONFIG_NOSYSTEM" not in kwargs["env"]
        assert arguments[3:] == (checkout._BROWSER_PROBE,)
        return subprocess.CompletedProcess(arguments, 0, stdout=f"{_VERSION}\n")

    monkeypatch.setattr(checkout.subprocess, "run", run)

    assert verify_mediacrawler_browser(Path(sys.executable)) == _VERSION
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["timeout", "oserror", "nonzero", "invalid_version", "oversized_version"])
def test_headless_probe_failures_are_fixed(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    def run(arguments: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if failure == "timeout":
            raise subprocess.TimeoutExpired(arguments, 45, output=_PRIVATE, stderr=_PRIVATE)
        if failure == "oserror":
            raise OSError(_PRIVATE)
        if failure == "nonzero":
            return subprocess.CompletedProcess(arguments, 1, stdout=_PRIVATE, stderr=_PRIVATE)
        output = "9" * 129 + ".0" if failure == "oversized_version" else f"{_PRIVATE}\n{_VERSION}"
        return subprocess.CompletedProcess(arguments, 0, stdout=output, stderr=_PRIVATE)

    monkeypatch.setattr(checkout.subprocess, "run", run)

    with pytest.raises(CheckoutValidationError) as caught:
        verify_mediacrawler_browser(Path(sys.executable))

    assert caught.value.code == "browser_launch_failed"
    assert _PRIVATE not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("platform", ["nt", "posix"])
@pytest.mark.parametrize(
    "failure",
    [
        None,
        "timeout",
        "cancel",
        "oserror",
        "nonzero",
        "invalid_version",
        "oversized_version",
        "hidden_suffix",
        "cleanup",
    ],
)
def test_interactive_probe_supervises_tree_and_closes_before_profile_cleanup(
    monkeypatch: pytest.MonkeyPatch, platform: str, failure: str | None
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/installed/bundled-browsers")
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.setenv("PYTHONPATH", _PRIVATE)
    monkeypatch.setenv("HTTPS_PROXY", _PRIVATE)
    monkeypatch.setattr(checkout, "os", SimpleNamespace(name=platform, access=os.access, X_OK=os.X_OK))
    events: list[str] = []
    profiles: list[Path] = []
    job = object()

    class Process:
        def __init__(self, arguments: tuple[str, ...], **kwargs: Any) -> None:
            self.returncode: int | None = None
            self.output = kwargs.pop("stdout")
            assert not self.output.closed
            assert arguments[:3] == (str(checkout.normalize_python_executable(Path(sys.executable))), "-I", "-c")
            assert arguments[3] == checkout._INTERACTIVE_BROWSER_PROBE
            profiles.append(Path(arguments[4]))
            assert profiles[-1].is_dir() and not list(profiles[-1].iterdir())
            assert kwargs == {
                "env": browser_child_environment(),
                "shell": False,
                "stdin": subprocess.PIPE,
                "stderr": subprocess.DEVNULL,
                "close_fds": True,
                **(
                    {
                        "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    }
                    if platform == "nt"
                    else {"start_new_session": True}
                ),
            }
            assert _PRIVATE not in str(kwargs)
            events.append("spawn")

        def communicate(self, *, input: bytes, timeout: int) -> tuple[None, None]:
            assert input == b"1" and timeout == 45
            events.append("start")
            if failure == "timeout":
                raise subprocess.TimeoutExpired("probe", timeout, output=_PRIVATE, stderr=_PRIVATE)
            if failure == "cancel":
                raise KeyboardInterrupt
            if failure == "oserror":
                raise OSError(_PRIVATE)
            self.returncode = 1 if failure == "nonzero" else 0
            output = _VERSION
            if failure == "invalid_version":
                output = _PRIVATE + "\n" + _VERSION
            if failure == "oversized_version":
                output = "9" * 1024 + ".0"
            if failure == "hidden_suffix":
                output = _VERSION + " " * 1024 + _PRIVATE
            self.output.write(output.encode("utf-8") + b"\n")
            return None, None

    def attach(process: Process) -> object:
        events.append("attach")
        return job

    def close(process: Process, windows_job: object | None) -> bool:
        assert windows_job is (job if platform == "nt" else None)
        assert profiles[-1].is_dir()
        events.append("close_tree")
        return failure != "cleanup"

    monkeypatch.setattr(checkout.subprocess, "Popen", Process)
    monkeypatch.setattr(runner._WindowsJob, "attach", attach)
    monkeypatch.setattr(runner, "_close_process_tree", close)

    if failure == "cancel":
        with pytest.raises(KeyboardInterrupt):
            verify_mediacrawler_browser(Path(sys.executable), interactive=True)
    elif failure is not None:
        with pytest.raises(CheckoutValidationError) as caught:
            verify_mediacrawler_browser(Path(sys.executable), interactive=True)
        assert caught.value.code == "browser_launch_failed"
        assert _PRIVATE not in str(caught.value)
    else:
        assert verify_mediacrawler_browser(Path(sys.executable), interactive=True) == _VERSION
    assert events == (
        ["spawn", "attach", "start", "close_tree"] if platform == "nt" else ["spawn", "start", "close_tree"]
    )
    assert all(not profile.exists() for profile in profiles)


def test_failed_windows_job_attach_never_releases_start_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checkout, "os", SimpleNamespace(name="nt", access=os.access, X_OK=os.X_OK))
    events: list[str] = []

    class Process:
        def __init__(self, *args: object, **kwargs: object) -> None:
            events.append("spawn")

        def communicate(self, **kwargs: object) -> None:
            pytest.fail("uncontained child must never receive a start token")

    def close(process: Process, windows_job: object | None) -> bool:
        assert windows_job is None
        events.append("close_tree")
        return True

    monkeypatch.setattr(checkout.subprocess, "Popen", Process)
    monkeypatch.setattr(runner._WindowsJob, "attach", lambda process: None)
    monkeypatch.setattr(runner, "_close_process_tree", close)

    with pytest.raises(CheckoutValidationError) as caught:
        verify_mediacrawler_browser(Path(sys.executable), interactive=True)

    assert caught.value.code == "browser_launch_failed"
    assert events == ["spawn", "close_tree"]


@pytest.mark.parametrize("stage", ["create", "cleanup"])
def test_temporary_profile_errors_are_redaction_safe(monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
    class FailingDirectory:
        def __init__(self, **kwargs: Any) -> None:
            if stage == "create":
                raise OSError(_PRIVATE)

        def __enter__(self) -> str:
            return "disposable-profile"

        def __exit__(self, *args: object) -> None:
            raise OSError(_PRIVATE)

    monkeypatch.setattr(checkout, "TemporaryDirectory", FailingDirectory)
    monkeypatch.setattr(checkout, "_run_interactive_browser_probe", lambda *args, **kwargs: _VERSION)

    with pytest.raises(CheckoutValidationError) as caught:
        verify_mediacrawler_browser(Path(sys.executable), interactive=True)

    assert caught.value.code == "browser_launch_failed"
    assert _PRIVATE not in str(caught.value)
    assert caught.value.__cause__ is None


def test_missing_interpreter_does_not_create_profile_or_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checkout, "TemporaryDirectory", lambda **kwargs: pytest.fail("must not create profile"))
    monkeypatch.setattr(checkout.subprocess, "run", lambda *args, **kwargs: pytest.fail("must not launch"))

    with pytest.raises(CheckoutValidationError) as caught:
        verify_mediacrawler_browser(tmp_path / "missing-private-interpreter", interactive=True)

    assert caught.value.code == "runtime_unavailable"
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("interactive", [False, True])
@pytest.mark.parametrize("version_fails", [False, True])
def test_exact_probe_script_uses_only_requested_launch_and_always_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interactive: bool, version_fails: bool
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    closed: list[str] = []
    profile = tmp_path / "disposable-profile"
    profile.mkdir()

    class Browser:
        @property
        def version(self) -> str:
            if version_fails:
                raise RuntimeError(_PRIVATE)
            return _VERSION

        def close(self) -> None:
            closed.append("browser")

    class PersistentContext:
        browser = Browser()

        def close(self) -> None:
            closed.append("context")

    class Chromium:
        executable_path = "/installed/bundled-chromium"

        def launch(self, **kwargs: object) -> Browser:
            calls.append(("headless", kwargs))
            return Browser()

        def launch_persistent_context(self, **kwargs: object) -> PersistentContext:
            calls.append(("persistent", kwargs))
            return PersistentContext()

    module = ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: contextlib.nullcontext(SimpleNamespace(chromium=Chromium()))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    monkeypatch.setattr(sys, "argv", ["-c", str(profile)])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"1")))
    output = io.StringIO()
    script = checkout._INTERACTIVE_BROWSER_PROBE if interactive else checkout._BROWSER_PROBE

    with contextlib.redirect_stdout(output):
        if version_fails:
            with pytest.raises(RuntimeError, match="credential-sentinel"):
                exec(script, {})
        else:
            exec(script, {})

    if interactive:
        assert calls == [
            (
                "persistent",
                {
                    "user_data_dir": str(profile),
                    "executable_path": "/installed/bundled-chromium",
                    "headless": False,
                    "accept_downloads": True,
                    "viewport": {"width": 1920, "height": 1080},
                    "timeout": 30000,
                },
            )
        ]
        assert closed == ["context"]
    else:
        assert calls == [("headless", {"headless": True})]
        assert closed == ["browser"]
    assert output.getvalue() == ("" if version_fails else f"{_VERSION}\n")
    assert not list(profile.iterdir())


@pytest.mark.parametrize("token", [b"", b"0"])
def test_interactive_probe_script_denies_missing_or_invalid_start_token(
    monkeypatch: pytest.MonkeyPatch, token: bytes
) -> None:
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(token)))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    with pytest.raises(SystemExit) as caught:
        exec(checkout._INTERACTIVE_BROWSER_PROBE, {})

    assert caught.value.code == 44
