# Frozen one-shot verification recipe for execution 0008.
#
# This file preserves the exact node allowlist, sentinels, SQLite authority
# checks, alias validation, retained-tree statistics and Git checks used by
# the authoritative closeout. It is intentionally fail-closed: the retained
# root now exists, so this recipe must never be run again for execution 0008.

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$watch = [Diagnostics.Stopwatch]::StartNew()
$workspace = (Resolve-Path -LiteralPath '.').Path
$relativeRoot = '.media-sync/verification/0008-closeout-sentinel-root'
$sentinelRoot = [IO.Path]::GetFullPath((Join-Path $workspace $relativeRoot))
$workspacePrefix = $workspace.TrimEnd(
    [IO.Path]::DirectorySeparatorChar,
    [IO.Path]::AltDirectorySeparatorChar
) + [IO.Path]::DirectorySeparatorChar

if (-not $sentinelRoot.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The closeout sentinel root escaped the workspace.'
}
if (Test-Path -LiteralPath $sentinelRoot) {
    throw "Closeout sentinel root already exists; never delete or rerun it: $sentinelRoot"
}

& git check-ignore -q -- "$relativeRoot/probe"
if ($LASTEXITCODE -ne 0) {
    throw 'The closeout sentinel root is not ignored by Git.'
}
$preexistingTracked = @(& git ls-files -- "$relativeRoot/**")
if ($LASTEXITCODE -ne 0 -or $preexistingTracked.Count -ne 0) {
    throw 'Tracked files unexpectedly exist below the closeout sentinel root.'
}

$nodes = @(
    'tests/integration/test_mediacrawler_scheduler_handler.py::test_all_platform_fixtures_prepare_v3_and_ingest_forward_off_loop'
    'tests/integration/test_mediacrawler_scheduler_handler.py::test_all_platforms_cross_real_v3_v2_process_protocol_retry_and_idempotent_restart'
    'tests/integration/test_mediacrawler_scheduler_handler.py::test_real_handler_process_wait_keeps_heartbeat_and_independent_sqlite_writer_live'
    'tests/integration/test_mediacrawler_scheduler_handler.py::test_bridge_late_failure_removes_the_exact_attempt_root'
    'tests/contract/test_mediacrawler_bridge.py::test_manifest_v3_binds_scheduler_and_attempt_identity'
    'tests/contract/test_mediacrawler_bridge.py::test_sealed_v2_v1_artifacts_round_trip_byte_exact_and_read_only'
    'tests/contract/test_mediacrawler_supervision.py::test_start_token_is_sent_only_after_tree_attachment'
    'tests/contract/test_mediacrawler_supervision.py::test_running_cancel_joins_child_and_grandchild_before_cleanup'
    'tests/contract/test_mediacrawler_supervision.py::test_cancel_after_successful_tree_join_never_starts_receipt_seal'
    'tests/contract/test_mediacrawler_supervision.py::test_receipt_failure_removes_secret_bytes_but_preserves_profile'
    'tests/contract/test_mediacrawler_supervision.py::test_hard_parent_death_stops_real_child_tree_and_allows_safe_recovery'
    'tests/contract/test_mediacrawler_supervision.py::test_pinned_shape_parse_cmd_preserves_cookie_delay_and_single_concurrency'
    'tests/integration/test_mediacrawler_scheduler_handler.py::test_child_exit_pre_seal_cancellation_never_enters_normalization_or_ingestion'
    'tests/integration/test_mediacrawler_scheduler_handler.py::test_post_seal_pre_ingest_cancellation_joins_before_unwind'
    'tests/integration/test_mediacrawler_security_matrix.py::test_mediacrawler_security_matrix_declares_exactly_thirty_three_cells'
    'tests/integration/test_mediacrawler_security_matrix.py::test_mediacrawler_failure_matrix_checks_every_sink'
    'tests/integration/test_scheduler_worker.py::test_worker_heartbeats_blocking_handler_then_cancel_returns_durable_terminal_state'
    'tests/integration/test_scheduler_secret_sinks.py::test_raw_handler_secret_stays_out_of_scheduler_and_retained_artifacts'
    'tests/integration/test_secret_sinks.py::test_all_json_error_and_url_sinks_redact_before_sqlite'
    'tests/integration/test_scheduled_offline_pipeline.py::test_scheduled_offline_pipeline_survives_restart_without_duplicate_identities'
    'tests/unit/test_cli.py::test_mediacrawler_dry_run_rejects_signed_creator_url_without_echoing_token'
    'tests/unit/test_cli.py::test_scheduler_mediacrawler_enablement_and_license_are_explicit'
)
if ($nodes.Count -ne 22) {
    throw "Expected 22 exact function nodes, observed $($nodes.Count)."
}

