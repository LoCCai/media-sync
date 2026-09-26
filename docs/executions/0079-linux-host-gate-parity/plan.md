**English** | [中文](plan.zh.md)

# Execution 0079 plan

- Status: Complete
- Date: 2026-09-26

## Steps

1. Fast-forward the server checkout to the remote `main`, stashing and re-applying the uncommitted 2026-09-12 deployment-record documents, then commit and push them as their own record.
2. Install the host toolchain (uv, Node 22 with the pinned pnpm) and run every local gate on the pulled tree to obtain a baseline failure inventory.
3. Attribute every failure to a root cause by re-running the failing set against the pristine tree, so pre-existing host failures are never mistaken for regressions.
4. Make the strict mypy gate platform-independent: swap enclosing `os.name` guards for `sys.platform` guards that mypy narrows (runtime-equivalent), and use paired `attr-defined, unused-ignore` comments only where Windows helpers must stay callable on POSIX under mocked native contracts.
5. Fix test-side portability: replace `Path(sys.executable).resolve()` fixture values with production `normalize_python_executable` semantics, scope the POSIX launcher test's subprocess mock to launcher probes only, and widen one load-sensitive bounding assertion while keeping it far below the bounded child's lifetime.
6. Fix the Emby failure-recording WAL busy-snapshot race with BEGIN IMMEDIATE plus a bounded retry, mirroring the operation coordinator's durable-write pattern.
7. Re-run the complete gate set on the final tree, rebuild the deployment image with the exact source revision, recreate the container, and verify health, deep doctor and UI reachability.

## Deviations

- None: every planned step ran; one load-sensitive cancellation test failed once during the 26-minute full suite and passed 3/3 in isolated reruns (recorded in verification).
