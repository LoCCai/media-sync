**English** | [中文](goal.zh.md)

# Execution 0013 goal

- Status: Offline frozen slice complete; every live qualification row remains `NOT_RUN`
- Started: 2026-08-31 05:12 +08:00
- Completed: 2026-08-31 06:05 +08:00
- Predecessor: Execution 0012 closeout commit `7c6f567`
- Plan commit: `46323bd`
- Implementation commit: `dd6cfec`

## Outcome

Deliver the first offline-proven playable Bilibili slice: one ordinary `aid`-backed upload contributes a refreshable first-page, single-segment progressive video Asset; the existing durable pipeline resolves its current signed URL, downloads and probes the bytes, and publishes the primary video plus metadata in the existing Emby/Jellyfin layout. Signed URLs and account credentials remain ephemeral, while unsupported DASH, split streams and multipart shapes fail explicitly instead of being treated as playable.

## Design basis

- The pinned MediaCrawler client exposes `get_video_info(aid|bvid)` and the WBI-signed `/x/player/wbi/playurl` request with `avid`, `cid`, configured `qn`, `fourk=1`, `fnval=1` and `platform=pc`; its current downloader follows `View.aid` plus `View.cid` and consumes only `durl`.
- The pinned bili-sync-up source proves that Bilibili media downloads require a browser-like User-Agent and Bilibili Referer even when no Cookie is sent to the CDN. It also provides the later DASH/multi-page design reference, but execution 0013 does not copy or claim those wider capabilities.
- MediaCrawler remains an optional, separately obtained, license-gated external research runtime. No upstream source is vendored or copied.

## Acceptance

1. **Locator-only discovery identity** — normalizing a Bilibili video metadata record emits exactly one position-zero `video` Asset in addition to its cover. That logical first-page slot uses stable remote ID `<aid>:video:0`, a `NULL` source URL and the existing `mediacrawler` `adapter_refresh` locator; it never persists a page URL or play URL as media. Replay keeps the same Asset identity and generation without a schema migration.
2. **Exact first-page lookup** — the detail child binds the stored numeric `aid` to the returned `View.aid`, selects the first page CID (`pages[0].cid` when present, otherwise the validated `View.cid` compatibility field), and invokes the pinned client's play-url method under the existing account, watchdog and license boundaries. Drift, missing IDs or malformed shapes fail closed.
3. **Single-segment progressive contract** — only a `durl` response containing exactly one valid HTTP(S) primary URL is accepted. DASH-only, empty, multi-segment or malformed responses return fixed unsupported/invalid outcomes; they are never partially downloaded or mislabeled as complete media. Backup URL failover is deferred.
4. **Memory-only locator and fixed Bilibili request profile** — the signed play URL exists only in a typed private detail result, the bounded child frame, process memory and the active HTTP request. It is added to normalized detail bytes only in memory under an explicit detail-only gate, removed from retained raw metadata, and never written to the attempt JSONL tree. The resolved locator selects a closed Bilibili header profile containing fixed non-secret User-Agent, Referer and Origin values. Cookie and arbitrary caller headers cannot enter CDN requests; resume, redirect, DNS pinning and byte/time/header limits remain enforced.
5. **Durable playable pipeline** — an offline integration composes MediaCrawler metadata ingestion, exact Subscription-bound refresh, deterministic HTTP bytes, mandatory video probing, archive publication, Asset/Job finalization and Emby export. The primary verified video is installed as the episode media file and replay is idempotent.
6. **Fixed failure and recovery behavior** — play-url fetch failure remains retryable, unsupported progressive shape is distinguished from transient failure, 401/403 may use the existing single adapter re-resolution, and no failed path mutates the stable locator into a signed direct URL.
7. **Truthful exclusions** — DASH video/audio selection and muxing, FLV remux, multi-segment concatenation, multiple pages, subtitles, danmaku, paid/bangumi/live media, backup-URL failover and real account/CDN/Emby qualification are outside this execution. All live rows remain `NOT_RUN`.
8. **Closed verification** — focused normalization/detail/refresh/network/downloader/pipeline/Emby tests, the full suite, lint, formatting, typing, docs/upstream checks, build, patch checks and retained-artifact/secret audits must pass before completion is claimed.

## Identity limitation

The discovery JSONL does not contain a CID, so execution 0013 models “the current logical first page of this aid” as `<aid>:video:0`. It verifies the current first CID during each unresolved detail lookup but cannot automatically invalidate already-verified bytes if Bilibili later replaces the first-page CID under the same aid. CID-aware discovery, generation replacement and multi-page identity are deferred together; the limitation must remain documented rather than hidden.
