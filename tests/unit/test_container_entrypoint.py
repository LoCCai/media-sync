"""Execute entrypoint command ordering with stubs, never claim container/UID coverage."""

from __future__ import annotations

import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

_ENTRYPOINT = Path(__file__).resolve().parents[2] / "docker" / "entrypoint.sh"


def _shell() -> str:
    shell = shutil.which("sh")
    if shell is None and os.name == "nt":
        git = shutil.which("git")
        if git is not None:
            candidate = Path(git).resolve().parents[1] / "usr" / "bin" / "sh.exe"
            if candidate.is_file():
                shell = str(candidate)
    if shell is None:
        pytest.skip("POSIX-compatible shell unavailable; container/UID execution is not implied")
    return shell


def _run_entrypoint(tmp_path: Path, args: list[str], *, preflight_exit: int = 0) -> tuple[int, list[str]]:
    shell = _shell()
    cli_stub = tmp_path / "cli-stub.sh"
    cli_stub.write_text(
        '#!/bin/sh\nprintf "cli" >> "$ENTRYPOINT_TEST_TRACE"\n'
        'for argument do printf "|%s" "$argument" >> "$ENTRYPOINT_TEST_TRACE"; done\n'
        'printf "\\n" >> "$ENTRYPOINT_TEST_TRACE"\n'
        'for argument do [ "$argument" != "--check-config" ] || exit "$ENTRYPOINT_TEST_EXIT"; done\n'
        "exit 0\n",
        encoding="utf-8",
        newline="\n",
    )
    xvfb_stub = tmp_path / "Xvfb"
    xvfb_stub.write_text('#!/bin/sh\nprintf "xvfb\\n" >> "$ENTRYPOINT_TEST_XVFB"\n', encoding="utf-8", newline="\n")
    xvfb_stub.chmod(0o700)
    entrypoint = tmp_path / "entrypoint.sh"
    entrypoint.write_text(
        _ENTRYPOINT.read_text(encoding="utf-8").replace(
            "/app/.venv/bin/media-sync", f"{shlex.quote(Path(shell).as_posix())} {shlex.quote(cli_stub.as_posix())}"
        ),
        encoding="utf-8",
        newline="\n",
    )
    trace = tmp_path / "trace.txt"
    env = dict(os.environ)
    env.update(
        {
            "PATH": str(tmp_path) + os.pathsep + env.get("PATH", ""),
            "ENTRYPOINT_TEST_TRACE": trace.as_posix(),
            "ENTRYPOINT_TEST_XVFB": (tmp_path / "xvfb.txt").as_posix(),
            "ENTRYPOINT_TEST_EXIT": str(preflight_exit),
        }
    )
    completed = subprocess.run(
        [shell, str(entrypoint), *args], env=env, capture_output=True, text=True, check=False, timeout=15
    )
    assert completed.stderr == "", completed.stderr
    return completed.returncode, trace.read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("global_terminator", [False, True])
def test_serve_preflight_preserves_arguments_and_precedes_migration(tmp_path: Path, global_terminator: bool) -> None:
    args = ["serve", "--host", "0.0.0.0", "--port", "9017"]
    if global_terminator:
        args.insert(0, "--")

    code, calls = _run_entrypoint(tmp_path, args)

    assert code == 0
    assert calls == [
        "cli|serve|--host|0.0.0.0|--port|9017|--check-config",
        "cli|db|init",
        "cli|serve|--host|0.0.0.0|--port|9017",
    ]
    assert (tmp_path / "xvfb.txt").read_text(encoding="utf-8") == "xvfb\n"


@pytest.mark.parametrize("exit_code", [1, 2, 7])
@pytest.mark.parametrize("global_terminator", [False, True])
def test_failed_serve_preflight_stops_before_xvfb_and_migration(
    tmp_path: Path, exit_code: int, global_terminator: bool
) -> None:
    args = ["--", "serve"] if global_terminator else ["serve"]
    code, calls = _run_entrypoint(tmp_path, args, preflight_exit=exit_code)

    assert code == exit_code
    assert calls == ["cli|serve|--check-config"]
    assert not (tmp_path / "xvfb.txt").exists()


