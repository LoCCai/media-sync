**English** | [中文](plan.zh.md)

# Plan: Douyin media request profile and bounded stream selection

Status: **frozen**. No deployment, platform request or resident-process restart
is authorized by this plan.

## 1. Re-confirm the pinned facts first

- Re-read `.upstream/MediaCrawler/store/douyin/__init__.py:132-140` (flattening
  order) and `media_platform/douyin/client.py:211-221` (detail endpoint and
  header handling) before writing a line, and cite them in the verification
  record.
- Record the media-sync call sites that must stay unchanged: the 0080 scan state
  machine, the `dy-work-v1:` cursor, the four stop reasons and the migration
  head `0017_kuaishou_creator_work`.

## 2. Request profile

- `src/media_sync/media/locator.py`: add `MediaRequestProfile.DY_MEDIA`
  (`"douyin_media"`) to the closed enum.
- `src/media_sync/media/network.py`: add exactly three headers for it —
  desktop `User-Agent`, `Referer: https://www.douyin.com/`, `Accept: */*` — and
  nothing else. No Cookie, no Authorization, no caller header, no TLS
  impersonation.
- `src/media_sync/integrations/mediacrawler/refresh.py`: select `DY_MEDIA` for
  `Platform.DY` with a helper that mirrors the existing Bilibili branch; the
  default branch keeps returning `DEFAULT`. No other platform changes.

## 3. Bounded selection

- New module `src/media_sync/integrations/mediacrawler/douyin_media.py` holding
  a pure function over one `aweme_detail` mapping. It returns a frozen
  `DouyinMediaSelection` carrying the chosen video URL (transient, `repr=False`),
  the cover URL, the ranking fact (`bit_rate`, `play_addr_h264`,
  `play_addr_256`, `play_addr`, `none`) and the declared quality. It raises a
  fixed `ValueError` subclass on drift; it never returns a partial guess.
- Ordering: highest `max(width, height)`, then highest `bit_rate`, then largest
  `data_size`, then declaration order. Bounded at 8 entries; more is drift.
- URL gate: HTTPS only, no userinfo, no fragment, default port, host must be a
  Douyin media host from a closed suffix list, path must be non-root.
- Cover follows the upstream rule (`raw_cover` then `origin_cover`,
  `url_list[1]` when at least two entries exist) and is optional.

## 4. Wiring without changing persisted shapes

- `douyin_creator_capture.py`: compute the selection once per detail inside the
  child and publish it through a context variable, exactly like
  `_ACTIVE_IDENTITY`; the store wrapper adds a private
  `__media_sync_dy_media_rank` field plus the transient selected URL.
- `normalizers.py`: register the new private field in the existing
  `_PRIVATE_MEDIA_FIELDS` set so it is stripped before the envelope is built, and
  let `_normalize_dy` prefer the selected URL only when the selected rank is
  strictly better than the upstream flattened field; otherwise keep today's
  byte-identical behaviour.
- The delivery payload gains nothing that leaks a URL: at most a fixed rank
  string.

## 5. Verification sequence

1. Unit: ordering matrix, each rejection branch, cover rule, fallback equality.
2. Contract: shim emits the private field; the field never appears in the
   envelope or in persisted `raw`; fallback reproduces the current URLs exactly.
3. Unit: profile header set is exactly the three expected headers, and the other
   platforms still send none.
4. Integration: SQLite → refresh → mock DNS/HTTP → archive → Emby for a work
   whose `bit_rate[]` beats `play_addr_h264`, plus zero-work replay, plus a
   drift case that fails closed with a fixed code.
5. Full Python and Web suites, Ruff, strict mypy, docs/upstreams, `git diff
   --check`; record exact numbers bilingually.

## 6. Explicitly not in scope

- Signing (`a_bogus`, `msToken`, `uifid`), TLS fingerprint impersonation, or the
  reference implementation's retry policy.
- Any claim about real CDN bytes, watermark state or playable output.
- Any change to 0074/0076/0080/0081 persisted semantics or migrations.