New-Item -ItemType Directory -Path $sentinelRoot | Out-Null
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_ADDOPTS = ''

$pytestArgs = @(
    'run'
    'pytest'
    '-vv'
    '--tb=short'
    '-p'
    'no:cacheprovider'
    '--basetemp'
    (Join-Path $sentinelRoot 'pytest')
    '--junitxml'
    (Join-Path $sentinelRoot 'pytest-junit.xml')
)
& uv @pytestArgs @nodes 2>&1 |
    Tee-Object -FilePath (Join-Path $sentinelRoot 'pytest-output.txt')
$pytestExit = $LASTEXITCODE
if ($pytestExit -ne 0) {
    throw "Focused closeout suite failed with exit code $pytestExit."
}

[xml]$junit = Get-Content -LiteralPath (Join-Path $sentinelRoot 'pytest-junit.xml') -Raw
$collectedCases = @($junit.SelectNodes('//testcase')).Count
if ($collectedCases -ne 45) {
    throw "Expected 45 exact pytest cases, observed $collectedCases."
}

$pythonAudit = @'
from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
import sys
from pathlib import Path
from xml.etree import ElementTree

root = Path(sys.argv[1]).resolve(strict=True)
phase = sys.argv[2]
receipt = root / "closeout-sentinel-PASS.txt"
if phase not in {"before_receipt", "after_receipt"}:
    raise AssertionError("unknown retained-audit phase")
if receipt.exists() != (phase == "after_receipt"):
    raise AssertionError("completion receipt has the wrong phase state")

needles = (
    b"fixture-cookie-value",
    b"SUPERVISION-COOKIE-SENTINEL-a84f83",
    b"PARSE-CALL-COOKIE-3ebc62",
    b"SENTINEL-scheduler-handler-secret-must-not-persist",
    b"sentinel-secret-value",
    b"SENTINEL-runtime-signed-query-0005",
    b"sentinel-xsec-token",
    b"attempt-secret",
    b"matrix-benign-cookie",
    b"MATRIX_SECRET_",
    b"COOKIE-SENTINEL-9f07c7b6",
    b"SIGNED-CREATOR-SENTINEL-3a7a53",
)

reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def fail_walk(error: OSError) -> None:
    raise error


def is_link_or_reparse(path: Path) -> bool:
    metadata = path.lstat()
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


real_directories: list[Path] = []
real_files: list[Path] = []
aliases: list[Path] = []

for current_text, directory_names, file_names in os.walk(
    root,
    topdown=True,
    onerror=fail_walk,
    followlinks=False,
):
    current = Path(current_text)
    real_directories.append(current)
    retained_directories: list[str] = []
    for name in directory_names:
        candidate = current / name
        if not is_link_or_reparse(candidate):
            if not stat.S_ISDIR(candidate.lstat().st_mode):
                raise AssertionError("non-directory entered the directory traversal")
            retained_directories.append(name)
            continue
        if not name.endswith("current"):
            raise AssertionError("unexpected reparse point below retained root")
        raw_target = Path(os.readlink(candidate))
        target = (candidate.parent / raw_target).resolve(strict=True) if not raw_target.is_absolute() else raw_target.resolve(strict=True)
        target.relative_to(root)
        if target.parent != candidate.parent.resolve(strict=True):
            raise AssertionError("pytest current alias target is not a same-parent target")
        if not stat.S_ISDIR(target.stat().st_mode):
            raise AssertionError("pytest current alias target is not a directory")
        aliases.append(candidate)
    directory_names[:] = retained_directories

    for name in file_names:
        candidate = current / name
        metadata = candidate.lstat()
        if is_link_or_reparse(candidate):
            raise AssertionError("file reparse point below retained root")
        if not stat.S_ISREG(metadata.st_mode):
            raise AssertionError("non-regular retained file")
        real_files.append(candidate)

if len(aliases) != 24:
    raise AssertionError(f"expected 24 pytest current aliases, observed {len(aliases)}")

