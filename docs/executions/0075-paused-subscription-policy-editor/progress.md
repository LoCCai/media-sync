**English** | [中文](progress.zh.md)

# Progress: paused subscriptions now have one revision-fenced policy editor

Status: the local implementation is complete in `aec3eac`. Docker/Linux deployment, real PostgreSQL races and live-platform qualification remain pending.

## Outcome

An existing MediaCrawler subscription can now be changed through one closed workflow:

```text
fresh subscription detail
  -> active + paused + idle check
  -> exact schedule-revision comparison
  -> one atomic policy update
  -> subscription remains paused with checkpoints, history and media preserved
```

All seven MediaCrawler platform subscriptions receive the same generic interval, item-cap, request-delay and browser-mode controls. Bilibili alone receives the fifth capture-scope control; XHS, Douyin, Kuaishou, Weibo, Tieba and Zhihu cannot receive that field. This is policy editing only and does not claim durable pagination or live incrementality for those platforms.

## Implemented

1. **One transaction owner.** The application service reserves the SQLite writer or locks the exact PostgreSQL subscription row, then rechecks active Jobs, non-terminal Runs and active operations before changing state.
2. **Closed atomic mutation.** Polling interval, per-run cap, upstream delay, headless mode and optional Bilibili scope change as one unit under `expected_schedule_revision`. A real change increments once; an exact no-op consumes no revision.
3. **Exact preservation.** Full-history acknowledgement and the opaque creator reference survive byte-for-byte in the closed policy. Cursor, backfill cursor, checkpoint, watermark, timing, failure and `next_run_at` fields are not rewritten. Existing scan/delivery/history/media authority is left in place; delivery-relevant Bilibili changes are re-qualified only when a later cycle materializes.
4. **Shared control surfaces.** `PUT /api/v1/subscriptions/{id}/policy`, `media-sync subscription policy` and the Web editor all call the same service. Requests reject extra fields; responses and errors use fixed allowlists without secret references, locators, upstream bodies or host paths.
5. **General paused-state editor.** The old Bilibili-only scope card is replaced by a structured policy editor. Enabled, removed, malformed and busy states explain why saving is unavailable. Success keeps the subscription paused and states that no crawl, download or export was started.
6. **Stale-response fences.** The browser request is bound to subscription identity, platform, exact revision, operator-session epoch, modal lifetime and a single in-flight generation. Saving cannot close the modal, and a cancelled or late response cannot become success.
7. **Operator feedback.** Invalid intervals and field ranges have explicit prompts; fixed failures can lead to the Jobs page, refreshed detail or deleted-subscription view without replaying a mutation.

## Review corrections

- The REST delay field now rejects string coercion and accepts only a strict JSON number.
- Direct application calls with an unhashable or foreign Bilibili scope now return the fixed options error instead of risking an internal `TypeError`.
- A final Ruff format pass removed one extra blank line in a test; no behavior changed.

## Remaining

- Pull and rebuild the published revision on the Linux host before using the editor there.
- Run the two optional real PostgreSQL policy race/NOWAIT checks with `MEDIA_SYNC_TEST_POSTGRESQL_URL`.
- Qualify real account, platform, CDN, archive/library/NFO and supervisor behavior separately; all remain `NOT_RUN`.
- Start the next source-backed design with XHS creator notes: bounded cursor progression, source-end evidence, reconciliation and delivery-qualified incrementality must be specified from XHS behavior rather than copied from Bilibili.
