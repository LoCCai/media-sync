**English** | [中文](goal.zh.md)

# Execution 0029 goal

- Status: Frozen offline multi-segment ordinary `durl` scope complete; live rows remain `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0028 closeout `2621f6a119aac60eaf89f0195d4fbe23bd5160f0`
- Scope: Bounded, ordered multi-segment Bilibili progressive `durl` downloads classified as ordinary (non-FLV), concatenated by one fixed stream-copy ffmpeg invocation into one Emby-compatible MP4
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Outcome

1. Upgrade the strict detail process protocol to v8 and accept an ordered tuple of 2–64 progressive `durl` segments — each with one primary URL and at most eight ordered backups — only while the closed top-level format classifies the response as ordinary; multi-segment FLV stays explicitly unsupported.
2. Carry one repr-safe ephemeral multi-segment target through a new collision-checked private bridge for both single-page and multipart page tuples, strip it recursively before persistence, and keep every historical payload without the new field byte-compatible.
3. Download every segment in order into generation-scoped per-segment stores that reuse the proven candidate-pass failover, strict resume, whole-pass restart and one all-auth refresh semantics, under one shared byte cap and deadline shared across segments.
4. Require each completed segment to structurally probe as exactly MP4 video, then concatenate all segments with a fixed-argument, bounded concat-demuxer `ffmpeg -c copy` invocation preserving the first video and optional first audio stream, and publish only a final that probes exactly as MP4.
5. Preserve per-segment resumability after concat/final-gate failure, prevent incomplete finals from recovery, retain published-final recovery, and clean all per-segment state on explicit cleanup.
6. Prove one real local two-segment MP4 → concat → Emby composition with a failed primary and ordered backup, zero-work replay and retained-tree non-disclosure, while every real account/API/CDN/media-server row stays `NOT_RUN`.

## Acceptance boundaries

- Exactly one `durl` segment keeps using the existing ordinary or FLV single-segment paths unchanged; this execution only adds the bounded 2–64 ordinary multi-segment shape.
- Multi-segment authority comes only from the closed `durl` tuple shape plus the closed top-level format classification; URL suffixes, response MIME and downloaded bytes cannot grant it. A top-level FLV format with more than one segment remains `_ChildUnsupportedError`.
- Segment primaries must be pairwise distinct; every segment must probe exactly as `video/mp4`. Mixed or non-MP4 segments fail closed without publication.
- One ffmpeg invocation per generation, fixed argv, non-shell, bounded output, timeout and shared media byte cap; the concat list file lives only inside the confined parts directory and never survives the attempt.
- No database schema or migration; stable Asset identity and the frozen media-shape count do not change. `.upstream` remains read-only and untracked.

## Explicitly deferred

Multi-segment FLV concatenation/remux, transcoding, codec repair, CDN ranking/racing/cross-run cache, mixed/non-auth exhaustion refresh, subtitles/danmaku, pages above 64, bangumi/paid/live media, broader platform shapes, REST/production packaging and every live qualification row remain outside this execution.