for retained_path in (*real_directories, *real_files):
    relative_bytes = str(retained_path.relative_to(root)).encode("utf-8")
    if any(needle in relative_bytes for needle in needles):
        raise AssertionError("sentinel remained in a retained path name")

for retained_file in real_files:
    payload = retained_file.read_bytes()
    if any(needle in payload for needle in needles):
        raise AssertionError("sentinel remained in a retained file")

junit_root = ElementTree.parse(root / "pytest-junit.xml").getroot()
testcases = junit_root.findall(".//testcase")
if len(testcases) != 45:
    raise AssertionError("retained JUnit does not contain exactly 45 cases")
matrix_cases = [
    testcase
    for testcase in testcases
    if "test_mediacrawler_security_matrix" in testcase.attrib.get("classname", "")
]
if len(matrix_cases) != 12:
    raise AssertionError("retained JUnit does not contain exactly 12 matrix cases")

sqlite_databases = sorted(path for path in real_files if path.name.endswith(".sqlite3"))
sqlite_sidecars = sorted(
    path for path in real_files if path.name.endswith((".sqlite3-wal", ".sqlite3-shm"))
)
if len(sqlite_databases) != 35:
    raise AssertionError(f"expected 35 SQLite databases, observed {len(sqlite_databases)}")
if len(sqlite_sidecars) != 22:
    raise AssertionError(f"expected 22 SQLite sidecars, observed {len(sqlite_sidecars)}")


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


for database in sqlite_databases:
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            query = f"SELECT * FROM {quote_identifier(table)}"
            for row in connection.execute(query):
                for value in row:
                    if isinstance(value, str):
                        encoded = value.encode("utf-8")
                    elif isinstance(value, bytes):
                        encoded = value
                    else:
                        continue
                    if any(needle in encoded for needle in needles):
                        raise AssertionError("sentinel remained in a logical SQLite value")
    finally:
        connection.close()

matrix_databases = sorted(
    (
        path
        for path in sqlite_databases
        if path.name == "matrix.sqlite3"
        and re.fullmatch(r"test_mediacrawler_failure_matr\d+", path.parent.name)
    ),
    key=lambda path: int(re.search(r"(\d+)$", path.parent.name).group(1)),
)
if len(matrix_databases) != 11:
    raise AssertionError("expected exactly eleven real matrix databases")

expected = (
    ("failed_terminal", "failed_terminal", "output_security_failed", "output_security_failed", False),
    ("retry_wait", "failed_retryable", "temporary_upstream", "temporary_upstream", False),
    ("retry_wait", "failed_retryable", "upstream_timeout", "upstream_timeout", False),
    ("failed_terminal", "failed_terminal", "output_security_failed", "output_security_failed", False),
    ("failed_terminal", "failed_terminal", "output_security_failed", "output_security_failed", False),
    ("failed_terminal", "failed_terminal", "output_security_failed", "output_security_failed", False),
    ("failed_terminal", "failed_terminal", "output_security_failed", "output_security_failed", False),
    ("failed_terminal", "failed_terminal", "output_security_failed", "output_security_failed", False),
    ("failed_terminal", "failed_terminal", "output_security_failed", "output_security_failed", False),
    ("running", "running", None, None, True),
    ("cancelled", "cancelled", None, "scheduler_cancelled", False),
)

for database, disposition in zip(matrix_databases, expected, strict=True):
    job_status, run_status, job_error, run_error, authority_retained = disposition
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        jobs = connection.execute(
            "SELECT status, lease_owner, lease_token, last_error_code FROM jobs"
        ).fetchall()
        runs = connection.execute(
            "SELECT status, error_code FROM sync_runs"
        ).fetchall()
        subscriptions = connection.execute(
            "SELECT cursor, checkpoint_revision, last_success_at FROM subscriptions"
        ).fetchall()
        content_count = connection.execute("SELECT count(*) FROM contents").fetchone()[0]
        asset_count = connection.execute("SELECT count(*) FROM assets").fetchone()[0]
    finally:
        connection.close()

    if len(jobs) != 1 or len(runs) != 1 or len(subscriptions) != 1:
        raise AssertionError("matrix database cardinality changed")
    observed_job_status, lease_owner, lease_token, observed_job_error = jobs[0]
    observed_run_status, observed_run_error = runs[0]
    cursor, checkpoint_revision, last_success_at = subscriptions[0]
    if (
        observed_job_status != job_status
        or observed_run_status != run_status
        or observed_job_error != job_error
        or observed_run_error != run_error
    ):
        raise AssertionError("matrix scheduler disposition changed")
    if authority_retained != (lease_owner is not None and lease_token is not None):
        raise AssertionError("matrix lease authority changed")
    if not authority_retained and (lease_owner is not None or lease_token is not None):
        raise AssertionError("partial matrix lease authority remained")
    if cursor not in (None, "null") or checkpoint_revision != 0 or last_success_at is not None:
        raise AssertionError("matrix checkpoint authority changed")
    if content_count != 0 or asset_count != 0:
        raise AssertionError("matrix ingestion unexpectedly persisted rows")

