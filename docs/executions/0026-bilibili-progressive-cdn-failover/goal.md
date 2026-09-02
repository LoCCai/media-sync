**English** | [中文](goal.zh.md)

# Execution 0026 goal

- Status: Frozen offline scope delivered; live qualification remains `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0025 closeout `7cb84fc6c93b832492b95513d9cb6a9708ee6cc9`
- Plan commit: `0694934bc9230151a85c040a061d6e704dffc4fc`
- Implementation commit: `190488f77d1704492cc148b890d6f9ae16d84f84`
- Scope: Ordered, bounded primary-to-backup CDN failover for the already-supported single-segment Bilibili progressive `durl` shape

## Outcome

Preserve the current compatible single-page and 2–64-page progressive media shape while carrying each exact target CID's `durl[0].url` plus zero to eight validated `backup_url` candidates through the private detail bridge and runtime locator. Download primary first, then backups under one lock, deadline, byte limit, strict Range fence, probe, immutable archive and deterministic Emby lifecycle. Candidate values and the winning index remain ephemeral.

## Frozen acceptance boundary

1. The strict Bilibili play parser continues to accept exactly one `durl` segment. It requires one valid primary `url`, accepts absent or equivalent `backup_url`/`backupUrl` aliases, and validates at most eight distinct string backups through `ResolvedLocator`; malformed, conflicting, duplicate or primary-equal candidates fail closed.
2. Single-page and multipart private JSONL bridges carry backups only in bounded private fields. Normalization accepts both the historical primary-only bridge and the new primary-plus-backups bridge, returns one repr-safe `ResolvedLocator`, and recursively strips all private fields before durable raw metadata, SQLite or Job creation.
3. Generic resolved-locator downloading uses `ResolvedLocator.urls` in source order. A successful primary performs no backup DNS or HTTP work; each pass remains bounded by one primary plus at most eight backups and the existing shared `DownloadLimits.total_timeout_seconds`.
4. Candidate-local DNS, timeout, transport, interruption, HTTP-status and non-empty-partial Range incompatibility may advance. Forbidden/mixed network addresses, redirect/header/encoding, chunk/size, filesystem, probe, archive and publication failures remain immediate and never touch a later candidate.
5. Cross-candidate append requires the exact requested offset, total length and strong validator kind/value. Incompatible candidates cannot discard a valid partial while another candidate remains. Only complete-pass rejection may consume the existing bounded restart allowance and start from zero.
6. For an adapter-refresh locator, a pass in which every candidate returns `401`/`403` triggers the existing single fresh-detail re-resolution, then tries that new bounded candidate list once. A second all-auth pass returns `locator_refresh_auth_expired`; mixed exhaustion returns a fixed redaction-safe failure. Direct/no-refresh behavior remains unchanged.
7. A backup-delivered progressive MP4 still passes the exact Bilibili request profile, media probe, SHA-256 archive, primary/part Emby publication and zero-work replay. Retained SQLite, Job, runtime, work, archive, export, NFO/source and operator errors contain no signed candidate or winning index.
8. Existing no-backup progressive, DASH failover/mux, static media, interruption recovery, auth refresh and published-final recovery behavior remains compatible. Both pinned upstream checkouts stay unmodified and clean.

## Explicit exclusions

Multiple `durl` segments, FLV remux, configurable CDN sorting/scoring, parallel racing, cross-run bad-CDN caches, fresh-detail retry after mixed/non-auth exhaustion, subtitles/danmaku, pages above 64, broader Bilibili types, real Bilibili account/API/CDN bytes and real Emby/Jellyfin scan/playback remain deferred or `NOT_RUN`. This execution is reliability work on an existing shape, not a thirteenth frozen media shape or complete Bilibili support.
