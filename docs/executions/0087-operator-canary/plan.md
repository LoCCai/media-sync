**English** | [中文](plan.zh.md)

# Plan: the operator-run bounded canary per platform

Status: **procedure frozen; every row is `NOT_RUN`.** Nothing here was executed on
a live host, and this execution changes no product behaviour.

## 1. One platform at a time

Run exactly one platform canary per session so the evidence stays attributable.
Order: Bilibili (already carries the longest history), then XHS, Douyin,
Kuaishou, Weibo, Tieba, Zhihu.

## 2. Prove identity before touching a platform

Follow the existing [deployment handoff](../0077-deployment-provenance-preflight/deployment-handoff.md):

- `git rev-parse HEAD` must equal the image's
  `org.opencontainers.image.revision` label and the recorded
  `MEDIA_SYNC_SOURCE_REVISION` build arg.
- `scripts/check_upstreams.py` must report both pinned checkouts verified.
- `media-sync doctor --deep` must report the expected database revision
  (`0020_zhihu_creator_answers`) and the per-platform continuation delays.
- Both `media-sync` and `supervisor` must carry the **same**
  `MEDIA_SYNC_<PLATFORM>_SCAN_CONTINUATION_DELAY_SECONDS` value; a mismatch
  invalidates the run.

## 3. Claim one native session and pause everything else

- Log in once through `/crawler/` with a real account and adopt the session into
  exactly one Account for that platform.
- Pause every other Subscription so a canary cannot be mixed with unrelated
  traffic or downloads.
- Record the Account id, the author id and `auth_revision`.

## 4. Run one bounded, single-author canary

- Create one Subscription for one creator with a small `max_items` (the smallest
  that still forces a page tail, e.g. 25 for a 20-per-page feed).
- Tick the scheduler until the durable progress row reaches `incremental`, and
  capture for each run: `run_id`, `phase`, `stop_reason`, page witnesses consumed,
  `batch_count`, `cursor_step_count` and the delivered/verified asset counts.
- Required observations per platform, from its own execution record:

| Platform | Must observe | Must never observe |
| --- | --- | --- |
| Bilibili | source end opens reconciliation | completeness claimed from a page count |
| XHS | empty-page stall distinct from source end | a stall treated as an end |
| Douyin | `has_more_false` end | an inferred end treated as complete |
| Kuaishou | `no_more_echoed` end | an echoed sentinel ignored |
| Weibo | `total_inferred_end` recorded as an inference | `total` presented as completeness |
| Tieba | `has_more_false` end plus a repeated-page stall if it happens | `error_code != 0` treated as an end |
| Zhihu | `is_end` end plus `zhihu_window_shifted` if a shift happens | a shifted window silently skipping answers |

## 5. Download, publish and replay

- Confirm real media bytes were fetched from the platform CDN, the deterministic
  NFO was written, and the file landed in the library.
- Replay the same canary: the second run must deliver **zero** new content and
  download **zero** new bytes while the durable row still advances its counters.
- Restart the resident supervisor once and confirm the row resumes rather than
  restarting from offset/page zero.

## 6. Record the qualification

- Write one row per platform into
  [`qualification.md`](qualification.md) with `PASS`, `FAIL` or `NOT_RUN`, the
  exact source revision, migration head, run ids and the observed transitions.
- A row stays `NOT_RUN` until a real login and a real request produced it. A
  local test run is evidence about code, never about a live platform.

## 7. Explicitly out of scope

- Changing product code from this execution. If a canary fails, the fix belongs
  to a new numbered execution that re-derives the platform facts first.
- Declaring a platform supported, or removing a `NOT_RUN` row, without the
  evidence above.