@pytest.mark.parametrize("args", [["serve", "--check-config"], ["serve", "--help"], ["--help"], ["db", "--help"]])
@pytest.mark.parametrize("global_terminator", [False, True])
def test_check_only_and_help_never_start_xvfb_or_migrate(
    tmp_path: Path, args: list[str], global_terminator: bool
) -> None:
    incoming = (["--"] if global_terminator else []) + args
    code, calls = _run_entrypoint(tmp_path, incoming)

    assert code == 0
    forwarded = args if args[0] == "serve" else incoming
    assert calls == ["cli|" + "|".join(forwarded)]
    assert not (tmp_path / "xvfb.txt").exists()


@pytest.mark.parametrize("global_terminator", [False, True])
def test_explicit_failed_check_never_initializes(tmp_path: Path, global_terminator: bool) -> None:
    args = (["--"] if global_terminator else []) + ["serve", "--check-config"]
    code, calls = _run_entrypoint(tmp_path, args, preflight_exit=2)

    assert code == 2
    assert calls == ["cli|serve|--check-config"]
    assert not (tmp_path / "xvfb.txt").exists()


@pytest.mark.parametrize("args", [["scheduler", "supervise"], ["db", "status"], ["account", "list"]])
def test_non_serve_workflow_retains_existing_initialization(tmp_path: Path, args: list[str]) -> None:
    code, calls = _run_entrypoint(tmp_path, args)

    assert code == 0
    assert calls == ["cli|db|init", "cli|" + "|".join(args)]
    assert (tmp_path / "xvfb.txt").read_text(encoding="utf-8") == "xvfb\n"


@pytest.mark.parametrize("check_only", [False, True])
def test_prefixed_entrypoint_real_cli_rejects_or_checks_without_startup(tmp_path: Path, check_only: bool) -> None:
    shell = _shell()
    entrypoint = tmp_path / "entrypoint.sh"
    entrypoint.write_text(
        _ENTRYPOINT.read_text(encoding="utf-8").replace(
            "/app/.venv/bin/media-sync",
            f"{shlex.quote(Path(sys.executable).as_posix())} -m media_sync.interfaces.cli",
        ),
        encoding="utf-8",
        newline="\n",
    )
    xvfb_stub = tmp_path / "Xvfb"
    xvfb_stub.write_text('#!/bin/sh\nprintf "xvfb\\n" >> "$ENTRYPOINT_TEST_XVFB"\n', encoding="utf-8", newline="\n")
    xvfb_stub.chmod(0o700)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    database = state_dir / "media-sync.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE retained (value TEXT)")
        connection.execute("INSERT INTO retained VALUES ('entrypoint-retained-state')")
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    env = {key: value for key, value in os.environ.items() if not key.startswith("MEDIA_SYNC_")}
    env.update(
        {
            "PATH": str(tmp_path) + os.pathsep + env.get("PATH", ""),
            "ENTRYPOINT_TEST_XVFB": (tmp_path / "xvfb.txt").as_posix(),
            "MEDIA_SYNC_STATE_DIR": str(state_dir),
            "MEDIA_SYNC_ARCHIVE_DIR": str(tmp_path / "archive"),
            "MEDIA_SYNC_EXPORT_DIR": str(tmp_path / "exports"),
            "MEDIA_SYNC_JOB_DIR": str(tmp_path / "jobs"),
            "MEDIA_SYNC_OPERATOR_CREDENTIAL_SECRET_REF": "env:ENTRYPOINT_TEST_CREDENTIAL",
            "ENTRYPOINT_TEST_CREDENTIAL": "entrypoint-operator-test-credential-0123456789" if check_only else "short",
        }
    )

    completed = subprocess.run(
        [shell, str(entrypoint), "--", "serve", *(["--check-config"] if check_only else [])],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == (0 if check_only else 2)
    expected = (
        '{"service":"media-sync-api","configuration":"valid"}'
        if check_only
        else '{"detail":"operator_auth_configuration_invalid"}'
    )
    assert (completed.stdout + completed.stderr).strip() == expected
    assert {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["Xvfb", "entrypoint.sh", "state"]
