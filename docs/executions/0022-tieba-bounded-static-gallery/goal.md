**English** | [中文](goal.zh.md)

# Execution 0022 goal

- Status: Frozen offline scope delivered and verified; live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0021 closeout `817875bdd1902f54c72397fa7da46359fbe33207`
- Plan commit: `fbcb7cf5c642fc9da210faa5d92b6886b350a9b8`
- Implementation commit: `b6d03aa1c6705e52c2e47c63086a5b7200c208e7`
- Scope: Three through 64 ordered static images in one ordinary Tieba creator thread first floor

## Outcome

Extend the delivered one- and two-image Tieba ARTICLE slices without changing their versioned identities. A qualifying ordinary first floor with 3–64 current type-3 image objects becomes one ARTICLE with the same number of ordered IMAGE Assets. The verified shim carries the complete signed gallery across the pinned gather-child → parent-store loss boundary, durable state retains only distinct query-free identities, exact canonical detail refresh reacquires the complete current gallery, and the existing bounded byte/archive/Emby pipeline processes every position deterministically.

## Frozen acceptance boundary

1. v1 remains exact single-image and v2 remains exact two-image. A separate `__media_sync_tieba_first_floor_gallery_v3` field represents only 3–64 images, and one row may claim exactly one versioned field.
2. The gallery maximum is 64. With the existing 4,096-character locator cap, the captured v3 URL list contributes at most about 256 KiB before JSON escaping, one quarter of the 1 MiB child watchdog line budget; normal JSONL/watchdog limits remain the final whole-record gate.
3. Every image satisfies the existing exact ten-key/scalar/host/path/query contract. Source order is Asset position and every query-free identity is distinct. 65 or more images, malformed items, duplicates, other content types and version-field conflicts fail closed.
4. Refresh binds the complete persisted identity tuple. Every requested position requires the complete current gallery with the same size, order and query-free identities; missing, added, reordered, replaced or duplicated images fail closed.
5. Offline composition proves at least three distinct static image bytes/formats, exact downloads, SHA-256 archives, poster/backdrop/N-item gallery/body/NFO/source output and zero-work query-only replay.

## Explicit exclusions

Mixed image/video/voice/emoji/link/rich-card first floors, replies/comments media, alternate image authorities, more than 64 images, replacement semantics and every authenticated/live platform/CDN/Emby/Jellyfin row remain deferred or `NOT_RUN`. This execution does not claim complete Tieba media support.
