# Execution 0022 plan / 执行 0022 计划

- Status / 状态：Approved for execution / 已批准执行
- Plan date / 计划日期：2026-09-02
- Predecessor / 前置：`817875bdd1902f54c72397fa7da46359fbe33207`
- Database migration / 数据库迁移：None planned / 计划无

## Baseline / 前置基线

Execution 0021 is pushed and reconciled at `817875b`. Its focused regression passed `413 passed in 44.50s`; the complete suite passed `1668 passed, 1 skipped in 314.72s`; Ruff, format, strict mypy, compileall, build, documentation, both upstream locks and retained-state audits passed. v1 single-image and v2 exact-two-image semantics are frozen compatibility surfaces. / Execution 0021 已在 `817875b` 推送并核对。其专项回归通过 `413 passed in 44.50s`；完整套件通过 `1668 passed, 1 skipped in 314.72s`；Ruff、格式、严格 mypy、compileall、构建、文档、两个上游锁与保留状态审计均通过。v1 单图与 v2 精确双图语义已冻结为兼容面。

## Delivery sequence / 交付顺序

1. Add the separate v3 3–64 image capture and shared maximum while retaining v1/v2 fields, installation markers and exact-object carry. / 增加独立 v3 3–64 图捕获与共享上限，同时保留 v1/v2 字段、安装 marker 与精确对象携带。
2. Extend normalizer contracts to reject all multi-version claims, emit one ARTICLE plus N ordered IMAGE Assets and recursively strip all three private fields. / 扩展归一化合约，拒绝全部多版本声明，输出一个 ARTICLE 加 N 项有序 IMAGE Asset，并递归移除三个私有字段。
3. Extend database lazy-refresh context and exact detail refresh from lengths 1/2 to the bounded 1–64 compatibility union while requiring the complete identity tuple. / 把数据库惰性刷新上下文与精确详情刷新从长度 1/2 扩展到有界 1–64 兼容集合，同时要求完整身份元组。
4. Add unit/source/ingestion/refresh tests for 3, 64 and 65 images, collisions, ordering, drift and v1/v2 compatibility. Add deterministic three-image SQLite → mock detail/DNS/HTTP → static gate → SHA-256 archive → Emby composition and query-only replay. / 增加 3、64、65 张图片、冲突、顺序、漂移与 v1/v2 兼容的单元/源码/入库/刷新测试；增加确定性三图 SQLite → mock detail/DNS/HTTP → 静态门 → SHA-256 归档 → Emby 组合及 query 重放。
5. Run focused and complete tests plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and retained-artifact audits. Update truth documents, create bilingual implementation/closeout commits, push and reconcile GitHub. / 运行专项与完整测试，以及 Ruff、格式、严格 mypy、compileall、构建、文档、上游、diff 与保留产物审计；更新真值文档，创建双语实现/收尾提交，推送并核对 GitHub。

## Commit sequence / 提交序列

1. Plan / 计划 — `docs: 启动贴吧有界静态 gallery / start bounded Tieba static gallery`
2. Implementation / 实现 — `feat: 闭环贴吧有界静态 gallery / close bounded Tieba static gallery`
3. Documentation closeout / 文档收尾 — `docs: 收尾贴吧有界静态 gallery / close bounded Tieba static gallery`

`.upstream` remains excluded, unmodified and clean. / `.upstream` 继续排除在跟踪外、保持未修改且干净。
