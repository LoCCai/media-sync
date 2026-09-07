**English** | [中文](goal.zh.md)

# Goal: durable XHS creator notes delivery with source-backed cursors

Status: **PLANNED ONLY**. No 0076 application code, migration, deployment or live crawl has started.

Execution 0076 extends the durable subscription delivery delivered for Bilibili in 0074 to Xiaohongshu creator notes. It follows the mandated source-first posture: every pacing, end-detection, reconciliation and incremental rule below is derived from the pinned MediaCrawler's XHS behavior and the XHS web API shapes, not copied from the Bilibili implementation.

The upstream XHS creator flow (`media_platform/xhs/core.py`, `client.py`) defines the facts this execution builds on:

- Creator listing paginates with an opaque string `cursor` (empty string starts the feed) plus a boolean `has_more`; pages return a `notes` array. There is no numeric page and no total count.
- Each listed note carries its own short-lived `xsec_token`. Note detail requests (`get_note_by_id`) are gated by that token; a failed API detail can fall back to HTML rendering (`get_note_by_id_from_html`).
- Creator identity and the initial `xsec_token` come from the creator URL itself (`parse_creator_info_from_url`); the profile endpoint requires the same token.
- Access can fail with ban/restriction states (`IPBlockError`, `PlatformAccessError`) that are distinct from feed exhaustion.
- Upstream loops stop on `has_more=false`, an empty `notes` array, a banned-response break, or reaching `CRAWLER_MAX_NOTES_COUNT` — four different stop reasons that the durable layer must distinguish.

The intended operator result:

```text
/crawler/ native login
  -> adopt the saved XHS session into one Account
  -> add one creator-notes Subscription
  -> bounded, cursor-tracked history batches
  -> per-note token-gated detail fetch and verified delivery
  -> head reconciliation after a genuine source end
  -> token-refreshing incremental head checks for new notes
```

## Required behavior

1. **Exact subscription ownership.** Every continuation, Job, Run, receipt and publication stays bound to one Subscription, Account, author, `notes` scope and the locked creator `user_id` plus its URL-borne `xsec_token` fingerprint.
2. **Opaque-cursor progression.** The continuation cursor is stored and replayed verbatim. Nothing may parse, reorder, regenerate or "optimize" it. A unit processes at most one upstream page per bounded step and stops at the subscription's `max_items` for that unit.
3. **Truthful source-end evidence.** Only an observed `has_more=false` (or a page that both carries no notes and advances nothing) recorded together with the exact page evidence counts as a source-end candidate. Ban/restriction errors, empty-but-`has_more=true` pages and `CRAWLER_MAX_NOTES_COUNT` stops are recorded as their own stop reasons and never as source end.
4. **Token-gated delivery.** Note details are fetched with the `xsec_token` captured from the same list page that surfaced the note. Tokens are short-lived: an incremental cycle must re-list the head pages for fresh tokens before any detail fetch, and a token rejection invalidates only that detail fetch (retry via HTML fallback, then bounded re-list), never the durable cursor.
5. **Head reconciliation before incrementality.** After a genuine source end, one bounded head re-list must reproduce the recorded newest boundary before the subscription may enter incremental polling. Drift (new notes, reordered head, changed cursor shape) keeps delivered data but re-opens reconciliation; no `baseline_snapshot_complete`-equivalent is published on drift.
6. **Incremental operation.** Incremental cycles re-list bounded head pages with fresh tokens, deduplicate by stable `note_id`, and produce work only for unseen or changed notes. An unchanged cycle writes no bytes and no NFO rows.
7. **Content-unit visibility.** Note kinds (`normal`, `video`) publish per complete Content unit; a failed note never blocks unrelated notes, and partial results are reported honestly.
8. **Pause, deletion and recovery.** The paused-state editor from 0075 fences policy changes; auth expiry routes to the existing waiting-auth path; restart, lease loss and duplicate execution fence the same durable unit.

## Acceptance evidence

- A deterministic locked-runner fixture paginates at least three cursor steps, records each cursor, survives restart between steps and reaches a genuine `has_more=false` end.
- A ban-state response mid-history records its distinct stop reason and resumes without fabricating source end.
- After source end, head drift (one inserted note) re-opens reconciliation and later closes it; an unchanged head enters incremental mode.
- One new note is fetched once through its fresh token and published; an unchanged rerun is zero work.
- Final tree/NFO validation passes with no media server configured.
- Linux image, real XHS login and a live creator canary remain `NOT_RUN` until the operator runs them.

## Explicit non-goals

- XHS comments, search-feed subscriptions or any non-creator scope.
- Treating other platforms' pagination as XHS-shaped.
- Automated handling of bans beyond the existing pause/backoff policy.
- Any Emby/Jellyfin server control.
