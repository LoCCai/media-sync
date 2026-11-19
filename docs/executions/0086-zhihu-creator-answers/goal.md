**English** | [中文](goal.zh.md)

# Goal: durable Zhihu creator-answer delivery

Media-sync already delivers durable creator work for Bilibili (0074), XHS (0076),
Douyin (0080), Kuaishou (0081), Weibo (0084) and Tieba (0085). Zhihu is the last
platform in the frozen [next-delivery sequence](../0083-douyin-media-profile/next-delivery.md)
that still relies on a bounded *count* only: a creator subscription can stop at a
cap, cannot resume, cannot tell a restricted feed from a source end, and cannot
publish per-content delivery evidence. This execution closes that gap.

## What Zhihu does differently

From the pinned upstream, and only from it:

- Pagination is an **integer `offset`** on
  `/api/v4/members/<url_token>/answers` with a **client-chosen `limit`** and
  `order_by=created` (`.upstream/MediaCrawler/media_platform/zhihu/client.py:399-419`).
- The loop is `while not is_end:` … `offset += limit`
  (`client.py:462-490`), so the end is the server-declared **`paging.is_end`**
  boolean, never a page count.
- A falsy body breaks out of the loop before any paging is read
  (`client.py:483-484`), which is *not* an end.
- Creator identity is the `url_token` taken from the `/people/<url_token>` URL
  (`core.py:265`); content identity is the extractor's `content_id`.

The offset is a page*limit product. An insertion or deletion between two requests
**shifts the whole window**: the next page then silently skips or repeats answers
while every response still looks valid. That is the risk this execution must make
durable — not just "count pages".

## Deliverable

A Zhihu creator subscription that:

1. walks the offset chain one page-bound unit at a time, capping at `max_items`;
2. records the server-declared `is_end` as a **source-end observation** that still
   only opens reconciliation, never completeness;
3. distinguishes `empty_page_end` from the declared end;
4. treats a falsy/malformed body, `DataFetchError`/`IPBlockError` or a transport
   failure as `access_restricted`, which never advances the cursor;
5. detects a **shifted window** by comparing page identity tuples, replays the
   identical offset, and blocks after a bounded number of non-advancing units with
   `zhihu_window_shifted`;
6. publishes per-content delivery only from a closed pipeline receipt, then
   reconciles the head boundary and only then enters incremental polling;
7. advances the migration head to `0020_zhihu_creator_answers` with the same
   constraint discipline as 0015–0019.

## Explicitly out of scope

- Deployment, a Linux host gate, a real Zhihu login, and any live request. Those
  rows stay `NOT_RUN` and belong to the operator-run canary (0087).
- Any change to the other six bounded contracts or to the 0033 gallery shim.
- Copying GPL or NC-licensed upstream source. Only behaviour and protocol facts
  derived from the pinned checkout are used.
