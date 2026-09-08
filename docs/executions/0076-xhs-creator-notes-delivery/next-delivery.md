**English** | [中文](next-delivery.zh.md)

# Next delivery: qualify XHS locally on the deployment before another platform

## Status

**PLANNED ONLY. Execution 0077 is not started.** This document records the next authorized order of work; it does not authorize a deployment, platform request, supervisor restart or new implementation by itself.

## Ordered scope

1. **Publish and rebuild exactly.** Pull the published 0076 revision, back up the SQLite database plus managed credentials and `/data`, verify the locked upstream, then rebuild and force-recreate the API container. Apply migration `0015_xhs_creator_notes` through normal startup. Keep the supervisor stopped initially.
2. **Match API and supervisor configuration.** Set the same `MEDIA_SYNC_XHS_SCAN_CONTINUATION_DELAY_SECONDS` in both services. Default `300` is appropriate for a bounded canary; `0` disables only fast pacing and uses the ordinary Subscription interval. Keep `/data/archive`, `/data/library`, `/data/jobs`, `/data/state` and the MediaCrawler runtime mounts identical.
3. **Run one low-volume manual canary.** Use the native `/crawler/` login, wait for the process to become idle, adopt the saved XHS session into one Account, and create one paused creator Subscription whose protected creator URL matches the selected author. Resume only that Subscription and use exact execution while the resident supervisor is stopped.
4. **Inspect every durable step.** Confirm one source page per unit, retained page-tail progress, exact Job/Run/pipeline IDs, no token/cursor in API or log output, and honest partial/blocked codes. Do not induce a ban; if access restriction occurs naturally, stop automation and verify that it is `blocked`, not source end.
5. **Verify directory delivery without server control.** Confirm downloaded bytes, SHA-256 archive, XHS platform directory, NFO and sidecars through the host mount. A media-server API is not required. An optional Emby/Jellyfin read/scan check is a separate qualification and cannot replace tree inspection.
6. **Qualify restart and scheduling.** After a clean manual unit, restart the API once and prove the same cursor continues. Restore the supervisor only after that proof, observe one scheduled continuation at the configured delay, then stop it if any scope, auth, directory or diagnostic evidence is ambiguous.
7. **Record exact evidence.** Add a bilingual qualification record with deployed SHA/image identity, redacted account/subscription IDs, commands, timestamps, directory tree facts and explicit `PASS`/`FAIL`/`NOT_RUN` rows. Never paste Cookies, creator tokens, opaque cursors or raw platform responses.

## Acceptance evidence

- The deployed image reports the published revision and migration `0015` is present.
- API and supervisor expose identical XHS continuation delay values.
- At least two bounded units continue the same Subscription without page-tail loss or duplicate publication.
- One compatible note reaches archive and the configured directory/NFO tree; an unchanged replay writes no new content bytes.
- Restart preserves the exact cursor and ownership chain.
- Any partial, empty-stalled or access-restricted outcome is visible under its fixed code and never counted as source-end completion.

## Stop conditions

- Stop immediately on authentication ambiguity, a creator-identity mismatch, unexpected full-history scanning, token/cursor disclosure, migration inconsistency, directory permission failure or unexplained Job/Run divergence.
- Do not automatically retry a restricted account and do not resume unrelated subscriptions.
- Do not call the historical baseline complete merely because one live response returned `has_more=false`; record it as time-bound source evidence.

## Following platform

After the XHS canary is documented, trace the pinned Douyin creator-work source path before freezing its own durable delivery execution. The next design must derive `has_more`, cursor, aweme identity, detail/media authority, risk-control and page-tail behavior from Douyin code and fixtures. It must not copy Bilibili page numbers or XHS token semantics. No Douyin implementation begins from this document alone.
