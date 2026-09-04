**English** | [中文](progress.zh.md)

# Execution 0052 progress

- Status: Delivered and verified locally; the closeout commit and GitHub reconciliation follow this record
- Closeout date: 2026-09-05
- Baseline: `d64b97b`
- Database migration: `0006_operations_observability`

## Delivered

1. Added the four durable tables `operations`, `operation_events`, `operation_subjects` and `operation_event_stream_state`, including constrained lifecycle shapes, active-scope and idempotency uniqueness, subject indexes and a singleton transactionally updated stream cursor.
2. Added the durable repository state machine: atomic create-or-replay, claim, heartbeat, progress, subject/event append, two-stage cancel, immutable terminal transitions, lease-token fencing, bounded list/event keyset pagination, stream bounds and conservative expired-work reconciliation.
3. Added closed request-identity, result-summary and event-context contracts for `account-login`, `asset-download`, `scheduler-run`, `pipeline-run` and `emby-export`. Payload size/depth/count bounds and forbidden-value checks fail closed before persistence.
4. Added `OperationCoordinator` and connected all five workflows. Create/replay plus claim commit atomically before a callable starts; worker identity is server-derived; heartbeat and cancellation monitoring are bounded; subject hooks link durable domain entities; pending terminal intent survives transient SQLite write contention for monitor retry. A phase boundary that discovers durable cancellation synchronously records observation, while a concurrent observer waits for the first observer to commit before terminal CAS.
5. Fixed a SQLite WAL deferred-read-to-write `BUSY_SNAPSHOT` race found during isolated reruns. Authoritative reads now acquire `BEGIN IMMEDIATE` and retry at most four fresh transactions. Shutdown establishes one deadline before cancellation observation, bounds any wait for an existing observer and stops monitor work when that deadline is reached.
6. Replaced process-local API operation responses with durable submission. Strict `Idempotency-Key` validation supports safe replay/conflict, private references enter fingerprints only as domain-separated digests, and request `worker_id` remains a deprecated compatibility input that is ignored for ownership and output.
7. Added `GET /api/v1/operations`, `GET /api/v1/operations/{id}`, per-operation events, `POST .../{id}/cancel` and global `GET /api/v1/operations/events` SSE. Reconciliation triggers as non-blocking single-flight background work. A fresh ready frame carries the captured high-water as `initial_cursor`; reconnect keeps the supplied cursor until committed events replay. Invalid, future, pruned and signed-BIGINT-overflow cursors fail with fixed codes; polling, batches, keepalives and connection duration are bounded.
8. Upgraded the Jobs route to a durable task center with operation summary/detail, filters, progress, safe result/context display, subject links, event timeline, cancellation, EventSource updates and bounded fallback polling.
9. Added a 16 KiB aggregate-only support-bundle service and `GET /api/v1/support-bundle`. It returns canonical JSON with `no-store`, includes only fixed revision/readiness/count projections, performs a second output-byte leak scan, and maps database failure to a fixed safe code.
10. Preserved domain authority: Operation does not replace Job, SyncRun or LoginSession. Login, asset download, scheduler, pipeline and Emby export all check both the authoritative phase snapshot and local signal immediately before their non-interruptible domain handoff. Scheduler/pipeline stop before claiming another Job; an archive/export domain success still wins truthfully after the handoff.

## Final verification

- Persistence/migration/CLI focused gate: 141 passed.
- Coordinator and related domain regression gate: 207 passed.
- Operation payload/repository/coordinator/scheduler/pipeline/API integration gate: 241 passed, with one known Starlette/httpx deprecation warning.
- Support service and HTTP contract: 30 passed.
- Final operation repository/coordinator/API regression selection: 78 passed, with the one known Starlette/httpx deprecation warning.
- Frozen complete Python suite: `2315 passed, 3 skipped, 1 warning in 555.05s (0:09:15)`. The skips are the three Windows-inapplicable POSIX launcher/mode cases; the warning is the existing Starlette/httpx deprecation.
- Whole-repository Python gates: Ruff passed; Ruff format checked 662 files; strict mypy passed 94 source files; compileall passed; `uv build` produced the sdist and wheel.
- Web: Prettier passed; 17 Vitest tests passed; Svelte/TypeScript reported 0 errors and 0 warnings; the adapter-static production build passed.
- Repository: both locked upstream checkouts passed; the tracked generated/local-state audit passed for 733 files; `scripts/check_docs.py` passed for 466 Markdown files; `git diff --check` and the local absolute-path scan passed.

The focused selections overlap and are not summed. A pre-freeze diagnostic run reached 2308 passes, 3 skips and two 15-second Windows child-process timeouts; both timed-out tests immediately passed alone in 3.24 seconds. Because the API changed during that run, it is recorded only as diagnosis. The result above is the later frozen, authoritative run after every fix.

## Publication handoff

- Commit the API/SSE/support HTTP integration and this bilingual closeout without staging `.mimosa/` or any generated/local-state output.
- Push `main`, then prove local `HEAD`, `origin/main` and GitHub `refs/heads/main` resolve to the same SHA. The containing closeout commit is intentionally not self-addressed by SHA.
- Add real browser route-interaction/E2E coverage for the task-center page in a later quality slice. Current 17 Web tests cover operation utilities/state/reconnect/fallback, not actual route interaction.

## Deferred scope and external gates

Generic file logs, a separate log browser, a ZIP or broad host/config/process support archive, one universal supervisor-to-Operation feed, backend retry, and subscription pause/resume/deletion audit were not delivered. Pause/resume/deletion remain behind Execution 0055's authentication and retention design.

Execution 0047 remains P0. Linux persistence/backup/process evidence, Bilibili/XHS canaries, the other live platforms and real Emby/Jellyfin rescan/playback remain `NOT_RUN`; no 0052 offline result substitutes for those operator checks.
