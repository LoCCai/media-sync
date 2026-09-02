**English** | [中文](progress.zh.md)

# Execution 0020 progress

- Status: Frozen offline slice implemented, verified and pushed; live rows `NOT_RUN`
- Last updated: 2026-09-02
- Predecessor: `431fd855dafce502e83f74a055a4b27ae5c6f40b`
- Plan commit: `df7a38a6f9beee35c6c19336260b512ebc87ce0d`
- Implementation commit: `8a0e935624e944809af1a56b0f02186686433d95`

## Completed before implementation

- [x] Reconciled clean local `main`, `origin/main` and GitHub predecessor at `431fd855dafce502e83f74a055a4b27ae5c6f40b`.
- [x] Verified both pinned upstream locks and clean checkout worktrees: MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`, bili-sync-up `dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`.
- [x] Audited the locked Tieba `page_pc` → extractor → `TiebaNote` → gather child/parent store → JSONL path and identified the exact loss boundary: structured first-floor media is available to the extractor but only `text`/`c` survives.
- [x] Ran a bounded unauthenticated read-only current-response audit. It confirmed integer type 3, the current ten-key image item family, exact `tiebapic.baidu.com` origin and single `tbpicau` query key, including real one-image rows. No query values or bodies were retained.
- [x] Demonstrated transiently that signed and query-free requests can both return HTTP 200 JPEG while returning different byte bodies (`65,144` versus `4,262` bytes). Durable query-free identity plus pre-download signed refresh is therefore mandatory.
- [x] Passed the pre-edit focused baseline: `307 passed in 36.66s`.
- [x] Frozen the claim to one ordinary first-floor static IMAGE while keeping the thread ARTICLE. Multiple images and every other media/rich-content type remain deferred.

## Implemented

- [x] Added a source-bound contract that verifies the exact locked SHA and executes the real Tieba extractor/model/store loss boundary without changing `.upstream`.
- [x] Added strict positive thread IDs, exact canonical thread URLs, the current ten-key integer type-3 item, signed `origin_src` and query-free source-hint validators.
- [x] Added verified-checkout exact-object capture across gather-child → parent-store, nested-store-only `ContextVar`, module/marker/collision guards and scheduled creator cap hardening. `max_items=23` produces `20 + 3` detail/callback batches, no third page and no post-cap sleep.
- [x] Kept ARTICLE and added exactly one `<note_id>:image:0` IMAGE, recursively removed private state, persisted only a query-free hint, and added canonical parent/child detail authority plus credential-free DEFAULT refresh.
- [x] Enabled automatic static qualification for Tieba IMAGE. Qualified JPEG/PNG/WebP pass; GIF/APNG/animated WebP/AVIF fail; normal, recovery and takeover preparation preserve the flag.
- [x] Added deterministic SQLite → fake detail → mock public DNS/HTTP → production byte gate → SHA-256 archive → Emby poster/backdrop/gallery/body/NFO/source composition. Query-only replay adds zero work, and retained SQLite/WAL/SHM/runtime/archive/export trees contain no private field or transient token.
- [x] Passed the final focused/full/quality/build/upstream/audit gates and pushed bilingual implementation commit `8a0e935` with local, tracking and GitHub reconciliation.

## Still open

- [ ] Multiple first-floor images/gallery, video/voice/emoji/link/rich-card types, reply/comment media, alternate image authorities and media replacement semantics.
- [ ] A retained redacted real response fixture and authenticated/live Tieba qualification.
- [ ] Broader per-platform shapes and the full seven-platform product outcome.

## Verification status

- Pre-edit focused baseline: `PASS — 307 passed in 36.66s`.
- Current public response shape audit: `PASS — bounded unauthenticated read-only evidence; no values retained
- Focused implementation regression: `PASS — 368 passed in 41.18s`.
- Complete suite: `PASS — 1650 passed, 1 skipped in 310.82s`; the skip is the Windows-inapplicable POSIX mode-bit boundary
- Quality/build/upstream/audit gates
- Authenticated Tieba login/creator/detail, future real CDN bytes and real Emby/Jellyfin server

The broader goal remains active. Execution 0020 establishes a seventh-platform media slice without claiming complete Tieba media or complete seven-platform product coverage.
