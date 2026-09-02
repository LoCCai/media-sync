**English** | [中文](goal.zh.md)

# Execution 0030 goal

- Status: Frozen offline multi-segment FLV concat scope complete; live rows remain `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0029 closeout `dbd06075eac67377a911b503de9aa609fdc30c79`
- Scope: Bounded, ordered multi-segment Bilibili progressive `durl` downloads classified as FLV, each segment structurally probed as FLV and concatenated by one fixed stream-copy ffmpeg invocation into one Emby-compatible MP4
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Outcome

1. Upgrade the strict detail process protocol to v9 and grant multi-segment FLV authority only from the closed top-level format classification plus the bounded 2–64 `durl` tuple, keeping exactly-one-segment FLV, multi-segment ordinary and DASH behavior byte-compatible.
2. Carry one repr-safe ephemeral multi-segment FLV target through the existing `{"cid", "segments"}` private bridge plus an exact `"format": "flv"` marker, with strict collision detection, recursive stripping before persistence and reconstruction only when the payload CID matches the selected page.
3. Download every segment in order into generation-scoped per-segment stores under one shared byte cap and deadline, reusing the proven candidate-pass failover, strict resume, whole-pass restart and one all-auth refresh that must return the same typed target and segment count.
4. Require each completed segment to structurally probe as exactly FLV video, then concatenate all segments with one fixed-argument, bounded concat-demuxer `ffmpeg -c copy` invocation preserving the first video and optional first audio stream, and publish only a final that probes exactly as MP4.
5. Preserve per-segment resumability after concat/final-gate failure, prevent incomplete finals from recovery, retain published-final recovery, clean all per-segment state on explicit cleanup, and never publish any raw FLV bytes.
6. Prove one real local two-segment FLV → concat → Emby composition with a failed primary and ordered backup, zero-work replay and retained-tree non-disclosure, while every real account/API/CDN/media-server row stays `NOT_RUN`.

## Acceptance boundaries

- Exactly-one-segment FLV keeps using the 0027 remux path unchanged; multi-segment ordinary keeps using the 0029 concat path unchanged; this execution only adds the bounded 2–64 multi-segment FLV shape.
- Multi-segment FLV authority comes only from the closed `durl` tuple shape plus the closed top-level format classification; URL suffixes, response MIME and downloaded bytes cannot grant it.
- Every segment must probe exactly as `video/x-flv`; mixed or non-FLV segments fail closed without publication, and the final must probe exactly as `video/mp4`.
- One ffmpeg invocation per generation, fixed argv, non-shell, bounded output, timeout and shared media byte cap; the concat list file lives only inside the confined parts directory and never survives the attempt.
- No database schema or migration; stable Asset identity and the frozen media-shape count do not change. `.upstream` remains read-only and untracked.

## Explicitly deferred

Transcoding, codec repair, FLV segment byte-level pre-concatenation, CDN ranking/racing/cross-run cache, mixed/non-auth exhaustion refresh, subtitles/danmaku, pages above 64, bangumi/paid/live media, broader platform shapes, REST/production packaging and every live qualification row remain outside this execution.
