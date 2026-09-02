**English** | [中文](progress.zh.md)

# Execution 0030 progress

- Status: Frozen offline multi-segment FLV concat scope implemented and gated; live rows remain `NOT_RUN`
- Date: 2026-09-02
- Plan commit: `e7395fb` (documentation baseline)

## Delivered

1. `ResolvedFlvSegmentsLocator` wraps exactly one `ResolvedSegmentsLocator`; the closed `ResolvedMediaTarget` union, exports and the resolver contract accept it while persistent locator v1 stays unchanged.
2. Strict detail protocol v9 grants multi-segment FLV authority only from the closed top-level format classification plus the bounded 2–64 `durl` tuple; exactly-one-segment FLV, multi-segment ordinary and DASH paths stay byte-compatible.
3. The private segments bridge carries an exact optional `"format": "flv"` marker for single-page and multipart page tuples; every existing private field still collides, stripping before persistence still recurses, and reconstruction still requires an exact payload-CID match with fail-closed drift.
4. The typed downloader branch accepts both segment target types: per-segment ordered download under one shared byte cap/deadline with the established candidate failover, per-segment exact `flv` extension probing for the FLV variant (flavor-bound resume fingerprints), one all-auth refresh that must return the same typed target and segment count, one fixed concat-demuxer `ffmpeg -c copy` invocation, exact-MP4 final gate, immutable publication, prepared-final recovery and safe failure retention.
5. Coverage: typed locator validation, protocol v9 classification, bridge marker/collisions/malformed payloads, refresh reconstruction, FLV per-segment failover/auth-drift/probe/final-gate semantics, failure retention, recovery, cleanup, and one production SQLite → failed primary → backup → two-segment FLV concat → SHA-256 MP4 → Emby replay with zero-work replay and no retained raw FLV.

## Verification snapshot

See [`verification.md`](verification.md) for the exact commands, exit codes and gate outputs.

## Not done

Transcoding, codec repair, FLV segment byte-level pre-concatenation, CDN ranking/racing/cross-run cache, mixed/non-auth exhaustion refresh, subtitles/danmaku, pages above 64, bangumi/paid/live media and every live qualification row remain deferred or `NOT_RUN`.
