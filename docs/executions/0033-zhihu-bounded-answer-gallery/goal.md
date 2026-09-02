**English** | [中文](goal.zh.md)

# Execution 0033 goal

- Status: Frozen offline bounded Zhihu answer-gallery scope complete; live rows remain `NOT_RUN`
- Date: 2026-09-03
- Predecessor: Execution 0032 closeout `41508b1cc57672aa9e18252498d10d98bc371b90`
- Scope: One ordinary Zhihu answer whose HTML carries 2–64 ordered static images, captured at the pinned extractor boundary and delivered as a bounded sibling-bound IMAGE gallery
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Outcome

1. Extend the pinned Zhihu extractor shim so an ordinary answer with exactly one image keeps the 0019 v1 capture byte-compatible, while 2–64 ordered images — each selected through the frozen `data-original` → `data-actualsrc` → `src` attribute priority, statically valid and pairwise distinct — capture one complete ordered tuple; any forbidden-media drift, invalid or duplicated image, or a gallery above 64 captures nothing.
2. Carry the tuple under one new private v2 field with strict collision checks against the v1 field, recursive stripping before persistence, and normalizer materialization of ARTICLE with `{content_id}:image:0..N-1` IMAGE assets.
3. Bind the lazy adapter refresh to the complete persisted sibling tuple: the refresh context carries the ordered query-free hints, one exact canonical-answer detail run re-resolves each position's current URL in memory, and any missing, added, reordered, replaced, duplicated or malformed drift closes as `locator_refresh_schema_changed`.
4. Download every position through the DEFAULT-profile candidate pass with the structural static-image gate, SHA-256 archival and deterministic Emby poster/backdrop/gallery/body/NFO/source publication, with zero-work replay.
5. Prove one production SQLite → detail refresh → mock DNS/HTTP → static probes → archive → Emby composition while every real account/API/CDN/media-server row stays `NOT_RUN`.

## Acceptance boundaries

- Exactly the frozen attribute priority and the closed zhimg static-image validator decide eligibility; the 0019 single-image semantics, forbidden-media rejection and TEXT fallback for media-less answers stay byte-compatible.
- Galleries above 64 images and mixed forbidden-media answers capture nothing rather than truncating.
- No database schema or migration; stable Asset identity does not change. `.upstream` remains read-only and untracked.

## Explicitly deferred

Articles, zvideo, animated/WebP-animated drift beyond the static gate, same-ID byte replacement, bounded creator pagination changes, richer HTML media, and every live qualification row remain outside this execution.
