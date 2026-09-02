**English** | [中文](goal.zh.md)

# Execution 0020 goal

- Status: Frozen offline scope delivered and verified; authenticated/live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0019 closeout commit `431fd855dafce502e83f74a055a4b27ae5c6f40b`
- Plan commit: `df7a38a6f9beee35c6c19336260b512ebc87ce0d`
- Implementation commit: `8a0e935624e944809af1a56b0f02186686433d95`
- Scope: Exactly one static image in an ordinary Tieba creator thread's first floor

## Outcome

Execution 0020 adds the first downloadable Tieba media slice and therefore a narrow media path for the seventh platform. A verified-checkout runtime shim captures exactly one current `type=3` first-floor image from the locked MediaCrawler `page_pc` response before the extractor reduces structured content to text. Scheduled creator discovery is bounded by Subscription `max_items`; normalization retains the thread as ARTICLE and adds one position-zero IMAGE; an exact canonical detail lookup reacquires the current transient `tbpicau` locator immediately before download; the existing bounded static-image gate, SHA-256 archive and deterministic Emby/Jellyfin layout complete the offline pipeline.

## Evidence for this slice

- At locked MediaCrawler SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`, `BaiduTieBaClient.get_note_by_id` calls `_get_pc_page_data`, then `TieBaExtractor.extract_note_detail_from_api`. The latter receives the full response but `_extract_api_content_text` keeps only `text`/`c`; `TiebaNote`, `model_dump()` and JSONL therefore lose every image locator.
- A bounded unauthenticated read-only audit of the current public API on 2026-09-02 found real successful first-floor rows with exactly one integer `type=3` item. The item exposed the stable key family `origin_src`, `cdn_src`, `big_cdn_src`, `cdn_src_active`, `pic_id`, `bsize`, `origin_size`, `is_long_pic` and `show_original_btn`; every observed image URL used HTTPS `tiebapic.baidu.com` and a single `tbpicau` query key. No query value or response body is retained in this repository.
- A transient default-profile check returned a 65,144-byte JPEG for the refreshed signed `origin_src`; the same origin/path without query returned a different 4,262-byte JPEG. This proves that a query-free durable hint cannot be used as the download locator even when it returns HTTP 200. It does not qualify future CDN behavior.

## Frozen acceptance boundary

1. The qualifying API shape has a canonical positive thread ID, exact `https://tieba.baidu.com/p/<id>` result URL, a bounded first-floor content list, exactly one integer `type=3` image item and only ordinary integer `type=0` text siblings. Zero images preserve historical ARTICLE-only behavior but are outside this media claim; multiple images, other content types, missing/extra ambiguous media keys, malformed IDs or mismatched returned objects produce no qualified Asset and fail refresh closed.
2. Selection uses only `origin_src`. It must be bounded HTTPS on exact `tiebapic.baidu.com`, use default port and canonical `/forum/pic/item/<40 lowercase hex>.<jpg|jpeg|png|webp>` path, contain exactly one non-empty bounded `tbpicau` query parameter, and have no userinfo, fragment, whitespace, controls or backslash. The derived durable source hint retains only canonical scheme/authority/path.
3. The shim wraps only verified pinned objects, attaches one frozen capture to the exact returned `TiebaNote`, carries it across `asyncio.gather` child-to-parent storage on that object, and uses `ContextVar` only for the nested `update_tieba_note` → JSONL store call. Wrong origin, marker collision, partial install, field collision, object/row mismatch and concurrent leakage fail closed. `.upstream` remains unmodified and untracked.
4. Scheduled creator execution successfully processes at most Subscription `max_items`. The verified wrapper preserves the pinned creator endpoint and callback contract while validating bounded page shapes, positive unique thread IDs, exact detail result identity, `has_more` progress and pacing. It slices before detail requests, performs no next request or post-cap sleep, and fails closed on repeats, malformed pages or identity drift.
5. Normalization keeps `ContentKind.ARTICLE` and adds exactly one position-zero `AssetKind.IMAGE` with remote ID `<note_id>:image:0`. The private capture field and every transient query value are recursively absent from normalized raw, SQLite and retained artifacts.
6. Refresh derives the only detail authority from the persisted exact canonical thread URL, performs one bounded detail run, and requires one matching ARTICLE, one matching IMAGE identity/position and the same query-free source hint. It returns only a newly validated signed URL with `MediaRequestProfile.DEFAULT`; account Cookie, Authorization, Referer and Origin are not forwarded to the image host.
7. Tieba IMAGE downloads automatically use the bounded static structural gate. Qualified JPEG, PNG and WebP pass; GIF, APNG, animated WebP and AVIF fail. The gate is structural qualification, not a complete pixel decoder, and the flag survives normal, recovery and takeover preparation.
8. One isolated composition traverses exact SQLite provenance, fake detail, mock public DNS/HTTP, production byte qualification, SHA-256 archive and Emby poster/backdrop/gallery/body/NFO/source publication. Query-only replay adds zero work, and retained SQLite/runtime/archive/export/WAL/SHM artifacts contain neither the private field nor transient query values.

## Explicit exclusions

Multiple first-floor images/gallery, video/voice/emoji/link/rich-card content types, replies/comments media, alternate Tieba image hosts/paths, media replacement semantics, real retained redacted API fixtures and authenticated/live qualification remain deferred or `NOT_RUN`. This execution is one frozen first-floor static-image slice; it does not mean complete Tieba media support or complete seven-platform product coverage.
