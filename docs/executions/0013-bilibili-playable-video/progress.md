**English** | [中文](progress.zh.md)

# Execution 0013 progress

- Status: Offline implementation and closeout gates complete; live qualification remains `NOT_RUN`
- Started: 2026-08-31 05:12 +08:00
- Completed: 2026-08-31 06:05 +08:00
- Plan commit: `46323bd`
- Implementation commit: `dd6cfec`

## Implemented

- Bilibili ordinary-video discovery now emits one stable locator-only `video` Asset at position `0`, with remote ID `<aid>:video:0`, `source_url=NULL` and the existing `mediacrawler` `adapter_refresh` locator. Dynamic records do not synthesize that Asset; replay preserves identity and generation. No schema migration was required.
- The nullable-source exception is closed to one exact shape: `platform=bili`, content remote type `content`, kind `video`, position `0`, remote ID `<aid>:video:0`, and a `NULL` source hint. Near-miss shapes and non-null hints fail as `locator_refresh_configuration_invalid` before secret resolution or child construction.
- The isolated detail child validates the requested numeric aid against `View.aid`, selects and validates the logical first CID (`pages[0].cid`, with the validated `View.cid` compatibility fallback only when pages are absent or empty), calls the pinned play-url task, and accepts exactly one valid primary `durl.url`.
- Play-url absence or call failure is retryable `locator_refresh_temporary`; DASH-only, empty or multi-segment `durl` is fixed `locator_refresh_unsupported`; identity drift and malformed responses are fixed `locator_refresh_result_invalid`. Bilibili cover refresh remains independent of progressive lookup.
- The signed URL crosses only a repr-safe private result, bounded child frame, in-memory JSONL bridge and active HTTP request. The bridge rejects private-field collisions before normalization. The detail-only normalizer gate defaults off and, when explicitly enabled, recursively removes the accepted private field before retaining Content/Asset raw metadata; the attempt JSONL tree is never rewritten with the URL.
- `ResolvedLocator` now carries the closed `BILIBILI_MEDIA` request profile. The bounded HTTP client supplies fixed browser-like User-Agent, Bilibili Referer and Origin, accepts only Range/If-Range resume state, and rejects Cookie, Authorization and arbitrary caller headers. Redirect, resume, DNS pinning, response bounds and one 401/403 URL re-resolution preserve the profile.
- The offline end-to-end test composes synthetic MediaCrawler metadata, Subscription-bound refresh, deterministic mock CDN bytes, controlled MP4 probing, SHA-256 archive publication, durable Asset/Job finalization and Emby/Jellyfin layout publication. The verified `.mp4` is the episode primary media, NFO/source metadata is emitted, and replay is `already_verified`/`already_exported` without another detail, HTTP or probe call.
- Independent review closed two findings: a missing Bilibili detail result is retryable rather than permanent `asset_not_found`, and a non-null Bilibili video hint cannot bypass predecessor source-hint constraints. No further actionable finding remained.
- The final focused gate passed `223` tests; the complete suite passed `1199` tests with one Windows-inapplicable skip. Lint, format, strict typing, documentation, pinned-upstream, build, patch and exact ephemeral-marker audits passed. Exact commands and counts are in `verification.md`.

## Known limitation

Forward discovery metadata contains no CID, so the durable identity is the logical `<aid>:video:0` slot. An unresolved lookup validates the current first CID, but if Bilibili later replaces that CID under the same aid, already-verified bytes do not automatically become stale and the Asset generation is not bumped. CID-aware discovery, replacement invalidation and multi-page identity remain one future unit of work.

## Remaining outside execution 0013

- Bilibili DASH audio/video selection and muxing, FLV remux, multi-`durl` concatenation, multi-page discovery/download, subtitles, danmaku, backup-URL failover, and bangumi/paid/live media.
- Downloadable primary media for the remaining crawler platforms where current normalization still yields metadata or cover-only results, plus broader automatic creator-authority bootstrap such as XHS multi-note lookup.
- REST/API management surface, deployment packaging/service integration, and cross-host/HA operation.
- Real QR/saved-session login, creator synchronization, signed CDN transfer and Emby/Jellyfin scan/playback qualification for all seven platforms. Every such row remains `NOT_RUN`; offline mocks do not promote them.
