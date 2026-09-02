**English** | [中文](goal.zh.md)

# Execution 0023 goal

- Status: Frozen offline scope delivered and verified; live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0022 closeout `27e45c89f20e8eb6bc871ab1505fe25167b70ae3`
- Plan commit: `bd45478b28cc61a7f35b6211faf3a0fc1eb94138`
- Implementation commit: `24fd41c600eb30fb2df22079e3cf52778589959e`
- Scope: Two through 64 ordered pages in one ordinary numeric-aid Bilibili upload, with one progressive stream per page

## Outcome

Extend the delivered logical-first-page Bilibili video without weakening its exact single-page compatibility boundary. A qualifying ordinary upload with 2–64 pages becomes one VIDEO content row plus the same number of ordered locator-only VIDEO Assets. A verified shim carries stable `page`/`cid` identities across the pinned MediaCrawler store-loss boundary, exact detail refresh resolves only the requested CID while binding the complete current page tuple, and the existing bounded downloader/archive/Emby pipeline publishes every verified page deterministically.

## Frozen acceptance boundary

1. The existing exact-one-page identity `<aid>:video:0` remains compatible. A valid 2–64 page capture uses ordered, distinct positive CIDs and stable `<aid>:video:cid:<cid>` identities at positions `0..N-1`.
2. The forward child captures only non-secret `page` and `cid` values before the pinned Bilibili store discards them. Private capture fields and signed play URLs are recursively removed before persistence.
3. Refresh loads the complete persisted VIDEO sibling tuple, passes the target CID through the strict child protocol, requires the current detail tuple to match in size, order and identity, and accepts exactly one progressive `durl` for that CID. Missing, added, reordered, replaced, duplicated or malformed pages fail closed.
4. Offline composition proves at least three pages with distinct bytes, targeted detail calls, Bilibili request profiles, SHA-256 archives, deterministic Emby primary/part media plus NFO/source files, and query-only replay with zero new detail/DNS/HTTP/archive/export work.
5. The pinned upstream checkouts remain read-only and clean; the integration is implemented only in `media-sync`.

## Explicit exclusions

DASH audio/video selection and mux, multiple `durl` segments, subtitles, danmaku, backup-URL failover, FLV remux, more than 64 pages, bangumi/paid/live media, real account/CDN behavior and real Emby/Jellyfin scanning remain deferred or `NOT_RUN`. This execution does not claim complete Bilibili media support.
