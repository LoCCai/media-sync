**English** | [中文](plan.zh.md)

# Execution 0038 plan

- Status: Executed and verified
- Plan date: 2026-09-03
- Predecessor: `b9c88c4afab6ba2d9d2a43efea63f63cd6cd31ca`
- Database migration: None planned
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Baseline and audit

Execution 0037 is clean, pushed and reconciled at `b9c88c4`. The pinned XHS store flattens `image_list` to a comma-join of image URLs and discards the nested `live_photo` streams; `update_xhs_note(note_detail)` receives the full raw API note, so a Weibo-style boundary shim can capture them. The 0017 `normal`-type creator branch accepts only all-IMAGE targets and the 0018/0037 `video`-type branch freezes the `video_url` scalar tuple.

Baseline gates recorded before implementation: 0037 focused regression `344 passed in 6.32s`, complete `2020 passed, 1 skipped in 370.56s`, Ruff/format clean, strict mypy clean, docs (328 files) and upstreams (2 locked checkouts) passing.

## Delivery sequence

1. Add the capture shim: one private field carrying the exact live `master_url`, checkout-verified modules, marker-safe reinstall and collision checks, installed in both children.
2. Extend `_normalize_xhs` with the frozen live branch (MIXED, one IMAGE plus one VIDEO, empty `video_url`, exactly one image) and add the field to the recursive strip set.
3. Extend the creator-fallback `normal`-type branch to accept the exact one-image-plus-one-video target when the live field is present, revalidating the live URL.
4. Add contract coverage through the real child (capture, drift closure, video-only compatibility) and integration coverage for the two-asset download → archive → Emby composition with zero-work replay.
5. Run focused and complete suites plus the full quality gate family; update the four execution documents and root truth, then create bilingual implementation/closeout commits, push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
