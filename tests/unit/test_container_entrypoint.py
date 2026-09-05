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


def _run_entrypoint(
    tmp_path: Path,
    args: list[str],
    *,
    preflight_exit: int = 0,
    xvfb_mode: str = "ready",
    probe_mode: str = "ready",
    expected_error: str = "",
) -> tuple[int, list[str]]:
    shell = _shell()
    actual_timeout = Path(shell).parent / ("timeout.exe" if os.name == "nt" else "timeout")
    if probe_mode == "hang" and not actual_timeout.is_file():
        found_timeout = shutil.which("timeout")
        if found_timeout is None:
            pytest.skip("GNU timeout unavailable; actual Linux timeout behavior is not implied")
        actual_timeout = Path(found_timeout)
    cli_stub = tmp_path / "cli-stub.sh"
    cli_stub.write_text(
        '#!/bin/sh\nprintf "cli:%s\\n" "$*" >> "$ENTRYPOINT_TEST_ORDER"\n'
        'printf "cli" >> "$ENTRYPOINT_TEST_TRACE"\n'
        'for argument do printf "|%s" "$argument" >> "$ENTRYPOINT_TEST_TRACE"; done\n'
        'printf "\\n" >> "$ENTRYPOINT_TEST_TRACE"\n'
        'for argument do [ "$argument" != "--check-config" ] || exit "$ENTRYPOINT_TEST_EXIT"; done\n'
        "exit 0\n",
        encoding="utf-8",
        newline="\n",
    )
    xvfb_stub = tmp_path / "Xvfb"
    xvfb_stub.write_text(
        '#!/bin/sh\nprintf "xvfb\\n" >> "$ENTRYPOINT_TEST_ORDER"\n'
        'printf "xvfb\\n" >> "$ENTRYPOINT_TEST_XVFB"\n'
        'printf "%s\\n" "$$" > "$ENTRYPOINT_TEST_PID"\n'
        '[ "$ENTRYPOINT_TEST_XVFB_MODE" != "exit" ] || exit 7\n'
        'if [ "$ENTRYPOINT_TEST_XVFB_MODE" = "warning" ]; then\n'
        '  printf "fixture-x11-warning-private-detail\\n" >&2\n'
        "fi\n"
        "trap 'exit 0' TERM INT\n"
        "while :; do sleep 0.1; done\n",
        encoding="utf-8",
        newline="\n",
    )
    xvfb_stub.chmod(0o700)
    probe_stub = tmp_path / "xdpyinfo"
    probe_stub.write_text(
        '#!/bin/sh\nwhile [ ! -f "$ENTRYPOINT_TEST_PID" ]; do sleep 0.01; done\n'
        'printf "probe:%s\\n" "$*" >> "$ENTRYPOINT_TEST_ORDER"\n'
        'case "$ENTRYPOINT_TEST_PROBE_MODE" in\n'
        '  fail|timeout) printf "fixture-probe-private-detail\\n" >&2; exit 1;;\n'
        "  hang) trap '' TERM; while :; do sleep 0.1; done;;\n"
        '  die) kill "$(cat "$ENTRYPOINT_TEST_PID")"; sleep 0.2;;\n'
        '  delayed) if [ ! -f "$ENTRYPOINT_TEST_PROBE_FIRST" ]; then\n'
        '    printf "first\\n" > "$ENTRYPOINT_TEST_PROBE_FIRST"; exit 1; fi;;\n'
        "esac\n"
        'printf "connected\\n" >> "$ENTRYPOINT_TEST_ORDER"\n',
        encoding="utf-8",
        newline="\n",
    )
    probe_stub.chmod(0o700)
    if probe_mode == "missing":
        probe_stub.unlink()
    timeout_stub = tmp_path / "timeout"
    timeout_stub.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$ENTRYPOINT_TEST_PROBE_COMMAND"\n'
        '[ "$1" = "--kill-after=1s" ] && [ "$2" = "1s" ] || exit 97\n'
        "shift 2\n"
        'if [ "$ENTRYPOINT_TEST_PROBE_MODE" = "timeout" ]; then\n'
        '  printf "probe-timeout\\n" >> "$ENTRYPOINT_TEST_ORDER"; exit 124\n'
        "fi\n"
        'if [ "$ENTRYPOINT_TEST_PROBE_MODE" = "hang" ]; then\n'
        '  exec "$ENTRYPOINT_TEST_REAL_TIMEOUT" --kill-after=1s 1s "$@"\n'
        "fi\n"
        'exec "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    timeout_stub.chmod(0o700)
    entrypoint = tmp_path / "entrypoint.sh"
    entrypoint.write_text(
        _ENTRYPOINT.read_text(encoding="utf-8")
        .replace(
            "/app/.venv/bin/media-sync", f"{shlex.quote(Path(shell).as_posix())} {shlex.quote(cli_stub.as_posix())}"
        )
        .replace("XVFB_READY_ATTEMPTS=10", "XVFB_READY_ATTEMPTS=3")
        .replace("sleep 0.2", "sleep 0.1"),
        encoding="utf-8",
        newline="\n",
    )
    trace = tmp_path / "trace.txt"
    env = dict(os.environ)
    env.update(
        {
            "PATH": os.pathsep.join((str(tmp_path), str(Path(shell).parent), env.get("PATH", ""))),
            "ENTRYPOINT_TEST_TRACE": trace.as_posix(),
            "ENTRYPOINT_TEST_XVFB": (tmp_path / "xvfb.txt").as_posix(),
            "ENTRYPOINT_TEST_EXIT": str(preflight_exit),
            "ENTRYPOINT_TEST_ORDER": (tmp_path / "order.txt").as_posix(),
            "ENTRYPOINT_TEST_PID": (tmp_path / "xvfb.pid").as_posix(),
            "ENTRYPOINT_TEST_XVFB_MODE": xvfb_mode,
            "ENTRYPOINT_TEST_PROBE_MODE": probe_mode,
            "ENTRYPOINT_TEST_PROBE_COMMAND": (tmp_path / "probe-command.txt").as_posix(),
            "ENTRYPOINT_TEST_PROBE_FIRST": (tmp_path / "probe-first.txt").as_posix(),
            "ENTRYPOINT_TEST_REAL_TIMEOUT": actual_timeout.as_posix(),
        }
    )
    if probe_mode == "missing":
        # Isolate lookup from a developer machine that may have real xdpyinfo.
        # The CLI still uses the absolute shell path substituted above.
        env["PATH"] = str(tmp_path)
    try:
        completed = subprocess.run(
            [shell, str(entrypoint), *args], env=env, capture_output=True, text=True, check=False, timeout=15
        )
    finally:
        # A successful entrypoint exec transfers Xvfb ownership to the container.
        # These are only shell stubs, so remove our exact recorded fixture PID.
        pid_file = tmp_path / "xvfb.pid"
        if pid_file.exists():
            pid = pid_file.read_text(encoding="ascii").strip()
            assert pid.isdecimal()
            check = subprocess.run(
                [shell, "-c", 'kill -0 "$1" 2>/dev/null', "fixture-liveness", pid],
                env=env,
                capture_output=True,
                check=False,
                timeout=5,
            )
            subprocess.run(
                [shell, "-c", 'kill -KILL "$1" 2>/dev/null || true', "fixture-cleanup", pid],
                env=env,
                capture_output=True,
                check=False,
                timeout=5,
            )
            if expected_error:
                assert check.returncode != 0, "entrypoint must clean up its Xvfb after startup failure"
    assert completed.stderr.strip() == expected_error, completed.stderr
    return completed.returncode, trace.read_text(encoding="utf-8").splitlines() if trace.exists() else []


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
    order = (tmp_path / "order.txt").read_text(encoding="utf-8").splitlines()
    assert order == [
        "cli:serve --host 0.0.0.0 --port 9017 --check-config",
        "xvfb",
        "probe:-display :99",
        "connected",
        "cli:db init",
        "cli:serve --host 0.0.0.0 --port 9017",
    ]


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


