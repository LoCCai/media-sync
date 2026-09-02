**English** | [中文](plan.zh.md)

# Execution 0022 plan

- Status: Executed for the frozen offline scope
- Plan date: 2026-09-02
- Predecessor: `817875bdd1902f54c72397fa7da46359fbe33207`
- Plan commit: `fbcb7cf5c642fc9da210faa5d92b6886b350a9b8`
- Implementation commit: `b6d03aa1c6705e52c2e47c63086a5b7200c208e7`
- Database migration: None planned

## Baseline

Execution 0021 is pushed and reconciled at `817875b`. Its focused regression passed `413 passed in 44.50s`; the complete suite passed `1668 passed, 1 skipped in 314.72s`; Ruff, format, strict mypy, compileall, build, documentation, both upstream locks and retained-state audits passed. v1 single-image and v2 exact-two-image semantics are frozen compatibility surfaces.

## Delivery sequence

1. Add the separate v3 3–64 image capture and shared maximum while retaining v1/v2 fields, installation markers and exact-object carry.
2. Extend normalizer contracts to reject all multi-version claims, emit one ARTICLE plus N ordered IMAGE Assets and recursively strip all three private fields.
3. Extend database lazy-refresh context and exact detail refresh from lengths 1/2 to the bounded 1–64 compatibility union while requiring the complete identity tuple.
4. Add unit/source/ingestion/refresh tests for 3, 64 and 65 images, collisions, ordering, drift and v1/v2 compatibility. Add deterministic three-image SQLite → mock detail/DNS/HTTP → static gate → SHA-256 archive → Emby composition and query-only replay.
5. Run focused and complete tests plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and retained-artifact audits. Update truth documents, create bilingual implementation/closeout commits, push and reconcile GitHub.

## Commit sequence

1. `fbcb7cf` — `docs: 启动贴吧有界静态 gallery / start bounded Tieba static gallery`
2. `b6d03aa` — `feat: 闭环贴吧有界静态 gallery / close bounded Tieba static gallery`
3. This documentation closeout commit; self SHA intentionally omitted — `docs: 收尾贴吧有界静态 gallery / close bounded Tieba static gallery`

`.upstream` remains excluded, unmodified and clean.
