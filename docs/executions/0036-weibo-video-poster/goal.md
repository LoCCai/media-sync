**English** | [中文](goal.zh.md)

# Execution 0036 goal

- Status: Frozen offline Weibo video-poster scope complete; live rows remain `NOT_RUN`
- Date: 2026-09-03
- Predecessor: Execution 0035 closeout `5a27e99949c54a5032454d91b8809d28afad7086`
- Scope: The poster of an ordinary original Weibo video post — `page_info.pic_info` — captured alongside the 0031/0035 stream URL and delivered as one COVER asset with adapter refresh and Emby poster publication
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Outcome

1. Extend the pinned Weibo store-shim video capture with a closed poster pass: `page_info.pic_info.pic_big.url` must be one HTTPS static-image URL on a `sinaimg.cn`-family host with a bounded path; the video shape (scalar or `playback_list`) must itself capture first, and a video without a valid poster captures video only.
2. Carry the poster under one new private `{"url"}` field with strict collision checks against every existing Weibo private field, recursive stripping before persistence, and normalizer materialization of the existing `{note_id}:cover:0` COVER asset alongside the VIDEO asset.
3. Add `AssetKind.COVER` to the WB refresh support set so the poster re-resolves through one exact numeric-note detail child run like the video, closing path drift fail-closed.
4. Publish the poster as the Emby episode poster while the video stays the main media, with zero-work replay and durable non-retention of signed queries.
5. Prove contract compositions through the real child (poster alongside scalar and playback-list video, poster drift closure) plus one integration SQLite → refresh → download both assets → archive → Emby replay.

## Acceptance boundaries

- Only the exact `pic_info.pic_big.url` scalar grants the poster; URL suffixes, response MIME and downloaded bytes cannot influence it, and a poster without a capturable video is ignored.
- Posts without `pic_info`, with malformed nested shapes, foreign hosts or non-static extensions capture video only, byte-compatible with 0031/0035.
- No database schema or migration; stable Asset identity does not change. `.upstream` remains read-only and untracked.

## Explicitly deferred

Alternate poster sizes (`pic_orig` and friends), GIF/animated posters, retweets, live/paid media and every live qualification row remain outside this execution.
