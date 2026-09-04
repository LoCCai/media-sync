**English** | [中文](goal.zh.md)

# Execution 0052 goal

- Status: Planned; implementation not started
- Date: 2026-09-04
- Predecessor: `d64b97b` (Execution 0051 closeout)
- Scope: durable operations, event streaming, cooperative cancellation and task-center observability
- Database migration: Planned — revision `0006_operations_observability`
- Plan commit: the commit containing this record (self SHA not embedded)

## Outcome

1. Replace the process-local `_OperationRegistry` with durable `Operation`, append-only `OperationEvent` and bounded operation-subject links. Preserve the five existing asynchronous workflows—account login, asset download, scheduler worker, pipeline worker and Emby export—while making their history survive API restarts.
2. Enforce one closed operation state machine, lease-token fencing, atomic active-scope exclusion and hashed request idempotency across SQLite writers and API processes. A stale owner must converge to `interrupted` or to the linked durable domain result; no operation may remain permanently running.
3. Publish bounded operation list/detail/event APIs and a same-origin SSE stream whose global monotonic event cursor supports `Last-Event-ID` catch-up without gaps or duplicate authority.
4. Add a generic cancellation request endpoint. Cancellation is cooperative and truthful: login receives its existing cancellation signal, bounded workers stop at safe job boundaries, and non-interruptible archive/export critical sections may finish successfully rather than being falsely reported as cancelled.
5. Turn the Jobs route into a persistent task center with operation filtering, progress, allowed actions, event timeline, SSE reconnect and a bounded polling fallback.
6. Treat operation events as structured safe logs. Persist only closed event codes and allowlisted scalar context, and provide a first redaction-scanned support bundle containing diagnostics and counts but no request bodies, exception text, secrets, signed URLs, QR data, lease tokens or local paths.

## Acceptance boundaries

- Migration `0006` upgrades from `0005`, creates only operations, events, bounded subject links and the singleton stream-sequence allocator, round-trips on SQLite, remains metadata-aligned and is present and executable in the built wheel.
- At most one active operation owns a generated exclusive scope. Repeating a request with the same valid `Idempotency-Key` returns the same durable identity, while a different request cannot borrow that identity.
- State, timestamps, lease ownership, cancellation and terminal transitions are enforced by compare-and-set rules. Terminal rows are immutable and stale lease tokens cannot append events or complete a newer owner's operation.
- Every accepted state transition appends an event with a unique per-operation sequence and a globally ordered `stream_sequence` in the same transaction. The stream cursor is allocated through one transactional counter row so PostgreSQL sequence allocation cannot reorder commits and make SSE skip a late event.
- The first SSE connection publishes a ready/high-water fact and relies on the bounded snapshot API; reconnect catch-up is ordered and bounded, honors `Last-Event-ID`, detects malformed or unavailable cursors with fixed safe codes, and never serializes private runtime state.
- A restart/reconciliation test proves valid foreign leases remain untouched, expired ownerless work converges, and linked Job/LoginSession truth wins where it is sufficient.
- API and Web tests cover all five existing operation kinds, cancellation races, multiple writers, 10,000-event pagination, reconnect/fallback behavior and secret/path/query/QR sentinels.
- No offline operation, event or browser test changes live platform or Emby/Jellyfin qualification; those rows remain `NOT_RUN` under Execution 0047.

## Explicit limits

This execution persists control-plane history, not executable Python callables: work interrupted by process death is reconciled, not automatically resumed unless an existing durable Job owns recovery. Hard process termination, distributed brokers, Redis/Kafka, multi-host HA and an installed daemon remain out of scope. Full operator authentication and destructive subscription deletion stay behind Execution 0055's authorization and retention design. Rich content recovery remains 0053, media-server control/qualification remains 0054, and final migration/release remains 0056.
