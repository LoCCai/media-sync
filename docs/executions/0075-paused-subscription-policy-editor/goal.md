[**Chinese**](goal.zh.md) | **English**

# Goal: paused subscription policy editor

Status: **implemented locally in `aec3eac`**. No deployment or live-platform action was part of this execution.

Execution 0075 adds the operator-facing policy edit that follows the durable Bilibili delivery work in 0074. An existing MediaCrawler subscription can be paused, edited, reviewed, and resumed without deleting its checkpoints, delivery evidence, content, archive bytes, or published library tree.

## Required behavior

1. Editing is allowed only for an active, paused, idle MediaCrawler subscription. A pending Job, non-terminal SyncRun, or active subscription operation rejects the edit.
2. Every edit carries the exact current `expected_schedule_revision`. A stale request changes nothing. A real change increments the revision exactly once; an exact no-op does not.
3. The editable set is closed to polling interval, per-run item cap, upstream request delay, browser headless mode, and Bilibili capture scope. The existing full-history acknowledgement and opaque creator secret reference are preserved and never returned.
4. Bilibili `dynamics` and `both` continue to require at least two items. Non-Bilibili subscriptions cannot receive a Bilibili scope.
5. Cursor, backfill cursor, checkpoint revision, watermarks, scan evidence, Bilibili delivery evidence, retry counters, `next_run_at`, historical rows, archive bytes, and library files are not rewritten by the edit transaction. Delivery-relevant Bilibili changes are re-qualified by the existing binding logic on the next run.
6. REST, CLI, and Web use the same application service and fixed safe error codes. Responses contain only an allowlisted policy summary and stable counters; no credential, locator, upstream response, or host path is exposed.
7. The Web detail view initializes from a freshly read subscription revision, remains disabled while enabled or removed, validates the returned identity and revision, and never automatically resumes or retries a rejected mutation.

## Acceptance evidence

- SQLite and PostgreSQL-compatible transaction tests cover paused/enabled/removed, stale revision, exact no-op, concurrent writers, active Job/Run/operation fences, invalid current policy, and secret/checkpoint preservation.
- API and CLI tests prove the closed request/response vocabulary and redaction behavior.
- Web tests cover payload/response validation, fixed failure copy, stale request cancellation, platform-specific scope rules, and source wiring.
- A rendered browser flow proves: subscription detail -> paused policy editor -> save -> updated policy remains paused, with no relevant console error.
- Targeted and full Python/Web gates, formatting, type checks, builds, documentation links, upstream locks, and package builds are recorded in the execution evidence.

## Explicitly out of scope

- Editing credentials, creator identity, local alias, full-history acknowledgement, output roots, retry policy, or scheduler lane policy.
- Cancelling work, resuming a subscription, starting a run, downloading, exporting, or contacting a media server as a side effect of editing.
- Adding durable pagination semantics for another platform. That audit starts after this editor is complete, beginning with XHS without copying Bilibili cursor assumptions.
- Docker/Linux deployment or any live account, platform, CDN, host-library, or supervisor qualification.
