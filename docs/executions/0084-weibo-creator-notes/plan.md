**English** | [中文](plan.zh.md)

# Plan: durable Weibo creator-note delivery

Status: **frozen; implemented in this round.**

## 1. Re-derive the pinned facts before writing

- Re-read `.upstream/MediaCrawler/media_platform/weibo/client.py:341-412` and
  `core.py:308-334`, and cite the exact line numbers in the verification record.
- Record what must stay unchanged: 0074/0076/0080/0081 cursors, coverage,
  migrations and progress tables; the Weibo media capture shim from 0016/0031/
  0035/0036; migration head `0017_kuaishou_creator_work` before this execution.

## 2. Durable cursor and stop reasons

- Migration `0018_weibo_creator_notes` creating `weibo_subscription_progress`
  with the same constraint discipline as 0015–0017: closed `phase` whitelist,
  the four fixed stop reasons, counter ranges, all-or-nothing evidence triples,
  `blocked_code` iff `blocked`, guarded downgrade.
- `wb-work-v1:` opaque cursor carrying: `since_id`, page witness, unit index,
  completed note ids, head boundary, stalled-unit counter, pages consumed and the
  last unit summary. Nothing else, and never a media URL or an `mblog` payload.

## 3. Fenced bounded continuation

- At most one page-bound unit per step; the cap is `max_items` alone because
  upstream's page size is an arithmetic constant, not a request parameter.
- A truncated page never advances the cursor: the same `since_id` is reissued and
  delivered notes are skipped by `mblog.id`.
- Continuation delay via `MEDIA_SYNC_WEIBO_SCAN_CONTINUATION_DELAY_SECONDS`
  (default 300, both services must agree).

## 4. Reconciliation and incremental head check

- After a retained inferred end, one bounded head re-list from the empty cursor
  must reproduce the recorded boundary before incremental polling starts.
- Incremental mode re-lists bounded head pages and only fetches detail for unseen
  or changed notes.

## 5. Per-Content delivery

- Only notes whose complete media shape is present are published; one failing
  note is counted with a fixed code and never blocks unrelated notes.
- Restart and zero-work replay preserve the content-addressed bytes and the
  deterministic NFO output.

## 6. Operator surface

- Subscription detail exposes phase, cursor step count, the declared total, the
  most recent end/reconciliation evidence and the next run time. It never exposes
  the cursor itself, the creator reference, a media URL or a raw response.

## 7. Verification sequence

1. Unit: cursor round-trip, four stop reasons, page-tail replay, stall blocking,
   binding-change rejection, inferred-end being distinct from completeness.
2. Contract: page parsing privacy, falsy body / missing `cards` mapped to
   `access_restricted`, coverage sealing.
3. Integration: three or more `since_id` steps across a restart, inferred end,
   head drift and reconciliation, incremental entry, partial delivery, zero-work
   replay, single-transaction ingestion, migration round-trip.
4. Advance every head-revision pinning test to `0018_weibo_creator_notes`.
5. Full Python and Web suites, Ruff, strict mypy, docs/upstreams, `git diff
   --check`; record exact bilingual results.
6. Linux build, real Weibo login and a live canary remain `NOT_RUN` until an
   operator runs them.
