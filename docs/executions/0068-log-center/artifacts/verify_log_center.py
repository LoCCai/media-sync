"""Offline affected regression. Does not access production or external platforms."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
TESTS = {
    "tests/unit/test_log_store.py", "tests/unit/test_log_center_api.py", "tests/unit/test_cli_log_center.py",
    "tests/unit/test_lifecycle_observability.py", "tests/integration/test_lifecycle_events.py",
    "tests/unit/test_config.py", "tests/unit/test_cli.py", "tests/unit/test_operator_auth_api.py",
    "tests/unit/test_support_bundle.py", "tests/unit/test_job_diagnostics.py",
    "tests/integration/test_packaged_migrations.py", "tests/integration/test_emby_application.py",
    "tests/integration/test_library_application.py", "tests/integration/test_scheduler_secret_sinks.py",
}
for directory in ("unit", "contract", "integration"):
    for pattern in ("test_*login*.py", "test_*operation*.py", "test_*scheduler*.py", "test_*supervisor*.py",
                    "test_*pipeline*.py", "test_api_*.py"):
        TESTS.update(str(path.relative_to(ROOT)) for path in (ROOT / "tests" / directory).glob(pattern))

if __name__ == "__main__":
    raise SystemExit(subprocess.call(
        [sys.executable, "-m", "pytest", *sorted(TESTS), "-q", "--tb=short", "--junitxml",
         str(Path(__file__).with_name("log-regression.xml"))], cwd=ROOT,
    ))
