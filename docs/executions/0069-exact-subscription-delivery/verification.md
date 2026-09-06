**English** | [中文](verification.zh.md)

# Verification

Status: implementation gates have not run.

## Planning evidence

- Worktree and `origin/main`: `f41c6b3ea53a92903c4494daa78c95dc51e828ee` before this checkpoint.
- Read-only repository trace established that `POST .../run-now` calls only `DurableSchedulerService.run_now`, and both bounded workers use global `claim_next`.
- A pure in-memory Bilibili model reproduced a source-end sweep that missed one still-visible item after a page-boundary deletion; existing coverage checks still accepted the sweep. This prevents any permanent `history_complete` claim.
- Real Windows process evidence established: exporter access `0` allowed ancestor rename; `FILE_LIST_DIRECTORY` denied it while open and allowed it after release.
- Existing focused output inspection baseline: `22 passed, 39 deselected`. An in-memory directory-access substitution passed the exporter/application/pipeline set: `109 passed`. These are design evidence only, not verification of an edited source tree.

## Required implementation gates

- Migration upgrade/downgrade preservation and refusal cases on SQLite; PostgreSQL constraint path where available.
- Exact scheduler/pipeline claim, concurrency, idempotency, cancellation and recovery tests.
- Typed Operation payload/result/API/auth/log/diagnostic tests.
- Deterministic no-media-server end-to-end directory delivery and zero-work replay.
- Bilibili per-feed scan-progress transaction and drift-negative tests; six-platform unproven projection tests.
- Real Windows rename pin test and non-Windows compatibility check.
- Complete Python and web quality/build/contract suites.

Live QR, creator, CDN, download and media-server acceptance: `NOT_RUN`.

