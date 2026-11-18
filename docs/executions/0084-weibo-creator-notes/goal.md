**English** | [中文](goal.zh.md)

# Goal: durable Weibo creator-note delivery

## Outcome

One exact Weibo creator subscription gains the same durable delivery chain that
Bilibili (0074), XHS (0076), Douyin (0080) and Kuaishou (0081) already carry, with
every rule derived from the pinned Weibo source rather than copied from another
platform.

## Why the Weibo shape is different

`docs/executions/0083-douyin-media-profile/next-delivery.md` recorded the facts; this
execution re-reads and cites them:

- Pagination is `/api/container/getIndex` with `containerid=107603<uid>` and a
  verbatim `since_id` cursor echoed in `cardlistInfo.since_id`
  (`.upstream/MediaCrawler/media_platform/weibo/client.py:341-372`).
- The page size is **not** a request parameter. Upstream advances an arithmetic
  counter by a hard-coded `10` per page and continues while
  `cardlistInfo.total > counter` (`client.py:411-412`). This is an **inference**,
  not a `has_more` flag, and it disagrees with observed content whenever the
  `card_type == 9` filter drops cards (`client.py:407`).
- A falsy body is logged as a possible ban and the loop breaks
  (`client.py:401-403`); a missing `cards` key breaks the loop
  (`client.py:404-406`). Neither is a source end.
- `core.py:326-331` passes `crawl_interval=0` and no note cap, so the upstream
  creator loop is unbounded and the durable layer must own its own unit cap.

## Required behaviour

1. **Verbatim cursor.** `since_id` is stored and replayed exactly; it is never
   parsed, regenerated or normalised. It lives under the opaque
   `wb-work-v1:` namespace with the same closed-schema round-trip discipline as
   `ks-work-v1:` and `dy-work-v1:`.
2. **Four stop reasons, four fixed codes.** `total_inferred_end` (the arithmetic
   candidate, kept together with the declared total and the page witness),
   `empty_page_end` (nothing listed and no declared total), `access_restricted`
   (falsy body, missing `cards`, `DataFetchError`, or any transport failure) and
   `unit_cap_reached`.
3. **An inferred end is never completeness.** The declared `total`, the number of
   pages consumed and the first-page witness survive in the cursor, so a head
   reconciliation can later confirm or reject the boundary. No API, log or
   document may describe `total_inferred_end` as a complete history.
4. **Page-tail retention.** When `max_items` stops a unit before the page tail,
   the identical `since_id` stays in place and the page witness is retained; the
   next unit re-issues the same request and skips already-delivered notes by
   stable `mblog.id`.
5. **Stall guard.** A non-empty page whose echoed `since_id` equals its input, or
   an empty filtered page that repeats its cursor, makes no progress upstream
   would never notice; such units accumulate and block at a bounded count with a
   fixed code.
6. **Identity-guarded delivery.** Notes are fetched from the page that presented
   them, published per complete Content, and one failing note never blocks
   unrelated notes.

## Acceptance

- Cursor round-trip, the four stop reasons, page-tail replay, stall blocking and
  binding-change rejection are unit tested.
- Page parsing keeps no media URL, no `mblog` payload and no raw `total`;
  a falsy body or missing `cards` records `access_restricted`, never an end.
- An integration test drives three or more `since_id` steps across a restart,
  reaches an inferred end, reconciles the head, enters incremental mode and
  publishes one IMAGE/GALLERY or VIDEO work through archive → Emby with
  zero-work replay.
- Every head-revision pinning test advances to `0018_weibo_creator_notes`.
- Full Python/Web/static/documentation gates pass.
- Deployment, real login and any live request stay `NOT_RUN`.

## Explicit non-goals

- Any claim that the arithmetic end proves a complete history.
- Weibo retweeted originals, `page_info` media on the creator path, GIF/video
  variants beyond the shapes already frozen by 0016/0031/0035/0036.
- Emby/Jellyfin server control, and any change to 0074/0076/0080/0081 semantics.
