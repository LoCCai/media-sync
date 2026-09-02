**English** | [中文](progress.zh.md)

# Execution 0035 progress

- Status: Frozen offline `playback_list` quality-selection scope implemented and gated; live rows remain `NOT_RUN`
- Date: 2026-09-03
- Plan commit: `ecc08da` (documentation baseline)

## Delivered

1. `_capture_video` gained the bounded closed `playback_list` fallback: when the scalar `stream_url` is absent, a 1–8-entry list is scanned with the closed quality preference `1080p > 720p > 540p > 480p > 360p`, every candidate URL revalidates against the 0031 closed validator, and the highest-preference valid entry is captured; the scalar path stays first and byte-compatible.
2. Unknown or missing quality labels, invalid URLs, above-bound lists and wrong shapes capture nothing; the selected URL crosses under the unchanged private `{"url"}` field with the same normalization and WB VIDEO adapter refresh.
3. Coverage: real-child contract compositions for highest-quality selection and closure on unusable shapes (unknown/missing quality, invalid URL, nine entries, wrong type), plus integration compositions proving a playback-sourced post normalizes, downloads, archives and publishes to Emby exactly like the scalar shape with zero-work replay and durable non-retention.

## Verification snapshot

See [`verification.md`](verification.md) for the exact commands, exit codes and gate outputs.

## Not done

Dolby/Hi-Res labels, posters, durations, retweets, live/paid media and every live qualification row remain deferred or `NOT_RUN`.
