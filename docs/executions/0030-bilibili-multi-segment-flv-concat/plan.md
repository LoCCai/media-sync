**English** | [中文](plan.zh.md)

# Execution 0030 plan

- Status: Executed and verified
- Plan date: 2026-09-02
- Predecessor: `dbd06075eac67377a911b503de9aa609fdc30c79`
- Database migration: None planned
- Plan commit: `e7395fb41a4c11cd59548bd0f95f7bc2d5b5b04e`
- Implementation commit: `564f80f7dca04ee5a8acb79797833238fb376004`

## Baseline and audit

Execution 0029 is clean, pushed and reconciled at `dbd0607`. The strict v8 detail path accepts bounded ordinary multi-segment `durl` tuples and closes a top-level FLV format with more than one segment as unsupported; the typed downloader branch requires per-segment exactly-MP4 probing and one fixed concat invocation. `FFprobeMediaProbe` already allowlists FLV video, `FFmpegStreamCopyMuxer.concat` already accepts the concat-demuxer form, and the per-segment `_PartStore` roles plus attempt-local script handling are in place.

The pinned MediaCrawler downloader still selects one `durl` entry; the pinned bili-sync-up analyzer still selects `durl[0]` only. Both checkouts stay read-only design evidence. Baseline gates recorded before implementation: 0029 focused regression `447 passed in 70.97s`, complete `1902 passed, 1 skipped in 409.85s`, Bilibili compositions `5 passed in 10.93s`, Ruff/format clean, strict mypy clean, docs (260 files) and upstreams (2 locked checkouts) passing.

## Delivery sequence

1. Add a repr-safe ephemeral `ResolvedFlvSegmentsLocator` wrapping one `ResolvedSegmentsLocator`; extend the closed runtime union, exports and resolver contract without changing persistent locator v1.
2. Upgrade the detail protocol to v9: a bounded ordered `durl` tuple with a top-level format classifying as FLV now yields the typed FLV segments target; exactly-one-segment, multi-segment ordinary and DASH paths stay byte-compatible.
3. Extend the private bridge with an exact optional `"format": "flv"` marker inside the segments payload; keep strict collision detection against every existing private field, recursive stripping before persistence, exact payload-CID binding, and fail-closed reconstruction drift.
4. Generalize the typed downloader branch to accept both segment target types: per-segment ordered download under one shared byte cap and deadline, per-segment exact `flv` extension probing for the FLV variant, one all-auth refresh that must return the same typed target with the same segment count, one fixed concat-demuxer `ffmpeg -c copy` invocation, exact-MP4 final gate, immutable publication, prepared-final recovery and safe failure retention.
5. Add unit/contract coverage for the typed locator, protocol v9 classification, bridge marker/collisions/stripping, refresh reconstruction, per-segment failover/auth-drift/budget/probe semantics, failure retention, recovery, cleanup and backward compatibility.
6. Add a production ffmpeg/ffprobe SQLite → failed primary → backup → two-segment FLV concat → SHA-256 MP4 archive → Emby composition with zero-work replay; retain no signed URL, raw FLV segment or private marker.
7. Run focused and complete suites plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audits; update the four execution documents and root truth, then create bilingual implementation/closeout commits, push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
