**English** | [中文](goal.zh.md)

# Execution 0031 goal

- Status: Frozen offline ordinary original playable-video scope complete; live rows remain `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0030 closeout `e242b16097b2fb1f0f6ee1dc8e863ace1c68ab32`
- Scope: One ordinary original numeric-ID Weibo post carrying an `mblog.page_info` video, captured at the pinned-store boundary and delivered as one playable Emby MP4 through a signed-URL adapter refresh
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Outcome

1. Extend the pinned Weibo store shim to capture exactly one scalar `media_info.stream_url` from an ordinary, original (non-retweet) numeric-ID `mblog` whose `page_info.page_type` is exactly `video`, before the locked store flattens it away.
2. Persist one private `{"url"}` payload under a media-sync-owned field with strict collision checks, recursive stripping before persistence, and a closed URL validator (HTTPS `sinaimg.cn`/`*.sinaimg.cn`/`f.video.weibocdn.com` host, non-root `.mp4` path, no fragment/userinfo, signed query allowed).
3. Normalize the post as `ContentKind.VIDEO` with exactly one position-0 VIDEO asset `{note_id}:video:0`, failing closed on retweets, image-field co-presence, malformed payloads and ineligible identities.
4. Extend the lazy adapter refresh to Weibo VIDEO assets: one exact numeric-note detail run re-captures the current signed URL in memory and returns a DEFAULT-profile ephemeral locator; the persisted durable state keeps only the query-free hint.
5. Download through the existing bounded candidate pass with structural MP4 probing, SHA-256 archival and deterministic Emby `.mp4`/NFO/source publication, with zero-work replay.
6. Prove one production SQLite → detail refresh → mock HTTP → ffprobe → archive → Emby composition while every real account/API/CDN/media-server row stays `NOT_RUN`.

## Acceptance boundaries

- Exactly one video per post, sourced only from the closed `page_type == "video"` + scalar `stream_url` shape; `playback_list` arrays, quality variants, posters, durations, retweets, live/paid media and mixed image+video posts are not claimed.
- Image-only posts keep the 0016 semantics byte-compatible; a post carrying both private fields fails closed.
- The signed query exists only in the ephemeral child frame, process memory and HTTP request; durable assets, raw envelopes, jobs, archives and exports retain no query-bearing URL.
- No database schema or migration; stable Asset identity and the frozen media-shape count do not change. `.upstream` remains read-only and untracked.

## Explicitly deferred

`playback_list`/quality selection, video posters and durations, retweets, GIFs, live/paid media, mixed media posts, broader Weibo pagination, CDN ranking/racing/cross-run cache, subtitles/danmaku, pages above 64, REST/production packaging and every live qualification row remain outside this execution.
