**English** | [中文](verification.zh.md)

# Verification

Baseline: published 8b80460; plan 9ec7d8d and refinement 79c2168 committed before implementation. No private deployment addresses, account/run/login identifiers or browser snapshots are retained in Git. Raw XML artifacts are ignored; the measured commands/results are recorded here.

## Python gates

- Root projection/API/CLI/Operation/security union: `.venv/Scripts/python.exe -m pytest -q tests/unit/test_scheduler_diagnostic_projection.py tests/unit/test_cli.py tests/unit/test_api_server.py tests/unit/test_api_operations.py tests/unit/test_operation_payloads.py tests/integration/test_scheduler_secret_sinks.py tests/integration/test_mediacrawler_security_matrix.py --junitxml=artifacts/scheduler-diagnostics-projection.xml` — **368 passed**, one existing Starlette/httpx deprecation warning, **68.01s**.
- Root final scheduler union: `.venv/Scripts/python.exe -m pytest -q tests/unit/test_scheduler_policy.py tests/unit/test_scheduler_handlers.py tests/unit/test_scheduler_supervisor.py tests/integration/test_scheduler_repository.py tests/integration/test_scheduler_worker.py tests/integration/test_scheduler_heartbeat_diagnostics.py tests/integration/test_scheduler_handler_safety.py tests/integration/test_scheduler_supervisor.py tests/integration/test_mediacrawler_scheduler_handler.py --junitxml=artifacts/scheduler-diagnostics-worker.xml` — **269 passed, 1 skipped, 55.75s**. The skip is a POSIX venv-symlink test on Windows, not a passed platform check.
- Agent worker/policy/real-SQLite focus: **118 passed, 8.48s**. Root worker-only check: **73 passed, 7.37s**. Independent real-contention/projection union: **141 passed, 1.73s**. These overlap and are not added to the root totals.
- Real contention uses an actual file-backed WAL database plus a second physical SQLite connection holding BEGIN IMMEDIATE. Only this test engine uses 100ms busy timeout; production stays 5000ms. The actual SQLAlchemy exception has native integer SQLITE_BUSY, runs off the event loop, and handler cancellation/join releases the lock before the sole finalization. Failed Job/running Run/zero Content/authenticated account/no secret-text persistence are asserted. Final test passed five consecutive isolated runs: **1.40s, 1.22s, 1.43s, 1.32s, 1.47s**.
- Injected cases separately cover generic heartbeat errors, native extended BUSY/LOCKED, wrong types/forged codes/text-only lookalikes, succeeded Run preservation, pre-finalize versus actual-finalize exceptions, persistent outage, lease loss, ordinary/cleanup cancellation, already-completed tasks and simultaneous completion. Cleanup fences still join in-flight heartbeat and do not gain finalization authority.

## Corrections during validation

The first projection subset was 233 passed / 1 failed because an old CLI assertion forbade even the now-authorized fixed license code. It was updated to assert that exact code while retaining all raw-secret/payload exclusions; the final 368-test union passed. Initial new worker fixtures used an unsupported cleanup-exception constructor and relied on unordered RunEvent rows; both test assumptions were corrected. A broader run that collected before that correction was 266 passed / 1 failed / 1 skipped; the final rerun above passed with two additional cancellation cases collected.

A repeated real-contention run exposed Windows monotonic clock resolution (about 15.625ms) rounding a 100ms wait down to 93ms; the test now measures with perf_counter without weakening its actual lock/timeout assertions. Independent review also found that propagating cleanup fences could bypass heartbeat join in finally; nested finally preserves the join, and two external-cancel/in-flight-heartbeat cases close this finding. These intermediate failures are not represented as passes.

## Web and static gates

Web gates ran serially from **19:39:20 to 19:40:42 UTC+8**: targeted `pnpm exec vitest run src/lib/utils/scheduler-job-diagnostics.test.ts src/lib/api/scheduler-job-detail.test.ts src/lib/utils/scheduler-worker-display.test.ts` passed **135 tests / 3 files**; full `pnpm test` passed **343 tests / 15 files**; `pnpm check` reported **0 errors / 0 warnings**; `pnpm format:check` and `pnpm build` passed. Vite build reported 3.15s client / 8.07s overall and only a plugin-timing performance notice. Web diff whitespace check passed; no Web failure/retry occurred. These are helper/request-generation/build checks, not rendered-page or deployed-browser evidence.

Python final Ruff check, Ruff format (**259 files**), mypy (**110 source files**) and compileall have passed. Both locked upstreams verify unchanged. The docs/link checker passed **572 Markdown files** before the final result text; it will run again before commit. A fresh fetch confirmed the two frozen docs commits ahead / zero behind the published baseline. Independent service/policy/projection review closed the cleanup-join finding; root reviewed the bounded Web changes and historical-error wording. No unresolved finding remains within this diagnostic slice.

## Evidence limits and publication

No full Python suite, Docker build, real PostgreSQL execution, package rebuild or rendered-browser run is claimed for this bounded increment. The production canary remains **FAILED** and new deployed diagnostics **NOT_RUN**. Neither genuine offline SQLite contention nor injected reproduction proves the historical production cause. No historical Run repair, production task, deployment, new login, download, export or supervisor restart was performed. Publication hash and remote verification will be recorded after final gates.