file_bytes = sum(path.lstat().st_size for path in real_files)
expected_stats = {
    "before_receipt": (369, 483, 10_104_647),
    "after_receipt": (370, 483, 10_104_859),
}
expected_files, expected_directories, expected_bytes = expected_stats[phase]
if (
    len(real_files) != expected_files
    or len(real_directories) != expected_directories
    or file_bytes != expected_bytes
):
    raise AssertionError(
        "retained-tree statistics changed: "
        f"files={len(real_files)} directories={len(real_directories)} bytes={file_bytes}"
    )

print(
    json.dumps(
        {
            "aliases": len(aliases),
            "bytes": file_bytes,
            "directories": len(real_directories),
            "files": len(real_files),
            "matrix_cases": len(matrix_cases),
            "secret_scans": len(needles),
            "sqlite_authority_rows": len(matrix_databases),
            "sqlite_files": len(sqlite_databases),
            "sqlite_sidecars": len(sqlite_sidecars),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
)
'@

function Invoke-RetainedAudit {
    param([Parameter(Mandatory = $true)][string]$Phase)

    $auditOutput = @($pythonAudit | & uv run python - $sentinelRoot $Phase)
    $auditExit = $LASTEXITCODE
    if ($auditExit -ne 0) {
        throw "Retained artifact audit failed in phase $Phase with exit code $auditExit."
    }
    return ($auditOutput -join [Environment]::NewLine) | ConvertFrom-Json
}

$beforeReceipt = Invoke-RetainedAudit -Phase 'before_receipt'

$tracked = @(& git ls-files -- "$relativeRoot/**")
if ($LASTEXITCODE -ne 0 -or $tracked.Count -ne 0) {
    throw 'The retained root contains tracked files.'
}
$statusLines = @(& git status --short --untracked-files=all -- $relativeRoot)
if ($LASTEXITCODE -ne 0 -or $statusLines.Count -ne 0) {
    throw 'The retained root appears in Git status.'
}

$receiptLines = @(
    'PASS'
    'function_nodes=22'
    'pytest_cases=45'
    'matrix_cells=33'
    'sqlite_authority_rows=11'
    'secret_scans=12'
    'aliases=24'
    'scan_scope=all hidden and ignored real files below the fresh retained root'
    'path_exclusions=none'
)
$receiptText = ($receiptLines -join [Environment]::NewLine) + [Environment]::NewLine
[IO.File]::WriteAllText(
    (Join-Path $sentinelRoot 'closeout-sentinel-PASS.txt'),
    $receiptText,
    [Text.UTF8Encoding]::new($false)
)

$afterReceipt = Invoke-RetainedAudit -Phase 'after_receipt'
$watch.Stop()

Write-Output "CLOSEOUT_PASS exit=0"
Write-Output "nodes=$($nodes.Count)"
Write-Output "cases=$collectedCases"
Write-Output "matrix_cases=$($afterReceipt.matrix_cases)"
Write-Output "matrix_cells=33"
Write-Output "secret_scans=$($afterReceipt.secret_scans)"
Write-Output "sqlite_authority_rows=$($afterReceipt.sqlite_authority_rows)"
Write-Output "sqlite_files=$($afterReceipt.sqlite_files)"
Write-Output "sqlite_sidecars=$($afterReceipt.sqlite_sidecars)"
Write-Output "aliases=$($afterReceipt.aliases)"
Write-Output "real_files=$($afterReceipt.files)"
Write-Output "real_directories_including_root=$($afterReceipt.directories)"
Write-Output "bytes=$($afterReceipt.bytes)"
Write-Output "tracked=$($tracked.Count)"
Write-Output "status_lines=$($statusLines.Count)"
Write-Output ("wall={0:F2}s" -f $watch.Elapsed.TotalSeconds)
