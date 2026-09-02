**English** | [中文](goal.zh.md)

# Execution 0024 goal

- Status: Frozen offline scope delivered; live qualification remains `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0023 closeout `d4c9941d2d5fb1206cd9b1a60ce2cc344a9e66e3`
- Plan commit: `a7d038e383c76f2c29825c6f42ac7ff29b967693`
- Implementation commit: `12314b927dcaac97dc9ae184c03f98153f3ef687`
- Scope: Ordinary numeric-aid Bilibili single-page and 2–64-page DASH video/audio selection, bounded component download, ffmpeg stream-copy mux and existing Emby/Jellyfin publication

## Outcome

Extend the delivered Bilibili progressive path with a durable DASH lifecycle rather than a parser-only result. For each unresolved Bilibili VIDEO Asset, the exact target CID is refreshed against the complete persisted page tuple, the best supported video and optional audio streams are selected in memory, generation-scoped components are downloaded and structurally verified, ffmpeg stream-copies them into one verified media file, and only that final file enters the immutable SHA-256 archive and Emby/Jellyfin tree. Existing single-progressive behavior remains compatible.

## Frozen acceptance boundary

1. The strict detail child requests `/x/player/wbi/playurl` with WBI signing, `avid`, the exact target `cid`, `qn=127`, `fourk=1`, `fnval=4048` and `platform=pc`. The complete current 1–64 page tuple must still match persisted VIDEO siblings before any target is returned.
2. A DASH result selects the highest supported video quality from `16,32,64,80,112,116,120,125,126,127`, then prefers AVC, HEVC and AV1 in that order at equal quality. It selects the highest supported ordinary, Dolby or Hi-Res audio using the pinned bili-sync-up ordering; no audio is a valid silent-video shape.
3. Signed primary/component URLs and private play fields remain ephemeral and repr-safe. They are stripped before normalized raw persistence and never written to SQLite, job payloads, archive metadata, export metadata or retained runtime trees.
4. DASH video and optional audio use distinct generation-scoped resumable work files beneath the existing exact asset lock. Each component is structurally probed, their combined bytes remain within the asset limit, ffmpeg runs with fixed argv, bounded time/output and `-c copy`, and the muxed result is probed again before archive publication.
5. Crash/retry behavior is closed: incomplete mux output is never published, verified components may resume, a published final blob plus prepared final sidecar can recover database finalization without detail/DNS/HTTP/ffmpeg work, and outward success cleans final/component work state.
6. A DASH result with audio publishes one muxed VIDEO Asset; a silent DASH result publishes one remuxed VIDEO Asset; a progressive `durl` result continues through the existing downloader unchanged. Single-page and 2–64-page Emby primary/part naming stays deterministic.
7. The pinned upstream checkouts remain unmodified and clean. All implementation belongs to `media-sync`, with source/unit/contract/integration evidence and bilingual local Git history pushed to GitHub.

## Explicit exclusions

Backup-CDN failover, multiple progressive `durl` segments, FLV remux, subtitles, danmaku, configurable quality policy, pages above 64, bangumi/paid/live media, real account/API/CDN behavior and real Emby/Jellyfin scan/playback remain deferred or `NOT_RUN`. This execution does not claim complete Bilibili support.
