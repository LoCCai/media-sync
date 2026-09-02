**English** | [中文](progress.zh.md)

# Execution 0027 progress

- Status: Frozen offline scope and implementation verification complete
- Last updated: 2026-09-02
- Predecessor: `245e8e377761ee8343b33f581dfcd27295eac532`
- Plan commit: `ec7095a9cc5e85fda1aee66f256eb16345c1294a`
- Implementation commit: `7f99aa480328a25b7e9c2acc8a9c2234128e7b74`

## Implemented

- [x] Reconciled Execution 0026, audited both pinned upstreams without modifying them, and froze a no-migration, exactly-one-segment, stream-copy-only contract.
- [x] Upgraded the bounded detail protocol to v7 and classified only an explicit closed top-level playback `format`: absent/`None` and MP4 remain ordinary progressive, FLV creates a typed target, while unknown, mixed and malformed values fail closed.
- [x] Added repr-safe `ResolvedFlvLocator`, single-page and multipart private format bridges, collision detection and recursive stripping; historical primary-only and primary-plus-backup payloads remain compatible.
- [x] Allowlisted structurally probed video-bearing FLV and added fixed non-shell single-input ffmpeg remux arguments selecting the first video plus optional first audio stream, with timeout, output, media-size and file-identity bounds.
- [x] Added a generation-scoped `bili-flv-source` store and downloader branch reusing ordered primary/backups, strict Range/validator continuity, whole-pass restart and one all-auth adapter refresh; refresh type drift fails closed.
- [x] Required the source to probe exactly as FLV video and the final exactly as MP4 video; only the final MP4 reaches SHA-256 archive/Emby, while remux/final-probe failure retains the verified source and discards an unprepared final.
- [x] Preserved published-final recovery and cleanup across source/final stores, and added focused coverage for locator/profile/repr, format bridges, FLV probe, exact remux argv, candidate/auth behavior, type/container drift, source retention and recovery.
- [x] Added a real local H.264+AAC FLV composition: SQLite → exact detail → primary `503` → backup FLV → production ffprobe → production ffmpeg stream-copy → final ffprobe → SHA-256 MP4 archive → Emby MP4/NFO/source; replay adds zero detail/DNS/HTTP/probe/ffmpeg/archive/export work.
- [x] Passed focused `394`, Bilibili compositions `4`, complete `1848 + 1 skip`, Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository gates; pushed and reconciled the bilingual plan and implementation commits.

## Remaining

Multiple `durl` segments and ordered FLV concatenation, transcoding/codec repair, CDN ranking/racing/cross-run cache, fresh-detail refresh after mixed/non-auth exhaustion, subtitles/danmaku, pages above 64, bangumi/paid/live media, broader platform shapes, REST/production packaging and every live account/API/CDN/media-server row remain deferred or `NOT_RUN`; the broader seven-platform goal stays active.
