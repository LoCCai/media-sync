**English** | [中文](progress.zh.md)

# Execution 0021 progress

- Status: Frozen offline scope and documentation closeout complete
- Last updated: 2026-09-02
- Predecessor: `e5d871050cdf25da1a51e2f057ba317dea2cffb1`
- Plan commit: `5095ed6e803a8a2f0a3134e756dd3e101fef10bd`
- Implementation commit: `e0fb8d572c8f5535a5495c2dfbf5b9cdf78461e7`

## Completed

- [x] Closed and reconciled Execution 0020 with a clean worktree.
- [x] Reused the prior bounded read-only evidence that current public responses contain real two-image first floors; no body, personal data or signed query value is retained.
- [x] Frozen this execution to exactly two ordered static images while preserving the single-image slice.
- [x] Added the mutually exclusive `__media_sync_tieba_first_floor_images_v2` capture while retaining the v1 single-image field and install markers. Exact source order, distinct durable identities, three-image rejection, exact-object carry and concurrent isolation pass.
- [x] Normalized one ARTICLE plus positions 0/1 IMAGE Assets, recursively removed both private fields, and persisted only query-free hints.
- [x] Bound lazy refresh to the complete persisted ordered gallery. Both positions refresh under canonical thread authority and DEFAULT profile; missing, reordered, replaced, duplicated or dual-claimed galleries fail closed.
- [x] Proved two downloads, JPEG/PNG static gates, two SHA-256 archives, Emby poster/backdrop/two gallery files/body/NFO/source output, retained-marker absence and query-only zero-work replay.
- [x] Pushed implementation `e0fb8d5`; local, tracking and GitHub `main` reconciled.

## Verification complete

- [x] Focused regression: `413 passed in 44.50s`.
- [x] Complete suite: `1668 passed, 1 skipped in 314.72s`; the skip is the Windows-inapplicable POSIX mode-bit boundary.
- [x] Ruff, format, strict mypy, compileall, wheel/sdist build, docs, both upstream locks/worktrees and Git/diff audits pass.

## Remaining

Three-or-more images, mixed/rich first-floor media, replies/comments media, replacement semantics and all authenticated/live platform/CDN/Emby/Jellyfin rows remain deferred or `NOT_RUN`. The broader goal remains active.
