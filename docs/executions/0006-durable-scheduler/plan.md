**English** | [中文](plan.zh.md)

# Execution 0006 plan

- Status: Frozen before implementation
- Execution result: Completed by this bilingual closeout commit
- Plan date: 2026-08-30
- Network policy: offline tests only

## Frozen design

### Durable identities

- Add `subscriptions.schedule_revision INTEGER NOT NULL DEFAULT 0 CHECK >= 0`.
- Add nullable `jobs.subscription_id`, `jobs.account_id`, `jobs.platform` and `jobs.scheduled_for`, plus claim/scope indexes and a partial unique index allowing only one active `sync.subscription` Job per subscription. Active is frozen as `queued`, `claimed`, `running`, `retry_wait`, `waiting_auth`, `waiting_user` or `failed_retryable`; terminal is only `succeeded`, `failed_terminal` or `cancelled`.
- Cycle natural key: `subscription:<subscription-id>:schedule:<revision>`.
- `enabled=true AND next_run_at IS NULL` means immediately due; disabled means paused. Materialization is limited and ordered by null-due first, due time, creation time and ID.
- Completion uses fixed delay: `next_run_at = finished_at + interval_seconds`. Success resets `consecutive_failures`; one terminal cycle failure increments it once. Downgrade removes scheduler lanes and all `sync.subscription` Jobs before dropping scheduler columns, so a re-upgrade cannot inherit a natural-key poison. Execution 0005 Job evidence expressible by `0003` remains field-for-field equal, including JSON storage type; this is not a physical SQLite-byte claim.

### Retry and lanes

- Freeze retry policy into each Job payload: schema v1, base 30 seconds, cap 1,800 seconds, maximum 5 attempts, equal jitter. A valid `Retry-After` is a lower bound.
- Add durable `scheduler_lanes` for platform and account scopes. Fields cover concurrency, start interval, failure threshold, cooldown, next start, consecutive failures, circuit state/open deadline, half-open Job and revision.
- Conservative defaults: platform concurrency 1, account concurrency 1, start interval 5 seconds, and a circuit that opens after 3 classified failures for 15 minutes.
- Claim must satisfy worker-global capacity and both lanes. It scans past blocked candidates to avoid head-of-line starvation. Half-open permits one exact Job.
- Risk/rate-limit/temporary upstream failures affect circuits; account lock contention does not. Authentication and interactive challenges enter explicit waiting states.

### Worker boundary

- Introduce a closed `sync.subscription` handler registry and short-transaction worker lifecycle: claim, start, heartbeat, finalize. Execution 0006 ships the deterministic Fake handler.
- Reclaim and requeue predicates are Job-type scoped before mutation. `asset_download` and `export.emby` continue to enqueue and exact-claim only inside their execution 0005 services.
- Fake handler reuses the application sync service. MediaCrawler remains on the execution 0004 manual CLI run/ingest path; its scheduler application handler, manifest v3 and child-process supervision are a separately documented later execution.
- Secret/credential values, untrusted real paths and raw handler errors never enter `sync.subscription` scheduler Job/lane payloads. Existing asset/export records may intentionally persist validated archive/output paths.

## Implementation sequence

1. Add retry/circuit pure policy types and exhaustive numeric/time tests.
2. Add migration `0004_scheduler_control_plane`, ORM models, source/wheel upgrade and downgrade preservation tests.
3. Fix generic Job reclaim/queue scoping, then add scheduler repositories for due materialization, lane policy/CAS, waiting resume and cycle finalization.
4. Add scheduler and worker application services with injected clock/RNG and handler protocol.
5. Deliver Fake handler and restart-safe offline cycle tests.
6. Add an offline acceptance harness that explicitly invokes existing execution 0005 download/export services after scheduled Fake sync; do not add a generic downstream planner or preclaim their Jobs.
7. Add redaction-safe CLI control surfaces and operations documentation.
8. Run concurrency, retry, circuit, migration, end-to-end and sentinel review; close every P0/P1 finding.
9. Run the exact final gates, update all four execution documents and create a bilingual local implementation commit. Never push.

## Required tests

- Concurrent due ticks with independent SQLite sessions; disabled/future/null due, run-now, pause/resume and no catch-up storm.
- Backoff boundaries, equal jitter, Retry-After, NaN/infinity, datetime overflow and max attempts.
- Global/platform/account concurrency, start intervals, queue scan fairness, open/cooldown/single-half-open/success-close/failure-reopen circuits.
- Expiry/ABA heartbeat and cancellation; sync reclaim proves zero mutation of expired download/export prepared-result or publication-intent Jobs.
- Waiting auth/user remains dormant until explicit resume.
- Fake handler lifecycle, retry/wait outcomes and no long I/O transaction.
- Offline restart E2E and byte-level secret sentinel across SQLite, Job/lane state, runtime output, archive and export.
- Empty database, real `0003` upgrade, downgrade, source package and unpacked-wheel migrations.