@pytest.mark.parametrize("args", [["serve"], ["scheduler", "supervise"]])
def test_xvfb_early_exit_is_fixed_failure_before_migration(tmp_path: Path, args: list[str]) -> None:
    code, calls = _run_entrypoint(
        tmp_path,
        args,
        xvfb_mode="exit",
        probe_mode="fail",
        expected_error='{"detail":"xvfb_start_failed"}',
    )

    assert code == 1
    assert calls == (["cli|serve|--check-config"] if args[0] == "serve" else [])
    assert "cli:db init" not in (tmp_path / "order.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("probe_mode", ["fail", "timeout", "hang"])
def test_xvfb_probe_retries_are_bounded_and_never_migrate(tmp_path: Path, probe_mode: str) -> None:
    code, calls = _run_entrypoint(
        tmp_path,
        ["serve"],
        probe_mode=probe_mode,
        expected_error='{"detail":"xvfb_ready_timeout"}',
    )

    assert code == 1
    assert calls == ["cli|serve|--check-config"]
    commands = (tmp_path / "probe-command.txt").read_text(encoding="utf-8").splitlines()
    assert commands == ["--kill-after=1s 1s xdpyinfo -display :99"] * 3


def test_successful_probe_cannot_hide_xvfb_exit_during_handshake(tmp_path: Path) -> None:
    code, calls = _run_entrypoint(
        tmp_path,
        ["serve"],
        probe_mode="die",
        expected_error='{"detail":"xvfb_start_failed"}',
    )

    assert code == 1
    assert calls == ["cli|serve|--check-config"]


def test_xvfb_warning_is_not_failure_when_display_connects(tmp_path: Path) -> None:
    code, calls = _run_entrypoint(tmp_path, ["serve"], xvfb_mode="warning")

    assert code == 0
    assert calls == ["cli|serve|--check-config", "cli|db|init", "cli|serve"]


def test_missing_display_probe_is_fixed_failure_without_xvfb_or_migration(tmp_path: Path) -> None:
    code, calls = _run_entrypoint(
        tmp_path,
        ["serve"],
        probe_mode="missing",
        expected_error='{"detail":"xvfb_probe_unavailable"}',
    )

    assert code == 1
    assert calls == ["cli|serve|--check-config"]
    assert not (tmp_path / "xvfb.txt").exists()


def test_migration_waits_for_delayed_display_connection(tmp_path: Path) -> None:
    code, calls = _run_entrypoint(tmp_path, ["serve"], probe_mode="delayed")

    assert code == 0
    assert calls == ["cli|serve|--check-config", "cli|db|init", "cli|serve"]
    order = (tmp_path / "order.txt").read_text(encoding="utf-8").splitlines()
    assert order == [
        "cli:serve --check-config",
        "xvfb",
        "probe:-display :99",
        "probe:-display :99",
        "connected",
        "cli:db init",
        "cli:serve",
    ]


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
