**English** | [中文](goal.zh.md)

# Execution 0027 goal

- Status: Complete for the frozen offline single-segment FLV-remux scope; live rows remain `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0026 closeout `245e8e377761ee8343b33f581dfcd27295eac532`
- Scope: Format-aware, bounded stream-copy remux of the already-supported exactly-one-segment Bilibili progressive `durl` FLV shape into an Emby-compatible MP4
- Plan commit: `ec7095a9cc5e85fda1aee66f256eb16345c1294a`
- Implementation commit: `7f99aa480328a25b7e9c2acc8a9c2234128e7b74`

## Outcome

1. Upgrade the strict detail process protocol to v7 and distinguish an explicitly declared FLV `durl` from the compatible ordinary progressive path without persisting format authority or signed URLs.
2. Carry one repr-safe ephemeral FLV target containing the existing ordered primary plus at most eight backups through the single-page and multipart private bridges; historical payloads without the new format marker remain compatible.
3. Download the FLV source with the proven candidate-pass, strict resume, whole-pass restart and one all-auth adapter refresh semantics, then require structural FLV probing before any remux.
4. Run fixed-argument, bounded `ffmpeg -c copy` remux preserving the first video and optional first audio stream; require final production-compatible probing and publish only the MP4 final to SHA-256 archive and Emby layout.
5. Keep the generation-scoped FLV source resumable after remux/probe failure, prevent incomplete finals from recovery, and preserve published-final recovery plus zero-work replay.
6. Prove a real local FLV → MP4 ffmpeg/ffprobe composition and retained-tree non-disclosure while keeping all real account/API/CDN/media-server rows `NOT_RUN`.

## Acceptance boundaries

- Exactly one `durl` segment remains required. Multiple segments, concatenation and per-segment ordering/size semantics are not claimed.
- FLV is detected only from the closed top-level playback format contract; URL suffixes, response MIME and downloaded bytes cannot grant FLV authority.
- The source must structurally probe as FLV video, and the final must structurally probe as MP4 video. No transcoding, codec repair, subtitle/danmaku embedding or fallback publication of raw FLV is allowed.
- Source and final bytes share the existing asset byte cap and deadline. ffmpeg output is bounded, fixed-argv and non-shell.
- No database schema or migration is planned; stable Asset identity and the twelve frozen media-shape count do not change.
- `.upstream` remains read-only and untracked.

## Explicitly deferred

Multiple `durl` segments, FLV concatenation, transcoding, CDN ranking/racing/cross-run cache, mixed/non-auth exhaustion refresh, subtitles/danmaku, pages above 64, bangumi/paid/live media, broader platform shapes, REST/production packaging and every live qualification row remain outside this execution.
