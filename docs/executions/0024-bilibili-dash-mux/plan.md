**English** | [中文](plan.zh.md)

# Execution 0024 plan

- Status: Executed for the frozen offline scope
- Plan date: 2026-09-02
- Predecessor: `d4c9941d2d5fb1206cd9b1a60ce2cc344a9e66e3`
- Plan commit: `a7d038e383c76f2c29825c6f42ac7ff29b967693`
- Implementation commit: `12314b927dcaac97dc9ae184c03f98153f3ef687`
- Database migration: None required or added

## Baseline and audit

Execution 0023 is clean and reconciled at `d4c9941`. Its protocol v4 resolves exactly one progressive `durl` per current CID, downloader lifecycle owns one resumable file per Asset generation, finalization recovers an already-published immutable blob, and Emby already publishes ordered VIDEO siblings as primary/part files. The pinned MediaCrawler client currently asks for `fnval=1`; the pinned bili-sync-up requests `fnval=4048`, models separate DASH video/audio streams including silent video, chooses quality before codec preference, and merges with ffmpeg `-c copy -strict unofficial`. Production media-sync wires ffprobe but not ffmpeg.

## Delivery sequence

1. Add closed ephemeral single-or-DASH media target types and a strict Bilibili DASH parser/selector. Carry one private target through detail JSONL normalization only in memory and recursively strip it from durable raw.
2. Version the detail child protocol, issue the exact WBI DASH request, preserve progressive fallback, validate page/CID binding and return one typed runtime target from parent refresh.
3. Add a bounded ffmpeg stream-copy mux port/implementation and extend the downloader with generation-scoped video/audio/final stores, component/final probing, combined-size limits, deterministic cleanup and published-result recovery.
4. Wire ffmpeg into pipeline and standalone asset-download composition. Fail capability preflight before durable child work when a pending Bilibili refresh VIDEO may require muxing and ffmpeg is unavailable.
5. Add source/unit/contract/integration coverage for quality/codec/audio selection, malformed responses, signed-target non-retention, audio-present and silent DASH, progressive compatibility, interrupted components, failed mux, archive-finalization recovery and deterministic Emby output.
6. Run focused and complete tests plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and retained-artifact audits; update root truth documents, create bilingual implementation/closeout commits, push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
