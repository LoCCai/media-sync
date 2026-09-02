**English** | [中文](goal.zh.md)

# Execution 0025 goal

- Status: Frozen offline scope delivered; live qualification remains `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0024 closeout `46905a50bbba19b7c4b74a0f7a274d5efdb013d6`
- Plan commit: `8e9467d2ecbedfd8f87e8d1d2ffb5a66d6d15591`
- Implementation commit: `fe45abcb7262c3d70437aff82a05609e43902af4`
- Scope: Ordered, bounded primary-to-backup CDN failover for the already-selected ephemeral Bilibili DASH video and optional audio components

## Outcome

Turn the validated but unused DASH backup URLs delivered by execution 0024 into a closed download lifecycle. Each selected video/audio component tries its primary URL and then at most eight validated backups in source order under the existing asset lock, total deadline, byte limit, request profile and structural gates. A partial component may cross candidates only when strict Range, total-length and strong-validator evidence proves byte continuity. No candidate URL, selected index or remote failure detail becomes durable.

## Frozen acceptance boundary

1. Failover applies only to `ResolvedDashLocator.video` and optional `.audio`. Each component uses the existing `ResolvedLocator.urls` order: primary first, followed by zero to eight distinct validated backups; a primary success performs no backup DNS or HTTP work.
2. One candidate pass is bounded by the existing component candidate count and one shared `DownloadLimits.total_timeout_seconds`. Candidate-local DNS, transport, interruption, HTTP status and Range incompatibility failures may advance to the next candidate; security-policy, header/encoding, chunk/size, filesystem, probe and mux failures fail immediately.
3. A candidate may append to an existing partial only with the exact existing validator kind/value, total length and requested offset. A candidate that returns full `200`, incompatible `206` or incompatible `416` for a non-empty partial cannot discard that evidence before later candidates are tried. Only after every candidate is incompatible may the existing bounded restart policy discard the partial and start a fresh candidate pass.
4. `401`/`403` are candidate-local while another URL remains. If every attempted candidate in a pass returns `401`/`403`, the existing redaction-safe `locator_refresh_auth_expired` result is preserved; otherwise exhaustion returns the last eligible redaction-safe failure without URL or host disclosure.
5. Video and audio fail over independently. A successful backup component still undergoes the same structural probe, combined byte cap, fixed bounded `ffmpeg -c copy`, final probe, SHA-256 archive publication and deterministic Emby/Jellyfin export as a primary component.
6. Signed primary/backup URLs remain repr-safe and runtime-only. SQLite, Job payloads, partial sidecars, archive/export metadata, retained runtime trees, exceptions and operator-facing output retain neither candidate values nor the winning candidate index.
7. Existing no-backup, silent DASH, progressive single-/multi-page, failed-mux and published-final recovery behavior remains compatible. Both pinned upstream checkouts remain unmodified and clean.

## Explicit exclusions

Progressive `durl` backup failover, multiple progressive segments, configurable CDN sorting/scoring, parallel racing, cross-run bad-CDN caches, fresh-detail retry after candidate exhaustion, FLV, subtitles/danmaku, pages above 64, real Bilibili account/API/CDN behavior and real Emby/Jellyfin scan/playback remain deferred or `NOT_RUN`. This execution does not claim complete Bilibili or general-purpose CDN failover support.
