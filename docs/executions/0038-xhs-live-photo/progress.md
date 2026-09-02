**English** | [中文](progress.zh.md)

# Execution 0038 progress

- Status: Frozen offline XHS live-photo scope implemented and gated; live rows remain `NOT_RUN`
- Date: 2026-09-03
- Plan commit: `650c256` (documentation baseline)

## Delivered

1. A new pinned-store shim (`xhs_live.py`) captures exactly the frozen `image_list[0].live_photo.stream.h264[0].master_url` shape for a `type="normal"` note with exactly one image, installed in both the scheduled and detail children; malformed nesting, foreign hosts, above-one images and wrong types capture nothing.
2. `_normalize_xhs` gained the frozen live branch: MIXED content with one `{note_id}:image:0` IMAGE (the store-retained URL) and one `{note_id}:video:0` VIDEO (the live stream) with an empty `video_url` scalar; malformed payloads quarantine and the private field joins the recursive strip set.
3. The creator-fallback `normal`-type branch accepts the exact one-image-plus-one-video target — the shape is unambiguous for a normal-type note — revalidating the live URL; ordinary `normal`/`video` notes stay byte-compatible.
4. Coverage: ingestion materialization and payload/shape drift matrices, refresh resolution of both assets with path-drift closure, and one production SQLite → refresh → download both → archive → Emby episode-with-poster composition with zero-work replay and durable non-retention.

## Verification snapshot

See [`verification.md`](verification.md) for the exact commands, exit codes and gate outputs.

## Not done

Multi-image live galleries, H.265 preference, live duration semantics and every live qualification row remain deferred or `NOT_RUN`.
