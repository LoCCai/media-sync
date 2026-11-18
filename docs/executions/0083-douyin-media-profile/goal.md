**English** | [中文](goal.zh.md)

# Goal: Douyin media request profile and bounded stream selection

## Outcome

Make one Douyin creator-work delivery able to fetch the *highest available*
stream that the pinned upstream detail response already carries, instead of
whichever flattened URL the upstream store happens to keep, and give those media
requests the browser-shaped profile the platform expects.

## Evidence that motivates this execution

- The pinned upstream flattens the detail response to four scalars
  (`.upstream/MediaCrawler/store/douyin/__init__.py:132-140`): `play_addr_h264`,
  then `play_addr_256`, then `play_addr`, taking `url_list[-1]` of the first
  non-empty candidate. The richer `video.bit_rate[]` array — one entry per
  quality with its own `play_addr.url_list` and `data_size` — is discarded
  before media-sync can see it, so a 1080p-only delivery cannot be expressed.
- Media-sync currently resolves every non-Bilibili asset, including Douyin, with
  `MediaRequestProfile.DEFAULT`, which sends no `User-Agent`, `Referer` or
  `Accept` header at all (`src/media_sync/media/network.py:25-32`,
  `src/media_sync/integrations/mediacrawler/refresh.py:614-618`). Douyin CDNs
  routinely answer such a request with `403`.
- The operator reports a working reference implementation
  (TikTokDownloader, GPLv3) whose Douyin link succeeds. Behavioural facts from it
  are usable; its source code, constants and structure are not, and nothing may
  be copied (see `THIRD_PARTY_NOTICES.md`).

## Required behaviour

1. **Closed request profile.** Add `MediaRequestProfile.DY_MEDIA` with a fixed
   desktop `User-Agent`, `Referer: https://www.douyin.com/`, `Accept: */*` and
   nothing else. No Cookie, no `Authorization`, no caller-supplied header. The
   profile is selected purely by platform inside `refresh.py`; Bilibili's
   existing profile behaviour is untouched.
2. **Bounded stream selection.** A pure function reduces one pinned upstream
   `aweme_detail` mapping to a `(video_url | None, cover_url | None, source
   rank)` decision by ordering `video.bit_rate[]` entries on documented
   response fields only. It must reject rather than guess on drift: missing
   `url_list`, non-HTTPS URLs, hosts outside the accepted Douyin media
   domains, duplicate or oversized arrays (bounded at 8 bit-rate entries), and
   an absent video when a video was expected.
3. **No persisted signature material.** Selection happens inside the child; only
   the already-existing no-query `source_hint` survives into SQLite, and the
   private selection field is stripped by the existing private-field discipline
   before the envelope is built.
4. **Fallback keeps history.** When `bit_rate[]` is absent or unusable the
   contract falls back to the upstream flattened `play_addr_h264` /
   `play_addr_256` / `play_addr` order, so every currently deliverable Douyin
   work keeps delivering with byte-identical accepted shapes.
5. **Explainable operator surface.** The delivery payload may report *which*
   rank won (no URL, no host, no query) so a future canary can prove the
   selection without leaking a signed locator.

## Acceptance

- Unit tests fix the ordering rule (highest resolution, then highest bit rate,
  then largest `data_size`, then first declared) and each rejection branch.
- A contract test proves the child shim emits the selected rank through the
  private field, that the field never reaches the envelope, and that the
  fallback path reproduces today's accepted URLs byte for byte.
- An integration test drives SQLite → refresh → mock DNS/HTTP → archive → Emby
  for a Douyin work whose `bit_rate[]` carries a better stream than
  `play_addr_h264`, and proves zero-work replay.
- `MediaRequestProfile.DY_MEDIA` is proven by asserting the exact outbound header
  set on the mock transport, plus the absence of any other header.
- Full Python/Web/static/documentation gates pass; deployment, real login and
  any live CDN byte fetch stay `NOT_RUN`.

## Explicit non-goals

- Reproducing TikTokDownloader's `a_bogus`/`msToken` signing, TLS impersonation,
  or its retry/chunking policy. MediaCrawler remains the sole signing authority.
- Watermark removal claims. Selection may prefer an un-watermarked candidate when
  the response declares one, but no claim is made about real bytes without a
  live canary.
- Any Emby/Jellyfin server control, and any change to the 0074/0076/0080/0081
  cursor, coverage, migration or progress-table semantics.
