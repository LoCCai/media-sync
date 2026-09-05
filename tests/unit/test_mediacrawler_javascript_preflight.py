"""Doctor checks executable JavaScript, not just Python imports or Chromium."""

from __future__ import annotations

import builtins
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from media_sync.integrations.mediacrawler import checkout


@pytest.mark.parametrize(
    ("failure", "expected"),
    [(None, 0), ("python_import", 42), ("execjs_import", 43), ("compile", 43), ("call", 43), ("wrong_result", 43)],
)
def test_real_probe_requires_fixed_javascript_execution(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], failure: str | None, expected: int
) -> None:
    imports: list[str] = []
    calls: list[str] = []
    original_import = builtins.__import__

    def call(name: str) -> int:
        calls.append(name)
        if failure == "call":
            raise RuntimeError("synthetic-private-runtime-error")
        return 0 if failure == "wrong_result" else 2

    def compile_js(source: str) -> Any:
        assert source == "function media_sync_probe() { return 1 + 1; }"
        if failure == "compile":
            raise RuntimeError("synthetic-private-runtime-error")
        return SimpleNamespace(call=call)

    def import_module(name: str, *args: Any, **kwargs: Any) -> Any:
        imports.append(name)
        if name in {"aiofiles", "playwright.async_api", "tenacity", "typer"}:
            if failure == "python_import":
                raise ImportError("synthetic-private-runtime-error")
            return SimpleNamespace()
        if name == "execjs":
            if failure == "execjs_import":
                raise ImportError("synthetic-private-runtime-error")
            return SimpleNamespace(compile=compile_js)
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(builtins, "__import__", import_module)
        with pytest.raises(SystemExit) as caught:
            exec(checkout._RUNTIME_IMPORT_PROBE, {})
    assert caught.value.code == expected
    assert "main" not in imports and "config" not in imports
    assert calls == (["media_sync_probe"] if failure in {None, "call", "wrong_result"} else [])
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_doctor_maps_js_failure_without_forwarding_private_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("EXECJS_RUNTIME", "NODE_OPTIONS", "NODE_PATH", "HTTP_PROXY", "MEDIA_SYNC_OPERATOR_SECRET"):
        monkeypatch.setenv(name, "synthetic-private-runtime-error")

    def run(arguments: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert arguments == (
            str(checkout.normalize_python_executable(Path(sys.executable))),
            "-I",
            "-c",
            checkout._RUNTIME_IMPORT_PROBE,
        )
        assert kwargs["timeout"] == 20
        assert kwargs["stdin"] == kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL
        assert "synthetic-private-runtime-error" not in str(kwargs)
        return subprocess.CompletedProcess(arguments, 43)

    monkeypatch.setattr(checkout.subprocess, "run", run)
    with pytest.raises(checkout.CheckoutValidationError) as caught:
        checkout.verify_mediacrawler_python(Path(sys.executable))
    assert caught.value.code == checkout.CheckoutValidationCode.RUNTIME_JAVASCRIPT_UNAVAILABLE.value
    assert "synthetic-private" not in str(caught.value)


def test_final_image_installs_runtime_node_and_gates_it_with_doctor() -> None:
    """Static wiring only; this is not evidence of a successful Docker build."""
    source = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text(encoding="utf-8")
    final_stage = source.split("FROM ${BASE_IMAGE} AS base", 1)[1]
    assert "      nodejs \\\n" in final_stage
    assert 'echo "javascript_runtime: $(node --version)"' in final_stage
    assert "mediacrawler doctor --accept-license --json" in final_stage
    assert "npm install" not in final_stage
