**English** | [中文](goal.zh.md)

# Goal: durable Tieba creator-work delivery

## Outcome

One exact Tieba creator subscription gains the same durable delivery chain the
other five platforms carry, with every rule re-derived from the pinned Tieba
source.

## Why the Tieba shape is different

Re-read and cite in the verification record
(`.upstream/MediaCrawler/media_platform/tieba/`):

- Pagination is a **1-based page number** on the signed PC feed endpoint
  `/c/u/feed/myThread` with `pn` and `rn=20` (`client.py:684-710`). There is no
  opaque cursor and no `since_id`.
- The loop walks pages while `max_note_count == 0 or len(result) < max_note_count`,
  breaks when a page yields no thread ids, and breaks when
  `int(data.get("has_more") or 0)` is falsy (`client.py:790-830`).
- A business `error_code != 0` or a malformed body makes upstream log and break
  (`client.py:806-810`); that is not a source end.
- Creator identity is the `portrait` extracted from the creator URL
  (`client.py:172-186`), and thread identity is `thread_info.tid` (or `id`)
  (`help.py:240-250`).

Because `pn` is an integer that always increments, a repeated page cannot be
detected by the cursor alone: the durable layer must compare page identities and
count a non-advancing page as a stall.

## Required behaviour

1. **Page-number cursor.** The page number is stored as a bounded positive
   integer under the opaque `tb-work-v1:` namespace with the same closed-schema
   round-trip discipline as the other four platforms.
2. **Four stop reasons, four fixed codes.** `has_more_false` (server-declared
   end, kept with the page witness and used to open reconciliation),
   `empty_page_end` (no thread ids on an otherwise valid page),
   `access_restricted` (non-zero `error_code`, malformed body, `DataFetchError`
   or any transport failure) and `unit_cap_reached`.
3. **Page-tail retention.** When `max_items` stops a unit before the page tail,
   the identical page number stays in place and the page witness is retained; the
   next unit re-issues the same request and skips already-delivered threads by
   stable `thread_id`.
4. **Stall guard.** Consecutive pages whose identity tuple repeats make no
   progress; such units accumulate and block at a bounded count with a fixed
   code instead of looping forever.
5. **Identity-guarded delivery.** Each listed thread is fetched by
   `get_note_by_id` from the page that presented it, published per complete
   Content, and one failing thread never blocks unrelated threads.

## Acceptance

- Cursor round-trip, the four stop reasons, page-tail replay, stall blocking and
  binding-change rejection are unit tested.
- Page parsing keeps no thread payload, no title and no media URL; a non-zero
  `error_code` or malformed body records `access_restricted`, never an end.
- An integration test drives three or more page steps across a restart, reaches
  `has_more_false`, reconciles the head, enters incremental mode and publishes one
  article work through archive → Emby with zero-work replay.
- Every head-revision pinning test advances to `0019_tieba_creator_notes`.
- Full Python/Web/static/documentation gates pass.
- Deployment, real login and any live request stay `NOT_RUN`.

## Explicit non-goals

- Replies, mixed/rich thread media, or galleries beyond the shapes frozen by
  0020–0022.
- Any Emby/Jellyfin server control, and any change to 0074/0076/0080/0081/0084
  semantics.
