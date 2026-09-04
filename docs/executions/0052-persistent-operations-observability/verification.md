**English** | [中文](verification.zh.md)

# Execution 0052 verification

- Status: Local implementation and all frozen closeout gates pass; publication reconciliation follows the containing commit
- Closeout date: 2026-09-05
- Baseline: `d64b97b`
- Database migration: `0006_operations_observability`

## Automated evidence

| Check | Process | Result |
| --- | --- | --- |
| Persistence/migration/CLI focus | Repository, SQLite multi-writer, migration upgrade/downgrade/package and CLI selection | `PASS` — 141 passed |
| Coordinator/domain regression | Coordinator plus login/download/scheduler/pipeline/Emby subject and cancellation selection | `PASS` — 207 passed |
| Operation/API integration | Operation payload, repository, coordinator, scheduler, pipeline and API/SSE selection | `PASS` — 241 passed; one known Starlette/httpx deprecation warning |
| Support bundle | `uv run --frozen pytest -q -p no:cacheprovider tests/unit/test_support_bundle.py tests/unit/test_api_support_bundle.py` | `PASS` — 30 passed |
| Final operation regression | Operation repository/coordinator/API/server/support selection after cancellation and cursor hardening | `PASS` — 78 passed; one known Starlette/httpx deprecation warning |
| Web units | `pnpm test` from `web/` | `PASS` — 17 tests |
| Web format | `pnpm format:check` from `web/` | `PASS` |
| Svelte/TypeScript | `pnpm check` from `web/` | `PASS` — 0 errors, 0 warnings |
| Static production bundle | `pnpm build` from `web/` | `PASS` — adapter-static build completed |
| Python quality | Whole-repository Ruff; Ruff format; strict mypy; compileall | `PASS` — 662 files formatted; 94 typed source files |
| Distribution build | `uv build` | `PASS` — sdist and wheel |
| Documentation | `uv run --frozen python scripts/check_docs.py` after closeout edits | `PASS` — 466 Markdown files |
| Locked upstreams | `uv run --frozen python scripts/check_upstreams.py` | `PASS` — 2 locked, clean checkouts |
| Tracked output audit | Generated/local-state denylist over `git ls-files` | `PASS` — 733 tracked files; no forbidden output |
| Repository whitespace | `git diff --check` after closeout edits | `PASS` |
| Complete Python suite | `uv run --frozen pytest -q` | `PASS` — 2315 passed, 3 skipped, 1 warning in 555.05s (0:09:15) |
| Git push reconciliation | Compare local `HEAD`, `origin/main` and GitHub `refs/heads/main` after pushing the containing closeout commit | Performed post-commit; self SHA intentionally not embedded |

Focused selections overlap and must not be added together. A pre-freeze diagnostic run produced 2308 passes, 3 skips and two Windows child-process timeouts; both timed-out tests immediately passed alone in 3.24 seconds. The API changed during that run, so only the later frozen `2315 passed` result is authoritative. The three final skips are the existing Windows-inapplicable POSIX launcher/mode tests, and the warning is the existing Starlette/httpx deprecation.

## Requirement evidence

| Requirement | Verified evidence |
| --- | --- |
| Migration and persistent history | `0006` tests exercise upgrade/downgrade, metadata/package alignment and the four Operation tables; repository/API tests open fresh sessions and preserve history across coordinator/app instances |
| Active-scope and request idempotency | Concurrent SQLite tests enforce one active exclusive key; same digest/fingerprint replays one identity, while changed fingerprints and malformed/duplicate headers return fixed errors without echo |
| State and lease fencing | Repository/coordinator tests cover valid transitions, immutable terminal rows, ABA/stale-token rejection, heartbeats, four-transaction bounded contention retry and pending terminal-intent retry |
| Commit-ordered events | Concurrent repository tests exercise atomic operation-local and global sequences, transactional counter allocation, keyset paging and a 10,000-event bounded path |
| Five workflow wiring | API and coordinator regressions cover account login, asset download, scheduler run, pipeline run and Emby export, including domain subject links and closed result summaries |
| Truthful cancellation and recovery | Tests cover request versus observation, cross-coordinator durable cancellation before all five domain handoffs, concurrent-observer ordering, bounded shutdown waits, success/cancel races, valid foreign lease preservation and conservative Job/LoginSession-backed or `interrupted` convergence |
| Bounded public API | List/detail/event/cancel tests cover pagination/filter errors and prove revision, fingerprints, requester, lease state, worker identities and raw idempotency data never serialize |
| SSE reconnect | The ready frame carries `initial_cursor`; fresh high-water and reconnect replay, invalid/future/expired/signed-BIGINT-overflow cursors, bounded batches, keepalive/disconnect and cross-session visibility are covered |
| Safe support response | Service and HTTP tests verify the fixed aggregate JSON shape, 16 KiB cap, canonical bytes, `application/json`, `no-store`, database-failure code and second-pass secret/path/query/QR/exception scan |
| Task-center state | Seventeen Web units cover filtering, ordering, snapshot/event merge, cursor de-duplication, reconnect and polling fallback; Svelte check and production compilation pass |

## Residual and deferred evidence

- Current Web units do not mount and interact with the real Jobs route in a browser. Route-interaction/E2E coverage is follow-up quality debt and is not silently treated as passed.
- The task center intentionally does not show internal requester, lease, revision or idempotency/fingerprint state. It does not provide a retry endpoint or subscription pause/resume/delete audit.
- Operation events are not a generic file-log subsystem, and the support endpoint is not a ZIP or broad environment export. Existing supervisor Jobs are not claimed to be unified into API Operations.
- The API lifespan tolerates a temporarily unavailable operation database so health can start; operation reads and submissions then fail with fixed safe availability codes. This is availability behavior, not successful task execution.

## Evidence policy

No real browser account, creator endpoint, platform API/CDN, downloaded creator media, Linux persistence/backup/process drill or Emby/Jellyfin server was used by these focused gates. Every such row remains `NOT_RUN` under Execution 0047. No offline test, local static build or support-bundle response changes live qualification.
