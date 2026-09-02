**English** | [中文](goal.zh.md)

# Execution 0014 goal

- Status: Offline frozen slice complete; every live qualification row remains `NOT_RUN`
- Started: 2026-08-31 06:25 +08:00
- Completed: 2026-08-31 06:59 +08:00
- Predecessor: Execution 0013 closeout commit `be979d6`
- Plan commit: `95c7082`
- Implementation commit: `c4ab537`

## Outcome

Close one ordinary Kuaishou single-video path with platform-specific offline evidence. Given one trusted Subscription and one normalized record with a valid `video_id`, exactly one `video_play_url` and an optional cover, prove that the existing stable MediaCrawler refresh locator resolves the current signed URL, downloads and probes deterministic bytes, publishes immutable archive blobs, and exports a playable primary `.mp4`, poster and metadata in the Emby/Jellyfin layout.

This execution qualifies an already composed product path and fixes only defects exposed by its contract/end-to-end tests. It does not invent a new locator schema, claim bounded Kuaishou creator pagination or treat offline mocks as live compatibility.

## Design basis

- The pinned MediaCrawler Kuaishou detail path accepts a pure video ID in `KS_SPECIFIED_ID_LIST`, parses it through `parse_video_info_from_url`, calls `get_video_info_task`, and writes `photo.id`, `photo.photoUrl` and optional `photo.coverUrl` as `video_id`, `video_play_url` and `video_cover_url`.
- media-sync already maps one valid play URL to `<video_id>:video:0`, an optional cover to `<video_id>:cover:0`, persists a query-free source hint plus stable `mediacrawler` `adapter_refresh`, and selects detail candidates by exact content/remote ID/kind/position/source hint. Execution 0014 must close one discovered gap: unknown query-key values in Kuaishou media URLs must also be removed from durable normalized raw metadata rather than relying only on the generic known-key redactor.
- The generic downloader, mandatory bounded video probe, SHA-256 archive and Emby layout already exist. Execution 0014 adds the missing locked-checkout and platform-composed evidence rather than duplicating these components.

## Acceptance

1. **Closed discovery shape** — one fixture record with a valid `video_id` and exactly one valid `video_play_url` emits one position-zero video Asset; a valid cover URL emits one position-zero cover. Remote IDs, MIME hints, stable source hints, locators and replay identity are asserted. Every durable raw copy of the Kuaishou play/cover URL is query- and fragment-free even for unknown parameter names. Missing or invalid required identity is quarantined.
2. **Pinned detail contract** — a real isolated fake checkout proves `platform=ks`, `CRAWLER_TYPE=detail`, raw-ID `KS_SPECIFIED_ID_LIST`, JSONL output, concurrency/comment/media-download switches, saved profile shape, bounded child framing and complete normal-success attempt cleanup. The returned record must bind the requested `video_id`.
3. **Exact refresh** — the runtime binds the Asset to one current Subscription/Account and accepts only one normalized candidate with the exact content, remote ID, kind, position and query-free origin/path hint. Query-only signature rotation is allowed in memory; missing, drifted or duplicate candidates fail with existing fixed locator errors.
4. **Transient URL boundary** — the signed URL may exist in the upstream's UUID-scoped temporary detail JSONL, bounded child frame, process memory and active HTTP request, but a successful call removes its exact attempt root before return. It is never written to stable SQLite source/locator/raw fields, archive names, Emby metadata, Job/SyncRun payloads or Git-visible files. Result and request `repr` remain non-disclosing.
5. **Default HTTP profile** — Kuaishou remains on the closed default request profile; the client sends no Cookie, Authorization or caller-controlled headers. DNS pinning, redirects, resume rules, response bounds and one adapter-only 401/403 re-resolution remain active. No unproven platform-specific header is added.
6. **Playable video and cover publication** — deterministic MP4 and image bytes pass the existing downloader; video receives mandatory controlled structural probing. Both assets finalize durably with immutable SHA-256 paths, and Emby layout contains the primary `.mp4`, poster, NFO and allowlisted source metadata.
7. **Replay and generation truth** — repeating ingestion with query-only URL rotation preserves Asset identity/generation and verified bytes; repeating download/export is `already_verified`/`already_exported` with no second detail, HTTP or probe. Host/path drift follows existing generation/reset or refresh-mismatch rules and is not silently accepted.
8. **Truthful qualification** — focused platform tests and complete repository gates pass before completion is claimed. Real login/session, creator pagination, detail/CDN traffic, platform bytes and Emby/Jellyfin server rows all remain `NOT_RUN`.

## Known identity and cleanup limitations

The durable identity is `<video_id>:video:0` plus a query-free source hint. If Kuaishou replaces bytes under the same video ID and origin/path while only query data changes, already-verified bytes do not automatically become stale. Conversely, a harmless CDN host/path move can require a new discovery generation or fail exact refresh. Detecting media replacement needs an upstream version/byte identity and is deferred.

The current detail runner reports a fixed failure when normal `rmtree` cleanup fails, but it does not yet provide the scheduled runner's full quarantine/incident/account-block protocol. Execution 0014 proves successful cleanup and records cleanup-failure hardening as follow-up; it does not claim zero retained credential material after an injected filesystem cleanup failure.

## Explicit exclusions

- Kuaishou galleries, live/paid/restricted/deleted media, multiple play URLs, audio, subtitles, comments and trustworthy creator profiles.
- Bounded upstream creator pagination; the pinned creator path traverses until `no_more`, so current use still requires `allow_full_history` plus outer watchdogs.
- Platform-specific CDN headers and every live qualification row.
