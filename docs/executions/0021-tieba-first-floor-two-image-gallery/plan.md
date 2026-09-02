**English** | [中文](plan.zh.md)

# Execution 0021 plan

- Status: Executed for the frozen offline scope
- Plan date: 2026-09-02
- Predecessor: `e5d871050cdf25da1a51e2f057ba317dea2cffb1`
- Plan commit: `5095ed6e803a8a2f0a3134e756dd3e101fef10bd`
- Implementation commit: `e0fb8d572c8f5535a5495c2dfbf5b9cdf78461e7`
- Database migration: None planned

## Baseline

Execution 0020 is pushed and reconciled at `e5d8710`. Its focused implementation regression passed `368 passed in 41.18s`; the complete suite passed `1650 passed, 1 skipped in 310.82s`; Ruff, format, strict mypy, compileall, build, documentation, both upstream locks and retained-marker audits passed. The prior bounded read-only audit observed real two-image first floors without retaining bodies or query values.

## Delivery sequence

1. Add a separately versioned exact-two-image private capture while preserving the v1 single-image field and installation markers. Freeze ordered, distinct source-hint semantics and collision rejection.
2. Extend source/unit/process contracts for exact two-image capture, gather-child → parent-store carry, concurrency, recursive field stripping and single-image compatibility.
3. Normalize ARTICLE plus two ordered IMAGE Assets and extend lazy/detail refresh to positions 0 and 1 only when the complete ordered gallery matches. Reject dual private claims, duplicates, reordering, replacement and shape drift.
4. Add deterministic two-image SQLite → detail → mock DNS/HTTP → static gate → SHA-256 archive → Emby composition and query-only zero-work replay with whole-tree transient-marker audits.
5. Run focused and complete tests plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and retained-artifact audits. Update truth documents, create bilingual implementation/closeout commits, push and reconcile GitHub.

## Commit sequence

1. `5095ed6` — `docs: 启动贴吧首楼双图闭环 / start Tieba first-floor two-image pipeline`
2. `e0fb8d5` — `feat: 闭环贴吧首楼双图 / close Tieba first-floor two-image pipeline`
3. This documentation closeout commit; self SHA intentionally omitted — `docs: 收尾贴吧首楼双图闭环 / close Tieba first-floor two-image pipeline`

`.upstream` remains excluded, unmodified and clean.
