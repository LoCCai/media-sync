**English** | [中文](goal.zh.md)

# Execution 0037 goal

- Status: Frozen offline bounded XHS multi-video scope complete; live rows remain `NOT_RUN`
- Date: 2026-09-03
- Predecessor: Execution 0036 closeout `145176f8624f5c1518b6cd28cea3f9aa3d938454`
- Scope: One ordinary XHS `type="video"` note whose pinned store joins an ordered multi-video list into the scalar `video_url`, delivered as a bounded 1–16 VIDEO asset tuple with per-position adapter refresh
- Plan commit: `d858147`
- Implementation commit: `c5682e5`

## Outcome

1. Freeze the comma-joined `video_url` scalar into a bounded ordered multi-video shape: 1–16 pairwise-distinct candidates each validating as one legal `xhscdn.com` HTTP(S) URL, with the zero-or-one image companion unchanged.
2. Materialize ordered `{note_id}:video:0..N-1` VIDEO assets (plus the optional position-0 IMAGE) while records above the bound quarantine fail-closed; the 0017/0018 single-video semantics stay byte-compatible.
3. Bind the creator-fallback refresh to the complete ordered video tuple: `_validated_xhs_media_scalar` accepts the bounded list, `_validate_xhs_creator_video_target` requires the fresh assets to reproduce count, order, positions and URLs exactly, and each position re-resolves through the established detail authority with path drift closing fail-closed.
4. Download every position through the DEFAULT-profile candidate pass with MP4 probing, SHA-256 archival and deterministic Emby multi-episode publication, with zero-work replay.
5. Prove contract and integration compositions for a two-video note while every real account/API/CDN/media-server row stays `NOT_RUN`.

## Acceptance boundaries

- Only the frozen comma-joined scalar with distinct in-order candidates grants the tuple; duplicates, embedded drift, above-bound lists and schema drift quarantine or close fail-closed.
- The scheduled-ingestion URL tolerance and the image companion semantics of 0017/0018 stay unchanged; only the detail-refresh contract widens from exactly-one to the bounded tuple.
- No database schema or migration; stable Asset identity does not change. `.upstream` remains read-only and untracked.

## Explicitly deferred

Live-photo semantics, animated image drift, same-ID byte replacement, bounded creator pagination changes, dedicated CDN headers and every live qualification row remain outside this execution.
