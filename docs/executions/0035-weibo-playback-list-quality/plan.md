**English** | [中文](plan.zh.md)

# Execution 0035 plan

- Status: Executed and verified
- Plan date: 2026-09-03
- Predecessor: `3cdd0fc`
- Database migration: None planned
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Baseline and audit

Execution 0034 is complete at `3cdd0fc` (push deferred by a transient GitHub TLS failure; retried during this execution). The 0031 Weibo video capture accepts only the scalar `media_info.stream_url`; `playback_list` posts capture nothing and fall back to TEXT. The closed URL validator, private-field plumbing, VIDEO normalization and WB VIDEO adapter refresh are unchanged and reusable.

Baseline gates recorded before implementation: 0034 focused regression `445 passed`, detail contracts `106 passed in 69.98s`, complete `2002 passed, 1 skipped in 352.79s`, Ruff/format clean, strict mypy clean, docs (304 files) and upstreams (2 locked checkouts) passing.

## Delivery sequence

1. Extend `_capture_video` in `weibo_media.py` with the bounded closed `playback_list` fallback and quality preference; keep the scalar path first and byte-compatible.
2. Add unit coverage for the selection matrix (tier precedence, unknown/missing quality, invalid URLs, above-bound lists, non-list shapes) and contract coverage through the real child for scalar precedence, list selection and closure.
3. Add one integration composition for a list-only post (SQLite → refresh → mock DNS/HTTP → MP4 probe → archive → Emby with zero-work replay and non-retention).
4. Run focused and complete suites plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audits; update the four execution documents and root truth, then create bilingual implementation/closeout commits, retry the deferred push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
