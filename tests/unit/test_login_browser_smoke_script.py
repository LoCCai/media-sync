"""The operator smoke command does not load credentials, accounts or URLs."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from media_sync.integrations.mediacrawler.checkout import CheckoutValidationError


@pytest.fixture
def smoke_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "check_login_browser.py"
    spec = importlib.util.spec_from_file_location("login_browser_smoke_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_success_is_headed_with_only_fixed_public_summary(
    smoke_script: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[Path, bool]] = []

    def verify(path: Path, *, interactive: bool = False) -> str:
        calls.append((path, interactive))
        return "151.0.7922.34"

    monkeypatch.setattr(smoke_script, "verify_mediacrawler_browser", verify)
    assert smoke_script.main(["--python", "synthetic-runtime"]) == 0
    assert calls == [(Path("synthetic-runtime"), True)]
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "ok": True,
        "browser": "bundled-chromium",
        "mode": "headed-persistent",
        "version": "151.0.7922.34",
        "live_qualification": "NOT_RUN",
    }


def test_failure_never_prints_exception_or_caller_paths(
    smoke_script: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def reject(*args: Any, **kwargs: Any) -> str:
        raise CheckoutValidationError("synthetic-secret", "synthetic-private-code")

    monkeypatch.setattr(smoke_script, "verify_mediacrawler_browser", reject)
    assert smoke_script.main(["--python", "synthetic-secret-path"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {"ok": False, "code": "login_browser_probe_failed"}


def test_help_does_not_launch_browser(
    smoke_script: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(smoke_script, "verify_mediacrawler_browser", lambda *_args, **_kwargs: pytest.fail("launch"))
    with pytest.raises(SystemExit) as result:
        smoke_script.main(["--help"])
    assert result.value.code == 0
    assert "--python" in capsys.readouterr().out
