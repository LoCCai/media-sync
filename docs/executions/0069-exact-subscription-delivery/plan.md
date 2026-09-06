**English** | [中文](plan.zh.md)

# Plan

## 1. Freeze authoritative scope

- Treat `run-now` as schedule control only and retain its compatibility route with clearer UI wording.
- Add a separate exact-delivery route and Operation kind. Use one per-subscription exclusive key and a closed request identity containing expected schedule revision, MediaCrawler enable/license flags and bounded lease parameters.
- Keep the current downstream selection explicit as `author_active_snapshot`; do not claim it is limited to newly discovered rows.

## 2. Database and durable contracts

- Add migration `0013_exact_subscription_delivery` to replace the database Operation-kind check with the new closed set and create a unique `(subscription_id, feed)` scan-progress table.
- Preserve all operation rows/events/subjects during SQLite batch recreation and PostgreSQL constraint replacement. Make downgrade refuse when new-kind operations or scan-progress history exists.
- Add closed payload/result schemas, target mapping, routes, summaries, diagnostics and support-bundle counts for `subscription-delivery`.

## 3. Exact scheduler and pipeline ownership

- Refactor the current materialization and claiming predicates into shared helpers, then add exact-ID variants with the same lease, capacity, lane and reconciliation rules.
- Materialize one enabled, non-deleted subscription without changing its periodic schedule semantics. Return or conflict with a pre-existing current cycle rather than enqueueing duplicates.
- Add exact worker entry points that reuse current start, heartbeat, handler and finalize implementations.
- Resolve the pipeline coordinator only from the exact succeeded sync Job and attached succeeded Run, then claim that exact Job without scanning another queue row.

## 4. Typed execution receipt

- Add an application orchestrator that advances phase-by-phase and links durable subjects as soon as their identities exist.
- Preserve a sanitized pipeline receipt through the handler/worker boundary instead of discarding `SubscriptionPipelineOutcome`.
- Re-read the exact Job/Run/export state before success. Return fixed error codes for busy, drift, discovery failure, missing coordinator, pipeline failure and directory verification failure.
- Name discovery semantics by adapter; keep unsupported updated-row counts nullable. Report archive dispositions and managed files without calling them network downloads or content counts.

## 5. Scan-progress evidence

- Integrate Bilibili upload/dynamic coverage updates into the same transaction that commits ingestion, checkpoint CAS and Run success.
- Persist only fixed feed/state/stop-reason values, bounded counters, upstream/contract generation and exact source-end Run identity. Never persist opaque source cursors in the new table or expose them through API/UI.
- Add the progress projection to subscription detail. All non-Bilibili feeds remain `unproven` in this execution.

## 6. API and web workflow

- Add the exact execute request/response, 202 Operation tracking and fixed conflict responses.
- Add the explicit confirmation and stage display to the subscription workbench; link to the exact Operation, Jobs and log filters.
- Preserve response-generation/abort guards so stale requests cannot replace the selected subscription state.

## 7. Windows directory pin

- Replace zero desired access with a named `FILE_LIST_DIRECTORY = 0x0001` constant only in the exporter directory opener. Keep `FILE_SHARE_READ | FILE_SHARE_WRITE`, omit `FILE_SHARE_DELETE`, and retain reparse/open-directory flags.
- Add a real Windows ancestor-rename regression plus non-Windows/static contract coverage.

## 8. Verification and publication

- Run focused tests after each layer, then Python unit/integration/contract suites, web tests/typecheck/lint/build, API-to-TypeScript contract, packaged migration/source consistency and secret/path scans.
- Record exact commands, counts, skips, failures and repairs in `verification(.zh).md`; update progress, status, roadmap and deployment notes.
- Commit implementation and closeout separately with bilingual messages and push `main`. Do not deploy, restart supervisor, initiate live login or start production download automatically.

