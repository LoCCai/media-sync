**English** | [中文](plan.zh.md)

# Plan: durable Zhihu creator-answer delivery

Status: **frozen; implemented in this round.**

## 1. Re-derive the pinned facts before writing

- Re-read `.upstream/MediaCrawler/media_platform/zhihu/client.py:399-419`,
  `:462-490`, `media_platform/zhihu/core.py:256-300` and
  `media_platform/zhihu/help.py:354-366`, and cite the exact lines in the
  verification record.
- Record what must not change: the other six bounded contracts
  (0074/0076/0080/0081/0084/0085), the 0033 gallery shim, and migration head
  `0019_tieba_creator_notes` before this execution.

## 2. Durable cursor and stop reasons

- Migration `0020_zhihu_creator_answers` creating `zhihu_subscription_progress`
  with the 0015–0019 discipline: closed `phase` whitelist, four fixed stop
  reasons (`is_end`, `empty_page_end`, `access_restricted`, `unit_cap_reached`),
  counter ranges, all-or-nothing evidence triples, `last_offset` range,
  `blocked_code` iff `blocked`, and a guarded downgrade.
- `zh-work-v1:` opaque cursor carrying: integer `offset`, page witness (offset,
  limit, `is_end`, identity tuple), unit index, completed `content_id`s, the
  previous page's identity tuple, the head boundary, the last unit summary, and
  the stall/shift counters. Never an answer payload, title, body or media URL.

## 3. Fenced bounded continuation

- One page-bound unit per step; the cap is `max_items` alone, and the requested
  `limit` is `min(20, remaining)` because Zhihu's page size is client-chosen.
- A unit that cannot finish its page keeps the identical offset and witness so the
  next unit reissues the same request and skips delivered answers.
- Continuation delay via `MEDIA_SYNC_ZHIHU_SCAN_CONTINUATION_DELAY_SECONDS`
  (default 300, both services must agree).

## 4. Window-shift detection

- After a completed page, compare the next page's identity tuple with the previous
  page's. A non-empty intersection means the integer offset product moved under
  us; the offset is replayed unchanged and the shift counter advances.
- `zhihu_window_shifted` blocks after a bounded number of shifted units, because
  continuing would silently duplicate or skip answers.

## 5. Reconciliation and incremental head check

- A retained `is_end` end opens reconciliation; one bounded head re-list from
  offset 0 must reproduce the recorded boundary before incremental polling starts.
- In the head lane an answer whose id and listing digest are unchanged is
  `unchanged`, which is what makes the boundary reproducible.

## 6. Per-Content delivery

- Only answers whose complete media shape is present are published; one failing
  answer is counted with a fixed code and never blocks unrelated answers.
- Restart and zero-work replay preserve the content-addressed bytes and the
  deterministic NFO output.

## 7. Operator surface

- Subscription detail exposes phase, offset steps, the last `offset` and the most
  recent end/reconciliation evidence. It never exposes the `url_token`, the
  creator URL, an answer payload or a media URL.

## 8. Verification sequence

1. Unit: cursor round-trip and binding rejection, four stop reasons, small-cap unit
   limits, offset replay, shifted-window blocking, head boundary reproduction,
   coverage JSON round-trip, failed-detail isolation, bounded shapes.
2. Contract: page parsing privacy, six drift shapes, sealed coverage,
   restricted ≠ end.
3. Integration: `is_end` → reconciling → incremental with `last_offset`,
   restricted blocked code, terminal-failure blocked code.
4. Advance every head-revision pinning test to `0020_zhihu_creator_answers`.
5. Full Python and Web suites, Ruff, strict mypy, docs/upstreams, `git diff
   --check`; record exact bilingual results.
6. Linux build, real Zhihu login and a live canary remain `NOT_RUN` until an
   operator runs them.
