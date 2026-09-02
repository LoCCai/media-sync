**English** | [中文](goal.zh.md)

# Execution 0034 goal

- Status: Frozen offline bounded Kuaishou atlas-gallery scope complete; live rows remain `NOT_RUN`
- Date: 2026-09-03
- Predecessor: Execution 0033 closeout `e9d1fcdb8970b5a10f84e3947e1570159c9f9011`
- Scope: One ordinary Kuaishou atlas photo whose `photo.ext_params.atlas.pics` carries 1–64 ordered CDN images, captured at the pinned store boundary and delivered as a bounded IMAGE/GALLERY content with per-image adapter refresh and Emby publication
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Outcome

1. Install a pinned-store capture shim for `update_kuaishou_video` that validates exactly the frozen `photo.ext_params.atlas.pics[].cdn` shape — HTTPS, query-tolerant, fragment/userinfo/port-free, static `.jpg/.jpeg/.png/.webp` extension, 1–64 pairwise-distinct candidates — and injects it under one media-sync-owned private field; any drift captures nothing.
2. Normalize the record as `ContentKind.IMAGE` (one image) or `ContentKind.GALLERY` (2–64) with ordered `{video_id}:image:0..N-1` IMAGE assets while the optional cover keeps its 0014 COVER asset; malformed payloads quarantine fail-closed and the private field is recursively stripped before persistence.
3. Add `AssetKind.IMAGE` to the KS refresh support set so the existing per-asset adapter refresh binds each position, re-resolves its current signed URL in memory through one exact numeric-ID detail child run, and closes path drift as `locator_refresh_asset_mismatch`.
4. Download every image through the DEFAULT-profile candidate pass with the structural static-image gate, SHA-256 archival and deterministic Emby poster/backdrop/gallery/NFO/source publication, with zero-work replay.
5. Prove one production SQLite → detail refresh → mock DNS/HTTP → static probes → archive → Emby composition while every real account/API/CDN/media-server row stays `NOT_RUN`.

## Acceptance boundaries

- The atlas authority comes only from the frozen nested store-input shape; URL suffixes, response MIME and downloaded bytes cannot grant it. Ordinary video photos keep the 0014 semantics byte-compatible.
- An atlas photo's `photoUrl` video field is ignored as in the pinned crawler's image-over-video choice; the cover stays optional.
- No database schema or migration; stable Asset identity does not change. `.upstream` remains read-only and untracked.

## Explicitly deferred

Atlas captions/durations, animated drift beyond the static gate, video+image mixed Asset semantics, same-ID byte replacement, bounded creator pagination, dedicated CDN headers, and every live qualification row remain outside this execution.
