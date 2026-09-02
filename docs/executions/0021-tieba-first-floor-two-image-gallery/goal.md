**English** | [中文](goal.zh.md)

# Execution 0021 goal

- Status: Frozen offline scope delivered and verified; live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0020 closeout `e5d871050cdf25da1a51e2f057ba317dea2cffb1`
- Plan commit: `5095ed6e803a8a2f0a3134e756dd3e101fef10bd`
- Implementation commit: `e0fb8d572c8f5535a5495c2dfbf5b9cdf78461e7`
- Scope: Exactly two ordered static images in one ordinary Tieba creator thread first floor

## Outcome

Extend the delivered single-image Tieba ARTICLE without changing its identity or compatibility. A qualifying first floor with ordinary text and exactly two current type-3 image objects becomes one ARTICLE with two ordered IMAGE Assets at positions 0 and 1. The verified shim carries both signed locators across the pinned gather-child → parent-store loss boundary, durable state retains only distinct query-free identities, and exact canonical detail refresh reacquires both current signed locators before the existing static-byte/archive/Emby pipeline.

## Frozen acceptance boundary

1. Execution 0020 single-image private field, normalized identity, refresh and export remain compatible. The new gallery field is versioned separately; one row cannot claim both fields.
2. The media shape contains a bounded first-floor list, at least one ordinary type-0 text item and exactly two type-3 items satisfying the already frozen ten-key/scalar/host/path/query contract. Their order is the source order. Zero, one, three-or-more, other content types, duplicate durable identities or malformed items do not qualify this gallery claim.
3. Normalization retains ARTICLE and emits exactly `<note_id>:image:0` and `<note_id>:image:1`. Private fields and signed queries are recursively absent from raw, SQLite and retained artifacts.
4. Refresh accepts only positions 0 or 1 for the exact two-image ARTICLE, revalidates canonical parent/child authority, requires the complete ordered gallery and matching query-free hint, then returns the current signed URL with credential-free DEFAULT profile. Reordering or replacement fails closed.
5. Both images automatically use the bounded static structural gate and deterministic Emby gallery layout. A two-image composition must prove exact downloads, SHA-256 archives, poster/backdrop/two gallery files/body/NFO/source output and zero-work query-only replay.

## Explicit exclusions

Three-or-more images, media replacement semantics, mixed image/video/voice/emoji/link/rich-card content, replies/comments media, alternate image authorities, retained real response fixtures and every authenticated/live platform/CDN/Emby/Jellyfin row remain deferred or `NOT_RUN`. This slice does not mean complete Tieba gallery or media support.
