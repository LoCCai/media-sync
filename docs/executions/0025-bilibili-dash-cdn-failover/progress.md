**English** | [中文](progress.zh.md)

# Execution 0025 progress

- Status: Frozen offline scope and documentation closeout complete
- Last updated: 2026-09-02
- Predecessor: `46905a50bbba19b7c4b74a0f7a274d5efdb013d6`
- Plan commit: `8e9467d2ecbedfd8f87e8d1d2ffb5a66d6d15591`
- Implementation commit: `fe45abcb7262c3d70437aff82a05609e43902af4`

## Completed

- [x] Reconciled the Execution 0024 closeout and audited the ephemeral target, component sidecar, strict resume, probe/mux/archive and recovery boundaries.
- [x] Verified that primary plus at most eight distinct backup candidates were already validated, repr-safe and runtime-only; audited pinned bili-sync-up ordering without modifying either checkout.
- [x] Added a DASH-only primary-first candidate pass for video and optional audio under the existing asset lock, component byte cap and shared total deadline.
- [x] Limited failover to candidate-local DNS, timeout, transport, interruption, HTTP status and Range incompatibility outcomes. Network-policy, header/encoding, chunk/size, filesystem, probe and mux failures remain immediate.
- [x] Reloaded partial state between candidates and required exact Range offset, total length and validator continuity. A partial survives mixed candidate failures; destructive restart occurs only after the complete candidate pass rejects it.
- [x] Preserved all-candidate `401`/`403` exhaustion as `locator_refresh_auth_expired`, returned only fixed redaction-safe errors otherwise and retained no URL, host or winning index.
- [x] Added 17 DASH-downloader unit cases covering primary short-circuit, ordered video/audio fallback, DNS fallback, exhaustion, fail-closed security/size limits, cross-candidate resume, partial preservation and whole-pass restart.
- [x] Extended the production integration composition so video primary `503` and audio primary `403` fall back independently to real local H.264/AAC components, then pass ffprobe → ffmpeg → final ffprobe → SHA-256 archive → Emby dual-stream publication and zero-work replay.
- [x] Proved signed primary/backup candidates and private play fields absent from retained SQLite, Job, runtime, work, archive and export artifacts.
- [x] Passed focused `466`, complete `1790 + 1 skip`, production-process, Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audit gates.
- [x] Created and pushed bilingual plan and implementation commits; aligned root truth documents for this closeout.

## Remaining outside this execution

Progressive backup failover, segmented progressive media, CDN sorting/racing/cache, fresh-detail retry, FLV, subtitles/danmaku, configurable quality policy and broader Bilibili/live qualification remain deferred; the broader seven-platform goal stays active.
