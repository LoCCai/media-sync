**English** | [中文](plan.zh.md)

# Plan

Status: **FROZEN FOR A LATER TURN**. This document authorizes no deployment, platform request or supervisor restart by itself.

## 1. Reconfirm and simplify the existing path

- Trace the current Bilibili uploads state from adopted Account profile through `BiliMultiFeedState`, `subscription_scan_progress`, scheduler completion, `pipeline.subscription`, asset download, archive and library publication.
- Reuse the existing stable IDs, locks, Jobs, Runs, receipts, retry policy and output settings. Remove or adapt redundant state only when tests prove it is safe; do not build a parallel coordinator.
- Record the exact pinned MediaCrawler SHA and the existing per-unit HTTP/detail limits in the execution verification.

## 2. Add a durable baseline state machine

- Define closed phases for initial backfill, head reconciliation, incremental polling and blocked/restart-required state.
- Bind state to Subscription, Account/auth revision, author, Bilibili `uploads` scope, policy generation and upstream identity.
- Extend the existing progress table or add the smallest migration only after confirming the present schema cannot represent these invariants. Upgrade and downgrade rules must preserve existing deployments; no inferred history-complete backfill.
- Store only bounded counters, cursor/boundary identities and timestamps. Do not store raw responses, signed locators or Cookies.

## 3. Chain bounded discovery to verified delivery

- Continue at most one exact historical unit after the prior unit's discovery and pipeline receipt are durably consistent.
- Respect `min(max_items, 30)`, existing request limits, configured continuation delay, subscription interval, pause/removal and auth/backoff state.
- Make API exact execution and resident supervisor compete through the same durable ownership fence. Duplicate submissions return/reuse the authoritative unit rather than creating another chain.
- Do not mark a batch delivered merely because the crawler process or sync Job exited successfully; require exact content/download/publication evidence.

## 4. Reconcile before switching to incremental

- When the history lane proves source end, save the boundary and schedule a bounded head reconciliation.
- If head identities or pagination generation drift, retain the data already delivered but invalidate completion and repeat the bounded reconciliation path.
- Publish `baseline_snapshot_complete` only after stable reconciliation. Periodic cycles then poll the head with a documented overlap window and stable-ID deduplication.
- Invalidate the baseline on identity/auth/scope/upstream-policy changes; never silently translate incompatible cursors.

## 5. Publish per complete Content unit

- Group selected Assets by Content and preserve required component integrity. Multi-part video/gallery publication remains atomic within its Content.
- Allow independent complete Contents to finalize and publish even if a different Content fails or is unsupported.
- Keep failed work retryable with exact safe counts and error codes. The operation may be `partial`/failed while retaining already verified publications; it must never label missing media as complete.
- Prove restart and zero-work replay preserve content-addressed bytes and deterministic NFO output.

## 6. Expose a small operator surface

- Add subscription-detail fields for phase, completed/remaining batch evidence, last reconciliation, next eligible continuation and partial Content failures.
- Reuse Jobs and the rolling log center for exact drill-down. Do not add a second dashboard or raw dependency log stream.
- Explain that “baseline complete” is a reconciled snapshot, not a permanent full-history guarantee, and that Emby/Jellyfin connection is optional.

## 7. Verification sequence

1. Unit-test state validation, invalidation, pacing and closed public projection.
2. Integration-test 65+ uploads across three or more batches, deterministic restart barriers, source-end/head drift and transition to incremental.
3. Exercise one-new-upload and zero-work reruns through real download/archive/NFO code using controlled fixtures.
4. Exercise one bad old Content beside two valid Contents, including multipart all-or-nothing behavior.
5. Exercise pause, removal, auth expiry/adoption recovery, lease loss, duplicate API/supervisor ownership and migration round trips.
6. Run focused tests, complete Python/Web suites, Ruff, strict mypy, Prettier/Svelte/build, documentation/upstream checks, package build and `git diff --check`; record exact results in bilingual progress/verification files.
7. Only after publication and operator approval, deploy the exact revision and run UID `252671524` as a bounded Bilibili canary. Record image SHA, Account/session adoption, content/media counts, final host directory/NFO and a later incremental cycle. Keep every unobserved item `NOT_RUN`.

## After 0074

Implement paused-state subscription policy editing with `expected_schedule_revision` CAS so operators can safely change interval, `max_items`, request delay, headless mode and Bilibili scope without deleting history. Then audit each of the other six platforms for its own bounded pagination, source-end and incremental evidence rather than copying Bilibili assumptions.
