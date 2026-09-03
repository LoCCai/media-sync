**English** | [中文](goal.zh.md)

# Execution 0043 goal

- Status: Planned — start record committed for review before implementation
- Date: 2026-09-03
- Predecessor: Execution 0042 (completion archive)
- Scope: Bilibili danmaku (XML → ASS) and closed-caption subtitle sidecars downloaded beside the episode media and published into the Emby tree, replicating bili-sync-up's sidecar coverage for the already-supported Bilibili shapes

## Outcome (target)

1. The detail protocol gains a bounded, closed danmaku/subtitle metadata read for the already-authorized play-page payload; signed CDN URLs stay runtime-only.
2. Danmaku XML is converted to ASS with a fixed rule set (font, size, roll/static lanes, bounded count) and subtitles are kept in their native format; both are written beside the episode as same-stem `.ass`/`.srt` sidecars inside the Emby layout.
3. Downloads traverse the same signed-URL, byte-cap and archive discipline as media; sidecars are derived artifacts, not versioned Assets, so the frozen media-shape count does not change.
4. Zero-work replay and recovery behavior extend to sidecars without new database schema.

## Acceptance boundaries

- Only Bilibili shapes already delivered (progressive/DASH/FLV, 1–64 pages); no bangumi/live.
- Offline fixtures only; every live API/CDN row `NOT_RUN` (operator, execution 0047 or deployment host).
- Full suite plus new tests run on the Linux deployment host; no local deployment verification.

## Explicitly deferred

Danmaku styling configuration, subtitle translation/merging, other platforms' danmaku.
