**English** | [中文](progress.zh.md)

# Progress: Douyin media request profile and bounded stream selection

Status: implemented and verified locally. Nothing was deployed and no platform
account or live CDN byte was used.

## Result

A Douyin creator-work delivery can now use the highest stream the pinned detail
response declares, instead of whichever flattened URL the upstream store keeps,
and its media requests carry the closed desktop header set the platform expects.

## What was implemented

1. **Closed media profile.** `MediaRequestProfile.DOUYIN_MEDIA` carries exactly
   `User-Agent` (desktop Chrome), `Referer: https://www.douyin.com/` and
   `Accept: */*`. `refresh.py` selects it through `_platform_media_profile()`;
   every other platform keeps `DEFAULT`, and Bilibili's progressive/dynamic
   branch is untouched. No Cookie, `Authorization`, `Origin`, caller header or
   TLS impersonation exists.
2. **Bounded selection.** `douyin_media.py` reduces one pinned `aweme_detail` to
   a frozen `DouyinMediaSelection`. Ranking is highest `max(width, height)`, then
   highest declared `bit_rate`, then largest `data_size`, then declaration order;
   at most 8 `bit_rate` entries. The module refuses rather than guesses: a
   missing `url_list`, a duplicate URL, an over-limit array, an `http` URL, a
   userinfo/port/fragment/root-path URL or a host outside the closed Douyin media
   suffix list raises `DouyinMediaSelectionError` with a fixed code.
3. **Pinned-store shim.** `install_douyin_media_capture()` wraps
   `store.douyin.update_douyin_aweme` and
   `store.douyin._store_impl.DouyinJsonlStoreImplement.store_content` with a
   task-local `ContextVar`, exactly like the Kuaishou atlas shim. Only the
   `bit_rate` rank rewrites `video_download_url`; the fallback ranks reproduce
   the pinned flattening order, so every currently deliverable work stays
   byte-identical. The private `__media_sync_dy_media_rank_v1` field is
   registered in `_PRIVATE_MEDIA_FIELDS`, so it never reaches the envelope or
   persisted `raw`; it only ever carries `{"rank": ..., "width": ..., "height": ...}`.
4. **Runner wiring.** `runner.py` installs the shim for every Douyin child;
   `detail_runner.py` installs it for the single-detail refresh path, so a refresh
   sees the same ranking the creator scan saw.

No migration, cursor, coverage, stop-reason or progress-table semantics changed;
migration head stays `0017_kuaishou_creator_work`.

## What was deliberately not done

- No `a_bogus`/`msToken`/`uifid` signing, no TLS fingerprint impersonation and no
  reference-implementation retry/chunking policy. MediaCrawler remains the sole
  signing authority, and no GPLv3 source was copied.
- No watermark claim and no real CDN byte fetch: a live canary is still required
  before any statement about delivered bytes.

## Observed while working

The earlier 0082 failure mode influenced the checks here: `ruff format --check`
and `ruff check` were run on the whole repository rather than only touched files,
which is what catches the test-side profile assertions that had to change.
