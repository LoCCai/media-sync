**English** | [中文](plan.zh.md)

# Plan: durable Tieba creator-work delivery

Status: **frozen; implemented in this round.**

## 1. Re-derive the pinned facts before writing

- Re-read `.upstream/MediaCrawler/media_platform/tieba/client.py:172-186`,
  `:684-710`, `:772-830` and `media_platform/tieba/help.py:240-250`, and cite the
  exact line numbers in the verification record.
- Record what must stay unchanged: the other five bounded contracts
  (0074/0076/0080/0081/0084), the 0020–0022 first-floor image shim, and migration
  head `0018_weibo_creator_notes` before this execution.

## 2. Durable cursor and stop reasons

- Migration `0019_tieba_creator_notes` creating `tieba_subscription_progress`
  with the same constraint discipline as 0015–0018: closed `phase` whitelist, the
  four fixed stop reasons (`has_more_false`, `empty_page_end`,
  `access_restricted`, `unit_cap_reached`), counter ranges, all-or-nothing
  evidence triples, `last_page_number` range, `blocked_code` iff `blocked`, and a
  guarded downgrade.
- `tb-work-v1:` opaque cursor carrying: 1-based page number, page witness, unit
  index, completed thread ids, previous-page identity tuple, head boundary and the
  last unit summary. Nothing else — never a thread payload, title or media URL.

## 3. Fenced bounded continuation

- At most one page-bound unit per step; the cap is `max_items` alone.
- A truncated page never advances the page number: the same request is reissued
  and delivered threads are skipped by stable `thread_id`.
- Continuation delay via `MEDIA_SYNC_TIEBA_SCAN_CONTINUATION_DELAY_SECONDS`
  (default 300, both services must agree).

## 4. Reconciliation and incremental head check

- After a retained `has_more_false` end, one bounded head re-list from page 1 must
  reproduce the recorded boundary before incremental polling starts.
- A repeated page identity tuple is the only stall signal available, because the
  page number always increments; such units accumulate and block at a bounded
  count with `tieba_page_stalled`.

## 5. Per-Content delivery

- Only threads whose complete media shape is present are published; one failing
  thread is counted with a fixed code and never blocks unrelated threads.
- Restart and zero-work replay preserve the content-addressed bytes and the
  deterministic NFO output.

## 6. Operator surface

- Subscription detail exposes phase, page step count, the last page number and
  the most recent end/reconciliation evidence. It never exposes the portrait, the
  creator URL, a thread payload or a media URL.

## 7. Verification sequence

1. Unit: cursor round-trip, four stop reasons, page-tail replay, stall blocking,
   binding-change rejection.
2. Contract: page parsing privacy, drift rejection, sealed coverage,
   restricted feed ≠ end.
3. Integration: page steps across a restart, server end, head drift and
   reconciliation, incremental entry, partial delivery, zero-work replay,
   single-transaction ingestion, migration round-trip.
4. Advance every head-revision pinning test to `0019_tieba_creator_notes`.
5. Full Python and Web suites, Ruff, strict mypy, docs/upstreams, `git diff
   --check`; record exact bilingual results.
6. Linux build, real Tieba login and a live canary remain `NOT_RUN` until an
   operator runs them.
