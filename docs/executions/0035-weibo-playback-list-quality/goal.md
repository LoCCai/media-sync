**English** | [中文](goal.zh.md)

# Execution 0035 goal

- Status: Frozen offline `playback_list` quality-selection scope complete; live rows remain `NOT_RUN`
- Date: 2026-09-03
- Predecessor: Execution 0034 closeout `3cdd0fc` (push pending network recovery)
- Scope: Weibo video posts whose `media_info` carries a `playback_list` instead of the 0031 scalar `stream_url`, resolved through one closed quality preference
- Plan commit: `ecc08dab850a1e9b4007b4758e7d225f2f7aed15`
- Implementation commit: `f2f4bc91790fd0cad30a86a644920824ca03a049`

## Outcome

1. Extend the pinned Weibo store-shim video capture with a closed `playback_list` fallback: when the scalar `stream_url` is absent, a bounded 1–8-entry list is accepted where every entry's `play_info.url` validates against the 0031 closed URL validator and its optional `quality` maps into the closed preference order `1080p > 720p > 540p > 480p > 360p`; the highest-preference valid entry is captured.
2. Entries with unknown, missing or malformed quality labels and lists whose every entry is unusable capture nothing; the 0031 scalar path stays byte-compatible and takes precedence.
3. The selected URL crosses under the unchanged private `{"url"}` field with the same collision checks, recursive stripping, VIDEO normalization and per-asset WB adapter refresh.
4. Prove contract compositions through the real child (scalar precedence, list selection at each preference tier, unknown-quality and all-invalid closure) plus one integration SQLite → refresh → download → Emby replay for a list-only post.

## Acceptance boundaries

- Only the closed nested shape and the closed quality preference grant selection; URL suffixes, response MIME and downloaded bytes cannot influence it.
- Lists longer than eight entries, non-list shapes, non-mapping entries and missing `play_info` capture nothing rather than degrading silently.
- No database schema or migration; stable Asset identity does not change. `.upstream` remains read-only and untracked.

## Explicitly deferred

Mixed scalar+list precedence drift diagnostics, Dolby/Hi-Res labels, posters, durations, retweets, live/paid media and every live qualification row remain outside this execution.
