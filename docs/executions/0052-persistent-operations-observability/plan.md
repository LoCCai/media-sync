**English** | [中文](plan.zh.md)

# Execution 0052 plan

- Status: Active
- Plan date: 2026-09-04
- Baseline: `d64b97b`
- Planned database revision: `0006_operations_observability`
- Plan commit: the commit containing this record (self SHA not embedded)

## Baseline decision

Execution 0051 removed account/subscription validation ambiguity but intentionally retained process-local Operations and polling. The next independently deliverable control-plane slice is durable operation ownership and observation. Execution 0047 remains the P0 Linux/live gate; 0052 proceeds in parallel without converting any unexecuted operator row into a pass.

One correction is explicit: the 0051 closeout grouped subscription deletion with 0052. Hard deletion needs authenticated operator authority and a retention/cascade policy, so 0052 records pause/resume and operation audit facts but leaves destructive deletion to 0055. This narrows authority and does not change the original seven-platform subscription/Emby objective.

## Delivery sequence

1. Record a clean baseline, inventory the five process-local operation workflows, freeze safe operation kinds/error codes/event codes and define one versioned public payload.
2. Add migration `0006` with `operations`, `operation_events`, bounded `operation_subjects` links and a singleton `operation_event_stream_state` counter. Store a canonical request fingerprint beside each optional idempotency-key hash so a reused key cannot authorize a different request. Allocate `stream_sequence` by locking and updating the counter row in the event transaction, because PostgreSQL sequence values do not imply commit order. Add partial unique indexes for active exclusive scopes and `(kind, idempotency_key_hash)`, plus constraints for states, timestamps, progress, subject shape and lease shape.
3. Add typed persistence/application services for atomic create-or-replay, claim/start, heartbeat, progress, event append, cancellation request, success/failure/cancel completion, list/detail pagination and expired-lease reconciliation. All mutations use expected state/revision and lease-token fencing.
4. Add closed result-summary and event-context projectors per operation kind. Unknown keys or unsafe values fail closed before persistence; redaction is defense in depth rather than the primary boundary.
5. Replace `_OperationRegistry` in the API. Support `Idempotency-Key` on the five asynchronous POST routes, return replay/conflict facts without exposing internal keys, heartbeat owners in the background, and keep domain Job/LoginSession state authoritative. Generate Job worker-owner values from the Operation UUID; retain request `worker_id` only as a deprecated compatibility input and never use it as durable ownership or log context.
6. Add `GET /api/v1/operations`, exact detail and paginated event routes, `POST /api/v1/operations/{id}/cancel`, and `GET /api/v1/operations/events` SSE. On a fresh connection publish ready/high-water and let the client load a bounded snapshot; on reconnect catch up strictly after the global cursor before tailing. Bound batches, keepalives, connection lifetime and input sizes, and poll the database so events from other API processes are visible.
7. Wire cooperative cancellation: direct signal for account login, stop-before-next-item for bounded scheduler/pipeline workers, and safe-boundary observation for asset/Emby work. Resolve finish-versus-cancel races from durable domain truth rather than arrival order.
8. Reconcile expired operations at app startup and on bounded reads. Preserve valid foreign leases, derive terminal state from linked Job/LoginSession evidence where unambiguous, otherwise record `interrupted`; never auto-resume an in-memory callable.
9. Upgrade the Jobs route into the task center, add typed event-stream support, filters/detail timeline/progress/allowed actions/cancel controls and a bounded polling fallback when SSE is unavailable.
10. Add a safe support-bundle endpoint or command backed by allowlisted project/build/schema/readiness/count/recent-code projections and a mandatory second-pass forbidden-value scan before bytes are returned.
11. Run focused concurrency/state/migration/SSE/API/Web/security tests, then Ruff/format/strict mypy/compileall/build, documentation/upstream/repository audits and the complete Python suite. Record Linux/live/media-server rows as `NOT_RUN` unless real operator evidence is supplied.
12. Update bilingual progress, verification, status, roadmap and execution index records; commit implementation and closeout with bilingual subject/body, push `main`, and reconcile local and GitHub SHAs.

## Design constraints

- Operation, Job, SyncRun and LoginSession remain distinct truths. An Operation is an operator request; bounded `operation_subjects` and event subjects may link multiple durable identities without pretending that one Job represents a whole bounded worker invocation or hiding links in result JSON.
- Store only the SHA-256 digest of a validated `Idempotency-Key`, plus a canonical request fingerprint that proves a replay is the same method, route, target and normalized body without retaining the body itself. Exclusive keys are server-generated from a closed kind/UUID mapping and never accepted from request bodies.
- `retryable` and `allowed_actions` are derived from state and fixed error classifications, not independent writable truths.
- A cancellation request is not a terminal transition. Only the current fenced owner or restart reconciler can publish the final state after the work reaches a safe boundary.
- The SSE cursor is the transactionally allocated global `stream_sequence`; operation-local sequence and any row identity remain separate invariants. Neither an autoincrement/sequence primary key nor wall-clock time is accepted as a reconnect cursor.
- Event/result JSON is small, shallow and allowlisted. No generic dictionary, request body or exception string crosses the persistence boundary.
- SQLite remains the default single-host database. PostgreSQL-compatible DDL is retained, but multi-host HA and external message brokers are not claimed.

## Verification plan

- Persistence: metadata/DDL parity, migration upgrade/downgrade/wheel, constraints/indexes/FKs, global cursor commit-order monotonicity under concurrent writers and 10,000-event keyset pagination.
- Concurrency: SQLite multi-connection active exclusivity, idempotency replay/conflict, event sequence allocation, cancel-versus-finish and lease-token ABA/fencing.
- Recovery: live foreign lease preservation, expired operation convergence and Job/LoginSession-authoritative terminal mapping.
- API/SSE: five workflow compatibility paths, list/detail/filter pagination, exact cancel semantics, catch-up/tail/reconnect/keepalive/disconnect and fixed invalid-cursor errors.
- Security: sentinel scans for credentials, signed queries, QR bytes, exception text, paths, owner IDs, lease tokens and raw idempotency keys across database, JSON, SSE, UI and support-bundle bytes.
- Frontend: type check, state reducers, SSE reconnect plus polling fallback, filters, timeline, progress and action gates.

## Commit policy

Commit this bilingual goal/plan/baseline before implementation. Prefer separate bilingual commits for migration/repository, API/runtime, Web task center and final documentation. Never stage `.mimosa/`, `.upstream`, local databases, support-bundle fixtures containing sentinels, JUnit XML, `node_modules`, `web/build`, `.svelte-kit` or distribution output.
