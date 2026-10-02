**English** | [中文](goal.zh.md)

# Goal: durable Douyin creator-work delivery with source-backed cursors

Status: **PLANNED ONLY**. No 0078 application code, migration, deployment or live crawl has started.

Execution 0078 extends the durable subscription delivery delivered for Bilibili (0074) and Xiaohongshu creator notes (0076) to Douyin creator works. It follows the mandated source-first posture: every pacing, end-detection, reconciliation and incremental rule below is derived from the pinned MediaCrawler's Douyin code and response shapes, not copied from the Bilibili or XHS implementations.

The upstream Douyin creator flow (`media_platform/douyin/core.py`, `client.py`, `exception.py`) defines the facts this execution builds on:

- Creator works paginate on `/aweme/v1/web/aweme/post/` with `sec_user_id`, a fixed `count: 18`, and a server-echoed `max_cursor` string that starts empty and must be replayed verbatim. There is no numeric page and no total count.
- The stop signal is the integer `has_more`: the upstream loop continues only while `has_more == 1`. A response whose `has_more` is not `1` is the only genuine source-end candidate.
- An empty `aweme_list` with `has_more == 1` keeps the upstream loop alive while making no progress; the durable layer must record that as its own stall reason instead of looping or claiming an end.
- Every request carries an `a_bogus` signature produced per request through the pinned `douyin.js` on the Playwright page; the client raises `DataFetchError` on unparseable bodies and treats an empty or literal `"blocked"` body as `account blocked`. `IPBlockError` marks rate limiting. These are access restrictions, never source ends.
- Work identity is `aweme_id`; creator identity is `sec_user_id` parsed from the protected creator URL. Media branches on the detail payload: `_extract_note_image_list` non-empty means a gallery (per-image `NNN.jpeg`), otherwise `_extract_video_download_url` names one video (`video.mp4`).

The intended operator result:

```text
/crawler/ native login
  -> adopt the saved Douyin session into one Account
  -> add one creator-work Subscription
  -> bounded, max_cursor-tracked history batches
  -> per-work identity-gated detail fetch and verified delivery
  -> head reconciliation after a genuine source end
  -> incremental head checks for new works
```

## Required behavior

1. **Exact subscription ownership.** Every continuation, Job, Run, receipt and publication stays bound to one Subscription, Account, author, `posts`-shaped creator scope and the locked `sec_user_id` fingerprint.
2. **Verbatim-cursor progression.** `max_cursor` is stored and replayed exactly as the server echoed it. Nothing may parse, reorder, regenerate or "optimize" it. A unit processes at most one upstream page and stops at the subscription's `max_items` for that unit.
3. **Four stop reasons, four fixed codes.** `has_more_false` (the only source-end candidate, retained with page evidence), `empty_page_stalled` (empty `aweme_list` while `has_more == 1`), `access_restricted` (signature failure, unparseable or blocked body, `DataFetchError`/`IPBlockError`/ban states), and `unit_cap_reached` (the unit's `max_items` bound). Only `has_more_false` may later qualify as source end.
4. **Identity-gated delivery.** Work details are fetched per `aweme_id` from the same page that surfaced the identity. A failed detail marks that work failed with its fixed code and never blocks unrelated works; media branches (gallery vs video) publish per complete Content unit with all-or-nothing semantics.
5. **Head reconciliation before incrementality.** After retained `has_more_false` evidence, one bounded head re-list must reproduce the recorded newest boundary (same newest work set, stable cursor echo) before the subscription may enter incremental polling. Drift keeps delivered data and re-opens reconciliation; no snapshot-complete equivalent is published on drift.
6. **Incremental operation.** Incremental cycles re-list bounded head pages, deduplicate by stable `aweme_id`, and produce work only for unseen or changed works. An unchanged cycle writes no bytes and no NFO rows.
7. **Pause, deletion and recovery.** The paused-state editor fences policy changes; auth expiry routes to the existing waiting-auth path; restart, lease loss and duplicate execution fence the same durable unit. Signature or risk-control restriction never discards the durable cursor.

## Acceptance evidence

- A deterministic locked-runner fixture paginates at least three `max_cursor` steps, records each echo, survives restart between steps and reaches a genuine `has_more != 1` end.
- An empty-page-with-`has_more == 1` response and a blocked-body response each record their distinct stop reason and resume without fabricating source end.
- After source end, head drift (one inserted work) re-opens reconciliation and later closes it; an unchanged head enters incremental mode.
- One new work is fetched once and published (gallery and video branches both covered by fixtures); an unchanged rerun is zero work.
- Final tree/NFO validation passes with no media server configured.
- Linux image, real Douyin login and a live creator canary remain `NOT_RUN` until the operator runs them.

## Explicit non-goals

- Douyin comments, search subscriptions or any non-creator scope.
- Treating Bilibili page numbers or XHS token semantics as Douyin-shaped.
- Automated handling of risk control beyond the existing pause/backoff policy.
- Any Emby/Jellyfin server control.
