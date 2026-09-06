"""Re-run the offline output-directory regression; no production access."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
TESTS = [
    "tests/integration/test_output_directories.py",
    "tests/integration/test_output_directory_migration.py",
    "tests/integration/test_pipeline_output_directories.py",
    "tests/integration/test_pipeline_runtime.py",
    "tests/integration/test_pipeline_worker.py",
    "tests/integration/test_offline_media_pipeline.py",
    "tests/integration/test_scheduled_offline_pipeline.py",
    "tests/integration/test_emby_application.py",
    "tests/integration/test_library_application.py",
    "tests/integration/test_media_server_publication.py",
    "tests/integration/test_packaged_migrations.py",
    "tests/integration/test_cookie_login_migration.py",
    "tests/unit/test_library_exporter_factory.py",
    "tests/unit/test_media_server_publication_scope.py",
    "tests/unit/test_cli.py",
    "tests/unit/test_operator_auth_api.py",
    "tests/unit/test_support_bundle.py",
    "tests/unit/test_job_diagnostics.py",
    "tests/contract/test_emby_export_contract.py",
]
TESTS += sorted(str(path.relative_to(ROOT)) for path in (ROOT / "tests/unit").glob("test_api_*.py"))

if __name__ == "__main__":
    raise SystemExit(subprocess.call(
        [sys.executable, "-m", "pytest", *TESTS, "-q", "--junitxml",
         str(Path(__file__).with_name("output-regression.xml"))], cwd=ROOT,
    ))
