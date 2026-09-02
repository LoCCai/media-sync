**English** | [中文](goal.zh.md)

# Execution 0038 goal

- Status: Frozen offline XHS live-photo scope complete; live rows remain `NOT_RUN`
- Date: 2026-09-03
- Predecessor: Execution 0037 closeout `b9c88c4afab6ba2d9d2a43efea63f63cd6cd31ca`
- Scope: One ordinary XHS `type="normal"` note whose single `image_list` entry carries a live photo, capturing the discarded H.264 master stream at the pinned store boundary and delivering one IMAGE plus one playable VIDEO
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Outcome

1. Install a pinned-store capture shim for `update_xhs_note` that validates exactly the frozen `image_list[0].live_photo.stream.h264[0].master_url` shape — one legal `xhscdn.com` HTTP(S) URL — for a `type="normal"` note with exactly one image, and injects it under one media-sync-owned private field; any drift captures nothing.
2. Materialize `ContentKind.MIXED` with one `{note_id}:image:0` IMAGE (the store-retained image URL) and one `{note_id}:video:0` VIDEO (the live stream); ordinary `normal`/`video` notes stay byte-compatible and malformed payloads quarantine fail-closed.
3. Extend the creator-fallback refresh so a live-photo target accepts the exact one-image-plus-one-video asset shape with the live URL re-resolved through the detail authority; path drift closes fail-closed.
4. Download both assets through the DEFAULT profile — static image gate for the IMAGE, MP4 probe for the VIDEO — archive under SHA-256 digests and publish the Emby episode with poster, with zero-work replay.
5. Prove contract and integration compositions while every real account/API/CDN/media-server row stays `NOT_RUN`.

## Acceptance boundaries

- Only the exact frozen nested store-input shape grants the live video; URL suffixes, response MIME and downloaded bytes cannot influence it. Notes without a live photo, with malformed nesting or above-one images capture nothing.
- The `video_url` scalar of a live note must be empty; the 0017 static and 0018/0037 video shapes stay unchanged.
- No database schema or migration; stable Asset identity does not change. `.upstream` remains read-only and untracked.

## Explicitly deferred

Multi-image live galleries, H.265 preference, live-photo duration semantics, animated image drift and every live qualification row remain outside this execution.
