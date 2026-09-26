**English** | [中文](goal.zh.md)

# Execution 0079 goal

- Status: Complete — delivered on the Linux deployment host
- Date: 2026-09-26
- Prior work: 0078 closeout (`764f46b`) and the 2026-09-12 server deployment record (`ec67097`)
- Scope: reproduce the complete local quality gate on the Linux deployment host, then fix every cross-platform defect it exposes

## Target outcomes

1. All local gates (Ruff lint/format, strict mypy, full pytest, documentation and upstream checks, Web tests/check/build) run and pass on the Linux server that actually deploys the container, not only on the Windows authoring workstation.
2. `mypy --strict src` passes under both platform views (`--platform linux` and `--platform win32`) so the strict gate no longer depends on the authoring OS.
3. Test fixtures stop dereferencing POSIX venv launcher symlinks: fake verifiers and manifests mirror production `normalize_python_executable` semantics, and the POSIX-only launcher test keeps its subprocess mock from leaking into real git verification.
4. The Emby export failure-recording path no longer misclassifies `stale_publish` as `export_failure_finalize_failed` when a concurrent worker's commit invalidates a WAL read snapshot (busy-snapshot conflicts ignore the busy timeout).
5. 0078 closeout documentation debt is cleared: the duplicated execution-index rows and the stale "in progress" progress status.

## Acceptance boundaries

- No XHS or Douyin delivery logic, contract or semantics change; the 0077 freeze is untouched.
- All live-platform rows remain `NOT_RUN` and stay operator-gated per the deployment handoff.
- Production guard changes are limited to swapping `os.name` checks for `sys.platform` checks (runtime-equivalent on every supported platform) plus paired platform-scoped type ignores; the WAL fix reuses the operation coordinator's existing BEGIN IMMEDIATE bounded-retry pattern.
