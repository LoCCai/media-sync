**English** | [中文](progress.zh.md)

# Execution 0017 progress

- Status: Offline implementation and documentation closeout complete
- Last updated: 2026-09-01
- Plan commit: `9d19e7e`
- Implementation commit: `2f8dbaa` (pushed to `origin/main`

## Implemented

- [x] Exact XHS note/creator validators, XOR request boundaries and child schema v3, including decoded xsec value validation.
- [x] Exact Subscription creator-secret fallback and `max_items` projection; explicit detail override wins with zero creator-secret resolution.
- [x] Bounded isolated creator child with one configured XHS path, cleared lists, concurrency one and disabled comments/media.
- [x] Unique ordinary raw `type="normal"` IMAGE/GALLERY/all-IMAGE target gate and duplicate-target rejection.
- [x] Exact SQLite provenance, DEFAULT-profile mock HTTP, synthetic image validation, SHA-256 archive and idempotent Emby/Jellyfin output with zero-work replay.
- [x] Durable raw shape preservation with field-specific authority/query cleanup; fixed pipeline/scheduler error taxonomy.
- [x] Exact authority preflight before archive repair or lifecycle writes; valid VERIFIED replay zero-secret; non-XHS CLI option rejection.

## Verification completed

- Focused: `266 passed in 56.90s`; post-format related: `89 passed in 13.74s`.
- Complete: `1298 passed, 1 skipped in 365.73s`; only skip is the Windows-inapplicable POSIX mode-bit test.
- Final pipeline/worker regression: `52 passed in 4.57s`.
- Ruff PASS; format 234 files; strict mypy 79 sources; compileall, two upstream locks, two build artifacts, diff and retained-artifact audits PASS. No coverage run is claimed.

## Remaining

- [ ] Main thread: create/push the bilingual closeout commit and reconcile local/tracking/GitHub SHAs; the post-edit checker already passes for 84 Markdown files.
- [ ] Real XHS QR/Cookie, creator/feed/detail, CDN bytes and Emby/Jellyfin server rows remain `NOT_RUN`.
- [ ] Automatic XHS video/live-photo/animation/mixed-media, authority-expiry recovery and remaining platform/media shapes remain future work.

Execution 0017 is complete at its offline boundary; the broader user goal remains active.
