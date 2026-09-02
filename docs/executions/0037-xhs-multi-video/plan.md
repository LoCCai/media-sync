**English** | [中文](plan.zh.md)

# Execution 0037 plan

- Status: Executed and verified
- Plan date: 2026-09-03
- Predecessor: `145176f8624f5c1518b6cd28cea3f9aa3d938454`
- Database migration: None planned
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Baseline and audit

Execution 0036 is clean, pushed and reconciled at `145176f`. The pinned XHS store joins `get_video_url_arr` into the scalar `video_url`, `_url_list` already splits it into ordered VIDEO assets during normalization, and the scheduled fixtures rely on that tolerance for non-CDN fixture hosts. The 0018 detail-refresh contract freezes exactly one video: `_validated_xhs_media_scalar` rejects `len(candidates) != 1` and `_validate_xhs_creator_video_target` requires one video asset at position 0.

Baseline gates recorded before implementation: 0036 focused regression `341 passed in 4.29s`, complete `2016 passed, 1 skipped in 370.47s`, Ruff/format clean, strict mypy clean, docs (320 files) and upstreams (2 locked checkouts) passing.

## Delivery sequence

1. Bound the normalization: `_normalize_xhs` quarantines records whose video field splits into more than 16 candidates while keeping the established tolerant parsing otherwise.
2. Widen `_validated_xhs_media_scalar` to the bounded 1–16 ordered distinct tuple and relax `_validate_xhs_creator_video_target` to bind the complete video tuple (count, positions 0..N-1, exact URL order).
3. Add unit/contract coverage: 1/2/16-video materialization and refresh binding, 17-video quarantine, replaced/reordered path drift closure.
4. Add one integration composition for a two-video note (SQLite → refresh → download both → archive → Emby with zero-work replay and non-retention).
5. Run focused and complete suites plus the full quality gate family; update the four execution documents and root truth, then create bilingual implementation/closeout commits, push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
