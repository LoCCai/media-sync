**English** | [中文](progress.zh.md)

# Execution 0036 progress

- Status: Frozen offline Weibo video-poster scope implemented and gated; live rows remain `NOT_RUN`
- Date: 2026-09-03
- Plan commit: `1ad49a7` (documentation baseline)

## Delivered

1. The Weibo store-shim video capture now also captures the closed `page_info.pic_info.pic_big.url` poster — HTTPS `sinaimg.cn`-family host, static extension, bounded path — only when the video itself (scalar or `playback_list`) captures first; absent, malformed, foreign or non-static posters capture video only.
2. One new private `{"url"}` poster field crosses with strict collision checks and recursive stripping; `_normalize_wb` materializes the `{note_id}:cover:0` COVER asset alongside VIDEO and quarantines malformed poster payloads.
3. `AssetKind.COVER` joined the WB refresh support set so the poster re-resolves through one exact numeric-note detail child run exactly like the video.
4. Coverage: real-child contract compositions (poster alongside the stream, foreign/animated/wrong-extension drift capturing video only) and integration compositions proving the two-asset normalize → ingest → refresh → download → archive → Emby poster publication with zero-work replay and durable non-retention.

## Verification snapshot

See [`verification.md`](verification.md) for the exact commands, exit codes and gate outputs.

## Not done

Alternate poster sizes, GIF/animated posters, retweets, live/paid media and every live qualification row remain deferred or `NOT_RUN`.
