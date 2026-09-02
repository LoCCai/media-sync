**English** | [中文](goal.zh.md)

# Execution 0018 goal

- Status: Offline execution complete; live qualification remains `NOT_RUN`
- Date: 2026-09-01
- Predecessor: Execution 0017 closeout commit `00add11`
- Plan commit: `c9d3586`
- Implementation commit: `356e254`
- Scope: Automatic XHS ordinary single playable video with optional static artwork

## Outcome

Execution 0018 extends the exact XHS author-Subscription authority path delivered in Execution 0017 from static notes to one ordinary `type="video"` note. A bounded creator lookup reacquires the target note and selects exactly one current XHS CDN video locator in memory. Independently, an embedded real H.264 MP4 passes the production bounded `FFprobeMediaProbe`; the deterministic composition archives controlled media bytes by immutable SHA-256 identity and publishes a playable `.mp4` plus optional static artwork and metadata in the existing Emby/Jellyfin layout.

The frozen offline shape accepts exactly one VIDEO Asset at position zero and at most one ordered IMAGE Asset used as artwork. The source row must remain `type="video"`; a video-only row becomes `ContentKind.VIDEO`, while one cover plus one video may remain `ContentKind.MIXED`. Multiple or malformed raw candidates, non-XHS initial media locators and identity drift fail closed.

## Why this slice

- Locked upstream `store/xhs/__init__.py` natively emits `video_url`: for `type="video"`, it prefers `video.consumer.origin_video_key`/`originVideoKey` and constructs `http://sns-video-bd.xhscdn.com/<key>`; otherwise it returns `video.media.stream.h264[].master_url`. No integration shim or upstream edit is required.
- media-sync already normalizes XHS VIDEO Assets, supports XHS video refresh, mandatory video probing, SHA-256 archives and Emby primary-video publication. Execution 0017 deliberately blocked only the automatic creator-video target gate.
- Tieba's locked `TiebaNote` contains no media field; media is discarded while extracting first-floor text. Zhihu's locked `ZhihuContent` likewise discards answer/article HTML media and nested playable-video data before JSONL. Both can be future shim slices, but neither is as direct or as evidence-complete as XHS video.
- Upstream downloads XHS note media with a plain GET and no platform headers. The existing `MediaRequestProfile.DEFAULT` is therefore the truthful offline profile until live evidence requires a dedicated one.

## Acceptance boundary

1. The creator result contains exactly one matching source row. Before trusting normalized Assets, its raw `video_url` must be an ordinary scalar string containing exactly one candidate and raw `image_list` must be an ordinary scalar string containing zero or one candidate. Empty segments, surrounding whitespace, duplicates, mixed valid/invalid candidates and container drift fail closed rather than being silently filtered or deduplicated.
2. The row is `type="video"`, has exactly one VIDEO Asset at position zero, has zero or one IMAGE Asset, contains no other Asset kind, maps raw candidates one-to-one to those Assets, and retains exact content/author/source-hint identity. Initial media locators are ordinary `http` or `https`, have no userinfo, scheme-mismatched/non-default port or fragment, use a non-root path, and normalize to `xhscdn.com` or a subdomain after lowercase/IDNA/trailing-dot handling. Explicit default `http:80` and `https:443` ports are accepted. Redirect targets remain governed by the existing per-hop public-network policy; this execution does not claim XHS-only redirect destinations.
3. Exact Subscription creator authority, bounded lookup, preflight-before-mutation, explicit note override precedence and valid VERIFIED zero-secret replay remain unchanged from Execution 0017.
4. A real embedded H.264 MP4 independently passes the production `FFprobeMediaProbe`. The deterministic composition sends controlled MP4 plus optional PNG bytes through mock public DNS/HTTP, `MediaRequestProfile.DEFAULT`, a recording probe, SHA-256 archives and idempotent Emby `.mp4`/poster/NFO/source publication. Query-only replay performs no second detail, HTTP, DNS, probe, archive or export call.
5. Signed creator/note authority and media query values remain transient; media fragments are rejected before download and never persisted. Durable XHS raw and Asset hints stay query-free, completed attempt roots are removed, and `.upstream` remains unmodified and untracked. The frozen creator-video gate applies only to automatic creator fallback; the existing explicit exact-note compatibility path remains outside this new qualification claim.

## Explicit exclusions

- Real QR/Cookie login, creator/feed/detail traffic, real XHS CDN bytes and real Emby/Jellyfin scan/playback remain `NOT_RUN` without user credentials and services.
- More than one cover/image, multiple video variants, broader mixed-media shapes, H.265/AV1 selection, DASH/HLS manifests, live photo, animation, audio extraction, subtitles, comments, media-version replacement and platform-specific headers remain deferred.
- Tieba/Zhihu media shims, creator pagination hardening, authority-expiry recovery and cross-Asset refresh caching remain future work. The broader seven-platform goal stays active.
