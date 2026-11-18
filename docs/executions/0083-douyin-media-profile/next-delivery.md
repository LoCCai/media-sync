**English** | [中文](next-delivery.zh.md)

# Next delivery: remaining creator-work deliveries, then the operator gate

## Status

**Plan only.** Nothing in this document authorizes deployment, platform requests
or a resident-process restart. It records the sequence and the upstream facts a
future execution must re-derive, so each step starts from evidence rather than
from a copied template.

## Where the project actually stands

Four platforms now carry the same durable creator-work chain, each derived from
its own pinned upstream semantics:

| Platform | Execution | Cursor / page signal | Stop reasons |
| --- | --- | --- | --- |
| Bilibili | 0074 | page number, 30 per page | source-end, unit cap, restricted |
| XHS | 0076 | opaque `cursor` + `has_more` | source-end, empty-page stall, restricted, unit cap |
| Douyin | 0080 | opaque `max_cursor` + integer `has_more`, 18 per page | `has_more_false`, `empty_page_stalled`, `access_restricted`, `unit_cap_reached` |
| Kuaishou | 0081 | echoed `pcursor` + string sentinel `no_more` | `no_more_echoed`, `empty_page_end`, `access_restricted`, `unit_cap_reached` |

Weibo, Tieba and Zhihu still have media capture, detail refresh and bounded
per-run caps, but **no durable cursor, no delivery progress table and no
per-Content publication**. Their creator paths remain the weakest link in the
product: a long history cannot be resumed, and a partial run has no durable
statement about what was already delivered.

## Upstream facts each future execution must re-derive

These were read from the pinned checkout during this closeout; each execution
must re-read and cite them rather than trusting this summary.

- **Weibo** (`.upstream/MediaCrawler/media_platform/weibo/client.py:346-412`,
  `core.py:326-331`): `since_id` is the only cursor; the page size is a
  hard-coded 10 (`crawler_total_count += 10`), and termination is an arithmetic
  inference `cardlistInfo.total > crawler_total_count`, not a `has_more` flag.
  `core.py` passes `crawl_interval=0` and no note cap, so the upstream loop is
  unbounded. A durable layer must therefore own its own unit cap and must treat
  `total` as a **time-bounded** end candidate, never as proof the history is
  complete.
- **Tieba** (`media_platform/tieba/client.py:684-710`, `:727`, `:857-860`):
  page numbers with `pn`/`rn=20`; termination is an empty `thread_id_list` or
  `has_more == 0`; the creator identity is a `portrait` parsed from the profile
  URL, and the thread identity is `thread_id`.
- **Zhihu** (`media_platform/zhihu/client.py:399-419`, `:462-490`): `offset` is
  an integer page×limit product, not an opaque cursor, so insertion or deletion
  shifts the window; termination is `paging.is_end`. A durable layer must dedupe
  by `content_id` and keep a page witness, otherwise a shift silently skips
  content.

## Sequence

1. **0084 — Weibo creator-work durable delivery.** Migration `0018`, a
   `weibo_subscription_progress` table with the same constraint discipline,
   `since_id` kept verbatim under an opaque namespace, a durable unit that never
   advances on an inferred `total`, and explicit `total_inferred_end` versus
   `access_restricted` versus `unit_cap_reached`. Acceptance: a bounded unit
   never claims completeness from `total`; page-tail retention under
   `max_items`; head reconciliation before incremental mode; one IMAGE/VIDEO work
   published through archive → Emby with zero-work replay.
2. **0085 — Tieba creator-work durable delivery.** Migration `0019`, page-number
   cursor, `has_more == 0` and empty-page end codes kept distinct, portrait
   identity bound into the cursor fingerprint. Acceptance mirrors 0084 with the
   `20 + 3` page sequence already proven by the 0020–0022 shims.
3. **0086 — Zhihu creator-work durable delivery.** Migration `0020`, integer
   offset cursor with an explicit page witness and `content_id` dedupe, so a
   shifted window is detected rather than silently skipped. Acceptance: an
   insertion between two units is either delivered or flagged, never lost.
4. **0087 — one bounded operator canary per platform.** Operator-only. Requires
   the deployment handoff, a claimed native session and a paused single-author
   subscription per platform. Produces a qualification record with explicit
   `PASS`/`FAIL`/`NOT_RUN` rows; no platform may be called Supported before it.

## Explicitly not in this plan

- Any deployment, real login, platform request or CDN byte fetch.
- Any change to the 0074/0076/0080/0081 semantics, migrations or progress tables.
- Any claim that an inferred end (`Weibo total`, `Zhihu is_end` after a shift)
  proves a complete history.
