**English** | [中文](goal.zh.md)

# Execution 0052 goal

- Status: Delivered and verified locally; the closeout commit and GitHub reconciliation follow this record
- Date: 2026-09-04
- Predecessor: `d64b97b` (Execution 0051 closeout)
- Scope: durable operations, event streaming, cooperative cancellation and task-center observability
- Database migration: Implemented — revision `0006_operations_observability`
- Closeout commit: the commit containing this record (self SHA not embedded)

## Outcome

1. Replace the process-local `_OperationRegistry` with durable `Operation`, append-only `OperationEvent`, bounded operation-subject links and a transactional stream clock. Preserve the five asynchronous workflows—account login, asset download, scheduler worker, pipeline worker and Emby export—while making their control-plane history survive API restarts.
2. Enforce one closed operation state machine, lease-token fencing, atomic active-scope exclusion and hashed request idempotency across SQLite writers and API processes. Expired work must converge to `interrupted` or to an unambiguous linked durable-domain result; no operation may remain permanently running.
3. Publish bounded operation list/detail/event APIs and a same-origin SSE stream. A fresh stream publishes a ready/high-water fact; `Last-Event-ID` reconnect replays strictly after the transactionally committed global cursor, with fixed handling for malformed, future and pruned cursors.
4. Provide cooperative, two-stage cancellation. A request records cancellation intent first; the current fenced owner observes it and reaches a truthful terminal result at a safe boundary. Login receives its cancellation signal, scheduler/pipeline workers stop between Jobs, and non-interruptible archive/export work may still finish successfully.
5. Turn the Jobs route into a persistent task center with kind/state/text filtering, progress, safe result summaries, subject links, an event timeline, cancellation controls, SSE reconnect and bounded polling fallback.
6. Treat operation events as the structured safe diagnostic surface. Persist only closed event codes and allowlisted scalar context, and expose a narrow, aggregate-only JSON support bundle with schema/readiness/entity counts and recent fixed error-code counts after a mandatory second leak scan.

## Acceptance boundaries

- Migration `0006` upgrades from `0005`, creates only `operations`, `operation_events`, `operation_subjects` and `operation_event_stream_state`, round-trips on SQLite, remains metadata-aligned and is present and executable in the built wheel.
- At most one active operation owns a generated exclusive scope. Repeating a request with the same valid `Idempotency-Key` and fingerprint returns the same durable identity; reuse for another request fails closed. Only a SHA-256 key digest and canonical request fingerprint persist.
- State, timestamps, lease ownership, cancellation and terminal transitions are compare-and-set constrained. Terminal rows are immutable, and stale lease tokens cannot append events, links or terminal results for a newer owner.
- Every accepted lifecycle change appends an event with a unique per-operation sequence and a transactionally allocated global `stream_sequence`. The singleton counter preserves commit order rather than relying on a database sequence or wall-clock time.
- Public operation JSON, SSE and the task center never expose `requested_by`, revision, request fingerprint, raw idempotency keys or hashes, lease owner/token/expiry, caller-supplied worker IDs, exception text, QR material, secrets, signed URLs or local paths.
- Startup and bounded-read reconciliation preserve valid foreign leases, reconcile expired work conservatively and prefer linked Job/LoginSession truth only when it is unambiguous. Both triggers are non-blocking, single-flight background work; interrupted in-memory callables are not automatically resumed.
- Cancellation uses the repository's authoritative phase snapshot rather than a stale process-local phase. All five workflows check the safe boundary immediately before an interruptible-to-non-interruptible handoff, and cross-coordinator observers preserve the audited `requested` → `observed` → `cancelled` sequence.
- The final focused regression selection passes 78 tests with one known Starlette/httpx deprecation warning. The frozen complete suite passes `2315 passed, 3 skipped, 1 warning in 555.05s (0:09:15)`, and every repository quality/package/Web/upstream/output gate passes.
- No offline operation, event, API or browser test changes live platform or Emby/Jellyfin qualification. Those rows remain `NOT_RUN` under Execution 0047.

## Explicit limits

This execution persists API control-plane history, not executable Python callables and not every existing supervisor Job. The scheduler supervisor keeps its established Job/RunEvent truth; a universal broker or unified supervisor-to-Operation feed is not claimed. Generic file logging, a separate log-file browser, archive downloads, system/process inventory and configuration-key exports are not part of the support bundle.

Subscription pause/resume audit and destructive deletion remain deferred to Execution 0055's authenticated authority and retention design. Rich content recovery remains 0053, media-server control/qualification remains 0054, and final migration/release remains 0056. Real browser-route interaction/E2E coverage for the Jobs page is follow-up quality debt; current Web evidence covers typed state/reducer behavior, static checking and production compilation. Hard process termination, distributed brokers, Redis/Kafka, multi-host HA and an installed daemon remain out of scope.

The publication SHA does not exist while this self-referential closeout record is being edited. The root closeout will commit, push `main`, and then compare local `HEAD`, `origin/main` and GitHub `refs/heads/main`; this record does not invent that future SHA.
