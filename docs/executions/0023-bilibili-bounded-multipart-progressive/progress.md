**English** | [中文](progress.zh.md)

# Execution 0023 progress

- Status: Frozen offline scope and documentation closeout complete
- Last updated: 2026-09-02
- Predecessor: `27e45c89f20e8eb6bc871ab1505fe25167b70ae3`
- Plan commit: `bd45478b28cc61a7f35b6211faf3a0fc1eb94138`
- Implementation commit: `24fd41c600eb30fb2df22079e3cf52778589959e`

## Completed

- [x] Reconciled a clean local/tracking/GitHub `main` at Execution 0022 closeout.
- [x] Audited current normalizer, detail child, refresh, downloader, archive and Emby multipart layout boundaries.
- [x] Audited pinned MediaCrawler `View.pages`/`get_video_play_url(aid,cid)` and bili-sync-up PageInfo/DASH/ffmpeg behavior.
- [x] Split bounded multi-P progressive from the later DASH derivative lifecycle and froze the 2–64 page acceptance boundary.
- [x] Added a verified, task-local forward shim that captures canonical 1–64 `page`/`cid` pairs before the pinned store drops them; malformed, duplicate, non-contiguous and 65-page declarations fail closed.
- [x] Preserved exact single-page `<aid>:video:0` compatibility and emitted ordered `<aid>:video:cid:<cid>` locator-only VIDEO Assets for qualifying 2–64-page uploads.
- [x] Upgraded the strict detail protocol to v4 with `bili_video_cid`; each refresh requests only its target CID and binds the complete current VIDEO sibling tuple.
- [x] Rejected missing, added, reordered, replaced, duplicated or malformed current page tuples before URL return; recursively stripped private page/play fields and signed URLs before persistence.
- [x] Proved a three-page SQLite → targeted detail → Bilibili-profile DNS/HTTP → probe → SHA-256 archive → Emby primary/two-part/NFO/source composition with distinct bytes.
- [x] Proved query-only replay performs zero new detail, DNS, HTTP, probe, archive or export work.
- [x] Focused regression passed `436 passed in 53.96s`; complete suite passed `1739 passed, 1 skipped in 321.25s`; all quality/build/docs/upstream/audit gates passed.
- [x] Pushed implementation `24fd41c`; local, tracking and GitHub `main` reconciled.

## Remaining outside this execution

DASH mux and recovery, segmented progressive media, subtitle/danmaku, backup failover, broader Bilibili types and all authenticated/live qualification rows remain deferred or `NOT_RUN`; the broader goal stays active.
