**English** | [中文](progress.zh.md)

# Execution 0029 progress

- Status: Frozen offline multi-segment ordinary `durl` scope implemented and gated; live rows remain `NOT_RUN`
- Date: 2026-09-02
- Plan commit: `9a40968` (documentation baseline)

## Delivered

1. `ResolvedSegmentsLocator` (2–64 ordered, pairwise-distinct Bilibili-profile segments) extends the closed `ResolvedMediaTarget` union, exports and the resolver contract; persistent locator v1 is unchanged.
2. Strict detail protocol v8 accepts the bounded ordered `durl` tuple; DASH keeps precedence, exactly-one-segment behavior is byte-compatible, and a top-level FLV format with more than one segment stays `_ChildUnsupportedError`.
3. One new private bridge field `__media_sync_bili_progressive_segments_v1` carries `{"cid", "segments": [{"url", "backup_urls"}...]}` for both single-page and multipart page tuples, collides with every existing private field, joins the recursive strip set, and reconstructs only when the payload CID matches the selected page.
4. `_PartStore` gained bounded per-segment roles (`bili-segment-000..063`); `cleanup_partial` discards every segment store plus the attempt-local concat script.
5. The typed downloader branch downloads segments in order under one shared byte cap/deadline, requires per-segment exactly-MP4 structural probing, allows one all-auth refresh that must return the same segment count, runs one fixed concat-demuxer `ffmpeg -c copy` invocation with a relative-name script inside the confined parts directory, gates the final on exactly-MP4 probing, publishes immutably and preserves prepared-final recovery.
6. `FFmpegStreamCopyMuxer.concat` adds the closed concat-demuxer argv with input/output identity, size and bounded-output checks.
7. Coverage: locator bound/distinctness, concat argv/list/identity/failures, per-segment failover/auth-drift/budget/probe/failure-retention/recovery/cleanup, bridge reconstruction/collisions/malformed payloads, protocol-v8 child compositions and one production SQLite → failed primary → backup → two-segment concat → SHA-256 archive → Emby replay.

## Verification snapshot

See [`verification.md`](verification.md) for the exact commands, exit codes and gate outputs.

## Not done

Multi-segment FLV concatenation/remux, transcoding, CDN ranking/racing/cross-run cache, mixed/non-auth exhaustion refresh, subtitles/danmaku, pages above 64, bangumi/paid/live media and every live qualification row remain deferred or `NOT_RUN`.
