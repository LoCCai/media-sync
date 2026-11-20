**English** | [中文](goal.zh.md)

# Goal: close the two Douyin selection gaps deferred by 0088

## Why this execution exists

[0088](../0088-code-review/verification.md) fixed 26 verified defects and
deliberately deferred four findings to their own executions, because each would
change behaviour frozen by 0076/0081/0083. This execution takes the two that
belong to 0083's Douyin selection and can be closed **without inventing facts**:

1. **The 8-entry `bit_rate` cap made the whole feature unreachable.** Upstream
   declares one entry per (quality × codec), so a realistic payload carries
   10–16 entries. Every such payload raised `douyin_media_field_invalid`, the
   shim swallowed it (`douyin_media.py:324-325`), and the pinned flattening was
   used unchanged — exactly what 0083 exists to prevent.
2. **The shim could write a URL its own reader rejects.** `validate_douyin_media_url`
   accepted a comma; `apply_douyin_media_selection` then persisted that URL into
   `video_download_url`, and `_dy_url_list(..., allow_scalar_commas=False)`
   returns `()` for any scalar containing one — so the work became an asset-less
   `TEXT` row instead of a `VIDEO`.

## Verified, not assumed

- A 12-entry payload (4 qualities × 3 codecs) reached `douyin_media_field_invalid`
  before this change and now ranks to the 2160×3840 entry.
- A 33-entry payload is still refused, so the bound remains fail-closed.
- A comma-bearing URL previously normalized to `kind=text` with zero assets;
  it is now refused at selection time.

## Deliberately still open

- **Kuaishou image-CDN allowlist.** No real Kuaishou CDN hostname appears
  anywhere in this repository, in the pinned upstream checkout, or in any
  fixture: a full-tree search for `yximgs`/`kwimgs`/`kwaicdn`/`kscdn`/`kuaishoucdn`
  returned zero hits. An allowlist cannot be derived from committed evidence,
  and inventing one would be a guess that fails closed on every real atlas.
  It needs one operator-captured real URL.
- **XHS plaintext `http`.** [0018's own verification](../0018-xhs-playable-video/verification.md)
  qualified "ordinary bounded HTTP/HTTPS" and its tests assert `http://…:80`
  is accepted, so the code matches its contract; the reviewer's claim that the
  docs promise HTTPS-only was inaccurate. Tightening it is a *documented
  capability* change to a frozen execution and needs an operator decision.
- **Animated images.** Only Kuaishou, Weibo and Zhihu gate image extensions
  (`.jpeg/.jpg/.png/.webp`); XHS, Tieba and Douyin do not, and the sniffed
  static-image gate (`application/downloads.py:44-45`) applies only to
  Tieba/Zhihu. So a GIF can still be published as a still on XHS and Douyin.

## Out of scope

- Any change to the pinned upstream files. Behaviour was re-derived from
  `.upstream/MediaCrawler/store/douyin/__init__.py:122-139` only.
- Deployment, login, or any platform request. Every live row stays `NOT_RUN`
  per [0087](../0087-operator-canary/qualification.md).
