**English** | [中文](plan.zh.md)

# Execution 0039 plan

- Status: Executed and verified
- Plan date: 2026-09-03
- Predecessor: `064bdb1d4ab493ec2b31afb96a29032a8b939b2d`
- Database migration: None planned
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Baseline and audit

Execution 0038 is clean, pushed and reconciled at `064bdb1`. The live shim captures only the exactly-one-image shape; multi-image live notes capture nothing and fall back. The store retains the comma-joined image URLs, so the shim only needs the per-image live tuple.

Baseline gates recorded before implementation: 0038 focused regression `355 passed in 6.92s`, detail contracts `116 passed in 80.18s`, complete `2032 passed, 1 skipped in 371.84s`, Ruff/format clean, strict mypy clean, docs (336 files) and upstreams (2 locked checkouts) passing.

## Delivery sequence

1. Extend `xhs_live.py` with the v2 list payload (2–16 per-image live URLs, all-or-nothing) under one new private field with strict collision checks.
2. Extend `_normalize_xhs` with the paired-gallery branch (equal ordered tuples, MIXED kind, empty `video_url`) and add the field to the recursive strip set.
3. Extend the creator-fallback `normal`-type branch to bind the exact paired gallery shape.
4. Add unit/contract coverage for the capture matrix (2/16 paired capture, partial/above-bound/malformed no-capture) and integration coverage for the multi-asset download → archive → Emby composition with zero-work replay.
5. Run focused and complete suites plus the full quality gate family; update the four execution documents and root truth, then create bilingual implementation/closeout commits, push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
