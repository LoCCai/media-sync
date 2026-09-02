**English** | [中文](goal.zh.md)

# Execution 0039 goal

- Status: Frozen offline XHS multi-live-gallery scope complete; live rows remain `NOT_RUN`
- Date: 2026-09-03
- Predecessor: Execution 0038 closeout `064bdb1d4ab493ec2b31afb96a29032a8b939b2d`
- Scope: One ordinary XHS `type="normal"` note whose 2–16 `image_list` entries each carry a live photo, capturing every discarded H.264 master stream at the pinned store boundary and delivering a bounded paired IMAGE+VIDEO gallery
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Outcome

1. Extend the pinned live-photo shim with a v2 list capture: a `type="normal"` note with 2–16 images where every image carries the frozen `live_photo.stream.h264[0].master_url` shape captures the complete ordered URL tuple; any image without a valid live photo, malformed nesting or an above-bound list captures nothing.
2. Materialize `ContentKind.MIXED` with ordered `{note_id}:image:0..N-1` IMAGE and `{note_id}:video:0..N-1` VIDEO assets; the one-image 0038 shape stays byte-compatible and malformed payloads quarantine fail-closed.
3. Extend the creator-fallback `normal`-type branch to bind the exact paired gallery (equal counts, ordered positions, revalidated live URLs); any drift closes fail-closed.
4. Download every asset through the DEFAULT profile with the static-image and MP4 gates, archive under SHA-256 digests and publish deterministic Emby episodes with posters, with zero-work replay.
5. Prove contract and integration compositions while every real account/API/CDN/media-server row stays `NOT_RUN`.

## Acceptance boundaries

- Only the exact frozen nested store-input shape with all-images-live pairing grants the gallery; partial live coverage captures nothing (no silent degradation).
- The `video_url` scalar must be empty; the 0017 static, 0018/0037 video and 0038 single-live shapes stay unchanged.
- No database schema or migration; stable Asset identity does not change. `.upstream` remains read-only and untracked.

## Explicitly deferred

H.265 preference, live durations, animated image drift and every live qualification row remain outside this execution.
