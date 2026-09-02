**English** | [中文](plan.zh.md)

# Execution 0036 plan

- Status: Executed and verified
- Plan date: 2026-09-03
- Predecessor: `5a27e99949c54a5032454d91b8809d28afad7086`
- Database migration: None planned
- Plan commit: `1ad49a7`
- Implementation commit: `72e9f62`

## Baseline and audit

Execution 0035 is clean, pushed and reconciled at `5a27e99`. The Weibo shim captures the video URL (scalar or `playback_list`) but discards `page_info.pic_info` with the rest of the flattening; the 0016 image proxy validator, the DY/KS COVER asset patterns and the platform-neutral Emby poster publication are proven. `_supported_kinds(WB)` covers IMAGE and VIDEO only.

Baseline gates recorded before implementation: 0035 focused regression `451 passed in 74.84s`, Weibo pipelines `4 passed in 2.70s`, complete `2010 passed, 1 skipped in 360.55s`, Ruff/format clean, strict mypy clean, docs (312 files) and upstreams (2 locked checkouts) passing.

## Delivery sequence

1. Add a closed `validate_weibo_poster_url` (HTTPS `sinaimg.cn`-family host, static extension, bounded path, no fragment/userinfo/port) and extend the shim's video capture with the `pic_info.pic_big.url` pass under one new private field with strict collision checks.
2. Extend `_normalize_wb` so a valid poster field materializes the `{note_id}:cover:0` COVER asset alongside VIDEO, quarantine on malformed/dual-field drift, and add the field to the recursive strip set.
3. Add `AssetKind.COVER` to the WB refresh support set so the poster re-resolves through one exact numeric-note detail child run.
4. Add unit/contract coverage for the poster matrix (valid alongside scalar and playback video, absent/malformed/foreign/animated drift, video-only fallback) and integration coverage for the two-asset SQLite → refresh → download → archive → Emby composition with zero-work replay.
5. Run focused and complete suites plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audits; update the four execution documents and root truth, then create bilingual implementation/closeout commits, push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
