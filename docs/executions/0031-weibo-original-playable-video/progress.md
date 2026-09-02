**English** | [中文](progress.zh.md)

# Execution 0031 progress

- Status: Frozen offline ordinary original playable-video scope implemented and gated; live rows remain `NOT_RUN`
- Date: 2026-09-02
- Plan commit: `1c79c6d` (documentation baseline)

## Delivered

1. The pinned Weibo store shim now also captures exactly one scalar `media_info.stream_url` from an ordinary, original, numeric-ID `mblog` whose `page_info.page_type` is exactly `video`, across the same exact-object store boundary as the 0016 image capture; retweets, non-video page types and drifted shapes capture nothing.
2. One new private `{"url"}` payload crosses the boundary with strict collision checks against the images field, joins the recursive pre-persistence strip set, and is bound to a closed URL validator (HTTPS `sinaimg.cn`/`*.sinaimg.cn`/`f.video.weibocdn.com` host, non-root case-insensitive `.mp4` path, no fragment/userinfo/port, signed query allowed).
3. `_normalize_wb` gained the frozen VIDEO branch: `ContentKind.VIDEO` with exactly one position-0 `{note_id}:video:0` VIDEO asset, failing closed on image-field co-presence, retained `page_info`, retweets, non-canonical identities and malformed payloads.
4. `AssetKind.VIDEO` joined the WB refresh support set, so the existing generic refresh binds the exact asset, re-captures the current signed URL in memory through one numeric-note detail child run and returns a DEFAULT-profile ephemeral locator while durable state keeps only the query-free hint.
5. Coverage: validator accept/reject matrix, shim capture matrix through the real child process, normalizer fail-closed outcomes, refresher drift outcomes, durable non-retention, and one production SQLite → detail refresh → mock DNS/HTTP → MP4 probe → SHA-256 archive → Emby `.mp4`/NFO/source composition with zero-work replay.

## Verification snapshot

See [`verification.md`](verification.md) for the exact commands, exit codes and gate outputs.

## Not done

`playback_list`/quality selection, posters, durations, retweets, GIFs, live/paid media, mixed media posts, broader pagination, CDN ranking/racing/cross-run cache and every live qualification row remain deferred or `NOT_RUN`.
