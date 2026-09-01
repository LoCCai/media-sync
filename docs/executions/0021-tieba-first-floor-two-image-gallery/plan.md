# Execution 0021 plan / 执行 0021 计划

- Status / 状态：Plan frozen; implementation pending / 计划已冻结；实现待执行
- Plan date / 计划日期：2026-09-02
- Predecessor / 前置：`e5d871050cdf25da1a51e2f057ba317dea2cffb1`
- Plan commit / 计划提交：`PENDING`
- Implementation commit / 实现提交：`PENDING`
- Database migration / 数据库迁移：None planned / 计划无

## Baseline / 前置基线

Execution 0020 is pushed and reconciled at `e5d8710`. Its focused implementation regression passed `368 passed in 41.18s`; the complete suite passed `1650 passed, 1 skipped in 310.82s`; Ruff, format, strict mypy, compileall, build, documentation, both upstream locks and retained-marker audits passed. The prior bounded read-only audit observed real two-image first floors without retaining bodies or query values. / Execution 0020 已在 `e5d8710` 推送并核对。其实现专项回归通过 `368 passed in 41.18s`；完整套件通过 `1650 passed, 1 skipped in 310.82s`；Ruff、格式、严格 mypy、compileall、构建、文档、两个上游锁与保留 marker 审计均通过。此前有界只读审计已观察到真实双图首楼，且未保留正文或 query 值。

## Delivery sequence / 交付顺序

1. Add a separately versioned exact-two-image private capture while preserving the v1 single-image field and installation markers. Freeze ordered, distinct source-hint semantics and collision rejection. / 增加独立版本化的精确双图私有捕获，同时保留 v1 单图字段与安装 marker；冻结有序、互异 source-hint 语义与冲突拒绝。
2. Extend source/unit/process contracts for exact two-image capture, gather-child → parent-store carry, concurrency, recursive field stripping and single-image compatibility. / 扩展源码/单元/进程合约，覆盖精确双图捕获、gather-child → parent-store 携带、并发、递归字段移除及单图兼容。
3. Normalize ARTICLE plus two ordered IMAGE Assets and extend lazy/detail refresh to positions 0 and 1 only when the complete ordered gallery matches. Reject dual private claims, duplicates, reordering, replacement and shape drift. / 归一化 ARTICLE 加两项有序 IMAGE Asset；只在完整有序 gallery 匹配时，把惰性/detail 刷新扩展到 position 0 与 1；拒绝双重私有声明、重复、重排、替换及形状漂移。
4. Add deterministic two-image SQLite → detail → mock DNS/HTTP → static gate → SHA-256 archive → Emby composition and query-only zero-work replay with whole-tree transient-marker audits. / 增加确定性双图 SQLite → detail → mock DNS/HTTP → 静态门 → SHA-256 归档 → Emby 组合及 query 零工作重放，并执行整树瞬态 marker 审计。
5. Run focused and complete tests plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and retained-artifact audits. Update truth documents, create bilingual implementation/closeout commits, push and reconcile GitHub. / 运行专项与完整测试，以及 Ruff、格式、严格 mypy、compileall、构建、文档、上游、diff 与保留产物审计；更新真值文档，创建双语实现/收尾提交，推送并核对 GitHub。

## Commit sequence / 提交序列

1. `PENDING` — `docs: 启动贴吧首楼双图闭环 / start Tieba first-floor two-image pipeline`
2. `PENDING` — `feat: 闭环贴吧首楼双图 / close Tieba first-floor two-image pipeline`
3. `PENDING` — `docs: 收尾贴吧首楼双图闭环 / close Tieba first-floor two-image pipeline`

`.upstream` remains excluded, unmodified and clean. / `.upstream` 继续排除在跟踪外、保持未修改且干净。
