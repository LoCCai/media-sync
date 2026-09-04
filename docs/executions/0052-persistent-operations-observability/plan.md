**English** | [中文](plan.zh.md)

# Execution 0052 plan

- Status: Delivery and local verification complete; publication reconciliation follows the closeout commit
- Plan date: 2026-09-04
- Baseline: `d64b97b`
- Database revision: `0006_operations_observability`
- Closeout commit: the commit containing this record (self SHA not embedded)

## Baseline decision

Execution 0051 removed account/subscription validation ambiguity but intentionally retained process-local Operations and polling. Execution 0052 therefore delivers the independently testable control-plane slice of durable operation ownership, safe observation and cooperative cancellation. Execution 0047 remains the P0 Linux/live gate; no offline work here converts an unexecuted operator row into a pass.

One scope correction is now frozen. Subscription pause/resume audit and destructive deletion require authenticated operator authority and a retention/cascade policy, so both remain behind Execution 0055. This execution records cancellation audit facts for the five API workflows only. It does not change the original seven-platform subscription and Emby/Jellyfin objective.

## Executed delivery sequence

1. Froze five operation kinds, seven states, twelve lifecycle event codes, fixed error codes and one v1 safe payload contract.
2. Added migration `0006` with `operations`, `operation_events`, bounded `operation_subjects` and singleton `operation_event_stream_state`. Active exclusive scopes and `(kind, idempotency_key_hash)` are unique where applicable; lifecycle, progress, target, lease, error and digest shapes are database-constrained.
3. Implemented atomic create-or-replay, claim/start, heartbeat, progress/event/link append, cancellation request, terminal completion, keyset pagination, stream bounds and expired-lease reconciliation. Lease tokens fence stale owners, while the global event cursor is allocated by updating the counter row inside the event transaction.
4. Added per-kind closed request identities, result summaries and event-context projectors. Unknown fields and unsafe values fail closed before persistence; raw request bodies, exceptions, references, URLs, paths, QR bytes and caller worker identities have no payload representation.
5. Added an `OperationCoordinator` that creates/replays and claims in one transaction, starts a callable only after commit, derives worker ownership server-side, heartbeats leases, observes cancellation and records subjects through transactional hooks. Authoritative reads take SQLite writer reservation with bounded fresh-transaction retries, and pending terminal intent is retried by the monitor. Concurrent observers wait for durable cancellation observation so the event history remains `requested` → `observed` → `cancelled`, including across coordinator instances.
6. Replaced API process-local operation wiring for account login, asset download, scheduler run, pipeline run and Emby export. All five POST routes accept a strictly validated `Idempotency-Key`; private references contribute only a domain-separated digest to the request fingerprint; request `worker_id` is ignored for durable ownership and never serialized.
7. Added bounded list/detail/per-operation-event APIs, two-stage cancel, and global SSE. The ready frame always uses `event_id=initial_cursor`: a fresh connection captures the current high-water, while a reconnect retains the supplied cursor so replay cannot skip events committed between sessions. Reconnects strictly replay committed events after that cursor, reject invalid/future cursors and return fixed `410 operation_event_cursor_expired` for pruned history.
8. Added conservative startup and bounded-read reconciliation as non-blocking, single-flight background work. Valid foreign leases remain untouched; expired operations converge from unambiguous Job/LoginSession evidence or to `interrupted`; failures release the single-flight slot for retry, shutdown prevents new triggers, and no in-memory callable is automatically resumed.
9. Upgraded the Jobs route into a task center with a 200-item bounded snapshot, kind/state/text filters, detail and event timeline, progress, subject links, derived actions, cancel control, EventSource updates, sequence de-duplication and bounded polling fallback.
10. Added `GET /api/v1/support-bundle` as a canonical JSON response with `application/json` and `Cache-Control: no-store`. Its fixed, aggregate-only shape contains project/build/schema readiness, entity counts, operation state/kind counts and bounded recent fixed error-code counts; it is capped at 16 KiB and scanned again before output. Database failure returns only `support_bundle_database_failed`.
11. Hardened cancellation at the domain handoff. The coordinator refreshes the authoritative phase snapshot, and all five workflows recheck both persisted `cancel_requested_at` and the local cancellation context immediately before entering a non-interruptible domain call. Once that call starts, a durable domain success truthfully wins over a later cancellation request.
12. Completed the final focused, frozen complete-suite, static/package, Web, upstream and tracked-output audits. Update the bilingual execution/global records, then commit with bilingual subject/body, push `main`, and reconcile local, `origin/main` and GitHub SHAs without embedding a nonexistent self SHA.

## Frozen contract corrections

- Persist only the validated `Idempotency-Key` SHA-256 digest plus a canonical request fingerprint. Never persist or return the raw key.
- `requested_by` is a fixed internal provenance label, not caller-controlled request data, and is absent from public API/SSE/Web payloads.
- Lease owner, token and expiry plus repository revision and fingerprints are private fencing state. The Web task center displays phase/progress/subjects and derived `allowed_actions`, never lease controls.
- Operation events are the 0052 structured diagnostic surface. Generic application file logs, exception-text logging, log-file selection/tailing/download and a separate Logs page are not implemented or claimed.
- The support bundle is a small JSON aggregate, not a ZIP and not a broad host/config/process/event export.
- Existing scheduler/supervisor Jobs remain distinct durable truth. Execution 0052 does not claim one universal supervisor, broker or operation stream for every non-API task.
- Subscription pause/resume audit and deletion remain deferred to 0055. A backend retry endpoint is also not delivered; `retryable` is informative and current `allowed_actions` exposes only safe cancellation for eligible active operations.

## Verification and closeout result

- The final focused operation/API regression selection passed 78 tests with one known Starlette/httpx deprecation warning. Earlier implementation selections (141 persistence/migration/CLI, 207 coordinator/domain, 241 integration and 30 support tests) overlap and are retained only as development checkpoints; they are never added together.
- The frozen complete suite passed `2315 passed, 3 skipped, 1 warning in 555.05s (0:09:15)`. The three skips are Windows-inapplicable POSIX virtual-environment/permission cases; the warning is the same existing Starlette/httpx deprecation.
- Whole-repository Ruff passed; Ruff format covered 662 files; strict mypy passed for 94 source files; compileall passed; `uv build` produced the sdist and wheel.
- Web Prettier passed; Vitest passed 17 tests; Svelte/TypeScript reported 0 errors and 0 warnings; the adapter-static production build passed. Current Web tests exercise typed operation state/reducer/reconnect/fallback behavior, not real browser route interaction; route-level interaction/E2E remains follow-up quality debt.
- Both pinned upstreams verified locked and clean. The tracked generated/local-output audit passed across 733 files; documentation and `git diff --check` pass. `.mimosa/`, `.upstream`, databases, XML reports, `node_modules`, `web/build`, `.svelte-kit` and `dist` remain excluded from the commit.
- Evidence policy: keep Linux persistence/process/backup checks, all live platform rows and real Emby/Jellyfin rescan/playback `NOT_RUN` under Execution 0047 unless operator evidence is actually produced.

## Commit policy

The implementation is intentionally split into bilingual commits for Web state foundations, safe payloads, cancellation boundaries, the task center, migration/repository, the support bundle and the coordinator. API/SSE integration and this closeout are committed separately with bilingual subject/body. Never stage generated or local-state paths listed above.
