"""Reproduce the frozen log-center cross-layer selection without production access."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
TESTS = [
    "tests/unit/test_log_store.py",
    "tests/unit/test_log_center_api.py",
    "tests/unit/test_cli_log_center.py",
    "tests/unit/test_lifecycle_observability.py",
    "tests/integration/test_lifecycle_events.py",
    "tests/unit/test_login_events.py",
    "tests/unit/test_login_diagnostics.py",
    "tests/contract/test_login_event_channel.py",
    "tests/integration/test_login_event_scope.py",
    "tests/unit/test_operator_auth_api.py",
    "tests/unit/test_cli.py",
    "tests/unit/test_cli_login.py",
    "tests/unit/test_cli_supervisor.py",
]

if __name__ == "__main__":
    raise SystemExit(subprocess.call(
        [sys.executable, "-m", "pytest", *TESTS, "-q", "--tb=short", "--junitxml",
         str(Path(__file__).with_name("final-log-regression.xml"))], cwd=ROOT,
    ))
