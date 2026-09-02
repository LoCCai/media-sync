**English** | [中文](goal.zh.md)

# Execution 0032 goal

- Status: Frozen offline bounded Douyin note-gallery scope complete; live rows remain `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0031 closeout `2e9e3b5378dd8966f56e068dced5f799e115f92b`
- Scope: One ordinary numeric-ID Douyin note whose pinned store joins an ordered note-image list into the scalar `note_download_url`, delivered as a bounded IMAGE/GALLERY content with per-image adapter refresh, static probing and Emby publication
- Plan commit: `286dac9b78710c8fd99e9ec8f260d0fac6d4f5ac`
- Implementation commit: `95758c2e6b3623a02f3a035590934da816e3cc6f`

## Outcome

1. Freeze the pinned comma-joined `note_download_url` shape into a strict all-or-nothing ordered parser: every candidate must be one valid query-free-or-signed HTTP(S) URL without embedded commas, duplicates collapse closed, and the frozen gallery bound is 1–64 images.
2. Materialize `ContentKind.IMAGE` for exactly one image and `ContentKind.GALLERY` with ordered `{aweme_id}:image:0..N-1` IMAGE assets for 2–64, while any embedded-comma drift, non-string item, invalid URL, duplicate candidate or gallery above 64 quarantines fail-closed instead of silently dropping items.
3. Keep the 0015 semantics byte-compatible: an empty or absent `note_download_url` still falls through to the video/audio/text shapes, and the video/music/cover fields keep their established tolerant parsing.
4. Qualify the existing per-asset adapter refresh for gallery positions: one exact numeric-ID detail run re-resolves each position's current signed URL in memory, and path drift closes as `locator_refresh_asset_mismatch`.
5. Download every gallery image through the DEFAULT-profile candidate pass with the structural static-image gate (JPEG/PNG/WebP only), SHA-256 archival and deterministic Emby poster/backdrop/gallery/NFO/source publication, with zero-work replay.
6. Prove one production SQLite → detail refresh → mock DNS/HTTP → static probes → archive → Emby composition while every real account/API/CDN/media-server row stays `NOT_RUN`.

## Acceptance boundaries

- Exactly the scalar comma-joined store field is the gallery authority; list-shaped payloads are accepted only as the JSON-frozen equivalent of the same ordered shape.
- Mixed image+video notes follow the pinned crawler's choice of images, as in 0015; the video URL of an image note is still ignored as a potential audio stream.
- No database schema or migration; stable Asset identity does not change; the frozen media-shape family gains the bounded Douyin gallery shape. `.upstream` remains read-only and untracked.

## Explicitly deferred

Video+image mixed Asset semantics, associated music for galleries, animated/WebP-animated drift beyond the static gate, same-ID byte replacement, bounded creator pagination, dedicated CDN headers, cleanup-failure quarantine, and every live qualification row remain outside this execution.
